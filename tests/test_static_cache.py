"""
test_static_cache.py — API 静态文件缓存（.json 变体）测试

测试策略：
- 临时 SQLite 文件 + CONFIG_FILE 注入（static_cache.dir 指向临时目录）
- Mock db.create_mysql_connection 避免真实 MySQL 依赖
- 以 api_handler.handle_api_request 为最高测试 seam（端到端行为断言）
- 覆盖：miss→重建→hit、meta 字段、TTL 过期、版本失效、自愈、鉴权、
  路径穿越、CSV/POST/非 200 不参与、并发原子写、业务参数忽略

PH-01 缓存新鲜度批次覆盖：
- 静态 .json 变体忽略 refresh=1（命中仍 hit，不重建；D4 决策）
"""

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import app_config
import api_handler
import config
import db
import report
import static_cache
from tests.test_mysql_mock import MockMySQLMixin

# 创建临时测试环境（数据库 + 缓存目录）
# 注意：不设置 CONFIG_FILE/CONFIG_DB 环境变量，避免污染同进程内其他测试
# （unittest discover 共享进程）；配置通过 patch("app_config.get_config") 注入
_TMP_ROOT = tempfile.mkdtemp(prefix="test_static_cache_")
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
    """创建测试数据库表结构。"""
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
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0,
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
            json_no_quotes  INTEGER NOT NULL DEFAULT 0,
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
            json_template TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE);
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


class TestStaticCache(MockMySQLMixin, unittest.TestCase):
    """静态缓存端到端测试（handle_api_request 为 seam）。"""

    @classmethod
    def setUpClass(cls):
        cls._mysql_patcher = patch("db.create_mysql_connection")
        cls._mock_factory = cls._mysql_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._mysql_patcher.stop()
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

    def setUp(self):
        """每个测试前注入配置、清空业务表、缓存目录与进程内失效记录。"""
        # 注入 app_config（含 static_cache.dir → 临时目录），不污染全局环境
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

    def tearDown(self):
        """停止配置 patcher。"""
        self._cfg_patcher.stop()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _create_report(self, sql="SELECT id, name, age, status FROM users",
                       ttl_hours=0, name="测试报表"):
        """创建测试报表（prefer_cache=0 避免测试环境 Redis 依赖）。"""
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs "
            "(name,sql_query,default_page_size,pool_id,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, sql, 20, 1, 0, ttl_hours, 1))
        conn.commit()
        rid = conn.execute(
            "SELECT id FROM report_configs WHERE name=?", (name,)).fetchone()[0]
        conn.close()
        return rid

    def _create_endpoint(self, report_id=1, url_path="/api/cust", **kwargs):
        """在数据库中创建测试端点。"""
        conn = _get_conn()
        eid = db.add_api_endpoint(conn, report_id, "测试端点", url_path, **kwargs)
        conn.close()
        return eid

    def _request(self, path, method="GET", query=None, headers=None, body=""):
        """直接调用 handle_api_request（最高测试 seam）。"""
        return api_handler.handle_api_request(
            _get_conn(), path, method, headers or {}, body, query or {},
            client_ip="127.0.0.1")

    def _assert_no_files(self):
        """断言缓存目录下无任何文件。"""
        if not os.path.isdir(_CACHE_DIR):
            return
        for _root, _dirs, files in os.walk(_CACHE_DIR):
            self.assertEqual(files, [])

    # ------------------------------------------------------------------
    # 命中 / 回退 / 重建
    # ------------------------------------------------------------------

    def test_first_miss_then_hit(self):
        """首次请求 miss → 回退计算 → 生成文件；二次请求 hit 直出文件。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        # 首次：miss
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        data = json.loads(body)
        self.assertTrue(data["full"])
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 3)
        self.assertEqual(data["total_pages"], 1)
        self.assertEqual(len(data["data"]), 3)
        self.assertIn("meta", data)
        file_path = static_cache.resolve_file_path("api/cust")
        self.assertIsNotNone(file_path)
        self.assertTrue(os.path.isfile(file_path))
        # 二次：hit，内容与文件一致
        status, body2, resp_headers2 = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(resp_headers2.get("Content-Type"),
                         "application/json; charset=utf-8")
        self.assertEqual(body2, body)

    def test_static_ignores_refresh_param(self):
        """PH-01：静态 .json 变体忽略 refresh=1（命中仍 hit，不重建，D4）"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/refresh-static")
        status, body, resp_headers = self._request("/api/refresh-static.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertTrue(os.path.isfile(
            static_cache.resolve_file_path("api/refresh-static")))
        # refresh=1 不应触发重建：仍返回 hit 且内容不变
        status, body2, resp_headers2 = self._request(
            "/api/refresh-static.json", query={"refresh": ["1"]})
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers2.get("X-Static-Cache"), "hit",
                         "静态缓存应忽略 refresh，命中直接返回文件")
        self.assertEqual(body2, body)

    def test_static_output_excludes_description(self):
        """静态缓存链路输出不含接口说明（description 只用于页面展示）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/desc-static",
                              description="静态链路说明\n不应出现")
        status, body, resp_headers = self._request("/api/desc-static.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertNotIn("静态链路说明", body)
        self.assertNotIn("description", body)
        # 命中链路同样不含
        status, body, resp_headers = self._request("/api/desc-static.json")
        self.assertEqual(resp_headers.get("X-Static-Cache"), "hit")
        self.assertNotIn("静态链路说明", body)

    def test_public_endpoint_accessible(self):
        """无 key 端点公开可访问。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        data = json.loads(body)
        self.assertEqual(len(data["data"]), 3)

    def test_meta_fields_and_expires_null_when_ttl_zero(self):
        """文件内容 meta 三字段齐全；TTL=0 时 expires_at 为 null；时间格式秒级+时区。"""
        rid = self._create_report(ttl_hours=0)
        self._create_endpoint(report_id=rid)
        _, body, _ = self._request("/api/cust.json")
        meta = json.loads(body)["meta"]
        for key in ("generated_at", "expires_at", "last_invalidated_at"):
            self.assertIn(key, meta)
        self.assertIsNone(meta["expires_at"])
        self.assertIsNone(meta["last_invalidated_at"])
        self.assertRegex(
            meta["generated_at"],
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}$")

    def test_ttl_expiry_rebuilds(self):
        """TTL 过期后再次请求 miss 并重建。"""
        rid = self._create_report(ttl_hours=1)
        self._create_endpoint(report_id=rid)
        self._request("/api/cust.json")
        file_path = static_cache.resolve_file_path("api/cust")
        old_mtime = os.path.getmtime(file_path)
        # 将 mtime 拨回 2 小时前 → 过期
        os.utime(file_path, (old_mtime - 7200, old_mtime - 7200))
        status, _, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertGreater(os.path.getmtime(file_path), old_mtime)

    def test_sql_change_invalidates(self):
        """SQL 变更（config_version 变化）自动失效重建。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        _, body1, _ = self._request("/api/cust.json")
        v1 = json.loads(body1)["meta"]["config_version"]
        # 更新报表 SQL → 版本变化
        conn = _get_conn()
        db.update_report(conn, rid, "测试报表", "SELECT id, name FROM users", 20, 1)
        conn.close()
        status, body2, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        v2 = json.loads(body2)["meta"]["config_version"]
        self.assertNotEqual(v1, v2)
        # 后续请求命中新版本文件
        _, body3, resp_headers3 = self._request("/api/cust.json")
        self.assertEqual(resp_headers3.get("X-Static-Cache"), "hit")
        self.assertEqual(body3, body2)

    def test_endpoint_config_change_invalidates(self):
        """端点变换配置（filters）变更 → config_version 变化 → 旧文件失效重建。"""
        rid = self._create_report()
        self._create_endpoint(
            report_id=rid,
            filters='[{"col":"status","op":"eq","val":"active"}]')
        _, body1, _ = self._request("/api/cust.json")
        v1 = json.loads(body1)["meta"]["config_version"]
        # 编辑端点筛选规则 → 版本变化 → 静态文件自动失效
        conn = _get_conn()
        eid = db.get_api_endpoint_by_path(conn, "/api/cust")["id"]
        db.update_api_endpoint(conn, eid, filters='[{"col":"status","op":"eq","val":"inactive"}]')
        conn.close()
        status, body2, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        v2 = json.loads(body2)["meta"]["config_version"]
        self.assertNotEqual(v1, v2)
        # 后续请求命中新版本文件
        _, body3, resp_headers3 = self._request("/api/cust.json")
        self.assertEqual(resp_headers3.get("X-Static-Cache"), "hit")
        self.assertEqual(body3, body2)

    def test_template_endpoint_static_uses_template(self):
        """模板端点 .json 变体：文件内容为模板渲染结果，命中时一致。"""
        rid = self._create_report()
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_count": {{total}}, "rows": {{data}}}')
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        parsed = json.loads(body)
        self.assertEqual(parsed["rand99_count"], 3)
        self.assertEqual(len(parsed["rows"]), 3)
        self.assertNotIn("total", parsed)
        # 二次请求命中缓存，内容一致
        _, body2, resp_headers2 = self._request("/api/cust.json")
        self.assertEqual(resp_headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(body2, body)

    def test_template_in_config_version(self):
        """编辑模板 → config_version 变化 → 旧文件自动失效重建。"""
        rid = self._create_report()
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_count": {{total}}, "meta": {{meta}}}')
        _, body1, _ = self._request("/api/cust.json")
        v1 = json.loads(body1)["meta"]["config_version"]
        conn = _get_conn()
        eid = db.get_api_endpoint_by_path(conn, "/api/cust")["id"]
        db.update_api_endpoint(
            conn, eid, json_template='{"rand99_count": {{total}}, "x": 1, "meta": {{meta}}}')
        conn.close()
        status, body2, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        v2 = json.loads(body2)["meta"]["config_version"]
        self.assertNotEqual(v1, v2)
        self.assertEqual(json.loads(body2)["x"], 1)
        # 后续请求命中新版本文件
        _, body3, resp_headers3 = self._request("/api/cust.json")
        self.assertEqual(resp_headers3.get("X-Static-Cache"), "hit")
        self.assertEqual(body3, body2)

    def test_template_with_meta_placeholder(self):
        """模板含 {{meta}}：meta 节点进入输出（用户自定位置）。"""
        rid = self._create_report(ttl_hours=1)
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_when": {{meta}}}')
        _, body, _ = self._request("/api/cust.json")
        parsed = json.loads(body)
        self.assertIn("generated_at", parsed["rand99_when"])
        self.assertIn("config_version", parsed["rand99_when"])
        self.assertIsInstance(parsed["rand99_when"]["expires_at"], str,
                              "TTL=1 时 expires_at 为时间字符串")

    def test_template_without_meta_placeholder(self):
        """模板不含 {{meta}}：输出不带 meta 节点。"""
        rid = self._create_report(ttl_hours=1)
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_rows": {{data}}}')
        _, body, _ = self._request("/api/cust.json")
        parsed = json.loads(body)
        self.assertNotIn("meta", parsed)
        self.assertEqual(len(parsed["rand99_rows"]), 3)

    def test_template_meta_non_object_value(self):
        """模板把 meta 改写为非对象值（键集内合法）：可命中，不 miss 重建循环。

        修复场景：{"meta": {{data}}} 时 meta 为数组，原实现 try_read 对
        非 dict meta 调 .get 抛 AttributeError → 每次请求 miss 重建 +
        warning 日志噪音。
        """
        rid = self._create_report(ttl_hours=24)
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_rows": {{data}}, "meta": {{data}}}')
        status, body1, headers1 = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers1.get("X-Static-Cache"), "miss")
        self.assertEqual(len(json.loads(body1)["rand99_rows"]), 3)
        # 二次请求必须命中（非对象 meta 走版本化文件判定）
        status, body2, headers2 = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(body2, body1)
        # 改模板 → 版本变化 → miss 重建
        conn = _get_conn()
        eid = db.get_api_endpoint_by_path(conn, "/api/cust")["id"]
        db.update_api_endpoint(
            conn, eid, json_template='{"rand99_rows": {{data}}, "meta": {{data}}, "extra": 1}')
        conn.close()
        static_cache._last_invalidated.clear()
        _, body3, headers3 = self._request("/api/cust.json")
        self.assertEqual(headers3.get("X-Static-Cache"), "miss")
        self.assertEqual(json.loads(body3)["extra"], 1)
        _, _, headers4 = self._request("/api/cust.json")
        self.assertEqual(headers4.get("X-Static-Cache"), "hit")

    def test_remove_stale_versioned_keeps_newer_concurrent(self):
        """清理旧版本文件时保留 mtime 新于 keep 的文件（并发写入保护）。

        并发场景：写入方 A 完成双写后清理旧版本，此时并发方 B 刚写入
        更新版本文件；清理不得删除 B 的新文件（最后写入者生效），
        否则 B 的版本文件下次请求 miss 重建。
        """
        os.makedirs(_CACHE_DIR, exist_ok=True)
        file_path = os.path.join(_CACHE_DIR, "api", "concurrent.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        v_keep = static_cache._versioned_path(file_path, "aaaa1111")
        v_newer = static_cache._versioned_path(file_path, "bbbb2222")
        with open(v_keep, "w", encoding="utf-8") as f:
            f.write("{}")
        with open(v_newer, "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(v_keep, (1000, 1000))
        os.utime(v_newer, (2000, 2000))
        static_cache._remove_stale_versioned(file_path, keep=v_keep)
        self.assertTrue(os.path.isfile(v_newer), "并发写入的更新版本文件必须保留")
        self.assertTrue(os.path.isfile(v_keep), "keep 文件不得被清理")
        # 旧版本（mtime 早于 keep）正常清理
        v_old = static_cache._versioned_path(file_path, "0000ffff")
        with open(v_old, "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(v_old, (500, 500))
        static_cache._remove_stale_versioned(file_path, keep=v_newer)
        self.assertFalse(os.path.isfile(v_old), "旧版本文件应被清理")
        self.assertTrue(os.path.isfile(v_newer))

    def test_template_no_meta_change_invalidates_after_restart(self):
        """无 meta 模板改库 → 版本文件不匹配 → 自动失效重建（不依赖进程内存）。

        修复场景：模板不含 {{meta}} 时静态文件无版本信息，原实现靠进程内存
        失效时刻判定，绕过 UI 改库后 TTL 内持续命中旧结构、进程重启后判定
        丢失。现版本号嵌入文件名，改库即版本变化 → miss。
        """
        rid = self._create_report(ttl_hours=24)
        self._create_endpoint(
            report_id=rid,
            json_template='{"rand99_rows": {{data}}}')
        _, body1, _ = self._request("/api/cust.json")
        self.assertNotIn("meta", json.loads(body1))
        # 二次请求命中
        _, _, resp_headers2 = self._request("/api/cust.json")
        self.assertEqual(resp_headers2.get("X-Static-Cache"), "hit")
        # 绕过 UI 直接改库（模拟进程外修改）→ 清空内存失效记录（模拟进程重启）
        conn = _get_conn()
        eid = db.get_api_endpoint_by_path(conn, "/api/cust")["id"]
        db.update_api_endpoint(
            conn, eid, json_template='{"rand99_rows": {{data}}, "extra": 1}')
        conn.close()
        static_cache._last_invalidated.clear()
        # 版本已变 → 即使无内存失效记录也必须 miss 并重建
        status, body3, resp_headers3 = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers3.get("X-Static-Cache"), "miss")
        self.assertEqual(json.loads(body3)["extra"], 1)
        # 新版本文件生成后命中
        _, body4, resp_headers4 = self._request("/api/cust.json")
        self.assertEqual(resp_headers4.get("X-Static-Cache"), "hit")
        self.assertEqual(body4, body3)

    def test_template_all_mode_static(self):
        """result_mode=all + 模板：静态 miss 链路输出模板渲染结果。"""
        rid = self._create_report()
        self._create_endpoint(
            report_id=rid, result_mode="all",
            json_template='{"mode": {{mode}}, "sets": {{results}}}')
        status, body, _ = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["mode"], "all")
        self.assertEqual(len(parsed["sets"]), 1)

    def test_endpoint_switch_off_falls_back(self):
        """端点静态缓存开关关闭：.json 请求回退普通 API，不生成文件。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, static_cache=0)
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self.assertNotIn("meta", json.loads(body))
        self._assert_no_files()

    def test_last_invalidated_at_semantics(self):
        """last_invalidated_at 语义：缺失重建沿用历史；失效重建记录本次时刻。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        # 首次缺失：无文件被判定失效 → null
        _, body1, _ = self._request("/api/cust.json")
        self.assertIsNone(json.loads(body1)["meta"]["last_invalidated_at"])
        # SQL 变更 → 文件存在但版本不符 → 本次为失效事件 → meta 记录本次时刻
        conn = _get_conn()
        db.update_report(conn, rid, "测试报表", "SELECT id, name FROM users", 20, 1)
        conn.close()
        _, body2, _ = self._request("/api/cust.json")
        meta2 = json.loads(body2)["meta"]
        self.assertIsNotNone(meta2["last_invalidated_at"])
        self.assertRegex(meta2["last_invalidated_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}$")
        # 第三方删除 → 缺失重建不算失效事件 → 沿用历史记录（= 上次失效时刻）
        file_path = static_cache.resolve_file_path("api/cust")
        os.remove(file_path)
        _, body3, _ = self._request("/api/cust.json")
        self.assertEqual(
            json.loads(body3)["meta"]["last_invalidated_at"],
            meta2["last_invalidated_at"])

    def test_last_invalidated_bounded(self):
        """失效记录有界：超过上限后淘汰最旧记录，内存不无界增长。"""
        for i in range(static_cache._MAX_LAST_INVALIDATED + 5):
            static_cache.record_invalidated(f"/api/edge-{i}")
        self.assertEqual(len(static_cache._last_invalidated),
                         static_cache._MAX_LAST_INVALIDATED)
        # 最旧的记录被淘汰，最新的保留
        self.assertNotIn("/api/edge-0", static_cache._last_invalidated)
        self.assertIn(
            f"/api/edge-{static_cache._MAX_LAST_INVALIDATED + 4}",
            static_cache._last_invalidated)

    def test_third_party_delete_heals(self):
        """文件被第三方删除后自动自愈重建。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        self._request("/api/cust.json")
        file_path = static_cache.resolve_file_path("api/cust")
        os.remove(file_path)
        status, _, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertTrue(os.path.isfile(file_path))

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    def test_auth_required_missing_and_wrong_key(self):
        """带 key 端点缺 key/错 key → 401 且不产生文件；正确 key 正常生成。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, api_key="secret-key")
        # 缺 key → 401
        status, _, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 401)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self._assert_no_files()
        # 错 key → 401
        status, _, resp_headers = self._request(
            "/api/cust.json", query={"api_key": ["wrong"]})
        self.assertEqual(status, 401)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self._assert_no_files()
        # 正确 key（查询参数）→ miss → 生成文件
        status, _, resp_headers = self._request(
            "/api/cust.json", query={"api_key": ["secret-key"]})
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertTrue(os.path.isfile(static_cache.resolve_file_path("api/cust")))

    def test_auth_header_key(self):
        """Authorization 头携带正确 key 同样可生成静态文件。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, api_key="header-key")
        status, _, resp_headers = self._request(
            "/api/cust.json", headers={"Authorization": "Bearer header-key"})
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")

    # ------------------------------------------------------------------
    # 排除场景
    # ------------------------------------------------------------------

    def test_path_traversal_rejected(self):
        """路径穿越（..）请求被拒绝并回退普通链路，不产生文件。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/a/1/../../../../evil")
        status, body, resp_headers = self._request("/api/a/1/../../../../evil.json")
        self.assertEqual(status, 200)
        self.assertNotIn("X-Static-Cache", resp_headers)
        data = json.loads(body)
        self.assertEqual(len(data["data"]), 3)
        self._assert_no_files()

    def test_csv_endpoint_not_involved(self):
        """CSV 端点不参与静态缓存：回退普通 API 输出 CSV，不产生文件。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, output_format="csv")
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self.assertEqual(resp_headers.get("Content-Type"),
                         "text/csv; charset=utf-8")
        self.assertIn("id,name,age,status", body)
        self._assert_no_files()

    def test_post_not_involved(self):
        """POST 请求不参与静态缓存（.json 变体仅 GET 入口，POST 原路径 404）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        status, _, resp_headers = self._request(
            "/api/cust.json", method="POST", body=json.dumps({"page": 2}))
        self.assertEqual(status, 404)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self._assert_no_files()

    def test_non_200_not_written(self):
        """非 200 响应（结果集索引越界）不落盘。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, result_index=5)
        status, _, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 400)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self._assert_no_files()

    def test_global_disable_falls_back(self):
        """全局开关 enable=false 时回退普通 API 链路。"""
        cfg = app_config.get_config()
        cfg["static_cache"]["enable"] = False
        try:
            rid = self._create_report()
            self._create_endpoint(report_id=rid)
            status, body, resp_headers = self._request("/api/cust.json")
            self.assertEqual(status, 200)
            self.assertNotIn("X-Static-Cache", resp_headers)
            self.assertNotIn("meta", json.loads(body))
            self._assert_no_files()
        finally:
            cfg["static_cache"]["enable"] = True

    def test_endpoint_url_ending_with_json_not_hijacked(self):
        """端点 URL 本身以 .json 结尾时不被静态分支误伤。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/weird.json")
        status, body, resp_headers = self._request("/api/weird.json")
        self.assertEqual(status, 200)
        self.assertNotIn("X-Static-Cache", resp_headers)
        self.assertNotIn("meta", json.loads(body))
        self._assert_no_files()

    # ------------------------------------------------------------------
    # 全量语义与业务参数
    # ------------------------------------------------------------------

    def test_business_params_ignored(self):
        """业务参数（page/page_size/columns 等）不影响静态文件内容（始终全量）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        _, body, _ = self._request("/api/cust.json", query={
            "page": ["3"], "page_size": ["1"], "limit": ["1"],
            "columns": ["id"], "fetch_all": ["0"],
        })
        data = json.loads(body)
        self.assertTrue(data["full"])
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 3)
        self.assertEqual(data["total_pages"], 1)
        self.assertEqual(len(data["data"]), 3)
        self.assertIn("age", data["data"][0], "columns 参数应被忽略，保留全部列")

    def test_result_mode_all_supported(self):
        """result_mode=all 端点同样支持静态化输出（全部结果集 + meta）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, result_mode="all")
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        data = json.loads(body)
        self.assertEqual(data["mode"], "all")
        self.assertTrue(data["full"])
        self.assertEqual(len(data["results"]), 1)
        self.assertTrue(data["results"][0]["full"])
        self.assertEqual(data["results"][0]["page_size"], 3)
        self.assertIn("meta", data)
        # 二次 hit
        _, body2, resp_headers2 = self._request("/api/cust.json")
        self.assertEqual(resp_headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(body2, body)

    def test_allow_fetch_all_disabled_still_full(self):
        """allow_fetch_all=0 的端点静态化输出仍为全量（文件固有语义，与开关无关）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, allow_fetch_all=0)
        _, body, _ = self._request("/api/cust.json")
        data = json.loads(body)
        self.assertTrue(data["full"])
        self.assertEqual(len(data["data"]), 3)

    # ------------------------------------------------------------------
    # 并发与自愈
    # ------------------------------------------------------------------

    def test_concurrent_miss_no_corruption(self):
        """并发 miss 写文件无损坏（原子写，最后写入者生效）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        results = []

        def worker():
            results.append(self._request("/api/cust.json"))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for status, body, _ in results:
            self.assertEqual(status, 200)
        # 文件内容完整可解析（无损坏）
        file_path = static_cache.resolve_file_path("api/cust")
        with open(file_path, encoding="utf-8") as f:
            content = json.loads(f.read())
        self.assertTrue(content["full"])
        self.assertEqual(len(content["data"]), 3)
        self.assertIn("meta", content)

    def test_corrupted_file_heals(self):
        """文件内容损坏（非法 JSON）视为 miss 并自动重建。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid)
        self._request("/api/cust.json")
        file_path = static_cache.resolve_file_path("api/cust")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("{{{broken json")
        status, body, resp_headers = self._request("/api/cust.json")
        self.assertEqual(status, 200)
        self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
        self.assertEqual(json.loads(body)["total"], 3)


    def test_refresh_deletes_static_files(self):
        """refresh=True（报表页重建缓存）删除该报表全部端点的静态文件。"""
        rid = self._create_report(ttl_hours=0)
        self._create_endpoint(report_id=rid, url_path="/api/refresh-a")
        self._create_endpoint(report_id=rid, url_path="/api/refresh-b")
        self._request("/api/refresh-a.json")
        self._request("/api/refresh-b.json")
        file_a = os.path.join(_CACHE_DIR, "api", "refresh-a.json")
        file_b = os.path.join(_CACHE_DIR, "api", "refresh-b.json")
        self.assertTrue(os.path.exists(file_a))
        self.assertTrue(os.path.exists(file_b))

        conn = _get_conn()
        pool_config = db.get_pool(conn, 1)
        report.execute_report(
            rid, "SELECT id, name, age, status FROM users", pool_config,
            refresh=True, report={"prefer_cache": 0, "cache_ttl_hours": 0}, conn=conn)
        conn.close()

        self.assertFalse(os.path.exists(file_a), "refresh 后静态文件应被删除")
        self.assertFalse(os.path.exists(file_b), "refresh 后静态文件应被删除")

    def test_refresh_only_affects_own_endpoints(self):
        """refresh 只删除该报表的端点文件，其他报表的文件保留。"""
        rid_a = self._create_report(name="报表A")
        rid_b = self._create_report(name="报表B")
        self._create_endpoint(report_id=rid_a, url_path="/api/refresh-a")
        self._create_endpoint(report_id=rid_b, url_path="/api/refresh-b")
        self._request("/api/refresh-a.json")
        self._request("/api/refresh-b.json")
        file_b = os.path.join(_CACHE_DIR, "api", "refresh-b.json")
        self.assertTrue(os.path.exists(file_b))

        conn = _get_conn()
        pool_config = db.get_pool(conn, 1)
        report.execute_report(
            rid_a, "SELECT id, name, age, status FROM users", pool_config,
            refresh=True, report={"prefer_cache": 0, "cache_ttl_hours": 0}, conn=conn)
        conn.close()

        self.assertTrue(os.path.exists(file_b), "其他报表的静态文件应保留")

    def test_refresh_with_none_page_size(self):
        """refresh 时 page_size/page 为 None（URL 未带参数）不应抛异常，联动照常执行。"""
        rid = self._create_report(name="报表NonePS")
        self._create_endpoint(report_id=rid, url_path="/api/refresh-none")
        self._request("/api/refresh-none.json")
        file_p = os.path.join(_CACHE_DIR, "api", "refresh-none.json")
        self.assertTrue(os.path.exists(file_p))

        conn = _get_conn()
        pool_config = db.get_pool(conn, 1)
        report.execute_report(
            rid, "SELECT id, name, age, status FROM users", pool_config,
            page=None, page_size=None, refresh=True,
            report={"prefer_cache": 0, "cache_ttl_hours": 0}, conn=conn)
        conn.close()

        self.assertFalse(os.path.exists(file_p),
                         "page_size=None 时 refresh 联动也应删除静态文件")

    def test_batch_close_cache_deletes_static_files(self):
        """批量关闭缓存删除选中报表的静态文件，未选中报表保留。"""
        rid_a = self._create_report(name="报表A")
        rid_b = self._create_report(name="报表B")
        self._create_endpoint(report_id=rid_a, url_path="/api/batch-a")
        self._create_endpoint(report_id=rid_b, url_path="/api/batch-b")
        self._request("/api/batch-a.json")
        self._request("/api/batch-b.json")
        file_a = os.path.join(_CACHE_DIR, "api", "batch-a.json")
        file_b = os.path.join(_CACHE_DIR, "api", "batch-b.json")
        self.assertTrue(os.path.exists(file_a))
        self.assertTrue(os.path.exists(file_b))

        code, redirect = config.handle_batch_cache(_get_conn(), f"report_ids={rid_a}&cache_switch=0")
        self.assertEqual(code, 302)

        self.assertFalse(os.path.exists(file_a), "批量关缓存后静态文件应被删除")
        self.assertTrue(os.path.exists(file_b), "未选中报表的静态文件应保留")

    def test_batch_close_cache_idempotent_without_files(self):
        """批量关缓存时文件不存在不报错（幂等）。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/batch-none")
        code, redirect = config.handle_batch_cache(_get_conn(), f"report_ids={rid}&cache_switch=0")
        self.assertEqual(code, 302)

    # ------------------------------------------------------------------
    # 端点变更 → 缓存文件删除
    # ------------------------------------------------------------------

    def _write_cache_file(self, path):
        """在缓存目录写入一个缓存文件，返回文件路径。"""
        fp = static_cache.resolve_file_path(path.lstrip("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write("{}")
        return fp

    def test_delete_endpoint_removes_cache_file(self):
        """删除 API 端点后对应静态缓存文件被删除。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/del-cache")
        fp = self._write_cache_file("/api/del-cache")
        self.assertTrue(os.path.exists(fp))
        db.delete_api_endpoint(_get_conn(), eid)
        self.assertFalse(os.path.exists(fp), "删除端点后缓存文件应被删除")

    def test_disable_endpoint_removes_cache_file(self):
        """禁用 API 端点（enabled=0）后对应静态缓存文件被删除。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/disable-cache")
        fp = self._write_cache_file("/api/disable-cache")
        db.update_api_endpoint(_get_conn(), eid, enabled=0)
        self.assertFalse(os.path.exists(fp), "禁用端点后缓存文件应被删除")

    def test_rename_endpoint_removes_cache_file(self):
        """改名 API 端点后对应静态缓存文件被删除。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/rename-cache")
        fp = self._write_cache_file("/api/rename-cache")
        db.update_api_endpoint(_get_conn(), eid, name="新名字")
        self.assertFalse(os.path.exists(fp), "改名后缓存文件应被删除")

    def test_change_url_path_removes_old_cache_file(self):
        """修改 API 端点 URL 后旧路径缓存文件被删除。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/old-path")
        fp = self._write_cache_file("/api/old-path")
        db.update_api_endpoint(_get_conn(), eid, url_path="/api/new-path")
        self.assertFalse(os.path.exists(fp), "修改 URL 后旧路径缓存文件应被删除")

    def test_any_config_change_removes_cache_file(self):
        """任意配置字段变更（columns/filters/row_limit 等）后缓存文件被删除。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/cfg-change")
        fp = self._write_cache_file("/api/cfg-change")
        self.assertTrue(os.path.exists(fp))
        db.update_api_endpoint(_get_conn(), eid, filters='[{"col":"status","op":"eq","val":"active"}]')
        self.assertFalse(os.path.exists(fp), "修改 filters 后缓存文件应被删除")

        fp2 = self._write_cache_file("/api/cfg-change")
        db.update_api_endpoint(_get_conn(), eid, row_limit=10)
        self.assertFalse(os.path.exists(fp2), "修改 row_limit 后缓存文件应被删除")

        fp3 = self._write_cache_file("/api/cfg-change")
        db.update_api_endpoint(_get_conn(), eid, output_format="csv")
        self.assertFalse(os.path.exists(fp3), "修改 output_format 后缓存文件应被删除")

    def test_no_change_does_not_invalidate(self):
        """无实际字段变更（空更新）时不应删除缓存文件。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid, url_path="/api/no-change")
        fp = self._write_cache_file("/api/no-change")
        self.assertTrue(os.path.exists(fp))
        ok = db.update_api_endpoint(_get_conn(), eid)
        self.assertFalse(ok, "无字段变更应返回 False")
        self.assertTrue(os.path.exists(fp), "空更新不应删除缓存文件")

    def test_delete_endpoints_by_report_removes_cache_files(self):
        """删除报表下所有端点时，对应缓存文件全部被删除。"""
        rid = self._create_report()
        self._create_endpoint(report_id=rid, url_path="/api/batch-a")
        self._create_endpoint(report_id=rid, url_path="/api/batch-b")
        fp_a = self._write_cache_file("/api/batch-a")
        fp_b = self._write_cache_file("/api/batch-b")
        db.delete_api_endpoints_by_report(_get_conn(), rid)
        self.assertFalse(os.path.exists(fp_a), "批量删除后 a 缓存应删除")
        self.assertFalse(os.path.exists(fp_b), "批量删除后 b 缓存应删除")


class TestStaticCacheModule(unittest.TestCase):
    """static_cache 模块单元测试（路径映射/穿越/原子写/失效记录）。"""

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_resolve_file_path_normal(self, _m):
        """常规路径映射为 {dir}/{url_path}.json。"""
        p = static_cache.resolve_file_path("api/cust")
        self.assertEqual(p, os.path.realpath(os.path.join(_CACHE_DIR, "api/cust.json")))
        p2 = static_cache.resolve_file_path("api/nested/path")
        self.assertEqual(p2, os.path.realpath(
            os.path.join(_CACHE_DIR, "api/nested/path.json")))

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_resolve_file_path_traversal_rejected(self, _m):
        """`..` 穿越到配置目录外的路径返回 None。"""
        for bad in ("../evil", "a/../../evil", "api/../../evil", "../../../etc/passwd"):
            self.assertIsNone(static_cache.resolve_file_path(bad))

    @patch("app_config.get_config", return_value={})
    def test_config_defaults(self, _m):
        """配置段缺失时按默认值（enable=True、dir=static_cache）。"""
        cfg = static_cache.get_static_cache_config()
        self.assertTrue(cfg["enable"])
        self.assertEqual(cfg["dir"], "static_cache")

    @patch("app_config.get_config",
           return_value={"static_cache": {"enable": False, "dir": "/tmp/sc"}})
    def test_config_custom(self, _m):
        """配置段存在时按配置取值。"""
        cfg = static_cache.get_static_cache_config()
        self.assertFalse(cfg["enable"])
        self.assertEqual(cfg["dir"], "/tmp/sc")

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_write_file_atomic(self, _m):
        """原子写：临时文件 + os.replace，覆盖写不损坏。"""
        p = static_cache.resolve_file_path("api/atomic")
        self.assertTrue(static_cache.write_file(p, '{"a": 1}'))
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"a": 1}')
        self.assertTrue(static_cache.write_file(p, '{"a": 2}'))
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"a": 2}')
        # 子目录自动创建
        p2 = static_cache.resolve_file_path("a/b/c")
        self.assertTrue(static_cache.write_file(p2, "{}"))
        self.assertTrue(os.path.isfile(p2))

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_write_file_failure_silent(self, _m):
        """写入失败（目标父路径被普通文件占用）静默降级返回 False。"""
        blocker = os.path.join(_CACHE_DIR, "blocker")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")
        self.assertFalse(static_cache.write_file(
            os.path.join(blocker, "sub", "x.json"), "{}"))

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_try_read_version_and_ttl(self, _m):
        """命中判定：版本不一致/过期/缺失均返回 None。"""
        p = static_cache.resolve_file_path("api/ttl")
        static_cache.write_file(p, '{"meta": {"config_version": "v1"}, "data": []}')
        self.assertIsNotNone(static_cache.try_read(p, "v1", 0))
        self.assertIsNone(static_cache.try_read(p, "v2", 0), "版本不一致应 miss")
        # TTL=1 小时，mtime 拨回 2 小时 → 过期
        old = os.path.getmtime(p)
        os.utime(p, (old - 7200, old - 7200))
        self.assertIsNone(static_cache.try_read(p, "v1", 1), "TTL 过期应 miss")
        self.assertIsNotNone(static_cache.try_read(p, "v1", 0), "TTL=0 永不过期")
        self.assertIsNone(static_cache.try_read(os.path.join(_CACHE_DIR, "missing.json"),
                                                "v1", 0), "缺失应 miss")

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_try_read_corrupted_json_returns_none(self, _m):
        """缺口 24：缓存文件损坏（非法 JSON）/空文件 → try_read 视为 miss 返回 None。"""
        p = static_cache.resolve_file_path("api/corrupt")
        static_cache.write_file(p, "{{{broken json")
        self.assertIsNone(static_cache.try_read(p, "v1", 0),
                          "损坏 JSON 应视为 miss")

        static_cache.write_file(p, "")
        self.assertIsNone(static_cache.try_read(p, "v1", 0),
                          "空文件应视为 miss")

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_try_read_versioned_file(self, _m):
        """无 meta 内容：版本体现在文件名，版本前缀匹配才命中。"""
        p = static_cache.resolve_file_path("api/verfile")
        content = '{"rows": []}'
        self.assertTrue(static_cache.write_versioned_file(p, "abc12345", content))
        # 版本前缀一致 → 命中（版本文件与稳定文件双写）
        self.assertEqual(static_cache.try_read(p, "abc12345" * 4, 0), content)
        self.assertTrue(os.path.isfile(p), "稳定文件应同步写入")
        version_path = os.path.join(_CACHE_DIR, "api", "verfile.vabc12345.json")
        self.assertTrue(os.path.isfile(version_path), "版本文件应写入")
        # 版本前缀不一致 → miss（改库即版本变化）
        self.assertIsNone(static_cache.try_read(p, "deadbeef" * 4, 0))
        # 旧版本文件被清理，仅保留当前版本
        stale = os.path.join(_CACHE_DIR, "api", "verfile.v99999999.json")
        with open(stale, "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertTrue(static_cache.write_versioned_file(p, "def01234", "{}"))
        self.assertFalse(os.path.exists(stale), "旧版本文件应被清理")

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_invalidate_removes_versioned_files(self, _m):
        """invalidate 同时删除稳定文件与全部版本文件（refresh 联动生效）。"""
        p = static_cache.resolve_file_path("api/verinv")
        static_cache.write_versioned_file(p, "abc12345", "{}")
        stale = os.path.join(_CACHE_DIR, "api", "verinv.v99999999.json")
        with open(stale, "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertTrue(static_cache.invalidate("api/verinv"))
        self.assertFalse(os.path.exists(p), "稳定文件应删除")
        self.assertFalse(os.path.exists(
            os.path.join(_CACHE_DIR, "api", "verinv.vabc12345.json")),
            "版本文件应删除")
        self.assertFalse(os.path.exists(stale), "残留旧版本文件应一并删除")

    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_invalidate_idempotent(self, _m):
        """invalidate 删除文件且幂等。"""
        p = static_cache.resolve_file_path("api/inv")
        static_cache.write_file(p, "{}")
        self.assertTrue(static_cache.invalidate("api/inv"))
        self.assertFalse(os.path.exists(p))
        self.assertTrue(static_cache.invalidate("api/inv"), "文件不存在仍应幂等返回")

    def test_record_invalidated(self):
        """失效时刻进程内存记录：无记录返回 None。"""
        self.assertIsNone(static_cache.get_last_invalidated("api/never"))
        static_cache.record_invalidated("api/x")
        self.assertIsNotNone(static_cache.get_last_invalidated("api/x"))


class TestPermissionsRoot(unittest.TestCase):
    """permissions_root()：权限调整根目录 = {dir}/api（缓存实际落点）。

    产品约束：API 端点 URL 必须以 /api/ 开头，缓存文件全部落在 {dir}/api 下，
    file_permissions 只以该子目录为权限起点，不得波及 dir 内其他内容。
    """

    @patch("app_config.get_config",
           return_value={"static_cache": {"enable": True,
                                          "dir": "/var/cache/sr"}})
    def test_absolute_dir_appends_api(self, _m):
        """绝对路径 dir → {dir}/api。"""
        self.assertEqual(static_cache.permissions_root(),
                         os.path.realpath("/var/cache/sr/api"))

    @patch("app_config.get_config",
           return_value={"static_cache": {"enable": True,
                                          "dir": "/var/cache/sr/"}})
    def test_trailing_slash_normalised(self, _m):
        """dir 带尾斜杠 → 归一化后仍为 {dir}/api。"""
        self.assertEqual(static_cache.permissions_root(),
                         os.path.realpath("/var/cache/sr/api"))

    @patch("app_config.get_config",
           return_value={"static_cache": {"enable": True,
                                          "dir": "cache_rel"}})
    def test_relative_dir_resolved(self, _m):
        """相对路径 dir → realpath 解析后追加 api。"""
        self.assertEqual(static_cache.permissions_root(),
                         os.path.realpath(os.path.join("cache_rel", "api")))

    @patch("app_config.get_config", return_value={})
    def test_default_dir(self, _m):
        """配置缺失 → 默认 dir=static_cache → static_cache/api。"""
        self.assertEqual(static_cache.permissions_root(),
                         os.path.realpath(os.path.join("static_cache", "api")))


if __name__ == "__main__":
    unittest.main()
