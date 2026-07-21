"""test_render.py — HTML 渲染模板函数测试"""

import unittest
from datetime import datetime
from decimal import Decimal
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
        """输出包含 JavaScript 脚本"""
        result = render_page_footer()
        self.assertIn('<script>', result)
        self.assertIn('toggleSection', result)
        self.assertIn('toggleFilterInput', result)


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
        """有备注内容时显示展开状态"""
        result = build_memo_section_html("这是一段备注内容")
        self.assertIn("▼ 备注", result)
        self.assertIn("这是一段备注内容", result)
        self.assertIn("debug-info", result)

    def test_empty_memo(self):
        """备注为空时显示折叠状态"""
        result = build_memo_section_html("")
        self.assertIn("▶ 备注", result)

    def test_none_memo(self):
        """备注为 None 时显示折叠状态"""
        result = build_memo_section_html(None)
        self.assertIn("▶ 备注", result)

    def test_memo_html_escaped(self):
        """备注中的 HTML 被转义"""
        result = build_memo_section_html("<script>alert(1)</script>")
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script>", result)

    def test_long_memo(self):
        """长备注全部显示"""
        long_text = "A" * 1000
        result = build_memo_section_html(long_text)
        self.assertIn("A" * 1000, result)
        self.assertIn("▼ 备注", result)


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
        """基础列生成 th 元素"""
        cols = ["id", "name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn("<th>", result)
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

    def test_filter_input_present(self):
        """每列包含筛选输入框"""
        cols = ["name"]
        result = build_table_header_html(cols, cols, [], [], 1, 20, "", "")
        self.assertIn("filter-input", result)
        self.assertIn('placeholder="筛选 name..."', result)

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
        self.assertIn("GBK", result)
        self.assertIn("UTF8", result)

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

    def test_rebuild_cache_link(self):
        """包含重建缓存链接"""
        result = build_controls_bar_html(1, 20, [], [], "", ["id", "name"], 0,
                                          "", 100, 5)
        self.assertIn("重建缓存", result)
        self.assertIn("refresh=1", result)

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

    def test_contains_add_buttons(self):
        """包含新增分类和新增报表按钮"""
        result = build_category_section_html(self.cat_reports, self.unclassified_reports,
                                              self.all_cats, self.all_reports,
                                              self.pools, self.cat_tree)
        self.assertIn("新增分类", result)
        self.assertIn("新增报表", result)

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
