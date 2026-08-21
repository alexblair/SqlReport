"""test_scheduler_primitives.py — 定时任务执行原语测试（T2）。

覆盖规格 .scratch/report-scheduler/spec.md 缺口：
- G9 force_rebuild「先算后换」（execute_report 保活参数）
- G11 前置：rebuild_static_endpoint_file 公共落盘函数（保活与 miss 共用）

测试策略：
- force_rebuild：mock Redis 管理器（新鲜快照/旧快照）+ mock MySQL，
  断言读取跳过、锁不获取、新快照原子覆盖、MySQL 失败走旧快照兜底
- rebuild_static_endpoint_file：临时 SQLite + CONFIG 隔离（复用
  test_static_cache 的环境模式），直接以公共函数为 seam 断言落盘行为
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, call

import api_handler
import db
import report
import redis_cache
import static_cache
from redis_cache import ReportSnapshot
from tests.test_mysql_mock import MockMySQLMixin


# ---------------------------------------------------------------------------
# G9：force_rebuild 先算后换
# ---------------------------------------------------------------------------

class TestForceRebuild(unittest.TestCase):
    """execute_report(force_rebuild=True) 保活语义。"""

    def setUp(self):
        self.cache = report.QueryCache(ttl=300)
        self.mgr = MagicMock()
        self.mgr.key_prefix = "sr"
        # 默认无快照；各用例自行设置 get_snapshot 行为
        self.mgr.get_snapshot.return_value = None

        patchers = [
            patch("report.redis_cache.redis_available", return_value=True),
            patch("report.redis_cache.get_redis_manager",
                  return_value=self.mgr),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def _snapshot(self, marker):
        """构造含标记数据的旧快照。"""
        return ReportSnapshot(
            results=[{"columns": ["id", "name"],
                      "rows": [[1, f"旧-{marker}"]],
                      "total": 1}],
            sql_query="SELECT id, name FROM users",
            updated_at=time.time(), config_version="v-old")

    def _mysql_mock(self, marker=None, error=None):
        """构造 MySQL 连接 mock；error 非 None 时查询抛异常。"""
        mock_conn, mock_cursor = MockMySQLMixin.make_mock_connection()
        if error is not None:
            mock_cursor.fetchall.side_effect = error
        else:
            mock_cursor.description = [("id",), ("name",)]
            mock_cursor.fetchall.return_value = [(2, f"新-{marker}")]
        return mock_conn

    def _run(self, pool_config, **kw):
        args = dict(
            report_id=1, sql_query="SELECT id, name FROM users",
            pool_config=pool_config,
            report={"prefer_cache": 1, "cache_ttl_hours": 6,
                    "pool_id": 7, "sql_query": "SELECT id, name FROM users"},
            conn=None, cache=self.cache)
        args.update(kw)
        return report.execute_report(**args)

    def test_force_rebuild_skips_fresh_snapshot_and_writes_new(self):
        """新鲜快照存在：普通调用命中快照；force_rebuild 直查 MySQL 并写新快照。"""
        self.mgr.get_snapshot.return_value = self._snapshot("A")
        with patch("db.create_mysql_connection",
                   return_value=self._mysql_mock("B")):
            normal = self._run({"host": "h"})
            self.assertEqual(normal.cache_info["source"], "redis")
            self.assertIn("旧-A", str(normal.results))

            rebuilt = self._run({"host": "h"}, force_rebuild=True)
            # 成功后新数据写入各层缓存：进程缓存来源标记为 redis（快照已更新）
            self.assertEqual(rebuilt.cache_info["source"], "redis")
            self.assertTrue(rebuilt.cache_info.get("fresh"))
            self.assertIn("新-B", str(rebuilt.results))
            # 新快照已原子写入 Redis（先算后换的"换"）
            self.mgr.set_snapshot.assert_called()

    def test_force_rebuild_does_not_acquire_lock(self):
        """force_rebuild 不取重建锁、不等他人锁结果。"""
        with patch("db.create_mysql_connection",
                   return_value=self._mysql_mock("B")):
            self._run({"host": "h"}, force_rebuild=True)
        self.mgr.acquire_lock.assert_not_called()
        self.mgr.wait_for_lock.assert_not_called()

    def test_force_rebuild_mysql_failure_falls_back_to_stale(self):
        """MySQL 失败：不抛异常，旧快照兜底返回，且未删除旧快照。"""
        self.mgr.get_snapshot.return_value = self._snapshot("A")
        with patch("db.create_mysql_connection",
                   return_value=self._mysql_mock(error=RuntimeError("db down"))):
            result = self._run({"host": "h"}, force_rebuild=True)
        self.assertEqual(result.cache_info["source"], "redis_fallback")
        self.assertIn("旧-A", str(result.results))
        self.mgr.delete_snapshot.assert_not_called()
        # 失败路径不写新快照
        self.mgr.set_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# G11 前置：rebuild_static_endpoint_file 公共落盘函数
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_primitives_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")
_CACHE_DIR = os.path.join(_TMP_ROOT, "cache")


def _test_config() -> dict:
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "static_cache": {"enable": True, "dir": _CACHE_DIR},
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _set_up_db():
    """内联建表 DDL（项目惯例：有意重复，避免循环导入）。"""
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
    """)
    conn.execute(
        "INSERT OR IGNORE INTO connection_pools "
        "(name,host,port,user,password,database,sort_order) "
        "VALUES (?,?,?,?,?,?,?)",
        ("测试池", "127.0.0.1", 3306, "root", "pass", "testdb", 1))
    conn.commit()
    conn.close()


_set_up_db()


class TestRebuildStaticEndpointFile(MockMySQLMixin, unittest.TestCase):
    """公共落盘原语：保活链路与请求 miss 链路共用。"""

    @classmethod
    def setUpClass(cls):
        cls._mysql_patcher = patch("db.create_mysql_connection")
        cls._mock_factory = cls._mysql_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._mysql_patcher.stop()
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

    def setUp(self):
        self._cfg_patcher = patch("app_config.get_config",
                                  return_value=_test_config())
        self._cfg_patcher.start()
        self.addCleanup(self._cfg_patcher.stop)
        conn = _get_conn()
        conn.execute("DELETE FROM api_endpoints")
        conn.execute("DELETE FROM report_configs")
        conn.commit()
        conn.close()
        if os.path.isdir(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
        static_cache._last_invalidated.clear()

        mock_conn, mock_cursor = self.make_mock_connection()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "张三"), (2, "李四")]

    def _create_fixture(self, sql="SELECT id, name FROM users",
                        url="/api/keep", allow_write=1):
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO report_configs "
            "(name,sql_query,default_page_size,pool_id,prefer_cache,"
            "cache_ttl_hours,allow_write) VALUES (?,?,?,?,?,2,?)",
            (f"报表-{url}", sql, 20, 1, 0, allow_write))
        rid = cur.lastrowid
        eid = db.add_api_endpoint(conn, rid, "端点", url,
                                  static_cache=1)
        conn.commit()
        endpoint = dict(conn.execute(
            "SELECT * FROM api_endpoints WHERE id=?", (eid,)).fetchone())
        conn.close()
        type(self)._mock_factory.return_value = self.make_mock_connection()[0]
        return endpoint

    def test_rebuild_writes_file_and_returns_200(self):
        endpoint = self._create_fixture()
        written, status, body, headers = api_handler.rebuild_static_endpoint_file(
            _get_conn(), endpoint)
        self.assertTrue(written)
        self.assertEqual(status, 200)
        file_path = os.path.join(_CACHE_DIR, "api", "keep.json")
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, encoding="utf-8") as fh:
            content = json.load(fh)
        self.assertIn("config_version", content["meta"])
        self.assertIsNotNone(content["meta"]["expires_at"])

    def test_rebuild_without_invalidation_keeps_record_clean(self):
        """record_invalidation=False（保活语义）：不产生失效事件记录。"""
        endpoint = self._create_fixture()
        api_handler.rebuild_static_endpoint_file(
            _get_conn(), endpoint, record_invalidation=False)
        self.assertNotIn("api/keep", static_cache._last_invalidated)
        # 对照：请求 miss 语义记录失效事件
        api_handler.rebuild_static_endpoint_file(
            _get_conn(), endpoint, record_invalidation=True)
        self.assertIn("api/keep", static_cache._last_invalidated)

    def test_rebuild_write_blocked_returns_403_no_file(self):
        endpoint = self._create_fixture(sql="UPDATE t SET x=1", allow_write=0)
        written, status, body, _ = api_handler.rebuild_static_endpoint_file(
            _get_conn(), endpoint)
        self.assertFalse(written)
        self.assertEqual(status, 403)
        self.assertFalse(os.path.exists(os.path.join(_CACHE_DIR, "api")))

    def test_miss_shell_preserves_error_content_type(self):
        """薄壳保留计算链路原始响应头（错误协商 Content-Type 不丢）。"""
        endpoint = self._create_fixture(sql="UPDATE t SET x=1", allow_write=0)
        status, body, headers = api_handler._execute_static_miss(
            _get_conn(), endpoint, "api/keep", None, 2, "v1", {})
        self.assertEqual(status, 403)
        self.assertEqual(headers["X-Static-Cache"], "miss")


if __name__ == "__main__":
    unittest.main()
