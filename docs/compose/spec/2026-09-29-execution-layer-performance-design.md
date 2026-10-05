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
| `export.py` | **C-4（2026-09-29 基线后经用户决策追加）**：`_load_and_transform` 的数据来源 |

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

### C-4 导出复用 execute_report（基线后追加 · 2026-09-29）

**触发**：§10.2 第 2 条。导出 S7 的 1519.7ms 是全站最大热点（第二名的 15 倍），
根因是 `export.py:73-81` 的 `_load_and_transform` 直接
`db.create_mysql_connection()` + `db.execute_mysql_query()`，
**完全不经过 L1 `QueryCache` / L2 Redis / L3 静态缓存**。

**佐证这不是特例而是异类**：`api_handler.py:454` 的 API 路径**已经在调用
`report.execute_report`**（走缓存 + 分页）。只有导出绕开了。让导出复用
`execute_report` 是回到「单一实现来源」，而非新增机制。

**改法**：`handle_export` 把已有的 `report_id` 与 `report_config` 向下传给
`_load_and_transform` → `export_report_to_csv` / `export_report_to_json`；
`_load_and_transform` 改为调用 `report.execute_report(...)` 取数，
不再自己建连接查 MySQL。

**关键风险控制 —— 不修改 `execute_report`**：本段只**调用** `execute_report`，
一行都不改它。Redis 契约全部留在原函数内，不受本次改动影响。

调用形态要点：

| 参数 | 取值 | 理由 |
|------|------|------|
| `report` | `report_config` | 必须传，否则 `limit_rows` 恒为 False，**全量输出护栏失效**（安全回归） |
| `page` / `page_size` | `1` / `_EXPORT_ALL_ROWS_PAGE_SIZE = 2**31 - 1` | 导出要全量行；Python 切片对超大 stop 自动截到末尾，10 亿行以上的报告不可能存在 |
| `active_index` | `result_index` | 多结果集时取用户选中的那个 |
| `filters` / `sorts` / `nested_filter` | 原样透传 | 三个 transform 函数本来就是共用的，不重复实现 |
| `read_timeout` | 不传（None） | 与现状一致（导出不设查询超时） |
| `refresh` / `force_rebuild` | 不传（False） | 导出沿用既有缓存，不主动失效 |

**语义等价性核对**（改前逐条确认，改后由测试锁定）：

1. **max_rows 护栏** —— 导出的 `export_limit` 条件
   （`allow_all_output=0` 且 `max_rows>0`）与 `execute_report` 的 `limit_rows`
   条件**字面相同**。差别只在 `execute_report` 对**每个**结果集截断、导出只对
   选中那个截断——对导出的输出而言结果一致。截断标记改从
   `ReportResult.truncated` 取，驱动既有的 `# 注意：查询结果超过 N 行上限`
   尾注与 `X-Export-Truncated` 响应头。
2. **写护栏** —— `handle_export` 自己的 403 判定在调用之前，导出根本到不了
   `execute_report`；`execute_report` 的 `PermissionError` 分支在此路径不会被触达。
3. **缓存副作用** —— `allow_all_output=0` 的报表，导出经 `execute_report` 后
   写入的截断快照与报表页写入的是同一份。**这不是新增污染，而是让导出的缓存
   行为与页面一致**（改前导出截断完全不落缓存，两条路径行为分叉）。
4. **多结果集越界** —— 现状 `if result_index >= len(results): result_index = 0`；
   `execute_report` 内部已做同样的 clamp，取 `results[result_index]` 即可。

**预期收益**：热导出 1519.7ms → 约 286ms（transform 15.1 + 行投影 64.2 +
`rows_to_csv` 207.0），约 **5.3 倍**。行投影与 CSV 序列化不动（`rows_to_csv` 是
三处共用的统一实现，见 AGENTS #3）。

## 6. 验证策略


### 6.1 Redis 契约守卫

1. **现有测试必须全绿**：`tests/test_redis_cache*.py`、`tests/test_query_cache.py`、`tests/test_cache_ui.py`、`tests/test_report*.py`、`tests/test_export*.py`、`tests/test_api*.py` —— 这些是 Redis 缓存契约的既有守卫
2. **压测每轮断言 `cache_info.source` 分布**符合预期：冷请求 → `mysql`，二次请求 → `redis`，数据源故障 → `redis_fallback` ——（2026-10-05 精确化为三态：冷请求 `mysql`；300s 内二次请求命中 L1 → `process`；L1 过期后命中 L2 → `redis`。见 `2026-10-05-cache-source-label-design.md`）
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
| C-4 | 导出输出与改前不一致（行数/顺序/截断标记）；全量输出护栏被绕过 | 任何一条语义等价性核对项不成立即弃用整段，回滚到自带连接的实现。**护栏失效是安全问题，不是性能问题，必须立即回滚** |
| 全部 | 渲染（`render.py`）成为新瓶颈 | **超出本任务范围**，需回到用户重新确认是否扩展到 UI 层 |

## 8. 知识库同步义务

按硬性约束 #7，代码落地后必须在同一次任务内同步更新：

| 变更 | 至少更新 |
|------|----------|
| `result_transform.py` 的 transform 内部实现 | `docs/compose/knowledge/03-report-transform.md` |
| `query_executor.py` 连接获取方式 | `docs/compose/knowledge/01-architecture.md` |
| `report.py` 缓存判定链 | `docs/compose/knowledge/07-cache-scheduler-audit.md` |
| `export.py` 改为走 `execute_report`（C-4） | `docs/compose/knowledge/03-report-transform.md`（导出的数据来源与缓存关系） |
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
| **C-4 导出复用 `execute_report`** | ✅ 采纳（范围追加） | 基线测出导出 1519.7ms 为全站最大热点（第二名 15 倍），根因是绕过三层缓存。用户 2026-09-29 决策纳入范围。API 路径已在用 `execute_report`，导出复用它是回到单一实现来源 |
| C-4 只修缓存绕过、不动 CSV 序列化 | ⚠️ 部分采纳 | `rows_to_csv` 是导出/API/审计页三处共用的统一实现，改它会波及三处；且它只占导出的 13.5%，收益主要来自缓存复用 |
| C-4 重构 `execute_report` 抽出取数函数 | ❌ 否决 | 会动到 Redis 契约所在的函数，回归面与本任务「不动 Redis 语义」的硬约束相悖。C-4 只**调用** `execute_report`，不修改它 |

## 10. 执行记录

### 10.1 Phase 0 基线（已冻结 · 2026-09-29）

采集条件：git `02a95a1`（优化前）· DEBUG 服务端口 1000 · MySQL 127.0.0.1:3307
`sqlreport_test` · Redis 127.0.0.1:6379 前缀 `sr_debug` · 每场景 1 次预热 + 20 次取
P50/P95 · 数据量 `perf_text` 10 万行 / `perf_wide` 5 万行 / `perf_multi_*` 各 2 万行 /
`big_table` 20 万行。

| 场景 | 说明 | 预热(冷) | P50 | P95 | cache_info.source |
|------|------|---------|-----|-----|-------------------|
| S1 | 报表首屏 10万行（`prefer_cache=0`） | 1324.3ms | **15.6ms** | 22.5ms | 预热 mysql → 正式 process |
| S2 | 翻页 page=2..21（无筛选无排序） | 15.3ms | **15.1ms** | 20.1ms | process |
| S3 | 排序 amount 降序 | 84.4ms | **76.1ms** | 96.6ms | process |
| S4 | 数值筛选 amount>100 | 97.1ms | **95.3ms** | 121.0ms | process |
| S5 | Redis 快照路径（`prefer_cache=1`） | 1465.6ms | **14.5ms** | 20.6ms | 全部 redis |
| S6 | API JSON 端点 | 6.9ms | **6.9ms** | 10.0ms | — |
| S7 | 导出 CSV | 1505.7ms | **1519.7ms** | 1596.3ms | — |
| S8 | 配置页 | 21.6ms | **12.6ms** | 16.1ms | — |
| S9 | **排序后翻页**（C-3 主战场） | 95.5ms | **73.0ms** | 88.0ms | process |
| S10 | **筛选后翻页**（C-3 主战场） | 94.8ms | **100.8ms** | 124.9ms | process |
| S11 | 宽表 30 列 × 5万行 | 1710.1ms | **15.1ms** | 20.9ms | process |
| S12 | 多结果集（3 个结果集） | 538.8ms | **12.9ms** | 19.1ms | process |

原始数据：`perf-logs/baseline-1790691445.json`（`perf-logs/` 已 gitignore）。

> 注（2026-10-05）：上表 S5 行的「全部 redis」是修复前的**旧实现账本式标注**（MySQL 查询成功即标
> `redis`）。本次修复后 S5 期望为预热 `mysql` → 正式 20 次 `process`（命中 L1）。历史数值本身不改。

### 10.2 基线暴露的关键事实（修正了本 spec 的两处判断）

1. **普通翻页没有 transform 成本。** S2 的 15.1ms 与 S1 的 15.6ms 几乎相同，
   因为无筛选无排序时 `filter_rows`（`result_transform.py:181`）与 `sort_rows`
   （`:200`）都直接早返回原列表。**§5 C-3 原先把「翻页」当主战场是不准确的**：
   真正的成本在**已排序/已筛选的报表再翻页**——S9 73.0ms、S10 100.8ms。
   C-3 的设计（挂在 `CachedResult` 上、只缓存 filter+sort 结果）依然成立且更有价值，
   但验收场景应盯 S9/S10 而非 S2。

2. **导出完全绕过三层缓存，是全站最大热点。** S7 的 1519.7ms 是第二名（S10）的
   15 倍。分解实测（进程内，同一 SQL）：

   | 阶段 | 耗时 | 占比 |
   |------|------|------|
   | MySQL 连接建立 | 113.5ms | 7.4% |
   | `execute_mysql_query` 取 10 万行 | 1151.4ms | 74.9% |
   | 行投影 | 64.2ms | 4.2% |
   | `rows_to_csv` 序列化 | 207.0ms | 13.5% |
   | **合计** | **1536.3ms** | 对得上实测 1520ms |

   根因：`export.py:73-81` 的 `_load_and_transform` 直接
   `db.create_mysql_connection()` + `db.execute_mysql_query()`，
   **完全不经过 L1 `QueryCache` / L2 Redis / L3 静态缓存**。
   若改为走缓存，热导出可降到约 286ms（15.1 + 64.2 + 207.0），约 **5.3 倍**。

3. **10 万行取数的 ~1150ms 是驱动地板，不可压缩。** 对照实验：
   dict 游标比 tuple 游标慢约 15%；`buffered=True` 相比现状仅快 2~4%。
   报表热路径当前已是 tuple 游标。**因此「消除 `_MySQLRow` 每行包装」对本热路径
   不成立**——该包装只发生在配置库路径（`_MySQLConnection`），不在报表取数路径上。

4. **MySQL 连接建立 113.5ms/次是真实成本**（§5 C-2 的收益依据）。在 10 万行场景
   占 8.5%，但在**缓存未命中的小查询场景是主要成本**。C-2 保留。

### 10.3 C-1 实施结果（T1–T3，2026-09-29）

**语义验证（首要门槛）**：`scripts/perf/verify_transform_equivalence.py` 以
`git 02a95a1`（优化前）的 `result_transform.py` 为参考实现，在真实 10 万行数据上
比对 **43 个条件组合、2,937,000 行次，全部逐行完全一致**。任一不一致即非零退出。

**收益测量 —— 两种方法结论不同，必须分开读**：

| 方法 | 数值筛选 | 排序 |
|------|---------|------|
| 隔离 A/B（同进程、5 次重复、同数据，`git HEAD` vs 工作区） | **-27% ~ -28%** | **-7.7% ~ -11.3%** |
| 端到端 bench（20 样本 HTTP） | S4 **-17.7%**、S10 **-28.1%** | S3 +9.6%、S9 +3.7%（**噪声**） |

⚠️ **端到端测量的噪声约 ±6%**：S7 导出在本次测量中 +6.3%，而导出的压测请求
既无筛选也无排序、根本不执行被修改的代码——这 6.3% 纯属噪声。因此
**小于 ~10% 的端到端差异不可解读**；排序的收益只能以隔离 A/B 为准。

**T3 中被实测否决的一项（如实记录）**：`filter_rows` 曾改为「M 个条件编译成行
判定函数、一趟遍历同时应用」，实测**慢 41%~72%**。根因是每单元格多一层闭包函数
调用的开销，压过了省下的遍历——M 个条件链式过滤时中间列表逐级缩小，总访问量
本就不高。已按 §7 退出条件整段回退，并把该结论写进 `filter_rows` 的 docstring
以免后人重蹈。`sort_rows` 的单趟分区则实测有效，予以保留。

### 10.4 条件性模块评估（§2.1「仅在实测证明是热点时」的三个模块）

| 模块 | 对应场景 | 实测 P50 | 结论 |
|------|---------|---------|------|
| `server.py`（每请求配置库连接 + 访问审计写入） | S8 配置页 | 12.7ms | **不是热点，不优化** |
| `redis_cache.py`（快照反序列化） | S5 Redis 路径 | 13.0ms | **不是热点，不优化**（本数据量下 JSON 解析成本可忽略） |
| `config_db.py` | 同 S8 | — | **不是热点，不优化** |

结论：§2.1 的条件性范围**本轮全部不启用**。若将来数据量增长一个数量级导致
S5/S8 显著抬升，再按 §2.1 重新评估。

### 10.5 C-4 实施结果：导出复用 `execute_report`

| 指标 | 改前 | 改后 | 变化 |
|------|------|------|------|
| S7 导出 CSV **P50** | 1519.7ms | **359.2ms** | **-76.4%（4.2 倍）** |
| S7 导出 CSV P95 | 1596.3ms | 387.6ms | -75.7% |
| S7 冷路径（预热） | 1505.7ms | 396.6ms | -73.7% |

其余 11 个场景无回退；`cache_info.source` 断言（S1 预热 mysql→正式 process、
S5 全 redis）全部通过。
（2026-10-05 注：S5 的「全 redis」是旧账本式标注的产物；修复后 S5 期望改为预热 `mysql` →
正式 `process`，见 `2026-10-05-cache-source-label-design.md`。）

359.2ms 的构成与 §10.2 的预测一致：transform 13.2 + 行投影 64.2 +
`rows_to_csv` 207.0 ≈ 285ms，加上 HTTP 与配置库开销。**主导项 `rows_to_csv`
按设计未动**——它是导出/API/审计页三处共用的统一实现。

**连带修正的测试隔离问题**：导出改走 `execute_report` 后会读写进程级 L1 缓存
（`report._query_cache`，键为 `report_id`）。既有导出测试各用同一个
`report_id=1` 且 mock 的是 `db.execute_mysql_query`，导致前一个用例写入的缓存
被后一个用例读到，40 个用例失败。已在 `tests/test_export.py`、
`tests/test_output_limit.py` 的各 `setUp` 与 `tests/test_base.py` 的
`BaseReportTest.setUp` 中统一清空缓存。**这本身就是缓存生效的证据**。

### 10.6 C-2 实施结果：连接池**本环境实测无收益**（用户 2026-09-29 决策保留）

实现已落地（`_PooledConnection` + 有界池，`close()` 语义为归还），但实测
**没有收益，反而略慢**：

| 场景 | 连接池 | 全新直连 | 差异 |
|------|--------|----------|------|
| 单线程 15 次交错采样 | 83.3ms | 79.7ms | 池慢 3.6ms/次 |
| 4 并发 × 6 次（总墙钟） | 1087ms | 1060ms | 池慢 2% |
| 8 并发 × 6 次（总墙钟） | 1880ms | 1847ms | 池慢 3% |

`ping(reconnect=True)` 探活仅 **0.13ms/次**，不是开销来源。

**根因**：本机 MySQL 就在 `127.0.0.1`，直连本身很便宜。§10.2 第 4 条测到的
113.5ms 是**冷启动首次**连接（含服务端握手与首包延迟），不是稳态成本 ——
把单次冷样本当作「每次连接的成本」是本设计早期的判断错误。

**用户决策：保留**。本基准只覆盖同机部署；若生产 MySQL 是远程的
（网络 RTT 5~20ms），连接建立成本会高一个量级，连接池在那里预期有正收益。
**待验条件**：远程 MySQL 或高并发报表场景下重测；若届时仍无收益，按 §7
退出条件弃用整段。

### 10.7 附带发现：官方测试入口一直在无隔离状态下运行

排查 C-2 时实测发现（探针：`"tests" in sys.modules`）：

| 入口 | `tests/__init__.py` 是否执行 | 后果 |
|------|------------------------------|------|
| `python -m unittest discover -s tests/ -v` | ❌ **否** | 整套测试隔离全部失效 |
| `python -m unittest discover -s tests/ -t . -v` | ✅ 是 | 隔离生效 |
| `python -m unittest tests.test_x` | ✅ 是 | 隔离生效 |

`tests/__init__.py` 承载本项目**全部**测试隔离：DEBUG_CONFIG_FILE 重定向、
vendor 落点重定向、branding 库重定向，以及本次新增的 Redis 隔离。
不指定 `-t .` 时 discover 把测试模块当顶层模块导入（`test_health` 而非
`tests.test_health`），包根本不被加载。

**其中最严重的一条**：主 `app_config.json` 的 `redis.enable` 为 `true`
（db 6、key_prefix `webreport_`），因此官方全量入口下**测试进程一直在连生产
Redis 并读写真实快照**。C-4 之前导出绕过 `execute_report` 碰不到 Redis，
所以一直没暴露。

已做：在 `tests/__init__.py` 中把 Redis 配置在测试进程内一律视为「关闭」
（需要 Redis 的用例自行 patch `redis_cache.get_redis_config` 或用
`reset_redis_manager` 显式注入；实测 `test_redis_cache*` 全部 patch
`RedisConnectionManager._create_client`，从不连真实服务）。

**已落地（2026-10-05 订正）**：官方入口现已统一为 `discover -s tests/ -t . -v` ——
`AGENTS.md` 硬性 #8 与 §4 命令块均已写明，`08-testing-conventions.md` 收录该陷阱。
原「本次只记入报告并同步知识库，不改 AGENTS.md」的限制已被后续改动取代。

### 10.8 C-3 实施结果：派生态缓存（**全程最大的一笔收益**）

| 场景 | 基线 P50 | C-3 后 P50 | 变化 |
|------|---------|------------|------|
| S3 排序 amount 降序 | 76.1ms | **16.1ms** | **-78.8%** |
| S4 数值筛选 amount>100 | 95.3ms | **15.5ms** | **-83.7%** |
| S9 排序后翻页 | 73.0ms | **14.6ms** | **-80.0%** |
| S10 筛选后翻页 | 100.8ms | **13.4ms** | **-86.7%** |
| S7 导出 CSV | 1519.7ms | 375.2ms | -75.3%（C-4 所得） |
| 其余场景 | — | — | 无回退 |

读数说明：这四个场景的 20 次正式请求使用**相同的筛选/排序**（只有页码变），
第一次预热完成计算，之后全部命中派生态。这正是 C-3 设计针对的访问模式。
**首次**访问仍需 O(N) 计算（预热值 S3 86.1ms / S4 73.9ms，与基线同量级）。

实现要点：
- `CachedResult.__slots__` 新增 `derived`，值是 `{(filters, sorts, nested_filter), i} → 有序全量行列表`
- 分页切片**不缓存**，每次现算（O(page_size)，可忽略）
- 键用规范化元组：`filters`/`sorts` 转 tuple，`nested_filter` 用
  `json.dumps(sort_keys=True, default=str)`（dict 不可哈希）
- **仅在 `not skip_cache_read` 时启用**：写报表每轮数据都变、force_rebuild 是
  「先算后换」，两者复用派生态都会返回旧行序
- LRU 上限 8 组合/报表（`_DERIVED_CACHE_MAX`）
- `derived` 绝不进入序列化路径（有专项测试守）

### 10.9 Redis 缓存机制的真实验证（spec §6.1 第 4 条）

`scripts/perf/verify_redis_fallback.py`。**不停止 MySQL、不改用户的 debug 配置** ——
把数据源端口改到无人监听的 3999，产生真实连接失败（`InterfaceError`）。

| # | 场景 | 结果 |
|---|------|------|
| ① | 正常执行（真实 MySQL + 真实 Redis 写入） | `source=redis`，5 行 ✅ |
| ② | 数据源不可用 + 快照新鲜 | `source=redis`，**L2 直接命中、根本没碰数据源** ✅ |
| ③ | 数据源不可用 + 无快照 | 正确抛 `InterfaceError`，**不静默返回空/错数据** ✅ |
| ④ | L2 首读 miss + 数据源不可用 | `source=redis_fallback`、`fresh=False`、行内容与①一致 ✅ |

**一处必须说清的限定**：④ 的触发方式是「让 `get_snapshot` 第一次返回 None」的
**受控模拟**，不是真的让 Redis 掉线。原因是 `redis_fallback` 分支的本质是
**尽力而为的重读**（首读 miss → 查 MySQL 失败 → 再读一次快照），真实世界里
能稳定命中它的序列本就窄（要求两次读之间 Redis 恰好恢复）。Redis、MySQL、
快照格式与兜底逻辑都是真的，只有「首读 miss」这一步是构造出来的。

顺带修正了本 spec 早期的一处措辞：`_snapshot_is_stale` 判的是**格式版本**
（v1/v2 淘汰），**不是时效**；TTL 由 Redis 自身的 key 过期管理。

---


最后更新：2026-09-29
