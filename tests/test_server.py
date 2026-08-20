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
import urllib.parse
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


class TestSafeLocation(unittest.TestCase):
    """server._safe_location 兜底编码（http.server 响应头仅支持 latin-1）"""

    def test_ascii_location_unchanged(self):
        """纯 ASCII Location 原样返回"""
        self.assertEqual(srv._safe_location("/report?id=1"), "/report?id=1")

    def test_encoded_location_unchanged(self):
        """已百分号编码的 Location 不被双重编码"""
        loc = "/config/api-endpoints?flash=%E9%94%99%E8%AF%AF"
        self.assertEqual(srv._safe_location(loc), loc)

    def test_non_ascii_location_encoded(self):
        """含中文的 Location 被兜底编码且可 latin-1 编码"""
        out = srv._safe_location("/config/api-endpoints?flash=API 接口已删除")
        out.encode("latin-1")
        self.assertNotIn("接口", out)
        self.assertIn("flash=", out)

    def test_non_ascii_location_keeps_structure(self):
        """兜底编码保留 URL 结构字符与已编码部分"""
        out = srv._safe_location("/a/b?x=中文&y=%E4%B8%AD&z=1")
        self.assertTrue(out.startswith("/a/b?x="))
        self.assertIn("&y=%E4%B8%AD", out)
        self.assertIn("&z=1", out)


class TestReportRefreshIntegration(unittest.TestCase):
    """T5 批次（PH-08）：POST action=refresh_cache 的 HTTP 层 302 全流程

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

    def test_refresh_redirects_with_flash(self):
        """1. 登录后 POST /report（action=refresh_cache）→ 302 且 Location 含 flash"""
        rid = self._seed_report()
        opener, _, _ = _login_opener(self.base_url)
        data = urllib.parse.urlencode({"action": "refresh_cache", "id": rid})
        req = urllib.request.Request(f"{self.base_url}/report", data=data.encode(),
                                     method="POST")
        try:
            opener.open(req)
            self.fail("refresh_cache 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            loc = e.headers["Location"]
        self.assertTrue(loc.startswith(f"/report?id={rid}"), loc)
        self.assertIn("flash=", loc)

    def test_refresh_preserves_other_params_in_location(self):
        """1. 302 Location 保留 sort/filters 等业务参数"""
        rid = self._seed_report()
        opener, _, _ = _login_opener(self.base_url)
        data = urllib.parse.urlencode({"action": "refresh_cache", "id": rid,
                                       "sort": "name", "dir": "asc", "f_name": "ali"})
        req = urllib.request.Request(f"{self.base_url}/report", data=data.encode(),
                                     method="POST")
        try:
            opener.open(req)
            self.fail("refresh_cache 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            loc = e.headers["Location"]
        self.assertIn(f"id={rid}", loc)
        self.assertIn("sort=name", loc)
        self.assertIn("dir=asc", loc)
        self.assertIn("f_name=ali", loc)
        self.assertIn("flash=", loc)

    def test_refresh_unauthenticated_redirects_to_login(self):
        """2. 未认证 POST refresh_cache → 302 到 /login（认证优先于业务重定向）"""
        opener = urllib.request.build_opener(_NoRedirect)
        data = urllib.parse.urlencode({"action": "refresh_cache", "id": "1"})
        req = urllib.request.Request(f"{self.base_url}/report", data=data.encode(),
                                     method="POST")
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
        data = urllib.parse.urlencode({"action": "refresh_cache", "id": rid})
        req = urllib.request.Request(f"{self.base_url}/report", data=data.encode(),
                                     method="POST")
        try:
            opener.open(req)
            self.fail("refresh_cache 应返回 302，实际 200")
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


class TestApiEndpointDeleteIntegration(unittest.TestCase):
    """API 端点独立管理页删除端到端：中文 flash 302 不产生 500

    回归：delete 分支直拼中文 flash 进 Location，send_header latin-1 编码
    头时抛 UnicodeEncodeError → 500（报错信息逐字为
    'latin-1' codec can't encode characters in position 42-46）。
    """

    @classmethod
    def setUpClass(cls):
        """强制 SQLite 临时库 + 动态空闲端口启动 HTTP 服务器"""
        cls._engine_patch = patch("db._get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        cls._dbcfg_patch = patch("db._get_db_config",
                                 return_value={"path": _tmp_db.name})
        cls._dbcfg_patch.start()
        _set_up_db()
        conn = db.get_config_db()
        db.add_report(conn, "删除集成报表", "SELECT 1", 20, None, prefer_cache=0)
        conn.execute(
            "INSERT INTO api_endpoints (report_id,name,url_path,output_format) "
            "VALUES (?,?,?,?)",
            (1, "删除集成端点", "/api/del-e2e", "json"))
        conn.commit()
        conn.close()
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

    def test_delete_endpoint_returns_302_not_500(self):
        """POST delete 成功 → 302（此前 500），Location 可 latin-1 编码"""
        opener, _, _ = _login_opener(self.base_url)
        req = urllib.request.Request(
            f"{self.base_url}/config/api-endpoints",
            data=urllib.parse.urlencode({"action": "delete", "endpoint_id": 1}).encode(),
            method="POST",
        )
        try:
            opener.open(req)
            self.fail("delete 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            loc = e.headers["Location"]
        loc.encode("latin-1")
        self.assertIn("flash=", loc)

    def test_delete_endpoint_redirect_target_renders(self):
        """302 后跟随 Location 目标页可渲染 200，且显示删除成功 flash"""
        opener, cj, _ = _login_opener(self.base_url)
        req = urllib.request.Request(
            f"{self.base_url}/config/api-endpoints",
            data=urllib.parse.urlencode({"action": "delete", "endpoint_id": 1}).encode(),
            method="POST",
        )
        try:
            opener.open(req)
            self.fail("delete 应返回 302，实际 200")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            target = e.headers["Location"]
        follow = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        resp = follow.open(f"{self.base_url}{target}")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("API 接口已删除", html)


class TestConfigReportsRoute(unittest.TestCase):
    """PH-13：/config/reports 报表管理独立页路由端到端"""

    @classmethod
    def setUpClass(cls):
        cls._engine_patch = patch("db._get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        cls._dbcfg_patch = patch("db._get_db_config",
                                 return_value={"path": _tmp_db.name})
        cls._dbcfg_patch.start()
        _set_up_db()
        conn = db.get_config_db()
        db.add_report(conn, "路由集成报表", "SELECT 1", 20, None, prefer_cache=0)
        conn.commit()
        conn.close()
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

    def test_reports_route_requires_auth(self):
        """未登录访问 /config/reports → 302 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(f"{self.base_url}/config/reports")
            self.fail("未登录应 302")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("/login", e.headers.get("Location", ""))

    def test_reports_route_renders_list(self):
        """登录后 GET /config/reports → 200 含报表列表与批量操作"""
        opener, _, _ = _login_opener(self.base_url)
        resp = opener.open(f"{self.base_url}/config/reports")
        self.assertEqual(resp.status, 200)
        html = resp.read().decode("utf-8")
        self.assertIn("报表管理", html)
        self.assertIn("路由集成报表", html)
        self.assertIn("批量修改连接池", html)


class TestConfigCategoriesRoute(unittest.TestCase):
    """config-reports-merge：/config/categories 旧地址重定向到报表管理页"""

    @classmethod
    def setUpClass(cls):
        cls._engine_patch = patch("db._get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        cls._dbcfg_patch = patch("db._get_db_config",
                                 return_value={"path": _tmp_db.name})
        cls._dbcfg_patch.start()
        _set_up_db()
        conn = db.get_config_db()
        db.add_category(conn, "路由集成分类")
        conn.commit()
        conn.close()
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

    def test_categories_route_requires_auth(self):
        """未登录访问 /config/categories → 302 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(f"{self.base_url}/config/categories")
            self.fail("未登录应 302")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("/login", e.headers.get("Location", ""))

    def test_categories_route_redirects_to_reports(self):
        """登录后 GET /config/categories → 302 /config/reports（旧地址兼容）"""
        opener, _, _ = _login_opener(self.base_url)
        try:
            opener.open(f"{self.base_url}/config/categories")
            self.fail("应 302 重定向")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertEqual(e.headers.get("Location", ""), "/config/reports")


class TestStaticVendorRoute(unittest.TestCase):
    """M5 白名单静态路由集成测试。

    独立服务器 + 动态端口（bind 0）+ 临时 vendor 根（patch server._VENDOR_ROOT），
    不依赖真实 vendor 资产文件。静态资产无鉴权（与 CDN 直出定位一致）。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        vendor = os.path.join(cls._tmpdir.name, "vendor")
        js_dir = os.path.join(vendor, "mermaid@11.16.1")
        other_dir = os.path.join(vendor, "other")
        os.makedirs(js_dir)
        os.makedirs(other_dir)
        with open(os.path.join(js_dir, "mermaid.min.js"), "w", encoding="utf-8") as f:
            f.write("/* mermaid fixture */")
        with open(os.path.join(js_dir, "style.css"), "w", encoding="utf-8") as f:
            f.write("body{}")
        with open(os.path.join(other_dir, "secret.txt"), "w", encoding="utf-8") as f:
            f.write("secret")
        cls._vendor = vendor
        cls._patcher = patch("server._VENDOR_ROOT", vendor)
        cls._patcher.start()
        cls._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), srv.ReportHandler)
        cls.base_url = f"http://127.0.0.1:{cls._server.server_address[1]}"
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._patcher.stop()
        cls._tmpdir.cleanup()

    def _get(self, path):
        return urllib.request.urlopen(f"{self.base_url}{path}")

    def test_vendor_js_served_no_auth(self):
        """存在的 vendor js 无鉴权 → 200 + text/javascript + immutable"""
        resp = self._get("/static/vendor/mermaid@11.16.1/mermaid.min.js")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "text/javascript; charset=utf-8")
        self.assertIn("immutable", resp.headers.get("Cache-Control", ""))
        self.assertIn("mermaid fixture", resp.read().decode("utf-8"))

    def test_vendor_css_mime(self):
        resp = self._get("/static/vendor/mermaid@11.16.1/style.css")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "text/css; charset=utf-8")

    def test_missing_file_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/mermaid@11.16.1/nope.js")
        self.assertEqual(ctx.exception.code, 404)

    def test_missing_vendor_dir_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/unknown@1.0.0/file.js")
        self.assertEqual(ctx.exception.code, 404)

    def test_path_traversal_rejected(self):
        # %2e%2e 编码绕过客户端 URL 规范化，服务端 unquote 后还原为 .. 穿越
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/%2e%2e/%2e%2e/etc/passwd")
        self.assertEqual(ctx.exception.code, 404)

    def test_single_dot_traversal_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/%2e%2e/")
        self.assertEqual(ctx.exception.code, 404)

    def test_outside_whitelist_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/other/x.js")
        self.assertEqual(ctx.exception.code, 404)

    def test_vendor_subpath_escaping_root_404(self):
        # vendor/other 仍在 vendor 根内但无 .js 白名单扩展名 → 404
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/other/secret.txt")
        self.assertEqual(ctx.exception.code, 404)

    def test_non_whitelist_extension_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/mermaid@11.16.1/evil.exe")
        self.assertEqual(ctx.exception.code, 404)

    def test_non_get_method_405(self):
        data = b"x"
        req = urllib.request.Request(
            f"{self.base_url}/static/vendor/mermaid@11.16.1/mermaid.min.js",
            data=data, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 405)
        self.assertIn("GET", ctx.exception.headers.get("Allow", ""))

    def test_directory_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/static/vendor/mermaid@11.16.1")
        self.assertEqual(ctx.exception.code, 404)


class TestMemoPreviewEndpoint(unittest.TestCase):
    """M4 备注 Markdown 预览端点集成测试（动态端口 + 临时 DB）"""

    @classmethod
    def setUpClass(cls):
        _set_up_db()
        cls._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), srv.ReportHandler)
        cls.base_url = f"http://127.0.0.1:{cls._server.server_address[1]}"
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()

    def test_memo_preview_requires_auth(self):
        """未认证 POST → 302 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        data = urllib.parse.urlencode({"memo": "# 标题"}).encode()
        req = urllib.request.Request(f"{self.base_url}/config/reports/memo-preview",
                                     data=data, method="POST")
        try:
            opener.open(req)
            self.fail("未登录应 302")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("/login", e.headers.get("Location", ""))

    def test_memo_preview_authenticated_returns_html(self):
        """登录后 POST → 200 渲染 HTML 片段"""
        opener, _, _ = _login_opener(self.base_url)
        data = urllib.parse.urlencode({"memo": "# 标题"}).encode()
        req = urllib.request.Request(f"{self.base_url}/config/reports/memo-preview",
                                     data=data, method="POST")
        resp = opener.open(req)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "text/html; charset=utf-8")
        self.assertIn("<h1>标题</h1>", resp.read().decode("utf-8"))

    def test_desc_preview_requires_auth(self):
        """description-preview 未认证 POST → 302 /login"""
        opener = urllib.request.build_opener(_NoRedirect)
        data = urllib.parse.urlencode({"description": "# 标题"}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/config/api-endpoints/description-preview",
            data=data, method="POST")
        try:
            opener.open(req)
            self.fail("未登录应 302")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("/login", e.headers.get("Location", ""))

    def test_desc_preview_authenticated_returns_html(self):
        """登录后 POST → 200 渲染 HTML 片段"""
        opener, _, _ = _login_opener(self.base_url)
        data = urllib.parse.urlencode({"description": "# 标题"}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/config/api-endpoints/description-preview",
            data=data, method="POST")
        resp = opener.open(req)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "text/html; charset=utf-8")
        self.assertIn("<h1>标题</h1>", resp.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
