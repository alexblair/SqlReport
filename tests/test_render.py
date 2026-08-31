"""test_render.py — HTML 渲染模板函数测试

筛选匹配表达式批次覆盖（T2/T4，渲染层断言）：
- 筛选值 URL 回路往返（build_filter_params → parse_qs → parse_filters 原值，
  空值按现状契约返回 []）— TestFilterUrlRoundtrip
- 列头筛选输入框 placeholder 带（*通配,多值）提示、悬停 title
- 筛选操作区 ? 帮助入口（默认收起弹窗 + toggle JS）— TestFilterActionHtml
"""

import unittest
import urllib.parse
import json
import re
from datetime import datetime
from decimal import Decimal
import report as report_mod
from filter_help import FILTER_HINT_SUFFIX
from render import (
    render_page_header, render_page_footer, render_navbar,
    # URL 参数工具
    build_sort_params, build_filter_params, filter_hidden_inputs, build_cols_param,
    # 单元格格式化与转义
    format_cell, _escape,
    # 筛选操作符常量
    FILTER_OPS, _OP_MAP, DEFAULT_OP,
    # 分页
    build_pagination_html,
    # Redis 横幅
    build_redis_banners_html,
    # Debug 区
    build_debug_section_html,
    # 备注区
    build_memo_section_html,
    # Markdown 排版 CSS
    _MD_CSS,
    # 结果切换
    build_result_selector_html,
    # 缓存标签
    build_cache_badge_html,
    # 排序栏
    build_sort_bar_html,
    # 表头
    build_table_header_html,
    # 表体
    build_table_body_html,
    # 控制栏
    build_controls_bar_html,
    # 字段设置面板
    build_field_settings_panel_html,
    # 排序设置面板
    build_sort_settings_panel_html,
    # 筛选表单
    build_filter_form_html,
    # 筛选操作
    build_filter_action_html,
    # 报表切换器
    build_report_switcher_html,
    # 按钮辅助
    _link_btn, build_move_buttons_html,
    # 表单渲染器
    build_pool_form_html, build_user_form_html,
    # 配置段渲染器
    build_pool_section_html, build_user_section_html, build_category_section_html,
    # 分类选项
    build_category_opts_html,
    # 当前规则区
    build_current_rules_section_html,
    # API 端点表单
    build_api_endpoint_form_html,
    # API 端点列表
    build_api_endpoints_list_html,
    # API URL 折叠区
    build_api_urls_section_html,
    # API 接口说明 Markdown 折叠区（api-desc-markdown T3）
    _build_api_description_html,
    # 接口说明列表摘要（纯文本守护，api-desc-markdown T3）
    _build_desc_summary_html,
    # 折叠区骨架
    build_collapse_section_html,
    # 公共 CSS/JS 常量
    _COMMON_CSS, _COMMON_JS,
)


class TestRenderPageHeader(unittest.TestCase):
    """render_page_header 函数测试"""

    def test_contains_doctype_and_html(self):
        """输出包含 DOCTYPE 和 html 根标签"""
        result = render_page_header()
        self.assertIn("<!DOCTYPE html>", result)
        self.assertIn("<html", result)
        self.assertIn("</head>", result)
        self.assertIn("<body>", result)

    def test_contains_title(self):
        """输出包含页面标题"""
        result = render_page_header(title="测试标题")
        self.assertIn("测试标题", result)

    def test_default_title(self):
        """不传 title 时使用默认标题"""
        result = render_page_header()
        self.assertIn("Web 报表工具", result)

    def test_contains_navbar(self):
        """输出包含导航栏"""
        result = render_page_header()
        self.assertIn('My<span>Report</span>', result)

    def test_navbar_has_api_entry(self):
        """导航栏包含 API 接口独立入口"""
        result = render_page_header()
        self.assertIn("API 接口", result)
        self.assertIn('href="/config/api-endpoints"', result)

    def test_contains_container_div(self):
        """输出包含 container div 开头"""
        result = render_page_header()
        self.assertIn('<div class="container">', result)

    def test_active_nav_report(self):
        """active_nav='report' 时报表页链接高亮"""
        result = render_page_header(active_nav="report")
        self.assertIn('报表页', result)
        self.assertIn('nav-active', result)

    def test_active_nav_config(self):
        """active_nav='config' 时配置页链接高亮"""
        result = render_page_header(active_nav="config")
        self.assertIn('配置管理', result)
        self.assertIn('nav-active', result)


class TestRenderPageFooter(unittest.TestCase):
    """render_page_footer 函数测试"""

    def test_contains_closing_tags(self):
        """输出包含 container 闭合和 body/html 闭合"""
        result = render_page_footer()
        self.assertIn('</div>', result)  # container close
        self.assertIn('</body>', result)
        self.assertIn('</html>', result)

    def test_contains_javascript(self):
        """输出包含 JavaScript 脚本（批次6#28 后为版本锁外链 <script defer>）

        找茬 M2a：测试环境资产落点已重定向到临时目录（tests/__init__.py），
        外链路径稳定可达，不再 or 内联双分支通吃——只钉住外链形式。
        """
        result = render_page_footer()
        self.assertIn('src="/static/vendor/self@', result)
        self.assertIn('common.js" defer></script>', result)


class TestRenderNavbar(unittest.TestCase):
    """render_navbar 函数测试"""

    def test_contains_brand(self):
        """导航栏包含品牌名"""
        result = render_navbar()
        self.assertIn('My<span>Report</span>', result)

    def test_contains_nav_links(self):
        """导航栏包含所有主要链接"""
        result = render_navbar()
        self.assertIn('/report', result)
        self.assertIn('/config', result)
        self.assertIn('/logout', result)

    def test_active_report(self):
        """active='report' 时报表页获得 nav-active"""
        result = render_navbar(active="report")
        self.assertIn('nav-active', result)
        # 确保 active 不会出现在每个链接上
        self.assertEqual(result.count('nav-active'), 1)

    def test_active_config(self):
        """active='config' 时配置页获得 nav-active"""
        result = render_navbar(active="config")
        self.assertIn('nav-active', result)
        self.assertEqual(result.count('nav-active'), 1)

    def test_no_active_default(self):
        """不传 active 时无 nav-active"""
        result = render_navbar()
        self.assertNotIn('nav-active', result)


class TestRenderFullPage(unittest.TestCase):
    """完整页面组合测试"""

    def test_header_footer_produces_valid_skeleton(self):
        """header + body + footer 组合为完整 HTML"""
        header = render_page_header(title="组合测试", active_nav="report")
        body_content = '<div class="card"><p>测试内容</p></div>'
        footer = render_page_footer()
        full_html = header + body_content + footer

        self.assertIn("<!DOCTYPE html>", full_html)
        self.assertIn("组合测试", full_html)
        self.assertIn("测试内容", full_html)
        self.assertIn("</html>", full_html)
        # head 在 body 之前，footer 在内容之后
        self.assertLess(full_html.index("</head>"), full_html.index("测试内容"))
        self.assertLess(full_html.index("测试内容"), full_html.index("</body>"))


# ===================================================================
# 筛选操作符常量测试
# ===================================================================


class TestFilterOpsConstants(unittest.TestCase):
    """FILTER_OPS / _OP_MAP / DEFAULT_OP 常量测试"""

    def test_filer_ops_is_list_of_tuples(self):
        """FILTER_OPS 是三元组列表"""
        self.assertIsInstance(FILTER_OPS, list)
        for item in FILTER_OPS:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 3)

    def test_default_op_is_contains(self):
        """DEFAULT_OP 默认为 contains"""
        self.assertEqual(DEFAULT_OP, "contains")

    def test_op_map_contains_all_ops(self):
        """_OP_MAP 包含 FILTER_OPS 中所有条目"""
        for code, label, short in FILTER_OPS:
            self.assertIn(code, _OP_MAP)
            self.assertEqual(_OP_MAP[code], (label, short))

    def test_op_map_keys_match_codes(self):
        """_OP_MAP 的 key 等于各操作符的 code"""
        for code, _, _ in FILTER_OPS:
            self.assertIn(code, _OP_MAP)

    def test_notcontains_in_ops_and_map(self):
        """notcontains 操作符存在于 FILTER_OPS 且 _OP_MAP 派生对应 label/short"""
        codes = [code for code, _, _ in FILTER_OPS]
        self.assertIn("notcontains", codes)
        self.assertEqual(_OP_MAP["notcontains"], ("不包含", "不包含"))
        # notcontains 紧邻 contains（语义取反，交互就近）
        self.assertEqual(codes.index("notcontains"), codes.index("contains") + 1)


# ===================================================================
# URL 参数工具测试
# ===================================================================


class TestBuildSortParams(unittest.TestCase):
    """build_sort_params 函数测试"""

    def test_single_sort(self):
        """单个排序字段生成正确 URL 参数"""
        result = build_sort_params([("name", "asc")])
        self.assertIn("sort=name", result)
        self.assertIn("dir=asc", result)

    def test_multi_sort(self):
        """多个排序字段用 & 连接"""
        result = build_sort_params([("name", "asc"), ("age", "desc")])
        self.assertIn("sort=name&dir=asc", result)
        self.assertIn("sort=age&dir=desc", result)

    def test_empty_sorts_returns_empty(self):
        """空列表返回空字符串"""
        result = build_sort_params([])
        self.assertEqual(result, "")

    def test_url_encoding(self):
        """列名含特殊字符时做 URL 编码"""
        result = build_sort_params([("first name", "asc")])
        # 空格被编码为 %20，原始空格不应出现
        self.assertNotIn("first name", result)
        self.assertIn("first%20name", result)


class TestBuildFilterParams(unittest.TestCase):
    """build_filter_params 函数测试"""

    def test_normal_filter_with_op(self):
        """普通筛选含操作符"""
        result = build_filter_params([("age", "gt", "18")])
        self.assertIn("f_age=18", result)
        self.assertIn("op_age=gt", result)

    def test_nofilter_skipped(self):
        """nofilter 操作被跳过"""
        result = build_filter_params([("age", "nofilter", "")])
        self.assertEqual(result, "")

    def test_default_op_omitted(self):
        """默认操作符（contains）不生成 op_ 参数"""
        result = build_filter_params([("name", "contains", "foo")])
        self.assertIn("f_name=foo", result)
        self.assertNotIn("op_name", result)

    def test_notcontains_roundtrip(self):
        """notcontains 非默认操作符 → 编码 op_ 参数（URL 往返可还原）"""
        result = build_filter_params([("name", "notcontains", "临时")])
        self.assertIn("f_name=", result)
        self.assertIn(urllib.parse.quote("临时"), result)
        self.assertIn("op_name=notcontains", result)

    def test_notcontains_hidden_input(self):
        """notcontains 非默认 → 生成 op_ 隐藏 input"""
        result = filter_hidden_inputs([("name", "notcontains", "临时")])
        self.assertIn('name="f_name"', result)
        self.assertIn('name="op_name"', result)
        self.assertIn('value="notcontains"', result)

    def test_skip_col(self):
        """skip_col 跳过指定列"""
        result = build_filter_params([("name", "eq", "foo"), ("age", "gt", "18")], skip_col="name")
        self.assertNotIn("f_name", result)
        self.assertIn("f_age=18", result)

    def test_empty_filters(self):
        """空列表返回空字符串"""
        result = build_filter_params([])
        self.assertEqual(result, "")

    def test_url_encoding_for_column_name(self):
        """列名含特殊字符时做 URL 编码"""
        result = build_filter_params([("user name", "eq", "foo")])
        # 空格被编码为 +
        self.assertIn("f_user", result)


class TestFilterHiddenInputs(unittest.TestCase):
    """filter_hidden_inputs 函数测试"""

    def test_normal_filter(self):
        """生成带操作符的隐藏 input"""
        result = filter_hidden_inputs([("age", "gt", "18")])
        self.assertIn('<input type="hidden"', result)
        self.assertIn('name="f_age"', result)
        self.assertIn('name="op_age"', result)
        self.assertIn('value="18"', result)

    def test_nofilter_skipped(self):
        """nofilter 操作不生成 input"""
        result = filter_hidden_inputs([("age", "nofilter", "")])
        self.assertEqual(result, "")

    def test_default_op_omitted(self):
        """默认操作符不生成 op_ input"""
        result = filter_hidden_inputs([("name", "contains", "foo")])
        self.assertIn('name="f_name"', result)
        self.assertNotIn('op_name', result)

    def test_html_escaping_in_value(self):
        """值中的特殊字符被 HTML 转义"""
        result = filter_hidden_inputs([("name", "eq", '<test&">')])
        self.assertIn("&lt;test", result)
        self.assertIn("&amp;", result)
        self.assertNotIn('<test&">', result)

    def test_empty_filters(self):
        """空列表返回空字符串"""
        result = filter_hidden_inputs([])
        self.assertEqual(result, "")


class TestFilterUrlRoundtrip(unittest.TestCase):
    r"""筛选值 URL 回路往返：输入 → build_filter_params → parse_qs → parse_filters → 原值

    匹配表达式语法（`*`、逗号多值、`\` 转义）使值含特殊字符成为常态，
    往返必须不丢字符、不被误解（HTML 转义与 URL 编码互不冲突）。
    """

    def _roundtrip(self, filters):
        qs_str = build_filter_params(filters)
        qs = urllib.parse.parse_qs(qs_str, keep_blank_values=True)
        return report_mod.parse_filters(qs)

    def test_wildcard_value_roundtrip(self):
        """含 * 的值往返不丢"""
        result = self._roundtrip([("name", "contains", "张*明")])
        self.assertEqual(result, [("name", "contains", "张*明")])

    def test_multivalue_roundtrip(self):
        """含逗号的值往返不丢（编码后不被误解为多个参数）"""
        result = self._roundtrip([("city", "contains", "北京,上海")])
        self.assertEqual(result, [("city", "contains", "北京,上海")])

    def test_escape_sequence_roundtrip(self):
        """含转义序列的值往返不丢（\\* \\, \\\\）"""
        result = self._roundtrip([("name", "contains", r"a\*b")])
        self.assertEqual(result, [("name", "contains", r"a\*b")])
        result2 = self._roundtrip([("name", "contains", r"1\,234")])
        self.assertEqual(result2, [("name", "contains", r"1\,234")])
        result3 = self._roundtrip([("name", "contains", r"a\\b")])
        self.assertEqual(result3, [("name", "contains", r"a\\b")])

    def test_ampersand_and_equals_in_value(self):
        """值含 & 与 = 时往返不丢（state_machine 风险点）"""
        result = self._roundtrip([("name", "contains", "a&b=c")])
        self.assertEqual(result, [("name", "contains", "a&b=c")])

    def test_empty_value_roundtrip(self):
        """空值不产生条件（parse_filters 现状契约：空值跳过）"""
        result = self._roundtrip([("name", "contains", "")])
        self.assertEqual(result, [])

    def test_hidden_inputs_preserve_special_values(self):
        """隐藏 input 保留通配/多值/转义原文（HTML 转义不破坏字符）"""
        html = filter_hidden_inputs([("city", "contains", "北京,上海")])
        self.assertIn("北京,上海", html)
        html2 = filter_hidden_inputs([("name", "contains", r"a\*b")])
        self.assertIn(r"a\*b", html2)


class TestBuildColsParam(unittest.TestCase):
    """build_cols_param 函数测试"""

    def test_default_order_returns_empty(self):
        """display_columns 等于 all_columns 时返回空"""
        result = build_cols_param(["a", "b", "c"], ["a", "b", "c"])
        self.assertEqual(result, "")

    def test_custom_order_returns_param(self):
        """自定义列顺序生成 cols 参数（URL 编码逗号）"""
        result = build_cols_param(["c", "a", "b"], ["a", "b", "c"])
        self.assertIn("cols=", result)
        # 逗号被 URL 编码为 %2C
        self.assertIn("c%2Ca%2Cb", result)

    def test_hidden_columns(self):
        """display_columns 为子集时生成 cols 参数（URL 编码逗号）"""
        result = build_cols_param(["a", "c"], ["a", "b", "c"])
        self.assertIn("cols=", result)
        self.assertIn("a%2Cc", result)
        self.assertNotIn("b", result)

    def test_empty_lists(self):
        """两个空列表返回空字符串"""
        result = build_cols_param([], [])
        self.assertEqual(result, "")


# ===================================================================
# 单元格格式化与转义测试
# ===================================================================


class TestFormatCell(unittest.TestCase):
    """format_cell 函数测试"""

    def test_none_returns_empty(self):
        """None 返回空字符串"""
        self.assertEqual(format_cell(None), "")

    def test_decimal_zero(self):
        """Decimal(0) 返回 '0'"""
        self.assertEqual(format_cell(Decimal("0")), "0")
        self.assertEqual(format_cell(Decimal("0.00")), "0")

    def test_decimal_normal(self):
        """Decimal 正常值去除尾部零"""
        self.assertEqual(format_cell(Decimal("1.500")), "1.5")
        self.assertEqual(format_cell(Decimal("100")), "100")

    def test_float_normal(self):
        """float 正常值"""
        self.assertEqual(format_cell(3.14), "3.14")

    def test_float_scientific_notation(self):
        """float 科学计数法转为全小数"""
        result = format_cell(1e-10)
        self.assertNotIn("e", result.lower())
        self.assertNotIn("E", result)

    def test_float_zero(self):
        """float 0 返回 '0'"""
        self.assertEqual(format_cell(0.0), "0")

    def test_negative_zero(self):
        """负零归一为零"""
        val = Decimal("-0.00")
        self.assertEqual(format_cell(val), "0")

    def test_string_returned_as_is(self):
        """字符串原样返回"""
        self.assertEqual(format_cell("hello"), "hello")

    def test_integer(self):
        """整数直接转字符串"""
        self.assertEqual(format_cell(42), "42")

    def test_large_decimal(self):
        """大 Decimal 去除尾部零"""
        self.assertEqual(format_cell(Decimal("123.456000")), "123.456")


class TestEscape(unittest.TestCase):
    """_escape 函数测试"""

    def test_html_escaping(self):
        """HTML 特殊字符被转义"""
        result = _escape('<script>alert("xss")</script>')
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script>", result)

    def test_none_returns_empty(self):
        """None 返回空字符串"""
        self.assertEqual(_escape(None), "")

    def test_normal_string_unchanged(self):
        """普通字符串保持不变"""
        self.assertEqual(_escape("hello"), "hello")

    def test_ampersand_escaped(self):
        """& 被转义"""
        self.assertEqual(_escape("a&b"), "a&amp;b")

    def test_decimal_handled(self):
        """Decimal 值经过 format_cell 后转义"""
        self.assertEqual(_escape(Decimal("0")), "0")
        self.assertEqual(_escape(Decimal("1.50")), "1.5")


# ===================================================================
# 分页 HTML 测试
# ===================================================================


class TestBuildPaginationHtml(unittest.TestCase):
    """build_pagination_html 函数测试"""

    def test_single_page_returns_empty(self):
        """total_pages <= 1 返回空字符串"""
        result = build_pagination_html(1, 1, 1, 20, 10)
        self.assertEqual(result, "")

    def test_zero_pages_returns_empty(self):
        """total_pages = 0 返回空字符串"""
        result = build_pagination_html(1, 0, 0, 20, 0)
        self.assertEqual(result, "")

    def test_multi_page_has_pagination_div(self):
        """多页时包含分页容器"""
        result = build_pagination_html(1, 1, 5, 20, 100)
        self.assertIn('<div class="pagination">', result)

    def test_prev_next_arrows(self):
        """包含前后导航箭头"""
        result = build_pagination_html(1, 3, 5, 20, 100)
        self.assertIn("‹", result)
        self.assertIn("›", result)

    def test_first_page_disabled_prev(self):
        """第一页时前翻箭头禁用"""
        result = build_pagination_html(1, 1, 5, 20, 100)
        self.assertIn('class="disabled"', result)
        self.assertIn("‹", result)

    def test_last_page_disabled_next(self):
        """最后一页时后翻箭头禁用"""
        result = build_pagination_html(1, 5, 5, 20, 100)
        self.assertIn('class="disabled"', result)
        self.assertIn("›", result)

    def test_current_page_active(self):
        """当前页显示为 active span"""
        result = build_pagination_html(1, 3, 5, 20, 100)
        self.assertIn('<span class="active">3</span>', result)

    def test_jump_box_present(self):
        """包含跳转输入框"""
        result = build_pagination_html(1, 3, 5, 20, 100)
        self.assertIn("跳转到:", result)
        self.assertIn('id="jump_page"', result)
        self.assertIn("GO", result)

    def test_contains_report_id(self):
        """分页链接包含 report id"""
        result = build_pagination_html(42, 1, 5, 20, 100)
        self.assertIn("id=42", result)

    def test_contains_page_size(self):
        """分页链接包含 page_size"""
        result = build_pagination_html(1, 1, 5, 50, 100)
        self.assertIn("page_size=50", result)

    def test_contains_sort_params(self):
        """包含排序参数"""
        result = build_pagination_html(1, 1, 5, 20, 100, sorts=[("name", "asc")])
        self.assertIn("sort=name", result)
        self.assertIn("dir=asc", result)

    def test_contains_filter_params(self):
        """包含筛选参数"""
        result = build_pagination_html(1, 1, 5, 20, 100, filters=[("age", "gt", "18")])
        self.assertIn("f_age=18", result)

    def test_contains_cols_param(self):
        """包含自定义列参数"""
        result = build_pagination_html(1, 1, 5, 20, 100, cols_param="cols=a%2Cb")
        self.assertIn("cols=", result)

    def test_contains_result_param(self):
        """包含多结果集参数"""
        result = build_pagination_html(1, 1, 5, 20, 100, result_param="result=0")
        self.assertIn("result=0", result)


# ===================================================================
# Redis 横幅测试
# ===================================================================


class TestBuildRedisBannersHtml(unittest.TestCase):
    """build_redis_banners_html 函数测试"""

    def test_empty_cache_info_returns_empty(self):
        """cache_info 为空时返回空字符串"""
        self.assertEqual(build_redis_banners_html(None), "")
        self.assertEqual(build_redis_banners_html({}), "")

    def test_redis_source_shows_banner(self):
        """Redis 来源显示快照时间"""
        ts = datetime.now().timestamp()
        result = build_redis_banners_html({"source": "redis", "timestamp": ts})
        self.assertIn("flash", result)
        self.assertIn("Redis 快照", result)


# ===================================================================
# Debug 区测试
# ===================================================================


class TestBuildDebugSectionHtml(unittest.TestCase):
    """build_debug_section_html 函数测试"""

    def test_minimal(self):
        """最小输入生成基本 debug 信息"""
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["result1"], [], [])
        self.assertIn("Debug", result)
        self.assertIn("SELECT 1", result)
        self.assertIn("debug-info", result)

    def test_with_pool_config(self):
        """含连接池配置时显示连接信息"""
        pool = {"name": "主库", "host": "10.0.0.1", "port": 3306, "user": "root", "database": "mydb"}
        result = build_debug_section_html(pool, "SELECT *", 0, 1, ["r1"], [], [])
        self.assertIn("主库", result)
        self.assertIn("10.0.0.1", result)
        self.assertIn("mydb", result)

    def test_with_sorts_and_filters(self):
        """含排序和筛选条件时显示"""
        result = build_debug_section_html(None, "SELECT *", 0, 1, ["r1"],
                                           [("name", "eq", "foo")],
                                           [("name", "asc")])
        self.assertIn("筛选:", result)
        self.assertIn("排序:", result)

    def test_multi_result_shows_index(self):
        """多结果集时显示结果序号"""
        result = build_debug_section_html(None, "SELECT *", 1, 3, ["a", "b", "c"], [], [])
        self.assertIn("2/3", result)
        self.assertIn("b", result)

    def test_toggle_section_script(self):
        """包含折叠按钮"""
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["r1"], [], [])
        self.assertIn("toggleSection", result)
        self.assertIn("▶ Debug 信息", result)


# ===================================================================
# 备注区测试
# ===================================================================


class TestBuildMemoSectionHtml(unittest.TestCase):
    """build_memo_section_html 函数测试"""

    def test_with_memo(self):
        """有备注内容时默认折叠（批次6#24），内容仍在 DOM 中"""
        result = build_memo_section_html("这是一段备注内容")
        self.assertIn("▶ 备注", result)
        self.assertIn('class="debug-content hidden"', result)
        self.assertIn("这是一段备注内容", result)
        self.assertIn("debug-info", result)

    def test_memo_wrapped_in_md_body(self):
        """渲染内容外包 .md-body 排版容器（列表缩进等样式由 _MD_CSS 提供）"""
        result = build_memo_section_html("这是备注")
        self.assertIn('<div class="md-body">', result)
        result_empty = build_memo_section_html("")
        self.assertNotIn("md-body", result_empty)

    def test_empty_memo(self):
        """备注为空时显示折叠状态"""
        result = build_memo_section_html("")
        self.assertIn("▶ 备注", result)

    def test_none_memo(self):
        """备注为 None 时显示折叠状态"""
        result = build_memo_section_html(None)
        self.assertIn("▶ 备注", result)

    def test_memo_html_sanitized(self):
        """备注中的 raw HTML 被 sanitize 剥离（脚本标签移除、文本保留）"""
        result = build_memo_section_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", result)
        self.assertIn("alert(1)", result)

    def test_memo_markdown_rendered(self):
        """备注按 Markdown 渲染为结构化 HTML"""
        result = build_memo_section_html("# 标题\n\n- a\n- b")
        self.assertIn("<h1>标题</h1>", result)
        self.assertIn("<ul>", result)
        self.assertIn("<li>a</li>", result)

    def test_memo_mermaid_codeblock(self):
        """备注含 ```mermaid 块时输出 <pre class="mermaid">"""
        result = build_memo_section_html("```mermaid\nflowchart TD\n A-->B\n```")
        self.assertIn('<pre class="mermaid">', result)

    def test_memo_empty_markdown_empty(self):
        """空备注渲染为空内容"""
        self.assertNotIn("<p>", build_memo_section_html(""))

    def test_md_css_restores_list_indent_and_dark_code(self):
        """_MD_CSS 为嵌套列表补回缩进（全局 reset 清掉了 ul/ol 默认 padding）、
        代码块深色化、mermaid 容器白底独立处理"""
        self.assertIn("padding-left: 1.6em", _MD_CSS)
        self.assertIn(".md-body pre.mermaid", _MD_CSS)
        self.assertIn("background: #0f172a", _MD_CSS)

    def test_long_memo(self):
        """长备注全部渲染在 DOM 中（默认折叠，批次6#24）"""
        long_text = "A" * 1000
        result = build_memo_section_html(long_text)
        self.assertIn("A" * 1000, result)
        self.assertIn("▶ 备注", result)


# ===================================================================
# 结果切换器测试
# ===================================================================


class TestBuildResultSelectorHtml(unittest.TestCase):
    """build_result_selector_html 函数测试"""

    def test_single_result_returns_empty(self):
        """仅一个结果时返回空字符串"""
        result = build_result_selector_html(1, 20, ["单结果"], 0, None, "tok")
        self.assertEqual(result, "")

    def test_multi_result_has_selector(self):
        """多个结果时包含下拉选择"""
        result = build_result_selector_html(1, 20, ["日报", "月报", "年报"], 0, None, "tok123")
        self.assertIn("result-selector", result)
        self.assertIn("结果视图:", result)
        self.assertIn("日报", result)
        self.assertIn("月报", result)
        self.assertIn("年报", result)

    def test_active_selected(self):
        """当前激活的结果标记为 selected"""
        result = build_result_selector_html(1, 20, ["a", "b", "c"], 1, None, "tok")
        self.assertIn('<option value="1" selected', result)

    def test_contains_data_attributes(self):
        """包含 data-report-id 等属性"""
        result = build_result_selector_html(42, 50, ["a", "b"], 1, "SELECT 1", "swi_abc")
        self.assertIn('data-report-id="42"', result)
        self.assertIn('data-active-index="1"', result)
        self.assertIn('data-swi="swi_abc"', result)
        self.assertIn('data-page-size="50"', result)

    def test_sql_override_in_data_attribute(self):
        """SQL 覆盖参数包含在 data-sql-override 属性中"""
        result = build_result_selector_html(1, 20, ["a", "b"], 0, "SELECT *", "tok")
        self.assertIn('data-sql-override="SELECT *"', result)

    def test_state_tip_always_shown_for_multi(self):
        """PH-11 多结果集下拉旁显示状态独立提示文案"""
        result = build_result_selector_html(1, 20, ["a", "b"], 0, None, "tok")
        self.assertIn("每个结果视图独立维护筛选/排序/分页状态", result)

    def test_no_badge_without_filters_sorts(self):
        """PH-11 无筛选/排序时不显示状态角标"""
        result = build_result_selector_html(1, 20, ["a", "b"], 0, None, "tok")
        self.assertNotIn("已筛选", result)
        self.assertNotIn("已排序", result)

    def test_badges_with_filters_and_sorts(self):
        """PH-11 有筛选/排序时显示角标（sort-tag 样式）"""
        result = build_result_selector_html(
            1, 20, ["a", "b"], 0, None, "tok",
            filters=[("name", "contains", "x")],
            sorts=[("id", "desc")])
        self.assertIn("已筛选 ×1", result)
        self.assertIn("已排序 ×1", result)
        self.assertIn('class="sort-tag"', result)

    def test_badge_counts_multiple(self):
        """PH-11 角标计数与筛选/排序条数一致"""
        result = build_result_selector_html(
            1, 20, ["a", "b"], 0, None, "tok",
            filters=[("a", "eq", "1"), ("b", "contains", "2")],
            sorts=[("id", "asc"), ("name", "desc"), ("x", "asc")])
        self.assertIn("已筛选 ×2", result)
        self.assertIn("已排序 ×3", result)


# ===================================================================
# 缓存标签测试
# ===================================================================


class TestBuildCacheBadgeHtml(unittest.TestCase):
    """build_cache_badge_html 函数测试"""

    def test_no_cache_info(self):
        """cache_info 为 None 显示未缓存"""
        result = build_cache_badge_html(None)
        self.assertIn("未缓存", result)
        self.assertIn("cache-badge", result)

    def test_redis_source(self):
        """Redis 来源显示快照"""
        result = build_cache_badge_html({"source": "redis", "timestamp": 1000000})
        self.assertIn("Redis 快照", result)
        self.assertIn("fresh", result)

    def test_mysql_source(self):
        """MySQL 来源显示直连"""
        result = build_cache_badge_html({"source": "mysql"})
        self.assertIn("直连 MySQL", result)

    def test_redis_fallback_source(self):
        """Redis 降级来源"""
        result = build_cache_badge_html({"source": "redis_fallback", "timestamp": 1000000})
        self.assertIn("缓存快照", result)

    def test_process_source(self):
        """进程缓存来源"""
        result = build_cache_badge_html({"source": "process", "timestamp": 1000000})
        self.assertIn("进程缓存", result)


# ===================================================================
# 排序栏测试
# ===================================================================


class TestBuildSortBarHtml(unittest.TestCase):
    """build_sort_bar_html 函数测试"""

    def test_no_sorts_returns_empty(self):
        """没有排序时返回空字符串"""
        result = build_sort_bar_html(1, 20, [], [], "", "")
        self.assertEqual(result, "")

    def test_single_sort(self):
        """单个排序字段"""
        result = build_sort_bar_html(1, 20, [("name", "asc")], [], "", "")
        self.assertIn("sort-bar", result)
        self.assertIn("name", result)
        self.assertIn("↑", result)

    def test_multi_sort_with_priority(self):
        """多字段排序显示优先级编号"""
        result = build_sort_bar_html(1, 20, [("name", "asc"), ("age", "desc")], [], "", "")
        self.assertIn("①", result)
        self.assertIn("②", result)

    def test_remove_sort_link(self):
        """每个排序标签含移除链接"""
        result = build_sort_bar_html(1, 20, [("name", "asc")], [], "", "")
        self.assertIn("✕", result)
        self.assertIn("移除排序", result)

    def test_desc_sort_shows_down_arrow(self):
        """降序显示 ↓"""
        result = build_sort_bar_html(1, 20, [("age", "desc")], [], "", "")
        self.assertIn("↓", result)


# ===================================================================
# 表头测试
# ===================================================================


class TestBuildTableHeaderHtml(unittest.TestCase):
    """build_table_header_html 函数测试"""

    def test_basic_columns(self):
        """基础列生成 th 元素（批次6#25 起携带 data-col 定位属性）"""
        cols = ["id", "name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn('<th data-col="id">', result)
        self.assertIn('<th data-col="name">', result)
        self.assertIn("id", result)
        self.assertIn("name", result)

    def test_sort_arrows_present(self):
        """包含排序箭头"""
        cols = ["id", "name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn("sort-arrow", result)
        self.assertIn("▲", result)
        self.assertIn("▼", result)

    def test_active_sort_highlight(self):
        """当前排序列箭头高亮"""
        cols = ["id", "name"]
        result = build_table_header_html(cols, cols, [("name", "asc")], [], 1, 20, "", "")
        # name 列的升序箭头应高亮
        self.assertIn("sort-arrow active", result)

    def test_filter_dropdown_present(self):
        """每列包含筛选操作符下拉框"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn("filter-op", result)
        self.assertIn("contains", result)
        self.assertIn("不筛选", result)

    def test_filter_dropdown_has_notcontains(self):
        """下拉框包含不包含操作符选项（值=notcontains，标签=不包含）"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn('value="notcontains"', result)
        self.assertIn(">不包含<", result)

    def test_filter_notcontains_selected(self):
        """当前 notcontains 筛选在下拉中为选中态且输入框可见"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [("name", "notcontains", "临时")], 1, 20, "", "")
        self.assertIn('<option value="notcontains" selected', result)
        self.assertIn('value="临时"', result)
        # notcontains 非无值操作符 → 输入框不禁用
        self.assertNotIn('name="f_name" disabled', result)

    def test_filter_input_present(self):
        """每列包含筛选输入框"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn("filter-input", result)
        self.assertIn(f'placeholder="筛选 name{FILTER_HINT_SUFFIX}"', result)

    def test_filter_input_placeholder_hint(self):
        """筛选输入框 placeholder 带统一语法提示（引用单一来源常量）"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn(FILTER_HINT_SUFFIX, result)

    def test_current_filter_value(self):
        """显示当前筛选值"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [("name", "contains", "test")], 1, 20, "", "")
        self.assertIn('value="test"', result)

    def test_sort_priority_badge(self):
        """多字段排序显示优先级"""
        cols = ["id", "name"]
        result = build_table_header_html(cols, cols, [("name", "asc"), ("id", "desc")], [], 1, 20, "", "")
        # name 应显示优先级 ①，id 应显示 ②
        self.assertIn("sort-prio", result)

    def test_display_columns_subset(self):
        """display_columns 为子集时仅显示部分列"""
        all_cols = ["id", "name", "age"]
        display = ["name", "age"]
        result = build_table_header_html(all_cols, display, [], [], 1, 20, "", "")
        self.assertIn("name", result)
        self.assertIn("age", result)
        # id 不应出现在表头
        self.assertNotIn(">id<", result)


# ===================================================================
# 表体测试
# ===================================================================


class TestBuildTableBodyHtml(unittest.TestCase):
    """build_table_body_html 函数测试"""

    def test_empty_rows_shows_no_data(self):
        """空数据行显示暂无数据"""
        result = build_table_body_html([], [0, 1])
        self.assertIn("暂无数据", result)
        self.assertIn("empty-state", result)

    def test_single_row(self):
        """单行数据"""
        rows = [("Alice", 30)]
        result = build_table_body_html(rows, [0, 1])
        self.assertIn("<tr>", result)
        self.assertIn("<td>", result)
        self.assertIn("Alice", result)
        self.assertIn("30", result)

    def test_multiple_rows(self):
        """多行数据"""
        rows = [("Alice", 30), ("Bob", 25)]
        result = build_table_body_html(rows, [0, 1])
        self.assertEqual(result.count("<tr>"), 2)

    def test_display_indices_subset(self):
        """display_indices 控制显示的列"""
        rows = [("Alice", 30, "NY")]
        result = build_table_body_html(rows, [0, 2])
        self.assertIn("Alice", result)
        self.assertIn("NY", result)
        self.assertNotIn("30", result)

    def test_none_values_in_row(self):
        """None 值在行中显示为空"""
        rows = [("Alice", None)]
        result = build_table_body_html(rows, [0, 1])
        self.assertIn("Alice", result)
        self.assertIn("<td></td>", result)


# ===================================================================
# 控制栏测试
# ===================================================================


class TestBuildControlsBarHtml(unittest.TestCase):
    """build_controls_bar_html 函数测试"""

    def test_contains_controls_div(self):
        """包含 controls div"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          '<span class="cache-badge">test</span>',
                                          100, 5)
        self.assertIn('<div class="controls">', result)

    def test_contains_report_form(self):
        """包含报表控制表单"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn('<form method="get" action="/report"', result)
        self.assertIn('name="id"', result)

    def test_contains_export_form(self):
        """包含导出表单"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn('<form method="get" action="/export"', result)
        self.assertIn("CSV", result)
        self.assertIn("JSON", result)

    def test_page_size_selector(self):
        """包含每页行数选择器"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("每页行数:", result)
        self.assertIn('name="page_size"', result)

    def test_export_format_options(self):
        """导出格式选项"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("CSV", result)
        self.assertIn("JSON", result)
        self.assertIn("GBK（Excel 中文版推荐）", result)
        self.assertIn("UTF-8（通用 / 程序处理）", result)

    def test_cache_badge_in_controls(self):
        """缓存标签出现在控制栏"""
        badge = '<span class="cache-badge">测试缓存</span>'
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          badge, 100, 5)
        self.assertIn("测试缓存", result)

    def test_stat_line(self):
        """统计行显示"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 500, 25)
        self.assertIn("共 500 行，25 页", result)

    def test_sort_hidden_inputs(self):
        """排序参数生成隐藏 input"""
        result = build_controls_bar_html(1, 20, [("name", "asc")], [], "",
                                          ["id", "name"], 0, "", 100, 5)
        self.assertIn('name="sort"', result)
        self.assertIn('name="dir"', result)

    def test_filter_hidden_inputs(self):
        """筛选参数生成隐藏 input"""
        result = build_controls_bar_html(1, 20, [], [("age", "gt", "18")], "",
                                          ["id", "name"], 0, "", 100, 5)
        self.assertIn('name="f_age"', result)

    def test_result_param_hidden(self):
        """多结果集时生成 result 隐藏 input"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5, result_param="result=0")
        self.assertIn('name="result"', result)
        self.assertIn('value="0"', result)

    def test_rebuild_cache_form(self):
        """重建缓存为 POST 表单（PH-08：破坏性操作 POST 化）"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("重建缓存", result)
        self.assertIn('method="post" action="/report"', result)
        self.assertIn('name="action" value="refresh_cache"', result)
        self.assertNotIn("refresh=1", result)

    def test_field_settings_button(self):
        """包含字段设置按钮"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("字段设置", result)
        self.assertIn("fieldSettingsPanel", result)

    def test_sort_settings_button(self):
        """包含排序设置按钮"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("排序设置", result)
        self.assertIn("sortSettingsPanel", result)

    def test_export_more_options_collapsed(self):
        """PH-12 低频导出选项折叠到「更多选项」details 内"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("<details", result)
        self.assertIn("更多选项", result)
        # 低频选项位于 details 折叠区内
        details_start = result.find("<details")
        details_end = result.find("</details>")
        self.assertGreater(details_start, 0)
        self.assertGreater(details_end, details_start)
        folded = result[details_start:details_end]
        self.assertIn('name="charset"', folded)
        self.assertIn('name="smart_quotes"', folded)
        self.assertIn('name="zip"', folded)
        self.assertIn('name="use_custom_cols"', folded)
        # 名称统一：「智能去引号」，无旧「值无引号」残留
        self.assertIn("智能去引号", result)
        self.assertNotIn("值无引号", result)
        # 格式与导出按钮保留在折叠区外
        format_pos = result.find('name="format"')
        self.assertLess(format_pos, details_start)

    def test_export_more_keep_submit_params(self):
        """PH-12 折叠区字段仍为表单提交字段（参数不丢）"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        details_start = result.find("<details")
        details_end = result.find("</details>")
        folded = result[details_start:details_end]
        self.assertIn("charset", folded)
        self.assertIn("gbk", folded)
        self.assertIn("utf8", folded)
        self.assertIn('value="1"', folded)

    def test_export_smart_quote_panel(self):
        """智能去引号面板：3 项勾选 + hidden 位图 + CSV 禁用 JS"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        # 3 个勾选项（1=十进制 / 2=科学计数法 / 4=千分位）
        self.assertIn('class="smart-quote-cb" value="1"', result)
        self.assertIn('class="smart-quote-cb" value="2"', result)
        self.assertIn('class="smart-quote-cb" value="4"', result)
        # 位图随勾选状态即时写入隐藏 input（导出 URL 参数 smart_quotes）
        self.assertIn('name="smart_quotes" id="export-smart-quotes-input" value="0"',
                      result)
        self.assertIn("updateExportSmartFlags", result)
        # 说明文案：原生 int/float 恒裸 / Decimal 勾选数字特征裸出 / 千分位去逗号
        self.assertIn("原生 int/float 恒裸输出", result)
        self.assertIn("Decimal 数值列勾选十进制/科学时输出数字", result)
        self.assertIn("千分位输出去逗号", result)
        self.assertIn("输出永远合法 JSON（RFC 8259）", result)
        # CSV 格式时面板禁用：格式 select 联动 + 仅 JSON 提示
        self.assertIn('id="export-format-select" onchange="updateExportSmartState()"',
                      result)
        self.assertIn("export-smart-csv-hint", result)
        self.assertIn("仅 JSON 格式支持", result)
        self.assertIn("cb.disabled = isCsv", result)


# ===================================================================
# 字段设置面板测试
# ===================================================================


class TestBuildFieldSettingsPanelHtml(unittest.TestCase):
    """build_field_settings_panel_html 函数测试"""

    def test_contains_panel_div(self):
        """包含面板容器"""
        result = build_field_settings_panel_html(["id", "name"], ["id", "name"])
        self.assertIn('id="fieldSettingsPanel"', result)
        self.assertIn("字段设置", result)

    def test_visible_fields_checked(self):
        """可见字段被选中"""
        result = build_field_settings_panel_html(["id", "name", "age"], ["id", "name"])
        self.assertIn('value="id" checked', result)
        self.assertIn('value="name" checked', result)

    def test_hidden_fields_not_checked(self):
        """隐藏字段未被选中"""
        result = build_field_settings_panel_html(["id", "name", "age"], ["id", "name"])
        self.assertIn('value="age"', result)
        # age 不应被 checked
        self.assertNotIn('value="age" checked', result)

    def test_move_buttons(self):
        """包含上下移动按钮"""
        result = build_field_settings_panel_html(["id", "name", "age"], ["id", "name", "age"])
        self.assertIn("class=\"field-up\"", result)
        self.assertIn("class=\"field-down\"", result)

    def test_apply_and_select_buttons(self):
        """包含全选、全不选、应用按钮"""
        result = build_field_settings_panel_html(["id"], ["id"])
        self.assertIn("全选", result)
        self.assertIn("全不选", result)
        self.assertIn("应用", result)

    def test_drag_handle(self):
        """包含拖拽手柄"""
        result = build_field_settings_panel_html(["id"], ["id"])
        self.assertIn("drag-handle", result)
        self.assertIn("⠿", result)

    def test_field_list_responsive_grid(self):
        """fieldList 应为响应式多列网格（ui-form-wide-layout 矩阵 C）"""
        result = build_field_settings_panel_html(["id", "name"], ["id", "name"])
        self.assertIn('id="fieldList"', result)
        self.assertIn("grid-template-columns:repeat(auto-fill,minmax(300px,1fr))", result)
        self.assertNotIn("flex-direction:column", result)


# ===================================================================
# 排序设置面板测试
# ===================================================================


class TestBuildSortSettingsPanelHtml(unittest.TestCase):
    """build_sort_settings_panel_html 函数测试"""

    def test_contains_panel_div(self):
        """包含面板容器"""
        result = build_sort_settings_panel_html([], ["id", "name"])
        self.assertIn('id="sortSettingsPanel"', result)
        self.assertIn("排序设置", result)

    def test_empty_sorts_shows_placeholder(self):
        """无排序时显示暂无排序"""
        result = build_sort_settings_panel_html([], ["id", "name"])
        self.assertIn("暂无排序", result)

    def test_sort_items_with_priority(self):
        """排序项显示优先级编号"""
        result = build_sort_settings_panel_html([("name", "asc"), ("age", "desc")], ["id", "name", "age"])
        self.assertIn("name", result)
        self.assertIn("age", result)
        self.assertIn("1", result)
        self.assertIn("2", result)

    def test_move_buttons(self):
        """排序项包含上下移动和删除按钮"""
        result = build_sort_settings_panel_html([("name", "asc")], ["id", "name"])
        self.assertIn("class=\"sort-up\"", result)
        self.assertIn("class=\"sort-down\"", result)
        # 删除按钮
        self.assertIn('onclick="removeSortItem(this)"', result)

    def test_add_sort_section(self):
        """包含添加排序界面"""
        result = build_sort_settings_panel_html([], ["id", "name"])
        self.assertIn("添加排序字段", result)
        self.assertIn("升序", result)
        self.assertIn("降序", result)
        self.assertIn('id="newSortCol"', result)
        self.assertIn('id="newSortDir"', result)

    def test_apply_button(self):
        """包含应用按钮"""
        result = build_sort_settings_panel_html([], ["id"])
        self.assertIn("应用", result)
        self.assertIn('onclick="applySortSettings()"', result)


# ===================================================================
# 筛选表单测试
# ===================================================================


class TestBuildFilterFormHtml(unittest.TestCase):
    """build_filter_form_html 函数测试"""

    def test_contains_form_tag(self):
        """包含 form 标签"""
        result = build_filter_form_html("ff", '<input type="hidden" name="test" value="1">')
        self.assertIn('<form id="ff"', result)
        self.assertIn("</form>", result)

    def test_form_is_hidden(self):
        """表单隐藏"""
        result = build_filter_form_html("ff", "")
        self.assertIn('style="display:none"', result)

    def test_contains_hidden_inputs(self):
        """包含传入的隐藏字段"""
        hidden = '<input type="hidden" name="f_name" value="test">'
        result = build_filter_form_html("ff", hidden)
        self.assertIn('name="f_name"', result)

    def test_action_is_report(self):
        """表单提交到 /report"""
        result = build_filter_form_html("ff", "")
        self.assertIn('action="/report"', result)


# ===================================================================
# 筛选操作测试
# ===================================================================


class TestBuildFilterActionHtml(unittest.TestCase):
    """build_filter_action_html 函数测试"""

    def test_returns_two_strings(self):
        """返回两个字符串 (filter_action_html, clear_html)"""
        action, clear = build_filter_action_html(1, 20, [], "", "", [])
        self.assertIsInstance(action, str)
        self.assertIsInstance(clear, str)

    def test_contains_filter_and_clear_buttons(self):
        """包含筛选和清除筛选按钮"""
        action, clear = build_filter_action_html(1, 20, [], "", "", [])
        self.assertIn("筛选", action)
        self.assertIn("清除筛选", action)

    def test_contains_filter_help_entry(self):
        """筛选操作区含 ? 帮助入口（默认收起弹窗，单一来源渲染）"""
        action, _ = build_filter_action_html(1, 20, [], "", "", [])
        self.assertIn("filter-help-btn", action)
        self.assertIn("filter-help-popup", action)
        self.assertIn("display:none", action)
        self.assertIn("toggleFilterHelp", action)

    def test_clear_html_empty_when_no_filters(self):
        """无筛选时 clear_html 为空"""
        _, clear = build_filter_action_html(1, 20, [], "", "", [])
        self.assertEqual(clear, "")

    def test_clear_html_present_when_filters(self):
        """有筛选时 clear_html 显示筛选摘要"""
        _, clear = build_filter_action_html(1, 20, [], "", "",
                                             [("name", "contains", "foo")])
        self.assertIn("筛选:", clear)
        self.assertIn("foo", clear)
        self.assertIn("全部清除", clear)

    def test_multiple_filters_in_summary(self):
        """多个筛选在摘要中显示"""
        _, clear = build_filter_action_html(1, 20, [], "", "",
                                             [("name", "eq", "foo"), ("age", "gt", "18")])
        self.assertIn("foo", clear)
        self.assertIn("18", clear)

    def test_sort_params_in_clear_href(self):
        """清除链接包含排序参数"""
        action, _ = build_filter_action_html(1, 20, [("name", "asc")], "", "", [])
        self.assertIn("sort=name", action)
        self.assertIn("dir=asc", action)


# ===================================================================
# 报表切换器测试
# ===================================================================


class TestBuildReportSwitcherHtml(unittest.TestCase):
    """build_report_switcher_html 函数测试"""

    def test_contains_card_and_form(self):
        """包含卡片和表单"""
        result = build_report_switcher_html([], [], [], None)
        self.assertIn("card", result)
        self.assertIn("切换报表:", result)
        self.assertIn('<form method="get" action="/report"', result)

    def test_select_with_options(self):
        """包含下拉选择框"""
        result = build_report_switcher_html([], [], [], None)
        self.assertIn('<select name="id"', result)
        self.assertIn("-- 选择报表 --", result)

    def test_categorized_reports_in_optgroup(self):
        """分类中的报表显示在 optgroup 中"""
        reports_data = [{"id": 1, "name": "日报", "category_id": 1}]
        all_cats = [{"id": 1, "name": "销售", "parent_id": None}]
        cat_tree = [{"id": 1, "name": "销售", "children": []}]
        result = build_report_switcher_html(reports_data, all_cats, cat_tree, None)
        self.assertIn("日报", result)
        self.assertIn("销售", result)

    def test_uncategorized_reports(self):
        """未分类报表显示在 (未分类) 中"""
        reports_data = [{"id": 1, "name": "测试报表", "category_id": None}]
        result = build_report_switcher_html(reports_data, [], [], None)
        self.assertIn("测试报表", result)
        self.assertIn("未分类", result)

    def test_current_report_selected(self):
        """当前报表标记为 selected"""
        reports_data = [{"id": 42, "name": "日报", "category_id": None}]
        result = build_report_switcher_html(reports_data, [], [], current_id=42)
        self.assertIn('value="42" selected', result)

    def test_empty_category_shows_disabled(self):
        """空分类显示无报表提示"""
        reports_data = []
        all_cats = [{"id": 1, "name": "空分类", "parent_id": None}]
        cat_tree = [{"id": 1, "name": "空分类", "children": []}]
        result = build_report_switcher_html(reports_data, all_cats, cat_tree, None)
        self.assertIn("无报表", result)
        self.assertIn("空分类", result)


class TestReportSwitcherWidthCSS(unittest.TestCase):
    """切换报表下拉框宽度契约（report 页 _CSS）

    断言真源：本会话决策（2026-08-18）——.report-select 不得有 max-width 钉死，
    select 填满卡片宽度（跟随容器 1200~2400px 宽屏分级）。
    """

    def test_select_fills_card_width(self):
        """select 保持 width:100% 填满卡片"""
        self.assertIn("  .report-select select {\n    width: 100%", report_mod._CSS)

    def test_no_500px_pin_on_report_select(self):
        """500px 钉死不得残留"""
        self.assertNotIn("max-width: 500px", report_mod._CSS)


# ===================================================================
# 按钮辅助函数测试
# ===================================================================


class TestLinkBtn(unittest.TestCase):
    """_link_btn 函数测试"""

    def test_creates_anchor_tag(self):
        """生成正确的 a 标签"""
        result = _link_btn("/test", "Click Me")
        self.assertIn('<a href="/test"', result)
        self.assertIn("Click Me", result)

    def test_default_class(self):
        """默认使用 btn btn-outline btn-sm"""
        result = _link_btn("/test", "Click Me")
        self.assertIn('class="btn btn-outline btn-sm"', result)

    def test_custom_class(self):
        """支持自定义 CSS 类"""
        result = _link_btn("/test", "Click Me", "btn btn-primary")
        self.assertIn('class="btn btn-primary"', result)

    def test_url_html_escaped(self):
        """URL 中的特殊字符被转义"""
        result = _link_btn('/test?name="foo"', "Link")
        self.assertIn("&quot;", result)


class TestBuildMoveButtonsHtml(unittest.TestCase):
    """build_move_buttons_html 函数测试"""

    def test_single_item_returns_empty(self):
        """只有一项时返回空字符串"""
        result = build_move_buttons_html(1, "pools", 0, 1)
        self.assertEqual(result, "")

    def test_first_item_has_down_only(self):
        """第一项只有下移按钮"""
        result = build_move_buttons_html(1, "pools", 0, 3)
        self.assertNotIn("move-up", result)
        self.assertIn("move-down", result)

    def test_last_item_has_up_only(self):
        """最后一项只有上移按钮"""
        result = build_move_buttons_html(1, "pools", 2, 3)
        self.assertIn("move-up", result)
        self.assertNotIn("move-down", result)

    def test_middle_item_has_both(self):
        """中间项同时有上下移按钮"""
        result = build_move_buttons_html(1, "pools", 1, 3)
        self.assertIn("move-up", result)
        self.assertIn("move-down", result)

    def test_contains_item_id_and_section(self):
        """按钮包含 id 和 section"""
        result = build_move_buttons_html(42, "reports", 0, 2)
        self.assertIn("/config/reports/42/move-down", result)

    def test_uses_post_method(self):
        """按钮表单使用 POST 方法"""
        result = build_move_buttons_html(1, "pools", 0, 2)
        self.assertIn('method="post"', result)


# ===================================================================
# 表单渲染器测试
# ===================================================================


class TestBuildPoolFormHtml(unittest.TestCase):
    """build_pool_form_html 函数测试"""

    def test_new_pool_form(self):
        """新增连接池表单"""
        result = build_pool_form_html()
        self.assertIn("新增连接池", result)
        self.assertIn('action="/config/pools/add"', result)
        self.assertIn('name="name"', result)
        self.assertIn('name="host"', result)
        self.assertIn('name="port"', result)
        self.assertIn('name="user"', result)
        self.assertIn('name="password"', result)
        self.assertIn('name="database"', result)

    def test_edit_pool_form(self):
        """编辑连接池表单显示已有值"""
        pool = {"id": 1, "name": "主库", "host": "10.0.0.1", "port": 3306,
                "user": "root", "password": "secret", "database": "mydb"}
        result = build_pool_form_html(pool)
        self.assertIn("编辑连接池", result)
        self.assertIn('action="/config/pools/1/edit"', result)
        self.assertIn('value="主库"', result)
        self.assertIn('value="10.0.0.1"', result)
        self.assertIn('value="3306"', result)
        self.assertIn('value="root"', result)

    def test_copy_pool_form(self):
        """复制连接池表单自动添加副本后缀"""
        pool = {"id": 1, "name": "主库", "host": "10.0.0.1", "port": 3306,
                "user": "root", "password": "secret", "database": "mydb"}
        result = build_pool_form_html(pool, copy_mode=True)
        self.assertIn("复制连接池", result)
        self.assertIn('action="/config/pools/1/copy"', result)
        self.assertIn("主库 (副本)", result)

    def test_new_pool_default_port(self):
        """新增连接池默认端口为 3306"""
        result = build_pool_form_html()
        self.assertIn('value="3306"', result)

    def test_save_and_cancel_buttons(self):
        """包含保存和取消按钮"""
        result = build_pool_form_html()
        self.assertIn("保存", result)
        self.assertIn("取消", result)
        self.assertIn('href="/config"', result)


class TestBuildUserFormHtml(unittest.TestCase):
    """build_user_form_html 函数测试"""

    def test_new_user_form(self):
        """新增用户表单"""
        result = build_user_form_html()
        self.assertIn("新增用户", result)
        self.assertIn('action="/config/users/add"', result)
        self.assertIn('name="username"', result)
        self.assertIn('name="password"', result)
        self.assertIn("required", result)

    def test_edit_user_form(self):
        """编辑用户表单显示用户名"""
        result = build_user_form_html({"id": 1, "username": "admin"})
        self.assertIn("编辑用户", result)
        self.assertIn('action="/config/users/1/edit"', result)
        self.assertIn('value="admin"', result)

    def test_edit_user_password_not_required(self):
        """编辑用户时密码 input 无 required 属性"""
        result = build_user_form_html({"id": 1, "username": "admin"})
        # 密码 input 应该没有 required（用户名 input 仍有 required）
        self.assertIn('name="password" value="" >', result)

    def test_edit_user_password_hint(self):
        """编辑用户时显示密码留空提示"""
        result = build_user_form_html({"id": 1, "username": "admin"})
        self.assertIn("留空则不修改密码", result)

    def test_save_and_cancel_buttons(self):
        """包含保存和取消按钮"""
        result = build_user_form_html()
        self.assertIn("保存", result)
        self.assertIn("取消", result)
        self.assertIn('href="/config"', result)


# ===================================================================
# 配置段渲染器测试
# ===================================================================


class TestBuildPoolSectionHtml(unittest.TestCase):
    """build_pool_section_html 函数测试"""

    def test_empty_pools(self):
        """空列表显示暂无连接池"""
        result = build_pool_section_html([])
        self.assertIn("暂无连接池配置", result)

    def test_pool_list(self):
        """连接池列表渲染"""
        pools = [{"id": 1, "name": "主库", "host": "10.0.0.1", "port": 3306,
                  "user": "root", "database": "mydb"}]
        result = build_pool_section_html(pools)
        self.assertIn("主库", result)
        self.assertIn("10.0.0.1", result)
        self.assertIn("root", result)
        self.assertIn("mydb", result)
        self.assertIn("连接池配置", result)

    def test_contains_action_buttons(self):
        """包含编辑、复制、删除按钮"""
        pools = [{"id": 1, "name": "主库", "host": "localhost", "port": 3306,
                  "user": "root", "database": "db"}]
        result = build_pool_section_html(pools)
        self.assertIn("编辑", result)
        self.assertIn("复制", result)
        self.assertIn("删除", result)

    def test_contains_add_button(self):
        """包含新增连接池按钮"""
        result = build_pool_section_html([])
        self.assertIn("新增连接池", result)
        self.assertIn("/config/pools/add", result)

    def test_table_structure(self):
        """包含表结构"""
        pools = [{"id": 1, "name": "P1", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        result = build_pool_section_html(pools)
        self.assertIn("<table>", result)
        self.assertIn("<thead>", result)
        self.assertIn("<tbody>", result)
        self.assertIn("名称", result)
        self.assertIn("地址", result)
        self.assertIn("用户", result)
        self.assertIn("数据库", result)
        self.assertIn("操作", result)


class TestBuildUserSectionHtml(unittest.TestCase):
    """build_user_section_html 函数测试"""

    def test_empty_users(self):
        """空列表显示暂无用户"""
        result = build_user_section_html([])
        self.assertIn("暂无用户", result)

    def test_user_list(self):
        """用户列表渲染"""
        users = [{"id": 1, "username": "admin"}]
        result = build_user_section_html(users)
        self.assertIn("admin", result)
        self.assertIn("用户配置", result)

    def test_contains_action_buttons(self):
        """包含编辑和删除按钮"""
        users = [{"id": 1, "username": "admin"}]
        result = build_user_section_html(users)
        self.assertIn("编辑", result)
        self.assertIn("删除", result)

    def test_contains_add_button(self):
        """包含新增用户按钮"""
        result = build_user_section_html([])
        self.assertIn("新增用户", result)
        self.assertIn("/config/users/add", result)

    def test_table_structure(self):
        """包含表结构"""
        users = [{"id": 1, "username": "admin"}]
        result = build_user_section_html(users)
        self.assertIn("<table>", result)
        self.assertIn("用户名", result)
        self.assertIn("操作", result)


class TestBuildCategorySectionHtml(unittest.TestCase):
    """build_category_section_html 函数测试"""

    def setUp(self):
        """准备测试数据"""
        self.pools = [
            {"id": 1, "name": "主库"},
            {"id": 2, "name": "从库"},
        ]
        self.all_cats = [
            {"id": 1, "name": "销售", "parent_id": None},
            {"id": 2, "name": "技术", "parent_id": None},
        ]
        self.cat_tree = [
            {"id": 1, "name": "销售", "children": []},
            {"id": 2, "name": "技术", "children": []},
        ]
        self.cat_reports = [{"id": 1, "reports": [{"id": 1, "name": "日报", "sql_query": "SELECT * FROM daily", "default_page_size": 20, "pool_id": 1, "memo": "每日统计", "prefer_cache": 1, "cache_ttl_hours": 0}]}]
        self.unclassified_reports = [{"id": 3, "name": "测试报表", "sql_query": "SELECT 1", "default_page_size": 10, "pool_id": None, "memo": "", "prefer_cache": 1, "cache_ttl_hours": 0}]
        self.all_reports = [{"id": 1, "name": "日报"}, {"id": 3, "name": "测试报表"}]

    def test_category_tree_visual_guides(self):
        """分类管理块渲染树形引导线 + 层级图标"""
        all_cats = [
            {"id": 1, "name": "根分类", "parent_id": None},
            {"id": 2, "name": "子分类", "parent_id": 1},
        ]
        cat_tree = [
            {"id": 1, "name": "根分类", "children": [
                {"id": 2, "name": "子分类", "children": []},
            ]},
        ]
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              all_cats, self.all_reports,
                                              self.pools, cat_tree)
        self.assertIn('class="tree-guide"', result)
        self.assertIn("└─", result)
        self.assertIn("📁", result)
        self.assertIn("📄", result)

    def test_report_sections_nested_visual(self):
        """报表区块按层级缩进 + 左侧竖条嵌套（替代全角空格标题缩进）"""
        all_cats = [
            {"id": 1, "name": "根分类", "parent_id": None},
            {"id": 2, "name": "子分类", "parent_id": 1},
        ]
        cat_tree = [
            {"id": 1, "name": "根分类", "children": [
                {"id": 2, "name": "子分类", "children": []},
            ]},
        ]
        cat_reports = [
            {"id": 1, "reports": [{"id": 1, "name": "日报", "sql_query": "SELECT * FROM daily",
                                    "default_page_size": 20, "pool_id": 1, "memo": "",
                                    "prefer_cache": 1, "cache_ttl_hours": 0}]},
            {"id": 2, "reports": [{"id": 2, "name": "周报", "sql_query": "SELECT * FROM weekly",
                                    "default_page_size": 10, "pool_id": None, "memo": "",
                                    "prefer_cache": 1, "cache_ttl_hours": 0}]},
        ]
        result = build_category_section_html(cat_reports, [],
                                              all_cats, self.all_reports,
                                              self.pools, cat_tree)
        self.assertIn("margin-left:24px;border-left:3px solid #c7d2fe", result)
        self.assertIn("📁 根分类", result)
        self.assertIn("📊 子分类", result)

    def test_contains_category_section(self):
        """包含报表分类段"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("报表分类", result)
        self.assertIn("销售", result)
        self.assertIn("技术", result)

    def test_contains_unclassified_section(self):
        """包含未分类报表段"""
        result = build_category_section_html([], self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("未分类报表", result)
        self.assertIn("测试报表", result)

    def test_contains_batch_bar(self):
        """包含批量操作栏"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("batch-bar", result)
        self.assertIn("批量修改连接池", result)
        self.assertIn("批量设置分类", result)
        self.assertIn("批量更新缓存配置", result)
        self.assertIn("批量删除报表", result)
        self.assertIn("batchDeleteReports()", result)
        self.assertIn("/config/reports/batch-delete", result)

    def test_contains_add_buttons(self):
        """包含新增分类和新增报表按钮"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("新增分类", result)
        self.assertIn("新增报表", result)

    def test_category_section_has_fold_toggle(self):
        """分类树区块含整体折叠按钮（标题栏按钮保留）"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn('id="cat-tree-toggle"', result)
        self.assertIn('onclick="toggleCatTree(this)"', result)
        self.assertIn('id="cat-tree-content"', result)
        self.assertIn("新增分类", result)
        self.assertIn("新增报表", result)

    def test_category_section_fold_toggle_beside_tree(self):
        """折叠按钮与树列表容器为兄弟结构，且树列表包裹在可隐藏容器内"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        toggle_pos = result.index('id="cat-tree-toggle"')
        content_pos = result.index('id="cat-tree-content"')
        self.assertGreater(content_pos, toggle_pos)
        self.assertIn('<div id="cat-tree-content">', result)

    def test_hidden_utility_class_defined_in_common_css(self):
        """折叠依赖的 .hidden 工具类必须在公共 CSS 中定义为 display:none

        回归：cat-tree-toggle 点击调 classList.toggle('hidden')，若 .hidden 无
        display:none 规则则点击无视觉变化（用户反馈"折叠按钮点击无效"）。
        """
        self.assertIn('.hidden { display: none !important; }', _COMMON_CSS)

    def test_page_style_emits_hidden_rule(self):
        """页面公共资产应包含 .hidden 规则（折叠端到端生效；批次6#28 后经外链引用）"""
        header = render_page_header("t")
        # 外链模式：<link> 引用 _COMMON_CSS；内联回退模式：<style> 直含规则。
        linked = '<link rel="stylesheet"' in header and (
            ".hidden { display: none !important; }" in _COMMON_CSS)
        inline = ".hidden { display: none !important; }" in header
        self.assertTrue(linked or inline)

    def test_pool_badge(self):
        """报表显示连接池名称"""
        result = build_category_section_html(self.cat_reports, [],
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("主库", result)

    def test_missing_pool_shows_warning(self):
        """连接池已删除时显示警告"""
        cat_reports = [{"id": 1, "reports": [{"id": 1, "name": "R1", "sql_query": "SELECT 1",
                                                "default_page_size": 20, "pool_id": 999,
                                                "memo": "", "prefer_cache": 1, "cache_ttl_hours": 0}]}]
        result = build_category_section_html(cat_reports, [],
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("连接池已删除", result)

    def test_memo_display(self):
        """备注显示预览"""
        result = build_category_section_html(self.cat_reports, [],
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("每日统计", result)

    def test_cache_ttl_display(self):
        """缓存 TTL 为零时显示横线"""
        result = build_category_section_html(self.cat_reports, [],
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        # cache_ttl_hours=0 时显示 em dash，非零时显示如 24h
        self.assertIn("—", result)

    def test_pool_options_in_batch(self):
        """批量操作包含连接池选项"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("主库", result)
        self.assertIn("从库", result)


# ===================================================================
# 分类选项测试
# ===================================================================


class TestBuildCategoryOptsHtml(unittest.TestCase):
    """build_category_opts_html 函数测试"""

    def test_flat_list(self):
        """扁平分类列表"""
        nodes = [{"id": 1, "name": "销售", "children": []},
                 {"id": 2, "name": "技术", "children": []}]
        result = build_category_opts_html(nodes, 0, "")
        self.assertIn("销售", result)
        self.assertIn("技术", result)
        self.assertIn('<option value="1"', result)
        self.assertIn('<option value="2"', result)

    def test_tree_with_children(self):
        """树形分类缩进"""
        nodes = [{"id": 1, "name": "根分类", "children": [
            {"id": 2, "name": "子分类", "children": []}
        ]}]
        result = build_category_opts_html(nodes, 0, "")
        self.assertIn("根分类", result)
        self.assertIn("子分类", result)

    def test_selected_category(self):
        """当前分类标记为 selected"""
        nodes = [{"id": 5, "name": "我的分类", "children": []}]
        result = build_category_opts_html(nodes, 0, "5")
        self.assertIn('value="5" selected', result)

    def test_empty_nodes(self):
        """空节点列表返回空字符串"""
        result = build_category_opts_html([], 0, "")
        self.assertEqual(result, "")


# ===================================================================
# 当前规则区测试
# ===================================================================


class TestBuildCurrentRulesSectionHtml(unittest.TestCase):
    """build_current_rules_section_html 函数测试"""

    def test_has_textarea(self):
        """替换为 textarea 元素"""
        result = build_current_rules_section_html([], [], ["a"], ["a"])
        self.assertIn('<textarea id="current-rules-json"', result)
        self.assertNotIn("<pre id=", result)

    def test_has_apply_button(self):
        """包含应用按钮"""
        result = build_current_rules_section_html([], [], ["a"], ["a"])
        self.assertIn("applyRulesJson()", result)
        self.assertIn("应用", result)

    def test_has_copy_button(self):
        """仍包含复制按钮"""
        result = build_current_rules_section_html([], [], ["a"], ["a"])
        self.assertIn("copyRulesJson()", result)
        self.assertIn("复制", result)

    def test_rules_json_in_textarea(self):
        """JSON 规则内容在 textarea 中（HTML 转义）"""
        filters = [("status", "eq", "active")]
        sorts = [("created_at", "desc")]
        result = build_current_rules_section_html(filters, sorts,
                                                   ["id", "name"],
                                                   ["id", "name", "age"])
        # JSON 被 HTML 转义，双引号变为 &quot;
        self.assertIn('&quot;status&quot;', result)
        self.assertIn('&quot;created_at&quot;', result)
        self.assertIn('&quot;id,name&quot;', result)

    def test_empty_rules_default(self):
        """无规则时显示默认提示"""
        result = build_current_rules_section_html([], [], ["a"], ["a"])
        self.assertIn("无自定义规则", result)


# ===================================================================
# API 端点表单测试
# ===================================================================


class TestBuildApiEndpointFormHtml(unittest.TestCase):
    """build_api_endpoint_form_html 函数测试"""

    def test_has_rule_json_field(self):
        """包含 rule_json textarea"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('name="rule_json"', result)
        self.assertIn("规则 JSON", result)

    def test_no_columns_field(self):
        """不再有独立的 columns 字段"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertNotIn('name="columns"', result)

    def test_no_filters_field(self):
        """不再有独立的 filters 字段"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertNotIn('name="filters"', result)

    def test_no_sorts_field(self):
        """不再有独立的 sorts 字段"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertNotIn('name="sorts"', result)

    def test_edit_populates_rule_json(self):
        """编辑时三字段合并为 JSON（HTML 转义）"""
        endpoint = {
            "id": 1, "name": "测试端点", "url_path": "/api/test",
            "output_format": "json", "columns": "id,name",
            "filters": '[{"col":"status","op":"eq","val":"active"}]',
            "sorts": '[{"col":"created_at","dir":"desc"}]',
            "row_limit": 0, "api_key": "", "allowed_origins": "",
            "enabled": 1,
        }
        result = build_api_endpoint_form_html(1, "测试报表", endpoint)
        # JSON 被 HTML 转义
        self.assertIn('&quot;id,name&quot;', result)
        self.assertIn('&quot;status&quot;', result)
        self.assertIn('&quot;created_at&quot;', result)

    def test_has_description_textarea(self):
        """表单包含接口说明多行文本框"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('name="description"', result)
        self.assertIn("接口说明", result)
        self.assertIn("<textarea", result)

    def test_edit_echoes_description(self):
        """编辑时回显已有接口说明（多行保留、HTML 转义）"""
        endpoint = {
            "id": 1, "name": "测试端点", "url_path": "/api/test",
            "output_format": "json", "row_limit": 0,
            "api_key": "", "allowed_origins": "", "enabled": 1,
            "description": "第一行说明\n第二行说明 <b>转义</b>",
        }
        result = build_api_endpoint_form_html(1, "测试报表", endpoint)
        self.assertIn("第一行说明", result)
        self.assertIn("第二行说明", result)
        self.assertIn("&lt;b&gt;", result)

    def test_edit_empty_fields(self):
        """编辑时三字段均为空"""
        endpoint = {
            "id": 1, "name": "测试端点", "url_path": "/api/test",
            "output_format": "json", "columns": "",
            "filters": "", "sorts": "",
            "row_limit": 0, "api_key": "", "allowed_origins": "",
            "enabled": 1,
        }
        result = build_api_endpoint_form_html(1, "测试报表", endpoint)
        self.assertIn('name="rule_json"', result)

    def test_has_save_close_button(self):
        """包含保存并关闭按钮"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('name="action" value="save_close"', result)
        self.assertIn("保存并关闭", result)

    def test_has_save_button(self):
        """包含保存按钮（不返回）"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('name="action" value="save"', result)
        self.assertIn("保存", result)

    def test_close_link_goes_to_report_edit(self):
        """关闭按钮跳转到报表编辑页"""
        result = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('href="/config/reports/1/edit"', result)
        self.assertIn("关闭", result)

    def test_flash_success_uses_green_css(self):
        """成功闪回消息使用绿色样式"""
        result = build_api_endpoint_form_html(1, "测试报表", flash="保存成功")
        self.assertIn('class="flash flash-success"', result)

    def test_flash_error_uses_red_css(self):
        """错误闪回消息使用红色样式"""
        result = build_api_endpoint_form_html(1, "测试报表", flash="错误: 出错了")
        self.assertIn('class="flash flash-error"', result)


class TestBuildApiEndpointsListHtml(unittest.TestCase):
    """build_api_endpoints_list_html 函数测试（列表快捷开关）"""

    def _ep(self, eid, enabled=1, report_id=1, description="",
            allow_fetch_all=1, static_cache=1, api_key=""):
        return {"id": eid, "name": f"接口{eid}", "url_path": f"/api/ep{eid}",
                "output_format": "json", "enabled": enabled,
                "report_id": report_id, "result_mode": "single",
                "result_index": 0, "allow_fetch_all": allow_fetch_all,
                "static_cache": static_cache, "api_key": api_key,
                "description": description}

    def test_row_has_toggle_button_enabled(self):
        """启用端点行含禁用按钮（POST toggle）"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn('name="action" value="toggle"', html)
        self.assertIn('name="endpoint_id" value="1"', html)
        self.assertIn("禁用", html)

    def test_row_toggle_disabled_shows_enable(self):
        """禁用端点行显示启用按钮"""
        html = build_api_endpoints_list_html([self._ep(1, enabled=0)], report_id=1)
        self.assertIn("启用", html)

    def test_toggle_return_to_report_edit(self):
        """报表编辑页列表：toggle 后回跳到该报表编辑页"""
        html = build_api_endpoints_list_html([self._ep(1, report_id=3)], report_id=3)
        self.assertIn('name="return_to" value="/config/reports/3/edit"', html)

    def test_toggle_return_to_admin_page(self):
        """独立管理页列表：toggle 后回跳到独立管理页"""
        html = build_api_endpoints_list_html([self._ep(1)], show_report_name=True)
        self.assertIn('name="return_to" value="/config/api-endpoints"', html)

    def test_disable_has_confirm(self):
        """禁用操作带确认提示"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn("onsubmit=", html)
        self.assertIn("confirm(", html)

    def test_edit_delete_still_present(self):
        """原有编辑/删除操作保留"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn("编辑", html)
        self.assertIn("删除", html)

    def test_list_has_description_column(self):
        """列表包含说明列表头"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn("<th>说明</th>", html)

    def test_list_description_truncated_with_title(self):
        """长说明单元格截断摘要显示，title 保留全文"""
        long_desc = ("这是一段很长的接口说明文本，用于描述接口的用途和调用注意事项，"
                     "内容足够长以验证摘要截断展示与悬停全文效果")
        html = build_api_endpoints_list_html([self._ep(1, description=long_desc)],
                                             report_id=1)
        self.assertIn(long_desc, html)  # title 全文
        self.assertIn("…", html)  # 截断标记

    def test_list_description_empty_placeholder(self):
        """无说明时显示占位符"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn("—", html)

    def test_name_is_link_to_endpoint_edit_new_tab(self):
        """名称列链接到接口配置页且新开窗"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertIn('href="/config/reports/1/api_endpoints/1/edit"', html)
        self.assertIn("target=\"_blank\"", html)
        self.assertIn('title="打开接口配置"', html)

    def test_report_name_is_link_to_report_page_new_tab(self):
        """独立管理页：关联报表列链接到报表查看页且新开窗"""
        ep = dict(self._ep(1), report_id=7, report_name="销售报表")
        html = build_api_endpoints_list_html([ep], show_report_name=True)
        self.assertIn('href="/report?id=7"', html)
        self.assertIn("target=\"_blank\"", html)
        self.assertIn("销售报表", html)

    def test_url_cell_shows_three_urls(self):
        """URL 列展示完整/全量/静态三种地址（data-kind 供 JS 填充 origin）"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1,
                                             base_url="http://127.0.0.1:8000")
        self.assertIn('data-kind="base"', html)
        self.assertIn('data-kind="full"', html)
        self.assertIn('data-kind="static"', html)
        self.assertIn("完整 URL:", html)
        self.assertIn("全量 URL:", html)
        self.assertIn("静态 URL:", html)
        self.assertIn("http://127.0.0.1:8000/api/ep1", html)
        self.assertIn("http://127.0.0.1:8000/api/ep1?fetch_all=true", html)
        self.assertIn("http://127.0.0.1:8000/api/ep1.json", html)

    def test_url_row_disabled_when_fetch_all_off(self):
        """allow_fetch_all=0 时全量 URL 置灰 + 原因提示 + 去开启链接"""
        html = build_api_endpoints_list_html([self._ep(1, allow_fetch_all=0)],
                                             report_id=1)
        self.assertIn("opacity:0.55", html)
        self.assertIn("未开启「允许全量获取」，请在接口配置中开启", html)
        self.assertIn("去开启 ↗", html)
        self.assertIn("disabled", html)

    def test_url_row_disabled_when_static_cache_off(self):
        """static_cache=0 时静态 URL 置灰 + 原因提示"""
        html = build_api_endpoints_list_html([self._ep(1, static_cache=0)],
                                             report_id=1)
        self.assertIn("未开启「静态缓存」，请在接口配置中开启", html)
        self.assertIn("去开启 ↗", html)

    def test_api_key_copy_button(self):
        """有 API Key 时掩码展示 + 复制完整值按钮（隐藏 code 存原始值）"""
        ep = dict(self._ep(1), api_key="sk-abcdef1234567890")
        html = build_api_endpoints_list_html([ep], report_id=1)
        self.assertIn("sk-a***7890", html)
        self.assertIn('id="api-key-raw-1"', html)
        self.assertIn("sk-abcdef1234567890", html)
        self.assertIn("copyToClipboard('api-key-raw-1')", html)

    def test_api_key_empty_no_copy(self):
        """无 API Key 时不显示复制按钮"""
        html = build_api_endpoints_list_html([self._ep(1)], report_id=1)
        self.assertNotIn("api-key-raw-1", html)

    def test_admin_page_has_edit_button(self):
        """独立管理页补上编辑入口（名称链接 + 操作列编辑按钮）"""
        html = build_api_endpoints_list_html([self._ep(1)], show_report_name=True)
        self.assertIn('href="/config/reports/1/api_endpoints/1/edit"', html)
        self.assertIn(">编辑</a>", html)


class TestApiUrlsSectionHtml(unittest.TestCase):
    """build_api_urls_section_html 测试 — 样式与 Debug 信息模块一致。"""

    def _ep(self, eid, path="/api/test", static_cache=1, enabled=1, description="",
            report_id=1, fetch_all=1):
        return {"id": eid, "name": f"接口{eid}", "url_path": path,
                "static_cache": static_cache, "enabled": enabled,
                "description": description, "report_id": report_id,
                "allow_fetch_all": fetch_all}

    def test_uses_debug_info_structure(self):
        """外层结构与 Debug 信息模块一致（debug-info/debug-toggle/toggleSection/debug-content hidden）。"""
        html = build_api_urls_section_html([self._ep(1)], "http://127.0.0.1:8080")
        self.assertIn('class="debug-info"', html)
        self.assertIn('class="debug-toggle"', html)
        self.assertIn("toggleSection(this, 'API 调用地址')", html)
        self.assertIn('class="debug-content hidden"', html)
        self.assertIn("▶ API 调用地址", html)

    def test_default_collapsed(self):
        """默认折叠（debug-content hidden）。"""
        html = build_api_urls_section_html([self._ep(1)], "http://127.0.0.1:8080")
        self.assertIn('class="debug-content hidden"', html)

    def test_multiple_grouped_label(self):
        """多个接口时标题显示数量。"""
        html = build_api_urls_section_html(
            [self._ep(1), self._ep(2)], "http://127.0.0.1:8080")
        self.assertIn("API 调用地址 (2 个接口)", html)
        self.assertIn('toggleSection(this, \'API 调用地址 (2 个接口)\')', html)

    def test_url_code_has_js_attributes(self):
        """URL code 保留 data-path/data-kind/api-url-code 供 JS 填充。"""
        html = build_api_urls_section_html([self._ep(1, "/api/测试")], "http://127.0.0.1:8080")
        self.assertIn('class="api-url-code"', html)
        self.assertIn('data-path="/api/测试"', html)
        self.assertIn('data-kind="base"', html)
        self.assertIn('data-kind="full"', html)
        self.assertIn('data-kind="static"', html)

    def test_no_duplicate_api_prefix(self):
        """URL 拼接不应重复 /api。"""
        html = build_api_urls_section_html([self._ep(1)], "http://127.0.0.1:8080")
        self.assertNotIn("/api//api/", html)

    def test_badge_enabled(self):
        """启用端点在接口名旁显示绿色启用徽章"""
        html = build_api_urls_section_html([self._ep(1, enabled=1)], "http://x")
        self.assertIn("#059669", html)
        self.assertIn("启用", html)

    def test_badge_disabled(self):
        """禁用端点在接口名旁显示红色禁用徽章"""
        html = build_api_urls_section_html([self._ep(1, enabled=0)], "http://x")
        self.assertIn("#dc2626", html)
        self.assertIn("禁用", html)

    def test_description_keeps_newlines(self):
        """说明文本 Markdown 渲染保留换行（nl2br）且 HTML 安全剥离"""
        html = build_api_urls_section_html(
            [self._ep(1, description="第一行说明\n第二行 <b>转义</b>")], "http://x")
        self.assertIn("第一行说明", html)
        self.assertIn("<br>", html)
        self.assertIn("第二行", html)
        # <b> 标签被消毒剥离、文本保留（render_markdown 语义，非 _escape 原样转义）
        self.assertNotIn("<b>", html)
        self.assertNotIn("&lt;b&gt;", html)
        self.assertIn("转义", html)

    def test_long_description_full_render_in_fold(self):
        """长说明（含换行）在折叠区内完整渲染，无 line-clamp、无 toggleApiDesc"""
        html = build_api_urls_section_html(
            [self._ep(1, description="行一\n行二\n行三\n行四")], "http://x")
        self.assertNotIn("toggleApiDesc", html)
        self.assertNotIn("webkit-line-clamp", html)
        self.assertIn("▼ 接口说明", html)
        self.assertIn('data-mem-key="api_desc_fold_1"', html)
        # 折叠区内四行全部渲染（含 <br> 换行保留）
        self.assertIn("行一<br>", html)
        self.assertIn("行四", html)

    def test_short_description_in_fold(self):
        """短说明在「接口说明」折叠区内渲染 + 三态控件，无 toggleApiDesc"""
        html = build_api_urls_section_html(
            [self._ep(1, description="简短说明")], "http://x")
        self.assertNotIn("toggleApiDesc", html)
        self.assertIn("▼ 接口说明", html)
        self.assertIn('data-mem-key="api_desc_fold_1"', html)
        self.assertIn("mem-mode", html)
        self.assertIn("<p>简短说明</p>", html)

    def test_no_description_no_block(self):
        """无说明时不渲染「接口说明」折叠区"""
        html = build_api_urls_section_html([self._ep(1)], "http://x")
        self.assertNotIn("toggleApiDesc", html)
        self.assertNotIn("webkit-line-clamp", html)
        self.assertNotIn("接口说明", html)
        self.assertNotIn("api_desc_fold_", html)

    def test_grouped_badges_and_descriptions(self):
        """分组形态每个接口均含徽章与说明"""
        html = build_api_urls_section_html(
            [self._ep(1, enabled=1, description="接口一说明"),
             self._ep(2, enabled=0, description="接口二说明")], "http://x")
        self.assertIn("接口一说明", html)
        self.assertIn("接口二说明", html)
        self.assertEqual(html.count("#059669"), 1)
        self.assertEqual(html.count("#dc2626"), 1)

    def test_admin_actions_row_enabled_ep(self):
        """启用端点显示禁用按钮（POST toggle + 回跳来源）"""
        html = build_api_urls_section_html([self._ep(1, enabled=1)], "http://x")
        self.assertIn('name="action" value="toggle"', html)
        self.assertIn('name="endpoint_id" value="1"', html)
        self.assertIn('name="return_to"', html)
        self.assertIn("禁用", html)

    def test_admin_actions_row_disabled_ep(self):
        """禁用端点显示启用按钮"""
        html = build_api_urls_section_html([self._ep(1, enabled=0)], "http://x")
        self.assertIn('name="action" value="toggle"', html)
        self.assertIn("启用", html)

    def test_config_button_opens_edit_form(self):
        """配置按钮新窗口打开该接口编辑表单"""
        html = build_api_urls_section_html([self._ep(1)], "http://x")
        self.assertIn('target="_blank"', html)
        self.assertIn("/config/reports/", html)
        self.assertIn("/api_endpoints/1/edit", html)
        self.assertIn("配置", html)

    def test_report_page_disable_has_confirm(self):
        """报表页禁用操作带确认提示（防误停服）"""
        html = build_api_urls_section_html([self._ep(1, enabled=1)], "http://x")
        self.assertIn("onsubmit=", html)
        self.assertIn("confirm(", html)

    def test_report_page_enable_no_confirm(self):
        """报表页启用操作不确认（无损操作）"""
        html = build_api_urls_section_html([self._ep(1, enabled=0)], "http://x")
        self.assertNotIn("onsubmit=", html)

    def test_static_url_disabled_when_static_cache_off(self):
        """static_cache=0 时静态 URL 行置灰展示（不隐藏）：保留地址 + 原因提示 + 去开启链接。"""
        html = build_api_urls_section_html(
            [self._ep(1), self._ep(2, static_cache=0)], "http://127.0.0.1:8080")
        self.assertIn("api-static-1", html)
        self.assertIn("api-static-2", html)
        self.assertIn("opacity:0.55", html)
        self.assertIn("未开启「静态缓存」，请在接口配置中开启", html)
        self.assertIn("去开启 ↗", html)
        self.assertIn('href="/config/reports/1/api_endpoints/2/edit"', html)

    def test_full_url_disabled_when_fetch_all_off(self):
        """allow_fetch_all=0 时全量 URL 行置灰 + 原因提示。"""
        html = build_api_urls_section_html(
            [self._ep(1, fetch_all=0)], "http://127.0.0.1:8080")
        self.assertIn("opacity:0.55", html)
        self.assertIn("未开启「允许全量获取」，请在接口配置中开启", html)
        self.assertIn("去开启 ↗", html)

    def test_empty_returns_empty(self):
        """无 API 端点返回空字符串。"""
        self.assertEqual(build_api_urls_section_html([], "http://x"), "")


class TestStickyTableHeaderCss(unittest.TestCase):
    """报表表头悬浮（sticky thead）CSS 契约测试。

    需求：报表数据超过一屏时表头吸附在容器顶部，向下滚动仍可见列名。
    实现位置：_COMMON_CSS 的 th（position: sticky）与
    .table-wrap（overflow-y + max-height 限高触发滚动容器）。
    """

    def test_th_is_sticky(self):
        """th 启用 position:sticky 且 top:0（吸附容器顶部）。"""
        css = _COMMON_CSS
        self.assertIn("position: sticky", css)
        self.assertIn("top: 0", css)
        self.assertIn("z-index: 5", css)

    def test_th_sticky_inside_th_rule(self):
        """sticky 规则位于 th 选择器块内（非全局裸规则）。"""
        css = _COMMON_CSS
        th_rule = css[css.index("th {"):]
        th_block_end = th_rule.index("}")
        th_block = th_rule[:th_block_end]
        self.assertIn("position: sticky", th_block)

    def test_table_wrap_scrollable(self):
        """table-wrap 垂直可滚 + max-height 限高（触发容器内滚动）。"""
        css = _COMMON_CSS
        self.assertIn("overflow-y: auto", css)
        self.assertIn("max-height: calc(100vh - 130px)", css)

    def test_table_wrap_rule_combined(self):
        """table-wrap 单规则内同时具备横向/垂直滚动与限高。"""
        css = _COMMON_CSS
        tw_rule = css[css.index(".table-wrap {"):]
        tw_block_end = tw_rule.index("}")
        tw_block = tw_rule[:tw_block_end]
        self.assertIn("overflow-x: auto", tw_block)
        self.assertIn("overflow-y: auto", tw_block)
        self.assertIn("max-height", tw_block)


# ===================================================================
# api-desc-markdown T1：三态折叠组件（build_collapse_section_html mem_key）
# 契约矩阵 M1 / M6
# ===================================================================

class TestCollapseMemKey(unittest.TestCase):
    """build_collapse_section_html 的 mem_key 三态折叠组件（矩阵 M1）。"""

    def test_without_mem_key_hidden_unchanged(self):
        """无 mem_key + default_hidden=True：与现状逐字符一致（无三态、无 data 属性）。"""
        html = build_collapse_section_html("备注", "内容", default_hidden=True)
        self.assertIn('<div class="debug-info">', html)
        self.assertIn('class="debug-content hidden"', html)
        self.assertNotIn("data-mem-key", html)
        self.assertNotIn("data-default-hidden", html)
        self.assertNotIn("mem-toggle", html)
        self.assertNotIn("mem-mode", html)

    def test_without_mem_key_expanded_unchanged(self):
        """无 mem_key + default_hidden=False：现状输出，无三态。"""
        html = build_collapse_section_html("备注", "内容", default_hidden=False)
        self.assertIn('<div class="debug-info">', html)
        self.assertIn('class="debug-content"', html)
        self.assertNotIn('class="debug-content hidden"', html)
        self.assertNotIn("mem-toggle", html)

    def test_mem_key_expanded_by_default(self):
        """mem_key + default_hidden=False：data 属性 + 三态按钮（自动高亮）+ 初始展开。"""
        html = build_collapse_section_html(
            "备注", "内容", default_hidden=False, button_text="▼ 备注", mem_key="memo_fold_3")
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn('data-default-hidden="0"', html)
        self.assertIn('class="mem-mode mem-mode-auto active" data-mode="auto"', html)
        self.assertIn('class="mem-mode mem-mode-open" data-mode="open"', html)
        self.assertIn('class="mem-mode mem-mode-fold" data-mode="fold"', html)
        self.assertIn("自动", html)
        self.assertIn("展开", html)
        self.assertIn("折叠", html)
        self.assertIn("▼ 备注", html)
        self.assertNotIn('class="debug-content hidden"', html)

    def test_mem_key_hidden_by_default(self):
        """mem_key + default_hidden=True：data-default-hidden=1 + 初始折叠。"""
        html = build_collapse_section_html(
            "备注", "内容", default_hidden=True, button_text="▶ 备注", mem_key="memo_fold_3")
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn('data-default-hidden="1"', html)
        self.assertIn("▶ 备注", html)
        self.assertIn('class="debug-content hidden"', html)
        self.assertIn("mem-mode", html)

    def test_mem_key_api_desc_key(self):
        """API 说明折叠区使用 api_desc_fold_{id} 记忆键（契约：data-mem-key + 三态 + 初始展开）。"""
        html = build_collapse_section_html(
            "接口说明", "说明", default_hidden=False, mem_key="api_desc_fold_7")
        self.assertIn('data-mem-key="api_desc_fold_7"', html)
        self.assertIn('data-default-hidden="0"', html)
        self.assertIn("mem-mode", html)
        self.assertNotIn('class="debug-content hidden"', html)

    def test_toggle_button_adjacent_to_content(self):
        """标题按钮与内容 div 保持相邻（toggleSection 依赖 nextElementSibling），三态在内容之后。"""
        html = build_collapse_section_html(
            "备注", "内容", default_hidden=False, button_text="▼ 备注", mem_key="memo_fold_3")
        self.assertIn("</button><div class=\"debug-content\">内容</div>", html)
        # 三态控件在内容 div 之后、折叠区容器之内
        self.assertIn('</div><span class="mem-toggle">', html)
        self.assertLess(
            html.index('class="debug-content"'), html.index("mem-toggle"))

    def test_mem_key_multiline_keeps_structure(self):
        """mem_key 与 multiline=True 组合：结构保持，三态仍在内容之后。"""
        html = build_collapse_section_html(
            "接口说明", "多行内容", default_hidden=False, multiline=True, mem_key="api_desc_fold_1")
        self.assertIn('data-mem-key="api_desc_fold_1"', html)
        self.assertIn('class="debug-content"', html)
        self.assertIn("mem-toggle", html)
        # multiline 输出 button 与 content 分行，但 button 后第一个兄弟仍是 content
        self.assertIn("</button>\n<div class=\"debug-content\">\n", html)


class TestCollapseMemKeyJs(unittest.TestCase):
    """_COMMON_JS 三态 JS 逻辑（矩阵 M6，静态断言）。"""

    def test_has_mem_toggle_functions(self):
        """_COMMON_JS 含三态初始化与设置函数。"""
        self.assertIn("function initMemToggles(", _COMMON_JS)
        self.assertIn("function applyMemMode(", _COMMON_JS)
        self.assertIn("function setMemToggle(", _COMMON_JS)
        self.assertIn("function highlightMemMode(", _COMMON_JS)

    def test_auto_open_fold_value_domain(self):
        """三态值域 auto/open/fold 出现在 JS 逻辑中。"""
        self.assertIn("'auto'", _COMMON_JS)
        self.assertIn("'open'", _COMMON_JS)
        self.assertIn("'fold'", _COMMON_JS)

    def test_init_mem_toggles_called(self):
        """页面加载即调用 initMemToggles（无 mem_key 元素时 no-op）。"""
        self.assertIn("initMemToggles();", _COMMON_JS)

    def test_toggle_section_syncs_mem_key(self):
        """标题按钮折叠切换与三态同步：容器含 data-mem-key 时写 localStorage 并刷新高亮。"""
        body = self._extract_js_function(_COMMON_JS, "toggleSection")
        self.assertTrue(body, "应在 _COMMON_JS 中找到 toggleSection 函数")
        self.assertIn("data-mem-key", body)
        self.assertIn("localStorage.setItem", body)
        self.assertIn("highlightMemMode", body)

    @staticmethod
    def _extract_js_function(js: str, name: str) -> str:
        start = js.find(f"function {name}(")
        if start < 0:
            return ""
        brace = js.find("{", start)
        depth = 0
        i = brace
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[brace:i + 1]
            i += 1
        return ""


# ===================================================================
# api-desc-markdown T2：报表备注折叠区三态（矩阵 M2）
# ===================================================================

class TestMemoSectionMemKey(unittest.TestCase):
    """build_memo_section_html 的 report_id 三态接入（矩阵 M2）。"""

    def test_nonempty_with_report_id(self):
        """非空备注 + report_id=3：默认折叠（批次6#24）+ data-mem-key + 三态 + .md-body。"""
        html = build_memo_section_html("这是备注", 3)
        self.assertIn("\u25b6 备注", html)
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn('data-default-hidden="1"', html)
        self.assertIn("mem-mode", html)
        self.assertIn('<div class="md-body"><p>这是备注</p></div>', html)
        self.assertIn('class="debug-content hidden"', html)

    def test_empty_with_report_id(self):
        """空备注 + report_id=3：▶ 备注 + data-mem-key + 三态（折叠区仍渲染）。"""
        html = build_memo_section_html("", 3)
        self.assertIn("▶ 备注", html)
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn('data-default-hidden="1"', html)
        self.assertIn("mem-mode", html)
        self.assertIn('class="debug-content hidden"', html)

    def test_nonempty_without_report_id_unchanged(self):
        """非空备注 + report_id=None：无三态、无 data-mem-key，默认折叠（批次6#24）。"""
        html = build_memo_section_html("这是备注")
        self.assertIn("\u25b6 备注", html)
        self.assertIn('class="debug-content hidden"', html)
        self.assertNotIn("data-mem-key", html)
        self.assertNotIn("data-default-hidden", html)
        self.assertNotIn("mem-mode", html)

    def test_mermaid_content_kept_with_report_id(self):
        """含 mermaid 备注 + report_id：折叠区内 <pre class="mermaid"> 保留，三态共存。"""
        html = build_memo_section_html("```mermaid\nflowchart TD\n A-->B\n```", 3)
        self.assertIn('data-mem-key="memo_fold_3"', html)
        self.assertIn("mem-mode", html)
        self.assertIn('<pre class="mermaid">', html)
        self.assertIn("\u25b6 备注", html)


# ===================================================================
# api-desc-markdown T3：API 接口说明查看页 Markdown 化 + 折叠区（矩阵 M3）
# ===================================================================

class TestApiDescriptionMarkdown(unittest.TestCase):
    """_build_api_description_html 的 Markdown 折叠区语义（矩阵 M3）。"""

    @staticmethod
    def _ep(ep_id=7, desc=None):
        return {"id": ep_id, "name": "测试接口", "description": desc,
                "url_path": "/api/t", "enabled": 1, "static_cache": 1,
                "allow_fetch_all": 1}

    def test_empty_returns_blank(self):
        """desc 空/None/纯空白：返回空串（不渲染任何块）。"""
        for desc in (None, "", "   "):
            self.assertEqual(_build_api_description_html(self._ep(desc=desc)), "")

    def test_plain_text(self):
        """纯文本 desc：▼ 接口说明 + data-mem-key + 三态 + <p> 渲染 + 初始展开。"""
        html = _build_api_description_html(self._ep(desc="说明"))
        self.assertIn("▼ 接口说明", html)
        self.assertIn('data-mem-key="api_desc_fold_7"', html)
        self.assertIn('data-default-hidden="0"', html)
        self.assertIn("mem-mode", html)
        self.assertIn('<div class="md-body"><p>说明</p></div>', html)
        self.assertNotIn('class="debug-content hidden"', html)

    def test_markdown_heading_and_list(self):
        """Markdown 结构：# 标题 + 列表 → <h1> + <ul><li>。"""
        html = _build_api_description_html(self._ep(desc="# 标题\n\n- a\n- b"))
        self.assertIn("<h1>标题</h1>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<li>a</li>", html)

    def test_markdown_bold_italic(self):
        """**粗** _斜_ → <strong>粗</strong> <em>斜</em>。"""
        html = _build_api_description_html(self._ep(desc="**粗** _斜_"))
        self.assertIn("<strong>粗</strong> <em>斜</em>", html)

    def test_newlines_kept_nl2br(self):
        """第一行\\n第二行 → <p>第一行<br>\\n第二行</p>（保留换行）。"""
        html = _build_api_description_html(self._ep(desc="第一行\n第二行"))
        self.assertIn("<p>第一行<br>", html)
        self.assertIn("第二行</p>", html)

    def test_dangerous_link_sanitized(self):
        """[危险](javascript:alert(1)) → 链接成对剥离、文本保留、无 javascript:。"""
        html = _build_api_description_html(self._ep(desc="[危险](javascript:alert(1))"))
        self.assertIn("危险", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("<a", html)

    def test_script_tag_stripped(self):
        """<script>alert(1)</script> → script 剥离、文本保留。"""
        html = _build_api_description_html(self._ep(desc="<script>alert(1)</script>"))
        self.assertIn("alert(1)", html)
        self.assertNotIn("<script>", html)

    def test_long_desc_full_render(self):
        """超长说明（>80 字符）在折叠区内完整渲染，无 line-clamp、无 toggleApiDesc。"""
        long_desc = "这是用于验证超长说明折叠区完整渲染的填充文本，" * 10
        self.assertGreater(len(long_desc), 80)
        html = _build_api_description_html(self._ep(desc=long_desc))
        self.assertNotIn("webkit-line-clamp", html)
        self.assertNotIn("toggleApiDesc", html)
        self.assertIn("▼ 接口说明", html)
        self.assertIn("这是用于验证超长说明折叠区完整渲染的填充文本，", html)

    def test_mermaid_block(self):
        """含 mermaid fenced 块：折叠区内 <pre class="mermaid"><code> 保留。"""
        html = _build_api_description_html(
            self._ep(desc="```mermaid\nflowchart TD\n A-->B\n```"))
        self.assertIn('<pre class="mermaid">', html)
        self.assertIn("▼ 接口说明", html)
        self.assertIn("mem-mode", html)


# ===================================================================
# api-desc-markdown T3：接口说明列表摘要保持纯文本（矩阵 M4，守护）
# ===================================================================

class TestApiDescSummaryPlainText(unittest.TestCase):
    """_build_desc_summary_html 列表摘要保持纯文本不渲染 Markdown（矩阵 M4）。"""

    def test_markdown_source_kept_verbatim(self):
        """**bold** 文本：原样转义显示源码，title 含全文，不渲染为 <strong>。"""
        html = _build_desc_summary_html("**bold** 文本")
        self.assertIn("**bold** 文本", html)
        self.assertNotIn("<strong>", html)
        self.assertIn('title="**bold** 文本"', html)

    def test_long_desc_truncated_with_title_fulltext(self):
        """超 40 字符：截断 40 字符 + …，title 保留全文。"""
        desc = ("这是一个用于验证接口说明列表摘要截断行为的文本，"
            "需要确保总长度明显超过四十个字符的上限以触发省略号。")
        self.assertGreater(len(desc), 40)
        html = _build_desc_summary_html(desc)
        self.assertIn(desc[:40] + "…", html)
        self.assertIn(f'title="{desc}"', html)
        self.assertNotIn(desc[40:], html.split("title=")[0])

    def test_empty_returns_none(self):
        """空/None/纯空白：返回 None。"""
        for desc in (None, "", "   "):
            self.assertIsNone(_build_desc_summary_html(desc))

    def test_raw_html_not_parsed(self):
        """<b>x</b>：转义显示（不解析为 HTML 元素）。"""
        html = _build_desc_summary_html("<b>x</b>")
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>", html)


class TestDeletionSafetyRender(unittest.TestCase):
    """批次2 删除安全渲染（spec ux-optimization）：

    confirm 弹窗必须披露破坏半径——删除不是「确定删除X？」一句话的事，
    管理员需要在点击前知道会连带发生什么。
    """

    def test_pool_confirm_with_ref_count(self):
        """#6：池有关联报表时 confirm 披露断连数量"""
        pools = [{"id": 1, "name": "主库", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        result = build_pool_section_html(pools, report_counts={1: 3})
        self.assertIn("3 个报表将失去数据库连接", result)
        self.assertIn("报表保留但无法执行", result)

    def test_pool_confirm_plain_without_refs(self):
        """无关联报表保持原文案"""
        pools = [{"id": 1, "name": "主库", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        result = build_pool_section_html(pools)
        self.assertIn("确定删除连接池 主库？", result)
        self.assertNotIn("失去数据库连接", result)

    def test_user_row_delete_hidden_for_current(self):
        """#7：当前登录用户的行不渲染删除按钮（服务端兜底仍在）"""
        users = [{"id": 1, "username": "admin"},
                 {"id": 2, "username": "bob"}]
        result = build_user_section_html(users, current_username="admin")
        # admin 行无删除表单；bob 行有
        self.assertEqual(result.count("/config/users/1/delete"), 0)
        self.assertIn("/config/users/2/delete", result)

    def test_user_confirm_mentions_sessions(self):
        """他人行 confirm 披露会话失效后果"""
        users = [{"id": 2, "username": "bob"}]
        result = build_user_section_html(users, current_username="admin")
        self.assertIn("登录会话将立即失效", result)


class TestCurrentRulesIncludeNestedFilter(unittest.TestCase):
    """「当前规则」文本框必须是含 nested_filter 的完整 JSON（FR-005 与 filters 并列）。

    确保用户在报表页复制后可整体粘贴到 API 配置「规则 JSON」并完整生效，
    不丢失嵌套筛选。
    """

    NF = {"op": "and", "conditions": [{"col": "age", "op": "gt", "value": 18}]}

    def _render_rules_json(self, nested_filter=NF):
        html = build_current_rules_section_html(
            filters=[("name", "contains", "a")],
            sorts=[("id", "asc")],
            display_columns=["id", "name"],
            all_columns=["id", "name", "x"],
            nested_filter=nested_filter,
        )
        m = re.search(
            r'<textarea id="current-rules-json"[^>]*>(.*?)</textarea>', html, re.S)
        self.assertIsNotNone(m, "当前规则未渲染 JSON 文本框")
        import html as _html
        return json.loads(_html.unescape(m.group(1))), html

    def test_nested_filter_present_in_rules_json(self):
        rules, _ = self._render_rules_json()
        self.assertIn("nested_filter", rules, "导出 JSON 漏写 nested_filter")
        self.assertEqual(rules["nested_filter"]["op"], "and")
        # 普通筛选/排序/字段仍并存
        self.assertEqual(rules["filters"][0]["col"], "name")
        self.assertEqual(rules["sorts"][0]["col"], "id")
        self.assertEqual(rules["columns"], "id,name")

    def test_no_nested_filter_key_when_absent(self):
        rules, _ = self._render_rules_json(nested_filter=None)
        self.assertNotIn("nested_filter", rules)

    def test_rules_json_roundtrips_to_api_config(self):
        """导出 JSON 能被 API 配置解析器拆出 nested_filter（端到端闭环）。"""
        import config
        rules, _ = self._render_rules_json()
        cols, f_str, s_str, nf_str = config._parse_rule_json(
            json.dumps(rules, ensure_ascii=False))
        self.assertTrue(nf_str, "API 配置解析器未拆出 nested_filter")
        self.assertEqual(json.loads(nf_str)["op"], "and")
        # 普通筛选/排序同步拆出
        self.assertEqual(json.loads(f_str)[0]["col"], "name")
        self.assertEqual(json.loads(s_str)[0]["col"], "id")

    def test_apply_rules_json_js_handles_nested_filter(self):
        """applyRulesJson() 必须写回 nested_filter 参数，否则复制→应用往返丢规则。"""
        import re as _re, pathlib
        src = pathlib.Path("render.py").read_text(encoding="utf-8")
        m = _re.search(r'function applyRulesJson\(\)\s*\{(.*?)\n\}', src, _re.S)
        self.assertIsNotNone(m, "未找到 applyRulesJson 函数")
        body = m.group(1)
        self.assertIn("nested_filter", body, "applyRulesJson 未处理 nested_filter")
