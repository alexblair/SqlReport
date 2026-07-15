"""
test_cache_ui.py — Redis 缓存 UI 显示测试（验证用户报告的两个问题）

策略：
- 缓存 UI 显示测试：直接测试 _build_report_html，传入带有 cache_info 的 ReportResult
- 重建缓存测试：在 execute_report 层测试，mock 只到 MySQL 层
"""

import unittest
from unittest.mock import patch, MagicMock
import sqlite3
import time
import re
import db
import report
from report import ReportResult, _build_report_html


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL,
            password TEXT NOT NULL, database TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE report_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            parent_id INTEGER);
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL,
            default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, category_id INTEGER, memo TEXT,
            result_names TEXT DEFAULT '',
            prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0);
    """)
    return conn


class TestCacheUIDisplay(unittest.TestCase):
    """Issue 1: 验证缓存 UI 是否显示完整的 Redis 缓存状态"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")

    def tearDown(self):
        self.conn.close()

    def _make_result(self, cache_info=None):
        """创建带 cache_info 的 ReportResult"""
        return ReportResult(
            columns=["id", "name"],
            rows=[(1, "test")],
            total=1,
            page=1,
            page_size=10,
            results=[{"columns": ["id", "name"], "rows": [(1, "test")]}],
            cache_info=cache_info,
        )

    def test_redis_cache_badge_shows_redis_source(self):
        """基线：Redis 快照模式应显示 'Redis 快照' 标签"""
        result = self._make_result(cache_info={"source": "redis", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表X", "sql_query": "SELECT 1", "memo": "", "result_names": ""},
            result)
        self.assertIn("Redis 快照", body)

    def test_cache_badge_missing_redis_cache_indicator(self):
        """FAIL: prefer_cache=1 时未显示 Redis 缓存已启用标记"""
        result = self._make_result(cache_info={"source": "redis", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表X", "sql_query": "SELECT 1", "memo": "",
             "result_names": "", "prefer_cache": 1, "cache_ttl_hours": 24},
            result)
        # 期望显示 prefer_cache 或"Redis 缓存已启用"
        # FAIL: 目前 cache-badge 仅显示"Redis 快照 (Xs 前)"，不包含 prefer_cache 状态
        self.assertIn("prefer_cache", body)

    def test_cache_badge_missing_ttl_display(self):
        """FAIL: cache_ttl_hours=24 时未显示 TTL 信息"""
        result = self._make_result(cache_info={"source": "redis", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "TTL报表", "sql_query": "SELECT 1", "memo": "",
             "result_names": "", "prefer_cache": 1, "cache_ttl_hours": 24},
            result)
        # 期望显示"24 小时过期"或类似信息
        # FAIL: 目前缓存标签仅显示相对时间
        self.assertIn("24", body)

    def test_cache_badge_shows_absolute_timestamp(self):
        """基线：缓存标签应显示绝对建立时间 YYYY-MM-DD HH:MM:SS"""
        result = self._make_result(cache_info={"source": "redis", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "时间报表", "sql_query": "SELECT 1", "memo": "",
             "result_names": "", "prefer_cache": 1, "cache_ttl_hours": 24},
            result)
        # 横幅 flash-info 中包含绝对时间
        has_abs_time = bool(re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', body))
        # FAIL: cache-badge 只有相对时间(60s前), 绝对时间仅在 flash-info 横幅
        self.assertTrue(has_abs_time, "页面应包含 YYYY-MM-DD HH:MM:SS 格式的缓存建立时间")

    def test_process_cache_badge_shows_process_source(self):
        """基线：进程缓存模式显示 '进程缓存'"""
        result = self._make_result(cache_info={"source": "process", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表P", "sql_query": "SELECT 1", "memo": "",
             "result_names": ""},
            result)
        self.assertIn("进程缓存", body)

    def test_mysql_direct_badge(self):
        """基线：直连 MySQL 模式显示 '直连 MySQL'"""
        result = self._make_result(cache_info={"source": "mysql", "timestamp": time.time()})
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表M", "sql_query": "SELECT 1", "memo": "",
             "result_names": ""},
            result)
        self.assertIn("直连 MySQL", body)

    def test_no_cache_info(self):
        """基线：无缓存信息显示 '未缓存'"""
        result = self._make_result(cache_info=None)
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表N", "sql_query": "SELECT 1", "memo": "",
             "result_names": ""},
            result)
        self.assertIn("未缓存", body)

    def test_process_cache_preserves_redis_source_after_f5(self):
        """F5 刷新后进程缓存仍显示 Redis 来源信息"""
        # 模拟进程缓存命中，但缓存数据源自 Redis
        report_id = 1
        test_ts = time.time() - 60  # 60 秒前
        report._query_cache.set(report_id,
            [{"columns": ["id"], "rows": [(1,)]}], "SELECT 1",
            source="redis", source_timestamp=test_ts)

        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        report_config = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                         "sql_query": "SELECT 1", "name": "报表X", "memo": "",
                         "result_names": ""}
        result_obj = report.execute_report(report_id, "SELECT 1", pool, report=report_config)
        self.assertIsNotNone(result_obj.cache_info)
        self.assertEqual(result_obj.cache_info["source"], "redis")

    def test_process_cache_fallback_when_source_not_set(self):
        """进程缓存无 source 字段时正常降级为 'process'"""
        report._query_cache.set(99,
            [{"columns": ["id"], "rows": [(1,)]}], "SELECT 1")
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result_obj = report.execute_report(99, "SELECT 1", pool)
        self.assertIsNotNone(result_obj.cache_info)
        self.assertEqual(result_obj.cache_info["source"], "process")


class TestRebuildCacheButton(unittest.TestCase):
    """Issue 2: 验证【重建缓存】按钮行为"""

    def setUp(self):
        report._query_cache.clear()
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")

    def tearDown(self):
        self.conn.close()

    def test_rebuild_button_exists(self):
        """验证【重建缓存】按钮存在于页面中"""
        result = ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10,
            results=[{"columns": ["id"], "rows": [(1,)]}])
        body = _build_report_html(self.conn,
            {"id": 1, "name": "报表X", "sql_query": "SELECT 1", "memo": "",
             "result_names": ""},
            result)
        self.assertIn("重建缓存", body)
        self.assertIn("refresh=1", body)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    def test_rebuild_clears_redis_snapshot(self, mock_get_mgr, mock_create_conn, mock_exec_q):
        """验证：【重建缓存】refresh=1 时清除 Redis 快照"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        mock_mgr = MagicMock()
        mock_mgr._config = {"key_prefix": "sr"}
        mock_mgr.available = True
        mock_mgr.acquire_lock.return_value = True
        mock_mgr.wait_for_lock.return_value = True
        mock_mgr.get_snapshot.return_value = None
        mock_get_mgr.return_value = mock_mgr

        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        report_config = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                         "sql_query": "SELECT 1", "name": "报表X", "memo": ""}

        # 第一次调用：写入 Redis 快照
        report.execute_report(1, "SELECT 1", pool, report=report_config, refresh=False)
        mock_mgr.set_snapshot.assert_called_once()
        mock_mgr.reset_mock()

        # 第二次调用：refresh=True → 清除 Redis 快照
        report.execute_report(1, "SELECT 1", pool, report=report_config, refresh=True)
        mock_mgr.delete_snapshot.assert_called_once()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    def test_rebuild_clears_process_cache(self, mock_get_mgr, mock_create_conn, mock_exec_q):
        """验证：refresh=1 清除进程缓存后重新从 MySQL 加载"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        mock_mgr = MagicMock()
        mock_mgr._config = {"key_prefix": "sr"}
        mock_mgr.available = False
        mock_get_mgr.return_value = mock_mgr

        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        report_config = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                         "sql_query": "SELECT 1", "name": "报表X", "memo": ""}

        # 先种入进程缓存
        report._query_cache.set(1, [{"columns": ["id"], "rows": [(1,)]}], "SELECT 1")

        # 验证 invalidate 在 refresh=True 时被触发
        orig_invalidate = report._query_cache.invalidate
        invalidate_called = [False]
        def tracking_invalidate(rid):
            invalidate_called[0] = True
            return orig_invalidate(rid)
        report._query_cache.invalidate = tracking_invalidate

        result = report.execute_report(1, "SELECT 1", pool, report=report_config, refresh=True)

        self.assertTrue(invalidate_called[0], "refresh=True 应清除进程缓存")
        # refresh 后进程缓存被重新填充（从 MySQL 加载），所以 get 不为 None
        self.assertIsNotNone(report._query_cache.get(1))

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    def test_rebuild_shows_redis_cache_info(self, mock_get_mgr, mock_create_conn, mock_exec_q):
        """验证：重建缓存后页面上显示 Redis 快照信息而非'直连 MySQL'"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        mock_mgr = MagicMock()
        mock_mgr._config = {"key_prefix": "sr"}
        mock_mgr.available = True
        mock_mgr.get_snapshot.return_value = None
        mock_mgr.acquire_lock.return_value = True
        mock_get_mgr.return_value = mock_mgr

        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        report_config = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                         "sql_query": "SELECT 1", "name": "报表X", "memo": "", "result_names": ""}

        result = report.execute_report(1, "SELECT 1", pool, report=report_config, refresh=True)
        self.assertIsNotNone(result.cache_info)
        self.assertEqual(result.cache_info["source"], "redis",
                         "重建缓存后应显示 Redis 快照来源")
        self.assertTrue(result.cache_info.get("fresh", False))

        # 验证进程缓存也被标记为 Redis 来源
        cached = report._query_cache.get(1)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.source, "redis")


if __name__ == "__main__":
    unittest.main()
