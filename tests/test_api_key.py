"""
test_api_key.py — API Key 多 key 化测试（PH-02）

覆盖：
- api_keys CRUD（add/get/list/delete/set_enabled + 审计 + 级联删除）
- 迁移 14：存量库数据迁入 api_keys、旧列置空、重复执行幂等
- _validate_api_key 旧列兼容回退与公开端点判定（单元级）

鉴权端到端（多 key/禁用/删除/防旧列绕过）在 test_api_extra.py 的
TestApiKeyAuth（继承 TestApiExtra 复用 MySQL mock 基建）中覆盖。
"""

import sqlite3
import unittest
from unittest.mock import patch

import api_handler
import config_db
import db
from tests.test_base import (
    BaseReportTest,
    init_test_db,
    make_config_db,
)


class TestApiKeyCRUD(BaseReportTest):
    """api_keys 表 CRUD 与审计测试。"""

    def _add_endpoint(self):
        return db.add_api_endpoint(
            self.conn, self.report_id, "测试端点", "/api/key-ep")

    def test_add_get_list(self):
        """新增后可按 id 查询、按端点列出（按创建顺序）。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa")
        k2 = config_db.add_api_key(self.conn, eid, "备用 Key", "sk-bbb")
        got = config_db.get_api_key(self.conn, k1)
        self.assertEqual(got["endpoint_id"], eid)
        self.assertEqual(got["name"], "主 Key")
        self.assertEqual(got["api_key"], "sk-aaa")
        self.assertEqual(got["enabled"], 1)
        keys = config_db.list_api_keys(self.conn, eid)
        self.assertEqual([r["id"] for r in keys], [k1, k2])
        self.assertEqual(
            config_db.list_api_keys(self.conn, 999), [],
            "无 key 的端点返回空列表")

    def test_get_missing_returns_none(self):
        """查询不存在的 id 返回 None。"""
        eid = self._add_endpoint()
        config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa")
        self.assertIsNone(config_db.get_api_key(self.conn, 999))

    def test_delete(self):
        """删除后查询返回 None，且仅在真实删除时返回 True。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa")
        self.assertTrue(config_db.delete_api_key(self.conn, k1))
        self.assertIsNone(config_db.get_api_key(self.conn, k1))
        self.assertFalse(config_db.delete_api_key(self.conn, k1))
        self.assertEqual(config_db.list_api_keys(self.conn, eid), [])

    def test_set_enabled(self):
        """启用/禁用切换生效；不存在的 id 返回 False。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa")
        self.assertTrue(config_db.set_api_key_enabled(self.conn, k1, 0))
        self.assertEqual(config_db.get_api_key(self.conn, k1)["enabled"], 0)
        self.assertTrue(config_db.set_api_key_enabled(self.conn, k1, 1))
        self.assertEqual(config_db.get_api_key(self.conn, k1)["enabled"], 1)
        self.assertFalse(config_db.set_api_key_enabled(self.conn, 999, 1))

    def test_cascade_delete_with_endpoint(self):
        """端点删除时 api_keys 级联删除（FK ON DELETE CASCADE）。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa")
        db.delete_api_endpoint(self.conn, eid)
        self.assertIsNone(config_db.get_api_key(self.conn, k1))
        # 表仍在（建表级联），删空后新增可用
        eid2 = self._add_endpoint()
        config_db.add_api_key(self.conn, eid2, "主 Key", "sk-bbb")
        self.assertEqual(len(config_db.list_api_keys(self.conn, eid2)), 1)

    @patch("config_db._write_audit_log")
    def test_audit_log_actions(self, mock_audit):
        """新增/启停/删除写审计日志，action 分别为 create/update/delete_api_key。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "主 Key", "sk-aaa",
                                   session_user="admin")
        self.assertEqual(
            mock_audit.call_args.args[1], "create_api_key",
            f"意外审计调用: {mock_audit.call_args}")
        config_db.set_api_key_enabled(self.conn, k1, 0, session_user="admin")
        config_db.delete_api_key(self.conn, k1, session_user="admin")
        actions = [c.args[1] for c in mock_audit.call_args_list]
        self.assertEqual(
            actions[-3:], ["create_api_key", "update_api_key", "delete_api_key"])


class TestMigration14(unittest.TestCase):
    """迁移 14：api_keys 建表 + 旧列数据迁入 + 幂等。"""

    def _legacy_db(self):
        """构造存量库：无 api_keys 表，旧列 api_key 有值。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute("DROP TABLE api_keys")
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("存量报表", "SELECT 1"))
        conn.execute(
            "INSERT INTO api_endpoints (report_id, name, url_path, api_key) "
            "VALUES (1, '存量端点', '/api/legacy', 'sk-legacy')")
        conn.commit()
        return conn

    def test_migration_creates_table_and_migrates_key(self):
        """旧列非空 → 建表 + 迁入（name=端点名、enabled=1）+ 旧列置空。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        row = conn.execute("SELECT * FROM api_keys").fetchone()
        self.assertIsNotNone(row, "迁移后 api_keys 应有记录")
        self.assertEqual(row["endpoint_id"], 1)
        self.assertEqual(row["name"], "存量端点")
        self.assertEqual(row["api_key"], "sk-legacy")
        self.assertEqual(row["enabled"], 1)
        old = conn.execute(
            "SELECT api_key FROM api_endpoints WHERE id=1").fetchone()[0]
        self.assertEqual(old, "", "迁移后旧列应置空（作兼容回退标记）")
        conn.close()

    def test_migration_idempotent(self):
        """重复执行不重复迁入（幂等）。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        config_db._init_sqlite_migrations(conn)
        n = conn.execute("SELECT COUNT(*) AS c FROM api_keys").fetchone()["c"]
        self.assertEqual(n, 1, "重复迁移不得产生重复记录")
        conn.close()

    def test_migration_keeps_existing_keys(self):
        """api_keys 已有记录（表存在）时迁移不重复、不丢数据。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("存量报表", "SELECT 1"))
        conn.execute(
            "INSERT INTO api_endpoints (report_id, name, url_path, api_key) "
            "VALUES (1, '存量端点', '/api/legacy', 'sk-legacy')")
        conn.commit()
        config_db.add_api_key(conn, 1, "已存在 Key", "sk-manual")
        config_db._init_sqlite_migrations(conn)
        keys = [(r["name"], r["api_key"]) for r in
                conn.execute("SELECT name, api_key FROM api_keys").fetchall()]
        self.assertEqual(keys, [("已存在 Key", "sk-manual"), ("存量端点", "sk-legacy")])
        conn.close()

    def test_migration_no_legacy_key_creates_empty_table(self):
        """旧列全空 → 建表但无记录（公开端点不受影响）。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute("DROP TABLE api_keys")
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("存量报表", "SELECT 1"))
        conn.execute(
            "INSERT INTO api_endpoints (report_id, name, url_path) "
            "VALUES (1, '公开端点', '/api/public')")
        conn.commit()
        config_db._init_sqlite_migrations(conn)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) AS c FROM api_keys").fetchone()["c"], 0)
        conn.close()


class TestValidateApiKeyUnit(unittest.TestCase):
    """_validate_api_key 旧列回退与公开端点判定（单元级）。"""

    def _endpoint_with_legacy_key(self):
        """构造 api_keys 表无记录、旧列有 key 的端点。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("报表", "SELECT 1"))
        conn.execute(
            "INSERT INTO api_endpoints (report_id, name, url_path, api_key) "
            "VALUES (1, '端点', '/api/legacy', 'sk-legacy')")
        conn.commit()
        return conn, db.get_api_endpoint(conn, 1)

    def test_fallback_to_legacy_column(self):
        """api_keys 表无记录时回退旧列：正确 key 通过、错误 key 拒绝、缺失拒绝。"""
        conn, ep = self._endpoint_with_legacy_key()
        self.assertIsNone(
            api_handler._validate_api_key(
                conn, ep, {"Authorization": "Bearer sk-legacy"}, {}))
        self.assertIsNone(
            api_handler._validate_api_key(
                conn, ep, {}, {"api_key": ["sk-legacy"]}))
        self.assertEqual(
            api_handler._validate_api_key(conn, ep, {}, {}),
            "未提供有效的 API Key")
        self.assertEqual(
            api_handler._validate_api_key(
                conn, ep, {}, {"api_key": ["sk-wrong"]}),
            "未提供有效的 API Key")
        conn.close()

    def test_public_endpoint_without_any_key(self):
        """端点无任何 key（表空 + 旧列空）→ 公开直接通过。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("报表", "SELECT 1"))
        conn.execute(
            "INSERT INTO api_endpoints (report_id, name, url_path) "
            "VALUES (1, '公开端点', '/api/public')")
        conn.commit()
        ep = db.get_api_endpoint(conn, 1)
        self.assertIsNone(api_handler._validate_api_key(conn, ep, {}, {}))
        self.assertIsNone(
            api_handler._validate_api_key(
                conn, ep, {"Authorization": "Bearer anything"}, {}))
        conn.close()

    def test_table_keys_take_precedence_over_legacy_column(self):
        """api_keys 有记录时优先表内 key，旧列不同值不生效（防旧列绕过）。"""
        conn, ep = self._endpoint_with_legacy_key()
        config_db.add_api_key(conn, ep["id"], "新 Key", "sk-new")
        # 旧列 key 不再生效
        self.assertEqual(
            api_handler._validate_api_key(
                conn, ep, {}, {"api_key": ["sk-legacy"]}),
            "未提供有效的 API Key")
        self.assertIsNone(
            api_handler._validate_api_key(
                conn, ep, {}, {"api_key": ["sk-new"]}))
        conn.close()

    def test_all_disabled_rejects_everything(self):
        """表内有记录但全部禁用 → 拒绝一切（含旧列 key）。"""
        conn, ep = self._endpoint_with_legacy_key()
        k1 = config_db.add_api_key(conn, ep["id"], "Key1", "sk-1")
        config_db.set_api_key_enabled(conn, k1, 0)
        for provided in ("sk-legacy", "sk-1", "sk-anything"):
            self.assertEqual(
                api_handler._validate_api_key(
                    conn, ep, {}, {"api_key": [provided]}),
                "未提供有效的 API Key",
                f"全部禁用时 key={provided} 应被拒绝")
        conn.close()
