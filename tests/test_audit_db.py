"""
test_audit_db.py — audit_db 模块测试

测试审计数据库的建表、插入、查询、筛选、分页、删除、导出功能。

筛选匹配表达式批次覆盖（T3，keyword 与报表侧同一语法）：
1. keyword 通配 — 前缀/后缀/中间 `*` 翻译为 SQL LIKE %
2. keyword 多值 — 逗号 OR 展开、空段忽略、全空忽略、与 type AND 组合
3. 缺陷修复回归 — 字面 `%`/`_` 转义（旧行为误当 SQL 通配，已翻转断言）
4. 转义 — `\\*` 字面星号与未转义 `*` 通配互斥
5. 链路 — export/delete 复用同一 keyword 翻译
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

    def test_operation_type_no_ip_address(self):
        """契约：operation 类事件不记录 IP（ip_address 为 NULL）；web_access/api 才记录"""
        rid = insert_audit_log(
            self.conn,
            type="operation",
            session_user="admin",
            action="create_pool",
            entity_type="pool",
            entity_name="p1",
            entity_id=1,
        )
        ip = self.conn.execute(
            "SELECT ip_address FROM audit_logs WHERE id=?", (rid,)).fetchone()[0]
        self.assertIsNone(ip, "operation 事件不应记录 IP")

        rid2 = insert_audit_log(
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
        ip2 = self.conn.execute(
            "SELECT ip_address FROM audit_logs WHERE id=?", (rid2,)).fetchone()[0]
        self.assertEqual(ip2, "127.0.0.1", "web_access 事件应记录 IP")

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


class TestAuditKeywordExpression(unittest.TestCase):
    """审计页 keyword 统一匹配表达式（通配符 + 多值 + 转义）"""

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
        self._insert_sample()

    def tearDown(self):
        self.conn.close()

        import app_config
        app_config.get_config = self._orig_get_config

        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _insert_sample(self):
        """插入若干条测试数据（同主类样例 + 特殊字符行）。"""
        for i in range(5):
            insert_audit_log(
                self.conn, type="operation", session_user="admin",
                action="create_pool", entity_type="pool",
                entity_name=f"pool_{i}", entity_id=i + 1,
            )
        insert_audit_log(
            self.conn, type="operation", session_user="user1",
            action="login", entity_type="user", entity_name="user1",
        )
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="login_failed", entity_type="user", entity_name="unknown",
        )
        insert_audit_log(
            self.conn, type="web_access", session_user="admin",
            action="page_view", entity_type="page", entity_name="/config",
            http_method="GET", http_path="/config", http_status=200,
        )
        insert_audit_log(
            self.conn, type="api", session_user="api_key:test123",
            action="api_call", entity_type="api_endpoint",
            entity_name="/api/report/1", http_method="GET",
            http_path="/api/report/1", http_status=200,
        )

    def _insert_special(self):
        """插入含特殊字符的对照行（字面 % / _ / * 场景）。"""
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="100%完成", entity_type="misc",
        )
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="100分", entity_type="misc",
        )
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="a_b", entity_type="misc",
        )
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="axb", entity_type="misc",
        )
        insert_audit_log(
            self.conn, type="operation", session_user="admin",
            action="a*b", entity_type="misc",
        )

    def test_keyword_plain_regression(self):
        """回归：无通配 keyword 子串匹配不变"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "create_pool"}), 5)
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "/config"}), 1)
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "user1"}), 1)

    def test_keyword_wildcard_prefix(self):
        """通配前缀 create_* → action 以 create_ 开头的行"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "create_*"}), 5)

    def test_keyword_wildcard_suffix(self):
        """通配后缀 *failed → login_failed"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "*failed"}), 1)

    def test_keyword_wildcard_middle(self):
        """通配中间 login*ailed → login_failed"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "login*ailed"}), 1)

    def test_keyword_multivalue_or(self):
        """多值 OR：user1 或 /config → 两行"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "user1,/config"}), 2)

    def test_keyword_mixed_wildcard_multivalue(self):
        """多值混合通配：create_* 或 page_* → 6 行"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "create_*,page_*"}), 6)

    def test_keyword_literal_percent(self):
        """缺陷修复回归：% 从 SQL 通配改为字面量"""
        self._insert_special()
        rows = query_audit_logs(self.conn, {"keyword": "100%"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "100%完成")
        self.assertNotIn(
            "100分",
            [r["action"] for r in rows],
            "旧行为 % 当通配会误匹配 '100分'，现已按字面量匹配",
        )

    def test_keyword_literal_underscore(self):
        """缺陷修复回归：_ 从 SQL 单字符通配改为字面量"""
        self._insert_special()
        rows = query_audit_logs(self.conn, {"keyword": "a_b"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "a_b")
        self.assertNotIn(
            "axb",
            [r["action"] for r in rows],
            "旧行为 _ 当单字符通配会误匹配 'axb'，现已按字面量匹配",
        )

    def test_keyword_escaped_star(self):
        """\\* 转义 → 字面星号（a\\*b 只匹配 a*b）"""
        self._insert_special()
        rows = query_audit_logs(self.conn, {"keyword": r"a\*b"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "a*b")

    def test_keyword_unescaped_star_wildcard(self):
        """未转义 * → 通配（a*b 匹配 a*b、axb、a_b）"""
        self._insert_special()
        rows = query_audit_logs(self.conn, {"keyword": "a*b"})
        actions = sorted(r["action"] for r in rows)
        self.assertEqual(actions, ["a*b", "a_b", "axb"])

    def test_keyword_empty_segments_ignored(self):
        """空段忽略：create_pool,,login → 7 行"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": "create_pool,,login"}), 7)

    def test_keyword_all_empty_ignored(self):
        """全空多值（" , "）→ keyword 条件忽略，返回全部"""
        self.assertEqual(count_audit_logs(self.conn, {"keyword": " , "}), 9)

    def test_keyword_and_type_combined(self):
        """keyword 与 type 组合 AND"""
        self.assertEqual(
            count_audit_logs(self.conn, {"keyword": "create_*", "type": "operation"}), 5)

    def test_export_with_wildcard_keyword(self):
        """导出带通配 keyword"""
        rows = export_audit_logs(self.conn, {"keyword": "create_*"})
        self.assertEqual(len(rows), 5)

    def test_delete_with_multivalue_keyword(self):
        """清理带多值 keyword"""
        deleted = delete_audit_logs(self.conn, {"keyword": "user1,/config"})
        self.assertEqual(deleted, 2)
        self.assertEqual(count_audit_logs(self.conn, {}), 7)


if __name__ == "__main__":
    unittest.main()
