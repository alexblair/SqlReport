"""
test_audit_db.py — audit_db 模块测试

测试审计数据库的建表、插入、查询、筛选、分页、删除、导出功能。
"""

import unittest
import os
import tempfile
import json
from datetime import datetime

from audit_db import (
    _connect_audit_db, init_audit_db, insert_audit_log,
    query_audit_logs, count_audit_logs, export_audit_logs,
    delete_audit_logs,
)


class TestAuditDB(unittest.TestCase):
    """审计数据库功能测试。"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        import app_config
        self._orig_get_config = app_config.get_config
        app_config.get_config = lambda: {
            "audit_db": {"path": self.db_path},
        }
        self.conn = _connect_audit_db()
        init_audit_db(self.conn)

    def tearDown(self):
        self.conn.close()

        import app_config
        app_config.get_config = self._orig_get_config

        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _insert_sample(self):
        """插入若干条测试数据。"""
        for i in range(5):
            insert_audit_log(
                self.conn,
                type="operation",
                session_user="admin",
                action="create_pool",
                entity_type="pool",
                entity_name=f"pool_{i}",
                entity_id=i + 1,
            )
        insert_audit_log(
            self.conn,
            type="operation",
            session_user="user1",
            action="login",
            entity_type="user",
            entity_name="user1",
        )
        insert_audit_log(
            self.conn,
            type="operation",
            session_user="admin",
            action="login_failed",
            entity_type="user",
            entity_name="unknown",
        )
        insert_audit_log(
            self.conn,
            type="web_access",
            session_user="admin",
            action="page_view",
            entity_type="page",
            entity_name="/config",
            http_method="GET",
            http_path="/config",
            http_status=200,
            ip_address="127.0.0.1",
        )
        insert_audit_log(
            self.conn,
            type="api",
            session_user="api_key:test123",
            action="api_call",
            entity_type="api_endpoint",
            entity_name="/api/report/1",
            http_method="GET",
            http_path="/api/report/1",
            http_status=200,
            duration_ms=45,
            ip_address="10.0.0.1",
        )

    def test_init_and_insert(self):
        """建表后插入一条记录应成功。"""
        rid = insert_audit_log(
            self.conn,
            type="operation",
            session_user="admin",
            action="test_action",
            entity_type="test",
            entity_name="test_entity",
            entity_id=1,
            before_value={"key": "old"},
            after_value={"key": "new"},
        )
        self.assertGreater(rid, 0)

    def test_count_all(self):
        """无筛选条件时 count 应返回总行数。"""
        self._insert_sample()
        total = count_audit_logs(self.conn, {})
        self.assertEqual(total, 9)

    def test_query_pagination(self):
        """分页查询应返回正确 page 的数据。"""
        self._insert_sample()
        rows = query_audit_logs(self.conn, {}, page=1, page_size=3)
        self.assertEqual(len(rows), 3)

        rows_page2 = query_audit_logs(self.conn, {}, page=2, page_size=3)
        self.assertEqual(len(rows_page2), 3)

        rows_page3 = query_audit_logs(self.conn, {}, page=3, page_size=3)
        self.assertEqual(len(rows_page3), 3)

    def test_filter_by_type(self):
        """按 type 筛选应只返回对应类型的记录。"""
        self._insert_sample()
        op_count = count_audit_logs(self.conn, {"type": "operation"})
        self.assertEqual(op_count, 7)

        web_count = count_audit_logs(self.conn, {"type": "web_access"})
        self.assertEqual(web_count, 1)

        api_count = count_audit_logs(self.conn, {"type": "api"})
        self.assertEqual(api_count, 1)

    def test_filter_by_session_user(self):
        """按 session_user 筛选应只返回对应用户的记录。"""
        self._insert_sample()
        count = count_audit_logs(self.conn, {"session_user": "admin"})
        self.assertEqual(count, 7)

        count_user1 = count_audit_logs(self.conn, {"session_user": "user1"})
        self.assertEqual(count_user1, 1)

    def test_filter_by_keyword(self):
        """按关键字搜索应匹配 action、entity_name、http_path、session_user。"""
        self._insert_sample()
        # 搜索 action 中的 create_pool
        c = count_audit_logs(self.conn, {"keyword": "create_pool"})
        self.assertEqual(c, 5)

        # 搜索 http_path
        c = count_audit_logs(self.conn, {"keyword": "/config"})
        self.assertEqual(c, 1)

        # 搜索 session_user
        c = count_audit_logs(self.conn, {"keyword": "user1"})
        self.assertEqual(c, 1)

    def test_filter_date_range(self):
        """按时段筛选应只返回该时段内的记录。"""
        self._insert_sample()
        now = datetime.now().isoformat()
        # 查询今天到未来的记录，应该包含所有
        c = count_audit_logs(self.conn, {"date_from": datetime(2000, 1, 1).isoformat()})
        self.assertEqual(c, 9)

        # 查询很远将来的记录，应该没有
        c = count_audit_logs(self.conn, {"date_from": "2099-01-01T00:00:00"})
        self.assertEqual(c, 0)

    def test_export_all(self):
        """export_audit_logs 应返回全部记录（无分页）。"""
        self._insert_sample()
        rows = export_audit_logs(self.conn, {})
        self.assertEqual(len(rows), 9)

    def test_export_with_filter(self):
        """export_audit_logs 应只返回匹配筛选的记录。"""
        self._insert_sample()
        rows = export_audit_logs(self.conn, {"type": "api"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["http_path"], "/api/report/1")

    def test_delete_all(self):
        """无条件 delete 应清空全部记录。"""
        self._insert_sample()
        deleted = delete_audit_logs(self.conn, {})
        self.assertEqual(deleted, 9)
        total = count_audit_logs(self.conn, {})
        self.assertEqual(total, 0)

    def test_delete_by_type(self):
        """按 type delete 应只删除对应类型的记录。"""
        self._insert_sample()
        deleted = delete_audit_logs(self.conn, {"type": "operation"})
        self.assertEqual(deleted, 7)
        remaining = count_audit_logs(self.conn, {})
        self.assertEqual(remaining, 2)

    def test_delete_by_time(self):
        """按时间 delete 应只删除该时段内的记录。"""
        self._insert_sample()
        deleted = delete_audit_logs(self.conn, {"date_from": "2099-01-01T00:00:00"})
        self.assertEqual(deleted, 0)
        remaining = count_audit_logs(self.conn, {})
        self.assertEqual(remaining, 9)

    def test_before_after_serialization(self):
        """before_value 和 after_value 作为 dict 传入时应自动序列化为 JSON。"""
        rid = insert_audit_log(
            self.conn,
            type="operation",
            session_user="admin",
            action="update_pool",
            entity_type="pool",
            entity_id=1,
            entity_name="test_pool",
            before_value={"name": "old", "host": "old_host", "port": 3306},
            after_value={"name": "new", "host": "new_host", "port": 3307},
        )
        rows = query_audit_logs(self.conn, {}, page=1, page_size=10)
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["before_value"])
        self.assertIsNotNone(rows[0]["after_value"])

    def test_empty_table(self):
        """空表查询不应抛异常。"""
        rows = query_audit_logs(self.conn, {}, page=1, page_size=20)
        self.assertEqual(len(rows), 0)
        total = count_audit_logs(self.conn, {})
        self.assertEqual(total, 0)

    def test_insert_web_access(self):
        """插入 web_access 类型应正确存储 HTTP 相关字段。"""
        insert_audit_log(
            self.conn,
            type="web_access",
            session_user="admin",
            action="page_view",
            entity_type="page",
            entity_name="/report/1",
            http_method="GET",
            http_path="/report/1",
            http_status=200,
            ip_address="192.168.1.1",
            duration_ms=120,
        )
        rows = query_audit_logs(self.conn, {"type": "web_access"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["http_status"], 200)
        self.assertEqual(rows[0]["duration_ms"], 120)

    def test_timestamp_auto_fill(self):
        """不传 timestamp 时应自动填充为当前时间。"""
        rid = insert_audit_log(
            self.conn,
            type="operation",
            session_user="admin",
            action="test",
            entity_type="test",
        )
        rows = query_audit_logs(self.conn, {})
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["timestamp"])


if __name__ == "__main__":
    unittest.main()
