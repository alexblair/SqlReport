---
module: markdown_render
contract_id: MOD-MARKDOWN_RENDER
version: 1.0
depends_on: []
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# markdown_render.py 模块分卷

> 本分卷由 T-006 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`markdown_render.py`（~250 行，7 个 def/class）——**Markdown 渲染单一来源**。将 Markdown 源文本渲染为已消毒（sanitize）的 HTML，供全项目 Markdown 消费点共用。包含白名单 HTML 消毒器（基于 `html.parser.HTMLParser`）和 mermaid fenced 块特殊处理（提取占位符 → 渲染 → 替换回 `<pre class="mermaid">`）。

## 2. 公开 API 契约

- `render_markdown(src)` → str：核心 API。Markdown 源文本 → 已消毒 HTML 片段（无 `<html>` 包裹）。
- `contains_mermaid(src)` → bool：判断源码是否包含 ` ```mermaid ` fenced 块。
- `extract_mermaid_blocks(src)` → int：返回已闭合 mermaid 块数量。
- `codehilite_css()` → str：返回 pygments monokai 代码高亮 CSS（带缓存）。

### 内部函数/类

- `_render_with_mermaid(src)` → (str, list[tuple[str, str]])：预处理 mermaid 块提取+占位符替换。
- `_sanitize_html(html_text)` → str：白名单 HTML 消毒入口。
- `_is_safe_href(href)` → bool：URL 协议白名单校验（http/https/mailto/#）。
- `_Sanitizer(HTMLParser)`：白名单消毒器类（标签剥离、属性过滤、事件属性剔除）。

### 常量

- `_MARKDOWN_EXTENSIONS = ["fenced_code", "codehilite", "tables", "nl2br"]`。
- `_ALLOWED_TAGS`：frozenset 28 个 HTML 白名单标签。
- `_ALLOWED_ATTRS`：`{"a": {"href"}, "img": {"src", "alt"}}`。
- `_VOID_TAGS = {"br", "hr", "img"}`。
- `_SAFE_URL_PROTOCOLS = ("http", "https", "mailto", "#")`。
- `MERMAID_VENDOR_VERSION = "11.16.1"` / `MERMAID_JS_URL`：mermaid 静态路径。

## 3. 数据流

```
render_markdown(src)
  → _render_with_mermaid(src)     # 提取 mermaid 块 → 占位符
  → markdown.markdown(...)        # Markdown → HTML（含 codehilite 高亮）
  → _sanitize_html(raw)           # 白名单标签过滤 + URL 协议校验
  → 替换占位符 → <pre class="mermaid">…</pre>
  → 返回已消毒 HTML 片段
```

## 4. 依赖关系

AST import 实测：**无内部模块依赖**。
- 外部依赖：`markdown`（Python-Markdown 库）、`pygments.formatters.HtmlFormatter`（延迟导入，仅 `codehilite_css`）。
- 被调用方：render（备注折叠区/接口说明）、config（备注预览/描述预览）。

## 5. 边界与异常

- 白名单消毒：28 个标签 + 每标签允许属性 + URL 协议白名单，非白名单标签/属性被剥离。
- mermaid 特殊处理：提取 → 占位符 → 渲染后替换回 `<pre class="mermaid">`，防止 codehilite 误处理。
- codehilite CSS 缓存：模块级 `_codehilite_css_cache`，首次调用生成后缓存。
- URL 安全：`_is_safe_href` 仅允许 http/https/mailto/# 协议。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 markdown_render.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
