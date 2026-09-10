"""
test_html_structure.py — 渲染层 HTML 结构校验（嵌套 form / 标签平衡）。

动机（2026-08-10 diagnosing-bugs 捕获）：编辑态 API Key 管理区块曾嵌套进主
表单，HTML5 解析使第一个 </form> 提前闭合主表单，保存按钮脱离表单点击无反应。
当时所有渲染测试都是字符串级断言，结构类 bug 无法被既有测试发现。

本文件对全部 form 渲染函数逐一遍历：
1. 无 HTML5 嵌套 form（嵌套会导致外层表单提前闭合）
2. 标签配对平衡（无未闭合/孤儿/错配标签）
3. 含保存按钮的表单：保存/保存并关闭按钮必须位于主表单区间内

被测函数均为纯数据→HTML（无 DB），故使用裸 unittest.TestCase。
config._report_form_html / render_category_form_page 为整页渲染，一并覆盖。
"""

import unittest

import config
import render
from tests import htmlcheck
from tests.test_config import _make_conn


def _endpoint(eid=1, report_id=1, name="测试端点", url_path="/api/ui-ep",
              enabled=1, allow_fetch_all=1, static_cache=1,
              output_format="json", result_mode="single", result_index=0,
              columns="", filters="", sorts="", description="",
              json_template="", row_limit=0):
    return {
        "id": eid, "report_id": report_id, "name": name, "url_path": url_path,
        "output_format": output_format, "result_mode": result_mode,
        "result_index": result_index, "columns": columns, "filters": filters,
        "sorts": sorts, "description": description, "json_template": json_template,
        "row_limit": row_limit, "enabled": enabled,
        "allow_fetch_all": allow_fetch_all, "static_cache": static_cache,
    }


class _HtmlStructureMixin:
    """结构断言通用方法。"""

    def assertWellFormed(self, html, label=""):
        """断言 HTML 无嵌套 form 且标签平衡。"""
        label = label or self._testMethodName
        nested = htmlcheck.find_nested_forms(html)
        self.assertEqual(
            [], nested,
            f"{label}: 发现嵌套 form（HTML5 下外层表单被提前闭合）: {nested}")
        problems = htmlcheck.check_tag_balance(html)
        self.assertEqual(
            [], problems,
            f"{label}: 标签结构问题: {problems[:5]}")

    def assertMainFormHasSubmit(self, html, action_hint="", label=""):
        """断言主表单区间内存在提交按钮（保存）。"""
        label = label or self._testMethodName
        start, end = htmlcheck.main_form_span(html, action_hint)
        self.assertNotEqual((-1, -1), (start, end), f"{label}: 未找到主表单")
        span = html[start:end]
        self.assertIn('type="submit"', span,
                      f"{label}: 主表单内缺少提交按钮")
        self.assertIn(">保存<", span,
                      f"{label}: 主表单内缺少保存按钮")

    def assertSaveButtonsInMainForm(self, html, action_hint="", label=""):
        """断言双按钮（保存/保存并关闭）位于主表单区间内。"""
        label = label or self._testMethodName
        start, end = htmlcheck.main_form_span(html, action_hint)
        self.assertNotEqual((-1, -1), (start, end), f"{label}: 未找到主表单")
        span = html[start:end]
        self.assertIn('name="action" value="save"', span,
                      f"{label}: 保存按钮不在主表单内")
        self.assertIn('name="action" value="save_close"', span,
                      f"{label}: 保存并关闭按钮不在主表单内")


class TestFormRenderingStructure(unittest.TestCase, _HtmlStructureMixin):
    """render.py 全部 form 渲染函数的结构校验。"""

    def test_build_controls_bar_html(self):
        html = render.build_controls_bar_html(
            1, 20, [], [], "", ["id"], 0, "", 0, 0)
        self.assertWellFormed(html)

    def test_build_filter_form_html(self):
        html = render.build_filter_form_html("ff", '<input type="hidden" name="x" value="1">')
        self.assertWellFormed(html)

    def test_build_report_switcher_html(self):
        html = render.build_report_switcher_html(
            [{"id": 1, "name": "报表A", "category_id": None}],
            [], [], current_id=None)
        self.assertWellFormed(html)

    def test_build_delete_form_html(self):
        html = render.build_delete_form_html(
            "/config/reports/1/delete", "确定删除？")
        self.assertWellFormed(html)

    def test_build_move_buttons_html(self):
        html = render.build_move_buttons_html(3, "report", 1, 5)
        self.assertWellFormed(html)

    def test_build_pool_form_html_new(self):
        html = render.build_pool_form_html(None)
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/pools/add")

    def test_build_pool_form_html_edit(self):
        html = render.build_pool_form_html({
            "id": 2, "name": "池", "host": "h", "port": 3306, "user": "u",
            "password": "", "database": "d",
        }, is_edit=True)
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/pools/2/edit")

    def test_build_user_form_html_new(self):
        html = render.build_user_form_html(None)
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/users/add")

    def test_build_user_form_html_edit(self):
        html = render.build_user_form_html(
            {"id": 5, "username": "alice"}, is_edit=True)
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/users/5/edit")

    def test_build_api_endpoints_list_html(self):
        html = render.build_api_endpoints_list_html(
            [_endpoint()], report_id=1, base_url="http://x", key_counts={1: 2})
        self.assertWellFormed(html)

    def test_build_api_endpoint_form_html_new(self):
        html = render.build_api_endpoint_form_html(1, "报表", None)
        self.assertWellFormed(html)
        self.assertSaveButtonsInMainForm(
            html, action_hint=f"/config/reports/1/api_endpoints/new")

    def test_build_api_endpoint_form_html_edit_with_keys(self):
        """类 bug 回归：编辑态含 Key 管理区块不得嵌套主表单。"""
        html = render.build_api_endpoint_form_html(
            1, "报表", _endpoint(), endpoint_id=1, is_edit=True,
            api_keys=[{"id": 1, "name": "k1", "api_key": "sk-x", "enabled": 1}])
        self.assertWellFormed(html)
        self.assertSaveButtonsInMainForm(
            html, action_hint="/config/reports/1/api_endpoints/1/edit")
        # Key 管理区块（含独立 form）在主表单之外
        start, end = htmlcheck.main_form_span(html)
        self.assertNotIn("🔑 API Key 管理", html[start:end])
        self.assertEqual(1, html.count("🔑 API Key 管理"))

    def test_build_api_endpoint_form_html_edit_no_keys(self):
        """编辑态无 Key：生成表单仍须在主表单之外。"""
        html = render.build_api_endpoint_form_html(
            1, "报表", _endpoint(), endpoint_id=1, is_edit=True, api_keys=[])
        self.assertWellFormed(html)
        self.assertSaveButtonsInMainForm(
            html, action_hint="/config/reports/1/api_endpoints/1/edit")

    def test_build_api_key_manage_html(self):
        html = render.build_api_key_manage_html(
            [{"id": 1, "name": "k1", "api_key": "sk-abcd1234", "enabled": 1}],
            1, 1)
        self.assertWellFormed(html)

    def test_render_audit_page(self):
        html = render.render_audit_page(
            [{"id": 1, "session_user": "u", "operation": "op",
              "target": "t", "detail_json": "{}", "ip_addr": "1.2.3.4",
              "created_at": "2026-01-01 00:00:00"}],
            total=1, page=1, page_size=20, filters={})
        self.assertWellFormed(html)


class TestWholePageStructure(unittest.TestCase, _HtmlStructureMixin):
    """整页渲染（header + navbar + 表单 + footer）的结构校验。"""

    @classmethod
    def setUpClass(cls):
        cls.conn = _make_conn()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _full_page(self, body):
        return (render.render_page_header(title="t", active_nav="config")
                + body + render.render_page_footer())

    def test_api_endpoint_edit_full_page(self):
        """整页组合：API 端点编辑页全文结构（复现真实页面场景）。"""
        endpoint = _endpoint()
        body = render.build_api_endpoint_form_html(
            1, "报表", endpoint, endpoint_id=1, is_edit=True,
            api_keys=[{"id": 1, "name": "k1", "api_key": "sk-x", "enabled": 1}])
        html = self._full_page(body)
        self.assertWellFormed(html)
        self.assertSaveButtonsInMainForm(
            html, action_hint="/config/reports/1/api_endpoints/1/edit")

    def test_pool_form_full_page(self):
        html = self._full_page(render.build_pool_form_html(None))
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/pools/add")

    def test_user_form_full_page(self):
        html = self._full_page(render.build_user_form_html(None))
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/users/add")

    def test_category_form_page(self):
        """分类表单整页（config.py 独立渲染路径）。"""
        html = config.render_category_form_page(self.conn)
        self.assertWellFormed(html)
        self.assertMainFormHasSubmit(html, action_hint="/config/categories/new")


if __name__ == "__main__":
    unittest.main()