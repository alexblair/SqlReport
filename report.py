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
# 缓存
# ===================================================================


class CachedResult:
    """单次报表查询的缓存结果，保存原始 SQL 返回的全量数据。"""

    __slots__ = ("columns", "rows", "sql_query", "timestamp")

    def __init__(self, columns: list[str], rows: list[tuple],
                 sql_query: str):
        self.columns = columns
        self.rows = rows
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

    def set(self, report_id: int, columns: list[str],
            rows: list[tuple], sql_query: str) -> None:
        self._cache[report_id] = CachedResult(columns, rows, sql_query)

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
    在内存中按多字段模糊筛选（AND 逻辑）。

    filters: list[(col, query), ...]
    每对 (col, query) 对列做不区分大小写的 LIKE '%query%' 匹配。
    多个条件之间为 AND 关系。
    """
    if not filters:
        return rows
    result = list(rows)
    for col_name, q in filters:
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name)
        q_lower = q.lower()
        result = [
            r for r in result
            if q_lower in str(r[col_idx] if r[col_idx] is not None else "").lower()
        ]
    return result


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


def _build_filter_params(filters, skip_col=None):
    """
    将 filters 列表编码为 URL 查询字符串（f_{col}=value 格式）。

    若指定 skip_col，则跳过该列的 filter 项（用于生成某列自己的排序链接时）。
    """
    parts = []
    for col, q in filters:
        if skip_col is not None and col == skip_col:
            continue
        k = "f_" + urllib.parse.quote(col, safe='')
        parts.append(f"{k}={urllib.parse.quote(q, safe='')}")
    return "&".join(parts)


def _build_sort_params(sorts):
    """将 sorts 列表编码为 URL 查询字符串（sort=col&dir=asc 重复）。"""
    parts = []
    for col, dir_ in sorts:
        parts.append(f"sort={urllib.parse.quote(col, safe='')}&dir={urllib.parse.quote(dir_, safe='')}")
    return "&".join(parts)


def _parse_filters(qs):
    """
    从 parse_qs 结果中解析多字段筛选参数。

    新格式（优先）：f_{colname}=value  如 f_name=alice&f_age=30
    旧格式（兼容）：f_col=name&f_q=alice（仅单字段有效）
    返回 list[(col, q), ...]
    """
    filters = []
    excl = frozenset(("f_col", "f_q", "filters"))
    for key, values in qs.items():
        if not key.startswith("f_") or key in excl:
            continue
        colname = urllib.parse.unquote(key[2:])
        if values and values[0]:
            filters.append((colname, values[0]))

    # 旧格式兼容
    if not filters:
        f_cols = qs.get("f_col", [])
        f_qs = qs.get("f_q", [])
        for c, q in zip(f_cols, f_qs):
            if q:
                filters.append((c, q))
    return filters


def _parse_sorts(qs):
    """
    从 parse_qs 结果中解析多字段排序参数。

    格式：sort=col1&dir=asc&sort=col2&dir=desc  (repeated)
    返回 list[(col, dir), ...]
    """
    sorts = list(zip(qs.get("sort", []), qs.get("dir", [])))
    return [(c, d) for c, d in sorts if d in ("asc", "desc")]


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
  .debug-toggle {
    display:inline-flex; align-items:center; gap:4px; font-size:12px;
    color:#94a3b8; cursor:pointer; background:none; border:1px solid #e2e8f0;
    border-radius:6px; padding:4px 10px; margin-bottom:8px; transition:color 0.15s;
  }
  .debug-toggle:hover { color:#475569; background:#f1f5f9; }
  .debug-content { padding: 0 16px 12px; }
  .debug-content.hidden { display: none; }
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

_FOOTER = """</div>
<script>
function toggleDebug(btn) {
  var content = btn.nextElementSibling;
  var hidden = content.classList.toggle("hidden");
  btn.textContent = hidden ? "▶ Debug 信息" : "▼ Debug 信息";
}
</script>
</body></html>"""


# ===================================================================
# 查询执行与分页（带缓存）
# ===================================================================


class ReportResult:
    """封装报表查询结果"""

    def __init__(self, columns: list[str], rows: list[tuple],
                 total: int, page: int, page_size: int):
        self.columns = columns
        self.rows = rows
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = math.ceil(total / page_size) if page_size > 0 else 1


def execute_report(report_id: int, sql_query: str, pool_config: dict,
                   page: int = 1, page_size: int = 20,
                   sorts=None, filters=None,
                   refresh: bool = False) -> ReportResult:
    """
    执行报表查询（优先使用缓存），支持多字段排序/筛选/分页。

    sorts:   list[(col, dir), ...]  或 None
    filters: list[(col, q), ...]    或 None
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
            columns, all_rows = db.execute_mysql_query(conn, clean_sql)
        finally:
            conn.close()
        _query_cache.set(report_id, columns, all_rows, sql_query)
    else:
        columns = cached.columns
        all_rows = cached.rows

    # 多字段筛选（AND）
    filtered = _filter_rows(all_rows, columns, filters or [])
    # 多字段排序
    sorted_rows = _sort_rows(filtered, columns, sorts or [])

    total = len(sorted_rows)
    offset = (page - 1) * page_size
    page_rows = sorted_rows[offset:offset + page_size]

    return ReportResult(columns, page_rows, total, page, page_size)


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
                       refresh: bool = False) -> str:
    """
    渲染报表数据展示页，支持多字段排序/筛选。
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

    try:
        result = execute_report(report_id, report["sql_query"], pool_config,
                                page, page_size, sorts or [], filters or [], refresh)
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

    return _build_report_html(conn, report, result, pool_config,
                              sorts or [], filters or [], refresh)


# ===================================================================
# HTML 构建（核心）
# ===================================================================


def _build_report_html(conn, report: dict, result: ReportResult,
                       pool_config: dict = None,
                       sorts=None, filters=None,
                       refresh: bool = False) -> str:
    """
    构建完整的报表 HTML。sorts/filters 均为列表。
    """
    sorts = sorts or []
    filters = filters or []
    report_id = report["id"]
    qs_page_size = result.page_size

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
    debug_lines.append(f'SQL: <code>{_escape(report["sql_query"])}</code>')
    if filters:
        filter_desc = " AND ".join(f'{_escape(c)} 包含 "{_escape(q)}"' for c, q in filters)
        debug_lines.append(f'筛选: {filter_desc}')
    if sorts:
        sort_desc = ", ".join(f'{_escape(c)} {"↑" if d == "asc" else "↓"}' for c, d in sorts)
        debug_lines.append(f'排序: {sort_desc}')
    debug_html = (
        '<div class="debug-info">'
        '<button class="debug-toggle" onclick="toggleDebug(this)" type="button">▶ Debug 信息</button>'
        '<div class="debug-content hidden">' + '<br>'.join(debug_lines) + '</div>'
        '</div>')

    # ---- 构建多字段筛选表单（单 Form，filter inputs 用 form 属性关联） ----
    filter_form_id = "ff"
    form_hidden = [f'<input type="hidden" name="id" value="{report_id}">',
                   f'<input type="hidden" name="page_size" value="{qs_page_size}">']
    # 排序状态（hidden，表单提交时保留）
    for col, dir_ in sorts:
        form_hidden.append(f'<input type="hidden" name="sort" value="{_escape(col)}">')
        form_hidden.append(f'<input type="hidden" name="dir" value="{_escape(dir_)}">')
    form_hidden_str = "\n    ".join(form_hidden)

    # ---- 构建表头（排序链接 + 筛选输入框） ----
    thead_parts = ["<tr>"]
    for col in result.columns:
        # ---- 排序链接 ----
        # 点击当前列：ASC → DESC → 移除
        current_dir = None
        for c, d in sorts:
            if c == col:
                current_dir = d
                break
        if current_dir == "asc":
            new_dir = "desc"
            arrow = " ▲"
            remove_sort = False
        elif current_dir == "desc":
            new_dir = None      # 移除
            arrow = " ▼"
            remove_sort = True
        else:
            new_dir = "asc"
            arrow = ""
            remove_sort = False

        # 构建排序 URL：移除其他列的 sort，保留当前列的 toggle
        if remove_sort:
            new_sorts = [(c, d) for c, d in sorts if c != col]
        else:
            # 只保留当前列的排序（移除其他）
            new_sorts = [(col, new_dir)]

        sort_href = f"/report?id={report_id}&page_size={qs_page_size}"
        if new_sorts:
            sort_href += "&" + _build_sort_params(new_sorts)
        # 保留所有筛选参数
        if filters:
            sort_href += "&" + _build_filter_params(filters)

        arrow_cls = "sort-arrow active" if current_dir else "sort-arrow"

        # ---- 筛选输入 ----
        cur_fval = ""
        for c, q in filters:
            if c == col:
                cur_fval = _escape(q)
                break
        # 列名作为表单字段名：f_{urlencoded_col}
        filter_input_name = "f_" + urllib.parse.quote(col, safe='')

        thead_parts.append(f"""<th>
  <a href="{sort_href}" class="sort-link">{_escape(col)}<span class="{arrow_cls}">{arrow}</span></a>
  <input type="text" class="filter-input" form="{filter_form_id}"
    name="{filter_input_name}" placeholder="筛选 {_escape(col)}..."
    value="{cur_fval}"
    onchange="document.getElementById('{filter_form_id}').submit()">
</th>""")
    thead_parts.append("</tr>")
    thead_str = "".join(thead_parts)

    # ---- 数据行 ----
    tbody = ""
    if not result.rows:
        tbody = ('<tr class="empty-state-row">'
                 '<td colspan="999"><div class="empty-state">'
                 '<div class="icon">📭</div>暂无数据</div></td></tr>')
    else:
        for row in result.rows:
            tbody += "<tr>" + "".join(f"<td>{_escape(v)}</td>" for v in row) + "</tr>"

    # ---- 分页 ----
    pagination = _build_pagination(report_id, result.page, result.total_pages,
                                   result.page_size, result.total, sorts, filters)

    # ---- 缓存状态 ----
    cached = _query_cache.get(report_id, report["sql_query"])
    if cached:
        cache_badge = ('<span class="cache-badge fresh">'
                       f'缓存中 ({int(time.time() - cached.timestamp)}s 前刷新)'
                       '</span>')
    else:
        cache_badge = '<span class="cache-badge">未缓存</span>'

    # ---- 控制栏 ----
    # 控制栏表单：携带所有状态（筛选+排序）
    controls = f"""
<div class="controls">
  <form method="get" action="/report" style="display:inline-flex;align-items:center;gap:12px">
    <input type="hidden" name="id" value="{report_id}">
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {(''.join(f'<input type="hidden" name="f_{urllib.parse.quote(c, safe="")}" value="{_escape(q)}">' for c, q in filters)) if filters else ''}
    <label>每页行数:
      <select name="page_size" onchange="this.form.submit()">
        {''.join(f'<option value="{s}"{" selected" if qs_page_size == s else ""}>{s}</option>'
                 for s in [10, 20, 50, 100, 200])}
      </select>
    </label>
    <noscript><button type="submit" class="btn btn-primary btn-sm">刷新</button></noscript>
  </form>
  <a href="/export?id={report_id}{('&'+_build_filter_params(filters)) if filters else ''}">
    <button type="button" class="btn btn-success btn-sm">导出 CSV</button>
  </a>
  <a href="/report?id={report_id}&page_size={qs_page_size}{('&'+_build_sort_params(sorts)) if sorts else ''}{('&'+_build_filter_params(filters)) if filters else ''}&refresh=1" class="btn-refresh">⟳ 重建缓存</a>
  {cache_badge}
  <span class="stat">共 {result.total} 行，{result.total_pages} 页</span>
</div>"""

    # ---- 筛选清除提示 ----
    clear_html = ""
    if filters:
        clear_href = f"/report?id={report_id}&page_size={qs_page_size}"
        if sorts:
            clear_href += "&" + _build_sort_params(sorts)
        filter_summary = "、".join(f'{_escape(c)}="{_escape(q)}"' for c, q in filters)
        clear_html = (f'<div style="margin-bottom:12px;font-size:13px;color:#64748b">'
                      f'筛选: {filter_summary} '
                      f'<a href="{clear_href}" class="clear-filter">✕ 全部清除</a></div>')

    # ---- 单 Form（filter inputs 通过 form 属性关联到此 form） ----
    filter_form_html = f'<form id="{filter_form_id}" method="get" action="/report" style="display:none">\n  {form_hidden_str}\n</form>'

    body = (_PAGE_HEADER +
            _build_report_switcher(conn, report_id) +
            f'<div class="card">'
            f'<h2>{_escape(report["name"])}</h2>' +
            debug_html +
            controls +
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
                      sorts=None, filters=None) -> str:
    """构建分页 HTML，携带多字段排序/筛选参数"""
    sorts = sorts or []
    filters = filters or []
    if total_pages <= 1:
        return ""

    # 基础 URL
    base_url = f"/report?id={report_id}&page_size={page_size}"
    if sorts:
        base_url += "&" + _build_sort_params(sorts)
    if filters:
        base_url += "&" + _build_filter_params(filters)

    parts = []

    if current > 1:
        parts.append(f'<a href="{base_url}&page={current - 1}" class="nav-arrow">‹</a>')
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
            parts.append(f'<a href="{base_url}&page={p}" class="page-btn">{p}</a>')
        prev = p

    if current < total_pages:
        parts.append(f'<a href="{base_url}&page={current + 1}" class="nav-arrow">›</a>')
    else:
        parts.append('<span class="disabled">›</span>')

    jump = (
        f'<span class="jump-box">跳转到: '
        f'<input type="number" id="jump_page" min="1" max="{total_pages}" '
        f'value="{current}"> '
        f'<button class="btn btn-primary btn-sm" '
        f'onclick="window.location.href=\'{base_url}&page=\' + '
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
    解析多字段排序/筛选/刷新缓存等参数。
    """
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

    # 刷新缓存
    refresh = _qs_val(qs, "refresh") or ""
    refresh_flag = refresh in ("1", "true", "yes")

    html = render_report_page(conn, report_id, page, page_size, pool_override,
                              sorts, filters, refresh_flag)
    return "200", html, {}
