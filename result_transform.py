r"""
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
- 排序：稳定排序；数值（含数值字符串）按数值大小比较，非数值按字符串比较且
  恒排在全部数值之后（同向）；None 值始终在最后，不受升降序影响
- 列选择：仅保留存在且不重复的列（保序）；空请求或全部无效时回退全部列
- 总页数：page_size 或 total 非正时返回 1（防除零），否则向上取整
"""

import math
import re
import datetime
import calendar

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
    """尝试将值转为 float，失败或非有限值（NaN/Inf）返回 None。

    NaN 参与数值比较恒为 False 会产生「静默清空结果集」的错误答案，
    Inf 无业务意义；统一按不可比较处理（独立找茬中危项 #3）。
    """
    if val is None:
        return None
    try:
        num = float(val)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(num):
        return None
    return num


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
      notcontains — contains 的取反：不区分大小写的 NOT LIKE '%val%'
      eq        — 字符串精确相等
      neq       — 字符串不相等
      gt / lt / gte / lte — 数值比较（尝试转 float，或 ISO 日期比较）
      isempty   — IS NULL OR = ''
      notempty  — IS NOT NULL AND != ''

    注：单一条件匹配逻辑抽取至 _apply_single_filter，供嵌套筛选（filter_rows_nested）
    复用，保证两套入口语义一致（复用优先，FR-014）。
    """
    if not filters:
        return rows
    result = list(rows)
    for col_name, op, q in filters:
        result = _apply_single_filter(result, columns, col_name, op, q)
    return result


def sort_rows(rows: list[tuple], columns: list[str],
              sorts=None) -> list[tuple]:
    """
    在内存中按多字段排序。

    sorts: list[(col, dir), ...]  按优先级从高到低
    使用稳定排序，从最低优先级到最高优先级依次排序。
    调用方应保证 sorts 中无重复列名。
    排序分区见 _ordered_by_column：数值（含数值字符串）按数值序且恒在
    文本之前，文本按字符串序；None 值始终排在最后，不受升降序影响。
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
        result = _ordered_by_column(not_none_part, col_idx, reverse) + none_part
    return result


def _ordered_by_column(part: list[tuple], col_idx: int,
                       reverse: bool) -> list[tuple]:
    """单列分区排序（spec ux-optimization 批次1#1）。

    数值（int/float/Decimal/数值字符串）与文本分成两组：
    - 数值组恒排在文本组之前（不随方向翻转——"数字优先、文本垫底"）；
    - 组内分别按数值大小 / 字符串字典序，受 reverse 控制。
    None 已由 sort_rows 分离，不会出现在 part 中。
    """
    numeric = []
    text = []
    for r in part:
        num = _try_float(r[col_idx])
        if num is not None:
            numeric.append((num, r))
        else:
            text.append((str(r[col_idx]), r))
    numeric.sort(key=lambda pair: pair[0], reverse=reverse)
    text.sort(key=lambda pair: pair[0], reverse=reverse)
    return [r for _, r in numeric] + [r for _, r in text]


# gt / lt / gte / lte — filter_rows 中要求条件值可转 float 的操作符集合
NUMERIC_FILTER_OPS = ("gt", "lt", "gte", "lte")


def invalid_numeric_filters(filters) -> list[tuple]:
    """返回条件值无法转为有限数值的数值比较条目 [(col, op, val), ...]。

    NaN/Inf 同样视为无效（float() 可转但比较无意义，独立找茬中危项 #3）。
    filter_rows 对这类条目静默跳过（既有语义保持不变）；本函数供 Web 报表页
    在渲染前检测被忽略的条件并回传提示。API 与导出路径不调用本函数，
    行为保持不变。
    注意：列名有效性不在检测范围（filter_rows 对未知列同样跳过该条件，
    其提示属后续工作）；本函数只保证「值不是有效数字」的归因成立。
    """
    bad = []
    for col_name, op, q in (filters or []):
        if op not in NUMERIC_FILTER_OPS:
            continue
        try:
            num = float(q)
        except (ValueError, TypeError):
            bad.append((col_name, op, q))
            continue
        if not math.isfinite(num):
            bad.append((col_name, op, q))
    return bad


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


# ---------------------------------------------------------------------------
# 嵌套筛选（NestedFilter）— T-001
# 在现有 filter_rows 的单一条件匹配基础上，支持 and/or 递归条件树，
# 并在 value 字段支持表达式语法（now()/today()/date_add()/...）。
# 全部为纯函数、无 IO、无外部依赖，并复用既有操作符语义（FR-014）。
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_numeric_or_date(s):
    """将值解析为 (num, date)：可转 float → (float, None)；ISO 日期 → (None, date)。

    用于数值/日期操作的统一比较入口；两者皆不可解析 → (None, None)。
    """
    if s is None:
        return (None, None)
    if isinstance(s, bool):
        return (None, None)
    if isinstance(s, (int, float)):
        num = float(s)
        return (num, None) if math.isfinite(num) else (None, None)
    s = str(s).strip()
    if _DATE_RE.match(s):
        try:
            return (None, datetime.date.fromisoformat(s))
        except ValueError:
            return (None, None)
    try:
        num = float(s)
    except (ValueError, TypeError):
        return (None, None)
    return (num, None) if math.isfinite(num) else (None, None)


def _apply_single_filter(result, columns, col_name, op, q):
    """对 result 应用单一筛选条件（与 filter_rows 既有语义一致），返回新列表。

    q 应为已解析的「字面量」——嵌套筛选调用方需先经 resolve_expression 解析
    value 表达式。未知列 / 无法比较的值 → 条件静默跳过（保持 filter_rows 行为）。
    """
    if col_name not in columns:
        return result
    col_idx = columns.index(col_name)

    if op in ("contains", "notcontains", "eq", "neq"):
        segments = parse_filter_expr(q)
        if not segments:
            return result
        regexes = _compile_segments(
            segments, ignorecase=(op in ("contains", "notcontains")))
        if op == "contains":
            return [r for r in result
                    if any(rx.search(_cell_str(r[col_idx])) for rx in regexes)]
        if op == "notcontains":
            return [r for r in result
                    if not any(rx.search(_cell_str(r[col_idx])) for rx in regexes)]
        if op == "eq":
            return [r for r in result
                    if any(rx.fullmatch(_cell_str(r[col_idx])) for rx in regexes)]
        # neq
        return [r for r in result
                if not any(rx.fullmatch(_cell_str(r[col_idx])) for rx in regexes)]

    if op in ("gt", "lt", "gte", "lte"):
        q_num, q_date = _parse_numeric_or_date(q)
        if q_num is None and q_date is None:
            return result
        out = []
        for r in result:
            cell = r[col_idx]
            cell_num, cell_date = _parse_numeric_or_date(cell)
            if q_date is not None and cell_date is not None:
                cmp = (cell_date > q_date) - (cell_date < q_date)
            elif q_num is not None and cell_num is not None:
                cmp = (cell_num > q_num) - (cell_num < q_num)
            else:
                continue  # 类型不可比，跳过该行
            if (op == "gt" and cmp > 0) or (op == "lt" and cmp < 0) \
               or (op == "gte" and cmp >= 0) or (op == "lte" and cmp <= 0):
                out.append(r)
        return out

    if op == "isempty":
        return [r for r in result
                if r[col_idx] is None or str(r[col_idx]).strip() == ""]
    if op == "notempty":
        return [r for r in result
                if r[col_idx] is not None and str(r[col_idx]).strip() != ""]
    # 未知操作符：静默跳过（与 filter_rows 历史行为一致）
    return result


def resolve_expression(value):
    """解析 value 字段中的表达式语法 → 字面量字符串。不区分大小写（统一转小写）。

    支持：
      now() / today()              → 今日日期 YYYY-MM-DD
      yesterday() / tomorrow()    → 昨/明日期
      date_add(base, n, unit)     → 在 base 上偏移 n 个单位
      date_sub(base, n, unit)     → 在 base 上反向偏移 n 个单位
      date('YYYY-MM-DD')          → 字面日期
    base 可为 now()/today()/yesterday()/tomorrow() 或 'YYYY-MM-DD'。
    unit ∈ day/week/month/year（可带 s 复数）。
    非表达式或无法识别 → 原样返回（不报错），交由后续匹配/校验处理。
    """
    if not isinstance(value, str):
        return value
    s = value.strip().lower()
    if s in ("now()", "today()"):
        return datetime.date.today().isoformat()
    if s == "yesterday()":
        return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if s == "tomorrow()":
        return (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    m = re.match(r"date\(\s*'(\d{4}-\d{2}-\d{2})'\s*\)", s)
    if m:
        return m.group(1)

    m = re.match(r"date_add\(\s*(.+?)\s*,\s*(-?\d+)\s*,\s*(\w+)\s*\)", s)
    if m:
        base = _parse_date_base(m.group(1))
        return _shift_date(base, int(m.group(2)), m.group(3)).isoformat()

    m = re.match(r"date_sub\(\s*(.+?)\s*,\s*(-?\d+)\s*,\s*(\w+)\s*\)", s)
    if m:
        base = _parse_date_base(m.group(1))
        return _shift_date(base, -int(m.group(2)), m.group(3)).isoformat()

    return value  # 字面量或无法识别，原样返回


def _parse_date_base(base):
    """解析 date_add/date_sub 的 base 参数 → date。"""
    base = base.strip().strip("'\"").strip()
    if base in ("now()", "today()"):
        return datetime.date.today()
    if base == "yesterday()":
        return datetime.date.today() - datetime.timedelta(days=1)
    if base == "tomorrow()":
        return datetime.date.today() + datetime.timedelta(days=1)
    m = re.match(r"date\(\s*'(\d{4}-\d{2}-\d{2})'\s*\)", base)
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    try:
        return datetime.date.fromisoformat(base)
    except ValueError:
        return datetime.date.today()


def _shift_date(d, n, unit):
    """在日期 d 上偏移 n 个 unit（unit∈day/week/month/year，可带 s）。"""
    unit = unit.rstrip("s")
    if unit == "day":
        return d + datetime.timedelta(days=n)
    if unit == "week":
        return d + datetime.timedelta(weeks=n)
    if unit == "month":
        total = (d.year * 12 + (d.month - 1)) + n
        y, m = divmod(total, 12)
        m += 1
        last = calendar.monthrange(y, m)[1]
        return d.replace(year=y, month=m, day=min(d.day, last))
    if unit == "year":
        return d.replace(year=d.year + n)
    return d


def filter_rows_nested(rows, columns, nested_filter):
    """按嵌套筛选条件树（and/or 递归）在内存中筛选，返回新列表（不修改入参）。

    nested_filter 结构：
      {"op": "and"|"or", "conditions": [节点, ...]}
      节点可为：分组节点（含 op+conditions）或叶节点 {"col", "op", "value"}。
    空 dict / None / 空 conditions → 视为 no-op，返回原全部行（不污染缓存，FR-006）。
    """
    if nested_filter is None or (isinstance(nested_filter, dict) and not nested_filter):
        return list(rows)
    return _eval_node(list(rows), columns, nested_filter)


def _eval_node(rows, columns, node):
    """递归求值单个条件节点。rows 为本节点作用域内的候选行。"""
    if not isinstance(node, dict):
        return list(rows)
    op = (node.get("op") or "").lower()
    if op in ("and", "or"):
        conditions = node.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            return list(rows)  # 空分组：no-op
        if op == "and":
            result = list(rows)
            for c in conditions:
                result = _eval_node(result, columns, c)
            return result
        # or：对原始候选行分别求值后取并集（按对象身份去重）
        seen = set()
        out = []
        for c in conditions:
            for r in _eval_node(list(rows), columns, c):
                if id(r) not in seen:
                    seen.add(id(r))
                    out.append(r)
        return out
    # 叶节点：具体筛选条件
    col = node.get("col")
    cop = node.get("op")
    val = node.get("value")
    if col is None or cop is None:
        return list(rows)
    resolved = resolve_expression(val) if isinstance(val, str) else val
    return _apply_single_filter(list(rows), columns, col, cop, resolved)


# 嵌套筛选支持的叶节点操作符集合
_NESTED_LEAF_OPS = ("contains", "notcontains", "eq", "neq",
                    "gt", "lt", "gte", "lte", "isempty", "notempty")


def validate_nested_filter(nested_filter, available_columns=None):
    """校验嵌套筛选 JSON 结构，返回 {'valid': bool, 'errors': [...]}。

    errors 每项：{'path', 'message', 'suggestion'}——指明问题条件位置、原因，
    并基于实际输入给出修正建议（FR-012，假设用户无编程基础）。
    available_columns：可选列名白名单；提供时检测非法列名并给出可用列名建议。
    """
    errors = []

    def walk(node, path):
        if not isinstance(node, dict):
            errors.append({
                "path": path,
                "message": "条件节点必须是对象（{...}）",
                "suggestion": "请检查该条件是否为合法 JSON 对象，例如 {\"col\":\"姓名\",\"op\":\"contains\",\"value\":\"张\"}",
            })
            return
        op = node.get("op")
        if op in ("and", "or"):
            conds = node.get("conditions")
            if not isinstance(conds, list) or not conds:
                errors.append({
                    "path": path + ".conditions",
                    "message": f"\"{op}\" 分组必须包含非空的 conditions 数组",
                    "suggestion": f"请在 \"{op}\" 下至少添加一个条件，例如 \"conditions\": [{{\"col\":\"姓名\",\"op\":\"contains\",\"value\":\"张\"}}]",
                })
                return
            for i, c in enumerate(conds):
                walk(c, f"{path}.conditions[{i}]")
            return
        # 叶节点
        col = node.get("col")
        if col is None or (isinstance(col, str) and col.strip() == ""):
            errors.append({
                "path": path,
                "message": "筛选条件缺少必填字段 col（列名）",
                "suggestion": "请添加 \"col\": \"列名\"；" + (
                    "可用列名：" + ", ".join(available_columns) if available_columns
                    else "列名即报表中的字段名，如「姓名」「年龄」"),
            })
        elif available_columns is not None and col not in available_columns:
            errors.append({
                "path": path + ".col",
                "message": f"列名不存在：{col}",
                "suggestion": "请使用报表中真实存在的列名；可用列名：" + ", ".join(available_columns),
            })
        cop = node.get("op")
        if cop is None or (isinstance(cop, str) and cop.strip() == ""):
            errors.append({
                "path": path,
                "message": "筛选条件缺少必填字段 op（操作符）",
                "suggestion": "请添加 \"op\": \"contains\"；支持的操作符：" + ", ".join(_NESTED_LEAF_OPS),
            })
        elif cop not in _NESTED_LEAF_OPS:
            errors.append({
                "path": path + ".op",
                "message": f"不支持的操作符：{cop}",
                "suggestion": "请使用支持的操作符：" + ", ".join(_NESTED_LEAF_OPS),
            })
        else:
            # 校验 value（isempty/notempty 无需 value）
            if cop not in ("isempty", "notempty"):
                val = node.get("value")
                resolved = resolve_expression(val) if isinstance(val, str) else val
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    errors.append({
                        "path": path + ".value",
                        "message": "筛选条件缺少必填字段 value（值）",
                        "suggestion": f"请为操作符 {cop} 提供 value，例如 \"value\": \"张\" 或 \"value\": \"date_add(now(),7,day)\"",
                    })
                elif cop in ("gt", "lt", "gte", "lte") \
                        and _parse_numeric_or_date(resolved) == (None, None):
                    errors.append({
                        "path": path + ".value",
                        "message": f"数值/日期操作符 {cop} 的值无法解析为数字或日期：{val}",
                        "suggestion": "请改为数字（如 30）或日期表达式（如 date_add(now(),7,day) / date('2026-02-01')）",
                    })
                # contains/eq/neq 接受任意字符串值，无需数值校验

    walk(nested_filter, "$")
    return {"valid": len(errors) == 0, "errors": errors}


def column_indices(display_cols: list[str], all_columns: list[str]) -> list[int]:
    """将显示列列表映射为在 all_columns 中的索引列表（调用方保证列存在）。"""
    index_map = {name: idx for idx, name in enumerate(all_columns)}
    return [index_map[c] for c in display_cols]
