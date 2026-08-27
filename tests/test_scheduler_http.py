"""test_scheduler_http.py — 定时任务 HTTP/UI 集成测试（T4）。

覆盖规格 .scratch/scheduler-composition-exclusion/spec.md 缺口（覆盖矩阵登记）：
- G8  报表编辑页「定时执行」折叠区已退役（任务统一在 /config/scheduler 管理，
       spec §7.3）；「缓存保活」折叠区保留并回显
- G9  报表保存只落保活字段；即使请求携带旧 schedule 字段也不创建任务行
       （折叠区退役后该路径彻底关闭）；复制报表不继承任务（防双跑）
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
            updated_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
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
        for table in ("report_schedules", "schedule_reports", "report_configs",
                      "connection_pools"):
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
        args = dict(report_ids=[report_id], schedule_type="interval",
                    interval_minutes=30, daily_time="08:00",
                    misfire_policy="skip", enabled=1, audit_enabled=1,
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
                "SELECT s.* FROM report_schedules s "
                "JOIN schedule_reports sr ON sr.schedule_id=s.id "
                "WHERE sr.report_id=? LIMIT 1", (report_id,)).fetchone()
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

    def test_edit_page_renders_keepalive_but_no_schedule_foldout(self):
        """G8：报表编辑页含「缓存保活」折叠区；「定时执行」折叠区已退役
        （任务统一在 /config/scheduler 管理，spec §7.3）。"""
        self._add_schedule_row(schedule_type="daily", daily_time="09:30",
                               misfire_policy="run_once", interval_minutes=99)
        _, body, _ = self._get("/config/reports/1/edit")
        self.assertIn("缓存保活", body)
        self.assertNotIn("⏰ 定时执行", body)            # 折叠区退役
        self.assertNotIn('name="schedule_type"', body)
        self.assertNotIn('name="schedule_enabled"', body)
        self.assertNotIn('name="interval_minutes"', body)
        self.assertNotIn('name="daily_time"', body)
        self.assertNotIn('name="misfire_policy"', body)

    def test_save_persists_keepalive_but_no_schedule_task(self):
        """G9：保存报表只落保活字段；即使请求携带旧 schedule 字段也不创建
        任务行（折叠区退役后该路径彻底关闭）。"""
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
        self.assertIsNone(sched)                        # 不再自动建任务
        row = self._report_row()
        self.assertEqual(row["keepalive_enabled"], 1)
        self.assertEqual(row["keepalive_ahead_seconds"], 900)

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
            "SELECT COUNT(*) FROM schedule_reports WHERE report_id=?",
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
                                         "duration_ms": 42,
                                         "report_total": 3,
                                         "report_executed": 2,
                                         "report_names": ["报表A", "报表C"]})},
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
        # T3：记录表 6 列，含「任务」「报表」列头
        self.assertIn(">任务</th>", body)
        self.assertIn(">报表</th>", body)
        # T3：任务列链接回编辑页
        self.assertIn('href="/config/scheduler?edit=1"', body)
        # T3：报表列展示「报表：…（n/m）」
        self.assertIn("报表：", body)

    def test_page_empty_events_block_all_audit_off(self):
        """无执行记录 + 所有任务未开审计 → 显示审计关闭提示（T4 空态）。"""
        self._add_schedule_row(audit_enabled=0)
        with patch("audit_db.get_recent_schedule_events", return_value=[]):
            _, body, _ = self._get("/config/scheduler")
        self.assertIn("最近执行记录", body)
        self.assertIn("暂无执行记录", body)
        self.assertIn("所有任务均未开启", body)

    def test_page_empty_events_block_some_audit_on(self):
        """无执行记录 + 有任务开启审计 → 仅通用占位，不含审计关闭提示（T4）。"""
        self._add_schedule_row(audit_enabled=1)
        with patch("audit_db.get_recent_schedule_events", return_value=[]):
            _, body, _ = self._get("/config/scheduler")
        self.assertIn("最近执行记录", body)
        self.assertIn("暂无执行记录", body)
        self.assertNotIn("所有任务均未开启", body)

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
                "UPDATE report_schedules SET enabled=0 WHERE id=?",
                (self._sched_row(1)["id"],))
            conn.commit()
            body = config.render_reports_page(conn)
            self.assertNotIn(badge_sched, body)
            self.assertIn("♻", body)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 定时任务 UX 优化（scheduler-ux-optimization）：T1 表单 config-form 化、
# T2 报表三列参与执行、T3 记录增强（测试在 test_scheduler_core）、T4 列表合并
# ---------------------------------------------------------------------------

class TestSchedulerUXForm(SchedulerHttpTest):
    """T1/T2：新增表单（无预填，默认 interval）。

    表单始终渲染在 /config/scheduler 页面底部（build_scheduler_task_form_html
    无 prefill）。所有报表初始未绑定 → 不渲染 bind_enabled 输入（T2 根因修复）。
    """

    def _form_body(self, query=""):
        _, body, _ = self._get("/config/scheduler", query)
        return body

    def test_form_uses_config_form_class_no_inline_maxwidth(self):
        """T1：表单改用 config-form sched-form，不再硬编码 max-width:640px。"""
        body = self._form_body()
        self.assertIn('class="config-form sched-form"', body)
        self.assertNotIn("max-width:640px", body)

    def test_form_new_defaults_interval_shows_only_interval_row(self):
        """T1/A1：新建默认 interval → row-interval 可见、row-daily 隐藏。"""
        body = self._form_body()
        self.assertIn('<div class="schedule-row span-full" id="row-interval">',
                      body)
        self.assertIn('<div class="schedule-row span-full" id="row-daily" '
                      'style="display:none">', body)

    def test_form_edit_daily_shows_only_daily_row(self):
        """T1/A2：编辑预填 daily → row-daily 可见、row-interval 隐藏。"""
        self._add_schedule_row(schedule_type="daily", daily_time="09:30")
        sid = self._sched_row()["id"]
        body = self._form_body(f"edit={sid}")
        self.assertIn('<div class="schedule-row span-full" id="row-daily"',
                      body)
        self.assertIn('<div class="schedule-row span-full" id="row-interval" '
                      'style="display:none">', body)

    def test_form_three_column_report_table(self):
        """T2：关联报表为「绑定|报表|参与执行」三列表头。"""
        body = self._form_body()
        self.assertIn("绑定</th><th>报表</th><th>参与执行", body)

    def test_form_unbound_report_has_no_bind_enabled_input(self):
        """T2/B3 根因：未绑定报表行不渲染 bind_enabled 输入，参与执行列显示「—」。"""
        # 新表单下报表A(id=1)未绑定
        body = self._form_body()
        self.assertIn('name="report_ids" value="1"', body)
        self.assertNotIn("bind_enabled_1", body)
        self.assertIn('<span class="muted">—</span>', body)

    def test_form_bound_report_renders_bind_enabled_input(self):
        """T2/B1：编辑已绑定任务时，绑定报表渲染 bind_enabled 输入。"""
        self._add_schedule_row()
        sid = self._sched_row()["id"]
        body = self._form_body(f"edit={sid}")
        self.assertIn("bind_enabled_1", body)


class TestSchedulerPlanColumn(SchedulerHttpTest):
    """T4：任务列表「计划」列（合并原类型/计划）。"""

    def test_plan_interval_text(self):
        self._add_schedule_row(schedule_type="interval", interval_minutes=45)
        _, body, _ = self._get("/config/scheduler")
        self.assertIn("每 45 分钟", body)
        self.assertNotIn("<th>类型</th>", body)       # T4 合并：无独立类型列

    def test_plan_daily_text(self):
        self._add_schedule_row(schedule_type="daily", daily_time="08:30")
        _, body, _ = self._get("/config/scheduler")
        self.assertIn("每天 08:30", body)


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
        toggles = [a for a in self.audit_calls if a["action"] == "toggle_schedule"]
        self.assertTrue(toggles)
        # S15：解耦后审计文案引用任务名/任务 id，不再引用 report#/report_id
        rec = toggles[-1]
        self.assertNotIn("report#", rec.get("detail") or "")
        self.assertNotIn("report_id", str(rec.get("before_value") or {}))

    def test_delete_removes_row_and_audits(self):
        sid = self._add_schedule_row()
        code, result, _ = self._post(f"/config/scheduler/delete/{sid}", {})
        self.assertEqual(code, 302)
        self.assertIsNone(self._sched_row())
        rec = self._audit_of("delete_schedule")[0]
        self.assertEqual(rec["entity_id"], sid)


# ---------------------------------------------------------------------------
# 回归（2026-08-23 审查）：save 必须消费 edit_id 隐藏域
#
# 表单带 edit_id 但后端丢弃 → 定位全靠任务名：编辑改名会另建重复任务、
# 同名任务互相顶替更新（数据事故源）。
# ---------------------------------------------------------------------------

class TestSchedulerSaveEditId(SchedulerHttpTest):

    def _task_count(self):
        conn = _get_conn()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM report_schedules").fetchone()[0]
        finally:
            conn.close()

    def _save(self, **extra):
        fields = dict(name="任务X", schedule_type="interval",
                      interval_minutes="45", daily_time="08:00",
                      misfire_policy="skip", report_ids="1",
                      exclusions="", action="save_close")
        fields.update(extra)
        return self._post("/config/scheduler/save", fields)

    def test_save_with_edit_id_updates_same_task_even_renamed(self):
        """编辑态改名 → 原任务行原地更新，不新建重复任务。"""
        sid = self._add_schedule_row(name="旧名")
        code, result, _ = self._save(edit_id=str(sid), name="新名",
                                     interval_minutes="90")
        self.assertEqual(code, 302)
        self.assertNotIn("错误", result)
        self.assertEqual(self._task_count(), 1)
        row = self._sched_row()
        self.assertIsNotNone(row)
        self.assertEqual((row["id"], row["name"], row["interval_minutes"]),
                         (sid, "新名", 90))

    def test_save_new_with_existing_name_rejected(self):
        """新建时任务名已被占用 → 回显错误且不落库（不顶替既有任务）。"""
        self._add_schedule_row(name="占用")
        code, result, _ = self._save(name="占用")
        self.assertEqual(code, 302)
        self.assertIn("错误", urllib.parse.unquote(result))
        self.assertIn("已存在", urllib.parse.unquote(result))
        self.assertEqual(self._task_count(), 1)

    def test_save_invalid_exclusions_rejected_without_write(self):
        """排除规则 JSON 非法 → 回显错误且不落库（§7.3 不静默吞）。"""
        code, result, _ = self._save(name="坏规则", exclusions="{bad json")
        self.assertEqual(code, 302)
        self.assertIn("错误", urllib.parse.unquote(result))
        self.assertIn("排除", urllib.parse.unquote(result))
        self.assertEqual(self._task_count(), 0)

    def test_save_parses_binding_enabled(self):
        """S10 UI：bind_enabled_<rid> 未勾选 → 该绑定停用（enabled=0）；
        勾选或未显式提供 → 启用。"""
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs (id,name,sql_query,default_page_size,"
            "pool_id,prefer_cache) VALUES (?,?,?,20,1,1)", (2, "报表B", "SELECT 2"))
        conn.commit()
        conn.close()
        code, result, _ = self._save(report_ids="1,2", bind_enabled_1="1",
                                     bind_enabled_2="1")
        self.assertEqual(code, 302)
        self.assertNotIn("错误", result)
        sid = self._sched_row()["id"]
        conn = _get_conn()
        en = dict(conn.execute(
            "SELECT report_id, enabled FROM schedule_reports "
            "WHERE schedule_id=?", (sid,)).fetchall())
        conn.close()
        self.assertEqual(en, {1: 1, 2: 1})
        # 编辑保存不勾 bind_enabled_2 → 绑定 2 停用，绑定 1 保留
        code, result, _ = self._save(edit_id=str(sid), report_ids="1,2",
                                     bind_enabled_1="1")
        self.assertEqual(code, 302)
        conn = _get_conn()
        en = dict(conn.execute(
            "SELECT report_id, enabled FROM schedule_reports "
            "WHERE schedule_id=?", (sid,)).fetchall())
        conn.close()
        self.assertEqual(en, {1: 1, 2: 0})

    def test_edit_link_targets_get_route(self):
        """列表页编辑链接指向 GET /config/scheduler?edit=N（原指向 POST
        端点 /config/scheduler/save，语义错误）。"""
        self._add_schedule_row(name="链接检查")
        _, body, _ = self._get("/config/scheduler")
        self.assertIn('href="/config/scheduler?edit=', body)
        self.assertNotIn('href="/config/scheduler/save?edit=', body)

    def test_task_form_renders_exclusion_tree_editor(self):
        """§7.3：排除规则为前端树编辑器骨架（增删规则/嵌套组/源码模式），
        JSON 经隐藏域 name=exclusions 提交，不再暴露裸 textarea。"""
        _, body, _ = self._get("/config/scheduler")
        for fragment in ('id="excl-rules"', 'id="excl-json"',
                         'name="exclusions"', "exclAddRule", "exclAddGroup",
                         "exclToggleSource", "exclRebuild"):
            self.assertIn(fragment, body)
        # 可视化模式下不应再有可直接编辑提交的可见 exclusions 文本域
        self.assertNotIn('<textarea name="exclusions"', body)

    def test_task_form_prefills_exclusions_json(self):
        """编辑态：既有排除树 JSON 转义后回填隐藏域供编辑器初始化。"""
        import json as _json
        tree = _json.dumps({"op": "OR", "children": [
            {"type": "dow", "in": ["sat", "sun"]}]})
        sid = self._add_schedule_row(name="带排除", exclusions=tree)
        _, body, _ = self._get("/config/scheduler", f"edit={sid}")
        self.assertIn("excl-json", body)
        self.assertIn("sat", body)


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
