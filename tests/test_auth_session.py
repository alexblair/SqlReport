"""
test_auth_session.py — 认证与会话域补充测试（批次 T1）

覆盖缺口：
1. 登出端到端（/logout → /login + Set-Cookie 清除 + 服务端 session 移除）
2. 无效/过期 cookie 访问受保护页 → 302 重定向 /login
3. 滑动过期：成功访问后下行响应携带刷新后的 Set-Cookie
4. 登录空字段、用户不存在分支
5. 登录参数 SQL 注入防护
6. 首次启动默认 admin/admin123 自动创建
7. session 字典并发安全
8. X-Forwarded-For 客户端 IP 提取与 _get_forwarded_url 行为
9. _send_html 写响应时客户端断开 → BrokenPipeError/ConnectionResetError 静默
10. 认证审计事件链路（login / login_failed / logout 写入 audit_db）
11. 同一用户两次登录产生两个独立 session
12. 首页 GET / 的行为级重定向
13. _send_redirect/_send_html 携带 Set-Cookie 头

测试策略：
- 单元级：构造 ReportHandler 裸实例（__new__ + mock 发送接口），
  patch db.get_config_db 返回 SQLite :memory: 连接，patch audit_db.get_audit_db
  返回独立 :memory: 审计连接，避免触碰真实 config.db / audit.db。
- HTTP 级（登出端到端、首页重定向等）见 tests/test_server.py 的追加方法。
"""

import time
import threading
import sqlite3
import urllib.parse
import unittest
from unittest.mock import patch, MagicMock

import auth
import audit_db
import db
import server as srv
from tests.test_base import BaseConfigTest, init_test_db, make_config_db


def _make_handler(headers=None, client_address=("127.0.0.1", 5555)):
    """构造一个不连接真实 socket 的 ReportHandler 裸实例。

    用 _sent 列表记录 send_response / send_header / end_headers 调用，
    wfile 用 MagicMock 捕获写入内容。
    """
    h = srv.ReportHandler.__new__(srv.ReportHandler)
    h._session_token = None
    h.headers = headers or {}
    h.client_address = client_address
    h._sent = []
    h.wfile = MagicMock()
    h.send_response = lambda code, *a: h._sent.append(("status", code))
    h.send_header = lambda k, v: h._sent.append(("header", k, v))
    h.end_headers = lambda: h._sent.append(("end_headers", None))
    return h


def _sent_statuses(h):
    return [item[1] for item in h._sent if item[0] == "status"]


def _sent_headers(h):
    return {item[1]: item[2] for item in h._sent if item[0] == "header"}


def _sent_body(h):
    return h.wfile.write.call_args[0][0].decode("utf-8")


def _open_shared_memory_db(name: str) -> sqlite3.Connection:
    """打开 shared-cache 模式的 :memory: SQLite 连接。

    record_operation / main() 内部会对连接调用 close()，普通 :memory: 连接
    关闭后数据即销毁；shared-cache 模式允许多个连接共享同一数据库，
    只要保持一个 seed 连接存活，数据就不丢失。
    """
    conn = sqlite3.connect(f"file:{name}?mode=memory&cache=shared", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class _SharedConfigDbMixin:
    """将 db.get_config_db patch 为每次返回新的 shared-cache 内存连接。

    产品代码（_handle_login / create_session / refresh_session / main）会对
    连接调用 close()，不能复用同一个连接；shared-cache 模式 + seed 连接
    保活，保证数据在测试全程可见。
    """

    _CFG_DB_NAME = None

    def _open_cfg(self):
        conn = _open_shared_memory_db(self._CFG_DB_NAME)
        init_test_db(conn)
        return conn

    def _query_cfg(self, sql, params=()):
        conn = self._open_cfg()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _patch_config_db(self):
        self._cfg_seed = self._open_cfg()
        self.patch_db = patch("db.get_config_db", side_effect=self._open_cfg)
        self.patch_db.start()

    def _unpatch_config_db(self):
        self.patch_db.stop()
        self._cfg_seed.close()


class TestLoginHandler(_SharedConfigDbMixin, BaseConfigTest):
    """登录处理器（server.py::_handle_login）分支测试"""

    _CFG_DB_NAME = "t1_cfg_login"

    def setUp(self):
        super().setUp()
        self._patch_config_db()
        db.add_user(self._cfg_seed, "admin", auth.hash_password("admin123"))
        self._audit_seed = _open_shared_memory_db("t1_audit_login")
        audit_db.init_audit_db(self._audit_seed)
        self.patch_audit = patch("audit_db.get_audit_db", side_effect=self._open_audit)
        self.patch_audit.start()
        auth.clear_all_sessions()

    def tearDown(self):
        auth.clear_all_sessions()
        self.patch_audit.stop()
        self._audit_seed.close()
        self._unpatch_config_db()
        super().tearDown()

    def _open_audit(self):
        """每次调用返回新的 shared-memory 审计连接（init 幂等）"""
        conn = _open_shared_memory_db("t1_audit_login")
        audit_db.init_audit_db(conn)
        return conn

    def _query_audit(self, sql, params=()):
        conn = self._open_audit()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _post_login(self, username, password):
        h = _make_handler()
        h._read_body = lambda: urllib.parse.urlencode(
            {"username": username, "password": password})
        h._handle_login()
        return h

    def test_login_success_302_report_and_set_cookie(self):
        """缺口13/4：正确凭据 → 302 /report + Set-Cookie(session_id, Max-Age)"""
        h = self._post_login("admin", "admin123")
        headers = _sent_headers(h)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(headers.get("Location"), "/report")
        sc = headers.get("Set-Cookie", "")
        self.assertIn("session_id=", sc)
        self.assertIn("Max-Age=", sc)
        self.assertIn("HttpOnly", sc)
        # 会话确实已创建
        token = sc.split("session_id=", 1)[1].split(";", 1)[0]
        self.assertEqual(auth.get_session_user(token), "admin")

    def test_login_empty_username_rejected(self):
        """缺口4：空用户名 → 200 错误页，不创建 session，无 Set-Cookie"""
        before = dict(auth._sessions)
        h = self._post_login("", "admin123")
        self.assertIn(200, _sent_statuses(h))
        self.assertIn("用户名或密码错误", _sent_body(h))
        self.assertNotIn("Set-Cookie", _sent_headers(h))
        self.assertEqual(auth._sessions, before)

    def test_login_empty_password_rejected(self):
        """缺口4：空密码 → 200 错误页，不创建 session"""
        before = dict(auth._sessions)
        h = self._post_login("admin", "")
        self.assertIn(200, _sent_statuses(h))
        self.assertIn("用户名或密码错误", _sent_body(h))
        self.assertEqual(auth._sessions, before)

    def test_login_unknown_user_rejected(self):
        """缺口4：用户不存在 → 200 错误页，不创建 session"""
        before = dict(auth._sessions)
        h = self._post_login("nobody", "whatever")
        self.assertIn(200, _sent_statuses(h))
        self.assertIn("用户名或密码错误", _sent_body(h))
        self.assertEqual(auth._sessions, before)

    def test_login_sql_injection_username(self):
        """缺口5：' OR '1'='1 不应登录成功"""
        before = dict(auth._sessions)
        h = self._post_login("' OR '1'='1", "x")
        self.assertIn(200, _sent_statuses(h))
        self.assertIn("用户名或密码错误", _sent_body(h))
        self.assertEqual(auth._sessions, before)
        # 用户表不应被篡改
        rows = self._query_cfg("SELECT COUNT(*) FROM users")
        self.assertEqual(rows[0][0], 1)

    def test_login_sql_injection_comment_variants(self):
        """缺口5：注释类注入变体不应登录成功"""
        for payload in ["' OR 1=1 --", "admin' --", "admin'/*", "' OR '1'='1' #"]:
            with self.subTest(payload=payload):
                h = self._post_login(payload, "x")
                self.assertIn(200, _sent_statuses(h))
                self.assertIn("用户名或密码错误", _sent_body(h))
        rows = self._query_cfg("SELECT COUNT(*) FROM users")
        self.assertEqual(rows[0][0], 1)

    def test_login_success_audit_event(self):
        """缺口10：登录成功写入 login 审计事件"""
        self._post_login("admin", "admin123")
        rows = self._query_audit("SELECT * FROM audit_logs WHERE action='login'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "operation")
        self.assertEqual(rows[0]["session_user"], "admin")
        self.assertEqual(rows[0]["entity_type"], "user")

    def test_login_failed_audit_event(self):
        """缺口10：登录失败（错误密码）写入 login_failed 审计事件"""
        self._post_login("admin", "wrong-password")
        rows = self._query_audit("SELECT * FROM audit_logs WHERE action='login_failed'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_user"], "admin")

    def test_login_unknown_user_audit_event(self):
        """缺口10：用户不存在同样写入 login_failed（记录原始输入用户名）"""
        self._post_login("ghost_user", "x")
        rows = self._query_audit("SELECT * FROM audit_logs WHERE action='login_failed'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_user"], "ghost_user")

    def test_login_empty_username_no_audit(self):
        """缺口10（实际行为）：空用户名时 record_operation 跳过，不写 login_failed"""
        self._post_login("", "admin123")
        rows = self._query_audit("SELECT COUNT(*) FROM audit_logs WHERE action='login_failed'")
        self.assertEqual(rows[0][0], 0)


class TestLogoutHandler(_SharedConfigDbMixin, BaseConfigTest):
    """登出处理器（server.py::_handle_logout）测试"""

    _CFG_DB_NAME = "t1_cfg_logout"

    def setUp(self):
        super().setUp()
        self._patch_config_db()
        self._audit_seed = _open_shared_memory_db("t1_audit_logout")
        audit_db.init_audit_db(self._audit_seed)
        self.patch_audit = patch("audit_db.get_audit_db", side_effect=self._open_audit)
        self.patch_audit.start()
        auth.clear_all_sessions()

    def tearDown(self):
        auth.clear_all_sessions()
        self.patch_audit.stop()
        self._audit_seed.close()
        self._unpatch_config_db()
        super().tearDown()

    def _open_audit(self):
        conn = _open_shared_memory_db("t1_audit_logout")
        audit_db.init_audit_db(conn)
        return conn

    def _query_audit(self, sql, params=()):
        conn = self._open_audit()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_logout_removes_session_and_redirects(self):
        """缺口1：登出 → 302 /login + Set-Cookie(Max-Age=0) + 服务端 session 移除（内存与 DB）"""
        token = auth.create_session("admin")
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        h._handle_logout()
        headers = _sent_headers(h)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(headers.get("Location"), "/login")
        self.assertIn("Max-Age=0", headers.get("Set-Cookie", ""))
        self.assertIsNone(auth.get_session_user(token))
        self.assertNotIn(token, auth._sessions)
        row = self._query_cfg("SELECT COUNT(*) FROM sessions WHERE token=?", (token,))
        self.assertEqual(row[0][0], 0)

    def test_logout_without_cookie_still_redirects(self):
        """缺口1：无 cookie 登出 → 302 /login，不抛异常"""
        h = _make_handler()
        h._handle_logout()
        headers = _sent_headers(h)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(headers.get("Location"), "/login")

    def test_logout_writes_audit_event(self):
        """缺口10：登出写入 logout 审计事件"""
        token = auth.create_session("admin")
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        h._handle_logout()
        rows = self._query_audit("SELECT * FROM audit_logs WHERE action='logout'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_user"], "admin")

    def test_logout_without_session_no_audit(self):
        """缺口10（实际行为）：无有效 session 登出不写 logout 审计"""
        h = _make_handler(headers={"Cookie": "session_id=bogus"})
        h._handle_logout()
        rows = self._query_audit("SELECT COUNT(*) FROM audit_logs WHERE action='logout'")
        self.assertEqual(rows[0][0], 0)


class TestAuthenticateMiddleware(_SharedConfigDbMixin, BaseConfigTest):
    """认证中间件（server.py::_authenticate）测试"""

    _CFG_DB_NAME = "t1_cfg_auth"

    def setUp(self):
        super().setUp()
        self._patch_config_db()
        auth.clear_all_sessions()

    def tearDown(self):
        auth.clear_all_sessions()
        self._unpatch_config_db()
        super().tearDown()

    def test_invalid_cookie_redirects_login(self):
        """缺口2：无效 token → 302 /login，_authenticate 返回 False"""
        h = _make_handler(headers={"Cookie": "session_id=deadbeef"})
        self.assertFalse(h._authenticate())
        headers = _sent_headers(h)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(headers.get("Location"), "/login")

    def test_missing_cookie_redirects_login(self):
        """缺口2：无 Cookie 头 → 302 /login"""
        h = _make_handler()
        self.assertFalse(h._authenticate())
        self.assertEqual(_sent_headers(h).get("Location"), "/login")

    def test_expired_cookie_redirects_login(self):
        """缺口2：过期 token → 302 /login 且被清理"""
        token = auth.create_session("admin")
        auth._sessions[token] = ("admin", time.time() - auth._SESSION_TTL - 100)
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        self.assertFalse(h._authenticate())
        self.assertEqual(_sent_headers(h).get("Location"), "/login")
        self.assertNotIn(token, auth._sessions)

    def test_valid_cookie_authenticates_and_refreshes(self):
        """缺口3：有效 token → 认证通过且 created_at 被刷新（滑动过期）"""
        token = auth.create_session("admin")
        before = auth._sessions[token][1]
        time.sleep(0.01)
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        self.assertTrue(h._authenticate())
        self.assertEqual(h._session_token, token)
        self.assertGreater(auth._sessions[token][1], before)

    def test_refresh_updates_db_timestamp(self):
        """缺口3：滑动过期同步更新 SQLite sessions.created_at"""
        token = auth.create_session("admin")
        row1 = self._query_cfg("SELECT created_at FROM sessions WHERE token=?", (token,))
        time.sleep(0.01)
        auth.refresh_session(token)
        row2 = self._query_cfg("SELECT created_at FROM sessions WHERE token=?", (token,))
        self.assertGreater(row2[0][0], row1[0][0])

    def test_authenticated_send_html_carries_refreshed_set_cookie(self):
        """缺口3/13：认证后 _send_html 下行响应携带刷新 Set-Cookie(Max-Age=86400)"""
        token = auth.create_session("admin")
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        self.assertTrue(h._authenticate())
        h._sent.clear()
        h._send_html(200, "<html>ok</html>")
        headers = _sent_headers(h)
        self.assertIn(200, _sent_statuses(h))
        sc = headers.get("Set-Cookie", "")
        self.assertIn(f"session_id={token}", sc)
        self.assertIn("Max-Age=86400", sc)

    def test_authenticated_send_redirect_carries_set_cookie(self):
        """缺口13：认证后 _send_redirect 携带刷新 Set-Cookie"""
        token = auth.create_session("admin")
        h = _make_handler(headers={"Cookie": f"session_id={token}"})
        self.assertTrue(h._authenticate())
        h._sent.clear()
        h._send_redirect("/report")
        headers = _sent_headers(h)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(headers.get("Location"), "/report")
        self.assertIn("session_id=", headers.get("Set-Cookie", ""))

    def test_anonymous_send_html_no_set_cookie(self):
        """缺口13（对照）：未认证的 _send_html 不携带 Set-Cookie"""
        h = _make_handler()
        h._send_html(200, "<html>login</html>")
        self.assertNotIn("Set-Cookie", _sent_headers(h))


class TestHomeRedirect(unittest.TestCase):
    """首页重定向（server.py::_handle_home_redirect）测试"""

    def test_home_redirect_to_report(self):
        """缺口12：GET / 处理器重定向到 /report"""
        h = _make_handler()
        h._handle_home_redirect("GET", "/", "", None)
        self.assertIn(302, _sent_statuses(h))
        self.assertEqual(_sent_headers(h).get("Location"), "/report")

    def test_home_route_requires_auth(self):
        """缺口12：路由表中 / 标记 needs_auth（未认证访问 → 登录页）"""
        route = srv._match_route("GET", "/")
        self.assertIsNotNone(route)
        self.assertTrue(route.needs_auth)


class TestProxyHelpers(unittest.TestCase):
    """代理辅助函数（_get_client_ip / _get_forwarded_url）测试"""

    def test_get_client_ip_default_ignores_xff(self):
        """缺口8（修复）：默认（trust_xff=False）客户端 IP 取 socket 对端地址。

        X-Forwarded-For 首 IP 可由客户端伪造，未开启信任时一律忽略。
        """
        headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"}
        self.assertEqual(srv._get_client_ip(headers, ("10.0.0.1", 1234)), "10.0.0.1")

    def test_get_client_ip_trust_xff_first(self):
        """缺口8：开启 trust_xff 后 X-Forwarded-For 取第一个 IP（逗号分隔去空格）"""
        headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"}
        with patch("server.get_trust_xff", return_value=True):
            self.assertEqual(srv._get_client_ip(headers, ("10.0.0.1", 1234)), "1.2.3.4")

    def test_get_client_ip_trust_xff_single(self):
        """缺口8：开启 trust_xff 后单 IP 的 X-Forwarded-For"""
        headers = {"X-Forwarded-For": " 8.8.8.8 "}
        with patch("server.get_trust_xff", return_value=True):
            self.assertEqual(srv._get_client_ip(headers, ("10.0.0.1", 1234)), "8.8.8.8")

    def test_get_client_ip_no_xff_fallback(self):
        """缺口8：无 X-Forwarded-For 时回退到 client_address[0]（默认与开启均回退）"""
        self.assertEqual(srv._get_client_ip({}, ("10.0.0.1", 1234)), "10.0.0.1")
        with patch("server.get_trust_xff", return_value=True):
            self.assertEqual(srv._get_client_ip({}, ("10.0.0.1", 1234)), "10.0.0.1")

    def test_get_client_ip_blank_xff_fallback(self):
        """缺口8：空字符串 X-Forwarded-For 回退 client_address[0]"""
        headers = {"X-Forwarded-For": ""}
        self.assertEqual(srv._get_client_ip(headers, ("10.0.0.1", 1234)), "10.0.0.1")
        with patch("server.get_trust_xff", return_value=True):
            self.assertEqual(srv._get_client_ip(headers, ("10.0.0.1", 1234)), "10.0.0.1")

    def test_get_forwarded_url_proto_host_priority(self):
        """缺口8：X-Forwarded-Proto/Host 优先于 Host 头"""
        headers = {
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "app.example.com",
            "Host": "internal:8080",
        }
        self.assertEqual(srv._get_forwarded_url(headers, "/report"), "https://app.example.com/report")

    def test_get_forwarded_url_host_fallback(self):
        """缺口8：无 X-Forwarded-Host 时回退 Host 头，proto 默认 http"""
        headers = {"Host": "example.com:8000"}
        self.assertEqual(srv._get_forwarded_url(headers, "/config"), "http://example.com:8000/config")

    def test_get_forwarded_url_defaults(self):
        """缺口8：无任何头时默认 http://localhost"""
        self.assertEqual(srv._get_forwarded_url({}, "/login"), "http://localhost/login")


class TestSendHtmlClientDisconnect(unittest.TestCase):
    """_send_html 客户端断开静默处理（缺口9）测试"""

    def test_send_html_broken_pipe_silenced(self):
        """缺口9：BrokenPipeError 应被静默吞掉，不抛异常"""
        h = _make_handler()
        h.wfile.write.side_effect = BrokenPipeError("broken")
        h._send_html(200, "<html>big</html>")  # 不应抛异常

    def test_send_html_connection_reset_silenced(self):
        """缺口9：ConnectionResetError 应被静默吞掉，不抛异常"""
        h = _make_handler()
        h.wfile.write.side_effect = ConnectionResetError("reset")
        h._send_html(200, "<html>big</html>")  # 不应抛异常

    def test_send_html_normal_writes_body(self):
        """缺口9（对照）：正常路径写入完整 body"""
        h = _make_handler()
        h._send_html(200, "<html>hello</html>")
        self.assertIn(200, _sent_statuses(h))
        self.assertEqual(_sent_body(h), "<html>hello</html>")

    def test_send_html_with_session_token_adds_cookie(self):
        """缺口13：_send_html 在 _session_token 非空时附加 Set-Cookie"""
        h = _make_handler()
        h._session_token = "tok123"
        h._send_html(200, "<html>x</html>")
        sc = _sent_headers(h).get("Set-Cookie", "")
        self.assertIn("session_id=tok123", sc)
        self.assertIn("Max-Age=86400", sc)


class TestConcurrentSessions(unittest.TestCase):
    """session 字典并发安全（缺口7）测试"""

    def setUp(self):
        auth.clear_all_sessions()

    def tearDown(self):
        auth.clear_all_sessions()

    def test_concurrent_create_and_read_no_errors(self):
        """缺口7：多线程并发创建/读取 session 不抛异常，状态一致"""
        errors = []

        def worker(uid):
            try:
                for i in range(30):
                    tok = auth.create_session(f"u{uid}_{i}")
                    if auth.get_session_user(tok) != f"u{uid}_{i}":
                        errors.append(f"mismatch uid={uid} i={i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with patch("db.get_config_db", return_value=MagicMock()):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        self.assertEqual(errors, [])
        for t in threads:
            self.assertFalse(t.is_alive(), "线程未在超时内结束")
        self.assertEqual(len(auth._sessions), 8 * 30)

    def test_concurrent_remove_and_read_no_errors(self):
        """缺口7：并发创建/删除/读取混合操作不抛异常"""
        errors = []
        with patch("db.get_config_db", return_value=MagicMock()):
            tokens = [auth.create_session("alice") for _ in range(50)]

            def remover():
                try:
                    for tok in tokens[:25]:
                        auth.remove_session(tok)
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            def reader():
                try:
                    for tok in tokens:
                        auth.get_session_user(tok)
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=remover), threading.Thread(target=reader)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        self.assertEqual(errors, [])
        # 未被删除的 25 个 token 应全部仍有效
        for tok in tokens[25:]:
            self.assertEqual(auth.get_session_user(tok), "alice")
        for tok in tokens[:25]:
            self.assertNotIn(tok, auth._sessions)


class TestMultiSession(unittest.TestCase):
    """同一用户多个独立 session（缺口11）测试"""

    def setUp(self):
        auth.clear_all_sessions()

    def tearDown(self):
        auth.clear_all_sessions()

    def test_two_sessions_same_user_independent(self):
        """缺口11：同一用户两次登录产生两个独立 session，可独立登出"""
        with patch("db.get_config_db", return_value=MagicMock()):
            t1 = auth.create_session("alice")
            t2 = auth.create_session("alice")
            self.assertNotEqual(t1, t2)
            self.assertEqual(auth.get_session_user(t1), "alice")
            self.assertEqual(auth.get_session_user(t2), "alice")
            # 登出一个，另一个不受影响
            self.assertTrue(auth.remove_session(t1))
            self.assertIsNone(auth.get_session_user(t1))
            self.assertEqual(auth.get_session_user(t2), "alice")

    def test_concurrent_login_same_user_all_sessions_valid(self):
        """缺口11：并发同一用户多次登录，全部 session 独立有效"""
        with patch("db.get_config_db", return_value=MagicMock()):
            tokens = []

            def worker():
                tokens.append(auth.create_session("alice"))

            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            self.assertEqual(len(set(tokens)), 20, "20 次登录应产生 20 个不同 token")
            for tok in tokens:
                self.assertEqual(auth.get_session_user(tok), "alice")


class TestDefaultAdminCreation(unittest.TestCase):
    """首次启动默认 admin/admin123 自动创建（server.py::main，缺口6）"""

    # main() 内会对 conn 调用 close()，且 load_sessions() 在 close 之后
    # 还要读取 sessions 表，故用 shared-cache 内存库 + 保持 seed 连接存活
    _DB_NAME = "t1_main_cfg"

    def setUp(self):
        self._seed = _open_shared_memory_db(self._DB_NAME)
        init_test_db(self._seed)

    def tearDown(self):
        self._seed.close()

    def _open(self):
        conn = _open_shared_memory_db(self._DB_NAME)
        init_test_db(conn)
        return conn

    def _run_main(self):
        with patch.object(srv, "setup_logging"), \
             patch("file_permissions.load_permissions", return_value=False), \
             patch("db._get_engine", return_value="sqlite3"), \
             patch("db.get_config_db", side_effect=self._open), \
             patch("audit_db.get_audit_db", return_value=MagicMock()), \
             patch("http.server.ThreadingHTTPServer"):
            srv.main()

    def _get_users(self):
        conn = self._open()
        try:
            return db.get_all_users(conn)
        finally:
            conn.close()

    def test_main_creates_default_admin_on_first_start(self):
        """缺口6：用户表为空时自动创建 admin/admin123"""
        self._run_main()
        users = self._get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "admin")
        self.assertTrue(auth.verify_password("admin123", users[0]["password_hash"]))

    def test_main_skips_when_users_exist(self):
        """缺口6：已有用户时不创建 admin"""
        conn = self._open()
        try:
            db.add_user(conn, "bob", auth.hash_password("bobpw"))
        finally:
            conn.close()
        self._run_main()
        users = self._get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "bob")

    def test_main_idempotent_on_second_run(self):
        """缺口6：重复启动不重复创建 admin"""
        self._run_main()
        self._run_main()
        users = self._get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "admin")


if __name__ == "__main__":
    unittest.main()
