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
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );
    """)
    db._initialized = True
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
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );
    """)
    db._initialized = True
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
        db._initialized = False

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
            CREATE TABLE report_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20, pool_id INTEGER, category_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL, FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL);
        """)
        db._initialized = True
        code, body, _ = report.handle_request(conn2, "GET", "/report", "")
        self.assertEqual(code, "200")
        self.assertIn("选择报表", body)
        conn2.close()
        db._initialized = False


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
        db._initialized = False

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
        mock_exec_q.return_value = (["id", "name"], all_rows)
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
        mock_exec_q.return_value = (["id", "name"], all_rows)
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
            filters=[("name", "e")],
        )
        # 包含 e/E: Charlie, Alice, dave, Eve → 4 条
        self.assertEqual(result.total, 4)

        # 筛选 + 排序 ASC
        result2 = report.execute_report(
            report_id=10,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            page=1, page_size=10,
            filters=[("name", "e")],
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
            filters=[("name", "e")],
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
        mock_exec_q.return_value = (["id", "name", "age"], all_rows)
        mock_conn = MagicMock()
        mock_create_conn.return_value = mock_conn

        pool = {"host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d"}

        # 同时筛选 name 包含 "alice" AND age 包含 "25"
        result = report.execute_report(
            report_id=50,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            filters=[("name", "alice"), ("age", "25")],
        )
        self.assertEqual(result.total, 1)  # (1, Alice, 25)
        self.assertEqual(result.rows[0][0], 1)
        self.assertEqual(result.rows[0][1], "Alice")

        # 只筛选 name 包含 "alice"
        result2 = report.execute_report(
            report_id=50,
            sql_query="SELECT * FROM t",
            pool_config=pool,
            filters=[("name", "alice")],
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
        mock_exec_q.return_value = (["id", "name", "age"], all_rows)
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
        mock_exec_q.return_value = (["id"], [(1,), (2,)])
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
        mock_exec_q.return_value = (["id"], [(1,), (2,)])
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
        mock_exec_q.return_value = (["id"], [(1,), (2,)])
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


if __name__ == "__main__":
    unittest.main()
