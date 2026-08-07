"""
tests/test_result_transform.py — 结果集变换模块边界测试

覆盖 result_transform.py（报表页面 / 导出 / API 三处调用方共用的变换模块）：
1. sort_rows 边界 — 不存在的列/无效 dir/重复列/多字段/None 值
2. filter_rows 边界 — 不存在的列/特殊字符/操作符语义
3. select_columns 边界 — None/空/全无效回退/去重/保序/strip
4. column_indices 边界 — 索引映射

筛选匹配表达式批次覆盖（T1，全系统统一语法）：
5. parse_filter_expr 解析 — 通配 token/字面转义（\\* \\, \\\\）/多值分段/
   段 strip/空段忽略/全空返回 []/大小写与换行
6. filter_rows 通配多值 — contains 通配子串（不敏感）/eq/neq 通配（敏感）/
   多值 OR/全空忽略/值非字符串 str 防御/单值不 strip 保序
7. 既有纯文本回归 — 特殊字符（% _ '）按字面匹配、前缀/后缀/中间通配

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


class TestFilterRowsWildcardMultivalue(unittest.TestCase):
    """filter_rows 通配符 + 多值语义（仅 contains/eq/neq 生效）"""

    def test_contains_wildcard_prefix(self):
        """✅ Positive: contains 前缀通配 张* → 含以"张"开头的子串的行"""
        rows = [(1, "张飞"), (2, "刘备"), (3, "小张"), (4, "张")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "张*")])
        # 子串视角：* 可为空，"小张"的子串"张"也以"张"开头 → 命中
        self.assertEqual([r[0] for r in result], [1, 3, 4])

    def test_contains_wildcard_suffix(self):
        """✅ Positive: contains 后缀通配 *章 → 含以"章"结尾的子串的行"""
        rows = [(1, "文章"), (2, "华章"), (3, "章鱼")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "*章")])
        self.assertEqual([r[0] for r in result], [1, 2, 3])

    def test_contains_wildcard_middle(self):
        """✅ Positive: contains 中间通配 张*明 → 张开头明结尾的行"""
        rows = [(1, "张明"), (2, "张大明"), (3, "张小明"), (4, "王大明")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "张*明")])
        self.assertEqual([r[0] for r in result], [1, 2, 3])

    def test_contains_wildcard_full_wrap(self):
        """✅ Positive: contains *abc* 等价子串匹配（回归一致性）"""
        rows = [(1, "xabcy"), (2, "abc"), (3, "abd")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "*abc*")])
        self.assertEqual([r[0] for r in result], [1, 2])

    def test_contains_multivalue_or(self):
        """✅ Positive: contains 多值 OR（北京,上海 → 任一命中）"""
        rows = [(1, "北京"), (2, "上海"), (3, "广州"), (4, "北京上海")]
        columns = ["id", "city"]
        result = filter_rows(rows, columns, [("city", "contains", "北京,上海")])
        self.assertEqual([r[0] for r in result], [1, 2, 4])

    def test_contains_multivalue_mixed_wildcard(self):
        """✅ Positive: contains 多值混合通配（abc,*def*）"""
        rows = [(1, "xxabcxx"), (2, "xxdefxx"), (3, "abd"), (4, "abc")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "abc,*def*")])
        self.assertEqual([r[0] for r in result], [1, 2, 4])

    def test_contains_case_insensitive_wildcard(self):
        """✅ Positive: contains 通配大小写不敏感（*ABC* 匹配 abc）"""
        rows = [(1, "xxabcxx"), (2, "xxABxx")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "*ABC*")])
        self.assertEqual([r[0] for r in result], [1])

    def test_eq_wildcard(self):
        """✅ Positive: eq 通配整串匹配（张* → 以张开头的整串，含仅"张"）"""
        rows = [(1, "张飞"), (2, "飞张"), (3, "张飞燕"), (4, "张")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "eq", "张*")])
        self.assertEqual([r[0] for r in result], [1, 3, 4])

    def test_eq_multivalue_in(self):
        """✅ Positive: eq 多值 IN 语义（a,b → 任一相等，保持原行序）"""
        rows = [(1, "a"), (2, "b"), (3, "c"), (4, "a")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "eq", "a,b")])
        self.assertEqual([r[0] for r in result], [1, 2, 4])

    def test_neq_multivalue_not_in(self):
        """✅ Positive: neq 多值 NOT IN 语义（排除命中任一的值）"""
        rows = [(1, "a"), (2, "b"), (3, "c")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "neq", "a,b")])
        self.assertEqual([r[0] for r in result], [3])

    def test_neq_wildcard(self):
        """✅ Positive: neq 通配（张* → 排除以张开头的整串）"""
        rows = [(1, "张飞"), (2, "刘备"), (3, "张")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "neq", "张*")])
        self.assertEqual([r[0] for r in result], [2])

    def test_eq_case_sensitive(self):
        """✅ Positive: eq 通配大小写敏感（*ABC* 不匹配 abc）"""
        rows = [(1, "xxabcxx"), (2, "xxABCxx")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "eq", "*ABC*")])
        self.assertEqual([r[0] for r in result], [2])

    def test_neq_case_sensitive(self):
        """✅ Positive: neq 通配大小写敏感（排除命中任一大小写匹配的值）"""
        rows = [(1, "张飞"), (2, "zhangfei"), (3, "张")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "neq", "张*")])
        self.assertEqual([r[0] for r in result], [2])

    def test_escaped_star_literal_match(self):
        """✅ Positive: \\* 字面星号匹配（a\\*b 匹配 a*b 不匹配 axb）"""
        rows = [(1, "a*b"), (2, "axb"), (3, "ab")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", r"a\*b")])
        self.assertEqual([r[0] for r in result], [1])

    def test_escaped_comma_literal_match(self):
        """✅ Positive: \\, 字面逗号匹配（1\\,234 匹配 1,234 不拆多值）"""
        rows = [(1, "1,234"), (2, "1234"), (3, "1")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "eq", r"1\,234")])
        self.assertEqual([r[0] for r in result], [1])

    def test_numeric_row_value(self):
        """✅ Positive: 数值行值 str 化后匹配"""
        rows = [(1, 100), (2, 200), (3, 150)]
        columns = ["id", "amount"]
        result = filter_rows(rows, columns, [("amount", "contains", "10*")])
        self.assertEqual([r[0] for r in result], [1])
        result2 = filter_rows(rows, columns, [("amount", "eq", "100")])
        self.assertEqual([r[0] for r in result2], [1])

    def test_numeric_query_str_defense(self):
        """✅ Positive: 数字 q（API JSON 传入）→ str 防御不崩溃"""
        rows = [(1, "100"), (2, "200")]
        columns = ["id", "amount"]
        result = filter_rows(rows, columns, [("amount", "contains", 100)])
        self.assertEqual([r[0] for r in result], [1])

    def test_none_row_value(self):
        """✅ Positive: None 行值视为空串（通配不匹配、eq 空串匹配）"""
        rows = [(1, None), (2, "张三")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "张*")])
        self.assertEqual([r[0] for r in result], [2])
        result2 = filter_rows(rows, columns, [("name", "eq", "")])
        self.assertEqual([r[0] for r in result2], [1])

    def test_all_empty_multivalue_ignored(self):
        """✅ Positive: 全空多值（" , "）→ 条件忽略，全部保留"""
        rows = [(1, "a"), (2, "b")]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", " , ")])
        self.assertEqual(len(result), 2)

    def test_gt_multivalue_ignored(self):
        """✅ Positive: gt 含逗号 → 非数值条件忽略（保持现状）"""
        rows = [(1, "10"), (2, "20")]
        columns = ["id", "amount"]
        result = filter_rows(rows, columns, [("amount", "gt", "1,5")])
        self.assertEqual(len(result), 2)

    def test_percent_underscore_still_literal(self):
        """✅ Positive: 回归 — % / _ 仍为纯文本，非元字符"""
        rows = [(1, "100%"), (2, "hello_world"), (3, "helloworld")]
        columns = ["id", "name"]
        r1 = filter_rows(rows, columns, [("name", "contains", "%")])
        self.assertEqual([r[0] for r in r1], [1])
        r2 = filter_rows(rows, columns, [("name", "contains", "_")])
        self.assertEqual([r[0] for r in r2], [2])

    def test_contains_empty_string_matches_all(self):
        """✅ Positive: 回归 — contains 空串匹配所有行"""
        rows = [(1, "a"), (2, "b"), (3, None)]
        columns = ["id", "name"]
        result = filter_rows(rows, columns, [("name", "contains", "")])
        self.assertEqual(len(result), 3)

    def test_multiple_filters_and(self):
        """✅ Positive: 多列条件仍 AND（含新语义组合）"""
        rows = [(1, "北京", "张飞"), (2, "上海", "张飞"), (3, "北京", "刘备")]
        columns = ["id", "city", "name"]
        result = filter_rows(
            rows, columns,
            [("city", "contains", "北京,上海"), ("name", "contains", "张*")],
        )
        self.assertEqual([r[0] for r in result], [1, 2])


# ===================================================================
# 2.5 匹配表达式解析（通配符 + 多值 + 转义）
# ===================================================================

class TestParseFilterExpr(unittest.TestCase):
    """parse_filter_expr 边界：单值/通配/多值/转义/空段/strip"""

    def test_single_value_no_wildcard(self):
        """✅ Positive: 单值无通配 → 全部字面 token"""
        result = result_transform.parse_filter_expr("abc")
        self.assertEqual(result, [[("lit", "a"), ("lit", "b"), ("lit", "c")]])

    def test_wildcard_prefix(self):
        """✅ Positive: 前缀通配 *abc → [wild, lit a, lit b, lit c]"""
        result = result_transform.parse_filter_expr("*abc")
        self.assertEqual(result, [[("wild",), ("lit", "a"), ("lit", "b"), ("lit", "c")]])

    def test_wildcard_suffix(self):
        """✅ Positive: 后缀通配 abc*"""
        result = result_transform.parse_filter_expr("abc*")
        self.assertEqual(result, [[("lit", "a"), ("lit", "b"), ("lit", "c"), ("wild",)]])

    def test_wildcard_middle(self):
        """✅ Positive: 中间通配 张*明"""
        result = result_transform.parse_filter_expr("张*明")
        self.assertEqual(result, [[("lit", "张"), ("wild",), ("lit", "明")]])

    def test_wildcard_multiple(self):
        """✅ Positive: 多次通配 a*b*c"""
        result = result_transform.parse_filter_expr("a*b*c")
        self.assertEqual(
            result,
            [[("lit", "a"), ("wild",), ("lit", "b"), ("wild",), ("lit", "c")]],
        )

    def test_multivalue_basic(self):
        """✅ Positive: 逗号多值 → 两段"""
        result = result_transform.parse_filter_expr("abc,def")
        self.assertEqual(
            result,
            [
                [("lit", "a"), ("lit", "b"), ("lit", "c")],
                [("lit", "d"), ("lit", "e"), ("lit", "f")],
            ],
        )

    def test_multivalue_segment_strip(self):
        """✅ Positive: 多值段 strip 前后空格（abc, def）"""
        result = result_transform.parse_filter_expr("abc, def")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [("lit", "a"), ("lit", "b"), ("lit", "c")])
        self.assertEqual(result[1], [("lit", "d"), ("lit", "e"), ("lit", "f")])

    def test_multivalue_empty_segment_ignored(self):
        """✅ Positive: 空段忽略（abc,,def → 两段；abc, → 一段）"""
        result = result_transform.parse_filter_expr("abc,,def")
        self.assertEqual(len(result), 2)
        result2 = result_transform.parse_filter_expr("abc,")
        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0][0], ("lit", "a"))

    def test_multivalue_all_empty(self):
        """✅ Positive: 全空段（" , "）→ 空列表（条件忽略）"""
        result = result_transform.parse_filter_expr(" , ")
        self.assertEqual(result, [])

    def test_multivalue_mixed_wildcard(self):
        """✅ Positive: 多值混合通配（abc,*def*）"""
        result = result_transform.parse_filter_expr("abc,*def*")
        self.assertEqual(len(result), 2)
        self.assertIn(("wild",), result[1])
        self.assertNotIn(("wild",), result[0])

    def test_escaped_star_literal(self):
        """✅ Positive: \\* → 字面星号（无通配 token）"""
        result = result_transform.parse_filter_expr(r"a\*b")
        self.assertEqual(
            result,
            [[("lit", "a"), ("lit", "*"), ("lit", "b")]],
        )
        self.assertNotIn(("wild",), result[0])

    def test_escaped_comma_not_split(self):
        """✅ Positive: \\, → 字面逗号，不拆分为多值"""
        result = result_transform.parse_filter_expr(r"a\,b")
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0],
            [("lit", "a"), ("lit", ","), ("lit", "b")],
        )

    def test_escaped_backslash_literal(self):
        """✅ Positive: \\\\ → 字面反斜杠"""
        result = result_transform.parse_filter_expr(r"a\\b")
        self.assertEqual(
            result,
            [[("lit", "a"), ("lit", "\\"), ("lit", "b")]],
        )

    def test_escaped_comma_then_multi(self):
        """✅ Positive: 字面逗号与裸逗号共存（a\\,b,c → 两段）"""
        result = result_transform.parse_filter_expr(r"a\,b,c")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [("lit", "a"), ("lit", ","), ("lit", "b")])
        self.assertEqual(result[1], [("lit", "c")])

    def test_double_backslash_then_comma_splits(self):
        """回归（审查发现）：\\\\, → 字面反斜杠 + 裸逗号分隔（偶数反斜杠）"""
        result = result_transform.parse_filter_expr(r"a\\,b")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [("lit", "a"), ("lit", "\\")])
        self.assertEqual(result[1], [("lit", "b")])

    def test_triple_backslash_then_comma_escaped(self):
        """回归（审查发现）：\\\\\\, → 字面反斜杠 + 字面逗号（奇数反斜杠）"""
        result = result_transform.parse_filter_expr(r"a\\\,b")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [("lit", "a"), ("lit", "\\"), ("lit", ","), ("lit", "b")])

    def test_quad_backslash_then_comma_splits(self):
        """回归（审查发现）：\\\\\\\\, → 两个字面反斜杠 + 分隔（偶数）"""
        result = result_transform.parse_filter_expr(r"a\\\\,b")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [("lit", "a"), ("lit", "\\"), ("lit", "\\")])
        self.assertEqual(result[1], [("lit", "b")])

    def test_single_value_no_strip(self):
        """✅ Positive: 无逗号单值不 strip（" abc" 保留前导空格）"""
        result = result_transform.parse_filter_expr(" abc")
        self.assertEqual(result, [[("lit", " "), ("lit", "a"), ("lit", "b"), ("lit", "c")]])

    def test_non_str_input(self):
        """✅ Positive: 非 str 输入（数字）→ 强制字符串"""
        result = result_transform.parse_filter_expr(123)
        self.assertEqual(result, result_transform.parse_filter_expr("123"))

    def test_empty_string(self):
        """✅ Positive: 空串 → 单段空 token（contains 空串匹配所有行）"""
        result = result_transform.parse_filter_expr("")
        self.assertEqual(result, [[]])

    def test_trailing_backslash(self):
        """✅ Positive: 结尾孤立反斜杠 → 字面反斜杠"""
        result = result_transform.parse_filter_expr("a\\")
        self.assertEqual(result, [[("lit", "a"), ("lit", "\\")]])

    def test_backslash_other_char(self):
        """✅ Positive: \\ 后跟非特殊字符 → 反斜杠为字面、后续字符照常"""
        result = result_transform.parse_filter_expr(r"a\xb")
        self.assertEqual(
            result,
            [[("lit", "a"), ("lit", "\\"), ("lit", "x"), ("lit", "b")]],
        )


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
        for name in ("filter_rows", "sort_rows", "select_columns", "column_indices",
                     "parse_filter_expr"):
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
