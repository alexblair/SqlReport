"""
test_redis_cache.py — redis_cache.py 单元测试

测试策略：
- ReportSnapshot 序列化/反序列化
- compute_config_version / build_snapshot_key / build_lock_key 工具函数
- RedisConnectionManager 使用 mock 避免真实 Redis 依赖
- 全局管理器的 reset 机制
"""

import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

from redis_cache import (
    ReportSnapshot,
    compute_config_version,
    build_snapshot_key,
    build_lock_key,
    RedisConnectionManager,
    get_redis_manager,
    reset_redis_manager,
    redis_available,
)


class TestReportSnapshot(unittest.TestCase):
    """ReportSnapshot 序列化/反序列化测试"""

    def test_to_json_and_from_json(self):
        """to_json 输出 should be 可被 from_json 正确还原（tuple 转 list 是 JSON 正常行为）"""  # noqa: E501
        results = [{"columns": ["id", "name"], "rows": [(1, "Alice"), (2, "Bob")]}]
        ts = time.time()
        snap = ReportSnapshot(results, "SELECT * FROM t", ts, "abc123")
        json_str = snap.to_json()
        restored = ReportSnapshot.from_json(json_str)
        # JSON 序列化会将 tuple 转为 list
        expected_results = [{"columns": ["id", "name"], "rows": [[1, "Alice"], [2, "Bob"]]}]
        self.assertEqual(restored.results, expected_results)
        self.assertEqual(restored.sql_query, "SELECT * FROM t")
        self.assertEqual(restored.updated_at, ts)
        self.assertEqual(restored.config_version, "abc123")

    def test_from_json_empty_array(self):
        """空结果集的反序列化"""
        json_str = '{"results":[],"sql_query":"","updated_at":0.0,"config_version":""}'
        snap = ReportSnapshot.from_json(json_str)
        self.assertEqual(snap.results, [])
        self.assertEqual(snap.sql_query, "")

    def test_to_json_unicode(self):
        """中文内容序列化/反序列化正常"""
        results = [{"columns": ["name"], "rows": [("张三",)]}]
        snap = ReportSnapshot(results, "SELECT 1", 100.0, "v1")
        restored = ReportSnapshot.from_json(snap.to_json())
        self.assertEqual(restored.results[0]["rows"][0][0], "张三")


class TestKeyFunctions(unittest.TestCase):
    """工具函数测试"""

    def test_compute_config_version_deterministic(self):
        """同一 SQL + pool_id 应产生相同版本号"""
        v1 = compute_config_version("SELECT * FROM t", 1)
        v2 = compute_config_version("SELECT * FROM t", 1)
        self.assertEqual(v1, v2)

    def test_compute_config_version_different_sql(self):
        """不同 SQL 应产生不同版本号"""
        v1 = compute_config_version("SELECT * FROM t", 1)
        v2 = compute_config_version("SELECT * FROM t WHERE id=1", 1)
        self.assertNotEqual(v1, v2)

    def test_compute_config_version_different_pool(self):
        """不同 pool_id 应产生不同版本号"""
        v1 = compute_config_version("SELECT * FROM t", 1)
        v2 = compute_config_version("SELECT * FROM t", 2)
        self.assertNotEqual(v1, v2)

    def test_build_snapshot_key(self):
        """快照 key 格式正确"""
        key = build_snapshot_key("sr", 42, "abc123")
        self.assertEqual(key, "sr:snapshot:42:abc123")

    def test_build_lock_key(self):
        """锁 key 格式正确"""
        key = build_lock_key("sr", 42, "abc123")
        self.assertEqual(key, "sr:snapshot:42:abc123:lock")


class TestRedisConnectionManager(unittest.TestCase):
    """RedisConnectionManager 测试（mock Redis 客户端）"""

    def setUp(self):
        self.config = {
            "enable": True,
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "password": "",
            "key_prefix": "sr",
            "default_ttl_hours": 24,
            "socket_timeout": 5,
        }

    def tearDown(self):
        reset_redis_manager()

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_connect_success(self, mock_create):
        """连接成功时 available 应为 True"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        ok = mgr.connect()
        self.assertTrue(ok)
        self.assertTrue(mgr.available)
        mock_client.ping.assert_called_once()

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_connect_failure(self, mock_create):
        """连接失败时 available 应为 False"""
        mock_create.side_effect = Exception("Connection refused")
        mgr = RedisConnectionManager(self.config)
        ok = mgr.connect()
        self.assertFalse(ok)
        self.assertFalse(mgr.available)
        self.assertIsNone(mgr.client)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_snapshot_set_and_get(self, mock_create):
        """set_snapshot 后再 get_snapshot 应还原"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        snap_data = '{"results": [], "sql_query": "SELECT 1", "updated_at": 100.0, "config_version": "v1"}'
        # get 返回模拟数据
        type(mock_client).decode_responses = PropertyMock(return_value=True)
        mock_client.get.return_value = snap_data

        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        # set
        snap = ReportSnapshot([], "SELECT 1", 100.0, "v1")
        mgr.set_snapshot("sr:snapshot:1:v1", snap, ttl_hours=0)
        mock_client.set.assert_called_once()

        # get
        result = mgr.get_snapshot("sr:snapshot:1:v1")
        self.assertIsNotNone(result)
        self.assertEqual(result.sql_query, "SELECT 1")
        mock_client.get.assert_called_with("sr:snapshot:1:v1")

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_set_snapshot_with_ttl(self, mock_create):
        """设置 TTL 时使用 setex"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        snap = ReportSnapshot([], "SELECT 1", 100.0, "v1")
        mgr.set_snapshot("sr:s:1:v1", snap, ttl_hours=2)
        # 2小时 = 7200 秒
        mock_client.setex.assert_called_once_with("sr:s:1:v1", 7200, snap.to_json())

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_acquire_and_release_lock(self, mock_create):
        """获取锁 → 释放锁"""
        mock_client = MagicMock()
        mock_client.setnx.return_value = True
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        ok = mgr.acquire_lock("my:lock")
        self.assertTrue(ok)
        mock_client.setnx.assert_called_with("my:lock", "1")
        mock_client.expire.assert_called_with("my:lock", 30)

        mgr.release_lock("my:lock")
        mock_client.delete.assert_called_with("my:lock")

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_acquire_lock_failure(self, mock_create):
        """锁已被占用时 acquire_lock 返回 False"""
        mock_client = MagicMock()
        mock_client.setnx.return_value = False
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        ok = mgr.acquire_lock("my:lock")
        self.assertFalse(ok)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_get_snapshot_not_found(self, mock_create):
        """不存在的 key 返回 None"""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        result = mgr.get_snapshot("nonexistent")
        self.assertIsNone(result)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_redis_unavailable_returns_none(self, mock_create):
        """Redis 不可用时 get_snapshot 返回 None"""
        mock_create.side_effect = Exception("No connection")
        mgr = RedisConnectionManager(self.config)
        mgr.connect()
        self.assertFalse(mgr.available)

        result = mgr.get_snapshot("any")
        self.assertIsNone(result)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_wait_for_lock_timeout(self, mock_create):
        """等待锁超时"""
        mock_client = MagicMock()
        mock_client.setnx.return_value = False  # 锁一直无法获取
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()

        start = time.time()
        ok = mgr.wait_for_lock("my:lock", max_wait=1)
        elapsed = time.time() - start
        self.assertFalse(ok)
        # 应该在约 1 秒后超时
        self.assertGreaterEqual(elapsed, 0.9)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_close(self, mock_create):
        """close 后 available 应为 False"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()
        self.assertTrue(mgr.available)
        mgr.close()
        self.assertFalse(mgr.available)
        mock_client.close.assert_called_once()

    @patch("redis_cache._HEALTH_CHECK_INTERVAL", 0.01)  # 跳过 15s 等待
    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_health_check_marks_unavailable(self, mock_create):
        """健康检查检测到 Redis 不可用时应标记 available=False"""
        import threading
        mock_client = MagicMock()
        # 第一次 ping 成功（connect），第二次 ping 失败（health check）
        mock_client.ping.side_effect = [None, Exception("Timeout")]
        mock_create.return_value = mock_client
        mgr = RedisConnectionManager(self.config)
        mgr.connect()
        self.assertTrue(mgr.available)

        # 后台启动健康检查线程，50ms 后停止
        mgr.start_health_check()
        timer = threading.Timer(0.05, lambda: setattr(mgr, '_stop_health', True))
        timer.start()
        timer.join()
        # 给健康检查线程时间完成一次迭代
        import time
        time.sleep(0.02)
        mgr._health_thread.join(timeout=1)
        self.assertFalse(mgr.available)


class TestGlobalManager(unittest.TestCase):
    """全局管理器测试（patch redis_cache.get_redis_config）"""

    def setUp(self):
        self.config_patcher = patch(
            "redis_cache.get_redis_config",
            return_value={
                "enable": False,
                "host": "127.0.0.1",
                "port": 6379,
                "db": 0,
                "password": "",
                "key_prefix": "sr",
                "default_ttl_hours": 24,
                "socket_timeout": 5,
            },
        )
        self.mock_redis_cfg = self.config_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        reset_redis_manager()

    def test_redis_disabled_by_default(self):
        """未启用 Redis 时 get_redis_manager 返回 None"""
        mgr = get_redis_manager()
        self.assertIsNone(mgr)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_redis_enabled_connects(self, mock_create):
        """启用 Redis 时 get_redis_manager 创建连接"""
        self.mock_redis_cfg.return_value = {
            "enable": True,
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "password": "",
            "key_prefix": "sr",
            "default_ttl_hours": 24,
            "socket_timeout": 5,
        }
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mgr = get_redis_manager()
        self.assertIsNotNone(mgr)
        self.assertTrue(mgr.available)

    def test_reset_redis_manager(self):
        """reset_redis_manager 应清除全局状态"""
        get_redis_manager()  # 此时为 None
        reset_redis_manager()
        self.assertIsNone(get_redis_manager())


class TestReportSnapshotEdgeCases(unittest.TestCase):
    """ReportSnapshot 边界情况测试"""

    def test_large_data(self):
        """大数据量的序列化/反序列化（tuple 转 list 是 JSON 正常行为）"""
        rows = [(i, f"name_{i}") for i in range(1000)]
        results = [{"columns": ["id", "name"], "rows": rows}]
        snap = ReportSnapshot(results, "SELECT * FROM t", 123.0, "v1")
        restored = ReportSnapshot.from_json(snap.to_json())
        self.assertEqual(len(restored.results[0]["rows"]), 1000)
        self.assertEqual(restored.results[0]["rows"][500][1], "name_500")

    def test_special_chars_in_sql(self):
        """SQL 中的特殊字符（引号、换行）序列化正常"""
        sql = "SELECT * FROM t WHERE name = \"O'Brien\" AND id IN (1,2)\n-- comment"
        snap = ReportSnapshot([], sql, 0.0, "v1")
        restored = ReportSnapshot.from_json(snap.to_json())
        self.assertEqual(restored.sql_query, sql)

    def test_none_config_version(self):
        """config_version 为空字符串也正常"""
        snap = ReportSnapshot([], "", 0.0, "")
        restored = ReportSnapshot.from_json(snap.to_json())
        self.assertEqual(restored.config_version, "")


if __name__ == "__main__":
    unittest.main()
