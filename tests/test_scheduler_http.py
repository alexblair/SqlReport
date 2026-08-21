"""test_scheduler_http.py — 定时任务 HTTP/UI 集成测试（T4）。

覆盖规格 .scratch/report-scheduler/spec.md 缺口（覆盖矩阵登记）：
- G8  报表编辑页渲染「定时执行」「缓存保活」折叠区（编辑态任务行回显，
       未配置报表用默认值）
- G9  报表保存链路：调度字段落 report_schedules（参数变更重算 next_run_at，
       参数未变保持原值）；保活字段落 report_configs；新建带调度字段同时建
       任务；复制不继承任务（防双跑）
- G11 报表管理列表徽标 ⏰/♻（仅启用任务出 ⏰）；管理页 /config/scheduler
       列表列 + 全局停用横幅（B17 页面可看不可自动跑）
- B21 手动触发端点（全局停用/未启动降级为一次性实例同步执行）、启停端点
       （重新启用且 next 过期 → 重算未来）、删除端点与审计
- 审计动作：create_schedule / toggle_schedule / delete_schedule /
  scheduled_run(trigger=manual, user=操作者)

测试策略：与 test_scheduler_core 相同的环境隔离（patch app_config.get_config
→ 临时文件库），HTTP 层直接调用 config.handle_request（不起真服务器，
模式同 test_config）。注意：
- 报表管理列表页由 server._handle_config_reports 直连 render_reports_page，
  不经过 handle_request——徽标用例直调渲染函数；
- 种子行显式固定 id=1（临时库跨方法持久，AUTOINCREMENT 会递增，写死 id
  保证引用恒有效）；
- 内联 DDL 需覆盖 handle_request 渲染链路触及的全部表（categories/users/
  api_endpoints/api_keys），新增列时同步本文件与 test_base。
"""

import os
import sqlite3
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

import config
import config_db
import db
import scheduler


_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_http_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")


def _test_config(scheduler_enable: bool) -> dict:
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "log": {"enable": False, "path": "/dev/null"},
        "scheduler": {"enable": scheduler_enable},
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
        CREATE TABLE IF NOT EXISTS report_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            parent_id INTEGER, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
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
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id INTEGER NOT NULL,
            name TEXT NOT NULL, api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, category_id INTEGER,
            memo TEXT, result_names TEXT DEFAULT '',
            prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1,
            max_rows INTEGER NOT NULL DEFAULT 100000,
            keepalive_enabled INTEGER NOT NULL DEFAULT 0,
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
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


class SchedulerHttpTest(unittest.TestCase):
    """T4 集成公共环境：临时库 + 种子数据 + 审计/执行 mock。"""

    def setUp(self):
        self.scheduler_enabled = True
        cfg_patcher = patch(
            "app_config.get_config",
            side_effect=lambda: _test_config(self.scheduler_enabled))
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)

        conn = _get_conn()
        for table in ("report_schedules", "report_configs", "connection_pools"):
            conn.execute(f"DELETE FROM {table}")
        # 种子行显式固定 id=1（跨测试方法持久库的 AUTOINCREMENT 防漂移）
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

        self.audit_calls = []

        def _record(session_user, action, entity_type, **kw):
            self.audit_calls.append(dict(
                user=session_user, action=action, entity_type=entity_type,
                entity_id=kw.get("entity_id"),
                after_value=kw.get("after_value")))
            return True

        audit_patcher = patch("audit_db.record_operation", side_effect=_record)
        audit_patcher.start()
        self.addCleanup(audit_patcher.stop)

        exec_patcher = patch("report.execute_report")
        self.mock_exec = exec_patcher.start()
        self.addCleanup(exec_patcher.stop)

        # 调度器单例复位（B17 全局状态不跨用例泄漏）
        scheduler._scheduler = None
        self.addCleanup(setattr, scheduler, "_scheduler", None)

    # -- 公共辅助 ----------------------------------------------------------

    def _conn(self):
        return _get_conn()

    def _get(self, path, query=""):
        code, body, headers = config.handle_request(
            self._conn(), "GET", path, query)
        return code, body, headers

    def _post(self, path, fields: dict):
        body = urllib.parse.urlencode(fields)
        code, result, headers = config.handle_request(
            self._conn(), "POST", path, "", form_body=body,
            session_user="admin")
        return code, result, headers

    def _add_schedule_row(self, report_id=1, last_run_at=None, **overrides):
        args = dict(report_id=report_id, schedule_type="interval",
                    interval_minutes=30, daily_time="08:00",
                    misfire_policy="skip", enabled=1,
                    next_run_at=time.time() - 60)
        args.update(overrides)
        conn = _get_conn()
        try:
            sid = config_db.upsert_schedule(conn, session_user=None, **args)
            if last_run_at is not None:
                conn.execute(
                    "UPDATE report_schedules SET last_run_at=? WHERE id=?",
                    (last_run_at, sid))
                conn.commit()
            return sid
        finally:
            conn.close()

    def _sched_row(self, report_id=1):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_schedules WHERE report_id=?",
                (report_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _report_row(self, report_id=1):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_configs WHERE id=?",
                (report_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _audit_of(self, action):
        return [a for a in self.audit_calls if a["action"] == action]

    def _base_form(self, **extra):
        """报表表单基础字段（含全部护栏/缓存字段 + 新增 T4 字段）。"""
        base = dict(name="报表A", sql_query="SELECT 1", default_page_size="20",
                    pool_id="1", category_id="", memo="", result_names="",
                    prefer_cache="1", cache_ttl_hours="2",
                    allow_write="0", allow_all_output="0", max_rows="100000",
                    keepalive_enabled="0", keepalive_ahead_seconds="600",
                    schedule_enabled="0", schedule_type="interval",
                    interval_minutes="30", daily_time="08:00",
                    misfire_policy="skip", action="save_close")
        base.update(extra)
        return base


# ---------------------------------------------------------------------------
# G8/G9：报表编辑页折叠区渲染与保存链路
# ---------------------------------------------------------------------------

class TestReportFormSchedule(SchedulerHttpTest):

    def test_edit_page_renders_schedule_and_keepalive_sections(self):
        """G8：编辑页含定时/保活折叠区，任务行字段回显到表单默认值。"""
        self._add_schedule_row(schedule_type="daily", daily_time="09:30",
                               misfire_policy="run_once", interval_minutes=99)
        _, body, _ = self._get("/config/reports/1/edit")
        self.assertIn("定时执行", body)
        self.assertIn("缓存保活", body)
        self.assertIn('value="09:30"', body)              # daily 回显
        self.assertIn('value="run_once"', body)           # 补偿策略回显
        # 未配任务的报表也正常渲染折叠区（默认值）
        self._add_schedule_row()                          # 先确保存在再删除场景
        conn = _get_conn()
        conn.execute("DELETE FROM report_schedules WHERE report_id=1")
        conn.commit()
        conn.close()
        _, body, _ = self._get("/config/reports/1/edit")
        self.assertIn('name="schedule_type"', body)
        self.assertIn('value="08:00"', body)              # 默认时刻

    def test_save_persists_schedule_and_keepalive(self):
        """G9：保存带调度+保活字段 → 任务行/报表行落库，next_run_at 未来。"""
        before = time.time()
        code, result, headers = self._post("/config/reports/1/edit",
                                           self._base_form(
                                               schedule_enabled="1",
                                               schedule_type="daily",
                                               daily_time="16:30",
                                               misfire_policy="run_once",
                                               keepalive_enabled="1",
                                               keepalive_ahead_seconds="900"))
        self.assertEqual(code, 302)
        sched = self._sched_row()
        self.assertIsNotNone(sched)
        self.assertEqual(sched["schedule_type"], "daily")
        self.assertEqual(sched["daily_time"], "16:30")
        self.assertEqual(sched["misfire_policy"], "run_once")
        self.assertEqual(sched["enabled"], 1)
        self.assertGreater(sched["next_run_at"], before)
        nxt = time.localtime(sched["next_run_at"])
        self.assertEqual((nxt.tm_hour, nxt.tm_min), (16, 30))
        report = self._report_row()
        self.assertEqual(report["keepalive_enabled"], 1)
        self.assertEqual(report["keepalive_ahead_seconds"], 900)
        self.assertEqual(len(self._audit_of("create_schedule")), 1)

    def test_save_disabled_clears_schedule(self):
        """未勾选启用 → upsert enabled=0（保留配置但不再派发）。"""
        self._add_schedule_row()
        self._post("/config/reports/1/edit", self._base_form())
        self.assertEqual(self._sched_row()["enabled"], 0)

    def test_save_unchanged_params_keeps_next_run_at(self):
        """G9：调度参数完全未变 → next_run_at 保持原值（不扰动节拍）。"""
        fixed_next = time.time() + 3600
        self._add_schedule_row(interval_minutes=30, next_run_at=fixed_next)
        self._post("/config/reports/1/edit",
                   self._base_form(schedule_enabled="1"))
        self.assertAlmostEqual(self._sched_row()["next_run_at"],
                               fixed_next, delta=1)

    def test_report_add_creates_schedule(self):
        """新建报表带调度字段 → 报表与任务同时创建。"""
        form = self._base_form(name="新报表", schedule_enabled="1",
                               schedule_type="interval",
                               interval_minutes="45")
        code, result, _ = self._post("/config/reports/add", form)
        self.assertEqual(code, 302)
        conn = _get_conn()
        new_id = conn.execute(
            "SELECT id FROM report_configs WHERE name='新报表'").fetchone()[0]
        conn.close()
        sched = self._sched_row(new_id)
        self.assertIsNotNone(sched)
        self.assertEqual(sched["interval_minutes"], 45)
        self.assertGreater(sched["next_run_at"], time.time())

    def test_report_copy_does_not_inherit_schedule(self):
        """复制报表不继承定时任务（避免新旧双跑）。"""
        self._add_schedule_row()
        code, result, _ = self._post("/config/reports/1/copy",
                                     self._base_form(name="副本A"))
        self.assertEqual(code, 302)
        conn = _get_conn()
        copy_id = conn.execute(
            "SELECT id FROM report_configs WHERE name='副本A'").fetchone()[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM report_schedules WHERE report_id=?",
            (copy_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# G11：管理页 /config/scheduler 与列表徽标
# ---------------------------------------------------------------------------

class TestSchedulerPage(SchedulerHttpTest):

    def test_page_lists_tasks_with_columns(self):
        self._add_schedule_row()
        code, body, _ = self._get("/config/scheduler")
        self.assertEqual(code, 200)
        for fragment in ("报表A", "下次执行", "上次执行", "上次结果",
                         "失败计数", "立即执行", "每 30 分钟"):
            self.assertIn(fragment, body)

    def test_page_shows_last_run_time(self):
        """上次执行列：last_run_at 格式化为本地时间。"""
        at = time.time() - 120
        self._add_schedule_row(last_run_at=at)
        _, body, _ = self._get("/config/scheduler")
        expect = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(at))
        self.assertIn(expect, body)

    def test_page_shows_recent_events(self):
        """最近执行记录区块：scheduled_run 成功/失败与 scheduled_misfire 渲染。"""
        import json as _json
        now = time.time()
        events = [
            {"id": 3, "action": "scheduled_misfire", "entity_type": "schedule",
             "entity_id": 1, "timestamp": now - 60,
             "after_value": _json.dumps({"policy": "skip"})},
            {"id": 2, "action": "scheduled_run", "entity_type": "schedule",
             "entity_id": 1, "timestamp": now - 3600,
             "after_value": _json.dumps({"trigger": "manual",
                                         "status": "fail", "error": "池炸了",
                                         "duration_ms": 88})},
            {"id": 1, "action": "scheduled_run", "entity_type": "schedule",
             "entity_id": 1, "timestamp": now - 7200,
             "after_value": _json.dumps({"trigger": "scheduler",
                                         "status": "success",
                                         "duration_ms": 42})},
        ]
        with patch("audit_db.get_recent_schedule_events",
                   return_value=events):
            _, body, _ = self._get("/config/scheduler")
        self.assertIn("最近执行记录", body)
        self.assertIn("✅ 成功", body)
        self.assertIn("❌ 失败", body)
        self.assertIn("88ms", body)
        self.assertIn("手动", body)                       # trigger=manual
        self.assertIn("跳过（推进到下次计划）", body)       # misfire skip
        self.assertIn("来自审计日志", body)

    def test_page_empty_events_block(self):
        """无执行记录时区块仍渲染（空状态占位）。"""
        with patch("audit_db.get_recent_schedule_events", return_value=[]):
            _, body, _ = self._get("/config/scheduler")
        self.assertIn("最近执行记录", body)
        self.assertIn("暂无执行记录", body)

    def test_page_shows_banner_when_globally_disabled(self):
        """B17：全局停用 → 横幅提示，页面仍可查看。"""
        self.scheduler_enabled = False
        self._add_schedule_row()
        code, body, _ = self._get("/config/scheduler")
        self.assertEqual(code, 200)
        self.assertIn("全局已停用", body)
        self.assertIn("报表A", body)

    def test_reports_list_badges(self):
        """列表徽标：⏰=已配启用任务，♻=已开保活。

        断言用 title 属性精确定位（页面「定时执行」折叠区标题本身
        含 ⏰ 字样，裸字符断言会误报）。
        """
        badge_sched = '<span title="已配置定时执行">⏰</span>'
        conn = _get_conn()
        conn.execute("UPDATE report_configs SET keepalive_enabled=1,"
                     "keepalive_ahead_seconds=600 WHERE id=1")
        conn.commit()
        conn.close()
        self._add_schedule_row(enabled=1)
        # 报表管理列表页由 server._handle_config_reports 直连
        # render_reports_page（不经过 handle_request），此处直调同款入口
        conn = _get_conn()
        try:
            _, body, _ = self._get("/config")
            body = config.render_reports_page(conn)
            self.assertIn(badge_sched, body)
            self.assertIn("♻", body)
            # 停用任务不出 ⏰ 徽标
            conn.execute(
                "UPDATE report_schedules SET enabled=0 WHERE report_id=1")
            conn.commit()
            body = config.render_reports_page(conn)
            self.assertNotIn(badge_sched, body)
            self.assertIn("♻", body)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# B21：手动触发 / 启停 / 删除端点
# ---------------------------------------------------------------------------

class TestSchedulerEndpoints(SchedulerHttpTest):

    def test_manual_run_executes_and_audits(self):
        sid = self._add_schedule_row(next_run_at=time.time() + 3600)
        code, result, _ = self._post(f"/config/scheduler/run/{sid}", {})
        self.assertEqual(code, 302)
        self.assertIn("/config/scheduler", result)
        self.mock_exec.assert_called_once()               # 未启动仍可触发（B21 降级）
        rec = self._audit_of("scheduled_run")[0]
        self.assertEqual(rec["user"], "admin")
        self.assertEqual(rec["after_value"]["trigger"], "manual")

    def test_manual_run_missing_task_redirects_error(self):
        code, result, _ = self._post("/config/scheduler/run/9999", {})
        self.assertEqual(code, 302)
        self.assertIn("flash=", result)

    def test_toggle_disable_then_enable_recomputes_stale_next(self):
        """启停循环：停用 → enabled=0；启用且 next 已过期 → 重算未来。"""
        sid = self._add_schedule_row(next_run_at=time.time() - 7200)
        self._post(f"/config/scheduler/toggle/{sid}", {})
        self.assertEqual(self._sched_row()["enabled"] if self._sched_row() else None,
                         0)
        stale_next = self._sched_row()["next_run_at"]
        self._post(f"/config/scheduler/toggle/{sid}", {})
        row = self._sched_row()
        self.assertEqual(row["enabled"], 1)
        self.assertGreater(row["next_run_at"], time.time())
        self.assertNotAlmostEqual(row["next_run_at"], stale_next, delta=1)
        self.assertTrue(any(a["action"] == "toggle_schedule"
                            for a in self.audit_calls))

    def test_delete_removes_row_and_audits(self):
        sid = self._add_schedule_row()
        code, result, _ = self._post(f"/config/scheduler/delete/{sid}", {})
        self.assertEqual(code, 302)
        self.assertIsNone(self._sched_row())
        rec = self._audit_of("delete_schedule")[0]
        self.assertEqual(rec["entity_id"], sid)


# ---------------------------------------------------------------------------
# T5：server.py 生命周期接线（启动钩子 + Ctrl+C 关闭链路）
# ---------------------------------------------------------------------------

class TestServerLifecycle(unittest.TestCase):
    """server.main() 的调度器接线为进程级行为，无法在线程内安全复跑 main；
    采用源码级断言钉住接线点（项目既有手法，同 test_filter_help /
    test_server 的源码读取用例），开关语义与关闭清理由 TestGlobalSwitch
    （tests/test_scheduler_core.py）行为级覆盖。
    """

    def test_main_wires_start_and_shutdown(self):
        import pathlib
        src = pathlib.Path("/opdev/SqlReport/server.py").read_text(
            encoding="utf-8")
        # HTTP 服务就绪后才启动调度器；失败只告警不阻断 Web 服务
        self.assertIn("scheduler.start_scheduler_from_config()", src)
        self.assertIn("报表调度器启动失败", src)
        # Ctrl+C 链路先停调度器（等待在途任务收尾）再关 socket
        self.assertIn("scheduler.shutdown_scheduler()", src)
        self.assertLess(src.index("scheduler.start_scheduler_from_config()"),
                        src.index("scheduler.shutdown_scheduler()"))

    def test_module_import_no_side_effects(self):
        """import server 不应创建调度器实例（仅 main() 内启动）。"""
        import importlib
        import sys
        mod = importlib.import_module("server")
        self.assertIsNone(scheduler._scheduler)
        self.assertTrue(hasattr(mod, "scheduler"))


if __name__ == "__main__":
    unittest.main()
