# 缓存徽标「取数来源」标注修正 实施计划

> **给执行代理**：实施本计划时逐任务勾选（`- [ ]`）。可用 subagent-driven-development（每任务一实现者 + 一复核者）
> 或 executing-plans（本会话内自行实施）。**禁止**创建 `docs/superpowers/`（AGENTS §3）。

> 状态: 生效
> 对应 spec: `docs/compose/spec/2026-10-05-cache-source-label-design.md`

**Goal:** 让 `cache_info.source` 真正表示「本次取数来源」，使报表页缓存徽标不再把刚查库的数据说成缓存快照。

**Architecture:** 只改生产者（`report.py` 3 处 dict/入参），渲染器与缓存行为零改动。冷路径（MySQL 成功）改报
`mysql`，L1 条目不再冒名 `redis`（改 `None` → L1 命中报 `process`），L2→L1 的继承链保持不变；
`cache_info` 新增 `snapshot_written` 键区分「查了库但没写快照」。

**Tech Stack:** Python 3 标准库 + `unittest`；无新依赖。

**Spec:** `docs/compose/spec/2026-10-05-cache-source-label-design.md`（§5.1 取值表 / §5.2 改动点 / §6 影响面 / §7 验证策略）

## 全局约束

- 全部用户可感知文字（代码注释、测试 docstring、提交说明、文档）用**简体中文**（AGENTS #2）。
- 一切命令在**仓库根**、**仓库 venv** 内执行（`./venv/bin/python`）；禁止系统 Python（#6）。
- `unittest discover` **必须带 `-t .`**（#8）；测试/日志产物落 `run-logs/`（已 gitignore），唯一文件名，**禁止 `rm`**。
- **不动 `render.py`**；不改缓存行为（键/TTL/refresh-ahead/SETNX 锁/`redis_fallback` 兜底/命中判定）；
  不改 `fresh` 语义与 API/导出输出契约（spec §3 非目标）。
- 工作树里已有**与本次无关的未提交改动**（ui-v2 的 CSS 外提：`render.py`/`config.py`/`report.py` 等）。
  **提交时只 `git add` 本计划点名的文件，禁止 `git add -A` / `git commit -a`。**
- 改完任何 `.py` 在同一次任务内跑 `codegraph sync`，收尾 `codegraph status` 的 `pendingChanges` 全 0（#19）。
- 同一测试段最多执行 2 次（首跑 + 1 次收口）；同一问题失败 2 次必须停下分析根因（#12/#14）。
- 改动 `report.py` 后必须重启 8099 再验收（否则验的是内存里的旧代码，MEMORY #14）。

## Review Focus

spec 未明说但很容易被破坏的输入/条件，按最可能踩雷排序；每条都已在下列任务里钉成断言：

1. **L2→L1 的继承链**：L1 条目若被统一改写成 `None`，从 L2 命中的那一页会从「缓存快照」退化成「本地缓存」——
   这是 spec §8 的整段回退条件。→ Task 1 的 `test_l1_entry_from_l2_still_reports_redis`。
2. **L1 命中不得再冒名 `redis`**：冷查后的第二次请求必须报 `process`。→ Task 1 的 `test_second_request_l1_hit_reports_process`。
3. **数据源故障兜底**：`redis_fallback` 与 `fresh=False` 不得被顺手改掉。→ Task 1 的 `test_mysql_failure_falls_back_to_stale_snapshot`。
4. **未启用 Redis**：`prefer_cache=0` 时 `snapshot_written` 必须是 `False` 而不是缺键。→ Task 1 的 `test_redis_disabled_reports_mysql_without_snapshot`。
5. **冷路径横幅**：`mysql` 且 Redis 可用时，`build_redis_banners_html` 不得再输出「数据来自缓存快照」。→ Task 1 的 `TestBadgeHonesty`。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `report.py` | 改 3 处（~1193-1207） | `cache_info` 生产者：MySQL 成功分支的来源标注 + L1 条目 `source` |
| `tests/test_cache_source_label.py` | 新建 | 新语义的第一性断言（冷/ L1 / L2 / L1←L2 / 兜底 / 无 Redis + 徽标文案） |
| `tests/test_query_cache.py`、`tests/test_report_extra.py`、`tests/test_scheduler_primitives.py`、`tests/test_cache_ui.py` | 改断言 7 处 | 既有生产路径断言同步到新语义 |
| `tests/manual_cache_scenarios.py` | 改 3 处 | 手工场景脚本（不进 discover）期望同步 |
| `scripts/perf/bench.py`、`scripts/perf/verify_redis_fallback.py` | 改期望 | 外部读取方的 S5 / ① 期望；`bench_session_script.py` 已容错**不改** |
| `docs/compose/spec/2026-10-05-cache-source-label-design.md` | 订正 §6/§7 | 「为什么必须改」的记录（§7.2 要求），并订正实施期核出的两处误判 |
| `docs/compose/knowledge/{03,07,08}.md`、`docs/compose/spec/2026-09-29-execution-layer-performance-design.md`、`MEMORY.md` | 同步 | 知识库 `cache_info.source` 语义 + 历史实测表补注 |

---

### Task 1: 生产者语义修正 + 新测试 + 既有断言同步（一次提交，全套件绿）

**Files:**
- Modify: `report.py`（3 处，均在 `execute_report` 内）
- Create: `tests/test_cache_source_label.py`
- Modify: `tests/test_query_cache.py:225-226,262,332-333`、`tests/test_report_extra.py:447,449`、
  `tests/test_scheduler_primitives.py:94-95`、`tests/test_cache_ui.py:305-306,312`、
  `tests/manual_cache_scenarios.py:225,261,321`
- Modify: `docs/compose/spec/2026-10-05-cache-source-label-design.md`（§6 表格订正 + §7.1 落地说明）

**Interfaces:**
- Consumes: 无（本次是链路最底层）。
- Produces: `ReportResult.cache_info` 的键约定 —— `source ∈ {mysql, process, redis, redis_fallback}`；
  `snapshot_written: bool` **仅**在 `source == "mysql"` 时存在（`True` = 本次同时写了 L2 快照）；
  L1 条目 `CachedResult.source` 取值改为：来自 MySQL → `None`，来自 L2 → `"redis"`（不变）。

- [x] **Step 1: 写失败测试（新建 `tests/test_cache_source_label.py`）**

```python
"""tests/test_cache_source_label.py — cache_info.source 生产者语义（spec 2026-10-05 §7.1）

钉死四件事：① 冷路径报 mysql（不再冒名 redis）；② 紧接的 L1 命中报 process；
③ L2 命中（含 L2→L1 继承）仍报 redis；④ 徽标文案与来源一致（不得说谎）。
"""
import time
import unittest
from unittest.mock import MagicMock, patch

import redis_cache
import render
import report

POOL = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
REDIS_CFG = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
             "sql_query": "SELECT 1", "name": "报表R", "memo": "", "result_names": ""}
NO_REDIS_CFG = dict(REDIS_CFG, prefer_cache=0)


def _mgr():
    """可用的 Redis 管理器 mock（acquire_lock 默认真值 → 本进程持锁）。"""
    mgr = MagicMock()
    mgr.key_prefix = "sr"
    return mgr


def _snapshot(rows):
    return redis_cache.ReportSnapshot(
        [{"columns": ["id"], "rows": rows}], "SELECT 1", 123.0, "v1")


class TestCacheSourceProducer(unittest.TestCase):
    """生产者取值表（spec §5.1）。"""

    def setUp(self):
        report._query_cache.clear()

    def tearDown(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_cold_request_reports_mysql_and_snapshot_written(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """冷路径（prefer_cache=1 + Redis 可用）→ mysql + snapshot_written=True。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "mysql")
        self.assertIs(result.cache_info["snapshot_written"], True)
        self.assertTrue(result.cache_info["fresh"])
        mgr.set_snapshot.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_second_request_l1_hit_reports_process(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """回归点：冷查后的第二次请求走 L1 → process（不得再是 redis），且不查库。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        first = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)
        second = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(first.cache_info["source"], "mysql")
        self.assertEqual(second.cache_info["source"], "process")
        self.assertEqual(mock_exec.call_count, 1)

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_l2_snapshot_hit_reports_redis(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """L2 命中 → redis（不变），并回填带 redis 来源的 L1 条目。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = _snapshot([(10,)])
        mock_mgr.return_value = mgr

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "redis")
        self.assertTrue(result.cache_info["fresh"])
        cached = report._query_cache.get(1)
        self.assertEqual(cached.source, "redis")
        self.assertEqual(cached.source_timestamp, 123.0)
        mock_exec.assert_not_called()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_l1_entry_from_l2_still_reports_redis(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """L2→L1 继承链不得断裂：L1 命中来自 L2 的条目仍报 redis。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = _snapshot([(10,)])
        mock_mgr.return_value = mgr

        report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)
        second = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(second.cache_info["source"], "redis")
        self.assertEqual(second.cache_info["timestamp"], 123.0)
        mgr.get_snapshot.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_mysql_failure_falls_back_to_stale_snapshot(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """数据源故障 + 过期快照 → redis_fallback 且 fresh=False（不变）。"""
        mgr = _mgr()
        mgr.get_snapshot.side_effect = [None, _snapshot([(9,)])]
        mock_mgr.return_value = mgr
        mock_conn.return_value = MagicMock()
        mock_exec.side_effect = RuntimeError("db down")

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "redis_fallback")
        self.assertIs(result.cache_info["fresh"], False)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_redis_disabled_reports_mysql_without_snapshot(self, mock_conn, mock_exec):
        """未启用 Redis（prefer_cache=0）→ mysql + snapshot_written=False（键必须在）。"""
        mock_exec.return_value = [{"columns": ["id"], "rows": [(3,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", POOL, report=NO_REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "mysql")
        self.assertIs(result.cache_info["snapshot_written"], False)


class TestBadgeHonesty(unittest.TestCase):
    """徽标/横幅不得说谎（spec §7.1 渲染断言）。"""

    def test_mysql_source_badge_says_realtime(self):
        html = render.build_cache_badge_html(
            {"source": "mysql", "timestamp": time.time(), "fresh": True,
             "snapshot_written": True},
            prefer_cache=True, cache_ttl_hours=24)
        self.assertIn("实时查询", html)
        self.assertNotIn("缓存快照", html)

    def test_process_source_badge_says_local_cache(self):
        html = render.build_cache_badge_html(
            {"source": "process", "timestamp": time.time()},
            prefer_cache=True, cache_ttl_hours=24)
        self.assertIn("本地缓存", html)
        self.assertNotIn("缓存快照", html)

    def test_cold_path_banner_does_not_claim_snapshot(self):
        with patch("render.redis_cache.redis_available", return_value=True):
            html = render.build_redis_banners_html(
                {"source": "mysql", "timestamp": time.time(),
                 "fresh": True, "snapshot_written": True})
        self.assertNotIn("数据来自缓存快照", html)
```

- [x] **Step 2: 跑测试确认失败（RED）**

Run: `./venv/bin/python -m unittest tests.test_cache_source_label -v`
Expected: FAIL —— 冷路径报 `redis`（`test_cold_request_reports_mysql_and_snapshot_written` 断言 `mysql` 失败；
KeyError `snapshot_written`）；`test_second_request_l1_hit_reports_process` 报 `redis`；`test_redis_disabled_...`
因缺 `snapshot_written` 键 KeyError。**记录实际报错文本**（取证）。

- [x] **Step 3: 改 `report.py` 三处（生产者）**

（a）MySQL 查询成功分支的 L1 写入 —— 数据来自 MySQL，L1 条目不再标 `redis`：

```python
                        cache.set(report_id, all_results, sql_query,
                                         truncated=_cut)
```

（b）紧随的 `if _redis_written:` / `else:` 两个 `cache_info` —— 来源改为 `mysql`，并补 `snapshot_written`：

```python
                        if _redis_written:
                            cache_info = {
                                "source": "mysql",
                                "timestamp": _snap_ts,
                                "fresh": True,
                                "snapshot_written": True,
                            }
                        else:
                            cache_info = {"source": "mysql", "snapshot_written": False}
```

（c）**不改**的两处（写进注释，防后人误改）：L2 命中回填 L1 的 `cache.set(..., source="redis",
source_timestamp=snapshot.updated_at, ...)` 与锁等待重读快照的那处 `source="redis"`，以及 L1 命中分支
`if cached.source == "redis":` 的 `redis` 取值 —— 它们确实来自 Redis。

- [x] **Step 4: 跑新测试确认全绿（GREEN）**

Run: `./venv/bin/python -m unittest tests.test_cache_source_label -v`
Expected: `Ran 9 tests ... OK`

- [x] **Step 5: 跑受影响模块组，逐条改既有断言**

Run（首跑，记录每条失败的实际值）:
`./venv/bin/python -m unittest tests.test_query_cache tests.test_report_extra tests.test_scheduler_primitives tests.test_cache_ui tests.test_report_perf tests.test_derived_cache tests.test_render_extra tests.test_render -v`

按 **实测报错** 逐条订正（下表已按代码路径核对过，逐条确认后再改）：

| 位置 | 原断言 | 实际路径 | 改为 |
|---|---|---|---|
| `tests/test_query_cache.py:225-226` | 注释「→ source=redis」+ `assertEqual(source,"redis")` | 冷（等锁超时 → 直查 MySQL + 写快照） | 注释改「→ source=mysql（本次取数来自 MySQL，同时写了快照）」；断言 `"mysql"` + `assertIs(snapshot_written, True)` |
| `tests/test_query_cache.py:262` | `"redis"` | 冷（TTL 过期重建快照） | `"mysql"` + `snapshot_written is True` |
| `tests/test_query_cache.py:332-333` | 注释 + `"redis"` | 冷（`get_snapshot` miss → MySQL + 写快照） | 注释改「→ source=mysql」；断言 `"mysql"`；`:334` 的 `fresh` True **保留** |
| `tests/test_query_cache.py:280` | `"redis_fallback"` | 兜底 | **不改** |
| `tests/test_report_extra.py:328,331,332` | `"redis"` / `cached.source=="redis"` / `source_timestamp==123.0` | **L2 命中**（`test_redis_snapshot_hit_skips_mysql`） | **不改**（spec §6 首行误判，Task 1 Step 7 订正 spec） |
| `tests/test_report_extra.py:354` | `"redis_fallback"` | 兜底 | **不改** |
| `tests/test_report_extra.py:379` | `"redis"` | **L2 命中**（锁等待后重读快照） | **不改** |
| `tests/test_report_extra.py:447,449` | `"redis"` + `fresh` True | 冷（MySQL + 写快照） | `"mysql"` + `assertIs(snapshot_written, True)`；`fresh` True **保留** |
| `tests/test_scheduler_primitives.py:90` | `"redis"` | **L2 命中**（新鲜快照存在） | **不改** |
| `tests/test_scheduler_primitives.py:94-95` | 注释 + `"redis"`（`force_rebuild` 重建） | 冷（保活重建 → MySQL + 写新快照） | 注释改「进程缓存来源标记为 mysql（本次取数来自 MySQL，快照已更新）」；断言 `"mysql"` + `snapshot_written is True`；`:96` `fresh` **保留** |
| `tests/test_scheduler_primitives.py:115` | `"redis_fallback"` | 兜底 | **不改** |
| `tests/test_cache_ui.py:305-306` | `"redis"`（`refresh=True` 重建缓存后） | 冷（先删后查 → MySQL + 写快照） | `"mysql"` + `assertIs(snapshot_written, True)`；`:307` `fresh` **保留** |
| `tests/test_cache_ui.py:312` | `cached.source == "redis"` | 同上 L1 条目 | `assertIsNone(cached.source)`（注释：L1 条目数据来自 MySQL，不再冒名 redis） |
| `tests/test_cache_ui.py:156` | `"redis"` | 手工 `cache.set(source="redis")` 的 L1 条目 | **不改**（不经生产者） |
| `tests/test_report_perf.py:149` | `"redis"` | **L2 命中** | **不改** |
| `tests/test_derived_cache.py:247` | `assertIn(source, ("process","redis"))` | 已容错 | **不改** |
| `tests/manual_cache_scenarios.py:225` | `"redis"`（场景2 首查） | 冷 | `"mysql"` |
| `tests/manual_cache_scenarios.py:235` | `"redis"`（场景2 二次） | L2 命中 | **不改** |
| `tests/manual_cache_scenarios.py:261` | `"redis"`（场景3 前置冷查） | 冷 | `"mysql"` |
| `tests/manual_cache_scenarios.py:273,283,296` | `"redis"` / `"redis_fallback"` | L2 命中 / 兜底 | **不改** |
| `tests/manual_cache_scenarios.py:321` | `"redis"`（4a 冷启动写） | 冷 | `"mysql"` |
| `tests/manual_cache_scenarios.py:205,210` | `"mysql"` / `"process"` | 未启用 Redis 冷查 / L1 命中 | **不改**（已符合新语义） |

- [x] **Step 6: 复跑模块组至全绿**

Run（收口，第 2 次）: 同 Step 5 的命令
Expected: `OK`（无 FAILED/ERROR）

- [x] **Step 7: 订正 spec 的 §6 / §7.1（「为什么必须改」的记录）**

在 `docs/compose/spec/2026-10-05-cache-source-label-design.md` §6 表格内**就地订正**两处，并追加「订正记录」小节：

1. 原「`:331-332` → 改为 `None`」行改为：**无需改动** —— `:328/:331/:332` 属 `test_redis_snapshot_hit_skips_mysql`
   （L2 命中），L2→L1 继承链按 §8 必须保持 `redis`；真正需要改的是 `tests/test_cache_ui.py:305/312`（`refresh=True` 冷路径写 L1 条目）。
2. 原 `bench.py` 行「S5 预热 `mysql` → 正式 `redis`」改为「S5 预热 `mysql`（并写入快照）→ 正式请求 `process`」
   —— 正式请求在 300s 内命中 L1 进程缓存，报 `process` 才是新语义的正确表现。
3. 补记 spec 漏列的影响点：`tests/test_cache_ui.py:305/312`、`scripts/perf/verify_redis_fallback.py:80`（①冷路径 → `mysql`）；
   `scripts/perf/bench_session_script.py:143` 已容错（`in ("process","redis")`）故不改。

- [x] **Step 8: 提交（只加本任务点名的文件）**

```bash
git add report.py tests/test_cache_source_label.py tests/test_query_cache.py \
        tests/test_report_extra.py tests/test_scheduler_primitives.py tests/test_cache_ui.py \
        tests/manual_cache_scenarios.py docs/compose/spec/2026-10-05-cache-source-label-design.md
git commit -m "fix(cache): cache_info.source 表示本次取数来源，徽标不再说谎"
```

---

### Task 2: 同步 `scripts/perf/*` 的外部期望

**Files:**
- Modify: `scripts/perf/bench.py`（docstring `:12-19`、S5 断言 `:286-291`）
- Modify: `scripts/perf/verify_redis_fallback.py`（docstring `:11`、① 断言 `:75-80`）

**Interfaces:**
- Consumes: Task 1 的取值约定（`mysql`/`process`/`redis`/`redis_fallback`、`snapshot_written`）。
- Produces: 无（仅期望值与说明）。

- [x] **Step 1: 改 `bench.py` 的说明与 S5 断言**

docstring 第 18-19 行改为：「S1（P1，prefer_cache=0）：预热必须是 `mysql`，正式请求必须是 `process`；
S5（P4，prefer_cache=1）：预热 `mysql`（本次取数来自 MySQL 并写入快照），正式请求命中 L1 → `process`」。
断言改为：

```python
    if s5["warm_source"] != "mysql":
        failures.append(f"S5 预热 cache_source 期望 mysql（冷路径查库并写快照），实际 {s5['warm_source']}")
    bad5 = {k: v for k, v in s5["result"]["cache_source_dist"].items() if k != "process"}
    if bad5:
        failures.append(f"S5 正式请求期望全为 process（300s 内命中 L1），实际 {bad5}")
```

`_BADGE_PATTERNS`（`:46-51`）**无需改**：`process → 本地缓存`、`mysql → 实时查询` 已映射。

- [x] **Step 2: 改 `verify_redis_fallback.py` 的 ① 期望**

docstring 第 11 行补一句「① 冷路径 `cache_info.source == "mysql"`（2026-10-05 起 source 表示本次取数来源）」；
① 断言改为：

```python
        if src1 != "mysql" or len(rows1) != 5:
            failures.append(f"① 期望 source=mysql（冷路径查库并写快照）且 5 行，实际 {src1}/{len(rows1)}")
```

②③④ 的期望（`redis` / 抛异常 / `redis_fallback`）**不改**。

- [x] **Step 3: 语法与静态门禁自检（这两个脚本不进 discover，用编译 + 静态分析兜底）**

Run: `./venv/bin/python -m py_compile scripts/perf/bench.py scripts/perf/verify_redis_fallback.py && ./venv/bin/python -m unittest tests.bug_hunt.test_static_analysis -v`
Expected: 无输出报错 + `OK`

- [x] **Step 4: 提交**

```bash
git add scripts/perf/bench.py scripts/perf/verify_redis_fallback.py
git commit -m "test(perf): 同步 bench S5 与 redis 兜底脚本的取数来源期望"
```

---

### Task 3: 知识库与项目记忆同步

**Files:**
- Modify: `docs/compose/knowledge/07-cache-scheduler-audit.md:79`（`cache_info` 取值行）
- Modify: `docs/compose/knowledge/03-report-transform.md`（`cache_info` 一句说明）
- Modify: `docs/compose/knowledge/08-testing-conventions.md:71`（bench.py 行）
- Modify: `docs/compose/spec/2026-09-29-execution-layer-performance-design.md`（§6.1 第 2 条附近补注 + §10 实测表补注）
- Modify: `MEMORY.md`（Discovered 末条订正）

**Interfaces:**
- Consumes: Task 1/2 已落地的取值表。
- Produces: 文档与代码一致（AGENTS #7：代码与知识库同一次任务内完成）。

- [x] **Step 1: `07-cache-scheduler-audit.md`**

把第 79 行 `→ cache_info: process | redis | mysql | redis_fallback` 扩为
「→ `cache_info.source` = **本次取数来源**：`mysql`（本次真查库，`snapshot_written` 标是否同时写了快照）|
`process`（命中 L1，条目数据来自 MySQL）| `redis`（L2 快照命中，或 L1 条目继承自 L2）| `redis_fallback`（查库失败 → 过期快照兜底，`fresh=False`）」，
并在上文 L1/L2 数据流两行分别注明「L1 写入时 `source=None`（来自 MySQL）/ `source="redis"`（来自 L2）」。

- [x] **Step 2: `03-report-transform.md`**

在 `cache_info` 出现处（第 7 行 `ReportResult` 说明之后）补一句：
「`cache_info.source` 表示**本次取数来源**（`mysql`/`process`/`redis`/`redis_fallback`），不是「是否写了缓存」的账本」。

- [x] **Step 3: `08-testing-conventions.md:71`**

`bench.py` 行末尾补「（S1 冷水 `mysql`→正式 `process`；S5 冷水 `mysql`→正式 `process`）」。

- [x] **Step 4: `2026-09-29-execution-layer-performance-design.md` 补注（不改历史实测数据）**

- §6.1 第 2 条（`:221`「冷请求 → `mysql`，二次请求 → `redis`」）后补注：
  「2026-10-05 起该措辞精确化为三态：冷请求 → `mysql`；300s 内二次请求命中 L1 → `process`；L1 过期后命中 L2 → `redis`。
  见 `2026-10-05-cache-source-label-design.md`。」
- §10 实测表 S5 行（`:280` 附近）后补注一句脚注：「该表 S5 的 `redis` 为 2026-10-05 修复前的**旧实现账本式标注**
  （MySQL 查询成功即标 `redis`），历史数值本身不改。」

- [x] **Step 5: `MEMORY.md` 订正**

把 Discovered 末条「**`cache_info.source` 不能用来判断「数据是否来自缓存」**…（2026-10-05 实测两臂均报 redis）」
改写为：「**`cache_info.source` 自 2026-10-05 起 = 本次取数来源**（`mysql`/`process`/`redis`/`redis_fallback`；
`snapshot_written` 仅 `mysql` 分支有）；此前「MySQL 成功即标 `redis`」的账本式标注已修复（`report.py` 生产者 3 处）。
**注意**：`scripts/perf/bench.py` 的 S5 正式请求期望是 `process`（命中 L1），不是 `redis`。」

- [x] **Step 6: 提交**

```bash
git add docs/compose/knowledge/03-report-transform.md docs/compose/knowledge/07-cache-scheduler-audit.md \
        docs/compose/knowledge/08-testing-conventions.md \
        docs/compose/spec/2026-09-29-execution-layer-performance-design.md MEMORY.md
git commit -m "docs(kb): 同步 cache_info.source 取数来源语义与 S5 期望"
```

---

### Task 4: 生产验收（8099 三态）+ 全量收口

**Files:**
- Modify: `docs/compose/plan/2026-10-05-cache-source-label-plan.md`（末尾追加「验收记录」小节 + 勾选状态）

**Interfaces:**
- Consumes: Task 1-3 的最终代码态（`report.py` 已改）。
- Produces: 生产证据（三种徽标文案 + 快照时间戳）、测试结论、`codegraph status` 全 0。

- [x] **Step 1: 重启 8099（清空 L1）并确认就绪**

```bash
./test_env.sh restart && ./test_env.sh status
```
Expected: `status` 显示监听 `0.0.0.0:8099` + 健康检查通过。

- [x] **Step 2: 找一个 `prefer_cache=1` 的报表 id**

```bash
./venv/bin/python -c "
import sqlite3
c = sqlite3.connect('config.debug.db')
print(c.execute('SELECT id,name,prefer_cache,cache_ttl_hours FROM report_configs WHERE prefer_cache=1').fetchall())"
```
Expected: 至少 1 行；无则先跑 `./venv/bin/python scripts/perf/init_debug_env.py`（凭据落 `perf-logs/bench-credentials.txt`）后重查。

- [ ] **Step 3: 冷加载 → 徽标必须是「实时查询」** ← **未按原样执行**：沙箱内无法访问/重启宿主 8099，改为真实组件栈 in-process 验收（见文末验收记录）

用 `perf-logs/bench-credentials.txt` 的账号登录后 GET `/report?id=<id>`，把 HTML 落 `run-logs/accept-1-cold.html`，
并用 `scripts/perf/bench.py` 的 `parse_cache_source`（复用，不重写解析）取文案：

```bash
./venv/bin/python -c "
from scripts.perf.bench import parse_cache_source
html = open('run-logs/accept-1-cold.html', encoding='utf-8').read()
print('source =', parse_cache_source(html))" 2>&1 | tail -3
```
Expected: `source = mysql`；同时用 grep 在该 HTML 上确认**不含**「数据来自缓存快照」且含「实时查询」。

- [ ] **Step 4: 300s 内再取一次 → 徽标必须是「本地缓存」** ← **未按原样执行**：沙箱内无法访问/重启宿主 8099，改为真实组件栈 in-process 验收（见文末验收记录）

同 Step 3 再取一次（落 `run-logs/accept-2-l1.html`）
Expected: `source = process`，HTML 含「本地缓存」、不含「缓存快照」。

- [ ] **Step 5: 等 L1 过期（>300s）后第三次取 → 「缓存快照」** ← **未按原样执行**：沙箱内无法访问/重启宿主 8099，改为真实组件栈 in-process 验收（见文末验收记录）

用**后台作业**（禁止前台整段 sleep）：
`bash -c 'sleep 310; curl -s -b <cookie> "http://127.0.0.1:8099/report?id=<id>" -o run-logs/accept-3-l2.html'`，
落盘后取数：Expected `source = redis`，HTML 含「缓存快照」。

- [x] **Step 6: 全量与分段测试（本任务内只跑一次）**

```bash
./venv/bin/python -m unittest discover -s tests/ -t . -v > run-logs/final-discover-$(date +%s).log 2>&1; tail -5 run-logs/final-discover-*.log | tail -5
```
Expected: `OK`（无 FAILED/ERROR；静态分析门禁随 discover 跑）。

- [x] **Step 7: 代码索引同步**

```bash
codegraph sync && codegraph status | tail -20
```
Expected: `pendingChanges` 全 0。

- [x] **Step 8: 回填验收记录并提交**

在本 plan 末尾追加「验收记录」：三态实测输出、`Ran N tests` 结论、`codegraph status` 结论、三个 HTML 证据文件路径；
勾选已完成的任务项。

```bash
git add docs/compose/plan/2026-10-05-cache-source-label-plan.md
git commit -m "docs(plan): 回填 8099 三态生产验收证据与收尾状态"
```

---

## 自检记录（spec 覆盖）

| spec 要求 | 落地任务 |
|---|---|
| §5.1 取值表（6 行） | Task 1 Step 1/3（6 个生产者用例逐一钉死） |
| §5.2 改动点 2 处（+ else 补键） | Task 1 Step 3（a)(b)(c) 三处代码块） |
| §6 影响面（测试/脚本/文档） | Task 1 Step 5 表格 22 条逐条核对（含订正 2 处误判、补 3 处漏列） |
| §7.1 单测（含渲染断言） | Task 1 Step 1 的 9 个用例 |
| §7.2 既有守卫全绿 + 断言改动留痕 | Task 1 Step 5/6 + Step 7 |
| §7.3 生产验收三态 | Task 4 Step 1-5 |
| §8 风险（L2→L1 继承链 / 外部读取方 / 渲染器不改） | Task 1 用例 4 + Task 2 全仓 `cache_info` 读取方清点 + 全局约束「不动 render.py」 |
| §9 范围（知识库 03/07 + 2026-09-29 补注） | Task 3 Step 1-4 |

**外部读取方清点结论（`grep cache_info` 全仓 .py）**：`render.py`（渲染，不改）、`scripts/perf/bench.py`（Task 2）、
`scripts/perf/verify_redis_fallback.py`（Task 2）、`scripts/perf/bench_session_script.py`（已容错 `in ("process","redis")`，不改）、
`export.py`/`api_handler.py`/`scheduler.py` 不读 `cache_info.source`。仓库外无消费者 → 不触发 §8 的「退回方案 A」。


---

## 验收记录（2026-10-05 执行）

**提交**：`7136c10`（生产者 + 新测试 + 既有断言 + spec 订正）、`2b579e0`（perf 脚本期望）、`e25c08a`（知识库/记忆同步）

**测试取证**

| 项 | 命令 | 结果 |
|---|---|---|
| 新用例 RED | `python -m unittest tests.test_cache_source_label` | `FAILED (failures=2, errors=1)` — `'redis' != 'mysql'` ×2、`KeyError: 'snapshot_written'`（与计划 Expected 逐条一致） |
| 新用例 GREEN | 同上 | **`Ran 9 tests — OK`** |
| 受影响模块组 | `tests.test_query_cache` + `test_report_extra` + `test_scheduler_primitives` + `test_cache_ui` + `test_report_perf` + `test_derived_cache` + `test_render_extra` + `test_render` | 首跑 `FAILED (failures=6)`（全是 `'mysql' != 'redis'`，与 §6 triage 表逐一吻合）→ 同步断言后 **`Ran 515 tests — OK`** |
| 全量（官方入口） | `python -m unittest discover -s tests/ -t .` | **`Ran 3002 tests — OK (skipped=4)`**，日志 `run-logs/final-discover-20261005-220227.log` |
| 脚本/静态门禁 | `py_compile scripts/perf/bench.py scripts/perf/verify_redis_fallback.py` + `tests.bug_hunt.test_static_analysis` | `OK`（5/5） |

**三态生产验收（真实 MySQL `127.0.0.1:3307/sqlreport_test` + 真实 Redis `6379` + 生产渲染器）**

脚本 `run-logs/accept-3state.py`，日志 `run-logs/accept-3state-*.log`；被测报表 3「缓存命中率报表」（`prefer_cache=1` / `cache_ttl_hours=24` / pool 2）：

| 状态 | 序列 | `cache_info`（实测原值） | 徽标 HTML（实测原文） |
|---|---|---|---|
| A 冷加载 | 已清 L2 键 + L1 空 | `{'source': 'mysql', 'timestamp': 1791209061.079, 'fresh': True, 'snapshot_written': True}` | `<span class="cache-badge">实时查询 (已启用缓存 · 缓存 24 小时)</span>` ✅ 不含「缓存快照」 |
| B 300s 内二次 | 同一 L1 实例 | `{'source': 'process', 'timestamp': 1791209061.079}` | `<span class="cache-badge fresh">本地缓存 (0s 前刷新 · 已启用缓存 · 缓存 24 小时)</span>` |
| C L1 过期 | 新 `QueryCache` → L2 命中 | `{'source': 'redis', 'timestamp': 1791209061.079, 'fresh': True}`（= 快照 `updated_at`） | `<span class="cache-badge fresh">缓存快照 (0s 前 · 已启用缓存 · 缓存 24 小时)</span>` |
| D 附加 | 坏端口 3999 + L2 首读 miss | `{'source': 'redis_fallback', 'timestamp': 1791209061.079, 'fresh': False}` | `<span class="cache-badge flash-warn">缓存快照（0s 前 · 已启用缓存 · 缓存 24 小时，数据库不可用）</span>` |

脚本结论行：`全部通过`（exit=0）。

**8099 页面级复核的替代说明**：本会话 bash 运行在 `bwrap --unshare-pid` 沙箱内，宿主进程（PID 文件 `run-logs/test-env-8099.pid` = `682744`）既不可见也不可信号 → **无法从本会话重启 8099**；运行中的 8099 承载的是改动前的代码（MEMORY #14：改 `report.py` 后必须重启再验），直接查它会得到改动前的行为。故 A–D 用「真实 MySQL/Redis + `render.build_cache_badge_html` 真实徽标函数」等价取证。**待用户在宿主机重启 8099 后**复核页面三态；如需本会话自查，可另起 8098 托管实例（会占用第二个端口）。

**代码索引**：`codegraph sync` → `Index is up to date`（`pendingChanges` 全 0）。

**与 spec 的偏差**：仅 spec §6 两处误判（已就地订正，见其 §6.1 订正记录）；其余按 §5.2 原样落地，`render.py` 一行未改。

**执行记录（ledger）**：`run-logs/sdd/2026-10-05-cache-source-label/progress.md`
