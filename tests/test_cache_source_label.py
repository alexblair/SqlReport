"""tests/test_cache_source_label.py — cache_info.source 生产者语义（spec 2026-10-05 §7.1）

钉死四件事：① 冷路径报 mysql（不再冒名 redis）；② 紧接的 L1 命中报 process；
③ L2 命中（含 L2→L1 继承）仍报 redis；④ 徽标文案与来源一致（不得说谎）。
"""
import time
import unittest
from unittest.mock import MagicMock, patch

import redis_cache
import render
import report

POOL = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
REDIS_CFG = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
             "sql_query": "SELECT 1", "name": "报表R", "memo": "", "result_names": ""}
NO_REDIS_CFG = dict(REDIS_CFG, prefer_cache=0)


def _mgr():
    """可用的 Redis 管理器 mock（acquire_lock 默认真值 → 本进程持锁）。"""
    mgr = MagicMock()
    mgr.key_prefix = "sr"
    return mgr


def _snapshot(rows):
    return redis_cache.ReportSnapshot(
        [{"columns": ["id"], "rows": rows}], "SELECT 1", 123.0, "v1")


class TestCacheSourceProducer(unittest.TestCase):
    """生产者取值表（spec §5.1）。"""

    def setUp(self):
        report._query_cache.clear()

    def tearDown(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_cold_request_reports_mysql_and_snapshot_written(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """冷路径（prefer_cache=1 + Redis 可用）→ mysql + snapshot_written=True。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "mysql")
        self.assertIs(result.cache_info["snapshot_written"], True)
        self.assertTrue(result.cache_info["fresh"])
        mgr.set_snapshot.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_second_request_l1_hit_reports_process(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """回归点：冷查后的第二次请求走 L1 → process（不得再是 redis），且不查库。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        first = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)
        second = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(first.cache_info["source"], "mysql")
        self.assertEqual(second.cache_info["source"], "process")
        self.assertEqual(mock_exec.call_count, 1)

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_l2_snapshot_hit_reports_redis(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """L2 命中 → redis（不变），并回填带 redis 来源的 L1 条目。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = _snapshot([(10,)])
        mock_mgr.return_value = mgr

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "redis")
        self.assertTrue(result.cache_info["fresh"])
        cached = report._query_cache.get(1)
        self.assertEqual(cached.source, "redis")
        self.assertEqual(cached.source_timestamp, 123.0)
        mock_exec.assert_not_called()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_l1_entry_from_l2_still_reports_redis(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """L2→L1 继承链不得断裂：L1 命中来自 L2 的条目仍报 redis。"""
        mgr = _mgr()
        mgr.get_snapshot.return_value = _snapshot([(10,)])
        mock_mgr.return_value = mgr

        report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)
        second = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(second.cache_info["source"], "redis")
        self.assertEqual(second.cache_info["timestamp"], 123.0)
        mgr.get_snapshot.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_mysql_failure_falls_back_to_stale_snapshot(
            self, mock_conn, mock_exec, mock_avail, mock_mgr):
        """数据源故障 + 过期快照 → redis_fallback 且 fresh=False（不变）。"""
        mgr = _mgr()
        mgr.get_snapshot.side_effect = [None, _snapshot([(9,)])]
        mock_mgr.return_value = mgr
        mock_conn.return_value = MagicMock()
        mock_exec.side_effect = RuntimeError("db down")

        result = report.execute_report(1, "SELECT 1", POOL, report=REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "redis_fallback")
        self.assertIs(result.cache_info["fresh"], False)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_redis_disabled_reports_mysql_without_snapshot(self, mock_conn, mock_exec):
        """未启用 Redis（prefer_cache=0）→ mysql + snapshot_written=False（键必须在）。"""
        mock_exec.return_value = [{"columns": ["id"], "rows": [(3,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", POOL, report=NO_REDIS_CFG)

        self.assertEqual(result.cache_info["source"], "mysql")
        self.assertIs(result.cache_info["snapshot_written"], False)


class TestBadgeHonesty(unittest.TestCase):
    """徽标/横幅不得说谎（spec §7.1 渲染断言）。"""

    def test_mysql_source_badge_says_realtime(self):
        html = render.build_cache_badge_html(
            {"source": "mysql", "timestamp": time.time(), "fresh": True,
             "snapshot_written": True},
            prefer_cache=True, cache_ttl_hours=24)
        self.assertIn("实时查询", html)
        self.assertNotIn("缓存快照", html)

    def test_process_source_badge_says_local_cache(self):
        html = render.build_cache_badge_html(
            {"source": "process", "timestamp": time.time()},
            prefer_cache=True, cache_ttl_hours=24)
        self.assertIn("本地缓存", html)
        self.assertNotIn("缓存快照", html)

    def test_cold_path_banner_does_not_claim_snapshot(self):
        with patch("render.redis_cache.redis_available", return_value=True):
            html = render.build_redis_banners_html(
                {"source": "mysql", "timestamp": time.time(),
                 "fresh": True, "snapshot_written": True})
        self.assertNotIn("数据来自缓存快照", html)
