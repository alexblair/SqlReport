"""
test_server.py — server.py 集成测试

测试策略：
- 在独立线程启动 HTTP 服务器
- 使用 urllib.request 发送真实 HTTP 请求
- 验证认证流程、页面路由、Cookie 处理
"""

import unittest
import threading
import time
import urllib.request
import urllib.error
import http.server
import os

# 使用独立的测试数据库，不碰生产 config.db
os.environ["CONFIG_DB"] = "test_config.db"

import sqlite3
import db
import auth
import server as srv


# 测试用端口
TEST_PORT = 19080
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def _set_up_db():
    """创建测试数据库并插入默认用户"""
    conn = db.get_config_db()
    db.init_db(conn)
    # 先检查是否已有用户
    if not db.get_user(conn, "admin"):
        pw_hash = auth.hash_password("admin123")
        db.add_user(conn, "admin", pw_hash)
    conn.close()


def _start_server():
    """在后台线程启动 HTTP 服务器"""
    srv.PORT = TEST_PORT
    server = http.server.HTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
    srv._server_ref = server
    server.serve_forever()


def _stop_server():
    """停止服务器"""
    if hasattr(srv, "_server_ref"):
        srv._server_ref.shutdown()


class TestServerIntegration(unittest.TestCase):
    """服务器集成测试"""

    @classmethod
    def setUpClass(cls):
        _set_up_db()
        cls._thread = threading.Thread(target=_start_server, daemon=True)
        cls._thread.start()
        time.sleep(0.3)  # 等待服务器启动

    @classmethod
    def tearDownClass(cls):
        _stop_server()
        # 清理测试数据库文件（独立于生产 config.db）
        if os.path.exists("test_config.db"):
            os.remove("test_config.db")

    def test_1_login_page_accessible(self):
        """登录页无需认证即可访问"""
        resp = urllib.request.urlopen(f"{BASE_URL}/login")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("Web 报表工具", html)

    def test_2_login_fail(self):
        """错误密码应返回登录页并显示错误"""
        data = urllib.parse.urlencode({"username": "admin", "password": "wrong"}).encode()
        req = urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST")
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("用户名或密码错误", html)

    def test_3_login_success(self):
        """正确密码应登录成功并重定向"""
        data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
        req = urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST")
        # 不允许自动重定向，以便获取 cookie
        from http.cookiejar import CookieJar
        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        resp = opener.open(req)
        self.assertEqual(resp.status, 200)  # POST 成功后重定向
        # 检查是否有 session cookie
        cookies = list(cj)
        self.assertTrue(any(c.name == "session_id" for c in cookies))

    def test_4_report_requires_auth(self):
        """未认证访问 /report 应重定向到 /login"""
        req = urllib.request.Request(f"{BASE_URL}/report")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)

    def test_5_config_requires_auth(self):
        """未认证访问 /config 应重定向到 /login"""
        # 清除 cookie 使用空 opener
        opener = urllib.request.build_opener()
        req = urllib.request.Request(f"{BASE_URL}/config")
        try:
            opener.open(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)

    def test_6_auth_flow_full(self):
        """完整认证流程测试"""
        from http.cookiejar import CookieJar
        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        # 登录
        data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
        req = urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST")
        opener.open(req)
        cookies = list(cj)
        self.assertTrue(any(c.name == "session_id" for c in cookies))

        # 使用 cookie 访问报表页
        resp = opener.open(f"{BASE_URL}/report")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("选择报表", html)

        # 使用 cookie 访问配置页
        resp = opener.open(f"{BASE_URL}/config")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("配置管理", html)


class TestLoginPage(unittest.TestCase):
    """登录页渲染测试"""

    def test_render_without_error(self):
        html = srv._render_login_page()
        self.assertIn("Web 报表工具", html)
        self.assertIn("method=\"post\"", html)

    def test_render_with_error(self):
        html = srv._render_login_page("用户名错误")
        self.assertIn("用户名错误", html)

    def test_render_empty_error(self):
        html = srv._render_login_page("")
        self.assertIn("Web 报表工具", html)
        self.assertNotIn("用户名或密码错误", html)


if __name__ == "__main__":
    unittest.main()
