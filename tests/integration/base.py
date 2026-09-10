"""
base.py — 真实数据库集成测试基座（DEBUG 模式激活时可用）

设计目标（对应「真层测试基座」步骤）：
1. DEBUG 模式未激活（无 app_config.debug.json）时，整层测试 skip；
2. 建表 DDL 直接取自 config_db._get_schema_sql(engine)，消灭 test_base.py
   的硬编码复制（消除 DDL 漂移幻觉）；
3. 提供 SQLite 文件库（临时文件，非 :memory:）与真实 MySQL 测试库两条连接线；
4. MySQL 条目通过 DEBUG 配置 config_db 段显式开启（enable=true 且 engine=mysql）。

连接建立失败（如 MySQL 未启动）时降级为 skip，避免误报失败。
"""

import os
import sqlite3
import tempfile
import unittest

import app_config
import config_db

# 进程内追踪待清理的临时 SQLite 文件库路径（sqlite3.Connection 不可挂属性）
_tmp_db_paths: list[str] = []


def is_debug_mode() -> bool:
    """真层测试视角的 DEBUG 激活判断：仓库根存在 DEBUG 配置文件即可。

    独立于 app_config.is_debug_mode() 的 CONFIG_FILE 叠加条件——测试基建
    （如 test_api_endpoint 模块导入期注入 CONFIG_FILE）不应阻断真层测试；
    真层只关心"开发者在仓库根放了 debug 配置文件"这一事实。
    """
    path = os.environ.get("DEBUG_CONFIG_FILE", app_config.DEFAULT_DEBUG_CONFIG_PATH)
    return os.path.exists(path)


def is_mysql_debug_enabled() -> bool:
    """DEBUG 配置的 config_db 段中是否存在 enable=true 的 mysql 条目。"""
    if not is_debug_mode():
        return False
    raw = app_config.get_config().get("config_db", [])
    if isinstance(raw, dict):
        return raw.get("engine") == "mysql" and raw.get("enable", False)
    return any(e.get("engine") == "mysql" and e.get("enable", False) for e in raw)


def make_real_sqlite_conn(path: str | None = None):
    """创建临时文件 SQLite 连接（真实文件库，非 :memory:）。

    path 为空时创建新临时文件并登记进 _tmp_db_paths；传入 path 时连接既有
    文件（不重复登记，调用方负责清理）。
    返回 _SqliteTxAdapter 包装（真实转发到 sqlite3.Connection），补齐
    begin/start_transaction 接口使 execute_mysql_query 事务路径可跑。
    """
    if path is None:
        fd, path = tempfile.mkstemp(prefix="sr-real-sqlite-", suffix=".db")
        os.close(fd)
        _tmp_db_paths.append(path)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return _SqliteTxAdapter(conn)


class _SqliteTxAdapter:
    """真实转发到 sqlite3.Connection，补齐事务接口的轻适配层。

    不伪造数据/行为：所有 execute/cursor/commit/rollback 均真实转发到底层
    sqlite 文件库连接，仅新增 begin/start_transaction（sqlite3 无该方法，
    但 execute_mysql_query 的 transactional 路径需要）。
    """

    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        self._conn.execute("BEGIN")

    def start_transaction(self):
        self._conn.execute("BEGIN")

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executescript(self, *a, **kw):
        return self._conn.executescript(*a, **kw)

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _cleanup_tmp_db(path: str | None) -> None:
    """删除临时 SQLite 文件库及其 WAL/SHM 附属文件。"""
    if not path:
        return
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass


def _cleanup_tmp_db(path: str) -> None:
    """删除临时 SQLite 文件库及其 WAL/SHM 附属文件。"""
    if not path:
        return
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass


def make_real_mysql_conn():
    """创建真实 MySQL 测试库连接（经 query_executor 的包装层）。

    直接使用 DEBUG 配置中激活的 mysql 条目连接，真实走驱动。
    """
    import db as _db
    return _db._connect_mysql_config()


class RealDbBase(unittest.TestCase):
    """真实数据库集成测试基类。

    子类设置 engine = "sqlite3" / "mysql"；未激活 DEBUG 模式时 setUpClass 抛
    SkipTest，整个测试类跳过。conn 由子类 setUpClass 建立。
    """

    engine = None

    @classmethod
    def setUpClass(cls):
        if not is_debug_mode():
            raise unittest.SkipTest(
                "DEBUG 模式未激活（缺少 app_config.debug.json），跳过真实库集成测试")
        if cls.engine == "mysql":
            if not is_mysql_debug_enabled():
                raise unittest.SkipTest(
                    "DEBUG 配置未启用 mysql 引擎（config_db 段无 enable=true 的 "
                    "mysql 条目），跳过 MySQL 真层测试")
            try:
                cls.conn = make_real_mysql_conn()
            except Exception as e:
                raise unittest.SkipTest(f"MySQL 测试库不可用，跳过真层测试: {e}")
        else:
            cls.conn = make_real_sqlite_conn()
            cls._sqlite_db_path = _tmp_db_paths.pop()
        cls.init_schema(cls.conn)
        cls._created_pool_ids = set()

    @classmethod
    def init_schema(cls, conn) -> None:
        """初始化真实库表结构（含迁移），引擎以 cls.engine 为准。

        不依赖全局 _get_engine()：sqlite 测试类在 debug 配置指向 mysql 时
        仍应能对 sqlite 文件库建表。迁移与 DDL 均真实执行于目标库。
        """
        import db as _db
        from unittest.mock import patch as _patch
        with _patch.object(_db, "_get_engine", return_value=cls.engine):
            config_db.init_db(conn)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None) is not None:
            try:
                cls.conn.close()
            except Exception:
                pass
        if cls.engine != "mysql":
            _cleanup_tmp_db(getattr(cls, "_sqlite_db_path", None))

    # ------------------------------------------------------------------
    # 公共断言工具
    # ------------------------------------------------------------------

    def assert_row_count(self, table: str, expected: int) -> None:
        """断言真实表行数（引擎无关）。"""
        row = self.conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
        self.assertEqual(row["cnt"], expected)

    def cleanup_table(self, table: str) -> None:
        """清空测试表（保证用例间隔离）。"""
        self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()
