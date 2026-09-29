# 执行层性能优化设计

> 状态: 生效
> 取代关系: 无（首次针对执行层性能的设计）

## 1. 背景与目标

SqlReport 的报表执行链路在数据量上升后响应明显变慢。本次任务的目标是：

1. **建立可信基线** —— 在 DEBUG 模式下用真实 MySQL 与 Redis 做端到端 HTTP 压测，量化各场景耗时，形成可复现的性能报告；
2. **逐项优化** —— 按基线数据定位热点，逐项优化并给出前后对比数据；
3. **不破坏 Redis 缓存机制** —— 这是本任务的第一硬约束，任何优化不得改变 Redis 快照的格式、键构造、TTL/保活、分布式锁与兜底语义。

成功判据：每个热点都有「同一脚本、同一数据、优化前 vs 优化后」的量化对比；不预设数字，收益多少报多少。

范围限定为**执行链路后端**，不含 `render.py` 页面渲染与前端 JS。

## 2. 范围

### 2.1 在范围内

| 模块 | 涉及内容 |
|------|----------|
| `server.py` | 请求分发、配置库连接获取、访问审计写入（仅在实测证明是热点时） |
| `report.py` | `execute_report` 缓存判定链、过滤/排序/分页循环 |
| `result_transform.py` | `filter_rows` / `sort_rows` / `_apply_single_filter` / `_parse_numeric_or_date` / `_try_float` |
| `query_executor.py` | MySQL 连接获取方式、结果行包装 |
| `redis_cache.py` | **仅在实测证明是热点时**；§3 列出的快照格式、键构造、TTL/保活、锁、兜底语义全部冻结，其余实现细节（连接管理、JSON 序列化效率）可优化 |
| `config_db.py` | 仅在实测证明是热点时 |

「冻结」约束的是**对外可观察的缓存语义**，不是整个文件不可改。改动后快照 JSON 必须逐字节一致（§6.1 第 3 条），这是判定边界。

### 2.2 不在范围内

- `render.py` 页面渲染与前端 JS 优化（用户已明确排除；按硬性约束 #11，若后续要动需先出可交互 HTML 确认稿）
- DB schema 调整、静态资源策略、缓存分层策略的整体重构
- 新增产品内的常驻性能埋点或管理端性能页（用户已明确选择「一次性脚本，不改产品」）

### 2.3 非目标

- 不追求「任何数据量下都够快」；优化目标是消除可测量的常数级浪费与重复计算
- 不引入新的 pip 依赖或框架（硬性约束 #5：纯 Python 3 标准库 + 极少量 pip 依赖）

## 3. 硬约束：Redis 缓存机制冻结

以下项在本任务中**逐字冻结**，任何优化不得触碰：

1. `ReportSnapshot` 的序列化格式与 `_SNAPSHOT_VERSION = 2`（含 v1 快照淘汰逻辑）
2. `build_snapshot_key` / `build_lock_key` / `compute_config_version` 的键构造
3. TTL 设置与 refresh-ahead 保活（先算后换）逻辑
4. SETNX 分布式锁与 `wait_for_lock` 等待语义
5. MySQL 失败时读取过期快照的兜底路径（`cache_info.source == "redis_fallback"`）
6. `cache_info.source` 的全部取值：`process` / `redis` / `mysql` / `redis_fallback`，及 `fresh` 标记

### 3.1 已否决的方案：SQL 下推

把筛选/排序/分页下推进 MySQL（`WHERE` / `ORDER BY` / `LIMIT`）理论上能把每请求的数据量从全量降到一页，是数量级胜利。**但它与本任务的硬约束直接冲突**：

L2 Redis 快照存储的是**全量未筛选未排序**的结果集，正是为了供任意筛选/排序/页码组合复用。若改为下推，快照语义变成「某个筛选组合的结果」，缓存键必须纳入 `filters`/`sorts`/`page`，缓存命中率将断崖式下跌，且 `truncated` / `max_rows` 护栏语义需要重做。

**结论：否决。** 本设计通过「保留全量快照 + 在其上做派生态缓存」达到近似收益，不改动 Redis 语义。

## 4. Phase 0：测量基础设施

所有优化判断的地基。**基线数字一旦采集即冻结**，写入本 spec 的执行记录，后续各段优化均对该组数字比较。

### 4.1 环境事实

DEBUG 配置 `app_config.debug.json` 保持原样（端口 1000、Redis 6379 已启用、`static_cache` 启用、scheduler 启用）。**造数脚本直接连接 MySQL 造表灌数，不走 debug 配置的 `test_mysql.tables`** —— 那是集成测试用的，不应被性能数据污染。

当前环境状态（开工时核实）：

- `config.debug.db` 是**空库**（连 `reports` 表都不存在），需先初始化建表 + 执行迁移，再导入报表
- 现有 `test_mysql` 表数据量过小（`big_table` 5 行、`orders` 3 行、`sales` 5 行），测不出执行层问题

### 4.2 一次性脚本（`scripts/perf/`，不进产品代码）

| 脚本 | 作用 |
|------|------|
| `seed_perf_data.py` | 连接 MySQL 3307 `sqlreport_test`，建表并灌入性能数据 |
| `init_debug_env.py` | 初始化空的 `config.debug.db`，创建性能报表并关联数据源 |
| `bench.py` | 压测，输出 JSON 明细与汇总表 |

### 4.3 性能数据集

| 表 | 规模 | 覆盖的退化模式 |
|----|------|----------------|
| `perf_text` | 10 万行，`amount DECIMAL(12,2)`，含 NULL 与混排文本 | MySQL DECIMAL 单元格解析；数值/文本分区排序；None 恒末尾 |
| `perf_wide` | 30 列 × 5 万行 | `columns.index()` 线性查找；宽表单元格字符串化 |
| `perf_multi` | 3 个结果集 | per-result-set 的 transform 循环 |
| `big_table`（沿用） | 扩到 20 万行 | 纯量级基线对照 |

### 4.4 压测场景

每场景先发 1 次预热请求（不计入统计，用于填充 L1 与连接池），再连跑 **20 次**取 P50 / P95。预热请求的耗时单独记录，用于观察冷路径代价。

| 编号 | 场景 | 路径 | 主要测量对象 |
|------|------|------|--------------|
| S1 | 报表首屏（冷） | `GET /report?id=<大表>` | MySQL 查询 + transform + 渲染 |
| S2 | 翻页 | `GET /report?id=X&page=2..20` | 纯 transform（缓存命中时） |
| S3 | 排序 | `GET /report?id=X&sort=amount:desc` | `sort_rows` |
| S4 | 数值筛选 | `GET /report?id=X&f_amount=gt:100` | `filter_rows` |
| S5 | Redis 命中 | `prefer_cache=1` 报表的二次起请求 | L2 快照读取与反序列化 |
| S6 | API | `GET /api/v1/...` | API 路径（共用 `execute_report`） |
| S7 | 导出 CSV | `GET /export?...&format=csv` | 导出路径 |
| S8 | 配置页 | `GET /config` | 每请求配置库连接与访问审计写入 |

**验收口径**：每段优化交付一张前后对比表（场景 / P50 前→后 / P95 前→后 / 提升倍数）。

## 5. 优化段

三段**独立实施、独立验证、独立可弃**，不捆绑。每段完成后重跑 `bench.py` 并更新本 spec 的执行记录。

### C-1 零语义变更优化（先做，风险最低）

| # | 位置 | 现状 | 改法 |
|---|------|------|------|
| 1 | `report.execute_report` | `sql_contains_write(sql_query)` 计算两遍（[:1064](../../report.py#L1064)、[:1071](../../report.py#L1071)） | 算一次存局部变量复用 |
| 2 | `report.execute_report` | `get_redis_manager()` 一次执行内取三次（[:1095](../../report.py#L1095)、[:1135](../../report.py#L1135)、[:1160](../../report.py#L1160)） | 统一取一次存局部变量 |
| 3 | `result_transform._parse_numeric_or_date` | 快速路径只认 `isinstance(s, (int, float))`（[:308](../../result_transform.py#L308)），MySQL `DECIMAL` 列返回 `decimal.Decimal`，**不在快速路径**，每格都要走 `str().strip()` + 正则 `_DATE_RE.match()` + `float()` | 快速路径补 `Decimal`（转 float 结果与原路径一致，零语义变更） |
| 4 | `result_transform._try_float` | 对已是 `int`/`float` 的值仍走 `try: float(val)`；文本列每格抛一次 `ValueError` 再捕获 | 增加类型快速路径，避免每格异常构造 |
| 5 | `result_transform.filter_rows` | `list(rows)` 拷贝 + 每个 filter 一次全量列表推导（M 个 filter = M+1 趟遍历 + M 份中间列表） | 合并为单趟遍历：目标 M 个 filter 只遍历 1 次、只产出 1 份结果列表 |
| 6 | `result_transform.sort_rows` | 每 sort key 4 趟：`columns.index()` + None 分离 2 趟 + `_ordered_by_column` 1 趟 | 降到单趟分区：一次遍历同时完成 None 分离、数值/文本判定与分组 |

⚠️ **第 3–6 项必须逐位保持既有语义**：数值恒在文本之前、None 恒排最后（不受升降序影响）、稳定排序保证的多字段优先级、`contains` 不区分大小写而 `eq`/`neq` 区分。这些行为有测试锁定，改错**不会报错，只会静默改变用户看到的行顺序**。

每项改完立即跑 L0：`tests.test_result_transform`、`tests.test_filter_help`、`tests.test_nested_filter`。

### C-2 MySQL 连接池

**现状**：每次缓存未命中都调用 `mysql.connector.connect()`，包含 TCP 握手与认证；`ThreadingHTTPServer` 下每请求一线程，并发时连接数无上限。

**改法**：按 `(host, port, user, database, read_timeout)` 分键的有界连接池。

⚠️ **`read_timeout` 必须进池键**。`execute_report` 的 docstring 明确区分两种场景：Web 交互路径传 30s（批次 5#18，防慢查询黑洞），调度器与 API 默认 `None` 不限制（避免超 30s 的合法重报表定时任务变成必然失败）。混池会让调度器的慢报表拿到 30s 超时的连接而**必然失败**——这是既有设计的硬区分，不可合并。

其余要点：
- 借出时 `ping(reconnect=True)` 探活，连接已死则重建
- 归还走 `try/finally`，任何异常路径都不泄漏
- 池耗尽时**降级为直连**，不因池的问题导致功能不可用
- 池上限默认 **8**（与 `ThreadingHTTPServer` 的实际并发量级匹配；超出即走直连降级），作为模块常量而非配置项 —— 避免为性能参数新增配置面

### C-3 派生态缓存

**问题**：L1 与 L2 缓存的都是**全量未筛选未排序**的数据，`execute_report` 末尾的 transform 循环（filter → nested_filter → sort → 分页切片）因此在**每次请求**都对全量 N 行重跑一遍。翻页是最高频的访问模式，而它恰恰把整个 transform 重做一次。

**核心设计决策：派生结果挂在 `CachedResult` 实例上**（新增 `derived` 字段 + LRU 上限），**不建独立的全局缓存**。

理由是**零失效逻辑**：
- L1 每次 `set` 都新建 `CachedResult` 对象 → 旧对象连同其派生态一起被回收
- L1 TTL 过期或逐出 → 派生态随之自动消失
- 不存在「底层数据已刷新但派生态还在」这种最难排查的 bug
- 派生态绝不会比 L1 活得久，严格保持现有语义（L1 TTL 内看不到别的进程经 scheduler 刷新 Redis 快照，本来就是既有行为）

**只缓存 filter + sort 的有序全量行列表，不缓存分页切片**：
- 排序是 O(N log N)、筛选是 O(N)，而分页切片只是 O(page_size) —— 切片每次现算几乎免费
- 翻页时 `filters` / `sorts` 不变、只有 `page` 变 → **命中率接近 100%**，翻页正是最热的场景
- 键极简：`(filters, sorts)`；值是一个 N 长度的指针列表，**复用原始行 tuple，不拷贝行数据**

**内存估算**：10 万行 × 8 字节指针 ≈ 800KB / 组合。LRU 上限 **8 个组合，每个 `CachedResult`（即每个报表）各自独立计数**，最坏约 6.4MB / 报表。`CachedResult` 已有 `__slots__`，新增 `derived` 字段即可。

**这是唯一有真实设计风险的一段，单独实施、单独验证**，不与 C-1 / C-2 捆绑。

## 6. 验证策略

### 6.1 Redis 契约守卫

1. **现有测试必须全绿**：`tests/test_redis_cache*.py`、`tests/test_query_cache.py`、`tests/test_cache_ui.py`、`tests/test_report*.py`、`tests/test_export*.py`、`tests/test_api*.py` —— 这些是 Redis 缓存契约的既有守卫
2. **压测每轮断言 `cache_info.source` 分布**符合预期：冷请求 → `mysql`，二次请求 → `redis`，数据源故障 → `redis_fallback`
3. **快照格式回归断言**：优化前后，同一 SQL 写入的快照 JSON 必须**逐字节相同**
4. **不止靠单测** —— 真实跑一次「MySQL 不可用 → 页面仍显示过期快照」的真实验证

### 6.2 语义守卫（C-1 专用）

第 3–6 项改完后，除 L0 外，还需在**同一份性能数据**上对比优化前后 `sort_rows` / `filter_rows` 的输出行序与行内容**完全一致**（不只是测试绿，而是真实大数据集上逐行比对）。因为这几项的错误模式是静默改变结果，不报错。

### 6.3 测试执行

按 AGENTS.md 测试策略：L0 单文件 → L1 相邻模块组 → L2 分段全量（按既定大模块顺序，不整体 discover 一把梭）。测试结果一律落盘 `/tmp/<域>-<时间戳>.log` 后 grep 取数。

## 7. 风险与退出条件

| 段 | 风险 | 退出条件 |
|----|------|----------|
| C-1 第 3–6 项 | 静默改变行序/行内容 | 该项退回原实现，只保留已验证项 |
| C-2 | scheduler 场景回归（慢查询被 30s 截断）；连接泄漏耗尽池 | 出现 scheduler 回归即弃用整段（收益有限，不值得冒险） |
| C-3 | 内存占用不可接受；派生态与 L1 生命周期脱钩 | LRU 降到 4 组合，或只对单结果集启用；无法保证生命周期脱钩则弃用整段 |
| 全部 | 渲染（`render.py`）成为新瓶颈 | **超出本任务范围**，需回到用户重新确认是否扩展到 UI 层 |

## 8. 知识库同步义务

按硬性约束 #7，代码落地后必须在同一次任务内同步更新：

| 变更 | 至少更新 |
|------|----------|
| `result_transform.py` 的 transform 内部实现 | `docs/compose/knowledge/03-report-transform.md` |
| `query_executor.py` 连接获取方式 | `docs/compose/knowledge/01-architecture.md` |
| `report.py` 缓存判定链 | `docs/compose/knowledge/07-cache-scheduler-audit.md` |
| 新增测试入口 / 压测脚本约定 | `docs/compose/knowledge/08-testing-conventions.md` |
| 掌握状态 | `learn/sqlreport-kb/course-state.md` |

`docs/compose/knowledge/INDEX.md` 路由表与共享语义表若无过时表述则不必改。

## 9. 取舍记录

| 方案 | 结论 | 理由 |
|------|------|------|
| SQL 下推筛选/排序/分页 | ❌ 否决 | 与 Redis 全量快照语义直接冲突，缓存命中率断崖，见 §3.1 |
| 逐点微优化（仅 C-1） | ⚠️ 部分采纳 | 全部停留在 O(N) 常数优化，翻页场景天花板低 |
| **C-1 + C-2 + 派生态缓存** | ✅ 采纳 | 拿到 SQL 下推的大部分收益（重复访问场景），完全不动 Redis 快照语义 |
| 产品内常驻性能埋点 | ❌ 否决 | 用户选择一次性脚本，产品面零新增，回归风险最低 |
| 产品内管理端性能页 | ❌ 否决 | 产品面新增过大，超出「执行层面」范围 |

## 10. 执行记录

> 由实施阶段回填。基线数字采集后冻结于此，后续各段对比均引用本节。

<!-- 执行时回填：Phase 0 基线数据表、各段优化前后对比、测试证据行 -->

---

最后更新：2026-09-29
