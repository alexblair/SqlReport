"""test_scheduler_db.py — 定时任务数据层测试（迁移 16 / CRUD / 级联删除）。

覆盖规格 .scratch/report-scheduler/spec.md 缺口：
- G1 迁移幂等（全新库 / 旧库升级 / 重复调用）
- G2 report_schedules CRUD + upsert 重算 next_run_at + 字段校验
- G3 应用层级联删除（delete_report 单个 + batch_delete_reports 批量）
"""

import sqlite3
import unittest
from unittest.mock import patch

from tests import init_test_db, BaseReportTest
import config_db


# 内联建表 DDL（项目惯例：有意重复，避免循环导入）
SQL_CREATE_REPORT_SCHEDULES = """CREATE TABLE IF NOT EXISTS report_schedules (
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
)"""


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


class TestMigration16(unittest.TestCase):
    """G1：迁移 16 幂等与旧库升级。"""

    def _init_via_config_db(self, conn):
        with patch("db._get_engine", return_value="sqlite3"):
            config_db.init_db(conn)

    def test_fresh_db_creates_table_and_columns(self):
        """全新库：init_db 创建 report_schedules 表与保活列。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            self._init_via_config_db(conn)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("report_schedules", tables)
            cols = _table_columns(conn, "report_schedules")
            for col in ("id", "report_id", "schedule_type", "interval_minutes",
                        "daily_time", "misfire_policy", "enabled",
                        "next_run_at", "last_run_at", "last_status",
                        "last_error", "fail_count"):
                self.assertIn(col, cols)
            rpt_cols = _table_columns(conn, "report_configs")
            self.assertIn("keepalive_enabled", rpt_cols)
            self.assertIn("keepalive_ahead_seconds", rpt_cols)
        finally:
            conn.close()

    def test_repeated_init_is_idempotent(self):
        """重复调用 init_db 不报错、不产生重复列。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            self._init_via_config_db(conn)
            self._init_via_config_db(conn)  # 第二次幂等
            rpt_cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(report_configs)")]
            self.assertEqual(rpt_cols.count("keepalive_enabled"), 1)
            self.assertEqual(rpt_cols.count("keepalive_ahead_seconds"), 1)
        finally:
            conn.close()

    def test_legacy_db_upgrade(self):
        """旧库升级：无 report_schedules 表、report_configs 无保活列 → 补齐且存量行保留。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            # 手工构造"迁移 16 之前"的最小结构（含一条存量报表）
            conn.executescript("""
                CREATE TABLE connection_pools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL, host TEXT NOT NULL,
                    port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL,
                    password TEXT NOT NULL, database TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE report_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    sql_query TEXT NOT NULL,
                    default_page_size INTEGER NOT NULL DEFAULT 20,
                    pool_id INTEGER,
                    sort_order INTEGER NOT NULL DEFAULT 0);
                INSERT INTO report_configs (name, sql_query, default_page_size, pool_id)
                    VALUES ('legacy', 'SELECT 1', 20, NULL);
            """)
            conn.commit()
            self._init_via_config_db(conn)
            row = conn.execute(
                "SELECT name FROM report_configs WHERE id=1").fetchone()
            self.assertEqual(row["name"], "legacy")
            self.assertIn("report_schedules",
                          {r[0] for r in conn.execute(
                              "SELECT name FROM sqlite_master WHERE type='table'")})
            self.assertIn("keepalive_enabled", _table_columns(conn, "report_configs"))
        finally:
            conn.close()


class _SchedBase(BaseReportTest):
    """带 report_schedules 表的公共基类。"""

    def setUp(self):
        super().setUp()
        self.conn.execute(SQL_CREATE_REPORT_SCHEDULES)
        self.conn.commit()


class TestScheduleCRUD(_SchedBase):
    """G2：定时任务 CRUD 与字段校验。"""

    def _create(self, **kw):
        args = dict(report_id=self.report_id, schedule_type="interval",
                    interval_minutes=30, daily_time="08:00",
                    misfire_policy="skip", enabled=1, next_run_at=1000.0)
        args.update(kw)
        return config_db.upsert_schedule(self.conn, session_user=None, **args)

    def test_create_and_get_by_report(self):
        sid = self._create()
        sched = config_db.get_schedule_by_report(self.conn, self.report_id)
        self.assertIsNotNone(sched)
        self.assertEqual(sched["id"], sid)
        self.assertEqual(sched["schedule_type"], "interval")
        self.assertEqual(sched["interval_minutes"], 30)
        self.assertEqual(sched["next_run_at"], 1000.0)
        self.assertIsNone(config_db.get_schedule_by_report(self.conn, 9999))

    def test_get_schedule_by_id(self):
        sid = self._create()
        self.assertEqual(config_db.get_schedule(self.conn, sid)["id"], sid)
        self.assertIsNone(config_db.get_schedule(self.conn, 9999))

    def test_upsert_updates_existing_row(self):
        """同报表二次 upsert 更新而非新增，且重算 next_run_at。"""
        self._create(next_run_at=1000.0)
        config_db.upsert_schedule(
            self.conn, report_id=self.report_id, schedule_type="daily",
            daily_time="09:30", misfire_policy="run_once", enabled=1,
            next_run_at=2000.0)
        rows = self.conn.execute(
            "SELECT * FROM report_schedules WHERE report_id=?",
            (self.report_id,)).fetchall()
        self.assertEqual(len(rows), 1)
        sched = config_db.get_schedule_by_report(self.conn, self.report_id)
        self.assertEqual(sched["schedule_type"], "daily")
        self.assertEqual(sched["daily_time"], "09:30")
        self.assertEqual(sched["misfire_policy"], "run_once")
        self.assertEqual(sched["next_run_at"], 2000.0)

    def test_get_all_schedules_orders_by_next_run(self):
        r2 = config_db.add_report(self.conn, "r2", "SELECT 2", 20, self.pool_id)
        self._create(next_run_at=3000.0)
        config_db.upsert_schedule(self.conn, report_id=r2,
                                  next_run_at=1000.0)
        all_scheds = config_db.get_all_schedules(self.conn)
        self.assertEqual([s["next_run_at"] for s in all_scheds],
                         [1000.0, 3000.0])

    def test_get_due_schedules_filters(self):
        """到期扫描只返回 enabled=1、fail_count<5、next_run_at<=now 的任务。"""
        self._create(next_run_at=500.0)                       # 到期
        r2 = config_db.add_report(self.conn, "r2", "SELECT 2", 20, self.pool_id)
        config_db.upsert_schedule(self.conn, report_id=r2, next_run_at=9999.0)  # 未到期
        due = config_db.get_due_schedules(self.conn, now=1000.0)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["report_id"], self.report_id)

    def test_get_due_excludes_disabled_and_burned(self):
        self._create(enabled=0, next_run_at=500.0)
        self.assertEqual(config_db.get_due_schedules(self.conn, 1000.0), [])
        self._create(enabled=1, next_run_at=500.0)
        self.conn.execute(
            "UPDATE report_schedules SET fail_count=5 WHERE report_id=?",
            (self.report_id,))
        self.conn.commit()
        self.assertEqual(config_db.get_due_schedules(self.conn, 1000.0), [])

    def test_mark_result_success_resets_failures(self):
        self._create()
        sid = config_db.get_schedule_by_report(self.conn, self.report_id)["id"]
        self.conn.execute(
            "UPDATE report_schedules SET fail_count=3, last_status='fail', "
            "last_error='x' WHERE id=?", (sid,))
        self.conn.commit()
        config_db.mark_schedule_result(self.conn, sid, "success",
                                       next_run_at=7777.0, last_run_at=7776.0)
        sched = config_db.get_schedule(self.conn, sid)
        self.assertEqual(sched["last_status"], "success")
        self.assertEqual(sched["fail_count"], 0)
        self.assertIsNone(sched["last_error"])
        self.assertEqual(sched["next_run_at"], 7777.0)
        self.assertEqual(sched["last_run_at"], 7776.0)

    def test_mark_result_failure_increments_and_truncates_error(self):
        self._create()
        sid = config_db.get_schedule_by_report(self.conn, self.report_id)["id"]
        config_db.mark_schedule_result(self.conn, sid, "fail",
                                       error="e" * 600, next_run_at=8888.0,
                                       last_run_at=8887.0)
        sched = config_db.get_schedule(self.conn, sid)
        self.assertEqual(sched["last_status"], "fail")
        self.assertEqual(sched["fail_count"], 1)
        self.assertEqual(len(sched["last_error"]), 500)
        self.assertEqual(sched["next_run_at"], 8888.0)

    def test_mark_result_invalid_status_raises(self):
        self._create()
        sid = config_db.get_schedule_by_report(self.conn, self.report_id)["id"]
        with self.assertRaises(ValueError):
            config_db.mark_schedule_result(self.conn, sid, "boom")

    def test_set_schedule_enabled_toggle(self):
        self._create(enabled=1)
        sid = config_db.get_schedule_by_report(self.conn, self.report_id)["id"]
        self.assertTrue(config_db.set_schedule_enabled(self.conn, sid, 0))
        self.assertEqual(config_db.get_schedule(self.conn, sid)["enabled"], 0)
        self.assertTrue(config_db.set_schedule_enabled(self.conn, sid, 1))
        self.assertEqual(config_db.get_schedule(self.conn, sid)["enabled"], 1)
        self.assertFalse(config_db.set_schedule_enabled(self.conn, 9999, 0))

    def test_delete_schedule(self):
        self._create()
        sid = config_db.get_schedule_by_report(self.conn, self.report_id)["id"]
        self.assertTrue(config_db.delete_schedule(self.conn, sid))
        self.assertIsNone(config_db.get_schedule(self.conn, sid))
        self.assertFalse(config_db.delete_schedule(self.conn, sid))

    def test_field_validation(self):
        cases = [
            dict(schedule_type="weekly"),
            dict(misfire_policy="always"),
            dict(interval_minutes=0),
            dict(daily_time="25:00"),
            dict(daily_time="8点"),
            dict(daily_time="08:60"),
        ]
        for kw in cases:
            with self.assertRaises(ValueError, msg=str(kw)):
                self._create(**kw)


class TestCascadeDelete(_SchedBase):
    """G3：删除报表时应用层级联清理任务行。"""

    def test_delete_report_removes_schedule(self):
        self._create_helper(self.report_id)
        self.assertTrue(config_db.delete_report(self.conn, self.report_id))
        self.assertIsNone(config_db.get_schedule_by_report(self.conn, self.report_id))

    def test_batch_delete_reports_removes_schedules(self):
        r2 = config_db.add_report(self.conn, "r2", "SELECT 2", 20, self.pool_id)
        self._create_helper(self.report_id)
        self._create_helper(r2)
        affected = config_db.batch_delete_reports(self.conn, [self.report_id, r2])
        self.assertEqual(affected, 2)
        self.assertIsNone(config_db.get_schedule_by_report(self.conn, self.report_id))
        self.assertIsNone(config_db.get_schedule_by_report(self.conn, r2))

    def _create_helper(self, report_id):
        config_db.upsert_schedule(self.conn, report_id=report_id,
                                  next_run_at=1000.0)


if __name__ == "__main__":
    unittest.main()
