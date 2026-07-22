"""
test_mysql_mock.py — MySQL config_db mock 测试框架

测试策略：
- 使用 @patch 模拟 mysql.connector.connect，避免真实 MySQL 数据库依赖
- 直接实例化 _MySQLRow / _MySQLCursor / _MySQLConnection 进行功能测试
- Mock _get_db_config 控制引擎选择，无需修改 app_config.json
- 使用 MockMySQLMixin 辅助创建模拟连接和游标对象

覆盖范围：
1. _get_engine() 引擎选择逻辑
2. _connect_mysql_config() MySQL 连接创建
3. _MySQLRow 行包装器的 dict-like 和索引访问
4. _MySQLCursor 游标包装器的 fetchone/fetchall/rowcount
5. _MySQLConnection 连接包装器的 execute/commit/close 等基本功能
"""

import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
import mysql.connector

import db
from report import format_cell


# ---------------------------------------------------------------------------
# MockMySQLMixin
# ---------------------------------------------------------------------------

class MockMySQLMixin:
    """
    辅助 Mixin，提供快速创建模拟 MySQL 连接对象的方法。

    用法:
        class MyTest(MockMySQLMixin, unittest.TestCase):
            def test_something(self):
                conn, cursor = self.make_mock_connection()
    """

    @staticmethod
    def make_mock_connection(mock_cursor=None):
        """
        创建模拟的 MySQL 原始连接（mysql.connector.connect 返回值）。

        参数:
            mock_cursor: 指定游标 mock，为 None 时自动创建。

        返回:
            (mock_conn, mock_cursor) 二元组。
        """
        mock_conn = MagicMock()
        cursor = mock_cursor or MagicMock()
        mock_conn.cursor.return_value = cursor
        return mock_conn, cursor

    @staticmethod
    def make_mock_cursor(
        fetchone_return=None,
        fetchall_return=None,
        rowcount=-1,
        lastrowid=0,
        description=None,
    ):
        """
        创建指定返回值的模拟游标。

        参数:
            fetchone_return: fetchone() 的返回值（None 表示不设置）。
            fetchall_return: fetchall() 的返回值。
            rowcount: rowcount 属性值。
            lastrowid: lastrowid 属性值。
            description: cursor.description 属性值。

        返回:
            MagicMock 游标对象。
        """
        mock_cursor = MagicMock()
        mock_cursor.rowcount = rowcount
        mock_cursor.lastrowid = lastrowid
        if fetchone_return is not None:
            mock_cursor.fetchone.return_value = fetchone_return
        if fetchall_return is not None:
            mock_cursor.fetchall.return_value = fetchall_return
        if description is not None:
            mock_cursor.description = description
        return mock_cursor


# ---------------------------------------------------------------------------
# 测试 _get_engine()
# ---------------------------------------------------------------------------

class TestGetEngine(unittest.TestCase):
    """测试 _get_engine() 引擎选择逻辑。"""

    @patch("db._get_db_config")
    def test_engine_returns_mysql_when_configured(self, mock_get_db_config):
        """配置 engine=mysql 时，_get_engine 应返回 'mysql'。"""
        mock_get_db_config.return_value = {"engine": "mysql", "enable": True}
        self.assertEqual(db._get_engine(), "mysql")

    @patch("db._get_db_config")
    def test_engine_returns_sqlite3_by_default(self, mock_get_db_config):
        """默认 engine 应返回 'sqlite3'。"""
        mock_get_db_config.return_value = {"engine": "sqlite3", "path": "config.db"}
        self.assertEqual(db._get_engine(), "sqlite3")

    @patch("db._get_db_config")
    def test_engine_returns_sqlite3_when_engine_missing(self, mock_get_db_config):
        """engine 字段缺失时，应返回 'sqlite3'（get() 默认值）。"""
        mock_get_db_config.return_value = {"path": "config.db"}
        self.assertEqual(db._get_engine(), "sqlite3")


# ---------------------------------------------------------------------------
# 测试 _connect_mysql_config()
# ---------------------------------------------------------------------------

class TestMySQLConnectConfig(unittest.TestCase):
    """测试 _connect_mysql_config() 创建 MySQL config_db 连接。"""

    @patch("db._get_db_config")
    @patch("mysql.connector.connect")
    def test_returns_mysql_connection_wrapper(self, mock_connect, mock_get_db):
        """应返回 _MySQLConnection 包装实例，内部持有原始连接。"""
        mock_get_db.return_value = {
            "engine": "mysql", "host": "127.0.0.1", "port": 3306,
            "user": "root", "password": "p", "database": "test",
        }
        mock_raw = MagicMock()
        mock_connect.return_value = mock_raw

        result = db._connect_mysql_config()

        self.assertIsInstance(result, db._MySQLConnection)
        self.assertIs(result._conn, mock_raw)
        mock_connect.assert_called_once()

    @patch("db._get_db_config")
    @patch("mysql.connector.connect")
    def test_uses_correct_config_parameters(self, mock_connect, mock_get_db):
        """应使用 app_config 中的连接参数调用 mysql.connector.connect。"""
        mock_get_db.return_value = {
            "engine": "mysql", "host": "db.example.com", "port": 3307,
            "user": "admin", "password": "secret", "database": "mydb",
        }
        db._connect_mysql_config()

        kwargs = mock_connect.call_args[1]
        self.assertEqual(kwargs["host"], "db.example.com")
        self.assertEqual(kwargs["port"], 3307)
        self.assertEqual(kwargs["user"], "admin")
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["database"], "mydb")
        self.assertEqual(kwargs["connection_timeout"], 10)
        self.assertEqual(kwargs["charset"], "utf8mb4")

    @patch("db._get_db_config")
    @patch("mysql.connector.connect")
    def test_localhost_converted_to_tcp(self, mock_connect, mock_get_db):
        """host=localhost 时应转为 127.0.0.1 强制走 TCP。"""
        mock_get_db.return_value = {
            "engine": "mysql", "host": "localhost", "port": 3306,
            "user": "root", "password": "", "database": "test",
        }
        db._connect_mysql_config()

        kwargs = mock_connect.call_args[1]
        self.assertEqual(kwargs["host"], "127.0.0.1")

    @patch("db._get_db_config")
    @patch("mysql.connector.connect")
    def test_socket_config_preserves_host(self, mock_connect, mock_get_db):
        """配置了 unix_socket 时，host 应保持 localhost 不变。"""
        mock_get_db.return_value = {
            "engine": "mysql", "host": "localhost", "port": 3306,
            "user": "root", "password": "", "database": "test",
            "socket": "/var/run/mysqld/mysqld.sock",
        }
        db._connect_mysql_config()

        kwargs = mock_connect.call_args[1]
        self.assertEqual(kwargs["host"], "localhost")
        self.assertEqual(kwargs["unix_socket"], "/var/run/mysqld/mysqld.sock")


# ---------------------------------------------------------------------------
# 测试 _MySQLRow
# ---------------------------------------------------------------------------

class TestMySQLRow(unittest.TestCase):
    """测试 _MySQLRow 行包装器的 dict-like 和索引访问。"""

    def setUp(self):
        self.row = db._MySQLRow({"id": 1, "name": "Alice", "age": 30})

    def test_dict_key_access(self):
        """应支持字符串键名访问（dict-like）。"""
        self.assertEqual(self.row["id"], 1)
        self.assertEqual(self.row["name"], "Alice")
        self.assertEqual(self.row["age"], 30)

    def test_index_access(self):
        """应支持整数索引访问（按 keys() 顺序）。"""
        self.assertEqual(self.row[0], 1)
        self.assertEqual(self.row[1], "Alice")
        self.assertEqual(self.row[2], 30)

    def test_slice_access(self):
        """应支持切片访问，返回对应值列表。"""
        self.assertEqual(self.row[0:2], [1, "Alice"])
        self.assertEqual(self.row[1:3], ["Alice", 30])

    def test_len(self):
        """__len__ 应返回字段个数。"""
        self.assertEqual(len(self.row), 3)

    def test_iteration(self):
        """__iter__ 应逐个返回字段值。"""
        self.assertEqual(list(self.row), [1, "Alice", 30])

    def test_keys_method(self):
        """keys() 应返回所有字段名。"""
        self.assertEqual(list(self.row.keys()), ["id", "name", "age"])

    def test_values_method(self):
        """values() 应返回所有字段值。"""
        self.assertEqual(list(self.row.values()), [1, "Alice", 30])

    def test_repr(self):
        """__repr__ 应返回底层 dict 的表示。"""
        self.assertEqual(repr(self.row), repr({"id": 1, "name": "Alice", "age": 30}))

    def test_key_error_on_missing_key(self):
        """访问不存在的键应抛出 KeyError。"""
        with self.assertRaises(KeyError):
            _ = self.row["nonexistent"]

    def test_index_error_on_out_of_range(self):
        """索引越界应抛出 IndexError。"""
        with self.assertRaises(IndexError):
            _ = self.row[100]

    def test_empty_row(self):
        """空数据行应正常处理。"""
        empty = db._MySQLRow({})
        self.assertEqual(len(empty), 0)
        self.assertEqual(list(empty), [])
        self.assertEqual(list(empty.keys()), [])


# ---------------------------------------------------------------------------
# 测试 _MySQLCursor
# ---------------------------------------------------------------------------

class TestMySQLCursor(unittest.TestCase):
    """测试 _MySQLCursor 游标包装器。"""

    def test_fetchone_returns_mysql_row(self):
        """fetchone 应返回 _MySQLRow 包装的行。"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"id": 1, "name": "Alice"}
        cursor = db._MySQLCursor(mock_cursor)

        row = cursor.fetchone()
        self.assertIsInstance(row, db._MySQLRow)
        self.assertEqual(row["name"], "Alice")

    def test_fetchone_returns_none_when_no_data(self):
        """fetchone 无数据时应返回 None。"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        cursor = db._MySQLCursor(mock_cursor)

        self.assertIsNone(cursor.fetchone())

    def test_fetchall_returns_list_of_rows(self):
        """fetchall 应返回 _MySQLRow 列表。"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        cursor = db._MySQLCursor(mock_cursor)

        rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIsInstance(rows[0], db._MySQLRow)
        self.assertIsInstance(rows[1], db._MySQLRow)
        self.assertEqual(rows[1]["name"], "Bob")

    def test_fetchall_returns_empty_list(self):
        """fetchall 无数据时应返回空列表。"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        cursor = db._MySQLCursor(mock_cursor)

        self.assertEqual(cursor.fetchall(), [])

    def test_rowcount_property(self):
        """rowcount 应从底层游标读取。"""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        cursor = db._MySQLCursor(mock_cursor)

        self.assertEqual(cursor.rowcount, 5)

    def test_lastrowid_property(self):
        """lastrowid 应从底层游标读取。"""
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 42
        cursor = db._MySQLCursor(mock_cursor)

        self.assertEqual(cursor.lastrowid, 42)

    def test_rowcount_negative_on_no_data(self):
        """无数据时 rowcount 应为 -1（与 SQLite 行为一致）。"""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = -1
        cursor = db._MySQLCursor(mock_cursor)

        self.assertEqual(cursor.rowcount, -1)

    def test_lastrowid_zero_on_no_insert(self):
        """非 INSERT 操作时 lastrowid 应为 0。"""
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 0
        cursor = db._MySQLCursor(mock_cursor)

        self.assertEqual(cursor.lastrowid, 0)


# ---------------------------------------------------------------------------
# _MySQLConnection 测试基类（处理 mock mysql.connector 模块注入）
# ---------------------------------------------------------------------------

class _MySQLConnectionTestBase(MockMySQLMixin, unittest.TestCase):
    """
    _MySQLConnection 测试基类。

    使用已安装的 mysql.connector（项目唯一外部依赖）的 Error 异常类，
    模拟 _MySQLConnection.execute() 内部 import mysql.connector 后的异常捕获。
    提供已初始化好的 self.conn / self.mock_raw / self.mock_cursor。
    """

    def setUp(self):
        self.mock_raw, self.mock_cursor = self.make_mock_connection()
        self.conn = db._MySQLConnection(self.mock_raw)


# ---------------------------------------------------------------------------
# 测试 _MySQLConnection 基本功能
# ---------------------------------------------------------------------------

class TestMySQLConnection(_MySQLConnectionTestBase):
    """测试 _MySQLConnection 连接包装器的基本功能。"""

    def test_init_stores_raw_connection(self):
        """__init__ 应保存原始连接。"""
        self.assertIs(self.conn._conn, self.mock_raw)

    def test_commit_delegates_to_raw(self):
        """commit 应委托给原始连接的 commit 方法。"""
        self.conn.commit()
        self.mock_raw.commit.assert_called_once_with()

    def test_rollback_delegates_to_raw(self):
        """rollback 应委托给原始连接的 rollback 方法。"""
        self.conn.rollback()
        self.mock_raw.rollback.assert_called_once_with()

    def test_close_delegates_to_raw(self):
        """close 应委托给原始连接的 close 方法。"""
        self.conn.close()
        self.mock_raw.close.assert_called_once_with()

    def test_context_manager_exit_closes(self):
        """with 语句退出时应自动调用 close。"""
        with self.conn as c:
            self.assertIs(c, self.conn)
        self.mock_raw.close.assert_called_once_with()

    def test_context_manager_exit_on_exception(self):
        """with 块内抛出异常时仍应关闭连接。"""
        class TestError(Exception):
            pass
        try:
            with self.conn:
                raise TestError("boom")
        except TestError:
            pass
        self.mock_raw.close.assert_called_once_with()


# ---------------------------------------------------------------------------
# 测试 _MySQLConnection.execute()
# ---------------------------------------------------------------------------

class TestMySQLConnectionExecute(_MySQLConnectionTestBase):
    """测试 _MySQLConnection.execute() 的 SQL 执行逻辑。"""

    def test_execute_returns_mysql_cursor(self):
        """execute 应返回 _MySQLCursor 实例。"""
        result = self.conn.execute("SELECT 1")
        self.assertIsInstance(result, db._MySQLCursor)

    def test_execute_requests_dictionary_cursor(self):
        """execute 应以 dictionary=True 创建游标。"""
        self.conn.execute("SELECT 1")
        self.mock_raw.cursor.assert_called_once_with(dictionary=True, buffered=True)

    def test_execute_with_params_converts_placeholder(self):
        """带参数时，execute 应将 ? 占位符转为 %s。"""
        self.conn.execute("SELECT * FROM t WHERE id = ?", (42,))
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM t WHERE id = %s", (42,)
        )

    def test_execute_without_params_no_conversion(self):
        """无参数时，execute 不应替换 SQL。"""
        self.conn.execute("SELECT * FROM t")
        self.mock_cursor.execute.assert_called_once_with("SELECT * FROM t", ())

    def test_execute_with_empty_params(self):
        """params=() 空元组时，应正常执行。"""
        self.conn.execute("SELECT 1", ())
        self.mock_cursor.execute.assert_called_once_with("SELECT 1", ())

    def test_execute_raises_and_closes_cursor_on_error(self):
        """execute 出错时应关闭游标并重新抛出异常。"""
        self.mock_cursor.execute.side_effect = mysql.connector.Error("DB error")

        with self.assertRaises(mysql.connector.Error):
            self.conn.execute("SELECT * FROM t")

        self.mock_cursor.close.assert_called_once_with()

    def test_execute_does_not_close_cursor_on_success(self):
        """execute 成功时不应关闭游标。"""
        self.conn.execute("SELECT 1")
        self.mock_cursor.close.assert_not_called()

    def test_execute_multiple_times(self):
        """连续多次调用 execute 应分别执行。"""
        self.conn.execute("SELECT 1")
        self.conn.execute("SELECT 2")
        self.assertEqual(self.mock_cursor.execute.call_count, 2)

    def test_execute_complex_sql_with_multiple_params(self):
        """多个 ? 占位符应全部转为 %s。"""
        self.conn.execute(
            "INSERT INTO t (a, b, c) VALUES (?, ?, ?)",
            (1, "two", 3.0),
        )
        self.mock_cursor.execute.assert_called_once_with(
            "INSERT INTO t (a, b, c) VALUES (%s, %s, %s)",
            (1, "two", 3.0),
        )


# ---------------------------------------------------------------------------
# 测试 _MySQLConnection.executescript()
# ---------------------------------------------------------------------------

class TestMySQLConnectionExecutescript(_MySQLConnectionTestBase):
    """测试 _MySQLConnection.executescript() 批量执行。"""

    def test_executescript_splits_and_executes(self):
        """executescript 应按分号拆分 SQL 逐条执行。"""
        self.conn.executescript("SELECT 1; SELECT 2")
        self.assertEqual(self.mock_cursor.execute.call_count, 2)

    def test_executescript_handles_trailing_semicolon(self):
        """executescript 应正确处理末尾分号。"""
        self.conn.executescript("SELECT 1;")
        self.assertEqual(self.mock_cursor.execute.call_count, 1)

    def test_executescript_commits_after_all(self):
        """executescript 执行完毕后应调用 commit。"""
        self.conn.executescript("SELECT 1; SELECT 2")
        self.mock_raw.commit.assert_called_once_with()

    def test_executescript_skips_empty_statements(self):
        """executescript 应跳过空语句（分号间的空白）。"""
        self.conn.executescript("SELECT 1;;;SELECT 2")
        self.assertEqual(self.mock_cursor.execute.call_count, 2)

    def test_executescript_single_statement(self):
        """单条 SQL 无需分号。"""
        self.conn.executescript("SELECT 1")
        self.assertEqual(self.mock_cursor.execute.call_count, 1)
        self.mock_raw.commit.assert_called_once_with()

    def test_executescript_handles_newlines(self):
        """包含换行的 SQL 应正常执行。"""
        self.conn.executescript("SELECT 1\nUNION ALL\nSELECT 2")
        self.assertEqual(self.mock_cursor.execute.call_count, 1)
        self.mock_raw.commit.assert_called_once_with()


# ---------------------------------------------------------------------------
# 测试 MockMySQLMixin 本身的功能
# ---------------------------------------------------------------------------

class TestMockMySQLMixin(unittest.TestCase):
    """测试 MockMySQLMixin 辅助方法的正确性。"""

    def test_make_mock_connection_returns_conn_and_cursor(self):
        """make_mock_connection 应返回 (conn, cursor) 二元组。"""
        conn, cursor = MockMySQLMixin.make_mock_connection()
        self.assertIsInstance(conn, MagicMock)
        self.assertIsInstance(cursor, MagicMock)
        conn.cursor.assert_not_called()

    def test_make_mock_connection_cursor_is_returned_by_conn(self):
        """conn.cursor() 应返回传入的 cursor。"""
        custom_cursor = MagicMock()
        conn, cursor = MockMySQLMixin.make_mock_connection(custom_cursor)
        self.assertIs(cursor, custom_cursor)
        self.assertIs(conn.cursor(), custom_cursor)

    def test_make_mock_cursor_with_fetchone(self):
        """make_mock_cursor 应正确设置 fetchone。"""
        cursor = MockMySQLMixin.make_mock_cursor(fetchone_return={"id": 1})
        self.assertEqual(cursor.fetchone(), {"id": 1})

    def test_make_mock_cursor_with_fetchall(self):
        """make_mock_cursor 应正确设置 fetchall。"""
        data = [{"id": 1}, {"id": 2}]
        cursor = MockMySQLMixin.make_mock_cursor(fetchall_return=data)
        self.assertEqual(cursor.fetchall(), data)

    def test_make_mock_cursor_with_rowcount(self):
        """make_mock_cursor 应正确设置 rowcount。"""
        cursor = MockMySQLMixin.make_mock_cursor(rowcount=10)
        self.assertEqual(cursor.rowcount, 10)

    def test_make_mock_cursor_with_lastrowid(self):
        """make_mock_cursor 应正确设置 lastrowid。"""
        cursor = MockMySQLMixin.make_mock_cursor(lastrowid=99)
        self.assertEqual(cursor.lastrowid, 99)

    def test_make_mock_cursor_default_values(self):
        """make_mock_cursor 默认值应为 rowcount=-1, lastrowid=0。"""
        cursor = MockMySQLMixin.make_mock_cursor()
        self.assertEqual(cursor.rowcount, -1)
        self.assertEqual(cursor.lastrowid, 0)


# ---------------------------------------------------------------------------
# MySQL CRUD 测试基类
# ---------------------------------------------------------------------------

class _MySQLCRUDTestBase(MockMySQLMixin, unittest.TestCase):
    """
    MySQL CRUD 测试基类。

    提供已初始化的 _MySQLConnection mock 环境。
    子类通过 self.conn 访问 mock 连接，通过 self.mock_cursor 控制
    execute/fetchone/fetchall/rowcount/lastrowid 等行为。
    """

    def setUp(self):
        self.mock_raw = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_raw.cursor.return_value = self.mock_cursor
        self.mock_cursor.lastrowid = 0
        self.mock_cursor.rowcount = -1
        self.conn = db._MySQLConnection(self.mock_raw)


# ---------------------------------------------------------------------------
# 测试 get_config_db() MySQL 路径
# ---------------------------------------------------------------------------

class TestMySQLGetConfigDB(unittest.TestCase):
    """测试 get_config_db() 在 MySQL 引擎下的路由行为。"""

    @patch("db._get_engine", return_value="mysql")
    @patch("db._connect_mysql_config")
    def test_returns_mysql_connection_when_mysql_engine(
        self, mock_connect_mysql, mock_engine
    ):
        """engine=mysql 时，get_config_db 应调用 _connect_mysql_config 并返回结果。"""
        fake_conn = MagicMock()
        mock_connect_mysql.return_value = fake_conn
        result = db.get_config_db()
        self.assertIs(result, fake_conn)
        mock_connect_mysql.assert_called_once_with()

    @patch("db._get_engine", return_value="sqlite3")
    @patch("db._connect_sqlite")
    def test_returns_sqlite_connection_when_sqlite_engine(
        self, mock_connect_sqlite, mock_engine
    ):
        """engine=sqlite3 时，get_config_db 应调用 _connect_sqlite 并返回结果。"""
        fake_conn = MagicMock()
        mock_connect_sqlite.return_value = fake_conn
        result = db.get_config_db()
        self.assertIs(result, fake_conn)
        mock_connect_sqlite.assert_called_once_with()

    @patch("db._get_engine", return_value="mysql")
    @patch("db._connect_mysql_config")
    def test_routes_to_connect_mysql(
        self, mock_connect_mysql, mock_engine
    ):
        """engine=mysql 时，_connect_mysql_config 应被精确调用一次。"""
        db.get_config_db()
        self.assertEqual(mock_connect_mysql.call_count, 1)


# ---------------------------------------------------------------------------
# 测试 init_db() MySQL 路径
# ---------------------------------------------------------------------------

class TestMySQLInitDB(_MySQLCRUDTestBase):
    """测试 init_db() 在 MySQL 引擎下的 DDL 执行和迁移行为。"""

    @patch("db._get_engine", return_value="mysql")
    def test_init_db_executes_mysql_ddl(self, mock_engine):
        """init_db (MySQL) 应执行 _MYSQL_SCHEMA 中的所有 DDL 语句。"""
        # 清除 setUp 中的 mock 调用记录
        self.mock_cursor.reset_mock()
        self.mock_raw.reset_mock()

        db.init_db(self.conn)

        # 验证所有非空 DDL 语句都被执行
        statements = [s.strip() for s in db._MYSQL_SCHEMA.split(";") if s.strip()]
        self.assertGreater(len(statements), 4)
        for stmt in statements:
            self.mock_cursor.execute.assert_any_call(stmt, ())

        # 验证 commit 被调用
        self.mock_raw.commit.assert_called()

    @patch("db._get_engine", return_value="mysql")
    def test_init_db_calls_mysql_migrations(self, mock_engine):
        """init_db (MySQL) 应调用 _init_mysql_migrations 执行迁移。"""
        self.mock_cursor.reset_mock()
        self.mock_raw.reset_mock()
        # mock SHOW COLUMNS 返回所有列都已存在（免迁移场景）
        self.mock_cursor.fetchone.return_value = None
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("name", "varchar(255)", "NO", "UNI", None, ""),
            ("pool_id", "int(11)", "YES", "MUL", None, ""),
            ("category_id", "int(11)", "YES", "MUL", None, ""),
            ("memo", "text", "YES", "", None, ""),
        ]

        db.init_db(self.conn)

        # 在 DDL 执行后，应执行 SHOW COLUMNS（迁移逻辑的入口）
        self.mock_cursor.execute.assert_any_call("SHOW COLUMNS FROM report_configs", ())

    @patch("db._get_engine", return_value="mysql")
    def test_init_db_idempotent_on_mysql(self, mock_engine):
        """重复调用 init_db (MySQL) 不应报错。"""
        self.mock_cursor.reset_mock()
        self.mock_raw.reset_mock()
        self.mock_cursor.fetchone.return_value = None
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("name", "varchar(255)", "NO", "UNI", None, ""),
            ("pool_id", "int(11)", "YES", "MUL", None, ""),
            ("category_id", "int(11)", "YES", "MUL", None, ""),
            ("memo", "text", "YES", "", None, ""),
        ]

        db.init_db(self.conn)  # 第一次
        db.init_db(self.conn)  # 第二次不应抛异常
        self.mock_raw.commit.assert_called()

    def test_get_schema_sql_returns_mysql(self):
        """_get_schema_sql('mysql') 应返回 _MYSQL_SCHEMA。"""
        self.assertIs(db._get_schema_sql("mysql"), db._MYSQL_SCHEMA)


# ---------------------------------------------------------------------------
# 测试 _init_mysql_migrations()
# ---------------------------------------------------------------------------

class TestMySQLMigrations(_MySQLCRUDTestBase):
    """测试 _init_mysql_migrations() 迁移逻辑。"""

    @patch("db._get_engine", return_value="mysql")
    def test_migration_1_modifies_pool_id_when_not_null(self, mock_engine):
        """pool_id 为 NOT NULL 时，应执行 MODIFY COLUMN。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = None
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("pool_id", "int(11)", "NO", "MUL", None, ""),  # Null=NO → NOT NULL
        ]

        db._init_mysql_migrations(self.conn)

        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE report_configs MODIFY COLUMN pool_id INTEGER NULL", ()
        )
        self.mock_raw.commit.assert_called()

    @patch("db._get_engine", return_value="mysql")
    def test_migration_2_adds_category_id_when_missing(self, mock_engine):
        """category_id 列缺失时，应执行 ADD COLUMN。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = None
        # 第一次 SHOW COLUMNS（迁移1用）— 不含 category_id
        # 第二次 SHOW COLUMNS（迁移2用）— 还是不包含 category_id
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("name", "varchar(255)", "NO", "", None, ""),
            ("pool_id", "int(11)", "YES", "MUL", None, ""),
        ]

        db._init_mysql_migrations(self.conn)

        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE report_configs ADD COLUMN category_id INTEGER", ()
        )

    @patch("db._get_engine", return_value="mysql")
    def test_migration_5_adds_memo_when_missing(self, mock_engine):
        """memo 列缺失时，应执行 ADD COLUMN。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = None
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("name", "varchar(255)", "NO", "", None, ""),
            ("pool_id", "int(11)", "YES", "MUL", None, ""),
            ("category_id", "int(11)", "YES", "MUL", None, ""),
        ]

        db._init_mysql_migrations(self.conn)

        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE report_configs ADD COLUMN memo TEXT", ()
        )


# ---------------------------------------------------------------------------
# 测试连接池 CRUD（MySQL 路径）
# ---------------------------------------------------------------------------

class TestMySQLPoolCRUD(_MySQLCRUDTestBase):
    """连接池 CRUD 在 MySQL engine 下的 SQL 执行验证。"""

    def test_add_pool(self):
        """add_pool 应执行 MAX + INSERT SQL，返回 lastrowid。"""
        self.mock_cursor.fetchone.return_value = {"COALESCE(MAX(sort_order), 0)": 0}
        self.mock_cursor.lastrowid = 1

        pid = db.add_pool(self.conn, "mypool", "host1", 3306, "user1", "pass1", "db1")

        self.assertEqual(pid, 1)
        self.mock_cursor.execute.assert_any_call(
            "SELECT COALESCE(MAX(sort_order), 0) FROM connection_pools", ()
        )
        self.mock_cursor.execute.assert_any_call(
            "INSERT INTO connection_pools (name,host,port,user,password,`database`,sort_order) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ("mypool", "host1", 3306, "user1", "pass1", "db1", 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_get_pool_found(self):
        """get_pool 存在时应返回 dict。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "name": "mypool", "host": "h1", "port": 3306,
            "user": "u1", "password": "p1", "database": "d1", "sort_order": 1,
        }

        pool = db.get_pool(self.conn, 1)

        self.assertIsNotNone(pool)
        self.assertEqual(pool["name"], "mypool")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM connection_pools WHERE id=%s", (1,)
        )

    def test_get_pool_not_found(self):
        """get_pool 不存在时应返回 None。"""
        self.mock_cursor.fetchone.return_value = None
        self.assertIsNone(db.get_pool(self.conn, 999))

    def test_get_all_pools(self):
        """get_all_pools 应返回所有连接池列表。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "pool_a", "host": "h1", "port": 3306,
             "user": "u1", "password": "p1", "database": "d1", "sort_order": 1},
            {"id": 2, "name": "pool_b", "host": "h2", "port": 3307,
             "user": "u2", "password": "p2", "database": "d2", "sort_order": 2},
        ]

        pools = db.get_all_pools(self.conn)

        self.assertEqual(len(pools), 2)
        self.assertEqual(pools[0]["name"], "pool_a")
        self.assertEqual(pools[1]["name"], "pool_b")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM connection_pools ORDER BY sort_order, id", ()
        )

    def test_update_pool_success(self):
        """update_pool 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1

        ok = db.update_pool(self.conn, 1, "newname", "h2", 3307, "u2", "p2", "d2")

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "UPDATE connection_pools SET name=%s,host=%s,port=%s,user=%s,password=%s,"
            "`database`=%s WHERE id=%s",
            ("newname", "h2", 3307, "u2", "p2", "d2", 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_update_pool_not_found(self):
        """update_pool 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.update_pool(self.conn, 999, "x", "x", 3306, "x", "x", "x"))

    def test_delete_pool_success(self):
        """delete_pool 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1

        ok = db.delete_pool(self.conn, 1)

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "DELETE FROM connection_pools WHERE id=%s", (1,)
        )

    def test_delete_pool_not_found(self):
        """delete_pool 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.delete_pool(self.conn, 999))

    def test_move_pool_up(self):
        """move_pool 'up' 应与前一项交换 sort_order。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "pool_a", "sort_order": 0},
            {"id": 2, "name": "pool_b", "sort_order": 1},
            {"id": 3, "name": "pool_c", "sort_order": 2},
        ]

        ok = db.move_pool(self.conn, 2, "up")

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE connection_pools SET sort_order=%s WHERE id=%s", (0, 2)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE connection_pools SET sort_order=%s WHERE id=%s", (1, 1)
        )
        self.mock_raw.commit.assert_called()

    def test_move_pool_down(self):
        """move_pool 'down' 应与后一项交换 sort_order。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "pool_a", "sort_order": 0},
            {"id": 2, "name": "pool_b", "sort_order": 1},
            {"id": 3, "name": "pool_c", "sort_order": 2},
        ]

        ok = db.move_pool(self.conn, 1, "down")

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE connection_pools SET sort_order=%s WHERE id=%s", (1, 1)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE connection_pools SET sort_order=%s WHERE id=%s", (0, 2)
        )

    def test_move_pool_at_edge_no_move(self):
        """首个 pool 不能 move up，末个不能 move down。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "pool_a", "sort_order": 0},
        ]
        self.assertFalse(db.move_pool(self.conn, 1, "up"))
        self.assertFalse(db.move_pool(self.conn, 1, "down"))

    def test_move_pool_not_found(self):
        """不存在的 pool_id 应返回 False。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "pool_a", "sort_order": 0},
        ]
        self.assertFalse(db.move_pool(self.conn, 999, "up"))


# ---------------------------------------------------------------------------
# 测试用户 CRUD（MySQL 路径）
# ---------------------------------------------------------------------------

class TestMySQLUserCRUD(_MySQLCRUDTestBase):
    """用户 CRUD 在 MySQL engine 下的 SQL 执行验证。"""

    def test_add_user(self):
        """add_user 应执行 INSERT SQL，返回 lastrowid。"""
        self.mock_cursor.lastrowid = 1
        uid = db.add_user(self.conn, "alice", "hash123")
        self.assertEqual(uid, 1)
        self.mock_cursor.execute.assert_called_once_with(
            "INSERT INTO users (username,password_hash) VALUES (%s,%s)",
            ("alice", "hash123"),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_get_user_found(self):
        """get_user 存在时应返回 dict。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "username": "alice", "password_hash": "hash123",
        }
        user = db.get_user(self.conn, "alice")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "alice")
        self.assertEqual(user["password_hash"], "hash123")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM users WHERE username=%s", ("alice",)
        )

    def test_get_user_not_found(self):
        """get_user 不存在时应返回 None。"""
        self.mock_cursor.fetchone.return_value = None
        self.assertIsNone(db.get_user(self.conn, "nobody"))

    def test_get_user_by_id(self):
        """get_user_by_id 应通过 id 查询用户。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "username": "bob", "password_hash": "h1",
        }
        user = db.get_user_by_id(self.conn, 1)
        self.assertEqual(user["username"], "bob")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM users WHERE id=%s", (1,)
        )

    def test_get_all_users(self):
        """get_all_users 应返回所有用户列表。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "username": "alice", "password_hash": "h1"},
            {"id": 2, "username": "bob", "password_hash": "h2"},
        ]
        users = db.get_all_users(self.conn)
        self.assertEqual(len(users), 2)
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM users ORDER BY id", ()
        )

    def test_update_user_success(self):
        """update_user 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.update_user(self.conn, 1, "newname", "newhash")
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "UPDATE users SET username=%s,password_hash=%s WHERE id=%s",
            ("newname", "newhash", 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_delete_user_success(self):
        """delete_user 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.delete_user(self.conn, 1)
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "DELETE FROM users WHERE id=%s", (1,)
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_delete_user_not_found(self):
        """delete_user 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.delete_user(self.conn, 999))


# ---------------------------------------------------------------------------
# 测试报表配置 CRUD（MySQL 路径）
# ---------------------------------------------------------------------------

class TestMySQLReportCRUD(_MySQLCRUDTestBase):
    """报表配置 CRUD 在 MySQL engine 下的 SQL 执行验证。"""

    def test_add_report(self):
        """add_report 应执行 MAX + INSERT SQL，返回 lastrowid。"""
        self.mock_cursor.fetchone.return_value = {"COALESCE(MAX(sort_order), 0)": 0}
        self.mock_cursor.lastrowid = 1

        rid = db.add_report(self.conn, "报表A", "SELECT * FROM t", 20, 1)

        self.assertEqual(rid, 1)
        self.mock_cursor.execute.assert_any_call(
            "SELECT COALESCE(MAX(sort_order), 0) FROM report_configs", ()
        )
        self.mock_cursor.execute.assert_any_call(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,"
            "category_id,memo,result_names,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("报表A", "SELECT * FROM t", 20, 1, None, None, '', 1, 0, 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_add_report_with_memo_and_category(self):
        """add_report 带 memo 和 category_id 应一并存储。"""
        self.mock_cursor.fetchone.return_value = {"COALESCE(MAX(sort_order), 0)": 5}
        self.mock_cursor.lastrowid = 2

        rid = db.add_report(self.conn, "完整报表", "SELECT 1", 50, 1,
                            category_id=3, memo="这是备注")

        self.assertEqual(rid, 2)
        self.mock_cursor.execute.assert_any_call(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,"
            "category_id,memo,result_names,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("完整报表", "SELECT 1", 50, 1, 3, "这是备注", '', 1, 0, 6),
        )

    def test_get_report_found(self):
        """get_report 存在时应返回 dict。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "name": "报表A", "sql_query": "SELECT 1",
            "default_page_size": 20, "pool_id": 1, "category_id": None,
            "memo": None, "result_names": "", "prefer_cache": 1,
            "cache_ttl_hours": 0, "sort_order": 1,
        }
        rpt = db.get_report(self.conn, 1)
        self.assertIsNotNone(rpt)
        self.assertEqual(rpt["name"], "报表A")
        self.assertEqual(rpt["default_page_size"], 20)
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM report_configs WHERE id=%s", (1,)
        )

    def test_get_report_not_found(self):
        """get_report 不存在时应返回 None。"""
        self.mock_cursor.fetchone.return_value = None
        self.assertIsNone(db.get_report(self.conn, 999))

    def test_get_all_reports(self):
        """get_all_reports 应返回所有报表列表。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "r1", "sql_query": "SELECT 1",
             "default_page_size": 10, "pool_id": None, "category_id": None,
             "memo": None, "result_names": "", "prefer_cache": 1,
             "cache_ttl_hours": 0, "sort_order": 1},
            {"id": 2, "name": "r2", "sql_query": "SELECT 2",
             "default_page_size": 20, "pool_id": 1, "category_id": None,
             "memo": "备注", "result_names": "", "prefer_cache": 1,
             "cache_ttl_hours": 0, "sort_order": 2},
        ]
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0]["name"], "r1")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM report_configs ORDER BY sort_order, id", ()
        )

    def test_update_report(self):
        """update_report 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.update_report(self.conn, 1, "newname", "SELECT 2", 50, 1,
                              category_id=2, memo="新备注")
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "UPDATE report_configs SET name=%s,sql_query=%s,default_page_size=%s,"
            "pool_id=%s,category_id=%s,memo=%s,result_names=%s,"
            "prefer_cache=%s,cache_ttl_hours=%s WHERE id=%s",
            ("newname", "SELECT 2", 50, 1, 2, "新备注", '', 1, 0, 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_update_report_not_found(self):
        """update_report 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.update_report(
            self.conn, 999, "x", "SELECT 1", 10, 1))

    def test_delete_report(self):
        """delete_report 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.delete_report(self.conn, 1)
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "DELETE FROM report_configs WHERE id=%s", (1,)
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_delete_report_not_found(self):
        """delete_report 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.delete_report(self.conn, 999))

    def test_move_report_up(self):
        """move_report 'up' 应与同分类前一项交换 sort_order。"""
        # get_report 调用
        self.mock_cursor.fetchone.return_value = {
            "id": 2, "name": "r2", "sql_query": "SELECT 1",
            "default_page_size": 20, "pool_id": None,
            "category_id": 1, "memo": None, "sort_order": 2,
        }
        # get_reports 调用 (通过 category_id)
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "r1", "category_id": 1, "sort_order": 1},
            {"id": 2, "name": "r2", "category_id": 1, "sort_order": 2},
            {"id": 3, "name": "r3", "category_id": 1, "sort_order": 3},
        ]

        ok = db.move_report(self.conn, 2, "up")

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_configs SET sort_order=%s WHERE id=%s", (1, 2)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_configs SET sort_order=%s WHERE id=%s", (2, 1)
        )

    def test_move_report_down(self):
        """move_report 'down' 应与同分类后一项交换 sort_order。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "category_id": 1, "sort_order": 1,
        }
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "category_id": 1, "sort_order": 1},
            {"id": 2, "category_id": 1, "sort_order": 2},
        ]

        ok = db.move_report(self.conn, 1, "down")

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_configs SET sort_order=%s WHERE id=%s", (2, 1)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_configs SET sort_order=%s WHERE id=%s", (1, 2)
        )


# ---------------------------------------------------------------------------
# 测试分类 CRUD（MySQL 路径）
# ---------------------------------------------------------------------------

class TestMySQLCategoryCRUD(_MySQLCRUDTestBase):
    """分类 CRUD 在 MySQL engine 下的 SQL 执行验证。"""

    def test_add_category(self):
        """add_category 应执行 MAX + INSERT SQL，返回 lastrowid。"""
        self.mock_cursor.fetchone.return_value = {"COALESCE(MAX(sort_order), 0)": 0}
        self.mock_cursor.lastrowid = 1

        cid = db.add_category(self.conn, "报表分类")

        self.assertEqual(cid, 1)
        self.mock_cursor.execute.assert_any_call(
            "SELECT COALESCE(MAX(sort_order), 0) FROM report_categories", ()
        )
        self.mock_cursor.execute.assert_any_call(
            "INSERT INTO report_categories (name, parent_id, sort_order) VALUES (%s,%s,%s)",
            ("报表分类", None, 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_add_category_with_parent(self):
        """add_category 带 parent_id 应正确存储。"""
        self.mock_cursor.fetchone.return_value = {"COALESCE(MAX(sort_order), 0)": 3}
        self.mock_cursor.lastrowid = 2

        cid = db.add_category(self.conn, "子分类", parent_id=1)

        self.assertEqual(cid, 2)
        self.mock_cursor.execute.assert_any_call(
            "INSERT INTO report_categories (name, parent_id, sort_order) VALUES (%s,%s,%s)",
            ("子分类", 1, 4),
        )

    def test_get_category_found(self):
        """get_category 存在时应返回 dict。"""
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "name": "报表分类", "parent_id": None, "sort_order": 1,
        }
        cat = db.get_category(self.conn, 1)
        self.assertIsNotNone(cat)
        self.assertEqual(cat["name"], "报表分类")

    def test_get_category_not_found(self):
        """get_category 不存在时应返回 None。"""
        self.mock_cursor.fetchone.return_value = None
        self.assertIsNone(db.get_category(self.conn, 999))

    def test_get_all_categories(self):
        """get_all_categories 应返回所有分类列表。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "分类A", "parent_id": None, "sort_order": 1},
            {"id": 2, "name": "分类B", "parent_id": None, "sort_order": 2},
        ]
        cats = db.get_all_categories(self.conn)
        self.assertEqual(len(cats), 2)
        self.assertEqual(cats[0]["name"], "分类A")

    def test_update_category(self):
        """update_category 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.update_category(self.conn, 1, "新名称", parent_id=3)
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "UPDATE report_categories SET name=%s, parent_id=%s WHERE id=%s",
            ("新名称", 3, 1),
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_update_category_no_parent(self):
        """update_category 不传 parent_id 应设为 None。"""
        self.mock_cursor.rowcount = 1
        ok = db.update_category(self.conn, 1, "独立分类")
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "UPDATE report_categories SET name=%s, parent_id=%s WHERE id=%s",
            ("独立分类", None, 1),
        )

    def test_delete_category(self):
        """delete_category 应先置空关联，再删除。"""
        self.mock_cursor.rowcount = 1

        ok = db.delete_category(self.conn, 1)

        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_configs SET category_id=NULL WHERE category_id=%s", (1,)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_categories SET parent_id=NULL WHERE parent_id=%s", (1,)
        )
        self.mock_cursor.execute.assert_any_call(
            "DELETE FROM report_categories WHERE id=%s", (1,)
        )
        self.mock_raw.commit.assert_called()

    def test_delete_category_not_found(self):
        """delete_category 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.delete_category(self.conn, 999))

    def test_move_category_up(self):
        """move_category 'up' 应与前一项交换 sort_order。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "cat_a", "parent_id": None, "sort_order": 0},
            {"id": 2, "name": "cat_b", "parent_id": None, "sort_order": 1},
        ]
        ok = db.move_category(self.conn, 2, "up")
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_categories SET sort_order=%s WHERE id=%s", (0, 2)
        )
        self.mock_cursor.execute.assert_any_call(
            "UPDATE report_categories SET sort_order=%s WHERE id=%s", (1, 1)
        )

    def test_move_category_not_found(self):
        """不存在的 category_id 应返回 False。"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "cat_a", "parent_id": None, "sort_order": 0},
        ]
        self.assertFalse(db.move_category(self.conn, 999, "up"))


# ---------------------------------------------------------------------------
# 测试 Session CRUD（MySQL 路径）
# ---------------------------------------------------------------------------

class TestMySQLSessionCRUD(_MySQLCRUDTestBase):
    """Session CRUD 在 MySQL engine 下的 SQL 执行验证。"""

    def test_add_session(self):
        """add_session 应执行 REPLACE SQL。"""
        db.add_session(self.conn, "tok1", "alice")
        (sql, params) = self.mock_cursor.execute.call_args[0]
        self.assertIn("REPLACE INTO sessions", sql)
        self.assertIn("%s", sql)
        self.assertEqual(params[0], "tok1")
        self.assertEqual(params[1], "alice")
        self.mock_raw.commit.assert_called_once_with()

    def test_get_session_found(self):
        """get_session 有效时应返回用户名。"""
        self.mock_cursor.fetchone.return_value = {"username": "alice"}
        username = db.get_session(self.conn, "tok1")
        self.assertEqual(username, "alice")
        sql = self.mock_cursor.execute.call_args[0][0]
        self.assertIn("SELECT username FROM sessions", sql)

    def test_get_session_expired(self):
        """get_session 过期或不存在时应返回 None。"""
        self.mock_cursor.fetchone.return_value = None
        self.assertIsNone(db.get_session(self.conn, "expired_tok"))

    def test_remove_session_success(self):
        """remove_session 成功时应返回 True。"""
        self.mock_cursor.rowcount = 1
        ok = db.remove_session(self.conn, "tok1")
        self.assertTrue(ok)
        self.mock_cursor.execute.assert_called_once_with(
            "DELETE FROM sessions WHERE token=%s", ("tok1",)
        )
        self.mock_raw.commit.assert_called_once_with()

    def test_remove_session_not_found(self):
        """remove_session 不存在时应返回 False。"""
        self.mock_cursor.rowcount = 0
        self.assertFalse(db.remove_session(self.conn, "ghost"))

    def test_get_all_sessions(self):
        """get_all_sessions 应返回所有未过期 session。"""
        self.mock_cursor.fetchall.return_value = [
            {"token": "tok_a", "username": "alice", "created_at": 1000000},
            {"token": "tok_b", "username": "bob", "created_at": 1000000},
        ]
        sessions = db.get_all_sessions(self.conn)
        self.assertEqual(len(sessions), 2)
        tokens = {s["token"] for s in sessions}
        self.assertIn("tok_a", tokens)

    def test_clear_sessions(self):
        """clear_sessions 应删除所有 session 记录。"""
        db.clear_sessions(self.conn)
        self.mock_cursor.execute.assert_called_once_with(
            "DELETE FROM sessions", ()
        )
        self.mock_raw.commit.assert_called_once_with()


# ---------------------------------------------------------------------------
# 组合矩阵测试：大结果集
# ---------------------------------------------------------------------------

class TestMySQLCursorLargeResultSet(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLCursor 在大结果集场景下的正确性。"""

    def test_fetchall_10000_rows(self):
        """fetchall 应能正确处理 10000 行数据。"""
        data = [{"id": i, "val": f"row_{i}"} for i in range(10000)]
        mock_raw_cursor = self.make_mock_cursor(fetchall_return=data)
        cursor = db._MySQLCursor(mock_raw_cursor)
        rows = cursor.fetchall()
        self.assertEqual(len(rows), 10000)
        self.assertIsInstance(rows[0], db._MySQLRow)
        self.assertEqual(rows[0]["id"], 0)
        self.assertEqual(rows[9999]["id"], 9999)
        self.assertEqual(rows[5000]["val"], "row_5000")

    def test_fetchall_batch_row_wrapping(self):
        """100 行数据每行都应被正确包装为 _MySQLRow 实例。"""
        data = [{"id": i, "name": f"n_{i}"} for i in range(100)]
        mock_raw_cursor = self.make_mock_cursor(fetchall_return=data)
        cursor = db._MySQLCursor(mock_raw_cursor)
        rows = cursor.fetchall()
        for i, row in enumerate(rows):
            self.assertIsInstance(row, db._MySQLRow)
            self.assertEqual(row["id"], i)
            self.assertEqual(row["name"], f"n_{i}")


# ---------------------------------------------------------------------------
# 组合矩阵测试：空结果集
# ---------------------------------------------------------------------------

class TestMySQLCursorEmptyResult(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLCursor 在空结果集场景下的正确性。"""

    def test_fetchall_empty_result(self):
        """查询返回 0 行时 fetchall 应返回空列表。"""
        mock_raw_cursor = self.make_mock_cursor(fetchall_return=[])
        cursor = db._MySQLCursor(mock_raw_cursor)
        self.assertEqual(cursor.fetchall(), [])

    def test_fetchone_none_result(self):
        """查询无数据时 fetchone 应返回 None。"""
        mock_raw_cursor = self.make_mock_cursor()
        mock_raw_cursor.fetchone.return_value = None
        cursor = db._MySQLCursor(mock_raw_cursor)
        self.assertIsNone(cursor.fetchone())

    def test_fetchall_then_fetchone_empty(self):
        """fetchall 返回空后，fetchone 仍应返回 None。"""
        mock_raw_cursor = self.make_mock_cursor(fetchall_return=[])
        mock_raw_cursor.fetchone.return_value = None
        cursor = db._MySQLCursor(mock_raw_cursor)
        self.assertEqual(cursor.fetchall(), [])
        self.assertIsNone(cursor.fetchone())

    def test_empty_result_rowcount(self):
        """空结果集时 rowcount 应为 0。"""
        mock_raw_cursor = self.make_mock_cursor(fetchall_return=[], rowcount=0)
        cursor = db._MySQLCursor(mock_raw_cursor)
        cursor.fetchall()
        self.assertEqual(cursor.rowcount, 0)


# ---------------------------------------------------------------------------
# 组合矩阵测试：NULL 值
# ---------------------------------------------------------------------------

class TestMySQLRowNullValues(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLRow 在包含 NULL/None 值时的正确行为。"""

    def test_none_key_access(self):
        """包含 None 值的行应正确通过键名访问。"""
        row = db._MySQLRow({"id": 1, "name": None, "age": 30})
        self.assertEqual(row["id"], 1)
        self.assertIsNone(row["name"])
        self.assertEqual(row["age"], 30)

    def test_none_index_access(self):
        """包含 None 值的行应正确通过索引访问。"""
        row = db._MySQLRow({"id": 1, "name": None, "age": 30})
        self.assertEqual(row[0], 1)
        self.assertIsNone(row[1])
        self.assertEqual(row[2], 30)

    def test_none_in_values_list(self):
        """values() 应包含 None 值。"""
        row = db._MySQLRow({"id": 1, "name": None})
        vals = list(row.values())
        self.assertIn(None, vals)
        self.assertIsNone(vals[1])

    def test_none_in_iteration(self):
        """迭代应生成 None 值。"""
        row = db._MySQLRow({"id": 1, "name": None})
        vals = list(row)
        self.assertEqual(vals, [1, None])

    def test_none_str_conversion(self):
        """str(None) 应为 'None'（与 Python 默认行为一致）。"""
        row = db._MySQLRow({"val": None})
        self.assertEqual(str(row["val"]), "None")

    def test_none_repr(self):
        """repr 应正确包含 None 值。"""
        row = db._MySQLRow({"id": 1, "name": None})
        self.assertIn("None", repr(row))


# ---------------------------------------------------------------------------
# 组合矩阵测试：Unicode/中文
# ---------------------------------------------------------------------------

class TestMySQLRowUnicode(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLRow 在包含 Unicode/中文字符串时的正确行为。"""

    def test_chinese_string_key_access(self):
        """包含中文的 _MySQLRow 应正确返回字符串。"""
        row = db._MySQLRow({"id": 1, "报表名": "月度销售报表", "备注": "测试数据"})
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["报表名"], "月度销售报表")
        self.assertEqual(row["备注"], "测试数据")

    def test_chinese_in_values(self):
        """values() 应包含中文字符串。"""
        row = db._MySQLRow({"name": "报表测试"})
        self.assertIn("报表测试", list(row.values()))

    def test_chinese_in_repr(self):
        """repr 应包含中文字符串。"""
        row = db._MySQLRow({"name": "年度汇总报表"})
        self.assertIn("年度汇总报表", repr(row))

    def test_unicode_special_chars(self):
        """特殊 Unicode 字符（如 emoji）应正确处理。"""
        row = db._MySQLRow({"name": "测试✓★ℹ", "emoji": "📊📈✅"})
        self.assertEqual(row["name"], "测试✓★ℹ")
        self.assertEqual(row["emoji"], "📊📈✅")

    def test_mixed_chinese_and_ascii(self):
        """中英文混合字符串应正确传递。"""
        row = db._MySQLRow({"title": "Report 2024 年度报表 (Q1)"})
        self.assertEqual(row["title"], "Report 2024 年度报表 (Q1)")


# ---------------------------------------------------------------------------
# 组合矩阵测试：边界值
# ---------------------------------------------------------------------------

class TestMySQLRowBoundaryValues(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLRow 在边界值场景下的正确行为。"""

    def test_large_integer(self):
        """超大整数应正确存储和访问。"""
        row = db._MySQLRow({"id": 2**63 - 1, "small": -(2**63)})
        self.assertEqual(row["id"], 2**63 - 1)
        self.assertEqual(row["small"], -(2**63))

    def test_tiny_float(self):
        """极小浮点数应正确存储和访问。"""
        row = db._MySQLRow({"val": 1e-300})
        self.assertEqual(row["val"], 1e-300)

    def test_huge_float(self):
        """极大浮点数应正确存储和访问。"""
        row = db._MySQLRow({"val": 1e308})
        self.assertEqual(row["val"], 1e308)

    def test_empty_string(self):
        """空字符串应正确存储和访问。"""
        row = db._MySQLRow({"name": "", "desc": "nonempty"})
        self.assertEqual(row["name"], "")
        self.assertEqual(row["desc"], "nonempty")

    def test_numeric_string(self):
        """纯数字字符串应保持字符串类型。"""
        row = db._MySQLRow({"phone": "13800138000", "code": "007"})
        self.assertIsInstance(row["phone"], str)
        self.assertEqual(row["code"], "007")
        self.assertNotEqual(row["code"], 7)

    def test_boolean_values(self):
        """布尔值 True/False 应正确存储。"""
        row = db._MySQLRow({"active": True, "deleted": False})
        self.assertIs(row["active"], True)
        self.assertIs(row["deleted"], False)

    def test_negative_zero_float(self):
        """负零浮点数应正确处理。"""
        row = db._MySQLRow({"val": -0.0})
        self.assertEqual(row["val"], 0.0)


# ---------------------------------------------------------------------------
# 组合矩阵测试：全 null 行
# ---------------------------------------------------------------------------

class TestMySQLRowAllNull(MockMySQLMixin, unittest.TestCase):
    """测试 _MySQLRow 在整行均为 None 时的正确行为。"""

    def setUp(self):
        self.row = db._MySQLRow({"id": None, "name": None, "age": None})

    def test_all_none_key_access(self):
        """全 None 行应正确通过键名访问。"""
        self.assertIsNone(self.row["id"])
        self.assertIsNone(self.row["name"])
        self.assertIsNone(self.row["age"])

    def test_all_none_index_access(self):
        """全 None 行应正确通过索引访问。"""
        self.assertIsNone(self.row[0])
        self.assertIsNone(self.row[1])
        self.assertIsNone(self.row[2])

    def test_all_none_len(self):
        """全 None 行的 len 应与字段数一致。"""
        self.assertEqual(len(self.row), 3)

    def test_all_none_keys(self):
        """全 None 行的 keys() 应返回所有字段名。"""
        self.assertEqual(list(self.row.keys()), ["id", "name", "age"])

    def test_all_none_values(self):
        """全 None 行的 values() 应全部为 None。"""
        self.assertEqual(list(self.row.values()), [None, None, None])

    def test_all_none_iteration(self):
        """全 None 行的迭代应生成全部 None。"""
        self.assertEqual(list(self.row), [None, None, None])

    def test_all_none_repr(self):
        """全 None 行的 repr 应包含 None 和字段名。"""
        rep = repr(self.row)
        self.assertIn("None", rep)
        self.assertIn("id", rep)
        self.assertIn("name", rep)


# ---------------------------------------------------------------------------
# 组合矩阵测试：混合类型与 format_cell 兼容性
# ---------------------------------------------------------------------------

class TestMySQLMixedTypes(MockMySQLMixin, unittest.TestCase):
    """
    测试混合数据类型在 _MySQLRow 和 format_cell 下的兼容性。

    format_cell 负责将单元格值格式化为显示字符串，需要处理
    int/float/None/Decimal/bytes 等多种类型。
    """

    def testformat_cell_with_none(self):
        """format_cell(None) 应返回空字符串。"""
        self.assertEqual(format_cell(None), "")

    def testformat_cell_with_int(self):
        """format_cell(int) 应返回整数字符串。"""
        self.assertEqual(format_cell(42), "42")
        self.assertEqual(format_cell(0), "0")
        self.assertEqual(format_cell(-1), "-1")

    def testformat_cell_with_large_int(self):
        """format_cell(超大整数) 不应使用科学计数法。"""
        val = 12345678901234567890
        self.assertEqual(format_cell(val), "12345678901234567890")

    def testformat_cell_with_float(self):
        """format_cell(float) 应返回浮点数字符串。"""
        self.assertEqual(format_cell(3.14), "3.14")
        self.assertEqual(format_cell(0.0), "0")

    def testformat_cell_with_float_scientific(self):
        """format_cell(科学计数法浮点数) 应转为全小数。"""
        result = format_cell(1e-10)
        self.assertNotIn("e", result.lower())
        self.assertAlmostEqual(float(result), 1e-10)

    def testformat_cell_with_negative_exponent(self):
        """format_cell(极小正浮点数) 应避免科学计数法。"""
        # 使用 1e-9 测试科学计数法转换（在 format_cell 的 15 位精度范围内）
        result = format_cell(1.23456e-9)
        self.assertNotIn("e", result.lower())
        self.assertAlmostEqual(float(result), 1.23456e-9)

    def testformat_cell_with_decimal_zero(self):
        """format_cell(Decimal(0)) 应返回 '0'。"""
        self.assertEqual(format_cell(Decimal("0")), "0")
        self.assertEqual(format_cell(Decimal("0.0")), "0")

    def testformat_cell_with_decimal(self):
        """format_cell(Decimal) 应返回格式化的十进制数字符串。"""
        self.assertEqual(format_cell(Decimal("3.14159")), "3.14159")
        self.assertEqual(format_cell(Decimal("100.500")), "100.5")
        self.assertEqual(format_cell(Decimal("-0.00100")), "-0.001")

    def testformat_cell_with_bytes(self):
        """format_cell(bytes) 应返回字符串表示。"""
        result = format_cell(b"hello")
        self.assertIsInstance(result, str)
        self.assertIn("hello", result)

    def testformat_cell_with_empty_string(self):
        """format_cell('') 应返回空字符串。"""
        self.assertEqual(format_cell(""), "")

    def testformat_cell_with_numeric_string(self):
        """format_cell(纯数字字符串) 应保持字符串原样。"""
        self.assertEqual(format_cell("007"), "007")
        self.assertEqual(format_cell("3.14"), "3.14")

    def testformat_cell_with_bool(self):
        """format_cell(bool) 应返回 'True' 或 'False'。"""
        self.assertEqual(format_cell(True), "True")
        self.assertEqual(format_cell(False), "False")

    def test_mysql_row_mixed_types_roundtrip(self):
        """_MySQLRow 包含混合类型时，各字段类型应保持不变。"""
        row = db._MySQLRow({
            "int_col": 42,
            "float_col": 3.14,
            "str_col": "hello",
            "none_col": None,
            "bool_col": True,
            "bigint_col": 2**62,
        })
        self.assertIsInstance(row["int_col"], int)
        self.assertIsInstance(row["float_col"], float)
        self.assertIsInstance(row["str_col"], str)
        self.assertIsNone(row["none_col"])
        self.assertIsInstance(row["bool_col"], bool)
        self.assertIsInstance(row["bigint_col"], int)
        self.assertEqual(row["bigint_col"], 2**62)

    @patch("db.execute_mysql_query")
    def test_execute_mysql_query_mock_mixed_types(self, mock_exec):
        """
        模拟 execute_mysql_query 返回混合类型数据，
        验证 format_cell 能正确处理各类型值。
        """
        # 模拟 execute_mysql_query 返回 list[dict]（多结果集格式）
        columns = ["id", "name", "score", "memo", "rate", "data"]
        rows = [
            (1, "Alice", 95.5, None, Decimal("3.14159"), b"binary"),
            (2, "Bob", 1e-10, "", Decimal("0"), b""),
            (3, "报表测试", 0.0, "备注", Decimal("-0.001"), b"\xff\x00"),
        ]
        mock_exec.return_value = [{"columns": columns, "rows": rows}]

        # 调用 execute_mysql_query（实际走 mock）
        result_data = db.execute_mysql_query(MagicMock(), "SELECT * FROM t")[0]
        cols, data_rows = result_data["columns"], result_data["rows"]

        # 验证列名正确
        self.assertEqual(cols, columns)

        # 验证每行的每个字段都能被 format_cell 正确格式化
        for row in data_rows:
            for cell in row:
                formatted = format_cell(cell)
                self.assertIsInstance(formatted, str)

        # 验证具体格式化结果
        alice_row = data_rows[0]
        self.assertEqual(format_cell(alice_row[0]), "1")        # int
        self.assertEqual(format_cell(alice_row[1]), "Alice")    # str
        self.assertEqual(format_cell(alice_row[2]), "95.5")     # float
        self.assertEqual(format_cell(alice_row[3]), "")         # None
        self.assertEqual(format_cell(alice_row[4]), "3.14159")  # Decimal

        # 验证中文正确传递
        chinese_row = data_rows[2]
        self.assertEqual(format_cell(chinese_row[1]), "报表测试")

        # 验证科学计数法转为全小数
        bob_row = data_rows[1]
        score_str = format_cell(bob_row[2])
        self.assertNotIn("e", score_str.lower())
        self.assertAlmostEqual(float(score_str), 1e-10)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
