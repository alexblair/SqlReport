"""
result_transform.py — 结果集变换模块（纯函数，无 IO）

职责：
- 对已取回的结果集（rows + columns）执行内存变换：筛选、排序、列选择、列索引映射
- 报表页面（report.py）、导出（export.py）、API（api_handler.py）三处调用方共用
- 不感知数据来源（MySQL / Redis / 静态文件），不负责分页语义（调用方协议）

领域约定（三处调用方一致，勿单边修改）：
- 筛选操作符：contains / eq / neq / gt / lt / gte / lte / isempty / notempty
- 筛选值匹配表达式（全系统统一语法，parse_filter_expr）：`*` 通配符（任意位置/多次，非正则）、
  英文逗号多值（段 strip、空段忽略，多值之间 OR）、`\*` / `\,` / `\\` 转义；
  仅 contains / eq / neq 生效（contains 不敏感，eq/neq 敏感），无通配符输入保持既有语义
- 排序：稳定排序，None 值始终在最后，不受升降序影响
- 列选择：仅保留存在且不重复的列（保序）；空请求或全部无效时回退全部列
- 总页数：page_size 或 total 非正时返回 1（防除零），否则向上取整
"""

import math
import re

# ---------------------------------------------------------------------------


def calc_total_pages(total: int, page_size: int) -> int:
    """计算总页数。

    边界保护（与既有调用方行为一致）：
    - page_size <= 0 或 total <= 0 → 返回 1（防止除零）
    - 其余 → math.ceil(total / page_size) 向上取整
    """
    if page_size <= 0 or total <= 0:
        return 1
    return math.ceil(total / page_size)


def _try_float(val):
    """尝试将值转为 float，失败返回 None"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_filter_expr(raw) -> list[list[tuple]]:
    """解析筛选值表达式 → 多值段列表（多值之间 OR 语义，全系统统一语法）。

    语法（报表页 / 导出 / API / 审计页一致）：
    - `*` 通配符：任意位置、可多次，匹配任意内容（非正则，仅 `*` 为元字符）
    - 英文逗号：拆分多个值（段级 strip 前后空格，空段忽略）；多值任一命中即匹配
    - 转义：`\\*` 字面星号、`\\,` 字面逗号（不拆分为多值）、`\\\\` 字面反斜杠
    - 无裸逗号时按单值处理（不 strip，保持既有行为）

    返回段列表，每段为 token 列表：[("lit", ch), ...] 与 [("wild",), ...] 的混合；
    全空多值（如 " , "）返回空列表，调用方应视为条件忽略。
    """
    if not isinstance(raw, str):
        raw = str(raw)
    segments = []
    parts = _split_filter_value(raw)
    for seg in parts:
        tokens = []
        i = 0
        n = len(seg)
        while i < n:
            ch = seg[i]
            if ch == "\\":
                if i + 1 < n and seg[i + 1] in ("*", ",", "\\"):
                    tokens.append(("lit", seg[i + 1]))
                    i += 2
                    continue
                tokens.append(("lit", "\\"))
                i += 1
                continue
            if ch == "*":
                tokens.append(("wild",))
                i += 1
                continue
            tokens.append(("lit", ch))
            i += 1
        segments.append(tokens)
    return segments


def _split_filter_value(raw: str) -> list[str]:
    """按裸英文逗号拆分段（`\\,` 为字面逗号不拆分）。

    转义判定：逗号前连续反斜杠为奇数 → 该逗号被转义（字面）；
    偶数 → 裸逗号（分隔符）。如 `a\\\\,b` = 字面反斜杠 + 分隔 → 两段，
    `a\\,b` = 字面反斜杠 + 字面逗号 → 单段。

    含裸逗号时逐段 strip 且空段忽略；不含裸逗号时返回原串单段（不 strip）。
    """
    has_comma = False
    parts = []
    cur = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\\":
            if i + 1 < n and raw[i + 1] == "\\":
                cur.append("\\")
                cur.append("\\")
                i += 2
                continue
            if i + 1 < n and raw[i + 1] == ",":
                cur.append("\\")
                cur.append(",")
                i += 2
                continue
            cur.append(ch)
            i += 1
            continue
        if ch == ",":
            has_comma = True
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    if has_comma:
        parts = [p.strip() for p in parts if p.strip()]
    return parts


def _segment_regex(tokens: list[tuple]) -> str:
    """段 token 列表 → 正则模式（`*` → `.*`，字面量 re.escape）。"""
    parts = []
    for tok in tokens:
        if tok[0] == "wild":
            parts.append(".*")
        else:
            parts.append(re.escape(tok[1]))
    return "".join(parts)


def _compile_segments(segments: list[list[tuple]], ignorecase: bool) -> list:
    """多值段 → 编译后的正则列表（contains 不敏感，eq/neq 敏感）。"""
    flags = re.IGNORECASE if ignorecase else 0
    return [re.compile(_segment_regex(seg), flags) for seg in segments]


def _cell_str(val) -> str:
    """行值字符串化（None → 空串，保持既有 contains/eq/neq 语义）。"""
    return str(val) if val is not None else ""


def filter_rows(rows: list[tuple], columns: list[str],
                filters=None) -> list[tuple]:
    """
    在内存中按多字段筛选（AND 逻辑），支持多种操作符。

    filters: list[(col, op, val), ...]
    操作符说明：
      contains  — 不区分大小写的 LIKE '%val%'
      eq        — 字符串精确相等
      neq       — 字符串不相等
      gt / lt / gte / lte — 数值比较（尝试转 float）
      isempty   — IS NULL OR = ''
      notempty  — IS NOT NULL AND != ''
    """
    if not filters:
        return rows
    result = list(rows)
    for col_name, op, q in filters:
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name)

        if op in ("contains", "eq", "neq"):
            segments = parse_filter_expr(q)
            if not segments:
                continue
            regexes = _compile_segments(segments, ignorecase=(op == "contains"))
            if op == "contains":
                result = [
                    r for r in result
                    if any(rx.search(_cell_str(r[col_idx])) for rx in regexes)
                ]
            elif op == "eq":
                result = [
                    r for r in result
                    if any(rx.fullmatch(_cell_str(r[col_idx])) for rx in regexes)
                ]
            else:
                result = [
                    r for r in result
                    if not any(rx.fullmatch(_cell_str(r[col_idx])) for rx in regexes)
                ]
        elif op in ("gt", "lt", "gte", "lte"):
            try:
                q_num = float(q)
            except (ValueError, TypeError):
                continue
            if op == "gt":
                result = [
                    r for r in result
                    if _try_float(r[col_idx]) is not None and _try_float(r[col_idx]) > q_num
                ]
            elif op == "lt":
                result = [
                    r for r in result
                    if _try_float(r[col_idx]) is not None and _try_float(r[col_idx]) < q_num
                ]
            elif op == "gte":
                result = [
                    r for r in result
                    if _try_float(r[col_idx]) is not None and _try_float(r[col_idx]) >= q_num
                ]
            elif op == "lte":
                result = [
                    r for r in result
                    if _try_float(r[col_idx]) is not None and _try_float(r[col_idx]) <= q_num
                ]
        elif op == "isempty":
            result = [
                r for r in result
                if r[col_idx] is None or str(r[col_idx]).strip() == ""
            ]
        elif op == "notempty":
            result = [
                r for r in result
                if r[col_idx] is not None and str(r[col_idx]).strip() != ""
            ]
    return result


def sort_rows(rows: list[tuple], columns: list[str],
              sorts=None) -> list[tuple]:
    """
    在内存中按多字段排序。

    sorts: list[(col, dir), ...]  按优先级从高到低
    使用稳定排序，从最低优先级到最高优先级依次排序。
    调用方应保证 sorts 中无重复列名。
    None 值始终排在最后，不受升降序影响。
    """
    if not sorts:
        return rows
    result = list(rows)
    # 从低优先级到高优先级应用（稳定排序保证优先级）
    for col_name, dir_ in reversed(sorts):
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name)
        reverse = dir_.lower() == "desc"
        # 分离 None 值与非 None 值，确保 None 始终最后
        none_part = [r for r in result if r[col_idx] is None]
        not_none_part = [r for r in result if r[col_idx] is not None]
        not_none_part.sort(key=lambda r, c=col_idx: str(r[c]), reverse=reverse)
        result = not_none_part + none_part
    return result


def select_columns(all_columns: list[str], requested=None) -> list[str]:
    """
    从 all_columns 中选择要显示的列（按请求顺序，去重，仅保留存在的列）。

    requested: 列名列表 / 逗号分隔字符串 / None。
    None 或空请求 → 返回全部列。
    全部请求列均无效 → 回退返回全部列。
    """
    if requested is None:
        return list(all_columns)
    if isinstance(requested, str):
        requested = [c.strip() for c in requested.split(",") if c.strip()]
    valid_set = set(all_columns)
    seen = set()
    result = []
    for c in requested:
        c = c.strip()
        if c in valid_set and c not in seen:
            result.append(c)
            seen.add(c)
    return result if result else list(all_columns)


def column_indices(display_cols: list[str], all_columns: list[str]) -> list[int]:
    """将显示列列表映射为在 all_columns 中的索引列表（调用方保证列存在）。"""
    index_map = {name: idx for idx, name in enumerate(all_columns)}
    return [index_map[c] for c in display_cols]
