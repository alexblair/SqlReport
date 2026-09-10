"""
test_ux_b6_polish.py — 批次6 效率与打磨（#21-#28）测试

spec ux-optimization 批次6：
- #21 合并页检索过滤框（config-filter-box 挂载 + initConfigFilter 纯前端 tr 过滤）
- #22 总览页「最近查看」（recent-reports-mount 挂载点 + saveRecentVisit/initRecentReports）
- #23 SQL 编辑器增强（rows=14 + data-tab-indent 标记 + Tab 插两空格）
- #24 memo 默认折叠（默认值分支翻转，三态记忆保留）
- #25 列设置 localStorage 记忆（th data-col + applyStoredCols，URL cols 优先）
- #26 移动端导航适配（@media max-width: 640px 块：navbar wrap / padding 收窄 / 表格横滚）
- #27 小项打包（title/favicon/HEAD/对比度/alert 移除/登录 label/导出文案/截断 title/锚点）
- #28 公共 CSS/JS 外链化（self@hash 目录写入 + 外链引用 + 缺失回退内联）

以 HTML 结构断言为主（class/id/data-* 属性存在性）；纯 JS 行为
（输入事件过滤、localStorage 读写、Tab 键拦截）无法单测，以公共 JS
函数文本与调用点存在性覆盖，运行时行为依赖浏览器。
"""

import inspect
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
import http.server
from unittest.mock import patch

import config
import db
import render
import report
import server as srv
from tests.test_base import BaseConfigTest, BaseReportTest


# ---------------------------------------------------------------------------
# #21 合并页检索过滤框
# ---------------------------------------------------------------------------


class TestMergePageFilterBox(BaseConfigTest):
    """合并页顶部过滤框（spec ux-optimization 批次6#21）"""

    def test_filter_box_rendered_in_reports_page(self):
        """报表管理页应在 flash 之后渲染过滤框容器与输入框"""
        db.add_pool(self.conn, "池A", "h", 3306, "u", "p", "d")
        body = config.render_reports_page(self.conn)
        self.assertIn('id="config-filter-box"', body)
        self.assertIn('id="config-filter-input"', body)
        self.assertIn('class="config-filter-input"', body)

    def test_filter_box_before_first_section(self):
        """过滤框应位于第一个配置区块（sec-reports）之前"""
        body = config.render_reports_page(self.conn)
        self.assertLess(body.index("config-filter-box"),
                        body.index('id="sec-reports"'))

    def test_filter_input_has_scope_marker(self):
        """输入框带 data-filter-scope 标记（过滤作用域声明）"""
        box = render.build_config_filter_box_html()
        self.assertIn('data-filter-scope="merge-tr"', box)
        self.assertIn("autocomplete=\"off\"", box)

    def test_filter_js_logic_in_common_js(self):
        """公共 JS 应含 initConfigFilter 与 input 监听、contains 显隐逻辑"""
        js = render._COMMON_JS
        self.assertIn("function initConfigFilter(", js)
        body = js[js.index("function initConfigFilter("):]
        self.assertIn("addEventListener('input'", body)
        self.assertIn(".toLowerCase()", body)
        self.assertIn("tr.style.display = ''", js)
        # 表头行跳过（避免表头被误藏破坏表格结构）
        self.assertIn("querySelector('th')", body)

    def test_filter_init_called_on_dom_ready(self):
        """DOMContentLoaded 应初始化过滤框"""
        self.assertIn("initConfigFilter();", render._COMMON_JS)


# ---------------------------------------------------------------------------
# #22 总览页「最近查看」
# ---------------------------------------------------------------------------


class TestRecentReports(BaseReportTest):
    """最近查看记录与总览快捷卡片（spec ux-optimization 批次6#22）"""

    def test_overview_mount_point_present(self):
        """总览页应包含 recent-reports-mount 挂载点 div"""
        html = report.render_report_selector(self.conn)
        self.assertIn('<div id="recent-reports-mount"></div>', html)

    def test_mount_point_at_top_of_body(self):
        """挂载点应位于页面主体最前（第一个 card 之前）"""
        html = report.render_report_selector(self.conn)
        self.assertLess(html.index("recent-reports-mount"),
                        html.index("<h2>选择报表</h2>"))

    def test_detail_page_injects_save_recent_visit(self):
        """报表详情页应注入 saveRecentVisit 调用（含报表 id 与名称）"""
        ri = {"id": 7, "name": "日报表", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        self.assertIn("saveRecentVisit(7,", html)
        self.assertIn("日报表", html)

    def test_preview_mode_does_not_record_recent(self):
        """预览模式（临时 SQL）不算正式查看，不写最近查看记录"""
        ri = {"id": 7, "name": "日报表", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"},
                                         sql_override="SELECT 2")
        # 页内调用脚本不应出现（公共 JS 的函数定义除外——按具体 id 匹配）
        self.assertNotIn("saveRecentVisit(7,", html)

    def test_report_name_escaped_for_script_context(self):
        """报表名内嵌 JS 前经安全转义，</script> 无法提前闭合脚本"""
        ri = {"id": 8, "name": '</script><b>x</b>', "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        script_part = html[html.index("saveRecentVisit(8,"):]
        self.assertNotIn("</script><b>", script_part.split("</script>")[0])

    def test_recent_js_helpers_in_common_js(self):
        """公共 JS 应含去重保序、上限 8 条与卡片渲染逻辑"""
        js = render._COMMON_JS
        self.assertIn("function saveRecentVisit(", js)
        self.assertIn("function initRecentReports(", js)
        save_body = js[js.index("function saveRecentVisit("):]
        self.assertIn("sqlreport_recent", save_body)
        self.assertIn("filter(", save_body)          # 去重
        self.assertIn("unshift(", save_body)         # 新纪录置顶（保序）
        self.assertIn("slice(0, 8)", save_body)      # 上限 8 条
        init_body = js[js.index("function initRecentReports("):
                       js.index("function applyStoredCols(")]
        self.assertIn("/report?id=", init_body)
        self.assertIn("recent-card", init_body)

    def test_overview_renders_nothing_without_records(self):
        """initRecentReports 无记录时不插入内容（空态不产生 DOM）"""
        js = render._COMMON_JS
        body = js[js.index("function initRecentReports("):
                  js.index("function applyStoredCols(")]
        self.assertIn("if (!cards) return;", body)


# ---------------------------------------------------------------------------
# #23 SQL 编辑器增强
# ---------------------------------------------------------------------------


class TestSqlEditorEnhancement(BaseConfigTest):
    """SQL 编辑器 rows/Tab 缩进标记（spec ux-optimization 批次6#23）"""

    def _form_html(self) -> str:
        code, body, _ = config.handle_request(
            self.conn, "GET", "/config/reports/add", "")
        assert code == 200
        return body

    def test_sql_textarea_rows_14(self):
        """报表 SQL textarea 行数应为 14"""
        m = re.search(r'<textarea name="sql_query"[^>]*>', self._form_html())
        self.assertIsNotNone(m)
        self.assertIn('rows="14"', m.group(0))

    def test_sql_textarea_tab_indent_marker(self):
        """SQL textarea 应带 sql-editor 类与 data-tab-indent 标记"""
        m = re.search(r'<textarea name="sql_query"[^>]*>', self._form_html())
        tag = m.group(0)
        self.assertIn("sql-editor", tag)
        self.assertIn('data-tab-indent="1"', tag)

    def test_memo_textarea_not_tab_indent_target(self):
        """memo/result_names textarea 不参与 Tab 缩进（无 sql-editor/data-tab-indent）"""
        body = self._form_html()
        for name in ("memo", "result_names"):
            m = re.search(rf'<textarea name="{name}"[^>]*>', body)
            self.assertIsNotNone(m, name)
            self.assertNotIn("sql-editor", m.group(0), name)
            self.assertNotIn("data-tab-indent", m.group(0), name)

    def test_tab_indent_js_scope_and_two_spaces(self):
        """Tab 拦截仅作用于 data-tab-indent 的 sql-editor，且插入两空格"""
        js = render._COMMON_JS
        self.assertIn("function initSqlEditorTabIndent(", js)
        body = js[js.index("function initSqlEditorTabIndent("):]
        self.assertIn("textarea.sql-editor[data-tab-indent=\"1\"]", body)
        self.assertIn("setRangeText('  '", body)
        self.assertIn("'Tab'", body)

    def test_tab_indent_init_called(self):
        """DOMContentLoaded 应初始化 Tab 缩进"""
        self.assertIn("initSqlEditorTabIndent();", render._COMMON_JS)


# ---------------------------------------------------------------------------
# #24 memo 默认折叠
# ---------------------------------------------------------------------------


class TestMemoDefaultCollapsed(unittest.TestCase):
    """备注区块默认态折叠、三态记忆保留（spec ux-optimization 批次6#24）"""

    def test_nonempty_memo_default_collapsed(self):
        """非空备注默认折叠：hidden 内容 + 折叠箭头 + default-hidden=1"""
        html = render.build_memo_section_html("有内容", 3)
        self.assertIn("\u25b6 备注", html)
        self.assertNotIn("\u25bc 备注", html)
        self.assertIn('class="debug-content hidden"', html)
        self.assertIn('data-default-hidden="1"', html)

    def test_empty_memo_default_collapsed(self):
        """空备注保持默认折叠"""
        html = render.build_memo_section_html("", 3)
        self.assertIn('class="debug-content hidden"', html)
        self.assertIn('data-default-hidden="1"', html)

    def test_mem_key_preserved_for_user_preference(self):
        """三态记忆键保留——用户已有 open/fold 选择仍由前端记忆覆盖"""
        html = render.build_memo_section_html("有内容", 3)
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn("mem-mode", html)

    def test_without_report_id_still_collapsed_no_memory(self):
        """report_id=None 时同样默认折叠，且无记忆控件"""
        html = render.build_memo_section_html("有内容")
        self.assertIn('class="debug-content hidden"', html)
        self.assertNotIn("data-mem-key", html)

    def test_content_not_lost_when_collapsed(self):
        """折叠只影响显隐类，Markdown 渲染内容仍在 DOM 中"""
        html = render.build_memo_section_html("# 标题内容", 5)
        self.assertIn("<h1>标题内容</h1>", html)


# ---------------------------------------------------------------------------
# #25 列设置 localStorage 记忆
# ---------------------------------------------------------------------------


class TestColumnMemory(BaseReportTest):
    """列显示 localStorage 记忆钩子（spec ux-optimization 批次6#25）"""

    def test_table_header_has_data_col(self):
        """表头 th 应携带 data-col 属性供前端定位列"""
        thead = render.build_table_header_html(
            ["id", "name"], ["id", "name"], [], [], 1, 20, "", "")
        self.assertIn('data-col="id"', thead)
        self.assertIn('data-col="name"', thead)

    def test_detail_page_injects_apply_stored_cols(self):
        """详情页应注入 applyStoredCols(report_id) 调用"""
        ri = {"id": 9, "name": "列测试", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        self.assertIn("applyStoredCols(9);", html)

    def test_col_memory_js_url_param_wins(self):
        """URL 有显式 cols 参数时写入记忆并直接返回（分享语义优先）"""
        js = render._COMMON_JS
        self.assertIn("function applyStoredCols(", js)
        body = js[js.index("function applyStoredCols("):]
        self.assertIn("'sqlreport_cols_' + reportId", body)
        # URL 参数分支：写 localStorage 后 return（不再读取旧记忆覆盖 URL）
        self.assertIn("if (colsParam)", body)
        set_after_if = body[body.index("if (colsParam)"):]
        self.assertIn("localStorage.setItem(key, colsParam)", set_after_if)
        self.assertLess(set_after_if.index("localStorage.setItem(key, colsParam)"),
                        set_after_if.index("localStorage.getItem(key)"))

    def test_col_memory_applies_frontend_hiding(self):
        """URL 无 cols 且有记忆时按记录隐藏 th 与同索引 td"""
        body = render._COMMON_JS[render._COMMON_JS.index("function applyStoredCols("):]
        self.assertIn("th.style.display = 'none'", body)
        self.assertIn("td.style.display = 'none'", body)
        self.assertIn("colSpan", body)  # 空态行（colspan）跳过保护


# ---------------------------------------------------------------------------
# #26 移动端导航适配
# ---------------------------------------------------------------------------


class TestMobileMediaQuery(unittest.TestCase):
    """移动端 media query（spec ux-optimization 批次6#26）"""

    @classmethod
    def setUpClass(cls):
        css = render._COMMON_CSS
        m = re.search(r"@media \(max-width: 640px\)\s*\{(.*?)\n\}", css, re.S)
        cls.block = m.group(1) if m else ""
        cls.full_css = css

    def test_media_query_exists(self):
        """公共 CSS 应含 @media (max-width: 640px) 块"""
        self.assertTrue(self.block, "未找到 640px media query 块")

    def test_navbar_allows_wrap_with_smaller_spacing(self):
        """navbar 允许换行且链接间距缩小"""
        self.assertIn(".navbar { flex-wrap: wrap", self.block)
        self.assertIn(".navbar a:not(.brand) { padding: 4px 8px", self.block)

    def test_container_padding_narrowed(self):
        """页面容器 padding 收窄"""
        self.assertIn(".container { padding: 12px; }", self.block)

    def test_table_wrap_horizontally_scrollable(self):
        """表格容器横向可滚（全局 .table-wrap 规则统一保证，窄屏同样生效）"""
        m = re.search(r"(\.table-wrap \{[^}]*overflow-x: auto[^}]*)\}",
                      render._COMMON_CSS)
        self.assertIsNotNone(m, "全局 .table-wrap 规则应含 overflow-x: auto")


# ---------------------------------------------------------------------------
# #27 小项打包
# ---------------------------------------------------------------------------


class Test27a_ReportPageTitle(BaseReportTest):
    """报表详情页 <title> 随报表名（spec ux-optimization 批次6#27a）"""

    def test_title_contains_report_name(self):
        """报表详情页 <title> 随报表名"""
        ri = {"id": 1, "name": "月度销售", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        self.assertIn("<title>月度销售 - Web 报表工具</title>", html)

    def test_title_is_html_escaped(self):
        """报表名中的 HTML 字符在 title 中被转义"""
        ri = {"id": 2, "name": "<x>&\"y\"", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        self.assertIn("<title>&lt;x&gt;&amp;&quot;y&quot; - Web 报表工具</title>", html)


class Test27b_FaviconRoute(unittest.TestCase):
    """favicon 路由（spec ux-optimization 批次6#27b）"""

    def test_route_registered_no_auth(self):
        route = srv._match_route("GET", "/favicon.ico")
        self.assertIsNotNone(route)
        self.assertFalse(route.needs_auth)

    def test_favicon_bytes_are_valid_ico(self):
        """内置图标为合法 ICO（ICONDIR type=1 count=1）且尺寸非零"""
        data = srv._FAVICON_BYTES
        self.assertEqual(data[:4], b"\x00\x00\x01\x00")
        # ICONDIRENTRY 从偏移 6 起：width/height 各 1 字节
        self.assertEqual(data[6], 16)   # 宽 16
        self.assertEqual(data[7], 16)   # 高 16
        self.assertGreater(len(data), 100)


class Test27c_HeadSupport(unittest.TestCase):
    """do_HEAD 支持（spec ux-optimization 批次6#27c）：同 GET 头、无响应体"""

    server = None
    port = None

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                     srv.ReportHandler)
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _head(self, path: str):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     method="HEAD")
        return urllib.request.urlopen(req)

    def test_head_health_ok_empty_body(self):
        resp = self._head("/health")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.read(), b"")
        self.assertIn("application/json", resp.headers.get("Content-Type", ""))

    def test_head_login_ok_empty_body(self):
        resp = self._head("/login")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.read(), b"")
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))

    def test_get_still_returns_body(self):
        """GET 不受 HEAD 支持影响（回归护栏）"""
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/health") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")


class Test27d_ContrastColors(unittest.TestCase):
    """辅助文字对比度加深至 #64748b（spec ux-optimization 批次6#27d）

    装饰色有意不动：.sql-hl-comment（语法高亮体系）、li::marker（项目符号）、
    drag-handle（拖拽把手图标）保留 #94a3b8。
    """

    def test_common_css_auxiliary_text_darkened(self):
        self.assertIn(".empty-state { text-align: center; color: #64748b;",
                      render._COMMON_CSS)
        self.assertIn(".btn-mini-disabled", render._COMMON_CSS)
        mini_block = render._COMMON_CSS[
            render._COMMON_CSS.index(".btn-mini-disabled"):]
        self.assertIn("color: #64748b", mini_block)
        # .md-body del 属于 Markdown 排版 CSS（_MD_CSS）
        self.assertIn(".md-body del { color: #64748b; }", render._MD_CSS)

    def test_syntax_highlight_comment_color_untouched(self):
        """代码高亮注释色属装饰体系，不应被误改"""
        self.assertIn(".sql-hl-comment { color:#94a3b8;",
                      render._COMMON_CSS)

    def test_state_span_muted_darkened(self):
        """muted 状态徽章文字加深"""
        span = render.build_state_span("否", "muted", bold=False)
        self.assertIn("#64748b", span)

    def test_inline_auxiliary_texts_darkened_spot_check(self):
        """渲染产物抽查：合并页/调度页辅助文字不再出现旧色值"""
        conn = None
        try:
            from tests.test_base import make_config_db, init_test_db
            conn = make_config_db()
            with patch("db._get_engine", return_value="sqlite3"):
                init_test_db(conn)
                db.add_pool(conn, "池A", "h", 3306, "u", "p", "d")
                body = config.render_reports_page(conn)
            self.assertNotIn("color:#94a3b8", body)
            self.assertIn("color:#64748b", body)
        finally:
            if conn is not None:
                conn.close()

    def test_login_page_auxiliary_text_darkened(self):
        self.assertNotIn("#94a3b8", srv._LOGIN_PAGE)
        self.assertIn(".login-subtitle { text-align: center; color: #64748b;",
                      srv._LOGIN_PAGE)


class Test27e_AlertReplacedWithInlineWarn(unittest.TestCase):
    """alert() 改 .flash-warn 内联提示条；confirm 保留（批次6#27e）"""

    def test_common_js_defines_show_flash_warn(self):
        js = render._COMMON_JS
        self.assertIn("function showFlashWarn(", js)
        self.assertIn("flash-warn", js)
        self.assertIn("js-flash-warn", js)

    def test_common_js_contains_no_alert_calls(self):
        """公共 JS 不再有任何 alert( 调用"""
        self.assertNotIn("alert(", render._COMMON_JS)

    def test_apply_rules_json_uses_inline_warn(self):
        """规则 JSON 校验失败走行内提示而非 alert"""
        js = render._COMMON_JS
        fn = js[js.index("function applyRulesJson("):]
        self.assertIn("showFlashWarn('请输入规则 JSON')", fn)
        self.assertIn("showFlashWarn('JSON 格式错误: ' + e.message)", fn)
        self.assertNotIn("alert(", fn)

    def test_batch_ops_script_alerts_removed_confirms_kept(self):
        """批量操作区 alert 全部移除、confirm 确认保留"""
        conn = None
        try:
            from tests.test_base import make_config_db, init_test_db
            conn = make_config_db()
            with patch("db._get_engine", return_value="sqlite3"):
                init_test_db(conn)
                cat = [{"id": 1, "name": "分类A", "parent_id": None}]
                tree = [{"id": 1, "name": "分类A", "children": []}]
                pools = [{"id": 1, "name": "池A"}]
                html = render.build_category_section_html(
                    {}, [], cat, [], pools, tree)
            self.assertNotIn("alert(", html)
            self.assertIn("confirm(", html)
            self.assertIn("showFlashWarn('请至少选择一项')", html)
        finally:
            if conn is not None:
                conn.close()


class Test27f_LoginFormAccessibility(unittest.TestCase):
    """登录页 label 关联与 autocomplete（spec ux-optimization 批次6#27f）"""

    def test_username_label_association(self):
        self.assertIn('<label for="login_username">用户名</label>',
                      srv._LOGIN_PAGE)
        self.assertIn('id="login_username"', srv._LOGIN_PAGE)
        self.assertIn('autocomplete="username"', srv._LOGIN_PAGE)

    def test_password_label_association(self):
        self.assertIn('<label for="login_password">密码</label>',
                      srv._LOGIN_PAGE)
        self.assertIn('id="login_password"', srv._LOGIN_PAGE)
        self.assertIn('autocomplete="current-password"',
                      srv._LOGIN_PAGE)


class Test27g_ExportCharsetLabels(BaseReportTest):
    """GBK/UTF8 导出选项面向结果描述（spec ux-optimization 批次6#27g）"""

    def test_charset_options_describe_outcome(self):
        ri = {"id": 1, "name": "导出", "sql_query": "SELECT 1",
              "memo": "", "pool_id": self.pool_id}
        result = report.ReportResult(columns=["id"], rows=[(1,)],
                                     total=1, page=1, page_size=10)
        html = report._build_report_html(self.conn, ri, result,
                                         {"id": self.pool_id, "name": "池"})
        self.assertIn('<option value="gbk">GBK（Excel 中文版推荐）</option>', html)
        self.assertIn('<option value="utf8">UTF-8（通用 / 程序处理）</option>', html)


class Test27h_TruncatedCellTitles(BaseConfigTest):
    """截断单元格补 title 全文（spec ux-optimization 批次6#27h）"""

    def test_truncated_cells_carry_full_text_titles(self):
        """报表管理列表：SQL 截断与 memo 截断单元格均带全文 title"""
        cat = [{"id": 1, "name": "分类A", "parent_id": None}]
        tree = [{"id": 1, "name": "分类A", "children": []}]
        pools = [{"id": 1, "name": "池A"}]
        reports = [{
            "id": 11, "name": "长SQL报表",
            "sql_query": "S" * 200,
            "default_page_size": 20, "pool_id": 1,
            "memo": "M" * 100,
            "prefer_cache": 1, "cache_ttl_hours": 0,
        }]
        html = render.build_category_section_html(
            [{"id": 1, "reports": reports}], [], cat, reports, pools, tree)
        self.assertIn(f'title="{"S" * 200}"', html)
        self.assertIn(f'title="{"M" * 100}"', html)
        # 截断展示本体仍为前缀 + ...
        self.assertIn("S" * 80 + "...", html)
        self.assertIn("M" * 15 + "...", html)


class Test27i_OverviewButtonAnchors(BaseConfigTest):
    """总览双按钮落点区分（spec ux-optimization 批次6#27i）"""

    def test_category_button_targets_category_anchor(self):
        """「管理分类」按钮应锚定合并页分类区块 sec-categories"""
        html = config.render_overview(self.conn)
        self.assertIn('href="/config/reports#sec-categories"', html)

    def test_report_button_targets_plain_reports_page(self):
        """「管理报表」按钮落点不带分类锚点（两按钮落点不同）"""
        html = config.render_overview(self.conn)
        self.assertIn('href="/config/reports#sec-categories"', html)
        # 精确提取两个按钮标签，逐一核对 href
        m_cat = re.search(r'<a href="([^"]*)"[^>]*>管理分类</a>', html)
        m_rpt = re.search(r'<a href="([^"]*)"[^>]*>管理报表</a>', html)
        self.assertIsNotNone(m_cat)
        self.assertIsNotNone(m_rpt)
        self.assertEqual(m_cat.group(1), "/config/reports#sec-categories")
        self.assertEqual(m_rpt.group(1), "/config/reports")


# ---------------------------------------------------------------------------
# #28 公共 CSS/JS 外链化
# ---------------------------------------------------------------------------


class Test28CommonAssetsExternal(unittest.TestCase):
    """公共资产外链化（spec ux-optimization 批次6#28）"""

    def setUp(self):
        render.reset_common_assets_cache()

    def tearDown(self):
        render.reset_common_assets_cache()

    def test_ensure_common_assets_writes_versioned_files(self):
        """ensure 写入 self@{hash8}/common.css|js 并返回版本锁 URL"""
        with tempfile.TemporaryDirectory() as tmp:
            urls = render.ensure_common_assets(root=tmp)
            self.assertIsNotNone(urls)
            hash8 = render.content_hash8(render._COMMON_CSS)
            css_path = os.path.join(tmp, f"self@{hash8}", "common.css")
            js_path = os.path.join(tmp, f"self@{hash8}", "common.js")
            self.assertTrue(os.path.isfile(css_path))
            self.assertTrue(os.path.isfile(js_path))
            with open(css_path, encoding="utf-8") as f:
                self.assertEqual(f.read(), render._COMMON_CSS)
            self.assertEqual(urls[0], f"/static/vendor/self@{hash8}/common.css")
            self.assertEqual(urls[1], f"/static/vendor/self@{hash8}/common.js")

    def test_ensure_is_idempotent_on_same_content(self):
        """同内容重复 ensure 幂等（目录/文件稳定）"""
        with tempfile.TemporaryDirectory() as tmp:
            first = render.ensure_common_assets(root=tmp)
            second = render.ensure_common_assets(root=tmp)
            self.assertEqual(first, second)

    def test_page_header_links_external_css(self):
        """页头输出 <link rel="stylesheet"> 版本锁外链而非内联大块样式"""
        with tempfile.TemporaryDirectory() as tmp:
            urls = render.ensure_common_assets(root=tmp)
            render._COMMON_ASSET_URLS = urls
            header = render.render_page_header(title="外链测试")
        self.assertIn('<link rel="stylesheet" href="/static/vendor/self@',
                      header)
        self.assertIn('common.css">', header)
        # 页头不应再出现公共 CSS 内联大块（外链模式下）
        self.assertNotIn(render._COMMON_CSS[:100], header)

    def test_page_footer_links_external_js_with_defer(self):
        """页尾输出 <script defer> 版本锁外链而非内联大块脚本"""
        with tempfile.TemporaryDirectory() as tmp:
            urls = render.ensure_common_assets(root=tmp)
            render._COMMON_ASSET_URLS = urls
            footer = render.render_page_footer()
        self.assertIn('<script src="/static/vendor/self@', footer)
        self.assertIn('common.js" defer></script>', footer)
        self.assertNotIn(render._COMMON_JS[:100], footer)

    def test_missing_assets_fallback_to_inline(self):
        """资产不可用时回退内联 <style>/<script>（功能不降级）"""
        render._COMMON_ASSET_URLS = ("", "")
        header = render.render_page_header(title="回退测试")
        footer = render.render_page_footer()
        self.assertIn("<style>" + render._COMMON_CSS, header)
        self.assertIn("<script>" + render._COMMON_JS + "</script>", footer)

    def test_ensure_returns_none_on_unwritable_root(self):
        """写入失败返回 None（触发调用方内联回退）"""
        fake_root = os.path.join(tempfile.gettempdir(), "no_such_dir_xyz",
                                 "sub")
        with patch("builtins.open", side_effect=OSError("denied")):
            self.assertIsNone(render.ensure_common_assets(root=fake_root))

    def test_server_main_preheats_assets(self):
        """server.main 启动序列显式预热公共资产"""
        src = inspect.getsource(srv.main)
        self.assertIn("ensure_common_assets", src)


if __name__ == "__main__":
    unittest.main()
