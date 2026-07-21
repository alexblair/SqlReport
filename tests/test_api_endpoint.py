"""
test_api_endpoint.py — API 端点功能集成测试

测试策略：
- 使用临时 SQLite 文件作为共享数据库（CONFIG_DB 环境变量）
- Mock db.create_mysql_connection 避免真实 MySQL 依赖
- CRUD 测试直接调用 config_db 函数
- HTTP 测试通过 urllib.request 发送真实 HTTP 请求
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
        server = http.server.HTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
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

        # 设置 mock MySQL 连接返回值（使用 side_effect 确保每次调用都返回新 mock）
        mock_conn, mock_cursor = self.make_mock_connection()
        mock_cursor.description = [("id",), ("name",), ("age",), ("status",)]
        mock_cursor.fetchall.return_value = [
            (1, "张三", 25, "active"),
            (2, "李四", 30, "inactive"),
            (3, "王五", 35, "active"),
        ]
        type(self)._mock_mysql_factory.side_effect = None
        type(self)._mock_mysql_factory.return_value = mock_conn

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


if __name__ == "__main__":
    unittest.main()
