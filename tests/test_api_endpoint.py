"""
test_api_endpoint.py — API 端点功能集成测试

测试策略：
- 使用临时 SQLite 文件作为共享数据库（CONFIG_DB 环境变量）
- Mock db.create_mysql_connection 避免真实 MySQL 依赖
- CRUD 测试直接调用 config_db 函数
- HTTP 测试通过 urllib.request 发送真实 HTTP 请求

筛选匹配表达式批次覆盖（T2，API 链路）：
- API filter JSON 通配/多值/混合（contains 通配、多值 eq、通配+多值）
- 数字等非字符串 filter val 不再 500（T1 str 防御 + _filter_val_str 归一化）
- POST 覆盖 rules filters 同样支持通配与数字 val

PH-01 缓存新鲜度批次覆盖：
- refresh=1 命中缓存仍直查 MySQL（查询计数增加）；无 refresh 走缓存
- refresh 非法值忽略（abc）；yes/TRUE 别名生效（严格值校验）
- fetch_all 与 refresh 可叠加
"""

import unittest
import unittest.mock
import threading
import time
import urllib.request
import urllib.error
import http.server
import os
import tempfile
import json
import sqlite3
import re

# 创建临时测试数据库文件
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="test_api_")
_tmp_db.close()
os.environ["CONFIG_DB"] = _tmp_db.name

# 创建临时 app_config.json 强制使用 SQLite
import json
_test_config_path = _tmp_db.name.replace(".db", "_config.json")
with open(_test_config_path, "w", encoding="utf-8") as _f:
    json.dump({
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _tmp_db.name}],
        "server": {"host": "0.0.0.0", "port": 9091},
        "log": {"enable": False, "path": "/dev/null"},
    }, _f)
os.environ["CONFIG_FILE"] = _test_config_path

# 强制 app_config 重新加载
import app_config as _app_config
_app_config.reload_config()

import db
import auth
import server as srv
import api_handler
import report
from tests.test_mysql_mock import MockMySQLMixin

TEST_PORT = 19091
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def _get_conn():
    """获取指向共享临时文件的配置数据库连接。"""
    conn = sqlite3.connect(_tmp_db.name, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _set_up_db():
    """创建测试数据库并插入测试数据"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL, password TEXT NOT NULL,
            database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS report_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            parent_id INTEGER, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, category_id INTEGER, memo TEXT,
            result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL,
            name TEXT NOT NULL, url_path TEXT UNIQUE NOT NULL,
            output_format TEXT NOT NULL DEFAULT 'json', columns TEXT, filters TEXT,
            sorts TEXT, row_limit INTEGER DEFAULT 0, api_key TEXT,
            allowed_origins TEXT, enabled INTEGER NOT NULL DEFAULT 1,
            result_mode TEXT NOT NULL DEFAULT 'single',
            result_index INTEGER NOT NULL DEFAULT 0,
            allow_fetch_all INTEGER NOT NULL DEFAULT 1,
            static_cache INTEGER NOT NULL DEFAULT 1,
            json_template TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE);
    """)

    pw_hash = auth.hash_password("admin123")
    conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                 ("admin", pw_hash))
    conn.execute("INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
                 "VALUES (?,?,?,?,?,?,?)",
                 ("测试池", "127.0.0.1", 3306, "root", "pass", "testdb", 1))
    conn.execute("INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,"
                 "result_names,prefer_cache,cache_ttl_hours,sort_order) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 ("测试报表", "SELECT id, name, age, status FROM users", 20, 1,
                  "", 1, 0, 1))
    conn.commit()
    report_id = conn.execute(
        "SELECT id FROM report_configs WHERE name='测试报表'"
    ).fetchone()[0]
    conn.close()
    return report_id


_TEST_REPORT_ID = _set_up_db()


def _start_server():
    """在后台线程启动 HTTP 服务器"""
    _stop_server()
    srv.PORT = TEST_PORT
    try:
        server = http.server.ThreadingHTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
        srv._server_ref = server
        server.serve_forever()
    except Exception:
        import traceback
        traceback.print_exc()


def _stop_server():
    """停止服务器"""
    if hasattr(srv, "_server_ref"):
        try:
            srv._server_ref.shutdown()
        except Exception:
            pass


class TestApiEndpointIntegration(MockMySQLMixin, unittest.TestCase):
    """API 端点集成测试"""

    @classmethod
    def setUpClass(cls):
        # Mock MySQL connection factory
        cls._mysql_patcher = unittest.mock.patch("db.create_mysql_connection")
        cls._mock_mysql_factory = cls._mysql_patcher.start()
        cls._mock_conn = None

        cls._thread = threading.Thread(target=_start_server, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        _stop_server()
        cls._mysql_patcher.stop()
        if os.path.exists(_tmp_db.name):
            os.remove(_tmp_db.name)
        if os.path.exists(_test_config_path):
            os.remove(_test_config_path)

    def setUp(self):
        """每个测试前清空 api_endpoints 表，确保独立。"""
        conn = _get_conn()
        conn.execute("DELETE FROM api_endpoints")
        conn.commit()
        conn.close()
        self._reset_mysql_mock()

    def _reset_mysql_mock(self):
        """重建 mock MySQL 连接（每次调用返回新 mock）并返回 (mock_conn, mock_cursor)。

        供 setUp 与 refresh 计数断言测试共用。
        """
        mock_conn, mock_cursor = self.make_mock_connection()
        mock_cursor.description = [("id",), ("name",), ("age",), ("status",)]
        mock_cursor.fetchall.return_value = [
            (1, "张三", 25, "active"),
            (2, "李四", 30, "inactive"),
            (3, "王五", 35, "active"),
        ]
        type(self)._mock_mysql_factory.side_effect = None
        type(self)._mock_mysql_factory.return_value = mock_conn
        return mock_conn, mock_cursor

    def _login_and_get_cookie(self):
        """登录并返回 cookie jar + opener"""
        from http.cookiejar import CookieJar
        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        data = urllib.parse.urlencode(
            {"username": "admin", "password": "admin123"}
        ).encode()
        req = urllib.request.Request(f"{BASE_URL}/login", data=data, method="POST")
        opener.open(req)
        return cj, opener

    def _create_endpoint_in_db(self, **kwargs):
        """在数据库中创建测试端点"""
        conn = _get_conn()
        defaults = dict(
            report_id=_TEST_REPORT_ID, name="测试端点",
            url_path="/api/test-ep",
        )
        defaults.update(kwargs)
        eid = db.add_api_endpoint(conn, **defaults)
        conn.close()
        return eid

    # =====================================================================
    # CRUD 测试
    # =====================================================================

    def test_crud_create_endpoint(self):
        """创建 API 端点"""
        conn = _get_conn()
        eid = db.add_api_endpoint(
            conn, _TEST_REPORT_ID, "测试接口",
            "/api/test-crud", output_format="json",
            filters='[{"col":"status","op":"eq","val":"active"}]',
            sorts='[{"col":"name","dir":"asc"}]',
            row_limit=100, api_key="test-key-123",
        )
        conn.close()
        conn2 = _get_conn()
        ep = db.get_api_endpoint(conn2, eid)
        conn2.close()
        self.assertEqual(ep["name"], "测试接口")
        self.assertEqual(ep["url_path"], "/api/test-crud")
        self.assertEqual(ep["api_key"], "test-key-123")

    def test_crud_get_by_path(self):
        """按路径查询 API 端点"""
        conn = _get_conn()
        db.add_api_endpoint(conn, _TEST_REPORT_ID, "路径测试", "/api/crud-path")
        conn.close()
        conn2 = _get_conn()
        ep = db.get_api_endpoint_by_path(conn2, "/api/crud-path")
        conn2.close()
        self.assertIsNotNone(ep)

    def test_crud_get_by_path_disabled(self):
        """禁用的端点不应被按路径查询到"""
        conn = _get_conn()
        db.add_api_endpoint(conn, _TEST_REPORT_ID, "禁用接口",
                             "/api/disabled-crud", enabled=0)
        conn.close()
        conn2 = _get_conn()
        ep = db.get_api_endpoint_by_path(conn2, "/api/disabled-crud")
        conn2.close()
        self.assertIsNone(ep)

    def test_crud_update_endpoint(self):
        """更新 API 端点"""
        conn = _get_conn()
        eid = db.add_api_endpoint(conn, _TEST_REPORT_ID, "更新前", "/api/update-me")
        db.update_api_endpoint(conn, eid, name="更新后", row_limit=50)
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["name"], "更新后")
        self.assertEqual(ep["row_limit"], 50)

    def test_crud_delete_endpoint(self):
        """删除 API 端点"""
        conn = _get_conn()
        eid = db.add_api_endpoint(conn, _TEST_REPORT_ID, "删除", "/api/delete-me")
        db.delete_api_endpoint(conn, eid)
        self.assertIsNone(db.get_api_endpoint(conn, eid))
        conn.close()

    def test_crud_unique_path(self):
        """重复 URL 路径应触发唯一约束"""
        conn = _get_conn()
        db.add_api_endpoint(conn, _TEST_REPORT_ID, "原接口", "/api/unique-test")
        with self.assertRaises(Exception):
            db.add_api_endpoint(conn, _TEST_REPORT_ID, "重复接口", "/api/unique-test")
        conn.close()

    # =====================================================================
    # API Key 生成测试
    # =====================================================================

    def test_generate_api_key(self):
        """API Key 生成格式正确"""
        key = api_handler.generate_api_key()
        self.assertTrue(key.startswith("sk-"))
        self.assertGreater(len(key), 10)

    # =====================================================================
    # HTTP API 调用测试
    # =====================================================================

    def test_api_404_unknown_path(self):
        """访问不存在的 API 路径返回 404"""
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/does-not-exist")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_api_disabled_endpoint(self):
        """访问已禁用的接口返回 404"""
        self._create_endpoint_in_db(url_path="/api/disabled-http", enabled=0)
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/disabled-http")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_api_auth_required(self):
        """需要 API Key 的接口未提供密钥时返回 401"""
        self._create_endpoint_in_db(url_path="/api/auth-needed", api_key="secret-key")
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/auth-needed")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_api_auth_success_header(self):
        """提供正确 API Key（通过 Authorization 头）"""
        self._create_endpoint_in_db(url_path="/api/auth-success", api_key="valid-key")
        req = urllib.request.Request(f"{BASE_URL}/api/auth-success")
        req.add_header("Authorization", "Bearer valid-key")
        try:
            resp = urllib.request.urlopen(req)
            self.assertEqual(resp.status, 200)
        except urllib.error.HTTPError as e:
            self.fail(f"Unexpected HTTP error: {e.code}")

    def test_api_auth_query_param(self):
        """通过查询参数传递 API Key"""
        self._create_endpoint_in_db(url_path="/api/auth-qp", api_key="qp-key")
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/auth-qp?api_key=qp-key")
            self.assertEqual(resp.status, 200)
        except urllib.error.HTTPError as e:
            self.fail(f"Unexpected HTTP error: {e.code}")

    def test_api_no_auth_needed(self):
        """无 API Key 的接口直接访问"""
        self._create_endpoint_in_db(url_path="/api/no-auth")
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/no-auth")
            self.assertEqual(resp.status, 200)
        except urllib.error.HTTPError as e:
            self.fail(f"Unexpected HTTP error: {e.code}")

    def test_api_json_response_structure(self):
        """JSON 响应包含 data/total/page/page_size/total_pages"""
        self._create_endpoint_in_db(url_path="/api/json-struct")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/json-struct")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertIn("data", body)
        self.assertIn("total", body)
        self.assertIn("page", body)
        self.assertIn("page_size", body)
        self.assertIn("total_pages", body)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 20)

    def test_api_json_data_content(self):
        """JSON 返回的数据内容正确"""
        self._create_endpoint_in_db(url_path="/api/json-data",
                                     columns="id,name")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/json-data")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(body["data"]), 3)
        self.assertIn("id", body["data"][0])
        self.assertIn("name", body["data"][0])
        self.assertNotIn("age", body["data"][0])

    def test_api_response_excludes_description(self):
        """API 响应体不含接口说明（description 只用于页面展示）"""
        self._create_endpoint_in_db(url_path="/api/desc-isolated",
                                     description="这是接口说明\n第二行不应出现")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/desc-isolated")
        body = resp.read().decode("utf-8")
        self.assertNotIn("这是接口说明", body)
        self.assertNotIn("description", body)

    def test_api_json_error_response(self):
        """Accept: application/json 时错误返回 JSON"""
        req = urllib.request.Request(f"{BASE_URL}/api/nonexistent-json")
        req.add_header("Accept", "application/json")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            self.assertIn("error", body)
            self.assertIn("code", body)

    def test_api_cors_preflight(self):
        """OPTIONS 预检返回正确 CORS 头"""
        self._create_endpoint_in_db(url_path="/api/cors-test",
                                     allowed_origins="https://example.com")
        req = urllib.request.Request(f"{BASE_URL}/api/cors-test", method="OPTIONS")
        req.add_header("Origin", "https://example.com")
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code == 204:
                resp = e
            else:
                raise
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"),
                         "https://example.com")

    def test_api_cors_wildcard(self):
        """allowed_origins 包含 * 时返回 *"""
        self._create_endpoint_in_db(url_path="/api/cors-star",
                                     allowed_origins="*")
        req = urllib.request.Request(f"{BASE_URL}/api/cors-star", method="OPTIONS")
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code == 204:
                resp = e
            else:
                raise
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_api_cors_no_config(self):
        """allowed_origins 为空时不设 CORS 头"""
        self._create_endpoint_in_db(url_path="/api/cors-empty")
        req = urllib.request.Request(f"{BASE_URL}/api/cors-empty", method="OPTIONS")
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code == 204:
                resp = e
            else:
                raise
        self.assertEqual(resp.status, 204)
        self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))

    # =====================================================================
    # 配置页面 UI 测试
    # =====================================================================

    def test_config_report_edit_has_api_section(self):
        """报表编辑页面包含 API 接口区块"""
        self._create_endpoint_in_db(url_path="/api/section-test")
        _, opener = self._login_and_get_cookie()
        resp = opener.open(f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/edit")
        html = resp.read().decode("utf-8")
        self.assertIn("API 接口", html)
        self.assertIn("新增 API 接口", html)

    def test_config_api_endpoint_create_page(self):
        """API 端点新增页面可访问"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        )
        html = resp.read().decode("utf-8")
        self.assertIn("新增 API 接口", html)
        self.assertIn("URL 路径", html)

    def test_config_api_endpoint_edit_page(self):
        """API 端点编辑页面可访问"""
        eid = self._create_endpoint_in_db(url_path="/api/edit-page-test")
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit"
        )
        html = resp.read().decode("utf-8")
        self.assertIn("编辑 API 接口", html)

    def test_config_api_endpoint_unique_path_error(self):
        """重复 URL 路径创建时显示错误"""
        self._create_endpoint_in_db(url_path="/api/duplicate-path-ui")
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode({
            "name": "重复路径",
            "url_path": "/api/duplicate-path-ui",
            "output_format": "json",
        }).encode()
        resp = opener.open(
            urllib.request.Request(
                f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
                data=form_data, method="POST",
            )
        )
        html = resp.read().decode("utf-8")
        self.assertIn("已存在", html)


    def test_config_api_endpoint_edit_clear_fields(self):
        """编辑 API 端点: 清空字段后应正确保存为空"""
        eid = self._create_endpoint_in_db(
            url_path="/api/clear-test",
            api_key="old-key",
            allowed_origins="https://old.example.com",
        )
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode({
            "name": "清空测试",
            "url_path": "clear-test",
            "output_format": "json",
            "row_limit": "0",
            "api_key": "",
            "allowed_origins": "",
            "rule_json": "",
            "enabled": "1",
            "action": "save_close",
        }).encode()
        resp = opener.open(
            urllib.request.Request(
                f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
                data=form_data, method="POST",
            )
        )
        # 跟随重定向
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertIsNotNone(ep)
        self.assertIsNone(ep["api_key"], "清空 api_key 后应存储为 None")
        self.assertIsNone(ep["allowed_origins"], "清空 allowed_origins 后应存储为 None")


    # =====================================================================
    # 中文/特殊符号 URL 路径测试
    # =====================================================================

    def test_api_chinese_path_encoded(self):
        """API 路径含中文（百分号编码）时应正确匹配"""
        import http.client
        self._create_endpoint_in_db(url_path="/api/中文", name="中文接口测试")
        hc = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=5)
        try:
            hc.request("GET", "/api/%E4%B8%AD%E6%96%87")
            resp = hc.getresponse()
            self.assertEqual(resp.status, 200,
                             "中文路径应匹配到 DB 中的 /api/ 中文")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body["page"], 1)
        finally:
            hc.close()

    def test_api_special_char_path_encoded(self):
        """API 路径含特殊字符（百分号编码）时应正确匹配"""
        import http.client
        self._create_endpoint_in_db(url_path="/api/特殊-path", name="特殊路径")
        hc = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=5)
        try:
            hc.request("GET", "/api/%E7%89%B9%E6%AE%8A-path")
            resp = hc.getresponse()
            self.assertEqual(resp.status, 200,
                             "特殊字符路径应匹配到 DB 中的 /api/ 特殊-path")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertIn("data", body)
        finally:
            hc.close()

    # =====================================================================
    # fetch_all 全量获取测试
    # =====================================================================

    def test_api_endpoint_default_allow_fetch_all(self):
        """新建端点 allow_fetch_all 默认开启"""
        conn = _get_conn()
        eid = db.add_api_endpoint(conn, _TEST_REPORT_ID, "默认全量", "/api/default-full")
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["allow_fetch_all"], 1)

    def test_api_endpoint_migration_allow_fetch_all_default_on(self):
        """存量库迁移后 allow_fetch_all 列存在且存量端点默认开启"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_USERS)
        conn.execute(tb._SQL_CREATE_REPORT_CATEGORIES)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_SESSIONS)
        old_schema = tb._SQL_CREATE_API_ENDPOINTS.replace(
            "    allow_fetch_all  INTEGER NOT NULL DEFAULT 1,\n", "")
        conn.execute(old_schema)
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '存量端点', '/api/legacy')")
        conn.commit()
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("allow_fetch_all", cols)
        val = conn.execute("SELECT allow_fetch_all FROM api_endpoints").fetchone()[0]
        self.assertEqual(val, 1, "存量端点迁移后默认开启")
        conn.close()

    def test_api_fetch_all_get_true(self):
        """GET ?fetch_all=true 返回全部行 + full 标记"""
        self._create_endpoint_in_db(url_path="/api/full-get")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-get?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 3)
        self.assertEqual(body["total_pages"], 1)
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["data"]), 3)

    def test_api_fetch_all_get_case_insensitive(self):
        """值大小写不敏感：TRUE/Yes/1 均合法"""
        self._create_endpoint_in_db(url_path="/api/full-case")
        for val in ("TRUE", "Yes", "1"):
            resp = urllib.request.urlopen(f"{BASE_URL}/api/full-case?fetch_all={val}")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body["full"], f"fetch_all={val} 应生效")

    def test_api_fetch_all_post_json(self):
        """POST JSON body fetch_all=true 返回全量"""
        self._create_endpoint_in_db(url_path="/api/full-post-json")
        req = urllib.request.Request(
            f"{BASE_URL}/api/full-post-json",
            data=json.dumps({"fetch_all": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["data"]), 3)

    # =====================================================================
    # 筛选匹配表达式（通配符 + 多值，契约扩展）
    # =====================================================================

    def test_api_filter_wildcard_contains(self):
        """预设筛选 val 支持 * 通配（contains 张* → 张三）"""
        self._create_endpoint_in_db(
            url_path="/api/wildcard-ep",
            filters='[{"col":"name","op":"contains","val":"张*"}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/wildcard-ep")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["data"][0]["name"], "张三")

    def test_api_filter_multivalue_eq_in(self):
        """预设筛选 val 多值 eq = IN 语义（active,inactive → 全部）"""
        self._create_endpoint_in_db(
            url_path="/api/multivalue-ep",
            filters='[{"col":"status","op":"eq","val":"active,inactive"}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/multivalue-ep")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 3)

    def test_api_filter_multivalue_mixed_wildcard(self):
        """预设筛选多值与通配混合（张三,王* → 张三、王五）"""
        self._create_endpoint_in_db(
            url_path="/api/mixed-ep",
            filters='[{"col":"name","op":"contains","val":"张三,王*"}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/mixed-ep")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 2)
        names = sorted(row["name"] for row in body["data"])
        self.assertEqual(names, ["张三", "王五"])

    def test_api_filter_val_numeric_no_500(self):
        """回归：预设 val 为数字（JSON 未加引号）→ 不 500，按字符串处理"""
        self._create_endpoint_in_db(
            url_path="/api/num-val-ep",
            filters='[{"col":"name","op":"contains","val":100}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/num-val-ep")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 0)

    def test_api_post_override_filters_numeric_val_no_500(self):
        """回归：POST 覆盖 filters 的 val 为数字 → 不 500"""
        self._create_endpoint_in_db(url_path="/api/post-num-val")
        req = urllib.request.Request(
            f"{BASE_URL}/api/post-num-val",
            data=json.dumps({"filters": [{"col": "name", "op": "contains",
                                          "val": 100}]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 0)

    def test_api_post_override_filters_wildcard(self):
        """POST 覆盖 filters 支持通配符（张* → 张三）"""
        self._create_endpoint_in_db(url_path="/api/post-wildcard")
        req = urllib.request.Request(
            f"{BASE_URL}/api/post-wildcard",
            data=json.dumps({"filters": [{"col": "name", "op": "contains",
                                          "val": "张*"}]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["data"][0]["name"], "张三")

    def test_api_fetch_all_post_form(self):
        """POST form-urlencoded fetch_all=1 返回全量"""
        self._create_endpoint_in_db(url_path="/api/full-post-form")
        data = urllib.parse.urlencode({"fetch_all": "1"}).encode()
        resp = urllib.request.urlopen(urllib.request.Request(
            f"{BASE_URL}/api/full-post-form", data=data, method="POST"))
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["data"]), 3)

    def test_api_fetch_all_invalid_values_ignored(self):
        """非法值按翻页处理：无 full 标记，page_size 保持默认"""
        self._create_endpoint_in_db(url_path="/api/full-invalid")
        for qs in ("fetch_all=0", "fetch_all=abc", "fetch_all=false", "fetch_all="):
            resp = urllib.request.urlopen(f"{BASE_URL}/api/full-invalid?{qs}")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertNotIn("full", body, f"fetch_all={qs} 不应生效")
            self.assertEqual(body["page_size"], 20)

    def test_api_fetch_all_ignores_row_limit(self):
        """端点配置 row_limit 时 fetch_all 仍返回全量"""
        self._create_endpoint_in_db(url_path="/api/full-limit", row_limit=1)
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-limit?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["data"]), 3)

    def test_api_fetch_all_ignores_request_limit_and_page(self):
        """请求 limit/page/page_size 被 fetch_all 无视"""
        self._create_endpoint_in_db(url_path="/api/full-req-limit")
        resp = urllib.request.urlopen(
            f"{BASE_URL}/api/full-req-limit?fetch_all=true&limit=1&page=2&page_size=1")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["data"]), 3)

    def test_api_fetch_all_disabled_switch(self):
        """allow_fetch_all=0 时参数被忽略，按翻页处理"""
        self._create_endpoint_in_db(url_path="/api/full-disabled", allow_fetch_all=0)
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-disabled?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertNotIn("full", body)
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(len(body["data"]), 3)

    # =====================================================================
    # PH-01：API 强制刷新（refresh=1 绕过缓存直查 MySQL）
    # =====================================================================

    def _api_get(self, path):
        resp = urllib.request.urlopen(f"{BASE_URL}{path}")
        return json.loads(resp.read().decode("utf-8"))

    def test_api_refresh_force_reload(self):
        """refresh=1 命中缓存仍直查 MySQL；无 refresh 走缓存；非法值忽略"""
        report._query_cache.clear()
        self._create_endpoint_in_db(url_path="/api/refresh-ep")
        _, mock_cursor = self._reset_mysql_mock()

        self._api_get("/api/refresh-ep")
        first = mock_cursor.execute.call_count
        self.assertGreaterEqual(first, 1, "首次请求应直查 MySQL")

        self._api_get("/api/refresh-ep")
        self.assertEqual(mock_cursor.execute.call_count, first,
                         "无 refresh 应命中进程缓存，不直查")

        self._api_get("/api/refresh-ep?refresh=1")
        self.assertGreater(mock_cursor.execute.call_count, first,
                           "refresh=1 应绕过缓存直查 MySQL")
        refreshed = mock_cursor.execute.call_count

        self._api_get("/api/refresh-ep?refresh=abc")
        self.assertEqual(mock_cursor.execute.call_count, refreshed,
                         "refresh 非法值应忽略，走缓存")

        body = self._api_get("/api/refresh-ep?refresh=yes")
        self.assertEqual(body["total"], 3, "yes 别名应生效且返回数据")

    def test_api_refresh_with_fetch_all(self):
        """fetch_all 与 refresh 可叠加：强制刷新 + 全量输出"""
        report._query_cache.clear()
        self._create_endpoint_in_db(url_path="/api/refresh-full-ep")
        _, mock_cursor = self._reset_mysql_mock()

        self._api_get("/api/refresh-full-ep")
        first = mock_cursor.execute.call_count

        body = self._api_get("/api/refresh-full-ep?refresh=1&fetch_all=true")
        self.assertTrue(body["full"], "fetch_all 生效")
        self.assertEqual(len(body["data"]), 3)
        self.assertGreater(mock_cursor.execute.call_count, first,
                           "refresh=1 与 fetch_all 叠加时仍直查 MySQL")

    def test_api_fetch_all_csv(self):
        """CSV 格式 fetch_all 输出全量行"""
        self._create_endpoint_in_db(url_path="/api/full-csv")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-csv?format=csv&fetch_all=true")
        text = resp.read().decode("utf-8")
        self.assertEqual(len(text.strip().splitlines()), 4, "表头 + 3 行数据")

    def test_api_fetch_all_result_mode_all(self):
        """result_mode=all 时每个结果集全量 + 子对象 full 标记"""
        self._create_endpoint_in_db(url_path="/api/full-multi", result_mode="all")
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-multi?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["mode"], "all")
        self.assertTrue(body["full"])
        self.assertEqual(body["page_size"], 3, "顶层 page_size 应显示行数而非内部值")
        self.assertEqual(len(body["results"]), 1)
        self.assertTrue(body["results"][0]["full"])
        self.assertEqual(body["results"][0]["total"], 3)
        self.assertEqual(len(body["results"][0]["data"]), 3)

    def test_api_fetch_all_filters_still_applied(self):
        """fetch_all 全量时筛选仍生效"""
        self._create_endpoint_in_db(
            url_path="/api/full-filter",
            filters='[{"col":"status","op":"eq","val":"active"}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-filter?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["data"]), 2)

    def test_api_fetch_all_sorts_still_applied(self):
        """fetch_all 全量时排序仍生效"""
        self._create_endpoint_in_db(
            url_path="/api/full-sort",
            sorts='[{"col":"name","dir":"desc"}]')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/full-sort?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["data"]), 3)
        names = [row["name"] for row in body["data"]]
        self.assertEqual(names, ["王五", "李四", "张三"])

    # =====================================================================
    # JSON 输出模板测试
    # =====================================================================

    def test_api_template_single_mode(self):
        """单结果集模式：模板键名替换默认结构"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-single",
            json_template='{"rand99_count": {{total}}, "rand99_items": {{data}}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-single")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["rand99_count"], 3)
        self.assertEqual(len(body["rand99_items"]), 3)
        self.assertNotIn("total", body)
        self.assertNotIn("data", body)

    def test_api_template_csv_ignored(self):
        """CSV 输出忽略模板，仍输出表头 + 行"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-csv",
            json_template='{"rand99_count": {{total}}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-csv?format=csv")
        text = resp.read().decode("utf-8")
        self.assertEqual(len(text.strip().splitlines()), 4, "表头 + 3 行数据")

    def test_api_template_fetch_all(self):
        """fetch_all + 模板：{{full}} 输出 true"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-full",
            json_template='{"full": {{full}}, "rows": {{data}}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-full?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["rows"]), 3)

    def test_api_template_result_mode_all(self):
        """result_mode=all + 模板：{{results}}/{{mode}} 替换"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-all", result_mode="all",
            json_template='{"mode": {{mode}}, "sets": {{results}}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-all")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["mode"], "all")
        self.assertEqual(len(body["sets"]), 1)
        self.assertIn("name", body["sets"][0])

    def test_api_template_all_fetch_all_full(self):
        """result_mode=all + fetch_all + 模板：{{full}} true"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-all-full", result_mode="all",
            json_template='{"full": {{full}}, "sets": {{results}}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-all-full?fetch_all=true")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["full"])
        self.assertEqual(len(body["sets"]), 1)

    def test_api_template_render_failure_fallback(self):
        """模板语法非法导致渲染失败时回退默认结构（不 500）"""
        self._create_endpoint_in_db(
            url_path="/api/tpl-bad",
            json_template='{"bad": {{data}}')
        resp = urllib.request.urlopen(f"{BASE_URL}/api/tpl-bad")
        body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["data"]), 3)

    # =====================================================================
    # fetch_all 配置 UI 测试
    # =====================================================================

    def test_config_api_endpoint_form_has_fetch_all_ui(self):
        """API 端点表单含全量开关与 DEMO 文案"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        )
        html = resp.read().decode("utf-8")
        self.assertIn("允许全量获取", html)
        self.assertIn("fetch_all", html)
        self.assertIn("使用示例", html)
        self.assertIn("true / 1 / yes", html)

    def test_config_api_endpoint_form_has_fetch_all_url_row(self):
        """表单含全量 URL 展示行，输出带 fetch_all=true 的可复制地址"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        )
        html = resp.read().decode("utf-8")
        self.assertIn("全量 URL:", html)
        self.assertIn("fetch-all-url-text", html)
        self.assertIn("fetch_all=true", html)
        self.assertIn("copyToClipboard('fetch-all-url-text')", html)

    def test_config_api_endpoint_fetch_all_url_row_visibility(self):
        """全量 URL 行初始可见性由服务端决定：默认勾选时显示，关闭时隐藏；
        JS 联动选择器须精确匹配 checkbox（排除 hidden 同名字段）"""
        _, opener = self._login_and_get_cookie()
        html = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        ).read().decode("utf-8")
        self.assertRegex(
            html,
            r'id="fetch-all-url-row"[^>]*display:flex')
        self.assertIn(
            'input[type="checkbox"][name="allow_fetch_all"]', html)
        eid = self._create_endpoint_in_db(url_path="/api/ui-row-hidden", allow_fetch_all=0)
        html_off = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit"
        ).read().decode("utf-8")
        self.assertRegex(
            html_off,
            r'id="fetch-all-url-row"[^>]*display:none')

    def test_config_api_endpoint_url_input_syncs_all_urls(self):
        """URL 路径输入时完整/全量/静态 URL 联动刷新：
        updateFullUrl（oninput 绑定）须联动调用 updateFetchAllUrl 与 updateStaticUrl"""
        _, opener = self._login_and_get_cookie()
        html = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        ).read().decode("utf-8")
        self.assertIn('oninput="updateFullUrl()"', html)
        func_body = re.search(
            r"function updateFullUrl\(\) \{(.*?)\n  \}", html, re.S)
        self.assertIsNotNone(func_body)
        self.assertIn("updateFetchAllUrl();", func_body.group(1))
        self.assertIn("updateStaticUrl();", func_body.group(1))

    def test_config_api_endpoint_form_fetch_all_default_checked(self):
        """新增表单全量开关默认勾选"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new"
        )
        html = resp.read().decode("utf-8")
        self.assertRegex(html, r'name="allow_fetch_all" value="1"[^>]*checked')

    def test_config_api_endpoint_save_fetch_all_enabled(self):
        """表单提交勾选全量开关 → DB 保存为 1"""
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode([
            ("name", "全量开启"),
            ("url_path", "ui-full-on"),
            ("output_format", "json"),
            ("row_limit", "0"),
            ("api_key", ""),
            ("allowed_origins", ""),
            ("rule_json", ""),
            ("enabled", "1"),
            ("allow_fetch_all", "0"),
            ("allow_fetch_all", "1"),
            ("action", "save_close"),
        ]).encode()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-full-on")
        conn.close()
        self.assertIsNotNone(ep)
        self.assertEqual(ep["allow_fetch_all"], 1)

    def test_config_api_endpoint_save_fetch_all_disabled(self):
        """表单提交不勾选全量开关 → DB 保存为 0"""
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode({
            "name": "全量关闭",
            "url_path": "ui-full-off",
            "output_format": "json",
            "row_limit": "0",
            "api_key": "",
            "allowed_origins": "",
            "rule_json": "",
            "enabled": "1",
            "allow_fetch_all": "0",
            "action": "save_close",
        }).encode()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-full-off")
        conn.close()
        self.assertIsNotNone(ep)
        self.assertEqual(ep["allow_fetch_all"], 0)

    def test_config_api_endpoint_edit_fetch_all_echo(self):
        """编辑页面回显 allow_fetch_all=0 的开关为不勾选"""
        eid = self._create_endpoint_in_db(url_path="/api/ui-echo", allow_fetch_all=0)
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit"
        )
        html = resp.read().decode("utf-8")
        self.assertIn("允许全量获取", html)
        self.assertNotRegex(html, r'name="allow_fetch_all" value="1"[^>]*checked')

    def test_config_api_endpoint_list_shows_fetch_all(self):
        """API 列表展示全量状态列"""
        self._create_endpoint_in_db(url_path="/api/ui-list", allow_fetch_all=1)
        _, opener = self._login_and_get_cookie()
        resp = opener.open(f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/edit")
        html = resp.read().decode("utf-8")
        self.assertIn("全量", html)
        self.assertIn("允许", html)

    def test_config_api_endpoint_edit_saves_allow_fetch_all(self):
        """编辑保存 allow_fetch_all 开关落库（回归：曾丢失该字段不更新）。

        修复场景：edit 路径改 update_kwargs 后丢失 allow_fetch_all 参数，
        update_api_endpoint 仅更新传入字段 → 开关不再落库。
        """
        eid = self._create_endpoint_in_db(url_path="/api/ui-fetch-save", allow_fetch_all=1)
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode({
            "name": "全量开关编辑",
            "url_path": "ui-fetch-save",
            "output_format": "json",
            "row_limit": "0",
            "rule_json": "",
            "enabled": "1",
            "allow_fetch_all": "0",
            "action": "save_close",
        }).encode()
        resp = opener.open(
            urllib.request.Request(
                f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
                data=form_data, method="POST",
            )
        )
        resp.read()
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["allow_fetch_all"], 0, "编辑关闭全量开关应落库")
        # 反向：勾选恢复为 1
        _, opener2 = self._login_and_get_cookie()
        form_data2 = urllib.parse.urlencode({
            "name": "全量开关编辑",
            "url_path": "ui-fetch-save",
            "output_format": "json",
            "row_limit": "0",
            "rule_json": "",
            "enabled": "1",
            "allow_fetch_all": "1",
            "action": "save_close",
        }).encode()
        resp2 = opener2.open(
            urllib.request.Request(
                f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
                data=form_data2, method="POST",
            )
        )
        resp2.read()
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["allow_fetch_all"], 1, "编辑勾选全量开关应落库")

    # ------------------------------------------------------------------
    # 静态文件缓存（.json 变体）UI
    # ------------------------------------------------------------------

    def test_config_api_endpoint_save_static_cache_enabled(self):
        """表单勾选静态缓存开关 → DB 保存为 1"""
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode([
            ("name", "静态缓存开"),
            ("url_path", "ui-sc-on"),
            ("output_format", "json"),
            ("row_limit", "0"),
            ("api_key", ""),
            ("allowed_origins", ""),
            ("rule_json", ""),
            ("enabled", "1"),
            ("static_cache", "0"),
            ("static_cache", "1"),
            ("action", "save_close"),
        ]).encode()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-sc-on")
        conn.close()
        self.assertIsNotNone(ep)
        self.assertEqual(ep["static_cache"], 1)

    def test_config_api_endpoint_save_static_cache_disabled(self):
        """表单不勾选静态缓存开关 → DB 保存为 0"""
        _, opener = self._login_and_get_cookie()
        form_data = urllib.parse.urlencode({
            "name": "静态缓存关",
            "url_path": "ui-sc-off",
            "output_format": "json",
            "row_limit": "0",
            "api_key": "",
            "allowed_origins": "",
            "rule_json": "",
            "enabled": "1",
            "static_cache": "0",
            "action": "save_close",
        }).encode()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-sc-off")
        conn.close()
        self.assertIsNotNone(ep)
        self.assertEqual(ep["static_cache"], 0)

    def test_config_api_endpoint_edit_static_cache_echo(self):
        """编辑页回显 static_cache=0 为不勾选；表单含静态 URL 预览行与说明"""
        eid = self._create_endpoint_in_db(url_path="/api/ui-sc-echo", static_cache=0)
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit")
        html = resp.read().decode("utf-8")
        self.assertIn("静态文件缓存", html)
        self.assertIn("static-url-row", html)
        self.assertNotRegex(html, r'name="static_cache" value="1"[^>]*checked')

    def test_config_api_endpoint_list_shows_static_cache(self):
        """API 列表展示静态缓存状态列（开/关徽标）+ 全局状态提示"""
        self._create_endpoint_in_db(url_path="/api/ui-sc-list", static_cache=1)
        self._create_endpoint_in_db(url_path="/api/ui-sc-off", static_cache=0)
        _, opener = self._login_and_get_cookie()
        resp = opener.open(f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/edit")
        html = resp.read().decode("utf-8")
        self.assertIn("静态缓存", html)
        self.assertIn("静态文件缓存: 全局", html)
        self.assertIn(">开<", html)
        self.assertIn(">关<", html)

    # ------------------------------------------------------------------
    # JSON 输出模板 UI
    # ------------------------------------------------------------------

    def test_config_api_endpoint_form_has_template_ui(self):
        """新增表单含模板 textarea、占位符清单、默认对照、还原按钮、预览区"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new")
        html = resp.read().decode("utf-8")
        for probe in ("JSON 输出模板", 'name="json_template"', "可用占位符",
                      "默认 JSON 起点", "还原为默认 JSON 格式", "实时预览"):
            self.assertIn(probe, html)
        self.assertIn("{{data}}", html)
        self.assertIn("{{results}}", html)
        self.assertIn("renderTemplatePreview", html)
        self.assertIn("TPL_KEYS", html)

    def test_config_api_endpoint_template_echo(self):
        """编辑页面回显 json_template"""
        eid = self._create_endpoint_in_db(
            url_path="/api/tpl-echo", json_template='{"a": {{data}}}')
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit")
        html = resp.read().decode("utf-8")
        self.assertIn('{"a": {{data}}}', html.replace('&quot;', '"'),
                      "模板内容应回显")

    def test_config_api_endpoint_save_template_success(self):
        """保存合法模板 → 落库"""
        form_data = urllib.parse.urlencode([
            ("name", "模板保存"), ("url_path", "ui-tpl-save"),
            ("output_format", "json"), ("row_limit", "0"),
            ("api_key", ""), ("allowed_origins", ""), ("rule_json", ""),
            ("enabled", "1"), ("result_mode", "single"), ("result_index", "0"),
            ("json_template", '{"rand99": {{total}}}'),
            ("action", "save_close"),
        ]).encode()
        _, opener = self._login_and_get_cookie()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-tpl-save")
        conn.close()
        self.assertIsNotNone(ep)
        self.assertEqual(ep["json_template"], '{"rand99": {{total}}}')

    def test_config_api_endpoint_save_template_invalid_rejected(self):
        """保存非法模板 → 拒绝 + 回显 + 行列错误 + 不落库"""
        form_data = urllib.parse.urlencode([
            ("name", "坏模板保存"), ("url_path", "ui-tpl-bad"),
            ("output_format", "json"), ("row_limit", "0"),
            ("api_key", ""), ("allowed_origins", ""), ("rule_json", ""),
            ("enabled", "1"), ("result_mode", "single"), ("result_index", "0"),
            ("json_template", '{"a": {{unknown_key}}}'),
            ("action", "save_close"),
        ]).encode()
        _, opener = self._login_and_get_cookie()
        resp = opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new",
            data=form_data, method="POST"))
        html = resp.read().decode("utf-8")
        self.assertIn("JSON 输出模板无效", html)
        self.assertIn("未知占位符 {{unknown_key}} 位于第 1 行第 7 列", html)
        self.assertIn("坏模板保存", html, "表单应回显原输入")
        self.assertIn('{"a": {{unknown_key}}}', html.replace('&quot;', '"'),
                      "模板应回显原输入")
        conn = _get_conn()
        ep = db.get_api_endpoint_by_path(conn, "/api/ui-tpl-bad")
        conn.close()
        self.assertIsNone(ep, "非法模板不应落库")

    def test_config_api_endpoint_edit_template_invalid_rejected(self):
        """编辑保存非法模板 → 拒绝 + 回显原输入 + 库内原值不变"""
        eid = self._create_endpoint_in_db(
            url_path="/api/tpl-edit-bad", json_template='{"ok": {{data}}}')
        form_data = urllib.parse.urlencode([
            ("name", "改模板名"), ("url_path", "tpl-edit-bad"),
            ("output_format", "json"), ("row_limit", "0"),
            ("api_key", ""), ("allowed_origins", ""), ("rule_json", ""),
            ("enabled", "1"), ("result_mode", "single"), ("result_index", "0"),
            ("json_template", '{"x": {{nope}}}'),
            ("action", "save_close"),
        ]).encode()
        _, opener = self._login_and_get_cookie()
        resp = opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
            data=form_data, method="POST"))
        html = resp.read().decode("utf-8")
        self.assertIn("JSON 输出模板无效", html)
        self.assertIn("改模板名", html, "表单应回显原输入")
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["json_template"], '{"ok": {{data}}}',
                         "非法编辑不应改动库内原值")

    def test_config_api_endpoint_save_template_clear(self):
        """编辑表单清空模板 → 库内清空（NULL）"""
        eid = self._create_endpoint_in_db(
            url_path="/api/tpl-clear", json_template='{"ok": {{data}}}')
        form_data = urllib.parse.urlencode([
            ("name", "清模板"), ("url_path", "tpl-clear"),
            ("output_format", "json"), ("row_limit", "0"),
            ("api_key", ""), ("allowed_origins", ""), ("rule_json", ""),
            ("enabled", "1"), ("result_mode", "single"), ("result_index", "0"),
            ("json_template", ""),
            ("action", "save_close"),
        ]).encode()
        _, opener = self._login_and_get_cookie()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertIsNone(ep["json_template"])

    def test_config_api_endpoint_template_js_parts(self):
        """模板区 JS 关键件存在：CSV 禁用、模式联动、预览替换"""
        _, opener = self._login_and_get_cookie()
        resp = opener.open(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/new")
        html = resp.read().decode("utf-8")
        self.assertIn("ta.disabled = isCsv", html, "CSV 禁用模板输入")
        self.assertIn("template-csv-hint", html)
        self.assertIn("radios[i].addEventListener('change', updateTemplateMode)",
                      html, "result_mode 切换联动")
        self.assertIn("tpl-default-single", html)
        self.assertIn("tpl-default-all", html)
        self.assertIn("resetTemplateToDefault", html, "还原按钮 JS")
        self.assertIn("JSON.parse(replaced)", html, "预览校验 JS")
        self.assertIn("TPL_DEFAULTS = {", html, "默认模板文本 JS 常量")
        self.assertIn("single: '{\\n", html)
        self.assertIn("ta.value = TPL_DEFAULTS[currentTemplateMode()]", html,
                      "还原按钮函数体应填入默认模板文本")
        self.assertIn("renderTemplatePreview()", html,
                      "还原后应即时刷新预览")

    def test_config_api_endpoint_csv_preserves_template(self):
        """CSV 模式保存：忽略模板字段，不覆盖（保留原模板，切回 JSON 仍可用）"""
        eid = self._create_endpoint_in_db(
            url_path="/api/tpl-csv-keep", json_template='{"a": {{data}}}')
        form_data = urllib.parse.urlencode([
            ("name", "切CSV"), ("url_path", "tpl-csv-keep"),
            ("output_format", "csv"), ("row_limit", "0"),
            ("api_key", ""), ("allowed_origins", ""), ("rule_json", ""),
            ("enabled", "1"), ("result_mode", "single"), ("result_index", "0"),
            ("action", "save_close"),
        ]).encode()
        _, opener = self._login_and_get_cookie()
        opener.open(urllib.request.Request(
            f"{BASE_URL}/config/reports/{_TEST_REPORT_ID}/api_endpoints/{eid}/edit",
            data=form_data, method="POST"))
        conn = _get_conn()
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["output_format"], "csv")
        self.assertEqual(ep["json_template"], '{"a": {{data}}}',
                         "CSV 模式保存不应清空已存模板")

    # =====================================================================
    # 客户端断开连接（ConnectionResetError）回归测试
    # =====================================================================

    def test_api_write_connection_reset_swallowed(self):
        """客户端在响应写出中断开连接：写异常被吞掉，不冒泡、不发 500"""
        self._create_endpoint_in_db(url_path="/api/reset-test")
        conn = _get_conn()
        handler = unittest.mock.Mock()
        handler.headers = {}
        handler.client_address = ("127.0.0.1", 12345)
        handler.wfile = unittest.mock.Mock()
        handler.wfile.write.side_effect = ConnectionResetError("Connection reset by peer")
        # 不抛异常即通过（修复前 ConnectionResetError 会冒泡到 _handle 并二次写失败）
        srv.ReportHandler._handle_api(
            handler, "GET", "/api/reset-test", "", conn)
        self.assertTrue(handler.wfile.write.called)
        conn.close()

    def test_api_write_broken_pipe_swallowed(self):
        """客户端断开后继续写响应：BrokenPipeError 同样被吞掉"""
        self._create_endpoint_in_db(url_path="/api/broken-pipe-test")
        conn = _get_conn()
        handler = unittest.mock.Mock()
        handler.headers = {}
        handler.client_address = ("127.0.0.1", 12345)
        handler.wfile = unittest.mock.Mock()
        handler.wfile.write.side_effect = BrokenPipeError("Broken pipe")
        srv.ReportHandler._handle_api(
            handler, "GET", "/api/broken-pipe-test", "", conn)
        conn.close()


# =====================================================================
# json_template 列（迁移 12）测试
# =====================================================================

class TestJsonTemplateColumn(unittest.TestCase):
    """api_endpoints.json_template 列：迁移、CRUD 读写与审计。

    注意：不使用模块级共享临时库（TestApiEndpointIntegration.tearDownClass
    会删除该文件，影响其后执行的类），每个测试自建独立内存库。
    """

    def _make_conn(self):
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_USERS)
        conn.execute(tb._SQL_CREATE_REPORT_CATEGORIES)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_SESSIONS)
        conn.execute(tb._SQL_CREATE_API_ENDPOINTS)
        conn.execute("INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
                     ("测试报表", "SELECT 1"))
        conn.commit()
        return conn

    def test_new_schema_has_json_template_column(self):
        """新库建表后 json_template 列存在"""
        conn = self._make_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        conn.close()
        self.assertIn("json_template", cols)

    def test_migration_adds_column_and_keeps_data(self):
        """存量库（无 json_template 列）迁移后列存在、存量数据完好且为 NULL"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_USERS)
        conn.execute(tb._SQL_CREATE_REPORT_CATEGORIES)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_SESSIONS)
        old_schema = tb._SQL_CREATE_API_ENDPOINTS.replace(
            "    static_cache    INTEGER NOT NULL DEFAULT 1,\n", "")
        conn.execute(old_schema)
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '存量端点', '/api/legacy-tpl')")
        conn.commit()
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("json_template", cols)
        row = conn.execute(
            "SELECT name, url_path, json_template FROM api_endpoints").fetchone()
        self.assertEqual(row[0], "存量端点")
        self.assertEqual(row[1], "/api/legacy-tpl")
        self.assertIsNone(row[2], "存量端点迁移后 json_template 为 NULL")
        conn.close()

    def test_add_with_template_roundtrip(self):
        """新增端点写入 json_template 可回读"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "模板端点", "/api/tpl-write",
            json_template='{"rand99": {{data}}}')
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["json_template"], '{"rand99": {{data}}}')

    def test_add_default_null(self):
        """不传 json_template 默认 NULL"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(conn, 1, "无模板", "/api/tpl-null")
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertIsNone(ep["json_template"])

    def test_update_template_roundtrip(self):
        """更新 json_template 生效；不传保持原值；显式空串可清除"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "更新模板", "/api/tpl-update",
            json_template='{"a": {{data}}}')
        db.update_api_endpoint(conn, eid, json_template='{"b": {{total}}}')
        ep = db.get_api_endpoint(conn, eid)
        self.assertEqual(ep["json_template"], '{"b": {{total}}}')
        db.update_api_endpoint(conn, eid, name="改名")
        ep = db.get_api_endpoint(conn, eid)
        self.assertEqual(ep["json_template"], '{"b": {{total}}}',
                         "不传模板应保持原值")
        db.update_api_endpoint(conn, eid, json_template="")
        ep = db.get_api_endpoint(conn, eid)
        self.assertEqual(ep["json_template"], "", "显式传空串可清除模板")
        conn.close()

    def test_update_static_cache_roundtrip(self):
        """更新 static_cache 生效（既有参数曾为死参数，本测试固化修复）"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "缓存开关", "/api/tpl-sc", static_cache=1)
        db.update_api_endpoint(conn, eid, static_cache=0)
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["static_cache"], 0)

    @unittest.mock.patch("config_db._write_audit_log")
    def test_update_audit_log_records_template_change(self, mock_audit):
        """更新端点时审计日志记录 json_template 变更（before/after 双快照）"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "审计端点", "/api/audit-tpl",
            json_template='{"a": {{data}}}')
        mock_audit.reset_mock()
        db.update_api_endpoint(conn, eid, json_template='{"b": {{total}}}',
                               session_user="admin")
        args, kwargs = mock_audit.call_args
        self.assertEqual(args[1], "update_api_endpoint")
        self.assertEqual(kwargs["before_value"]["json_template"],
                         '{"a": {{data}}}')
        self.assertEqual(kwargs["after_value"]["json_template"],
                         '{"b": {{total}}}')
        conn.close()


class TestDescriptionColumn(unittest.TestCase):
    """api_endpoints.description 列：迁移、CRUD 读写与缓存失效联动。

    注意：每个测试自建独立内存库（description 为纯展示字段）。
    """

    def _make_conn(self):
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_USERS)
        conn.execute(tb._SQL_CREATE_REPORT_CATEGORIES)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_SESSIONS)
        conn.execute(tb._SQL_CREATE_API_ENDPOINTS)
        conn.execute("INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
                     ("测试报表", "SELECT 1"))
        conn.commit()
        return conn

    def test_new_schema_has_description_column(self):
        """新库建表后 description 列存在"""
        conn = self._make_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        conn.close()
        self.assertIn("description", cols)

    def test_migration_adds_column_and_keeps_data(self):
        """存量库（无 description 列）迁移后列存在、存量数据完好且为 NULL"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_USERS)
        conn.execute(tb._SQL_CREATE_REPORT_CATEGORIES)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_SESSIONS)
        old_schema = tb._SQL_CREATE_API_ENDPOINTS.replace(
            "    json_template   TEXT,\n", "")
        conn.execute(old_schema)
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '存量端点', '/api/legacy-desc')")
        conn.commit()
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("description", cols)
        row = conn.execute(
            "SELECT name, url_path, description FROM api_endpoints").fetchone()
        self.assertEqual(row[0], "存量端点")
        self.assertEqual(row[1], "/api/legacy-desc")
        self.assertIsNone(row[2], "存量端点迁移后 description 为 NULL")
        conn.close()

    def test_add_description_roundtrip(self):
        """新增端点写入多行 description 可回读"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "说明端点", "/api/desc-write",
            description="第一行用途说明\n第二行注意事项")
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertEqual(ep["description"], "第一行用途说明\n第二行注意事项")

    def test_add_description_default_null(self):
        """不传 description 默认 NULL"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(conn, 1, "无说明", "/api/desc-null")
        ep = db.get_api_endpoint(conn, eid)
        conn.close()
        self.assertIsNone(ep["description"])

    def test_update_description_roundtrip(self):
        """更新 description 生效；不传保持原值；显式 None 可清除"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "更新说明", "/api/desc-update", description="旧说明")
        db.update_api_endpoint(conn, eid, description="新说明\n第二行")
        self.assertEqual(db.get_api_endpoint(conn, eid)["description"],
                         "新说明\n第二行")
        db.update_api_endpoint(conn, eid, name="改名")
        self.assertEqual(db.get_api_endpoint(conn, eid)["description"],
                         "新说明\n第二行")
        db.update_api_endpoint(conn, eid, description=None)
        self.assertIsNone(db.get_api_endpoint(conn, eid)["description"])
        conn.close()

    @unittest.mock.patch("config_db.static_cache.invalidate")
    def test_update_description_only_does_not_invalidate(self, mock_invalidate):
        """仅更新 description 不触发静态缓存失效（纯元数据字段）"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(
            conn, 1, "说明端点", "/api/desc-cache", description="旧说明")
        db.update_api_endpoint(conn, eid, description="新说明")
        mock_invalidate.assert_not_called()
        conn.close()

    def test_update_output_field_still_invalidates(self):
        """更新输出相关字段仍触发失效（回归保护：只跳过纯元数据字段）"""
        conn = self._make_conn()
        eid = db.add_api_endpoint(conn, 1, "说明端点", "/api/desc-cache2")
        with unittest.mock.patch("config_db.static_cache.invalidate") as mock_invalidate:
            db.update_api_endpoint(conn, eid, row_limit=10)
        mock_invalidate.assert_called_once()
        conn.close()


if __name__ == "__main__":
    unittest.main()
