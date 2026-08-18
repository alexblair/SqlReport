"""
markdown_render.py — Markdown 渲染单一来源模块

将 Markdown 源文本渲染为已消毒（sanitize）的 HTML，供全项目 Markdown
消费点（报表备注 memo、未来的接口说明 description 等）共用，杜绝多实现漂移。

安全模型：
- markdown 库渲染（禁用 raw HTML 透传，codehilite 高亮 + fenced_code + tables + nl2br）
- 渲染结果经白名单 sanitize（标准库 html.parser 自实现，不引 bleach）
- URL 协议白名单：仅 http/https/mailto/#；javascript:/data: 等危险协议
  → 对应 <a> 成对剥离，内部文本保留为纯文本
- mermaid fenced 块输出 <pre class="mermaid"><code>…</code></pre>（源码转义），
  由前端 mermaid.min.js 按需渲染
"""

import html.parser
import html as html_mod

import markdown as _markdown

# ---------------------------------------------------------------------------
# 渲染配置
# ---------------------------------------------------------------------------

_MARKDOWN_EXTENSIONS = [
    "fenced_code",
    "codehilite",
    "tables",
    "nl2br",
]

_MARKDOWN_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "highlight",
        "guess_lang": False,
    }
}


# ---------------------------------------------------------------------------
# Sanitize 白名单
# ---------------------------------------------------------------------------

# 允许保留的标签（其余标签成对剥离、内部文本保留为纯文本）
_ALLOWED_TAGS = frozenset({
    "p", "br", "h1", "h2", "h3", "h4", "ul", "ol", "li",
    "strong", "em", "code", "pre", "blockquote", "a",
    "table", "thead", "tbody", "tr", "th", "td", "img",
    "div", "span", "hr", "del",
})

# 允许的额外属性（class 全局允许，供 codehilite 高亮类与 pre.mermaid 使用）
_ALLOWED_ATTRS = {
    "a": {"href"},
    "img": {"src", "alt"},
}

# 无闭合标签（HTML void 元素）：输出后不入栈，避免吞掉后续结束标签
_VOID_TAGS = frozenset({"br", "hr", "img"})

_SAFE_URL_PROTOCOLS = ("http", "https", "mailto", "#")

_MERMAID_PLACEHOLDER = '<div class="mermaid-placeholder-{idx}"></div>'

# mermaid 前端资产（本地静态托管，版本锁 URL 随仓库提交）
MERMAID_VENDOR_VERSION = "11.16.1"
MERMAID_JS_URL = (f"/static/vendor/mermaid@{MERMAID_VENDOR_VERSION}"
                  "/mermaid.min.js")


def _is_safe_href(href: str) -> bool:
    """URL 协议白名单校验。

    空 href（无协议）视为安全；含协议时仅 http/https/mailto/纯锚点 允许。
    对实体编码的协议（如 &#106;avascript:）先解码再校验。
    """
    value = html_mod.unescape(href).strip()
    if not value:
        return True
    if value.startswith("#"):
        return True
    lower = value.lower()
    if ":" not in lower:
        return True
    return any(lower.startswith(p + ":") for p in _SAFE_URL_PROTOCOLS)


class _Sanitizer(html.parser.HTMLParser):
    """白名单 HTML 消毒器。

    机制：
    - 白名单标签 + 属性合法 → 输出过滤后的标签
    - 白名单标签但 href 危险（<a>）→ 成对剥离（内部文本保留）
    - 非白名单标签 → 成对剥离（内部文本保留，子标签一并吞掉）
    - 事件属性（onclick 等）不在白名单 → 从标签中过滤掉
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        # 标签栈：元素 (tag, skip_flag)。skip=True 表示该标签对被剥离。
        self._stack: list[tuple[str, bool]] = []

    @property
    def _in_skip(self) -> bool:
        return any(skip for _, skip in self._stack)

    def _filter_attrs(self, tag: str, attrs) -> list[tuple[str, str | None]]:
        allowed = _ALLOWED_ATTRS.get(tag, ())
        result = []
        for name, value in attrs:
            if name == "class":
                result.append((name, value))
            elif name in allowed:
                if name == "href" and not _is_safe_href(value):
                    return None
                result.append((name, value))
        return result

    def _emit_start(self, tag: str, attrs) -> None:
        parts = [f'<{tag}']
        for name, value in attrs:
            if value is None:
                parts.append(f" {name}")
            else:
                parts.append(f' {name}="{value}"')
        parts.append(">")
        self._out.append("".join(parts))

    def _emit_end(self, tag: str) -> None:
        self._out.append(f"</{tag}>")

    def handle_starttag(self, tag: str, attrs) -> None:
        if self._in_skip:
            return
        if tag not in _ALLOWED_TAGS:
            self._stack.append((tag, True))
            return
        filtered = self._filter_attrs(tag, attrs)
        if filtered is None:
            self._stack.append((tag, True))
            return
        self._emit_start(tag, filtered)
        if tag not in _VOID_TAGS:
            self._stack.append((tag, False))

    def handle_startendtag(self, tag: str, attrs) -> None:
        # 自闭合标签（<br/> / <hr/> / <img … />）
        if self._in_skip:
            return
        if tag not in _ALLOWED_TAGS:
            return
        filtered = self._filter_attrs(tag, attrs)
        if filtered is None:
            return
        self._emit_start(tag, filtered)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1][0] == tag:
            _, skip = self._stack.pop()
            if not skip and not self._in_skip:
                self._emit_end(tag)
            return
        # 栈顶不匹配（HTML 结构错配）：静默忽略，避免产生不平衡标签

    def handle_data(self, data: str) -> None:
        self._out.append(data)

    def handle_comment(self, data: str) -> None:
        # 注释一律剥离
        pass

    def handle_decl(self, decl: str) -> None:
        pass

    def handle_pi(self, data: str) -> None:
        pass

    def handle_entityref(self, name: str) -> None:
        # convert_charrefs=False 时实体原样保留（已是转义形态，安全）
        self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._out.append(f"&#{name};")

    def output(self) -> str:
        return "".join(self._out)


def _sanitize_html(html_text: str) -> str:
    """白名单消毒 HTML（标准库 html.parser 自实现）。"""
    sanitizer = _Sanitizer()
    sanitizer.feed(html_text)
    sanitizer.close()
    return sanitizer.output()


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------


def _render_with_mermaid(src: str) -> tuple[str, list[tuple[str, str]]]:
    """提取 mermaid fenced 块并替换为占位符，返回 (处理后文本, 占位块列表)。

    markdown 的 codehilite 会把 ```mermaid 当普通代码块高亮，无法产出
    <pre class="mermaid">。故渲染前先将 mermaid 块整体提取为占位 div，
    渲染 + sanitize 后再原位替换为 <pre class="mermaid"><code>…</code></pre>。
    """
    blocks: list[tuple[str, str]] = []
    out_lines: list[str] = []
    lines = str(src).split("\n")
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].lstrip()
        if s.startswith("```") and s[3:].strip() == "mermaid":
            block_lines: list[str] = []
            j = i + 1
            while j < n and not lines[j].lstrip().startswith("```"):
                block_lines.append(lines[j])
                j += 1
            placeholder = _MERMAID_PLACEHOLDER.format(idx=len(blocks))
            blocks.append((placeholder, "\n".join(block_lines)))
            out_lines.append(placeholder)
            i = j + 1 if j < n else j
        else:
            out_lines.append(lines[i])
            i += 1
    return "\n".join(out_lines), blocks


def render_markdown(src: str | None) -> str:
    """将 Markdown 源文本渲染为已消毒的 HTML。

    Args:
        src: Markdown 源文本；None / 空白字符串返回空串。

    Returns:
        已消毒的 HTML 片段（无 <html>/<body> 包裹）。
    """
    if not src or not str(src).strip():
        return ""
    preprocessed, blocks = _render_with_mermaid(src)
    raw = _markdown.markdown(
        preprocessed,
        extensions=_MARKDOWN_EXTENSIONS,
        extension_configs=_MARKDOWN_EXTENSION_CONFIGS,
        output_format="html5",
    )
    sanitized = _sanitize_html(raw)
    for placeholder, block_src in blocks:
        escaped = html_mod.escape(block_src)
        sanitized = sanitized.replace(
            placeholder,
            f'<pre class="mermaid"><code>{escaped}</code></pre>',
        )
    return sanitized


def contains_mermaid(src: str | None) -> bool:
    """判断源码是否包含 ```mermaid fenced 块（含未闭合块）。"""
    if not src:
        return False
    for line in str(src).splitlines():
        s = line.lstrip()
        if s.startswith("```") and s[3:].strip() == "mermaid":
            return True
    return False


def extract_mermaid_blocks(src: str | None) -> int:
    """返回源码中已闭合的 ```mermaid fenced 块数量（供测试断言）。"""
    if not src:
        return 0
    count = 0
    fence_open = False
    for line in str(src).splitlines():
        s = line.lstrip()
        if s.startswith("```"):
            if fence_open:
                fence_open = False
                count += 1
            elif s[3:].strip() == "mermaid":
                fence_open = True
    return count


_codehilite_css_cache: str | None = None


def codehilite_css() -> str:
    """返回 pygments 代码高亮 CSS（作用于 .highlight 容器）。

    渲染模块的配套样式，消费点（报表页、编辑预览面板）将其追加到页面
    <style> 中，使 render_markdown 产出的 <span class="..."> 高亮真正可见。
    monokai 为深色高亮色系，配套 .md-body 的深色 pre 代码块（见 render._MD_CSS）。
    """
    global _codehilite_css_cache
    if _codehilite_css_cache is None:
        from pygments.formatters import HtmlFormatter
        _codehilite_css_cache = HtmlFormatter(style="monokai").get_style_defs(
            ".highlight")
    return _codehilite_css_cache