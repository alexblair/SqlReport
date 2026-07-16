"""test_context.py — AppContext 数据容器测试"""

import unittest
from context import AppContext


class TestAppContext(unittest.TestCase):
    """AppContext 纯数据容器测试"""

    def test_create_with_all_fields(self):
        """所有字段通过构造参数传入"""
        ctx = AppContext(
            config_db="conn_obj",
            redis_manager="rm_obj",
            query_cache={"r1": "data"},
            sessions={"user": "token"},
        )
        self.assertEqual(ctx.config_db, "conn_obj")
        self.assertEqual(ctx.redis_manager, "rm_obj")
        self.assertEqual(ctx.query_cache, {"r1": "data"})
        self.assertEqual(ctx.sessions, {"user": "token"})

    def test_create_with_defaults(self):
        """不传参时各字段有合理默认值"""
        ctx = AppContext()
        self.assertIsNone(ctx.config_db)
        self.assertIsNone(ctx.redis_manager)
        self.assertEqual(ctx.query_cache, {})
        self.assertEqual(ctx.sessions, {})

    def test_fields_are_mutable(self):
        """dataclass 字段可正常修改"""
        ctx = AppContext()
        ctx.config_db = "sqlite_conn"
        ctx.redis_manager = "redis_conn"
        ctx.query_cache["k"] = "v"
        ctx.sessions["admin"] = "abc123"
        self.assertEqual(ctx.config_db, "sqlite_conn")
        self.assertEqual(ctx.redis_manager, "redis_conn")
        self.assertEqual(ctx.query_cache, {"k": "v"})
        self.assertEqual(ctx.sessions, {"admin": "abc123"})

    def test_multiple_instances_independent(self):
        """多个 AppContext 实例互不影响"""
        ctx1 = AppContext(config_db="db1")
        ctx2 = AppContext(config_db="db2")
        self.assertEqual(ctx1.config_db, "db1")
        self.assertEqual(ctx2.config_db, "db2")
        ctx1.config_db = "changed"
        self.assertEqual(ctx2.config_db, "db2")
