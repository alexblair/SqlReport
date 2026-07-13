"""
report.py — 报表页面处理

职责：
- 报表选择（根据配置显示下拉列表）
- 缓存原始 SQL 查询结果，避免重复查询数据库
- 在缓存结果上执行**多字段**内存排序、**多字段**模糊筛选、分页
- 完整分页控制（显示总页数、跳转任意页）

URL 路由：
  GET /report                       → 报表选择页
  GET /report?id=N                  → 展示第 N 个报表的第一页
  GET /report?id=N&page=P           → 第 P 页
  GET /report?id=N&sort=COL&dir=asc → 按 COL 单列排序
  GET /report?id=N&sort=C1&dir=asc&sort=C2&dir=desc → 多列排序
  GET /report?id=N&f_name=alice     → name 列模糊筛选
  GET /report?id=N&f_name=alice&f_age=30 → 多字段同时筛选
  GET /report?id=N&refresh=1        → 强制刷新缓存
  POST /report/preview              → 预览模式：不保存配置，临时以 POST 表单中的 SQL 查看

兼容旧格式：
  GET /report?id=N&f_col=name&f_q=alice →（自动转为 f_name=alice）
"""

import urllib.parse
import math
import time
from decimal import Decimal
import db
import html as html_mod
from typing import Optional

# ===================================================================
# 筛选操作符定义
# ===================================================================

FILTER_OPS = [
    ("nofilter", "不筛选", "不筛选"),
    ("contains", "包含", "包含"),
    ("eq",       "等于",   "="),
    ("neq",      "不等于", "≠"),
    ("gt",       "大于",   ">"),
    ("lt",       "小于",   "<"),
    ("gte",      "大于等于", "≥"),
    ("lte",      "小于等于", "≤"),
    ("isempty",  "为空",   "为空"),
    ("notempty", "非空",   "非空"),
]
_OP_MAP: dict[str, tuple[str, str]] = {
    code: (label, short) for code, label, short in FILTER_OPS
}
DEFAULT_OP = "contains"


# ===================================================================
# 缓存
# ===================================================================


class CachedResult:
    """单次报表查询的缓存结果，保存原始 SQL 返回的全量数据（支持多结果集）。"""

    __slots__ = ("results", "sql_query", "timestamp")

    def __init__(self, results: list[dict], sql_query: str):
        """
        results: [{"columns": [...], "rows": [...]}, ...]
        """
        self.results = results
        self.sql_query = sql_query
        self.timestamp = time.time()


class QueryCache:
    """
    报表查询结果缓存。

    将原始 SQL 查询结果（全量行）保存在内存中，后续的排序/筛选/分页
    均在缓存数据上操作，避免对 MySQL 数据库产生重复压力。
    """

    def __init__(self, ttl: int = 300):
        """ttl: 缓存有效期（秒），默认 5 分钟"""
        self._cache: dict[int, CachedResult] = {}
        self._ttl = ttl

    def get(self, report_id: int,
            sql_query: str = None) -> CachedResult | None:
        cached = self._cache.get(report_id)
        if cached is None:
            return None
        if time.time() - cached.timestamp > self._ttl:
            del self._cache[report_id]
            return None
        if sql_query is not None and cached.sql_query != sql_query:
            del self._cache[report_id]
            return None
        return cached

    def set(self, report_id: int, results: list[dict],
            sql_query: str) -> None:
        self._cache[report_id] = CachedResult(results, sql_query)

    def invalidate(self, report_id: int) -> None:
        self._cache.pop(report_id, None)

    def clear(self) -> None:
        self._cache.clear()


# 全局缓存实例
_query_cache = QueryCache()


# ===================================================================
# 多字段排序/筛选工具
# ===================================================================


def _safe_sort_key(val):
    """安全的排序键：None 始终在最后，其余转字符串比较"""
    if val is None:
        return (1, '')
    return (0, str(val))


def _filter_rows(rows: list[tuple], columns: list[str],
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


def _try_float(val):
    """尝试将值转为 float，失败返回 None"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _sort_rows(rows: list[tuple], columns: list[str],
               sorts=None) -> list[tuple]:
    """
    在内存中按多字段排序。

    sorts: list[(col, dir), ...]  按优先级从高到低
    使用稳定排序，从最低优先级到最高优先级依次排序。
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
        result = sorted(result, key=lambda r, c=col_idx: _safe_sort_key(r[c]),
                        reverse=reverse)
    return result


# ===================================================================
# URL 参数工具
# ===================================================================


def _filter_hidden_inputs(filters) -> str:
    """生成筛选参数的隐藏 input 标签（含操作符）"""
    parts = []
    for col, op, val in filters:
        if op == "nofilter":
            continue
        fk = urllib.parse.quote(col, safe='')
        parts.append(f'<input type="hidden" name="f_{fk}" value="{_escape(val)}">')
        if op != DEFAULT_OP:
            ok = urllib.parse.quote(col, safe='')
            parts.append(f'<input type="hidden" name="op_{ok}" value="{_escape(op)}">')
    return "".join(parts)


def _build_filter_params(filters, skip_col=None):
    """
    将 filters 列表编码为 URL 查询字符串（f_{col}=value & op_{col}=op）。

    若指定 skip_col，则跳过该列的 filter 项（用于生成某列自己的排序链接时）。
    filters: list[(col, op, val), ...]
    """
    parts = []
    for col, op, val in filters:
        if op == "nofilter":
            continue
        if skip_col is not None and col == skip_col:
            continue
        fk = "f_" + urllib.parse.quote(col, safe='')
        parts.append(f"{fk}={urllib.parse.quote(val, safe='')}")
        if op != DEFAULT_OP:
            ok = "op_" + urllib.parse.quote(col, safe='')
            parts.append(f"{ok}={urllib.parse.quote(op, safe='')}")
    return "&".join(parts)


def _build_sort_params(sorts):
    """将 sorts 列表编码为 URL 查询字符串（sort=col&dir=asc 重复）。"""
    parts = []
    for col, dir_ in sorts:
        parts.append(f"sort={urllib.parse.quote(col, safe='')}&dir={urllib.parse.quote(dir_, safe='')}")
    return "&".join(parts)


def parse_filters(qs):
    """
    从 parse_qs 结果中解析多字段筛选参数。

    新格式（推荐）：
      f_{col}=value    筛选值
      op_{col}=op      操作符（缺省为 contains）
      例：f_age=100&op_age=gt   → age > 100
          f_name=alice           → name 包含 alice

    旧格式（兼容）：
      f_col=name&f_q=alice（仅单字段有效）

    返回 list[(col, op, val), ...]
    """
    # 第一步：收集筛选值 f_{col}=val
    f_values: dict[str, str] = {}
    excl = frozenset(("f_col", "f_q", "filters"))
    for key, values in qs.items():
        if not key.startswith("f_") or key in excl:
            continue
        colname = urllib.parse.unquote(key[2:])
        if values and values[0]:
            f_values[colname] = values[0]

    # 第二步：收集操作符 op_{col}=op
    op_values: dict[str, str] = {}
    for key, values in qs.items():
        if not key.startswith("op_") or key in ("op_col", "op_q"):
            continue
        colname = urllib.parse.unquote(key[3:])
        if values and values[0] in _OP_MAP:
            op_values[colname] = values[0]

    # 旧格式兼容
    if not f_values:
        f_cols = qs.get("f_col", [])
        f_qs = qs.get("f_q", [])
        for c, q in zip(f_cols, f_qs):
            if q:
                f_values[c] = q

    filters = []
    for col, val in f_values.items():
        op = op_values.get(col, DEFAULT_OP)
        filters.append((col, op, val))
    # 单独的操作符也需要输出（如 isempty/notempty 可能无值）
    for col, op in op_values.items():
        if col not in f_values and op != "nofilter":
            filters.append((col, op, ""))
    filters = [(c, o, v) for c, o, v in filters if o != "nofilter"]
    return filters


_parse_filters = parse_filters  # 向后兼容别名


def _parse_sorts(qs):
    """
    从 parse_qs 结果中解析多字段排序参数。

    格式：sort=col1&dir=asc&sort=col2&dir=desc  (repeated)
    返回 list[(col, dir), ...]
    """
    sorts = list(zip(qs.get("sort", []), qs.get("dir", [])))
    return [(c, d) for c, d in sorts if d in ("asc", "desc")]


def _parse_cols(qs, all_columns: list[str]) -> list[str]:
    """
    从 parse_qs 结果中解析自定义列顺序参数。

    格式：cols=col1,col2,col3
    返回实际要显示的列名列表（按用户指定顺序）。
    仅保留 all_columns 中存在的列名，忽略无效列名。
    若未传 cols 参数或为空，返回 all_columns（默认显示全部）。
    """
    cols_raw = qs.get("cols", [])
    if not cols_raw or not cols_raw[0]:
        return list(all_columns)
    requested = [urllib.parse.unquote(c) for c in cols_raw[0].split(",")]
    valid_set = set(all_columns)
    seen = set()
    result = []
    for c in requested:
        if c in valid_set and c not in seen:
            result.append(c)
            seen.add(c)
    return result if result else list(all_columns)


def _build_cols_param(display_columns: list[str], all_columns: list[str]) -> str:
    """
    构建 cols URL 查询参数字符串。
    仅在用户自定义了列顺序或隐藏了列时生成参数，否则返回空字符串。
    """
    if display_columns == list(all_columns):
        return ""
    return "cols=" + urllib.parse.quote(",".join(display_columns), safe='')


def _format_cell(val) -> str:
    """
    格式化表格单元格值。

    - Decimal：避免科学计数法（如 0E-10 → 0）
    - float：如果 str() 产生科学计数法，重新格式化为全小数形式
    - None：返回空字符串
    - 其余：str() 原样输出
    """
    if val is None:
        return ""
    if isinstance(val, Decimal):
        if val == 0:
            return "0"
        s = format(val, "f")
    elif isinstance(val, float):
        s = str(val)
        # float 的 str() 可能产生科学计数法（如 1e-10），重新格式化为全小数
        if "e" in s or "E" in s:
            s = f"{val:.15f}"
    else:
        return str(val)
    # 去除尾部多余的 0 和小数点
    if "." in s:
        s = s.rstrip("0").rstrip(".")
        if s == "-0" or s == "":
            s = "0"
    return s


def _escape(val) -> str:
    """HTML 转义（自动格式化数值避免科学计数法）"""
    return html_mod.escape(_format_cell(val))


def _qs_val(qs: dict, key: str, default: str = None) -> Optional[str]:
    """从 parse_qs 结果中安全取第一个值"""
    vals = qs.get(key, [])
    return vals[0] if vals else default


# ===================================================================
# HTML 模板（CSS）
# ===================================================================

_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: #f1f5f9; color: #1e293b; min-height: 100vh;
  }
  .navbar {
    background: linear-gradient(135deg, #1e293b, #334155);
    padding: 0 24px; height: 60px; display: flex; align-items: center; gap: 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12); position: sticky; top: 0; z-index: 100;
  }
  .navbar .brand { color: #fff; font-size: 18px; font-weight: 700; letter-spacing: -0.3px; text-decoration: none; }
  .navbar .brand span { color: #818cf8; }
  .navbar a:not(.brand) {
    color: #cbd5e1; text-decoration: none; font-size: 14px; font-weight: 500;
    padding: 6px 14px; border-radius: 6px; transition: background 0.2s, color 0.2s;
  }
  .navbar a:not(.brand):hover { background: rgba(255,255,255,0.1); color: #fff; }
  .navbar .nav-active { color: #fff !important; background: rgba(255,255,255,0.12); }
  .navbar .spacer { flex: 1; }
  .container { max-width: 100%; margin: 0 auto; padding: 24px 5px; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); padding: 24px; margin-bottom: 20px; animation: fadeUp 0.3s ease-out; }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  h2 { font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 16px; letter-spacing: -0.3px; }
  h3 { font-size: 16px; font-weight: 600; color: #334155; margin-bottom: 12px; }
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 600;
    text-decoration: none; cursor: pointer; transition: all 0.15s; border: none;
  }
  .btn-primary { background: #4f46e5; color: #fff; box-shadow: 0 2px 8px rgba(79,70,229,0.3); }
  .btn-primary:hover { background: #4338ca; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(79,70,229,0.35); }
  .btn-success { background: #059669; color: #fff; box-shadow: 0 2px 8px rgba(5,150,105,0.3); }
  .btn-success:hover { background: #047857; transform: translateY(-1px); }
  .btn-outline { background: transparent; color: #475569; border: 1px solid #e2e8f0; }
  .btn-outline:hover { background: #f8fafc; border-color: #cbd5e1; }
  .btn-sm { padding: 5px 12px; font-size: 13px; }
  table {
    border-collapse: separate; border-spacing: 0; width: 100%; font-size: 14px;
  }
  th {
    background: #f8fafc; color: #475569; font-weight: 600; font-size: 13px;
    text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 14px 6px;
    border-bottom: 2px solid #e2e8f0; text-align: left; white-space: nowrap; vertical-align: bottom;
  }
  th .sort-link {
    color: #475569; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;
    transition: color 0.15s; cursor: pointer;
  }
  th .sort-link:hover { color: #4f46e5; }
  th .sort-arrow { font-size: 12px; color: #94a3b8; }
  th .sort-arrow.active { color: #4f46e5; }
  th .filter-input {
    display: block; width: 100%; margin-top: 6px; padding: 4px 8px;
    border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px;
    font-weight: 400; text-transform: none; letter-spacing: 0;
    outline: none; transition: border-color 0.2s; background: #fff;
    box-sizing: border-box;
  }
  th .filter-input:focus { border-color: #4f46e5; box-shadow: 0 0 0 2px rgba(79,70,229,0.12); }
  th .filter-input::placeholder { color: #cbd5e1; }
  td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; text-align: left; white-space: nowrap; }
  tbody tr:hover { background: #f8fafc; }
  tbody tr:last-child td { border-bottom: none; }
  .table-wrap {
    overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px;
  }
  .empty-state {
    text-align: center; color: #94a3b8; padding: 48px 14px; font-size: 15px;
  }
  .empty-state .icon { font-size: 40px; margin-bottom: 12px; opacity: 0.5; }
  .flash {
    padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;
    font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 10px;
  }
  .flash-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
  .flash-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
  .flash-info { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
  .debug-info {
    background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;
    margin-bottom: 16px; font-size: 13px; color: #64748b;
    word-break: break-all; line-height: 1.6;
  }
  .debug-info code {
    background: #e9ecef; padding: 2px 6px; border-radius: 4px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px; color: #334155;
  }
  .debug-info pre {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px; color: #334155;
  }
  .debug-toggle {
    display:inline-flex; align-items:center; gap:4px; font-size:12px;
    color:#94a3b8; cursor:pointer; background:none; border:1px solid #e2e8f0;
    border-radius:6px; padding:4px 10px; margin-bottom:8px; transition:color 0.15s;
  }
  .debug-toggle:hover { color:#475569; background:#f1f5f9; }
  .debug-content { padding: 0 16px 12px; }
  .debug-content.hidden { display: none; }
  .sql-hl-keyword { font-weight:700; color:#7c3aed; }
  .sql-hl-string { color:#059669; }
  .sql-hl-number { color:#d97706; }
  .sql-hl-comment { color:#94a3b8; font-style:italic; }
  .sql-hl-function { font-weight:600; color:#2563eb; }
  .pagination { display: flex; align-items: center; gap: 4px; margin: 16px 0 0; flex-wrap: wrap; }
  .pagination a, .pagination .page-btn, .pagination .page-span {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 36px; height: 36px; padding: 0 10px; border-radius: 8px;
    font-size: 14px; text-decoration: none; color: #475569; transition: all 0.15s;
  }
  .pagination a { background: #fff; border: 1px solid #e2e8f0; }
  .pagination a:hover { background: #f1f5f9; border-color: #cbd5e1; }
  .pagination .active { background: #4f46e5 !important; color: #fff !important; border-color: #4f46e5 !important; font-weight: 600; }
  .pagination .disabled { color: #cbd5e1; background: transparent; border: none; cursor: default; }
  .controls {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 14px 16px; background: #f8fafc; border-radius: 8px; margin-bottom: 16px;
    border: 1px solid #e2e8f0;
  }
  .controls label { font-size: 14px; color: #475569; font-weight: 500; display: inline-flex; align-items: center; gap: 8px; }
  .controls select {
    padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
    font-size: 14px; color: #1e293b; background: #fff; outline: none;
    cursor: pointer; transition: border-color 0.2s;
  }
  .controls select:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.12); }
  .controls .stat { font-size: 14px; color: #64748b; margin-left: auto; }
  .controls .cache-badge {
    font-size: 12px; color: #64748b; background: #e9ecef; padding: 2px 10px;
    border-radius: 99px; white-space: nowrap;
  }
  .controls .cache-badge.fresh { background: #dcfce7; color: #166534; }
  .btn-refresh {
    display:inline-flex; align-items:center; gap:4px; padding:6px 14px;
    font-size:13px; font-weight:600; border-radius:6px; cursor:pointer;
    background:#f0f0f0; color:#475569; border:1px solid #cbd5e1;
    text-decoration:none; transition:background 0.2s, color 0.2s;
  }
  .btn-refresh:hover { background:#e2e8f0; color:#1e293b; }
  .report-select { max-width: 500px; }
  .report-select label { font-size: 15px; color: #334155; font-weight: 500; display: block; margin-bottom: 8px; }
  .report-select select {
    width: 100%; padding: 10px 14px; border: 2px solid #e2e8f0; border-radius: 8px;
    font-size: 15px; color: #1e293b; outline: none; cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s; background: #fff;
    appearance: auto;
  }
  .report-select select:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.15); }
  .report-list { list-style: none; padding: 0; margin-top: 4px; }
  .report-list li { padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
  .report-list li:last-child { border-bottom: none; }
  .report-list a {
    color: #4f46e5; text-decoration: none; font-weight: 500; font-size: 15px;
    transition: color 0.15s; display: flex; align-items: center; gap: 8px;
  }
  .report-list a:hover { color: #4338ca; }
  .report-list a::before { content: "→"; color: #94a3b8; font-weight: 400; }
  .jump-box { display: inline-flex; align-items: center; gap: 6px; margin-left: 16px; }
  .jump-box input {
    width: 64px; padding: 6px 8px; border: 1px solid #e2e8f0; border-radius: 6px;
    font-size: 14px; text-align: center; outline: none; transition: border-color 0.2s;
  }
  .jump-box input:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.12); }
  .clear-filter {
    display: inline-block; margin-left: 8px; font-size: 12px; color: #94a3b8;
    text-decoration: none; cursor: pointer;
  }
  .clear-filter:hover { color: #dc2626; }
"""

_PAGE_HEADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web 报表工具</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="navbar">
  <a href="/report" class="brand">My<span>Report</span></a>
  <div class="spacer"></div>
  <a href="/report" class="nav-active">报表页</a>
  <a href="/config">配置管理</a>
  <a href="/logout">退出</a>
</div>
<div class="container">
"""

_FOOTER = r"""</div>
<script>
function toggleSection(btn, label) {
  var content = btn.nextElementSibling;
  var hidden = content.classList.toggle("hidden");
  btn.textContent = hidden ? "▶ " + label : "▼ " + label;
}
function toggleFilterInput(inputName, select) {
  var input = document.getElementsByName(inputName)[0];
  if (!input) return;
  var val = select.value;
  if (val === 'nofilter' || val === 'isempty' || val === 'notempty') {
    input.style.display = 'none';
    input.disabled = true;
  } else {
    input.style.display = '';
    input.disabled = false;
  }
}
function toggleFieldItem(checkbox) {
  var label = checkbox.closest('.field-item');
  if (label) {
    label.style.background = checkbox.checked ? '#f8fafc' : '#fff';
  }
}
function moveField(btn, dir) {
  var item = btn.closest('.field-item');
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  var idx = items.indexOf(item);
  var target = idx + dir;
  if (target < 0 || target >= items.length) return;
  if (dir === -1) {
    list.insertBefore(item, items[target]);
  } else {
    list.insertBefore(item, items[target].nextSibling);
  }
  updateMoveButtons();
}
function updateMoveButtons() {
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  items.forEach(function(item, i) {
    var up = item.querySelector('.field-up');
    var down = item.querySelector('.field-down');
    if (up) up.disabled = (i === 0);
    if (down) down.disabled = (i === items.length - 1);
  });
}
function selectAllFields(checked) {
  var list = document.getElementById('fieldList');
  var checkboxes = list.querySelectorAll('input[type="checkbox"]');
  checkboxes.forEach(function(cb) {
    cb.checked = checked;
    toggleFieldItem(cb);
  });
}
function applyFieldSettings() {
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  var cols = [];
  items.forEach(function(item) {
    var cb = item.querySelector('input[type="checkbox"]');
    if (cb && cb.checked) {
      var colInput = item.querySelector('input[name="col_order"]');
      if (colInput) cols.push(colInput.value);
    }
  });
  var reportId = new URLSearchParams(window.location.search).get('id');
  var pageSize = new URLSearchParams(window.location.search).get('page_size') || '';
  var resultIdx = new URLSearchParams(window.location.search).get('result') || '';
  var sorts = [];
  var filters = [];
  var params = new URLSearchParams(window.location.search);
  params.forEach(function(val, key) {
    if (key === 'sort') sorts.push(val);
    if (key === 'dir') sorts.push(val);
    if (key.startsWith('f_')) filters.push({key: key, val: val});
    if (key.startsWith('op_')) filters.push({key: key, val: val});
  });
  var url = '/report?id=' + reportId;
  if (pageSize) url += '&page_size=' + pageSize;
  if (resultIdx) url += '&result=' + encodeURIComponent(resultIdx);
  for (var i = 0; i < sorts.length; i += 2) {
    url += '&sort=' + encodeURIComponent(sorts[i]) + '&dir=' + encodeURIComponent(sorts[i+1]);
  }
  filters.forEach(function(f) {
    url += '&' + f.key + '=' + encodeURIComponent(f.val);
  });
  if (cols.length > 0 && cols.length < items.length) {
    url += '&cols=' + encodeURIComponent(cols.join(','));
  }
  window.location.href = url;
}
var _dragSrcEl = null;
function initDragHandlers() {
  var list = document.getElementById('fieldList');
  if (!list) return;
  list.addEventListener('dragstart', function(e) {
    var item = e.target.closest('.field-item');
    if (!item) return;
    _dragSrcEl = item;
    item.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
  });
  list.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    var item = e.target.closest('.field-item');
    if (!item || item === _dragSrcEl) return;
    var rect = item.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;
    if (e.clientY < midY) {
      list.insertBefore(_dragSrcEl, item);
    } else {
      list.insertBefore(_dragSrcEl, item.nextSibling);
    }
  });
  list.addEventListener('dragend', function(e) {
    if (_dragSrcEl) {
      _dragSrcEl.style.opacity = '';
      _dragSrcEl = null;
    }
    updateMoveButtons();
  });
}
document.addEventListener('DOMContentLoaded', function() {
  initDragHandlers();
  initSortDragHandlers();
});

function initSortDragHandlers() {
  var list = document.getElementById('sortList');
  if (!list) return;
  list.addEventListener('dragstart', function(e) {
    var item = e.target.closest('.sort-item');
    if (!item) return;
    _dragSrcEl = item;
    item.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
  });
  list.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    var item = e.target.closest('.sort-item');
    if (!item || item === _dragSrcEl) return;
    var rect = item.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;
    if (e.clientY < midY) {
      list.insertBefore(_dragSrcEl, item);
    } else {
      list.insertBefore(_dragSrcEl, item.nextSibling);
    }
  });
  list.addEventListener('dragend', function(e) {
    if (_dragSrcEl) {
      _dragSrcEl.style.opacity = '';
      _dragSrcEl = null;
    }
    updateSortMoveButtons();
  });
}

// ---- 排序管理面板 ----
function moveSortItem(btn, dir) {
  var item = btn.closest('.sort-item');
  var list = document.getElementById('sortList');
  if (!list || !item) return;
  var items = Array.from(list.children);
  var idx = items.indexOf(item);
  var target = idx + dir;
  if (target < 0 || target >= items.length) return;
  list.insertBefore(item, dir === -1 ? items[target] : items[target].nextSibling);
  updateSortMoveButtons();
}
function updateSortMoveButtons() {
  var list = document.getElementById('sortList');
  if (!list) return;
  var items = Array.from(list.children);
  items.forEach(function(item, i) {
    var up = item.querySelector('.sort-up');
    var down = item.querySelector('.sort-down');
    var num = item.querySelector('.sort-num');
    if (up) up.disabled = (i === 0);
    if (down) down.disabled = (i === items.length - 1);
    if (num) num.textContent = i + 1;
  });
}
function removeSortItem(btn) {
  var item = btn.closest('.sort-item');
  if (item) item.parentNode.removeChild(item);
  updateSortMoveButtons();
}
function addSortItem() {
  var col = document.getElementById('newSortCol').value;
  var dir = document.getElementById('newSortDir').value;
  if (!col) return;
  var list = document.getElementById('sortList');
  var existing = Array.from(list.querySelectorAll('input[name="sort_col"]')).some(function(inp) {
    return inp.value === col;
  });
  if (existing) return;
  var div = document.createElement('div');
  div.className = 'sort-item';
  div.draggable = true;
  div.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;background:#f8fafc;cursor:grab;user-select:none';
  var icon = dir === 'asc' ? '↑' : '↓';
  div.innerHTML = '<span class="drag-handle" style="color:#94a3b8;font-size:14px;cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
    + '<span class="sort-num" style="font-weight:700;font-size:11px;color:#4f46e5;min-width:20px">' + (list.children.length + 1) + '</span>'
    + '<span style="flex:1;font-size:13px;color:#1e293b">' + col + ' ' + icon + '</span>'
    + '<input type="hidden" name="sort_col" value="' + col + '">'
    + '<input type="hidden" name="sort_dir" value="' + dir + '">'
    + '<button type="button" class="sort-up" onclick="moveSortItem(this,-1)" style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff;color:#475569">▲</button>'
    + '<button type="button" class="sort-down" onclick="moveSortItem(this,1)" style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff;color:#475569">▼</button>'
    + '<button type="button" onclick="removeSortItem(this)" style="padding:2px 6px;font-size:11px;border:none;border-radius:4px;cursor:pointer;background:transparent;color:#dc2626">✕</button>';
  list.appendChild(div);
  updateSortMoveButtons();
  document.getElementById('newSortCol').value = '';
}
function applySortSettings() {
  var list = document.getElementById('sortList');
  var items = Array.from(list.children);
  var sorts = [];
  items.forEach(function(item) {
    var colInput = item.querySelector('input[name="sort_col"]');
    if (!colInput) return;
    sorts.push({col: colInput.value, dir: item.querySelector('input[name="sort_dir"]').value});
  });
  var reportId = new URLSearchParams(window.location.search).get('id');
  var pageSize = new URLSearchParams(window.location.search).get('page_size') || '';
  var resultIdx = new URLSearchParams(window.location.search).get('result') || '';
  var cols = new URLSearchParams(window.location.search).get('cols') || '';
  var url = '/report?id=' + reportId;
  if (pageSize) url += '&page_size=' + pageSize;
  if (resultIdx) url += '&result=' + encodeURIComponent(resultIdx);
  sorts.forEach(function(s) {
    url += '&sort=' + encodeURIComponent(s.col) + '&dir=' + encodeURIComponent(s.dir);
  });
  var params = new URLSearchParams(window.location.search);
  params.forEach(function(val, key) {
    if (key.startsWith('f_') || key.startsWith('op_')) {
      url += '&' + key + '=' + encodeURIComponent(val);
    }
  });
  if (cols) url += '&cols=' + encodeURIComponent(cols);
  window.location.href = url;
}
function switchResult(sel) {
  var rid = sel.dataset.reportId;
  var currIdx = parseInt(sel.dataset.activeIndex);
  var targetIdx = parseInt(sel.value);
  var swi = sel.dataset.swi;
  var ps = sel.dataset.pageSize;
  var so = sel.dataset.sqlOverride;
  if (targetIdx === currIdx) return;
  var key = 'rstate_' + rid;
  sessionStorage.setItem(key + '_' + currIdx, window.location.href);
  var saved = sessionStorage.getItem(key + '_' + targetIdx);
  if (saved) {
    window.location.href = saved;
  } else {
    var base = '/' + swi + '?id=' + rid + '&page_size=' + ps;
    if (so) base += '&sql_query=' + encodeURIComponent(so);
    base += '&result=' + targetIdx;
    window.location.href = base;
  }
}
// ---- SQL 格式化与高亮 ----
function h(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function highlight(txt) {
  var s = txt.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
  var kw = 'SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN|EXISTS|AS|ON|JOIN|INNER|OUTER|LEFT|RIGHT|CROSS|FULL|NATURAL|USING|GROUP|BY|HAVING|ORDER|ASC|DESC|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|DROP|ALTER|ADD|COLUMN|INDEX|UNIQUE|PRIMARY|KEY|FOREIGN|REFERENCES|CASCADE|DEFAULT|DISTINCT|COUNT|SUM|AVG|MIN|MAX|CASE|WHEN|THEN|ELSE|END|UNION|ALL|EXCEPT|INTERSECT|WITH|RECURSIVE|REPLACE|TRUNCATE|EXPLAIN|DESCRIBE|SHOW|USE|DATABASE|IF|EXISTS|GRANT|REVOKE';
  var re = new RegExp(
    "('(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\")|" +
    "(--[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/)|" +
    "\\b(\\d+(?:\\.\\d+)?)\\b|" +
    "\\b(" + kw + ")\\b|" +
    "\\b(\\w+)\\s*\\(",
    "gi"
  );
  return s.replace(re, function(m, str, cmt, num, kw, fn) {
    if (str) return '<span class="sql-hl-string">' + str + '</span>';
    if (cmt) return '<span class="sql-hl-comment">' + cmt + '</span>';
    if (num) return '<span class="sql-hl-number">' + num + '</span>';
    if (kw) return '<span class="sql-hl-keyword">' + kw + '</span>';
    if (fn)  return '<span class="sql-hl-function">' + fn + '</span>';
    return m;
  });
}
function fmt(t) {
  if (!t || !t.trim()) return t;
  var s = t.replace(/\s*;\s*$/,""), lines = [], indent = 0, clauseCount = 0;
  var parts = s.split(/\b(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|CROSS\s+JOIN|FULL\s+JOIN|NATURAL\s+JOIN|INSERT\s+INTO|DELETE\s+FROM|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE|GROUP\s+BY|ORDER\s+BY|UNION\s+ALL|SELECT|FROM|WHERE|JOIN|ON|AND|OR|GROUP|BY|HAVING|ORDER|LIMIT|OFFSET|UNION|VALUES|SET|CASE|WHEN|THEN|ELSE|END|INTO)\b/i);
  for (var i = 0; i < (parts ? parts.length : 0); i++) {
    var p = parts[i];
    if (!p || !p.trim()) continue;
    var w = p.trim(), u = w.toUpperCase();
    function pad() {
      if (indent === 0) return "";
      if (indent === 1) return "  ";
      return Array(indent + 1).join("  ");
    }
    if (u === "SELECT") { indent = indent === 0 ? 1 : (clauseCount > 0 && indent++); lines.push(pad() + "SELECT"); indent = 2; clauseCount++; }
    else if (u === "FROM" || u === "INNER JOIN" || u === "LEFT JOIN" || u === "RIGHT JOIN" || u === "CROSS JOIN" || u === "FULL JOIN" || u === "NATURAL JOIN" || u === "JOIN") { indent = Math.max(1, indent - 1); lines.push(pad() + w); indent = 2; }
    else if (u === "ON") { lines.push(pad() + w); indent = 2; }
    else if (u === "WHERE") { indent = Math.max(1, indent - 1); lines.push(pad() + "WHERE"); indent = 2; }
    else if (u === "AND" || u === "OR") { lines.push(pad() + w); indent = 2; }
    else if (u === "GROUP BY" || u === "GROUP") { indent = Math.max(1, indent - 1); lines.push(pad() + "GROUP BY"); indent = 2; }
    else if (u === "HAVING") { indent = Math.max(1, indent - 1); lines.push(pad() + "HAVING"); indent = 2; }
    else if (u === "ORDER BY" || u === "ORDER") { indent = Math.max(1, indent - 1); lines.push(pad() + "ORDER BY"); indent = 2; }
    else if (u === "LIMIT") { indent = Math.max(1, indent - 1); lines.push(pad() + "LIMIT"); indent = 1; }
    else if (u === "OFFSET") { lines.push(pad() + "OFFSET"); indent = 1; }
    else if (u === "UNION" || u === "UNION ALL") { indent = 0; lines.push(""); lines.push(w); }
    else if (u === "VALUES") { lines.push(pad() + "VALUES"); indent = 2; }
    else if (u === "SET") { lines.push(pad() + "SET"); indent = 2; }
    else if (u === "DELETE FROM" || u === "INSERT INTO" || u === "CREATE TABLE" || u === "DROP TABLE" || u === "ALTER TABLE") { indent = 0; lines.push(w); indent = 2; }
    else if (u === "CASE") { lines.push(pad() + "CASE"); indent++; }
    else if (u === "WHEN") { lines.push(pad() + "WHEN"); indent = 2; }
    else if (u === "THEN" || u === "ELSE") { lines.push(pad() + w); }
    else if (u === "END") { indent = Math.max(1, indent - 1); lines.push(pad() + "END"); }
    else if (u === "INTO") { lines.push(pad() + "INTO"); indent = 1; }
    else { lines.push(pad() + w); }
  }
  return lines.join("\n") + ";";
}
function formatDebugSQL() {
  var pres = document.querySelectorAll('.sql-debug');
  pres.forEach(function(pre) {
    var raw = pre.textContent;
    if (!raw || !raw.trim()) return;
    var formatted = fmt(raw);
    pre.innerHTML = highlight(h(formatted));
  });
}
document.addEventListener('DOMContentLoaded', formatDebugSQL);
</script>
</body></html>"""


# ===================================================================
# 查询执行与分页（带缓存）
# ===================================================================


class ReportResult:
    """封装报表查询结果（支持多结果集）"""

    __slots__ = ("results", "active_index", "page", "page_size")

    def __init__(self, results=None, active_index: int = 0,
                 page: int = 1, page_size: int = 20, **kwargs):
        """
        新式调用：results=[{"columns":..., "rows":..., "total":N}, ...], active_index
        旧式兼容：results=columns(list[str]), active_index=rows(list[tuple]), total=total

        当第一个参数是 str 列表时自动识别为旧式调用。
        """
        total = kwargs.pop("total", None)
        columns_kw = kwargs.pop("columns", None)
        rows_kw = kwargs.pop("rows", None)
        if kwargs:
            raise TypeError(f"不支持的参数: {kwargs}")

        if columns_kw is not None or rows_kw is not None:
            # 旧式兼容：columns=..., rows=... 关键字参数
            cols = columns_kw or []
            rws = rows_kw or []
            self.results = [{
                "columns": cols,
                "rows": rws,
                "total": total if total is not None else len(rws)
            }]
            self.active_index = 0
        elif results is not None and isinstance(results[0], str):
            # 旧式兼容：results 其实是 columns，active_index 其实是 rows
            cols = results
            rws = active_index if isinstance(active_index, (list, tuple)) else []
            self.results = [{
                "columns": cols,
                "rows": rws,
                "total": total if total is not None else len(rws)
            }]
            self.active_index = 0
        else:
            # 新式：results 是 [{"columns":..., "rows":..., "total":...}, ...]
            self.results = results if results is not None else [{"columns": [], "rows": [], "total": 0}]
            self.active_index = active_index
        self.page = page
        self.page_size = page_size

    @property
    def columns(self) -> list[str]:
        """当前激活结果的列名"""
        return self.results[self.active_index]["columns"]

    @property
    def rows(self) -> list[tuple]:
        """当前激活结果的行数据"""
        return self.results[self.active_index]["rows"]

    @property
    def total(self) -> int:
        """当前激活结果的总行数"""
        return self.results[self.active_index]["total"]

    @property
    def total_pages(self) -> int:
        """当前激活结果的总页数"""
        t = self.total
        ps = self.page_size
        return math.ceil(t / ps) if ps > 0 else 1


def execute_report(report_id: int, sql_query: str, pool_config: dict,
                   page: int = 1, page_size: int = 20,
                   sorts=None, filters=None,
                   refresh: bool = False,
                   active_index: int = 0) -> ReportResult:
    """
    执行报表查询（优先使用缓存），支持多字段排序/筛选/分页。

    sorts:   list[(col, dir), ...]  或 None
    filters: list[(col, op, val), ...]  或 None
    active_index: 当前渲染的结果索引
    """
    page = max(page, 1)
    page_size = max(page_size, 1)

    if refresh:
        _query_cache.invalidate(report_id)

    cached = _query_cache.get(report_id, sql_query)
    if cached is None:
        clean_sql = sql_query.rstrip("; \t\n\r")
        conn = db.create_mysql_connection(pool_config)
        try:
            all_results = db.execute_mysql_query(conn, clean_sql)
        finally:
            conn.close()
        _query_cache.set(report_id, all_results, sql_query)
    else:
        all_results = cached.results

    # 对每个结果集独立执行筛选、排序、分页
    report_results = []
    for i, res in enumerate(all_results):
        columns = res["columns"]
        all_rows = res["rows"]

        filtered = _filter_rows(all_rows, columns, filters or [])
        sorted_rows = _sort_rows(filtered, columns, sorts or [])

        total = len(sorted_rows)
        if i == active_index:
            offset = (page - 1) * page_size
            page_rows = sorted_rows[offset:offset + page_size]
        else:
            page_rows = sorted_rows

        report_results.append({
            "columns": columns,
            "rows": page_rows if i == active_index else sorted_rows,
            "total": total,
        })

    return ReportResult(report_results, active_index, page, page_size)


# ===================================================================
# 页面渲染
# ===================================================================


def render_report_selector(conn) -> str:
    """渲染报表选择页面（按分类层级树状呈现）"""
    reports = db.get_all_reports(conn)
    # 按分类分组
    cat_reports: dict[int, list] = {}
    uncategorized: list = []
    for r in reports:
        cid = r.get("category_id")
        if cid is not None:
            cat_reports.setdefault(cid, []).append(r)
        else:
            uncategorized.append(r)

    all_cats = db.get_all_categories(conn)
    cat_tree = db.get_category_tree(conn)

    def _cat_depth(cat_id: int) -> int:
        d = 0
        seen = set()
        c = next((x for x in all_cats if x["id"] == cat_id), None)
        while c and c.get("parent_id") is not None:
            if c["parent_id"] in seen:
                break
            seen.add(c["parent_id"])
            d += 1
            c = next((x for x in all_cats if x["id"] == c["parent_id"]), None)
        return d

    # ── 下拉框选项（按分类树层级） ──
    def _render_tree_options(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            # 如果分类有报表或是父分类，显示为 optgroup
            if rpts or node["children"]:
                label = f"{indent}{node['name']}"
                html += f'<optgroup label="{_escape(label)}">'
                for r in rpts:
                    html += f'<option value="{r["id"]}">{_escape(r["name"])}</option>'
                if node["children"]:
                    html += _render_tree_options(node["children"], depth + 1)
                html += "</optgroup>"
            else:
                # 空分类（无报表无子分类）只显示占位行
                html += f'<option value="" disabled style="color:#94a3b8;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</option>'
                if node["children"]:
                    html += _render_tree_options(node["children"], depth + 1)
        return html

    options = _render_tree_options(cat_tree)

    # 未分类报表
    for r in uncategorized:
        options += f'<option value="{r["id"]}">(未分类) {_escape(r["name"])}</option>'

    # ── 列表视图（按分类树层级） ──
    def _render_tree_list(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            if rpts or node["children"]:
                html += f'<li class="cat-header" style="list-style:none;font-weight:600;color:#4f46e5;padding:6px 0 2px {8 + depth * 20}px;font-size:14px">{indent}📁 {_escape(node["name"])}</li>'
                for r in rpts:
                    html += f'<li style="padding:4px 0 4px {28 + depth * 20}px"><a href="/report?id={r["id"]}">{_escape(r["name"])}</a></li>'
                if node["children"]:
                    html += _render_tree_list(node["children"], depth + 1)
            else:
                html += f'<li style="list-style:none;padding:4px 0 2px {8 + depth * 20}px;color:#94a3b8;font-size:13px;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</li>'
                if node["children"]:
                    html += _render_tree_list(node["children"], depth + 1)
        return html

    report_list = _render_tree_list(cat_tree)
    for r in uncategorized:
        report_list += f'<li style="padding:4px 0"><a href="/report?id={r["id"]}">(未分类) {_escape(r["name"])}</a></li>'

    if not report_list:
        report_list = '<li style="color:#94a3b8;padding:16px;list-style:none">暂无可用报表</li>'

    body = _PAGE_HEADER + """
<div class="card">
  <h2>选择报表</h2>
  <div class="report-select">
    <form method="get" action="/report">
      <label>请选择要查看的报表：</label>
      <select name="id" onchange="this.form.submit()" style="width:100%">
        <option value="">-- 请选择 --</option>
""" + options + """
      </select>
      <noscript><button type="submit" class="btn btn-primary btn-sm" style="margin-top:10px">查看</button></noscript>
    </form>
  </div>
</div>
<div class="card">
  <h3>可用报表列表</h3>
  <ul class="report-list" style="padding-left:0">""" + report_list + """</ul>
</div>
""" + _FOOTER
    return body


def render_report_page(conn, report_id: int, page: int = 1,
                       page_size: Optional[int] = None,
                       pool_override: Optional[dict] = None,
                       sorts=None, filters=None,
                       refresh: bool = False,
                       cols_raw: str = None,
                       sql_override: str = None,
                       active_index: int = 0,
                       result_names_override: str = None) -> str:
    """
    渲染报表数据展示页，支持多字段排序/筛选/自定义列/多结果集。
    cols_raw: 原始 cols 参数字符串（如 "id,name,age"），由 execute_report 结果中的列名解析。
              为 None 表示全部显示。
    sql_override: 预览模式时替代 report["sql_query"] 的临时 SQL，不保存到数据库。
    active_index: 当前激活的结果集索引。
    """
    report = db.get_report(conn, report_id)
    if not report:
        return _PAGE_HEADER + '<div class="flash flash-error">错误: 报表不存在</div>' + _FOOTER

    if page_size is None or page_size < 1:
        page_size = report["default_page_size"]

    if pool_override:
        pool_config = pool_override
    else:
        pool_id = report["pool_id"]
        if pool_id is None:
            return (_PAGE_HEADER +
                    f'<div class="flash flash-error">该报表 "{_escape(report["name"])}" 关联的连接池已被删除。'
                    f' 请前往 <a href="/config" style="color:#4f46e5;font-weight:600">配置管理</a> 重新指定连接池。</div>' +
                    _FOOTER)
        pool_config = db.get_pool(conn, pool_id)
        if not pool_config:
            return (_PAGE_HEADER +
                    f'<div class="flash flash-error">错误: 报表 "{_escape(report["name"])}" 关联的连接池不存在</div>' +
                    _FOOTER)

    actual_sql = sql_override or report["sql_query"]
    try:
        result = execute_report(report_id, actual_sql, pool_config,
                                page, page_size, sorts or [], filters or [], refresh,
                                active_index)
    except Exception as e:
        pool_name = pool_config.get("name", "?")
        pool_host = pool_config.get("host", "?")
        pool_port = pool_config.get("port", "?")
        pool_user = pool_config.get("user", "?")
        return (_PAGE_HEADER +
                f'<div class="flash flash-error">查询执行失败: {_escape(str(e))}'
                f'<br><small>连接池: {_escape(str(pool_name))}'
                f' ({_escape(str(pool_host))}:{pool_port}, 用户: {_escape(str(pool_user))})'
                f'</small></div>' + _FOOTER)

    # 从原始 cols 字符串解析自定义列（利用 execute_report 已获取的列名）
    all_cols = result.columns
    if cols_raw:
        display_columns = _parse_cols({"cols": [cols_raw]}, all_cols)
    else:
        display_columns = None

    return _build_report_html(conn, report, result, pool_config,
                              sorts or [], filters or [], refresh,
                              display_columns, sql_override, active_index,
                              result_names_override=result_names_override)


# ===================================================================
# HTML 构建（核心）
# ===================================================================


def _build_report_html(conn, report: dict, result: ReportResult,
                       pool_config: dict = None,
                       sorts=None, filters=None,
                       refresh: bool = False,
                       display_columns: list[str] = None,
                       sql_override: str = None,
                       active_index: int = 0,
                       result_names_override: str = None) -> str:
    """
    构建完整的报表 HTML，支持多结果集下拉切换。
    sorts/filters 均为列表。
    display_columns: 用户自定义的显示列列表（顺序 + 可见性），None 表示全部显示。
    sql_override: 预览模式时替代 report["sql_query"] 的临时 SQL。
    active_index: 当前激活的结果集索引。
    """
    sorts = sorts or []
    filters = filters or []
    report_id = report["id"]
    actual_sql = sql_override or report["sql_query"]
    qs_page_size = result.page_size
    all_columns = list(result.columns)
    if display_columns is None:
        display_columns = all_columns
    cols_param = _build_cols_param(display_columns, all_columns)

    # ---- 多结果集 ----
    num_results = len(result.results)
    # 解析 result_names（每行一个名称，JSON 格式字符串）
    result_names_raw = result_names_override if result_names_override else (report.get("result_names", "") or "")
    result_names_list = [n.strip() for n in result_names_raw.split("\n") if n.strip()]
    # 补齐或截断到实际结果数
    result_names = []
    for i in range(num_results):
        if i < len(result_names_list):
            result_names.append(result_names_list[i])
        else:
            result_names.append(f"结果{i + 1}")
    swi = ("report" if not sql_override else "report/preview")
    result_selector_html = ""
    if num_results > 1:
        opts = "".join(
            f'<option value="{i}"{" selected" if i == active_index else ""}>{_escape(result_names[i])}</option>'
            for i in range(num_results)
        )
        # 构建基础 URL（仅保留 id/page_size/sql_override，不携带筛选排序列）
        qs_parts = [f"id={report_id}", f"page_size={qs_page_size}"]
        if sql_override:
            qs_parts.append(f"sql_query={urllib.parse.quote(sql_override)}")
        base_qs = "&".join(qs_parts)
        result_selector_html = (
            f'<div class="result-selector" style="margin-bottom:12px;display:flex;align-items:center;gap:8px">'
            f'<label style="font-size:13px;color:#475569;font-weight:500">结果视图:</label>'
            f'<select id="resultSwitcher"'
            f' data-report-id="{report_id}" data-active-index="{active_index}"'
            f' data-swi="{_escape(swi)}" data-page-size="{qs_page_size}"'
            f' data-sql-override="{_escape(sql_override or "")}"'
            f' onchange="switchResult(this)"'
            f' style="padding:4px 8px;font-size:13px;border:1px solid #e2e8f0;border-radius:4px;background:#fff">'
            f'{opts}</select>'
            f'</div>'
        )

    # ---- Debug 信息 ----
    debug_lines = []
    if pool_config:
        pname = pool_config.get("name", "?")
        phost = pool_config.get("host", "?")
        pport = pool_config.get("port", "?")
        puser = pool_config.get("user", "?")
        pdb = pool_config.get("database", "?")
        debug_lines.append(f'连接池: {_escape(str(pname))} ({_escape(str(phost))}:{pport})'
                           f' | 用户: {_escape(str(puser))} | 数据库: {_escape(str(pdb))}')
    debug_lines.append(
        f'SQL: <pre class="sql-debug" style="white-space:pre-wrap;word-break:break-all;'
        f'background:#f1f5f9;padding:8px 10px;border-radius:4px;font-size:13px;'
        f'line-height:1.6;margin:4px 0;border:1px solid #e2e8f0;overflow-x:auto">'
        f'{_escape(actual_sql)}</pre>'
    )
    if num_results > 1:
        debug_lines.append(f'结果: {active_index + 1}/{num_results} ({result_names[active_index]})')
    if filters:
        filter_desc = " AND ".join(f'{_escape(c)} {_escape(_OP_MAP.get(o, [o, o])[1])} "{_escape(v)}"' for c, o, v in filters)
        debug_lines.append(f'筛选: {filter_desc}')
    if sorts:
        sort_desc = ", ".join(f'{_escape(c)} {"↑" if d == "asc" else "↓"}' for c, d in sorts)
        debug_lines.append(f'排序: {sort_desc}')
    debug_html = (
        '<div class="debug-info">'
        '<button class="debug-toggle" onclick="toggleSection(this, \'Debug 信息\')" type="button">▶ Debug 信息</button>'
        '<div class="debug-content hidden">' + '<br>'.join(debug_lines) + '</div>'
        '</div>')

    # ---- 备注 ----
    memo_raw = report.get("memo") or ""
    if memo_raw:
        memo_btn_text = "▼ 备注"
        memo_hidden_cls = ""
    else:
        memo_btn_text = "▶ 备注"
        memo_hidden_cls = " hidden"
    memo_html = (
        '<div class="debug-info">'
        f'<button class="debug-toggle" onclick="toggleSection(this, \'备注\')" type="button">{memo_btn_text}</button>'
        f'<div class="debug-content{memo_hidden_cls}">' + _escape(memo_raw) + '</div>'
        '</div>')

    # ---- 结果参数（多结果集时附加到 URL） ----
    result_param = f"result={active_index}" if num_results > 1 else ""

    # ---- 构建多字段筛选表单（单 Form，filter inputs 用 form 属性关联） ----
    filter_form_id = "ff"
    form_hidden = [f'<input type="hidden" name="id" value="{report_id}">',
                   f'<input type="hidden" name="page_size" value="{qs_page_size}">']
    if result_param:
        form_hidden.append(f'<input type="hidden" name="result" value="{active_index}">')
    # 排序状态（hidden，表单提交时保留）
    for col, dir_ in sorts:
        form_hidden.append(f'<input type="hidden" name="sort" value="{_escape(col)}">')
        form_hidden.append(f'<input type="hidden" name="dir" value="{_escape(dir_)}">')
    # 自定义列排序/隐藏（hidden，表单提交时保留）
    #
    # 注意：筛选操作符不再通过隐藏 input 保留，因为可见的筛选下拉框（form="ff"）已经
    # 在表单提交时提供操作符值。隐藏的 op_ 输入在 DOM 中排在可见下拉框之前，会导致
    # 其旧值覆盖用户选择的新值（如"不筛选"被忽略）。见 AGENTS.md 中的 bug 记录。
    if cols_param:
        form_hidden.append(f'<input type="hidden" name="cols" value="{_escape(",".join(display_columns))}">')
    form_hidden_str = "\n    ".join(form_hidden)

    # ---- 构建排序栏（显示当前排序列及其优先级） ----
    sort_bar_parts = []
    if sorts:
        sort_bar_parts.append('<div class="sort-bar" style="margin-bottom:10px;font-size:13px;display:flex;align-items:center;gap:6px;flex-wrap:wrap">')
        sort_bar_parts.append('<span style="color:#475569;font-weight:500">排序:</span>')
        for idx, (sc, sd) in enumerate(sorts, 1):
            label = f'{_escape(sc)} {"↑" if sd == "asc" else "↓"}'
            prio = chr(0x2460 + idx - 1) if idx <= 20 else f"#{idx}"
            # 移除该列排序的 URL
            rm_sorts = [(c, d) for c, d in sorts if c != sc]
            rm_href = f"/report?id={report_id}&amp;page_size={qs_page_size}"
            if rm_sorts:
                rm_href += "&amp;" + _build_sort_params(rm_sorts)
            if filters:
                rm_href += "&amp;" + _build_filter_params(filters)
            if cols_param:
                rm_href += "&amp;" + cols_param
            if result_param:
                rm_href += "&amp;" + result_param
            sort_bar_parts.append(
                f'<span class="sort-tag" style="display:inline-flex;align-items:center;gap:3px;'
                f'background:#eef2ff;color:#4f46e5;border-radius:4px;padding:2px 8px;'
                f'font-size:12px;border:1px solid #c7d2fe">'
                f'<span style="font-weight:700;font-size:11px">{prio}</span> {label}'
                f'<a href="{rm_href}" style="text-decoration:none;color:#94a3b8;margin-left:2px" '
                f'title="移除排序">✕</a>'
                f'</span>'
            )
        sort_bar_parts.append('</div>')
    sort_bar_html = "".join(sort_bar_parts)

    # ---- 构建表头（排序双箭头 + 筛选操作符下拉框 + 筛选输入框） ----
    thead_parts = ["<tr>"]
    for col in display_columns:
        # 当前排序列信息
        current_dir = None
        sort_priority = 0
        for idx, (c, d) in enumerate(sorts, 1):
            if c == col:
                current_dir = d
                sort_priority = idx
                break

        # 构建 ▲ (asc) 链接 — 追加/切换多字段排序
        asc_sorts = list(sorts)
        found_asc = False
        for i, (c, d) in enumerate(asc_sorts):
            if c == col:
                asc_sorts[i] = (col, "asc")
                found_asc = True
                break
        if not found_asc:
            asc_sorts.append((col, "asc"))
        asc_href = f"/report?id={report_id}&amp;page_size={qs_page_size}"
        asc_href += "&amp;" + _build_sort_params(asc_sorts)
        if filters:
            asc_href += "&amp;" + _build_filter_params(filters)
        if cols_param:
            asc_href += "&amp;" + cols_param
        if result_param:
            asc_href += "&amp;" + result_param
        asc_cls = "sort-arrow active" if current_dir == "asc" else "sort-arrow"

        # 构建 ▼ (desc) 链接 — 追加/切换多字段排序
        desc_sorts = list(sorts)
        found_desc = False
        for i, (c, d) in enumerate(desc_sorts):
            if c == col:
                desc_sorts[i] = (col, "desc")
                found_desc = True
                break
        if not found_desc:
            desc_sorts.append((col, "desc"))
        desc_href = f"/report?id={report_id}&amp;page_size={qs_page_size}"
        desc_href += "&amp;" + _build_sort_params(desc_sorts)
        if filters:
            desc_href += "&amp;" + _build_filter_params(filters)
        if cols_param:
            desc_href += "&amp;" + cols_param
        if result_param:
            desc_href += "&amp;" + result_param
        desc_cls = "sort-arrow active" if current_dir == "desc" else "sort-arrow"

        # 排序优先级标示
        priority_badge = ""
        if sort_priority > 0:
            prio_char = chr(0x2460 + sort_priority - 1) if sort_priority <= 20 else f"#{sort_priority}"
            priority_badge = f'<span class="sort-prio" style="font-size:10px;color:#4f46e5;font-weight:700;margin-left:2px">{prio_char}</span>'

        # ---- 筛选信息 ----
        cur_fval = ""
        cur_op = "nofilter"
        for item in filters:
            c, op, val = item
            if c == col:
                cur_fval = val
                cur_op = op
                break

        # 筛选输入 name
        filter_input_name = "f_" + urllib.parse.quote(col, safe='')
        filter_op_name = "op_" + urllib.parse.quote(col, safe='')

        # 构建操作符下拉框选项
        op_options = ""
        for code, label, short in FILTER_OPS:
            sel = ' selected' if code == cur_op else ''
            op_options += f'<option value="{code}"{sel}>{_escape(label)}</option>'

        # 输入框是否隐藏/禁用（不筛选/为空/非空不需要值）
        input_hidden = cur_op in ("nofilter", "isempty", "notempty")
        input_style = "display:none" if input_hidden else ""
        input_disabled = "disabled" if input_hidden else ""

        thead_parts.append(f"""<th>
  <div class="sort-links" style="display:inline-flex;align-items:center;gap:0">
    <a href="{asc_href}" class="sort-link" title="升序">{_escape(col)}</a>
    <a href="{asc_href}" class="sort-link" style="padding:0 1px;text-decoration:none" title="升序"><span class="{asc_cls}">▲</span></a>
    <a href="{desc_href}" class="sort-link" style="padding:0 1px;text-decoration:none" title="降序"><span class="{desc_cls}">▼</span></a>
    {priority_badge}
  </div>
  <div class="filter-row" style="display:flex;gap:2px;margin-top:6px;align-items:center">
    <select class="filter-op" form="{filter_form_id}" name="{filter_op_name}"
      style="padding:2px 2px;font-size:11px;border:1px solid #e2e8f0;border-radius:3px;background:#fff;width:auto;min-width:52px;flex-shrink:0;cursor:pointer"
      onchange="toggleFilterInput('{filter_input_name}', this)">{op_options}</select>
    <input type="text" class="filter-input" form="{filter_form_id}"
      name="{filter_input_name}" placeholder="筛选 {_escape(col)}..."
      value="{_escape(cur_fval)}"
      style="{input_style}" {input_disabled}>
  </div>
</th>""")
    thead_parts.append("</tr>")
    thead_str = "".join(thead_parts)

    # ---- 数据行 ----
    # 构建列名到索引的映射，用于按 display_columns 顺序提取数据
    col_index_map = {name: idx for idx, name in enumerate(all_columns)}
    display_indices = [col_index_map[c] for c in display_columns]
    tbody = ""
    if not result.rows:
        tbody = ('<tr class="empty-state-row">'
                 '<td colspan="999"><div class="empty-state">'
                 '<div class="icon">📭</div>暂无数据</div></td></tr>')
    else:
        for row in result.rows:
            cells = "".join(f"<td>{_escape(row[i])}</td>" for i in display_indices)
            tbody += "<tr>" + cells + "</tr>"

    # ---- 分页 ----
    pagination = _build_pagination(report_id, result.page, result.total_pages,
                                   result.page_size, result.total, sorts, filters, cols_param, result_param if num_results > 1 else "")

    # ---- 缓存状态 ----
    cached = _query_cache.get(report_id, actual_sql)
    if cached:
        cache_badge = ('<span class="cache-badge fresh">'
                       f'缓存中 ({int(time.time() - cached.timestamp)}s 前刷新)'
                       '</span>')
    else:
        cache_badge = '<span class="cache-badge">未缓存</span>'

    # ---- 控制栏 ----
    # 控制栏表单：携带所有状态（筛选+排序+自定义列）
    cols_hidden = f'<input type="hidden" name="cols" value="{_escape(",".join(display_columns))}">' if cols_param else ""
    controls = f"""
<div class="controls">
  <form method="get" action="/report" style="display:inline-flex;align-items:center;gap:12px">
    <input type="hidden" name="id" value="{report_id}">
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {_filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    <label>每页行数:
      <select name="page_size" onchange="this.form.submit()">
        {''.join(f'<option value="{s}"{" selected" if qs_page_size == s else ""}>{s}</option>'
                 for s in [10, 20, 50, 100, 200])}
      </select>
    </label>
    <noscript><button type="submit" class="btn btn-primary btn-sm">刷新</button></noscript>
  </form>
  <form method="get" action="/export" style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">
    <input type="hidden" name="id" value="{report_id}">
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    {''.join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {_filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:3px">
      格式:
      <select name="format" style="padding:2px 5px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px">
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
      </select>
    </label>
    <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:3px">
      字符集:
      <select name="charset" style="padding:2px 5px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px">
        <option value="gbk">GBK</option>
        <option value="utf8">UTF8</option>
      </select>
    </label>
    <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:2px">
      <input type="checkbox" name="json_no_quotes" value="1"> 数字无引号
    </label>
    <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:2px">
      <input type="checkbox" name="zip" value="1"> 压缩包
    </label>
    <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:2px">
      <input type="checkbox" name="use_custom_cols" value="1" {"checked" if cols_param else ""}> 应用自定义字段
    </label>
    <button type="submit" class="btn btn-success btn-sm" style="font-size:12px;padding:3px 10px">导出</button>
  </form>
  <button type="button" onclick="document.getElementById('fieldSettingsPanel').style.display='block'" class="btn-refresh" style="font-size:13px">⚙ 字段设置</button>
  <button type="button" onclick="document.getElementById('sortSettingsPanel').style.display='block'" class="btn-refresh" style="font-size:13px">⇅ 排序设置</button>
   <a href="/report?id={report_id}&amp;page_size={qs_page_size}{('&amp;'+_build_sort_params(sorts)) if sorts else ''}{('&amp;'+_build_filter_params(filters)) if filters else ''}{('&amp;'+cols_param) if cols_param else ''}{'&amp;'+result_param if result_param else ''}&amp;refresh=1" class="btn-refresh">⟳ 重建缓存</a>
  {cache_badge}
  <span class="stat">共 {result.total} 行，{result.total_pages} 页</span>
</div>"""

    # ---- 筛选清除提示与筛选操作按钮 ----
    clear_href = f"/report?id={report_id}&amp;page_size={qs_page_size}"
    if sorts:
        clear_href += "&amp;" + _build_sort_params(sorts)
    if cols_param:
        clear_href += "&amp;" + cols_param
    if result_param:
        clear_href += "&amp;" + result_param

    filter_action_html = (f'<div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
                         f'<button type="submit" form="ff" class="btn btn-primary btn-sm">筛选</button>'
                         f'<a href="{clear_href}" class="btn btn-outline btn-sm">清除筛选</a>'
                         f'</div>')

    clear_html = ""
    if filters:
        filter_items = []
        for c, o, v in filters:
            op_label = _OP_MAP.get(o, (o, o))[1]
            if o in ("isempty", "notempty"):
                filter_items.append(f'{_escape(c)} ({op_label})')
            else:
                filter_items.append(f'{_escape(c)} {op_label} "{_escape(v)}"')
        filter_summary = "、".join(filter_items)
        clear_html = (f'<div style="margin-bottom:12px;font-size:13px;color:#64748b">'
                      f'筛选: {filter_summary} '
                      f'<a href="{clear_href}" class="clear-filter">✕ 全部清除</a></div>')

    # ---- 字段设置面板 ----
    field_settings_items = []
    for idx, col in enumerate(all_columns):
        checked = "checked" if col in display_columns else ""
        # 找到当前列在 display_columns 中的位置（用于排序箭头）
        pos = display_columns.index(col) if col in display_columns else -1
        up_disabled = "disabled" if pos <= 0 else ""
        down_disabled = "disabled" if pos >= len(display_columns) - 1 or pos < 0 else ""
        field_settings_items.append(
            f'<label class="field-item" draggable="true" style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
            f'border:1px solid #e2e8f0;border-radius:6px;background:{'#f8fafc' if col in display_columns else '#fff'};'
            f'cursor:grab;user-select:none">'
            f'<span class="drag-handle" style="color:#94a3b8;font-size:14px;cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
            f'<input type="checkbox" name="col_visible" value="{_escape(col)}" {checked} '
            f'onchange="toggleFieldItem(this)" onclick="event.stopPropagation()">'
            f'<span style="flex:1;font-size:13px;color:#1e293b">{_escape(col)}</span>'
            f'<input type="hidden" name="col_order" value="{_escape(col)}">'
            f'<button type="button" class="field-up" {up_disabled} onclick="moveField(this,-1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▲</button>'
            f'<button type="button" class="field-down" {down_disabled} onclick="moveField(this,1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▼</button>'
            f'</label>'
        )
    field_settings_html = (
        '<div id="fieldSettingsPanel" style="display:none;margin-bottom:16px;padding:16px;'
        'background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'
        '<h3 style="margin:0;font-size:15px;color:#1e293b">字段设置</h3>'
        '<button type="button" onclick="document.getElementById(\'fieldSettingsPanel\').style.display=\'none\'" '
        'style="padding:4px 10px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff">收起</button>'
        '</div>'
        '<div id="fieldList" style="display:flex;flex-direction:column;gap:4px;max-height:400px;overflow-y:auto">'
        + "".join(field_settings_items) +
        '</div>'
        '<div style="display:flex;gap:8px;margin-top:12px">'
        '<button type="button" onclick="selectAllFields(true)" class="btn btn-outline btn-sm">全选</button>'
        '<button type="button" onclick="selectAllFields(false)" class="btn btn-outline btn-sm">全不选</button>'
        '<button type="button" onclick="applyFieldSettings()" class="btn btn-primary btn-sm" style="margin-left:auto">应用</button>'
        '</div>'
        '</div>'
    )

    # ---- 排序管理面板 ----
    sort_settings_items = []
    for idx, (sc, sd) in enumerate(sorts):
        up_disabled = "disabled" if idx == 0 else ""
        down_disabled = "disabled" if idx == len(sorts) - 1 else ""
        icon = "↑" if sd == "asc" else "↓"
        sort_settings_items.append(
            f'<div class="sort-item" draggable="true" style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
            f'border:1px solid #e2e8f0;border-radius:6px;background:#f8fafc;cursor:grab;user-select:none">'
            f'<span class="drag-handle" style="color:#94a3b8;font-size:14px;cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
            f'<span class="sort-num" style="font-weight:700;font-size:11px;color:#4f46e5;min-width:20px">{idx + 1}</span>'
            f'<span style="flex:1;font-size:13px;color:#1e293b">{_escape(sc)} {icon}</span>'
            f'<input type="hidden" name="sort_col" value="{_escape(sc)}">'
            f'<input type="hidden" name="sort_dir" value="{_escape(sd)}">'
            f'<button type="button" class="sort-up" {up_disabled} onclick="moveSortItem(this,-1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▲</button>'
            f'<button type="button" class="sort-down" {down_disabled} onclick="moveSortItem(this,1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▼</button>'
            f'<button type="button" onclick="removeSortItem(this)" '
            f'style="padding:2px 6px;font-size:11px;border:none;border-radius:4px;'
            f'cursor:pointer;background:transparent;color:#dc2626">✕</button>'
            f'</div>'
        )
    col_options = "".join(f'<option value="{_escape(c)}">{_escape(c)}</option>' for c in all_columns)
    sort_settings_html = (
        '<div id="sortSettingsPanel" style="display:none;margin-bottom:16px;padding:16px;'
        'background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'
        '<h3 style="margin:0;font-size:15px;color:#1e293b">排序设置</h3>'
        '<button type="button" onclick="document.getElementById(\'sortSettingsPanel\').style.display=\'none\'" '
        'style="padding:4px 10px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff">收起</button>'
        '</div>'
        '<div id="sortList" style="display:flex;flex-direction:column;gap:4px;max-height:300px;overflow-y:auto;margin-bottom:8px">'
        + ("".join(sort_settings_items) if sort_settings_items
           else '<div style="color:#94a3b8;font-size:13px;padding:12px;text-align:center">暂无排序</div>') +
        '</div>'
        '<div style="display:flex;gap:8px;align-items:center;padding:8px;background:#f8fafc;'
        'border:1px solid #e2e8f0;border-radius:6px;margin-bottom:8px">'
        '<select id="newSortCol" style="flex:1;padding:4px 8px;border:1px solid #e2e8f0;'
        'border-radius:4px;font-size:13px">'
        '<option value="">-- 添加排序字段 --</option>'
        + col_options +
        '</select>'
        '<select id="newSortDir" style="padding:4px 8px;border:1px solid #e2e8f0;'
        'border-radius:4px;font-size:13px">'
        '<option value="asc">↑ 升序</option>'
        '<option value="desc">↓ 降序</option>'
        '</select>'
        '<button type="button" onclick="addSortItem()" class="btn btn-primary btn-sm">添加</button>'
        '</div>'
        '<div style="display:flex;gap:8px;margin-top:8px">'
        '<button type="button" onclick="applySortSettings()" class="btn btn-primary btn-sm" style="margin-left:auto">应用</button>'
        '</div>'
        '</div>'
    )

    # ---- 单 Form（filter inputs 通过 form 属性关联到此 form） ----
    filter_form_html = f'<form id="{filter_form_id}" method="get" action="/report" style="display:none">\n  {form_hidden_str}\n</form>'

    body = (_PAGE_HEADER +
            _build_report_switcher(conn, report_id) +
            f'<div class="card">'
            f'<h2>{_escape(report["name"])}</h2>' +
            ('<div class="preview-badge" style="background:#fef3c7;color:#92400e;padding:6px 12px;border-radius:6px;margin-bottom:10px;font-size:13px;font-weight:600">'
             '🔍 预览模式 — 当前显示的是未保存的临时 SQL 查询结果，点击筛选/排序将跳转到正式报表。'
             '</div>' if sql_override else '') +
            f'<div style="margin-bottom:10px">'
            f'<a href="/config/reports/{report_id}/edit" class="btn btn-outline btn-sm" target="_blank" rel="noopener">编辑</a>'
            f'</div>' +
            memo_html +
            debug_html +
            result_selector_html +
            controls +
            field_settings_html +
            sort_settings_html +
            sort_bar_html +
            filter_action_html +
            clear_html +
            filter_form_html +
            '<div class="table-wrap"><table>' + thead_str + tbody + '</table></div>' +
            pagination +
            '</div>' +
            _FOOTER)
    return body


def _build_report_switcher(conn, current_id: int = None) -> str:
    """构建报表切换下拉框（按分类层级树状呈现）"""
    reports = db.get_all_reports(conn)
    cat_reports: dict[int, list] = {}
    uncategorized: list = []
    for r in reports:
        cid = r.get("category_id")
        if cid is not None:
            cat_reports.setdefault(cid, []).append(r)
        else:
            uncategorized.append(r)

    all_cats = db.get_all_categories(conn)
    cat_tree = db.get_category_tree(conn)

    def _cat_depth(cat_id: int) -> int:
        d = 0
        seen = set()
        c = next((x for x in all_cats if x["id"] == cat_id), None)
        while c and c.get("parent_id") is not None:
            if c["parent_id"] in seen:
                break
            seen.add(c["parent_id"])
            d += 1
            c = next((x for x in all_cats if x["id"] == c["parent_id"]), None)
        return d

    def _render_tree_switcher(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            if rpts or node["children"]:
                label = f"{indent}{node['name']}"
                html += f'<optgroup label="{_escape(label)}">'
                for r in rpts:
                    sel = ' selected' if r["id"] == current_id else ''
                    html += f'<option value="{r["id"]}"{sel}>{_escape(r["name"])}</option>'
                if node["children"]:
                    html += _render_tree_switcher(node["children"], depth + 1)
                html += "</optgroup>"
            else:
                html += f'<option value="" disabled style="color:#94a3b8;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</option>'
                if node["children"]:
                    html += _render_tree_switcher(node["children"], depth + 1)
        return html

    options = _render_tree_switcher(cat_tree)
    for r in uncategorized:
        sel = ' selected' if r["id"] == current_id else ''
        options += f'<option value="{r["id"]}"{sel}>(未分类) {_escape(r["name"])}</option>'

    return f"""<div class="card" style="margin-bottom:16px">
  <div class="report-select">
    <form method="get" action="/report">
      <label style="font-size:14px;color:#475569;font-weight:500;margin-bottom:6px;display:block">切换报表:</label>
      <select name="id" onchange="this.form.submit()" style="width:100%">
        <option value="">-- 选择报表 --</option>
        {options}
      </select>
    </form>
  </div>
</div>"""


def _build_pagination(report_id: int, current: int, total_pages: int,
                      page_size: int, total_rows: int,
                      sorts=None, filters=None, cols_param: str = '',
                      result_param: str = '') -> str:
    """构建分页 HTML，携带多字段排序/筛选/自定义列/多结果参数"""
    sorts = sorts or []
    filters = filters or []
    if total_pages <= 1:
        return ""

    # 基础 URL（使用 &amp; 确保 HTML 中 & 被正确转义）
    base_url = f"/report?id={report_id}&amp;page_size={page_size}"
    if sorts:
        base_url += "&amp;" + _build_sort_params(sorts)
    if filters:
        base_url += "&amp;" + _build_filter_params(filters)
    if cols_param:
        base_url += "&amp;" + cols_param
    if result_param:
        base_url += "&amp;" + result_param
        base_url += "&amp;" + cols_param

    parts = []

    if current > 1:
        parts.append(f'<a href="{base_url}&amp;page={current - 1}" class="nav-arrow">‹</a>')
    else:
        parts.append('<span class="disabled">‹</span>')

    pages_to_show = set()
    pages_to_show.add(1)
    pages_to_show.add(total_pages)
    for i in range(max(1, current - 3), min(total_pages, current + 3) + 1):
        pages_to_show.add(i)

    sorted_pages = sorted(pages_to_show)
    prev = 0
    for p in sorted_pages:
        if p - prev > 1:
            parts.append('<span class="disabled">…</span>')
        if p == current:
            parts.append(f'<span class="active">{p}</span>')
        else:
            parts.append(f'<a href="{base_url}&amp;page={p}" class="page-btn">{p}</a>')
        prev = p

    if current < total_pages:
        parts.append(f'<a href="{base_url}&amp;page={current + 1}" class="nav-arrow">›</a>')
    else:
        parts.append('<span class="disabled">›</span>')

    jump = (
        f'<span class="jump-box">跳转到: '
        f'<input type="number" id="jump_page" min="1" max="{total_pages}" '
        f'value="{current}"> '
        f'<button class="btn btn-primary btn-sm" '
        f'onclick="window.location.href=\'{base_url}&amp;page=\' + '
        f"document.getElementById('jump_page').value\">GO</button>"
        f'</span>'
    )

    return f'<div class="pagination">{" ".join(parts)}{jump}</div>'


# ===================================================================
# 入口
# ===================================================================


def handle_request(conn, method: str, path: str, query: str,
                   form_body: str = None,
                   pool_override: Optional[dict] = None) -> tuple[str, str, dict]:
    """
    报表页面请求入口。
    解析多字段排序/刷新缓存等参数。
    支持 POST 预览模式（/report/preview），不保存配置，临时查看。
    """
    # 预览模式：不保存配置，临时以表单中的 SQL 在新窗口中查看
    if path == "/report/preview" and method == "POST":
        form_data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
        try:
            preview_id_str = form_data.get("id", [None])[0] or ""
            preview_id = int(preview_id_str)
        except (ValueError, TypeError, IndexError):
            return "200", render_report_selector(conn), {}
        sql_override = form_data.get("sql_query", [None])[0] or ""
        preview_result = 0
        if "result" in form_data and form_data["result"][0]:
            try:
                preview_result = max(0, int(form_data["result"][0]))
            except ValueError:
                pass
        preview_names = form_data.get("result_names", [None])[0]
        return "200", render_report_page(conn, preview_id, sql_override=sql_override,
                                         active_index=preview_result,
                                         result_names_override=preview_names or None), {}

    qs = urllib.parse.parse_qs(query, keep_blank_values=True)

    if "id" not in qs or not qs["id"][0]:
        return "200", render_report_selector(conn), {}

    try:
        report_id = int(qs["id"][0])
    except (ValueError, IndexError):
        return "200", render_report_selector(conn), {}

    page = 1
    if "page" in qs and qs["page"][0]:
        try:
            page = max(1, int(qs["page"][0]))
        except ValueError:
            pass

    page_size = None
    if "page_size" in qs and qs["page_size"][0]:
        try:
            page_size = max(1, int(qs["page_size"][0]))
        except ValueError:
            pass

    # 多字段排序
    sorts = _parse_sorts(qs)
    # 多字段筛选
    filters = _parse_filters(qs)

    # 自定义列顺序/可见性（原始参数字符串，推迟到 render_report_page 中解析）
    cols_raw = _qs_val(qs, "cols")

    # 刷新缓存
    refresh = _qs_val(qs, "refresh") or ""
    refresh_flag = refresh in ("1", "true", "yes")

    # 多结果集索引
    active_index = 0
    if "result" in qs and qs["result"][0]:
        try:
            active_index = max(0, int(qs["result"][0]))
        except ValueError:
            pass

    html = render_report_page(conn, report_id, page, page_size, pool_override,
                              sorts, filters, refresh_flag, cols_raw, active_index=active_index)
    return "200", html, {}
