"""test_scheduler_cache.py — 定时执行缓存预热集成测试（B24）。

回归（2026-08-21）：定时执行曾以 refresh=False 走普通读取路径，命中
进程缓存/Redis 旧快照即短路——不执行 MySQL、不更新 Redis 快照（用户
现象：手动"立即执行"能建立 Redis 缓存，定时执行日志显示成功但缓存
不更新）。修复后定时/手动/补跑统一 force_rebuild=True（B14 保活同款
"先算后换"）。

本文件走真实 execute_report（不 mock 该函数），mock 的仅是外部依赖：
- MySQL 连接/查询层（report.db.create_mysql_connection / execute_mysql_query）
- Redis 管理器（FakeMgr 计数 set_snapshot 写入并留存快照）
- 配置库（临时 SQLite 文件库 + app_config.get_config 隔离）

覆盖矩阵（G15）：
- 手动执行（冷缓存）→ 查询 MySQL 并写快照
- 定时执行（进程缓存热）→ 仍重查 MySQL 并覆盖写快照
- 定时执行（进程冷、Redis 旧快照热）→ 仍重查 MySQL 并覆盖写快照
- 全冷定时执行 → 查询并写快照
"""

import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import config_db
import report as report_mod
import scheduler as scheduler_mod

_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_cache_")
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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS connection_pools ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, "
        "host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, "
        "user TEXT NOT NULL, password TEXT NOT NULL, "
        "database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS report_configs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, "
        "sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, "
        "pool_id INTEGER, memo TEXT, prefer_cache INTEGER NOT NULL DEFAULT 1, "
        "cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, "
        "allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, "
        "max_rows INTEGER NOT NULL DEFAULT 100000, "
        "keepalive_enabled INTEGER NOT NULL DEFAULT 0, "
        "keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS report_schedules ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL DEFAULT '', "
        "schedule_type TEXT NOT NULL DEFAULT 'interval', "
        "interval_minutes INTEGER NOT NULL DEFAULT 60, "
        "daily_time TEXT NOT NULL DEFAULT '08:00', "
        "misfire_policy TEXT NOT NULL DEFAULT 'skip', "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "exclusions TEXT, audit_enabled INTEGER NOT NULL DEFAULT 0, "
        "next_run_at REAL, last_run_at REAL, last_status TEXT, "
        "last_error TEXT, fail_count INTEGER NOT NULL DEFAULT 0, "
        "last_duration_ms INTEGER, "
        "created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')), "
        "updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schedule_reports ("
        "schedule_id INTEGER NOT NULL, report_id INTEGER NOT NULL, "
        "order_index INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, "
        "PRIMARY KEY (schedule_id, report_id))")
    conn.commit()
    conn.close()


_set_up_db()


class FakeMgr:
    """可观测 Redis 管理器：记录快照写入次数并留存最新快照。"""

    def __init__(self):
        self.key_prefix = "sr"
        self.writes = 0
        self.snapshot = None

    def get_snapshot(self, key):
        return self.snapshot

    def set_snapshot(self, key, snap, ttl_hours=None):
        self.writes += 1
        self.snapshot = snap

    def acquire_lock(self, key):
        return True

    def wait_for_lock(self, key):
        return True

    def release_lock(self, key):
        pass

    def delete_snapshot(self, key):
        self.snapshot = None


class FakeConn:
    def close(self):
        pass


class TestScheduleForcesCacheRebuild(unittest.TestCase):
    """真实 execute_report 集成：缓存热时定时执行仍刷新 Redis 快照。"""

    def setUp(self):
        report_mod._query_cache.clear()

        cfg_patcher = patch("app_config.get_config",
                            return_value=_test_config())
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)

        conn = _get_conn()
        for table in ("schedule_reports", "report_schedules", "report_configs",
                      "connection_pools"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "INSERT INTO connection_pools "
            "(id,name,host,port,user,password,database,sort_order) "
            "VALUES (1,'pool','127.0.0.1',3306,'root','p','db',1)")
        conn.execute(
            "INSERT INTO report_configs (id,name,sql_query,default_page_size,"
            "pool_id,prefer_cache,cache_ttl_hours,allow_write,allow_all_output,"
            "max_rows) "
            "VALUES (11,'99条物资','SELECT id FROM goods',20,1,1,6,1,1,100000)")
        conn.commit()
        conn.close()

        # 建任务（interval 30 分钟，绑定报表 11）
        self.sid = config_db.upsert_schedule(
            _get_conn(), report_ids=[11], schedule_type="interval",
            interval_minutes=30, daily_time="08:00", misfire_policy="skip",
            enabled=1, next_run_at=0.0)
        conn.close()

        # MySQL 查询层：计数 + 递增标记数据（每次执行返回不同值）
        self.mysql_calls = []
        self.mysql_counter = 0

        def _fake_query(mconn, sql, transactional=True):
            self.mysql_calls.append(sql)
            self.mysql_counter += 1
            n = self.mysql_counter
            return [{"columns": ["id"], "rows": [[n]], "total": 1}]

        self.conn_patcher = patch("report.db.create_mysql_connection",
                                  return_value=FakeConn())
        self.conn_patcher.start()
        self.addCleanup(self.conn_patcher.stop)
        self.query_patcher = patch("report.db.execute_mysql_query",
                                   side_effect=_fake_query)
        self.query_patcher.start()
        self.addCleanup(self.query_patcher.stop)

        # Redis 管理器 mock
        self.mgr = FakeMgr()
        redis_patchers = [
            patch("report.redis_cache.redis_available", return_value=True),
            patch("report.redis_cache.get_redis_manager", return_value=self.mgr),
            patch("report.redis_cache.compute_config_version", return_value="v1"),
            patch("report.redis_cache.build_snapshot_key",
                  return_value="snap:11"),
            patch("report.redis_cache.build_lock_key", return_value="lock:11"),
            patch("config_db.get_pool", return_value={
                "id": 1, "name": "pool", "host": "h", "port": 3306,
                "user": "u", "password": "p", "database": "d"}),
            patch("audit_db.record_operation"),
        ]
        for p in redis_patchers:
            p.start()
            self.addCleanup(p.stop)

        # 调度器实例：同步假执行器
        self.sched = scheduler_mod.ReportScheduler(tick_seconds=10, workers=2)

        class _SyncExec:
            def submit(self, fn, *a, **k):
                fn(*a, **k)
                return None

            def shutdown(self, wait=True):
                pass

        self.sched._executor = _SyncExec()

    def tearDown(self):
        report_mod._query_cache.clear()

    def _schedule_row(self):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_schedules WHERE id=?", (self.sid,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def test_manual_run_then_scheduled_run_both_refresh_snapshot(self):
        """核心回归：手动执行后进程缓存热，定时执行仍重查并覆盖快照。"""
        # 1) 手动立即执行（冷）→ 写快照一次，快照内容 = 第一次查询
        self.sched.trigger_schedule(self.sid, session_user="admin")
        self.assertEqual(self.mgr.writes, 1)
        self.assertEqual(self.mgr.snapshot.results[0]["rows"], [[1]])
        # 执行后进程缓存已热（force_rebuild 也写进程缓存）
        self.assertIsNotNone(
            report_mod._query_cache.get(11, "SELECT id FROM goods"))

        # 2) 定时执行（进程缓存热）→ 不得短路：重查 MySQL 并覆盖快照
        self.sched._run_schedule(self._schedule_row(), "scheduler")
        self.assertEqual(self.mgr.writes, 2)
        self.assertEqual(self.mgr.snapshot.results[0]["rows"], [[2]])
        self.assertEqual(len(self.mysql_calls), 2)

        # 3) 进程缓存冷（推进超过 TTL 300s）、Redis 旧快照仍热 → 仍重查覆盖
        with patch("time.time",
                   return_value=time.time() + 301):
            self.sched._run_schedule(self._schedule_row(), "scheduler")
        self.assertEqual(self.mgr.writes, 3)
        self.assertEqual(self.mgr.snapshot.results[0]["rows"], [[3]])
        self.assertEqual(len(self.mysql_calls), 3)

    def test_scheduled_run_with_warm_redis_snapshot_refreshes(self):
        """Redis 已有旧快照时定时执行仍强制重建（不命中旧快照短路）。"""
        # 预置"旧"快照（模拟手动执行遗留）
        self.sched.trigger_schedule(self.sid)
        old_updated_at = self.mgr.snapshot.updated_at

        # 定时执行 → 快照被覆盖写（updated_at 变化、数据变化）
        self.sched._run_schedule(self._schedule_row(), "scheduler")
        self.assertEqual(self.mgr.writes, 2)
        self.assertGreater(self.mgr.snapshot.updated_at, old_updated_at)
        self.assertEqual(self.mgr.snapshot.results[0]["rows"], [[2]])


if __name__ == "__main__":
    unittest.main()
