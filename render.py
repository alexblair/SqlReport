"""
render.py — HTML 渲染模板层

职责：
提供基于 string.Template 的公共 HTML 渲染函数，统一页面头/尾/导航栏/
CSS/JS 资源。避免 report.py 和 config.py 各自维护一套 HTML 模板。

设计原则：
- 使用 string.Template（Python 标准库），零外部依赖
- 模板为 Python 字符串常量，无外部模板文件
- 渲染函数接收纯数据 dict，返回 HTML 字符串
- 页面特定的 CSS/JS 通过参数传入，不包含在公共模板中
"""

import string
import html as html_mod
import urllib.parse
import time
import json
from decimal import Decimal
import redis_cache

# ---------------------------------------------------------------------------
# 公共 CSS（report.py + config.py 公共子集合并去重）
# ---------------------------------------------------------------------------

_COMMON_CSS = """
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
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.card {
  background: #fff; border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  padding: 24px; margin-bottom: 20px; animation: fadeUp 0.3s ease-out;
}
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
.btn-danger { background: #dc2626; color: #fff; box-shadow: 0 2px 8px rgba(220,38,38,0.3); }
.btn-danger:hover { background: #b91c1c; transform: translateY(-1px); }
.btn-outline { background: transparent; color: #475569; border: 1px solid #e2e8f0; }
.btn-outline:hover { background: #f8fafc; border-color: #cbd5e1; }
.btn-sm { padding: 5px 12px; font-size: 13px; }
table {
  border-collapse: separate; border-spacing: 0; width: 100%; font-size: 14px;
}
th {
  background: #f8fafc; color: #475569; font-weight: 600; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.5px; padding: 12px 14px;
  border-bottom: 2px solid #e2e8f0; text-align: left; white-space: nowrap;
}
td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; text-align: left; }
tbody tr:hover { background: #f8fafc; }
tbody tr:last-child td { border-bottom: none; }
.table-wrap { overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
.flash {
  padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;
  font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 10px;
}
.flash-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.flash-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.flash-info { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.empty-state { text-align: center; color: #94a3b8; padding: 32px 14px; font-size: 14px; }
"""

# ---------------------------------------------------------------------------
# 公共 JavaScript（交互式 UI 组件）
# ---------------------------------------------------------------------------

_COMMON_JS = r"""
function toggleSection(btn, label) {
  var content = btn.nextElementSibling;
  var hidden = content.classList.toggle("hidden");
  btn.textContent = hidden ? "\u25b6 " + label : "\u25bc " + label;
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
function copyRulesJson() {
  var el = document.getElementById('current-rules-json');
  if (!el) return;
  var text = el.value || el.textContent || el.innerText;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(function(){});
  } else {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}
function applyRulesJson() {
  var ta = document.getElementById('current-rules-json');
  if (!ta) return;
  var text = ta.value.trim();
  if (!text) { alert('请输入规则 JSON'); return; }
  var rules;
  try { rules = JSON.parse(text); } catch (e) {
    alert('JSON 格式错误: ' + e.message); return;
  }
  var params = new URLSearchParams(window.location.search);
  var keysToRemove = [];
  params.forEach(function(_, k) {
    if (k.startsWith('f_') || k.startsWith('op_') || k.startsWith('s_') || k === 'cols' || k === 'page') {
      keysToRemove.push(k);
    }
  });
  keysToRemove.forEach(function(k) { params.delete(k); });
  if (rules.filters && rules.filters.length) {
    rules.filters.forEach(function(f) {
      params.set('f_' + f.col, f.val || '');
      if (f.op && f.op !== 'contains') params.set('op_' + f.col, f.op);
    });
  }
  if (rules.sorts && rules.sorts.length) {
    rules.sorts.forEach(function(s) { params.set('s_' + s.col, s.dir || 'asc'); });
  }
  if (rules.columns) params.set('cols', rules.columns);
  params.set('page', '1');
  window.location.href = '?' + params.toString();
}
"""

# ---------------------------------------------------------------------------
# SQL 格式化与高亮 JS（config.py 与 report.py 共享）
# ---------------------------------------------------------------------------

_SQL_HIGHLIGHT_JS = r"""
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
"""

_SQL_FORMATTER_JS = r"""
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
"""

# ---------------------------------------------------------------------------
# 公共模板
# ---------------------------------------------------------------------------

_PAGE_HEADER_TEMPLATE = string.Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>${common_css}${extra_css}</style>
</head>
<body>
$navbar
<div class="container">
""")

_PAGE_FOOTER = """</div>
<script>""" + _COMMON_JS + """</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 导航栏链接定义
# ---------------------------------------------------------------------------

_NAV_ITEMS = [
    ("report", "/report", "报表页"),
    ("config", "/config", "配置管理"),
    ("audit", "/audit", "审计日志"),
    ("logout", "/logout", "退出"),
]


def _build_navbar_html(active: str = "") -> str:
    """
    构建导航栏 HTML。

    Args:
        active: 当前活动页标识（report / config / logout），为空时无高亮。

    Returns:
        导航栏 HTML 字符串。
    """
    links_html = ""
    for key, href, label in _NAV_ITEMS:
        cls = ' class="nav-active"' if key == active else ""
        links_html += f'<a href="{href}"{cls}>{html_mod.escape(label)}</a>\n  '
    return (
        '<div class="navbar">\n'
        '  <a href="/" class="brand">My<span>Report</span></a>\n'
        '  <div class="spacer"></div>\n'
        f'  {links_html}'
        '</div>'
    )


# ---------------------------------------------------------------------------
# 公开渲染函数
# ---------------------------------------------------------------------------


def render_navbar(active: str = "") -> str:
    """
    渲染导航栏。

    Args:
        active: 当前活动页标识（report / config / logout），为空时无高亮。

    Returns:
        导航栏 HTML 字符串。
    """
    return _build_navbar_html(active)


def render_page_header(title: str = "Web 报表工具",
                       active_nav: str = "",
                       extra_css: str = "") -> str:
    """
    渲染页面头部（<head> + 导航栏 + container 开头）。

    Args:
        title: 页面标题（显示在浏览器标签页）。
        active_nav: 当前活动页标识，传给导航栏用于高亮。
        extra_css: 页面特定的额外 CSS 内容，追加在公共 CSS 之后。

    Returns:
        从 DOCTYPE 到 <div class="container"> 的完整头部 HTML。
    """
    navbar_html = _build_navbar_html(active_nav)
    return _PAGE_HEADER_TEMPLATE.substitute(
        title=title.replace("$", "$$"),
        common_css=_COMMON_CSS,
        extra_css=extra_css.replace("$", "$$"),
        navbar=navbar_html,
    )


def render_page_footer() -> str:
    """
    渲染页面尾部（container 闭合 + 脚本 + </body></html>）。

    Returns:
        从 </div> 到 </html> 的完整尾部 HTML。
    """
    return _PAGE_FOOTER


# ===================================================================
# 筛选操作符定义（从 report.py 移入）
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
# 单元格格式化与 HTML 转义（从 report.py 移入）
# ===================================================================


def format_cell(val) -> str:
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
    return html_mod.escape(format_cell(val))


# ===================================================================
# URL 参数工具（从 report.py 移入）
# ===================================================================


def build_sort_params(sorts):
    """将 sorts 列表编码为 URL 查询字符串（sort=col&dir=asc 重复）。"""
    parts = []
    for col, dir_ in sorts:
        parts.append(f"sort={urllib.parse.quote(col, safe='')}&dir={urllib.parse.quote(dir_, safe='')}")
    return "&".join(parts)


def build_filter_params(filters, skip_col=None):
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


def filter_hidden_inputs(filters) -> str:
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


def build_cols_param(display_columns: list[str], all_columns: list[str]) -> str:
    """
    构建 cols URL 查询参数字符串。
    仅在用户自定义了列顺序或隐藏了列时生成参数，否则返回空字符串。
    """
    if display_columns == list(all_columns):
        return ""
    return "cols=" + urllib.parse.quote(",".join(display_columns), safe='')


# ===================================================================
# HTML 渲染函数（从 report.py 移入）
# ===================================================================


def build_pagination_html(report_id: int, current: int, total_pages: int,
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
        base_url += "&amp;" + build_sort_params(sorts)
    if filters:
        base_url += "&amp;" + build_filter_params(filters)
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


def build_redis_banners_html(cache_info) -> str:
    """构建 Redis 降级/兜底提示横幅。"""
    if not cache_info:
        return ""
    src = cache_info.get("source", "")
    banners = []

    if src == "redis":
        ts = cache_info.get("timestamp")
        if ts:
            from datetime import datetime
            dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            banners.append(
                f'<div class="flash flash-info">'
                f'数据来自 Redis 快照（{_escape(dt_str)}）</div>'
            )
    elif src == "mysql":
        if not redis_cache.redis_available():
            banners.append(
                '<div class="flash flash-info">'
                'Redis 不可用，已切换至直连 MySQL 模式'
                '</div>'
            )

    return "".join(banners)


def build_debug_section_html(pool_config, actual_sql, active_index,
                              num_results, result_names, filters, sorts) -> str:
    """构建 Debug 信息折叠区 HTML。"""
    sorts = sorts or []
    filters = filters or []
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
    return debug_html


def build_current_rules_section_html(filters, sorts, display_columns: list[str],
                                     all_columns: list[str]) -> str:
    """
    构建当前规则输出折叠区 HTML。
    展示当前报表使用的筛选/排序/字段规则为 JSON 格式，提供复制按钮，
    方便用户将规则粘贴到 API 接口配置表单。
    """
    sorts = sorts or []
    filters = filters or []

    # 构建 JSON 规则对象
    rules = {}
    if filters:
        rules["filters"] = [
            {"col": c, "op": o, "val": v}
            for c, o, v in filters
        ]
    if sorts:
        rules["sorts"] = [
            {"col": c, "dir": d}
            for c, d in sorts
        ]
    if display_columns and display_columns != all_columns:
        rules["columns"] = ",".join(display_columns)
    else:
        rules["columns"] = ""

    rules_json = json.dumps(rules, indent=2, ensure_ascii=False)

    # 可读摘要
    summary_parts = []
    if filters:
        filter_summary = " AND ".join(
            f'{_escape(c)} {_escape(_OP_MAP.get(o, [o, o])[1])} "{_escape(v)}"'
            for c, o, v in filters
        )
        summary_parts.append(f'筛选: {filter_summary}')
    if sorts:
        sort_summary = ", ".join(
            f'{_escape(c)} {"↑" if d == "asc" else "↓"}'
            for c, d in sorts
        )
        summary_parts.append(f'排序: {sort_summary}')
    if display_columns and display_columns != all_columns:
        summary_parts.append(f'字段: {", ".join(_escape(c) for c in display_columns)}')
    if not summary_parts:
        summary_parts.append("无自定义规则（显示全部字段和数据）")

    html = (
        '<div class="debug-info" style="margin-top:8px">'
        '<button class="debug-toggle" onclick="toggleSection(this, \'当前规则\')" type="button">▶ 当前规则</button>'
        '<div class="debug-content hidden">'
        '<div style="margin-bottom:8px;line-height:1.6">'
        + '<br>'.join(summary_parts) +
        '</div>'
        '<div style="position:relative">'
        '<textarea id="current-rules-json" style="width:100%;background:#1e293b;color:#e2e8f0;padding:12px;'
        'border-radius:6px;font-size:13px;line-height:1.5;font-family:monospace;border:1px solid #334155;'
        'resize:vertical;margin:0;min-height:80px" spellcheck="false">'
        f'{_escape(rules_json)}</textarea>'
        '<div style="margin-top:6px;display:flex;gap:6px">'
        '<button onclick="copyRulesJson()" style="padding:4px 10px;font-size:12px;background:#4f46e5;color:#fff;border:none;'
        'border-radius:4px;cursor:pointer">复制</button>'
        '<button onclick="applyRulesJson()" style="padding:4px 10px;font-size:12px;background:#059669;color:#fff;border:none;'
        'border-radius:4px;cursor:pointer">应用</button>'
        '</div>'
        '</div>'
        '<div style="margin-top:6px;font-size:12px;color:#94a3b8">'
        '提示: 在 API 接口配置中填入以上 JSON 规则，即可复用当前报表的筛选/排序/字段设置。'
        '</div>'
        '</div>'
        '</div>'
    )
    return html


def build_memo_section_html(memo_raw: str) -> str:
    """构建备注折叠区 HTML。"""
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
    return memo_html


def build_result_selector_html(report_id, qs_page_size, result_names,
                                active_index, sql_override, swi) -> str:
    """构建多结果集切换下拉框 HTML。"""
    num_results = len(result_names)
    if num_results <= 1:
        return ""
    opts = "".join(
        f'<option value="{i}"{" selected" if i == active_index else ""}>{_escape(result_names[i])}</option>'
        for i in range(num_results)
    )
    qs_parts = [f"id={report_id}", f"page_size={qs_page_size}"]
    if sql_override:
        qs_parts.append(f"sql_query={urllib.parse.quote(sql_override)}")
    base_qs = "&".join(qs_parts)
    return (
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


def build_cache_badge_html(cache_info, prefer_cache: bool = False,
                           cache_ttl_hours: int = 0) -> str:
    """构建缓存状态标签 HTML。

    当 prefer_cache=True 且 cache_ttl_hours>0 时，额外显示 TTL 信息。
    """
    extra = ""
    if prefer_cache:
        extra = " prefer_cache"
        if cache_ttl_hours > 0:
            extra += f" | TTL={cache_ttl_hours}h"
    if cache_info:
        src = cache_info.get("source", "")
        ts = cache_info.get("timestamp")
        if src == "redis":
            age = int(time.time() - ts) if ts else 0
            return ('<span class="cache-badge fresh">'
                    f'Redis 快照 ({age}s 前{extra})'
                    '</span>')
        elif src == "redis_fallback":
            age = int(time.time() - ts) if ts else 0
            return ('<span class="cache-badge" '
                    'style="background:#fef3c7;color:#92400e">'
                    f'缓存快照（{age}s 前{extra}，MySQL 不可用）'
                    '</span>')
        elif src == "process":
            age = int(time.time() - ts) if ts else 0
            return ('<span class="cache-badge fresh">'
                    f'进程缓存 ({age}s 前刷新{extra})'
                    '</span>')
        else:
            badge = '直连 MySQL'
            if extra:
                badge += f' ({extra.strip()})'
            return f'<span class="cache-badge">{badge}</span>'
    else:
        badge = '未缓存'
        if extra:
            badge += f' ({extra.strip()})'
        return f'<span class="cache-badge">{badge}</span>'


def build_sort_bar_html(report_id, page_size, sorts, filters,
                         cols_param, result_param) -> str:
    """构建排序栏（显示当前排序列及其优先级）HTML。"""
    sorts = sorts or []
    filters = filters or []
    sort_bar_parts = []
    if sorts:
        sort_bar_parts.append('<div class="sort-bar" style="margin-bottom:10px;font-size:13px;display:flex;align-items:center;gap:6px;flex-wrap:wrap">')
        sort_bar_parts.append('<span style="color:#475569;font-weight:500">排序:</span>')
        for idx, (sc, sd) in enumerate(sorts, 1):
            label = f'{_escape(sc)} {"↑" if sd == "asc" else "↓"}'
            prio = chr(0x2460 + idx - 1) if idx <= 20 else f"#{idx}"
            rm_sorts = [(c, d) for c, d in sorts if c != sc]
            rm_href = f"/report?id={report_id}&amp;page_size={page_size}"
            if rm_sorts:
                rm_href += "&amp;" + build_sort_params(rm_sorts)
            if filters:
                rm_href += "&amp;" + build_filter_params(filters)
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
    return "".join(sort_bar_parts)


def build_table_header_html(columns, display_columns, sorts, filters,
                             report_id, page_size, cols_param, result_param) -> str:
    """构建表头 HTML（含排序双箭头 + 筛选操作符下拉框 + 筛选输入框）。"""
    sorts = sorts or []
    filters = filters or []
    filter_form_id = "ff"
    thead_parts = ["<tr>"]
    for col in display_columns:
        current_dir = None
        sort_priority = 0
        for idx, (c, d) in enumerate(sorts, 1):
            if c == col:
                current_dir = d
                sort_priority = idx
                break

        asc_sorts = list(sorts)
        found_asc = False
        for i, (c, d) in enumerate(asc_sorts):
            if c == col:
                asc_sorts[i] = (col, "asc")
                found_asc = True
                break
        if not found_asc:
            asc_sorts.append((col, "asc"))
        asc_href = f"/report?id={report_id}&amp;page_size={page_size}"
        asc_href += "&amp;" + build_sort_params(asc_sorts)
        if filters:
            asc_href += "&amp;" + build_filter_params(filters)
        if cols_param:
            asc_href += "&amp;" + cols_param
        if result_param:
            asc_href += "&amp;" + result_param
        asc_cls = "sort-arrow active" if current_dir == "asc" else "sort-arrow"

        desc_sorts = list(sorts)
        found_desc = False
        for i, (c, d) in enumerate(desc_sorts):
            if c == col:
                desc_sorts[i] = (col, "desc")
                found_desc = True
                break
        if not found_desc:
            desc_sorts.append((col, "desc"))
        desc_href = f"/report?id={report_id}&amp;page_size={page_size}"
        desc_href += "&amp;" + build_sort_params(desc_sorts)
        if filters:
            desc_href += "&amp;" + build_filter_params(filters)
        if cols_param:
            desc_href += "&amp;" + cols_param
        if result_param:
            desc_href += "&amp;" + result_param
        desc_cls = "sort-arrow active" if current_dir == "desc" else "sort-arrow"

        priority_badge = ""
        if sort_priority > 0:
            prio_char = chr(0x2460 + sort_priority - 1) if sort_priority <= 20 else f"#{sort_priority}"
            priority_badge = f'<span class="sort-prio" style="font-size:10px;color:#4f46e5;font-weight:700;margin-left:2px">{prio_char}</span>'

        cur_fval = ""
        cur_op = "nofilter"
        for item in filters:
            c, op, val = item
            if c == col:
                cur_fval = val
                cur_op = op
                break

        filter_input_name = "f_" + urllib.parse.quote(col, safe='')
        filter_op_name = "op_" + urllib.parse.quote(col, safe='')

        op_options = ""
        for code, label, short in FILTER_OPS:
            sel = ' selected' if code == cur_op else ''
            op_options += f'<option value="{code}"{sel}>{_escape(label)}</option>'

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
    return "".join(thead_parts)


def build_table_body_html(rows, display_indices) -> str:
    """构建表格数据行 HTML。"""
    tbody = ""
    if not rows:
        tbody = ('<tr class="empty-state-row">'
                 '<td colspan="999"><div class="empty-state">'
                 '<div class="icon">📭</div>暂无数据</div></td></tr>')
    else:
        for row in rows:
            cells = "".join(f"<td>{_escape(row[i])}</td>" for i in display_indices)
            tbody += "<tr>" + cells + "</tr>"
    return tbody


def build_controls_bar_html(report_id, page_size, sorts, filters,
                             cols_param, display_columns, active_index,
                             cache_badge, total_rows, total_pages,
                             result_param='') -> str:
    """构建控制栏 HTML（分页控件、导出表单、缓存状态等）。
    result_param: 多结果集时的 URL 参数字符串（如 "result=0"），仅当 num_results > 1 时非空。
    """
    sorts = sorts or []
    filters = filters or []
    cols_hidden = f'<input type="hidden" name="cols" value="{_escape(",".join(display_columns))}">' if cols_param else ""
    return f"""
<div class="controls">
  <form method="get" action="/report" style="display:inline-flex;align-items:center;gap:12px">
    <input type="hidden" name="id" value="{report_id}">
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    <label>每页行数:
      <select name="page_size" onchange="this.form.submit()">
        {''.join(f'<option value="{s}"{" selected" if page_size == s else ""}>{s}</option>'
                 for s in [10, 20, 50, 100, 200])}
      </select>
    </label>
    <noscript><button type="submit" class="btn btn-primary btn-sm">刷新</button></noscript>
  </form>
  <form method="get" action="/export" style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">
    <input type="hidden" name="id" value="{report_id}">
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    {''.join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {filter_hidden_inputs(filters) if filters else ''}
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
   <a href="/report?id={report_id}&amp;page_size={page_size}{('&amp;'+build_sort_params(sorts)) if sorts else ''}{('&amp;'+build_filter_params(filters)) if filters else ''}{('&amp;'+cols_param) if cols_param else ''}{'&amp;'+result_param if result_param else ''}&amp;refresh=1" class="btn-refresh">⟳ 重建缓存</a>
  {cache_badge}
  <span class="stat">共 {total_rows} 行，{total_pages} 页</span>
</div>"""


def build_field_settings_panel_html(all_columns, display_columns) -> str:
    """构建字段设置面板 HTML。"""
    field_settings_items = []
    for idx, col in enumerate(all_columns):
        checked = "checked" if col in display_columns else ""
        pos = display_columns.index(col) if col in display_columns else -1
        up_disabled = "disabled" if pos <= 0 else ""
        down_disabled = "disabled" if pos >= len(display_columns) - 1 or pos < 0 else ""
        bg_color = '#f8fafc' if col in display_columns else '#fff'
        field_settings_items.append(
            f'<label class="field-item" draggable="true" style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
            f'border:1px solid #e2e8f0;border-radius:6px;background:{bg_color};'
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
    return field_settings_html


def build_sort_settings_panel_html(sorts, all_columns) -> str:
    """构建排序管理面板 HTML。"""
    sorts = sorts or []
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
    return sort_settings_html


def build_filter_form_html(form_id: str, form_hidden_str: str) -> str:
    """构建隐藏筛选表单 HTML。"""
    return f'<form id="{form_id}" method="get" action="/report" style="display:none">\n  {form_hidden_str}\n</form>'


def build_filter_action_html(report_id, page_size, sorts, cols_param,
                              result_param, filters) -> tuple:
    """构建筛选操作按钮和清除筛选提示 HTML。"""
    sorts = sorts or []
    filters = filters or []
    clear_href = f"/report?id={report_id}&amp;page_size={page_size}"
    if sorts:
        clear_href += "&amp;" + build_sort_params(sorts)
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

    return filter_action_html, clear_html


def build_report_switcher_html(reports_data, all_cats, cat_tree,
                                current_id=None) -> str:
    """构建报表切换下拉框 HTML（按分类层级树状呈现，纯 HTML 渲染，无 DB 调用）。"""
    cat_reports: dict[int, list] = {}
    uncategorized: list = []
    for r in reports_data:
        cid = r.get("category_id")
        if cid is not None:
            cat_reports.setdefault(cid, []).append(r)
        else:
            uncategorized.append(r)

    def _render_tree_switcher(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            if rpts or node.get("children", []):
                label = f"{indent}{node['name']}"
                html += f'<optgroup label="{_escape(label)}">'
                for r in rpts:
                    sel = ' selected' if r["id"] == current_id else ''
                    html += f'<option value="{r["id"]}"{sel}>{_escape(r["name"])}</option>'
                if node.get("children", []):
                    html += _render_tree_switcher(node["children"], depth + 1)
                html += "</optgroup>"
            else:
                html += f'<option value="" disabled style="color:#94a3b8;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</option>'
                if node.get("children", []):
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


# ===================================================================
# 配置页渲染函数（从 config.py 移入）
# ===================================================================


def _link_btn(url: str, label: str, cls: str = "btn btn-outline btn-sm") -> str:
    """生成链接按钮"""
    return f'<a href="{_escape(url)}" class="{cls}">{_escape(label)}</a>'


def build_move_buttons_html(item_id: int, section: str, index: int, total: int) -> str:
    """
    生成上下移动按钮的 HTML。

    统一处理连接池/报表/分类列表中的上移/下移按钮。
    在三个地方使用：连接池列表、分类列表中的分类项、分类列表中的报表行。

    Args:
        item_id: 被移动项的数据库 ID。
        section: 配置段名称（pools / reports / categories），对应 URL 路径。
        index: 当前项在列表中的序号（从 0 开始）。
        total: 列表总项数。

    Returns:
        移动按钮的 HTML 字符串（空字符串表示无需显示按钮）。
    """
    if total <= 1:
        return ""
    html = ""
    if index > 0:
        html += (f'<form method="post" action="/config/{section}/{item_id}/move-up" style="display:inline">'
                 f'<button type="submit" class="btn btn-outline btn-sm" title="上移">↑</button></form> ')
    if index < total - 1:
        html += (f'<form method="post" action="/config/{section}/{item_id}/move-down" style="display:inline">'
                 f'<button type="submit" class="btn btn-outline btn-sm" title="下移">↓</button></form> ')
    return html


def build_pool_form_html(pool: dict = None, copy_mode: bool = False) -> str:
    """渲染连接池编辑/新增/复制表单（纯数据 → HTML，无 DB 调用）"""
    is_edit = pool is not None and not copy_mode
    is_copy = pool is not None and copy_mode
    if is_edit:
        action_url = f"/config/pools/{pool['id']}/edit"
        title = "编辑连接池"
    elif is_copy:
        action_url = f"/config/pools/{pool['id']}/copy"
        title = "复制连接池"
    else:
        action_url = "/config/pools/add"
        title = "新增连接池"

    name = _escape(pool["name"] if pool else "")
    host = _escape(pool["host"] if pool else "")
    port = str(pool["port"]) if pool else "3306"
    user = _escape(pool["user"] if pool else "")
    password = _escape(pool["password"] if (pool and is_edit) else "")
    database = _escape(pool["database"] if pool else "")

    if is_copy:
        # 复制时自动加后缀，允许用户改名
        name = _escape(pool["name"] + " (副本)")
        password = _escape(pool["password"])

    return f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form">
  <label>名称: <input type="text" name="name" value="{name}" required></label>
  <label>主机地址: <input type="text" name="host" value="{host}" placeholder="例如 127.0.0.1" required></label>
  <label>端口: <input type="number" name="port" value="{port}" required></label>
  <label>用户名: <input type="text" name="user" value="{user}" required></label>
  <label>密码: <input type="password" name="password" value="{password}" required></label>
  <label>数据库: <input type="text" name="database" value="{database}" required></label>
  <div class="form-actions">
    <button type="submit" class="btn btn-primary">保存</button>
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
</div>"""


def build_user_form_html(user: dict = None) -> str:
    """渲染用户编辑/新增表单（纯数据 → HTML，无 DB 调用）"""
    is_edit = user is not None
    action_url = f"/config/users/{user['id']}/edit" if is_edit else "/config/users/add"
    title = "编辑用户" if is_edit else "新增用户"
    username = _escape(user["username"] if is_edit else "")
    pw_required = "" if is_edit else "required"
    pw_hint = ' <span style="color:#94a3b8;font-weight:400;font-size:13px">留空则不修改密码</span>' if is_edit else ""
    return f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form">
  <label>用户名: <input type="text" name="username" value="{username}" required></label>
  <label>密码: <input type="password" name="password" value="" {pw_required}>{pw_hint}</label>
  <div class="form-actions">
    <button type="submit" class="btn btn-primary">保存</button>
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
</div>"""


def build_category_opts_html(nodes, depth, cur_cat_id):
    """递归生成分类选项 HTML（树形缩进）（纯数据 → HTML，无 DB 调用）"""
    html = ""
    for node in nodes:
        indent = "　" * depth
        sel = ' selected' if cur_cat_id != "" and str(node["id"]) == str(cur_cat_id) else ''
        html += f'<option value="{node["id"]}"{sel}>{indent}{_escape(node["name"])}</option>'
        if node["children"]:
            html += build_category_opts_html(node["children"], depth + 1, cur_cat_id)
    return html


def _get_cat_depth(cat: dict, all_cats: list[dict]) -> int:
    """计算分类的层级深度（用于缩进显示）。"""
    depth = 0
    seen = set()
    pid = cat.get("parent_id")
    while pid is not None:
        if pid in seen:
            break
        seen.add(pid)
        depth += 1
        parent = next((c for c in all_cats if c["id"] == pid), None)
        if parent:
            pid = parent.get("parent_id")
        else:
            break
    return depth


def build_pool_section_html(pools: list) -> str:
    """渲染连接池配置列表（含复制、排序）（纯数据 → HTML，无 DB 调用）"""
    rows = ""
    pool_count = len(pools)
    for i, p in enumerate(pools):
        move_btns = build_move_buttons_html(p["id"], "pools", i, pool_count)
        rows += f"""<tr>
  <td><strong>{_escape(p['name'])}</strong></td>
  <td><span class="badge badge-pool">{_escape(p['host'])}:{p['port']}</span></td>
  <td>{_escape(p['user'])}</td>
  <td>{_escape(p['database'])}</td>
  <td class="ops-cell">
    {move_btns}
    {_link_btn(f"/config/pools/{p['id']}/edit", "编辑")}
    {_link_btn(f"/config/pools/{p['id']}/copy", "复制")}
    <form method="post" action="/config/pools/{p['id']}/delete" style="display:inline"
          onsubmit="return confirm('确定删除连接池 {_escape(p['name'])}？')">
      <button type="submit" class="btn btn-danger btn-sm">删除</button>
    </form>
  </td>
</tr>"""
    return f"""<div class="section">
<div class="section-title">
  <span>📦 连接池配置</span>
  <span class="actions">{_link_btn("/config/pools/add", "新增连接池", "btn btn-primary btn-sm")}</span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th>名称</th><th>地址</th><th>用户</th><th>数据库</th><th>操作</th>
</tr></thead><tbody>
{rows or '<tr><td colspan="5" class="empty-state">暂无连接池配置</td></tr>'}
</tbody></table>
</div>
</div>"""


def build_user_section_html(users: list) -> str:
    """渲染用户配置列表（纯数据 → HTML，无 DB 调用）"""
    rows = ""
    for u in users:
        rows += f"""<tr>
  <td><strong>{_escape(u['username'])}</strong></td>
  <td class="ops-cell">
    {_link_btn(f"/config/users/{u['id']}/edit", "编辑")}
    <form method="post" action="/config/users/{u['id']}/delete" style="display:inline"
          onsubmit="return confirm('确定删除用户 {_escape(u['username'])}？')">
      <button type="submit" class="btn btn-danger btn-sm">删除</button>
    </form>
  </td>
</tr>"""
    return f"""<div class="section">
<div class="section-title">
  <span>👤 用户配置</span>
  <span class="actions">{_link_btn("/config/users/add", "新增用户", "btn btn-primary btn-sm")}</span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th>用户名</th><th>操作</th>
</tr></thead><tbody>
{rows or '<tr><td colspan="2" class="empty-state">暂无用户</td></tr>'}
</tbody></table>
</div>
</div>"""


def build_category_section_html(cat_reports, unclassified_reports, all_cats,
                                 all_reports, pools, cat_tree,
                                 api_endpoints_map: dict[int, list[dict]] = None) -> str:
    """渲染报表分类配置段（分类管理 + 各分类下的报表列表，纯数据 → HTML，无 DB 调用）

    参数:
        api_endpoints_map: { report_id: [api_endpoint_dict, ...] }，可选。
    """
    pools_map: dict = {p["id"]: p for p in pools}

    # 批量操作：连接池选择 + 分类选择
    pool_opts = '<option value="">-- 请选择 --</option>'
    for p in pools:
        pool_opts += f'<option value="{p["id"]}">{_escape(p["name"])}</option>'
    cat_opts = '<option value="">-- 请选择分类 --</option>'
    for c in all_cats:
        prefix = "　" * _get_cat_depth(c, all_cats)
        cat_opts += f'<option value="{c["id"]}">{prefix}{_escape(c["name"])}</option>'
    cat_opts += '<option value="-1">无分类</option>'
    batch_bar = f"""
<div class="batch-bar" style="display:flex;align-items:center;gap:12px;padding:10px 0;margin-bottom:8px;flex-wrap:wrap">
  <span style="font-size:14px;color:#475569;font-weight:500">
    <span id="batch_count">0</span> 项已选
  </span>
  <select id="batch_pool_id" style="padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:14px">
    {pool_opts}
  </select>
  <button type="button" class="btn btn-primary btn-sm"
    onclick="batchUpdatePool()">批量修改连接池</button>
  <select id="batch_cat_id" style="padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:14px">
    {cat_opts}
  </select>
   <button type="button" class="btn btn-success btn-sm"
    onclick="batchSetCategory()">批量设置分类</button>
   <select id="batch_cache_switch" style="padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:14px">
     <option value="">不改变</option>
     <option value="1">启用缓存</option>
     <option value="0">关闭缓存</option>
   </select>
   <input type="checkbox" id="batch_modify_ttl" onchange="toggleTtlInput()">
   <label for="batch_modify_ttl" style="font-size:13px">修改TTL</label>
   <input type="number" id="batch_cache_ttl" value="0" min="0" step="1"
     style="padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:14px;width:80px;opacity:0.5"
     disabled>
   <span style="font-size:12px;color:#94a3b8">小时（0=永久）</span>
   <button type="button" class="btn btn-info btn-sm"
     onclick="batchUpdateCache()">批量更新缓存配置</button>
</div>
<script>
function batchUpdatePool() {{
  var checkboxes = document.querySelectorAll('.report-checkbox:checked');
  var ids = [];
  for (var i = 0; i < checkboxes.length; i++) {{
    ids.push(checkboxes[i].value);
  }}
  if (ids.length === 0) {{ alert('请至少选择一项'); return; }}
  var poolId = document.getElementById('batch_pool_id').value;
  if (!poolId) {{ alert('请选择目标连接池'); return; }}
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '/config/reports/batch-pool';
  ids.forEach(function(id) {{
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'report_ids'; inp.value = id;
    form.appendChild(inp);
  }});
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'pool_id'; inp.value = poolId;
  form.appendChild(inp);
  document.body.appendChild(form);
  form.submit();
}}
function batchSetCategory() {{
  var checkboxes = document.querySelectorAll('.report-checkbox:checked');
  var ids = [];
  for (var i = 0; i < checkboxes.length; i++) {{
    ids.push(checkboxes[i].value);
  }}
  if (ids.length === 0) {{ alert('请至少选择一项'); return; }}
  var catId = document.getElementById('batch_cat_id').value;
  if (!catId) {{ alert('请选择目标分类'); return; }}
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '/config/reports/batch-set-category';
  ids.forEach(function(id) {{
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'report_ids'; inp.value = id;
    form.appendChild(inp);
  }});
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'category_id'; inp.value = catId === '-1' ? '' : catId;
  form.appendChild(inp);
  document.body.appendChild(form);
  form.submit();
}}
function toggleTtlInput() {{
  var cb = document.getElementById('batch_modify_ttl');
  var inp = document.getElementById('batch_cache_ttl');
  inp.disabled = !cb.checked;
  inp.style.opacity = cb.checked ? '1' : '0.5';
}}
function batchUpdateCache() {{
  var checkboxes = document.querySelectorAll('.report-checkbox:checked');
  var ids = [];
  for (var i = 0; i < checkboxes.length; i++) {{
    ids.push(checkboxes[i].value);
  }}
  if (ids.length === 0) {{ alert('请至少选择一项'); return; }}
  var cacheSwitch = document.getElementById('batch_cache_switch').value;
  var modifyTtl = document.getElementById('batch_modify_ttl').checked;
  if (cacheSwitch === '' && !modifyTtl) {{
    alert('请选择缓存开关或勾选修改TTL');
    return;
  }}
  if (!confirm(`确定批量更新 ${{ids.length}} 个报表的缓存配置？`)) return;
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '/config/reports/batch-cache';
  ids.forEach(function(id) {{
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'report_ids'; inp.value = id;
    form.appendChild(inp);
  }});
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'cache_switch'; inp.value = cacheSwitch;
  form.appendChild(inp);
  if (modifyTtl) {{
    var inp2 = document.createElement('input');
    inp2.type = 'hidden'; inp2.name = 'modify_ttl'; inp2.value = '1';
    form.appendChild(inp2);
    var inp3 = document.createElement('input');
    inp3.type = 'hidden'; inp3.name = 'cache_ttl_hours';
    inp3.value = document.getElementById('batch_cache_ttl').value;
    form.appendChild(inp3);
  }}
  document.body.appendChild(form);
  form.submit();
}}
function updateBatchCount() {{
  var n = document.querySelectorAll('.report-checkbox:checked').length;
  document.getElementById('batch_count').textContent = n;
}}
</script>"""

    def _render_report_rows(report_list, in_category=False):
        """渲染报表列表行（含调序按钮）"""
        rows = ""
        total = len(report_list)
        for idx, r in enumerate(report_list):
            rpt_id = r["id"]
            pool_name = ""
            pool_id = r["pool_id"]
            if pool_id is not None:
                pool = pools_map.get(pool_id)
                if pool:
                    pool_name = pool["name"]
            pool_badge = (
                f'<span class="badge badge-pool">{_escape(pool_name)}</span>'
                if pool_name
                else '<span style="color:#dc2626;font-size:13px">连接池已删除</span>'
            )
            move_btns = build_move_buttons_html(rpt_id, "reports", idx, total)
            memo_raw = r.get("memo") or ""
            if memo_raw:
                memo_display = _escape(memo_raw[:15])
                if len(memo_raw) > 15:
                    memo_display += "..."
            else:
                memo_display = '<span style="color:#cbd5e1">—</span>'

            prefer_cache = int(r.get("prefer_cache", 1))
            prefer_cache_display = (
                '<span style="color:#059669;font-weight:600">是</span>'
                if prefer_cache
                else '<span style="color:#94a3b8">否</span>'
            )
            cache_ttl_hours = int(r.get("cache_ttl_hours", 0))
            cache_ttl_display = f'{cache_ttl_hours}h' if cache_ttl_hours else '<span style="color:#cbd5e1">—</span>'

            # API 接口列
            eps = (api_endpoints_map or {}).get(rpt_id, [])
            if eps:
                total_cnt = len(eps)
                enabled_cnt = sum(1 for ep in eps if int(ep.get("enabled", 1)))
                disabled_cnt = total_cnt - enabled_cnt
                parts = []
                if enabled_cnt:
                    parts.append(f'{enabled_cnt}启用')
                if disabled_cnt:
                    parts.append(f'{disabled_cnt}禁用')
                summary = f'{total_cnt} 个接口 ({" / ".join(parts)})' if parts else f'{total_cnt} 个接口'
                tooltip_lines = []
                for ep in eps:
                    ep_name = ep.get("name", "")
                    ep_path = ep.get("url_path", "")
                    ep_format = ep.get("output_format", "json")
                    ep_enabled = int(ep.get("enabled", 1))
                    ep_status = "启用" if ep_enabled else "禁用"
                    ep_key = "有 Key" if ep.get("api_key") else "无 Key"
                    tooltip_lines.append(f"  [{ep_status}] {ep_name} ({ep_path}) - {ep_format}, {ep_key}")
                tooltip = "\\n".join(tooltip_lines)
                api_cell = f'<a href="/config/reports/{rpt_id}/edit#api-endpoints" style="color:#4f46e5;text-decoration:none;font-size:13px" title="{_escape(tooltip)}">🔌 {summary}</a>'
            else:
                api_cell = '<span style="color:#cbd5e1;font-size:13px">—</span>'

            rows += f"""<tr>
  <td><input type="checkbox" class="report-checkbox" value="{rpt_id}" onchange="updateBatchCount()"></td>
   <td><strong><a href="/report?id={rpt_id}" target="_blank" rel="noopener" style="color:#4f46e5;text-decoration:none">{_escape(r['name'])}</a></strong></td>
  <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;">
    <code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px;color:#475569">{_escape(r['sql_query'][:80])}{'...' if len(r['sql_query']) > 80 else ''}</code>
  </td>
  <td>{r['default_page_size']}</td>
  <td>{pool_badge}</td>
  <td style="text-align:center">{prefer_cache_display}</td>
  <td style="text-align:center">{cache_ttl_display}</td>
  <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;color:#64748b;font-size:13px">{memo_display}</td>
  <td style="text-align:center;white-space:nowrap">{api_cell}</td>
  <td class="ops-cell">
    {move_btns}
    {_link_btn(f"/config/reports/{rpt_id}/edit", "编辑")}
    {_link_btn(f"/config/reports/{rpt_id}/copy", "复制")}
    <form method="post" action="/config/reports/{rpt_id}/delete" style="display:inline"
          onsubmit="return confirm('确定删除报表 {_escape(r['name'])}？')">
      <button type="submit" class="btn btn-danger btn-sm">删除</button>
    </form>
  </td>
</tr>"""
        return rows

    cat_areas = ""

    def _render_cat_item(cat, depth=0):
        children = [c for c in all_cats if c.get("parent_id") == cat["id"]]
        has_children = len(children) > 0
        siblings = [c for c in all_cats if c.get("parent_id") == cat.get("parent_id")]
        idx = next((i for i, c in enumerate(siblings) if c["id"] == cat["id"]), -1)
        n = len(siblings)
        move_btns = build_move_buttons_html(cat["id"], "categories", idx, n)
        badge = f'<span style="color:#94a3b8;font-size:11px;margin-left:4px">({len(children)} 子分类)</span>' if has_children else ""
        return f"""<div style="padding:8px {8 + depth * 24}px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f1f5f9">
  <span style="font-size:14px;font-weight:500">{_escape(cat["name"])}{badge}</span>
  <span style="flex:1"></span>
  {move_btns}
  {_link_btn(f"/config/categories/{cat['id']}/edit", "编辑", "btn btn-outline btn-sm")}
  <form method="post" action="/config/categories/{cat['id']}/delete" style="display:inline"
        onsubmit="return confirm('确定删除分类 {_escape(cat['name'])}？分类下的报表和子分类将变为未分类。')">
    <button type="submit" class="btn btn-danger btn-sm" style="padding:2px 8px;font-size:12px">删除</button>
  </form>
</div>"""

    def _render_tree(nodes, depth=0):
        html = ""
        for node in nodes:
            html += _render_cat_item(node, depth)
            if node["children"]:
                html += _render_tree(node["children"], depth + 1)
        return html

    cat_list_html = _render_tree(cat_tree)

    if not cat_list_html and not all_reports:
        cat_list_html = '<div style="color:#94a3b8;font-size:14px;padding:12px 0">暂无分类</div>'

    cat_areas += f"""<div class="section">
<div class="section-title">
  <span>📁 报表分类</span>
  <span class="actions">
    {_link_btn("/config/categories/add", "新增分类", "btn btn-primary btn-sm")}
    {_link_btn("/config/reports/add", "新增报表", "btn btn-outline btn-sm")}
  </span>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
  {cat_list_html}
</div>
</div>"""

    report_lookup: dict[int, list] = {entry["id"]: entry.get("reports", []) for entry in cat_reports}
    tab_html = ""

    def _render_report_sections(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            reports = report_lookup.get(node["id"], [])
            if reports:
                indent = "　" * depth
                rows = _render_report_rows(reports, in_category=True)
                html += f"""<div class="section">
<div class="section-title">
  <span>📊 {indent}{_escape(node['name'])} <span style="font-weight:400;font-size:14px;color:#94a3b8">({len(reports)} 个报表)</span></span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th style="width:40px"><input type="checkbox" onchange="var section=this.closest('.section');var c=section.querySelectorAll('.report-checkbox');for(var i=0;i<c.length;i++){{c[i].checked=this.checked;}}updateBatchCount()"></th>
  <th>名称</th><th>SQL 查询</th><th>默认分页</th><th>连接池</th><th>缓存</th><th>TTL</th><th>备注</th><th>API 接口</th><th>操作</th>
</tr></thead><tbody>
{rows}
</tbody></table>
</div>
</div>"""
            if node["children"]:
                html += _render_report_sections(node["children"], depth + 1)
        return html

    tab_html = _render_report_sections(cat_tree)

    uncat_rows = _render_report_rows(unclassified_reports)
    uncat_section = ""
    if unclassified_reports or all_reports:
        uncat_section = f"""<div class="section">
<div class="section-title">
  <span>📋 未分类报表 <span style="font-weight:400;font-size:14px;color:#94a3b8">({len(unclassified_reports)} 个报表)</span></span>
  <span class="actions">{_link_btn("/config/reports/add", "新增报表", "btn btn-primary btn-sm")}</span>
</div>
{batch_bar}
<div class="table-wrap">
<table><thead><tr>
  <th style="width:40px"><input type="checkbox" onchange="var section=this.closest('.section');var c=section.querySelectorAll('.report-checkbox');for(var i=0;i<c.length;i++){{c[i].checked=this.checked;}}updateBatchCount()"></th>
  <th>名称</th><th>SQL 查询</th><th>默认分页</th><th>连接池</th><th>缓存</th><th>TTL</th><th>备注</th><th>API 接口</th><th>操作</th>
</tr></thead><tbody>
{uncat_rows or '<tr><td colspan="10" class="empty-state">暂无未分类报表</td></tr>'}
</tbody></table>
</div>
</div>"""

    return cat_areas + tab_html + uncat_section


# ===================================================================
# API 端点管理渲染函数
# ===================================================================


def build_api_endpoints_list_html(api_endpoints: list[dict],
                                   report_id: int) -> str:
    """
    渲染报表编辑表单中的 API 接口列表区块。

    参数:
        api_endpoints: API 端点列表
        report_id: 关联报表 ID
    """
    rows = ""
    for ep in api_endpoints:
        ep_id = ep["id"]
        ep_name = _escape(ep.get("name", ""))
        ep_path = _escape(ep.get("url_path", ""))
        ep_format = _escape(ep.get("output_format", "json"))
        enabled = int(ep.get("enabled", 1))
        enabled_badge = ('<span style="color:#059669;font-weight:600">启用</span>'
                         if enabled else
                         '<span style="color:#dc2626;font-weight:600">禁用</span>')
        api_key_raw = ep.get("api_key") or ""
        api_key_display = _mask_api_key(api_key_raw) if api_key_raw else "—"
        ep_result_mode = ep.get("result_mode", "single")
        ep_result_index = int(ep.get("result_index", 0))
        if ep_result_mode == "all":
            mode_display = '<span style="color:#4f46e5;font-weight:600">全部</span>'
        else:
            mode_display = f'<span style="color:#475569">结果 {ep_result_index}</span>'
        rows += f"""<tr>
  <td><strong>{ep_name}</strong></td>
  <td><code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px;color:#4f46e5">{ep_path}</code></td>
  <td>{ep_format}</td>
  <td>{mode_display}</td>
  <td>{enabled_badge}</td>
  <td><code style="font-size:12px;color:#94a3b8">{api_key_display}</code></td>
  <td class="ops-cell">
    {_link_btn(f"/config/reports/{report_id}/api_endpoints/{ep_id}/edit", "编辑")}
    <form method="post" action="/config/reports/{report_id}/api_endpoints/{ep_id}/delete" style="display:inline"
          onsubmit="return confirm('确定删除 API 接口 {_escape(ep_name)}？')">
      <button type="submit" class="btn btn-danger btn-sm">删除</button>
    </form>
  </td>
</tr>"""
    return f"""<div class="section" style="margin-top:24px" id="api-endpoints">
<div class="section-title" style="font-size:16px">
  <span>🔌 API 接口</span>
  <span class="actions">{_link_btn(f"/config/reports/{report_id}/api_endpoints/new", "新增 API 接口", "btn btn-primary btn-sm")}</span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th>名称</th><th>URL 路径</th><th>格式</th><th>输出模式</th><th>状态</th><th>API Key</th><th>操作</th>
</tr></thead><tbody>
{rows or '<tr><td colspan="7" class="empty-state">暂无 API 接口配置</td></tr>'}
</tbody></table>
</div>
</div>"""


def _mask_api_key(key: str) -> str:
    """
    对 API Key 进行掩码显示。

    保留前4个字符和后4个字符，中间用 *** 替代。
    短密钥则全部显示后4位以 *** 开头。
    """
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***" + key[-2:]
    return key[:4] + "***" + key[-4:]


def _build_result_mode_ui(result_count: int, result_names_list: list,
                          current_mode: str, current_index: int) -> str:
    """生成结果集输出模式的 UI 区块 HTML。"""
    if result_count <= 1:
        return ""
    has_names = bool(result_names_list)
    names = result_names_list if has_names else [f"结果{i+1}" for i in range(result_count)]
    assert len(names) == result_count, "result_names_list 长度与 result_count 不一致"

    # 名称列表展示
    name_items = "".join(
        f'<li style="margin:2px 0;font-size:13px;color:#475569">{"①" if i == 0 else "②" if i == 1 else "③" if i == 2 else f"<span style=\"font-family:monospace\">{i+1}.</span>"} {_escape(n)}</li>'
        for i, n in enumerate(names)
    )

    # 下拉框选项
    select_opts = "".join(
        f'<option value="{i}"{" selected" if current_mode == "single" and current_index == i else ""}>{_escape(names[i])}</option>'
        for i in range(result_count)
    )

    single_checked = ' checked' if current_mode == 'single' else ''
    all_checked = ' checked' if current_mode == 'all' else ''
    select_disabled = ' disabled' if current_mode == 'all' else ''

    warning_html = ""
    if not has_names:
        warning_html = f'''<div style="margin:8px 0;padding:8px 12px;background:#fefce8;border-radius:6px;border:1px solid #fde68a;font-size:13px;color:#92400e">
  <span>⚠️ 该报表的 SQL 包含 {result_count} 段 SELECT，但未配置结果集名称</span>
  <span>请在报表编辑页的「结果名称」字段中设置，便于识别。暂用默认名称：{" / ".join(names)}</span>
</div>'''

    return f'''<div class="result-mode-section" style="margin-bottom:16px;padding:14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
  <div style="font-weight:600;font-size:14px;color:#1e293b;margin-bottom:8px">结果集输出模式</div>
  <div style="margin-bottom:8px;font-size:13px;color:#475569">
    该报表的 SQL 包含 <strong>{result_count}</strong> 段 SELECT，返回 <strong>{result_count}</strong> 个结果集
  </div>
  <ul style="list-style:none;padding:0;margin:0 0 10px 0">{name_items}</ul>
  {warning_html}
  <div style="margin:6px 0">
    <label style="display:flex;align-items:center;gap:6px;font-weight:400;cursor:pointer;margin:4px 0">
      <input type="radio" name="result_mode" value="all"{all_checked} onchange="toggleResultIndex()">
      <span style="font-weight:600">输出全部结果集</span>
      <span style="color:#94a3b8;font-size:12px;font-weight:400">— 每个结果集独立分页，API 返回 JSON 数组</span>
    </label>
    <label style="display:flex;align-items:center;gap:6px;font-weight:400;cursor:pointer;margin:4px 0">
      <input type="radio" name="result_mode" value="single"{single_checked} onchange="toggleResultIndex()">
      <span style="font-weight:600">输出单个结果集：</span>
      <select name="result_index"{select_disabled} style="margin-left:4px">
        {select_opts}
      </select>
    </label>
  </div>
  <div style="font-size:12px;color:#94a3b8;margin-top:4px">
    结果集名称在报表编辑页的「结果名称」中配置
  </div>
  <script>
  function toggleResultIndex() {{
    var radios = document.getElementsByName('result_mode');
    var select = document.getElementsByName('result_index')[0];
    for (var i = 0; i < radios.length; i++) {{
      if (radios[i].checked && radios[i].value === 'all') {{
        select.disabled = true;
      }} else {{
        select.disabled = false;
      }}
    }}
  }}
  document.addEventListener('DOMContentLoaded', toggleResultIndex);
  </script>
</div>'''


def build_api_endpoint_form_html(report_id: int, report_name: str,
                                 endpoint: dict = None,
                                 flash: str = None,
                                 result_names_list: list = None,
                                 result_count: int = 1) -> str:
    """
    渲染 API 端点编辑/新增表单。

    参数:
        report_id: 关联报表 ID
        report_name: 关联报表名称（显示用）
        endpoint: 现有端点配置（None 表示新增）
        flash: 错误消息
        result_names_list: 结果集名称列表（按行分割）
        result_count: 结果集估算数量
    """
    is_edit = endpoint is not None
    if is_edit:
        ep_id = endpoint["id"]
        action_url = f"/config/reports/{report_id}/api_endpoints/{ep_id}/edit"
        title = "编辑 API 接口"
    else:
        action_url = f"/config/reports/{report_id}/api_endpoints/new"
        title = "新增 API 接口"

    if flash:
        css_cls = " flash-error" if flash.startswith("错误") else " flash-success"
        flash_html = f'<div class="flash{css_cls}">{_escape(flash)}</div>'
    else:
        flash_html = ""

    name = _escape(endpoint["name"]) if is_edit else ""
    url_path = endpoint["url_path"] if is_edit else ""
    # 从完整 URL 路径中剥离 /api/ 前缀，仅保留用户输入的后段
    if url_path.startswith("/api/"):
        url_path_short = url_path[5:]
    elif url_path.startswith("/api"):
        url_path_short = url_path[4:]
    else:
        url_path_short = url_path
    url_path_short = _escape(url_path_short)
    output_format = endpoint.get("output_format", "json") if is_edit else "json"
    row_limit = str(endpoint.get("row_limit", 0) or 0) if is_edit else "0"
    api_key_raw = endpoint.get("api_key") or "" if is_edit else ""
    allowed_origins = _escape(endpoint.get("allowed_origins") or "") if is_edit else ""
    enabled_checked = (' checked' if (is_edit and int(endpoint.get("enabled", 1)))
                       else (' checked' if not is_edit else ''))

    # 结果集输出模式
    result_mode = endpoint.get("result_mode", "single") if is_edit else "single"
    result_index = int(endpoint.get("result_index", 0)) if is_edit else 0

    # 从三个 DB 字段拼合规则 JSON
    if is_edit:
        rules = {}
        cols_val = endpoint.get("columns") or ""
        filters_raw_db = endpoint.get("filters") or ""
        sorts_raw_db = endpoint.get("sorts") or ""
        if cols_val:
            rules["columns"] = cols_val
        if filters_raw_db:
            try:
                rules["filters"] = json.loads(filters_raw_db)
            except (json.JSONDecodeError, TypeError):
                rules["filters"] = filters_raw_db
        if sorts_raw_db:
            try:
                rules["sorts"] = json.loads(sorts_raw_db)
            except (json.JSONDecodeError, TypeError):
                rules["sorts"] = sorts_raw_db
        rule_json = json.dumps(rules, indent=2, ensure_ascii=False) if rules else ""
    else:
        rule_json = ""

    format_opts = "".join(
        f'<option value="{v}"{" selected" if output_format == v else ""}>{v.upper()}</option>'
        for v in ("json", "csv")
    )

    return f"""<div class="card">
<h2>{title}</h2>
{flash_html}
<div style="margin-bottom:16px;padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:14px;color:#475569">
  关联报表: <strong>{_escape(report_name)}</strong> (ID: {report_id})
</div>
<form method="post" action="{action_url}" class="config-form">
  <label>接口名称: <input type="text" name="name" value="{name}" required
    placeholder="例如: 客户数据 API"></label>

  <label>URL 路径:
    <div style="display:flex;align-items:center;gap:0;margin-top:4px">
      <span style="padding:6px 12px;background:#e2e8f0;border:1px solid #cbd5e1;border-right:none;border-radius:6px 0 0 6px;font-family:monospace;font-size:14px;color:#475569;white-space:nowrap;line-height:1.5">/api/</span>
      <input type="text" name="url_path" value="{url_path_short}" required
        id="url-path-input"
        placeholder="customers"
        style="border-radius:0 6px 6px 0;flex:1;min-width:200px"
        oninput="updateFullUrl()">
    </div>
  </label>
  <div style="margin-top:6px;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:13px;color:#475569;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span style="font-weight:500;color:#64748b">完整 URL:</span>
    <code id="full-url-text" style="flex:1;font-family:monospace;font-size:13px;word-break:break-all"></code>
    <button type="button" onclick="copyFullUrl()" style="padding:3px 10px;font-size:12px;cursor:pointer;border:1px solid #cbd5e1;border-radius:4px;background:#fff;white-space:nowrap">复制</button>
  </div>
  <script>
  function updateFullUrl() {{
    var input = document.getElementById('url-path-input');
    var display = document.getElementById('full-url-text');
    var path = input.value || '';
    display.textContent = window.location.origin + '/api/' + path;
  }}
  function copyFullUrl() {{
    var el = document.getElementById('full-url-text');
    if (!el) return;
    var text = el.textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text).catch(function(){{}});
    }} else {{
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }}
  }}
  document.addEventListener('DOMContentLoaded', updateFullUrl);
  </script>

  <label>输出格式:
    <select name="output_format">{format_opts}</select>
  </label>

  {_build_result_mode_ui(result_count, result_names_list, result_mode, result_index)}

  <div style="margin-bottom:16px;padding:10px 14px;background:#fefce8;border-radius:8px;border:1px solid #fde68a;font-size:13px;color:#92400e">
    <strong>💡 快捷获取规则：</strong>在报表页面使用筛选/排序/字段选择功能调整数据后，
    展开「<strong>当前规则</strong>」折叠区，点击<strong>复制</strong>按钮即可获取 JSON 格式的配置，
    直接粘贴到下方的 JSON 文本框中。
    <div style="margin-top:4px;font-size:12px;color:#a16207">
      查看报表 → <a href="/report?id={report_id}" target="_blank" style="color:#4f46e5;font-weight:600">/report?id={report_id}</a>
    </div>
  </div>

  <label>规则 JSON（筛选/排序/字段选择，留空=无二次加工）:
    <textarea name="rule_json" class="sql-textarea"
      placeholder='{{"filters":[{{"col":"status","op":"eq","val":"active"}}],"sorts":[{{"col":"created_at","dir":"desc"}}],"columns":"id,name,email"}}'
      rows="5" style="min-height:100px;font-family:monospace">{_escape(rule_json)}</textarea></label>

  <label>最大行数（0=不限制）:
    <input type="number" name="row_limit" value="{row_limit}" min="0" step="1"></label>

  <label>API Key（留空=无需鉴权）:
    <input type="text" name="api_key" value="{_escape(api_key_raw)}"
      placeholder="留空则不鉴权"
      pattern="[a-zA-Z0-9_\\-]+" title="仅允许字母、数字、下划线和短横线">
    <span style="color:#94a3b8;font-weight:400;font-size:13px;display:block;margin-top:4px">
      调用时通过 Authorization: Bearer &lt;key&gt; 或 ?api_key=xxx 传递
    </span>
  </label>

  <label>CORS 允许来源（逗号分隔，留空=不设 CORS）:
    <input type="text" name="allowed_origins" value="{allowed_origins}"
      placeholder="例如: https://example.com,http://localhost:3000"></label>

  <label style="display:flex;align-items:center;gap:8px;font-weight:400">
    <input type="hidden" name="enabled" value="0">
    <input type="checkbox" name="enabled" value="1"{enabled_checked}>
    <span style="font-weight:600">启用</span>
  </label>

  <div class="form-actions">
    <button type="submit" name="action" value="save_close" class="btn btn-primary">保存并关闭</button>
    <button type="submit" name="action" value="save" class="btn btn-primary">保存</button>
    <a href="/config/reports/{report_id}/edit" class="cancel">关闭</a>
  </div>
</form>
</div>"""


# ===================================================================
# 审计日志页
# ===================================================================


def render_audit_page(
    rows: list[dict],
    total: int,
    page: int,
    page_size: int,
    filters: dict,
    message: str = "",
) -> str:
    """渲染审计日志页面（筛选栏 + 表格 + 分页 + CSV 导出 + 清理）。"""
    now = time.time()
    total_pages = max(1, (total + page_size - 1) // page_size)
    selected_type = filters.get("type", "")
    type_options = {"": "全部类型", "operation": "操作日志", "web_access": "页面访问", "api": "API 调用"}
    type_html = ""
    for val, label in type_options.items():
        sel = ' selected' if val == selected_type else ''
        type_html += f'<option value="{val}"{sel}>{label}</option>'
    range_presets = {"today": "今天", "yesterday": "昨天", "last7": "近7天", "last30": "近30天"}
    range_btns = ""
    for rkey, rlabel in range_presets.items():
        range_btns += f'<button type="button" class="btn btn-sm btn-outline" onclick="setAuditDateRange(\'{rkey}\')">{rlabel}</button>'
    date_from = filters.get("date_from", "")
    date_to = filters.get("date_to", "")
    session_user_val = filters.get("session_user", "")
    keyword_val = filters.get("keyword", "")

    table_header = """<thead><tr>
      <th style="width:160px">时间</th>
      <th style="width:90px">类型</th>
      <th style="width:100px">操作者</th>
      <th style="width:130px">操作</th>
      <th style="width:100px">实体类型</th>
      <th>详情</th>
    </tr></thead>"""

    type_labels = {"operation": "操作", "web_access": "页面", "api": "API"}
    rows_html = ""
    for r in rows:
        rtype = r.get("type", "")
        type_label = type_labels.get(rtype, rtype)
        ts = r.get("timestamp", "")
        user = html_mod.escape(r.get("session_user") or "")
        action = html_mod.escape(r.get("action") or "")
        entity_type = html_mod.escape(r.get("entity_type") or "")
        entity_name = html_mod.escape(r.get("entity_name") or "")
        http_method = html_mod.escape(r.get("http_method") or "")
        http_path = html_mod.escape(r.get("http_path") or "")
        http_status = r.get("http_status") or ""
        duration = r.get("duration_ms") or ""
        ip = html_mod.escape(r.get("ip_address") or "")
        before_val = r.get("before_value") or ""
        after_val = r.get("after_value") or ""
        request_body = r.get("request_body") or ""

        detail_parts = []
        if rtype == "operation":
            if entity_name:
                detail_parts.append(f"名称: {entity_name}")
            if before_val:
                detail_parts.append(f"改前: {html_mod.escape(str(before_val)[:80])}")
            if after_val:
                detail_parts.append(f"改后: {html_mod.escape(str(after_val)[:80])}")
        elif rtype in ("web_access", "api"):
            detail_parts.append(f"{http_method} {http_path}")
            if http_status:
                detail_parts.append(f"状态: {http_status}")
            if duration:
                detail_parts.append(f"耗时: {duration}ms")
            if ip:
                detail_parts.append(f"IP: {ip}")
            if request_body:
                detail_parts.append(f"请求: {html_mod.escape(str(request_body)[:200])}")
        detail_html = " | ".join(detail_parts) if detail_parts else "-"

        rows_html += f"""<tr>
      <td style="white-space:nowrap;font-size:13px">{html_mod.escape(ts)}</td>
      <td><span class="audit-type audit-type-{rtype}">{type_label}</span></td>
      <td>{user}</td>
      <td style="font-family:monospace;font-size:13px">{action}</td>
      <td>{entity_type}</td>
      <td style="font-size:13px;max-width:400px;overflow:hidden;text-overflow:ellipsis">{detail_html}</td>
    </tr>"""
    if not rows_html:
        rows_html = '<tr><td colspan="6" class="empty-state">暂无匹配的审计日志</td></tr>'

    qs = urllib.parse.urlencode({k: v for k, v in filters.items() if v})
    pagination = ""
    if total_pages > 1:
        page_links = ""
        for p in range(1, total_pages + 1):
            if p == page:
                page_links += f'<strong style="padding:4px 10px;background:#4f46e5;color:#fff;border-radius:4px">{p}</strong>'
            else:
                pq = urllib.parse.urlencode({**{k: v for k, v in filters.items() if v}, "page": p})
                page_links += f'<a href="/audit?{pq}" style="padding:4px 10px;color:#4f46e5;text-decoration:none">{p}</a>'
        pagination = f'<div style="display:flex;align-items:center;gap:6px;margin-top:16px;justify-content:center;font-size:14px">{page_links}</div>'

    export_qs = urllib.parse.urlencode({**{k: v for k, v in filters.items() if v}, "export": "csv"})

    extra_css = """
    .audit-filters { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }
    .audit-filters label { font-size:13px; color:#475569; display:flex; flex-direction:column; gap:2px; }
    .audit-filters input, .audit-filters select { padding:6px 10px; border:1px solid #e2e8f0; border-radius:6px; font-size:14px; }
    .audit-filters input:focus, .audit-filters select:focus { outline:none; border-color:#4f46e5; box-shadow:0 0 0 3px rgba(79,70,229,0.1); }
    .audit-filters .filter-btns { display:flex; gap:8px; align-items:flex-end; }
    .audit-type { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; }
    .audit-type-operation { background:#ede9fe; color:#5b21b6; }
    .audit-type-web_access { background:#dbeafe; color:#1e40af; }
    .audit-type-api { background:#d1fae5; color:#065f46; }
    .date-shortcuts { display:flex; gap:4px; align-items:flex-end; }
    .audit-actions { display:flex; gap:10px; margin-bottom:16px; }
    .audit-info { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; font-size:14px; color:#64748b; }
    """

    extra_js = r"""
    function setAuditDateRange(range) {
      var now = new Date();
      function fmt(d) { return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'); }
      var dateFrom, dateTo, y;
      switch(range) {
        case 'today':
          dateFrom=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
        case 'yesterday':
          y=new Date(now);y.setDate(y.getDate()-1);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),23,59)); break;
        case 'last7':
          y=new Date(now);y.setDate(y.getDate()-6);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
        case 'last30':
          y=new Date(now);y.setDate(y.getDate()-29);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
      }
      document.querySelector('input[name="date_from"]').value=dateFrom;
      document.querySelector('input[name="date_to"]').value=dateTo;
    }
    function confirmClean() {
      if(!confirm('确定要删除当前筛选条件下的所有审计日志吗？此操作不可恢复。')) return;
      var form=document.querySelector('.audit-filters form');
      var input=document.createElement('input');
      input.type='hidden';input.name='action';input.value='clean';
      form.appendChild(input);
      form.method='post';
      form.submit();
    }
    """

    navbar_html = _build_navbar_html("audit")
    html = _PAGE_HEADER_TEMPLATE.substitute(
        title="审计日志",
        common_css=_COMMON_CSS + extra_css,
        extra_css="",
        navbar=navbar_html,
    )

    if message:
        msg_class = "flash-success" if "成功" in message else "flash-error"
        html += f'<div class="flash {msg_class}">{html_mod.escape(message)}</div>'

    html += f"""
<div class="card">
  <h2>审计日志</h2>
  <div class="audit-info">
    <span>共 {total} 条记录，第 {page}/{total_pages} 页</span>
    <div class="audit-actions">
      <a href="/audit?{export_qs}" class="btn btn-sm btn-success">导出 CSV</a>
    </div>
  </div>
  <div class="audit-filters">
    <form method="get" action="/audit" style="display:contents">
      <label>类型: <select name="type">{type_html}</select></label>
      <label>操作者: <input type="text" name="session_user" value="{html_mod.escape(session_user_val)}" placeholder="操作者"></label>
      <label>关键字: <input type="text" name="keyword" value="{html_mod.escape(keyword_val)}" placeholder="操作/实体/路径"></label>
      <div class="date-shortcuts">{range_btns}</div>
      <label>从: <input type="datetime-local" name="date_from" value="{html_mod.escape(date_from)}"></label>
      <label>到: <input type="datetime-local" name="date_to" value="{html_mod.escape(date_to)}"></label>
      <div class="filter-btns">
        <button type="submit" class="btn btn-sm btn-primary">筛选</button>
        <button type="button" class="btn btn-sm btn-danger" onclick="confirmClean()">清理</button>
      </div>
    </form>
  </div>
</div>
<div class="card">
  <div class="table-wrap">
    <table>{table_header}<tbody>{rows_html}</tbody></table>
  </div>
  {pagination}
</div>
<script>{extra_js}</script>"""

    html += _PAGE_FOOTER
    return html
