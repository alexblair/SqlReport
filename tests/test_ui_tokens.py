"""UI v2 视觉体系门禁（令牌 / 对比度 / 单一来源 / 新结构契约）。

背景（spec 2026-09-30-ui-v2-design）：
- 旧代码共享 CSS 里 49 种 hex、12 种字号、37 种 padding、269 处内联样式；
  「改了 N 次还是丑」的根因是全站没有统一尺度，且表现性样式散落在页面级
  补丁与内联 style 里，任何局调都会被别处覆盖。
- 本轮把视觉收成单一来源（render._BASE_CSS + render._COMMON_CSS），并新增
  代码面（深色）令牌——历史事故：<pre class="sql-debug code-block"> 命中
  「深底」与「深字」两条规则 → 正文 1.02:1 完全隐形（用户实测反馈）。

本文件把以下契约钉成测试，避免回归：
1. 必需令牌齐备（颜色 / 代码面 / 圆角 / 间距 / 字阶）；
2. 关键前景-背景组合对比度 ≥ 4.5:1（WCAG AA，程序实算，不钉 hex 字面量）；
3. 页面级 CSS 补丁与表现性内联样式不得回流（单一来源约束）；
4. 报表配置页新结构（分组卡 + 层级导轨 + 行卡片/卡片双形态）存在。
"""
from __future__ import annotations

import re
import unittest
from unittest.mock import patch

import render
import config
import report

from tests import BaseReportTest


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _contrast(fg: str, bg: str) -> float:
    """WCAG 相对亮度对比度。"""
    def lum(h):
        h = h.lstrip('#')
        parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [p / 12.92 if p <= 0.04045 else ((p + 0.055) / 1.055) ** 2.4 for p in parts]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _token(css: str, name: str) -> str:
    m = re.search(re.escape(name) + r':\s*(#[0-9a-fA-F]{6})', css)
    if not m:
        raise AssertionError(f"缺少令牌 {name}")
    return m.group(1)


ALL_CSS = render._BASE_CSS + render._COMMON_CSS


def _live_css() -> str:
    """调用时取值的公共 CSS（供需要做「变异证明了」的门禁使用）。

    `ALL_CSS` 是模块导入时的快照，无法反映内存变异；新门禁若要进
    `tests/bug_hunt/gate_redproof.py` 的 RED-GREEN 自证，必须走本函数。
    """
    return render._BASE_CSS + render._COMMON_CSS


class TestTokensPresent(unittest.TestCase):
    """必需令牌齐备（唯一取值来源）。"""

    REQUIRED = [
        # 中性 / 文字
        "--bg-app", "--bg-surface", "--bg-subtle", "--bg-sunken",
        "--line", "--line-soft", "--line-strong",
        "--ink-1", "--ink-2", "--ink-3", "--ink-4",
        # 主色
        "--accent", "--accent-hover", "--accent-ink", "--accent-soft", "--accent-line",
        # 语义
        "--ok", "--ok-ink", "--ok-soft", "--warn", "--warn-ink", "--warn-soft",
        "--danger", "--danger-ink", "--danger-soft", "--info", "--info-ink", "--info-soft",
        # 代码面
        "--code-bg", "--code-ink", "--code-dim", "--code-kw", "--code-fn",
        "--code-str", "--code-num", "--code-comment",
        # 侧栏
        "--sidebar-bg", "--sidebar-ink", "--sidebar-ink-active",
    ]

    def test_all_tokens_defined(self):
        for name in self.REQUIRED:
            with self.subTest(token=name):
                _token(ALL_CSS, name)

    def test_scale_tokens_defined(self):
        for name in ("--fs-12", "--fs-13", "--fs-14", "--fs-22",
                     "--sp-2", "--sp-4", "--sp-6",
                     "--r-sm", "--r-md", "--r-lg",
                     "--sh-1", "--sh-2", "--sh-3"):
            with self.subTest(token=name):
                self.assertRegex(ALL_CSS, re.escape(name) + r':\s*\S+')


class TestContrastGate(unittest.TestCase):
    """关键前景/背景组合必须达 WCAG AA（正文 ≥4.5:1）。"""

    def test_text_on_surfaces(self):
        surface = _token(ALL_CSS, "--bg-surface")
        app = _token(ALL_CSS, "--bg-app")
        for tok, bg in (("--ink-1", surface), ("--ink-2", surface),
                        ("--ink-3", surface), ("--ink-1", app)):
            with self.subTest(token=tok, bg=bg):
                self.assertGreaterEqual(_contrast(_token(ALL_CSS, tok), bg), 4.5)

    def test_accent_pairs(self):
        surface = _token(ALL_CSS, "--bg-surface")
        accent = _token(ALL_CSS, "--accent")
        self.assertGreaterEqual(_contrast(_token(ALL_CSS, "--accent-ink"), surface), 4.5)
        self.assertGreaterEqual(
            _contrast(_token(ALL_CSS, "--accent-ink"), _token(ALL_CSS, "--accent-soft")), 4.5)
        # 白字压主色（主按钮）
        self.assertGreaterEqual(_contrast("#ffffff", accent), 4.5)

    def test_semantic_inks(self):
        surface = _token(ALL_CSS, "--bg-surface")
        for tok, soft in (("--ok-ink", "--ok-soft"), ("--warn-ink", "--warn-soft"),
                          ("--danger-ink", "--danger-soft"), ("--info-ink", "--info-soft")):
            with self.subTest(token=tok):
                self.assertGreaterEqual(_contrast(_token(ALL_CSS, tok), surface), 4.5)
                self.assertGreaterEqual(
                    _contrast(_token(ALL_CSS, tok), _token(ALL_CSS, soft)), 4.5)

    def test_code_surface_readable(self):
        """代码面：正文与全部词法色都必须清晰（历史事故 1.02:1）。"""
        bg = _token(ALL_CSS, "--code-bg")
        for tok in ("--code-ink", "--code-dim", "--code-kw", "--code-fn",
                    "--code-str", "--code-num", "--code-comment"):
            with self.subTest(token=tok):
                self.assertGreaterEqual(_contrast(_token(ALL_CSS, tok), bg), 4.5)

    def test_code_surface_pairs_bg_and_color(self):
        """底色与文字色必须成对声明（禁止再分属两个 class 各写一半）。"""
        for m in re.finditer(r'([^{}]*)\{([^{}]*)\}', ALL_CSS):
            sel, body = m.group(1), m.group(2)
            if "var(--code-bg)" in body and "color" in sel + body:
                if re.search(r'\bcolor\s*:', body):
                    self.assertRegex(body, r'\bcolor\s*:\s*var\(--code-ink\)|color\s*:\s*inherit')
                    break
        else:
            self.fail("未找到代码面规则（background:var(--code-bg)）")


class TestOverlayDefaultsHidden(unittest.TestCase):
    """加载遮罩默认必须隐藏（历史回归：基础规则里 display:none 被同规则的 display:flex 覆盖）。

    用户实测反馈：登录后整页被「查询中…请稍候」盖住，什么都点不了。
    """

    def _block(self, sel: str) -> str:
        m = re.search(re.escape(sel) + r'\s*\{([^}]*)\}', ALL_CSS)
        self.assertIsNotNone(m, f"未找到规则 {sel}")
        return m.group(1)

    def test_base_rule_hides_overlay(self):
        decls = re.findall(r'display\s*:\s*[a-z-]+', self._block('.query-loading-overlay'))
        self.assertTrue(decls, "遮罩基础规则应声明 display")
        self.assertEqual('display:none', decls[-1].replace(' ', ''),
                         "基础规则的最后一条 display 必须是 none（同规则内后面的 display 会覆盖前面的）")

    def test_show_rule_reveals_overlay(self):
        self.assertRegex(ALL_CSS, r'\.query-loading-overlay\.show\s*\{\s*display:\s*flex')

    def test_other_js_toggled_display_classes_have_hidden_default(self):
        """JS 用 class 切换显隐的组件，基础态必须是隐藏。"""
        for sel, show in ((r'\.side-panel', r'\.side-panel\.open'),
                          (r'\.modal', r'\.modal\.open')):
            with self.subTest(sel=sel):
                self.assertRegex(ALL_CSS, sel + r'\s*\{[^}]*display\s*:\s*none')
                self.assertRegex(ALL_CSS, show + r'\s*\{[^}]*display\s*:\s*flex')


class TestJsToggledClassesHaveStyles(unittest.TestCase):
    """JS 运行时切换的 class 必须在公共 CSS 里有对应规则。

    历史事故（两起同源）：
    - 加载遮罩：CSS 只写 `.query-loading-overlay` 基础态却漏了「隐藏」，整页被盖住；
    - 字段设置/排序设置抽屉：确认稿用 `.open`，生产 JS 加的是 `.on`，
      结果点按钮毫无反应（用户实测反馈「功能丢失」）。
    因此这里直接从生产 JS 源码里提取 classList 操作的字面量，逐个回查 CSS。
    """

    #: 无视觉语义的纯状态标记（由更高层规则或业务逻辑消费），不要求独立规则
    ALLOW = {"active", "hidden", "sb-rail", "sb-wide", "on", "open", "show",
             "picked", "collapsed", "row-highlight", "fading-out", "loading",
             "filter-input-touch", "nofilter", "contains"}

    def _js_sources(self):
        out = []
        for mod in (render, report, config):
            out.append(open(mod.__file__, encoding="utf-8").read())
        try:
            import filter_help
            out.append(open(filter_help.__file__, encoding="utf-8").read())
        except Exception:
            pass
        return "\n".join(out)

    def test_every_toggled_class_has_rule_or_is_aliased(self):
        src = self._js_sources()
        changed = set(re.findall(r"classList\.(?:add|remove|toggle)\(\s*['\"]([\w-]+)['\"]", src))
        changed |= set(re.findall(r"classList\.(?:add|remove|toggle)\(\s*[A-Za-z_$][\w$]*\s*\?\s*['\"]([\w-]+)['\"]", src))
        self.assertTrue(changed, "未能从 JS 中提取任何 classList 字面量（正则失配？）")
        missing = []
        for cls in sorted(changed):
            if cls in self.ALLOW:
                continue
            if not re.search(r'[.\s,]' + re.escape(cls) + r'(?![\w-])', ALL_CSS):
                missing.append(cls)
        self.assertEqual([], missing, f"JS 会切换但这些 class 在公共 CSS 中无规则：{missing}")

    def test_modal_supports_sibling_sections(self):
        """生产导出对话框是 head/body/foot 三个并列兄弟（无包装盒）。

        若按「遮罩 + 单个 .modal-box」实现，三段会被 flex 排成一行（宽度各 ~469px 并排），
        实测过这个错法。故断言：.modal 纵向排列 + 三段同宽同左缘。
        """
        m = re.search(r'(?<![\w>.-])\.modal\s*\{([^}]*)\}', ALL_CSS)
        self.assertIsNotNone(m, "缺少 .modal 基础规则")
        # 纵向排列的声明可以在任意一条 .modal 规则里
        modal_rules = "\n".join(x.group(1) for x in re.finditer(r'(?<![\w>.-])\.modal\s*\{([^}]*)\}', ALL_CSS))
        self.assertRegex(modal_rules, r'flex-direction:\s*column')
        for part in ('modal-head', 'modal-body', 'modal-foot'):
            with self.subTest(part=part):
                self.assertRegex(ALL_CSS, r'\.modal\s*>\s*\.' + part + r'[^{]*\{[^}]*max-width')

    def test_state_aliases_cover_production_names(self):
        """生产 JS 加 `.on`；` .open`/`.show` 是确认稿别名，两者都必须可用。"""
        for base in ('.side-panel', '.modal'):
            with self.subTest(base=base):
                self.assertRegex(ALL_CSS, re.escape(base) + r'\.on\s*,\s*' + re.escape(base) + r'\.open\s*\{\s*display:\s*flex')
        self.assertRegex(ALL_CSS, r'\.backdrop\.on\s*,\s*\.backdrop\.show\s*\{\s*display:\s*block')
class TestRevealClassContracts(unittest.TestCase):
    """展开/收起面板的「显示规则」必须认生产 JS 实际切换的类名（元素级契约）。

    历史事故（ad109be：UI v2 落公共 CSS 时只抄了确认稿类名）：确认稿写
    `.api-row.open .api-more`，生产 `_COMMON_JS` 却切 `.api-more` 上的 `.on`
    —— 两边各说各话：按钮文案照切、面板纹丝不动（用户实测反馈
    「/config/api-endpoints 展开 收起 功能失效」）。同一提交还删掉了
    `.tree .kids{display:none}` / `.tree .kids.on{display:block}`，分类树折叠同款失效。
    `.side-panel.on,.side-panel.open` 即此事故的既有修法：**CSS 必须认 JS 的类**。
    """

    @staticmethod
    def _all_css() -> str:
        """当前公共 CSS；**调用时取值**——门禁自证脚本会临时变异 render._COMMON_CSS 验证本门禁能拦住回归。"""
        return render._BASE_CSS + render._COMMON_CSS

    @staticmethod
    def _css_rules() -> list:
        """拆 CSS 为 [(选择器列表, 声明块)]（先剥注释，避免注释里的花括号串场）。"""
        css = re.sub(r'/\*.*?\*/', '', TestRevealClassContracts._all_css(), flags=re.S)
        return [([s.strip() for s in sel.split(',') if s.strip()], decl)
                for sel, decl in re.findall(r'([^{}]+)\{([^{}]*)\}', css)]

    def _display_selectors(self, base: str, cls: str) -> list:
        """返回同时含 base 类与状态类、且声明了 display 的选择器。"""
        out = []
        for sels, decl in self._css_rules():
            if 'display' not in decl:
                continue
            for s in sels:
                if (re.search(r'\.' + re.escape(base) + r'(?![\w-])', s)
                        and re.search(r'\.' + re.escape(cls) + r'(?![\w-])', s)):
                    out.append(s)
        return out

    def test_queried_element_toggled_class_has_element_level_display_rule(self):
        """JS「querySelector(某类) → 同一变量 classList 切换类」必须有元素级 display 规则。

        直接从生产 JS 源码提取「元素选择器 + 切换的类」，回查公共 CSS：
        只要 CSS 按确认稿的类名写、JS 按旧类名切，本条必红（.api-more 即历史实例）。
        """
        src = "\n".join(open(mod.__file__, encoding="utf-8").read()
                        for mod in (render, report, config))
        assign = dict(re.findall(
            r"var\s+(\w+)\s*=\s*[^;\n]*?querySelector\(\s*['\"]([^'\"]+)['\"]\s*\)", src))
        pairs = []
        for var, sel in assign.items():
            if not re.fullmatch(r'\.[\w-]+', sel):
                continue      # 多选择器 / 非单一类选择器无法与 CSS 选择器对齐，跳过
            base = sel[1:]
            for cls in re.findall(
                    re.escape(var) + r"\.classList\.(?:add|remove|toggle)\(\s*['\"](\w[\w-]*)['\"]",
                    src):
                pairs.append((base, cls))
        self.assertIn(('api-more', 'on'), pairs,
                      f"契约提取失配：未从 JS 提取到 .api-more/.on（实际 {sorted(set(pairs))}）")
        missing = [f".{base} + .{cls}" for base, cls in pairs
                   if not self._display_selectors(base, cls)]
        self.assertEqual([], missing,
                         f"JS 会切换这些元素上的类，但公共 CSS 无元素级 display 规则：{missing}")

    def test_api_more_hidden_by_default_and_revealed_by_js_class(self):
        """API 行展开区：默认 display:none，展开规则必须含 `.api-more.on`（JS 实际切法）。"""
        self.assertTrue(re.search(r'more\.classList\.toggle\("on"\)', render._COMMON_JS),
                        "apiToggleMore 不再切 .api-more 的 .on —— JS 契约变了，本门禁需同步")
        base = re.search(r'\.api-more\s*\{([^}]*)\}', self._all_css())
        self.assertIsNotNone(base, "缺少 .api-more 基础规则")
        self.assertIn('display:none', base.group(1).replace(' ', ''))
        self.assertIn('.api-more.on', self._display_selectors('api-more', 'on'))

    def test_tree_kids_hidden_by_default_and_revealed_by_js_class(self):
        """分类树子节点容器：默认隐藏 + `.tree .kids.on` 展开（两张树都切这个类）。"""
        self.assertTrue(re.search(r'kids\.classList\.toggle\("on"\)', render._COMMON_JS),
                        "toggleCatNode 不再切 .kids 的 .on —— JS 契约变了，本门禁需同步")
        self.assertTrue(re.search(r'\.tree\s+\.kids\s*\{[^}]*display\s*:\s*none', self._all_css()),
                        ".tree .kids 缺 display:none 基础态（子分类永不隐藏）")
        self.assertTrue(re.search(r'\.tree\s+\.kids\.on\s*\{[^}]*display\s*:\s*block', self._all_css()),
                        ".tree .kids.on 缺 display:block 展开规则（分类树折叠失效）")

class TestInlineJsSyntax(unittest.TestCase):
    """内联 JS 必须语法合法（整块脚本一个语法错误 → 该页所有函数都不存在）。

    实测事故：在 JS 块注释里写了 `f_*/op_*`，其中的 `*/` 提前结束注释，
    导致报表页整块 footer 脚本报错、`applyFieldSettings`/`applySortSettings`
    全部 undefined —— 表现就是「按钮点了没反应」，而控制台里没有 Log 级错误。
    这里用 node --check 做真语法校验（无 node 时给出明确的 skip 原因）。
    """

    JS_CONSTANTS = ("_FOOTER_GLUE", "_COMMON_JS")

    def _js_sources(self):
        import report as report_mod
        out = {"render._COMMON_JS": render._COMMON_JS, "report._FOOTER_GLUE": report_mod._FOOTER_GLUE}
        # 合并成一份整体校验（同一页面里它们会一起执行）
        return out

    def test_js_comment_hazard_documented(self):
        """仅记录危害（朴素计数会误报，权威判定交给下面的 node --check）。

        反例：块注释里写 `f_*/op_*`，其中 `*/` 提前结束注释 → 整块脚本语法错误。
        不要用「/* 与 */ 计数相等」来判定——注释正文里出现 `/*` 字符串会造成误报
        （本轮实测：_COMMON_JS 合法但计数不等）。
        """
        self.assertTrue(self._js_sources(), "应至少有一份内联 JS 需要校验")

    def test_node_syntax_check(self):
        import shutil, subprocess, tempfile, os
        node = shutil.which("node")
        if not node:
            self.skipTest("环境无 node，跳过 JS 语法校验（CI 建议安装 node）")
        for name, js in self._js_sources().items():
            if not js.strip():
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
                fh.write(js)
                path = fh.name
            try:
                r = subprocess.run([node, "--check", path], capture_output=True, text=True)
                self.assertEqual(0, r.returncode,
                                 f"{name} 语法错误：\n{r.stderr[:600]}")
            finally:
                os.unlink(path)


class TestNoRefreshSwapReinit(unittest.TestCase):
    """无刷新换页（navigateTo）必须只有一份实现，且换页后要重初始化。

    实测事故（用户步骤：隐藏列→应用→还原→应用→再排序）：报表页的 navigateTo 自己复制了
    一份 innerHTML 替换逻辑，既不重跑 <main> 内的内联脚本，也不重新绑定 addEventListener
    的行为（字段/排序列表的拖拽），于是「应用过一次之后拖拽排序就报废」。
    """

    def test_single_swap_implementation(self):
        import report as report_mod
        glue = report_mod._FOOTER_GLUE
        # 报表页不得再自行实现 innerHTML 替换：统一委托公共 _swapMain
        self.assertNotIn("oldMain.innerHTML", glue,
                         "报表页不应重复实现 <main> 替换，应委托公共 _swapMain")
        self.assertIn("_swapMain", glue, "navigateTo 应委托 _swapMain")

    def test_reinit_runs_scripts_and_page_hooks(self):
        js = render._COMMON_JS
        self.assertIn("function _reinitAfterSwap", js)
        self.assertRegex(js, r"replaceChild\(fresh, old\)", "换页后需重建 <script> 让内联脚本重放")
        self.assertIn("initPage", js)
        self.assertIn("initReportPage", js)

    def test_onready_available_before_inline_scripts(self):
        """onReady 必须在页面内联脚本之前定义（外链 common.js 是 defer，晚于 body 内联脚本）。"""
        self.assertIn("window.onReady", render._SIDEBAR_BOOTSTRAP_JS,
                      "onReady 需在头部内联引导脚本中定义")

    def test_drag_binding_is_idempotent(self):
        import report as report_mod
        glue = report_mod._FOOTER_GLUE
        for fn in ("initDragHandlers", "initSortDragHandlers"):
            self.assertIn(fn, glue)
        self.assertGreaterEqual(glue.count("dataset.dragBound"), 2,
                                "两个拖拽绑定都要有幂等标记，避免换页后重复叠加监听")

    def test_sort_placeholder_managed(self):
        """加排序项要移除「暂无排序」占位块，清空要恢复；序号按排序项数量重排。"""
        import report as report_mod
        glue = report_mod._FOOTER_GLUE
        for probe in ("function sortItemEls", "function syncSortEmptyState", "function renumberSortItems"):
            self.assertIn(probe, glue)
        self.assertIn("sort-empty", render._COMMON_CSS + render._BASE_CSS + glue,
                      "占位块应有 class 便于查找/移除")


class TestHtmlFreshness(unittest.TestCase):
    """HTML 响应必须禁缓存。

    实测教训：修复已经上线，但用户标签页仍在跑旧的内联 JS（页面 HTML 无 Cache-Control），
    表现为「你明明修了，我这儿还是坏的」。静态资产走 /static/vendor 内容哈希 + immutable，
    不受影响；动态 HTML 不能缓存。
    """

    def test_send_html_sets_no_store(self):
        import inspect
        import server as server_mod
        handler = None
        for _, obj in inspect.getmembers(server_mod, inspect.isclass):
            if hasattr(obj, "_send_html"):
                handler = obj
                break
        self.assertIsNotNone(handler, "未找到带 _send_html 的 Handler 类")
        src = inspect.getsource(handler._send_html)
        self.assertIn("Cache-Control", src, "_send_html 应显式设置 Cache-Control")
        self.assertIn("no-store", src, "HTML 必须禁缓存（no-store）")


class TestSingleSourcePolicy(unittest.TestCase):
    """单一来源：页面级 CSS 补丁必须为空；表现性内联样式不得回流。"""

    def test_page_level_css_patches_removed(self):
        self.assertEqual("", report._CSS.strip() if hasattr(report, "_CSS") else "")
        self.assertEqual("", config._CONFIG_EXTRA_CSS.strip())
        self.assertEqual("", config._REPORTS_EXTRA_CSS.strip())

    def test_no_presentational_inline_styles_in_reports_page(self):
        """渲染产物里不得再出现表现性内联样式（颜色/背景/边框/字号/内外边距/尺寸）。"""
        conn = None
        try:
            from tests.test_base import make_config_db, init_test_db
            import db as db_mod
            conn = make_config_db()
            with patch("db._get_engine", return_value="sqlite3"):
                init_test_db(conn)
                db_mod.add_pool(conn, "池A", "h", 3306, "u", "p", "d")
                body = config.render_reports_page(conn)
        finally:
            if conn is not None:
                conn.close()
        bad = re.findall(
            r'style="[^"]*\b(color|background|border|border-radius|font-size|padding|margin|'
            r'width|height|box-shadow)\s*:', body)
        self.assertEqual([], bad, f"表现性内联样式回流：{bad[:5]}")


class TestReportsPageStructure(unittest.TestCase):
    """报表配置页方案 A 结构契约（旧断言对此零覆盖，故在此补齐）。"""

    @classmethod
    def setUpClass(cls):
        from tests.test_base import make_config_db, init_test_db
        import db as db_mod
        cls.conn = make_config_db()
        with patch("db._get_engine", return_value="sqlite3"):
            init_test_db(cls.conn)
            db_mod.add_pool(cls.conn, "池A", "h", 3306, "u", "p", "d")
            db_mod.add_category(cls.conn, "父分类")
            cls.body = config.render_reports_page(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_group_card_and_rail(self):
        self.assertRegex(self.body, r'class="[^"]*\bcat-block\b')
        self.assertRegex(self.body, r'class="[^"]*\bcat-head\b')
        self.assertRegex(self.body, r'class="[^"]*\bcat-depth-dot\b')

    def test_dual_view_forms_present(self):
        """列表=行卡片、卡片=网格，两形态同数据各渲一份（.view-list/.view-card 语义不变）。"""
        self.assertRegex(self.body, r'class="[^"]*\bview-list\b')
        self.assertRegex(self.body, r'class="[^"]*\bview-card\b')
        self.assertRegex(self.body, r'class="[^"]*\brpt-grid\b')

    def test_all_css_covers_new_components(self):
        for cls in ("cat-block", "cat-head", "cat-children", "cat-depth-dot",
                    "rpt-row", "rpt-main", "rpt-line1", "rpt-ops", "cfg-chip",
                    "cat-empty", "table-fixed"):
            with self.subTest(cls=cls):
                self.assertRegex(ALL_CSS, r'\.' + re.escape(cls) + r'(?![\w-])')

# ---------------------------------------------------------------------------
# 失败模式门禁（2026-09-30 复盘固化）
#
# 下面每一条都对应本轮真实发生、且已经让用户看到的缺陷。原则：
# **能机械检测的绝不写进口头约定**（约定只留给判断类问题，见 knowledge/06 卷）。
# ---------------------------------------------------------------------------


class TestSqlEditorScrollContract(unittest.TestCase):
    """② SQL 编辑框的滚动契约（2026-10-09 用户实测反馈「缺少文本滚动条」）。

    事故：`<textarea class="sql-textarea sql-editor">` 同时命中两条规则——
    `.sql-editor` 是给「容器」写的（圆角裁切 + 边框），里面带 `overflow:hidden`；
    它落在 textarea 自身后，计算样式变成 `overflow:hidden`，滚动条消失、
    超出可视区的 SQL 被裁掉。无头 Chrome 实测（60 行 SQL）：

        overflowY=hidden  clientHeight=318  scrollHeight=1284  scrollbarGutter=0

    对照：同页只带 `.sql-textarea` 的 memo/result_names → `overflowY=auto`、gutter=10px。
    契约：编辑框自己声明 `overflow:auto`；任何命中编辑框类的规则都不得再声明 hidden。
    """

    EDITOR_CLASSES = ("sql-textarea", "sql-editor")

    @staticmethod
    def _rules(css):
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css, re.S):
            sel = m.group(1).strip()
            if not sel or sel.startswith('@'):
                continue
            yield sel, m.group(2)

    def test_sql_textarea_declares_own_overflow(self):
        """`.sql-textarea` 必须显式 `overflow:auto`（不靠 UA 默认，也不被别的类覆盖）。"""
        bodies = [body for sel, body in self._rules(render._COMMON_CSS)
                  if sel == '.sql-textarea']
        self.assertTrue(bodies, "缺少 .sql-textarea 规则")
        self.assertRegex(bodies[-1], r'overflow\s*:\s*auto',
                         ".sql-textarea 未声明 overflow:auto → 编辑框没有滚动条")

    def test_no_rule_hides_editor_overflow(self):
        """命中编辑框类（.sql-textarea/.sql-editor）的规则不得声明 overflow(-x|-y):hidden。"""
        offenders = []
        for sel, body in self._rules(render._COMMON_CSS):
            hits = [s.strip() for s in sel.split(',')
                    if any('.' + cls in s for cls in self.EDITOR_CLASSES)]
            if not hits:
                continue
            if re.search(r'(?<!-)overflow(?:-x|-y)?\s*:\s*hidden', body):
                offenders.append(f"{','.join(hits)} → {body.strip()[:60]}")
        self.assertEqual([], offenders,
                         "编辑框被 overflow:hidden 裁掉（滚动条消失）：" + "; ".join(offenders))


class TestNoDuplicateDeclarations(unittest.TestCase):
    """同一条规则内不得重复声明同一属性（后者静默覆盖前者）。

    实测事故：`.query-loading-overlay` 基础规则里先写了 `display:none`（想默认隐藏），
    同一规则后面还留着一条 `display:flex` → 覆盖生效，登录后整页被「查询中…」遮住。
    这类错误 CSS 不报错、不波及其它规则，人工评审几乎必漏，只能靠机器查。
    """

    def test_no_duplicate_property_in_one_rule(self):
        for sheet, css in (("_BASE_CSS", render._BASE_CSS),
                           ("_COMMON_CSS", render._COMMON_CSS)):
            for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css, re.S):
                sel = m.group(1).strip()
                if not sel or sel.startswith('@'):
                    continue
                props = [p.lower() for p in
                         re.findall(r'(?:^|;)\s*([-a-zA-Z]+)\s*:', m.group(2))]
                dup = sorted({p for p in props if props.count(p) > 1})
                self.assertEqual([], dup,
                                 f"{sheet} 规则 `{sel[:60]}` 内重复声明：{dup}（后者会静默覆盖前者）")


class TestPageInitRegistration(unittest.TestCase):
    """页面级初始化必须能在无刷新换页后重放。

    实测事故（用户步骤：隐藏列→应用→还原→应用→再排序）：
    - 换页只做 `innerHTML` 替换 → 重建出来的 <script> 不执行、初始化不重跑，
      靠 addEventListener 绑定的交互（字段/排序拖拽）全部静默失效；
    - `onReady` 一度只定义在外链 common.js（defer，晚于 body 内联脚本）→ ReferenceError；
    - 个别 init 函数自己另绑一条 DOMContentLoaded，首次加载跑两遍、换页后一次不跑。
    规则：
      1. 每个 init* 函数都必须被 initPage() / initReportPage() 调用（换页重放靠它）；
      2. 内联脚本里绑 DOMContentLoaded 时必须带 readyState 守卫（onReady 形式），
         或属于全局唯一注册点（initPage / initReportPage 本身，二者换页时被显式调用）。
    """

    ALLOWED = (
        re.compile(r"readyState\s*===?\s*['\"]loading['\"]"),
        re.compile(r"addEventListener\(\s*['\"]DOMContentLoaded['\"]\s*,\s*initPage\s*\)"),
        re.compile(r"addEventListener\(\s*['\"]DOMContentLoaded['\"]\s*,\s*initReportPage\s*\)"),
    )

    def test_every_init_function_is_reachable_after_swap(self):
        import report as report_mod
        for label, js, entry in (("_COMMON_JS", render._COMMON_JS, "initPage"),
                                 ("report._FOOTER_GLUE", report_mod._FOOTER_GLUE, "initReportPage")):
            defined = set(re.findall(r'function\s+(init[A-Za-z0-9_]*)\s*\(', js)) - {entry}
            self.assertTrue(defined, f"{label} 未提取到任何 init* 函数（正则失配？）")
            m = re.search(r'function\s+' + entry + r'\(\)\s*\{(.*?)\n\s*\}', js, re.S)
            self.assertIsNotNone(m, f"{label} 缺少 {entry}()")
            called = set(re.findall(r'(init[A-Za-z0-9_]*)\s*\(', m.group(1)))
            missing = sorted(defined - called)
            self.assertEqual([], missing,
                             f"{label} 中这些初始化不会被 {entry}() 调用 → 换页后不重放：{missing}")

    def test_dom_content_loaded_bindings_are_replay_safe(self):
        for mod in (render, report, config):
            with open(mod.__file__, encoding="utf-8") as fh:
                src = fh.read()
            for m in re.finditer(r"addEventListener\(\s*['\"]DOMContentLoaded['\"]", src):
                window = src[max(0, m.start() - 220):m.end() + 140]
                if any(p.search(window) for p in self.ALLOWED):
                    continue
                line = src[:m.start()].count("\n") + 1
                self.fail(f"{mod.__name__}.py:{line} 无条件绑定 DOMContentLoaded："
                          "换页重建 <script> 后不会执行，请改用 onReady(fn) 或交给 initPage/initReportPage")

class TestMermaidTabRenderContract(unittest.TestCase):
    """备注/接口页卡初始 display:none：mermaid 不得在隐藏容器里自动渲染。

    2026-10-09 用户实测（报表 /report?id=42 备注页卡两张流程图全空，只剩空框）：
    `startOnLoad:true` 在 window load 时把 display:none 页卡里的
    `<pre class="mermaid">` 一起渲染了——隐藏容器里量测全 0，mermaid 退化成 16×16
    空图（viewBox `-8 -8 16 16`）并打上 `data-processed`；之后 `mermaid.run` 对已打标
    记的节点直接 continue，所以切到备注页卡也不会重画 → 永远空框。
    契约：① 初始化必须 startOnLoad:false；② 页卡可见时（gotoTab / initReportPage）
    必须渲染尚未处理的 mermaid 节点。两条均可内存变异（gate_redproof）。
    """

    def test_mermaid_not_autostarted_for_hidden_tabs(self):
        init_js = report._MERMAID_INIT_JS
        self.assertIn("startOnLoad: false", init_js,
                      "报表页 mermaid 未显式关闭自动渲染：备注/接口页卡初始 display:none，"
                      "隐藏容器会渲染成 16×16 空图并打 data-processed，切页后不再重画")
        self.assertNotIn("startOnLoad: true", init_js)

    def test_visible_tab_renders_mermaid(self):
        glue = report._FOOTER_GLUE
        self.assertIn("function renderTabMermaid(", glue,
                      "_FOOTER_GLUE 缺少 renderTabMermaid：页卡可见后无渲染入口")
        goto = re.search(r"function gotoTab\(key\)\s*\{(.*?)\n\}", glue, re.S)
        init = re.search(r"function initReportPage\(\)\s*\{(.*?)\n\s*\}", glue, re.S)
        self.assertIsNotNone(goto, "_FOOTER_GLUE 缺少 gotoTab()")
        self.assertIsNotNone(init, "_FOOTER_GLUE 缺少 initReportPage()")
        self.assertIn("renderTabMermaid(", goto.group(1),
                      "gotoTab 未渲染新可见页卡的 mermaid → 备注页卡仍会空白")
        self.assertIn("renderTabMermaid(", init.group(1),
                      "initReportPage 未渲染当前可见页卡 → 换页/首屏重放后不渲染")


class TestFormControlNameUniqueness(BaseReportTest):
    """同一页面内，同名控件不得混用类型（镜像控件不得带 name）。

    实测事故：导出对话框的隐藏 `<select id="export-format-select">` 与格式单选共用
    `name="format"` → 提交时同名参数重复，靠服务端「取第一个」侥幸正确。
    仅允许两种协议性同名：hidden+checkbox（0/1 协议）、hidden+select（默认值+覆盖）。
    """

    OK_PAIRS = (frozenset({"hidden", "checkbox"}), frozenset({"hidden", "select"}))

    def setUp(self):
        super().setUp()
        self.mock_pool = {"host": "dbhost", "port": 3306,
                          "user": "user", "password": "pass", "database": "mydb"}

    def _report_page(self):
        with patch("report.execute_report") as mock_exec:
            mock_exec.return_value = report.ReportResult(
                columns=["id"], rows=[(1,)], total=1, page=1, page_size=10)
            code, body, _ = report.handle_request(
                self.conn, "GET", "/report", f"id={self.report_id}",
                pool_override=self.mock_pool)
        return code, body


    def test_report_page_controls(self):
        code, body = self._report_page()
        conn = self.conn
        self.assertEqual(200, code)
        kinds = {}
        for m in re.finditer(r'<(input|select|textarea)\b[^>]*>', body, re.I):
            tag = m.group(0)
            nm = re.search(r'\bname="([^"]*)"', tag)
            if not nm:
                continue
            kind = m.group(1).lower()
            if kind == "input":
                t = re.search(r'\btype="([^"]*)"', tag)
                kind = t.group(1).lower() if t else "text"
            kinds.setdefault(nm.group(1), set()).add(kind)
        self.assertTrue(kinds, "未从报表页提取到任何具名控件（正则失配？）")
        bad = {n: sorted(ks) for n, ks in kinds.items()
               if len(ks) > 1 and frozenset(ks) not in self.OK_PAIRS}
        self.assertEqual({}, bad, f"同名控件混用类型（提交会重复/错乱）：{bad}")


class TestFocusDoesNotBreakCodeSurface(unittest.TestCase):
    """BUG-1 门禁：通用 `:focus` 规则不得把「深色代码面」翻成白底。

    实测事故（用户反馈）：报表编辑页「规则 → 当前规则」点击文本框后底色变白，
    而文字仍是浅色 --code-ink(#e2e6ef) → 14.88:1 掉到 1.25:1，完全无法辨认。

    根因：`input:focus,select:focus,textarea:focus{...;background:var(--bg-surface)}`
    特异性 (0,1,1) 高于 `.code-textarea{background:var(--code-bg)}` (0,1,0)，
    聚焦时后者被覆盖。同类风险组件：凡「深色令牌做底」且可能被聚焦的表单控件
    （.code-textarea / .sql-textarea / .sql-editor / 代码块 textarea）。

    本门禁按「解析 CSS 规则 + 实算对比度」判定，不钉具体类名，新组件自动纳入。
    """

    @staticmethod
    def _rules(css):
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css, re.S):
            sel = m.group(1).strip()
            if not sel or sel.startswith('@'):
                continue
            yield sel, m.group(2)

    def _focus_rules_setting_surface_bg(self):
        """找出所有「命中 :focus 且把 background 设为亮色表面令牌」的规则。"""
        hits = []
        for sel, body in self._rules(_live_css()):
            if ':focus' not in sel:
                continue
            if re.search(r'background\s*:\s*var\(--bg-(surface|app|subtle)\)', body):
                hits.append((sel, body))
        return hits

    def test_focus_rule_must_not_override_dark_surface(self):
        """聚焦时把底色写成亮色表面的规则，必须有配套的「文字色改正」或「深面豁免规则」。

        否则任何「深底浅字」的控件（代码面）一旦聚焦就会变成白底浅字。
        两种合法做法（二者必居其一）：
          a) 同一规则内同时声明 `color`（改底就改字，成对声明）；
          b) 另有一条更高特异性的规则，把深面控件的聚焦底色回写成 --code-bg。
        历史事故即是两者都没做。
        """
        offenders = []
        for sel, body in self._focus_rules_setting_surface_bg():
            # (a) 成对声明：改底就改字
            if re.search(r'(?:^|;)\s*color\s*:', body):
                continue
            # (b) 深面豁免：存在更高特异性的 :focus 规则把底回写成代码底
            if re.search(r':focus\s*\{[^}]*background\s*:\s*var\(--code-bg\)', _live_css()):
                continue
            offenders.append(sel)
        self.assertEqual(
            [], offenders,
            '聚焦规则把底色改成亮色表面，既无配对文字色也无深面豁免，'
            '深色代码面会变成白底浅字：' + '; '.join(offenders))

    def test_dark_surface_components_keep_readable_contrast_on_focus(self):
        """凡以 --code-bg 为底的 textarea 类组件，聚焦态实际生效的底色仍是 --code-bg。

        做法：对每个「声明 background:var(--code-bg)」的选择器类名，模拟一轮
        聚焦（把通用 :focus 规则也算进来，按特异性后者胜），断言胜出的底色是
        --code-bg，且 --code-ink 在它上面的对比度 ≥ 4.5:1。
        """
        # 仅考察「真正会被聚焦的表单控件」：代码面族里 <pre>/<code> 不是表单控件，
        # 通用 input/textarea:focus 规则碰不到它们，纳入会造成假阳性。
        code_bg = _token(_live_css(), '--code-bg')
        code_ink = _token(_live_css(), '--code-ink')

        # 收集「以 --code-bg 为底」的类选择器（单类名，便于特异性比较）
        dark_classes = set()
        for sel, body in self._rules(_live_css()):
            if re.search(r'background\s*:\s*var\(--code-bg\)', body):
                for cls in re.findall(r'\.([A-Za-z0-9_-]+)', sel):
                    dark_classes.add(cls)
        self.assertTrue(dark_classes, '未找到任何以 --code-bg 为底的组件（正则失配？）')

        # 仅考察「真正会被聚焦的表单控件」：代码面族里 <pre>/<code> 不是表单控件，
        # 通用 input/textarea:focus 规则碰不到它们，纳入会造成假阳性。
        import glob
        _srcs = []
        for _f in (['render.py', 'config.py', 'report.py', 'config_db.py',
                    'api_handler.py', 'export.py'] + glob.glob('config_pages/*.py')):
            try:
                with open(_f, encoding='utf-8') as _fh:
                    _srcs.append(_fh.read())
            except OSError:
                pass
        _src = '\n'.join(_srcs)

        def _is_form_control(cls):
            pat = re.compile(r'<(?:textarea|input|select)\b[^>]*class="[^"]*\b'
                             + re.escape(cls) + r'\b')
            return bool(pat.search(_src))

        dark_classes = {c for c in dark_classes if _is_form_control(c)}
        self.assertTrue(
            dark_classes,
            '未找到任何「以 --code-bg 为底且用于表单控件」的类（门禁已失效，需同步）')

        # 通用的「元素 + :focus」规则（特异性 0,1,1）会盖过单类名（0,1,0）
        generic_focus_bg = None
        for sel, body in self._rules(_live_css()):
            if ':focus' not in sel:
                continue
            if not re.search(r'\btextarea\b', sel):
                continue
            m = re.search(r'background\s*:\s*var\((--[a-z0-9-]+)\)', body)
            if m:
                generic_focus_bg = m.group(1)
        self.assertIsNotNone(
            generic_focus_bg,
            '未找到 textarea:focus 的 background 声明（结构已变，门禁需同步）')

        offenders = []
        for cls in sorted(dark_classes):
            # 该组件是否有自己的 :focus 规则且胜出（单类名+:focus = 0,2,0 仍低于 0,1,1 之外的
            # 元素选择器？按 CSS 规则：0,1,1 > 0,1,0；类名+伪类 = 0,2,0 > 0,1,1）
            own_focus = [body for sel, body in self._rules(_live_css())
                         if ':focus' in sel and re.search(r'\.' + re.escape(cls) + r'\b', sel)]
            if own_focus:
                continue  # 组件自带聚焦契约，视为已声明
            if generic_focus_bg != '--code-bg':
                offenders.append(f'.{cls} 聚焦时被 {generic_focus_bg} 覆盖')

        self.assertEqual(
            [], offenders,
            '深色代码面组件聚焦后底色被通用 :focus 规则翻白：' + '; '.join(offenders))

    def test_code_ink_on_focus_surface_is_readable(self):
        """扣住用户实测数值：焦点前的 14.88:1 不得退化为不可辨认。"""
        code_ink = _token(_live_css(), '--code-ink')
        white = _token(_live_css(), '--bg-surface')
        # 反证：白底 + 浅字确实不可读（这是被修复的现象）
        self.assertLess(_contrast(code_ink, white), 4.5,
                        '前提已变：--code-ink 在白底上已可读，本门禁需重新评估')
        # 正证：修复后聚焦态生效底色必须是深色代码底
        self.assertGreaterEqual(_contrast(code_ink, _token(_live_css(), '--code-bg')), 4.5)


class TestCategoryCollapseScopedToOwnLevel(unittest.TestCase):
    """BUG-2 门禁：折叠/展开必须只作用于「当前这一级」，不得波及下一级。

    实测反馈：卡片视图下点分类箭头折叠，被错误作用到它的下一级；
    且用户永远无法实现「当前级别的全部折叠」。

    根因：`.cat-block.collapsed > .cat-body` 用的是子选择器，但同一分类块内
    卡片的直接容器是 `.rpt-grid.cat-cards.view-card`，折叠它只隐藏了本级的
    一层容器，而 `.cat-children`（下一级）内的卡片仍各自独立展开 —— 与列表
    视图（.cat-body 内含全部行）的语义不一致。

    契约：折叠类施加在 .cat-block 上时，应同时隐藏「本级的列表体」与「本级的
    卡片体」，即所有直接子容器；下一级 .cat-block 容器整体作为一级被隐藏，
    且下一级自身的 .collapsed 状态必须被保留（不串味）。
    """
    @classmethod
    def setUpClass(cls):
        from tests.test_base import make_config_db, init_test_db
        import db as db_mod
        cls.conn = make_config_db()
        with patch("db._get_engine", return_value="sqlite3"):
            init_test_db(cls.conn)
            db_mod.add_pool(cls.conn, "池A", "h", 3306, "u", "p", "d")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _empty_body(self, body):
        m = re.search(r'<body[^>]*>(.*)</body>', body, re.S)
        return m.group(1) if m else body

    def test_collapsed_rule_covers_both_view_bodies(self):
        """折叠规则必须覆盖本级的两种视图容器（列表体 + 卡片体）。

        注意：必须先去掉 CSS 注释再匹配——注释块会被 `[^{}]+` 吞进「选择器」里，
        而本规则上方的说明文字恰好提到 .cat-cards，否则门禁会被注释本身喂饱
        （变异证明时发现：删掉选择器里的 .cat-cards 门禁仍绿）。
        """
        css_nc = re.sub(r'/\*.*?\*/', '', _live_css(), flags=re.S)
        rule = None
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css_nc, re.S):
            if '.cat-block.collapsed' in m.group(1) and 'display:none' in m.group(2):
                rule = m.group(1).strip()
                break
        self.assertIsNotNone(rule, '未找到 .cat-block.collapsed 的 display:none 规则')
        self.assertIn('.cat-body', rule, '折叠规则未覆盖列表体 .cat-body')
        self.assertIn('.cat-cards', rule.replace(' ', ''),
                      '折叠规则未覆盖卡片体 .cat-cards → 卡片视图下折叠会漏掉本级卡片')
    def test_toggle_uses_closest_cat_block_only(self):
        """toggleCatBlock 只允许切换「按钮所属的那一个」cat-block，不得向下传播。"""
        m = re.search(r'function toggleCatBlock\s*\([^)]*\)\s*\{(.*?)\n\}',
                      render._COMMON_JS, re.S)
        self.assertIsNotNone(m, '未找到 toggleCatBlock 实现')
        body = m.group(1)
        # 去掉注释后再做「不得批量操作」的判定（注释里会提到 .cat-children 语义）
        code = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
        code = re.sub(r'//[^\n]*', '', code)
        self.assertIn("closest('.cat-block')", code.replace('"', "'"),
                      'toggleCatBlock 未用 closest 锚定当前分类块')
        for bad in ('querySelectorAll', 'children', 'nextElementSibling'):
            self.assertNotIn(bad, code,
                             f'toggleCatBlock 出现 {bad} → 折叠可能外溢到相邻/下级')

class TestCategoryTreeLocatesRightPane(unittest.TestCase):
    """BUG-3 门禁：点击左栏「报表分类」层级 → 右栏滚动定位并高亮，而非折叠。

    实测反馈：点击树中任意层级目前的交互是折叠/展开（做错了），
    期望右侧列表视图（列表或卡片）第一行定位到该分类模块位置。

    契约：
    1. 树行必须携带「目标区块锚点」标识（data-target 或等价物）；
    2. 存在唯一的定位函数（复用既有锚点高亮机制 .row-highlight）；
    3. 该函数被注册进 initPage（换页后仍可用）；
    4. 定位不得再触发折叠（.kids 的 .on 切换只保留给独立的展开箭头）。
    """
    @classmethod
    def setUpClass(cls):
        from tests.test_base import make_config_db, init_test_db
        import db as db_mod
        cls.conn = make_config_db()
        with patch("db._get_engine", return_value="sqlite3"):
            init_test_db(cls.conn)
            db_mod.add_pool(cls.conn, "池A", "h", 3306, "u", "p", "d")
            parent = db_mod.add_category(cls.conn, "父分类")
            db_mod.add_category(cls.conn, "子分类", parent_id=parent)
            db_mod.add_report(cls.conn, "报表A", "SELECT 1", 20, 1, parent)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _reports_page(self):
        from unittest.mock import patch as _patch
        import config_pages.reports as reports_mod
        with _patch.object(config, "_nav_badges", return_value={}):
            return reports_mod.render_reports_page(self.conn)

    def test_tree_rows_carry_target_anchor(self):
        """每个分类树行必须带 data-target（指向右侧对应 .cat-block 的 id）。"""
        body = self._reports_page()
        tree = re.search(r'<div class="tree"[^>]*>(.*?)</div>\s*</div>', body, re.S)
        self.assertIsNotNone(tree, '未找到分类树容器 .tree')
        self.assertIn('data-target=', tree.group(1),
                      '分类树行未携带 data-target，点击无法定位右侧区块')

    def test_locate_function_exists_and_registered(self):
        """定位函数存在、被 initPage 注册（换页后可用），且走滚动 + 高亮。"""
        js = render._COMMON_JS
        m = re.search(r'function (catTreeLocate\w*)\s*\(', js)
        self.assertIsNotNone(m, '未找到分类定位函数（catTreeLocate*）')
        name = m.group(1)
        body = re.search(r'function ' + name + r'\s*\([^)]*\)\s*\{(.*?)\n\}', js, re.S).group(1)
        self.assertIn('scrollIntoView', body, '定位函数未滚动到目标区块')
        self.assertIn('row-highlight', body, '定位函数未复用既有高亮类 .row-highlight')
        # 注册路径唯一：定位链路必须在 initPage 内可达（换页后重放）。
        # 注意：项目门禁 TestPageInitRegistration 要求 initPage 只调用 init* 前缀函数，
        # 故定位刷新由包装函数 initCatTreeLocate() 承担，它内部操作 data-target。
        init = re.search(r'function initPage\s*\([^)]*\)\s*\{(.*?)\n\}', js, re.S)
        self.assertIsNotNone(init, '未找到 initPage')
        init_body = init.group(1)
        self.assertRegex(init_body, r'init[A-Za-z0-9_]*Cat[A-Za-z0-9_]*\s*\(',
                         '分类树相关初始化未在 initPage 内注册 → 无刷新换页后失效')
        wrapper = re.search(r'function (initCatTreeLocate\w*)\s*\([^)]*\)\s*\{(.*?)\n\}',
                            js, re.S)
        self.assertIsNotNone(wrapper, '缺少 initCatTreeLocate 包装函数')
        self.assertIn('data-target', wrapper.group(2),
                      'initCatTreeLocate 未按 data-target 恢复左树高亮')

    def test_row_click_locates_instead_of_collapsing(self):
        """树行点击处理必须做定位，而不是切 .kids 的 .on。"""
        js = render._COMMON_JS
        m = re.search(r'function (catTreeLocate\w*|onCatRowClick)\s*\(', js)
        self.assertIsNotNone(m, '未找到树行定位函数')
        name = m.group(1)
        body = re.search(r'function ' + name + r'\s*\([^)]*\)\s*\{(.*?)\n\}', js, re.S).group(1)
        self.assertIn('scrollIntoView', body, '树行定位函数未做滚动定位')
        self.assertIn('row-highlight', body, '树行定位函数未复用既有高亮 .row-highlight')
        # 行点击入口（toggleCatNode）必须委派给定位函数，不得再切 .kids 的 .on
        entry = re.search(r'function (toggleCatNode\w*)\s*\([^)]*\)\s*\{(.*?)\n\}',
                          js, re.S)
        self.assertIsNotNone(entry, '未找到树行点击入口 toggleCatNode')
        entry_code = re.sub(r'/\*.*?\*/', '', entry.group(2), flags=re.S)
        self.assertNotIn("classList.toggle('on')", entry_code,
                         '树行点击仍在切换 .kids 的 .on → 折叠语义未解除')
        self.assertIn(name, entry_code,
                      f'树行点击未委派给定位函数 {name}')

    def test_has_own_expand_affordance(self):
        """折叠能力必须保留给「独立的展开箭头」，不随行点击一起消失。"""
        body = self._reports_page()
        self.assertIn('cat-expand', body,
                      '缺少独立展开箭头（cat-expand）→ 折叠能力被一并删除')

    def test_both_views_have_addressable_anchor(self):
        """定位目标对两种视图都成立：区块 id 存在，且卡片/列表都在其中。"""
        body = self._reports_page()
        ids = set(re.findall(r'class="section cat-block[^"]*"\s+id="([^"]+)"', body))
        self.assertTrue(ids, '分类区块缺少可定位 id')


class TestTreeRowClickConsistency(unittest.TestCase):
    """交互统一门禁（用户要求）：全站「分类树」的行点击语义必须一致。

    现有两棵树：
      - `/config/reports` 左树（render.build_category_manage_section_html）
      - 报表中心 `#rc-tree`（report.render_report_selector）
    两处都必须遵守同一契约：
      1. 行点击 ≠ 折叠；展开折叠只归独立箭头（.cat-expand / [data-chevron]）；
      2. 行点击做本树的主职责（定位或筛选/选中）。
    历史缺陷：`#rc-tree` 行点击既切筛选又 toggle .kids，与左树行为打架。
    """

    def test_rc_tree_row_click_does_not_toggle_kids(self):
        """报表中心左树：行点击主分支不得再 toggle 下级 .kids（折叠归 chevron）。"""
        import inspect
        src = inspect.getsource(report.render_report_selector)
        i = src.find("closest('.cat, .leaf')")
        self.assertGreaterEqual(i, 0, '未找到 #rc-tree 的点击监听器（结构已变，门禁需同步）')
        j = src.find('e.preventDefault();', i)
        self.assertGreaterEqual(j, 0, '未找到 chevron 分支（结构已变，门禁需同步）')
        end = src.find('\n    });', j)
        tail = src[j:end if end > 0 else j + 800]
        code = re.sub(r'/\*.*?\*/', '', tail, flags=re.S)
        self.assertNotIn("classList.toggle('on')", code,
                         '#rc-tree 行点击仍在 toggle .kids → 与左树定位语义不一致')

    def test_both_trees_expose_independent_expand_affordance(self):
        """两棵树都必须有「独立展开箭头」，否则删掉行点击折叠就没折叠入口了。"""
        import inspect
        src = inspect.getsource(report.render_report_selector)
        self.assertIn('data-chevron', src, '#rc-tree 缺少独立展开箭头 data-chevron')
        mgmt = inspect.getsource(render.build_category_manage_section_html)
        self.assertIn('cat-expand', mgmt, '/config/reports 左树缺少独立展开箭头 .cat-expand')

if __name__ == "__main__":
    unittest.main()
