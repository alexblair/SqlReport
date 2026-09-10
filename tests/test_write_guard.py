"""
test_write_guard.py — PH-05 (T3b) 写操作护栏测试

覆盖矩阵（PH-05.md 功能点 → 测试方法）：
- 功能点 1（新建可预览）→ TestReportFormWriteGuard.test_add_form_has_preview_button /
  test_copy_form_has_preview_button；TestPreviewWithoutId（无 id + pool_id + sql_query 预览）
- 功能点 2（表单开关与警示）→ TestReportFormWriteGuard（checkbox/警示/hidden 0）；
  TestReportFormSaveWriteGuard（保存链路：新建默认 0、编辑、复制继承）
- 功能点 3（执行拦截）→ TestExecuteReportWriteGuard；TestReportPageWriteGuard.test_page_blocked_flash_message；
  TestApiWriteGuard；TestReportPageWriteGuard.test_preview_write_blocked_for_saved_report
- 功能点 4（执行警示）→ TestReportPageWriteGuard.test_page_allowed_shows_banner /
  test_page_read_sql_no_banner
- 功能点 5（导出一致性）→ TestExportWriteGuard

覆盖：
- 新建/复制表单预览按钮（config.py 表单渲染）
- 表单 allow_write 开关与警示（含写 → checkbox + flash-warn；纯读 → 仅 hidden 0）
- 保存链路：新建默认 0、编辑保存、复制继承
- /report/preview 无 id 预览（pool_id + sql_query 构造）
- execute_report 拦截（单元）：allow_write=0 拒绝 / =1 放行 / 缺省按存量 1
- 页面执行：拦截 flash 文案 / 放行警示条
- API：403 结构化错误 WRITE_DENIED
- 导出：403 拒绝 / 放行
"""

import unittest
from unittest.mock import patch, MagicMock

import db
import config
import report
import export
import api_handler
from query_executor import sql_contains_write
from report import (
    WRITE_DENIED_MESSAGE,
    WRITE_ALLOWED_BANNER,
    ReportResult,
)
from tests import BaseConfigTest, init_test_db


# ===================================================================
# 表单渲染：预览按钮 + allow_write 开关
# ===================================================================


class TestReportFormWriteGuard(BaseConfigTest):
    """报表表单渲染：预览按钮与写操作开关"""

    def _render_form(self, report_dict=None, copy_mode=False, is_edit=None):
        return config._render_report_form(
            self.conn, report_dict, copy_mode=copy_mode, is_edit=is_edit)

    def test_add_form_has_preview_button(self):
        """新建表单（无 id）应渲染预览按钮（PH-05 打通新建预览）"""
        body = self._render_form(None, is_edit=False)
        self.assertIn('onclick="previewReport(this.form)"', body)
        self.assertIn("/report/preview", body)

    def test_copy_form_has_preview_button(self):
        """复制表单应渲染预览按钮"""
        body = self._render_form({"id": 3, "name": "源", "sql_query": "SELECT 1",
                                  "default_page_size": 20, "pool_id": 1,
                                  "prefer_cache": 1, "cache_ttl_hours": 1},
                                 copy_mode=True)
        self.assertIn('onclick="previewReport(this.form)"', body)
        self.assertIn("/report/preview", body)

    def test_add_form_has_no_view_button(self):
        """新建表单不应渲染【查看】按钮（无 id 无查看目标）"""
        body = self._render_form(None, is_edit=False)
        self.assertNotIn('href="/report?id=', body)

    def test_write_sql_shows_checkbox_unchecked_and_warning(self):
        """SQL 含写且 allow_write=0 → 显示未勾选开关 + 黄色警示（新建默认 0）"""
        body = config._report_form_html(
            "新增报表", "/config/reports/add", "报表A", "DELETE FROM t", "20",
            "required", "", "", "", "",
            is_edit=False, report_id=None, allow_write=0, sql_has_write=True)
        self.assertIn('name="allow_write" value="0"', body)
        self.assertIn('name="allow_write" value="1"', body)
        self.assertNotIn('name="allow_write" value="1" checked', body)
        self.assertIn("允许执行写操作", body)
        self.assertIn("该 SQL 包含写操作语句，未开启时将拒绝执行", body)
        self.assertIn("flash-warn", body)

    def test_write_sql_shows_checkbox_checked_no_warning(self):
        """SQL 含写且 allow_write=1（存量）→ 开关勾选、无警示"""
        body = config._report_form_html(
            "编辑报表", "/config/reports/1/edit", "报表A", "UPDATE t SET a=1", "20",
            "required", "", "", "", "",
            is_edit=True, report_id=1, allow_write=1, sql_has_write=True)
        self.assertIn('name="allow_write" value="1" checked', body)
        self.assertNotIn("该 SQL 包含写操作语句，未开启时将拒绝执行", body)

    def test_read_sql_renders_hidden_zero_only(self):
        """SQL 纯读 → 不显示开关，仅保底隐藏 allow_write=0"""
        body = config._report_form_html(
            "新增报表", "/config/reports/add", "报表A", "SELECT 1", "20",
            "required", "", "", "", "",
            is_edit=False, report_id=None, allow_write=0, sql_has_write=False)
        self.assertIn('name="allow_write" value="0"', body)
        self.assertNotIn('name="allow_write" value="1"', body)
        self.assertNotIn("允许执行写操作", body)

    def test_edit_form_write_sql_integration(self):
        """编辑页集成：存量报表 SQL 含写 → 表单含开关（存量默认 1 勾选）"""
        rid = db.add_report(self.conn, "写报表", "UPDATE t SET a=1", 20, None,
                            allow_write=1)
        code, body, _ = config.handle_request(
            self.conn, "GET", f"/config/reports/{rid}/edit", "")
        self.assertEqual(code, 200)
        self.assertIn("允许执行写操作", body)
        self.assertIn('name="allow_write" value="1" checked', body)

    def test_edit_form_read_sql_no_switch(self):
        """编辑页集成：纯读 SQL 报表 → 表单无开关（仅隐藏 0）"""
        rid = db.add_report(self.conn, "读报表", "SELECT 1", 20, None)
        code, body, _ = config.handle_request(
            self.conn, "GET", f"/config/reports/{rid}/edit", "")
        self.assertEqual(code, 200)
        self.assertNotIn("允许执行写操作", body)
        self.assertIn('name="allow_write" value="0"', body)


# ===================================================================
# 保存链路：新建默认 0 / 编辑保存 / 复制继承
# ===================================================================


class TestReportFormSaveWriteGuard(BaseConfigTest):
    """表单保存链路 allow_write 落库"""

    def test_add_report_defaults_to_zero(self):
        """新建报表（表单未提交 allow_write）→ 落库默认 0"""
        rid = db.add_report(self.conn, "新报表", "UPDATE t SET a=1", 20, None)
        row = self.conn.execute(
            "SELECT allow_write FROM report_configs WHERE id=?", (rid,)).fetchone()
        self.assertEqual(row[0], 0)

    def test_add_report_parses_form_allow_write(self):
        """新建表单提交 allow_write=1（勾选）→ 落库 1；未勾选 → 0"""
        code, _ = config.handle_report_add(
            self.conn,
            "name=报表A&sql_query=DELETE+FROM+t&default_page_size=20&allow_write=1")
        self.assertEqual(code, 302)
        self.assertEqual(
            self.conn.execute(
                "SELECT allow_write FROM report_configs WHERE name='报表A'"
            ).fetchone()[0], 1)

        code, _ = config.handle_report_add(
            self.conn,
            "name=报表B&sql_query=DELETE+FROM+t&default_page_size=20&allow_write=0")
        self.assertEqual(code, 302)
        self.assertEqual(
            self.conn.execute(
                "SELECT allow_write FROM report_configs WHERE name='报表B'"
            ).fetchone()[0], 0)

    def test_edit_report_saves_allow_write(self):
        """编辑保存：SQL 含写且关闭开关 → 落库 0；开启 → 1"""
        rid = db.add_report(self.conn, "报表A", "DELETE FROM t", 20, None,
                            allow_write=1)
        config.handle_report_edit(
            self.conn, rid,
            "name=报表A&sql_query=DELETE+FROM+t&default_page_size=20&allow_write=0")
        self.assertEqual(
            self.conn.execute(
                "SELECT allow_write FROM report_configs WHERE id=?", (rid,)
            ).fetchone()[0], 0)

        config.handle_report_edit(
            self.conn, rid,
            "name=报表A&sql_query=DELETE+FROM+t&default_page_size=20&allow_write=1")
        self.assertEqual(
            self.conn.execute(
                "SELECT allow_write FROM report_configs WHERE id=?", (rid,)
            ).fetchone()[0], 1)

    def test_copy_form_inherits_source_allow_write(self):
        """复制表单回显源 allow_write（源 0 → 表单未勾选）"""
        rid = db.add_report(self.conn, "源报表", "DELETE FROM t", 20, None,
                            allow_write=0)
        code, body, _ = config.handle_request(
            self.conn, "GET", f"/config/reports/{rid}/copy", "")
        self.assertEqual(code, 200)
        self.assertIn("允许执行写操作", body)
        self.assertNotIn('name="allow_write" value="1" checked', body)

    def test_copy_submit_carries_allow_write(self):
        """复制提交：allow_write 随表单值写入新报表"""
        rid = db.add_report(self.conn, "源报表", "DELETE FROM t", 20, None,
                            allow_write=1)
        config.handle_report_copy(
            self.conn, rid,
            "name=副本&sql_query=DELETE+FROM+t&default_page_size=20&allow_write=1")
        row = self.conn.execute(
            "SELECT allow_write FROM report_configs WHERE name='副本'").fetchone()
        self.assertEqual(row[0], 1)


# ===================================================================
# execute_report 拦截（单元级）
# ===================================================================


class TestExecuteReportWriteGuard(unittest.TestCase):
    """execute_report 写操作拦截单元测试（拦截在连库前，无需 mock 连接）"""

    def test_allow_write_zero_rejects_write_sql(self):
        """allow_write=0 + 写 SQL → 抛 PermissionError（拒绝执行）"""
        with self.assertRaises(PermissionError) as ctx:
            report.execute_report(1, "DELETE FROM t", {"host": "h"},
                                  report={"allow_write": 0})
        self.assertIn(WRITE_DENIED_MESSAGE, str(ctx.exception))

    def test_allow_write_zero_allows_read_sql(self):
        """allow_write=0 + 纯读 SQL → 不拦截（放行至连库）"""
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            result = report.execute_report(
                1, "SELECT 1", {"host": "h"},
                report={"allow_write": 0})
            self.assertEqual(result.total, 1)
            self.assertTrue(mock_query.called)

    def test_allow_write_one_allows_write_sql(self):
        """allow_write=1 + 写 SQL → 不拦截（存量语义，可执行）"""
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            result = report.execute_report(
                1, "UPDATE t SET a=1", {"host": "h"},
                report={"allow_write": 1})
            self.assertEqual(result.total, 1)
            self.assertTrue(mock_query.called)

    def test_allow_write_missing_defaults_to_one(self):
        """报表缺 allow_write 字段（历史调用）→ 按存量 1 放行，不破坏契约"""
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            result = report.execute_report(
                1, "DELETE FROM t", {"host": "h"},
                report={"prefer_cache": 0})
            self.assertEqual(result.total, 1)

    def test_naked_call_without_report_not_blocked(self):
        """裸调用（report=None，测试等）→ 不拦截，保持历史契约"""
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            result = report.execute_report(1, "DELETE FROM t", {"host": "h"})
            self.assertEqual(result.total, 1)

    def test_blocked_before_cache_read(self):
        """拦截先于缓存读取：即使缓存命中也不得绕过拦截"""
        with self.assertRaises(PermissionError):
            report.execute_report(
                1, "DELETE FROM t", {"host": "h"},
                report={"allow_write": 0, "prefer_cache": 1})


# ===================================================================
# /report/preview 无 id 预览（新建/复制表单）
# ===================================================================


class TestPreviewWithoutId(BaseConfigTest):
    """预览 POST 无 id：pool_id + sql_query 构造预览"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "127.0.0.1", 3306, "u", "p", "d", 1))
        self.conn.commit()
        self.pool_id = 1

    @patch("report.execute_report")
    def test_preview_without_id_uses_pool_and_sql(self, mock_exec):
        """无 id 预览：以表单 pool_id + sql_query 执行（allow_write 默认 0）"""
        mock_exec.return_value = ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            "pool_id=1&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        args = mock_exec.call_args[0]
        self.assertEqual(args[0], 0)              # report_id=0（无库中报表）
        self.assertEqual(args[1], "SELECT 1")     # sql_query=表单 SQL
        self.assertEqual(args[9]["pool_id"], 1)   # report 配置来自表单 pool_id
        self.assertEqual(args[9]["allow_write"], 0)
        self.assertIn("预览模式", body)
        # 无库中报表 → 不显示编辑入口
        self.assertNotIn('/config/reports/0/edit', body)

    @patch("report.execute_report")
    def test_preview_without_id_form_allow_write_one(self, mock_exec):
        """无 id 预览：表单勾选 allow_write=1（hidden 0 + checkbox 1 取最后）→ 预览可执行写"""
        mock_exec.return_value = ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            "pool_id=1&sql_query=DELETE+FROM+t&allow_write=0&allow_write=1")
        self.assertEqual(code, 200)
        self.assertEqual(mock_exec.call_args[0][9]["allow_write"], 1)

    def test_preview_without_id_write_blocked(self):
        """无 id 预览 + 写 SQL + allow_write=0 → 拒绝并给出指引（不应发起连接）"""
        with patch("db.create_mysql_connection") as mock_conn:
            code, body, _ = report.handle_request(
                self.conn, "POST", "/report/preview", "",
                "pool_id=1&sql_query=DELETE+FROM+t&allow_write=0")
            self.assertEqual(code, 200)
            self.assertIn(WRITE_DENIED_MESSAGE, body)
            mock_conn.assert_not_called()

    def test_preview_without_pool_returns_selector(self):
        """无 id 且无 pool_id → 回退报表选择页（兼容历史行为）"""
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("选择报表", body)

    def test_preview_invalid_pool_returns_selector(self):
        """无 id 且 pool_id 非法 → 回退报表选择页（不崩溃）"""
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            "pool_id=abc&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("选择报表", body)

    @patch("report.execute_report")
    def test_preview_without_id_pool_missing_shows_error(self, mock_exec):
        """无 id 预览但连接池不存在 → 渲染错误提示而非崩溃"""
        mock_exec.return_value = ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            "pool_id=999&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("连接池", body)


# ===================================================================
# 页面执行：拦截 flash / 放行警示条
# ===================================================================


class TestReportPageWriteGuard(BaseConfigTest):
    """报表页执行：allow_write=0 拒绝；=1 放行且警示"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "127.0.0.1", 3306, "u", "p", "d", 1))
        self.conn.commit()

    def _make_write_report(self, allow_write):
        rid = db.add_report(self.conn, "写报表", "UPDATE t SET a=1", 20, 1,
                            allow_write=allow_write)
        return rid

    def test_page_blocked_flash_message(self):
        """allow_write=0 + 写 SQL → 页面 flash 明确拒绝文案"""
        rid = self._make_write_report(0)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", f"id={rid}")
        self.assertEqual(code, 200)
        self.assertIn(WRITE_DENIED_MESSAGE, body)

    def test_page_allowed_shows_banner(self):
        """allow_write=1 + 写 SQL → 正常执行且页面顶部出警示条"""
        rid = self._make_write_report(1)
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            code, body, _ = report.handle_request(
                self.conn, "GET", "/report", f"id={rid}")
        self.assertEqual(code, 200)
        self.assertIn(WRITE_ALLOWED_BANNER, body)
        self.assertIn("flash-warn", body)

    def test_page_read_sql_no_banner(self):
        """纯读 SQL → 无写操作警示条"""
        rid = db.add_report(self.conn, "读报表", "SELECT 1", 20, 1,
                            allow_write=0)
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            code, body, _ = report.handle_request(
                self.conn, "GET", "/report", f"id={rid}")
        self.assertEqual(code, 200)
        self.assertNotIn(WRITE_ALLOWED_BANNER, body)

    def test_preview_write_blocked_for_saved_report(self):
        """存量报表 allow_write=0：编辑页预览写 SQL → 拒绝（sql_override 同拦截）"""
        rid = self._make_write_report(0)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            f"id={rid}&sql_query=INSERT+INTO+t+VALUES(1)&allow_write=0")
        self.assertEqual(code, 200)
        self.assertIn(WRITE_DENIED_MESSAGE, body)

    @patch("report.execute_report")
    def test_saved_report_preview_uses_form_allow_write(self, mock_exec):
        """有 id 预览：表单提交的 allow_write 优先于库值（开关状态与预览联动）"""
        mock_exec.return_value = ReportResult(
            columns=["c"], rows=[("v",)], total=1, page=1, page_size=20)
        rid = self._make_write_report(0)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            f"id={rid}&sql_query=DELETE+FROM+t&allow_write=0&allow_write=1")
        self.assertEqual(code, 200)
        self.assertEqual(mock_exec.call_args[0][9]["allow_write"], 1)

    def test_saved_report_preview_form_unchecked_still_blocked(self):
        """有 id 预览：库值 1 但表单未勾选（提交 0）→ 按表单值拦截"""
        rid = self._make_write_report(1)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            f"id={rid}&sql_query=DELETE+FROM+t&allow_write=0")
        self.assertEqual(code, 200)
        self.assertIn(WRITE_DENIED_MESSAGE, body)


# ===================================================================
# API：结构化错误透传
# ===================================================================


class TestApiWriteGuard(BaseConfigTest):
    """API 执行：allow_write=0 + 写 SQL → 403 结构化错误"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "127.0.0.1", 3306, "u", "p", "d", 1))
        self.conn.commit()

    def _make_report(self, sql, allow_write):
        return db.add_report(self.conn, "测试报表", sql, 20, 1,
                             allow_write=allow_write)

    def _make_endpoint(self, report_id, url_path, api_key=None):
        eid = db.add_api_endpoint(
            self.conn, report_id, "写端点", url_path, api_key=api_key)
        return eid

    def test_api_write_blocked_403(self):
        """allow_write=0 + 写 SQL → 403 WRITE_DENIED"""
        rid = self._make_report("DELETE FROM t", 0)
        self._make_endpoint(rid, "/api/write-ep")
        status, body, _ = api_handler.handle_api_request(
            self.conn, "/api/write-ep", "GET", {}, "", {},
            client_ip="127.0.0.1")
        self.assertEqual(status, 403)
        self.assertIn(WRITE_DENIED_MESSAGE, body)

    def test_api_write_blocked_403_json_accept(self):
        """Accept json 时 403 body 为结构化 JSON（code=WRITE_DENIED）"""
        rid = self._make_report("DELETE FROM t", 0)
        self._make_endpoint(rid, "/api/write-json")
        import json as json_mod
        status, body, headers = api_handler.handle_api_request(
            self.conn, "/api/write-json", "GET",
            {"Accept": "application/json"}, "", {},
            client_ip="127.0.0.1")
        self.assertEqual(status, 403)
        parsed = json_mod.loads(body)
        self.assertEqual(parsed["code"], "WRITE_DENIED")
        self.assertIn("允许执行写操作", parsed["error"])

    def test_api_write_allowed_when_allow_write_one(self):
        """allow_write=1 + 写 SQL → 正常执行 200"""
        rid = self._make_report("DELETE FROM t", 1)
        self._make_endpoint(rid, "/api/write-ok")
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            status, body, _ = api_handler.handle_api_request(
                self.conn, "/api/write-ok", "GET", {}, "", {},
                client_ip="127.0.0.1")
        self.assertEqual(status, 200)

    def test_api_read_sql_unaffected(self):
        """纯读 SQL + allow_write=0 → 不拦截（读操作永远允许）"""
        rid = self._make_report("SELECT 1", 0)
        self._make_endpoint(rid, "/api/read-ep")
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            status, body, _ = api_handler.handle_api_request(
                self.conn, "/api/read-ep", "GET", {}, "", {},
                client_ip="127.0.0.1")
        self.assertEqual(status, 200)


# ===================================================================
# 导出：独立连接路径同样拦截
# ===================================================================


class TestExportWriteGuard(BaseConfigTest):
    """导出：allow_write=0 + 写 SQL → 403 拒绝"""

    def setUp(self):
        super().setUp()
        self.pool = {"host": "127.0.0.1", "port": 3306, "user": "u",
                     "password": "p", "database": "d"}

    def test_export_write_blocked_403(self):
        """allow_write=0 + 写 SQL → 403 + 拒绝文案（不触发查询）"""
        rid = db.add_report(self.conn, "写报表", "DELETE FROM t", 20, None,
                            allow_write=0)
        with patch("db.create_mysql_connection") as mock_conn:
            code, body, _ = export.handle_export(
                self.conn, f"id={rid}", pool_override=self.pool)
            self.assertEqual(code, 403)
            self.assertIn(WRITE_DENIED_MESSAGE, body)
            mock_conn.assert_not_called()

    def test_export_write_allowed_when_allow_write_one(self):
        """allow_write=1 + 写 SQL → 正常导出 200"""
        rid = db.add_report(self.conn, "写报表", "DELETE FROM t", 20, None,
                            allow_write=1)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("c",)]
        mock_cursor.fetchall.return_value = [("v",)]
        with patch("db.create_mysql_connection", return_value=mock_conn):
            code, content, _ = export.handle_export(
                self.conn, f"id={rid}", pool_override=self.pool)
        self.assertEqual(code, 200)
        self.assertIn("c", content.decode("gbk"))

    def test_export_read_sql_unaffected(self):
        """纯读 SQL + allow_write=0 → 不拦截"""
        rid = db.add_report(self.conn, "读报表", "SELECT 1", 20, None,
                            allow_write=0)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [("c",)]
        mock_cursor.fetchall.return_value = [("v",)]
        with patch("db.create_mysql_connection", return_value=mock_conn):
            code, content, _ = export.handle_export(
                self.conn, f"id={rid}", pool_override=self.pool)
        self.assertEqual(code, 200)


class TestStaticCacheWriteGuard(unittest.TestCase):
    """静态 .json 变体护栏：历史缓存文件不得绕过 allow_write 拦截"""

    def setUp(self):
        import os
        import shutil
        import sqlite3
        import tempfile
        import static_cache
        self._tmp = tempfile.mkdtemp(prefix="test_write_guard_static_")
        self._db_path = os.path.join(self._tmp, "config.db")
        self._cache_dir = os.path.join(self._tmp, "cache")
        self.conn = sqlite3.connect(self._db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        init_test_db(self.conn)
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "127.0.0.1", 3306, "u", "p", "d", 1))
        self.conn.commit()
        self._cfg_patcher = patch("app_config.get_config", return_value={
            "config_db": [{"enable": True, "engine": "sqlite3", "path": self._db_path}],
            "static_cache": {"enable": True, "dir": self._cache_dir},
        })
        self._cfg_patcher.start()
        self._engine_patcher = patch("db._get_engine", return_value="sqlite3")
        self._engine_patcher.start()

    def tearDown(self):
        import shutil
        self._engine_patcher.stop()
        self._cfg_patcher.stop()
        self.conn.close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _request(self, path):
        return api_handler.handle_api_request(
            self.conn, path, "GET", {}, "", {}, client_ip="127.0.0.1")

    def test_static_cache_hit_cannot_bypass_guard(self):
        """allow_write=1 构建缓存文件后关闭开关 → .json 变体 403（不得直出缓存）"""
        import static_cache
        rid = db.add_report(self.conn, "写报表", "DELETE FROM t", 20, 1,
                            allow_write=1)
        db.add_api_endpoint(self.conn, rid, "写端点", "/api/write-static")
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            # 第一次：miss → 全量执行 → 生成缓存文件
            status, body, resp_headers = self._request("/api/write-static.json")
            self.assertEqual(status, 200)
            self.assertEqual(resp_headers.get("X-Static-Cache"), "miss")
            # 关闭写护栏开关（模拟编辑报表取消勾选）
            self.conn.execute(
                "UPDATE report_configs SET allow_write=0 WHERE id=?", (rid,))
            self.conn.commit()
            # 第二次：即使缓存文件存在，也不得直出 → 回退普通链路 → 403 拦截
            status, body, _ = self._request("/api/write-static.json")
        self.assertEqual(status, 403)
        self.assertIn(WRITE_DENIED_MESSAGE, body)

    def test_static_cache_read_sql_unaffected(self):
        """纯读报表 + allow_write=0：静态 .json 变体仍正常（读操作不受护栏影响）"""
        import static_cache
        rid = db.add_report(self.conn, "读报表", "SELECT 1", 20, 1,
                            allow_write=0)
        db.add_api_endpoint(self.conn, rid, "读端点", "/api/read-static")
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [("v",)]}]
            status, body, _ = self._request("/api/read-static.json")
        self.assertEqual(status, 200)


# ===================================================================
# 检测函数接线自检
# ===================================================================


class TestWriteDetectWire(unittest.TestCase):
    """sql_contains_write 关键路径自检（PH-04 检测函数的 PH-05 接线）"""

    def test_detect_write_statements(self):
        self.assertTrue(sql_contains_write("DELETE FROM t"))
        self.assertTrue(sql_contains_write("INSERT INTO t VALUES (1)"))
        self.assertTrue(sql_contains_write("UPDATE t SET a=1"))
        self.assertTrue(sql_contains_write("  -- 注释\nDROP TABLE t"))

    def test_detect_read_statements(self):
        self.assertFalse(sql_contains_write("SELECT * FROM t"))
        self.assertFalse(sql_contains_write("SHOW TABLES"))
        self.assertFalse(sql_contains_write("EXPLAIN SELECT 1"))


if __name__ == "__main__":
    unittest.main()
