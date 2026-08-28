"""test_scheduler_extra.py — scheduler.py 未覆盖路径补充测试。

覆盖行号：
- 91: _eval_node 非 dict 节点
- 143, 150, 155, 159, 164: validate_exclusions / _validate_node 校验失败路径
- 176-178, 180-185: _validate_node date_range 解析失败、未知类型
- 282-288: start() 已启动线程直接返回
- 295: shutdown() thread.join
- 299-311: _tick_loop() 异常路径
- 374-375: _mark_skipped 审计写入失败
- 395-398: _execute_schedule 返回错误
- 452-453: _run_schedule 审计写入失败
- 468-469, 476-478, 482-485: _execute_schedule 报表不存在/连接池缺失/绑定禁用
- 619, 650: run_keepalive_tick 快照 None/ahead<=0 + 连接池不可用
- 677, 718: _rebuild_static_files 端点失败 + get_scheduler 返回 None
- 734: 文件末尾
"""

import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import config_db
import db
import redis_cache
import scheduler
from redis_cache import ReportSnapshot


# ---------------------------------------------------------------------------
# 临时库与环境隔离
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_extra_")
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
            name             TEXT    NOT NULL DEFAULT '',
            schedule_type    TEXT    NOT NULL DEFAULT 'interval',
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            daily_time       TEXT    NOT NULL DEFAULT '08:00',
            misfire_policy   TEXT    NOT NULL DEFAULT 'skip',
            enabled          INTEGER NOT NULL DEFAULT 1,
            exclusions       TEXT,
            audit_enabled    INTEGER NOT NULL DEFAULT 0,
            next_run_at      REAL,
            last_run_at      REAL,
            last_status      TEXT,
            last_error       TEXT,
            fail_count       INTEGER NOT NULL DEFAULT 0,
            last_duration_ms INTEGER,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS schedule_reports (
            schedule_id INTEGER NOT NULL,
            report_id   INTEGER NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            enabled     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (schedule_id, report_id)
        );
    """)
    conn.commit()
    conn.close()


_set_up_db()


def _local_ts(year, month, day, hour, minute, second=0):
    return time.mktime((year, month, day, hour, minute, second, 0, 0, -1))


NOW = _local_ts(2026, 8, 28, 15, 0, 0)


class _FakeExecutor:
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


class SchedulerExtraTest(unittest.TestCase):
    def setUp(self):
        cfg_patcher = patch("app_config.get_config", return_value=_test_config())
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)

        conn = _get_conn()
        for table in ("schedule_reports", "report_schedules", "api_endpoints",
                       "report_configs", "connection_pools"):
            conn.execute(f"DELETE FROM {table}")
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

        exec_patcher = patch("report.execute_report")
        self.mock_exec = exec_patcher.start()
        self.addCleanup(exec_patcher.stop)

        avail_patcher = patch("scheduler.redis_cache.redis_available", return_value=False)
        avail_patcher.start()
        self.addCleanup(avail_patcher.stop)
        self.mgr = MagicMock()
        self.mgr.key_prefix = "sr"
        self.mgr.get_snapshot.return_value = None
        mgr_patcher = patch("scheduler.redis_cache.get_redis_manager", return_value=self.mgr)
        mgr_patcher.start()
        self.addCleanup(mgr_patcher.stop)

        self.executor = _FakeExecutor()
        self.sched = scheduler.ReportScheduler(tick_seconds=30, workers=2)
        self.sched._executor = self.executor
        scheduler._scheduler = None
        self.addCleanup(setattr, scheduler, "_scheduler", None)

    def _add_schedule(self, report_ids=None, next_run_at=1000.0,
                      last_run_at=None, **kw):
        conn = _get_conn()
        try:
            args = dict(report_ids=[self.report_id] if report_ids is None
                        else report_ids,
                        schedule_type="interval", interval_minutes=30,
                        daily_time="08:00", misfire_policy="skip",
                        enabled=1, audit_enabled=1, next_run_at=next_run_at)
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


# ---------------------------------------------------------------------------
# 行 91: _eval_node 非 dict 节点
# ---------------------------------------------------------------------------

class TestEvalNodeNonDict(unittest.TestCase):

    def test_non_dict_returns_false(self):
        self.assertFalse(scheduler._eval_node("not a dict", datetime.now()))
        self.assertFalse(scheduler._eval_node(123, datetime.now()))
        self.assertFalse(scheduler._eval_node(None, datetime.now()))
        self.assertFalse(scheduler._eval_node([1, 2], datetime.now()))


# ---------------------------------------------------------------------------
# 行 143, 150, 155, 159, 164: validate_exclusions / _validate_node 校验失败
# ---------------------------------------------------------------------------

class TestValidateExclusionsErrors(unittest.TestCase):

    def test_json_string_parse_failure(self):
        ok, err = scheduler.validate_exclusions("{bad json")
        self.assertFalse(ok)
        self.assertIn("JSON 解析失败", err)

    def test_root_not_dict(self):
        ok, err = scheduler.validate_exclusions([1, 2, 3])
        self.assertFalse(ok)
        self.assertEqual(err, "排除规则根节点必须是对象")

    def test_and_children_not_list(self):
        ok, err = scheduler.validate_exclusions({"op": "AND", "children": "bad"})
        self.assertFalse(ok)
        self.assertIn("AND 节点必须包含非空 children 列表", err)

    def test_and_children_empty_list(self):
        ok, err = scheduler.validate_exclusions({"op": "AND", "children": []})
        self.assertFalse(ok)
        self.assertIn("非空 children 列表", err)

    def test_or_children_not_list(self):
        ok, err = scheduler.validate_exclusions({"op": "OR", "children": 123})
        self.assertFalse(ok)
        self.assertIn("OR 节点必须包含非空 children 列表", err)

    def test_nested_invalid_child_propagates(self):
        tree = {"op": "AND", "children": [
            {"type": "dow", "in": []}
        ]}
        ok, err = scheduler.validate_exclusions(tree)
        self.assertFalse(ok)
        self.assertIn("dow 节点需要非空 in 列表", err)

    def test_dow_missing_in(self):
        ok, err = scheduler.validate_exclusions({"type": "dow"})
        self.assertFalse(ok)
        self.assertEqual(err, "dow 节点需要非空 in 列表")

    def test_dow_in_not_list(self):
        ok, err = scheduler.validate_exclusions({"type": "dow", "in": "mon"})
        self.assertFalse(ok)
        self.assertEqual(err, "dow 节点需要非空 in 列表")

    def test_dow_bad_day_name(self):
        ok, err = scheduler.validate_exclusions({"type": "dow", "in": ["mon", "xyz"]})
        self.assertFalse(ok)
        self.assertIn("非法星期", err)

    def test_tod_invalid_format(self):
        ok, err = scheduler.validate_exclusions({"type": "tod", "from": "abc", "to": "12:00"})
        self.assertFalse(ok)
        self.assertEqual(err, "tod 节点 from/to 须为 HH:MM")


# ---------------------------------------------------------------------------
# 行 176-178, 180-185: _validate_node date_range / 未知类型
# ---------------------------------------------------------------------------

class TestValidateNodeTypeErrors(unittest.TestCase):

    def test_date_missing_on_list(self):
        ok, err = scheduler.validate_exclusions({"type": "date"})
        self.assertFalse(ok)
        self.assertEqual(err, "date 节点需要非空 on 列表")

    def test_date_on_not_list(self):
        ok, err = scheduler.validate_exclusions({"type": "date", "on": "2026-01-01"})
        self.assertFalse(ok)
        self.assertEqual(err, "date 节点需要非空 on 列表")

    def test_date_on_empty_list(self):
        ok, err = scheduler.validate_exclusions({"type": "date", "on": []})
        self.assertFalse(ok)
        self.assertEqual(err, "date 节点需要非空 on 列表")

    def test_date_range_invalid_from(self):
        ok, err = scheduler.validate_exclusions({
            "type": "date_range", "from": "bad-date", "to": "2026-12-31"
        })
        self.assertFalse(ok)
        self.assertEqual(err, "date_range 节点 from/to 须为 YYYY-MM-DD")

    def test_date_range_invalid_to(self):
        ok, err = scheduler.validate_exclusions({
            "type": "date_range", "from": "2026-01-01", "to": "not-a-date"
        })
        self.assertFalse(ok)
        self.assertEqual(err, "date_range 节点 from/to 须为 YYYY-MM-DD")

    def test_unknown_node_type(self):
        ok, err = scheduler.validate_exclusions({"type": "unknown_type"})
        self.assertFalse(ok)
        self.assertIn("未知节点类型", err)

    def test_node_not_dict(self):
        ok, err = scheduler._validate_node("not a dict")
        self.assertFalse(ok)
        self.assertEqual(err, "节点必须是对象")


# ---------------------------------------------------------------------------
# 行 282-288: start() 已启动线程直接返回
# ---------------------------------------------------------------------------

class TestStartAlreadyRunning(unittest.TestCase):

    def test_start_with_alive_thread_returns_early(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        sched._thread = mock_thread

        with patch("threading.Thread") as MockThread:
            sched.start()
            MockThread.assert_not_called()


# ---------------------------------------------------------------------------
# 行 295: shutdown() thread.join
# ---------------------------------------------------------------------------

class TestShutdownJoinsThread(unittest.TestCase):

    def test_shutdown_joins_thread(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        sched._thread = mock_thread

        sched.shutdown(timeout=10)
        mock_thread.join.assert_called_once_with(timeout=10)

    def test_shutdown_no_thread(self):
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._thread = None
        sched.shutdown(timeout=1)


# ---------------------------------------------------------------------------
# 行 299-311: _tick_loop() 异常路径
# ---------------------------------------------------------------------------

class TestTickLoopExceptions(unittest.TestCase):
    """覆盖 _tick_loop() 行 299-311。

    使用 tick_seconds=0.01 使 wait() 不阻塞，避免 30 秒超时。
    """

    def setUp(self):
        cfg_patcher = patch("app_config.get_config", return_value=_test_config())
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)
        audit_patcher = patch("audit_db.record_operation", return_value=True)
        audit_patcher.start()
        self.addCleanup(audit_patcher.stop)
        avail_patcher = patch("scheduler.redis_cache.redis_available", return_value=False)
        avail_patcher.start()
        self.addCleanup(avail_patcher.stop)
        mgr_patcher = patch("scheduler.redis_cache.get_redis_manager", return_value=MagicMock())
        mgr_patcher.start()
        self.addCleanup(mgr_patcher.stop)
        self.sched = scheduler.ReportScheduler(tick_seconds=0.01, workers=1)
        self.sched._executor = _FakeExecutor()
        scheduler._scheduler = None
        self.addCleanup(setattr, scheduler, "_scheduler", None)

    def test_startup_scan_exception_does_not_break_loop(self):
        """行 299-302: 启动扫描异常不阻断主循环。"""
        self.sched._stop_event.set()
        with patch.object(self.sched, "run_startup_scan", side_effect=RuntimeError("scan boom")):
            with patch.object(self.sched, "run_tick") as mock_tick:
                self.sched._tick_loop()
                mock_tick.assert_not_called()

    def test_tick_exception_does_not_break_loop(self):
        """行 304-307: tick 异常不阻断主循环。"""
        call_count = {"n": 0}
        def _tick_side_effect(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("tick boom")
            self.sched._stop_event.set()

        with patch.object(self.sched, "run_startup_scan"):
            with patch.object(self.sched, "run_tick", side_effect=_tick_side_effect):
                with patch.object(self.sched, "run_keepalive_tick"):
                    self.sched._tick_loop()

    def test_keepalive_exception_does_not_break_loop(self):
        """行 308-311: 保活 tick 异常不阻断主循环。"""
        call_count = {"n": 0}
        def _ka_side_effect(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("ka boom")
            self.sched._stop_event.set()

        with patch.object(self.sched, "run_startup_scan"):
            with patch.object(self.sched, "run_tick"):
                with patch.object(self.sched, "run_keepalive_tick", side_effect=_ka_side_effect):
                    self.sched._tick_loop()


# ---------------------------------------------------------------------------
# 行 374-375: _mark_skipped 审计写入失败
# ---------------------------------------------------------------------------

class TestMarkSkippedAuditFailure(SchedulerExtraTest):

    def test_mark_skipped_audit_write_failure_logs_warning(self):
        import json as _json
        from datetime import datetime as _dt
        sid = self._add_schedule(next_run_at=NOW - 60)
        # 计算当前星期几，写入 JSON 格式排除规则
        now_dt = _dt.fromtimestamp(NOW)
        _DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today_dow = _DOW_NAMES[now_dt.weekday()]
        conn = _get_conn()
        conn.execute(
            "UPDATE report_schedules SET exclusions=? WHERE id=?",
            (_json.dumps({"type": "dow", "in": [today_dow]}), sid))
        conn.commit()
        conn.close()
        with patch("config_db._write_audit_log", side_effect=RuntimeError("disk full")):
            with patch("logging.warning") as mock_warn:
                self.sched.run_tick(now=NOW)
                mock_warn.assert_any_call(
                    "定时任务 #%s 跳过审计写入失败", sid)


# ---------------------------------------------------------------------------
# 行 395-398: _run_schedule _execute_schedule 返回错误
# ---------------------------------------------------------------------------

class TestRunScheduleExecuteError(SchedulerExtraTest):

    def test_execute_schedule_returns_error_marks_fail(self):
        sid = self._add_schedule(next_run_at=NOW - 60)
        with patch.object(self.sched, "_execute_schedule", return_value="报表 #1: connection refused"):
            self.sched.trigger_schedule(sid)
        row = self._row(sid)
        self.assertEqual(row["last_status"], "fail")
        self.assertEqual(row["last_error"], "报表 #1: connection refused")
        self.assertEqual(row["fail_count"], 1)


# ---------------------------------------------------------------------------
# 行 452-453: _run_schedule 审计写入失败
# ---------------------------------------------------------------------------

class TestRunScheduleAuditFailure(SchedulerExtraTest):

    def test_audit_write_failure_logs_warning(self):
        sid = self._add_schedule(next_run_at=NOW - 60)
        with patch("config_db._write_audit_log", side_effect=RuntimeError("io error")):
            with patch("logging.warning") as mock_warn:
                self.sched.trigger_schedule(sid)
                mock_warn.assert_any_call(
                    "定时任务 #%s 审计写入失败", sid)


# ---------------------------------------------------------------------------
# 行 468-469, 476-478, 482-485: _execute_schedule 各种失败路径
# ---------------------------------------------------------------------------

class TestExecuteScheduleFailurePaths(SchedulerExtraTest):

    def test_no_bound_reports_returns_none(self):
        """_execute_schedule 在无绑定报表时返回 None（不报错）。"""
        # 先创建一个有绑定的 schedule，再手动删除绑定
        sid = self._add_schedule(next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute("DELETE FROM schedule_reports WHERE schedule_id=?", (sid,))
        conn.commit()
        sched = dict(conn.execute(
            "SELECT * FROM report_schedules WHERE id=?", (sid,)).fetchone())
        conn.close()
        with patch("logging.warning"):
            err = self.sched._execute_schedule(sched)
        self.assertIsNone(err)

    def test_report_not_exists_skips(self):
        sid = self._add_schedule(next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute(
            "INSERT INTO schedule_reports (schedule_id, report_id, order_index, enabled) "
            "VALUES (?, 9999, 0, 1)", (sid,))
        conn.commit()
        conn.close()
        with patch("logging.warning") as mock_warn:
            err = self.sched._execute_schedule(self._row(sid))
            self.assertIsNone(err)
            mock_warn.assert_any_call(
                "定时任务 #%s 报表 #%s 不存在，跳过", sid, 9999)

    def test_pool_missing_marks_error(self):
        sid = self._add_schedule(next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute("UPDATE report_configs SET pool_id=NULL WHERE id=1")
        conn.commit()
        conn.close()
        with patch("logging.warning"):
            err = self.sched._execute_schedule(self._row(sid))
            self.assertIn("未绑定有效连接池", err)

    def test_binding_disabled_skips(self):
        sid = self._add_schedule(next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute(
            "UPDATE schedule_reports SET enabled=0 WHERE schedule_id=? AND report_id=?",
            (sid, self.report_id))
        conn.commit()
        conn.close()
        err = self.sched._execute_schedule(self._row(sid))
        self.assertIsNone(err)
        self.mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# 行 619, 650: run_keepalive_tick 快照 None/ahead<=0 + 连接池不可用
# ---------------------------------------------------------------------------

class TestKeepaliveEdgeCases(SchedulerExtraTest):

    def _enable_keepalive(self, report_id=1, ahead=600, ttl_hours=6,
                          prefer_cache=1, with_schedule=True, fail_count=0):
        conn = _get_conn()
        conn.execute(
            "UPDATE report_configs SET keepalive_enabled=1, "
            "keepalive_ahead_seconds=?, cache_ttl_hours=?, prefer_cache=? "
            "WHERE id=?", (ahead, ttl_hours, prefer_cache, report_id))
        if with_schedule:
            cur = conn.execute(
                "INSERT INTO report_schedules (name, enabled, fail_count, "
                "next_run_at) VALUES ('', 1, ?, ?)", (fail_count, NOW))
            sid = cur.lastrowid
            conn.execute(
                "INSERT INTO schedule_reports (schedule_id, report_id, "
                "order_index, enabled) VALUES (?,?,0,1)", (sid, report_id))
        conn.commit()
        conn.close()

    def test_redis_manager_none_returns_zero(self):
        self._enable_keepalive()
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            with patch("scheduler.redis_cache.get_redis_manager", return_value=None):
                result = self.sched.run_keepalive_tick(now=NOW)
                self.assertEqual(result, 0)

    def test_snapshot_none_skips(self):
        self._enable_keepalive()
        self.mgr.get_snapshot.return_value = None
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            result = self.sched.run_keepalive_tick(now=NOW)
            self.assertEqual(result, 0)

    def test_ahead_zero_skips(self):
        self._enable_keepalive(ahead=0)
        snap = ReportSnapshot(
            results=[{"columns": ["id"], "rows": [[1]], "total": 1}],
            sql_query="SELECT 1",
            updated_at=NOW - 3600,
            config_version="v-test")
        self.mgr.get_snapshot.return_value = snap
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            result = self.sched.run_keepalive_tick(now=NOW)
            self.assertEqual(result, 0)

    def test_pool_none_raises_and_logs(self):
        self._enable_keepalive(ahead=3600, ttl_hours=1)
        snap = ReportSnapshot(
            results=[{"columns": ["id"], "rows": [[1]], "total": 1}],
            sql_query="SELECT 1",
            updated_at=NOW - 7200,
            config_version="v-test")
        self.mgr.get_snapshot.return_value = snap
        conn = _get_conn()
        conn.execute("UPDATE report_configs SET pool_id=NULL WHERE id=1")
        conn.commit()
        conn.close()
        with patch("scheduler.redis_cache.redis_available", return_value=True):
            with patch("logging.warning") as mock_warn:
                result = self.sched.run_keepalive_tick(now=NOW)
                self.assertEqual(result, 0)
                mock_warn.assert_any_call(
                    "保活重建失败 report=%s: %s", 1,
                    unittest.mock.ANY)


# ---------------------------------------------------------------------------
# 行 677, 718: _rebuild_static_files 端点失败 + get_scheduler 返回 None
# ---------------------------------------------------------------------------

class TestRebuildStaticFilesFailure(unittest.TestCase):

    def test_endpoint_not_written_logs_warning(self):
        conn = MagicMock()
        ep = {"id": 1, "url_path": "/api/test", "static_cache": 1}
        with patch("config_db.get_api_endpoints_by_report", return_value=[ep]):
            with patch("api_handler.rebuild_static_endpoint_file",
                       return_value=(False, 500, None, None)):
                with patch("logging.warning") as mock_warn:
                    scheduler.ReportScheduler._rebuild_static_files(conn, {"id": 1})
                    mock_warn.assert_any_call(
                        "保活静态联动未落盘 endpoint=%s status=%s",
                        "/api/test", 500)

    def test_endpoint_exception_logs_warning(self):
        conn = MagicMock()
        ep = {"id": 1, "url_path": "/api/test", "static_cache": 1}
        with patch("config_db.get_api_endpoints_by_report", return_value=[ep]):
            with patch("api_handler.rebuild_static_endpoint_file",
                       side_effect=RuntimeError("write error")):
                with patch("logging.warning") as mock_warn:
                    scheduler.ReportScheduler._rebuild_static_files(conn, {"id": 1})
                    mock_warn.assert_any_call(
                        "保活静态联动失败 endpoint=%s: %s",
                        "/api/test", unittest.mock.ANY)


class TestGetSchedulerReturnsNone(unittest.TestCase):

    def test_get_scheduler_returns_none_when_not_started(self):
        scheduler._scheduler = None
        self.assertIsNone(scheduler.get_scheduler())


# ---------------------------------------------------------------------------
# 行 734: trigger_manual 临时实例路径
# ---------------------------------------------------------------------------

class TestTriggerManualFallback(unittest.TestCase):

    def test_trigger_manual_no_singleton_uses_temp_instance(self):
        scheduler._scheduler = None
        sid = 9999
        with patch("app_config.get_config", return_value=_test_config()):
            with patch("config_db.get_schedule", return_value=None):
                result = scheduler.trigger_manual(sid)
                self.assertFalse(result)

    def test_trigger_manual_no_singleton_with_valid_schedule(self):
        scheduler._scheduler = None
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs (id,name,sql_query,default_page_size,"
            "pool_id,prefer_cache) VALUES (10,'报表X','SELECT 1',20,1,1)")
        conn.commit()
        cur = conn.execute(
            "INSERT INTO report_schedules (name, schedule_type, interval_minutes, "
            "daily_time, misfire_policy, enabled, next_run_at) "
            "VALUES ('test','interval',30,'08:00','skip',1,?)", (NOW - 60,))
        sid = cur.lastrowid
        conn.execute(
            "INSERT INTO schedule_reports (schedule_id, report_id, order_index, enabled) "
            "VALUES (?,?,0,1)", (sid, 10))
        conn.commit()
        conn.close()
        with patch("app_config.get_config", return_value=_test_config()):
            with patch("report.execute_report"):
                result = scheduler.trigger_manual(sid)
                self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()