# B4 工作包（P0 调度器：保活节拍/连接泄漏 + 任务永久停摆）

> 本文件是 **B4 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B4
> 开工基线：`Ran 3077 tests, OK (skipped=4)`（B3 后）
> 放在 `docs/compose/reports/`（`run-logs/` 会被 `cleanup_tmp.py` 删除）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. **只改 `scheduler.py`**，测试新建 `tests/test_b4_scheduler_safety.py`。
4. 不改变可观测行为，除任务明确要改的。
5. 用户可感知文字一律简体中文（硬性 #2）。
6. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
7. 中断恢复：只做一件事；被中断不要重做。

## 0.1 关键背景：本批与 B2 的关系

B2 刚改了 `db.get_config_db()`（现在返回**池化连接**，`close()` 语义是「归还池」）。
本批在 `scheduler.py` 上加 try/finally 保护——**两者互不冲突**，但注意：
`conn.close()` 在池化后依然是「归还」，**既有调用点一律不要改它的语义**。

---

## 1. 三个已核实的缺陷（行号实测）

### 缺陷 A：保活没有独立节拍（`_next_keepalive_at` 是死字段）
```
scheduler.py:273   self._next_keepalive_at = 0.0     ← 全仓仅此一处赋值，从未被读
scheduler.py:303-311  while not self._stop_event.wait(self._tick_seconds):
                          self.run_tick()
                          self.run_keepalive_tick()   ← 每个 tick 都跑
```
`app_config.json` 的 `scheduler.tick_seconds = 30` → 每 30 秒就全量扫一次 `report_configs`
JOIN 两张表并探测 Redis，**只为判断"是否临近过期"**。

### 缺陷 B：保活连接无 `try/finally`（泄漏面）
```
scheduler.py:622   conn = db.get_config_db()
scheduler.py:624-629   rows = [... conn.execute("SELECT DISTINCT ...") ...]   ← 抛异常则泄漏
scheduler.py:662   conn.close()                                             ← 永远到不了
```
对照：`run_startup_scan`（`:538-597`）与 `_run_schedule`（`:408-425`）**都有** try/finally，
唯独 `run_keepalive_tick` 没有。

### 缺陷 C：任务可被**永久**卡死（最严重）
```
scheduler.py:408   conn = db.get_config_db()    ← 在 try: 之外！（行号已按实测校正）
scheduler.py:409   try:
scheduler.py:422-425   finally:
                           self._running.discard(sid)   ← 释放只在这里
                           conn.close()
```
`:408` 一旦抛异常（DB 抖动 / 池不可用），`finally` **不会执行** → `sid` 永久留在 `_running`
→ 之后每次 `run_tick` 都 `continue` 跳过它 → **该任务在本进程生命周期内
再也不会被派发，且无任何告警**。

> **签名实测**（不要搞错）：`_run_schedule(self, sched: dict, trigger: str, session_user=None)`。
> `finished` / `started` 是**函数内局部变量**，不是参数。测试最多传 3 个位置参数。
> 真实调用点：`:524` `(sched, "manual", session_user=…)`；`:352/565/580` 用 `executor.submit`。

---

## 2. Task B4-1：保活独立节拍 + 连接泄漏防护

**Files**
- Modify: `scheduler.py`（`_tick_loop` :303-311、新增 `_maybe_run_keepalive`、`run_keepalive_tick` :607-663）
- Test: 新建 `tests/test_b4_scheduler_safety.py`

### Step 1 — 写测试

```python
# tests/test_b4_scheduler_safety.py
import unittest
from unittest import mock

import scheduler


class TestKeepaliveConnSafety(unittest.TestCase):
    """缺陷 B：保活连接必须有 try/finally，SELECT 抛异常时也得归还。"""

    def test_keepalive_closes_conn_when_select_raises(self):
        sched = scheduler.ReportScheduler(tick_seconds=999, workers=1)
        closed = {"v": False}

        class BadConn:
            def execute(self, *a, **k):
                raise RuntimeError("select boom")
            def close(self):
                closed["v"] = True

        with mock.patch.object(scheduler.db, "get_config_db",
                               return_value=BadConn()), \
             mock.patch.object(scheduler.redis_cache, "redis_available",
                               return_value=True), \
             mock.patch.object(scheduler.redis_cache, "get_redis_manager",
                               return_value=mock.MagicMock()):
            with self.assertRaises(RuntimeError):
                sched.run_keepalive_tick()
        self.assertTrue(closed["v"], "SELECT 抛异常后连接未被归还（泄漏）")


class TestKeepaliveCadence(unittest.TestCase):
    """缺陷 A：保活必须按独立节拍跑，而不是每个 tick 都跑。"""

    def test_skipped_when_interval_not_reached(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._next_keepalive_at = 9e18           # 远未来
        with mock.patch.object(sched, "run_keepalive_tick") as m:
            sched._maybe_run_keepalive(now=1000.0)
            m.assert_not_called()

    def test_runs_and_reschedules_when_due(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._next_keepalive_at = 0.0
        with mock.patch.object(sched, "run_keepalive_tick", return_value=0) as m:
            sched._maybe_run_keepalive(now=1000.0)
            m.assert_called_once()
        self.assertGreater(sched._next_keepalive_at, 1000.0,
                           "执行后必须把下次节拍推后")

    def test_tick_loop_uses_maybe_run_keepalive(self):
        """护栏：循环里不得再直接调 run_keepalive_tick。"""
        import inspect
        src = inspect.getsource(scheduler.ReportScheduler._tick_loop)
        self.assertIn("_maybe_run_keepalive", src)
        self.assertNotIn("self.run_keepalive_tick()", src)
```

### Step 2 — 跑确认失败
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b4_scheduler_safety.py' -t . 2>&1 | tail -5
```
Expected: `AttributeError: 'ReportScheduler' object has no attribute '_maybe_run_keepalive'`；
连接归还测试也应 FAIL。

### Step 3 — 实现

**① 模块级常量**（放在其他调度常量附近）：
```python
#: 保活扫描的独立节拍（秒）。保活是「提前重建临近过期的缓存」，
#: 不需要跟着 tick_seconds（默认 30s）跑——那样每 tick 都要全量扫
#: report_configs 并探测 Redis，纯浪费。
_KEEPALIVE_INTERVAL_SECONDS = 300
```

**② 新增 `_maybe_run_keepalive`**：
```python
def _maybe_run_keepalive(self, now: float = None) -> int:
    """按独立节拍执行保活扫描（未到点直接返回 0）。"""
    now = time.time() if now is None else now
    if now < self._next_keepalive_at:
        return 0
    self._next_keepalive_at = now + _KEEPALIVE_INTERVAL_SECONDS
    return self.run_keepalive_tick(now=now)
```
> 注意：先推后跑还是先跑后推？**用上面的顺序**（先推时间戳再跑）。
> 理由：若 `run_keepalive_tick` 抛异常，下次不会因为时间戳没更新而下个 tick 立刻重试，
> 避免异常时的忙循环。

**③ `_tick_loop` 里替换调用**：
```python
            try:
                self._maybe_run_keepalive()      # ← 原为 self.run_keepalive_tick()
            except Exception:
                logging.exception("调度器保活 tick 异常")
```

**④ 给 `run_keepalive_tick` 的连接加 try/finally**：
把 `:622` 的 `conn = db.get_config_db()` 到 `:662` 的 `conn.close()` 包起来：
```python
        conn = db.get_config_db()
        try:
            # DISTINCT：同一报表可挂多个任务（多对多），不去重会重复重建
            rows = [dict(r) for r in conn.execute(
                "SELECT DISTINCT rc.* FROM report_configs rc "
                ... 既有 SQL 原样不动 ...
            )]
            ... 既有循环体原样不动 ...
        finally:
            conn.close()
```
> ⚠️ **只加 try/finally 外壳，内部逻辑一行都不要改**（尤其是 `_rebuild_static_files(conn, rpt)`
> 依赖 `conn` 在循环内仍可用）。

### Step 4 — 跑确认通过
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b4_scheduler_safety.py' -t . 2>&1 | tail -3
```

### Step 5 — 回归（调度器相关全部）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_scheduler*.py' -t . 2>&1 | tail -3
```

### Step 6 — 报告（六行内）
1. 改动文件与行号
2. 新测试结果（精确 `Ran N tests, OK`）
3. `test_scheduler*.py` 结果（精确 `Ran N tests, OK`）
4. `_KEEPALIVE_INTERVAL_SECONDS` 取值
5. `run_keepalive_tick` 内部逻辑是否一行未改（必须：是）
6. `_tick_loop` 里是否已无直接 `run_keepalive_tick()` 调用

---

## 3. Task B4-2：`_running` 去重集在取连接失败时永不释放

> **仅在 B4-1 验收通过后开始。**

**Files**
- Modify: `scheduler.py`（`_run_schedule` 约 :408-425）
- Test: 追加到 `tests/test_b4_scheduler_safety.py`

### Step 1 — 写失败测试

```python
class TestRunningSetRelease(unittest.TestCase):
    """缺陷 C：取连接失败时 sid 必须从 _running 释放，否则任务永久停摆。"""

    def test_sid_released_when_conn_acquisition_fails(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._running.add(42)
        with mock.patch.object(scheduler.db, "get_config_db",
                               side_effect=RuntimeError("db down")):
            try:
                # ⚠️ 签名实测为 (self, sched, trigger, session_user=None)
                # finished/started 是函数内局部变量，不是参数——不要多传
                sched._run_schedule({"id": 42, "name": "t", "report_id": 1},
                                    "success")
            except Exception:
                pass
        self.assertNotIn(42, sched._running,
                         "取连接失败后 sid 仍留在 _running（任务永久停摆）")

    def test_sid_released_on_normal_path(self):
        """正常路径仍要释放（防回归）。"""
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._running.add(43)
        with mock.patch.object(scheduler.db, "get_config_db",
                               return_value=mock.MagicMock()), \
             mock.patch.object(scheduler.config_db, "get_schedule",
                               return_value=None), \
             mock.patch.object(scheduler.config_db, "mark_schedule_result"):
            sched._run_schedule({"id": 43, "name": "t2", "report_id": 1},
                                "success")   # 签名：3 参，不多传
        self.assertNotIn(43, sched._running)
```

### Step 2 — 跑确认失败
Expected: `test_sid_released_when_conn_acquisition_fails` FAIL（`42 unexpectedly found in _running`）

### Step 3 — 改 `_run_schedule`

把取连接移进 `try`，并让 `finally` 容忍 `conn` 未绑定：
```python
        conn = None
        try:
            conn = db.get_config_db()
            ... 既有回写逻辑原样不动 ...
        except Exception:
            logging.exception("定时任务 #%s 结果回写失败", sid)
        finally:
            with self._running_lock:
                self._running.discard(sid)
            if conn is not None:
                conn.close()
```
> ⚠️ `if conn is not None` 是必需的：`get_config_db()` 自身抛异常时 `conn` 未绑定，
> 直接 `conn.close()` 会 `NameError`（并把真正的异常盖掉）。

### Step 4 — 跑确认通过 + 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b4_scheduler_safety.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_scheduler*.py' -t . 2>&1 | tail -3
```

### Step 5 — 报告（五行内）
1. 改动文件与行号
2. 新测试结果（精确 `Ran N tests, OK`）
3. `test_scheduler*.py` 结果
4. 是否用了 `conn = None` + `if conn is not None`（必须：是）
5. `_running.discard(sid)` 是否仍在 `finally` 里且无条件执行（必须：是）

---

## 4. B4 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3082` / `OK (skipped=4)`（3077 + B4 新增用例）。
