"""
result_transform.py — 结果集变换模块（纯函数，无 IO）

职责：
- 对已取回的结果集（rows + columns）执行内存变换：筛选、排序、列选择、列索引映射
- 报表页面（report.py）、导出（export.py）、API（api_handler.py）三处调用方共用
- 不感知数据来源（MySQL / Redis / 静态文件），不负责分页语义（调用方协议）

领域约定（三处调用方一致，勿单边修改）：
- 筛选操作符：contains / eq / neq / gt / lt / gte / lte / isempty / notempty
- 排序：稳定排序，None 值始终在最后，不受升降序影响
- 列选择：仅保留存在且不重复的列（保序）；空请求或全部无效时回退全部列
"""

# ---------------------------------------------------------------------------


def _try_float(val):
    """尝试将值转为 float，失败返回 None"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


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

        if op == "contains":
            q_lower = q.lower()
            result = [
                r for r in result
                if q_lower in str(r[col_idx] if r[col_idx] is not None else "").lower()
            ]
        elif op == "eq":
            result = [
                r for r in result
                if str(r[col_idx] if r[col_idx] is not None else "") == q
            ]
        elif op == "neq":
            result = [
                r for r in result
                if str(r[col_idx] if r[col_idx] is not None else "") != q
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
