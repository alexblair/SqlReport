"""
tests/test_result_transform.py — 结果集变换模块边界测试

覆盖 result_transform.py（报表页面 / 导出 / API 三处调用方共用的变换模块）：
1. sort_rows 边界 — 不存在的列/无效 dir/重复列/多字段/None 值
2. filter_rows 边界 — 不存在的列/特殊字符/操作符语义
3. select_columns 边界 — None/空/全无效回退/去重/保序/strip
4. column_indices 边界 — 索引映射

每个场景使用独立的 test_ 方法，遵循 Arrange-Act-Assert 模式。
"""

import unittest

import result_transform
from result_transform import (
    filter_rows,
    sort_rows,
    select_columns,
    column_indices,
)


# ===================================================================
# 1. sort_rows 边界
# ===================================================================

class TestSortRowsBoundaries(unittest.TestCase):
    """sort_rows 边界：不存在的列/无效 dir/多字段/None 值"""

    def test_sort_col_not_in_columns(self):
        """✅ Positive: sort 中 col 名不存在 → 忽略该排序条件"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("nonexistent", "asc")]
        result = sort_rows(rows, columns, sorts)
        # 排序条件被忽略，顺序不变
        self.assertEqual(result, [(2, "b"), (1, "a")])

    def test_sort_dir_invalid(self):
        """✅ Positive: sort 中 dir='INVALID' → 视为 asc（非 'desc' 即升序）"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("id", "INVALID")]
        result = sort_rows(rows, columns, sorts)
        # "INVALID" != "desc"，所以升序：1 在 2 前
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[1][0], 2)

    def test_sort_dir_empty(self):
        """✅ Positive: sort 中 dir='' → 视为 asc"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("id", "")]
        result = sort_rows(rows, columns, sorts)
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[1][0], 2)

    def test_sort_duplicate_col_last_wins(self):
        """✅ Positive: 同一列重复出现 → 保留最后的方向（稳定排序）"""
        rows = [(1, "z"), (2, "y"), (3, "x")]
        columns = ["id", "name"]
        # 按优先级从高到低：name(asc) 之后 name(desc)——后者先应用，前者后应用生效
        sorts = [("name", "asc"), ("name", "desc")]
        result = sort_rows(rows, columns, sorts)
        # reversed 顺序应用，最后保留的优先级最高的条件生效
        names = [r[1] for r in result]
        self.assertEqual(names, ["x", "y", "z"])

    def test_sort_multiple_cols(self):
        """✅ Positive: 多字段排序（先 name asc，再 id desc）"""
        rows = [(2, "a"), (1, "a"), (3, "b")]
        columns = ["id", "name"]
        sorts = [("name", "asc"), ("id", "desc")]
        result = sort_rows(rows, columns, sorts)
        # name asc: all "a"s first, then "b"
        # then id desc within same name: 2, 1, 3
        self.assertEqual([r[0] for r in result], [2, 1, 3])

    def test_sort_none_values_at_end(self):
        """✅ Positive: None 值始终排在最后（升序）"""
        rows = [(3, "c"), (1, None), (2, "a")]
        columns = ["id", "name"]
        sorts = [("name", "asc")]
        result = sort_rows(rows, columns, sorts)
        # asc: "a", "c", None
        names = [r[1] for r in result]
        self.assertEqual(names, ["a", "c", None])

    def test_sort_none_values_at_end_desc(self):
        """✅ Positive: None 值始终排在最后（降序）"""
        rows = [(3, "c"), (1, None), (2, "a")]
        columns = ["id", "name"]
        sorts = [("name", "desc")]
        result = sort_rows(rows, columns, sorts)
        # desc: "c", "a", None
        names = [r[1] for r in result]
        self.assertEqual(names, ["c", "a", None])

    def test_sort_numeric_strings(self):
        """✅ Positive: 数值字符串按字符串排序（与历史行为一致）"""
        rows = [(1, "10"), (2, "2"), (3, "1")]
        columns = ["id", "name"]
        sorts = [("name", "asc")]
        result = sort_rows(rows, columns, sorts)
        # str 比较："1" < "10" < "2"
        self.assertEqual([r[0] for r in result], [3, 1, 2])


# ===================================================================
# 2. filter_rows 边界
# ===================================================================

class TestFilterRowsBoundaries(unittest.TestCase):
    """filter_rows 边界：不存在的列/特殊字符/操作符语义"""

    def test_filter_col_not_in_columns(self):
        """✅ Positive: filter 中 col 名不存在 → 忽略该条件"""
        rows = [(1, "hello"), (2, "world")]
        columns = ["id", "name"]
        filters = [("nonexistent", "contains", "hello")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 2)

    def test_filter_special_sql_chars_percent(self):
        """✅ Positive: 筛选值含 '%' → 纯文本匹配，非 SQL LIKE"""
        rows = [(1, "100%"), (2, "200"), (3, "300%")]
        columns = ["id", "name"]
        filters = [("name", "contains", "%")]
        result = filter_rows(rows, columns, filters)
        # Python str in 检查，% 为普通字符
        self.assertEqual(len(result), 2)  # 100% 和 300% 匹配
        self.assertEqual(result[0][1], "100%")
        self.assertEqual(result[1][1], "300%")

    def test_filter_special_sql_chars_underscore(self):
        """✅ Positive: 筛选值含 '_' → 纯文本匹配"""
        rows = [(1, "hello_world"), (2, "helloworld")]
        columns = ["id", "name"]
        filters = [("name", "contains", "_")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "hello_world")

    def test_filter_special_sql_chars_quote(self):
        """✅ Positive: 筛选值含单引号 → 正常处理"""
        rows = [(1, "it's"), (2, "its")]
        columns = ["id", "name"]
        filters = [("name", "contains", "'")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "it's")

    def test_filter_isempty_matches_none(self):
        """✅ Positive: isempty 操作符匹配 None 值"""
        rows = [(1, None), (2, "a"), (3, "")]
        columns = ["id", "name"]
        filters = [("name", "isempty", "")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 2)  # None 和 "" 都匹配
        self.assertIsNone(result[0][1])
        self.assertEqual(result[1][1], "")

    def test_filter_isempty_matches_empty_string(self):
        """✅ Positive: isempty 操作符匹配空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "isempty", "")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "")

    def test_filter_notempty_excludes_none(self):
        """✅ Positive: notempty 操作符排除 None"""
        rows = [(1, None), (2, "a"), (3, "")]
        columns = ["id", "name"]
        filters = [("name", "notempty", "")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "a")

    def test_filter_notempty_excludes_empty_string(self):
        """✅ Positive: notempty 操作符排除空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "notempty", "")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "b")

    def test_filter_eq_empty_string(self):
        """✅ Positive: eq 操作符匹配空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "eq", "")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "")

    def test_filter_gt_numeric(self):
        """✅ Positive: gt 操作符数值比较"""
        rows = [(1, "10"), (2, "abc"), (3, "30")]
        columns = ["id", "name"]
        filters = [("name", "gt", "15")]
        result = filter_rows(rows, columns, filters)
        # 非数值行被排除，"30" > 15
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 3)

    def test_filter_gt_invalid_query(self):
        """✅ Positive: gt 筛选值非数值 → 条件被忽略（全部保留）"""
        rows = [(1, "10"), (2, "20")]
        columns = ["id", "name"]
        filters = [("name", "gt", "abc")]
        result = filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 2)


# ===================================================================
# 3. select_columns 边界
# ===================================================================

class TestSelectColumnsBoundaries(unittest.TestCase):
    """select_columns 边界：None/空/全无效回退/去重/保序/strip"""

    def test_none_returns_all(self):
        """✅ Positive: requested=None → 返回全部列"""
        result = select_columns(["a", "b", "c"], None)
        self.assertEqual(result, ["a", "b", "c"])

    def test_empty_list_returns_all(self):
        """✅ Positive: requested=[] → 返回全部列"""
        result = select_columns(["a", "b", "c"], [])
        self.assertEqual(result, ["a", "b", "c"])

    def test_empty_string_returns_all(self):
        """✅ Positive: requested="" → 返回全部列"""
        result = select_columns(["a", "b", "c"], "")
        self.assertEqual(result, ["a", "b", "c"])

    def test_select_subset(self):
        """✅ Positive: 请求子集 → 按请求顺序返回"""
        result = select_columns(["a", "b", "c"], ["c", "a"])
        self.assertEqual(result, ["c", "a"])

    def test_invalid_col_ignored(self):
        """✅ Positive: 无效列名被忽略"""
        result = select_columns(["a", "b", "c"], ["x", "b"])
        self.assertEqual(result, ["b"])

    def test_all_invalid_falls_back(self):
        """✅ Positive: 全部无效 → 回退全部列"""
        result = select_columns(["a", "b", "c"], ["x", "y"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_duplicates_deduplicated(self):
        """✅ Positive: 重复列名去重（保留首个位置）"""
        result = select_columns(["a", "b", "c"], ["b", "b", "a", "b"])
        self.assertEqual(result, ["b", "a"])

    def test_reverse_order(self):
        """✅ Positive: 逆序请求 → 按请求顺序（非原始列序）"""
        result = select_columns(["a", "b", "c"], ["c", "b", "a"])
        self.assertEqual(result, ["c", "b", "a"])

    def test_string_input_with_strip(self):
        """✅ Positive: 逗号分隔字符串输入，元素 strip 后匹配"""
        result = select_columns(["a", "b"], " a, b ")
        self.assertEqual(result, ["a", "b"])

    def test_list_input_with_strip(self):
        """✅ Positive: 列表元素带空格 → strip 后匹配"""
        result = select_columns(["a", "b"], [" a "])
        self.assertEqual(result, ["a"])

    def test_original_list_unchanged(self):
        """✅ Positive: 输入列表不被修改"""
        requested = ["b", "a"]
        select_columns(["a", "b", "c"], requested)
        self.assertEqual(requested, ["b", "a"])


# ===================================================================
# 4. column_indices 边界
# ===================================================================

class TestColumnIndicesBoundaries(unittest.TestCase):
    """column_indices 边界：索引映射"""

    def test_basic_mapping(self):
        """✅ Positive: 显示列映射为原始列索引"""
        result = column_indices(["c", "a"], ["a", "b", "c"])
        self.assertEqual(result, [2, 0])

    def test_all_columns(self):
        """✅ Positive: 全部列 → 顺序索引"""
        result = column_indices(["a", "b", "c"], ["a", "b", "c"])
        self.assertEqual(result, [0, 1, 2])

    def test_duplicate_display_cols(self):
        """✅ Positive: 显示列含重复 → 索引重复"""
        result = column_indices(["a", "a"], ["a", "b"])
        self.assertEqual(result, [0, 0])


# ===================================================================
# 5. 模块符号完整性
# ===================================================================

class TestResultTransformModuleSymbols(unittest.TestCase):
    """模块符号完整性：公开接口存在且为函数"""

    def test_public_symbols_exist(self):
        for name in ("filter_rows", "sort_rows", "select_columns", "column_indices"):
            self.assertTrue(
                callable(getattr(result_transform, name)),
                f"缺少公开符号: {name}",
            )

    def test_no_report_import_cycle(self):
        """✅ Positive: 模块不依赖 report.py（纯函数，无 IO）"""
        import result_transform as rt
        self.assertNotIn("report", rt.__dict__)


if __name__ == "__main__":
    unittest.main()
