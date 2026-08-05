"""
json_template.py — API JSON 输出模板引擎（纯标准库，零依赖）

模板语法：JSON 占位符替换。模板本身是一段 JSON 文本，值位置以
{{占位符}} 引用上下文数据；渲染时每个占位符替换为其对应值的 JSON
片段（ensure_ascii=False、default=str，与现有 JSON 序列化约定一致），
替换后整体必须是合法 JSON。

占位符匹配规则：{{ + 可选空白 + 标识符（[A-Za-z_][A-Za-z0-9_]*）+ 可选空白 + }}
实现正则：\\{\\{\\s*[A-Za-z_][A-Za-z0-9_]*\\s*\\}\\}
（_PLACEHOLDER_RE 与之同义；04 工单的 JS 端预览实现须使用同语义正则，
保证前后端占位符契约一致）
模板中不出现的字段即不输出；未知占位符（不在当前模式键集内）→ 校验失败。
模板为空/空白 = 未启用模板。

上下文语义：键集内键缺失时替换为 null（典型场景：普通链路无 meta，
渲染 {{meta}} 得到 null，调用方无需显式传 None）；键集外的占位符仍报错。

可用占位符（键集）：
- 单结果集模式（SINGLE_KEYS）：data（数据行数组）、total（总行数）、
  page（当前页码）、page_size（每页条数）、total_pages（总页数）、
  full（全量标记 true/false）、meta（静态缓存 meta 对象，普通链路为 null）
- 全部结果集模式（ALL_KEYS）：results（结果集数组）、mode（模式字符串）、
  page、page_size、full、meta
"""

import json
import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# 单结果集模式可用占位符
SINGLE_KEYS = ("data", "total", "page", "page_size", "total_pages", "full", "meta")
# 全部结果集模式可用占位符
ALL_KEYS = ("results", "mode", "page", "page_size", "full", "meta")

# 校验/预览用内置样例上下文（与配置表单预览一致，含中文列名与数据值）
_SAMPLE_SINGLE_CONTEXT = {
    "data": [{"单价": 500, "可交易数量": "311 个", "物资名称": "示例物资"}],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "full": False,
    "meta": None,
}
_SAMPLE_ALL_CONTEXT = {
    "results": [{
        "name": "结果1",
        "data": [{"单价": 500}],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }],
    "mode": "all",
    "page": 1,
    "page_size": 20,
    "full": False,
    "meta": None,
}
_SAMPLES = {
    SINGLE_KEYS: _SAMPLE_SINGLE_CONTEXT,
    ALL_KEYS: _SAMPLE_ALL_CONTEXT,
}
_VALID_KEYS = frozenset(SINGLE_KEYS) | frozenset(ALL_KEYS)


def _is_valid_key(name: str) -> bool:
    """占位符名是否在任一模式键集内（区分「可选键缺失」与「未知占位符」）。"""
    return name in _VALID_KEYS


def is_template_enabled(template: str | None) -> bool:
    """模板留空/空白 = 未启用。"""
    return bool(template and template.strip())


def _value_to_json(value) -> str:
    """值序列化为 JSON 片段（与响应序列化约定一致）。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def _pos_to_line_col(text: str, pos: int) -> tuple[int, int]:
    """把字符位置映射为 (行, 列)，均为 1-based。"""
    line = text.count("\n", 0, pos) + 1
    col = pos - text.rfind("\n", 0, pos)
    return line, col


def _split_segments(template: str) -> list[tuple]:
    """按占位符切分模板。

    返回 [(kind, start, end, text)]：
    - 文本段：("text", start, end, 原文片段)
    - 占位符段：("ph", start, end, 占位符名)
    """
    segments = []
    pos = 0
    for m in _PLACEHOLDER_RE.finditer(template):
        if m.start() > pos:
            segments.append(("text", pos, m.start(), template[pos:m.start()]))
        segments.append(("ph", m.start(), m.end(), m.group(1)))
        pos = m.end()
    if pos < len(template):
        segments.append(("text", pos, len(template), template[pos:]))
    return segments


def _render_to_output(segments: list[tuple], context: dict) -> tuple[str, list[int]]:
    """渲染各段，返回 (输出字符串, 各段输出长度列表)。"""
    parts = []
    lengths = []
    for kind, _start, _end, text in segments:
        if kind == "text":
            parts.append(text)
            lengths.append(len(text))
        else:
            # 键集内键缺失 → null（可选键语义）
            rendered = _value_to_json(context.get(text))
            parts.append(rendered)
            lengths.append(len(rendered))
    return "".join(parts), lengths


def _output_pos_to_template_pos(segments: list[tuple], lengths: list[int],
                                pos: int, template_len: int) -> int:
    """把输出字符串中的位置映射回模板位置（占位符段映射到其起始）。

    pos 超出所有段（如缺右括号的 EOF 错误）时指向模板结尾，行号列号
    落在最后一行末尾附近，与错误文案的「附近」语义一致。
    """
    cursor = 0
    for (kind, start, _end, _text), seg_len in zip(segments, lengths):
        if pos < cursor + seg_len:
            if kind == "text":
                return start + (pos - cursor)
            return start
        cursor += seg_len
    return template_len


def render_template(template: str, context: dict, keys: tuple = None) -> tuple[bool, str, str]:
    """渲染模板。

    参数:
        template: 模板文本
        context: 渲染上下文（键集内键可缺失，缺失替换为 null，典型场景：
                 普通链路无 meta）
        keys: 可选；占位符严格键集（SINGLE_KEYS/ALL_KEYS）。提供时跨模式
              键（如 single 模板含 {{results}}）报未知占位符；None 时按
              全部合法键宽松判定。校验/保存场景必须传 keys。

    返回 (ok, output, error)：
    - ok=True：output 为渲染后的 JSON 字符串，error 为空
    - ok=False：output 为空，error 含行列定位的说明
    """
    if not is_template_enabled(template):
        return False, "", "模板为空或空白（未启用）"

    valid = keys if keys is not None else _VALID_KEYS
    segments = _split_segments(template)
    for kind, start, _end, name in segments:
        if kind == "ph" and name not in context:
            # 合法键缺失 → null（可选键语义）；键集外键 → 未知占位符
            if name in valid:
                continue
            line, col = _pos_to_line_col(template, start)
            display = "{{" + name + "}}"
            return False, "", f"未知占位符 {display} 位于第 {line} 行第 {col} 列"

    output, lengths = _render_to_output(segments, context)
    try:
        json.loads(output)
    except json.JSONDecodeError as e:
        tpos = _output_pos_to_template_pos(segments, lengths, e.pos, len(template))
        line, col = _pos_to_line_col(template, tpos)
        return False, "", f"替换后的 JSON 非法（第 {line} 行第 {col} 列附近）：{e.msg}"
    return True, output, ""


def validate_template(template: str, keys: tuple) -> tuple[bool, str]:
    """校验模板是否可用（保存前把关）。

    参数:
        template: 模板文本
        keys: 该模式允许的占位符键集（SINGLE_KEYS 或 ALL_KEYS），
              决定未知占位符判定与样例上下文

    返回 (ok, error)：
    - 模板为空/空白 → (True, "")（未启用，无需校验）
    - 未知占位符 → (False, "未知占位符 {{x}} 位于第 L 行第 C 列")
    - 替换后非法 JSON → (False, "替换后的 JSON 非法（第 L 行第 C 列附近）：msg"）
    - 合法 → (True, "")
    """
    if not is_template_enabled(template):
        return True, ""
    if keys not in _SAMPLES:
        raise ValueError(f"不支持的键集: {keys!r}，仅支持 SINGLE_KEYS / ALL_KEYS")
    ok, _output, error = render_template(template, _SAMPLES[keys], keys=keys)
    return ok, error
