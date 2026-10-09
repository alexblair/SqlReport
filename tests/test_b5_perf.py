import unittest

from result_transform import filter_rows

COLS = ["a", "b"]
ROWS = [("alpha", "x"), ("beta", "y"), ("ALPHA", "z"), (None, "w"), ("", "v"),
        ("a|b", "p"), ("a.b", "q"), ("x", "r")]


class TestFilterEquivalence(unittest.TestCase):
    """B5-1：合并为 alternation 后语义必须与旧实现完全一致。"""

    def test_multi_value_contains_is_case_insensitive(self):
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "alpha,beta")])
        self.assertEqual([x[0] for x in r], ["alpha", "beta", "ALPHA"])

    def test_contains_hits_regex_metachars_literally(self):
        """`|` `.` 等必须是字面量，不得被当正则元字符。"""
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "a|b")])
        self.assertEqual([x[0] for x in r], ["a|b"])
        r2 = filter_rows(list(ROWS), COLS, [("a", "contains", "a.b")])
        self.assertEqual([x[0] for x in r2], ["a.b"])

    def test_notcontains_inverts(self):
        r = filter_rows(list(ROWS), COLS, [("a", "notcontains", "alpha")])
        got = [x[0] for x in r]
        self.assertNotIn("alpha", got)
        self.assertNotIn("ALPHA", got)

    def test_eq_is_case_sensitive(self):
        r = filter_rows(list(ROWS), COLS, [("a", "eq", "alpha")])
        self.assertEqual([x[0] for x in r], ["alpha"])

    def test_neq_inverts(self):
        r = filter_rows(list(ROWS), COLS, [("a", "neq", "alpha")])
        self.assertNotIn("alpha", [x[0] for x in r])
        self.assertIn("ALPHA", [x[0] for x in r])   # neq 大小写敏感

    def test_wildcard_still_works(self):
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "al*ha")])
        self.assertEqual(sorted(x[0] for x in r), ["ALPHA", "alpha"])

    def test_empty_segments_ignored(self):
        """全空值（如 " , "）→ 条件忽略，返回原列表。"""
        r = filter_rows(list(ROWS), COLS, [("a", "contains", " , ")])
        self.assertEqual(len(r), len(ROWS))

    def test_unknown_column_ignored(self):
        r = filter_rows(list(ROWS), COLS, [("nope", "contains", "x")])
        self.assertEqual(len(r), len(ROWS))

    def test_none_matches_empty_string_semantics(self):
        """None → ""（既有语义），故 contains "" 会命中 None 行。"""
        r = filter_rows(list(ROWS), COLS, [("a", "isempty", "")])
        self.assertIn(None, [x[0] for x in r])


# ---------------------------------------------------------------------------
# B5-2：配置页 scheduler 徽标改为计数查询（去掉 N+1）
# ---------------------------------------------------------------------------

import os as _os                                              # noqa: E402
import re as _re                                              # noqa: E402
from unittest.mock import patch as _patch                     # noqa: E402

from tests import init_test_db                                # noqa: E402
from tests.test_base import make_config_db                    # noqa: E402


def _load_sched_ddl() -> str:
    """复用 test_scheduler_db 的内联建表 DDL（项目惯例：有意重复，避免循环导入）。

    注意：make_config_db() 只建连接、不建表，必须显式 init_test_db + 本 DDL；
    裸 sqlite3 连接上 config_db.init_db() 会报 `near "=": syntax error`。
    """
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                         "test_scheduler_db.py")
    with open(path, encoding="utf-8") as f:
        return _re.search(
            r'SQL_CREATE_REPORT_SCHEDULES = """(.*?)"""', f.read(), _re.S).group(1)


_SCHED_DDL = _load_sched_ddl()


class TestCountSchedules(unittest.TestCase):
    """B5-2：count_schedules 与 len(get_all_schedules) 数量一致，且不做 N+1。"""

    def setUp(self):
        self.conn = make_config_db()
        init_test_db(self.conn)
        self.conn.executescript(_SCHED_DDL)
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES ('r1','SELECT 1')")
        self.conn.commit()
        self._rid = self.conn.execute(
            "SELECT id FROM report_configs LIMIT 1").fetchone()["id"]

    def tearDown(self):
        self.conn.close()

    def _add_schedule(self, name):
        # upsert_schedule 要求至少绑定一张报表（config_db.py:2285），
        # 空 report_ids 会抛 ValueError —— 不要传 report_ids=[]
        import config_db
        return config_db.upsert_schedule(
            self.conn, name=name, report_ids=[self._rid],
            schedule_type="interval", interval_minutes=60)

    def test_count_schedules_exists(self):
        import config_db
        self.assertTrue(hasattr(config_db, "count_schedules"))

    def test_count_matches_len_of_get_all(self):
        import config_db
        self.assertEqual(config_db.count_schedules(self.conn), 0)
        self._add_schedule("任务甲")
        self._add_schedule("任务乙")
        self.assertEqual(config_db.count_schedules(self.conn), 2)
        # 与全量取数一致（防止数错）
        self.assertEqual(config_db.count_schedules(self.conn),
                         len(config_db.get_all_schedules(self.conn)))

    def test_count_does_not_need_report_binding(self):
        """徽标只要数量：不得因任务无绑定报表而少计（即不得靠 JOIN 计数）。"""
        import config_db
        self._add_schedule("无绑定任务")
        self.assertEqual(config_db.count_schedules(self.conn), 1)
        # 直接落一行无绑定关系的任务行：COUNT(*) 仍应计入
        self.conn.execute("INSERT INTO report_schedules (name) VALUES ('裸任务')")
        self.conn.commit()
        self.assertEqual(config_db.count_schedules(self.conn), 2)

    def test_nav_badges_uses_count_schedules(self):
        """config.py 的 scheduler 徽标必须走 count_schedules（接线护栏）。"""
        import config
        import config_db
        with _patch.object(config_db, "count_schedules", return_value=7):
            badges = config._nav_badges(self.conn)
        self.assertEqual(badges["scheduler"], 7)


class TestReportsByCategoryGrouping(unittest.TestCase):
    """B5-3：get_reports_by_category 改为一次全量查询 + Python 分组，

    分组结果（每组内顺序 + 未分类集合）必须与逐分类调用 get_reports 逐条一致。
    """

    def setUp(self):
        import config_db
        self.config_db = config_db
        self.conn = make_config_db()
        init_test_db(self.conn)
        self.cats = [config_db.add_category(self.conn, f"分类{i}")
                     for i in range(3)]
        # 故意让 sort_order 跨分类交错、同分类内乱序（含并列，靠 id 兜底）：
        # 这样「按 sort_order, id 全表扫后分组」与「逐分类 ORDER BY 后查询」
        # 只要有一处顺序不同就会暴露。
        spec = [
            ("报表A1", 0, 30), ("报表B1", 1, 10), ("报表C1", 2, 50),
            ("报表A2", 0, 10), ("报表B2", 1, 40), ("报表C2", 2, 20),
            ("报表A3", 0, 10), ("未分类X", None, 5), ("未分类Y", None, 60),
        ]
        for name, ci, order in spec:
            rid = config_db.add_report(
                self.conn, name, "SELECT 1", 20, None,
                category_id=(self.cats[ci] if ci is not None else None),
                session_user=None)
            self.conn.execute(
                "UPDATE report_configs SET sort_order=? WHERE id=?", (order, rid))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_grouping_matches_per_category_queries(self):
        """每组名称/ id 序列逐条 == 旧式 get_reports(conn, category_id=cid)。"""
        cats, unassigned = self.config_db.get_reports_by_category(self.conn)
        self.assertEqual([c["id"] for c in cats], self.cats)
        for cat in cats:
            legacy = self.config_db.get_reports(self.conn, category_id=cat["id"])
            self.assertEqual([r["id"] for r in cat["reports"]],
                             [r["id"] for r in legacy])
            self.assertEqual([r["name"] for r in cat["reports"]],
                             [r["name"] for r in legacy])
        # 每个分类都必须非空：防止误用 get_reports(conn) 静默清空全部分类。
        self.assertTrue(all(c["reports"] for c in cats))
        expected_un = self.config_db.get_reports(self.conn, category_id=None)
        self.assertEqual([r["id"] for r in unassigned],
                         [r["id"] for r in expected_un])
        self.assertEqual([r["name"] for r in unassigned],
                         [r["name"] for r in expected_un])

    def test_explicit_expected_order(self):
        """显式锁死顺序：组内 sort_order 升序、并列按 id 升序。"""
        cats, unassigned = self.config_db.get_reports_by_category(self.conn)
        got = {c["id"]: [r["name"] for r in c["reports"]] for c in cats}
        self.assertEqual(got[self.cats[0]], ["报表A2", "报表A3", "报表A1"])
        self.assertEqual(got[self.cats[1]], ["报表B1", "报表B2"])
        self.assertEqual(got[self.cats[2]], ["报表C2", "报表C1"])
        self.assertEqual([r["name"] for r in unassigned],
                         ["未分类X", "未分类Y"])

    def test_query_count_is_constant(self):
        """查询次数常量（分类 + 报表各一次），不随分类数增长（旧为 2+C）。"""
        def count_selects():
            seen = []
            self.conn.set_trace_callback(seen.append)
            try:
                self.config_db.get_reports_by_category(self.conn)
            finally:
                self.conn.set_trace_callback(None)
            return [s for s in seen if s.lstrip().upper().startswith("SELECT")]

        selects = count_selects()
        # 旧实现 = 2 + C = 2 + 3 = 5 次；新实现必须恒为 2 次。
        self.assertEqual(len(selects), 2)
        self.assertEqual(sum("report_configs" in s for s in selects), 1)
        self.assertEqual(sum("report_categories" in s for s in selects), 1)
        # 再加一个分类，查询次数不得增加。
        self.config_db.add_category(self.conn, "分类3")
        self.assertEqual(len(count_selects()), 2)

    def test_does_not_fall_back_to_get_reports(self):
        """接线护栏：不得再逐分类调用 get_reports（否则直接被 mock 拦下）。"""
        with _patch.object(self.config_db, "get_reports",
                           side_effect=AssertionError("不得逐分类调用 get_reports")):
            cats, unassigned = self.config_db.get_reports_by_category(self.conn)
        self.assertEqual(len(cats), 3)
        self.assertEqual([len(c["reports"]) for c in cats], [3, 2, 2])
        self.assertEqual(len(unassigned), 2)

    def test_null_semantics_matches_legacy_blank_and_dangling(self):
        """NULL 语义核对：`''` 与悬空 category_id 既不进未分类、也不进任何分类。

        与旧实现一致（旧：`IS NULL` + 逐分类等值查询，两者都不会命中）。
        """
        con = self.conn
        con.execute("PRAGMA foreign_keys=OFF")   # 模拟存量脏值，绕过外键写入
        try:
            for val in ("", 99999):
                con.execute(
                    "INSERT INTO report_configs (name, sql_query, category_id,"
                    " sort_order) VALUES (?, 'SELECT 1', ?, 7)", (f"异常{val!r}", val))
        finally:
            con.execute("PRAGMA foreign_keys=ON")
        con.commit()
        cats, unassigned = self.config_db.get_reports_by_category(con)
        shown = {r["id"] for c in cats for r in c["reports"]}
        shown |= {r["id"] for r in unassigned}
        abnormal = {r["id"] for r in self.config_db.get_all_reports(con)
                    if r["category_id"] is not None
                    and r["category_id"] not in self.cats}
        self.assertEqual(len(abnormal), 2)
        self.assertFalse(abnormal & shown)
        # 未分类集合严格等于 WHERE category_id IS NULL
        self.assertEqual(sorted(r["id"] for r in unassigned),
                         sorted(r["id"] for r in
                                self.config_db.get_reports(con, category_id=None)))
