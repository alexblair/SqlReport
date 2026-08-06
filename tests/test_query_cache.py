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

import redis_cache
import report
from report import QueryCache, execute_report


REDIS_REPORT_CFG = {"prefer_cache": 1, "cache_ttl_hours": 0, "pool_id": 1,
                    "sql_query": "SELECT 1", "name": "报表R", "memo": ""}


def _make_redis_mgr():
    """构造可用的 Redis 管理器 mock。"""
    mgr = MagicMock()
    mgr.key_prefix = "sr"
    return mgr


def _make_snapshot(rows):
    return redis_cache.ReportSnapshot(
        [{"columns": ["id"], "rows": rows}], "SELECT 1", 100.0, "v1")


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


# ---------------------------------------------------------------------------
# 缺口10：Redis 锁竞争双检查（等锁后重读快照，不重复查 MySQL）
# ---------------------------------------------------------------------------


class TestExecuteReportRedisLockContention(unittest.TestCase):
    """execute_report 的 Redis 重建锁竞争路径。"""

    POOL = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}

    def setUp(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_waiter_rechecks_snapshot_after_lock(self, mock_conn, mock_exec,
                                                 mock_avail, mock_mgr):
        """获取锁失败 → 等待成功 → 双检查命中快照 → MySQL 不再执行"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.side_effect = [None, _make_snapshot([(7,)])]
        mgr.acquire_lock.return_value = False   # 首次拿不到锁
        mgr.wait_for_lock.return_value = True   # 等待后拿到锁
        mock_mgr.return_value = mgr

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        self.assertEqual(result.results[0]["rows"], [(7,)])
        mock_exec.assert_not_called()           # 双检查命中 → 未查 MySQL
        mock_conn.assert_not_called()
        mgr.acquire_lock.assert_called_once()
        mgr.wait_for_lock.assert_called_once()
        self.assertEqual(mgr.get_snapshot.call_count, 2)  # 初检 + 双检查
        mgr.release_lock.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_waiter_timeout_falls_back_to_mysql(self, mock_conn, mock_exec,
                                                mock_avail, mock_mgr):
        """等待锁超时且双检查无快照 → 直查 MySQL，结果正常"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.side_effect = [None, None]   # 初检 miss + 双检查 miss
        mgr.acquire_lock.return_value = False
        mgr.wait_for_lock.return_value = False        # 等待超时
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(3,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        self.assertEqual(result.results[0]["rows"], [(3,)])
        mock_exec.assert_called_once()
        # 真实行为：等待锁超时后直查 MySQL 成功，并写入 Redis 快照 → source=redis
        self.assertEqual(result.cache_info["source"], "redis")


# ---------------------------------------------------------------------------
# 缺口11：Redis 过期兜底（TTL 过期后重新执行 / MySQL 失败读旧快照）
# ---------------------------------------------------------------------------


class TestExecuteReportRedisFallback(unittest.TestCase):
    """TTL 过期重建与 MySQL 失败时的过期快照兜底。"""

    POOL = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}

    def setUp(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_ttl_expired_rebuilds_from_mysql(self, mock_conn, mock_exec,
                                             mock_avail, mock_mgr):
        """TTL 过期（get 返回 None）→ 重新执行 MySQL 并重建快照"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.return_value = None        # 快照已过期/不存在
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(5,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        mock_exec.assert_called_once()
        mgr.set_snapshot.assert_called_once()       # 重建写入 Redis
        self.assertEqual(result.results[0]["rows"], [(5,)])
        self.assertEqual(result.cache_info["source"], "redis")

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_mysql_failure_serves_expired_snapshot(self, mock_conn, mock_exec,
                                                   mock_avail, mock_mgr):
        """MySQL 失败 → 兜底读过期 Redis 快照（redis_fallback）"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.side_effect = [None, _make_snapshot([(9,)])]
        mock_mgr.return_value = mgr
        mock_exec.side_effect = Exception("数据库连接失败")

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        self.assertEqual(result.results[0]["rows"], [(9,)])
        self.assertEqual(result.cache_info["source"], "redis_fallback")
        self.assertFalse(result.cache_info["fresh"])

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_mysql_failure_without_snapshot_raises(self, mock_conn, mock_exec,
                                                   mock_avail, mock_mgr):
        """MySQL 失败且无任何快照兜底 → 异常向上传播（不吞错）"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.side_effect = Exception("数据库连接失败")

        with self.assertRaises(Exception) as ctx:
            report.execute_report(1, "SELECT 1", self.POOL,
                                  report=REDIS_REPORT_CFG)
        self.assertIn("数据库连接失败", str(ctx.exception))


# ---------------------------------------------------------------------------
# 缺口13：Redis 方法失败降级（get/set 异常回退进程缓存或直查 DB）
# ---------------------------------------------------------------------------


class TestExecuteReportRedisDegradation(unittest.TestCase):
    """Redis 各方法异常时 execute_report 的降级行为。"""

    POOL = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}

    def setUp(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_get_failure_degrades_to_mysql(self, mock_conn, mock_exec,
                                           mock_avail, mock_mgr):
        """get_snapshot miss（管理器降级返回 None）→ 直查 MySQL 成功并重建快照"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.return_value = None
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(2,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        self.assertEqual(result.results[0]["rows"], [(2,)])
        # 真实行为：MySQL 成功后写入 Redis 快照 → source=redis（fresh 快照）
        self.assertEqual(result.cache_info["source"], "redis")
        self.assertTrue(result.cache_info["fresh"])
        mock_exec.assert_called_once()
        mgr.set_snapshot.assert_called_once()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_lock_failure_degrades_to_mysql(self, mock_conn, mock_exec,
                                            mock_avail, mock_mgr):
        """acquire_lock/wait_for_lock 均失败（锁不可用）→ 直查 MySQL 正常返回"""
        mgr = _make_redis_mgr()
        mgr.get_snapshot.return_value = None
        mgr.acquire_lock.return_value = False
        mgr.wait_for_lock.return_value = False
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(4,)]}]
        mock_conn.return_value = MagicMock()

        result = report.execute_report(1, "SELECT 1", self.POOL,
                                       report=REDIS_REPORT_CFG)

        self.assertEqual(result.results[0]["rows"], [(4,)])
        mock_exec.assert_called_once()

    def test_process_cache_hit_skips_redis_and_mysql(self):
        """进程缓存命中 → 不再触碰 Redis 与 MySQL（纯降级路径）"""
        cache = QueryCache()
        cache.set(1, [{"columns": ["id"], "rows": [(6,)]}], "SELECT 1")
        with patch("report.redis_cache.redis_available",
                   return_value=True) as m_avail, \
                patch("report.db.create_mysql_connection") as m_conn, \
                patch("report.db.execute_mysql_query") as m_exec:
            result = report.execute_report(1, "SELECT 1", self.POOL,
                                           report=REDIS_REPORT_CFG,
                                           cache=cache)
        m_conn.assert_not_called()
        m_exec.assert_not_called()
        self.assertEqual(result.results[0]["rows"], [(6,)])


# ---------------------------------------------------------------------------
# 缺口14：并发 miss 重建（多线程同时 miss 同一报表，结果一致）
# ---------------------------------------------------------------------------


class TestExecuteReportConcurrentMiss(unittest.TestCase):
    """多线程并发 miss 同一报表的重建一致性。"""

    POOL = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}

    def setUp(self):
        report._query_cache.clear()

    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_concurrent_miss_results_consistent(self, mock_conn, mock_exec,
                                                mock_avail, mock_mgr):
        """6 线程同时 miss：双检查保证只查一次 MySQL，所有线程结果一致"""
        n = 6
        mgr = _make_redis_mgr()
        mgr.get_snapshot.side_effect = [None] + [_make_snapshot([(1,)])] * n
        mgr.acquire_lock.side_effect = [True] + [False] * n
        mgr.wait_for_lock.return_value = True
        mock_mgr.return_value = mgr
        mock_exec.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn.return_value = MagicMock()

        barrier = threading.Barrier(n)
        outcomes = []
        errors = []

        def worker():
            barrier.wait()
            try:
                r = report.execute_report(1, "SELECT 1", self.POOL,
                                          report=REDIS_REPORT_CFG)
                outcomes.append(r.results[0]["rows"])
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"并发 miss 不应抛异常: {errors}")
        self.assertEqual(len(outcomes), n)
        self.assertTrue(all(rows == [(1,)] for rows in outcomes),
                        f"所有线程结果必须一致: {outcomes}")
        self.assertEqual(mock_exec.call_count, 1,
                         "锁 + 双检查下 MySQL 应恰好执行一次")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_concurrent_miss_without_redis_consistent(self, mock_conn,
                                                      mock_exec):
        """无 Redis（降级模式）：并发 miss 各自查询，结果一致无异常"""
        n = 4
        mock_exec.return_value = [{"columns": ["id"], "rows": [(8,)]}]
        mock_conn.return_value = MagicMock()

        barrier = threading.Barrier(n)
        outcomes = []
        errors = []

        def worker():
            barrier.wait()
            try:
                r = report.execute_report(
                    1, "SELECT 1", self.POOL,
                    report={"prefer_cache": 0, "cache_ttl_hours": 0,
                            "pool_id": 1, "sql_query": "SELECT 1",
                            "name": "x", "memo": ""})
                outcomes.append(r.results[0]["rows"])
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(outcomes), n)
        self.assertTrue(all(rows == [(8,)] for rows in outcomes))
        self.assertGreaterEqual(mock_exec.call_count, 1)


if __name__ == "__main__":
    unittest.main()
