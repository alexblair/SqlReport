"""test_scheduler_core.py — 调度器核心测试（T3）。

覆盖规格 .scratch/report-scheduler/spec.md 缺口：
- G4 compute_next_run 纯函数（interval/daily/跨日/当日已过/防漂移/非法值）
- G5 tick 到期扫描 + running 在途去重（B7）
- G6 启动 misfire 三分支（B8 合并补跑 / B9 skip 推进+审计 / B10 run_once 当日一次）
- G7 熔断（B5 连败 5 次停止派发）与手动触发重置（B6）
- G10 保活阈值边界判定（B13：剩余 TTL < ahead_seconds 才触发 force_rebuild）
- G12 审计 scheduled_run / scheduled_misfire（B19/B20）

测试策略：
- 临时 SQLite 文件库 + patch app_config.get_config 配置隔离（模式同
  test_scheduler_primitives），调度器经 db.get_config_db() 自建的每个
  连接均落在临时库上；
- ReportScheduler._executor 替换为同步/挂起双模式假执行器：sync 模式
  提交即执行（结果回写可立即断言），pending 模式仅登记提交（模拟在途，
  验证去重）；
- execute_report / audit_db.record_operation / redis 管理器全部 mock，
  不触真实外部依赖；不起真线程，直接调用各同步入口。
"""

import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import config_db
import db
import redis_cache
import scheduler
from redis_cache import ReportSnapshot


# ---------------------------------------------------------------------------
# 临时库与环境隔离（内联建表 DDL：项目惯例，有意重复避免循环导入）
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_core_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")


def _test_config() -> dict:
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _set_up_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL, password TEXT NOT NULL,
            database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, memo TEXT, prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1,
            max_rows INTEGER NOT NULL DEFAULT 100000,
            keepalive_enabled INTEGER NOT NULL DEFAULT 0,
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL,
            name TEXT NOT NULL, url_path TEXT UNIQUE NOT NULL,
            output_format TEXT NOT NULL DEFAULT 'json', columns TEXT, filters TEXT,
            sorts TEXT, row_limit INTEGER DEFAULT 0, api_key TEXT,
            allowed_origins TEXT, enabled INTEGER NOT NULL DEFAULT 1,
            result_mode TEXT NOT NULL DEFAULT 'single',
            result_index INTEGER NOT NULL DEFAULT 0,
            allow_fetch_all INTEGER NOT NULL DEFAULT 1,
            static_cache INTEGER NOT NULL DEFAULT 1,
            json_no_quotes INTEGER NOT NULL DEFAULT 0,
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
            json_template TEXT, description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS report_schedules (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id        INTEGER NOT NULL UNIQUE,
            schedule_type    TEXT    NOT NULL DEFAULT 'interval',
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            daily_time       TEXT    NOT NULL DEFAULT '08:00',
            misfire_policy   TEXT    NOT NULL DEFAULT 'skip',
            enabled          INTEGER NOT NULL DEFAULT 1,
            next_run_at      REAL,
            last_run_at      REAL,
            last_status      TEXT,
            last_error       TEXT,
            fail_count       INTEGER NOT NULL DEFAULT 0,
            last_duration_ms INTEGER,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()


_set_up_db()


def _local_ts(year, month, day, hour, minute, second=0):
    """构造本地时区固定时刻的 epoch 秒（DST 交给 libc 决策）。"""
    return time.mktime((year, month, day, hour, minute, second, 0, 0, -1))


# 固定"今天"：2026-08-21 15:00 本地时间
NOW = _local_ts(2026, 8, 21, 15, 0, 0)


class _FakeExecutor:
    """同步/挂起双模式假执行器。

    mode="sync"：submit 立即执行 fn（生产 ThreadPoolExecutor 的完成语义）；
    mode="pending"：仅登记提交（模拟任务在途，供去重断言）。
    """

    def __init__(self):
        self.mode = "sync"
        self.submitted = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        if self.mode == "sync":
            fn(*args, **kwargs)
        return None

    def shutdown(self, wait=True):
        pass


class SchedulerCoreTest(unittest.TestCase):
    """调度器核心公共环境：临时库 + 种子数据 + 全量 mock。"""

    def setUp(self):
        # 配置隔离：db.get_config_db() 全部落到临时库
        cfg_patcher = patch("app_config.get_config",
                            return_value=_test_config())
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)

        # 清表并植入种子：1 池 + 1 报表
        conn = _get_conn()
        for table in ("report_schedules", "api_endpoints", "report_configs",
                      "connection_pools"):
            conn.execute(f"DELETE FROM {table}")
        # 种子行显式固定 id=1：临时文件库跨测试方法持久，
        # AUTOINCREMENT 序号会递增，写死 id 保证 self.report_id 恒有效
        conn.execute(
            "INSERT INTO connection_pools "
            "(id,name,host,port,user,password,database,sort_order) "
            "VALUES (1,'pool','127.0.0.1',3306,'root','p','db',1)")
        conn.execute(
            "INSERT INTO report_configs (id,name,sql_query,default_page_size,"
            "pool_id,prefer_cache,cache_ttl_hours,keepalive_enabled,"
            "keepalive_ahead_seconds) "
            "VALUES (1,'报表A','SELECT 1',20,1,1,0,0,0)")
        conn.commit()
        conn.close()
        self.pool_id = 1
        self.report_id = 1

        # 审计收集（scheduler 经 config_db._write_audit_log → audit_db.record_operation）
        self.audit_calls = []

        def _record(session_user, action, entity_type, **kw):
            self.audit_calls.append(dict(
                user=session_user, action=action, entity_type=entity_type,
                entity_id=kw.get("entity_id"), entity_name=kw.get("entity_name"),
                after_value=kw.get("after_value"),
                log_type=kw.get("log_type", "operation")))
            return True

        audit_patcher = patch("audit_db.record_operation", side_effect=_record)
        audit_patcher.start()
        self.addCleanup(audit_patcher.stop)

        # execute_report mock（定时与保活共用入口）
        exec_patcher = patch("report.execute_report")
        self.mock_exec = exec_patcher.start()
        self.addCleanup(exec_patcher.stop)

        # Redis 默认不可用（保活用例自行打开）
        avail_patcher = patch("scheduler.redis_cache.redis_available",
                              return_value=False)
        avail_patcher.start()
        self.addCleanup(avail_patcher.stop)
        self.mgr = MagicMock()
        self.mgr.key_prefix = "sr"
        self.mgr.get_snapshot.return_value = None
        mgr_patcher = patch("scheduler.redis_cache.get_redis_manager",
                            return_value=self.mgr)
        mgr_patcher.start()
        self.addCleanup(mgr_patcher.stop)

        # 调度器实例：替换为假执行器（不起真线程/线程池）
        self.executor = _FakeExecutor()
        self.sched = scheduler.ReportScheduler(tick_seconds=30, workers=2)
        self.sched._executor = self.executor
        # 全局单例卫生：隔离其他测试文件可能遗留的单例状态
        scheduler._scheduler = None
        self.addCleanup(setattr, scheduler, "_scheduler", None)

    # -- 公共辅助 ----------------------------------------------------------

    def _add_schedule(self, report_id=None, next_run_at=1000.0,
                      last_run_at=None, **kw):
        """经 CRUD 建任务行（贴近真实写入路径），返回 schedule_id。

        last_run_at 是运行时回写字段、不在 upsert 签名内，
        非 None 时以 SQL 直接预置。
        """
        conn = _get_conn()
        try:
            args = dict(report_id=self.report_id if report_id is None else report_id,
                        schedule_type="interval", interval_minutes=30,
                        daily_time="08:00", misfire_policy="skip",
                        enabled=1, next_run_at=next_run_at)
            args.update(kw)
            sid = config_db.upsert_schedule(conn, session_user=None, **args)
            if last_run_at is not None:
                conn.execute(
                    "UPDATE report_schedules SET last_run_at=? WHERE id=?",
                    (last_run_at, sid))
                conn.commit()
            return sid
        finally:
            conn.close()

    def _row(self, schedule_id):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_schedules WHERE id=?",
                (schedule_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _audit_of(self, action):
        return [a for a in self.audit_calls if a["action"] == action]

    def _snapshot_with_remaining(self, remaining_seconds, ttl_hours=6,
                                 now=NOW):
        """构造剩余有效期恰为 remaining_seconds 的快照。"""
        return ReportSnapshot(
            results=[{"columns": ["id"], "rows": [[1]], "total": 1}],
            sql_query="SELECT 1",
            updated_at=now + remaining_seconds - ttl_hours * 3600,
            config_version="v-test")


# ---------------------------------------------------------------------------
# G4：compute_next_run 纯函数
# ---------------------------------------------------------------------------

class TestComputeNextRun(unittest.TestCase):
    """next_run_at 计算：注入固定 now，覆盖 interval/daily/非法输入。"""

    def test_interval_from_now(self):
        self.assertEqual(scheduler.compute_next_run(
            "interval", 30, "08:00", NOW), NOW + 1800)

    def test_interval_anti_drift_uses_future_last_run(self):
        """last_run_at 晚于 now：以 last_run_at 为基准顺延（防重启漂移叠加）。"""
        future_last = NOW + 600
        self.assertEqual(scheduler.compute_next_run(
            "interval", 30, "08:00", NOW, last_run_at=future_last),
            future_last + 1800)

    def test_interval_past_last_run_falls_back_to_now(self):
        """last_run_at 早于 now：以 now 为基准，不追补历史周期。"""
        self.assertEqual(scheduler.compute_next_run(
            "interval", 30, "08:00", NOW, last_run_at=NOW - 3600),
            NOW + 1800)

    def test_interval_minimum_one_minute(self):
        self.assertEqual(scheduler.compute_next_run(
            "interval", 0, "08:00", NOW), NOW + 60)

    def test_daily_future_time_is_today(self):
        self.assertEqual(scheduler.compute_next_run(
            "daily", 60, "16:00", NOW), _local_ts(2026, 8, 21, 16, 0))

    def test_daily_past_time_rollsto_tomorrow(self):
        self.assertEqual(scheduler.compute_next_run(
            "daily", 60, "09:00", NOW), _local_ts(2026, 8, 22, 9, 0))

    def test_daily_exact_now_rolls_to_tomorrow(self):
        """target <= now 视为已过（整点相等不再执行今日）。"""
        self.assertEqual(scheduler.compute_next_run(
            "daily", 60, "15:00", NOW), _local_ts(2026, 8, 22, 15, 0))

    def test_daily_invalid_time_returns_none(self):
        for bad in ("25:00", "08:60", "8点", "", "0800"):
            self.assertIsNone(
                scheduler.compute_next_run("daily", 60, bad, NOW),
                msg=f"daily_time={bad!r} 应返回 None")

    def test_unknown_schedule_type_returns_none(self):
        self.assertIsNone(
            scheduler.compute_next_run("weekly", 30, "08:00", NOW))


# ---------------------------------------------------------------------------
# G5：tick 到期扫描 + running 在途去重（B7）
# ---------------------------------------------------------------------------

class TestTickDispatch(SchedulerCoreTest):

    def test_tick_dispatches_due_and_marks_success(self):
        """B1/B3：到期任务派发执行，成功后回写状态并推进 next_run_at。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        dispatched = self.sched.run_tick(now=NOW)
        self.assertEqual(dispatched, 1)
        self.mock_exec.assert_called_once()
        # B12 前提：report 以全量 dict 传入（PH-05 护栏可读 allow_write）
        _, kwargs = self.mock_exec.call_args
        self.assertIsInstance(kwargs["report"], dict)
        self.assertIn("allow_write", kwargs["report"])
        self.assertEqual(kwargs["report"]["id"], self.report_id)
        row = self._row(sid)
        self.assertEqual(row["last_status"], "success")
        self.assertEqual(row["fail_count"], 0)
        self.assertIsNone(row["last_error"])
        self.assertIsNotNone(row["last_run_at"])
        self.assertGreater(row["next_run_at"], NOW)

    def test_inflight_task_not_redispatched(self):
        """B7：在途任务第二次 tick 跳过，同一周期只提交一次。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.executor.mode = "pending"
        self.assertEqual(self.sched.run_tick(now=NOW), 1)
        # 任务仍在途（未消费）：行未回写、仍满足到期条件
        self.assertEqual(self.sched.run_tick(now=NOW), 0)
        self.assertEqual(len(self.executor.submitted), 1)
        # 消费在途任务后回写正常发生（submit 存的是 (fn, args, kwargs)）
        self.executor.mode = "sync"
        fn, fargs, fkwargs = self.executor.submitted.pop()
        fn(*fargs, **fkwargs)
        self.assertEqual(self._row(sid)["last_status"], "success")

    def test_tick_ignores_future_disabled_and_burned(self):
        self._add_schedule(next_run_at=NOW + 3600)                    # 未到期
        self._add_schedule(report_id=2, next_run_at=NOW - 60, enabled=0)
        self._add_schedule(report_id=3, next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute("UPDATE report_schedules SET fail_count=5 WHERE report_id=3")
        conn.commit()
        conn.close()
        # 补齐 report 2/3 行（外键无约束，但 _run_schedule 需要报表存在；
        # 本用例不应有任何派发，故仅需行满足过滤条件）
        self.assertEqual(self.sched.run_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# 执行结果回写与审计（B3/B4/B19 + B6 手动触发）
# ---------------------------------------------------------------------------

class TestRunScheduleOutcome(SchedulerCoreTest):

    def test_failure_records_summary_and_increments_counter(self):
        """B4：异常摘要截断 ≤500 字符入 last_error，fail_count 递增。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.mock_exec.side_effect = RuntimeError("x" * 800)
        self.sched.trigger_schedule(sid)
        row = self._row(sid)
        self.assertEqual(row["last_status"], "fail")
        self.assertEqual(row["fail_count"], 1)
        self.assertTrue(row["last_error"].startswith("RuntimeError"))
        self.assertEqual(len(row["last_error"]), 500)

    def test_success_audit_fields(self):
        """B19：自动执行审计 action=scheduled_run，type=scheduler，after_value 结构完整。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.sched.run_tick(now=NOW)
        records = self._audit_of("scheduled_run")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["user"], "system")
        self.assertEqual(rec["entity_type"], "schedule")
        self.assertEqual(rec["entity_id"], sid)
        self.assertEqual(rec["log_type"], "scheduler")
        after = rec["after_value"]
        self.assertEqual(after["trigger"], "scheduler")
        self.assertEqual(after["status"], "success")
        self.assertIn("duration_ms", after)
        self.assertIn("error", after)

    def test_manual_trigger_resets_fail_count(self):
        """B6：手动触发绕过熔断，成功后 fail_count 重置、审计记操作者。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute("UPDATE report_schedules SET fail_count=3 WHERE id=?", (sid,))
        conn.commit()
        conn.close()
        self.assertTrue(self.sched.trigger_schedule(sid, session_user="alice"))
        row = self._row(sid)
        self.assertEqual(row["fail_count"], 0)
        self.assertEqual(row["last_status"], "success")
        rec = self._audit_of("scheduled_run")[0]
        self.assertEqual(rec["user"], "alice")
        self.assertEqual(rec["after_value"]["trigger"], "manual")

    def test_manual_trigger_missing_schedule_returns_false(self):
        self.assertFalse(self.sched.trigger_schedule(9999))

    def test_scheduled_run_forces_cache_rebuild(self):
        """B24 回归（2026-08-21）：定时执行强制重建缓存（force_rebuild=True）。

        曾用 refresh=False 走普通读取路径——命中进程缓存/Redis 旧快照即
        短路，不执行 MySQL、不刷新 Redis 快照（用户现象：手动执行能建
        缓存，定时执行"执行成功"但缓存不更新）。保活 B14 同款先算后换。
        """
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.sched.run_tick(now=NOW)
        kwargs = self.mock_exec.call_args.kwargs
        self.assertTrue(kwargs["force_rebuild"])
        self.assertFalse(kwargs["refresh"])

    def test_manual_trigger_forces_cache_rebuild(self):
        """手动"立即执行"同样强制重建（用户主动点击=强制刷新语义）。"""
        sid = self._add_schedule(next_run_at=NOW + 3600)
        self.sched.trigger_schedule(sid)
        self.assertTrue(self.mock_exec.call_args.kwargs["force_rebuild"])

    def test_misfire_rerun_forces_cache_rebuild(self):
        """启动 misfire 补跑（B8/B10）同样强制重建。"""
        sid = self._add_schedule(next_run_at=NOW - 7200)
        self.sched.run_startup_scan(now=NOW)
        self.assertTrue(self.mock_exec.call_args.kwargs["force_rebuild"])

    def test_result_writeback_failure_does_not_raise(self):
        """结果回写异常只记日志，不影响工作线程（running 集合仍清理）。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        with patch("config_db.mark_schedule_result",
                   side_effect=sqlite3.OperationalError("locked")):
            self.sched.trigger_schedule(sid)
        self.assertNotIn(sid, self.sched._running)


# ---------------------------------------------------------------------------
# G6：启动 misfire 三分支（B8/B9/B10）
# ---------------------------------------------------------------------------

class TestStartupScanMisfire(SchedulerCoreTest):

    def test_interval_overdue_merges_into_single_rerun(self):
        """B8：interval 过期多个周期 → 合并补跑一次，next 推进一个周期。"""
        sid = self._add_schedule(next_run_at=NOW - 7200)  # 停机跨 4 个周期
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 1)
        self.assertEqual(self.mock_exec.call_count, 1)
        self.assertGreater(self._row(sid)["next_run_at"], NOW)

    def test_daily_skip_advances_and_audits(self):
        """B9：daily skip 当日已过 → 不补跑、next 推进明日、审计 scheduled_misfire。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="skip",
                                 next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 0)
        self.assertEqual(stats["skipped"], 1)
        self.mock_exec.assert_not_called()
        nxt = time.localtime(self._row(sid)["next_run_at"])
        self.assertEqual((nxt.tm_year, nxt.tm_mon, nxt.tm_mday,
                          nxt.tm_hour, nxt.tm_min), (2026, 8, 22, 9, 0))
        records = self._audit_of("scheduled_misfire")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["entity_id"], sid)
        self.assertEqual(records[0]["log_type"], "scheduler")
        self.assertEqual(records[0]["after_value"]["policy"], "skip")

    def test_daily_run_once_reruns_when_not_run_today(self):
        """B10：run_once 且今天未跑 → 补跑一次。"""
        self._add_schedule(schedule_type="daily", daily_time="09:00",
                           misfire_policy="run_once", last_run_at=None,
                           next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 1)
        self.mock_exec.assert_called_once()

    def test_daily_run_once_skips_if_already_ran_today(self):
        """B10 反例：当日已跑过 → 不补跑（防止重复执行）。"""
        self._add_schedule(schedule_type="daily", daily_time="09:00",
                           misfire_policy="run_once",
                           last_run_at=_local_ts(2026, 8, 21, 9, 0, 5),
                           next_run_at=_local_ts(2026, 8, 22, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 0)
        self.mock_exec.assert_not_called()

    def test_scan_ignores_disabled_and_future_tasks(self):
        """启动扫描同样受 enabled=1 与 fail_count<5、next_run_at<=now 约束。"""
        self._add_schedule(next_run_at=NOW + 3600)
        self._add_schedule(report_id=2, next_run_at=NOW - 60, enabled=0)
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats, {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# G7：连续失败熔断（B5）与手动恢复（B6）
# ---------------------------------------------------------------------------

class TestCircuitBreaker(SchedulerCoreTest):

    FAR_FUTURE = NOW + 30 * 86400

    def test_five_consecutive_failures_stop_auto_dispatch(self):
        """B5：连败 5 次（经手动触发累积）后 tick 不再自动派发。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.mock_exec.side_effect = RuntimeError("boom")
        for _ in range(5):
            self.sched.trigger_schedule(sid)   # 手动不受熔断限制
        self.assertEqual(self._row(sid)["fail_count"], 5)
        # 到期条件满足（next_run_at 已推进但仍早于 FAR_FUTURE 前 29 天处
        # 可能不满足——改用真实推进值验证：失败后 next=finished+interval，
        # 此处以远超它的 now 证明拦截来自熔断而非未到期）
        self.assertEqual(self.sched.run_tick(now=self.FAR_FUTURE), 0)
        self.assertEqual(self.mock_exec.call_count, 5)

    def test_manual_success_after_breaker_restores_dispatch(self):
        """人工确认恢复：手动成功 → fail_count=0 → 自动派发恢复。"""
        sid = self._add_schedule(next_run_at=NOW - 60)
        self.mock_exec.side_effect = RuntimeError("boom")
        for _ in range(5):
            self.sched.trigger_schedule(sid)
        self.mock_exec.side_effect = None
        self.assertTrue(self.sched.trigger_schedule(sid))
        self.assertEqual(self._row(sid)["fail_count"], 0)
        self.mock_exec.side_effect = RuntimeError("again")
        self.assertEqual(self.sched.run_tick(now=self.FAR_FUTURE), 1)


# ---------------------------------------------------------------------------
# G10：保活阈值边界（B13）与异常隔离（B16）
# ---------------------------------------------------------------------------

class TestKeepalive(SchedulerCoreTest):

    def _enable_keepalive(self, report_id=1, ahead=600, ttl_hours=6,
                          prefer_cache=1, with_schedule=True,
                          fail_count=0):
        conn = _get_conn()
        conn.execute(
            "UPDATE report_configs SET keepalive_enabled=1, "
            "keepalive_ahead_seconds=?, cache_ttl_hours=?, prefer_cache=? "
            "WHERE id=?", (ahead, ttl_hours, prefer_cache, report_id))
        if with_schedule:
            conn.execute(
                "INSERT INTO report_schedules (report_id, next_run_at, "
                "fail_count) VALUES (?,?,?)", (report_id, NOW, fail_count))
        conn.commit()
        conn.close()

    def _remaining_snapshot(self, remaining):
        self.mgr.get_snapshot.return_value = \
            self._snapshot_with_remaining(remaining)
        self.mgr.available = True

    def test_below_threshold_triggers_force_rebuild(self):
        """剩余 TTL 500s < ahead 600s → 先算后换重建（force_rebuild=True）。"""
        self._enable_keepalive()
        self._remaining_snapshot(500)
        avail = patch("scheduler.redis_cache.redis_available",
                      return_value=True)
        avail.start()
        self.addCleanup(avail.stop)
        rebuilt = self.sched.run_keepalive_tick(now=NOW)
        self.assertEqual(rebuilt, 1)
        self.mock_exec.assert_called_once()
        self.assertTrue(self.mock_exec.call_args.kwargs["force_rebuild"])

    def test_threshold_equality_skips(self):
        """剩余 TTL 恰等于 ahead → 仍未进入提前量窗口，跳过。"""
        self._enable_keepalive()
        self._remaining_snapshot(600)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_above_threshold_skips(self):
        self._enable_keepalive()
        self._remaining_snapshot(700)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_missing_snapshot_skips(self):
        """无快照：等请求自然重建，保活不抢跑。"""
        self._enable_keepalive()
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_zero_ahead_skips(self):
        """ahead_seconds=0：未配置提前量，永不触发。"""
        self._enable_keepalive(ahead=0)
        self._remaining_snapshot(100)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_redis_unavailable_skips_entire_scan(self):
        self._enable_keepalive()
        self._remaining_snapshot(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mgr.get_snapshot.assert_not_called()

    def test_join_requires_live_schedule_row(self):
        """JOIN report_schedules：无启用任务行 / 熔断中的报表不参与保活。"""
        self._enable_keepalive(with_schedule=False)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self._enable_keepalive(fail_count=5)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)

    def test_prefer_cache_off_skips(self):
        """prefer_cache=0 的报表不缓存快照，保活无意义 → 跳过。"""
        self._enable_keepalive(prefer_cache=0)
        self._remaining_snapshot(100)
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)

    def test_per_report_exception_does_not_break_loop(self):
        """B16：单个报表保活异常仅告警，其余报表继续处理。"""
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size,"
            "pool_id,prefer_cache,cache_ttl_hours,keepalive_enabled,"
            "keepalive_ahead_seconds) "
            "VALUES ('报表B','SELECT 2',20,1,1,6,1,300)")
        conn.commit()
        conn.close()
        self._enable_keepalive(report_id=1, ahead=600)
        self._enable_keepalive(report_id=2, ahead=300)
        self._remaining_snapshot(100)
        self.mock_exec.side_effect = [RuntimeError("池炸了"), None]
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            rebuilt = self.sched.run_keepalive_tick(now=NOW)
        self.assertEqual(rebuilt, 1)
        self.assertEqual(self.mock_exec.call_count, 2)


# ---------------------------------------------------------------------------
# B17：全局开关与模块级单例生命周期
# ---------------------------------------------------------------------------

class TestGlobalSwitch(unittest.TestCase):

    def tearDown(self):
        scheduler._scheduler = None

    def _with_cfg(self, enable):
        p = patch("app_config.get_config", return_value={
            "scheduler": {"enable": enable}})
        p.start()
        self.addCleanup(p.stop)

    def test_disabled_never_starts(self):
        self._with_cfg(False)
        with patch.object(scheduler, "ReportScheduler") as cls:
            self.assertIsNone(scheduler.start_scheduler_from_config())
        cls.assert_not_called()
        self.assertIsNone(scheduler._scheduler)

    def test_missing_config_section_defaults_to_disabled(self):
        """回归（2026-08-21）：app_config.json 缺 scheduler 节 → 默认停用。

        曾误写默认 True（违反 B17 规格），导致未配置开关的环境
        调度器静默启动。
        """
        p = patch("app_config.get_config", return_value={})
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual(scheduler.get_scheduler_config()["enable"], False)
        with patch.object(scheduler, "ReportScheduler") as cls:
            self.assertIsNone(scheduler.start_scheduler_from_config())
        cls.assert_not_called()

    def test_enabled_creates_and_starts_idempotent(self):
        self._with_cfg(True)
        with patch.object(scheduler.ReportScheduler, "start") as mock_start:
            first = scheduler.start_scheduler_from_config()
            self.assertIsNotNone(first)
            mock_start.assert_called_once()
            second = scheduler.start_scheduler_from_config()
            self.assertIs(first, second)          # 幂等：不重复建线程池
            mock_start.assert_called_once()

    def test_shutdown_clears_singleton(self):
        self._with_cfg(True)
        with patch.object(scheduler.ReportScheduler, "start"):
            scheduler.start_scheduler_from_config()
        instance = scheduler._scheduler
        with patch.object(instance, "shutdown") as mock_down:
            scheduler.shutdown_scheduler()
        mock_down.assert_called_once()
        self.assertIsNone(scheduler._scheduler)


if __name__ == "__main__":
    unittest.main()
