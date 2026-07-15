"""
redis_cache.py — Redis 缓存层

职责：
1. 连接管理：根据 app_config.json 中的 redis 配置段创建/销毁连接
2. 健康检查：定时轮询 Redis 可用性
3. 快照锁：基于 SETNX 的分布式锁，防止同一报表同时被多个请求重建
4. 报表快照读写：将全量结果集序列化为 JSON 存入 Redis

设计：
- 全局 RedisConnectionManager 维护连接和健康状态
- 全局 _redis_manager 实例由模块加载时初始化
- 上层通过 redis_available() / get_redis_manager() 获取状态和实例
- 调用方需先检查 redis_available()，不可用时走降级逻辑
"""

import hashlib
import json
import threading
import time
from typing import Any, Optional

from app_config import get_redis_config

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_LOCK_TIMEOUT = 30       # 锁自动释放时间（秒）
_LOCK_RETRY_INTERVAL = 1 # 锁等待重试间隔（秒）
_LOCK_MAX_WAIT = 60      # 等待锁的最大时间（秒）
_HEALTH_CHECK_INTERVAL = 15  # 健康检查间隔（秒）

# ---------------------------------------------------------------------------
# 快照数据实体
# ---------------------------------------------------------------------------


class ReportSnapshot:
    """Redis 中存储的报表快照实体。

    包含全部结果集、执行时间戳、SQL 原文、配置版本号。
    """

    __slots__ = ("results", "sql_query", "updated_at", "config_version")

    def __init__(self, results: list[dict], sql_query: str,
                 updated_at: float, config_version: str):
        self.results = results
        self.sql_query = sql_query
        self.updated_at = updated_at
        self.config_version = config_version

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps({
            "results": self.results,
            "sql_query": self.sql_query,
            "updated_at": self.updated_at,
            "config_version": self.config_version,
        }, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, data: str) -> "ReportSnapshot":
        """从 JSON 字符串反序列化。"""
        obj = json.loads(data)
        return cls(
            results=obj["results"],
            sql_query=obj["sql_query"],
            updated_at=obj["updated_at"],
            config_version=obj["config_version"],
        )


# ---------------------------------------------------------------------------
# 配置版本计算
# ---------------------------------------------------------------------------


def compute_config_version(sql_query: str, pool_id: Optional[int]) -> str:
    """计算报表的配置版本号（MD5 of sql + pool_id）。

    配置变化时版本号变化，旧快照自然淘汰。
    """
    raw = f"{sql_query}|{pool_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_snapshot_key(prefix: str, report_id: int,
                       config_version: str) -> str:
    """构建 Redis 中存储报表快照的 key。"""
    return f"{prefix}:snapshot:{report_id}:{config_version}"


def build_lock_key(prefix: str, report_id: int,
                   config_version: str) -> str:
    """构建 Redis 中用于重建锁的 key。"""
    return f"{prefix}:snapshot:{report_id}:{config_version}:lock"


# ---------------------------------------------------------------------------
# Redis 连接管理器
# ---------------------------------------------------------------------------


class RedisConnectionManager:
    """Redis 连接管理器，包含健康检查。"""

    def __init__(self, config: dict):
        self._config = config
        self._client: Any = None
        self._available: bool = False
        self._lock = threading.Lock()
        self._health_thread: Optional[threading.Thread] = None
        self._stop_health: bool = False

    # ---- 连接 ----

    def _create_client(self):
        """创建 Redis 连接客户端。"""
        try:
            import redis
        except ImportError:
            raise RuntimeError("redis 模块未安装，请执行: pip install redis")

        host = self._config.get("host", "127.0.0.1")
        port = self._config.get("port", 6379)
        db = self._config.get("db", 0)
        password = self._config.get("password") or None
        socket_timeout = self._config.get("socket_timeout", 5)

        return redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            decode_responses=True,
        )

    def connect(self) -> bool:
        """建立 Redis 连接并执行健康检查，返回是否可用。"""
        try:
            self._client = self._create_client()
            self._client.ping()
            self._available = True
        except Exception:
            self._client = None
            self._available = False
        return self._available

    @property
    def available(self) -> bool:
        """Redis 是否可用。"""
        return self._available

    @property
    def client(self):
        """获取 Redis 客户端。"""
        return self._client

    # ---- 健康检查 ----

    def _health_check_loop(self):
        """后台健康检查线程。"""
        while not self._stop_health:
            time.sleep(_HEALTH_CHECK_INTERVAL)
            try:
                if self._client:
                    self._client.ping()
                    self._available = True
                else:
                    self._available = False
            except Exception:
                self._available = False

    def start_health_check(self):
        """启动后台健康检查线程。"""
        if self._health_thread is not None and self._health_thread.is_alive():
            return
        self._stop_health = False
        self._health_thread = threading.Thread(
            target=self._health_check_loop, daemon=True
        )
        self._health_thread.start()

    def stop_health_check(self):
        """停止后台健康检查线程。"""
        self._stop_health = True
        self._health_thread = None

    # ---- 快照锁 ----

    def acquire_lock(self, lock_key: str,
                     timeout: int = _LOCK_TIMEOUT) -> bool:
        """尝试获取快照重建锁（SETNX）。"""
        if not self._available or not self._client:
            return False
        try:
            ok = self._client.setnx(lock_key, "1")
            if ok:
                self._client.expire(lock_key, timeout)
            return bool(ok)
        except Exception:
            return False

    def release_lock(self, lock_key: str):
        """释放快照重建锁。"""
        if not self._available or not self._client:
            return
        try:
            self._client.delete(lock_key)
        except Exception:
            pass

    def wait_for_lock(self, lock_key: str, max_wait: int = _LOCK_MAX_WAIT) -> bool:
        """等待锁释放，轮询直到获取锁或超时。"""
        start = time.time()
        while time.time() - start < max_wait:
            if self.acquire_lock(lock_key):
                return True
            time.sleep(_LOCK_RETRY_INTERVAL)
        return False

    # ---- 快照读写 ----

    def get_snapshot(self, key: str) -> Optional[ReportSnapshot]:
        """从 Redis 读取报表快照。"""
        if not self._available or not self._client:
            return None
        try:
            data = self._client.get(key)
            if data is None:
                return None
            return ReportSnapshot.from_json(data)
        except Exception:
            return None

    def set_snapshot(self, key: str, snapshot: ReportSnapshot,
                     ttl_hours: int = 0):
        """将报表快照写入 Redis。

        ttl_hours: 过期时间（小时），0=永不过期。
        """
        if not self._available or not self._client:
            return
        try:
            data = snapshot.to_json()
            if ttl_hours > 0:
                self._client.setex(key, ttl_hours * 3600, data)
            else:
                self._client.set(key, data)
        except Exception:
            pass

    def delete_snapshot(self, key: str):
        """从 Redis 删除报表快照。"""
        if not self._available or not self._client:
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def scan_snapshots(self, prefix: str, report_id: int) -> list[str]:
        """SCAN 匹配某报表全部快照 key（跨配置版本）。"""
        if not self._available or not self._client:
            return []
        pattern = f"{prefix}:snapshot:{report_id}:*"
        try:
            cursor = 0
            keys = []
            while True:
                cursor, batch = self._client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                keys.extend(batch)
                if cursor == 0:
                    break
            return keys
        except Exception:
            return []

    def set_expiration(self, key: str, ttl_hours: int):
        """设置 key 的过期时间（小时）。0=永久（PERSIST）。"""
        if not self._available or not self._client:
            return
        try:
            if ttl_hours > 0:
                self._client.expire(key, ttl_hours * 3600)
            else:
                self._client.persist(key)
        except Exception:
            pass

    def close(self):
        """关闭 Redis 连接。"""
        self.stop_health_check()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._available = False


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_redis_manager: Optional[RedisConnectionManager] = None


def get_redis_manager() -> Optional[RedisConnectionManager]:
    """获取全局 Redis 连接管理器。"""
    global _redis_manager
    if _redis_manager is None:
        config = get_redis_config()
        if config.get("enable", False):
            _redis_manager = RedisConnectionManager(config)
            _redis_manager.connect()
            if _redis_manager.available:
                _redis_manager.start_health_check()
    return _redis_manager


def redis_available() -> bool:
    """Redis 是否可用。"""
    mgr = get_redis_manager()
    return mgr is not None and mgr.available


def reset_redis_manager(config: Optional[dict] = None):
    """重置全局 Redis 连接管理器（测试用）。"""
    global _redis_manager
    if _redis_manager:
        _redis_manager.close()
    if config:
        _redis_manager = RedisConnectionManager(config)
        _redis_manager.connect()
        if _redis_manager.available:
            _redis_manager.start_health_check()
    else:
        _redis_manager = None
