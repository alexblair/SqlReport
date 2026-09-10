"""嵌套筛选（NestedFilter）单元测试 — T-001。

覆盖：表达式解析（FR-002）、递归 and/or 求值（FR-001）、不污染缓存（FR-006）、
中文列名/值（FR-011）、结构化校验与修正建议（FR-012）。
"""
import datetime

import result_transform as rt


ROWS = [
    ("alice", 1, 25, "bj"),
    ("bob", 0, 30, "sh"),
    ("charlie", 1, 35, "bj"),
]
COLS = ["name", "active", "age", "city"]


class TestResolveExpression:
    def test_today_case_insensitive(self):
        # FR-002：表达式不区分大小写，TODAY() 与 today() 等价
        assert rt.resolve_expression("TODAY()") == rt.resolve_expression("today()")
        assert rt.resolve_expression("Today()") == rt.resolve_expression("today()")

    def test_now_equals_today(self):
        assert rt.resolve_expression("now()") == rt.resolve_expression("today()")

    def test_yesterday_tomorrow(self):
        today = datetime.date.today()
        assert rt.resolve_expression("yesterday()") == (today - datetime.timedelta(days=1)).isoformat()
        assert rt.resolve_expression("tomorrow()") == (today + datetime.timedelta(days=1)).isoformat()

    def test_date_add(self):
        # FR-002：date_add(now(), 7, day) 解析为 7 天后
        expect = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        assert rt.resolve_expression("date_add(now(), 7, day)") == expect
        assert rt.resolve_expression("DATE_ADD(NOW(), 7, DAY)") == expect  # 大小写等价

    def test_date_add_month(self):
        # 2026-01-31 + 1 month → 月末裁剪为 2026-02-28
        assert rt.resolve_expression("date_add('2026-01-31', 1, month)") == "2026-02-28"

    def test_date_sub(self):
        expect = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        assert rt.resolve_expression("date_sub(now(), 3, day)") == expect

    def test_date_literal(self):
        assert rt.resolve_expression("date('2026-02-01')") == "2026-02-01"

    def test_unknown_expression_passthrough(self):
        # 无法识别的表达式原样返回（交由匹配/校验处理）
        assert rt.resolve_expression("hello world") == "hello world"


class TestFilterRowsNested:
    def test_deep_nesting(self):
        # FR-001：三层嵌套 AND/(OR/AND) 条件树
        nf = {
            "op": "and",
            "conditions": [
                {"col": "active", "op": "eq", "value": "1"},
                {"op": "or", "conditions": [
                    {"col": "name", "op": "contains", "value": "a"},
                    {"op": "and", "conditions": [
                        {"col": "age", "op": "gt", "value": "30"},
                        {"col": "city", "op": "eq", "value": "bj"},
                    ]},
                ]},
            ],
        }
        out = rt.filter_rows_nested(ROWS, COLS, nf)
        assert sorted(r[0] for r in out) == ["alice", "charlie"]

    def test_nested_and_or(self):
        # FR-001：((active=1 AND name contains 'a') OR age>28)
        nf = {
            "op": "or",
            "conditions": [
                {"op": "and", "conditions": [
                    {"col": "active", "op": "eq", "value": "1"},
                    {"col": "name", "op": "contains", "value": "a"},
                ]},
                {"col": "age", "op": "gt", "value": "28"},
            ],
        }
        out = rt.filter_rows_nested(ROWS, COLS, nf)
        assert sorted(r[0] for r in out) == ["alice", "bob", "charlie"]

    def test_not_modifies_original(self):
        # FR-006：不污染缓存——入参 rows 未被改动
        snapshot = [tuple(r) for r in ROWS]
        rt.filter_rows_nested(ROWS, COLS, {"op": "and", "conditions": [
            {"col": "name", "op": "contains", "value": "a"}]})
        assert ROWS == snapshot

    def test_chinese_columns(self):
        # FR-011：中文列名与值
        rows = [("李雷",), ("韩梅",)]
        cols = ["姓名"]
        nf = {"op": "and", "conditions": [{"col": "姓名", "op": "contains", "value": "李"}]}
        out = rt.filter_rows_nested(rows, cols, nf)
        assert [r[0] for r in out] == ["李雷"]

    def test_expression_val(self):
        # FR-002：value 中的日期表达式参与比较
        rows = [("2026-01-01",), ("2026-03-01",)]
        cols = ["日期"]
        nf = {"op": "and", "conditions": [
            {"col": "日期", "op": "gt", "value": "date('2026-02-01')"}]}
        out = rt.filter_rows_nested(rows, cols, nf)
        assert [r[0] for r in out] == ["2026-03-01"]

    def test_empty_filter_noop(self):
        # 空 dict / None 视为 no-op，返回全部行
        assert rt.filter_rows_nested(ROWS, COLS, {}) == ROWS
        assert rt.filter_rows_nested(ROWS, COLS, None) == ROWS

    def test_unknown_column_skipped(self):
        # 未知列条件静默跳过（与 filter_rows 行为一致）
        nf = {"op": "and", "conditions": [{"col": "不存在", "op": "eq", "value": "x"}]}
        assert rt.filter_rows_nested(ROWS, COLS, nf) == ROWS


class TestValidateNestedFilter:
    def test_invalid_column(self):
        # FR-012：非法列名返回错误 + 可用列名建议
        v = rt.validate_nested_filter(
            {"col": "不存在列", "op": "eq", "value": "x"},
            available_columns=["name", "age"])
        assert v["valid"] is False
        assert any(e["path"].endswith(".col") and "不存在" in e["message"] for e in v["errors"])
        assert any("name" in e["suggestion"] for e in v["errors"])

    def test_invalid_op(self):
        # FR-012：非法操作符返回错误 + 支持操作符列表
        v = rt.validate_nested_filter({"col": "age", "op": "外星操作符", "value": "1"})
        assert v["valid"] is False
        assert any(e["path"].endswith(".op") for e in v["errors"])

    def test_missing_col(self):
        # FR-012：缺少 col 必填字段
        v = rt.validate_nested_filter({"op": "eq", "value": "x"})
        assert v["valid"] is False
        assert any("col" in e["message"] for e in v["errors"])

    def test_group_invalid_op(self):
        # 分组 op 非法（非 and/or）按叶节点处理 → op 错误
        v = rt.validate_nested_filter({"op": "zzz", "conditions": []})
        assert v["valid"] is False
        assert any(e["path"].endswith(".op") for e in v["errors"])

    def test_numeric_op_non_numeric(self):
        # FR-012：数值操作符值为非数字（非表达式）报错
        v = rt.validate_nested_filter({"col": "age", "op": "gt", "value": "非数字"})
        assert v["valid"] is False
        assert any(e["path"].endswith(".value") for e in v["errors"])

    def test_valid_nested(self):
        nf = {"op": "and", "conditions": [
            {"col": "name", "op": "contains", "value": "a"},
            {"op": "or", "conditions": [{"col": "age", "op": "gt", "value": "30"}]}]}
        v = rt.validate_nested_filter(nf, available_columns=["name", "age"])
        assert v["valid"] is True
        assert v["errors"] == []
