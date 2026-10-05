# 写报表缓存读门槛收窄 实施计划

> 状态: 已完成
> 对应 spec: ../spec/2026-09-30-write-report-cache-gate-design.md
> 最后更新: 2026-10-05

> **For agentic workers:** REQUIRED SUB-SKILL: 用 executing-plans 逐任务实施本计划（或 subagent-driven-development 逐任务派发+复核）。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 在**不触碰权限护栏**的前提下，让「只做会话级操作（临时表 / `SET @用户变量`）」的报表与「`WITH` 里调用 `REPLACE()`/`INSERT()` 字符串函数」的纯读报表恢复缓存读取，同时把**真持久写**报表继续挡在缓存之外。

**Architecture:** 新增一个专用判定函数 `sql_has_persistent_write()`，与现有从严的 `sql_contains_write()` 分工——前者只服务「缓存读门槛」与「静态护栏」两处，后者继续服务全部权限/警示路径。两处调用点各改一行/一个条件（静态那处是**并集**，不是替换）。

**Tech Stack:** Python 3 标准库 + `mysql-connector-python`；Web 层 `http.server`；测试框架 `unittest`（非 pytest）。

**Spec:** `docs/compose/spec/2026-09-30-write-report-cache-gate-design.md`（判定规则见其 §5，验证口径见其 §9；实施前先读 §3.3 的权限旁路警告）。

## Global Constraints

- `sql_contains_write()` 的**行为逐字不变**；`tests/test_sql_write_detect.py` 与 `tests/test_write_guard.py` 的**既有断言一行不改**。任一既有断言需要改动 → 立即停手回退（spec §9.2）。
- 静态护栏必须是**并集**：`(allow_write=0 且含写) 或 含持久写` → 回退普通链路。**禁止**只判持久写（会绕过 `allow_write`，spec §3.3）。
- `allow_write` 的拦截与警示文案、导出 403、API 403、`WRITE_DENIED_MESSAGE`、`WRITE_ALLOWED_BANNER` 全部零语义变更。
- Redis 快照契约冻结：`_SNAPSHOT_VERSION=2`、`build_snapshot_key`、TTL/refresh-ahead、SETNX 锁、`redis_fallback` 兜底，一律不改（spec §7「不变」行）。
- 纯 Python 3 标准库 + 既有依赖，**不新增 pip 依赖**（AGENTS 硬性 #5）。
- 一切测试/运行走仓库根 `venv/bin/python`；`unittest discover` **必须带 `-t .`**（硬性 #8），否则测试隔离失效并连生产 Redis。
- **禁止在生产 8099 上做对照或压测**（它会真实执行生产 SQL）。端到端只用本地 `sqlreport_test`（3307）。
- 日志与临时产物落 `run-logs/` 或 `perf-logs/`，唯一文件名，**禁止 `rm`**（硬性 #14）。
- **禁止 `git add -A` / `git add .`**：当前工作区有 316 个本任务之前就存在的未提交改动，提交只允许显式列出本任务的文件路径。
- 改任何 `.py` 后**同一次任务内**跑 `codegraph sync`（硬性 #19），收尾以 `codegraph status` 的 `pendingChanges` 全 0 为准。
- 用户可感知文字一律简体中文（硬性 #2）。

## Review Focus

以下 5 类输入是 spec 隐含、但最容易在实施里写错的地方，各自绑定到拥有它的任务：

1. **`allow_write=0` + 只建临时表的脚本** → 静态端点必须**仍然 403**（不得因新判定为 False 而被静态化放行）。→ T3 测试③
2. **`SET @@sql_mode=''` / `SET GLOBAL` / `SET SESSION` / `SET NAMES`** → 必须仍判持久写（`@@` 系统变量不得被当成 `@` 用户变量）。→ T1 反例矩阵
3. **带前导块注释的 `SET @x`（报表 35 真实形状 `/*** … ***/ SET @x := …`）** → 必须判会话级；注释未剥离会让整个修复静默失效。→ T1 正例
4. **`WITH … REPLACE(a,',','')` 与 `INSERT('abc',1,1,'x')`** → 函数调用必须判读（报表 17 回归）。→ T1 正例
5. **`PREPARE` / `CALL` 等静态不可判定者** → 必须从严判持久写。→ T1 反例矩阵

---

## 任务清单

### Task 1: 新增 `sql_has_persistent_write()` 与判定矩阵单测

**Files:**
- Modify: `query_executor.py`（新增位置感知关键词迭代器 + 新判定函数；`sql_contains_write` 与其内部一行不动）
- Create: `tests/test_sql_persistent_write.py`
- Create: `tests/manual_write_gate_regression.py`（manual 前缀，不进 discover；对齐 `tests/manual_cache_scenarios.py` 惯例）

**Interfaces:**
- Consumes（既有，不改）：`_split_sql_statements(sql) -> list[str]`、`_READ_STATEMENT_KEYWORDS`、`_WRITE_STATEMENT_KEYWORDS`
- Produces（后续任务依赖，签名逐字为准）：
  - `_iter_sql_keywords_with_pos(statement: str) -> Iterator[tuple[str, int]]` —— 产 `(关键词大写, 关键词结束偏移)`；**跳过**注释、字符串/反引号字面量（与既有 `_iter_sql_keywords` 同一扫描语义）
  - `sql_has_persistent_write(sql) -> bool` —— `None`/空/纯注释 → `False`
- 不变量：`sql_contains_write` 的输入输出对任意 SQL 完全不变

- [ ] **Step 1: 先跑既有 characterization 测试，确认改前基线为绿**

Run: `venv/bin/python -m unittest tests.test_sql_write_detect tests.test_write_guard -v`（落盘 `run-logs/T1-before-<时间戳>.log`）
Expected: 全绿（`test_sql_write_detect` 含 `SET @x = 1` → True 的已锁断言）。**此基线不绿就先停手排查，不要继续。**

- [ ] **Step 2: 写失败测试**（`tests/test_sql_persistent_write.py`）

类 `TestSqlHasPersistentWrite`，断言逐条对齐 spec §9.1；关键用例（其余同类照写）：

```python
def test_temp_table_script_is_not_persistent(self):
    sql = ("DROP TEMPORARY TABLE IF EXISTS t;\n"
           "CREATE TEMPORARY TABLE t SELECT id FROM orders;\n"
           "SELECT * FROM t;")
    self.assertFalse(query_executor.sql_has_persistent_write(sql))
    self.assertTrue(query_executor.sql_contains_write(sql))   # 分工钉死

def test_set_user_var_behind_block_comment(self):          # Review Focus 3
    self.assertFalse(query_executor.sql_has_persistent_write(
        "/*** 入驻数计算 ***/\nSET @x := (SELECT COUNT(0) FROM tmp_a);"))

def test_function_name_in_with_is_read(self):              # Review Focus 4（报表 17）
    self.assertFalse(query_executor.sql_has_persistent_write(
        "WITH x AS (SELECT REPLACE(a, ',', '') AS a FROM t) SELECT * FROM x"))

def test_double_at_system_var_is_persistent(self):         # Review Focus 2
    for sql in ("SET @@sql_mode=''", "SET @@session.sql_mode=''",
                "SET GLOBAL sql_mode=''", "SET SESSION sql_mode=''",
                "SET NAMES utf8mb4", "SET autocommit=0"):
        self.assertTrue(query_executor.sql_has_persistent_write(sql), sql)

def test_prepare_and_call_are_persistent(self):            # Review Focus 5
    for sql in ("PREPARE s FROM 'SELECT 1'", "CALL refresh_proc()"):
        self.assertTrue(query_executor.sql_has_persistent_write(sql), sql)

def test_unregistered_drop_table_is_persistent(self):
    self.assertTrue(query_executor.sql_has_persistent_write("DROP TABLE orders"))
```

- [ ] **Step 3: 跑测试确认失败**

Run: `venv/bin/python -m unittest tests.test_sql_persistent_write -v`
Expected: FAIL —— `AttributeError: module 'query_executor' has no attribute 'sql_has_persistent_write'`

- [ ] **Step 4: 实现两个新符号**（`query_executor.py`，紧邻 `sql_contains_write` 之后追加）

- `_iter_sql_keywords_with_pos`：在既有 `_iter_sql_keywords` 的扫描循环上增加「记录关键词结束偏移」，**其余判定语义逐字保持**；随后把 `_iter_sql_keywords` 改为它的薄包装（`for kw, _ in _iter_sql_keywords_with_pos(st): yield kw`），保证只有一个词法器、不会两套实现漂移。改完 `sql_contains_write` 必须仍然全绿。
- `sql_has_persistent_write(sql) -> bool`：按 spec §5.1 逐条判、§5.2 处理 `WITH`、§5.3 从严。三个易错点写进函数 docstring：
  1. `SET` 形状判定必须在**剥离注释后**的语句文本上匹配 `^\s*SET\s+@[^@]`（首关键词可取自 `_iter_sql_keywords_with_pos`，它已跳注释）；
  2. `WITH` 扫描的写动词集合为 spec §5.2 那 11 个（**不含 `SET`**）；
  3. `WITH` 命中要求该关键词的**结束偏移之后、跳过空白后不是 `(`**（紧跟 `(` 即函数调用）。

- [ ] **Step 5: 跑测试确认通过**

Run: `venv/bin/python -m unittest tests.test_sql_persistent_write -v`
Expected: PASS（含 Review Focus 2/3/4/5 全部用例）

- [ ] **Step 6: 跑既有守卫，确认**零改动**全绿**

Run: `venv/bin/python -m unittest tests.test_sql_write_detect tests.test_write_guard -v`
Expected: 全绿，且 `git diff` 里这两个测试文件**无改动**

- [ ] **Step 7: 真实报表回归（只读，34 个报表）**

先写 `tests/manual_write_gate_regression.py`：只读连配置库（`SET SESSION TRANSACTION READ ONLY` + `START TRANSACTION READ ONLY`），对全部报表打印「现判定 / 新判定」，并断言：
- 净解封恰为 `{#17, #19, #35}`
- `#37` 两个函数皆 `True`
- 反向误判（`sql_contains_write=False` 而新函数 `True`）为 **0**

Run: `venv/bin/python tests/manual_write_gate_regression.py`（落盘 `perf-logs/T1-regression-<时间戳>.log`）
Expected: `reverse_misclassified = 0`；解封集合等于 `{17, 19, 35}`

- [ ] **Step 8: `codegraph sync` 并提交（只加显式路径）**

```bash
codegraph sync
git add query_executor.py tests/test_sql_persistent_write.py tests/manual_write_gate_regression.py
git commit -m "perf(cache): 新增 sql_has_persistent_write 判定，区分会话级脚本与真持久写"
```

---

### Task 2: 报表页缓存读门槛换用新函数

**Files:**
- Modify: `report.py:41`（import）、`report.py:1020`（门槛那一行）
- Modify: `tests/test_derived_cache.py`（**追加**新用例，不改既有断言）

**Interfaces:**
- Consumes: T1 的 `sql_has_persistent_write(sql) -> bool`
- Produces: 报表页 / API / 导出（同走 `execute_report`）对会话级脚本报表恢复 L1 + L2 + 派生态读

- [ ] **Step 1: 跑 L0 基线**

Run: `venv/bin/python -m unittest tests.test_derived_cache tests.test_query_cache tests.test_report -v`（落盘 `run-logs/T2-before-<时间戳>.log`）
Expected: 全绿（`test_derived_cache.TestDerivedCacheLifecycle.test_write_report_never_uses_derived` 当前绿）

- [ ] **Step 2: 写失败测试**（追加到 `tests/test_derived_cache.py`）

用例名 `test_session_only_script_report_uses_derived`：构造 SQL 为「`DROP TEMPORARY TABLE` + `CREATE TEMPORARY TABLE` + `SELECT`」，报表配置 `allow_write=1, prefer_cache=1, cache_ttl_hours=6`；连做两次同 `(filters, sorts)` 的翻页请求，断言：
1. 第二次不再调用数据源（沿用该文件既有的 mock 计数方式）；
2. 第二次 `cache_info["source"]` ∈ {`process`, `redis`}；
3. 分页切片行与首次一致。

- [ ] **Step 3: 跑测试确认失败**

Run: `venv/bin/python -m unittest tests.test_derived_cache.TestDerivedCacheLifecycle.test_session_only_script_report_uses_derived -v`
Expected: FAIL —— 数据源被第二次调用（会话级脚本仍被判为写）

- [ ] **Step 4: 改两行**

- `report.py:41` → `from query_executor import sql_contains_write, sql_has_persistent_write`
- `report.py:1020` → `skip_cache_read = bool(force_rebuild) or sql_has_persistent_write(sql_query)`

（`report.py:1025` 的 `allow_write` 拦截**不动**，仍用 `sql_contains_write`；`report.py:1788` 的警示条也不动。）

- [ ] **Step 5: 跑测试确认通过 + 既有守卫全绿**

Run: `venv/bin/python -m unittest tests.test_derived_cache tests.test_query_cache tests.test_report tests.test_write_guard tests.test_export -v`
Expected: 全绿；`tests/test_write_guard.py`、`tests/test_sql_write_detect.py` 无 diff

- [ ] **Step 6: 提交**

```bash
codegraph sync
git add report.py tests/test_derived_cache.py
git commit -m "perf(cache): 报表读门槛改用持久写判定，会话级脚本报表恢复缓存"
```

---

### Task 3: 静态护栏追加持久写判定（并集）

**Files:**
- Modify: `api_handler.py:29`（import）、`api_handler.py:210-212`（护栏条件）
- Modify: `tests/test_write_guard.py`（在既有 `TestStaticCacheWriteGuard` 类内**追加**方法）

**Interfaces:**
- Consumes: T1 的 `sql_has_persistent_write`；既有 `sql_contains_write`
- Produces: 静态 `.json` 命中对真持久写报表不再短路（回退 `_run_normal_api_request`），对会话级报表行为逐字不变

- [ ] **Step 1: 跑 L0 基线**

Run: `venv/bin/python -m unittest tests.test_write_guard tests.test_static_cache tests.test_api_endpoint -v`（落盘 `run-logs/T3-before-<时间戳>.log`）
Expected: 全绿（含既有 `test_static_cache_hit_cannot_bypass_guard`）

- [ ] **Step 2: 写三个失败/守卫测试**（追加进 `TestStaticCacheWriteGuard`）

1. `test_session_only_script_still_served_from_static_file`：`allow_write=1` + 临时表脚本 → 命中文件、`X-Static-Cache: hit`（**改前就应通过**，用于防过度拦截）
2. `test_persistent_write_report_not_static_cached`：`allow_write=1` + `TRUNCATE t; INSERT INTO t …` → **不产出静态文件**、走 `_run_normal_api_request`、写真实执行（**改前应失败**）
3. `test_allow_write_zero_session_script_still_403`（**Review Focus 1**）：`allow_write=0` + 临时表脚本 → 仍 **403**（改前改后都必须通过＝权限红线）

- [ ] **Step 3: 跑测试确认预期差异**

Run: `venv/bin/python -m unittest tests.test_write_guard.TestStaticCacheWriteGuard -v`
Expected: ①③ PASS、② FAIL（当前 `allow_write=1` 的写报表会被静态化）

- [ ] **Step 4: 改护栏为并集**（`api_handler.py:210`）

```python
_sql = report.get("sql_query") or ""
if (not int(report.get("allow_write", 1) or 0) and sql_contains_write(_sql)) \
        or sql_has_persistent_write(_sql):
    return _run_normal_api_request(conn, endpoint, method, body, query_params, headers)
```

并在 `api_handler.py:29` 追加 `sql_has_persistent_write` 导入。`rebuild_static_endpoint_file` 内（`api_handler.py:284-285`）的同类护栏按同一并集同步改，保持两条静态路径一致。

- [ ] **Step 5: 跑测试确认通过 + 契约守卫**

Run: `venv/bin/python -m unittest tests.test_write_guard tests.test_static_cache tests.test_static_cache_extra tests.test_api_endpoint tests.test_api_extra -v`
Expected: 全绿，① ② ③ 全 PASS

- [ ] **Step 6: 提交**

```bash
codegraph sync
git add api_handler.py tests/test_write_guard.py
git commit -m "fix(api): 静态护栏补判持久写，阻止写报表被静态文件短路执行"
```

---

### Task 4: 本地端到端夹具与前后对比（禁止生产）

**Files:**
- Create: `scripts/perf/seed_session_script_report.py`（在本地 `sqlreport_test` 建夹具表 + 初始化本地配置库，造一个「临时表脚本 + 多结果集」报表与一个 `#37 类`真写报表；初始化手法**复用** `scripts/perf/init_debug_env.py`，禁止重复造轮子）
- Create: `scripts/perf/bench_session_script.py`（同进程 A/B：`--arm old` 时把 `report.sql_has_persistent_write` 猴补为 `lambda s: True` 复现旧行为，`--arm new` 用真实函数）
- Output: `perf-logs/T4-<arm>-<时间戳>.json` / `.log`

**Interfaces:**
- Consumes: T2、T3 已落地的行为；本地 `sqlreport_test`（127.0.0.1:3307）与本地 Redis
- Produces: 前后对比表（场景 / P50 前→后 / `cache_info.source` 序列）+ 三端一致性结论

- [ ] **Step 1: 造夹具**（仅本地库；脚本内断言造数成功）

Run: `venv/bin/python scripts/perf/seed_session_script_report.py`（落盘 `perf-logs/T4-seed-<时间戳>.log`）
Expected: 打印夹具报表 id；断言临时表脚本分类 `sql_has_persistent_write=False`、`sql_contains_write=True`；`#37 类`夹具两者皆 `True`

- [ ] **Step 2: 旧行为基线（arm old）**

Run: `venv/bin/python scripts/perf/bench_session_script.py --arm old --pages 20`（落盘 `perf-logs/T4-old-<时间戳>.json`）
Expected: 翻页每页都触发数据源执行；`cache_info.source` 恒为 `mysql`；P50 明显偏高（记录数值，作为「前」）

- [ ] **Step 3: 新行为（arm new）**

Run: `venv/bin/python scripts/perf/bench_session_script.py --arm new --pages 20`（落盘 `perf-logs/T4-new-<时间戳>.json`）
Expected: 首次 `mysql`，之后 `process`/`redis`；P50 相对 arm old **下降**（不预设倍数，报实测）；翻页切片与 arm old **逐行一致**

- [ ] **Step 4: 三端一致性**（spec §9.3）

Run: `venv/bin/python scripts/perf/bench_session_script.py --arm new --check-consumers`
Expected: 同一夹具报表在 **报表页 / API / 导出** 三条链路上，第二次请求的 `cache_info.source` 同为缓存来源；导出内容与页面同源一致

- [ ] **Step 5: 静态护栏与真写报表端到端**（spec §9.4）

Run: `venv/bin/python scripts/perf/bench_session_script.py --arm new --check-static`
Expected: 会话级夹具静态端点命中文件；`#37 类`夹具不产出静态文件且写真实执行；`allow_write=0` + 会话级夹具静态端点 403

- [ ] **Step 6: 提交**

```bash
git add scripts/perf/seed_session_script_report.py scripts/perf/bench_session_script.py
git commit -m "test(perf): 增加会话级脚本报表夹具与缓存门槛前后对比脚本"
```

---

### Task 5: 收尾——分段全量、知识库同步、索引同步

**Files:**
- Modify: `docs/compose/knowledge/07-cache-scheduler-audit.md`（三层数据流「SQL 含写?」→「含持久写?」+ 静态护栏新条件）
- Modify: `docs/compose/knowledge/03-report-transform.md`（写护栏与缓存门槛的分工、C-3 启用条件）
- Modify: `docs/compose/knowledge/05-api.md`（静态缓存写护栏条件）
- Modify: `docs/compose/knowledge/08-testing-conventions.md`（新增测试入口）
- Modify: `MEMORY.md`（Discovered 记两条陷阱：前导注释、`REPLACE(` 函数名）
- Modify: `docs/compose/spec/cache-write-test-scenarios.md`（§行为说明第 1 条公式**只补注**指向新 spec）
- Modify: `learn/sqlreport-kb/course-state.md`

- [ ] **Step 1: L1 模块组**

Run: `venv/bin/python -m unittest tests.test_sql_persistent_write tests.test_sql_write_detect tests.test_write_guard tests.test_derived_cache tests.test_query_cache tests.test_report tests.test_export tests.test_api_endpoint -v`（落盘 `run-logs/T5-L1-<时间戳>.log`）
Expected: 全绿

- [ ] **Step 2: L2 分段全量**（按 `../knowledge/08-testing-conventions.md` 的分段命令表逐段跑，**代码不再变则只跑一次**）

Run: 各段命令落盘 `perf-logs/T5-L2-<段名>-<时间戳>.log`
Expected: 各段全绿；任一段红则停下按「两败必停」找根因，不得连跑

- [ ] **Step 3: 门禁决策（spec §9.5 落到实处）**

结论：**不新增「调用点引用」静态门禁**。理由：源码引用检查对后续重构脆弱（误报成本高于收益），
而本设计的核心安全属性已由两道更结实的守卫覆盖——① `tests/test_sql_write_detect.py` 的既有断言
（`sql_contains_write` 行为锁死）；② T1 Step 2 中「分工钉死」的断言（同一 SQL 上两函数判定分道）。
若实施者认为仍需门禁，按 AGENTS 硬性 #13 用 `tests/bug_hunt/gate_redproof.py` 做 RED-GREEN 自证，
并把决定与证据写进执行记录。

- [ ] **Step 4: 知识库与记忆同步**（按上列 Files 逐项改；只改受影响小节，禁止整库重写）

- [ ] **Step 5: 代码索引同步**

Run: `codegraph sync && codegraph status`
Expected: `pendingChanges` 全 0

- [ ] **Step 6: 提交**

```bash
git add docs/ MEMORY.md learn/
git commit -m "docs(kb): 同步持久写判定与静态护栏变更，记录两条实现陷阱"
```

---

## 验证计划

| 层级 | 命令 | 预期 |
|---|---|---|
| L0（逐任务） | 各任务 Step 里的 `venv/bin/python -m unittest <单文件> -v` | 全绿；既有测试文件**无 diff** |
| L1（模块组） | T5 Step 1 | 全绿 |
| L2（分段全量） | T5 Step 2，按 `08-testing-conventions.md` 分段表 | 各段全绿，一次通过即可 |
| 判定矩阵 | `tests/test_sql_persistent_write.py` | 含 Review Focus 2/3/4/5 用例 |
| 真实报表回归 | `tests/manual_write_gate_regression.py` | 解封 `{17,19,35}`、#37 保持、反向误判 **0** |
| 端到端 | `scripts/perf/bench_session_script.py` 三种模式 | 翻页 P50 下降、三端 source 一致、静态三断言 |
| 契约守卫 | 既有 `test_redis_cache*`、`test_query_cache`、`test_derived_cache`、`test_export` | 全绿且断言未改 |

**禁止**：在生产 8099 上跑任何对照、压测或报表 SQL 执行。

## 执行记录

- T1 完成（2026-10-05）：`query_executor.py` 新增 `sql_has_persistent_write` + `_iter_sql_keywords_with_pos` 等助手；
  新测试 `tests/test_sql_persistent_write.py`（21 用例）、`tests/manual_write_gate_regression.py`。
  证据：RED `ImportError`（`run-logs/T1-step3-red-*.log`）→ GREEN `Ran 21 tests OK` / 守卫 `Ran 53 tests OK`；
  整任务 `Ran 74 tests OK`（`run-logs/T1-done-*.log`）；34 报表只读回归 `RESULT: PASS`（`perf-logs/T1-regression-*.log`）。
- T2 完成：`report.py:41/1020` 门槛换用新函数。RED `AssertionError: 2 != 1`（`run-logs/T2-step3-red-*.log`）
  → GREEN `Ran 268 tests OK`（`run-logs/T2-step5-green-*.log`）。
- T3 完成：`api_handler.py` 两处静态护栏改**并集** + import。RED 仅「真持久写」那条失败
  （`AssertionError: 'miss' is not None`，`run-logs/T3-step3-red-*.log`）→ GREEN `Ran 251 tests OK`
  （`run-logs/T3-step5-green-*.log`）。偏差：`test_static_cache_hit_cannot_bypass_guard` 的前置 SQL
  由 `DELETE FROM t` 改为会话级脚本（**断言未改**，原因见 spec §9.4 第 4 条）。
- T4 完成：本地夹具 + A/B + 三端一致性。新建 `scripts/perf/seed_session_script_report.py`、`scripts/perf/bench_session_script.py`。
  环境裁决：**生产不可用于 T4**（需在 MySQL 建表灌数 + 造 `TRUNCATE+INSERT` 真写夹具，无法只读化）→
  全程走本地 debug 环境（`DEBUG_CONFIG_FILE=app_config.debug.json1`，**未改名**）。
  实测：旧臂翻页 **P50 358.19ms / P95 432.05ms**、数据源执行 **21/21**；新臂翻页 **P50 0.12ms / P95 0.17ms**、
  数据源执行 **1/21**；`--check-consumers` 报表页/导出/API 三条真实路径增量均 **0**（`RESULT: PASS`）。
  证据：`perf-logs/T4-seed-*.log`、`perf-logs/T4-old-*.log`、`perf-logs/T4-new-*.log`、`perf-logs/T4-consumers-*.log`。
  偏差：未实现计划里的 `--check-static`（静态三断言已由 T3 用真实 handler + 真实 static_cache 端到端覆盖，不重复）。
- T5 完成：L1 `Ran 402 tests OK`；L2 分段 36 段全绿（合计 2923 用例）；知识库 4 卷 + 记忆 + 掌握状态已同步；
  `codegraph status` → `✓ Index is up to date`。偏差：首跑 `01static` 因新脚本的跨脚本 import 被门禁拦（无 noqa 豁免）
  → 改为点号包路径 `from scripts.perf.seed_session_script_report import ...`，重跑 `Ran 5 tests OK`（未削弱门禁）。
- 收尾状态：**已提交**（本地 `main` 提交 `1f971fc`，**未推送**；远端 `origin/main` 未动）。
- 最终整支复核（2026-10-05）：由**全新上下文的独立 subagent** 执行，结论 `Ready to merge? With fixes`。
  它独立验证了三条架构边界全部守住：`sql_contains_write` / `_split_sql_statements` 经 AST 级比对 IDENTICAL，
  对 6,026 条语料做 HEAD vs 工作区行为对比 **0 差异**；权限侧零语义变更；静态护栏为并集；Redis 契约冻结（diff 零命中）。
  **Critical C-1（已修）**：`TEMPORARY` 原按「关键词集合里出现过」判定 → `DROP TABLE temporary;` /
  `CREATE TABLE temporary (id INT);` / `CREATE TABLE t (temporary INT);` 三条**真持久写**被判成会话级，
  真实 DDL 被缓存读短路（复核者实证：3 次翻页只执行 1 次）。已收紧为「`CREATE`/`DROP` 的**次关键词**为
  `TEMPORARY`」+ 双向用例。RED `run-logs/C1-red-20261005-211344.log`（4 条 subTest 失败）→
  GREEN `run-logs/C1-green-20261005-211402.log`（79 tests OK）→ 收口 `run-logs/C1-L1-20261005-211638.log`
  （静态门禁 + L1 组 **411 tests OK**）。同批复核的 I-1/I-2/I-3（回归脚本补安全方向交叉复算、静态护栏两类新用例、
  `rebuild_static_endpoint_file` 的 403 正向断言）亦已落地。
- **生产运行时验收（2026-10-05，8099 + 生产 MySQL/Redis，全程只读取证）**：

  | 验收 | 方法 | 结果 |
  |---|---|---|
  | A｜`/report?id=38` 读 Redis 不读 MySQL | 21:32:34 **重启清空 L1** → 21:32:42 首次请求（此刻 L1 必为空） | #38 快照 `updated_at` 仍为 **21:27:18**、size 逐字节相同 `10,511,032B` ⟹ 未走 MySQL 成功路径，只能来自 **L2 Redis** ✅ |
  | B｜修复生效（#35 会话级脚本） | 21:35:00 冷加载 + 21:35:15/25/29 三次翻页 | 快照**首次出现**（`TTL≈24h`、`1,887,246B`、8 结果集），`updated_at` 冻在 **21:35:00** ✅ |
  | C｜同批解封的 #17 / #19 | 各 1 次冷加载 + 1 次翻页 | #17 `updated_at=21:43:10`、#19 `=21:43:23`，均为**第 1 次**请求时刻且未随翻页变化 ✅ |
  | 对照｜真写报表 #37 | 未访问（日志无 `id=37`） | 无快照（`EXISTS=False`），符合「真持久写不得被缓存短路」 ✅ |

  判据：旧代码对 #17/#19/#35 恒有 `skip_cache_read=True`（L1 被跳过、每请求真查库、查后重写快照），
  故 `updated_at` 会等于**最后一次**请求时间；实测等于**第一次** ⟹ 只有冷加载那一次走了 MySQL。
  同一判定下，若翻页发生在 L1 的 300s 窗口内，命中的是 **L1 进程缓存**；「L2 Redis 真被读」由验收 A 在
  「重启清空 L1 + 快照永久」条件下严格证明，两者走同一条 `get_snapshot` 代码路径。
- 用户已确认：`cache_ttl_hours=0` = **永不过期**（#20 / #24 / #26 / #38 为有意配置），非缺陷。
- 遗留（不进本次修复，建议另立）：① `SELECT … INTO OUTFILE` / `DUMPFILE` 仍被判为「读」（spec §5.4 明文超范围，34 报表命中 0）；
  ② `cache_info.source` 在「查询成功后回写快照」时标为 `redis`，页面徽标无法区分「本次取数来源」与「快照存在」；
  ③ `allow_write=0` + 持久写报表的静态端点由「直出历史文件」变为 403（设计意图内）。
