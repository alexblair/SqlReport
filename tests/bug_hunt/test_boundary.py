"""test_boundary.py — 边界条件自动化测试

在 unittest discover 时自动运行。
覆盖 bug_hunt_boundary.py 中未在 test_deep_edge_cases.py 覆盖的边界场景：
  1. render 模板一致性
  2. auth 极端输入
  3. server 路由边界
  4. SQL 边界
  5. export 边界

注：分页、排序、Cookie、配置 CRUD 边界已在 test_deep_edge_cases.py 中覆盖。
"""

import unittest
import unittest.mock
from unittest.mock import patch, MagicMock
from decimal import Decimal
import importlib


# ===================================================================
# 1. Render 模板边界
# ===================================================================

class TestRenderBoundary(unittest.TestCase):
    """render.py 模板和函数边界条件"""

    @classmethod
    def setUpClass(cls):
        cls.render = importlib.import_module("render")

    def test_format_cell_none(self):
        """format_cell(None) → 返回空字符串"""
        result = self.render.format_cell(None)
        self.assertEqual(result, "")

    def test_format_cell_decimal_zero(self):
        """format_cell(Decimal(0)) → 返回 '0'"""
        result = self.render.format_cell(Decimal(0))
        self.assertEqual(result, "0")

    def test_format_cell_bytes(self):
        """format_cell(b'test') → 返回字符串"""
        result = self.render.format_cell(b"test")
        self.assertIsInstance(result, str)

    def test_render_page_header_with_dollar(self):
        """render_page_header(title=含$字符串) — 应正确转义 $ 防止 substitute 报错"""
        try:
            html = self.render.render_page_header(
                title="测试 $100 充值",
                active_nav="report",
            )
            self.assertIn("测试", html)
            self.assertIn("充值", html)
        except Exception as e:
            self.fail(f"render_page_header(title='含$') 抛出 {type(e).__name__}: {e}")

    def test_render_page_header_none_active(self):
        """render_page_header(active_nav=None) — 不抛异常"""
        try:
            html = self.render.render_page_header(title="Test", active_nav=None)
            self.assertIsInstance(html, str)
        except Exception as e:
            self.fail(f"render_page_header(active_nav=None) 抛出 {type(e).__name__}: {e}")


# ===================================================================
# 2. Auth 边界
# ===================================================================

class TestAuthBoundary(unittest.TestCase):
    """auth.py 极端输入边界"""

    @classmethod
    def setUpClass(cls):
        cls.auth = importlib.import_module("auth")

    def test_verify_password_none(self):
        """verify_password(None, hash) → 应返回 False 不抛异常"""
        hashed = self.auth.hash_password("dummy")
        try:
            result = self.auth.verify_password(None, hashed)
            self.assertFalse(result)
        except (TypeError, AttributeError) as e:
            self.fail(f"verify_password(None, hash) 抛出 {type(e).__name__}: {e}")

    def test_verify_password_no_dollar(self):
        """verify_password(pwd, 'hash_no_dollar') → 应返回 False"""
        try:
            result = self.auth.verify_password("pwd", "hash_without_dollar")
            self.assertFalse(result)
        except Exception as e:
            self.fail(f"verify_password(pwd, no_dollar_hash) 抛出 {type(e).__name__}: {e}")

    def test_parse_cookie_none(self):
        """parse_cookie(None) → 应返回空 dict"""
        result = self.auth.parse_cookie(None)
        self.assertEqual(result, {})

    def test_parse_cookie_malformed_no_equal(self):
        """parse_cookie('abc') → 应返回空 dict"""
        result = self.auth.parse_cookie("abc")
        self.assertEqual(result, {})

    def test_get_session_user_none(self):
        """get_session_user(None) → 应返回 None"""
        user = self.auth.get_session_user(None)
        self.assertIsNone(user)

    def test_make_set_cookie_header_negative_max_age(self):
        """make_set_cookie_header(token, max_age=-1) → 不应抛异常"""
        try:
            header = self.auth.make_set_cookie_header("test_token", max_age=-1)
            self.assertIn("Max-Age=-1", header)
        except Exception as e:
            self.fail(f"make_set_cookie_header(max_age=-1) 抛出 {type(e).__name__}: {e}")


# ===================================================================
# 3. Server 路由边界
# ===================================================================

class TestServerBoundary(unittest.TestCase):
    """server.py 路由匹配和请求处理边界"""

    @classmethod
    def setUpClass(cls):
        cls.server = importlib.import_module("server")

    def test_unknown_path_returns_none(self):
        """_match_route(GET, '/nonexistent') → 应返回 None（404）"""
        route = self.server._match_route("GET", "/nonexistent")
        self.assertIsNone(route)

    def test_unknown_post_path_returns_none(self):
        """_match_route(POST, '/api/unknown') → 应匹配 API 路由"""
        route = self.server._match_route("POST", "/api/unknown")
        self.assertIsNotNone(route)
        self.assertEqual(route.handler, "_handle_api")

    def test_empty_path_matches_root(self):
        """_match_route(GET, '') → 应匹配根路由"""
        route = self.server._match_route("GET", "")
        self.assertIsNotNone(route)

    def test_route_report_subpath(self):
        """_match_route(GET, '/report/123') → 应匹配报表路由"""
        route = self.server._match_route("GET", "/report/123")
        self.assertIsNotNone(route)
        self.assertEqual(route.handler, "_handle_report")

    def test_cookie_malformed_with_semicolon(self):
        """parse_cookie(';;;=;==;') → 畸形 Cookie 不崩溃"""
        from auth import parse_cookie
        try:
            cookies = parse_cookie(";;;=;==;")
            self.assertIsInstance(cookies, dict)
        except Exception as e:
            self.fail(f"parse_cookie(';;;=;==;') 抛出 {type(e).__name__}: {e}")


# ===================================================================
# 4. SQL 边界
# ===================================================================

class TestSqlBoundary(unittest.TestCase):
    """query_executor.py 中 SQL 处理边界"""

    @classmethod
    def setUpClass(cls):
        cls.qe = importlib.import_module("query_executor")

    def test_split_sql_none(self):
        """_split_sql_statements(None) → 应返回 []"""
        try:
            result = self.qe._split_sql_statements(None)
            self.assertEqual(result, [])
        except TypeError as e:
            self.fail(f"_split_sql_statements(None) 抛出 TypeError: {e}")

    def test_split_sql_empty(self):
        """_split_sql_statements('') → 应返回 []"""
        result = self.qe._split_sql_statements("")
        self.assertEqual(result, [])

    def test_split_sql_unclosed_quote(self):
        """_split_sql_statements(\"'unclosed\") → 应尽量处理不崩溃"""
        try:
            result = self.qe._split_sql_statements("SELECT 'unclosed")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.fail(f"_split_sql_statements(引号不闭合) 抛出 {type(e).__name__}: {e}")

    def test_mysql_row_empty_dict(self):
        """_MySQLRow({}) → 应正常工作"""
        row = self.qe._MySQLRow({})
        self.assertEqual(len(row), 0)
        self.assertEqual(list(row.keys()), [])
        self.assertEqual(list(row.values()), [])

    def test_mysql_row_empty_list(self):
        """_MySQLRow([]) → 应正常工作"""
        row = self.qe._MySQLRow([])
        self.assertEqual(len(row), 0)
        self.assertEqual(list(row.keys()), [])
        self.assertEqual(list(row.values()), [])

    def test_execute_mysql_query_empty_sql(self):
        """execute_mysql_query(mock_conn, '') → 应抛 RuntimeError"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with self.assertRaises(RuntimeError):
            self.qe.execute_mysql_query(mock_conn, "")


# ===================================================================
# 5. Export 边界
# ===================================================================

class TestExportBoundary(unittest.TestCase):
    """export.py 边界条件"""

    @classmethod
    def setUpClass(cls):
        cls.export = importlib.import_module("export")

    def test_encode_content_empty_utf8(self):
        """_encode_content('', 'utf8') → 返回 b''"""
        result = self.export._encode_content("", "utf8")
        self.assertEqual(result, b"")

    def test_no_quote_value_none(self):
        """_no_quote_value(None) → 返回 None"""
        result = self.export._no_quote_value(None)
        self.assertIsNone(result)

    def test_no_quote_value_bytes(self):
        """_no_quote_value(bytes) → 解码为字符串"""
        result = self.export._no_quote_value(b"hello world")
        self.assertEqual(result, "hello world")

    def test_build_export_filename_empty_name(self):
        """_build_export_filename('', ...) → 不崩溃"""
        try:
            raw, asc, enc = self.export._build_export_filename("", 1, "csv", False)
            self.assertEqual(raw, ".csv")
            self.assertEqual(asc, "report_1.csv")
        except Exception as e:
            self.fail(f"_build_export_filename('') 抛出 {type(e).__name__}: {e}")
