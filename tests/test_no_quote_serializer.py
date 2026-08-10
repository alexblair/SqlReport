"""
test_no_quote_serializer.py — app_config.serialize_no_quote「值无引号」序列化测试

覆盖（对应 .scratch/api-json-no-quotes/issues/01 覆盖矩阵）：
- 标量：None / bool / int / float / Decimal（0、-0、尾零、整数、大数）/ bytes / str（含特殊字符）/ date/datetime
- 结构：dict（键保留标准引号）/ list / tuple / 嵌套 / 空容器
- indent 模式（报表导出 indent=2 的缩进形状）

新语义：所有标量值不带引号裸输出，无「数字 vs 字符串」类型判断。
"""

import unittest
from datetime import date, datetime
from decimal import Decimal

import app_config


class TestNoQuoteScalar(unittest.TestCase):
    """标量裸输出。"""

    def test_none_null(self):
        self.assertEqual(app_config.serialize_no_quote(None), "null")

    def test_bool(self):
        self.assertEqual(app_config.serialize_no_quote(True), "true")
        self.assertEqual(app_config.serialize_no_quote(False), "false")

    def test_int(self):
        self.assertEqual(app_config.serialize_no_quote(25), "25")
        self.assertEqual(app_config.serialize_no_quote(-7), "-7")

    def test_float(self):
        self.assertEqual(app_config.serialize_no_quote(29.99), "29.99")

    def test_decimal_plain(self):
        self.assertEqual(app_config.serialize_no_quote(Decimal("123.45")), "123.45")

    def test_decimal_trailing_zeros_trimmed(self):
        self.assertEqual(app_config.serialize_no_quote(Decimal("0.50")), "0.5")

    def test_decimal_zero_and_negzero(self):
        self.assertEqual(app_config.serialize_no_quote(Decimal("0")), "0")
        self.assertEqual(app_config.serialize_no_quote(Decimal("-0.00")), "0")

    def test_decimal_integer(self):
        self.assertEqual(app_config.serialize_no_quote(Decimal("5")), "5")

    def test_decimal_large(self):
        self.assertEqual(
            app_config.serialize_no_quote(Decimal("999999999999.99")),
            "999999999999.99")

    def test_bytes_decoded(self):
        self.assertEqual(app_config.serialize_no_quote(b"abc"), "abc")

    def test_str_bare(self):
        self.assertEqual(app_config.serialize_no_quote("张三"), "张三")

    def test_str_special_chars_not_escaped(self):
        """裸输出不转义：引号/花括号等特殊字符原样输出。"""
        self.assertEqual(app_config.serialize_no_quote('a"b'), 'a"b')
        self.assertEqual(app_config.serialize_no_quote("a}b"), "a}b")

    def test_date_datetime(self):
        self.assertEqual(
            app_config.serialize_no_quote(date(2026, 1, 2)), "2026-01-02")
        self.assertEqual(
            app_config.serialize_no_quote(datetime(2026, 1, 2, 3, 4, 5)),
            "2026-01-02 03:04:05")


class TestNoQuoteStructure(unittest.TestCase):
    """结构保留 JSON 语法（键带引号），值裸输出。"""

    def test_dict_keys_quoted_values_bare(self):
        out = app_config.serialize_no_quote(
            {"name": "张三", "age": 25, "code": "007", "none": None})
        self.assertEqual(
            out, '{"name": 张三, "age": 25, "code": 007, "none": null}')

    def test_dict_empty(self):
        self.assertEqual(app_config.serialize_no_quote({}), "{}")

    def test_list(self):
        self.assertEqual(app_config.serialize_no_quote([1, "a"]), "[1, a]")

    def test_tuple(self):
        self.assertEqual(app_config.serialize_no_quote((1, "a")), "[1, a]")

    def test_list_empty(self):
        self.assertEqual(app_config.serialize_no_quote([]), "[]")

    def test_nested(self):
        out = app_config.serialize_no_quote(
            {"rows": [{"x": 1, "s": "甲"}]})
        self.assertEqual(out, '{"rows": [{"x": 1, "s": 甲}]}')

    def test_unicode_key(self):
        out = app_config.serialize_no_quote({"单价": 500})
        self.assertEqual(out, '{"单价": 500}')

    def test_insertion_order_preserved(self):
        out = app_config.serialize_no_quote({"b": 1, "a": 2})
        self.assertEqual(out, '{"b": 1, "a": 2}')


class TestNoQuoteIndent(unittest.TestCase):
    """indent 模式（与 json.dumps(indent=2) 形状一致，值裸输出）。"""

    def test_indent_shape(self):
        out = app_config.serialize_no_quote(
            {"报表": [{"id": 1, "name": "甲"}]}, indent=2)
        expected = (
            '{\n'
            '  "报表": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "name": 甲\n'
            '    }\n'
            '  ]\n'
            '}'
        )
        self.assertEqual(out, expected)

    def test_indent_none_compact(self):
        out = app_config.serialize_no_quote({"a": 1}, indent=None)
        self.assertEqual(out, '{"a": 1}')


if __name__ == "__main__":
    unittest.main()
