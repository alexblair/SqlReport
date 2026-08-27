"""test_filter_help.py — 筛选语法帮助（单一来源 + 弹窗渲染）测试

覆盖 04 号工单：
- 帮助内容结构化单一来源（分区标题/说明/案例表/要点），无第二份文案硬编码
- 单一渲染函数产物：报表页/审计页入口存在且都含默认收起弹窗
- 弹窗交互动作 JS 分支（展开/收起/点击外部关闭）
- 文案与 T1 实现语义逐条一致（多值 OR、* 通配、转义、空段忽略、等于下通配生效、多列 AND）
"""

import unittest
import re

import filter_help
from filter_help import filter_help_content, render_filter_help


class TestFilterHelpContent(unittest.TestCase):
    """帮助内容单一来源与语义一致性"""

    def test_content_structure(self):
        """结构化内容：5 分区（标题/说明/案例表）+ 要点列表"""
        content = filter_help_content()
        self.assertEqual(len(content["sections"]), 5)
        for sec in content["sections"]:
            self.assertTrue(sec["title"])
            self.assertTrue(sec["desc"])
            self.assertGreaterEqual(len(sec["examples"]), 2)
            for row in sec["examples"]:
                self.assertEqual(len(row), 3)
        self.assertGreaterEqual(len(content["notes"]), 2)

    def test_render_uses_single_content_source(self):
        """渲染产物与单一内容源一致：每个分区标题、说明、案例行都出现"""
        html = render_filter_help()
        content = filter_help_content()
        for sec in content["sections"]:
            self.assertIn(sec["title"], html)
            self.assertIn(sec["desc"], html)
            for row in sec["examples"]:
                for cell in row:
                    self.assertIn(cell, html)
        for note in content["notes"]:
            self.assertIn(note, html)

    def test_no_duplicate_copy_in_render(self):
        """表头文案仅渲染代码生成一处，内容常量无第二份文案"""
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "filter_help.py")
        src = open(src_path, encoding="utf-8").read()
        html = render_filter_help()
        self.assertEqual(src.count("想筛选"), 1)   # 仅渲染代码里的统一表头
        self.assertEqual(html.count("想筛选"), 5)  # 五个分区表头各一次
        self.assertEqual(html.count("筛选语法说明"), 2)  # 按钮 title + 弹窗标题

    def test_copy_matches_implementation_semantics(self):
        """文案与 parse_filter_expr 语义逐条一致（转义/空段/通配/AND）"""
        html = render_filter_help()
        self.assertIn("英文逗号分隔多个值", html)
        self.assertIn("\\*", html)
        self.assertIn("\\,", html)
        self.assertIn("\\", html)
        self.assertIn("多余的", html)
        self.assertIn("或", html)
        self.assertIn("且", html)
        self.assertIn("包含", html)
        self.assertIn("不包含", html)


class TestFilterHelpRender(unittest.TestCase):
    """弹窗渲染与交互动作（observable-assertions）"""

    def test_popup_default_collapsed(self):
        """弹窗默认收起：display:none 在渲染产物中"""
        self.assertIn("display:none", render_filter_help())

    def test_trigger_button_present(self):
        """常驻 ? 入口按钮存在，且带筛选语法说明标题"""
        html = render_filter_help()
        self.assertIn('class="filter-help-btn"', html)
        self.assertIn("?", html)
        self.assertIn("title=\"筛选语法说明\"", html)

    def test_toggle_js_has_expand_collapse_branches(self):
        """开关 JS 同时具备展开与收起分支"""
        js = render_filter_help()
        self.assertIn("function toggleFilterHelp", js)
        self.assertIn("display = 'block'", js)
        self.assertIn("display = 'none'", js)
        self.assertIn("onclick=\"toggleFilterHelp(this)\"", js)

    def test_click_outside_closes_popup(self):
        """点击弹窗外区域收起所有弹窗的分支存在"""
        js = render_filter_help()
        self.assertIn("addEventListener('click'", js)
        self.assertIn("closest('.filter-help')", js)
        self.assertIn("querySelectorAll('.filter-help-popup')", js)

    def test_popup_contains_close_button(self):
        """弹窗内提供“知道了”收起按钮"""
        self.assertIn("知道了", render_filter_help())


if __name__ == "__main__":
    unittest.main()
