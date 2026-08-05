"""
test_api_endpoint_preview.py — API 端点真实数据预览（工单 05）测试

测试策略：
- 直接调用 config.handle_api_endpoint_preview 单元级验证
- Mock db.create_mysql_connection 返回固定结果集
- 各测试内联建表 DDL（避免循环导入）
"""

import unittest
import unittest.mock
import json
import sqlite3
import urllib.parse

import config
import report as report_mod
from tests.test_mysql_mock import MockMySQLMixin

_q = urllib.parse.quote


def _mk_conn():
    """内存 SQLite 配置库：池 + 报表 + 端点。返回 (conn, endpoint_id)。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL, password TEXT NOT NULL,
            database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, category_id INTEGER, memo TEXT,
            result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE api_endpoints (
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
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '');
    """)
    conn.execute("INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
                 "VALUES ('测试池','127.0.0.1',3306,'root','pass','testdb',1)")
    conn.execute("INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,"
                 "prefer_cache,cache_ttl_hours,sort_order) "
                 "VALUES ('测试报表','SELECT * FROM users',20,1,0,0,1)")
    conn.execute("INSERT INTO api_endpoints (report_id,name,url_path,output_format,row_limit,"
                 "enabled,result_mode,result_index,allow_fetch_all,static_cache) "
                 "VALUES (1,'预览端点','/api/preview-ep','json',0,1,'single',0,1,1)")
    conn.commit()
    eid = conn.execute("SELECT id FROM api_endpoints").fetchone()[0]
    return conn, eid


class TestApiEndpointPreview(MockMySQLMixin, unittest.TestCase):
    """真实数据预览 handler 单元测试"""

    def setUp(self):
        self._patch = unittest.mock.patch("db.create_mysql_connection")
        self._factory = self._patch.start()
        self.addCleanup(self._patch.stop)
        self.conn, self.eid = _mk_conn()
        self.addCleanup(self.conn.close)
        # 清空进程内查询缓存：预览复用 execute_report，缓存的 key 是
        # (report_id, sql_query)，与本测试 SQL 相同，前序测试写入的缓存
        # 会绕过 mock cursor（description/side_effect 不生效）
        report_mod._query_cache.clear()

        self.mock_conn, self.mock_cursor = self.make_mock_connection()
        self.mock_cursor.description = [("id",), ("name",), ("age",), ("status",)]
        self.mock_cursor.fetchall.return_value = [
            (1, "张三", 25, "active"),
            (2, "李四", 30, "inactive"),
            (3, "王五", 35, "active"),
            (4, "赵六", 40, "active"),
        ]
        self._factory.return_value = self.mock_conn

    def _preview(self, form=None, template=None, result_mode="single",
                 result_index="0", row_limit="0", rule_json=""):
        """执行预览并返回 (code, headers, 解析后 JSON)。"""
        if form is None:
            form = "&".join([
                "json_template=" + _q(template or ""),
                "rule_json=" + _q(rule_json),
                "result_mode=" + result_mode,
                "result_index=" + result_index,
                "row_limit=" + row_limit,
            ])
        code, body, headers = config.handle_api_endpoint_preview(
            self.conn, 1, self.eid, form)
        return code, headers, json.loads(body)

    # ------------------------------------------------------------------
    # 成功路径
    # ------------------------------------------------------------------

    def test_preview_success_with_template(self):
        """模板渲染成功：真实 total + 最多 3 行数据。"""
        _, headers, resp = self._preview(
            template='{"total": {{total}}, "rows": {{data}}}')
        self.assertEqual(resp["ok"], True)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        out = json.loads(resp["output"])
        self.assertEqual(out["total"], 4)  # 真实总数，非 3 行截断数
        self.assertEqual(len(out["rows"]), 3)
        self.assertEqual(out["rows"][0]["name"], "张三")

    def test_preview_empty_template_default_output(self):
        """空模板时输出默认格式 {"data": ..., "total": ...}。"""
        _, _, resp = self._preview(template="")
        self.assertEqual(resp["ok"], True)
        out = json.loads(resp["output"])
        self.assertEqual(out["total"], 4)
        self.assertEqual(len(out["data"]), 3)

    def test_preview_all_mode(self):
        """all 模式：输出 results 数组 + mode。"""
        _, _, resp = self._preview(template='{"mode": {{mode}}, "r": {{results}}}',
                                   result_mode="all")
        self.assertEqual(resp["ok"], True)
        out = json.loads(resp["output"])
        self.assertEqual(out["mode"], "all")
        self.assertEqual(len(out["r"]), 1)

    def test_preview_rule_json_columns_injection(self):
        """表单 rule_json 的 columns 注入生效（未保存的临时规则）。"""
        _, _, resp = self._preview(template='{"rows": {{data}}}',
                                   rule_json='{"columns":"id,name"}')
        self.assertEqual(resp["ok"], True)
        out = json.loads(resp["output"])
        self.assertEqual(list(out["rows"][0].keys()), ["id", "name"])

    def test_preview_row_limit_form_value_ignored(self):
        """表单 row_limit=100 不得放大预览行数（硬上限 3 行）。"""
        _, _, resp = self._preview(template='{"a": {{data}}}', row_limit="100")
        self.assertEqual(resp["ok"], True)
        self.assertEqual(len(json.loads(resp["output"])["a"]), 3)

    def test_preview_json_response_header(self):
        """响应头 Content-Type 为 application/json。"""
        code, headers, _ = self._preview()
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")

    # ------------------------------------------------------------------
    # 错误路径
    # ------------------------------------------------------------------

    def test_preview_unknown_placeholder_error(self):
        """未知占位符：ok=False + 含行号列号的错误消息。"""
        _, _, resp = self._preview(template='{"bad": {{unknown_key}}}')
        self.assertEqual(resp["ok"], False)
        self.assertIn("未知占位符", resp["error"])
        self.assertIn("第 1 行", resp["error"])

    def test_preview_invalid_template_error(self):
        """模板非法 JSON：ok=False。"""
        _, _, resp = self._preview(template='{"unclosed": ')
        self.assertEqual(resp["ok"], False)
        self.assertIn("JSON", resp["error"])

    def test_preview_endpoint_not_found(self):
        """端点不存在：ok=False。"""
        code, body, _ = config.handle_api_endpoint_preview(
            self.conn, 1, 9999, "json_template=&result_mode=single")
        resp = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(resp["ok"], False)
        self.assertIn("不存在", resp["error"])

    def test_preview_result_index_out_of_range(self):
        """result_index 越界：ok=False。"""
        _, _, resp = self._preview(result_index="5")
        self.assertEqual(resp["ok"], False)
        self.assertIn("超出范围", resp["error"])

    def test_preview_query_failure(self):
        """数据库异常：ok=False 且不抛 500 外错误。"""
        self.mock_cursor.execute.side_effect = RuntimeError("连接失败")
        _, _, resp = self._preview()
        self.assertEqual(resp["ok"], False)
        self.assertIn("连接失败", resp["error"])

    def test_preview_no_description(self):
        """服务器不返回列描述（description=None）：按无结果集处理，ok=False。"""
        self.mock_cursor.description = None
        self.mock_cursor.fetchall.return_value = []
        _, _, resp = self._preview(template='{"rows": {{data}}}')
        self.assertEqual(resp["ok"], False)
        self.assertIn("未返回任何结果集", resp["error"])

    # ------------------------------------------------------------------
    # 渲染完整性
    # ------------------------------------------------------------------

    def test_form_html_contains_live_preview_button_edit_mode(self):
        """编辑态表单含真实数据预览按钮。"""
        html = config.build_api_endpoint_form_html(1, "测试报表", {}, None,
                                                   ["结果"], 1, self.eid, True)
        self.assertIn("preview-live-btn", html)
        self.assertIn(f"/config/reports/1/api_endpoints/{self.eid}/preview", html)

    def test_form_html_no_button_add_mode(self):
        """新增态表单不含真实数据预览按钮。"""
        html = config.build_api_endpoint_form_html(1, "测试报表", {}, None,
                                                   ["结果"], 1, None, False)
        self.assertNotIn('id="preview-live-btn"', html)
        self.assertNotIn("/preview", html)

    def test_preview_error_page_renders(self):
        """直接 GET 打开预览地址（无表单）：返回可交互指引页。"""
        code, body, headers = config.handle_api_endpoint_preview(self.conn, 1, self.eid, "")
        self.assertEqual(code, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn("返回编辑页", body)
        self.assertIn(f"/config/reports/1/api_endpoints/{self.eid}/edit", body)


if __name__ == "__main__":
    unittest.main()
