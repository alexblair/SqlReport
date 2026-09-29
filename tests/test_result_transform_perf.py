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


class TestSortFilterCharacterization(unittest.TestCase):
    """T3 前置：改代码**之前**先把这些行为钉死。

    下面的期望值不是推导出来的，是用未改动的实现实测出来的真实行序
    （见 spec §10.2 第 1 条的教训：性能判断必须先量）。
    C-1c 的错误模式是静默换行序，所以这些断言精确到「哪一行排第几位」。
    """

    COLS = ["v"]
    MIXED = [None, 3, "2.5", "abc", 1.5, "", -2, "0", "10"]

    def _rows(self):
        return [(v,) for v in self.MIXED]

    def test_sort_ascending_exact_order(self):
        """✅ 实测行序：数值组升序 → 文本组升序 → None 恒最后。

        注意 '0' 与 '10' 是「数字字符串」，_try_float 成功 → 进数值组，
        按数值排在 1.5/2.5/3 之间，不是按字符串排在 '2.5' 之后。
        """
        rows = [(v,) for v in self.MIXED]
        self.assertEqual(
            [r[0] for r in sort_rows(rows, self.COLS, [("v", "asc")])],
            [-2, "0", 1.5, "2.5", 3, "10", "", "abc", None])

    def test_sort_descending_exact_order(self):
        """✅ 实测行序：降序时数值组与文本组各自降序，但 None 仍在最后。"""
        rows = [(v,) for v in self.MIXED]
        self.assertEqual(
            [r[0] for r in sort_rows(rows, self.COLS, [("v", "desc")])],
            ["10", 3, "2.5", 1.5, "0", -2, "abc", "", None])

    def test_none_always_last_both_directions(self):
        """✅ Positive: None 不受升降序影响（模块 docstring 的领域约定）。"""
        rows = [(None,), (1,), (None,), (2,)]
        for direction in ("asc", "desc"):
            out = [r[0] for r in sort_rows(rows, self.COLS, [("v", direction)])]
            self.assertEqual(out[-1], None, f"{direction} 时 None 应在最后")

    def test_sort_multi_key_priority_and_stability(self):
        """✅ 实测：主键 b 升序；b 相同则按 a 降序；完全相同的行保持输入次序。

        sorts=[("b","asc"),("a","desc")] 的优先级是 b 最高、a 次之
        （调用方按「从低优先级到高优先级」传入）。
        """
        rows = [("a1", 1), ("a1", 2), ("a1", 2), ("a2", 1), ("a1", 3)]
        self.assertEqual(
            sort_rows(rows, ["a", "b"], [("b", "asc"), ("a", "desc")]),
            [("a2", 1), ("a1", 1), ("a1", 2), ("a1", 2), ("a1", 3)])

    def test_sort_single_key_preserves_input_order_for_ties(self):
        """✅ Positive: 同 key 的行保持输入相对次序（稳定排序）。"""
        rows = [("a1", 1), ("a1", 2), ("a1", 2), ("a2", 1), ("a1", 3)]
        self.assertEqual(
            sort_rows(rows, ["a", "b"], [("a", "asc")]),
            [("a1", 1), ("a1", 2), ("a1", 2), ("a1", 3), ("a2", 1)])

    def test_filter_multiple_conditions_are_anded(self):
        """✅ Positive: 多条件是 AND，不是 OR。"""
        rows = [("alice", 10), ("bob", 20), ("carol", 30)]
        cols = ["name", "age"]
        out = filter_rows(rows, cols, [("name", "contains", "o"),
                                       ("age", "gt", "15")])
        self.assertEqual(out, [("bob", 20), ("carol", 30)])

    def test_unknown_column_filter_is_skipped_not_rows_dropped(self):
        """✅ Positive: 未知列的筛选条件被静默跳过（不丢行）。"""
        rows = [("alice", 10), ("bob", 20)]
        self.assertEqual(
            filter_rows(rows, ["name", "age"], [("nope", "eq", "x")]), rows)

    def test_unknown_column_sort_is_skipped(self):
        """✅ Positive: 未知列的排序键被静默跳过，保持原序。"""
        rows = [("bob", 20), ("alice", 10)]
        self.assertEqual(sort_rows(rows, ["name", "age"], [("nope", "asc")]), rows)

    def test_no_filters_returns_same_object(self):
        """✅ Positive: 无筛选时返回原对象（不做无谓拷贝）。"""
        rows = [(1,), (2,)]
        self.assertIs(filter_rows(rows, ["v"], None), rows)
        self.assertIs(filter_rows(rows, ["v"], []), rows)

    def test_no_sorts_returns_same_object(self):
        """✅ Positive: 无排序时返回原对象。"""
        rows = [(1,), (2,)]
        self.assertIs(sort_rows(rows, ["v"], None), rows)
        self.assertIs(sort_rows(rows, ["v"], []), rows)

    def test_numeric_string_sorts_numerically_not_lexically(self):
        """✅ 实测：数字字符串按**数值**排序，不是按字典序。

        输入 ['9','100','10'] → 实测 ['9','10','100']（数值序 9<10<100）。
        若退化成字典序，结果应是 ['100','10','9']。返回值仍是原始字符串，
        变的只是行的先后。
        """
        rows = [("9",), ("100",), ("10",)]
        self.assertEqual(
            [r[0] for r in sort_rows(rows, ["v"], [("v", "asc")])],
            ["9", "10", "100"])


if __name__ == "__main__":
    unittest.main()
