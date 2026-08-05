"""
tests/test_query_cache.py — 查询缓存会话测试

覆盖候选 2 深化成果：
1. QueryCache 线程安全 — 并发逐出同一过期项不再抛 KeyError
2. 实例隔离 — 显式注入独立缓存会话，互不干扰（测试污染消除）
3. execute_report 缓存注入 — cache 参数生效，默认仍用全局缓存
"""

import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import report
from report import QueryCache, execute_report


class TestQueryCacheThreadSafety(unittest.TestCase):
    """QueryCache 线程安全：并发读/逐出不抛异常"""

    def test_concurrent_eviction_of_expired_entry(self):
        """✅ Positive: 多线程并发 get 同一过期项 → 无 KeyError（锁内逐出）"""
        cache = QueryCache(ttl=0.01)
        cache.set(1, [{"columns": ["id"], "rows": [(1,)]}], "SELECT 1")
        time.sleep(0.03)  # 等待过期

        errors = []

        def worker():
            try:
                for _ in range(200):
                    cache.get(1, "SELECT 1")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"并发逐出不应抛异常: {errors}")
        # 过期项已被逐出
        self.assertIsNone(cache.get(1, "SELECT 1"))

    def test_concurrent_set_and_get(self):
        """✅ Positive: 并发 set/get 混合操作不抛异常且最终一致"""
        cache = QueryCache(ttl=300)
        stop = threading.Event()
        errors = []

        def writer():
            try:
                for i in range(300):
                    cache.set(1, [{"columns": ["id"], "rows": [(i,)]}],
                              f"SELECT {i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def reader():
            try:
                while not stop.is_set():
                    cache.get(1)
                    cache.invalidate(2)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        w = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(4)]
        for r in readers:
            r.start()
        w.start()
        w.join()
        stop.set()
        for r in readers:
            r.join()

        self.assertEqual(errors, [], f"并发 set/get 不应抛异常: {errors}")


class TestQueryCacheIsolation(unittest.TestCase):
    """缓存会话隔离：独立实例互不干扰"""

    def test_instances_do_not_share_entries(self):
        """✅ Positive: 两个实例各自管理自己的缓存项"""
        a = QueryCache()
        b = QueryCache()
        a.set(1, [{"columns": ["id"], "rows": [(1,)]}], "SELECT A")
        b.set(1, [{"columns": ["id"], "rows": [(2,)]}], "SELECT B")

        self.assertEqual(a.get(1).results[0]["rows"], [(1,)])
        self.assertEqual(b.get(1).results[0]["rows"], [(2,)])
        # 清除 a 不影响 b
        a.clear()
        self.assertIsNone(a.get(1))
        self.assertIsNotNone(b.get(1))

    def test_sql_mismatch_evicts_only_own_instance(self):
        """✅ Positive: SQL 变更逐出只发生在自己的实例"""
        a = QueryCache()
        b = QueryCache()
        a.set(1, [{"columns": ["id"], "rows": [(1,)]}], "SELECT OLD")
        b.set(1, [{"columns": ["id"], "rows": [(2,)]}], "SELECT OLD")

        # a 的 SQL 变了 → a 逐出；b 不受影响
        self.assertIsNone(a.get(1, "SELECT NEW"))
        self.assertIsNotNone(b.get(1, "SELECT OLD"))


class TestExecuteReportCacheInjection(unittest.TestCase):
    """execute_report 的 cache 参数：显式注入与默认全局"""

    POOL = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}
    REPORT_CFG = {"prefer_cache": 0, "cache_ttl_hours": 0, "pool_id": 1,
                  "sql_query": "SELECT 1", "name": "报表X", "memo": ""}

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_injected_cache_used_not_global(self, mock_create_conn, mock_exec_q):
        """✅ Positive: 注入独立缓存 → 命中注入实例，全局缓存不受污染"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_create_conn.return_value = MagicMock()

        isolated = QueryCache()
        report._query_cache.clear()

        execute_report(1, "SELECT 1", self.POOL, report=self.REPORT_CFG,
                       cache=isolated)

        # 注入实例被写入
        self.assertIsNotNone(isolated.get(1, "SELECT 1"))
        # 全局缓存未被污染（默认模式写全局，注入模式只写注入实例）
        self.assertIsNone(report._query_cache.get(1, "SELECT 1"))

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_default_uses_global_cache(self, mock_create_conn, mock_exec_q):
        """✅ Positive: 不带 cache 参数 → 使用模块级全局缓存（向后兼容）"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_create_conn.return_value = MagicMock()

        report._query_cache.clear()
        execute_report(1, "SELECT 1", self.POOL, report=self.REPORT_CFG)

        self.assertIsNotNone(report._query_cache.get(1, "SELECT 1"))


if __name__ == "__main__":
    unittest.main()
