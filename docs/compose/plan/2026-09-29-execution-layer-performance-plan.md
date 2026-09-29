# 执行层性能优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> 状态: 待执行
> 对应 spec: ../spec/2026-09-29-execution-layer-performance-design.md
> 最后更新: 2026-09-29

**Goal:** 在 DEBUG 模式下建立可复现的执行层性能基线，逐项优化报表执行链路，每项给出前后对比数据，且 Redis 缓存机制逐字不变。

**Architecture:** Phase 0 先建测量基础设施（连接健康检查 → 造数 → 初始化 debug 配置库 → 压测脚本）并冻结基线；随后三段独立优化：C-1 零语义变更（去重 + transform 快速路径与单趟化）、C-2 MySQL 有界连接池、C-3 挂在 `CachedResult` 上的派生态缓存。三段各自独立可弃，不捆绑。

**Tech Stack:** Python 3 标准库 + `unittest`（项目既有测试框架，**不用 pytest**）；MySQL 测试源 127.0.0.1:3307；Redis 127.0.0.1:6379。**不引入任何新 pip 依赖。**

**Spec:** [../spec/2026-09-29-execution-layer-performance-design.md](../spec/2026-09-29-execution-layer-performance-design.md)

## Global Constraints

以下约束对**每个任务**都生效：

1. **只动执行链路后端**：`server.py` / `report.py` / `result_transform.py` / `query_executor.py` / `redis_cache.py` / `config_db.py`。**禁止修改 `render.py` 与前端 JS**（spec §2.2）。
2. **Redis 冻结清单**（spec §3）：`ReportSnapshot` 格式与 `_SNAPSHOT_VERSION=2`、`build_snapshot_key` / `build_lock_key` / `compute_config_version`、TTL 与 refresh-ahead、SETNX 锁与 `wait_for_lock`、过期快照兜底、`cache_info.source` 全部取值与 `fresh` 标记——**逐字不动**。
3. **一切测试、运行、造数、压测必须在仓库根的 `venv` 中执行**，先 `source venv/bin/activate`。禁止系统 Python。
4. **测试框架是 `unittest`**，命令形如 `python -m unittest tests.test_x -v`。**禁止用 pytest。**
5. **所有用户可感知文字用简体中文**：脚本输出、提交说明、报告、注释。
6. **禁止硬编码仓库主目录绝对路径**（AGENTS #10）。脚本用 `pathlib.Path(__file__).resolve().parents[2]` 推导仓库根。
7. **禁止修改 `app_config.debug.json` / `app_config.json`**。连接或认证失败时**立即停止并报告用户**，由用户补配置（用户 2026-09-29 明确要求）。
8. **测试段执行上限 2 次**（首跑 + 1 次收口复跑）。任何源码或测试文件变更后计数重置。**禁止第 3 次执行**。
9. **测试结果一律落盘再取数**：`python -m unittest … > /tmp/perf-<段>-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' <log>`。
10. **静态分析必须绿**：`python -m unittest tests.bug_hunt.test_static_analysis -v`。新增文件若触发 import 误报，按 `tests/bug_hunt/test_static_analysis.py` 的 `_WILDCARD_FALSE_POSITIVES` 机制登记，而不是删检查。
11. **临时产物唯一文件名、禁止 `rm`**（AGENTS #14）。
12. **两败必停**（AGENTS #12）：同一问题连续 2 次未解决即停手做根因分析，禁止第 3 次盲试。

## Review Focus

以下五类输入/失败模式是 spec 隐含、但**没有任务覆盖**、且最可能咬人的。已分别指派到拥有该代码的任务中，由该任务自己的测试钉住。

1. **MySQL `DECIMAL` 列返回 `decimal.Decimal`** —— 不在 `isinstance(s, (int, float))` 快速路径内，导致每格走 `str().strip()` + 正则 + `float()` 三连。测试库的 `orders.amount`、`sales.amount` 都是 DECIMAL，用户最常筛的就是金额列。→ **T2**
2. **混合类型列的分区顺序** —— `NULL` / 纯数字 / 数字字符串 / 纯文本混在一列时，既有语义要求「数值恒在文本前、None 恒最后（不受升降序影响）」。改错不报错，只静默换行序。→ **T3**
3. **多字段排序的稳定性** —— 按优先级从低到高依次稳定排序，同 sort key 的行必须保持原有相对次序。→ **T3**
4. **连接池归还与探活** —— 连接被 MySQL 单方面关闭（`wait_timeout`）后，池里若不探活会把死连接交给下一个请求；归还路径若不幂等会泄漏耗尽池。→ **T5**
5. **派生态缓存与 L1 生命周期的绑定** —— 底层数据已刷新而派生态仍残留，会让用户看到过期行序，且**不报错**。→ **T6**

## 文件结构

| 文件 | 责任 |
|------|------|
| `scripts/perf/check_conn.py` | 连接健康检查：MySQL 3307 + Redis 6379，**只读不建表**，失败即非零退出 |
| `scripts/perf/seed_perf_data.py` | 在 `sqlreport_test` 库建 `perf_*` 表并灌入性能数据 |
| `scripts/perf/init_debug_env.py` | 初始化空的 `config.debug.db`，建数据源与 4 张性能报表 |
| `scripts/perf/bench.py` | 压测：登录 → 跑 8 个场景 → 输出 JSON 明细与汇总表 |
| `tests/test_report_perf.py` | T1：`execute_report` 去重的调用次数断言 |
| `tests/test_result_transform_perf.py` | T2/T3：transform 快速路径与单趟化的语义等价 + 趟数计数 |
| `tests/test_mysql_pool.py` | T5：连接池的复用、归还、探活、降级 |
| `tests/test_derived_cache.py` | T6：派生态缓存的命中、失效、生命周期绑定 |

`scripts/perf/` 刻意**不放 `tests/`**：这些脚本会建表、灌数、改真实 MySQL 与真实配置库，绝不能被 `unittest discover` 触及或被维护者误当测试跑。

---

## 任务清单

### T0: Phase 0 — 连接健康检查与性能数据环境

**Files:**
- Create: `scripts/perf/check_conn.py`
- Create: `scripts/perf/seed_perf_data.py`
- Create: `scripts/perf/init_debug_env.py`
- Create: `scripts/perf/bench.py`
- Modify: `docs/compose/spec/2026-09-29-execution-layer-performance-design.md`（回填 §10 执行记录：基线数据表）

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `check_conn.py` 退出码 0 = MySQL 与 Redis 均可用；非 0 = 不可用，stderr 打印**具体失败原因与缺失的配置键名**
  - `seed_perf_data.py` 在 `sqlreport_test` 库建 4 张表（见下）
  - `init_debug_env.py` 在 `config.debug.db` 建 3 个数据源 + 4 张报表，返回打印每张报表的 `id`
  - `bench.py --out <path>` 写 JSON，结构见 Step 8

- [ ] **Step 1: 写 `scripts/perf/check_conn.py`**

按 AGENTS #10 用 `Path(__file__).resolve().parents[2]` 推导仓库根，`sys.path.insert` 后 `import app_config`。读 `app_config.get_config()` 的 `test_mysql` 段（MySQL）与 `redis` 段（Redis），分别做一次最小往返：MySQL `SELECT 1`，Redis `PING`。

关键要求：**失败信息要能直接告诉用户去 debug 配置里补什么**。例如 MySQL 连不上时打印 `test_mysql.host/port/user/password/database` 当前读到的值（password 打码）与驱动原始异常；Redis 打印 `redis.host/port/db/password` 与原始异常。不要 traceback 裸喷。

- [ ] **Step 2: 跑连接健康检查**

```bash
source venv/bin/activate && python scripts/perf/check_conn.py
```

Expected: 两行 `OK`，退出码 0。

**若失败：立即停止本任务，把失败原因报给用户，等用户补好 `app_config.debug.json` 再继续。不要自行猜测或修改配置文件（Global Constraint #7）。**

- [ ] **Step 3: 写 `scripts/perf/seed_perf_data.py` 并造数**

建表 DDL（表名以 `perf_` 前缀，便于识别与清理）：

```sql
CREATE TABLE IF NOT EXISTS perf_text (
  id INT PRIMARY KEY,
  amount DECIMAL(12,2) NULL,      -- Decimal 慢路径 + None 恒末尾
  mixed VARCHAR(32) NULL,        -- 混排：'123' / '45.6' / 'abc' / NULL → 数值/文本分区
  label VARCHAR(32) NOT NULL,
  created_at DATETIME NULL       -- 日期解析 + None 排序
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS perf_wide (
  id INT PRIMARY KEY,
  c01 VARCHAR(24) NULL, ... c30 VARCHAR(24) NULL   -- 30 列，程序生成
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS perf_multi_a (id INT PRIMARY KEY, v INT);
CREATE TABLE IF NOT EXISTS perf_multi_b (id INT PRIMARY KEY, v INT);
CREATE TABLE IF NOT EXISTS perf_multi_c (id INT PRIMARY KEY, v INT);
```

行数与分布（**必须精确，后续基线数字依赖它**）：

| 表 | 行数 | 分布 |
|----|------|------|
| `perf_text` | 100000 | `amount` 约 15% 为 NULL；`mixed` 五分之一轮换 `'123'` / `'45.6'` / `'abc'` / `''` / NULL；`created_at` 约 10% 为 NULL |
| `perf_wide` | 50000 | 30 列，值从 `'v00001'`… 轮换 |
| `perf_multi_a/b/c` | 各 20000 | 单列 `v INT` |
| `big_table`（沿用） | 扩到 200000 | 先 `TRUNCATE` 再批量插 |

造数用 `executemany` 分批提交（每批 5000 行），避免单事务过大。脚本可重复执行（幂等：先 `DROP TABLE IF EXISTS` 再建）。**追加 `--rows-scale` 参数**（默认 1.0），使将来能缩小规模快速迭代而不必改代码。

- [ ] **Step 4: 跑造数并核对行数**

```bash
source venv/bin/activate && python scripts/perf/seed_perf_data.py
```

Expected: 每张表打印实际行数；脚本自身 `assert` 行数与上表一致（一次性脚本必须自检，MEMORY Rules 4）。

- [ ] **Step 5: 写 `scripts/perf/init_debug_env.py` 并初始化**

先确认 `config.debug.db` 的现状——开工时核实它是**空库**（连 `reports` 表都没有）。脚本需：

1. 调 `config_db.init_db(conn)` 建表 + 跑迁移（`tests/integration/base.py:169` 的 `init_schema` 是现成参考）
2. 建 3 个数据源（pool），全部指向 `test_mysql` 段的同一套连接参数
3. 建 4 张报表：

| 报表 | SQL | 用途 | `prefer_cache` |
|------|-----|------|----------------|
| P1 文本/Decimal | `SELECT * FROM perf_text` | S1/S3/S4 主力，10 万行 | 0 |
| P2 宽表 | `SELECT * FROM perf_wide` | 宽表 30 列，5 万行 | 0 |
| P3 多结果集 | `SELECT * FROM perf_multi_a; SELECT * FROM perf_multi_b; SELECT * FROM perf_multi_c` | 多结果集循环 | 0 |
| P4 Redis 路径 | `SELECT * FROM perf_text` | S5 走 L2 快照 | **1**（并设 `cache_ttl_hours=24`） |

4. 打印每张报表的 `id`（`bench.py` 需要）

脚本幂等：重复执行时先按 `name` 清理同名旧报表再建。

- [ ] **Step 6: 跑初始化并确认配置库可用**

```bash
source venv/bin/activate && python scripts/perf/init_debug_env.py
```

Expected: 打印 4 个报表 id；再跑一次 `python -c` 用 `config_db.get_reports(conn)` 确认 4 张都在。

- [ ] **Step 7: 写 `scripts/perf/bench.py`**

**认证方式**：`bench.py` 从环境变量 `SR_USER` / `SR_PASS` 读登录凭据，**未设置则报错退出并提示**（禁止硬编码凭据，Global Constraint #6/AGENTS #10）。登录走 `POST /login` 取 session cookie，后续请求带上。

8 个场景（对应 spec §4.4）：

| 编号 | 请求 |
|------|------|
| S1 | `GET /report?id=<P1>` 冷路径 |
| S2 | `GET /report?id=<P1>&page=2..20`（20 次） |
| S3 | `GET /report?id=<P1>&sort=amount:desc` |
| S4 | `GET /report?id=<P1>&f_amount=gt:100` |
| S5 | `GET /report?id=<P4>` 二次起（验证 `cache_info` 显示 redis） |
| S6 | `GET /api/v1/<P4 端点>` |
| S7 | `GET /export?id=<P1>&format=csv` |
| S8 | `GET /config` |

每场景：1 次预热（不计入，单独记录冷路径耗时）+ 20 次正式，取 P50 / P95。`--out <path>` 写 JSON：

```json
{"scenarios": {"S1": {"warm_ms": 812.3, "p50_ms": 45.1, "p95_ms": 52.0, "n": 20}, ...},
 "meta": {"rows_perf_text": 100000, "ts": "2026-09-29T14:00:00", "git": "<sha>"}}
```

脚本内 `assert` 每个场景 20 次全部 HTTP 200，否则非零退出。

**还须断言 `cache_info.source` 分布**（spec §6.1 第 2 条的 Redis 契约守卫）：S1 冷路径响应里 `cache_info.source` 必须是 `mysql`；S5 二次起必须是 `redis`。报表页把 `cache_info` 渲染在页面上，`bench.py` 解析响应 HTML 取出该字段断言。分布不符即非零退出——**这比任何单测都更早发现 Redis 链路被破坏**。

- [ ] **Step 8: 起 DEBUG 服务并采集基线**

```bash
source venv/bin/activate
nohup python server.py > /tmp/perf-server-$(date +%s).log 2>&1 &
sleep 1; ls -la /tmp/perf-server-*.log    # 确认文件已建（AGENTS #16 P1）
```

轮询 `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:1000/health` 至返回 200，**上限 10 次、每次间隔 2 秒**，到顶未就绪即汇报阻塞（禁止无界循环）。

然后：

```bash
SR_USER=<debug 账号> SR_PASS=<密码> python scripts/perf/bench.py --out /tmp/perf-baseline-$(date +%s).json
```

**若登录失败或任何场景非 200：立即停止并报告用户。**

- [ ] **Step 9: 把基线冻结进 spec §10 执行记录**

把 Step 8 的 JSON 汇总表（8 场景 × P50/P95）写进 spec 的「执行记录」小节，标注 git sha 与数据行数。**此后所有优化的对比都引用这张表。**

- [ ] **Step 10: 提交**

```bash
git add scripts/perf/ docs/compose/spec/
git commit -m "perf: Phase 0 测量基础设施（连接检查/造数/初始化/压测）+ 冻结基线"
```

---

### T1: C-1a — `execute_report` 去重

**Files:**
- Create: `tests/test_report_perf.py`
- Modify: `report.py:1064-1072`（`sql_contains_write` 去重）、`report.py:1094-1160`（`get_redis_manager` 去重）

**Interfaces:**
- Consumes: T0 的成果（无代码依赖）
- Produces: 无对外新增接口。`execute_report` 签名与返回结构**完全不变**。

- [ ] **Step 1: 写失败的测试**

`tests/test_report_perf.py`，用 `unittest.TestCase`，参照 `tests/test_query_cache.py:136` 的 mock 方式（`@patch("report.db.execute_mysql_query")` + `@patch("report.db.create_mysql_connection")`）。

两个用例：

- `test_sql_contains_write_evaluated_once`：patch `report.sql_contains_write` 为 `MagicMock(return_value=False)`，调 `execute_report(report_id=1, sql_query="SELECT 1", pool_config={...}, report={"allow_write": 0})`，断言 `mock.call_count == 1`。

  **注意**：`allow_write=0` 是必要条件——`sql_contains_write` 当前只在 `allow_write=0` 时被调第二次（`report.py:1071`）；`allow_write` 为默认 1 时本来就只调一次，测不出问题。
- `test_redis_manager_fetched_once`：patch `report.redis_cache.redis_available` 返回 True、`report.redis_cache.get_redis_manager` 返回一个 `MagicMock`（`available=True`，`get_snapshot` 返回 None），调 `execute_report(prefer_cache=1 的 report)`，断言 `get_redis_manager.call_count == 1`。

- [ ] **Step 2: 跑测试确认失败**

```bash
source venv/bin/activate && python -m unittest tests.test_report_perf -v > /tmp/perf-t1-1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t1-1.log
```

Expected: `FAILED`，两个用例的 `call_count` 实际为 2（Redis 场景为 3）。

- [ ] **Step 3: 实现去重**

`report.py:1064` 处把 `sql_contains_write(sql_query)` 的结果存进局部变量（如 `_has_write`），`:1064` 与 `:1071` 两处都改用它。

`get_redis_manager()`：在 `report.py:1094-1100` 已取过一次 `mgr` 的基础上，把后续 `:1135` 与 `:1160` 的重复获取改为复用同一个局部变量。注意 `:1106`（refresh 分支）也已取过，一并复用。

**只做变量提取，不改任何控制流。**

- [ ] **Step 4: 跑测试确认通过**

同 Step 2 命令（这是本测试段第 2 次执行，符合上限）。

Expected: `OK`。

- [ ] **Step 5: 跑 L1 相邻模块组**

```bash
source venv/bin/activate && python -m unittest tests.test_query_cache tests.test_report tests.test_report_extra tests.test_max_rows tests.test_output_limit tests.test_write_guard > /tmp/perf-t1-l1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t1-l1.log
```

Expected: `OK`。

- [ ] **Step 6: 提交**

```bash
git add report.py tests/test_report_perf.py
git commit -m "perf(C-1a): execute_report 去重 sql_contains_write 与 get_redis_manager"
```

---

### T2: C-1b — transform 类型快速路径

**Files:**
- Create: `tests/test_result_transform_perf.py`
- Modify: `result_transform.py:299-321`（`_parse_numeric_or_date`）、`result_transform.py:40-54`（`_try_float`）

**Interfaces:**
- Consumes: T0 的成果（无代码依赖）
- Produces: `_parse_numeric_or_date` 与 `_try_float` 签名不变，返回值类型不变（`(num, date)` / `float | None`）。

- [ ] **Step 1: 写失败的测试**

`tests/test_result_transform_perf.py`：

- `test_decimal_bypasses_date_regex`：`from decimal import Decimal`。patch `result_transform._DATE_RE` 为一个 `match` 会 `self.fail(...)` 的 MagicMock，调用 `_parse_numeric_or_date(Decimal("123.45"))`，断言返回 `((123.45, None))` 且 `_DATE_RE.match` 未被调用。

  **当前必然失败**：`:308` 的 `isinstance(s, (int, float))` 不含 `Decimal`，会走到 `:312` 的 `_DATE_RE.match(s)`。
- `test_decimal_none_returns_none_none`：`_parse_numeric_or_date(None)` 保持 `(None, None)`。
- `test_decimal_infinity_treated_as_uncomparable`：`_parse_numeric_or_date(Decimal("Infinity"))` 必须是 `(None, None)`（与既有 NaN/Inf 处理一致，MEMORY 记录的「独立找茬中危项 #3」语义不得被绕过）。
- `test_try_float_int_avoids_float_call`：patch `result_transform.math` 不可行（内建），改为对 `_try_float(3)` 与 `_try_float(3.5)` 断言返回值，并用一个会抛异常的子类验证不依赖异常路径——具体做法：定义 `class _NoFloat(float): pass` 无法拦截，**改为直接断言返回值正确即可**，快速路径的性能收益由 T0 的 bench 验证，不在单测里断言调用次数。
- `test_decimal_gt_filter_matches_float_filter`（**Review Focus #1**）：构造 `rows = [(Decimal("10.50"),), (Decimal("200.00"),), (None,)]`，`columns=["amount"]`，断言 `filter_rows(rows, columns, [("amount", "gt", "100")])` 返回 `[(Decimal("200.00"),)]`，与同值 float 输入结果一致。
- `test_decimal_sort_order_matches_float_sort_order`（**Review Focus #1**）：Decimal 列排序结果与等价 float 列排序结果**逐行相同**。

- [ ] **Step 2: 跑测试确认失败**

```bash
source venv/bin/activate && python -m unittest tests.test_result_transform_perf -v > /tmp/perf-t2-1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t2-1.log
```

Expected: `FAILED`，`test_decimal_bypasses_date_regex` 失败（`_DATE_RE.match` 被调用）。

- [ ] **Step 3: 实现 `_parse_numeric_or_date` 的 Decimal 快速路径**

把 `:308` 的 `isinstance(s, (int, float))` 扩为包含 `Decimal`。`Decimal` 需要模块级 `from decimal import Decimal` 导入（当前 `result_transform.py` 没有）。

关键：**必须保留 `math.isfinite` 检查**——`Decimal("Infinity")` 转 `float` 得 `inf`，`isfinite` 为 False，必须走 `(None, None)`。

- [ ] **Step 4: 实现 `_try_float` 的类型快速路径**

`float(val)` 对已是 `int`/`float` 的值本就便宜，真正的浪费是**文本列每格抛一次 `ValueError`**。改法：在 `try` 之前加 `if isinstance(val, (int, float)) and not isinstance(val, bool):` 分支直接走 `isfinite` 判断并返回，跳过异常构造。`bool` 必须排除（`isinstance(True, int)` 为 True，但 `float(True)` 得 1.0——**既有代码对 bool 没有特殊处理，改为显式排除会改变语义**）。

⚠️ **因此本步只对 `int`/`float` 加速，不引入 `bool` 排除**——保持 `_try_float(True) == 1.0` 的既有行为不变。

- [ ] **Step 5: 跑测试确认通过 + L1**

```bash
source venv/bin/activate && python -m unittest tests.test_result_transform_perf tests.test_result_transform tests.test_filter_help tests.test_nested_filter tests.test_exclusion_engine > /tmp/perf-t2-2.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t2-2.log
```

Expected: `OK`。

- [ ] **Step 6: 提交**

```bash
git add result_transform.py tests/test_result_transform_perf.py
git commit -m "perf(C-1b): _parse_numeric_or_date 补 Decimal 快速路径，_try_float 免异常路径"
```

---

### T3: C-1c — `filter_rows` / `sort_rows` 单趟化

**Files:**
- Modify: `tests/test_result_transform_perf.py`（追加用例）
- Modify: `result_transform.py:163-235`

**Interfaces:**
- Consumes: T2 的成果（`_try_float` / `_parse_numeric_or_date` 已有快速路径）
- Produces: `filter_rows(rows, columns, filters) -> list[tuple]` 与 `sort_rows(rows, columns, sorts) -> list[tuple]` 签名与**返回内容**均不变。

⚠️ **本任务风险最高**：改错不报错，只静默改变行序。Step 1 的 characterization 测试是**先写、先通过、再改**（与 T1/T2 的红绿相反），因为它们守的是「不许变」而非「要变新」。

- [ ] **Step 1: 写 characterization 测试（改前必须绿）**

追加到 `tests/test_result_transform_perf.py`，覆盖 **Review Focus #2 与 #3**：

- `test_sort_partition_order_mixed_types`（Review Focus #2）：列 `["v"]`，值 `[None, 3, "2.5", "abc", 1.5, "", -2]`，断言升序结果的**精确行序**：`[-2, 1.5, 3, "2.5", "abc", "", None]`（数值按值升序在前，文本按字符串升序在后，None 恒最后）。再断降序：数值与文本各自降序，**None 仍在最后**。
- `test_sort_multi_key_priority_and_stability`（Review Focus #3）：两列 `["a", "b"]`，构造 `a` 相同的多行，断言按 `sorts=[("b","asc"),("a","desc")]` 时，`a` 相同组内按 `b` 排序，且原始输入中 `a`、`b` 都相同的行**保持输入相对次序**。
- `test_filter_multiple_conditions_single_pass_semantics`：3 个 filter 的 AND 组合，断言结果与逐个 filter 手工推导一致。
- `test_unknown_column_filter_skipped`：`filter_rows(rows, columns, [("nope","eq","x")])` 返回全部行（既有静默跳过语义）。
- `test_sort_unknown_column_skipped`：`sort_rows(rows, columns, [("nope","asc")])` 返回原序。
- `test_no_filters_returns_same_object`、`test_no_sorts_returns_same_object`：无 filter/sort 时返回**原对象**（`assertIs`），锁住 `:181-182` / `:200-201` 的早返回。

跑一次确认**全绿**：

```bash
source venv/bin/activate && python -m unittest tests.test_result_transform_perf > /tmp/perf-t3-1.log 2>&1; grep -E '^(OK|FAILED|Ran )' /tmp/perf-t3-1.log
```

- [ ] **Step 2: `filter_rows` 合并为单趟**

把 `filter_rows`（`:163`）改为：对每个 `(col_name, op, q)` 预解析出「判定函数」，再对 `rows` 做**一趟**遍历同时应用全部条件。

⚠️ 预解析必须复用 `_apply_single_filter` 现有的解析逻辑（`parse_filter_expr` / `_compile_segments` / `_parse_numeric_or_date`），**不得另写一套**（AGENTS #3 禁止重复造轮子）。未知列 / 无法比较的值仍按既有语义**静默跳过该条件**（不是跳过该行）。

- [ ] **Step 3: `sort_rows` 合并为单趟**

把每 sort key 的 4 趟（None 分离 2 趟 + `_ordered_by_column` 1 趟 + `columns.index()`）压成 1 趟：一次遍历同时完成 None 判定、数值/文本判定与入组，`columns.index()` 结果在进入循环前算一次。

**排序稳定性要求**：既有实现是「从低优先级到高优先级依次应用稳定排序」。改为单趟分组后必须**保持等价**——最稳妥的实现是保留外层「从低到高」的循环顺序，只把**内层**每 key 的 4 趟压成 1 趟。不要试图把多个 key 合成一次排序（会破坏多字段优先级语义）。

- [ ] **Step 4: 跑测试确认仍绿**

```bash
source venv/bin/activate && python -m unittest tests.test_result_transform_perf tests.test_result_transform tests.test_filter_help tests.test_nested_filter tests.test_exclusion_engine tests.test_report tests.test_export tests.test_api_endpoint > /tmp/perf-t3-2.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t3-2.log
```

Expected: `OK`。**任何一个失败都是语义被破坏**——回到 Step 2/3 找根因，不要改测试断言来迁就实现（AGENTS #12）。

- [ ] **Step 5: 提交**

```bash
git add result_transform.py tests/test_result_transform_perf.py
git commit -m "perf(C-1c): filter_rows 多条件单趟化，sort_rows 每 key 4 趟压成 1 趟"
```

---

### T4: C-1 收口 — 大数据集逐行一致性验证与收益测量

**Files:**
- Create: `scripts/perf/verify_transform_equivalence.py`
- Modify: `docs/compose/spec/2026-09-29-execution-layer-performance-design.md`（§10 回填 T1/T2/T3 前后对比）

**Interfaces:**
- Consumes: T0 的 `bench.py` 与性能数据；T1/T2/T3 的代码改动
- Produces: 逐行一致性报告（spec §6.2 要求）+ C-1 三项的 P50/P95 前后对比

- [ ] **Step 1: 写 `scripts/perf/verify_transform_equivalence.py`**

从 MySQL `perf_text` 取全量 10 万行，构造含 NULL / Decimal / 数字串 / 纯文本 / 空串的混合数据，对下列每种 (filters, sorts) 组合，比对**优化前后的 `filter_rows` + `sort_rows` 输出**：

- 无 filter + 无 sort
- 单 `contains` / 单 `eq` / 单 `neq` / 单 `notcontains`
- 单 `gt` / `lt` / `gte` / `lte`（对 `amount` 与 `mixed` 各一遍）
- `isempty` / `notempty`
- 3 个 filter 的 AND 组合
- 单 key 升/降序，对 `amount` / `mixed` / `created_at` 各一遍
- 双 key、三 key 排序

**比对方式**：脚本需同时持有「优化前」与「优化后」的实现。做法是把优化前的实现以**函数源码快照**落到脚本内的参考实现（`_reference_filter_rows` / `_reference_sort_rows`），逐行 `assert` 输出完全一致（长度、每行每列的值）。

⚠️ 参考实现必须**逐字复制自 T1 之前的源码**（从 `git show 02a95a1:result_transform.py` 取），不得凭记忆重写——重写就变成了「用新实现验证新实现」。

任一不一致即 `self.fail` / 非零退出，打印第一处不同的行号与两侧值。

- [ ] **Step 2: 跑一致性验证**

```bash
source venv/bin/activate && python scripts/perf/verify_transform_equivalence.py > /tmp/perf-t4-equiv.log 2>&1; grep -E '^(OK|FAILED|Ran |不一致)' /tmp/perf-t4-equiv.log
```

Expected: 全部一致，退出码 0。

**若出现不一致：立即停止。这是 T2/T3 破坏了语义，按 AGENTS #12 做根因分析，不得改参考实现去迁就。**

- [ ] **Step 3: 重跑 bench 采集 C-1 后的数据**

服务需重启以加载新代码（`kill` 旧进程 → 重新 `nohup python server.py` → 按 T0 Step 8 的轮询判据等就绪）。

```bash
SR_USER=<账号> SR_PASS=<密码> python scripts/perf/bench.py --out /tmp/perf-after-c1-<ts>.json
```

- [ ] **Step 4: 把 C-1 前后对比表写进 spec §10**

表格列：场景 / 基线 P50 / C-1 后 P50 / 基线 P95 / C-1 后 P95 / 提升倍数。重点看 S2（翻页）、S3（排序）、S4（筛选）—— 这三个是 C-1 的主战场。

**如实填写，没提升的项照实写"无明显变化"。**

- [ ] **Step 5: 评估 spec §2.1 中「仅在实测证明是热点时」才动的三个模块**

spec 把 `server.py`（每请求配置库连接、访问审计写入）、`redis_cache.py`、`config_db.py` 列为**条件性范围**——只在基线证明它们是热点时才优化。对着 Step 3 的 JSON 逐项判断：

- **S8（配置页）** 若 P50 明显高于其他场景 → `server.py` 的每请求 `db.get_config_db()` 与 `_log_web_access` 写审计是嫌疑点，需要**新增一个 T5b 任务**（连接复用 / 审计批量写），并同样走 TDD + L0/L1
- **S5（Redis 路径）** 若 `redis_cache` 的快照反序列化占比高 → 需评估快照体积控制，但这**触碰冻结边界**，必须先回用户确认再动
- `config_db.py` 同理，按 S8 的结论决定

**判断结论写进 spec §10 执行记录**（含「已评估，X 不是热点，不优化」这种结论也要写）。任何需要动 Redis 快照格式的优化，**先停下来问用户**（Global Constraint #2/#7）。

- [ ] **Step 6: 提交**

```bash
git add scripts/perf/ docs/compose/spec/
git commit -m "perf(C-1): 大数据集逐行一致性验证 + 收益对比回填 spec"
```

---

### T5: C-2 — MySQL 有界连接池

**Files:**
- Create: `tests/test_mysql_pool.py`
- Modify: `query_executor.py`（新增 `_PooledConnection` 与池实现，改 `create_mysql_connection` 走池）
- Modify: `db.py`（如需导出新名字）

**Interfaces:**
- Consumes: T0 的 `test_mysql` 连接参数
- Produces:
  - `create_mysql_connection(pool_config, read_timeout=None)` —— **签名与返回类型不变**。返回对象新增行为：其 `close()` 是「归还池」而非「真关闭」；其余方法（`cursor` / `begin` / `commit` / `rollback` / `start_transaction` / `__enter__` / `__exit__`）全部透传到底层真实连接。
  - 因此 `report.execute_report` 的 `finally: conn.close()` **一行都不用改**。
  - `db.py` 追加导出 `clear_pools()`（仅测试清理用；生产路径不需要任何新名字）

⚠️ **这是让本任务回归面可控的关键决策**：把「归还」语义藏进 `close()`，`execute_report` 完全不动，`tests/test_query_cache.py` 等一批 patch `report.db.create_mysql_connection` 的测试也不受影响。

- [ ] **Step 1: 写失败的测试**

`tests/test_mysql_pool.py`，**不依赖真实 MySQL**（用假 connector），保证全量 discover 时永远能跑：

- `test_second_call_reuses_pooled_connection`：patch `query_executor.mysql` 模块的 `connect`（用 `sys.modules` 注入假模块或 patch `mysql.connector.connect`）。同一 `pool_config` 连续调 `create_mysql_connection` 两次，断言底层 `connect` 只被调用 1 次。
- `test_read_timeout_separates_pools`（**关键护栏**）：`create_mysql_connection(cfg, read_timeout=30)` 与 `create_mysql_connection(cfg, read_timeout=None)` 各一次，断言底层 `connect` 被调用 **2 次**（不同池），且两次传入的 config 字典的 `read_timeout` 分别为 `30` 与**不含该键**。
- `test_different_pool_config_uses_different_pool`：不同 `database` → 不同池。
- `test_close_returns_to_pool`：借出 → `close()` → 再借出，断言拿到**同一个**底层连接对象，且 `connect` 仍只调 1 次。
- `test_pool_overflow_falls_back_to_direct_connection`（**Review Focus #4**）：池上限为 8（spec §5 C-2），借出 8 个不归还，第 9 次仍应成功（直连），断言成功且无异常。
- `test_dead_connection_replaced_on_checkout`（**Review Focus #4**）：让假连接的 `ping(reconnect=True)` 返回 False，断言归还后再借出拿到的是**新**连接（`connect` 调用 2 次）。
- `test_release_is_idempotent`：同一连接 `close()` 两次不抛异常、不重复入池。
- [ ] **Step 2: 跑测试确认失败**

```bash
source venv/bin/activate && python -m unittest tests.test_mysql_pool -v > /tmp/perf-t5-1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t5-1.log
```

Expected: `FAILED`（当前无池，`connect` 每次都调）。

- [ ] **Step 3: 实现池**

在 `query_executor.py` 中：

- `_PooledConnection`：包装底层真实连接，`close()` 归还池而非关闭；其余方法透传。归还时用 `ping(reconnect=True)` 探活，死的直接丢弃不入池。
- `_ConnectionPool`：按 `(host, port, user, database, read_timeout)` 分键的字典，值为 `queue.LifoQueue`（`maxsize=8`）。借出时若队列非空则取出并探活；否则直连。归还时若队列满则真关闭底层连接（**这是防止池泄漏撑爆的关键**）。
- 全局字典 + `threading.Lock` 保护（`ThreadingHTTPServer` 多线程）。
- `create_mysql_connection` 改为：先查池，命中则返回 `_PooledConnection`；未命中或池满则直连并（若池未满）入池。
- 池的连接惰性建立，**不预热**（避免启动时连不上就崩）。
- 提供 `clear_pools()` 供测试清理。

⚠️ **`read_timeout` 必须在池键里**（spec §5 C-2）：`create_mysql_connection` 现有实现是「`read_timeout is not None` 才加这个键」，池键要显式用 `read_timeout` 的实际值（含 `None`）。

- [ ] **Step 4: 跑测试确认通过**

同 Step 2 命令（本段第 2 次执行）。Expected: `OK`。

- [ ] **Step 5: 跑 L1 + 真层验证**

```bash
source venv/bin/activate && python -m unittest tests.test_mysql_pool tests.test_mysql_mock tests.test_mysql_transactional tests.test_query_cache tests.test_report tests.test_scheduler_cache tests.test_scheduler_core > /tmp/perf-t5-l1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t5-l1.log
```

然后重启 DEBUG 服务，**真跑一次报表页与一次定时任务**，确认：
- 报表页正常返回（连接借出/归还没破）
- 调度器任务能跑完（**这是 `read_timeout` 分池是否真的生效的关键验证**——如果混池，慢查询任务会被 30s 砍断）
- 日志中无连接相关异常

**若调度器出现回归：按 spec §7 退出条件弃用整段 C-2，回滚本任务，保留 C-1 成果。**

- [ ] **Step 6: 跑 bench 采集 C-2 后数据并回填 spec §10**

重点看 S1（冷路径，连接建立占比最大）。服务**需重启两次**才能同时测到冷池与热池：重启后首次请求是冷池，之后是热池。

- [ ] **Step 7: 提交**

```bash
git add query_executor.py db.py tests/test_mysql_pool.py docs/compose/spec/
git commit -m "perf(C-2): MySQL 有界连接池（read_timeout 分池，close() 语义为归还）"
```

---

### T6: C-3 — 派生态缓存

**Files:**
- Create: `tests/test_derived_cache.py`
- Modify: `report.py:81-101`（`CachedResult` 加 `derived` 字段）、`report.py:1266-1292`（transform 循环接入派生态）

**Interfaces:**
- Consumes: T0 的 bench 与性能数据；T1–T5 的成果
- Produces:
  - `CachedResult.__init__` 新增关键字参数 `derived: dict | None = None`，存到 `self.derived`（`__slots__` 需加 `"derived"`）。**既有参数与默认值不变**，现有构造调用全部兼容。
  - transform 循环的行为：分页切片**仍每次现算**（O(page_size)），只有 filter+sort 的有序全量行列表被缓存。

⚠️ **本任务必须最后做** —— 它依赖 C-1 的单趟化才有意义（C-1 让单次 transform 变便宜，C-3 让重复 transform 免做）。

- [ ] **Step 1: 写失败的测试**

`tests/test_derived_cache.py`：

- `test_second_page_request_skips_filter_and_sort`：**核心用例**。patch `report.sort_rows` 为计数 `MagicMock(side_effect=真实实现)`，连调两次 `execute_report`（同 report_id、同 filters/sorts、`page=1` 与 `page=2`），断言 `sort_rows` **只被调用 1 次**，且两次返回的 `rows` 内容正确（`page=2` 是第 2 页的行）。
- `test_different_filters_use_different_entry`：先 `filters=[]` 再 `filters=[("amount","gt","100")]`，断言 `sort_rows` 被调用 2 次。
- `test_different_sorts_use_different_entry`：`sorts=[]` vs `[("amount","desc")]`，断言调用 2 次。
- `test_l1_expiry_discards_derived`（**Review Focus #5**）：用 TTL 极小的 `QueryCache` 实例；第一次执行后手动让 L1 条目过期（改 `cached.timestamp`），第二次执行，断言 `sort_rows` 被再次调用（**派生态必须随 L1 一起消失**）。
- `test_refresh_discards_derived`（Review Focus #5）：`refresh=True` 两次执行，断言 `sort_rows` 调用 2 次。
- `test_force_rebuild_discards_derived`（Review Focus #5）：`force_rebuild=True` 两次，断言调用 2 次。
- `test_force_rebuild_serves_new_data`：第一次返回 `[("a",1)]`，第二次让 MySQL 返回 `[("a",2)]`，断言第二次输出是新数据（**派生态不得跨数据版本存活**）。
- `test_write_report_never_uses_derived`：含写语句的 SQL（`allow_write=1`）两次执行，断言 transform 每次都跑（写报表本就不走缓存）。
- `test_derived_lru_bounded`：`CachedResult` 上挂 10 个不同 filters 组合，断言 `len(derived)` ≤ 8（spec §5 C-3 的上限）。
- `test_snapshot_json_unchanged`（**Global Constraint #2 的兜底**）：`CachedResult` 加字段后，构造 `ReportSnapshot` 并 `to_json()`，断言 JSON 字符串与加字段前的预期完全一致（新增字段不得泄漏进快照）。
- [ ] **Step 2: 跑测试确认失败**

```bash
source venv/bin/activate && python -m unittest tests.test_derived_cache -v > /tmp/perf-t6-1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t6-1.log
```

Expected: `FAILED`（`sort_rows` 当前每次都被调用）。

- [ ] **Step 3: `CachedResult` 加 `derived` 字段**

`report.py:83-85` 的 `__slots__` 加 `"derived"`；`__init__` 加 `derived: dict | None = None` 关键字参数（放最后，有默认值），`self.derived = derived if derived is not None else {}`。

**`derived` 绝不能进入 `ReportSnapshot` 或任何序列化路径**（`to_json` 只取 `results` / `sql_query` / `updated_at` / `config_version` / `truncated`）。

- [ ] **Step 4: transform 循环接入派生态**

在 `report.py:1266-1289` 的循环里，键取自 `(filters, sorts, nested_filter)` 的规范化元组（**必须用可哈希的稳定表示**，例如 `tuple(tuple(f) for f in filters or [])`；`nested_filter` 是 dict，需 `json.dumps(sort_keys=True)` 或其 `repr`）。

命中则复用有序全量行列表；未命中则算一次并存入，**同时做 LRU 淘汰**（超过 8 个组合时删最早插入的）。

**分页切片仍在循环内现算**，不缓存。

- [ ] **Step 5: 跑测试确认通过 + L1**

```bash
source venv/bin/activate && python -m unittest tests.test_derived_cache tests.test_query_cache tests.test_redis_cache tests.test_redis_cache_extra tests.test_cache_ui tests.test_report tests.test_report_extra tests.test_export tests.test_api_endpoint tests.test_scheduler_cache > /tmp/perf-t6-2.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-t6-2.log
```

Expected: `OK`。

- [ ] **Step 6: 跑 bench 采集 C-3 后数据并回填 spec §10**

重点看 **S2（翻页）** —— 这应是全任务提升最大的一项。同时确认 S5（Redis 路径）的 `cache_info.source` 仍正确显示 `redis`。

- [ ] **Step 7: 提交**

```bash
git add report.py tests/test_derived_cache.py docs/compose/spec/
git commit -m "perf(C-3): 派生态缓存挂 CachedResult，翻页免重跑 filter/sort"
```

---

### T7: 知识库同步与收尾

**Files:**
- Modify: `docs/compose/knowledge/03-report-transform.md`
- Modify: `docs/compose/knowledge/01-architecture.md`
- Modify: `docs/compose/knowledge/07-cache-scheduler-audit.md`
- Modify: `docs/compose/knowledge/08-testing-conventions.md`
- Modify: `learn/sqlreport-kb/course-state.md`
- Modify: `docs/compose/plan/2026-09-29-execution-layer-performance-plan.md`（状态与执行记录）

- [ ] **Step 1: 按 spec §8 同步知识库**

逐项：
- `03-report-transform.md` —— 记录 `_parse_numeric_or_date` 的 Decimal 快速路径、`filter_rows`/`sort_rows` 的单趟实现、**既有排序分区语义（数值恒在文本前、None 恒最后）现在由哪些测试锁定**
- `01-architecture.md` —— 记录 MySQL 连接池的存在与「`close()` 语义为归还」这个反直觉约定
- `07-cache-scheduler-audit.md` —— 在「三层数据流」补一句派生态缓存的位置（**明确它不属于三层中的任何一层，是 L1 之上的请求级 memo**），并强调 Redis 快照语义未变
- `08-testing-conventions.md` —— 记录 `scripts/perf/` 工具链的存在与用途（**以及「这些脚本会改真实库，不可被 discover 触及」这个坑**）
- `learn/sqlreport-kb/course-state.md` —— 更新掌握状态

遵守 AGENTS 的**冗余红线**：知识库只写「是什么/为什么」，不复述本 spec 的前后对比数据表（那些留在 spec §10）。

- [ ] **Step 2: 跑 L2 分段全量**

按 AGENTS.md「L2 大模块顺序」分段执行，**不要一次 discover 一把梭**。每段落盘后 grep 取数：

```bash
source venv/bin/activate
python -m unittest tests.bug_hunt.test_static_analysis -v > /tmp/perf-l2-1.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-1.log
python -m unittest tests.test_result_transform tests.test_filter_help tests.test_nested_filter tests.test_exclusion_engine tests.test_max_rows tests.test_output_limit tests.test_write_guard tests.test_sql_write_detect -v > /tmp/perf-l2-2.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-2.log
python -m unittest discover -s tests/ -p 'test_report*.py' -v > /tmp/perf-l2-3.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-3.log
python -m unittest discover -s tests/ -p 'test_export*.py' -v > /tmp/perf-l2-4.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-4.log
python -m unittest discover -s tests/ -p 'test_api*.py' -v > /tmp/perf-l2-5.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-5.log
python -m unittest discover -s tests/ -p 'test_redis_cache*.py' -v > /tmp/perf-l2-6.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-6.log
python -m unittest tests.test_query_cache tests.test_cache_ui tests.test_mysql_pool tests.test_derived_cache tests.test_result_transform_perf tests.test_report_perf -v > /tmp/perf-l2-7.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-7.log
python -m unittest discover -s tests/ -p 'test_scheduler*.py' -v > /tmp/perf-l2-8.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-8.log
python -m unittest discover -s tests/ -p 'test_server.py' -v > /tmp/perf-l2-9.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' /tmp/perf-l2-9.log
```

**某段失败先修该段，不要整库重来**（AGENTS #8）。

- [ ] **Step 3: 做一次真实的 Redis 兜底验证**（spec §6.1 第 4 条）

不止靠单测：停掉 MySQL（或临时改 `test_mysql` 端口指向一个不存在的端口），请求 `prefer_cache=1` 的报表 P4，断言页面**仍显示数据**且 `cache_info.source` 为 `redis_fallback`。

⚠️ 这一步**需要用户协助**（涉及停 MySQL 服务或改配置）。若用户不便，改为在 `bench.py` 之外用一次性脚本 + mock 数据源完成，**但必须在报告中如实标注为「未做真实验证」**。

- [ ] **Step 4: 回填 plan 执行记录并置状态**

把各任务的测试证据行（`Ran N` / `OK`）与 spec §10 的最终对比表汇总，plan 状态置 `已完成`。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "docs: 性能优化知识库同步 + 计划执行记录收口"
```

---

## 验证计划

| 级别 | 范围 | 时机 |
|------|------|------|
| L0 | 单个新测试文件（`test_report_perf` / `test_result_transform_perf` / `test_mysql_pool` / `test_derived_cache`） | 每个实现任务内，红→绿 |
| L1 | 与改动同模块的相邻测试文件 | 每个实现任务末 |
| 一致性 | `scripts/perf/verify_transform_equivalence.py`（10 万行逐行比对） | T4 |
| L2 | AGENTS.md 规定的 9 段大模块顺序，分段执行 | T7 收口 |

**取数模板（所有测试命令）**：`python -m unittest … > /tmp/perf-<段>-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' <log>`

## 执行记录

> 由实施阶段回填。

- [ ] T0 Phase 0 测量基础设施 —— 待执行
- [ ] T1 C-1a `execute_report` 去重 —— 待执行
- [ ] T2 C-1b transform 类型快速路径 —— 待执行
- [ ] T3 C-1c filter/sort 单趟化 —— 待执行
- [ ] T4 C-1 收口验证与收益测量 —— 待执行
- [ ] T5 C-2 MySQL 连接池 —— 待执行
- [ ] T6 C-3 派生态缓存 —— 待执行
- [ ] T7 知识库同步与收尾 —— 待执行
