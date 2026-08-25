"""
test_real_crud.py — 配置库真层 CRUD 集成测试（DEBUG 模式激活时运行）

覆盖 connection_pools / users / report_categories / report_configs /
api_endpoints / sessions 在真实 SQLite 文件库与真实 MySQL 测试库上的完整
生命周期（增删改查 + 排序移动 + 级联删除 + Unicode）。

两引擎共享同一套断言（_RealCrudMixin），消灭 test_base 硬编码 DDL 复制。
未激活 DEBUG 模式时整层 skip。
"""

import unittest

import config_db

from tests.integration.base import RealDbBase

_TABLES = (
    "api_keys",
    "api_endpoints",
    "report_configs",
    "report_categories",
    "connection_pools",
    "sessions",
    "users",
)


class _RealCrudMixin:
    """引擎无关的 CRUD 断言集（非 TestCase，防止基类被 unittest 收集）。"""

    engine = None

    # ------------------------------------------------------------------
    # 隔离
    # ------------------------------------------------------------------

    def setUp(self):
        for table in _TABLES:
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()

    # ------------------------------------------------------------------
    # 连接池
    # ------------------------------------------------------------------

    def test_pool_lifecycle(self):
        pid = config_db.add_pool(self.conn, "真层池", "127.0.0.1", 3306,
                                 "u", "p", "db_test", session_user=None)
        self.assertGreater(pid, 0)

        got = config_db.get_pool(self.conn, pid)
        self.assertEqual(got["name"], "真层池")
        self.assertEqual(got["host"], "127.0.0.1")
        self.assertEqual(got["port"], 3306)
        self.assertEqual(got["database"], "db_test")

        self.assertTrue(config_db.update_pool(
            self.conn, pid, "真层池改", "10.0.0.1", 3307,
            "u2", "p2", "db_test2", session_user=None))
        got2 = config_db.get_pool(self.conn, pid)
        self.assertEqual(got2["name"], "真层池改")
        self.assertEqual(got2["host"], "10.0.0.1")
        self.assertEqual(got2["port"], 3307)

        self.assert_row_count("connection_pools", 1)
        self.assertTrue(config_db.delete_pool(self.conn, pid, session_user=None))
        self.assert_row_count("connection_pools", 0)

    def test_pool_sort_move(self):
        a = config_db.add_pool(self.conn, "a", "h", 1, "u", "p", "db", session_user=None)
        b = config_db.add_pool(self.conn, "b", "h", 1, "u", "p", "db", session_user=None)
        c = config_db.add_pool(self.conn, "c", "h", 1, "u", "p", "db", session_user=None)
        self.assertTrue(config_db.move_pool(self.conn, a, "down", session_user=None))
        names = [p["name"] for p in config_db.get_all_pools(self.conn)]
        self.assertEqual(names, ["b", "a", "c"])
        self.assertTrue(config_db.move_pool(self.conn, a, "up", session_user=None))
        names = [p["name"] for p in config_db.get_all_pools(self.conn)]
        self.assertEqual(names, ["a", "b", "c"])
        self.assertFalse(config_db.move_pool(self.conn, a, "up", session_user=None))
        self.assertFalse(config_db.move_pool(self.conn, 99999, "up", session_user=None))
        self.assertEqual(len(config_db.get_all_pools(self.conn)), 3)

    def test_pool_name_unique(self):
        config_db.add_pool(self.conn, "dup", "h", 1, "u", "p", "db", session_user=None)
        with self.assertRaises(Exception):
            config_db.add_pool(self.conn, "dup", "h", 1, "u", "p", "db", session_user=None)

    # ------------------------------------------------------------------
    # 用户
    # ------------------------------------------------------------------

    def test_user_lifecycle(self):
        uid = config_db.add_user(self.conn, "alice", "hash1", session_user=None)
        self.assertGreater(uid, 0)
        u = config_db.get_user(self.conn, "alice")
        self.assertEqual(u["password_hash"], "hash1")
        self.assertEqual(config_db.get_user_by_id(self.conn, uid)["username"], "alice")
        self.assertTrue(config_db.update_user(
            self.conn, uid, "alice", "hash2", session_user=None))
        self.assertEqual(config_db.get_user(self.conn, "alice")["password_hash"], "hash2")
        self.assertEqual(len(config_db.get_all_users(self.conn)), 1)
        self.assertTrue(config_db.delete_user(self.conn, uid, session_user=None))
        self.assert_row_count("users", 0)

    def test_user_username_unique(self):
        config_db.add_user(self.conn, "bob", "h", session_user=None)
        with self.assertRaises(Exception):
            config_db.add_user(self.conn, "bob", "h2", session_user=None)

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------

    def test_category_lifecycle_with_parent(self):
        parent = config_db.add_category(self.conn, "父分类", session_user=None)
        child = config_db.add_category(self.conn, "子分类", parent_id=parent, session_user=None)
        got = config_db.get_category(self.conn, child)
        self.assertEqual(got["parent_id"], parent)
        self.assertEqual(len(config_db.get_all_categories(self.conn)), 2)

        self.assertTrue(config_db.update_category(
            self.conn, child, "子分类改", session_user=None))
        self.assertEqual(config_db.get_category(self.conn, child)["name"], "子分类改")

        self.assertTrue(config_db.delete_category(self.conn, child, session_user=None))
        self.assertTrue(config_db.delete_category(self.conn, parent, session_user=None))
        self.assert_row_count("report_categories", 0)

    def test_category_move(self):
        a = config_db.add_category(self.conn, "cat-a", session_user=None)
        b = config_db.add_category(self.conn, "cat-b", session_user=None)
        c = config_db.add_category(self.conn, "cat-c", session_user=None)
        self.assertTrue(config_db.move_category(self.conn, a, "down", session_user=None))
        names = [x["name"] for x in config_db.get_all_categories(self.conn)]
        self.assertEqual(names, ["cat-b", "cat-a", "cat-c"])
        self.assertEqual(len(config_db.get_category_tree(self.conn)), 3)

    # ------------------------------------------------------------------
    # 报表
    # ------------------------------------------------------------------

    def test_report_lifecycle(self):
        pid = config_db.add_pool(self.conn, "rp", "h", 3306, "u", "p", "db", session_user=None)
        cat = config_db.add_category(self.conn, "cat", session_user=None)
        rid = config_db.add_report(
            self.conn, "真层报表", "SELECT 1 AS x", 20, pid,
            category_id=cat, memo="备注", prefer_cache=0,
            cache_ttl_hours=5, session_user=None)
        self.assertGreater(rid, 0)

        r = config_db.get_report(self.conn, rid)
        self.assertEqual(r["name"], "真层报表")
        self.assertEqual(r["pool_id"], pid)
        self.assertEqual(r["category_id"], cat)
        self.assertEqual(r["memo"], "备注")
        self.assertEqual(r["prefer_cache"], 0)
        self.assertEqual(r["cache_ttl_hours"], 5)

        self.assertTrue(config_db.update_report(
            self.conn, rid, "真层报表改", "SELECT 2 AS y", 50, pid,
            category_id=cat, memo="备注2", result_names="col1",
            prefer_cache=1, cache_ttl_hours=9, session_user=None))
        r2 = config_db.get_report(self.conn, rid)
        self.assertEqual(r2["name"], "真层报表改")
        self.assertEqual(r2["default_page_size"], 50)
        self.assertEqual(r2["result_names"], "col1")
        self.assertEqual(r2["prefer_cache"], 1)

        self.assertTrue(config_db.delete_report(self.conn, rid, session_user=None))
        self.assert_row_count("report_configs", 0)

    def test_report_category_association(self):
        pid = config_db.add_pool(self.conn, "rp2", "h", 3306, "u", "p", "db", session_user=None)
        cat = config_db.add_category(self.conn, "grp", session_user=None)
        rid = config_db.add_report(self.conn, "assoc", "SELECT 1", 20, pid,
                                   category_id=cat, session_user=None)
        categories, unassigned = config_db.get_reports_by_category(self.conn)
        assigned_ids = [r["id"] for cat in categories for r in cat["reports"]]
        self.assertIn(rid, assigned_ids)
        self.assertEqual(len(config_db.get_reports(self.conn, category_id=cat)), 1)
        self.assert_row_count("report_configs", 1)
        self.assertEqual(config_db.count_reports_by_pool(self.conn)[pid], 1)

    # ------------------------------------------------------------------
    # API 端点
    # ------------------------------------------------------------------

    def test_api_endpoint_lifecycle_and_cascade(self):
        pid = config_db.add_pool(self.conn, "ap", "h", 3306, "u", "p", "db", session_user=None)
        rid = config_db.add_report(self.conn, "ap-report", "SELECT 1", 20, pid, session_user=None)
        eid = config_db.add_api_endpoint(
            self.conn, rid, "endpoint", "/api/report_test",
            output_format="json", enabled=1, session_user=None)
        self.assertGreater(eid, 0)
        e = config_db.get_api_endpoint(self.conn, eid)
        self.assertEqual(e["report_id"], rid)
        self.assertEqual(e["url_path"], "/api/report_test")
        self.assertEqual(len(config_db.get_all_api_endpoints(self.conn)), 1)

        self.assertTrue(config_db.update_api_endpoint(
            self.conn, eid, name="endpoint2", url_path="/api/report_test2",
            output_format="json", session_user=None))
        self.assertEqual(config_db.get_api_endpoint_by_path(
            self.conn, "/api/report_test2")["name"], "endpoint2")

        # 删除报表 → API 端点级联删除
        config_db.delete_report(self.conn, rid, session_user=None)
        self.assert_row_count("api_endpoints", 0)

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------

    def test_session_roundtrip(self):
        config_db.add_session(self.conn, "tok123", "alice")
        self.assertEqual(config_db.get_session(self.conn, "tok123"), "alice")
        config_db.add_session(self.conn, "tok123", "bob")  # REPLACE 覆盖
        self.assertEqual(config_db.get_session(self.conn, "tok123"), "bob")
        self.assertTrue(config_db.remove_session(self.conn, "tok123"))
        self.assertIsNone(config_db.get_session(self.conn, "tok123"))

    # ------------------------------------------------------------------
    # Unicode
    # ------------------------------------------------------------------

    def test_unicode_names(self):
        pid = config_db.add_pool(self.conn, "连接池-中文", "192.168.0.1", 3306,
                                 "用户", "密", "数据库", session_user=None)
        cat = config_db.add_category(self.conn, "分类-中文", session_user=None)
        rid = config_db.add_report(self.conn, "报表-中文", "SELECT '中文' AS v", 10,
                                   pid, category_id=cat, memo="中文备注",
                                   session_user=None)
        self.assertEqual(config_db.get_pool(self.conn, pid)["name"], "连接池-中文")
        self.assertEqual(config_db.get_category(self.conn, cat)["name"], "分类-中文")
        self.assertEqual(config_db.get_report(self.conn, rid)["name"], "报表-中文")
        self.assertEqual(config_db.get_report(self.conn, rid)["memo"], "中文备注")


class RealCrudSqliteTest(_RealCrudMixin, RealDbBase):
    """真实 SQLite 文件库 CRUD 真层测试。"""

    engine = "sqlite3"


class RealCrudMysqlTest(_RealCrudMixin, RealDbBase):
    """真实 MySQL 测试库 CRUD 真层测试（需 DEBUG 配置启用 mysql 引擎）。"""

    engine = "mysql"


if __name__ == "__main__":
    unittest.main()
