"""
test_base.py — 测试基类与工厂函数

提供可复用的测试基类和工厂函数，消除测试文件中重复的 SQLite :memory: 连接创建、
engine patcher 管理和建表代码。

使用方法：
    from test_base import BaseConfigTest, BaseReportTest

    class TestMyFeature(BaseConfigTest):
        def test_something(self):
            # self.conn 已可用，engine 已 patch
            ...
"""

import unittest
from unittest.mock import patch
import sqlite3


# ---------------------------------------------------------------------------
# SQL 常量（与 db.py::_SQLITE_SCHEMA 一致，避免循环依赖）
#
# 注意：这些常量不依赖 db 模块，确保 test_base 作为独立的测试工具模块
# 可以被任何测试文件安全 import，不会引起循环导入。
# ---------------------------------------------------------------------------

_SQL_CREATE_CONNECTION_POOLS = """CREATE TABLE IF NOT EXISTS connection_pools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    host        TEXT    NOT NULL,
    port        INTEGER NOT NULL DEFAULT 3306,
    user        TEXT    NOT NULL,
    password    TEXT    NOT NULL,
    database    TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
)"""

_SQL_CREATE_USERS = """CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    UNIQUE NOT NULL,
    password_hash   TEXT    NOT NULL
)"""

_SQL_CREATE_REPORT_CATEGORIES = """CREATE TABLE IF NOT EXISTS report_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    parent_id   INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
)"""

_SQL_CREATE_REPORT_CONFIGS = """CREATE TABLE IF NOT EXISTS report_configs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    UNIQUE NOT NULL,
    sql_query          TEXT    NOT NULL,
    default_page_size  INTEGER NOT NULL DEFAULT 20,
    pool_id            INTEGER,
    category_id        INTEGER,
    memo               TEXT,
    result_names       TEXT DEFAULT '',
    prefer_cache       INTEGER NOT NULL DEFAULT 1,
    cache_ttl_hours    INTEGER NOT NULL DEFAULT 0,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
)"""

_SQL_CREATE_SESSIONS = """CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created_at REAL NOT NULL
)"""

_SQL_CREATE_API_ENDPOINTS = """CREATE TABLE IF NOT EXISTS api_endpoints (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id        INTEGER NOT NULL,
    name             TEXT    NOT NULL,
    url_path         TEXT    UNIQUE NOT NULL,
    output_format    TEXT    NOT NULL DEFAULT 'json',
    columns          TEXT,
    filters          TEXT,
    sorts            TEXT,
    row_limit        INTEGER DEFAULT 0,
    api_key          TEXT,
    allowed_origins  TEXT,
    enabled          INTEGER NOT NULL DEFAULT 1,
    result_mode      TEXT    NOT NULL DEFAULT 'single',
    result_index     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
)"""


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def make_config_db(memory: bool = True) -> sqlite3.Connection:
    """
    创建测试用 config_db 连接（SQLite :memory:）。

    自动设置 row_factory = sqlite3.Row 并启用外键约束。
    所有测试应优先使用该工厂函数创建连接，确保行为一致性。

    Args:
        memory: 保留参数，当前仅支持 :memory: 模式。

    Returns:
        配置好的 sqlite3.Connection 对象，已设置 row_factory 和 PRAGMA。
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_test_db(conn: sqlite3.Connection) -> None:
    """
    在 SQLite 连接上初始化所有测试表结构。

    创建 connection_pools、users、report_categories、report_configs、sessions、
    api_endpoints 六张配置表。DDL 与 db.py::_SQLITE_SCHEMA 保持一致，但不依赖 db 模块，
    避免循环依赖。

    幂等设计：使用 IF NOT EXISTS，可安全重复调用。
    FK 依赖顺序：connection_pools / report_categories 先于 report_configs。

    Args:
        conn: 由 make_config_db() 创建的 SQLite 连接。
    """
    conn.execute(_SQL_CREATE_CONNECTION_POOLS)
    conn.execute(_SQL_CREATE_USERS)
    conn.execute(_SQL_CREATE_REPORT_CATEGORIES)
    conn.execute(_SQL_CREATE_REPORT_CONFIGS)
    conn.execute(_SQL_CREATE_SESSIONS)
    conn.execute(_SQL_CREATE_API_ENDPOINTS)
    conn.commit()


# ---------------------------------------------------------------------------
# 测试基类
# ---------------------------------------------------------------------------


class BaseConfigTest(unittest.TestCase):
    """
    配置管理测试基类。

    职责：
    - setUp：自动创建 :memory: SQLite 连接、patch db._get_engine 返回 'sqlite3'、
            初始化所有配置表。
    - tearDown：自动停止 patcher、关闭连接。

    使用方式：
        class TestPoolCRUD(BaseConfigTest):
            def test_add_pool(self):
                pid = db.add_pool(self.conn, "mypool", ...)
                ...
    """

    def setUp(self):
        """创建测试连接、patch engine、初始化表结构。"""
        self.conn = make_config_db()
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        init_test_db(self.conn)

    def tearDown(self):
        """停止 engine patcher 并关闭连接。"""
        self.engine_patcher.stop()
        self.conn.close()


class BaseReportTest(BaseConfigTest):
    """
    报表测试基类。

    继承 BaseConfigTest，额外创建一套种子数据：
    - 1 个测试连接池 (self.pool_id)
    - 1 个测试分类 (self.category_id)
    - 1 个测试报表 (self.report_id)

    子类可直接通过上述实例属性引用种子数据的 ID，无需重复插入。
    setUp/tearDown 确保每个测试方法获得干净的数据库环境。
    """

    def setUp(self):
        """创建基础环境后插入连接池、分类、报表种子数据。"""
        super().setUp()

        # 添加测试连接池
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("testpool", "127.0.0.1", 3306, "root", "secret", "testdb", 1),
        )
        self.pool_id = 1

        # 添加测试分类
        self.conn.execute(
            "INSERT INTO report_categories (name, sort_order) VALUES (?,?)",
            ("测试分类", 1),
        )
        self.category_id = 1

        # 添加测试报表（引用上述连接池和分类）
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,category_id,memo,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("测试报表", "SELECT * FROM test_table", 20, self.pool_id, self.category_id, "测试备注", 1, 0, 1),
        )
        self.report_id = 1
        self.conn.commit()
