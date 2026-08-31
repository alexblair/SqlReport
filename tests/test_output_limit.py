"""test_output_limit.py — 全量输出护栏表单与透传（PH-07）

覆盖矩阵见 .scratch/product-hardening/issues/PH-07.md：
- CT-01~03：config_db add/update 写入 allow_all_output/max_rows（默认与缺省兼容）
- FT-01~07：表单渲染（新建默认 0 / 存量回显 1 / max_rows 输入）/提交落库/confirm/非法值
- PT-01~02：报表页截断提示条
- ET-01~07：导出截断与 X-Export-Truncated 响应头
- AT-01~05：API truncated 标记（单/all/静态 config_version）
- RT-01~02：缓存策略校验（截断缓存/快照在开启全量输出时丢弃重建）
"""

import unittest
import sqlite3
import json
from unittest.mock import patch, MagicMock

import config
import db
import export
import api_handler
import report
import redis_cache
from report import ReportResult


def _make_conn():
    """创建带完整表结构的测试内存数据库（config + api 域）。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL,
            password TEXT NOT NULL,
            database TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL);
        CREATE TABLE report_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL,
            default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER,
            category_id INTEGER,
            memo TEXT,
            result_names TEXT DEFAULT '',
            prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            allow_write INTEGER NOT NULL DEFAULT 1,
            allow_all_output INTEGER NOT NULL DEFAULT 1,
            max_rows INTEGER NOT NULL DEFAULT 100000,
            keepalive_enabled INTEGER NOT NULL DEFAULT 0,
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL);
        CREATE TABLE sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at REAL NOT NULL);
        CREATE TABLE api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url_path TEXT UNIQUE NOT NULL,
            output_format TEXT NOT NULL DEFAULT 'json',
            columns TEXT,
            filters TEXT,
            sorts TEXT,
            row_limit INTEGER DEFAULT 0,
            api_key TEXT,
            allowed_origins TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
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
        nested_filter    TEXT,
            FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE);
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE);
    """)
    return conn


def _add_pool(conn, name="池"):
    return db.add_pool(conn, name, "h", 3306, "u", "p", "d")


# ===================================================================
# config_db 层：add/update 写入
# ===================================================================


class TestConfigDbOutputLimit(unittest.TestCase):
    """CT：add_report / update_report 写入 allow_all_output / max_rows。"""

    def setUp(self):
        self.conn = _make_conn()
        self.pool_id = _add_pool(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_add_report_defaults(self):
        """CT-01：新建默认 allow_all_output=0、max_rows=100000（写护栏）。"""
        rid = db.add_report(self.conn, "R", "SELECT 1", 20, self.pool_id)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 0)
        self.assertEqual(r["max_rows"], 100000)

    def test_add_report_explicit_values(self):
        """CT-01：显式传 allow_all_output/max_rows 落库。"""
        rid = db.add_report(self.conn, "R", "SELECT 1", 20, self.pool_id,
                            allow_all_output=1, max_rows=5000)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 1)
        self.assertEqual(r["max_rows"], 5000)

    def test_update_report_values(self):
        """CT-02：update_report 写入两字段。"""
        rid = db.add_report(self.conn, "R", "SELECT 1", 20, self.pool_id)
        ok = db.update_report(self.conn, rid, "R2", "SELECT 2", 20, self.pool_id,
                              allow_all_output=1, max_rows=888)
        self.assertTrue(ok)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 1)
        self.assertEqual(r["max_rows"], 888)

    def test_update_report_legacy_defaults(self):
        """CT-03：update_report 缺省参数保持存量语义（allow_all_output=1）。"""
        rid = db.add_report(self.conn, "R", "SELECT 1", 20, self.pool_id)
        db.update_report(self.conn, rid, "R2", "SELECT 2", 20, self.pool_id)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 1)
        self.assertEqual(r["max_rows"], 100000)


# ===================================================================
# config.py 表单层：渲染与提交
# ===================================================================


class TestReportFormOutputLimit(unittest.TestCase):
    """FT：报表表单的 allow_all_output / max_rows 渲染与提交。"""

    def setUp(self):
        self.conn = _make_conn()
        self.pool_id = _add_pool(self.conn)

    def tearDown(self):
        self.conn.close()

    def _form(self, path):
        code, body, _ = config.handle_request(self.conn, "GET", path, "")
        self.assertEqual(code, 200)
        return body

    def test_new_form_switch_off_by_default(self):
        """FT-01：新建表单默认关闭（hidden 0 + checkbox 未勾选）+ max_rows 默认。"""
        body = self._form("/config/reports/add")
        self.assertIn('<input type="hidden" name="allow_all_output" value="0">', body)
        self.assertIn('name="allow_all_output" value="1">', body)
        self.assertNotIn('name="allow_all_output" value="1" checked>', body)
        self.assertIn('name="max_rows" value="100000"', body)
        self.assertNotIn("确定开启全部输出", body, "关闭状态不显示开启 confirm")

    def test_edit_form_legacy_checked(self):
        """FT-02：编辑存量报表（allow_all_output=1）→ checkbox 勾选 + confirm。"""
        rid = db.add_report(self.conn, "存量", "SELECT 1", 20, self.pool_id,
                            allow_all_output=1)
        body = self._form(f"/config/reports/{rid}/edit")
        self.assertIn('name="allow_all_output" value="1" checked>', body)
        self.assertIn("确定开启全部输出", body, "开启状态保存前 confirm")

    def test_edit_form_off_state_no_confirm(self):
        """FT-02：编辑关闭状态的报表 → 无开启 confirm。"""
        rid = db.add_report(self.conn, "关闭", "SELECT 1", 20, self.pool_id,
                            allow_all_output=0)
        body = self._form(f"/config/reports/{rid}/edit")
        self.assertNotIn("确定开启全部输出", body)

    def test_edit_form_shows_max_rows(self):
        """FT-02：编辑表单回显 max_rows 原值。"""
        rid = db.add_report(self.conn, "上限", "SELECT 1", 20, self.pool_id,
                            max_rows=4321)
        body = self._form(f"/config/reports/{rid}/edit")
        self.assertIn('name="max_rows" value="4321"', body)

    def test_submit_add_with_values(self):
        """FT-03：新建提交勾选 + max_rows → 落库。"""
        form = ("name=新报表&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&allow_all_output=0&allow_all_output=1&max_rows=2500")
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        r = db.get_all_reports(self.conn)[0]
        self.assertEqual(r["allow_all_output"], 1)
        self.assertEqual(r["max_rows"], 2500)

    def test_submit_add_defaults(self):
        """FT-04：新建不携带字段 → 默认关闭 + max_rows=100000。"""
        form = ("name=默认报表&sql_query=SELECT 1&default_page_size=20&pool_id=1")
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        r = db.get_all_reports(self.conn)[0]
        self.assertEqual(r["allow_all_output"], 0)
        self.assertEqual(r["max_rows"], 100000)

    def test_submit_edit_values(self):
        """FT-05：编辑提交开关与上限 → 更新落库。"""
        rid = db.add_report(self.conn, "被编辑", "SELECT 1", 20, self.pool_id,
                            allow_all_output=0, max_rows=100000)
        form = ("name=被编辑&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&allow_all_output=0&allow_all_output=1&max_rows=999")
        code, body, _ = config.handle_request(
            self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 302)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 1)
        self.assertEqual(r["max_rows"], 999)

    def test_submit_max_rows_invalid_falls_back(self):
        """FT-06：max_rows 非法值 → 回退默认 100000（不 500）。"""
        form = ("name=非法上限&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&allow_all_output=0&max_rows=abc")
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        r = db.get_all_reports(self.conn)[0]
        self.assertEqual(r["max_rows"], 100000)

    def test_submit_edit_switch_off(self):
        """FT-05：编辑把开启改为关闭（0 覆盖 1 的存量值）。"""
        rid = db.add_report(self.conn, "改关闭", "SELECT 1", 20, self.pool_id,
                            allow_all_output=1)
        form = ("name=改关闭&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&allow_all_output=0&max_rows=50")
        code, body, _ = config.handle_request(
            self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 302)
        r = db.get_report(self.conn, rid)
        self.assertEqual(r["allow_all_output"], 0)
        self.assertEqual(r["max_rows"], 50)

    def test_parse_report_form_last_value_wins(self):
        """FT-07：_parse_report_form 重复键取最后一个（hidden 0 + checkbox 1）。"""
        from config import _parse_report_form
        rf = _parse_report_form({"allow_all_output": "0", "allow_all_output": "1",
                                 "max_rows": "77"})
        self.assertEqual(rf["allow_all_output"], 1)
        self.assertEqual(rf["max_rows"], 77)
        rf2 = _parse_report_form({})
        self.assertEqual(rf2["allow_all_output"], 0)
        self.assertEqual(rf2["max_rows"], 100000)


# ===================================================================
# 导出：截断与响应头
# ===================================================================


class TestExportOutputLimit(unittest.TestCase):
    """ET：导出 max_rows 截断 + X-Export-Truncated 头。"""

    def setUp(self):
        self.conn = _make_conn()
        self.pool_id = _add_pool(self.conn)
        self.mock_pool = {"host": "h", "port": 3306,
                          "user": "u", "password": "p", "database": "d"}

    def tearDown(self):
        self.conn.close()

    def _export(self, report_cfg_extra, query, n_rows):
        """构造报表 + mock MySQL 返回 n 行，执行 handle_export。"""
        rid = db.add_report(self.conn, "导出报表", "SELECT * FROM t", 20,
                            self.pool_id, **report_cfg_extra)
        with patch("db.create_mysql_connection") as mock_conn_f:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = [(i,) for i in range(n_rows)]
            mock_conn_f.return_value = mock_conn
            return export.handle_export(self.conn, f"id={rid}&{query}",
                                        pool_override=self.mock_pool)

    def test_csv_truncates_and_marks(self):
        """ET-01：关闭全量输出 + 超限 → 截断 + X-Export-Truncated: true。

        ♻️ 契约变更(spec ux-optimization 批次1#4)：文件末尾追加截断注释行，
        行数 = 表头 + 5 行数据 + 1 注释行。
        """
        code, content, headers = self._export(
            {"allow_all_output": 0, "max_rows": 5}, "charset=utf8", 8)
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("X-Export-Truncated"), "true")
        text = content.decode("utf-8")
        self.assertEqual(text.count("\n"), 7, "表头 + 5 行数据 + 截断注释行")
        note_line = text.rstrip("\n").split("\n")[-1]
        self.assertIn("#", note_line)
        self.assertIn("截断", note_line)
        self.assertIn("5", note_line)

    def test_csv_no_header_under_limit(self):
        """ET-02：行数未超限 → 无截断头。"""
        code, content, headers = self._export(
            {"allow_all_output": 0, "max_rows": 5}, "charset=utf8", 3)
        self.assertEqual(code, 200)
        self.assertNotIn("X-Export-Truncated", headers)
        text = content.decode("utf-8")
        self.assertEqual(text.count("\n"), 4, "表头 + 3 行数据")

    def test_csv_no_header_allow_all(self):
        """ET-03：开启全量输出 → 不截断、无头。"""
        code, content, headers = self._export(
            {"allow_all_output": 1, "max_rows": 5}, "charset=utf8", 8)
        self.assertEqual(code, 200)
        self.assertNotIn("X-Export-Truncated", headers)
        self.assertEqual(content.decode("utf-8").count("\n"), 9)

    def test_csv_no_header_legacy_report(self):
        """ET-04：存量报表（缺字段）→ 按存量语义不截断、无头。"""
        code, content, headers = self._export({}, "charset=utf8", 8)
        self.assertEqual(code, 200)
        self.assertNotIn("X-Export-Truncated", headers)
        self.assertEqual(content.decode("utf-8").count("\n"), 9)

    def test_json_truncates_and_marks(self):
        """ET-05：JSON 导出同样截断 + 头。"""
        code, content, headers = self._export(
            {"allow_all_output": 0, "max_rows": 4}, "format=json&charset=utf8", 7)
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("X-Export-Truncated"), "true")
        data = json.loads(content.decode("utf-8"))
        self.assertEqual(len(data["导出报表"]), 4)

    def test_zip_truncates_and_marks(self):
        """ET-06：ZIP 导出同样带截断头。"""
        code, content, headers = self._export(
            {"allow_all_output": 0, "max_rows": 2}, "charset=utf8&zip=1", 6)
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("X-Export-Truncated"), "true")


# ===================================================================
# API：truncated 标记透传
# ===================================================================


class TestApiTruncatedFlag(unittest.TestCase):
    """AT：API 响应 truncated 标记（缺省不出现，不破坏契约）。"""

    def setUp(self):
        self.conn = _make_conn()
        self.pool_id = _add_pool(self.conn)
        self.rid = db.add_report(self.conn, "API报表", "SELECT 1", 20, self.pool_id)
        self.endpoint = {
            "report_id": self.rid, "result_mode": "single", "result_index": 0,
            "output_format": "json", "row_limit": 0, "allow_fetch_all": 1,
            "json_template": None, "columns": None, "filters": None,
            "sorts": None, "static_cache": 0,
        }

    def tearDown(self):
        self.conn.close()

    def test_format_json_truncated_key_absent_by_default(self):
        """AT-01：缺省 truncated=False → 响应无 truncated 键（契约不破坏）。"""
        status, body, _ = api_handler._format_json_response(
            [{"id": 1}], 1, 1, 20, 1)
        self.assertEqual(status, 200)
        resp = json.loads(body)
        self.assertNotIn("truncated", resp)

    def test_format_json_truncated_key_present(self):
        """AT-01：truncated=True → 响应含 "truncated": true。"""
        status, body, _ = api_handler._format_json_response(
            [{"id": 1}], 1, 1, 20, 1, truncated=True)
        resp = json.loads(body)
        self.assertIs(resp["truncated"], True)

    @patch("api_handler.execute_report")
    def test_single_mode_truncated_through_normal_request(self, mock_exec):
        """AT-02：单结果集截断 → 普通 API 链路响应体含 truncated。"""
        mock_exec.return_value = ReportResult(
            [{"columns": ["id"], "rows": [(1,)], "total": 1}],
            0, 1, 20, truncated=True)
        status, body, _ = api_handler._run_normal_api_request(
            self.conn, self.endpoint, "GET", "", {}, {"Accept": "application/json"})
        self.assertEqual(status, 200)
        resp = json.loads(body)
        self.assertIs(resp["truncated"], True)

    @patch("api_handler.execute_report")
    def test_single_mode_not_truncated_no_key(self, mock_exec):
        """AT-02：未截断 → 响应无 truncated 键。"""
        mock_exec.return_value = ReportResult(
            [{"columns": ["id"], "rows": [(1,)], "total": 1}],
            0, 1, 20)
        status, body, _ = api_handler._run_normal_api_request(
            self.conn, self.endpoint, "GET", "", {}, {"Accept": "application/json"})
        resp = json.loads(body)
        self.assertNotIn("truncated", resp)

    @patch("api_handler.execute_report")
    def test_all_mode_top_level_truncated(self, mock_exec):
        """AT-03：result_mode=all 截断 → 顶层 truncated。"""
        ep = dict(self.endpoint, result_mode="all")
        mock_exec.return_value = ReportResult(
            [{"columns": ["id"], "rows": [(1,)], "total": 1}],
            -1, 1, 20, truncated=True)
        status, body, _ = api_handler._run_normal_api_request(
            self.conn, ep, "GET", "", {}, {"Accept": "application/json"})
        self.assertEqual(status, 200)
        resp = json.loads(body)
        self.assertIs(resp["truncated"], True)
        self.assertEqual(resp["mode"], "all")

    def test_static_config_version_changes_with_policy(self):
        """AT-04：静态缓存版本纳入 allow_all_output/max_rows。"""
        report_cfg = {"sql_query": "SELECT 1", "pool_id": self.pool_id,
                      "allow_all_output": 0, "max_rows": 100000}
        v1 = api_handler._compute_static_config_version(self.endpoint, report_cfg)
        report_cfg2 = dict(report_cfg, allow_all_output=1)
        report_cfg3 = dict(report_cfg, max_rows=50000)
        self.assertNotEqual(v1, api_handler._compute_static_config_version(
            self.endpoint, report_cfg2))
        self.assertNotEqual(v1, api_handler._compute_static_config_version(
            self.endpoint, report_cfg3))
        report_cfg4 = dict(report_cfg, max_rows=50000, allow_all_output=1)
        self.assertEqual(
            api_handler._compute_static_config_version(self.endpoint, report_cfg4),
            api_handler._compute_static_config_version(
                self.endpoint, dict(report_cfg4)))
        self.assertNotEqual(v1, api_handler._compute_static_config_version(
            self.endpoint, report_cfg4))


# ===================================================================
# 报表页：截断提示条
# ===================================================================


class TestReportPageBanner(unittest.TestCase):
    """PT：报表页截断提示条渲染。"""

    def setUp(self):
        self.conn = _make_conn()
        self.pool_id = _add_pool(self.conn)

    def tearDown(self):
        self.conn.close()

    def _result(self, truncated):
        return ReportResult(
            [{"columns": ["id"], "rows": [(i,) for i in range(3)],
              "total": 3}],
            0, 1, 20, truncated=truncated)

    def test_banner_shown_when_truncated(self):
        """PT-01：truncated=True → 页面含提示条与 max_rows 数字。"""
        rid = db.add_report(self.conn, "截断报表", "SELECT 1", 20, self.pool_id,
                            allow_all_output=0, max_rows=5000)
        r = db.get_report(self.conn, rid)
        html = report._build_report_html(
            self.conn, r, self._result(True), {"name": "池"})
        self.assertIn("已截断显示前 5000 行", html)
        self.assertIn("允许全部输出", html)

    def test_banner_hidden_when_not_truncated(self):
        """PT-02：未截断 → 页面无提示条。"""
        rid = db.add_report(self.conn, "正常报表", "SELECT 1", 20, self.pool_id,
                            allow_all_output=0, max_rows=5000)
        r = db.get_report(self.conn, rid)
        html = report._build_report_html(
            self.conn, r, self._result(False), {"name": "池"})
        self.assertNotIn("已截断显示", html)


# ===================================================================
# 缓存策略校验：Redis 截断快照在开启全量输出时丢弃重建
# ===================================================================


class TestRedisSnapshotPolicy(unittest.TestCase):
    """RT：截断快照（truncated=True）+ 当前全量策略 → 丢弃重建。"""

    def setUp(self):
        report._query_cache.clear()
        self.pool = {"host": "h", "port": 3306, "user": "u",
                     "password": "p", "database": "d"}
        self.report_cfg = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                           "sql_query": "SELECT saved", "name": "R",
                           "memo": "", "result_names": "",
                           "allow_all_output": 1, "max_rows": 5}

    def tearDown(self):
        report._query_cache.clear()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_truncated_snapshot_discarded_when_full_policy(
            self, mock_avail, mock_mgr_f, mock_conn_f, mock_query):
        """RT-01：快照 truncated=True + allow_all_output=1 → 不命中，重查 MySQL 取全量。"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(1,), (2,)]}],
            sql_query="SELECT saved", updated_at=123.0, config_version="v1",
            truncated=True)
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = snap
        mock_mgr_f.return_value = mock_mgr
        mock_conn_f.return_value = MagicMock()
        mock_query.return_value = [{"columns": ["id"], "rows": [(i,) for i in range(7)]}]

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        mock_query.assert_called_once(), "截断快照被丢弃 → 发生 MySQL 重建"
        self.assertEqual(result.total, 7, "全量策略丢弃截断快照，重查取回全量")
        self.assertIsNone(result.truncated)
        mock_mgr.set_snapshot.assert_called_once(), "重建后全量数据写回快照"

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_full_snapshot_still_hits_under_truncate_policy(
            self, mock_avail, mock_mgr_f, mock_conn_f, mock_query):
        """RT-02：快照 truncated=False + 当前截断策略 → 命中快照并按 max_rows 兜底截断。"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(i,) for i in range(9)]}],
            sql_query="SELECT saved", updated_at=123.0, config_version="v1",
            truncated=False)
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = snap
        mock_mgr_f.return_value = mock_mgr
        cfg = dict(self.report_cfg, allow_all_output=0, max_rows=5)

        result = report.execute_report(1, "SELECT saved", self.pool, report=cfg)

        self.assertEqual(result.total, 5, "快照命中并按 max_rows 兜底截断")
        self.assertIs(result.truncated, True)
        mock_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
