"""
test_redis_cache_extra.py — 补充 redis_cache.py 未覆盖路径的单元测试

覆盖范围：
1. Redis 不可用路径（available=False）
2. 异常日志路径（delete/scan/close 抛异常）
3. wait_for_lock 首次成功
4. set_expiration 完整方法（TTL>0 和 TTL=0）
5. reset_redis_manager(config=...) 传参分支
"""

import logging
import unittest
from unittest.mock import patch, MagicMock

from redis_cache import (
    ReportSnapshot,
    RedisConnectionManager,
    get_redis_manager,
    reset_redis_manager,
    _redis_manager,
)


def _make_config(**overrides):
    """生成默认测试配置。"""
    cfg = {
        "enable": True,
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "password": "",
        "key_prefix": "sr",
        "default_ttl_hours": 24,
        "socket_timeout": 5,
    }
    cfg.update(overrides)
    return cfg


def _make_unavailable_manager():
    """创建 Redis 不可用的 manager（跳过 connect）。"""
    mgr = RedisConnectionManager(_make_config())
    mgr._available = False
    mgr._client = None
    return mgr


def _make_available_manager():
    """创建 Redis 可用的 manager（mock client）。"""
    mgr = RedisConnectionManager(_make_config())
    mock_client = MagicMock()
    mgr._client = mock_client
    mgr._available = True
    return mgr, mock_client


# ---------------------------------------------------------------------------
# 1. Redis 不可用路径
# ---------------------------------------------------------------------------

class TestRedisUnavailablePaths(unittest.TestCase):
    """当 Redis 不可用时，各操作应安全降级。"""

    def test_acquire_lock_returns_false(self):
        """acquire_lock 在 Redis 不可用时返回 False"""
        mgr = _make_unavailable_manager()
        result = mgr.acquire_lock("lock:key")
        self.assertFalse(result)

    def test_release_lock_returns_early(self):
        """release_lock 在 Redis 不可用时直接返回，不抛异常"""
        mgr = _make_unavailable_manager()
        mgr.release_lock("lock:key")  # 无异常即通过

    def test_set_snapshot_returns_early(self):
        """set_snapshot 在 Redis 不可用时直接返回，不抛异常"""
        mgr = _make_unavailable_manager()
        snap = ReportSnapshot([], "SELECT 1", 100.0, "v1")
        mgr.set_snapshot("sr:snapshot:1:v1", snap)  # 无异常即通过

    def test_delete_snapshot_returns_early(self):
        """delete_snapshot 在 Redis 不可用时直接返回，不抛异常"""
        mgr = _make_unavailable_manager()
        mgr.delete_snapshot("sr:snapshot:1:v1")  # 无异常即通过

    def test_scan_snapshots_returns_empty_list(self):
        """scan_snapshots 在 Redis 不可用时返回空列表"""
        mgr = _make_unavailable_manager()
        result = mgr.scan_snapshots("sr", 1)
        self.assertEqual(result, [])

    def test_set_expiration_returns_early(self):
        """set_expiration 在 Redis 不可用时直接返回，不抛异常"""
        mgr = _make_unavailable_manager()
        mgr.set_expiration("sr:snapshot:1:v1", 24)  # 无异常即通过


# ---------------------------------------------------------------------------
# 2. 异常日志路径
# ---------------------------------------------------------------------------

class TestExceptionLoggingPaths(unittest.TestCase):
    """Redis 操作抛异常时应记录对应级别日志，不向上冒泡。"""

    def test_release_lock_logs_error_on_delete_exception(self):
        """release_lock 中 delete 抛异常时记录 error 日志"""
        mgr, mock_client = _make_available_manager()
        mock_client.delete.side_effect = Exception("连接中断")

        with self.assertLogs(level=logging.WARNING) as cm:
            mgr.release_lock("lock:key")
        self.assertTrue(any("release_lock" in msg for msg in cm.output))

    def test_delete_snapshot_logs_warning_on_delete_exception(self):
        """delete_snapshot 中 delete 抛异常时记录 warning 日志"""
        mgr, mock_client = _make_available_manager()
        mock_client.delete.side_effect = Exception("超时")

        with self.assertLogs(level=logging.WARNING) as cm:
            mgr.delete_snapshot("sr:snapshot:1:v1")
        self.assertTrue(any("delete_snapshot" in msg for msg in cm.output))

    def test_scan_snapshots_logs_warning_on_scan_exception(self):
        """scan_snapshots 中 SCAN 抛异常时记录 warning 日志"""
        mgr, mock_client = _make_available_manager()
        mock_client.scan.side_effect = Exception("SCAN 命令不可用")

        with self.assertLogs(level=logging.WARNING) as cm:
            result = mgr.scan_snapshots("sr", 1)
        self.assertEqual(result, [])
        self.assertTrue(any("scan_snapshots" in msg for msg in cm.output))

    def test_close_logs_warning_on_client_close_exception(self):
        """close() 中 client.close() 抛异常时记录 warning 日志"""
        mgr, mock_client = _make_available_manager()
        mock_client.close.side_effect = Exception("管道已断开")

        with self.assertLogs(level=logging.WARNING) as cm:
            mgr.close()
        self.assertTrue(any("close" in msg and "失败" in msg
                            for msg in cm.output))
        self.assertFalse(mgr.available)
        self.assertIsNone(mgr._client)


# ---------------------------------------------------------------------------
# 3. wait_for_lock 首次成功
# ---------------------------------------------------------------------------

class TestWaitForLockFirstSuccess(unittest.TestCase):
    """wait_for_lock 第一次轮询即获取到锁。"""

    def test_wait_for_lock_immediate_success(self):
        """acquire_lock 首次即成功，wait_for_lock 立即返回 True"""
        mgr, mock_client = _make_available_manager()
        mock_client.setnx.return_value = True

        result = mgr.wait_for_lock("lock:key", max_wait=10)
        self.assertTrue(result)
        # 只调用一次 acquire_lock（内部调用一次 setnx）
        self.assertEqual(mock_client.setnx.call_count, 1)


# ---------------------------------------------------------------------------
# 4. set_expiration 完整方法
# ---------------------------------------------------------------------------

class TestSetExpiration(unittest.TestCase):
    """set_expiration 的 TTL>0 和 TTL=0 两种路径。"""

    def test_set_expiration_with_positive_ttl(self):
        """ttl_hours > 0 时调用 expire(key, ttl*3600)"""
        mgr, mock_client = _make_available_manager()
        mgr.set_expiration("sr:snapshot:1:v1", 24)
        mock_client.expire.assert_called_once_with("sr:snapshot:1:v1", 86400)

    def test_set_expiration_with_zero_ttl(self):
        """ttl_hours = 0 时调用 persist(key) 移除过期时间"""
        mgr, mock_client = _make_available_manager()
        mgr.set_expiration("sr:snapshot:1:v1", 0)
        mock_client.persist.assert_called_once_with("sr:snapshot:1:v1")


# ---------------------------------------------------------------------------
# 5. reset_redis_manager(config=...) 传参分支
# ---------------------------------------------------------------------------

class TestResetRedisManagerWithConfig(unittest.TestCase):
    """reset_redis_manager 传入 config 参数时的分支行为。"""

    def setUp(self):
        reset_redis_manager()

    def tearDown(self):
        reset_redis_manager()

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_reset_with_config_creates_new_manager(self, mock_create):
        """传入 config 时创建新 manager 并连接"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        cfg = _make_config()
        reset_redis_manager(config=cfg)

        import redis_cache
        self.assertIsNotNone(redis_cache._redis_manager)
        self.assertTrue(redis_cache._redis_manager.available)

    def test_reset_without_config_sets_none(self):
        """不传 config 时 _redis_manager 设为 None"""
        import redis_cache
        redis_cache._redis_manager = MagicMock()  # 模拟已存在
        reset_redis_manager()
        self.assertIsNone(redis_cache._redis_manager)

    @patch("redis_cache.RedisConnectionManager._create_client")
    def test_reset_with_config_closes_old_manager(self, mock_create):
        """传入 config 时先关闭旧 manager 再创建新 manager"""
        import redis_cache
        old_mgr = MagicMock()
        redis_cache._redis_manager = old_mgr

        mock_create.return_value = MagicMock()
        reset_redis_manager(config=_make_config())

        old_mgr.close.assert_called_once()
        self.assertIsNotNone(redis_cache._redis_manager)


if __name__ == "__main__":
    unittest.main()
