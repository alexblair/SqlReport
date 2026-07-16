"""
context.py — 应用上下文数据容器

职责：
提供 AppContext 纯数据容器，持有所有共享依赖（config_db 连接、Redis 管理器、
查询缓存、会话存储等）。不包含生命周期或初始化逻辑。

设计原则：
- 纯数据容器（@dataclass），无生命周期方法
- 所有字段可选，调用方按需赋值
- 对可变类型使用 field(default_factory=...) 避免实例间共享
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppContext:
    """应用上下文，持有所有共享依赖。

    Attributes:
        config_db: 配置数据库连接（SQLite Connection 或 MySQL 连接）。
        redis_manager: Redis 快照管理器实例，为 None 表示 Redis 不可用。
        query_cache: 报表查询结果缓存（report_id → CachedResult）。
        sessions: 用户会话存储（token → username）。
    """

    config_db: Any = None
    redis_manager: Any = None
    query_cache: dict = field(default_factory=dict)
    sessions: dict = field(default_factory=dict)
