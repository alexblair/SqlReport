"""
test_export.py — export.py 单元测试

测试策略：
- 使用 mock 模拟 MySQL 查询
- 验证 CSV 格式正确（BOM、引号、分隔符）
- 验证新导出选项（字符集、JSON数字无引号、ZIP压缩包）
- 覆盖错误路径（缺少参数、报表不存在、查询失败）
"""

import io
import json
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

    def _decode(self, content):
        """解码 handle_export 返回的 bytes（默认 charset=gbk）"""
        if isinstance(content, bytes):
            return content.decode("gbk", errors="replace")
        return content

    @patch("db.create_mysql_connection")
    def test_export_csv_content_utf8(self, mock_create_conn):
        """导出 CSV（UTF-8）应包含 BOM、表头和数据行"""
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
            self.conn, "id=1&charset=utf8", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertIsInstance(csv_content, bytes)
        text = csv_content.decode("utf-8")
        # 应包含 BOM
        self.assertTrue(text.startswith("\ufeff"))
        # 所有字段应被引号包裹
        self.assertIn('"id","product","price"', text)
        self.assertIn('"1","笔记本","29.99"', text)
        self.assertIn('"2","鼠标","9.99"', text)

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

        text = self._decode(csv_content)
        # 引号应被转义为 ""
        self.assertIn('"包含""引号""的文本"', text)
        # 逗号在引号内应保持原样
        self.assertIn('"包含,逗号的文本"', text)

    @patch("db.create_mysql_connection")
    def test_export_csv_headers_gbk(self, mock_create_conn):
        """默认 GBK 导出的响应头"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)

        self.assertEqual(headers.get("Content-Type"), "text/csv; charset=gbk")
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        disp = headers.get("Content-Disposition", "")
        self.assertIn('filename="report_1.csv"', disp)
        self.assertIn("filename*=UTF-8''", disp)
        self.assertIn(urllib.parse.quote("订单报表.csv", safe=''), disp)

    @patch("db.create_mysql_connection")
    def test_export_csv_utf8(self, mock_create_conn):
        """指定 UTF8 字符集导出"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&charset=utf8", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertIsInstance(content, bytes)
        text = content.decode("utf-8")
        self.assertIn('"1"', text)

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

        code, csv_content, _ = export.handle_export(
            self.conn, "id=1&f_name=alice", pool_override=self.mock_pool)

        text = self._decode(csv_content)
        self.assertEqual(code, "200")
        self.assertIn("Alice", text)
        self.assertNotIn("Bob", text)
        self.assertNotIn("Charlie", text)
        self.assertNotIn("dave", text)
        self.assertIn("name", text)
        self.assertIn("age", text)

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


# ===================================================================
# JSON 导出测试
# ===================================================================


class TestJSONExport(unittest.TestCase):
    """JSON 导出功能测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "订单报表", "SELECT * FROM orders", 20, 1)
        self.mock_pool = {"host": "h", "port": 3306,
                          "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()
        db._initialized = False

    def _decode_json(self, content):
        """解码 handle_export 返回的 JSON bytes 为 Python 对象"""
        if isinstance(content, bytes):
            text = content.decode("gbk", errors="replace")
        else:
            text = content
        return json.loads(text)

    @patch("db.create_mysql_connection")
    def test_json_export_basic(self, mock_create_conn):
        """JSON 导出基本功能：含表头和数据行"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("product",), ("price",)]
        mock_cursor.fetchall.return_value = [
            (1, "笔记本", 29.99),
            (2, "鼠标", 9.99),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = self._decode_json(content)
        self.assertIn("订单报表", data)
        rows = data["订单报表"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "1")
        self.assertEqual(rows[0]["product"], "笔记本")
        self.assertEqual(rows[0]["price"], "29.99")

    @patch("db.create_mysql_connection")
    def test_json_export_special_chars(self, mock_create_conn):
        """JSON 导出应自动转义字段内的引号和特殊字符"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("name",), ("detail",)]
        mock_cursor.fetchall.return_value = [
            ('商品A', '包含"引号"的文本'),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = self._decode_json(content)
        detail = data["订单报表"][0]["detail"]
        self.assertEqual(detail, '包含"引号"的文本')

    @patch("db.create_mysql_connection")
    def test_json_export_embedded_json(self, mock_create_conn):
        """字段内嵌 JSON 字符串时，内部引号应自动转义"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("物资详情",)]
        mock_cursor.fetchall.return_value = [
            ("""[[{"物资名称": "钢筋"}, {"参数": "6~25"}]]""",),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, _ = export.handle_export(
            self.conn, "id=1&format=json", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = self._decode_json(content)
        detail = data["订单报表"][0]["物资详情"]
        self.assertIn("钢筋", detail)
        self.assertIn("6~25", detail)
        # 原始 JSON 字符串中应包含转义后的引号
        if isinstance(content, bytes):
            text = content.decode("gbk", errors="replace")
        else:
            text = content
        self.assertIn('\\"', text)

    @patch("db.create_mysql_connection")
    def test_json_export_empty_result(self, mock_create_conn):
        """空结果集应输出报表名 + 空数组"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("col1",), ("col2",)]
        mock_cursor.fetchall.return_value = []
        mock_create_conn.return_value = mock_conn

        code, content, _ = export.handle_export(
            self.conn, "id=1&format=json", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = self._decode_json(content)
        self.assertEqual(data["订单报表"], [])

    @patch("db.create_mysql_connection")
    def test_json_export_with_filter(self, mock_create_conn):
        """带筛选条件的 JSON 导出应只输出匹配行"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("name",), ("age",)]
        mock_cursor.fetchall.return_value = [
            ("Alice", 25), ("Bob", 30), ("Charlie", 35),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, _ = export.handle_export(
            self.conn, "id=1&format=json&f_name=alice",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = self._decode_json(content)
        rows = data["订单报表"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alice")

    @patch("db.create_mysql_connection")
    def test_json_export_headers_gbk(self, mock_create_conn):
        """JSON 默认 GBK 导出响应头"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"),
                         "application/json; charset=gbk")
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertIn("filename*=UTF-8''", headers.get("Content-Disposition", ""))

    def test_json_export_missing_id(self):
        """缺少 id 参数应返回 400"""
        code, body, _ = export.handle_export(self.conn, "format=json")
        self.assertEqual(code, "400")
        self.assertIn("缺少", body)


# ===================================================================
# 新导出选项测试
# ===================================================================


class TestExportCharset(unittest.TestCase):
    """导出字符集测试"""

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
    def test_csv_gbk_default(self, mock_create_conn):
        """默认 CSV 导出为 GBK 编码"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "中文")]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertIsInstance(content, bytes)
        # 应该能正常解码为 GBK
        text = content.decode("gbk")
        self.assertIn("中文", text)

    @patch("db.create_mysql_connection")
    def test_csv_utf8_charset(self, mock_create_conn):
        """指定 UTF8 字符集导出 CSV"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&charset=utf8", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"), "text/csv; charset=utf-8")

    @patch("db.create_mysql_connection")
    def test_json_gbk_charset(self, mock_create_conn):
        """JSON 导出指定 GBK 字符集"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&charset=gbk",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"),
                         "application/json; charset=gbk")
        self.assertIsInstance(content, bytes)
        text = content.decode("gbk")
        data = json.loads(text)
        self.assertEqual(data["订单报表"][0]["id"], "1")

    @patch("db.create_mysql_connection")
    def test_json_utf8_charset(self, mock_create_conn):
        """JSON 导出指定 UTF8 字符集"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"),
                         "application/json; charset=utf-8")


class TestExportJSONNoQuotes(unittest.TestCase):
    """JSON 导出数值不带引号功能测试"""

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
    def test_json_no_quotes_numbers(self, mock_create_conn):
        """json_no_quotes 启用时，数值类型不加引号"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("price",), ("name",)]
        mock_cursor.fetchall.return_value = [
            (1, 29.99, "商品A"),
            (2, 9.99, "商品B"),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&json_no_quotes=1&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        # id 应为数字 1 而不是字符串 "1"
        self.assertIn('"id": 1', text)
        # price 应为数字
        self.assertIn('"price": 29.99', text)
        # name 仍为字符串
        self.assertIn('"name": "商品A"', text)

        data = json.loads(text)
        row = data["订单报表"][0]
        self.assertIsInstance(row["id"], int)
        self.assertIsInstance(row["price"], float)
        self.assertIsInstance(row["name"], str)

    @patch("db.create_mysql_connection")
    def test_json_no_quotes_with_charset(self, mock_create_conn):
        """json_no_quotes 与 charset 可同时使用"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("val",)]
        mock_cursor.fetchall.return_value = [
            (100, 3.14),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&json_no_quotes=1&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertIsInstance(content, bytes)
        data = json.loads(content.decode("utf-8"))
        self.assertIsInstance(data["订单报表"][0]["id"], int)
        self.assertEqual(data["订单报表"][0]["id"], 100)

    @patch("db.create_mysql_connection")
    def test_json_no_quotes_none_values(self, mock_create_conn):
        """json_no_quotes 启用时，None 应输出为 null"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("remark",)]
        mock_cursor.fetchall.return_value = [
            (1, None),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&json_no_quotes=1&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        text = content.decode("utf-8")
        self.assertIn('"remark": null', text)
        data = json.loads(text)
        self.assertIsNone(data["订单报表"][0]["remark"])

    @patch("db.create_mysql_connection")
    def test_default_values_all_strings(self, mock_create_conn):
        """不启用 json_no_quotes 时，所有值仍为字符串（向后兼容）"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("price",)]
        mock_cursor.fetchall.return_value = [
            (1, 29.99),
        ]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        data = json.loads(content.decode("utf-8"))
        self.assertIsInstance(data["订单报表"][0]["id"], str)
        self.assertEqual(data["订单报表"][0]["id"], "1")


class TestExportZip(unittest.TestCase):
    """ZIP 压缩包导出测试"""

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
    def test_zip_csv_export(self, mock_create_conn):
        """ZIP + CSV 导出应返回有效的 ZIP 文件"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "测试")]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&zip=1", pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertIsInstance(content, bytes)
        self.assertEqual(headers.get("Content-Type"), "application/zip")
        self.assertIn(".zip", headers.get("Content-Disposition", ""))

        # 验证 ZIP 内容可解压
        import zipfile
        import io as io_mod
        with zipfile.ZipFile(io_mod.BytesIO(content)) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 1)
            self.assertTrue(names[0].endswith(".csv"))
            csv_data = zf.read(names[0]).decode("gbk")
            self.assertIn("测试", csv_data)

    @patch("db.create_mysql_connection")
    def test_zip_json_export(self, mock_create_conn):
        """ZIP + JSON 导出"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(42,)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&zip=1&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"), "application/zip")

        import zipfile
        import io as io_mod
        with zipfile.ZipFile(io_mod.BytesIO(content)) as zf:
            names = zf.namelist()
            self.assertTrue(any(n.endswith(".json") for n in names))
            json_file = [n for n in names if n.endswith(".json")][0]
            data = json.loads(zf.read(json_file).decode("utf-8"))
            self.assertEqual(data["订单报表"][0]["id"], "42")

    @patch("db.create_mysql_connection")
    def test_zip_json_no_quotes(self, mock_create_conn):
        """ZIP + JSON + json_no_quotes 联合导出"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("count",)]
        mock_cursor.fetchall.return_value = [(1, 100)]
        mock_create_conn.return_value = mock_conn

        code, content, headers = export.handle_export(
            self.conn, "id=1&format=json&zip=1&json_no_quotes=1&charset=utf8",
            pool_override=self.mock_pool)

        self.assertEqual(code, "200")
        self.assertEqual(headers.get("Content-Type"), "application/zip")

        import zipfile
        import io as io_mod
        with zipfile.ZipFile(io_mod.BytesIO(content)) as zf:
            json_file = [n for n in zf.namelist() if n.endswith(".json")][0]
            data = json.loads(zf.read(json_file).decode("utf-8"))
            self.assertIsInstance(data["订单报表"][0]["id"], int)
            self.assertEqual(data["订单报表"][0]["id"], 1)
            self.assertIsInstance(data["订单报表"][0]["count"], int)
            self.assertEqual(data["订单报表"][0]["count"], 100)


# ===================================================================
# 单元函数测试
# ===================================================================


def _extract_report_key(content: str) -> str:
    """从 JSON 导出内容中提取顶层 key（报表名）"""
    import re
    m = re.search(r'"(\w+)":\s*\[', content)
    return m.group(1) if m else ""


class TestExportReportToJSON(unittest.TestCase):
    """export_report_to_json 函数测试"""

    @patch("db.create_mysql_connection")
    def test_report_name_as_key(self, mock_create_conn):
        """报表名应作为 JSON 顶层 key"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        result = export.export_report_to_json(
            "SELECT * FROM t",
            {"host": "h", "port": 3306, "user": "u", "password": "p",
             "database": "d"},
            "我的报表",
        )
        data = json.loads(result)
        self.assertIn("我的报表", data)
        self.assertEqual(len(data["我的报表"]), 1)

    @patch("db.create_mysql_connection")
    def test_report_name_with_spaces(self, mock_create_conn):
        """报表名带空格应被替换为下划线"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [(1,)]
        mock_create_conn.return_value = mock_conn

        result = export.export_report_to_json(
            "SELECT * FROM t",
            {"host": "h", "port": 3306, "user": "u", "password": "p",
             "database": "d"},
            "Bidding List V2",
        )
        data = json.loads(result)
        self.assertIn("Bidding_List_V2", data)

    @patch("db.create_mysql_connection")
    def test_json_no_quotes_param(self, mock_create_conn):
        """export_report_to_json 支持 json_no_quotes 参数"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("id",), ("price",)]
        mock_cursor.fetchall.return_value = [(1, 99.5)]
        mock_create_conn.return_value = mock_conn

        result = export.export_report_to_json(
            "SELECT * FROM t",
            {"host": "h", "port": 3306, "user": "u", "password": "p",
             "database": "d"},
            "测试报表",
            json_no_quotes=True,
        )
        data = json.loads(result)
        row = data["测试报表"][0]
        self.assertIsInstance(row["id"], int)
        self.assertEqual(row["id"], 1)
        self.assertIsInstance(row["price"], float)


class TestEncodeContent(unittest.TestCase):
    """_encode_content 函数测试"""

    def test_encode_utf8(self):
        """UTF8 编码"""
        result = export._encode_content("中文测试", "utf8")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result.decode("utf-8"), "中文测试")

    def test_encode_gbk(self):
        """GBK 编码"""
        result = export._encode_content("中文测试", "gbk")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result.decode("gbk"), "中文测试")

    def test_encode_gbk_replace(self):
        """GBK 无法编码的字符应替换为 ?"""
        result = export._encode_content("\U0001F600", "gbk")
        self.assertIsInstance(result, bytes)


class TestBuildExportFilename(unittest.TestCase):
    """_build_export_filename 函数测试"""

    def test_csv_filename(self):
        """CSV 导出文件名"""
        raw, ascii_name, encoded = export._build_export_filename(
            "报表", 1, "csv", False)
        self.assertEqual(ascii_name, "report_1.csv")
        self.assertIn("报表", urllib.parse.unquote(encoded))

    def test_json_filename(self):
        """JSON 导出文件名"""
        raw, ascii_name, encoded = export._build_export_filename(
            "报表", 1, "json", False)
        self.assertEqual(ascii_name, "report_1.json")
        self.assertIn("报表", urllib.parse.unquote(encoded))

    def test_zip_filename(self):
        """ZIP 导出文件名"""
        raw, ascii_name, encoded = export._build_export_filename(
            "报表", 1, "csv", True)
        self.assertEqual(ascii_name, "report_1.zip")
        self.assertTrue(ascii_name.endswith(".zip"))


if __name__ == "__main__":
    unittest.main()
