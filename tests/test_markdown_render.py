"""
test_markdown_render.py — Markdown 渲染模块测试

覆盖 spec（.scratch/memo-markdown/spec.md）行为契约矩阵 M1 / M2 全形态：
- M1 render_markdown 输入形态 → 输出 HTML 关键特征
- M2 contains_mermaid / extract_mermaid_blocks 判定

测试只断言外部行为（渲染输出 HTML），不测 sanitize 内部实现细节。
"""

import unittest

from markdown_render import (
    contains_mermaid, extract_mermaid_blocks, render_markdown,
    codehilite_css,
)


class TestRenderMarkdownInputs(unittest.TestCase):
    """矩阵 M1：输入形态 → 输出 HTML"""

    def test_none_returns_empty(self):
        self.assertEqual(render_markdown(None), "")

    def test_empty_string_returns_empty(self):
        self.assertEqual(render_markdown(""), "")

    def test_blank_string_returns_empty(self):
        self.assertEqual(render_markdown("   \n\t"), "")

    def test_plain_text(self):
        self.assertEqual(render_markdown("hello"), "<p>hello</p>")

    def test_single_newline_kept_via_nl2br(self):
        out = render_markdown("a\nb")
        self.assertIn("<br", out)
        self.assertIn("a", out)
        self.assertIn("b", out)

    def test_heading(self):
        self.assertEqual(render_markdown("# 标题"), "<h1>标题</h1>")

    def test_subheading_levels(self):
        self.assertIn("<h2>", render_markdown("## 二级"))
        self.assertIn("<h3>", render_markdown("### 三级"))

    def test_unordered_list(self):
        out = render_markdown("- a\n- b")
        self.assertIn("<ul>", out)
        self.assertEqual(out.count("<li>"), 2)

    def test_bold_and_italic(self):
        out = render_markdown("**粗** _斜_")
        self.assertIn("<strong>粗</strong>", out)
        self.assertIn("<em>斜</em>", out)

    def test_safe_link(self):
        self.assertIn('<a href="https://x">链接</a>', render_markdown("[链接](https://x)"))

    def test_mailto_link(self):
        self.assertIn('<a href="mailto:a@b.com">m</a>',
                      render_markdown("[m](mailto:a@b.com)"))

    def test_javascript_link_stripped_text_kept(self):
        out = render_markdown("[危险](javascript:alert(1))")
        self.assertNotIn("<a", out)
        self.assertIn("危险", out)

    def test_data_uri_link_stripped(self):
        out = render_markdown("[x](data:text/html;base64,PHNjcmlwdD4=)")
        self.assertNotIn("<a", out)
        self.assertIn("x", out)

    def test_entity_encoded_javascript_protocol_stripped(self):
        out = render_markdown('[x](&#106;avascript:alert(1))')
        self.assertNotIn("<a", out)

    def test_relative_link_allowed(self):
        self.assertIn('<a href="/path">x</a>', render_markdown("[x](/path)"))

    def test_table(self):
        out = render_markdown("| a | b |\n| --- | --- |\n| 1 | 2 |")
        self.assertIn("<table>", out)
        self.assertIn("<thead>", out)
        self.assertIn("<tbody>", out)
        self.assertIn("<th>a</th>", out)
        self.assertIn("<td>1</td>", out)

    def test_inline_code(self):
        self.assertIn("<code>code</code>", render_markdown("`code`"))

    def test_sql_codeblock_highlighted(self):
        out = render_markdown("```sql\nSELECT 1\n```")
        self.assertIn('<div class="highlight">', out)
        self.assertIn('<span class="k">SELECT</span>', out)
        self.assertIn('<span class="mi">1</span>', out)

    def test_mermaid_codeblock_pre_style(self):
        out = render_markdown("```mermaid\nflowchart TD\n A-->B\n```")
        self.assertIn('<pre class="mermaid">', out)
        self.assertIn("<code>flowchart TD\n A--&gt;B</code>", out)

    def test_multiple_mermaid_blocks(self):
        out = render_markdown("```mermaid\nA\n```\n\n```mermaid\nB\n```")
        self.assertEqual(out.count('<pre class="mermaid">'), 2)

    def test_mermaid_block_surrounded_by_text(self):
        out = render_markdown("a\n\n```mermaid\ngraph LR\n X-->Y\n```\n\nb")
        self.assertIn('<pre class="mermaid">', out)
        self.assertIn("<p>a</p>", out)
        self.assertIn("<p>b</p>", out)

    def test_unclosed_mermaid_block_rendered_as_mermaid(self):
        out = render_markdown("```mermaid\nflowchart TD\n A-->B\n")
        self.assertIn('<pre class="mermaid">', out)

    def test_mermaid_source_escaped(self):
        out = render_markdown("```mermaid\nA-->B & <b>\n```")
        self.assertIn("A--&gt;B &amp; &lt;b&gt;", out)
        self.assertNotIn("<b>", out)

    def test_script_tag_stripped_text_kept(self):
        out = render_markdown("<script>alert(1)</script>")
        self.assertNotIn("<script", out)
        self.assertIn("alert(1)", out)

    def test_event_attribute_stripped_tag_kept(self):
        out = render_markdown('<span onclick="x()">t</span>')
        self.assertIn("<span>t</span>", out)
        self.assertNotIn("onclick", out)

    def test_img_onerror_stripped(self):
        out = render_markdown('<img onerror="x()" src="y">')
        self.assertIn('<img src="y">', out)
        self.assertNotIn("onerror", out)

    def test_mixed_attack_inputs(self):
        out = render_markdown("**粗** <script>alert(1)</script> [跳](javascript:x)")
        self.assertNotIn("<script", out)
        self.assertNotIn("<a", out)
        self.assertIn("<strong>粗</strong>", out)

    def test_comment_stripped(self):
        self.assertNotIn("<!--", render_markdown("<!-- hi -->"))

    def test_raw_html_block_stripped(self):
        out = render_markdown("<div>内部</div>")
        self.assertIn("<div>内部</div>", out)

    def test_long_text_no_crash(self):
        text = "段落内容。\n\n" * 2000
        out = render_markdown(text)
        self.assertIn("<p>", out)

    def test_codehilite_css_classes_survive_sanitize(self):
        out = render_markdown("```python\nprint(1)\n```")
        self.assertIn('<div class="highlight">', out)
        self.assertIn('<span class="', out)

    def test_codehilite_css_is_dark_theme(self):
        """高亮 CSS 为深色系（monokai，配套 .md-body 深色 pre）"""
        css = codehilite_css()
        self.assertIn("#272822", css)
        self.assertIn(".highlight .k { color: #66D9EF", css)

    def test_markdown_special_chars_entity_safe(self):
        self.assertIn("&lt;script&gt;", render_markdown("&lt;script&gt;"))


class TestMermaidDetection(unittest.TestCase):
    """矩阵 M2：contains_mermaid / extract_mermaid_blocks 判定"""

    def test_contains_mermaid_block(self):
        self.assertTrue(contains_mermaid("```mermaid\nA\n```"))

    def test_contains_mermaid_unclosed(self):
        self.assertTrue(contains_mermaid("```mermaid\nA"))

    def test_not_contains_python_block(self):
        self.assertFalse(contains_mermaid("```python\nx\n```"))

    def test_not_contains_no_fence(self):
        self.assertFalse(contains_mermaid("普通文本"))

    def test_not_contains_empty(self):
        self.assertFalse(contains_mermaid(""))

    def test_not_contains_none(self):
        self.assertFalse(contains_mermaid(None))

    def test_extract_single_block(self):
        self.assertEqual(extract_mermaid_blocks("```mermaid\nA\n```"), 1)

    def test_extract_multiple_blocks(self):
        self.assertEqual(
            extract_mermaid_blocks("```mermaid\nA\n```\n```mermaid\nB\n```"), 2)

    def test_extract_ignores_other_language(self):
        self.assertEqual(extract_mermaid_blocks("```python\nx\n```"), 0)

    def test_extract_unclosed_not_counted(self):
        self.assertEqual(extract_mermaid_blocks("```mermaid\nA\n"), 0)

    def test_extract_empty(self):
        self.assertEqual(extract_mermaid_blocks(""), 0)
        self.assertEqual(extract_mermaid_blocks(None), 0)


if __name__ == "__main__":
    unittest.main()