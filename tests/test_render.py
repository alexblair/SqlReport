"""test_render.py — HTML 渲染模板函数测试"""

import unittest
from render import render_page_header, render_page_footer, render_navbar


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
