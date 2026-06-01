"""
test_db.py — db.py 单元测试

测试策略：
- 使用 :memory: SQLite 内存库，每个测试独立，互不干扰
- MySQL 相关函数使用 mock，避免真实数据库依赖
"""

import unittest
from unittest.mock import patch, MagicMock
import sqlite3
import db


class TestInitDB(unittest.TestCase):
    """测试数据库初始化"""

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        # 重置全局标志，允许重复初始化
        db._initialized = False

    def tearDown(self):
        self.conn.close()
        db._initialized = False
        self.engine_patcher.stop()

    def test_init_db_creates_tables(self):
        """init_db 应创建所有配置表"""
        db.init_db(self.conn)
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [r[0] for r in tables]
        self.assertIn("connection_pools", table_names)
        self.assertIn("users", table_names)
        self.assertIn("report_configs", table_names)
        self.assertIn("sessions", table_names)

    def test_init_db_idempotent(self):
        """重复调用 init_db 不应报错"""
        db.init_db(self.conn)
        db.init_db(self.conn)  # 第二次不应抛异常


class TestConnectionPoolCRUD(unittest.TestCase):
    """连接池 CRUD 测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
            CREATE TABLE connection_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 3306,
                user TEXT NOT NULL,
                password TEXT NOT NULL,
                database TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
        """)
        db._initialized = True

    def tearDown(self):
        self.conn.close()
        db._initialized = False

    def test_add_and_get_pool(self):
        """新增连接池后应能通过 id 查询到"""
        pid = db.add_pool(self.conn, "mydb", "192.168.1.1", 3306, "root", "secret", "mydb")
        pool = db.get_pool(self.conn, pid)
        self.assertIsNotNone(pool)
        self.assertEqual(pool["name"], "mydb")
        self.assertEqual(pool["host"], "192.168.1.1")

    def test_get_pool_not_found(self):
        """查询不存在的连接池应返回 None"""
        self.assertIsNone(db.get_pool(self.conn, 999))

    def test_add_pool_duplicate_name(self):
        """重复名称应抛异常"""
        db.add_pool(self.conn, "dup", "h", 3306, "u", "p", "d")
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_pool(self.conn, "dup", "h2", 3306, "u2", "p2", "d2")

    def test_get_all_pools(self):
        """get_all_pools 应返回所有记录"""
        db.add_pool(self.conn, "p1", "h1", 3306, "u1", "p1", "d1")
        db.add_pool(self.conn, "p2", "h2", 3306, "u2", "p2", "d2")
        pools = db.get_all_pools(self.conn)
        self.assertEqual(len(pools), 2)

    def test_update_pool(self):
        """更新连接池应修改字段并返回 True"""
        pid = db.add_pool(self.conn, "old", "h", 3306, "u", "p", "d")
        ok = db.update_pool(self.conn, pid, "new", "h2", 3307, "u2", "p2", "d2")
        self.assertTrue(ok)
        pool = db.get_pool(self.conn, pid)
        self.assertEqual(pool["name"], "new")
        self.assertEqual(pool["port"], 3307)

    def test_update_pool_not_found(self):
        """更新不存在的连接池应返回 False"""
        ok = db.update_pool(self.conn, 999, "x", "x", 3306, "x", "x", "x")
        self.assertFalse(ok)

    def test_delete_pool(self):
        """删除连接池应返回 True 且后续查询为 None"""
        pid = db.add_pool(self.conn, "del", "h", 3306, "u", "p", "d")
        ok = db.delete_pool(self.conn, pid)
        self.assertTrue(ok)
        self.assertIsNone(db.get_pool(self.conn, pid))

    def test_delete_pool_not_found(self):
        """删除不存在的连接池应返回 False"""
        self.assertFalse(db.delete_pool(self.conn, 999))


class TestUserCRUD(unittest.TestCase):
    """用户 CRUD 测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        """)
        db._initialized = True

    def tearDown(self):
        self.conn.close()
        db._initialized = False

    def test_add_and_get_user(self):
        """新增用户后应能通过用户名查询到"""
        uid = db.add_user(self.conn, "alice", "hash123")
        user = db.get_user(self.conn, "alice")
        self.assertIsNotNone(user)
        self.assertEqual(user["password_hash"], "hash123")

    def test_get_user_not_found(self):
        """查询不存在的用户应返回 None"""
        self.assertIsNone(db.get_user(self.conn, "nobody"))

    def test_get_all_users(self):
        db.add_user(self.conn, "u1", "h1")
        db.add_user(self.conn, "u2", "h2")
        users = db.get_all_users(self.conn)
        self.assertEqual(len(users), 2)

    def test_update_user(self):
        uid = db.add_user(self.conn, "old", "hash1")
        ok = db.update_user(self.conn, uid, "new", "hash2")
        self.assertTrue(ok)
        user = db.get_user(self.conn, "new")
        self.assertEqual(user["password_hash"], "hash2")

    def test_delete_user(self):
        uid = db.add_user(self.conn, "del", "h")
        self.assertTrue(db.delete_user(self.conn, uid))
        self.assertIsNone(db.get_user(self.conn, "del"))


class TestReportCRUD(unittest.TestCase):
    """报表配置 CRUD 测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
            CREATE TABLE connection_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 3306,
                user TEXT NOT NULL,
                password TEXT NOT NULL,
                database TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE report_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sql_query TEXT NOT NULL,
                default_page_size INTEGER NOT NULL DEFAULT 20,
                pool_id INTEGER,
                category_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
            );
        """)
        # 插入一个连接池供报表引用
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) VALUES (?,?,?,?,?,?)",
            ("testpool", "h", 3306, "u", "p", "d"),
        )
        self.pool_id = 1
        db._initialized = True

    def tearDown(self):
        self.conn.close()
        db._initialized = False

    def test_add_and_get_report(self):
        rid = db.add_report(self.conn, "报表A", "SELECT * FROM t", 20, self.pool_id)
        rpt = db.get_report(self.conn, rid)
        self.assertIsNotNone(rpt)
        self.assertEqual(rpt["name"], "报表A")
        self.assertEqual(rpt["default_page_size"], 20)

    def test_get_all_reports(self):
        db.add_report(self.conn, "r1", "SELECT 1", 10, self.pool_id)
        db.add_report(self.conn, "r2", "SELECT 2", 50, self.pool_id)
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 2)

    def test_update_report(self):
        rid = db.add_report(self.conn, "old", "SELECT 1", 10, self.pool_id)
        ok = db.update_report(self.conn, rid, "new", "SELECT 2", 50, self.pool_id)
        self.assertTrue(ok)
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["name"], "new")
        self.assertEqual(rpt["default_page_size"], 50)

    def test_delete_report(self):
        rid = db.add_report(self.conn, "del", "SELECT 1", 10, self.pool_id)
        self.assertTrue(db.delete_report(self.conn, rid))
        self.assertIsNone(db.get_report(self.conn, rid))

    def test_report_cascade_on_pool_delete(self):
        """删除连接池后，关联报表的 pool_id 应被置空，报表本身保留"""
        rid = db.add_report(self.conn, "cascade", "SELECT 1", 10, self.pool_id)
        self.conn.execute("DELETE FROM connection_pools WHERE id=?", (self.pool_id,))
        self.conn.commit()
        rpt = db.get_report(self.conn, rid)
        self.assertIsNotNone(rpt, "报表应保留，不应被级联删除")
        self.assertIsNone(rpt["pool_id"], "pool_id 应被置空")


class TestMySQLManager(unittest.TestCase):
    """MySQL 连接管理测试（使用 mock 避免真实数据库）"""

    @patch("db.create_mysql_connection")
    def test_execute_mysql_query(self, mock_create_conn):
        """execute_mysql_query 应返回列名和数据行"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        mock_create_conn.return_value = mock_conn

        conn = db.create_mysql_connection({"host": "h", "port": 3306, "user": "u",
                                           "password": "p", "database": "d"})
        columns, rows = db.execute_mysql_query(conn, "SELECT * FROM t")
        self.assertEqual(columns, ["id", "name"])
        self.assertEqual(rows, [(1, "Alice"), (2, "Bob")])
        mock_cursor.execute.assert_called_once_with("SELECT * FROM t", ())

    @patch("db.create_mysql_connection")
    def test_count_mysql_query(self, mock_create_conn):
        """count_mysql_query 应返回总行数"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (42,)
        mock_create_conn.return_value = mock_conn

        conn = db.create_mysql_connection({"host": "h", "port": 3306, "user": "u",
                                           "password": "p", "database": "d"})
        count = db.count_mysql_query(conn, "SELECT * FROM t")
        self.assertEqual(count, 42)

    @patch("db.create_mysql_connection")
    def test_count_mysql_query_trailing_semicolon(self, mock_create_conn):
        """SQL 末尾带分号时 count 应正确去除"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (7,)
        mock_create_conn.return_value = mock_conn

        conn = db.create_mysql_connection({"host": "h", "port": 3306, "user": "u",
                                           "password": "p", "database": "d"})
        count = db.count_mysql_query(conn, "SELECT * FROM D1;")
        self.assertEqual(count, 7)
        # 验证 SQL 中不含分号
        call_sql = mock_cursor.execute.call_args[0][0]
        self.assertNotIn(";)", call_sql)
        self.assertIn("D1) AS _sub", call_sql)


class TestSessionCRUD(unittest.TestCase):
    """Session CRUD 测试"""

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        db._initialized = False
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        db._initialized = False
        self.engine_patcher.stop()

    def test_add_and_get_session(self):
        """添加 session 后应能通过 token 查询到用户名"""
        db.add_session(self.conn, "tok1", "alice")
        username = db.get_session(self.conn, "tok1")
        self.assertEqual(username, "alice")

    def test_get_nonexistent_session(self):
        """不存在的 token 应返回 None"""
        self.assertIsNone(db.get_session(self.conn, "nonexistent"))

    def test_remove_session(self):
        """删除 session 后查询应返回 None"""
        db.add_session(self.conn, "tok2", "bob")
        db.remove_session(self.conn, "tok2")
        self.assertIsNone(db.get_session(self.conn, "tok2"))

    def test_remove_nonexistent_session(self):
        """删除不存在的 session 应返回 False"""
        self.assertFalse(db.remove_session(self.conn, "ghost"))

    def test_get_all_sessions(self):
        """get_all_sessions 应返回所有未过期 session"""
        db.add_session(self.conn, "tok_a", "alice")
        db.add_session(self.conn, "tok_b", "bob")
        sessions = db.get_all_sessions(self.conn)
        tokens = {s["token"] for s in sessions}
        self.assertIn("tok_a", tokens)
        self.assertIn("tok_b", tokens)

    def test_clear_sessions(self):
        """清空后所有 session 应不可见"""
        db.add_session(self.conn, "tok_x", "charlie")
        db.clear_sessions(self.conn)
        self.assertIsNone(db.get_session(self.conn, "tok_x"))
        self.assertEqual(len(db.get_all_sessions(self.conn)), 0)

    def test_expired_session_returns_none(self):
        """过期的 session（超过 86400 秒）应返回 None"""
        import time
        past = time.time() - 90000
        self.conn.execute(
            "INSERT INTO sessions (token, username, created_at) VALUES (?,?,?)",
            ("expired_tok", "old_user", past),
        )
        self.conn.commit()
        self.assertIsNone(db.get_session(self.conn, "expired_tok"))

    def test_add_and_get_session(self):
        """添加 session 后应能通过 token 查询到用户名"""
        db.add_session(self.conn, "tok1", "alice")
        username = db.get_session(self.conn, "tok1")
        self.assertEqual(username, "alice")

    def test_get_nonexistent_session(self):
        """不存在的 token 应返回 None"""
        self.assertIsNone(db.get_session(self.conn, "nonexistent"))

    def test_remove_session(self):
        """删除 session 后查询应返回 None"""
        db.add_session(self.conn, "tok2", "bob")
        db.remove_session(self.conn, "tok2")
        self.assertIsNone(db.get_session(self.conn, "tok2"))

    def test_remove_nonexistent_session(self):
        """删除不存在的 session 应返回 False"""
        self.assertFalse(db.remove_session(self.conn, "ghost"))

    def test_get_all_sessions(self):
        """get_all_sessions 应返回所有未过期 session"""
        db.add_session(self.conn, "tok_a", "alice")
        db.add_session(self.conn, "tok_b", "bob")
        sessions = db.get_all_sessions(self.conn)
        tokens = {s["token"] for s in sessions}
        self.assertIn("tok_a", tokens)
        self.assertIn("tok_b", tokens)

    def test_clear_sessions(self):
        """清空后所有 session 应不可见"""
        db.add_session(self.conn, "tok_x", "charlie")
        db.clear_sessions(self.conn)
        self.assertIsNone(db.get_session(self.conn, "tok_x"))
        self.assertEqual(len(db.get_all_sessions(self.conn)), 0)

    def test_expired_session_returns_none(self):
        """过期的 session（超过 86400 秒）应返回 None"""
        import time
        # 写入一个过去 90000 秒（~25h）的 session
        past = time.time() - 90000
        self.conn.execute(
            "INSERT INTO sessions (token, username, created_at) VALUES (?,?,?)",
            ("expired_tok", "old_user", past),
        )
        self.conn.commit()
        self.assertIsNone(db.get_session(self.conn, "expired_tok"))


if __name__ == "__main__":
    unittest.main()
