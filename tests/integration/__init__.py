"""
tests/integration/__init__.py — 真实数据库集成测试包

仅当 DEBUG 模式激活（存在 app_config.debug.json）时运行，否则整层 skip。
覆盖 SQLite 文件库与真实 MySQL 测试库的方言/驱动真实行为。
"""

from .base import (
    RealDbBase,
    make_real_sqlite_conn,
    make_real_mysql_conn,
    is_mysql_debug_enabled,
)

__all__ = [
    "RealDbBase",
    "make_real_sqlite_conn",
    "make_real_mysql_conn",
    "is_mysql_debug_enabled",
]
