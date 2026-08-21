"""
test_api_extra.py — API 域补充测试（T4 批次：鉴权切换/CORS/参数覆盖/错误路径/静态缓存版本）

测试策略：
- 临时 SQLite 文件 + patch("app_config.get_config") 注入，不污染同进程其他测试
- Mock db.create_mysql_connection 避免真实 MySQL 依赖
- 以 api_handler.handle_api_request 为最高测试 seam（端到端行为断言）
- 建表 DDL 不带外键约束（便于构造报表/连接池缺失场景）
"""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

import app_config
import api_handler
import audit_db
import config_db
import db
import report as report_mod
import server as srv
import static_cache
from tests.test_mysql_mock import MockMySQLMixin

# ---------------------------------------------------------------------------
# 临时测试环境
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_api_extra_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")
_CACHE_DIR = os.path.join(_TMP_ROOT, "cache")


def _test_config() -> dict:
    """返回测试用 app_config 内容（static_cache.dir 指向临时目录）。"""
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "static_cache": {"enable": True, "dir": _CACHE_DIR},
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    """获取指向共享临时文件的配置数据库连接。"""
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _set_up_db():
    """创建测试数据库表结构（无外键约束，便于构造缺失场景）。"""
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
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, max_rows INTEGER NOT NULL DEFAULT 100000,
            keepalive_enabled INTEGER NOT NULL DEFAULT 0,
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
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
            json_no_quotes  INTEGER NOT NULL DEFAULT 0,
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
            json_template TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id INTEGER NOT NULL,
            name TEXT NOT NULL, api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE);
    """)
    conn.execute("INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
                 "VALUES (?,?,?,?,?,?,?)",
                 ("测试池", "127.0.0.1", 3306, "root", "pass", "testdb", 1))
    conn.commit()
    conn.close()


_set_up_db()


class TestApiExtra(MockMySQLMixin, unittest.TestCase):
    """API 域补充测试（handle_api_request 为 seam）。"""

    @classmethod
    def setUpClass(cls):
        cls._mysql_patcher = patch("db.create_mysql_connection")
        cls._mock_factory = cls._mysql_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._mysql_patcher.stop()
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

    def setUp(self):
        """每个测试前注入配置、清空业务表、缓存目录、进程内缓存与失效记录。"""
        self._cfg_patcher = patch("app_config.get_config", return_value=_test_config())
        self._cfg_patcher.start()
        conn = _get_conn()
        conn.execute("DELETE FROM api_endpoints")
        conn.execute("DELETE FROM report_configs")
        conn.commit()
        conn.close()
        if os.path.isdir(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
        static_cache._last_invalidated.clear()
        report_mod._query_cache.clear()

        # 设置 mock MySQL 连接返回值
        mock_conn, mock_cursor = self.make_mock_connection()
        mock_cursor.description = [("id",), ("name",), ("age",), ("status",)]
        mock_cursor.fetchall.return_value = [
            (1, "张三", 25, "active"),
            (2, "李四", 30, "inactive"),
            (3, "王五", 35, "active"),
        ]
        type(self)._mock_factory.side_effect = None
        type(self)._mock_factory.return_value = mock_conn
        self.mock_cursor = mock_cursor

    def tearDown(self):
        """停止配置 patcher。"""
        self._cfg_patcher.stop()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _create_report(self, sql="SELECT id, name, age, status FROM users",
                       ttl_hours=0, name="测试报表", pool_id=1):
        """创建测试报表（prefer_cache=0 避免测试环境 Redis 依赖）。"""
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs "
            "(name,sql_query,default_page_size,pool_id,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, sql, 20, pool_id, 0, ttl_hours, 1))
        conn.commit()
        rid = conn.execute(
            "SELECT id FROM report_configs WHERE name=?", (name,)).fetchone()[0]
        conn.close()
        return rid

    def _create_endpoint(self, report_id=None, url_path="/api/cust", **kwargs):
        """在数据库中创建测试端点（report_id 缺省取最新报表）。

        SQLite AUTOINCREMENT 序列不因 DELETE 重置，报表 id 跨测试增长，
        不能硬编码 report_id=1。
        """
        conn = _get_conn()
        if report_id is None:
            report_id = conn.execute(
                "SELECT id FROM report_configs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        eid = db.add_api_endpoint(conn, report_id, "测试端点", url_path, **kwargs)
        conn.close()
        return eid

    def _request(self, path, method="GET", query=None, headers=None, body=""):
        """直接调用 handle_api_request（最高测试 seam）。"""
        return api_handler.handle_api_request(
            _get_conn(), path, method, headers or {}, body, query or {},
            client_ip="127.0.0.1")

    # ------------------------------------------------------------------
    # 缺口 1：新 Key 旧 Key 失效切换
    # ------------------------------------------------------------------

    def test_api_key_update_invalidates_old_key(self):
        """API Key 更新后旧 Key 立即失效，新 Key 生效。"""
        self._create_report()
        self._create_endpoint(api_key="sk-old-key")
        status, body, _ = self._request(
            "/api/cust", query={"api_key": ["sk-old-key"]})
        self.assertEqual(status, 200)

        conn = _get_conn()
        eid = conn.execute("SELECT id FROM api_endpoints").fetchone()[0]
        config_db.update_api_endpoint(conn, eid, api_key="sk-new-key")
        conn.close()

        status, body, _ = self._request(
            "/api/cust", query={"api_key": ["sk-old-key"]})
        self.assertEqual(status, 401, "旧 Key 必须立即失效")
        self.assertIn("API Key", body)
        status, body, _ = self._request(
            "/api/cust", query={"api_key": ["sk-new-key"]})
        self.assertEqual(status, 200, "新 Key 应生效")

    # ------------------------------------------------------------------
    # 缺口 2：CSV + all 同时请求 → 400
    # ------------------------------------------------------------------

    def test_result_mode_all_with_csv_400(self):
        """result_mode=all 且输出 CSV → 400 CSV_NOT_SUPPORTED。"""
        self._create_report()
        self._create_endpoint(result_mode="all")
        status, body, headers = self._request(
            "/api/cust", query={"format": ["csv"]})
        self.assertEqual(status, 400)
        parsed = json.loads(body)
        self.assertEqual(parsed["code"], "CSV_NOT_SUPPORTED")
        self.assertIn("CSV", parsed["error"])

    # ------------------------------------------------------------------
    # 缺口 3/4：CORS 白名单
    # ------------------------------------------------------------------

    def test_cors_origin_not_in_whitelist_no_header(self):
        """非白名单来源：不返回 Access-Control-Allow-Origin 头。"""
        self._create_report()
        self._create_endpoint(allowed_origins="https://a.example.com, https://b.example.com")
        status, body, headers = self._request(
            "/api/cust", headers={"Origin": "https://evil.example.com"})
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_cors_multiple_allowed_origins(self):
        """多来源白名单：两个合法来源均返回对应 Allow-Origin。"""
        self._create_report()
        self._create_endpoint(allowed_origins="https://a.example.com, https://b.example.com")
        for origin in ("https://a.example.com", "https://b.example.com"):
            with self.subTest(origin=origin):
                status, body, headers = self._request(
                    "/api/cust", headers={"Origin": origin})
                self.assertEqual(status, 200)
                self.assertEqual(headers["Access-Control-Allow-Origin"], origin)

    # ------------------------------------------------------------------
    # 缺口 5：带 Key 的 OPTIONS 请求不鉴权直接 200
    # ------------------------------------------------------------------

    def test_options_with_api_key_skips_auth(self):
        """OPTIONS 预检请求跳过 API Key 鉴权，直接返回 204。"""
        self._create_report()
        self._create_endpoint(api_key="sk-secret",
                              allowed_origins="https://app.example.com")
        status, body, headers = self._request(
            "/api/cust", method="OPTIONS",
            headers={"Origin": "https://app.example.com"},
            query={"api_key": ["wrong-key"]})
        self.assertEqual(status, 204, "OPTIONS 不应执行鉴权")
        self.assertEqual(body, "")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.example.com")

    # ------------------------------------------------------------------
    # 缺口 6：fetch_all=2 非法枚举值回退
    # ------------------------------------------------------------------

    def test_fetch_all_invalid_value_falls_back(self):
        """fetch_all=2（非法枚举）回退翻页语义，无 full 标记。"""
        self._create_report()
        self._create_endpoint()
        status, body, _ = self._request("/api/cust", query={"fetch_all": ["2"]})
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertNotIn("full", parsed)
        self.assertEqual(parsed["page_size"], 20)
        self.assertEqual(parsed["total_pages"], 1)

    # ------------------------------------------------------------------
    # 缺口 7：GET 参数覆盖（URL 参数覆盖预设）
    # ------------------------------------------------------------------

    def test_get_url_params_override_preset(self):
        """URL 参数覆盖端点预设（row_limit=100 → limit=2 生效）。"""
        self._create_report()
        self._create_endpoint(row_limit=100)
        status, body, _ = self._request("/api/cust", query={"limit": ["2"]})
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(len(parsed["data"]), 2, "URL limit=2 应覆盖预设 100")
        self.assertEqual(parsed["total"], 3)

    def test_get_duplicate_param_first_value_wins(self):
        """URL 同名参数多次出现（parse_qs 列表）取第一个值。"""
        self._create_report()
        self._create_endpoint()
        status, body, _ = self._request(
            "/api/cust", query={"page": ["2", "3"]})
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["page"], 2, "同名参数应取第一个值")
        status, body, _ = self._request(
            "/api/cust", query={"limit": ["1", "9"]})
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(len(parsed["data"]), 1, "limit 应取第一个值 1")

    # ------------------------------------------------------------------
    # 缺口 8：POST 参数覆盖（表单与 JSON body 等价）
    # ------------------------------------------------------------------

    def test_post_form_and_json_overrides_equivalent(self):
        """表单与 JSON body 覆盖行为等价：format=csv 均输出 CSV。"""
        self._create_report()
        self._create_endpoint()
        form_body = "format=csv&limit=1"
        status, body, headers = self._request(
            "/api/cust", method="POST", body=form_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(len(body.strip().splitlines()), 2, "表头 + 1 行数据")

        json_body = json.dumps({"format": "csv", "limit": 1})
        status, body, headers = self._request(
            "/api/cust", method="POST", body=json_body,
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(len(body.strip().splitlines()), 2, "表头 + 1 行数据")

    def test_post_body_overrides_url_params(self):
        """POST 带 body 时 URL 参数被忽略（body 优先）。"""
        self._create_report()
        self._create_endpoint()
        status, body, headers = self._request(
            "/api/cust", method="POST",
            query={"format": ["csv"]},
            body=json.dumps({"format": "json"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8",
                         "POST body 应覆盖 URL 参数")

    # ------------------------------------------------------------------
    # 缺口 9：非法参数回退（缺必需参数时 400 语义）
    # ------------------------------------------------------------------

    def test_invalid_param_values_fallback_defaults(self):
        """非法数值参数回退默认值，不报 400。"""
        self._create_report()
        self._create_endpoint()
        status, body, _ = self._request(
            "/api/cust", query={"page": ["abc"], "limit": ["xyz"]})
        self.assertEqual(status, 200, "非法数值参数应回退默认而非 400")
        parsed = json.loads(body)
        self.assertEqual(parsed["page"], 1)
        self.assertEqual(parsed["page_size"], 20)

    def test_missing_params_use_presets(self):
        """请求缺参数时使用端点预设（API 参数均为可选，无缺参 400）。"""
        self._create_report()
        self._create_endpoint(row_limit=2)
        status, body, _ = self._request("/api/cust")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(len(parsed["data"]), 2, "缺参时应用端点预设 row_limit=2")

    # ------------------------------------------------------------------
    # 缺口 10：非法 POST JSON body（解析失败）
    # ------------------------------------------------------------------

    def test_invalid_post_json_body_400(self):
        """非法 JSON body → 400 INVALID_JSON（修复缺陷：不再静默回退预设）。

        空 body（无请求体）不视为解析失败，仍回退预设正常响应。
        """
        self._create_report()
        self._create_endpoint(row_limit=2)
        status, body, headers = self._request(
            "/api/cust", method="POST", body='{"format": "csv", ',
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400, "非法 JSON body 应 400 拒绝")
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("JSON 解析失败", body)

        status, body, headers = self._request(
            "/api/cust", method="POST", body='{"format": "csv", ',
            headers={"Content-Type": "application/json",
                     "Accept": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        parsed = json.loads(body)
        self.assertEqual(parsed["code"], "INVALID_JSON")

        status, body, headers = self._request(
            "/api/cust", method="POST", body="",
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200, "空 body 不视为解析失败，回退预设")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")

    # ------------------------------------------------------------------
    # 缺口 11：result_index 越界 → 400
    # ------------------------------------------------------------------

    def test_result_index_out_of_range_400(self):
        """result_index 越界 → 400（错误消息含越界说明）。

        无 Accept 头时错误响应为纯文本（无 code 字段），见缺口 16。
        """
        self._create_report()
        self._create_endpoint(result_index=5)
        status, body, _ = self._request("/api/cust")
        self.assertEqual(status, 400)
        self.assertIn("超出范围", body)
        self.assertIn("5", body)

    # ------------------------------------------------------------------
    # 缺口 12/13：关联报表/连接池不存在 → 500
    # ------------------------------------------------------------------

    def test_missing_report_500(self):
        """关联报表不存在 → 500（错误消息含「关联报表不存在」）。"""
        self._create_report()
        self._create_endpoint()
        conn = _get_conn()
        conn.execute("UPDATE api_endpoints SET report_id=999 WHERE url_path='/api/cust'")
        conn.commit()
        conn.close()
        status, body, _ = self._request("/api/cust")
        self.assertEqual(status, 500)
        self.assertIn("关联报表不存在", body)

    def test_missing_pool_500(self):
        """连接池不存在 → 500 INTERNAL_ERROR。"""
        self._create_report(pool_id=999)
        self._create_endpoint()
        status, body, _ = self._request("/api/cust")
        self.assertEqual(status, 500)
        self.assertIn("连接池配置不存在", body)

    # ------------------------------------------------------------------
    # 缺口 19：静态缓存 miss 时报表缺失回退
    # ------------------------------------------------------------------

    def test_static_miss_report_deleted_falls_back(self):
        """静态缓存路径上报表被删 → 回退普通链路 → 500 且失败路径不落盘。

        首次 miss 会合法写入缓存文件，故断言「报表删除后的失败请求
        不产生新文件」：先删除既有文件再请求，文件应保持缺失。
        """
        self._create_report()
        self._create_endpoint()
        status, body, headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")

        conn = _get_conn()
        conn.execute("DELETE FROM report_configs")
        conn.commit()
        conn.close()
        # 清除首次 miss 写入的合法文件，验证后续失败路径不重新落盘
        file_path = static_cache.resolve_file_path("api/cust")
        if os.path.exists(file_path):
            os.remove(file_path)

        status, body, headers = self._request("/api/cust.json")
        self.assertEqual(status, 500, "报表缺失应回退普通链路报 500")
        self.assertIn("关联报表不存在", body)
        self.assertNotIn("X-Static-Cache", headers)
        self.assertFalse(os.path.exists(file_path), "失败路径不应落盘")

    # ------------------------------------------------------------------
    # 缺口 23：result_mode/result_index 不纳入 config_version（疑似缺陷）
    # ------------------------------------------------------------------

    def test_config_version_includes_filters_change(self):
        """config_version 随 filters 文本变化（筛选行为变更 → 静态缓存失效重建）。

        filters 原样参与 MD5（ADR-0005 契约）；新匹配表达式语义使旧缓存
        在 TTL 内自然失效重建，本测试钉住该耦合。
        """
        self._create_report()
        self._create_endpoint()
        conn = _get_conn()
        ep = dict(conn.execute(
            "SELECT * FROM api_endpoints WHERE url_path='/api/cust'").fetchone())
        rep = dict(conn.execute("SELECT * FROM report_configs").fetchone())
        conn.close()

        v1 = api_handler._compute_static_config_version(ep, rep)
        ep2 = dict(ep)
        ep2["filters"] = '[{"col":"name","op":"contains","val":"张*"}]'
        v2 = api_handler._compute_static_config_version(ep2, rep)
        self.assertNotEqual(v1, v2, "filters 变化必须改变 config_version")

    def test_resolve_params_filter_val_normalized(self):
        """_resolve_params 归一化 filters val：数字→str、None/缺失→空串"""
        endpoint = {
            "filters": json.dumps([
                {"col": "a", "op": "contains", "val": 100},
                {"col": "b", "op": "eq", "val": None},
                {"col": "c", "op": "neq"},
            ]),
            "sorts": "", "row_limit": 0, "columns": None,
            "output_format": "json", "allow_fetch_all": 1,
        }
        filters, _sorts, _page, _ps, _rl, _fmt, _cols, _bom, _fa = \
            api_handler._resolve_params(endpoint, "GET", "", {})
        self.assertEqual(filters[0], ("a", "contains", "100"))
        self.assertEqual(filters[1], ("b", "eq", ""))
        self.assertEqual(filters[2], ("c", "neq", ""))
        for _col, _op, val in filters:
            self.assertIsInstance(val, str, "filters val 必须恒为 str")

    def test_config_version_includes_result_mode_and_index(self):
        """config_version 随 result_mode/result_index 变化（修复缺陷）。

        result_mode/result_index 均影响静态文件输出内容（结构/结果集选择），
        _compute_static_config_version 键集须包含它们；绕过 update_api_endpoint
        的失效联动（直接 SQL/迁移脚本修改）时，TTL 内才不会命中旧结构。
        """
        self._create_report()
        self._create_endpoint()
        conn = _get_conn()
        ep = conn.execute(
            "SELECT * FROM api_endpoints WHERE url_path='/api/cust'").fetchone()
        ep = dict(ep)
        rep = conn.execute("SELECT * FROM report_configs").fetchone()
        rep = dict(rep)
        conn.close()

        v1 = api_handler._compute_static_config_version(ep, rep)

        ep2 = dict(ep)
        ep2["result_mode"] = "all"
        ep2["result_index"] = 3
        v2 = api_handler._compute_static_config_version(ep2, rep)
        self.assertNotEqual(v1, v2,
                            "result_mode/result_index 变化必须纳入 config_version")

        ep3 = dict(ep)
        ep3["row_limit"] = 50
        v3 = api_handler._compute_static_config_version(ep3, rep)
        self.assertNotEqual(v1, v3, "对照组：row_limit 变化应改变版本")

    def test_static_miss_after_direct_result_index_change(self):
        """直接 SQL 改 result_index（绕过 update 失效联动）→ 版本变化 → miss 重建。"""
        self._create_report()
        self._create_endpoint(url_path="/api/idx", result_index=0)
        status, body, headers = self._request("/api/idx.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")

        conn = _get_conn()
        conn.execute("UPDATE api_endpoints SET result_index=5 WHERE url_path='/api/idx'")
        conn.commit()
        conn.close()

        status, body, headers = self._request("/api/idx.json")
        self.assertEqual(headers.get("X-Static-Cache"), "miss",
                         "result_index 变化应触发版本失效重建")
        self.assertEqual(status, 400, "result_index=5 越界应返回 400")
        self.assertIn("超出范围", body)

    def test_static_miss_after_direct_row_limit_change(self):
        """对照组：直接 SQL 改 row_limit → config_version 变化 → miss 重建。"""
        self._create_report()
        self._create_endpoint(url_path="/api/rl", row_limit=0)
        status, body, headers = self._request("/api/rl.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")

        conn = _get_conn()
        conn.execute("UPDATE api_endpoints SET row_limit=1 WHERE url_path='/api/rl'")
        conn.commit()
        conn.close()

        status, body, headers = self._request("/api/rl.json")
        self.assertEqual(headers.get("X-Static-Cache"), "miss",
                         "row_limit 变化应触发版本失效重建")
        self.assertEqual(status, 200)

    # ------------------------------------------------------------------
    # 缺口 27：空串 api_key 拒绝
    # ------------------------------------------------------------------

    def test_empty_api_key_query_param_rejected(self):
        """api_key 传空串不能通过鉴权 → 401。"""
        self._create_report()
        self._create_endpoint(api_key="sk-secret")
        status, body, _ = self._request("/api/cust", query={"api_key": [""]})
        self.assertEqual(status, 401)
        status, body, _ = self._request("/api/cust", query={"api_key": []})
        self.assertEqual(status, 401, "空列表等同未提供")

    # ------------------------------------------------------------------
    # 缺口 28：Bearer 变体鉴权
    # ------------------------------------------------------------------

    def test_bearer_variant_authentication(self):
        """Authorization: Bearer <key> 通过；Bearer: 与 Token 变体拒绝。"""
        self._create_report()
        self._create_endpoint(api_key="sk-secret")
        status, body, _ = self._request(
            "/api/cust", headers={"Authorization": "Bearer sk-secret"})
        self.assertEqual(status, 200, "标准 Bearer 前缀应通过")
        status, body, _ = self._request(
            "/api/cust", headers={"Authorization": "Bearer: sk-secret"})
        self.assertEqual(status, 401, "Bearer: 变体应拒绝（当前实际行为）")
        status, body, _ = self._request(
            "/api/cust", headers={"Authorization": "Token sk-secret"})
        self.assertEqual(status, 401, "Token 变体应拒绝（当前实际行为）")

    # ------------------------------------------------------------------
    # 缺口 29：active_index=-1 哨兵（多结果集默认展示行为）
    # ------------------------------------------------------------------

    def test_active_index_minus_one_sentinel_all_mode(self):
        """result_mode=all 时以 active_index=-1 哨兵调用 execute_report。"""
        self._create_report()
        self._create_endpoint(result_mode="all")
        with patch.object(api_handler, "execute_report",
                          wraps=api_handler.execute_report) as m:
            status, body, _ = self._request("/api/cust")
            self.assertEqual(status, 200)
            self.assertEqual(m.call_count, 1)
            kwargs = m.call_args.kwargs
            self.assertEqual(kwargs["active_index"], -1,
                             "all 模式应以 -1 哨兵表示全部结果集")
        parsed = json.loads(body)
        self.assertEqual(parsed["mode"], "all")

    def test_active_index_equals_result_index_single_mode(self):
        """single 模式 active_index 等于端点 result_index。"""
        self._create_report()
        self._create_endpoint(result_index=0)
        with patch.object(api_handler, "execute_report",
                          wraps=api_handler.execute_report) as m:
            status, body, _ = self._request("/api/cust")
            self.assertEqual(status, 200)
            self.assertEqual(m.call_args.kwargs["active_index"], 0)

    # ------------------------------------------------------------------
    # 缺口 30：refresh 恒 False + 缓存复用
    # ------------------------------------------------------------------

    def test_refresh_always_false_and_query_cache_reuse(self):
        """API 链路 refresh 恒为 False；相同查询命中进程内缓存不重复执行 MySQL。

        进程内缓存位于 execute_report 内部：每次 API 请求仍会调用
        execute_report，但第二次请求缓存命中，不再触碰 MySQL（fetchall 仅 1 次）。
        """
        self._create_report()
        self._create_endpoint()
        with patch.object(api_handler, "execute_report",
                          wraps=api_handler.execute_report) as m:
            status, body, _ = self._request("/api/cust")
            self.assertEqual(status, 200)
            self.assertIs(m.call_args.kwargs["refresh"], False,
                          "API 链路不得主动刷新缓存")

            status, body2, _ = self._request("/api/cust")
            self.assertEqual(status, 200)
            self.assertIs(m.call_args.kwargs["refresh"], False,
                          "第二次请求同样不得刷新缓存")
            self.assertEqual(body, body2)
        self.assertEqual(self.mock_cursor.fetchall.call_count, 1,
                         "第二次请求应命中进程内查询缓存，不重复执行 SQL")

    # ------------------------------------------------------------------
    # 缺口 14/15/16/26：server._handle_api 层行为（审计写入 + 错误响应）
    # ------------------------------------------------------------------

    def _make_handler(self, headers=None, **kwargs):
        """构造最小可用的 ReportHandler 替身。

        用 __new__ 实例化以保留真实方法（_read_body/_log_api_call/_write_audit_log），
        仅覆盖请求/响应 IO（rfile/wfile）与响应头记录（send_response 等）。
        """
        handler = srv.ReportHandler.__new__(srv.ReportHandler)
        handler.headers = headers or {}
        handler.client_address = ("127.0.0.1", 12345)
        handler._session_token = None
        handler.rfile = Mock()
        handler.rfile.read.return_value = b""
        handler.wfile = Mock()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        for k, v in kwargs.items():
            setattr(handler, k, v)
        return handler

    def test_api_audit_log_written_e2e(self):
        """缺口 14：API 调用经 server._handle_api 端到端写入 audit_log（type=api）。"""
        self._create_report()
        self._create_endpoint()
        audit_path = os.path.join(_TMP_ROOT, "audit_e2e.db")
        if os.path.exists(audit_path):
            os.remove(audit_path)
        a_conn = sqlite3.connect(audit_path)
        audit_db.init_audit_db(a_conn)
        a_conn.close()

        handler = self._make_handler()
        with patch("audit_db.get_audit_db",
                   side_effect=lambda: sqlite3.connect(audit_path)):
            srv.ReportHandler._handle_api(handler, "GET", "/api/cust", "", _get_conn())

        a_conn = sqlite3.connect(audit_path)
        a_conn.row_factory = sqlite3.Row
        rows = a_conn.execute("SELECT * FROM audit_logs").fetchall()
        a_conn.close()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["type"], "api")
        self.assertEqual(row["action"], "api_call")
        self.assertEqual(row["entity_type"], "api_endpoint")
        self.assertEqual(row["entity_name"], "/api/cust")
        self.assertEqual(row["http_path"], "/api/cust")
        self.assertEqual(row["http_method"], "GET")
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["session_user"], "anonymous")

    def test_audit_failure_does_not_affect_api_response(self):
        """缺口 15：审计写入异常被静默吞掉，API 响应不受影响（200 正常返回）。"""
        self._create_report()
        self._create_endpoint()
        handler = self._make_handler()
        with patch("audit_db.get_audit_db", side_effect=Exception("磁盘满")):
            srv.ReportHandler._handle_api(handler, "GET", "/api/cust", "", _get_conn())
        self.assertEqual(handler.send_response.call_args[0][0], 200,
                         "审计失败不应改变 API 响应状态码")
        written = b"".join(c[0][0] for c in handler.wfile.write.call_args_list
                           if isinstance(c[0][0], bytes))
        self.assertIn(b'"total"', written, "API 正常响应体应完整写出")

    def test_error_response_plain_text_content_type(self):
        """缺口 16：无 Accept 头时错误响应为纯文本 + Content-Type text/plain。"""
        self._create_report()
        self._create_endpoint(result_index=5)
        handler = self._make_handler()
        srv.ReportHandler._handle_api(handler, "GET", "/api/cust", "", _get_conn())
        self.assertEqual(handler.send_response.call_args[0][0], 400)
        cts = [c[0][1] for c in handler.send_header.call_args_list
               if c[0][0] == "Content-Type"]
        self.assertIn("text/plain; charset=utf-8", cts)
        written = b"".join(c[0][0] for c in handler.wfile.write.call_args_list
                           if isinstance(c[0][0], bytes))
        self.assertIn("超出范围".encode("utf-8"), written)
        self.assertNotIn(b'"error"', written, "无 Accept 时错误体应为纯文本而非 JSON")

    def test_error_response_accept_json_matches_content_type(self):
        """缺口 16（修复）：Accept=application/json 时错误 body 为 JSON 且 Content-Type 一致。"""
        self._create_report()
        self._create_endpoint(result_index=5)
        handler = self._make_handler(headers={"Accept": "application/json"})
        srv.ReportHandler._handle_api(handler, "GET", "/api/cust", "", _get_conn())
        cts = [c[0][1] for c in handler.send_header.call_args_list
               if c[0][0] == "Content-Type"]
        self.assertIn("application/json; charset=utf-8", cts,
                      "错误响应 Content-Type 应与 JSON body 一致")
        self.assertNotIn("text/plain; charset=utf-8", cts)
        written = b"".join(c[0][0] for c in handler.wfile.write.call_args_list
                           if isinstance(c[0][0], bytes))
        parsed = json.loads(written)
        self.assertEqual(parsed["code"], "INVALID_RESULT_INDEX")

    def test_body_read_exception_returns_400(self):
        """缺口 26（修复）：请求体读取/解码异常 → 400 纯文本，不再冒泡 500。"""
        self._create_report()
        self._create_endpoint()
        handler = self._make_handler(headers={"Content-Length": "10"})
        handler.rfile.read.return_value = b"\xff\xfe"  # 截断/非法 UTF-8
        srv.ReportHandler._handle_api(handler, "POST", "/api/cust", "", _get_conn())
        self.assertEqual(handler.send_response.call_args[0][0], 400,
                         "请求体解码失败应返回 400 而非 500/异常冒泡")
        cts = [c[0][1] for c in handler.send_header.call_args_list
               if c[0][0] == "Content-Type"]
        self.assertIn("text/plain; charset=utf-8", cts)
        written = b"".join(c[0][0] for c in handler.wfile.write.call_args_list
                           if isinstance(c[0][0], bytes))
        self.assertIn("请求体读取失败".encode("utf-8"), written)


class TestApiKeyAuth(MockMySQLMixin, unittest.TestCase):
    """API Key 多 key 化鉴权端到端测试（PH-02）。

    api_keys 表已含于 _set_up_db 建表脚本；复用模块级临时库与
    db.create_mysql_connection mock 基建（与 TestApiExtra 相同模式）。
    """

    @classmethod
    def setUpClass(cls):
        cls._mysql_patcher = patch("db.create_mysql_connection")
        cls._mock_factory = cls._mysql_patcher.start()
        # TestApiExtra.tearDownClass 会删除共享临时库（_TMP_ROOT），本类
        # 按定义顺序在其后执行，必须重建（幂等），避免 sqlite 打不开。
        os.makedirs(_TMP_ROOT, exist_ok=True)
        _set_up_db()

    @classmethod
    def tearDownClass(cls):
        cls._mysql_patcher.stop()

    def setUp(self):
        """每个测试前注入配置、清空业务表、缓存目录、进程内缓存与失效记录。"""
        self._cfg_patcher = patch("app_config.get_config", return_value=_test_config())
        self._cfg_patcher.start()
        conn = _get_conn()
        conn.execute("DELETE FROM api_endpoints")
        conn.execute("DELETE FROM report_configs")
        conn.commit()
        conn.close()
        if os.path.isdir(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
        static_cache._last_invalidated.clear()
        report_mod._query_cache.clear()

        mock_conn, mock_cursor = self.make_mock_connection()
        mock_cursor.description = [("id",), ("name",), ("age",), ("status",)]
        mock_cursor.fetchall.return_value = [
            (1, "张三", 25, "active"),
            (2, "李四", 30, "inactive"),
            (3, "王五", 35, "active"),
        ]
        type(self)._mock_factory.side_effect = None
        type(self)._mock_factory.return_value = mock_conn
        self.mock_cursor = mock_cursor

    def tearDown(self):
        self._cfg_patcher.stop()

    def _create_report(self, sql="SELECT id, name, age, status FROM users"):
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs "
            "(name,sql_query,default_page_size,pool_id,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试报表", sql, 20, 1, 0, 0, 1))
        conn.commit()
        rid = conn.execute(
            "SELECT id FROM report_configs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        return rid

    def _create_endpoint(self, url_path="/api/cust", **kwargs):
        """创建测试端点（report_id 缺省取最新报表）。"""
        conn = _get_conn()
        report_id = conn.execute(
            "SELECT id FROM report_configs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        eid = db.add_api_endpoint(conn, report_id, "测试端点", url_path, **kwargs)
        conn.close()
        return eid

    def _request(self, path, method="GET", query=None, headers=None, body=""):
        """直接调用 handle_api_request（最高测试 seam）。"""
        return api_handler.handle_api_request(
            _get_conn(), path, method, headers or {}, body, query or {},
            client_ip="127.0.0.1")

    def test_any_enabled_key_authenticates(self):
        """多 key：任一启用 key 均通过；错误 key 与缺失拒绝。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        config_db.add_api_key(conn, eid, "key1", "sk-1")
        config_db.add_api_key(conn, eid, "key2", "sk-2")
        conn.close()
        for key in ("sk-1", "sk-2"):
            status, _, _ = self._request("/api/cust", query={"api_key": [key]})
            self.assertEqual(status, 200, f"启用 key {key} 应通过")
        status, body, _ = self._request("/api/cust", query={"api_key": ["sk-3"]})
        self.assertEqual(status, 401, "未注册 key 应拒绝")
        self.assertIn("API Key", body)
        status, body, _ = self._request("/api/cust")
        self.assertEqual(status, 401, "未提供 key 应拒绝")

    def test_disabled_key_rejected_others_ok(self):
        """禁用某 key 后立即失效，其余启用 key 不受影响。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        k1 = config_db.add_api_key(conn, eid, "key1", "sk-1")
        config_db.add_api_key(conn, eid, "key2", "sk-2")
        config_db.set_api_key_enabled(conn, k1, 0)
        conn.close()
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-1"]})
        self.assertEqual(status, 401, "禁用 key 应拒绝")
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-2"]})
        self.assertEqual(status, 200, "其他启用 key 不受影响")

    def test_all_disabled_denies_even_legacy_column(self):
        """表内有记录但全部禁用：旧列 key 也不生效（防旧列绕过）。"""
        self._create_report()
        eid = self._create_endpoint(api_key="sk-legacy")
        conn = _get_conn()
        k1 = config_db.add_api_key(conn, eid, "key1", "sk-1")
        config_db.set_api_key_enabled(conn, k1, 0)
        conn.close()
        for key in ("sk-legacy", "sk-1"):
            status, _, _ = self._request("/api/cust", query={"api_key": [key]})
            self.assertEqual(status, 401, f"全部禁用时 key={key} 应拒绝")

    def test_deleted_key_rejected_immediately(self):
        """删除某 key 后立即失效，其余 key 不受影响。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        k1 = config_db.add_api_key(conn, eid, "key1", "sk-1")
        config_db.add_api_key(conn, eid, "key2", "sk-2")
        conn.close()
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-1"]})
        self.assertEqual(status, 200, "删除前应通过")
        conn = _get_conn()
        config_db.delete_api_key(conn, k1)
        conn.close()
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-1"]})
        self.assertEqual(status, 401, "删除后应拒绝")
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-2"]})
        self.assertEqual(status, 200, "其余 key 不受影响")

    def test_last_key_deleted_returns_to_public(self):
        """删除最后一个 key 后端点恢复公开（与旧版清空 api_key 行为一致）。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        k1 = config_db.add_api_key(conn, eid, "key1", "sk-1")
        conn.close()
        conn = _get_conn()
        config_db.delete_api_key(conn, k1)
        conn.close()
        status, _, _ = self._request("/api/cust")
        self.assertEqual(status, 200, "无任何 key 配置的端点应公开")

    def test_legacy_column_key_still_works(self):
        """未迁移场景（api_keys 空表）旧列 key 仍可鉴权（兼容回退）。"""
        self._create_report()
        self._create_endpoint(api_key="sk-legacy")
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-legacy"]})
        self.assertEqual(status, 200, "旧列 key 应通过（回退路径）")
        status, _, _ = self._request("/api/cust", query={"api_key": ["sk-other"]})
        self.assertEqual(status, 401, "错误 key 应拒绝")

    def test_migration_then_new_key_takes_effect(self):
        """模拟存量迁移：旧列 key 迁入 api_keys 后，新增 key 生效、旧 key 仍有效。"""
        self._create_report()
        eid = self._create_endpoint(api_key="sk-old")
        conn = _get_conn()
        config_db._init_sqlite_migrations(conn)  # 存量迁入（测试库本已含表，幂等）
        config_db.add_api_key(conn, eid, "新 Key", "sk-new")
        conn.close()
        for key in ("sk-old", "sk-new"):
            status, _, _ = self._request("/api/cust", query={"api_key": [key]})
            self.assertEqual(status, 200, f"key={key} 应通过")


if __name__ == "__main__":
    unittest.main()
