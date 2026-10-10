import unittest
import server


class TestLoginPagePlaceholder(unittest.TestCase):
    def test_failed_login_page_has_no_raw_placeholder(self):
        html = server._render_login_page("用户名或密码错误")
        self.assertNotIn("{next_field}", html)
        self.assertNotIn("{error}", html)

    def test_failed_login_page_shows_error_text(self):
        html = server._render_login_page("用户名或密码错误")
        self.assertIn("用户名或密码错误", html)


class TestBannerFString(unittest.TestCase):
    def test_no_raw_icon_literal_in_report_module_source(self):
        """report.py 不得再有落单的 {_icon(...)} 字面量（非 f-string）。"""
        import ast, pathlib
        src = pathlib.Path("report.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if '{_icon(' in node.value:
                    bad.append(node.lineno)
        self.assertEqual(bad, [], f"report.py 存在未插值的 {{_icon}} 字面量: 行 {bad}")


class TestConfigWarnBanner(unittest.TestCase):
    def test_no_raw_icon_literal_in_config_module_source(self):
        """config.py（及 B9-2 拆分出的 config_pages/）不得有落单的 {_icon(...)} 字面量。"""
        import ast, pathlib
        paths = [pathlib.Path("config.py")] + sorted(pathlib.Path("config_pages").glob("*.py"))
        bad = []
        for p in paths:
            tree = ast.parse(p.read_text(encoding="utf-8"))
            bad += [(str(p), n.lineno) for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and '{_icon(' in n.value]
        self.assertEqual(bad, [], f"存在未插值的 {{_icon}} 字面量: {bad}")


class TestDeleteConfirmJsEscape(unittest.TestCase):
    def test_js_str_escapes_single_quote_and_backslash(self):
        import render
        self.assertEqual(render._js_str("O'Brien"), r"O\'Brien")
        self.assertEqual(render._js_str("a\\b"), "a\\\\b")
        self.assertEqual(render._js_str("a\nb"), "a\\nb")

    def test_confirm_with_quote_name_is_js_safe(self):
        """传原文：产出必须是「HTML 属性解码后仍是合法 JS 字符串」。"""
        import html, re, render
        html_out = render.build_delete_form_html("/x/delete", "确定删除连接池 O'Brien？")
        m = re.search(r"onsubmit=\"return confirm\('(.*)'\)\"", html_out)
        self.assertIsNotNone(m, "未匹配到 onsubmit confirm")
        decoded = html.unescape(m.group(1))          # 浏览器解码 HTML 属性
        self.assertEqual(decoded, r"确定删除连接池 O\'Brien？")

    def test_confirm_shows_original_name_to_user(self):
        """最强断言：把生成的 JS 真的执行，看用户看到什么。"""
        import html, re, render
        html_out = render.build_delete_form_html("/x/delete", "确定删除 O'Brien？")
        m = re.search(r"onsubmit=\"return confirm\('(.*)'\)\"", html_out)
        decoded = html.unescape(m.group(1))
        code = "confirm('" + decoded + "')"
        shown = []
        ns = {"confirm": lambda msg: (shown.append(msg), True)[1]}
        exec(compile(code, "<t>", "exec"), ns)   # 编译不过即 SyntaxError → 测试失败
        self.assertEqual(shown, ["确定删除 O'Brien？"])

    def test_backslash_tail_name_is_safe(self):
        import html, re, render
        html_out = render.build_delete_form_html("/x/delete", "name\\")
        m = re.search(r"onsubmit=\"return confirm\('(.*)'\)\"", html_out)
        decoded = html.unescape(m.group(1))
        exec(compile("confirm('" + decoded + "')", "<t>", "exec"), {"confirm": lambda m: True})


class TestToggleConfirmJsEscape(unittest.TestCase):
    """第 8 处同类缺陷：API 端点「禁用」按钮的 confirm（render.py:4735）。

    该处不经 build_delete_form_html，独立拼 onsubmit，曾漏 _js_str，现已修。
    """

    def test_toggle_confirm_with_quote_name_is_js_safe(self):
        import html, re, render
        # 直接构造与 render.py:4735 相同的片段，验证转义契约
        for name in ["O'Brien 接口", "a\\", "普通接口"]:
            frag = (' onsubmit=\"return confirm(\'确定禁用 API 接口 '
                    f'{render._escape(render._js_str(name))}？\')\"')
            m = re.search(r"confirm\('(.*)'\)", frag)
            self.assertIsNotNone(m)
            decoded = html.unescape(m.group(1))
            shown = []
            ns = {"confirm": lambda msg: (shown.append(msg), True)[1]}
            # 编译不过即 SyntaxError → 测试失败
            exec(compile("confirm('" + decoded + "')", "<t>", "exec"), ns)
            self.assertEqual(shown, [f"确定禁用 API 接口 {name}？"])

    def test_no_unescaped_confirm_interpolation_in_render(self):
        """护栏：render.py 中所有把变量插进 confirm('...') 的地方都必须过 _js_str。"""
        import pathlib, re
        src = pathlib.Path("render.py").read_text(encoding="utf-8")
        bad = []
        for i, line in enumerate(src.splitlines(), 1):
            if "confirm(" in line and "onsubmit" in line and "{" in line:
                if "_js_str" not in line and "确定删除该 API Key" not in line:
                    bad.append(i)
        self.assertEqual(bad, [], f"render.py 存在未过 _js_str 的 confirm 插值: 行 {bad}")
