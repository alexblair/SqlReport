"""
htmlcheck.py — 渲染层 HTML 结构校验工具（纯标准库）。

设计动机（2026-08-10，dianostic-bugs 会话捕获）：
render.py 编辑态 API Key 管理区块嵌套进主表单，HTML5 解析时内层 form 的开始
标签被忽略、第一个 </form> 提前闭合主表单，保存按钮被挤出表单外，点击无反应。
此前所有渲染测试均为字符串级断言（assertIn/正则），无法发现结构类 bug。

本模块提供三个纯函数（均为「报告问题」而非「断言」，由调用方决定如何失败）：
- form_ranges(html)          : 所有 <form>..</form> 配对区间（栈式）
- find_nested_forms(html)    : HTML5 语义下嵌套 form（会提前闭合外层主表单）
- check_tag_balance(html)    : 标签配对/自闭合/合法空标签校验（html.parser）

使用方式：tests/test_html_structure.py 对全部 form 渲染函数逐一遍历断言；
单个渲染函数测试（如 test_api_key_ui）也可直接 import 复用。
"""

import re
from html.parser import HTMLParser

# HTML5 空元素（void elements）：无闭合标签也不报错
_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

_FORM_START_RE = re.compile(r"<form\b[^>]*>")
_FORM_END_RE = re.compile(r"</form>")
_FORM_RE = re.compile(r"<form\b[^>]*>|</form>")


def form_ranges(html: str) -> list[tuple[int, int]]:
    """返回 HTML 中所有 <form>..</form> 配对 (开始, 结束) 偏移区间。

    栈式配对：遇到 <form> 入栈、遇到 </form> 弹栈配对。
    内层先闭合，因此嵌套 form 的内层区间在前、外层区间包含内层。
    """
    ranges = []
    stack = []
    for m in _FORM_RE.finditer(html):
        if m.group(0).startswith("</"):
            if stack:
                ranges.append((stack.pop(), m.end()))
        else:
            stack.append(m.start())
    return ranges


def find_nested_forms(html: str) -> list[dict]:
    """检测 HTML5 语义下的嵌套 form（即会破坏外层表单的结构）。

    HTML5 规范禁止 form 嵌套：解析器遇到已在 form 内的 <form> 开始标签时
    忽略之，因此内层 form 的 </form> 会提前闭合外层主表单，其后所有控件
    （保存按钮等）脱离表单。

    返回问题列表：[{outer_start, outer_end, nested_start}]
    """
    problems = []
    for outer_start, outer_end in form_ranges(html):
        inner = _FORM_START_RE.search(html, outer_start + 1, outer_end)
        if inner:
            problems.append({
                "outer_start": outer_start,
                "outer_end": outer_end,
                "nested_start": inner.start(),
            })
    return problems


def check_tag_balance(html: str) -> list[str]:
    """用 html.parser 校验标签配对，返回问题描述列表（合法时为空）。

    校验项：
    - 非空元素缺 </tag>（未闭合）
    - 孤儿 </tag>（无配对开始标签）
    - 空元素（void）携带结束标签（浏览器会忽略，属冗余）
    自闭合 </> 形式同样处理。属性解析错误（如引号不闭合导致属性吞并）
    通过 HTMLParser 内部语法容忍——本函数只做配对级校验。
    """
    problems = []

    class _Checker(HTMLParser):
        def __init__(self, sink):
            super().__init__(convert_charrefs=True)
            self.sink = sink
            self.stack = []  # [(tag, line, offset)]

        def handle_starttag(self, tag, attrs):
            if tag in _VOID_ELEMENTS:
                return
            self.stack.append((tag, self.getpos()))

        def handle_startendtag(self, tag, attrs):
            if tag in _VOID_ELEMENTS:
                return
            self.sink.append(f"自闭合非空元素 <{tag}/> （位置 {self.getpos()}）缺少配对闭合标签")

        def handle_endtag(self, tag):
            if tag in _VOID_ELEMENTS:
                self.sink.append(f"空元素 <{tag}> 携带冗余 </{tag}> （位置 {self.getpos()}）")
                return
            if not self.stack:
                self.sink.append(f"孤儿闭合标签 </{tag}> （位置 {self.getpos()}）")
                return
            open_tag, open_pos = self.stack.pop()
            if open_tag != tag:
                self.sink.append(
                    f"标签错配：<{open_tag}>（位置 {open_pos}）被 </{tag}> 闭合（位置 {self.getpos()}）"
                    f"——未闭合中间 {len(self.stack)} 个标签")
                # 弹出直到匹配或栈空（继续尽力配对）
                while self.stack:
                    if self.stack[-1][0] == tag:
                        break
                    self.stack.pop()

        def handle_decl(self, decl):
            # <!DOCTYPE> 等声明忽略
            pass

    checker = _Checker(problems)
    checker.feed(html)
    checker.close()
    # feed 后 getpos 已到末尾；未闭合的栈
    for tag, pos in checker.stack:
        problems.append(f"标签 <{tag}> 未闭合（位置 {pos}）——可能导致后续内容被吞入")
    return problems


def main_form_span(html: str, action_hint: str = "") -> tuple[int, int]:
    """以 HTML5 语义返回主表单范围 (start, end)。

    主表单 = 页面第一个 <form>；其结束位置按 HTML5 语义取第一个 </form>
    （嵌套 form 时该 </form> 来自内层——主表单被提前闭合，正是 bug 场景）。
    action_hint 不为空时，优先定位 action 包含该字符串的表单。

    返回 (start, end)；找不到表单时返回 (-1, -1)。
    """
    if action_hint:
        prefer = re.search(rf'<form\b[^>]*action="[^"]*{re.escape(action_hint)}[^"]*"', html)
        if prefer:
            start = prefer.start()
            close = html.find("</form>", start)
            return (start, close + len("</form>") if close != -1 else len(html))
    first = _FORM_START_RE.search(html)
    if not first:
        return (-1, -1)
    start = first.start()
    close = html.find("</form>", start)
    return (start, close + len("</form>") if close != -1 else len(html))