"""
test_api_key_ui.py — API Key 管理 UI 测试（PH-03，T2-UI）

覆盖：
- 端点编辑表单：api_key 输入框移除 → 「API Key 管理」区块（编辑态）/ 自动生成提示（新增态）
- build_api_key_manage_html：列表行（名称/掩码/复制/禁用/删除/生成表单）、空态提示
- config.handle_request 分发：/api_keys 路径解析、add/delete/toggle 动作、错误路径
- 新增端点保存自动生成 key（含旧表单 api_key 字段兼容 → 写入 api_keys 表）
- 端点列表 key 数量徽标（key_counts）与旧逻辑回退
"""

import sqlite3
import unittest
import urllib.parse

import config
import config_db
import db
import render
from tests import htmlcheck
from tests.test_config import _make_conn


class _Base(unittest.TestCase):
    """自建内存库 + 种子报表的基类。"""

    def setUp(self):
        self.conn = _make_conn()
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("测试报表", "SELECT 1"))
        self.report_id = 1
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _add_endpoint(self, name="测试接口", url_path="/api/ui-ep",
                      **kwargs):
        return db.add_api_endpoint(self.conn, self.report_id, name, url_path,
                                   **kwargs)


class TestPathParsing(_Base):
    """/api_keys 路径解析与 GET 重定向。"""

    def test_parse_config_path_api_keys(self):
        parsed = config.parse_config_path(
            "/config/reports/1/api_endpoints/7/api_keys")
        self.assertEqual(parsed["action"], "api_keys")
        self.assertEqual(parsed["report_id"], 1)
        self.assertEqual(parsed["endpoint_id"], 7)

    def test_get_api_keys_redirects_to_edit(self):
        eid = self._add_endpoint()
        code, body, headers = config.handle_request(
            self.conn, "GET",
            f"/config/reports/1/api_endpoints/{eid}/api_keys", "")
        self.assertEqual(code, 302)
        self.assertIn(f"/api_endpoints/{eid}/edit", headers["Location"])


class TestApiKeyManageActions(_Base):
    """handle_request 分发的 API Key 管理动作。"""

    def _post(self, eid, body):
        return config.handle_request(
            self.conn, "POST",
            f"/config/reports/1/api_endpoints/{eid}/api_keys", "", body)

    def _loc(self, headers):
        """Location 中的 flash 为 URL 编码，统一解码后断言。"""
        return urllib.parse.unquote_plus(headers["Location"])

    def _edit_url(self, eid):
        return f"/config/reports/1/api_endpoints/{eid}/edit"

    def test_add_key_with_name(self):
        """生成新 Key：指定名称生效。"""
        eid = self._add_endpoint()
        code, _body, headers = self._post(
            eid, urllib.parse.urlencode({"action": "add", "name": "调用方A"}))
        self.assertEqual(code, 302)
        self.assertIn("API Key 已生成", self._loc(headers))
        keys = config_db.list_api_keys(self.conn, eid)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["name"], "调用方A")
        self.assertTrue(keys[0]["api_key"].startswith("sk-"))
        self.assertEqual(keys[0]["enabled"], 1)

    def test_add_key_default_name_is_endpoint_name(self):
        """生成新 Key：名称为空时用端点名。"""
        eid = self._add_endpoint(name="订单接口")
        code, _body, headers = self._post(eid, "action=add")
        self.assertEqual(code, 302)
        self.assertIn("API Key 已生成（订单接口）", self._loc(headers))
        keys = config_db.list_api_keys(self.conn, eid)
        self.assertEqual(keys[0]["name"], "订单接口")

    def test_toggle_key_enabled(self):
        """启用/禁用切换。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "Key1", "sk-1")
        code, _body, headers = self._post(
            eid, urllib.parse.urlencode({"action": "toggle", "key_id": str(k1)}))
        self.assertEqual(code, 302)
        self.assertIn("已禁用", self._loc(headers))
        self.assertEqual(config_db.get_api_key(self.conn, k1)["enabled"], 0)
        code, _body, headers = self._post(
            eid, urllib.parse.urlencode({"action": "toggle", "key_id": str(k1)}))
        self.assertIn("已启用", self._loc(headers))
        self.assertEqual(config_db.get_api_key(self.conn, k1)["enabled"], 1)

    def test_toggle_missing_key(self):
        """toggle 不存在的 Key → flash 错误。"""
        eid = self._add_endpoint()
        code, _body, headers = self._post(eid, "action=toggle&key_id=999")
        self.assertEqual(code, 302)
        self.assertIn("API Key 不存在", self._loc(headers))

    def test_delete_key(self):
        """删除 Key → 立即失效（表记录消失）。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "Key1", "sk-1")
        code, _body, headers = self._post(
            eid, urllib.parse.urlencode({"action": "delete", "key_id": str(k1)}))
        self.assertEqual(code, 302)
        self.assertIn("API Key 已删除", self._loc(headers))
        self.assertIsNone(config_db.get_api_key(self.conn, k1))
        # 重复删除 → 错误 flash
        code, _body, headers = self._post(
            eid, urllib.parse.urlencode({"action": "delete", "key_id": str(k1)}))
        self.assertIn("API Key 不存在", self._loc(headers))

    def test_invalid_key_id(self):
        """非数字 key_id → 错误 flash。"""
        eid = self._add_endpoint()
        code, _body, headers = self._post(eid, "action=delete&key_id=abc")
        self.assertEqual(code, 302)
        self.assertIn("无效的 Key ID", self._loc(headers))

    def test_unknown_action(self):
        """未知 action → 错误 flash。"""
        eid = self._add_endpoint()
        code, _body, headers = self._post(eid, "action=hack")
        self.assertEqual(code, 302)
        self.assertIn("未知操作", self._loc(headers))

    def test_endpoint_missing(self):
        """端点不存在 → 错误 flash 并回编辑页。"""
        code, _body, headers = config.handle_request(
            self.conn, "POST",
            "/config/reports/1/api_endpoints/999/api_keys", "", "action=add")
        self.assertEqual(code, 302)
        self.assertIn("API 接口不存在", self._loc(headers))

    def test_endpoint_not_in_report(self):
        """端点不属于该报表 → 拒绝。"""
        eid = self._add_endpoint()
        code, _body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/2/api_endpoints/{eid}/api_keys", "",
            "action=add")
        self.assertEqual(code, 302)
        self.assertIn("API 接口不属于该报表", self._loc(headers))
        self.assertEqual(config_db.list_api_keys(self.conn, eid), [])

    def test_cross_endpoint_key_id_rejected(self):
        """跨端点 key_id（delete/toggle）→ 拒绝且数据不变。"""
        eid_a = self._add_endpoint(name="端点A")
        eid_b = self._add_endpoint(name="端点B", url_path="/api/ui-ep-b")
        k_b = config_db.add_api_key(self.conn, eid_b, "KeyB", "sk-b")
        # delete：来自端点 A 的请求删 B 的 key → 拒绝
        code, _body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/1/api_endpoints/{eid_a}/api_keys", "",
            urllib.parse.urlencode({"action": "delete", "key_id": str(k_b)}))
        self.assertEqual(code, 302)
        self.assertIn("API Key 不属于该接口", self._loc(headers))
        self.assertIsNotNone(config_db.get_api_key(self.conn, k_b),
                             "跨端点删除应被拒绝，key 必须保留")
        # toggle：同样拒绝，enabled 不变
        code, _body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/1/api_endpoints/{eid_a}/api_keys", "",
            urllib.parse.urlencode({"action": "toggle", "key_id": str(k_b)}))
        self.assertEqual(code, 302)
        self.assertIn("API Key 不属于该接口", self._loc(headers))
        self.assertEqual(config_db.get_api_key(self.conn, k_b)["enabled"], 1,
                         "跨端点 toggle 应被拒绝，enabled 不变")


class TestApiKeyAutoGenerate(_Base):
    """新增端点保存自动生成 Key。"""

    def _post_new(self, extra=None):
        data = {
            "name": "新接口",
            "url_path": "new-ep",
            "output_format": "json",
            "rule_json": "",
            "row_limit": "0",
            "allowed_origins": "",
            "enabled": "1",
            "action": "save_close",
        }
        if extra:
            data.update(extra)
        return config.handle_request(
            self.conn, "POST", "/config/reports/1/api_endpoints/new", "",
            urllib.parse.urlencode(data))

    def test_new_endpoint_auto_generates_key(self):
        """保存后自动生成一条 Key（name=端点名、sk- 前缀、enabled=1）。"""
        code, _body, headers = self._post_new()
        self.assertEqual(code, 302)
        keys = config_db.list_api_keys(self.conn, 1)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["name"], "新接口")
        self.assertTrue(keys[0]["api_key"].startswith("sk-"))
        self.assertEqual(keys[0]["enabled"], 1)
        # 旧列保持空（多 key 化后旧列只读回退）
        ep = db.get_api_endpoint(self.conn, 1)
        self.assertIsNone(ep["api_key"])

    def test_new_endpoint_legacy_api_key_field_goes_to_table(self):
        """旧客户端 POST 仍带 api_key 字段 → 写入 api_keys 表而非旧列。"""
        code, _body, _headers = self._post_new(extra={"api_key": "legacy-key"})
        self.assertEqual(code, 302)
        keys = config_db.list_api_keys(self.conn, 1)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["api_key"], "legacy-key")
        self.assertEqual(keys[0]["name"], "新接口")
        ep = db.get_api_endpoint(self.conn, 1)
        self.assertIsNone(ep["api_key"], "旧列不应再被表单写入")

    def test_save_action_shows_key_block(self):
        """action=save（留在表单页）→ 页面含「API Key 管理」区块与自动生成 Key。"""
        code, body, _headers = self._post_new(extra={"action": "save"})
        self.assertEqual(code, 200)
        self.assertIn("API Key 管理", body)
        self.assertIn("🔑 API Key 管理", body)


class TestKeyManageHtml(_Base):
    """build_api_key_manage_html 渲染断言。"""

    def test_rows_rendered(self):
        """每行含名称/掩码/复制/禁用/删除/生成表单。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "调用方A", "sk-abcdefgh1234")
        html = render.build_api_key_manage_html(
            config_db.list_api_keys(self.conn, eid), 1, eid)
        self.assertIn("🔑 API Key 管理", html)
        self.assertIn("调用方A", html)
        self.assertIn("sk-a***1234", html)  # 掩码：前4后4
        self.assertIn("copyToClipboard('api-key-raw-%d')" % k1, html)
        self.assertIn('value="add"', html)
        self.assertIn("生成新 Key", html)
        # 禁用表单：启用态按钮文案为「禁用」
        self.assertIn(">禁用<", html)
        # 删除表单带确认
        self.assertIn("确定删除该 API Key", html)
        # POST 指向 api_keys 动作端点
        self.assertIn(f"/api_endpoints/{eid}/api_keys", html)

    def test_disabled_key_shows_enable_button(self):
        """禁用态 Key：显示「启用」按钮与禁用徽章。"""
        eid = self._add_endpoint()
        k1 = config_db.add_api_key(self.conn, eid, "Key1", "sk-1")
        config_db.set_api_key_enabled(self.conn, k1, 0)
        html = render.build_api_key_manage_html(
            config_db.list_api_keys(self.conn, eid), 1, eid)
        self.assertIn(">启用<", html)
        self.assertIn("禁用", html)

    def test_empty_state(self):
        """无 Key：提示公开访问。"""
        eid = self._add_endpoint()
        html = render.build_api_key_manage_html([], 1, eid)
        self.assertIn("暂无 API Key", html)
        self.assertIn("公开访问", html)


class TestEndpointFormKeyBlock(_Base):
    """端点编辑/新增表单的 Key 区块切换。"""

    def test_edit_form_has_manage_block_no_input(self):
        """编辑态：含「API Key 管理」区块；不含旧 api_key 输入框。"""
        eid = self._add_endpoint()
        config_db.add_api_key(self.conn, eid, "Key1", "sk-abcdefgh1234")
        html = render.build_api_endpoint_form_html(
            1, "测试报表", db.get_api_endpoint(self.conn, eid),
            result_names_list=[], result_count=1,
            endpoint_id=eid, is_edit=True,
            api_keys=config_db.list_api_keys(self.conn, eid))
        self.assertIn("🔑 API Key 管理", html)
        self.assertNotIn('name="api_key"', html)
        self.assertNotIn("留空=无需鉴权", html)

    def test_new_form_shows_auto_generate_hint(self):
        """新增态：含自动生成提示；不含管理区块。"""
        html = render.build_api_endpoint_form_html(
            1, "测试报表", None, result_names_list=[], result_count=1,
            endpoint_id=None, is_edit=False)
        self.assertIn("保存后将自动生成 API Key", html)
        self.assertNotIn("🔑 API Key 管理", html)
        self.assertNotIn('name="api_key"', html)

    def test_edit_save_button_inside_main_form_only(self):
        """回归（嵌套 form 破坏保存）：编辑态保存按钮必须位于主表单内。

        API Key 管理区块含独立 <form>（toggle/删除/生成），若被插入主表单
        内部，HTML5 解析会提前闭合主表单，保存按钮脱离表单，点击无反应。
        """
        eid = self._add_endpoint()
        config_db.add_api_key(self.conn, eid, "Key1", "sk-abcdefgh1234")
        html = render.build_api_endpoint_form_html(
            1, "测试报表", db.get_api_endpoint(self.conn, eid),
            result_names_list=[], result_count=1,
            endpoint_id=eid, is_edit=True,
            api_keys=config_db.list_api_keys(self.conn, eid))
        # HTML5 语义：嵌套 <form> 开始标签被忽略，第一个 </form> 闭合主表单。
        # 主 form 是页面第一个 <form>；其内部若含嵌套 form，第一个 </form> 会
        # 提前闭合主表单，导致保存按钮脱离表单。
        main_start, main_end = htmlcheck.main_form_span(
            html, action_hint=f"/config/reports/1/api_endpoints/{eid}/edit")
        main_span = html[main_start:main_end]
        self.assertIn('name="action" value="save"', main_span,
                      "保存按钮必须位于主表单内")
        self.assertIn('name="action" value="save_close"', main_span,
                      "保存并关闭按钮必须位于主表单内")
        self.assertNotIn("🔑 API Key 管理", main_span,
                         "API Key 管理区块不得嵌套在主表单内")
        self.assertEqual(html.count("🔑 API Key 管理"), 1,
                         "API Key 管理区块只能渲染一次")


class TestEndpointsListKeyCounts(_Base):
    """端点列表 key 数量徽标。"""

    def test_counts_badge(self):
        """key_counts 提供时显示 N 个 Key。"""
        eid = self._add_endpoint()
        config_db.add_api_key(self.conn, eid, "Key1", "sk-1")
        config_db.add_api_key(self.conn, eid, "Key2", "sk-2")
        ep = db.get_api_endpoint(self.conn, eid)
        html = render.build_api_endpoints_list_html(
            [ep], base_url="http://x", key_counts={eid: 2})
        self.assertIn("2 个 Key", html)

    def test_counts_zero_dash(self):
        """无 Key → 显示 —。"""
        eid = self._add_endpoint()
        ep = db.get_api_endpoint(self.conn, eid)
        html = render.build_api_endpoints_list_html(
            [ep], base_url="http://x", key_counts={})
        self.assertIn("—", html)

    def test_fallback_legacy_column_when_no_counts(self):
        """key_counts 未提供 → 回退旧 api_key 列掩码+复制。"""
        eid = self._add_endpoint(api_key="sk-legacy1234")
        ep = db.get_api_endpoint(self.conn, eid)
        html = render.build_api_endpoints_list_html(
            [ep], base_url="http://x")
        self.assertIn("sk-l***1234", html)  # 前4后4：sk-l + *** + 1234
        self.assertIn("复制", html)


if __name__ == "__main__":
    unittest.main()
