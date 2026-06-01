"""
test_auth.py — auth.py 单元测试

测试策略：
- 密码哈希：验证 hash+verify 正确性，以及错误密码/篡改哈希被拒绝
- Session：创建/查询/删除/清空
- Cookie：解析和生成
"""

import unittest
import auth


class TestPasswordHash(unittest.TestCase):
    """密码哈希与校验测试"""

    def test_hash_and_verify_correct(self):
        """正确密码应通过校验"""
        pw = "my_secret_pass_123"
        stored = auth.hash_password(pw)
        self.assertTrue(auth.verify_password(pw, stored))

    def test_verify_wrong_password(self):
        """错误密码应校验失败"""
        pw = "correct_password"
        stored = auth.hash_password(pw)
        self.assertFalse(auth.verify_password("wrong_password", stored))

    def test_hash_format_contains_salt(self):
        """哈希格式应为 salt$hex_digest"""
        stored = auth.hash_password("test")
        self.assertIn("$", stored)
        salt, digest = stored.split("$", 1)
        # salt 为 32 个十六进制字符（16 字节）
        self.assertEqual(len(salt), 32)
        # digest 为 64 个十六进制字符（SHA-256）
        self.assertEqual(len(digest), 64)

    def test_verify_malformed_hash(self):
        """格式错误的哈希应返回 False"""
        self.assertFalse(auth.verify_password("pw", "not-a-valid-format"))
        self.assertFalse(auth.verify_password("pw", ""))
        self.assertFalse(auth.verify_password("pw", "onlysalt$"))

    def test_same_password_different_hash(self):
        """同一密码每次生成的哈希应不同（因随机 salt）"""
        pw = "same_password"
        h1 = auth.hash_password(pw)
        h2 = auth.hash_password(pw)
        self.assertNotEqual(h1, h2)
        # 但两者都应能验证
        self.assertTrue(auth.verify_password(pw, h1))
        self.assertTrue(auth.verify_password(pw, h2))

    def test_empty_password(self):
        """空密码也应能正常工作"""
        stored = auth.hash_password("")
        self.assertTrue(auth.verify_password("", stored))
        self.assertFalse(auth.verify_password("not_empty", stored))


class TestSession(unittest.TestCase):
    """Session 管理测试"""

    def setUp(self):
        auth.clear_all_sessions()

    def test_create_and_get_session(self):
        """创建 session 后应能通过 token 查询到用户名"""
        token = auth.create_session("alice")
        user = auth.get_session_user(token)
        self.assertEqual(user, "alice")

    def test_get_invalid_token(self):
        """无效 token 应返回 None"""
        self.assertIsNone(auth.get_session_user("nonexistent_token"))

    def test_remove_session(self):
        """删除 session 后应返回 True，后续查询为 None"""
        token = auth.create_session("bob")
        self.assertTrue(auth.remove_session(token))
        self.assertIsNone(auth.get_session_user(token))

    def test_remove_nonexistent_session(self):
        """删除不存在的 session 应返回 False"""
        self.assertFalse(auth.remove_session("nope"))

    def test_clear_all_sessions(self):
        """清空所有 session 后所有 token 失效"""
        t1 = auth.create_session("u1")
        t2 = auth.create_session("u2")
        auth.clear_all_sessions()
        self.assertIsNone(auth.get_session_user(t1))
        self.assertIsNone(auth.get_session_user(t2))


class TestCookieUtils(unittest.TestCase):
    """Cookie 工具测试"""

    def test_parse_cookie_empty(self):
        """空字符串应返回空字典"""
        self.assertEqual(auth.parse_cookie(""), {})

    def test_parse_cookie_single(self):
        """解析单个 cookie"""
        result = auth.parse_cookie("session_id=abc123")
        self.assertEqual(result, {"session_id": "abc123"})

    def test_parse_cookie_multiple(self):
        """解析多个 cookie"""
        header = "session_id=abc123; theme=dark"
        result = auth.parse_cookie(header)
        self.assertEqual(result, {"session_id": "abc123", "theme": "dark"})

    def test_parse_cookie_with_spaces(self):
        """处理 key=value 之间的空格"""
        header = "session_id = abc123;  theme=dark"
        result = auth.parse_cookie(header)
        self.assertEqual(result, {"session_id": "abc123", "theme": "dark"})

    def test_make_set_cookie_header(self):
        """生成 Set-Cookie 应包含必要属性"""
        header = auth.make_set_cookie_header("tok123")
        self.assertIn("session_id=tok123", header)
        self.assertIn("Max-Age=", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertIn("Path=/", header)

    def test_make_expire_cookie_header(self):
        """清除 cookie 应设置 Max-Age=0"""
        header = auth.make_expire_cookie_header()
        self.assertIn("Max-Age=0", header)


if __name__ == "__main__":
    unittest.main()
