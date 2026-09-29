"""
tests/test_result_transform_perf.py — result_transform 类型快速路径与单趟化

分两批（T2 类型快速路径 / T3 单趟化），本文件是两者共同的测试基座。

**为什么先写这些测试**：C-1b/C-1c 的错误模式是**静默改变行序与行内容**——
不报错，只是用户看到的排序/筛选结果变了。所以这里的断言必须精确到
「哪一行排在第几位」，而不只是「结果集条数对」。

T2 关注点：MySQL 的 DECIMAL 列返回 `decimal.Decimal`，它不在
`_parse_numeric_or_date` 的 `isinstance(s, (int, float))` 快速路径内，
于是每个单元格都要走 `str().strip()` + 正则 + `float()` 三连。
这些测试把「Decimal 必须走快速路径」钉死。
"""

import unittest
from decimal import Decimal
from unittest.mock import patch

import result_transform
from result_transform import (
    _parse_numeric_or_date, _try_float, filter_rows, sort_rows,
)


class TestDecimalFastPath(unittest.TestCase):
    """T2：_parse_numeric_or_date 的 Decimal 快速路径。"""

    def test_decimal_bypasses_date_regex(self):
        """✅ Positive: Decimal 单元格不得走日期正则（那是最贵的一步）。"""
        with patch.object(result_transform, "_DATE_RE") as mock_re:
            mock_re.match.side_effect = AssertionError(
                "Decimal 单元格不应走 _DATE_RE.match")
            result = _parse_numeric_or_date(Decimal("123.45"))
        self.assertEqual(result, (123.45, None))
        mock_re.match.assert_not_called()

    def test_decimal_none_returns_none_none(self):
        """✅ Positive: None 仍返回 (None, None)。"""
        self.assertEqual(_parse_numeric_or_date(None), (None, None))

    def test_decimal_infinity_treated_as_uncomparable(self):
        """✅ Positive: Decimal('Infinity') 必须按不可比较处理。

        快速路径若漏掉 isfinite 检查，Infinity 会变成 inf 参与数值比较，
        静默产出错误排序。既有语义（见 _try_float docstring 的
        「独立找茬中危项 #3」）不得被快速路径绕过。
        """
        self.assertEqual(_parse_numeric_or_date(Decimal("Infinity")),
                         (None, None))
        self.assertEqual(_parse_numeric_or_date(Decimal("NaN")), (None, None))

    def test_decimal_matches_float_result(self):
        """✅ Positive: Decimal 与等价 float 的解析结果完全一致。"""
        for d, f in ((Decimal("10.50"), 10.50), (Decimal("0"), 0.0),
                     (Decimal("-3.75"), -3.75)):
            self.assertEqual(_parse_numeric_or_date(d), (f, None))
            self.assertEqual(_parse_numeric_or_date(d), _parse_numeric_or_date(f))

    def test_decimal_bool_not_treated_as_numeric(self):
        """✅ Positive: bool 仍按既有语义 (None, None) 处理，不得被快速路径吞掉。"""
        self.assertEqual(_parse_numeric_or_date(True), (None, None))
        self.assertEqual(_parse_numeric_or_date(False), (None, None))

    def test_iso_date_string_still_parsed(self):
        """✅ Positive: 快速路径不得吃掉日期字符串的既有行为。"""
        num, date_val = _parse_numeric_or_date("2026-01-31")
        self.assertIsNone(num)
        self.assertIsNotNone(date_val)
        self.assertEqual(date_val.year, 2026)
        self.assertEqual(date_val.month, 1)
        self.assertEqual(date_val.day, 31)


class TestTryFloatBehavior(unittest.TestCase):
    """T2：_try_float 的语义锁定（快速路径不得改变任何既有行为）。"""

    def test_int_and_float_pass_through(self):
        self.assertEqual(_try_float(3), 3.0)
        self.assertEqual(_try_float(3.5), 3.5)

    def test_bool_keeps_existing_float_coercion(self):
        """✅ Positive: 既有代码对 bool 没有特判，float(True)==1.0。

        快速路径若「顺手」排除 bool 就会改变语义，故显式钉住。
        """
        self.assertEqual(_try_float(True), 1.0)
        self.assertEqual(_try_float(False), 0.0)

    def test_numeric_string_and_text(self):
        self.assertEqual(_try_float("12.5"), 12.5)
        self.assertIsNone(_try_float("abc"))
        self.assertIsNone(_try_float(""))

    def test_nan_and_inf_return_none(self):
        self.assertIsNone(_try_float(float("nan")))
        self.assertIsNone(_try_float(float("inf")))

    def test_none_returns_none(self):
        self.assertIsNone(_try_float(None))


class TestDecimalSemanticsInFilterAndSort(unittest.TestCase):
    """T2 端到端：Decimal 列的筛选与排序结果必须与 float 列完全一致。"""

    COLS = ["amount"]

    def test_gt_filter_same_for_decimal_and_float(self):
        dec_rows = [(Decimal("10.50"),), (Decimal("200.00"),), (None,),
                    (Decimal("99.99"),)]
        flt_rows = [(10.50,), (200.00,), (None,), (99.99,)]
        filters = [("amount", "gt", "100")]
        self.assertEqual(filter_rows(dec_rows, self.COLS, filters),
                         filter_rows(flt_rows, self.COLS, filters))
        self.assertEqual(filter_rows(dec_rows, self.COLS, filters),
                         [(Decimal("200.00"),)])

    def test_sort_ascending_same_for_decimal_and_float(self):
        dec_rows = [(Decimal("10.50"),), (None,), (Decimal("2.25"),),
                    (Decimal("-5.00"),)]
        flt_rows = [(10.50,), (None,), (2.25,), (-5.00,)]
        self.assertEqual(sort_rows(dec_rows, self.COLS, [("amount", "asc")]),
                         sort_rows(flt_rows, self.COLS, [("amount", "asc")]))
        self.assertEqual(
            sort_rows(dec_rows, self.COLS, [("amount", "asc")]),
            [(Decimal("-5.00"),), (Decimal("2.25"),), (Decimal("10.50"),), (None,)])

    def test_sort_descending_keeps_none_last(self):
        """✅ Positive: None 恒最后，不受升降序影响（既有语义）。"""
        rows = [(Decimal("10.50"),), (None,), (Decimal("2.25"),)]
        self.assertEqual(
            sort_rows(rows, self.COLS, [("amount", "desc")]),
            [(Decimal("10.50"),), (Decimal("2.25"),), (None,)])


if __name__ == "__main__":
    unittest.main()
