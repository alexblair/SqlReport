"""test_render_extra.py — render.py 未覆盖路径的补充测试

测试策略：每个测试只验证一个路径，使用 mock 模拟外部依赖。
"""

import unittest
from unittest.mock import patch, MagicMock
import time


class TestGetBrandingPrefix(unittest.TestCase):
    """_get_branding_prefix 测试"""

    @patch('render.branding')
    def test_prefix_with_value(self, mock_branding):
        """带前缀时返回转义后的值"""
        from render import _get_branding_prefix
        mock_branding.get_site_branding.return_value = {"prefix": "MySite"}
        result = _get_branding_prefix()
        self.assertEqual(result, "MySite")

    @patch('render.branding')
    def test_prefix_empty(self, mock_branding):
        """前缀为空字符串时返回空串"""
        from render import _get_branding_prefix
        mock_branding.get_site_branding.return_value = {"prefix": ""}
        result = _get_branding_prefix()
        self.assertEqual(result, "")

    @patch('render.branding')
    def test_prefix_html_escape(self, mock_branding):
        """前缀含 HTML 特殊字符时转义"""
        from render import _get_branding_prefix
        mock_branding.get_site_branding.return_value = {"prefix": '<script>"&"'}
        result = _get_branding_prefix()
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)
        self.assertIn("&quot;", result)
        self.assertIn("&amp;", result)


class TestBuildMemoSectionHtml(unittest.TestCase):
    """build_memo_section_html 测试"""

    @patch('render.markdown_render')
    def test_with_memo_content(self, mock_md):
        """有备注内容时渲染为 HTML"""
        from render import build_memo_section_html
        mock_md.render_markdown.return_value = "<p>备注内容</p>"
        result = build_memo_section_html("备注内容", report_id=1)
        self.assertIn("md-body", result)
        self.assertIn("备注内容", result)
        self.assertIn("▶ 备注", result)

    @patch('render.markdown_render')
    def test_empty_memo(self, mock_md):
        """空备注时无 md-body 容器"""
        from render import build_memo_section_html
        mock_md.render_markdown.return_value = ""
        result = build_memo_section_html("", report_id=1)
        self.assertNotIn("md-body", result)
        self.assertIn("▶ 备注", result)

    @patch('render.markdown_render')
    def test_with_report_id_enables_memory(self, mock_md):
        """report_id 提供时启用三态记忆"""
        from render import build_memo_section_html
        mock_md.render_markdown.return_value = "<p>test</p>"
        result = build_memo_section_html("test", report_id=42)
        self.assertIn("memo_fold_42", result)

    @patch('render.markdown_render')
    def test_without_report_id_no_memory(self, mock_md):
        """report_id 为 None 时无记忆控件"""
        from render import build_memo_section_html
        mock_md.render_markdown.return_value = "<p>test</p>"
        result = build_memo_section_html("test", report_id=None)
        self.assertNotIn("memo_fold_", result)


class TestBuildReportSwitcherHtml(unittest.TestCase):
    """build_report_switcher_html 测试"""

    def test_basic_structure(self):
        """基本结构包含表单和下拉框"""
        from render import build_report_switcher_html
        reports = [{"id": 1, "name": "报表1", "category_id": None}]
        result = build_report_switcher_html(reports, [], [])
        self.assertIn('<select name="id"', result)
        self.assertIn("切换报表:", result)
        self.assertIn("报表1", result)

    def test_uncategorized_reports(self):
        """未分类报表显示为未分类"""
        from render import build_report_switcher_html
        reports = [{"id": 1, "name": "未分类报表", "category_id": None}]
        result = build_report_switcher_html(reports, [], [])
        self.assertIn("(未分类)", result)
        self.assertIn("未分类报表", result)

    def test_categorized_reports(self):
        """分类报表在 optgroup 中"""
        from render import build_report_switcher_html
        reports = [{"id": 1, "name": "分类报表", "category_id": 10}]
        cats = [{"id": 10, "name": "分类A", "children": []}]
        result = build_report_switcher_html(reports, [], cats)
        self.assertIn("分类A", result)
        self.assertIn("分类报表", result)

    def test_current_report_selected(self):
        """当前报表高亮选中"""
        from render import build_report_switcher_html
        reports = [{"id": 1, "name": "报表1", "category_id": None}]
        result = build_report_switcher_html(reports, [], [], current_id=1)
        self.assertIn("selected", result)

    def test_empty_category_shows_disabled(self):
        """空分类显示为禁用项"""
        from render import build_report_switcher_html
        reports = []
        cats = [{"id": 10, "name": "空分类", "children": []}]
        result = build_report_switcher_html(reports, [], cats)
        self.assertIn("disabled", result)
        self.assertIn("无报表", result)

    def test_nested_children(self):
        """嵌套子分类正确渲染"""
        from render import build_report_switcher_html
        reports = [{"id": 1, "name": "子报表", "category_id": 20}]
        cat_tree = [{"id": 10, "name": "父分类", "children": [
            {"id": 20, "name": "子分类", "children": []}
        ]}]
        result = build_report_switcher_html(reports, [], cat_tree)
        self.assertIn("父分类", result)
        self.assertIn("子分类", result)
        self.assertIn("子报表", result)


class TestBuildDebugSectionHtml(unittest.TestCase):
    """build_debug_section_html 测试"""

    def test_with_pool_config(self):
        """有连接池配置时显示连接池信息"""
        from render import build_debug_section_html
        pool = {"name": "test_pool", "host": "localhost", "port": 3306,
                "user": "root", "database": "testdb"}
        result = build_debug_section_html(pool, "SELECT 1", 0, 1, ["结果1"], [], [])
        self.assertIn("连接池:", result)
        self.assertIn("test_pool", result)
        self.assertIn("localhost", result)
        self.assertIn("SELECT 1", result)

    def test_without_pool_config(self):
        """无连接池配置时不显示连接池信息"""
        from render import build_debug_section_html
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["结果1"], [], [])
        self.assertNotIn("连接池:", result)
        self.assertIn("SELECT 1", result)

    def test_multiple_results(self):
        """多结果集时显示当前索引"""
        from render import build_debug_section_html
        result = build_debug_section_html(None, "SELECT 1", 1, 3, ["R1", "R2", "R3"], [], [])
        self.assertIn("结果: 2/3 (R2)", result)

    def test_with_filters(self):
        """有筛选时显示筛选条件"""
        from render import build_debug_section_html
        filters = [("name", "contains", "test")]
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["结果1"], filters, [])
        self.assertIn("筛选:", result)
        self.assertIn("name", result)

    def test_with_sorts(self):
        """有排序时显示排序信息"""
        from render import build_debug_section_html
        sorts = [("id", "asc")]
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["结果1"], [], sorts)
        self.assertIn("排序:", result)
        self.assertIn("id", result)
        self.assertIn("↑", result)

    def test_descending_sort_arrow(self):
        """降序排序显示向下箭头"""
        from render import build_debug_section_html
        sorts = [("name", "desc")]
        result = build_debug_section_html(None, "SELECT 1", 0, 1, ["结果1"], [], sorts)
        self.assertIn("↓", result)


class TestBuildCurrentRulesSectionHtml(unittest.TestCase):
    """build_current_rules_section_html 测试"""

    def test_with_filters_and_sorts(self):
        """有筛选和排序时生成 JSON 规则"""
        from render import build_current_rules_section_html
        filters = [("col1", "contains", "val1")]
        sorts = [("col1", "asc")]
        result = build_current_rules_section_html(filters, sorts, ["col1"], ["col1", "col2"])
        self.assertIn("current-rules-json", result)
        self.assertIn("filters", result)
        self.assertIn("sorts", result)

    def test_no_custom_rules(self):
        """无自定义规则时显示默认提示"""
        from render import build_current_rules_section_html
        result = build_current_rules_section_html([], [], ["col1", "col2"], ["col1", "col2"])
        self.assertIn("无自定义规则", result)

    def test_columns_subset(self):
        """字段子集时显示字段信息"""
        from render import build_current_rules_section_html
        result = build_current_rules_section_html([], [], ["col1"], ["col1", "col2"])
        self.assertIn("columns", result)
        self.assertIn("字段:", result)

    def test_copy_button_exists(self):
        """包含复制按钮"""
        from render import build_current_rules_section_html
        result = build_current_rules_section_html([], [], ["col1"], ["col1"])
        self.assertIn("复制", result)

    def test_apply_button_exists(self):
        """包含应用按钮"""
        from render import build_current_rules_section_html
        result = build_current_rules_section_html([], [], ["col1"], ["col1"])
        self.assertIn("应用", result)


class TestBuildRedisBannersHtml(unittest.TestCase):
    """build_redis_banners_html 测试"""

    def test_no_cache_info(self):
        """无缓存信息时返回空"""
        from render import build_redis_banners_html
        result = build_redis_banners_html(None)
        self.assertEqual(result, "")

    @patch('render.app_config')
    def test_redis_source(self, mock_app_config):
        """Redis 源时显示 Redis 快照横幅"""
        from render import build_redis_banners_html
        mock_app_config.format_local_time.return_value = "2024-01-01 12:00:00"
        cache_info = {"source": "redis", "timestamp": time.time()}
        result = build_redis_banners_html(cache_info)
        self.assertIn("Redis 快照", result)
        self.assertIn("flash-info", result)

    @patch('render.redis_cache')
    def test_mysql_unavailable(self, mock_redis):
        """MySQL 模式下 Redis 不可用时显示切换提示"""
        from render import build_redis_banners_html
        mock_redis.redis_available.return_value = False
        cache_info = {"source": "mysql"}
        result = build_redis_banners_html(cache_info)
        self.assertIn("Redis 不可用", result)
        self.assertIn("直连 MySQL", result)

    @patch('render.redis_cache')
    def test_mysql_available(self, mock_redis):
        """MySQL 模式下 Redis 可用时无横幅"""
        from render import build_redis_banners_html
        mock_redis.redis_available.return_value = True
        cache_info = {"source": "mysql"}
        result = build_redis_banners_html(cache_info)
        self.assertEqual(result, "")

    def test_unknown_source(self):
        """未知源时返回空"""
        from render import build_redis_banners_html
        cache_info = {"source": "unknown"}
        result = build_redis_banners_html(cache_info)
        self.assertEqual(result, "")


class TestBuildCacheBadgeHtml(unittest.TestCase):
    """build_cache_badge_html 测试"""

    def test_no_cache_info(self):
        """无缓存信息时显示未缓存"""
        from render import build_cache_badge_html
        result = build_cache_badge_html(None)
        self.assertIn("未缓存", result)

    def test_redis_cache(self):
        """Redis 缓存时显示 Redis 快照"""
        from render import build_cache_badge_html
        cache_info = {"source": "redis", "timestamp": time.time() - 10}
        result = build_cache_badge_html(cache_info)
        self.assertIn("Redis 快照", result)
        self.assertIn("fresh", result)

    def test_redis_fallback(self):
        """Redis 兜底时显示 MySQL 不可用"""
        from render import build_cache_badge_html
        cache_info = {"source": "redis_fallback", "timestamp": time.time() - 10}
        result = build_cache_badge_html(cache_info)
        self.assertIn("MySQL 不可用", result)

    def test_process_cache(self):
        """进程缓存时显示进程缓存"""
        from render import build_cache_badge_html
        cache_info = {"source": "process", "timestamp": time.time() - 10}
        result = build_cache_badge_html(cache_info)
        self.assertIn("进程缓存", result)

    def test_direct_mysql(self):
        """直连 MySQL 时显示直连"""
        from render import build_cache_badge_html
        cache_info = {"source": "other"}
        result = build_cache_badge_html(cache_info)
        self.assertIn("直连 MySQL", result)

    def test_prefer_cache_with_ttl(self):
        """prefer_cache 且 TTL>0 时显示 TTL"""
        from render import build_cache_badge_html
        cache_info = {"source": "other"}
        result = build_cache_badge_html(cache_info, prefer_cache=True, cache_ttl_hours=2)
        self.assertIn("TTL=2h", result)

    def test_expired_cache(self):
        """缓存已过期时显示过期提示"""
        from render import build_cache_badge_html
        cache_info = {"source": "redis", "timestamp": time.time() - 7200}
        result = build_cache_badge_html(cache_info, prefer_cache=True, cache_ttl_hours=1)
        self.assertIn("已过期", result)
        self.assertIn("flash-warn", result)


class TestBuildScheduleFlagsBadgeHtml(unittest.TestCase):
    """build_schedule_flags_badge_html 测试"""

    def test_both_disabled(self):
        """两项都未启用时返回空"""
        from render import build_schedule_flags_badge_html
        result = build_schedule_flags_badge_html(0, 0)
        self.assertEqual(result, "")

    def test_sched_enabled(self):
        """定时启用时显示时钟符号"""
        from render import build_schedule_flags_badge_html
        result = build_schedule_flags_badge_html(1, 0)
        self.assertIn("⏰", result)
        self.assertIn("已配置定时执行", result)

    def test_keepalive_enabled(self):
        """保活启用时显示回收符号"""
        from render import build_schedule_flags_badge_html
        result = build_schedule_flags_badge_html(0, 1)
        self.assertIn("♻", result)
        self.assertIn("已开启缓存保活", result)

    def test_both_enabled(self):
        """两项都启用时显示两个符号"""
        from render import build_schedule_flags_badge_html
        result = build_schedule_flags_badge_html(1, 1)
        self.assertIn("⏰", result)
        self.assertIn("♻", result)

    def test_none_values(self):
        """None 值等同于 0"""
        from render import build_schedule_flags_badge_html
        result = build_schedule_flags_badge_html(None, None)
        self.assertEqual(result, "")


class TestBuildDeleteFormHtml(unittest.TestCase):
    """build_delete_form_html 测试"""

    def test_basic_form(self):
        """基本删除表单结构"""
        from render import build_delete_form_html
        result = build_delete_form_html("/delete/1", "确认删除?")
        self.assertIn('method="post"', result)
        self.assertIn('action="/delete/1"', result)
        self.assertIn("确认删除?", result)
        self.assertIn("删除", result)

    def test_with_extra_hidden(self):
        """带额外隐藏域"""
        from render import build_delete_form_html
        hidden = '<input type="hidden" name="token" value="abc">'
        result = build_delete_form_html("/delete/1", "确认?", extra_hidden=hidden)
        self.assertIn("token", result)

    def test_with_button_cls(self):
        """带额外按钮 class"""
        from render import build_delete_form_html
        result = build_delete_form_html("/delete/1", "确认?", button_cls=" btn-mini-s")
        self.assertIn("btn-mini-s", result)

    def test_custom_indent(self):
        """自定义缩进"""
        from render import build_delete_form_html
        result = build_delete_form_html("/delete/1", "确认?", indent=2)
        self.assertTrue(result.startswith("  <form"))

    def test_multi_line_hidden(self):
        """多行隐藏域正确缩进"""
        from render import build_delete_form_html
        hidden = '<input type="hidden" name="a" value="1">\n<input type="hidden" name="b" value="2">'
        result = build_delete_form_html("/delete/1", "确认?", extra_hidden=hidden)
        self.assertIn("a", result)
        self.assertIn("b", result)


class TestBuildMoveButtonsHtml(unittest.TestCase):
    """build_move_buttons_html 测试"""

    def test_single_item_no_buttons(self):
        """单个项不显示按钮"""
        from render import build_move_buttons_html
        result = build_move_buttons_html(1, "pools", 0, 1)
        self.assertEqual(result, "")

    def test_first_item_only_down(self):
        """第一项只显示下移按钮"""
        from render import build_move_buttons_html
        result = build_move_buttons_html(1, "pools", 0, 3)
        self.assertNotIn("move-up", result)
        self.assertIn("move-down", result)

    def test_last_item_only_up(self):
        """最后一项只显示上移按钮"""
        from render import build_move_buttons_html
        result = build_move_buttons_html(3, "pools", 2, 3)
        self.assertIn("move-up", result)
        self.assertNotIn("move-down", result)

    def test_middle_item_both_buttons(self):
        """中间项显示上下移按钮"""
        from render import build_move_buttons_html
        result = build_move_buttons_html(2, "pools", 1, 3)
        self.assertIn("move-up", result)
        self.assertIn("move-down", result)

    def test_section_in_url(self):
        """section 参数体现在 URL 中"""
        from render import build_move_buttons_html
        result = build_move_buttons_html(1, "reports", 0, 2)
        self.assertIn("/config/reports/1/", result)


if __name__ == "__main__":
    unittest.main()
