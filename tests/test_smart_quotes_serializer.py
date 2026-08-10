"""
test_smart_quotes_serializer.py — app_config.serialize_smart_quotes「智能去引号」序列化测试

覆盖（对应 .scratch/smart-quotes-json/issues/01 覆盖矩阵）：
- 3 特征互斥判定：十进制数字（含正负号）/ 科学计数法 / 千分位数字，位图组合矩阵
- 合法化转换：去逗号 → 去前导 + → 去前导零（文本级，不过 float/int）
- 兜底：RFC 8259 number ABNF 直译严格正则，转换后仍非法 → 回退带引号
- 禁止清单：非 number 语法、字符串 true/false/null、Infinity/NaN、空串、全角等一律带引号
- 增量语义：flags=0 与 serialize_json 逐字节等价
- 原生 int/float/Decimal/bool/None 恒按标准 JSON（flags 任意值不变）
- 兜底校验不得用 json.loads（Python 放行 Infinity/NaN）
- indent 模式与 json.dumps(indent=N) 形状一致，值按判定裸出
"""

import unittest
import json
from datetime import date, datetime
from decimal import Decimal

import app_config


# 位图常量（与实现对齐）
F_DECIMAL = 1
F_SCIENTIFIC = 2
F_THOUSAND = 4


class TestSmartFlagsValidation(unittest.TestCase):
    """flags 位图校验。"""

    def test_invalid_flag_bits_rejected(self):
        with self.assertRaises(ValueError):
            app_config.serialize_smart_quotes({"a": 1}, flags=8)
        with self.assertRaises(ValueError):
            app_config.serialize_smart_quotes({"a": 1}, flags=-1)

    def test_zero_flags_ok(self):
        app_config.serialize_smart_quotes({"a": 1}, flags=0)


class TestSmartIncrementalEquivalence(unittest.TestCase):
    """增量语义：flags=0 与 serialize_json 逐字节等价（零破坏承诺）。"""

    def test_zero_flags_equals_serialize_json(self):
        cases = [
            {"name": "张三", "age": 25, "score": 9.99, "ok": True, "none": None},
            {"amount": Decimal("123.45"), "d": date(2026, 1, 2)},
            {"b": b"raw", "t": datetime(2026, 1, 2, 3, 4, 5)},
            {"rows": [{"x": "1,000"}, {"x": "1e5"}], "empty": [], "nested": {}},
            {"code": "007", "signed": "-1.5"},
        ]
        for obj in cases:
            self.assertEqual(
                app_config.serialize_smart_quotes(obj, flags=0),
                app_config.serialize_json(obj))

    def test_zero_flags_with_indent_equals_serialize_json(self):
        obj = {"报表": [{"id": 1, "name": "甲", "v": "9.999"}]}
        self.assertEqual(
            app_config.serialize_smart_quotes(obj, flags=0, indent=2),
            app_config.serialize_json(obj, indent=2))


class TestSmartScalarNativeTypes(unittest.TestCase):
    """原生类型恒按标准 JSON（flags 任意值不改变输出）。"""

    def test_native_numbers_bool_none_constant(self):
        for flags in (F_DECIMAL, F_SCIENTIFIC, F_THOUSAND, 7):
            self.assertEqual(
                app_config.serialize_smart_quotes(25, flags=flags), "25")
            self.assertEqual(
                app_config.serialize_smart_quotes(-7.5, flags=flags), "-7.5")
            self.assertEqual(
                app_config.serialize_smart_quotes(True, flags=flags), "true")
            self.assertEqual(
                app_config.serialize_smart_quotes(False, flags=flags), "false")
            self.assertEqual(
                app_config.serialize_smart_quotes(None, flags=flags), "null")

    def test_decimal_follows_standard_json(self):
        """Decimal 在标准 JSON（default=str）下带引号，跟随现状语义。"""
        for flags in (0, F_DECIMAL, 7):
            self.assertEqual(
                app_config.serialize_smart_quotes(Decimal("123.45"), flags=flags),
                json.dumps(Decimal("123.45"), ensure_ascii=False, default=str))

    def test_date_datetime_follows_standard_json(self):
        self.assertEqual(
            app_config.serialize_smart_quotes(date(2026, 1, 2), flags=7),
            '"2026-01-02"')
        self.assertEqual(
            app_config.serialize_smart_quotes(datetime(2026, 1, 2, 3, 4, 5), flags=7),
            '"2026-01-02 03:04:05"')


class TestSmartMutualExclusion(unittest.TestCase):
    """3 特征互斥：每个值至多命中一项；未勾选的形态保持带引号。"""

    def test_decimal_only_matches_decimal_flag(self):
        # -1.5 仅命中十进制；勾科学或千分位不生效
        self.assertEqual(
            app_config.serialize_smart_quotes("-1.5", flags=F_DECIMAL), "-1.5")
        self.assertEqual(
            app_config.serialize_smart_quotes("-1.5", flags=F_SCIENTIFIC),
            json.dumps("-1.5", ensure_ascii=False))
        self.assertEqual(
            app_config.serialize_smart_quotes("-1.5", flags=F_THOUSAND),
            json.dumps("-1.5", ensure_ascii=False))

    def test_scientific_only_matches_scientific_flag(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("1e5", flags=F_SCIENTIFIC), "1e5")
        self.assertEqual(
            app_config.serialize_smart_quotes("1e5", flags=F_DECIMAL),
            json.dumps("1e5", ensure_ascii=False))
        self.assertEqual(
            app_config.serialize_smart_quotes("1e5", flags=F_THOUSAND),
            json.dumps("1e5", ensure_ascii=False))

    def test_thousand_only_matches_thousand_flag(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("1,000", flags=F_THOUSAND), "1000")
        self.assertEqual(
            app_config.serialize_smart_quotes("1,000", flags=F_DECIMAL),
            json.dumps("1,000", ensure_ascii=False))
        self.assertEqual(
            app_config.serialize_smart_quotes("1,000", flags=F_SCIENTIFIC),
            json.dumps("1,000", ensure_ascii=False))

    def test_flag_combination_or_semantics(self):
        # flags=5：十进制 + 千分位；科学未勾 → 1e5 带引号
        self.assertEqual(
            app_config.serialize_smart_quotes("9.999", flags=5), "9.999")
        self.assertEqual(
            app_config.serialize_smart_quotes("1,000", flags=5), "1000")
        self.assertEqual(
            app_config.serialize_smart_quotes("1e5", flags=5),
            json.dumps("1e5", ensure_ascii=False))

    def test_plain_text_never_stripped(self):
        for flags in (F_DECIMAL, F_SCIENTIFIC, F_THOUSAND, 7):
            self.assertEqual(
                app_config.serialize_smart_quotes("abc", flags=flags),
                json.dumps("abc", ensure_ascii=False))


class TestSmartNormalization(unittest.TestCase):
    """合法化转换：去逗号 → 去前导 + → 去前导零。"""

    def test_leading_zeros_removed(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("007", flags=F_DECIMAL), "7")
        self.assertEqual(
            app_config.serialize_smart_quotes("007", flags=F_THOUSAND),
            json.dumps("007", ensure_ascii=False))
        self.assertEqual(
            app_config.serialize_smart_quotes("01.50", flags=F_DECIMAL), "1.50")
        self.assertEqual(
            app_config.serialize_smart_quotes("00.5", flags=F_DECIMAL), "0.5")

    def test_zero_kept(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("0", flags=F_DECIMAL), "0")
        self.assertEqual(
            app_config.serialize_smart_quotes("0.5", flags=F_DECIMAL), "0.5")

    def test_neg_zero_kept(self):
        # -0 为 RFC 8259 合法数字（minus zero），不得改动
        self.assertEqual(
            app_config.serialize_smart_quotes("-0", flags=F_DECIMAL), "-0")

    def test_leading_plus_removed(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("+5", flags=F_DECIMAL), "5")
        self.assertEqual(
            app_config.serialize_smart_quotes("+007", flags=F_DECIMAL), "7")
        self.assertEqual(
            app_config.serialize_smart_quotes("+1.5", flags=F_DECIMAL), "1.5")
        # 电话号形态：前导 + 后全数字，按「带符号」语义去 + 数值化
        self.assertEqual(
            app_config.serialize_smart_quotes("+8613800000000", flags=F_DECIMAL),
            "8613800000000")
        json.loads(
            app_config.serialize_smart_quotes("+8613800000000", flags=F_DECIMAL))

    def test_signed_kept(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("-1.5", flags=F_DECIMAL), "-1.5")
        self.assertEqual(
            app_config.serialize_smart_quotes("-9.99", flags=F_DECIMAL), "-9.99")

    def test_thousand_commas_removed(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("1,000", flags=F_THOUSAND), "1000")
        self.assertEqual(
            app_config.serialize_smart_quotes("-1,234.50", flags=F_THOUSAND),
            "-1234.50")
        self.assertEqual(
            app_config.serialize_smart_quotes("1,234,567", flags=F_THOUSAND),
            "1234567")
        self.assertEqual(
            app_config.serialize_smart_quotes("0,007", flags=F_THOUSAND), "7")
        self.assertEqual(
            app_config.serialize_smart_quotes("00,000", flags=F_THOUSAND), "0")

    def test_malformed_thousand_kept_quoted(self):
        # 千分位必须 1-3 位 + 每组 3 位；1,00 不合法 → 带引号
        self.assertEqual(
            app_config.serialize_smart_quotes("1,00", flags=F_THOUSAND),
            json.dumps("1,00", ensure_ascii=False))

    def test_scientific_preserved(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("1e5", flags=F_SCIENTIFIC), "1e5")
        self.assertEqual(
            app_config.serialize_smart_quotes("1E+5", flags=F_SCIENTIFIC), "1E+5")
        self.assertEqual(
            app_config.serialize_smart_quotes("1e-5", flags=F_SCIENTIFIC), "1e-5")
        self.assertEqual(
            app_config.serialize_smart_quotes("-1.5e-3", flags=F_SCIENTIFIC),
            "-1.5e-3")

    def test_scientific_normalization_applied(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("007e5", flags=F_SCIENTIFIC), "7e5")
        self.assertEqual(
            app_config.serialize_smart_quotes("+1e5", flags=F_SCIENTIFIC), "1e5")

    def test_plain_9_999_kept_verbatim(self):
        self.assertEqual(
            app_config.serialize_smart_quotes("9.999", flags=F_DECIMAL), "9.999")


class TestSmartOutputAlwaysValidJson(unittest.TestCase):
    """产品承诺：裸输出文本全部可被标准解析器 json.loads 解析。"""

    def test_stripped_values_are_parseable(self):
        samples = [
            ("-9.99", F_DECIMAL),
            ("9.999", F_DECIMAL),
            ("007", F_DECIMAL),
            ("+5", F_DECIMAL),
            ("-0", F_DECIMAL),
            ("1e5", F_SCIENTIFIC),
            ("1E+5", F_SCIENTIFIC),
            ("1e-3", F_SCIENTIFIC),
            ("1,000", F_THOUSAND),
            ("-1,234.50", F_THOUSAND),
        ]
        for text, flags in samples:
            out = app_config.serialize_smart_quotes({"v": text}, flags=flags)
            payload = json.loads(out)  # 必须可解析
            self.assertIsInstance(payload["v"], (int, float), f"{text} 应解析为数值")

    def test_full_object_parseable(self):
        out = app_config.serialize_smart_quotes({
            "name": "张三",
            "a": "007",
            "b": "-1,234.50",
            "c": "1e5",
            "text": "1-2",
            "empty": "",
            "flag": "true",
        }, flags=7)
        payload = json.loads(out)
        self.assertEqual(payload["a"], 7)
        self.assertEqual(payload["b"], -1234.5)
        self.assertEqual(payload["c"], 100000.0)
        self.assertEqual(payload["text"], "1-2")
        self.assertEqual(payload["empty"], "")
        self.assertEqual(payload["flag"], "true")


class TestSmartForbiddenList(unittest.TestCase):
    """禁止清单：一律带引号（标准 JSON 字符串）。"""

    def test_quoted_strings(self):
        cases = [
            "abc", "张三", "ID-001", "2026-08-10", "1-2", "1/2", "50%",
            "1 000", " 5", "5 ", "1.2.3", "0086-010-1234",
            "true", "false", "null", "True", "FALSE",
            "Infinity", "-Infinity", "NaN", "undefined",
            "", ".", "-", "+", ",", "-.", "1e", "1E", "1e+", "e5",
            "5.", ".5", "1,000.5.5", "１２３", "－1", "１，０００",
        ]
        for text in cases:
            for flags in (F_DECIMAL, F_SCIENTIFIC, F_THOUSAND, 7):
                out = app_config.serialize_smart_quotes(text, flags=flags)
                self.assertEqual(
                    out, json.dumps(text, ensure_ascii=False),
                    f"{text!r} flags={flags} 应带引号输出")
                json.loads(out)  # 输出必须可解析

    def test_quoted_strings_in_dict(self):
        out = app_config.serialize_smart_quotes(
            {"a": "abc", "b": "true", "c": "1e", "d": ""}, flags=7)
        json.loads(out)  # 结构完整
        self.assertIn('"a": "abc"', out)
        self.assertIn('"b": "true"', out)


class TestSmartFallback(unittest.TestCase):
    """兜底：RFC 8259 number 语法严格校验，拒绝 json.loads 放行的形态。"""

    def test_validator_rejects_what_json_loads_accepts(self):
        # 验证证据：json.loads 放行 'Infinity'/'NaN'（RFC 8259 禁止），
        # 兜底校验必须拒绝 → 不能使用 json.loads 做校验。
        for bad in ("Infinity", "-Infinity", "NaN"):
            self.assertTrue(json.loads(bad) is not None)  # loads 放行（前提）
            self.assertFalse(app_config._smart_valid_number(bad))

    def test_validator_rejects_invalid_forms(self):
        for bad in ("", ".", "-", "+", ",", "-.", "007", "+5", "1e", "e5",
                    "5.", ".5", "1e5x", "1.2.3", "0x10", "1_000", " 5", "5 ",
                    "12３4"):
            self.assertFalse(
                app_config._smart_valid_number(bad), f"{bad!r} 不应通过")

    def test_validator_accepts_valid_forms(self):
        for good in ("0", "-0", "0.5", "1", "-9.99", "1e5", "1E+5", "1e-3",
                     "1000", "-1234.50", "7e5", "12345678901234567890"):
            self.assertTrue(
                app_config._smart_valid_number(good), f"{good!r} 应通过")


class TestSmartStructure(unittest.TestCase):
    """结构处理：键标准引号、值按判定、嵌套/空容器。"""

    def test_dict_structure(self):
        out = app_config.serialize_smart_quotes(
            {"name": "张三", "code": "007", "sci": "1e5", "n": 1}, flags=7)
        self.assertEqual(
            out, '{"name": "张三", "code": 7, "sci": 1e5, "n": 1}')

    def test_dict_empty(self):
        self.assertEqual(
            app_config.serialize_smart_quotes({}, flags=7), "{}")

    def test_list(self):
        self.assertEqual(
            app_config.serialize_smart_quotes(["1,000", "abc", 2], flags=7),
            "[1000, \"abc\", 2]")

    def test_tuple_like_list(self):
        self.assertEqual(
            app_config.serialize_smart_quotes(("1e5",), flags=F_SCIENTIFIC),
            "[1e5]")

    def test_list_empty(self):
        self.assertEqual(
            app_config.serialize_smart_quotes([], flags=7), "[]")

    def test_nested(self):
        out = app_config.serialize_smart_quotes(
            {"rows": [{"x": "007", "s": "甲"}]}, flags=7)
        self.assertEqual(out, '{"rows": [{"x": 7, "s": "甲"}]}')

    def test_unicode_key(self):
        self.assertEqual(
            app_config.serialize_smart_quotes({"单价": "9.99"}, flags=F_DECIMAL),
            '{"单价": 9.99}')

    def test_key_always_quoted_and_escaped(self):
        out = app_config.serialize_smart_quotes({'a"b': "1,000"}, flags=7)
        self.assertEqual(out, '{"a\\"b": 1000}')

    def test_insertion_order_preserved(self):
        self.assertEqual(
            app_config.serialize_smart_quotes({"b": "1", "a": "2"}, flags=F_DECIMAL),
            '{"b": 1, "a": 2}')


class TestSmartBytes(unittest.TestCase):
    """bytes：flags=0 走标准（b'' 形态）；面板开启时 UTF-8 decode 后按字符串判定。"""

    def test_bytes_zero_flags_standard(self):
        self.assertEqual(
            app_config.serialize_smart_quotes(b"abc", flags=0),
            json.dumps(b"abc", ensure_ascii=False, default=str))

    def test_bytes_decoded_and_judged(self):
        self.assertEqual(
            app_config.serialize_smart_quotes(b"123", flags=F_DECIMAL), "123")
        self.assertEqual(
            app_config.serialize_smart_quotes(b"abc", flags=7),
            json.dumps("abc", ensure_ascii=False))


class TestSmartIndent(unittest.TestCase):
    """indent 模式：与 json.dumps(indent=N) 形状一致，值按判定裸出。"""

    def test_indent_shape(self):
        out = app_config.serialize_smart_quotes(
            {"报表": [{"id": 1, "name": "甲", "v": "007"}]}, flags=7, indent=2)
        expected = (
            '{\n'
            '  "报表": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "name": "甲",\n'
            '      "v": 7\n'
            '    }\n'
            '  ]\n'
            '}'
        )
        self.assertEqual(out, expected)

    def test_indent_none_compact(self):
        self.assertEqual(
            app_config.serialize_smart_quotes({"a": "1,000"}, flags=7, indent=None),
            '{"a": 1000}')


if __name__ == "__main__":
    unittest.main()
