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

    def tearDown(self):
        self.conn.close()
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

    def tearDown(self):
        self.conn.close()

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

    def tearDown(self):
        self.conn.close()

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
                memo TEXT,
                result_names TEXT DEFAULT '',
                prefer_cache INTEGER NOT NULL DEFAULT 1,
                cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0, allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, max_rows INTEGER NOT NULL DEFAULT 100000,
                keepalive_enabled INTEGER NOT NULL DEFAULT 0,
                keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS api_endpoints (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id        INTEGER NOT NULL,
                name             TEXT    NOT NULL,
                url_path         TEXT    NOT NULL,
                output_format    TEXT    NOT NULL DEFAULT 'json',
        nested_filter    TEXT
            );
        """)
        # 插入一个连接池供报表引用
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) VALUES (?,?,?,?,?,?)",
            ("testpool", "h", 3306, "u", "p", "d"),
        )
        self.pool_id = 1

    def tearDown(self):
        self.conn.close()

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

    def test_add_report_with_memo(self):
        """新增报表带备注应正确存储和返回"""
        rid = db.add_report(self.conn, "带备注报表", "SELECT 1", 20, self.pool_id, memo="这是备注内容")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["memo"], "这是备注内容")

    def test_add_report_without_memo(self):
        """新增报表不带备注，memo 应为 None"""
        rid = db.add_report(self.conn, "无备注报表", "SELECT 1", 20, self.pool_id)
        rpt = db.get_report(self.conn, rid)
        self.assertIsNone(rpt["memo"])

    def test_update_report_memo(self):
        """更新报表的备注字段应生效"""
        rid = db.add_report(self.conn, "改备注", "SELECT 1", 20, self.pool_id, memo="旧备注")
        db.update_report(self.conn, rid, "改备注", "SELECT 1", 20, self.pool_id, memo="新备注")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["memo"], "新备注")

    def test_update_report_clear_memo(self):
        """将备注置空应存为 None"""
        rid = db.add_report(self.conn, "清备注", "SELECT 1", 20, self.pool_id, memo="待清除")
        db.update_report(self.conn, rid, "清备注", "SELECT 1", 20, self.pool_id, memo=None)
        rpt = db.get_report(self.conn, rid)
        self.assertIsNone(rpt["memo"])


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
        results = db.execute_mysql_query(conn, "SELECT * FROM t")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["columns"], ["id", "name"])
        self.assertEqual(results[0]["rows"], [(1, "Alice"), (2, "Bob")])
        mock_cursor.execute.assert_called_once_with("SELECT * FROM t", ())

class TestSessionCRUD(unittest.TestCase):
    """Session CRUD 测试"""

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
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


# ---------------------------------------------------------------------------
# 缺口 3：SQLite 侧排序 SQL 正确性（move_* 交换 sort_order）
# ---------------------------------------------------------------------------


class TestSortingSQL(unittest.TestCase):
    """move_pool / move_report / move_category 的 SQLite 排序 SQL 行为"""

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
                parent_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sql_query TEXT NOT NULL,
                default_page_size INTEGER NOT NULL DEFAULT 20,
                pool_id INTEGER,
                category_id INTEGER,
                memo TEXT,
                result_names TEXT DEFAULT '',
                prefer_cache INTEGER NOT NULL DEFAULT 1,
                cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0, allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, max_rows INTEGER NOT NULL DEFAULT 100000, keepalive_enabled INTEGER NOT NULL DEFAULT 0, keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
        """)

    def tearDown(self):
        self.conn.close()

    def test_get_all_sorts_by_sort_order_then_id(self):
        """get_all_pools 排序 SQL：ORDER BY sort_order, id"""
        db.add_pool(self.conn, "b", "h", 3306, "u", "p", "d")
        db.add_pool(self.conn, "a", "h", 3306, "u", "p", "d")
        pools = db.get_all_pools(self.conn)
        self.assertEqual(pools[0]["name"], "b")  # sort_order 1
        self.assertEqual(pools[1]["name"], "a")  # sort_order 2

    def test_get_reports_sorts_by_sort_order(self):
        """get_reports 排序 SQL：同一分类内 ORDER BY sort_order, id"""
        db.add_category(self.conn, "c1")
        db.add_category(self.conn, "c2")
        # 后添加的报表 sort_order 更大，应排在后面
        first = db.add_report(self.conn, "r2", "SELECT 1", 20, None, category_id=1)
        second = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        reports = db.get_reports(self.conn, 1)
        self.assertEqual([r["id"] for r in reports], [first, second])

    def test_move_report_up_swaps_sort_order(self):
        """move_report up 应交换相邻两项 sort_order"""
        db.add_category(self.conn, "c1")
        r1 = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        r2 = db.add_report(self.conn, "r2", "SELECT 1", 20, None, category_id=1)
        ok = db.move_report(self.conn, r2, "up", category_id=1)
        self.assertTrue(ok)
        self.assertEqual(db.get_report(self.conn, r1)["sort_order"], 2)
        self.assertEqual(db.get_report(self.conn, r2)["sort_order"], 1)

    def test_move_report_down_swaps_sort_order(self):
        """move_report down 应交换相邻两项 sort_order"""
        db.add_category(self.conn, "c1")
        r1 = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        r2 = db.add_report(self.conn, "r2", "SELECT 1", 20, None, category_id=1)
        ok = db.move_report(self.conn, r1, "down", category_id=1)
        self.assertTrue(ok)
        self.assertEqual(db.get_report(self.conn, r1)["sort_order"], 2)
        self.assertEqual(db.get_report(self.conn, r2)["sort_order"], 1)

    def test_move_report_first_up_returns_false(self):
        """首个报表 move-up 返回 False 且顺序不变（边界）"""
        db.add_category(self.conn, "c1")
        r1 = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        r2 = db.add_report(self.conn, "r2", "SELECT 1", 20, None, category_id=1)
        before = [r["id"] for r in db.get_reports(self.conn, 1)]
        self.assertFalse(db.move_report(self.conn, r1, "up", category_id=1))
        self.assertEqual([r["id"] for r in db.get_reports(self.conn, 1)], before)

    def test_move_report_last_down_returns_false(self):
        """末尾报表 move-down 返回 False 且顺序不变（边界）"""
        db.add_category(self.conn, "c1")
        r1 = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        r2 = db.add_report(self.conn, "r2", "SELECT 1", 20, None, category_id=1)
        self.assertFalse(db.move_report(self.conn, r2, "down", category_id=1))
        self.assertEqual([r["id"] for r in db.get_reports(self.conn, 1)], [r1, r2])

    def test_move_invalid_direction_returns_false(self):
        """direction 非法值返回 False 且顺序不变（缺字段/非法值场景）"""
        db.add_category(self.conn, "c1")
        r1 = db.add_report(self.conn, "r1", "SELECT 1", 20, None, category_id=1)
        self.assertFalse(db.move_report(self.conn, r1, "sideways", category_id=1))
        self.assertFalse(db.move_report(self.conn, r1, "", category_id=1))

    def test_move_report_missing_report_returns_false(self):
        """移动不存在的报表返回 False"""
        db.add_category(self.conn, "c1")
        self.assertFalse(db.move_report(self.conn, 999, "up", category_id=1))

    def test_move_category_up_swaps(self):
        """move_category up 应交换分类 sort_order"""
        db.add_category(self.conn, "c1")
        db.add_category(self.conn, "c2")
        self.assertTrue(db.move_category(self.conn, 2, "up"))
        cats = db.get_all_categories(self.conn)
        self.assertEqual([c["id"] for c in cats], [2, 1])

    def test_move_category_parent_scoped_swaps_sibling_not_child(self):
        """多级分类回归：父分类下移只与同级兄弟交换，不与子分类换（原 bug）"""
        db.add_category(self.conn, "财务")
        db.add_category(self.conn, "月报", parent_id=1)
        db.add_category(self.conn, "季报", parent_id=1)
        db.add_category(self.conn, "销售")
        ok = db.move_category(self.conn, 1, "down")
        self.assertTrue(ok)
        self.assertEqual(db.get_category(self.conn, 1)["sort_order"], 4)
        self.assertEqual(db.get_category(self.conn, 4)["sort_order"], 1)
        self.assertEqual(db.get_category(self.conn, 2)["parent_id"], 1)

    def test_move_category_child_scoped_swaps_sibling(self):
        """子分类移动在同父兄弟内交换，不影响其他分类"""
        db.add_category(self.conn, "财务")
        db.add_category(self.conn, "月报", parent_id=1)
        db.add_category(self.conn, "季报", parent_id=1)
        db.add_category(self.conn, "销售")
        ok = db.move_category(self.conn, 2, "down")
        self.assertTrue(ok)
        self.assertEqual(db.get_category(self.conn, 2)["sort_order"], 3)
        self.assertEqual(db.get_category(self.conn, 3)["sort_order"], 2)

    def test_move_category_boundary_scoped_to_parent(self):
        """同父兄弟边界：根级首/末项在兄弟内判定上下移边界"""
        db.add_category(self.conn, "财务")
        db.add_category(self.conn, "月报", parent_id=1)
        db.add_category(self.conn, "销售")
        self.assertFalse(db.move_category(self.conn, 3, "down"))
        self.assertFalse(db.move_category(self.conn, 1, "up"))
        self.assertFalse(db.move_category(self.conn, 2, "up"))

    def test_move_pool_up_swaps(self):
        """move_pool up 应交换连接池 sort_order"""
        db.add_pool(self.conn, "p1", "h", 3306, "u", "p", "d")
        db.add_pool(self.conn, "p2", "h", 3306, "u", "p", "d")
        self.assertTrue(db.move_pool(self.conn, 2, "up"))
        pools = db.get_all_pools(self.conn)
        self.assertEqual([p["id"] for p in pools], [2, 1])


# ---------------------------------------------------------------------------
# 缺口 11：SQLite 迁移覆盖（1/2/3/4/5/6/7/8/9/10/11/12/13）与失败回滚
# ---------------------------------------------------------------------------


def _create_legacy_schema(conn, with_pool_notnull=False):
    """创建最旧版 SQLite 库（缺失后续迁移引入的表/列）。

    with_pool_notnull=True 时 report_configs.pool_id 为 NOT NULL（迁移 1 场景）。
    """
    conn.executescript("""
        CREATE TABLE connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL,
            password TEXT NOT NULL,
            database TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL);
    """)
    pool_col = "pool_id INTEGER NOT NULL" if with_pool_notnull else "pool_id INTEGER"
    conn.execute(f"""
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL,
            default_page_size INTEGER NOT NULL DEFAULT 20,
            {pool_col},
            sort_order INTEGER NOT NULL DEFAULT 0, allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, max_rows INTEGER NOT NULL DEFAULT 100000, keepalive_enabled INTEGER NOT NULL DEFAULT 0, keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0)""")
    conn.commit()


def _table_info(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


class TestSQLiteMigrations(unittest.TestCase):
    """_init_sqlite_migrations 各迁移号行为"""

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        self.engine_patcher.stop()

    def test_migration_1_rebuilds_notnull_pool_id(self):
        """迁移 1：旧版 pool_id NOT NULL 时应重建为可空"""
        _create_legacy_schema(self.conn, with_pool_notnull=True)
        db._init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "report_configs")
        # notnull 判定：迁移后 pool_id 不再 NOT NULL
        rows = self.conn.execute("PRAGMA table_info(report_configs)").fetchall()
        pool_row = next(r for r in rows if r[1] == "pool_id")
        self.assertEqual(pool_row[3], 0)

    def test_migration_2_adds_category_id(self):
        """迁移 2：report_configs 缺 category_id 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("category_id", _table_info(self.conn, "report_configs"))

    def test_migration_3_creates_categories_table(self):
        """迁移 3：缺 report_categories 表时应创建"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("report_categories", tables)

    def test_migration_4_adds_parent_id(self):
        """迁移 4：report_categories 缺 parent_id 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("parent_id", _table_info(self.conn, "report_categories"))

    def test_migration_5_adds_memo(self):
        """迁移 5：report_configs 缺 memo 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("memo", _table_info(self.conn, "report_configs"))

    def test_migration_6_adds_result_names(self):
        """迁移 6：report_configs 缺 result_names 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("result_names", _table_info(self.conn, "report_configs"))

    def test_migration_7_adds_cache_columns(self):
        """迁移 7：prefer_cache / cache_ttl_hours 缺时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "report_configs")
        self.assertIn("prefer_cache", cols)
        self.assertIn("cache_ttl_hours", cols)

    def test_migration_8_creates_api_endpoints_table(self):
        """迁移 8：缺 api_endpoints 表时应创建"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("api_endpoints", tables)

    def test_migration_9_adds_result_mode_index(self):
        """迁移 9：api_endpoints 缺 result_mode / result_index 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "api_endpoints")
        self.assertIn("result_mode", cols)
        self.assertIn("result_index", cols)

    def test_migration_10_adds_allow_fetch_all(self):
        """迁移 10：api_endpoints 缺 allow_fetch_all 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("allow_fetch_all", _table_info(self.conn, "api_endpoints"))

    def test_migration_11_adds_static_cache(self):
        """迁移 11：api_endpoints 缺 static_cache 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        self.assertIn("static_cache", _table_info(self.conn, "api_endpoints"))

    def test_migration_12_13_add_json_template_description(self):
        """迁移 12/13：api_endpoints 缺 json_template / description 时应补充"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "api_endpoints")
        self.assertIn("json_template", cols)
        self.assertIn("description", cols)

    def test_migrations_preserve_existing_data(self):
        """迁移不破坏存量数据（报表行保留）"""
        _create_legacy_schema(self.conn)
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size) "
            "VALUES (?,?,?)", ("存量报表", "SELECT 1", 20))
        self.conn.commit()
        db._init_sqlite_migrations(self.conn)
        rows = self.conn.execute(
            "SELECT name, sql_query FROM report_configs").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "存量报表")

    def test_migration_idempotent_on_new_schema(self):
        """新库上重复执行迁移应幂等"""
        _create_legacy_schema(self.conn)
        db._init_sqlite_migrations(self.conn)
        db._init_sqlite_migrations(self.conn)  # 第二次不抛异常
        db._init_sqlite_migrations(self.conn)


class _AlterFailProxy:
    """包装 sqlite3.Connection 的代理连接：ALTER TABLE 时抛异常、记录 rollback。

    sqlite3.Connection 的 execute/rollback 是 C 层只读属性，无法直接替换，
    通过 __getattr__ 委托 + 覆写目标方法实现模拟迁移失败。
    """

    def __init__(self, real: sqlite3.Connection, fail_alter: bool = True):
        self._real = real
        self.fail_alter = fail_alter
        self.rollback_count = 0
        self.alter_attempts = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def execute(self, sql, *args):
        if self.fail_alter and str(sql).strip().upper().startswith("ALTER TABLE"):
            self.alter_attempts += 1
            raise sqlite3.OperationalError("模拟迁移失败")
        return self._real.execute(sql, *args)

    def rollback(self):
        self.rollback_count += 1
        return self._real.rollback()


class TestSQLiteMigrationRollback(unittest.TestCase):
    """迁移失败回滚：ALTER TABLE 异常时应 rollback 并继续，不崩溃"""

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        self.engine_patcher.stop()

    def test_alter_failure_rolls_back_and_continues(self):
        """迁移 2 的 ALTER 失败：应调用 rollback 且后续迁移继续执行"""
        _create_legacy_schema(self.conn)
        proxy = _AlterFailProxy(self.conn, fail_alter=True)

        # 不应抛出异常
        db._init_sqlite_migrations(proxy)

        self.assertGreater(proxy.alter_attempts, 0, "应触发 ALTER 失败")
        self.assertGreater(proxy.rollback_count, 0, "ALTER 失败应触发 rollback")
        # 失败后继续：迁移 3 仍创建了 report_categories 表
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("report_categories", tables)

    def test_migration_1_rebuild_keeps_working_after_alter_failure(self):
        """ALTER 全部失败的极端场景下迁移仍不崩溃（逐条 try/except 隔离）"""
        _create_legacy_schema(self.conn)
        proxy = _AlterFailProxy(self.conn, fail_alter=True)
        db._init_sqlite_migrations(proxy)
        # 表仍可查询（结构不完整但不崩溃）
        self.conn.execute("SELECT COUNT(*) FROM report_configs").fetchone()


# ===================================================================
# 批次2 删除安全（spec ux-optimization）：db 层级联与计数原语
# ===================================================================

class TestDeletionSafetyDb(unittest.TestCase):
    """delete_report 级联对齐 batch_delete_reports + 计数辅助函数。

    缺陷背景：单删报表不清理 api_endpoints，遗留孤儿端点让 API 调用方
    500（批量删却有完整级联——两条路径语义不一致）。
    """

    def setUp(self):
        self.engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self.engine_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)
        self.pool_id = db.add_pool(self.conn, "池", host="h", port=3306,
                                   user="u", password="p", database="d")

    def tearDown(self):
        self.conn.close()
        self.engine_patcher.stop()

    def _make_report_with_endpoints(self, n=2, url_paths=None):
        rid = db.add_report(self.conn, "报表A", "SELECT 1", 20, self.pool_id)
        for i in range(n):
            path = (url_paths[i] if url_paths else f"/api/r{rid}_{i}.json")
            db.add_api_endpoint(self.conn, rid, f"ep{i}", path,
                                output_format="json")
        return rid

    def test_delete_report_cascades_endpoints(self):
        """批次2#5：单删报表应一并删除其 API 端点"""
        rid = self._make_report_with_endpoints(2)
        self.assertTrue(db.delete_report(self.conn, rid))
        left = self.conn.execute(
            "SELECT COUNT(*) FROM api_endpoints WHERE report_id=?",
            (rid,)).fetchone()[0]
        self.assertEqual(left, 0)

    def test_delete_report_without_endpoints_ok(self):
        """无端点报表删除不受影响"""
        rid = db.add_report(self.conn, "裸报表", "SELECT 1", 20, self.pool_id)
        self.assertTrue(db.delete_report(self.conn, rid))

    def test_delete_report_still_cascades_schedules(self):
        """回归保护：原有 schedules 绑定级联保持（schedule_reports 绑定表）"""
        rid = self._make_report_with_endpoints(0)
        cur = self.conn.execute(
            "INSERT INTO report_schedules (name, schedule_type,"
            " interval_minutes, misfire_policy, enabled)"
            " VALUES ('任务', 'interval', 60, 'skip', 0)")
        sid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO schedule_reports (schedule_id, report_id)"
            " VALUES (?, ?)", (sid, rid))
        self.conn.commit()
        db.delete_report(self.conn, rid)
        left = self.conn.execute(
            "SELECT COUNT(*) FROM schedule_reports WHERE report_id=?",
            (rid,)).fetchone()[0]
        self.assertEqual(left, 0)

    def test_count_reports_by_pool(self):
        """批次2#6：按连接池聚合报表数（NULL pool 不计入）"""
        r1 = db.add_report(self.conn, "R1", "SELECT 1", 20, self.pool_id)
        db.add_report(self.conn, "R2", "SELECT 1", 20, self.pool_id)
        other_pool = db.add_pool(self.conn, "池B", host="h2", port=3307,
                                 user="u", password="p", database="d")
        db.add_report(self.conn, "R3", "SELECT 1", 20, other_pool)
        # 无池报表（pool_id NULL）
        self.conn.execute("UPDATE report_configs SET pool_id=NULL WHERE id=?",
                          (r1,))
        self.conn.commit()
        counts = db.count_reports_by_pool(self.conn)
        self.assertEqual(counts.get(self.pool_id), 1)
        self.assertEqual(counts.get(other_pool), 1)
        self.assertNotIn(None, counts)

    def test_count_reports_by_pool_empty(self):
        self.assertEqual(db.count_reports_by_pool(self.conn), {})

    def test_delete_sessions_for_user(self):
        """批次2#7：按用户名清除持久层会话，返回行数"""
        db.add_session(self.conn, "tok-a", "alice")
        db.add_session(self.conn, "tok-b", "alice")
        db.add_session(self.conn, "tok-c", "bob")
        removed = db.delete_sessions_for_user(self.conn, "alice")
        self.assertEqual(removed, 2)
        remaining = {r["username"] for r in db.get_all_sessions(self.conn)}
        self.assertEqual(remaining, {"bob"})

    def test_delete_sessions_for_user_none(self):
        self.assertEqual(db.delete_sessions_for_user(self.conn, "ghost"), 0)


if __name__ == "__main__":
    unittest.main()
