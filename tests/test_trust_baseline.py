"""
test_trust_baseline.py — 信任底线域测试（spec ux-optimization 批次3 #8-#13）

覆盖矩阵（功能点 → 缺口编号 → 测试方法，格式见 docs/conv/test/full-coverage.md）：

#8 统一错误页（不裸奔异常详情 / 死胡同有返回入口）
  TB-08-01 _render_error_page 输出完整 HTML + 返回报表页导航链接
      → TestErrorPages.test_error_page_structure
  TB-08-02 404 走统一错误页
      → TestErrorPages.test_404_uses_error_page
  TB-08-03 500 响应不含异常详情文本（详情仅进日志）
      → TestErrorPages.test_500_no_exception_detail_leak
  TB-08-04 导出错误分支收口为 HTML 错误页
      → TestErrorPages.test_export_error_renders_html_page

#9 会话过期 next 回跳
  TB-09-01 认证失败重定向携带 expired=1 与 next=原路径
      → TestExpiredNextRedirect.test_auth_redirect_carries_next_and_expired
  TB-09-02 登录页 expired=1 显示过期提示
      → TestExpiredNextRedirect.test_login_page_shows_expired_notice
  TB-09-03 登录表单透传 hidden next 字段
      → TestExpiredNextRedirect.test_login_form_carries_hidden_next
  TB-09-04 登录成功 302 到 next（站内路径）
      → TestExpiredNextRedirect.test_login_success_redirects_to_next
  TB-09-05 next 外部 URL / 协议相对路径拒绝回 /report（open redirect 防护）
      → TestExpiredNextRedirect.test_login_rejects_external_next
      → TestExpiredNextRedirect.test_login_rejects_protocol_relative_next

#10 数据库错误人话化
  TB-10-01 errno 映射（1064/1146/1054/1142/2003/1045）
      → TestSqlErrorHumanize.test_known_errnos_mapped
  TB-10-02 未知异常兜底返回原文
      → TestSqlErrorHumanize.test_unknown_error_falls_back_to_raw
  TB-10-03 报表页渲染人话文案 + details 折叠原始错误
      → TestSqlErrorHumanize.test_report_page_renders_friendly_error

#11 登录失败限流（内存滑动窗口）
  TB-11-01 同一用户名窗口内第 6 次尝试被拒
      → TestLoginRateLimit.test_sixth_attempt_blocked
  TB-11-02 成功登录清零计数
      → TestLoginRateLimit.test_success_clears_failures
  TB-11-03 窗口滑出后恢复放行
      → TestLoginRateLimit.test_window_slide_restores_access
  TB-11-04 不同用户名互不影响
      → TestLoginRateLimit.test_isolated_per_username
  TB-11-05 被限时登录 handler 不触达用户库且提示模糊措辞
      → TestLoginRateLimit.test_handler_blocked_no_db_touch

#12 连接池密码不回显 + 测试连接
  TB-12-01 编辑态密码输入框 value 为空（留空沿用旧密码）
      → TestPasswordNoEcho.test_edit_form_does_not_echo_password
  TB-12-02 测试连接端点成功分支 flash 提示连接成功
      → TestPoolTestConnection.test_success_flash
  TB-12-03 测试连接端点失败分支 flash 提示原因（不炸 500）
      → TestPoolTestConnection.test_failure_flash

#13 flash 错误样式判定单点化
  TB-13-01 以「错误」开头判错样式；含「失败」段亦判错样式
      → TestFlashUnified.test_failure_text_gets_error_style
  TB-13-02 普通成功文案保持 success 样式
      → TestFlashUnified.test_success_text_keeps_style

测试策略：与 tests/test_auth_session.py 一致——ReportHandler 裸实例 +
mock 发送接口；config 库经 patch 指向 :memory:。
302 Location 断言取自 _sent_headers。
"""

import sqlite3
import time
import unittest
import urllib.parse
from unittest.mock import patch, MagicMock

import auth
import config
import db
import export
import render as render_mod
import report as report_mod
import server as srv
from tests.test_base import BaseConfigTest, init_test_db, make_config_db


def _make_handler(headers=None, path="/", client_address=("127.0.0.1", 5555)):
    """构造 ReportHandler 裸实例（同 test_auth_session 模式，补 path 属性）。"""
    h = srv.ReportHandler.__new__(srv.ReportHandler)
    h._session_token = None
    h.headers = headers or {}
    h.path = path
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
    parts = []
    for c in h.wfile.write.call_args_list:
        if c and c[0] and isinstance(c[0][0], bytes):
            parts.append(c[0][0].decode("utf-8"))
        elif c and c[0] and isinstance(c[0][0], str):
            parts.append(c[0][0])
    return "".join(parts)


def _open_memory_db(name):
    conn = sqlite3.connect(f"file:{name}?mode=memory&cache=shared", uri=True)
    conn.row_factory = sqlite3.Row
    init_test_db(conn)
    return conn


# ---------------------------------------------------------------------------
# 缺口 TB-08：统一错误页
# ---------------------------------------------------------------------------

class TestErrorPages(unittest.TestCase):
    """批次3#8：404/405/400/500 全部走统一错误页模板。"""

    def test_error_page_structure(self):
        html = srv._render_error_page(404, "页面不存在")
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("页面不存在", html)
        self.assertIn("/report", html, "必须提供返回报表页的导航入口")
        self.assertIn("404", html)

    def test_404_uses_error_page(self):
        """未知路径返回统一错误页而非裸 <h1>"""
        captured = {}

        def fake_send(status, body, extra=None):
            captured["status"] = status
            captured["body"] = body

        h = _make_handler(path="/no/such/page")
        with patch.object(srv, "_match_route", return_value=None), \
             patch.object(srv, "_allowed_methods_for_path", return_value=[]), \
             patch.object(srv.ReportHandler, "_send_html",
                          side_effect=lambda s, b, e=None: fake_send(s, b)):
            srv.ReportHandler._handle(h, "GET")
        self.assertEqual(captured.get("status"), 404)
        self.assertIn("页面不存在", captured["body"])
        self.assertIn("/report", captured["body"])

    def test_500_no_exception_detail_leak(self):
        """500 页面模板不含异常详情容器（防信息泄露），详情只进日志"""
        html = srv._render_error_page(500, "服务器内部错误")
        self.assertNotIn("<pre>", html)
        self.assertNotIn("Traceback", html)
        # 分支源码不再拼接 escape(str(e))（防回归锚点）
        import inspect
        src = inspect.getsource(srv.ReportHandler._handle)
        self.assertNotIn('escape(str(e))', src)

    def test_export_error_renders_html_page(self):
        """导出 404/403 等错误分支返回 HTML 错误页而非纯文本"""
        h = _make_handler(path="/export?id=999")
        with patch.object(srv, "export_mod") as m_exp:
            m_exp.handle_export.return_value = (404, "报表不存在", {})
            srv.ReportHandler._handle_export(
                h, "GET", "/export", "?id=999", None)
        body = _sent_body(h)
        self.assertIn("<!DOCTYPE html>", body)
        self.assertIn("/report", body)


# ---------------------------------------------------------------------------
# 缺口 TB-09：会话过期 next 回跳
# ---------------------------------------------------------------------------

class TestExpiredNextRedirect(BaseConfigTest):
    def setUp(self):
        super().setUp()
        auth.clear_all_sessions()
        self.addCleanup(auth.clear_all_sessions)

    def test_auth_redirect_carries_next_and_expired(self):
        h = _make_handler(headers={"Cookie": "session_id=invalid"},
                          path="/config")
        ok = srv.ReportHandler._authenticate(h)
        self.assertFalse(ok)
        loc = _sent_headers(h).get("Location", "")
        self.assertTrue(loc.startswith("/login?"), f"实际: {loc}")
        self.assertIn("expired=1", loc)
        self.assertIn(urllib.parse.quote("/config", safe=""), loc)

    def test_login_page_shows_expired_notice(self):
        h = _make_handler(path="/login")
        with patch.object(srv.ReportHandler, "_send_html",
                          side_effect=lambda s, b, e=None: h.wfile.write(
                              b.encode("utf-8"))):
            srv.ReportHandler._handle_login_get(
                h, "GET", "/login", "expired=1&next=%2Fconfig")
        body = _sent_body(h)
        self.assertIn("会话已过期", body)
        self.assertIn("重新登录", body)

    def test_login_form_carries_hidden_next(self):
        h = _make_handler(path="/login")
        with patch.object(srv.ReportHandler, "_send_html",
                          side_effect=lambda s, b, e=None: h.wfile.write(
                              b.encode("utf-8"))):
            srv.ReportHandler._handle_login_get(h, "GET", "/login",
                                                "next=%2Fconfig%3Fa%3D1")
        body = _sent_body(h)
        self.assertIn('type="hidden"', body)
        self.assertIn('name="next"', body)
        self.assertIn("/config?a=1", body)

    def test_login_success_redirects_to_next(self):
        db.add_user(self.conn, "admin", auth.hash_password("pw"))
        form = urllib.parse.urlencode(
            {"username": "admin", "password": "pw", "next": "/config"})
        h = _make_handler(path="/login")
        h._read_body = lambda: form
        with patch("db.get_config_db", return_value=self.conn), \
             patch("audit_db.record_operation"):
            srv.ReportHandler._handle_login(h, "POST", "/login", "", form)
        self.assertEqual(_sent_statuses(h)[0], 302)
        self.assertEqual(_sent_headers(h).get("Location"), "/config")

    def test_login_rejects_external_next(self):
        db.add_user(self.conn, "admin", auth.hash_password("pw"))
        form = urllib.parse.urlencode(
            {"username": "admin", "password": "pw",
             "next": "http://evil.example.com/phish"})
        h = _make_handler(path="/login")
        h._read_body = lambda: form
        with patch("db.get_config_db", return_value=self.conn), \
             patch("audit_db.record_operation"):
            srv.ReportHandler._handle_login(h, "POST", "/login", "", form)
        self.assertEqual(_sent_headers(h).get("Location"), "/report",
                         "外部 URL 必须忽略，回落 /report")

    def test_login_rejects_protocol_relative_next(self):
        db.add_user(self.conn, "admin", auth.hash_password("pw"))
        form = urllib.parse.urlencode(
            {"username": "admin", "password": "pw", "next": "//evil.com"})
        h = _make_handler(path="/login")
        h._read_body = lambda: form
        with patch("db.get_config_db", return_value=self.conn), \
             patch("audit_db.record_operation"):
            srv.ReportHandler._handle_login(h, "POST", "/login", "", form)
        self.assertEqual(_sent_headers(h).get("Location"), "/report")


# ---------------------------------------------------------------------------
# 缺口 TB-10：数据库错误人话化
# ---------------------------------------------------------------------------

class TestSqlErrorHumanize(unittest.TestCase):
    def test_known_errnos_mapped(self):
        cases = {
            1064: "语法", 1146: "数据表", 1054: "字段",
            1142: "权限", 2003: "无法连接", 1045: "账号或密码",
        }
        for errno, keyword in cases.items():
            e = Exception(f"{errno} (HY000): fake message")
            friendly, raw = report_mod.humanize_db_error(e)
            self.assertIn(keyword, friendly, f"errno {errno} 未映射到「{keyword}」")
            self.assertIn(str(e), raw, "原始错误必须保留供技术排查")

    def test_unknown_error_falls_back_to_raw(self):
        e = RuntimeError("weird failure")
        friendly, raw = report_mod.humanize_db_error(e)
        self.assertIn("weird failure", friendly)
        self.assertEqual(raw, str(e))

    def test_report_page_renders_friendly_error(self):
        """错误区块：人话主文案 + details 折叠原始错误"""
        friendly, raw = report_mod.humanize_db_error(
            Exception("1064 (42000) syntax near FROM"))
        html = report_mod.render_sql_error_section(friendly, raw)
        self.assertIn("语法", html)
        self.assertIn("<details", html)
        self.assertIn("1064", html)


# ---------------------------------------------------------------------------
# 缺口 TB-11：登录失败限流
# ---------------------------------------------------------------------------

class TestLoginRateLimit(unittest.TestCase):
    def setUp(self):
        auth.reset_login_failures()
        self.addCleanup(auth.reset_login_failures)

    def test_sixth_attempt_blocked(self):
        for _ in range(5):
            self.assertFalse(auth.is_login_blocked("alice"))
            auth.register_login_failure("alice")
        self.assertTrue(auth.is_login_blocked("alice"))

    def test_success_clears_failures(self):
        for _ in range(5):
            auth.register_login_failure("alice")
        self.assertTrue(auth.is_login_blocked("alice"))
        auth.clear_login_failures("alice")
        self.assertFalse(auth.is_login_blocked("alice"))

    def test_window_slide_restores_access(self):
        real_time = time.time
        base = real_time()
        with patch("auth.time.time", side_effect=lambda: base):
            for _ in range(5):
                auth.register_login_failure("alice")
            self.assertTrue(auth.is_login_blocked("alice"))
        with patch("auth.time.time", side_effect=lambda: base + 301):
            self.assertFalse(auth.is_login_blocked("alice"),
                             "超过 5 分钟窗口应恢复放行")

    def test_isolated_per_username(self):
        for _ in range(5):
            auth.register_login_failure("alice")
        self.assertTrue(auth.is_login_blocked("alice"))
        self.assertFalse(auth.is_login_blocked("bob"))

    def test_handler_blocked_no_db_touch(self):
        """被限流时直接返回提示页，不触达用户查询/密码校验"""
        for _ in range(5):
            auth.register_login_failure("alice")
        form = urllib.parse.urlencode({"username": "alice",
                                       "password": "anything"})
        h = _make_handler(path="/login", client_address=("9.9.9.9", 1))
        h._read_body = lambda: form
        with patch("db.get_config_db") as m_db:
            srv.ReportHandler._handle_login(h, "POST", "/login", "", form)
        m_db.assert_not_called()
        body = _sent_body(h)
        self.assertIn("过于频繁", body)


# ---------------------------------------------------------------------------
# 缺口 TB-12：连接池密码不回显 + 测试连接
# ---------------------------------------------------------------------------

class TestPasswordNoEcho(BaseConfigTest):
    def test_edit_form_does_not_echo_password(self):
        pool_id = db.add_pool(self.conn, "生产库", "10.0.0.5", 3306,
                              "root", "S3cret!", "analytics")
        pool = db.get_pool(self.conn, pool_id)
        html = render_mod.build_pool_form_html(pool=pool, is_edit=True)
        self.assertNotIn("S3cret!", html, "明文密码绝不能出现在页面里")
        self.assertIn('type="password"', html)


class TestPoolTestConnection(BaseConfigTest):
    def _post(self, form_body):
        return config.handle_request(self.conn, "POST", "/config/pools/test",
                                     "", form_body, session_user="admin")

    def test_success_flash(self):
        fake_conn = MagicMock()
        with patch("mysql.connector.connect", return_value=fake_conn) as mc:
            code, body, headers = self._post(
                "name=x&host=10.0.0.5&port=3306&user=root"
                "&password=pw&database=d")
        mc.assert_called_once()
        self.assertEqual(code, 302)
        self.assertIn("连接成功", urllib.parse.unquote(body))
        fake_conn.close.assert_called_once()

    def test_failure_flash(self):
        err = Exception("1045 (28000): Access denied")
        with patch("mysql.connector.connect", side_effect=err):
            code, body, headers = self._post(
                "name=x&host=10.0.0.5&port=3306&user=root"
                "&password=bad&database=d")
        self.assertEqual(code, 302)
        self.assertIn("错误:", urllib.parse.unquote(body))

    def test_bad_params_no_crash(self):
        code, body, headers = self._post("host=&port=&user=")
        self.assertEqual(code, 302)
        self.assertIn("错误:", urllib.parse.unquote(body))


# ---------------------------------------------------------------------------
# 缺口 TB-13：flash 错误样式判定单点化
# ---------------------------------------------------------------------------

class TestFlashUnified(unittest.TestCase):
    def test_failure_text_gets_error_style(self):
        """「失败」类文案应渲染错误样式（此前仅「错误」前缀触发——双标准残余）"""
        for msg in ("错误: x", "缓存重建失败，数据未刷新", "清理失败：超时"):
            html = render_mod.build_flash_html(msg)
            self.assertIn("flash-error", html, f"「{msg}」应为错误样式")

    def test_success_text_keeps_style(self):
        for msg in ("已完成", "报表 X 已删除", "用户 y 已更新"):
            html = render_mod.build_flash_html(msg)
            self.assertIn("flash-success", html, f"「{msg}」应为成功样式")


if __name__ == "__main__":
    unittest.main()
