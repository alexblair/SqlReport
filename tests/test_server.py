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
import tempfile
from unittest.mock import patch

# 创建临时测试数据库文件，不碰生产 config.db
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="test_server_")
_tmp_db.close()
os.environ["CONFIG_DB"] = _tmp_db.name

import sqlite3
import db
import auth
import server as srv


# 测试用端口
TEST_PORT = 19080
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁用自动重定向，便于断言 302 的 Location/Set-Cookie 头"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _login_opener(base_url: str = BASE_URL):
    """返回 (opener, cookie_jar, token)，opener 已登录 admin/admin123 且不自动跟随重定向"""
    from http.cookiejar import CookieJar
    cj = CookieJar()
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{base_url}/login", data=data, method="POST")
    try:
        resp = opener.open(req)
    except urllib.error.HTTPError as e:
        # _NoRedirect 拦截 302 登录成功重定向
        if e.code != 302:
            raise
        resp = e
    if resp.status != 302 or resp.headers.get("Location") != "/report":
        raise AssertionError(f"登录失败: status={resp.status}")
    token = [c.value for c in cj if c.name == "session_id"][0]
    return opener, cj, token


def _open_no_redirect(opener, url, headers=None):
    """请求 url 并返回响应对象；302 以 HTTPError 形式返回（不跟随重定向）"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        return opener.open(req)
    except urllib.error.HTTPError as e:
        return e


def _expect_redirect(opener, url, location, headers=None):
    """断言 opener 请求 url 得到 302 且 Location 匹配，返回响应头"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        opener.open(req)
        raise AssertionError(f"期望 302 重定向到 {location}，但未发生: {url}")
    except urllib.error.HTTPError as e:
        if e.code != 302:
            raise AssertionError(f"期望 302，实际 {e.code}: {url}") from e
        got = e.headers.get("Location")
        if got != location:
            raise AssertionError(f"期望 Location={location}，实际 {got}: {url}") from e
        return e.headers


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
    server = http.server.ThreadingHTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
    srv._server_ref = server
    server.serve_forever()


def _stop_server():
    """停止服务器（shutdown 后关闭监听 socket，避免端口残留）"""
    if hasattr(srv, "_server_ref") and srv._server_ref is not None:
        srv._server_ref.shutdown()
        srv._server_ref.server_close()
        srv._server_ref = None


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
        # 清理临时测试数据库文件
        db_path = _tmp_db.name
        if os.path.exists(db_path):
            os.remove(db_path)

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

    def test_7_home_redirect_anonymous(self):
        """缺口12：未认证访问 GET / → 302 重定向 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        _expect_redirect(opener, f"{BASE_URL}/", "/login")

    def test_8_home_redirect_authenticated(self):
        """缺口12：已认证访问 GET / → 302 重定向 /report"""
        opener, _, _ = _login_opener()
        _expect_redirect(opener, f"{BASE_URL}/", "/report")

    def test_9_logout_end_to_end(self):
        """缺口1：登出端到端 — /logout → 302 /login + Set-Cookie 清除 + 服务端 session 移除"""
        opener, cj, token = _login_opener()

        # 登出响应：302 /login + Set-Cookie Max-Age=0
        resp = _open_no_redirect(opener, f"{BASE_URL}/logout")
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.headers.get("Location"), "/login")
        set_cookie = resp.headers.get("Set-Cookie", "")
        self.assertIn("Max-Age=0", set_cookie)
        self.assertNotIn(f"session_id={token}", set_cookie)

        # 服务端 session 已移除：旧 token 再访问受保护页 → 302 /login
        old_session_opener = urllib.request.build_opener(_NoRedirect)
        _expect_redirect(old_session_opener, f"{BASE_URL}/report", "/login",
                         headers={"Cookie": f"session_id={token}"})

        # CookieJar 收到 Max-Age=0 后应丢弃 cookie，jar 中不再有 session_id
        self.assertNotIn("session_id", [c.name for c in cj])

    def test_10_invalid_cookie_protected_page_302(self):
        """缺口2：无效 session cookie 访问 /report → 302 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        _expect_redirect(opener, f"{BASE_URL}/report", "/login",
                         headers={"Cookie": "session_id=deadbeef"})

    def test_11_expired_cookie_protected_page_302(self):
        """缺口2：过期 session cookie 访问 /report → 302 /login 且 session 被清理"""
        import auth
        token = auth.create_session("admin")
        auth._sessions[token] = ("admin", time.time() - auth._SESSION_TTL - 100)
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            _expect_redirect(opener, f"{BASE_URL}/report", "/login",
                             headers={"Cookie": f"session_id={token}"})
            self.assertNotIn(token, auth._sessions)
        finally:
            auth._sessions.pop(token, None)

    def test_12_sliding_expiry_refresh_set_cookie(self):
        """缺口3：成功访问后下行响应携带刷新后的 Set-Cookie（Max-Age=86400）"""
        opener, _, token = _login_opener()
        resp = opener.open(f"{BASE_URL}/report")
        self.assertEqual(resp.status, 200)
        set_cookie = resp.headers.get("Set-Cookie", "")
        self.assertIn(f"session_id={token}", set_cookie)
        self.assertIn("Max-Age=86400", set_cookie)
        self.assertIn("HttpOnly", set_cookie)

    def test_13_two_independent_sessions_same_user(self):
        """缺口11：同一用户两次登录产生两个独立 session，可独立登出"""
        opener_a, _, token_a = _login_opener()
        opener_b, _, token_b = _login_opener()
        self.assertNotEqual(token_a, token_b)

        # 两个 session 同时可访问
        self.assertEqual(opener_a.open(f"{BASE_URL}/report").status, 200)
        self.assertEqual(opener_b.open(f"{BASE_URL}/report").status, 200)

        # 登出 A，A 的 session 失效
        resp = _open_no_redirect(opener_a, f"{BASE_URL}/logout")
        self.assertEqual(resp.status, 302)
        stale_a = urllib.request.build_opener(_NoRedirect)
        _expect_redirect(stale_a, f"{BASE_URL}/report", "/login",
                         headers={"Cookie": f"session_id={token_a}"})

        # B 的 session 不受影响
        self.assertEqual(opener_b.open(f"{BASE_URL}/report").status, 200)

    def test_14_login_sql_injection_rejected(self):
        """缺口5（HTTP 级）：登录参数 SQL 注入不应登录成功"""
        for payload in ["' OR '1'='1", "' OR 1=1 --", "admin' --"]:
            with self.subTest(payload=payload):
                data = urllib.parse.urlencode(
                    {"username": payload, "password": "x"}).encode()
                opener = urllib.request.build_opener(_NoRedirect)
                try:
                    resp = opener.open(
                        urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST"))
                except urllib.error.HTTPError as e:
                    self.fail(f"登录注入不应 3xx: {payload} → {e.code}")
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("用户名或密码错误", html)

    def test_15_login_empty_fields_rejected(self):
        """缺口4（HTTP 级）：空用户名/空密码登录被拒绝"""
        for username, password in [("", "admin123"), ("admin", "")]:
            with self.subTest(username=username, password=password):
                data = urllib.parse.urlencode(
                    {"username": username, "password": password}).encode()
                opener = urllib.request.build_opener(_NoRedirect)
                resp = opener.open(
                    urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST"))
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("用户名或密码错误", html)


class TestRouteTable(unittest.TestCase):
    """路由表测试"""

    @classmethod
    def setUpClass(cls):
        cls.routes = srv.ROUTES

    def test_route_table_exists(self):
        """路由表应定义且非空"""
        self.assertTrue(hasattr(srv, "ROUTES"))
        self.assertGreater(len(self.routes), 0)

    def test_exact_path_routes(self):
        """精确路径路由应正确匹配"""
        for name, method, path in [
            ("login_get", "GET", "/login"),
            ("home", "GET", "/"),
            ("logout", "GET", "/logout"),
        ]:
            with self.subTest(name=name):
                self.assertIsNotNone(
                    srv._match_route(method, path),
                    f"{method} {path} 未匹配任何路由",
                )

    def test_prefix_path_routes(self):
        """前缀路径路由应匹配子路径"""
        for name, method, path in [
            ("config_root", "GET", "/config"),
            ("config_sub", "POST", "/config/pools/1/edit"),
            ("report_root", "GET", "/report"),
            ("report_sub", "POST", "/report"),
            ("export_root", "GET", "/export"),
            ("export_sub", "GET", "/export"),
        ]:
            with self.subTest(name=name):
                self.assertIsNotNone(
                    srv._match_route(method, path),
                    f"{method} {path} 未匹配任何路由",
                )

    def test_no_match_returns_none(self):
        """不存在的路径应返回 None"""
        self.assertIsNone(srv._match_route("GET", "/nonexistent"))
        self.assertIsNone(srv._match_route("DELETE", "/login"))
        self.assertIsNone(srv._match_route("PUT", "/"))

    def test_auth_routes_require_auth(self):
        """需要认证的路由应标记 needs_auth=True"""
        for path in ["/", "/logout", "/config", "/report", "/export"]:
            route = srv._match_route("GET", path)
            self.assertIsNotNone(route, f"{path} 未匹配任何路由")
            self.assertTrue(
                route.needs_auth,
                f"{path} 应需要认证但未标记",
            )

    def test_public_routes_no_auth(self):
        """无需认证的路由应标记 needs_auth=False"""
        for method, path in [("GET", "/login"), ("POST", "/login")]:
            route = srv._match_route(method, path)
            self.assertIsNotNone(route, f"{method} {path} 未匹配任何路由")
            self.assertFalse(route.needs_auth, f"{path} 不应需要认证")

    def test_route_method_restriction(self):
        """路由应限制 HTTP 方法"""
        self.assertIsNone(srv._match_route("POST", "/"))
        self.assertIsNone(srv._match_route("DELETE", "/login"))
        self.assertIsNone(srv._match_route("PUT", "/logout"))

    def test_db_routes_require_db(self):
        """需要数据库的路由应标记 needs_db=True"""
        for path in ["/config", "/report", "/export"]:
            route = srv._match_route("GET", path)
            self.assertIsNotNone(route, f"{path} 未匹配任何路由")
            self.assertTrue(route.needs_db, f"{path} 应需要数据库但未标记")

    def test_api_route_marker(self):
        """缺口 25：/api 路径在路由表中正确分发到 _handle_api。

        API 路由：无 session 认证（needs_auth=False）、需 DB 连接、
        任意 HTTP 方法（GET/POST/OPTIONS）均匹配、handler 为 _handle_api。
        """
        for method in ("GET", "POST", "OPTIONS"):
            route = srv._match_route(method, "/api/cust/data")
            self.assertIsNotNone(route, f"{method} /api/cust/data 未匹配任何路由")
            self.assertFalse(route.needs_auth, "/api 应无需 session 认证")
            self.assertTrue(route.needs_db, "/api 应需要 DB 连接")
            self.assertEqual(route.handler, "_handle_api")
        # 非 /api 前缀路径不得命中该路由
        route = srv._match_route("GET", "/apiary")
        self.assertIsNone(route)
        self.assertIsNone(srv._match_route("GET", "/not-api"))


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


class TestReportRefreshIntegration(unittest.TestCase):
    """T3 批次：refresh=1 的 HTTP 层 302 全流程（缺口 1/2）

    隔离策略：本类强制 SQLite 引擎并指向临时库（否则 app_config.json 启用
    的 MySQL 配置库会被真实读写，且 seed 报表会指向生产连接池）。
    """

    @classmethod
    def setUpClass(cls):
        """强制 SQLite 临时库 + 动态空闲端口启动 HTTP 服务器

        端口动态分配（bind 0 取系统分配）：环境中存在监督进程反复跑
        test_server，固定端口（含 19080）会被其占用，导致请求打到别的进程。
        """
        cls._engine_patch = patch("db._get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        cls._dbcfg_patch = patch("db._get_db_config",
                                 return_value={"path": _tmp_db.name})
        cls._dbcfg_patch.start()
        _set_up_db()
        srv.PORT = 0
        server = http.server.ThreadingHTTPServer((srv.HOST, 0), srv.ReportHandler)
        cls.port = server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        srv._server_ref = server
        cls._thread = threading.Thread(target=server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        _stop_server()
        cls._dbcfg_patch.stop()
        cls._engine_patch.stop()

    @classmethod
    def _seed_report(cls):
        """插入测试连接池与报表，返回报表 id

        prefer_cache 置 0：本环境 Redis 在线，若走 Redis 快照锁路径，
        execute_report 在 MySQL 失败时会泄漏重建锁（report.py 缺陷，见
        test_report_extra.TestExecuteReportRedisPaths），导致后续请求在
        wait_for_lock 阻塞数十秒。本类只验证 HTTP 302 流程，Redis 路径
        由单元测试覆盖，故关闭 prefer_cache 保持确定性。
        """
        conn = db.get_config_db()
        try:
            pools = db.get_all_pools(conn)
            if not pools:
                db.add_pool(conn, "集成池", "127.0.0.1", 3306, "u", "p", "d")
                pool_id = 1
            else:
                pool_id = pools[0]["id"]
            reports = db.get_all_reports(conn)
            for r in reports:
                if r["name"] == "集成刷新报表":
                    return r["id"]
            rid = db.add_report(conn, "集成刷新报表", "SELECT 1", 20, pool_id,
                                prefer_cache=0)
            conn.commit()
            return rid
        finally:
            conn.close()

    def test_refresh_redirects_without_refresh_param(self):
        """1. 登录后 GET /report?id=N&refresh=1 → 302 且 Location 剔除 refresh"""
        rid = self._seed_report()
        opener, _, _ = _login_opener(self.base_url)
        req = urllib.request.Request(f"{self.base_url}/report?id={rid}&refresh=1")
        try:
            opener.open(req)
            self.fail("refresh=1 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertEqual(e.headers["Location"], f"/report?id={rid}")
            self.assertNotIn("refresh", e.headers["Location"])

    def test_refresh_preserves_other_params_in_location(self):
        """1. 302 Location 保留 sort/filters 等业务参数"""
        rid = self._seed_report()
        opener, _, _ = _login_opener(self.base_url)
        url = f"{self.base_url}/report?id={rid}&refresh=1&sort=name&dir=asc&f_name=ali"
        req = urllib.request.Request(url)
        try:
            opener.open(req)
            self.fail("refresh=1 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            loc = e.headers["Location"]
        self.assertIn(f"id={rid}", loc)
        self.assertIn("sort=name", loc)
        self.assertIn("dir=asc", loc)
        self.assertIn("f_name=ali", loc)
        self.assertNotIn("refresh", loc)

    def test_refresh_unauthenticated_redirects_to_login(self):
        """2. 未认证访问 refresh=1 → 302 到 /login（认证优先于业务重定向）"""
        opener = urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(f"{self.base_url}/report?id=1&refresh=1")
        try:
            opener.open(req)
            self.fail("未认证应 302 到 /login，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertEqual(e.headers["Location"], "/login")

    def test_refresh_target_page_renders_after_redirect(self):
        """1. 302 后跟随 Location 的目标页可正常渲染（200，无 MySQL 时降级为错误页）"""
        rid = self._seed_report()
        opener, cj, _ = _login_opener(self.base_url)
        req = urllib.request.Request(f"{self.base_url}/report?id={rid}&refresh=1")
        try:
            opener.open(req)
            self.fail("refresh=1 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            target = e.headers["Location"]
        # 用同一 cookie 跟随重定向（跟随式 opener）
        follow = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        resp = follow.open(f"{self.base_url}{target}")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        # 无 MySQL 时预填失败，目标页应降级为错误页（200），而非 500
        self.assertIn("Web 报表工具", html)


class TestHttpStatusCodes(unittest.TestCase):
    """T2 批次缺口 8 + F3 修复：服务器级 404/405（未知路径/方法）

    真实行为：
    - 未知路径（GET/POST/OPTIONS/PUT/DELETE）→ 404（路由表无匹配）
    - 已知路径但方法不支持（PUT/DELETE 等）→ 405 + Allow 头列出允许方法
    - 方法不匹配不进入路由分发
    """

    @classmethod
    def setUpClass(cls):
        """强制 SQLite 临时库 + 动态空闲端口启动 HTTP 服务器

        端口动态分配（bind 0 取系统分配）：环境中有监督进程反复跑
        test_server，固定端口 19080 会被其占用，导致请求打到别的进程。
        """
        cls._engine_patch = patch("db._get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        cls._dbcfg_patch = patch("db._get_db_config",
                                 return_value={"path": _tmp_db.name})
        cls._dbcfg_patch.start()
        _set_up_db()
        srv.PORT = 0
        server = http.server.ThreadingHTTPServer((srv.HOST, 0), srv.ReportHandler)
        cls.port = server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        srv._server_ref = server
        cls._thread = threading.Thread(target=server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        _stop_server()
        cls._dbcfg_patch.stop()
        cls._engine_patch.stop()

    def _raw_request(self, path, method="GET"):
        """发送原始请求并返回 HTTPError/response，不跟随重定向。"""
        req = urllib.request.Request(f"{self.base_url}{path}", method=method)
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            return opener.open(req)
        except urllib.error.HTTPError as e:
            return e

    def test_unknown_get_path_returns_404(self):
        """未知路径 GET → 404 HTML"""
        resp = self._raw_request("/no-such-page-xyz")
        self.assertEqual(resp.status, 404)
        html = resp.read().decode("utf-8")
        self.assertIn("404", html)

    def test_unknown_post_path_returns_404(self):
        """未知路径 POST → 404（不依赖认证，路由先于认证判定）"""
        resp = self._raw_request("/no-such-post", method="POST")
        self.assertEqual(resp.status, 404)

    def test_unknown_options_path_returns_404(self):
        """未知路径 OPTIONS → 404"""
        resp = self._raw_request("/no-such-opt", method="OPTIONS")
        self.assertEqual(resp.status, 404)

    def test_put_unsupported_returns_405(self):
        """已知路径 PUT 无处理器 → 405 + Allow 头列出允许方法（修复 501）"""
        resp = self._raw_request("/login", method="PUT")
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.headers.get("Allow"), "GET, POST")

    def test_delete_unsupported_returns_405(self):
        """DELETE 已知路径 → 405 + Allow 头（修复 501）"""
        resp = self._raw_request("/login", method="DELETE")
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.headers.get("Allow"), "GET, POST")

    def test_put_unknown_path_returns_404(self):
        """未知路径 PUT → 404（路径未知优先于方法不支持）"""
        resp = self._raw_request("/no-such-put", method="PUT")
        self.assertEqual(resp.status, 404)

    def test_put_api_path_returns_405_with_allow(self):
        """已知 /api 路径 PUT → 405 + Allow: GET, POST, OPTIONS"""
        resp = self._raw_request("/api/cust", method="PUT")
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.headers.get("Allow"), "GET, POST, OPTIONS")

    def test_unknown_path_unauthenticated_still_404(self):
        """未认证访问未知路径仍返回 404（而非重定向 /login）"""
        opener = urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(f"{self.base_url}/definitely-not-here")
        try:
            opener.open(req)
            self.fail("未知路径应 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            self.assertNotEqual(e.headers.get("Location"), "/login")


if __name__ == "__main__":
    unittest.main()
