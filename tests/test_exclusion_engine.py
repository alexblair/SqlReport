"""排除规则树求值引擎测试（T2 / 规格 E1–E27）。

独立单测：纯函数 evaluate_exclusions / validate_exclusions，不依赖 DB 或网络。
日期标定：2026-08-22=周六，08-23=周日，08-24=周一，08-28=周五。
"""

import unittest
from datetime import datetime

import scheduler


def dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi)


DOW_WEEKEND = {"type": "dow", "in": ["sat", "sun"]}
TOD_DAY = {"type": "tod", "from": "08:00", "to": "21:00"}
TOD_NIGHT = {"type": "tod", "from": "21:00", "to": "09:00"}

# 用户示例任务一排除树（规格 §6；工作日上午排除用 00:00–07:59 = 8 点前）
TASK1 = {
    "op": "OR",
    "children": [
        DOW_WEEKEND,
        {"op": "AND", "children": [
            {"type": "dow", "in": ["mon", "tue", "wed", "thu", "fri"]},
            {"op": "OR", "children": [
                {"type": "tod", "from": "21:00", "to": "23:59"},
                {"type": "tod", "from": "00:00", "to": "07:59"},
            ]},
        ]},
    ],
}


class TestExclusionEval(unittest.TestCase):

    # ---- E1：空树 ----
    def test_e1_none(self):
        self.assertFalse(scheduler.evaluate_exclusions(None, dt(2026, 8, 24, 14)))
        self.assertFalse(scheduler.evaluate_exclusions("", dt(2026, 8, 24, 14)))
        self.assertFalse(scheduler.evaluate_exclusions({}, dt(2026, 8, 24, 14)))

    # ---- E2/E3：dow 周末 ----
    def test_e2_saturday_hit(self):
        self.assertTrue(scheduler.evaluate_exclusions(DOW_WEEKEND, dt(2026, 8, 22, 14)))
    def test_e3_monday_miss(self):
        self.assertFalse(scheduler.evaluate_exclusions(DOW_WEEKEND, dt(2026, 8, 24, 14)))

    # ---- E4/E5：tod 不跨午夜 08:00–21:00 ----
    def test_e4_day_inner(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_DAY, dt(2026, 8, 24, 14)))
    def test_e5_day_outer(self):
        self.assertFalse(scheduler.evaluate_exclusions(TOD_DAY, dt(2026, 8, 24, 22)))

    # ---- E6/E7/E8：tod 跨午夜 21:00–09:00 ----
    def test_e6_night_late(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_NIGHT, dt(2026, 8, 24, 22)))
    def test_e7_night_early(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_NIGHT, dt(2026, 8, 24, 8)))
    def test_e8_night_noon(self):
        self.assertFalse(scheduler.evaluate_exclusions(TOD_NIGHT, dt(2026, 8, 24, 12)))

    # ---- E9/E10/E11：边界含上下界 ----
    def test_e9_bound_low(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_DAY, dt(2026, 8, 24, 8, 0)))
    def test_e10_bound_high(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_DAY, dt(2026, 8, 24, 21, 0)))
    def test_e11_night_upper(self):
        self.assertTrue(scheduler.evaluate_exclusions(TOD_NIGHT, dt(2026, 8, 24, 9, 0)))

    # ---- E12–E15：OR 根（dow 周末 ∪ tod 跨午夜）----
    def test_e12_or_saturday(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"op": "OR", "children": [DOW_WEEKEND, TOD_NIGHT]},
            dt(2026, 8, 22, 14)))
    def test_e13_or_monday_noon(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"op": "OR", "children": [DOW_WEEKEND, TOD_NIGHT]},
            dt(2026, 8, 24, 14)))
    def test_e14_or_monday_late(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"op": "OR", "children": [DOW_WEEKEND, TOD_NIGHT]},
            dt(2026, 8, 24, 22)))
    def test_e15_or_monday_early(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"op": "OR", "children": [DOW_WEEKEND, TOD_NIGHT]},
            dt(2026, 8, 24, 8, 30)))

    # ---- E16/E17：AND 根（工作日 AND 白天）----
    def test_e16_and_weekday_day(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"op": "AND", "children": [
                {"type": "dow", "in": ["mon", "tue", "wed", "thu", "fri"]}, TOD_DAY]},
            dt(2026, 8, 24, 14)))
    def test_e17_and_saturday(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"op": "AND", "children": [
                {"type": "dow", "in": ["mon", "tue", "wed", "thu", "fri"]}, TOD_DAY]},
            dt(2026, 8, 22, 14)))

    # ---- E18–E20：用户示例任务一 ----
    def test_e18_task1_mon_0830(self):
        self.assertFalse(scheduler.evaluate_exclusions(TASK1, dt(2026, 8, 24, 8, 30)))
    def test_e19_task1_mon_2200(self):
        self.assertTrue(scheduler.evaluate_exclusions(TASK1, dt(2026, 8, 24, 22)))
    def test_e20_task1_sat_1000(self):
        self.assertTrue(scheduler.evaluate_exclusions(TASK1, dt(2026, 8, 22, 10)))

    # ---- E21/E22：date 精确 ----
    def test_e21_date_hit(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"type": "date", "on": ["2026-08-23"]}, dt(2026, 8, 23, 12)))
    def test_e22_date_miss(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"type": "date", "on": ["2026-08-23"]}, dt(2026, 8, 24, 12)))

    # ---- E23/E24：date_range 闭区间 ----
    def test_e23_range_hit(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            {"type": "date_range", "from": "2026-08-01", "to": "2026-08-31"},
            dt(2026, 8, 15)))
    def test_e24_range_miss(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"type": "date_range", "from": "2026-08-01", "to": "2026-08-31"},
            dt(2026, 9, 1)))

    # ---- E25：空 children ----
    def test_e25_empty_children(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"op": "AND", "children": []}, dt(2026, 8, 24, 14)))

    # ---- E26：损坏 JSON / 未知类型 ----
    def test_e26_bad_json(self):
        self.assertFalse(scheduler.evaluate_exclusions("}{not json", dt(2026, 8, 24, 14)))
    def test_e26_unknown_type(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"type": "bogus"}, dt(2026, 8, 24, 14)))
    def test_e26_unknown_type_warns(self):
        """E26 完整语义：未知叶子类型除返回 False 外必须打 warning（2026-08-23
        审查补齐——静默吞配置笔误会让用户以为规则生效）。"""
        with self.assertLogs(level="WARNING") as captured:
            self.assertFalse(scheduler.evaluate_exclusions(
                {"type": "bogus"}, dt(2026, 8, 24, 14)))
        self.assertTrue(any("未知叶子类型" in line for line in captured.output))
    def test_e26_non_object(self):
        self.assertFalse(scheduler.evaluate_exclusions([1, 2, 3], dt(2026, 8, 24, 14)))
    def test_e26_missing_leaf_fields(self):
        """E26 缺字段变体：type 合法但 from/to/in/on 缺失 → False + warning
        （fail-open，不得误判命中而吞掉执行）。"""
        for bad in ({"type": "tod"}, {"type": "tod", "from": "08:00"},
                    {"type": "dow"}, {"type": "date"},
                    {"type": "date_range", "from": "2026-08-01"}):
            with self.assertLogs(level="WARNING"):
                self.assertFalse(scheduler.evaluate_exclusions(
                    bad, dt(2026, 8, 24, 14)))

    # ---- E27：dow 非法值不静默 ----
    def test_e27_bad_dow_value(self):
        self.assertFalse(scheduler.evaluate_exclusions(
            {"type": "dow", "in": ["Mon"]}, dt(2026, 8, 24, 14)))

    # ---- JSON 字符串入参 ----
    def test_json_string_input(self):
        self.assertTrue(scheduler.evaluate_exclusions(
            '{"type":"dow","in":["sat","sun"]}', dt(2026, 8, 22, 14)))

    # ---- validate_exclusions ----
    def test_validate_ok_empty(self):
        ok, err = scheduler.validate_exclusions(None)
        self.assertTrue(ok)
    def test_validate_ok_tree(self):
        ok, err = scheduler.validate_exclusions(TASK1)
        self.assertTrue(ok)
        self.assertIsNone(err)
    def test_validate_bad_json(self):
        ok, err = scheduler.validate_exclusions("}{")
        self.assertFalse(ok)
    def test_validate_bad_dow(self):
        ok, err = scheduler.validate_exclusions({"type": "dow", "in": ["Mon"]})
        self.assertFalse(ok)
    def test_validate_bad_tod(self):
        ok, err = scheduler.validate_exclusions({"type": "tod", "from": "8am"})
        self.assertFalse(ok)
    def test_validate_bad_node_type(self):
        ok, err = scheduler.validate_exclusions({"type": "nope"})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
