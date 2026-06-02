"""
test_export.py — export.py 单元测试

测试策略：
- 使用 mock 模拟 MySQL 查询
- 验证 CSV 格式正确（BOM、引号、分隔符）
- 覆盖错误路径（缺少参数、报表不存在、查询失败）
"""

import unittest
import urllib.parse
from unittest.mock import patch, MagicMock
import sqlite3
import db
import export


def _make_conn():
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


class TestExportToCSV(unittest.TestCase):
    """CSV 导出核心功能测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "订单报表", "SELECT * FROM orders", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306,
                          "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()
        db._initialized = False

    @patch("db.create_mysql_connection")
    def test_export_csv_content(self, mock_create_conn):
        """导出 CSV 应包含 BOM、表头和数据行"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("product",), ("price",)]
        mock_cursor.fetchall.return_value = [
            (1, "笔记本", 29.99),
            (2, "鼠标", 9.99),
        ]
        mock_create_conn.return_value = mock_conn

        code, csv_content, headers = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        # 应包含 BOM
        self.assertTrue(csv_content.startswith("\ufeff"))
        # 所有字段应被引号包裹
        self.assertIn('"id","product","price"', csv_content)
        self.assertIn('"1","笔记本","29.99"', csv_content)
        self.assertIn('"2","鼠标","9.99"', csv_content)

    @patch("db.create_mysql_connection")
    def test_export_csv_quotes_special_chars(self, mock_create_conn):
        """包含逗号或引号的字段应正确转义"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("name",), ("desc",)]
        mock_cursor.fetchall.return_value = [
            ('商品A', '包含"引号"的文本'),
            ('商品B', '包含,逗号的文本'),
        ]
        mock_create_conn.return_value = mock_conn

        code, csv_content, _ = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)

        # 引号应被转义为 ""
        self.assertIn('"包含""引号""的文本"', csv_content)
        # 逗号在引号内应保持原样
        self.assertIn('"包含,逗号的文本"', csv_content)

    @patch("db.create_mysql_connection")
    def test_export_headers(self, mock_create_conn):
        """响应头应包含正确的 Content-Type 和 Content-Disposition"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)

        self.assertEqual(headers.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        # 验证 RFC 5987 编码的中文文件名
        disp = headers.get("Content-Disposition", "")
        self.assertIn('filename="report_1.csv"', disp)
        self.assertIn("filename*=UTF-8''", disp)
        self.assertIn(urllib.parse.quote("订单报表.csv", safe=''), disp)

    @patch("db.create_mysql_connection")
    def test_export_with_filter(self, mock_create_conn):
        """带筛选条件的导出应只导出匹配的行"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("name",), ("age",)]
        mock_cursor.fetchall.return_value = [
            ("Alice", 25), ("Bob", 30), ("Charlie", 35), ("dave", 40),
        ]
        mock_create_conn.return_value = mock_conn

        # 导出时携带筛选参数 f_name=alice（不区分大小写）
        code, csv_content, _ = export.handle_export(
            self.conn, "id=1&f_name=alice", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        # 应只包含 Alice（匹配"alice"）一条数据
        self.assertIn("Alice", csv_content)
        self.assertNotIn("Bob", csv_content)
        self.assertNotIn("Charlie", csv_content)
        self.assertNotIn("dave", csv_content)
        # 表头仍在
        self.assertIn("name", csv_content)
        self.assertIn("age", csv_content)

    def test_export_missing_id(self):
        """缺少 id 参数应返回 400"""
        code, body, _ = export.handle_export(self.conn, "")
        self.assertEqual(code, "400")
        self.assertIn("缺少", body)

    def test_export_invalid_id(self):
        """无效 id 应返回 400"""
        code, body, _ = export.handle_export(self.conn, "id=abc")
        self.assertEqual(code, "400")

    def test_export_report_not_found(self):
        """不存在的报表应返回 404"""
        code, body, _ = export.handle_export(self.conn, "id=999")
        self.assertEqual(code, "404")

    @patch("db.create_mysql_connection")
    def test_export_query_error(self, mock_create_conn):
        """查询失败应返回 500"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("表不存在")
        mock_create_conn.return_value = mock_conn

        code, body, _ = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)
        self.assertEqual(code, "500")
        self.assertIn("表不存在", body)


class TestExportReportToCSV(unittest.TestCase):
    """export_report_to_csv 函数测试"""

    @patch("db.create_mysql_connection")
    def test_empty_result(self, mock_create_conn):
        """空结果集应只输出 BOM + 表头"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("col1",), ("col2",)]
        mock_cursor.fetchall.return_value = []
        mock_create_conn.return_value = mock_conn

        result = export.export_report_to_csv("SELECT * FROM t",
                                              {"host": "h", "port": 3306,
                                               "user": "u", "password": "p",
                                               "database": "d"})
        self.assertEqual(result, '\ufeff"col1","col2"\n')


if __name__ == "__main__":
    unittest.main()
