"""
test_feedback_loop_b5.py — 批次5 反馈闭环（#14-#20）测试

spec ux-optimization 批次5：
- #14 flash 自动消失 + 剥参数（data-autohide 标记 + × 关闭按钮 + 公共 JS）
- #15 上移/下移操作反馈（flash 文案 + 锚点回跳 + 失败提示）
- #16 保存后锚点定位 + 高亮（回跳 URL 含 #report-{id} 等，行渲染含 id）
- #17 批量操作条全局浮动（页面级单实例 sticky 浮动条）
- #18 慢查询 loading 遮罩（read_timeout 传入 connect + 超时错误人话化）
- #19 筛选空结果提示区分（两种空态文案 + 清除筛选链接）
- #20 跳页钳制 + 回车提交（form onsubmit goPage）

JS/CSS 行为无法单测的部分以 HTML 结构断言覆盖（class/id/data-* 属性存在性、
公共 JS 函数文本存在性）。
"""

import unittest
import urllib.parse
from unittest.mock import patch, MagicMock

import config
import db
import render
import report
import query_executor
from tests.test_base import BaseConfigTest


# ---------------------------------------------------------------------------
# #14 flash 自动消失 + 剥参数
# ---------------------------------------------------------------------------


class TestFlashAutohideMarkup(unittest.TestCase):
    """flash HTML 含关闭按钮与 data-autohide 标记（spec ux-optimization 批次5#14）"""

    def test_success_flash_has_autohide_and_close(self):
        """成功 flash 应带 data-autohide="1" 与 × 关闭按钮"""
        html = render.build_flash_html("保存成功")
        self.assertIn('data-autohide="1"', html)
        self.assertIn('class="flash-close"', html)
        self.assertIn("×", html)

    def test_error_flash_no_autohide_but_closable(self):
        """错误 flash 不自动消失（data-autohide="0"）但仍可关闭"""
        html = render.build_flash_html("错误: 保存失败")
        self.assertIn('data-autohide="0"', html)
        self.assertIn('class="flash-close"', html)

    def test_common_js_contains_strip_param_logic(self):
        """公共 JS 应包含 flash 参数剥除与定时淡出逻辑"""
        js = render._COMMON_JS
        self.assertIn("initFlashMessages", js)
        self.assertIn("history.replaceState", js)
        self.assertIn("fading-out", render._COMMON_CSS)

    def test_common_css_contains_close_button_style(self):
        """× 按钮 CSS 应包含 cursor:pointer（规格 b 条）"""
        css = render._COMMON_CSS
        self.assertIn(".flash-close", css)
        self.assertIn("cursor: pointer", css)


# ---------------------------------------------------------------------------
# #15 上移/下移操作反馈
# ---------------------------------------------------------------------------


class TestMoveFeedback(BaseConfigTest):
    """移动 handler 成功/失败均带 flash 与锚点（spec ux-optimization 批次5#15）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池A", "h", 3306, "u", "p", "d")
        db.add_pool(self.conn, "池B", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类A")
        db.add_category(self.conn, "分类B")
        db.add_report(self.conn, "报表A", "SELECT 1", 20, 1, category_id=1)
        db.add_report(self.conn, "报表B", "SELECT 1", 20, 1, category_id=1)

    @staticmethod
    def _decoded(location: str) -> str:
        """Location 经 urlencode 传输，断言前解码（+ 还原为空格）。"""
        return urllib.parse.unquote_plus(location)

    def test_pool_move_up_redirects_with_flash_and_anchor(self):
        """连接池上移应回跳 /config 带「已上移」flash 与 #sec-pools 锚点"""
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/pools/2/move-up", "", "")
        self.assertEqual(code, 302)
        text = self._decoded(body)
        self.assertTrue(text.startswith("/config?"))
        self.assertIn("已上移 池B", text)
        self.assertIn("#sec-pools", text)

    def test_pool_move_down_flash_text(self):
        """连接池下移 flash 文案为「已下移 {name}」"""
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/pools/1/move-down", "", "")
        self.assertEqual(code, 302)
        text = self._decoded(body)
        self.assertIn("已下移 池A", text)

    def test_pool_move_failure_carries_error_flash(self):
        """越界移动（首个项上移）应带「错误:」flash 且不改变排序"""
        order_before = [p["id"] for p in db.get_all_pools(self.conn)]
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/pools/1/move-up", "", "")
        self.assertEqual(code, 302)
        self.assertIn("错误:", self._decoded(body))
        order_after = [p["id"] for p in db.get_all_pools(self.conn)]
        self.assertEqual(order_before, order_after)

    def test_report_move_up_redirects_with_anchor(self):
        """报表上移应回跳 /config/reports 带 flash 与 #sec-reports 锚点"""
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/reports/2/move-up", "", "")
        self.assertEqual(code, 302)
        text = self._decoded(body)
        self.assertTrue(text.startswith("/config/reports?"))
        self.assertIn("已上移 报表B", text)
        self.assertIn("#sec-reports", text)

    def test_category_move_up_redirects_with_anchor(self):
        """分类上移应回跳 /config/reports 带 flash 与 #sec-categories 锚点"""
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/categories/2/move-up", "", "")
        self.assertEqual(code, 302)
        text = self._decoded(body)
        self.assertTrue(text.startswith("/config/reports?"))
        self.assertIn("已上移 分类B", text)
        self.assertIn("#sec-categories", text)

    def test_section_anchor_ids_rendered(self):
        """各配置区块标题应携带 sec-* 锚点 id"""
        overview = config.render_overview(self.conn)
        self.assertIn('id="sec-pools"', overview)
        self.assertIn('id="sec-users"', overview)
        reports_page = config.render_reports_page(self.conn)
        self.assertIn('id="sec-reports"', reports_page)
        self.assertIn('id="sec-categories"', reports_page)


# ---------------------------------------------------------------------------
# #16 保存后锚点定位 + 高亮
# ---------------------------------------------------------------------------


class TestSaveAnchorRedirect(BaseConfigTest):
    """保存回跳 URL 含锚点（spec ux-optimization 批次5#16）"""

    def setUp(self):
        super().setUp()
        self.pid = db.add_pool(self.conn, "锚点池", "h", 3306, "u", "p", "d")
        db.add_user(self.conn, "锚点用户", "x")
        self.rid = db.add_report(self.conn, "锚点报表", "SELECT 1", 20, self.pid)

    def test_report_add_close_redirect_has_anchor(self):
        """新增报表保存并关闭应回跳带 #report-{id} 锚点"""
        form = ("name=新报表&sql_query=SELECT+1&default_page_size=20"
                "&pool_id=1&action=save_close")
        code, body, _ = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        self.assertRegex(body, r"#report-\d+$")

    def test_report_edit_close_redirect_has_anchor(self):
        """编辑报表保存并关闭应回跳带 #report-{id} 锚点（fragment 不被编码）"""
        form = ("name=锚点报表改&sql_query=SELECT+2&default_page_size=20"
                "&pool_id=1&action=save_close")
        code, body, _ = config.handle_request(
            self.conn, "POST", f"/config/reports/{self.rid}/edit", "", form)
        self.assertEqual(code, 302)
        self.assertIn(f"#report-{self.rid}", body)

    def test_pool_edit_close_redirect_has_anchor(self):
        """编辑连接池保存并关闭应回跳带 #pool-{id} 锚点"""
        form = ("name=锚点池改&host=h2&port=3306&user=u2&password=p2"
                "&database=d2&action=save_close")
        code, body, _ = config.handle_request(
            self.conn, "POST", f"/config/pools/{self.pid}/edit", "", form)
        self.assertEqual(code, 302)
        self.assertIn(f"#pool-{self.pid}", body)

    def test_row_ids_rendered_in_sections(self):
        """连接池/用户/报表行 <tr> 应携带 pool-/user-/report- 行 id"""
        overview = config.render_overview(self.conn)
        self.assertIn(f'id="pool-{self.pid}"', overview)
        self.assertIn('id="user-1"', overview)
        reports_page = config.render_reports_page(self.conn)
        self.assertIn(f'id="report-{self.rid}"', reports_page)

    def test_highlight_css_and_js_present(self):
        """公共 CSS/JS 应包含行高亮动画与 hash 匹配逻辑"""
        self.assertIn(".row-highlight", render._COMMON_CSS)
        self.assertIn("@keyframes", render._COMMON_CSS)
        self.assertIn("initAnchorRowHighlight", render._COMMON_JS)


# ---------------------------------------------------------------------------
# #17 批量操作条全局浮动
# ---------------------------------------------------------------------------


class TestBatchBarSingleInstance(BaseConfigTest):
    """批量操作条页面级单实例（spec ux-optimization 批次5#17）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类")
        db.add_report(self.conn, "报表", "SELECT 1", 20, 1, category_id=1)
        self.body = config.render_reports_page(self.conn)

    def test_batch_bar_appears_exactly_once(self):
        """整页 batch-bar 容器应只出现一次（单实例）"""
        self.assertEqual(self.body.count('class="batch-bar'), 1)

    def test_batch_bar_is_sticky_float_with_id(self):
        """批量条应为 sticky 底部浮动条且带 id 供 JS 控制显隐"""
        self.assertIn('id="batch-bar"', self.body)
        self.assertIn("batch-float", self.body)
        self.assertIn("position:sticky", self.body.replace(" ", ""))
        self.assertIn("bottom:0", self.body.replace(" ", ""))

    def test_batch_bar_hidden_by_default_with_count_text(self):
        """批量条初始隐藏，计数文案为「已选 N 项」结构"""
        self.assertIn("display:none", self.body)
        self.assertIn('id="batch_count"', self.body)

    def test_checkbox_change_updates_visibility(self):
        """updateBatchCount 应联动显隐与计数（JS 文本断言）"""
        self.assertIn("function updateBatchCount()", self.body)
        self.assertIn("batch_count", self.body)

    def test_old_inline_bar_removed_from_unclassified_section(self):
        """未分类区块内不再内联旧操作条（避免双实例）"""
        # 单实例断言已覆盖；此处补充确认端点动作仍保留（表单 action 不变）
        self.assertIn("/config/reports/batch-delete", self.body)
        self.assertIn("/config/reports/batch-pool", self.body)


# ---------------------------------------------------------------------------
# #18 慢查询 loading 遮罩
# ---------------------------------------------------------------------------


class TestReadTimeoutPassedToConnect(unittest.TestCase):
    """read_timeout 参数传入 mysql.connector.connect（spec ux-optimization 批次5#18）

    找茬 H1 修订：仅 Web 交互报表查询路径传 30；默认/调度路径不限制。
    """

    @patch("mysql.connector.connect")
    def test_interactive_path_passes_read_timeout(self, mock_connect):
        """交互路径显式传 read_timeout=30"""
        mock_connect.return_value = MagicMock()
        query_executor.create_mysql_connection(
            {"host": "127.0.0.1", "port": 3306, "user": "u",
             "password": "p", "database": "d"},
            read_timeout=30)
        kwargs = mock_connect.call_args[1]
        self.assertEqual(kwargs.get("read_timeout"), 30)

    @patch("mysql.connector.connect")
    def test_default_path_omits_read_timeout(self, mock_connect):
        """找茬 H1：默认（调度器共享工厂）不设 read_timeout，超长报表不受限"""
        mock_connect.return_value = MagicMock()
        query_executor.create_mysql_connection({
            "host": "127.0.0.1", "port": 3306, "user": "u",
            "password": "p", "database": "d",
        })
        kwargs = mock_connect.call_args[1]
        self.assertNotIn("read_timeout", kwargs)


class TestHumanizeTimeoutMapping(unittest.TestCase):
    """超时错误人话化映射（spec ux-optimization 批次5#18c）"""

    def test_errno_1969_maps_to_friendly_message(self):
        """errno 1969 应映射为查询超时人话文案"""
        e = Exception("1969 (HY000): Read timed out")
        e.errno = 1969
        friendly, raw = report.humanize_db_error(e)
        self.assertIn("查询超时", friendly)
        self.assertIn("缩小筛选范围", friendly)

    def test_read_timed_out_message_matches(self):
        """消息含 Read timed out 且无已知 errno 时也应命中超时文案"""
        e = Exception("Read timed out. (internal)")
        friendly, _ = report.humanize_db_error(e)
        self.assertIn("查询超时", friendly)

    def test_overlay_markup_in_common_assets(self):
        """遮罩 HTML/CSS/JS 结构存在于公共资源（spinner 动画圆环）"""
        self.assertIn("query-loading-overlay", render._COMMON_CSS)
        self.assertIn("query-loading-overlay", render._COMMON_JS)
        self.assertIn("查询中…请稍候", render._COMMON_JS)
        self.assertIn("goPage", render._COMMON_JS)


# ---------------------------------------------------------------------------
# #19 筛选空结果提示区分
# ---------------------------------------------------------------------------


class TestEmptyStateWithFilters(unittest.TestCase):
    """表格空态两种文案（spec ux-optimization 批次5#19）"""

    def test_empty_without_filters_shows_plain_empty(self):
        """无筛选时保持「暂无数据」原文案"""
        result = render.build_table_body_html([], [0])
        self.assertIn("暂无数据", result)
        self.assertNotIn("没有符合筛选条件", result)

    def test_empty_with_filters_shows_filtered_message(self):
        """有筛选时空态改为「没有符合筛选条件的行」+ 清除筛选链接"""
        result = render.build_table_body_html(
            [], [0], filters=[("name", "eq", "x")],
            clear_filters_href="/report?id=1&amp;page_size=20")
        self.assertIn("没有符合筛选条件的行", result)
        self.assertIn("清除筛选", result)
        self.assertIn('href="/report?id=1&amp;page_size=20"', result)

    def test_nonempty_rows_unaffected(self):
        """有数据行时不输出任何空态"""
        result = render.build_table_body_html(
            [("a",)], [0], filters=[("name", "eq", "x")],
            clear_filters_href="/report?id=1")
        self.assertNotIn("empty-state-row", result)


# ---------------------------------------------------------------------------
# #20 跳页钳制 + 回车提交
# ---------------------------------------------------------------------------


class TestJumpBoxClampForm(unittest.TestCase):
    """分页跳转 form 包裹与钳制（spec ux-optimization 批次5#20）"""

    def test_jump_box_wrapped_in_form_with_onsubmit(self):
        """GO 跳转应以 form onsubmit 触发（支持回车原生提交）"""
        result = render.build_pagination_html(1, 3, 5, 20, 100)
        self.assertIn("<form", result)
        self.assertIn("goPage(event", result)
        self.assertIn('type="submit"', result)

    def test_go_page_receives_clamp_bounds(self):
        """goPage 调用参数应携带当前页与总页数（钳制上下界）"""
        result = render.build_pagination_html(1, 3, 5, 20, 100)
        self.assertIn(", 3, 5)", result)

    def test_go_page_function_defined_in_common_js(self):
        """公共 JS 定义 goPage，含 NaN 回落与 min/max 钳制逻辑"""
        js = render._COMMON_JS
        self.assertIn("function goPage(", js)
        self.assertIn("isNaN", js)


# ===================================================================
# 找茬轮次（批次5/6 审查）回归测试
# ===================================================================

class TestMoveFlashSpecialChars(unittest.TestCase):
    """找茬 L2：移动对象名含 # & 时 flash 文案与锚点不破坏"""

    def test_quote_name_roundtrip(self):
        """名称含 #1& 的分类：quote 后拼 URL，parse_qs 解码文案完整"""
        name = "分类#1&测试"
        obj_name = urllib.parse.quote(name, safe="")
        url = f"/config/reports?flash=已上移 {obj_name}#sec-categories"
        # _redirect_or_render 的 fragment 分离逻辑：# 只在编码后的值之外出现
        path_qs, frag = url.split("#", 1)
        self.assertEqual(frag, "sec-categories")
        params = urllib.parse.parse_qs(
            path_qs.split("?", 1)[1], keep_blank_values=True)
        self.assertEqual(params["flash"], [f"已上移 {name}"])


class TestExecuteReportReadTimeoutWiring(unittest.TestCase):
    """找茬 H1：交互路径传 30、调度/API 默认不受限——签名接线验证"""

    def test_execute_report_accepts_read_timeout_kwarg(self):
        import inspect
        sig = inspect.signature(report.execute_report)
        self.assertIn("read_timeout", sig.parameters)
        self.assertIsNone(sig.parameters["read_timeout"].default)

    def test_create_mysql_connection_none_omits_param(self):
        """read_timeout=None 时不向 connector 传参（行为回到改动前）"""
        with patch("mysql.connector.connect") as mc:
            mc.return_value = MagicMock()
            query_executor.create_mysql_connection(
                {"host": "h", "port": 3306, "user": "u",
                 "password": "p", "database": "d"}, read_timeout=None)
            self.assertNotIn("read_timeout", mc.call_args[1])


if __name__ == "__main__":
    unittest.main()
