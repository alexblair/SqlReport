"""B4-1：保活独立节拍 + 保活连接泄漏防护。

依据：docs/compose/reports/b4-work-brief.md §2。
"""
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


class TestRunningSetRelease(unittest.TestCase):
    """缺陷 C：取连接失败时 sid 必须从 _running 释放，否则任务永久停摆。"""

    def test_sid_released_when_conn_acquisition_fails(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._running.add(42)
        with mock.patch.object(scheduler.db, "get_config_db",
                               side_effect=RuntimeError("db down")):
            try:
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
                                "success")
        self.assertNotIn(43, sched._running)
