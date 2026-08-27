# -*- coding: utf-8 -*-
"""预设测试用例一键导入的单元测试。

覆盖：按名称 upsert（新增 + 覆盖更新）、实体间引用解析、定时任务关联级联、
以及配置页按钮的 DEBUG 可见性门禁。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import sqlite3
import config_db
import preset_cases
import app_config

PRESET_PATH = os.path.join(ROOT, "tests", "preset_test_cases.json")


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    config_db.init_db(conn)
    return conn


class TestPresetImport(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_import_adds_all_groups(self):
        data = preset_cases.load_preset(PRESET_PATH)
        res = preset_cases.import_preset_test_cases(self.conn, data, PRESET_PATH)
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["groups"]["connection_pools"]["added"], 2)
        self.assertEqual(res["groups"]["report_categories"]["added"], 3)
        self.assertEqual(res["groups"]["report_configs"]["added"], 7)
        self.assertEqual(res["groups"]["api_endpoints"]["added"], 6)
        self.assertEqual(res["groups"]["api_keys"]["added"], 4)
        self.assertEqual(res["groups"]["report_schedules"]["added"], 2)
        self.assertGreater(res["added"], 0)
        self.assertEqual(res["updated"], 0)

    def test_upsert_overwrite_by_name(self):
        data = preset_cases.load_preset(PRESET_PATH)
        preset_cases.import_preset_test_cases(self.conn, data, PRESET_PATH)
        # 改一条报表的 memo 后重新导入 → 应走覆盖更新而非新增
        data2 = preset_cases.load_preset(PRESET_PATH)
        for r in data2["report_configs"]:
            if r["name"] == "订单概览":
                r["memo"] = "被覆盖后的备注"
        res = preset_cases.import_preset_test_cases(self.conn, data2, PRESET_PATH)
        self.assertEqual(res["groups"]["report_configs"]["added"], 0)
        self.assertEqual(res["groups"]["report_configs"]["updated"], 7)
        row = self.conn.execute(
            "SELECT memo FROM report_configs WHERE name=?", ("订单概览",)
        ).fetchone()
        self.assertEqual(row["memo"], "被覆盖后的备注")
        # 总数不变（无重复）
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM report_configs").fetchone()[0]
        self.assertEqual(cnt, 7)

    def test_reference_resolution(self):
        data = preset_cases.load_preset(PRESET_PATH)
        preset_cases.import_preset_test_cases(self.conn, data, PRESET_PATH)
        # 报表 → 连接池
        pid = self.conn.execute(
            "SELECT pool_id FROM report_configs WHERE name=?", ("订单概览",)
        ).fetchone()[0]
        pname = self.conn.execute(
            "SELECT name FROM connection_pools WHERE id=?", (pid,)
        ).fetchone()[0]
        self.assertEqual(pname, "主库-交易")
        # 报表 → 分类
        cid = self.conn.execute(
            "SELECT category_id FROM report_configs WHERE name=?",
            ("销售多维统计",)
        ).fetchone()[0]
        cname = self.conn.execute(
            "SELECT name FROM report_categories WHERE id=?", (cid,)
        ).fetchone()[0]
        self.assertEqual(cname, "区域销售")
        # 端点 → 报表
        rid = self.conn.execute(
            "SELECT report_id FROM api_endpoints WHERE url_path=?",
            ("/api/orders",)
        ).fetchone()[0]
        rname = self.conn.execute(
            "SELECT name FROM report_configs WHERE id=?", (rid,)
        ).fetchone()[0]
        self.assertEqual(rname, "订单概览")
        # Key → 端点
        eid = self.conn.execute(
            "SELECT id FROM api_endpoints WHERE url_path=?",
            ("/api/orders",)
        ).fetchone()[0]
        kid = self.conn.execute(
            "SELECT endpoint_id FROM api_keys WHERE name=?",
            ("内部服务Key",)
        ).fetchone()[0]
        self.assertEqual(kid, eid)

    def test_schedule_reports_cascade(self):
        data = preset_cases.load_preset(PRESET_PATH)
        preset_cases.import_preset_test_cases(self.conn, data, PRESET_PATH)
        sid = self.conn.execute(
            "SELECT id FROM report_schedules WHERE name=?", ("销售日报",)
        ).fetchone()[0]
        rows = self.conn.execute(
            "SELECT report_id FROM schedule_reports WHERE schedule_id=? "
            "ORDER BY order_index", (sid,)
        ).fetchall()
        self.assertEqual(len(rows), 2)
        names = []
        for r in rows:
            names.append(self.conn.execute(
                "SELECT name FROM report_configs WHERE id=?", (r["report_id"],)
            ).fetchone()[0])
        self.assertEqual(names, ["销售多维统计", "全量导出报表"])
        # exclusions 已序列化为 JSON 文本
        exc = self.conn.execute(
            "SELECT exclusions FROM report_schedules WHERE id=?", (sid,)
        ).fetchone()[0]
        self.assertIn("dow", exc)


class TestTestMysql(unittest.TestCase):
    """测试 MySQL 初始化：写权限校验 + 建表 + 灌数据（mock mysql.connector）。"""

    def _fake_connector(self, connect_side_effect=None):
        import unittest.mock as mock

        conn = mock.MagicMock()
        cur = mock.MagicMock()
        conn.cursor.return_value = cur
        mod = mock.MagicMock()
        mod.Error = Exception
        if connect_side_effect is not None:
            mod.connect = mock.MagicMock(side_effect=connect_side_effect)
        else:
            mod.connect = mock.MagicMock(return_value=conn)
        return mod, conn, cur

    def _cfg(self):
        return {
            "enable": True,
            "host": "db", "port": 3306, "user": "u", "password": "p",
            "database": "sqlreport_test",
            "tables": [
                {"name": "orders", "ddl": "CREATE TABLE orders ...",
                 "seed": ["INSERT INTO orders VALUES (1)", "INSERT INTO orders VALUES (2)"]},
                {"name": "sales", "ddl": "CREATE TABLE sales ...", "seed": []},
            ],
        }

    def test_setup_success_creates_and_seeds(self):
        fake, conn, cur = self._fake_connector()
        with unittest.mock.patch.object(preset_cases, "_mysql_connector", fake):
            res = preset_cases.setup_test_mysql_tables(self._cfg())
        self.assertTrue(res["ok"])
        self.assertTrue(res["write_ok"])
        self.assertEqual(len(res["tables"]), 2)
        self.assertEqual(res["tables"][0]["seed_rows"], 2)
        calls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any("__sr_perm_check" in c for c in calls))
        self.assertTrue(any("CREATE DATABASE" in c for c in calls))
        self.assertTrue(any("CREATE TABLE orders" in c for c in calls))
        self.assertTrue(any("INSERT INTO orders" in c for c in calls))
        self.assertTrue(any("CREATE TABLE sales" in c for c in calls))

    def test_setup_no_write_permission_reports_error(self):
        fake, conn, cur = self._fake_connector()
        def _side(sql, *a, **k):
            if "INSERT INTO `__sr_perm_check`" in sql:
                raise Exception("Access denied")
            return None
        cur.execute.side_effect = _side
        with unittest.mock.patch.object(preset_cases, "_mysql_connector", fake):
            res = preset_cases.setup_test_mysql_tables(self._cfg())
        self.assertFalse(res["ok"])
        self.assertFalse(res["write_ok"])
        self.assertTrue(any("写权限" in e or "Access denied" in e for e in res["errors"]))

    def test_setup_connection_failure_reports_error(self):
        fake, conn, cur = self._fake_connector(
            connect_side_effect=Exception("Can't connect"))
        with unittest.mock.patch.object(preset_cases, "_mysql_connector", fake):
            res = preset_cases.setup_test_mysql_tables(self._cfg())
        self.assertFalse(res["ok"])
        self.assertTrue(any("连接" in e for e in res["errors"]))

    def test_import_overrides_pools_with_test_mysql(self):
        conn = make_db()
        cfg = {"enable": True, "host": "9.9.9.9", "port": 3306,
               "user": "tu", "password": "tp", "database": "test_db", "tables": []}
        data = preset_cases.load_preset(PRESET_PATH)
        res = preset_cases.import_preset_test_cases(conn, data, PRESET_PATH,
                                                    test_mysql_cfg=cfg)
        # 导入的连接池应被覆盖为 test_mysql 的连接信息
        rows = conn.execute(
            "SELECT host, port, `database`, user FROM connection_pools").fetchall()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["host"], "9.9.9.9")
            self.assertEqual(r["database"], "test_db")
            self.assertEqual(r["user"], "tu")
        self.assertIsNotNone(res["test_mysql"])

    def test_import_without_test_mysql_skips_mysql(self):
        conn = make_db()
        data = preset_cases.load_preset(PRESET_PATH)
        res = preset_cases.import_preset_test_cases(conn, data, PRESET_PATH)
        self.assertIsNone(res["test_mysql"])
        # 连接池保持夹具原值
        r = conn.execute(
            "SELECT host, `database` FROM connection_pools LIMIT 1").fetchone()
        self.assertEqual(r["host"], "127.0.0.1")


class TestDebugVisibility(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def _overview(self, debug):
        import config
        with unittest.mock.patch.object(app_config, "is_debug_mode",
                                        return_value=debug):
            return config.render_overview(self.conn)

    def test_button_visible_in_debug(self):
        html = self._overview(True)
        self.assertIn("新增测试用例", html)
        self.assertIn("/config/test-cases/import", html)

    def test_button_hidden_without_debug(self):
        html = self._overview(False)
        self.assertNotIn("新增测试用例", html)
        self.assertNotIn("/config/test-cases/import", html)


if __name__ == "__main__":
    unittest.main()
