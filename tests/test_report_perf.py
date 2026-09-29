"""
tests/test_report_perf.py — execute_report 执行链路的调用次数约束（C-1a）

背景：
    性能基线（spec §10.1）显示执行链路的固定开销随请求线性累积。本文件把
    「同一次执行内不该重复做的事」钉成可回归的断言：

    1. sql_contains_write —— 对整条 SQL 做一次拆分 + 关键词扫描。改前在
       allow_write=0 时被调用两次（report.py:1064 与 :1071），每次都要把
       整条 SQL 重新解析一遍。
    2. get_redis_manager —— 改前一次执行内最多取三次（:1095 / :1135 / :1160）。

这两个断言的价值不在于"快了多少"，而在于**它们一旦变红就说明有人重新引入了
重复解析**。这类回归不会报错，只会让 SQL 越长越慢。
"""

import unittest
from unittest.mock import patch, MagicMock

import report
from report import execute_report


POOL = {"host": "h", "port": 3306, "user": "u",
        "password": "p", "database": "d"}

# allow_write=0：这是 sql_contains_write 被调第二次的唯一条件
REPORT_NO_WRITE = {"prefer_cache": 0, "cache_ttl_hours": 0, "pool_id": 1,
                   "sql_query": "SELECT 1", "name": "报表A", "memo": "",
                   "allow_write": 0}

# prefer_cache=1：触发 Redis 分支
REPORT_REDIS = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                "sql_query": "SELECT 1", "name": "报表B", "memo": "",
                "allow_write": 1}


def _redis_mgr():
    """可用的 Redis 管理器 mock：快照未命中、需要走 MySQL。"""
    mgr = MagicMock()
    mgr.key_prefix = "sr"
    mgr.get_snapshot.return_value = None
    mgr.acquire_lock.return_value = True
    mgr.wait_for_lock.return_value = True
    return mgr


class TestSqlContainsWriteEvaluatedOnce(unittest.TestCase):
    """sql_contains_write 每次执行只解析一遍 SQL。"""

    def setUp(self):
        report._query_cache.clear()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.sql_contains_write", return_value=False)
    def test_evaluated_once_when_allow_write_is_zero(self, mock_has_write,
                                                     mock_conn, mock_query):
        """✅ Positive: allow_write=0（写护栏开启）时也只解析一次。

        改前此路径会调用两次：一次算 skip_cache_read，一次算写护栏。
        """
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        execute_report(1, "SELECT 1 FROM t", POOL, report=REPORT_NO_WRITE)

        self.assertEqual(
            mock_has_write.call_count, 1,
            f"sql_contains_write 被调用 {mock_has_write.call_count} 次，"
            f"应只解析整条 SQL 一次")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.sql_contains_write", return_value=False)
    def test_evaluated_once_when_allow_write_is_one(self, mock_has_write,
                                                    mock_conn, mock_query):
        """✅ Positive: allow_write=1（默认）时只解析一次。"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        cfg = dict(REPORT_NO_WRITE, allow_write=1)
        execute_report(1, "SELECT 1 FROM t", POOL, report=cfg)

        self.assertEqual(mock_has_write.call_count, 1)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.sql_contains_write", return_value=True)
    def test_write_sql_still_denied_with_single_parse(self, mock_has_write,
                                                      mock_conn, mock_query):
        """✅ Positive: 去重没有削弱写护栏——含写语句仍然 403。"""
        mock_conn.return_value = MagicMock()

        with self.assertRaises(PermissionError):
            execute_report(1, "DELETE FROM t", POOL, report=REPORT_NO_WRITE)

        self.assertEqual(mock_has_write.call_count, 1)
        # 写护栏拦下后不应再去连 MySQL
        mock_conn.assert_not_called()


class TestRedisManagerFetchedOnce(unittest.TestCase):
    """get_redis_manager 每次执行只取一次全局单例。"""

    def setUp(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_manager_fetched_once_on_miss_path(self, mock_conn, mock_query,
                                               mock_avail, mock_get_mgr):
        """✅ Positive: 快照未命中、走 MySQL 的路径上只取一次管理器。

        改前该路径取三次：算 config_version、试读快照、准备重建锁。
        """
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()
        mock_get_mgr.return_value = _redis_mgr()

        execute_report(1, "SELECT 1 FROM t", POOL, report=REPORT_REDIS)

        self.assertEqual(
            mock_get_mgr.call_count, 1,
            f"get_redis_manager 被调用 {mock_get_mgr.call_count} 次，"
            f"应只取一次全局单例")

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_manager_fetched_once_on_redis_hit_path(self, mock_conn, mock_query,
                                                    mock_avail, mock_get_mgr):
        """✅ Positive: L2 快照直接命中时同样只取一次。"""
        mock_conn.return_value = MagicMock()
        mgr = _redis_mgr()
        mgr.get_snapshot.return_value = report.redis_cache.ReportSnapshot(
            [{"columns": ["id"], "rows": [(1,)]}], "SELECT 1 FROM t",
            100.0, "v1")
        mock_get_mgr.return_value = mgr

        result = execute_report(1, "SELECT 1 FROM t", POOL, report=REPORT_REDIS)

        self.assertEqual(mock_get_mgr.call_count, 1)
        # 命中路径不得连 MySQL
        mock_conn.assert_not_called()
        self.assertEqual(result.cache_info["source"], "redis")

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_manager_fetched_once_on_refresh_path(self, mock_conn, mock_query,
                                                  mock_avail, mock_get_mgr):
        """✅ Positive: refresh=True（先删后查）也只取一次。"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()
        mock_get_mgr.return_value = _redis_mgr()

        execute_report(1, "SELECT 1 FROM t", POOL, report=REPORT_REDIS,
                       refresh=True)

        self.assertEqual(mock_get_mgr.call_count, 1)


if __name__ == "__main__":
    unittest.main()
