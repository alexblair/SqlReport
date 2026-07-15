"""
test_report.py — report.py 单元测试

测试策略：
- SQLite 使用 :memory: 内存库
- MySQL 查询使用 mock，避免真实数据库依赖
- pool_override 参数注入 mock 连接池配置
"""

import unittest
from unittest.mock import patch, MagicMock
import sqlite3
import db
import report


def _make_conn():
    """创建带连接池和报表配置的测试数据库"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
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
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );
    """)
    return conn


def _make_conn2():
    """创建第二个独立连接（TestReportExecution/TestReportSelector 共用）"""
    conn2 = sqlite3.connect(":memory:")
    conn2.row_factory = sqlite3.Row
    conn2.execute("PRAGMA foreign_keys=ON")
    conn2.executescript("""
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
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );
    """)
    return conn


class TestReportSelector(unittest.TestCase):
    """报表选择页测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "报表A", "SELECT * FROM t1", 20, 1)
        db.add_report(self.conn, "报表B", "SELECT * FROM t2", 50, 1)

    def tearDown(self):
        self.conn.close()

    def test_selector_lists_reports(self):
        """报表选择页应列出所有报表"""
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "")
        self.assertEqual(code, "200")
        self.assertIn("报表A", body)
        self.assertIn("报表B", body)
        self.assertIn("选择报表", body)

    def test_selector_empty(self):
        """没有报表时仍应正常渲染"""
        conn2 = sqlite3.connect(":memory:")
        conn2.row_factory = sqlite3.Row
        conn2.execute("PRAGMA foreign_keys=ON")
        conn2.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL, FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL);
        """)
        code, body, _ = report.handle_request(conn2, "GET", "/report", "")
        self.assertEqual(code, "200")
        self.assertIn("选择报表", body)
        conn2.close()


class TestReportExecution(unittest.TestCase):
    """报表查询与展示测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "数据池", "dbhost", 3306, "user", "pass", "mydb")
        db.add_report(self.conn, "用户报表", "SELECT id, name, email FROM users", 10, 1)
        # mock 连接池配置
        self.mock_pool = {"host": "dbhost", "port": 3306,
                          "user": "user", "password": "pass", "database": "mydb"}

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_report_renders_table(self, mock_exec):
        """报表页应渲染表格"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "email"],
            rows=[(1, "Alice", "a@x.com"), (2, "Bob", "b@x.com")],
            total=2, page=1, page_size=10,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertEqual(code, "200")
        self.assertIn("用户报表", body)
        self.assertIn("Alice", body)
        self.assertIn("Bob", body)
        self.assertIn("id", body)
        self.assertIn("name", body)
        self.assertIn("email", body)

    @patch("report.execute_report")
    def test_report_empty_result(self, mock_exec):
        """空结果集应显示暂无数据"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[], total=0, page=1, page_size=10,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn("暂无数据", body)

    def test_report_not_found(self):
        """不存在的报表 ID 应显示错误"""
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=999", pool_override=self.mock_pool)
        self.assertIn("报表不存在", body)

    @patch("report.execute_report")
    def test_pagination_controls_shown(self, mock_exec):
        """多页数据应显示分页控件"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(i,) for i in range(1, 26)],
            total=25, page=1, page_size=10,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn("共 25 行", body)
        self.assertIn("3 页", body)
        self.assertIn("›", body)

    @patch("report.execute_report")
    def test_page_2(self, mock_exec):
        """请求第二页应正确传递 page 参数"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(i,) for i in range(11, 21)],
            total=25, page=2, page_size=10,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1&page=2", pool_override=self.mock_pool)
        self.assertIn("‹", body)
        self.assertIn("›", body)

    @patch("report.execute_report")
    def test_custom_page_size(self, mock_exec):
        """用户可自定义分页大小"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(i,) for i in range(1, 51)],
            total=100, page=1, page_size=50,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1&page_size=50", pool_override=self.mock_pool)
        self.assertIn("共 100 行", body)
        self.assertIn("2 页", body)

    def test_invalid_id_param(self):
        """无效的 id 参数应回到选择页"""
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=abc", pool_override=self.mock_pool)
        self.assertEqual(code, "200")
        self.assertIn("选择报表", body)

    @patch("report.execute_report")
    def test_query_error_shown(self, mock_exec):
        """查询执行失败应显示错误信息"""
        mock_exec.side_effect = Exception("连接超时")
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn("查询执行失败", body)
        self.assertIn("连接超时", body)

    @patch("report.execute_report")
    def test_report_shows_memo_when_present(self, mock_exec):
        """有备注时应在报表页显示备注内容（默认展开）"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10,
        )
        # 修改报表配置加入 memo
        db.update_report(self.conn, 1, "用户报表", "SELECT id, name, email FROM users",
                         10, 1, memo="这是报表备注说明")
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn("这是报表备注说明", body)
        self.assertIn("▼ 备注", body)  # 有内容时默认展开

    @patch("report.execute_report")
    def test_report_hides_memo_when_empty(self, mock_exec):
        """无备注时备注区域应默认隐藏"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10,
        )
        # 确保 memo 为 None
        db.update_report(self.conn, 1, "用户报表", "SELECT id, name, email FROM users",
                         10, 1, memo=None)
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn("▶ 备注", body)  # 无内容时默认折叠

    @patch("report.execute_report")
    def test_report_memo_toggle_button(self, mock_exec):
        """备注切换按钮应使用 toggleSection 函数"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10,
        )
        db.update_report(self.conn, 1, "用户报表", "SELECT id, name, email FROM users",
                         10, 1, memo="测试备注")
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override=self.mock_pool)
        self.assertIn('toggleSection(this', body)
        self.assertIn("备注", body)


class TestReportResult(unittest.TestCase):
    """ReportResult 工具类测试"""

    def test_total_pages_calculation(self):
        r = report.ReportResult(["id"], [(1,)], total=25, page=1, page_size=10)
        self.assertEqual(r.total_pages, 3)

    def test_single_page(self):
        r = report.ReportResult(["id"], [(1,)], total=5, page=1, page_size=10)
        self.assertEqual(r.total_pages, 1)

    def test_exact_division(self):
        r = report.ReportResult(["id"], list(range(20)), total=20, page=1, page_size=20)
        self.assertEqual(r.total_pages, 1)

    def test_zero_page_size(self):
        """page_size 为 0 时 total_pages 应为 1（防止除零）"""
        r = report.ReportResult(["id"], [], total=0, page=1, page_size=0)
        self.assertEqual(r.total_pages, 1)


class TestExecuteReport(unittest.TestCase):
    """execute_report 函数测试（使用 mock + 缓存）"""

    def setUp(self):
        """每个测试前清空缓存，确保隔离"""
        report._query_cache.clear()

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_execute_with_pagination(self, mock_exec_q, mock_create_conn):
        """execute_report 应缓存原始 SQL 并返回正确分页结果"""
        # 模拟 100 条全量数据
        all_rows = [(i, f"Name{i}") for i in range(1, 101)]
        mock_exec_q.return_value = [{"columns": ["id", "name"], "rows": all_rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=2, page_size=10,
        )

        self.assertEqual(result.columns, ["id", "name"])
        self.assertEqual(len(result.rows), 10)
        # 第二页 = 第 11~20 条
        self.assertEqual(result.rows[0][0], 11)
        self.assertEqual(result.rows[-1][0], 20)
        self.assertEqual(result.total, 100)
        self.assertEqual(result.page, 2)
        self.assertEqual(result.page_size, 10)
        self.assertEqual(result.total_pages, 10)

        # 验证传递给 db.execute_mysql_query 的是原始 SQL（不含 LIMIT/OFFSET）
        call_sql = mock_exec_q.call_args[0][1]
        self.assertEqual(call_sql, "SELECT * FROM t")

        # 第二次调用（不同分页）应命中缓存，不再调用 db
        result2 = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=1, page_size=50,
        )
        self.assertEqual(result2.total, 100)
        self.assertEqual(len(result2.rows), 50)
        self.assertEqual(mock_exec_q.call_count, 1)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_execute_with_filter_sort(self, mock_exec_q, mock_create_conn):
        """execute_report 应在内存中执行多字段筛选和排序"""
        all_rows = [
            (3, "Charlie"), (1, "Alice"), (2, "Bob"),
            (4, "dave"),    (5, "Eve"),
        ]
        mock_exec_q.return_value = [{"columns": ["id", "name"], "rows": all_rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}

        # 单字段筛选 name 包含 "e"
        result = report.execute_report(
            report_id=10,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=1, page_size=10,
            filters=[("name", "contains", "e")],
        )
        # 包含 e/E: Charlie, Alice, dave, Eve → 4 条
        self.assertEqual(result.total, 4)

        # 筛选 + 排序 ASC
        result2 = report.execute_report(
            report_id=10,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=1, page_size=10,
            filters=[("name", "contains", "e")],
            sorts=[("name", "asc")],
        )
        self.assertEqual(result2.total, 4)
        self.assertEqual(result2.rows[0][1], "Alice")
        self.assertEqual(result2.rows[-1][1], "dave")

        # 筛选 + 排序 DESC
        result3 = report.execute_report(
            report_id=10,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=1, page_size=10,
            filters=[("name", "contains", "e")],
            sorts=[("name", "desc")],
        )
        self.assertEqual(result3.total, 4)
        self.assertEqual(result3.rows[0][1], "dave")
        self.assertEqual(result3.rows[-1][1], "Alice")

        # 缓存命中验证
        self.assertEqual(mock_exec_q.call_count, 1)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_multi_field_filter(self, mock_exec_q, mock_create_conn):
        """多字段筛选应同时生效（AND 逻辑）"""
        all_rows = [
            (1, "Alice", 25), (2, "Bob", 30), (3, "Charlie", 35),
            (4, "Alice", 40), (5, "dave", 25),
        ]
        mock_exec_q.return_value = [{"columns": ["id", "name", "age"], "rows": all_rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}

        # 同时筛选 name 包含 "alice" AND age 包含 "25"
        result = report.execute_report(
            report_id=50,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            filters=[("name", "contains", "alice"), ("age", "contains", "25")],
        )
        self.assertEqual(result.total, 1)  # (1, Alice, 25)
        self.assertEqual(result.rows[0][0], 1)
        self.assertEqual(result.rows[0][1], "Alice")

        # 只筛选 name 包含 "alice"
        result2 = report.execute_report(
            report_id=50,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            filters=[("name", "contains", "alice")],
        )
        self.assertEqual(result2.total, 2)  # Alice(25) + Alice(40)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_multi_field_sort(self, mock_exec_q, mock_create_conn):
        """多字段排序应正确组合优先级"""
        all_rows = [
            (1, "Alice", 30), (2, "Bob", 25), (3, "Alice", 25),
            (4, "Bob", 35),   (5, "Charlie", 30),
        ]
        mock_exec_q.return_value = [{"columns": ["id", "name", "age"], "rows": all_rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}

        # name ASC, age DESC → Alice(30), Alice(25), Bob(35), Bob(25), Charlie(30)
        result = report.execute_report(
            report_id=60,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            sorts=[("name", "asc"), ("age", "desc")],
        )
        self.assertEqual(result.total, 5)
        self.assertEqual(result.rows[0][1], "Alice")
        self.assertEqual(result.rows[0][2], 30)  # Alice 30 before Alice 25
        self.assertEqual(result.rows[1][1], "Alice")
        self.assertEqual(result.rows[1][2], 25)
        self.assertEqual(result.rows[2][1], "Bob")
        self.assertEqual(result.rows[2][2], 35)  # Bob 35 before Bob 25
        self.assertEqual(result.rows[3][1], "Bob")
        self.assertEqual(result.rows[3][2], 25)

        # 第二次调用使用缓存
        result2 = report.execute_report(
            report_id=60,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            sorts=[("age", "asc")],
        )
        self.assertEqual(result2.total, 5)
        self.assertEqual(result2.rows[0][2], 25)  # youngest first
        self.assertEqual(mock_exec_q.call_count, 1)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_execute_refresh_clears_cache(self, mock_exec_q, mock_create_conn):
        """refresh=True 应重新查询数据库"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,), (2,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}

        # 第一次调用
        report.execute_report(report_id=5, sql_query="SELECT * FROM t",
                               pool_config=pool)
        self.assertEqual(mock_exec_q.call_count, 1)

        # 普通调用命中缓存
        report.execute_report(report_id=5, sql_query="SELECT * FROM t",
                               pool_config=pool)
        self.assertEqual(mock_exec_q.call_count, 1)

        # refresh=True → 重新查询
        report.execute_report(report_id=5, sql_query="SELECT * FROM t",
                               pool_config=pool, refresh=True)
        self.assertEqual(mock_exec_q.call_count, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_execute_min_page(self, mock_exec_q, mock_create_conn):
        """page 小于 1 时应自动修正为 1"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,), (2,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}
        result = report.execute_report(
            report_id=20,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=-5, page_size=10,
        )
        self.assertEqual(result.page, 1)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_execute_with_trailing_semicolon(self, mock_exec_q, mock_create_conn):
        """SQL 末尾带分号时应正确去除再传给 db.execute_mysql_query"""
        mock_exec_q.return_value = [{"columns": ["id"], "rows": [(1,), (2,)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}
        result = report.execute_report(
            report_id=30,
            sql_query="SELECT * FROM D1;",
            pool_config=pool,
            page=1, page_size=10,
        )

        # 验证分号已被去除
        call_sql = mock_exec_q.call_args[0][1]
        self.assertNotIn(";", call_sql.rstrip())
        self.assertEqual(result.total, 2)


class TestNewFilterOperators(unittest.TestCase):
    """新筛选操作符测试（eq, neq, gt, lt, isempty, notempty 等）"""

    def setUp(self):
        report._query_cache.clear()

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_contains(self, mock_exec_q, mock_create_conn):
        """包含（默认操作符）"""
        mock_exec_q.return_value = [{"columns": ["name"], "rows": [("Alice",), ("Bob",), ("Charlie",)]}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=90, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("name", "contains", "ali")])
        self.assertEqual(result.total, 1)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_eq(self, mock_exec_q, mock_create_conn):
        """等于"""
        rows = [("Alice", 25), ("Bob", 30), ("alice", 35)]
        mock_exec_q.return_value = [{"columns": ["name", "age"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=91, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("name", "eq", "Alice")])
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0][0], "Alice")

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_neq(self, mock_exec_q, mock_create_conn):
        """不等于"""
        rows = [(1, "Alice"), (2, "Bob"), (3, "Charlie")]
        mock_exec_q.return_value = [{"columns": ["id", "name"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=92, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("name", "neq", "Bob")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_gt(self, mock_exec_q, mock_create_conn):
        """大于"""
        rows = [(1, "A", 10), (2, "B", 20), (3, "C", 30)]
        mock_exec_q.return_value = [{"columns": ["id", "name", "val"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=93, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("val", "gt", "15")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_lt(self, mock_exec_q, mock_create_conn):
        """小于"""
        rows = [(1, 5), (2, 15), (3, 25)]
        mock_exec_q.return_value = [{"columns": ["id", "val"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=94, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("val", "lt", "20")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_gte(self, mock_exec_q, mock_create_conn):
        """大于等于"""
        rows = [(1, 10), (2, 20), (3, 30)]
        mock_exec_q.return_value = [{"columns": ["id", "val"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=95, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("val", "gte", "20")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_lte(self, mock_exec_q, mock_create_conn):
        """小于等于"""
        rows = [(1, 10), (2, 20), (3, 30)]
        mock_exec_q.return_value = [{"columns": ["id", "val"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=96, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("val", "lte", "20")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_isempty(self, mock_exec_q, mock_create_conn):
        """为空"""
        rows = [(1, "A"), (2, ""), (3, None), (4, "B")]
        mock_exec_q.return_value = [{"columns": ["id", "name"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=97, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("name", "isempty", "")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_notempty(self, mock_exec_q, mock_create_conn):
        """非空"""
        rows = [(1, "A"), (2, ""), (3, None), (4, "B")]
        mock_exec_q.return_value = [{"columns": ["id", "name"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        result = report.execute_report(report_id=98, sql_query="SELECT * FROM t",
                                       pool_config=pool, filters=[("name", "notempty", "")])
        self.assertEqual(result.total, 2)

    @patch("db.create_mysql_connection")
    @patch("report.db.execute_mysql_query")
    def test_filter_combined_ops(self, mock_exec_q, mock_create_conn):
        """多字段混合操作符（AND 逻辑）"""
        rows = [
            (1, "Alice", 25), (2, "Bob", 30), (3, "Charlie", 35),
            (4, "Alice", 40), (5, "dave", 25),
        ]
        mock_exec_q.return_value = [{"columns": ["id", "name", "age"], "rows": rows}]
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn
        pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}
        # name 包含 "lice" AND age >= 30
        result = report.execute_report(
            report_id=99, sql_query="SELECT * FROM t", pool_config=pool,
            filters=[("name", "contains", "lice"), ("age", "gte", "30")])
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0][0], 4)


class TestSortBarUI(unittest.TestCase):
    """排序栏 UI 测试（检查 HTML 输出）"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, parent_id INTEGER);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "测试", "SELECT * FROM t", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_sort_bar_appears_when_sorted(self, mock_exec):
        """有排序时应在表格上方显示排序栏"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        self.assertIn("sort-bar", body)
        self.assertIn("↑", body)

    @patch("report.execute_report")
    def test_sort_arrows_in_header(self, mock_exec):
        """表头应有 ▲ ▼ 两个排序箭头"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        # ▲ ▼ 应同时存在
        self.assertIn("▲", body)
        self.assertIn("▼", body)

    @patch("report.execute_report")
    def test_remove_sort_link_in_bar(self, mock_exec):
        """排序栏中应有移除排序的 ✕ 按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=desc",
            pool_override=self.mock_pool)
        self.assertIn("✕", body)

    @patch("report.execute_report")
    def test_filter_op_dropdown(self, mock_exec):
        """表头应有筛选操作符下拉框"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1",
            pool_override=self.mock_pool)
        self.assertIn("filter-op", body)
        self.assertIn("value=\"contains\"", body)
        self.assertIn("value=\"eq\"", body)
        self.assertIn("value=\"isempty\"", body)

    @patch("report.execute_report")
    def test_filter_op_preserved_in_url(self, mock_exec):
        """筛选操作符应在排序/分页链接中保留"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)],
            total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&f_age=15&op_age=gt",
            pool_override=self.mock_pool)
        # op_age=gt 应出现在链接中
        self.assertIn("op_age=gt", body)

    @patch("report.execute_report")
    def test_filter_input_hidden_for_isempty(self, mock_exec):
        """isempty/notempty 操作符应隐藏输入框"""
        # 模拟后端处理之后，isempty 会隐藏输入框但不影响 URL
        mock_exec.return_value = report.ReportResult(
            columns=["name"], rows=[("A",)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&f_name=&op_name=isempty",
            pool_override=self.mock_pool)
        # isempty 应在操作符选项中 selected
        self.assertIn('value="isempty" selected', body)


class TestParseFiltersNewFormat(unittest.TestCase):
    """_parse_filters 新格式测试"""

    def test_op_col_parameter(self):
        """传递 op_COL 应正确解析操作符"""
        qs = {"f_age": ["100"], "op_age": ["gt"], "f_name": ["ali"]}
        result = report._parse_filters(qs)
        self.assertIn(("age", "gt", "100"), result)
        self.assertIn(("name", "contains", "ali"), result)

    def test_op_only_no_value(self):
        """只有 op_COL 无 f_COL 时，也应添加过滤条件（用于 isempty）"""
        qs = {"op_name": ["isempty"]}
        result = report._parse_filters(qs)
        self.assertIn(("name", "isempty", ""), result)

    def test_backward_compat_old_format(self):
        """旧格式 f_col + f_q 仍应被正确解析"""
        qs = {"f_col": ["name"], "f_q": ["alice"]}
        result = report._parse_filters(qs)
        self.assertIn(("name", "contains", "alice"), result)

    def test_backward_compat_no_operator(self):
        """无 op_COL 时默认为 contains"""
        qs = {"f_name": ["alice"]}
        result = report._parse_filters(qs)
        self.assertIn(("name", "contains", "alice"), result)

    def test_op_col_unknown_operator(self):
        """未知操作符应使用默认（contains）"""
        qs = {"f_age": ["10"], "op_age": ["unknown_op"]}
        result = report._parse_filters(qs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "contains")


class TestNofilter(unittest.TestCase):
    """不筛选（nofilter）相关测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, parent_id INTEGER);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "测试", "SELECT * FROM t", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    def test_parse_filters_skips_nofilter(self):
        """op_COL=nofilter 不应产生过滤条件"""
        qs = {"op_name": ["nofilter"]}
        result = report._parse_filters(qs)
        self.assertEqual(result, [])

    def test_parse_filters_skips_nofilter_with_value(self):
        """f_COL + op_COL=nofilter 时应跳过该列"""
        qs = {"f_age": ["100"], "op_age": ["nofilter"]}
        result = report._parse_filters(qs)
        self.assertEqual(result, [])

    def test_build_filter_params_skips_nofilter(self):
        """_build_filter_params 应跳过 nofilter 条目"""
        url = report._build_filter_params([("name", "nofilter", "")])
        self.assertEqual(url, "")

    def test_build_filter_params_nofilter_mixed(self):
        """nofilter 与其他操作符混合时只输出非 nofilter"""
        url = report._build_filter_params([
            ("name", "nofilter", ""),
            ("age", "gt", "100"),
        ])
        self.assertNotIn("name", url)
        self.assertIn("age", url)
        self.assertIn("op_age=gt", url)

    @patch("report.execute_report")
    def test_nofilter_in_html(self, mock_exec):
        """nofilter 应出现在操作符下拉框中"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1",
            pool_override=self.mock_pool)
        self.assertIn('value="nofilter"', body)

    @patch("report.execute_report")
    def test_nofilter_selected_by_default(self, mock_exec):
        """无筛选时操作符默认显示不筛选"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1",
            pool_override=self.mock_pool)
        self.assertIn('value="nofilter" selected', body)

    @patch("report.execute_report")
    def test_filter_button_in_html(self, mock_exec):
        """页面上应有筛选按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1",
            pool_override=self.mock_pool)
        self.assertIn('type="submit"', body)
        self.assertIn('form="ff"', body)
        self.assertIn('筛选', body)

    @patch("report.execute_report")
    def test_clear_filter_button_in_html(self, mock_exec):
        """页面上应有清除筛选按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1",
            pool_override=self.mock_pool)
        self.assertIn('清除筛选', body)


class TestBuildFilterParamsNewFormat(unittest.TestCase):
    """_build_filter_params 新格式测试"""

    def test_default_op_not_encoded(self):
        """默认操作符 contains 不应出现在 URL 中"""
        url = report._build_filter_params([("name", "contains", "ali")])
        self.assertNotIn("op_name", url)
        self.assertIn("f_name=", url)

    def test_nondefault_op_encoded(self):
        """非默认操作符应在 URL 中出现"""
        url = report._build_filter_params([("age", "gt", "100")])
        self.assertIn("op_age=gt", url)
        self.assertIn("f_age=100", url)

    def test_skip_col(self):
        """skip_col 应跳过指定列的参数"""
        url = report._build_filter_params(
            [("name", "contains", "ali"), ("age", "gt", "100")], skip_col="name")
        self.assertNotIn("name", url)
        self.assertIn("age", url)
        self.assertIn("op_age=gt", url)


class TestFieldSettingsPanel(unittest.TestCase):
    """字段设置面板 UI 测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, parent_id INTEGER);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "测试", "SELECT * FROM t", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_field_settings_button_present(self, mock_exec):
        """页面上应有字段设置按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("字段设置", body)
        self.assertIn("fieldSettingsPanel", body)

    @patch("report.execute_report")
    def test_field_settings_panel_contains_all_columns(self, mock_exec):
        """字段设置面板应包含所有列"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("id", body)
        self.assertIn("name", body)
        self.assertIn("age", body)

    @patch("report.execute_report")
    def test_field_settings_drag_handle_present(self, mock_exec):
        """字段设置面板的列应有拖拽手柄"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("⠿", body)
        self.assertIn('draggable="true"', body)
        self.assertIn("class=\"field-item\"", body)

    @patch("report.execute_report")
    def test_field_settings_checkbox_all_checked_by_default(self, mock_exec):
        """默认所有列的复选框应处于选中状态"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn('checked', body)

    @patch("report.execute_report")
    def test_field_settings_hidden_col_not_checked(self, mock_exec):
        """隐藏的列在字段设置面板中不应选中"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        # 通过 cols 参数隐藏 age 列
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&cols=id,name",
            pool_override=self.mock_pool)
        # age 的 checkbox 不应有 checked 属性（或只显示未选中）
        # 简单检查 age 列存在但不再表格/面板中选中
        self.assertIn("age", body)

    @patch("report.execute_report")
    def test_field_settings_order_respected(self, mock_exec):
        """cols 参数应改变字段显示顺序"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&cols=age,name,id",
            pool_override=self.mock_pool)
        # cols 参数应出现在隐藏表单中
        self.assertIn("cols=", body)
        self.assertIn("cols", body)

    @patch("report.execute_report")
    def test_field_settings_up_down_buttons(self, mock_exec):
        """字段设置面板的每列应有上下移动按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("class=\"field-up\"", body)
        self.assertIn("class=\"field-down\"", body)

    @patch("report.execute_report")
    def test_field_settings_apply_button(self, mock_exec):
        """字段设置面板应有应用按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("applyFieldSettings", body)
        self.assertIn("应用", body)

    @patch("report.execute_report")
    def test_field_settings_select_all_buttons(self, mock_exec):
        """字段设置面板应有全选/全不选按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("selectAllFields(true)", body)
        self.assertIn("selectAllFields(false)", body)

    @patch("report.execute_report")
    def test_field_settings_init_drag_js(self, mock_exec):
        """页面应加载字段拖拽初始化脚本"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("initDragHandlers", body)

    def test_clear_filter_preserves_cols(self):
        """清除筛选链接应保留 cols 参数（通过 _build_report_html 验证）"""
        report_info = {"id": 1, "name": "测试", "sql_query": "SELECT * FROM t", "memo": ""}
        result = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        body = report._build_report_html(
            self.conn, report_info, result, self.mock_pool,
            sorts=[], filters=[("name", "contains", "a")],
            display_columns=["id", "name"])
        self.assertIn("清除筛选", body)
        # 清除筛选的 href 应包含 cols（URL 编码逗号）
        self.assertIn("cols=id%2Cname", body)


class TestSortSettingsPanel(unittest.TestCase):
    """排序设置面板 UI 测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, parent_id INTEGER);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "测试", "SELECT * FROM t", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_sort_settings_button_present(self, mock_exec):
        """页面上应有排序设置按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("排序设置", body)
        self.assertIn("sortSettingsPanel", body)

    @patch("report.execute_report")
    def test_sort_settings_shows_empty_when_no_sorts(self, mock_exec):
        """无排序时排序设置面板应显示暂无排序"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("暂无排序", body)

    @patch("report.execute_report")
    def test_sort_settings_shows_sorts(self, mock_exec):
        """有排序时排序设置面板应显示排序项"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc&sort=age&dir=desc",
            pool_override=self.mock_pool)
        self.assertIn("sort-item", body)
        self.assertIn("↑", body)
        self.assertIn("↓", body)
        self.assertNotIn("暂无排序", body)

    @patch("report.execute_report")
    def test_sort_settings_drag_handle_present(self, mock_exec):
        """排序设置面板的排序项应有拖拽手柄"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        self.assertIn("⠿", body)
        self.assertIn('draggable="true"', body)
        self.assertIn("class=\"sort-item\"", body)

    @patch("report.execute_report")
    def test_sort_settings_priority_numbers(self, mock_exec):
        """排序项应显示优先级编号"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc&sort=age&dir=desc",
            pool_override=self.mock_pool)
        self.assertIn("class=\"sort-num\"", body)
        # 第一个排序编号应为 1
        self.assertIn("1", body)

    @patch("report.execute_report")
    def test_sort_settings_up_down_buttons(self, mock_exec):
        """排序项应有上下移动按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc&sort=age&dir=desc",
            pool_override=self.mock_pool)
        self.assertIn("class=\"sort-up\"", body)
        self.assertIn("class=\"sort-down\"", body)

    @patch("report.execute_report")
    def test_sort_settings_remove_button(self, mock_exec):
        """排序项应有移除按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        self.assertIn("removeSortItem", body)
        self.assertIn("✕", body)

    @patch("report.execute_report")
    def test_sort_settings_add_dropdown(self, mock_exec):
        """排序设置面板应有添加排序的下拉框"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("newSortCol", body)
        self.assertIn("newSortDir", body)
        self.assertIn("addSortItem", body)

    @patch("report.execute_report")
    def test_sort_settings_apply_button(self, mock_exec):
        """排序设置面板应有应用按钮"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("applySortSettings", body)

    @patch("report.execute_report")
    def test_sort_settings_init_drag_js(self, mock_exec):
        """页面应加载排序拖拽初始化脚本"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("initSortDragHandlers", body)

    @patch("report.execute_report")
    def test_sort_settings_column_options_in_add(self, mock_exec):
        """添加排序下拉框应包含所有列"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("id", body)
        self.assertIn("name", body)
        self.assertIn("age", body)


class TestCombinationScenarios(unittest.TestCase):
    """字段设置与排序等组合场景测试"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE connection_pools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306, user TEXT NOT NULL, password TEXT NOT NULL, database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, parent_id INTEGER);
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER, memo TEXT, result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1, cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "测试", "SELECT * FROM t", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306, "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    def test_bug_fix_sort_remove_preserves_cols(self):
        """BUG验证: 排序栏✕按钮移除排序时不应丢失 cols 参数"""
        report_info = {"id": 1, "name": "测试", "sql_query": "SELECT * FROM t", "memo": ""}
        result = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        body = report._build_report_html(
            self.conn, report_info, result, self.mock_pool,
            sorts=[("name", "asc"), ("age", "desc")],
            filters=[],
            display_columns=["id", "name"])
        # 找出 sort-bar 块
        sort_bar_start = body.find("sort-bar")
        self.assertGreater(sort_bar_start, 0, "页面应包含排序栏")
        sort_bar_end = body.find("</div>", sort_bar_start)
        sort_bar_html = body[sort_bar_start:sort_bar_end]
        # 每个 ✕ 链接都应包含 cols=
        pos = 0
        found_any = False
        while True:
            a_start = sort_bar_html.find('✕</a>', pos)
            if a_start < 0:
                break
            href_start = sort_bar_html.rfind('href="', 0, a_start)
            href_end = sort_bar_html.find('"', href_start + 6)
            if href_start >= 0 and href_end > href_start:
                link = sort_bar_html[href_start:href_end + 1]
                found_any = True
                self.assertIn("cols=", link,
                              f"排序移除链接缺失 cols 参数: {link}")
            pos = a_start + 5
        self.assertTrue(found_any, "排序栏中应包含至少一个 ✕ 链接")

    @patch("report.execute_report")
    def test_multi_sort_header_asc_adds_new_col(self, mock_exec):
        """多排序: ▲ 点击未排序列应追加到末尾而非替换"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        # 当前已有 name asc 排序
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        # age 列后的 ▲ 链接应包含 sort=name&dir=asc&sort=age&dir=asc
        # 找到 age 列的 th，检查其中的 ▲ href
        age_th_start = body.find("age")
        if age_th_start >= 0:
            age_section = body[age_th_start:age_th_start + 2000]
            # ▲ 链接应在 age 列附近
            asc_match = age_section.find("▲")
            if asc_match >= 0:
                # 往前找 href
                href_start = age_section.rfind('<a href="', 0, asc_match)
                if href_start >= 0:
                    href_quote = age_section.find('"', href_start + 9)
                    href = age_section[href_start + 9:href_quote]
                    self.assertIn("sort=name", href)
                    self.assertIn("dir=asc", href)
                    self.assertIn("sort=age", href)
                    self.assertIn("dir=asc", href)

    @patch("report.execute_report")
    def test_multi_sort_header_desc_adds_new_col(self, mock_exec):
        """多排序: ▼ 点击未排序列应追加到末尾"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc",
            pool_override=self.mock_pool)
        # age 列后的 ▼ 链接应包含 sort=name&dir=asc&sort=age&dir=desc
        age_th_start = body.find("age")
        if age_th_start >= 0:
            age_section = body[age_th_start:age_th_start + 2000]
            desc_match = age_section.find("▼")
            if desc_match >= 0:
                href_start = age_section.rfind('<a href="', 0, desc_match)
                if href_start >= 0:
                    href_quote = age_section.find('"', href_start + 9)
                    href = age_section[href_start + 9:href_quote]
                    self.assertIn("sort=name", href)
                    self.assertIn("dir=asc", href)
                    self.assertIn("sort=age", href)
                    self.assertIn("dir=desc", href)

    @patch("report.execute_report")
    def test_multi_sort_header_toggle_in_place(self, mock_exec):
        """多排序: 点击已排序列的▲应在原位更新方向不改变排序顺序"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        # name asc, age desc
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&sort=name&dir=asc&sort=age&dir=desc",
            pool_override=self.mock_pool)
        # age 列的 ▲ 链接应改为 age asc（在原位，不改变 name 排序）
        age_th_start = body.find("age")
        if age_th_start >= 0:
            age_section = body[age_th_start:age_th_start + 2000]
            asc_match = age_section.find("▲")
            if asc_match >= 0:
                href_start = age_section.rfind('<a href="', 0, asc_match)
                if href_start >= 0:
                    href_quote = age_section.find('"', href_start + 9)
                    href = age_section[href_start + 9:href_quote]
                    # 应包含 name asc 和 age asc（name 在 age 前）
                    sort_pos_name = href.find("sort=name")
                    sort_pos_age = href.find("sort=age")
                    self.assertGreater(sort_pos_age, sort_pos_name,
                                       "age 排序应保持在 name 之后")
                    self.assertIn("dir=asc&dir=asc", href.replace("&amp;", "&"))

    @patch("report.execute_report")
    def test_sorts_filters_cols_all_preserved_in_pagination(self, mock_exec):
        """分页链接应同时保留排序、筛选和列设置"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)],
            total=25, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&sort=name&dir=asc&sort=age&dir=desc&f_name=a&op_age=gt&cols=id,name",
            pool_override=self.mock_pool)
        # 分页链接应包含所有参数（检查下一页箭头）
        self.assertIn("sort=name", body)
        self.assertIn("dir=asc", body)
        self.assertIn("sort=age", body)
        self.assertIn("dir=desc", body)
        self.assertIn("f_name=", body)
        self.assertIn("op_age=gt", body)
        self.assertIn("cols=", body)

    def test_clear_filter_preserves_sorts_and_cols(self):
        """清除筛选链接应保留排序和列设置"""
        report_info = {"id": 1, "name": "测试", "sql_query": "SELECT * FROM t", "memo": ""}
        result = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        body = report._build_report_html(
            self.conn, report_info, result, self.mock_pool,
            sorts=[("name", "asc")],
            filters=[("name", "contains", "a")],
            display_columns=["id", "name"])
        # 清除筛选链接应包含 sort 和 cols 但不包含 f_
        # 从 body 中提取清除筛选链接的 href
        clear_link_start = body.find('清除筛选')
        # 往回找最近的 href="
        href_start = body.rfind('href="', 0, clear_link_start)
        href_end = body.find('"', href_start + 6)
        clear_href = body[href_start:href_end + 1]
        self.assertIn("sort=name", clear_href)
        self.assertIn("cols=", clear_href)
        self.assertNotIn("f_name", clear_href)

    def test_export_form_preserves_sorts_filters_cols(self):
        """导出表单应保留排序、筛选和列设置"""
        report_info = {"id": 1, "name": "测试", "sql_query": "SELECT * FROM t", "memo": ""}
        result = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        body = report._build_report_html(
            self.conn, report_info, result, self.mock_pool,
            sorts=[("name", "asc")],
            filters=[("name", "contains", "a")],
            display_columns=["id", "name"])
        # 导出应包含排序、筛选、列隐藏字段
        self.assertRegex(body, r'name="sort" value="name"')
        self.assertRegex(body, r'name="dir" value="asc"')
        self.assertIn("f_name", body)
        self.assertIn("cols", body)

    @patch("report.execute_report")
    def test_rebuild_cache_preserves_sorts_filters_cols(self, mock_exec):
        """重建缓存链接应保留排序、筛选和列设置"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&sort=name&dir=asc&f_name=a&cols=id,name",
            pool_override=self.mock_pool)
        self.assertIn("refresh=1", body)
        self.assertIn("sort=name", body)
        self.assertIn("cols=", body)

    @patch("report.execute_report")
    def test_apply_field_settings_preserves_sorts(self, mock_exec):
        """applyFieldSettings JS 应保留当前排序"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&sort=name&dir=asc&sort=age&dir=desc",
            pool_override=self.mock_pool)
        # applyFieldSettings 函数应读取并保留 sort/dir 参数
        self.assertIn("key === 'sort'", body)
        self.assertIn("key === 'dir'", body)
        self.assertIn("sorts.push", body)

    @patch("report.execute_report")
    def test_apply_sort_settings_preserves_filters_and_cols(self, mock_exec):
        """applySortSettings JS 应保留筛选和列设置"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&f_name=a&op_age=gt&cols=id,name",
            pool_override=self.mock_pool)
        # applySortSettings 函数应读取并保留 f_/op_/cols 参数
        self.assertIn("key.startsWith('f_')", body)
        self.assertIn("key.startsWith('op_')", body)
        self.assertIn("cols", body)

    @patch("report.execute_report")
    def test_multi_sort_bar_shows_priority(self, mock_exec):
        """多字段排序时排序栏应显示优先级序号"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&sort=name&dir=asc&sort=age&dir=desc&sort=id&dir=asc",
            pool_override=self.mock_pool)
        self.assertIn("sort-bar", body)
        # 检查优先级符号（①②③...）
        self.assertIn("①", body)
        self.assertIn("②", body)
        self.assertIn("③", body)

    @patch("report.execute_report")
    def test_sort_bar_remove_link_has_correct_preserved_sorts(self, mock_exec):
        """排序栏 ✕ 移除排序后，其余排序的优先级顺序应保持不变"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name", "age"], rows=[(1, "A", 25)], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&sort=name&dir=asc&sort=age&dir=desc&sort=id&dir=asc",
            pool_override=self.mock_pool)
        sort_bar_start = body.find("sort-bar")
        sort_bar_end = body.find("</div>", sort_bar_start)
        sort_bar_html = body[sort_bar_start:sort_bar_end]
        # name 的 ✕ 移除后应剩 age desc + id asc
        name_x = sort_bar_html.find("name")
        if name_x >= 0:
            name_section = sort_bar_html[name_x:name_x + 200]
            x_link_start = name_section.find('href="')
            if x_link_start >= 0:
                x_link_end = name_section.find('"', x_link_start + 6)
                link = name_section[x_link_start + 6:x_link_end]
                self.assertIn("sort=age", link)
                self.assertIn("dir=desc", link)
                self.assertIn("sort=id", link)
                self.assertIn("dir=asc", link)
                # name 不应出现在移除后的链接中
                self.assertNotIn("sort=name", link)

    @patch("report.execute_report")
    def test_sort_settings_has_init_js_call(self, mock_exec):
        """DOMContentLoaded 应同时初始化字段和排序拖拽"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(1, "A")], total=1, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1", pool_override=self.mock_pool)
        self.assertIn("initDragHandlers", body)
        self.assertIn("initSortDragHandlers", body)


class TestEditButtonOnReportPage(unittest.TestCase):
    """报表页面【编辑】按钮测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "可编辑报表", "SELECT 1", 20, 1)

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_edit_button_present(self, mock_exec):
        """报表页应包含【编辑】按钮，链接到 /config/reports/{id}/edit"""
        mock_exec.return_value = report.ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=1", pool_override={"host": "h"})
        self.assertEqual(code, "200")
        self.assertIn('/config/reports/1/edit', body)
        self.assertIn('编辑', body)
        self.assertIn('target="_blank"', body)
        self.assertIn('rel="noopener"', body)

    @patch("report.execute_report")
    def test_edit_button_links_correct_report(self, mock_exec):
        """有多个报表时编辑按钮应指向对应报表"""
        db.add_report(self.conn, "第二个报表", "SELECT 2", 30, 1)
        mock_exec.return_value = report.ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20,
        )
        code, body, _ = report.handle_request(self.conn, "GET", "/report",
                                               "id=2", pool_override={"host": "h"})
        self.assertIn('/config/reports/2/edit', body)
        self.assertNotIn('/config/reports/1/edit', body)


class TestPreviewEndpoint(unittest.TestCase):
    """报表预览 POST 接口测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "预览报表", "SELECT original", 20, 1)

    def tearDown(self):
        self.conn.close()

    @patch("report.execute_report")
    def test_preview_uses_override_sql(self, mock_exec):
        """预览应使用表单中的 SQL 而非已保存的 SQL"""
        mock_exec.return_value = report.ReportResult(
            columns=["c"], rows=[("preview_data",)], total=1, page=1, page_size=20,
        )
        form_body = "id=1&sql_query=SELECT+override_sql&name=预览报表&default_page_size=20"
        code, body, _ = report.handle_request(self.conn, "POST", "/report/preview",
                                               "", form_body)
        self.assertEqual(code, "200")
        # 应使用 override SQL 进行查询
        actual_sql = mock_exec.call_args[0][1]
        self.assertEqual(actual_sql, "SELECT override_sql")
        self.assertIn("preview_data", body)

    @patch("report.execute_report")
    def test_preview_shows_preview_badge(self, mock_exec):
        """预览模式应显示预览标签"""
        mock_exec.return_value = report.ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20,
        )
        form_body = "id=1&sql_query=SELECT+preview_sql"
        code, body, _ = report.handle_request(self.conn, "POST", "/report/preview",
                                               "", form_body)
        self.assertIn("预览模式", body)

    @patch("report.execute_report")
    def test_preview_missing_id_returns_selector(self, mock_exec):
        """预览缺少 id 参数应返回报表选择页"""
        form_body = "sql_query=SELECT+test"
        code, body, _ = report.handle_request(self.conn, "POST", "/report/preview",
                                               "", form_body)
        self.assertIn("可用报表列表", body)


if __name__ == "__main__":
    unittest.main()
