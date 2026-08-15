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
import app_config
import redis_cache
import static_cache
from filter_help import render_filter_help, FILTER_HINT_SUFFIX

# ---------------------------------------------------------------------------
# 公共 CSS（全站单一来源：report.py + config.py + audit + 登录页共享）
# ---------------------------------------------------------------------------

# 基础片段（reset + body 字体栈 + fadeUp 关键帧），供登录页等独立页面复用
_BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
"""

_COMMON_CSS = """
body {
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
/* 宽屏利用率：视口越宽容器越宽（1200 → 1440 → 1680 → 1920 → 2400），
   窄屏保持 1200px 现状；表格类页面在宽屏下避免左右横移 */
@media (min-width: 1400px) { .container { max-width: 1440px; } }
@media (min-width: 1700px) { .container { max-width: 1680px; } }
@media (min-width: 2100px) { .container { max-width: 1920px; } }
@media (min-width: 2600px) { .container { max-width: 2400px; } }
.card {
  background: #fff; border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  padding: 24px; margin-bottom: 20px; animation: fadeUp 0.3s ease-out;
}
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
  position: sticky; top: 0; z-index: 5;
}
td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; text-align: left; }
tbody tr:hover { background: #f8fafc; }
tbody tr:last-child td { border-bottom: none; }
.table-wrap { overflow-x: auto; overflow-y: auto; max-height: calc(100vh - 130px); border: 1px solid #e2e8f0; border-radius: 8px; }
.flash {
  padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;
  font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 10px;
}
.flash-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.flash-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.flash-info { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.empty-state { text-align: center; color: #94a3b8; padding: 32px 14px; font-size: 14px; }
.empty-state .icon { font-size: 40px; margin-bottom: 12px; opacity: 0.5; }
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
.jump-box { display: inline-flex; align-items: center; gap: 6px; margin-left: 16px; }
.jump-box input {
  width: 64px; padding: 6px 8px; border: 1px solid #e2e8f0; border-radius: 6px;
  font-size: 14px; text-align: center; outline: none; transition: border-color 0.2s;
}
.jump-box input:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.12); }
"""

# 迷你按钮公共样式（config 页与 report 页共享；类拆分与内联现状视觉等价）
_MINIBTN_CSS = """
.btn-mini {
  font-size: 12px; border-radius: 4px; cursor: pointer;
}
.btn-mini-solid { padding: 4px 10px; border: none; }
.btn-mini-primary { background: #4f46e5; color: #fff; }
.btn-mini-success { background: #059669; color: #fff; }
.btn-mini-disabled {
  padding: 4px 10px; background: #e2e8f0; color: #94a3b8;
  border: none; cursor: not-allowed;
}
.btn-mini-outline {
  padding: 3px 10px; background: #fff; border: 1px solid #cbd5e1; white-space: nowrap;
}
.btn-mini-outline-light { padding: 4px 10px; background: #fff; border: 1px solid #e2e8f0; }
.btn-mini-outline-key { padding: 2px 8px; background: #fff; border: 1px solid #cbd5e1; color: #475569; }
.btn-mini-outline-accent { padding: 2px 8px; background: #fff; border: 1px solid #cbd5e1; color: #4f46e5; }
.btn-mini-s { padding: 2px 8px; font-size: 12px; }
.btn-mini-m { padding: 3px 10px; font-size: 12px; }
"""

# 黄色警示条公共样式（色值统一为较新的 #fefce8 系；!important 覆盖
# report 页 .controls .cache-badge 等既有类，保证与内联时代视觉一致）
_FLASH_WARN_CSS = """
.flash-warn { background: #fefce8 !important; color: #92400e !important; }
"""

# 黄色警示框内联样式（flash-warn 块级组件：表单警示、结果集名称警示共用，防样式漂移）
_WARN_BOX_STYLE = "margin:8px 0;padding:8px 12px;border-radius:6px;border:1px solid #fde68a;font-size:13px"

_COMMON_CSS = _BASE_CSS + _COMMON_CSS + _MINIBTN_CSS + _FLASH_WARN_CSS

# ---------------------------------------------------------------------------
# 公共 JavaScript（交互式 UI 组件）
# ---------------------------------------------------------------------------

# 全量获取 URL 查询串（JS 字符串与 Python f-string 统一引用）
FETCH_ALL_QUERY = "?fetch_all=true"

_COMMON_JS = r"""
function toggleSection(btn, label) {
  var content = btn.nextElementSibling;
  var hidden = content.classList.toggle("hidden");
  btn.textContent = hidden ? "\u25b6 " + label : "\u25bc " + label;
}
function selectAllInSection(el) {
  var section = el.closest('.section');
  if (!section) return;
  var c = section.querySelectorAll('.report-checkbox');
  for (var i = 0; i < c.length; i++) {
    c[i].checked = el.checked;
  }
  updateBatchCount();
}
function submitBatchPost(actionUrl, ids, extraFields) {
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = actionUrl;
  ids.forEach(function(id) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'report_ids'; inp.value = id;
    form.appendChild(inp);
  });
  extraFields.forEach(function(f) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = f.name; inp.value = f.value;
    form.appendChild(inp);
  });
  document.body.appendChild(form);
  form.submit();
  return false;
}
function buildApiUrl(path, kind) {
  var origin = window.location.origin;
  if (kind === 'full') {
    return origin + path + '""" + FETCH_ALL_QUERY + r"""';
  } else if (kind === 'static') {
    return origin + path + '.json';
  }
  return origin + path;
}
function toggleApiDesc(btn) {
  var box = btn.previousElementSibling;
  if (!box) return;
  if (box.style.webkitLineClamp) {
    box.style.webkitLineClamp = '';
    box.style.display = 'block';
    btn.textContent = '收起';
  } else {
    box.style.webkitLineClamp = '3';
    box.style.display = '-webkit-box';
    btn.textContent = '展开';
  }
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
  copyToClipboard('current-rules-json');
}
function copyToClipboard(elementId) {
  var el = document.getElementById(elementId);
  if (!el) return;
  var text = el.value || el.textContent || el.innerText;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      var btn = el.nextElementSibling;
      if (btn && btn.tagName === 'BUTTON') {
        var originalText = btn.textContent;
        btn.textContent = '已复制';
        btn.style.color = '#059669';
        setTimeout(function() {
          btn.textContent = originalText;
          btn.style.color = '';
        }, 2000);
      }
    }).catch(function() {
      fallbackCopyText(text, el);
    });
  } else {
    fallbackCopyText(text, el);
  }
}
function fallbackCopyText(text, el) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    var btn = el.nextElementSibling;
    if (btn && btn.tagName === 'BUTTON') {
      var originalText = btn.textContent;
      btn.textContent = '已复制';
      btn.style.color = '#059669';
      setTimeout(function() {
        btn.textContent = originalText;
        btn.style.color = '';
      }, 2000);
    }
  } catch (err) {
    console.error('复制失败:', err);
  }
  document.body.removeChild(ta);
}
function initApiUrls() {
  var els = document.querySelectorAll('.api-url-code');
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var path = el.getAttribute('data-path') || '';
    var kind = el.getAttribute('data-kind') || 'base';
    el.textContent = buildApiUrl(path, kind);
  }
}
document.addEventListener('DOMContentLoaded', function() {
  initApiUrls();
});
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
    if (k.startsWith('f_') || k.startsWith('op_') || k.startsWith('s_')
        || k === 'sort' || k === 'dir' || k === 'cols' || k === 'page') {
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
    rules.sorts.forEach(function(s) {
      params.append('sort', s.col);
      params.append('dir', s.dir || 'asc');
    });
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
    "\\b(\\w+)(?=\\s*\\()",
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
  var s = t.replace(/\s*;\s*$/,""), toks = [], lines = [], indent = 0, clauseCount = 0;
  s = s.replace(/(--[^\n]*|\/\*[\s\S]*?\*\/|'(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.|"")*"|`(?:[^`\\]|\\.|``)*`)/g,
    function(m) { toks.push(m); return "\u0001" + (toks.length - 1) + "\u0001"; });
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
  return lines.map(function(l) {
    return l.replace(/\u0001(\d+)\u0001/g, function(m, n) { return toks[+n]; });
  }).join("\n") + ";";
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
    ("api", "/config/api-endpoints", "API 接口"),
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
    active = active or ""
    for key, href, label in _NAV_ITEMS:
        # 子页面（如 config-reports）高亮所属主菜单项
        is_active = key == active or (key == "config" and active.startswith("config-"))
        cls = ' class="nav-active"' if is_active else ""
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


def build_flash_html(flash: str, is_error: bool = None) -> str:
    """构建 flash 提示条 HTML。

    默认按消息是否以"错误"开头判定错误样式；is_error 传入时显式指定。
    """
    if is_error is None:
        is_error = flash.startswith("错误")
    css_cls = " flash-error" if is_error else " flash-success"
    return f'<div class="flash{css_cls}">{_escape(flash)}</div>'


def build_empty_row_html(colspan, text: str, with_icon: bool = False) -> str:
    """构建表格空状态提示行 HTML。

    with_icon=True 时输出带 📭 图标的变体（图标面板专用，colspan 固定 999）。
    其余为纯文字版 `<tr><td colspan="N" class="empty-state">text</td></tr>`。
    """
    if with_icon:
        return ('<tr class="empty-state-row">'
                '<td colspan="999"><div class="empty-state">'
                '<div class="icon">📭</div>' + text + '</div></td></tr>')
    return f'<tr><td colspan="{colspan}" class="empty-state">{text}</td></tr>'


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
                          result_param: str = '',
                          page_url_base: str = None) -> str:
    """构建分页 HTML，携带多字段排序/筛选/自定义列/多结果参数。

    当提供 page_url_base 时，直接以此为基 URL（须已含 &amp; 转义），
    忽略 report_id/page_size/sorts/filters/cols/result 参数。
    """
    sorts = sorts or []
    filters = filters or []
    if total_pages <= 1:
        return ""

    if page_url_base is not None:
        base_url = page_url_base
    else:
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
            dt_str = app_config.format_local_time(ts, with_tz=False)
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
    debug_html = build_collapse_section_html("Debug 信息", "<br>".join(debug_lines))
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

    content = (
        '<div style="margin-bottom:8px;line-height:1.6">'
        + '<br>'.join(summary_parts) +
        '</div>'
        '<div style="position:relative">'
        '<textarea id="current-rules-json" style="width:100%;background:#1e293b;color:#e2e8f0;padding:12px;'
        'border-radius:6px;font-size:13px;line-height:1.5;font-family:monospace;border:1px solid #334155;'
        'resize:vertical;margin:0;min-height:80px" spellcheck="false">'
        f'{_escape(rules_json)}</textarea>'
        '<div style="margin-top:6px;display:flex;gap:6px">'
        '<button onclick="copyRulesJson()" class="btn-mini btn-mini-solid btn-mini-primary">复制</button>'
        '<button onclick="applyRulesJson()" class="btn-mini btn-mini-solid btn-mini-success">应用</button>'
        '</div>'
        '</div>'
        '<div style="margin-top:6px;font-size:12px;color:#94a3b8">'
        '提示: 在 API 接口配置中填入以上 JSON 规则，即可复用当前报表的筛选/排序/字段设置。'
        '</div>'
    )
    return build_collapse_section_html("当前规则", content, extra_style="margin-top:8px")


def build_memo_section_html(memo_raw: str) -> str:
    """构建备注折叠区 HTML。"""
    if memo_raw:
        memo_btn_text = "▼ 备注"
        memo_hidden = False
    else:
        memo_btn_text = "▶ 备注"
        memo_hidden = True
    return build_collapse_section_html("备注", _escape(memo_raw),
                                       default_hidden=memo_hidden,
                                       button_text=memo_btn_text)


def build_result_selector_html(report_id, qs_page_size, result_names,
                                active_index, sql_override, swi,
                                filters=None, sorts=None) -> str:
    """构建多结果集切换下拉框 HTML。

    filters/sorts: 当前结果视图已应用的筛选/排序（用于状态角标，None 视为无）。
    """
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
    # PH-11 视图状态角标：复用 sort-tag 样式，当前视图已应用筛选/排序时展示
    badge_parts = []
    if filters:
        badge_parts.append(
            f'<span class="sort-tag" style="display:inline-flex;align-items:center;gap:3px;'
            f'background:#eef2ff;color:#4f46e5;border-radius:4px;padding:2px 8px;'
            f'font-size:12px;border:1px solid #c7d2fe">已筛选 ×{len(filters)}</span>')
    if sorts:
        badge_parts.append(
            f'<span class="sort-tag" style="display:inline-flex;align-items:center;gap:3px;'
            f'background:#eef2ff;color:#4f46e5;border-radius:4px;padding:2px 8px;'
            f'font-size:12px;border:1px solid #c7d2fe">已排序 ×{len(sorts)}</span>')
    badges_html = "".join(badge_parts)
    return (
        f'<div class="result-selector" style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
        f'<label style="font-size:13px;color:#475569;font-weight:500">结果视图:</label>'
        f'<select id="resultSwitcher"'
        f' data-report-id="{report_id}" data-active-index="{active_index}"'
        f' data-swi="{_escape(swi)}" data-page-size="{qs_page_size}"'
        f' data-sql-override="{_escape(sql_override or "")}"'
        f' onchange="switchResult(this)"'
        f' style="padding:4px 8px;font-size:13px;border:1px solid #e2e8f0;border-radius:4px;background:#fff">'
        f'{opts}</select>'
        f'{badges_html}'
        f'<span style="font-size:12px;color:#94a3b8">每个结果视图独立维护筛选/排序/分页状态</span>'
        f'</div>'
    )


def build_cache_badge_html(cache_info, prefer_cache: bool = False,
                           cache_ttl_hours: int = 0) -> str:
    """构建缓存状态标签 HTML。

    当 prefer_cache=True 且 cache_ttl_hours>0 时，额外显示 TTL 信息；
    快照模式（redis/redis_fallback/process）带时间戳时计算过期时刻
    （ts + ttl*3600），已过期显示警示样式 + 「已过期（下次请求自动刷新）」；
    TTL=0（永不过期）保持现状。
    """
    extra = ""
    expired = False
    if prefer_cache:
        extra = " prefer_cache"
        if cache_ttl_hours > 0:
            extra += f" | TTL={cache_ttl_hours}h"
    if cache_info:
        src = cache_info.get("source", "")
        ts = cache_info.get("timestamp")
        if (src in ("redis", "redis_fallback", "process")
                and prefer_cache and cache_ttl_hours > 0 and ts
                and ts + cache_ttl_hours * 3600 < time.time()):
            expired = True
            extra += " | 已过期（下次请求自动刷新）"
        if src == "redis":
            age = int(time.time() - ts) if ts else 0
            css = "flash-warn" if expired else "fresh"
            return (f'<span class="cache-badge {css}">'
                    f'Redis 快照 ({age}s 前{extra})'
                    '</span>')
        elif src == "redis_fallback":
            age = int(time.time() - ts) if ts else 0
            return ('<span class="cache-badge flash-warn">'
                    f'缓存快照（{age}s 前{extra}，MySQL 不可用）'
                    '</span>')
        elif src == "process":
            age = int(time.time() - ts) if ts else 0
            css = "flash-warn" if expired else "fresh"
            return (f'<span class="cache-badge {css}">'
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
      name="{filter_input_name}" placeholder="筛选 {_escape(col)}{FILTER_HINT_SUFFIX}"
      value="{_escape(cur_fval)}" title="{_escape(cur_fval)}"
      style="{input_style}" {input_disabled}>
  </div>
</th>""")
    thead_parts.append("</tr>")
    return "".join(thead_parts)


def build_table_body_html(rows, display_indices) -> str:
    """构建表格数据行 HTML。"""
    tbody = ""
    if not rows:
        tbody = build_empty_row_html(999, "暂无数据", with_icon=True)
    else:
        for row in rows:
            cells = "".join(f"<td>{_escape(row[i])}</td>" for i in display_indices)
            tbody += "<tr>" + cells + "</tr>"
    return tbody


def build_controls_bar_html(report_id, page_size, sorts, filters,
                             cols_param, display_columns, active_index,
                             cache_badge, total_rows, total_pages,
                             result_param='', page=1) -> str:
    """构建控制栏 HTML（分页控件、导出表单、缓存状态等）。
    result_param: 多结果集时的 URL 参数字符串（如 "result=0"），仅当 num_results > 1 时非空。
    page: 当前页码（重建缓存 POST 表单随附，回跳保持分页位置）。
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
      <select name="format" id="export-format-select" onchange="updateExportSmartState()" style="padding:2px 5px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px">
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
      </select>
    </label>
    <details class="export-more" style="position:relative;display:inline-block">
      <summary style="font-size:12px;color:#475569;cursor:pointer;user-select:none;list-style:none;background:#fff;border:1px solid #e2e8f0;border-radius:4px;padding:2px 8px">更多选项 ▾</summary>
      <div style="position:absolute;right:0;top:calc(100% + 4px);background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px 12px;z-index:30;box-shadow:0 4px 12px rgba(0,0,0,.08);display:flex;flex-direction:column;gap:8px;min-width:240px">
        <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:3px">
          字符集:
          <select name="charset" style="padding:2px 5px;font-size:12px;border:1px solid #e2e8f0;border-radius:4px">
            <option value="gbk">GBK</option>
            <option value="utf8">UTF8</option>
          </select>
        </label>
        <div id="export-smart-panel" style="border-top:1px dashed #e2e8f0;padding-top:6px;font-size:12px;color:#475569;line-height:1.7">
          <input type="hidden" name="smart_quotes" id="export-smart-quotes-input" value="0">
          <div style="font-weight:600;color:#334155">智能去引号
            <span id="export-smart-csv-hint" style="display:none;color:#dc2626;font-weight:400">（仅 JSON 格式支持）</span>
          </div>
          <label style="display:inline-flex;align-items:center;gap:2px;margin-top:2px">
            <input type="checkbox" class="smart-quote-cb" value="1" onchange="updateExportSmartFlags()"> 十进制数字（含正负号）
          </label>
          <label style="display:inline-flex;align-items:center;gap:2px">
            <input type="checkbox" class="smart-quote-cb" value="2" onchange="updateExportSmartFlags()"> 科学计数法
          </label>
          <label style="display:inline-flex;align-items:center;gap:2px">
            <input type="checkbox" class="smart-quote-cb" value="4" onchange="updateExportSmartFlags()"> 千分位数字
          </label>
          <div style="font-size:11px;color:#64748b;line-height:1.6;margin-top:2px">
            原生 int/float 恒裸输出；Decimal 数值列勾选十进制/科学时输出数字；勾选形态的字符串值
            去引号，未勾选保持带引号；千分位输出去逗号；输出永远合法 JSON（RFC 8259）。
          </div>
        </div>
        <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:2px">
          <input type="checkbox" name="zip" value="1"> 压缩包
        </label>
        <label style="font-size:12px;color:#475569;display:inline-flex;align-items:center;gap:2px">
          <input type="checkbox" name="use_custom_cols" value="1" {"checked" if cols_param else ""}> 应用自定义字段
        </label>
      </div>
    </details>
    <button type="submit" class="btn btn-success btn-sm btn-mini-m">导出</button>
  </form>
  <button type="button" onclick="document.getElementById('fieldSettingsPanel').style.display='block'" class="btn-refresh" style="font-size:13px">⚙ 字段设置</button>
  <button type="button" onclick="document.getElementById('sortSettingsPanel').style.display='block'" class="btn-refresh" style="font-size:13px">⇅ 排序设置</button>
   <form method="post" action="/report" style="display:inline-flex;align-items:center">
    <input type="hidden" name="action" value="refresh_cache">
    <input type="hidden" name="id" value="{report_id}">
    <input type="hidden" name="page" value="{page}">
    <input type="hidden" name="page_size" value="{page_size}">
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    <button type="submit" class="btn-refresh">⟳ 重建缓存</button>
   </form>
  {cache_badge}
  <span class="stat">共 {total_rows} 行，{total_pages} 页</span>
  <script>
  function updateExportSmartFlags() {{
    var input = document.getElementById('export-smart-quotes-input');
    if (!input) return;
    var flags = 0;
    var cbs = document.querySelectorAll('#export-smart-panel .smart-quote-cb');
    cbs.forEach(function(cb) {{
      if (cb.checked) flags |= parseInt(cb.value, 10) || 0;
    }});
    input.value = flags;
  }}
  function updateExportSmartState() {{
    var fmtSel = document.getElementById('export-format-select');
    if (!fmtSel) return;
    var isCsv = fmtSel.value === 'csv';
    var cbs = document.querySelectorAll('#export-smart-panel .smart-quote-cb');
    cbs.forEach(function(cb) {{
      cb.disabled = isCsv;
      if (isCsv) cb.checked = false;
    }});
    if (isCsv) updateExportSmartFlags();
    var hint = document.getElementById('export-smart-csv-hint');
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
  }}
  document.addEventListener('DOMContentLoaded', function() {{
    updateExportSmartState();
  }});
  </script>
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
        'class="btn-mini btn-mini-outline-light">收起</button>'
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
        'class="btn-mini btn-mini-outline-light">收起</button>'
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
                         + render_filter_help() +
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


def build_delete_form_html(action_url: str, confirm_msg: str,
                           extra_hidden: str = "",
                           button_cls: str = "",
                           indent: int = 4) -> str:
    """构建删除确认表单 HTML（POST + confirm 确认 + 可选隐藏域）。

    参数:
        action_url: 表单提交地址
        confirm_msg: confirm() 提示文案（不含引号包裹）
        extra_hidden: 额外隐藏域 HTML，多行时按按钮行缩进统一缩进
        button_cls: 追加到按钮的额外 class（如迷你按钮尺寸 .btn-mini-s）
        indent: 表单开标签源码缩进空格数（与调用处对齐，保持输出逐字符一致）
    """
    pad = " " * indent
    btn_pad = " " * (indent + 2)
    hidden_html = ""
    if extra_hidden:
        hidden_html = "\n".join(f"{btn_pad}{ln}" for ln in extra_hidden.split("\n")) + "\n"
    return (
        f'{pad}<form method="post" action="{action_url}" style="display:inline"\n'
        f'{pad}      onsubmit="return confirm(\'{confirm_msg}\')">\n'
        f'{btn_pad}{hidden_html}'
        f'<button type="submit" class="btn btn-danger btn-sm{button_cls}">删除</button>\n'
        f'{pad}</form>'
    )


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


def build_pool_form_html(pool: dict = None, copy_mode: bool = False, is_edit: bool = None,
                         prefill_copy_suffix: bool = True) -> str:
    """渲染连接池编辑/新增/复制表单（纯数据 → HTML，无 DB 调用）

    is_edit: 显式指定编辑模式（None 时按 pool 是否非空 + copy_mode 判定）
    prefill_copy_suffix: 复制模式是否自动追加「 (副本)」后缀（保存失败回显时关闭）
    """
    if is_edit is None:
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
        if prefill_copy_suffix:
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


def build_user_form_html(user: dict = None, is_edit: bool = None) -> str:
    """渲染用户编辑/新增表单（纯数据 → HTML，无 DB 调用）

    is_edit: 显式指定编辑模式（None 时按 user 是否非空判定）
    """
    if is_edit is None:
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
    {build_delete_form_html(f"/config/pools/{p['id']}/delete", f"确定删除连接池 {_escape(p['name'])}？")}
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
{rows or build_empty_row_html(5, "暂无连接池配置")}
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
    {build_delete_form_html(f"/config/users/{u['id']}/delete", f"确定删除用户 {_escape(u['username'])}？")}
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
{rows or build_empty_row_html(2, "暂无用户")}
</tbody></table>
</div>
</div>"""


def build_category_manage_section_html(all_cats, cat_tree,
                                       show_report_add: bool = True) -> str:
    """渲染分类管理区块（分类树 + 排序 + CRUD，纯数据 → HTML，无 DB 调用）

    PH-14：/config/categories 独立页与报表页共用该区块；
    show_report_add=False 时隐藏「新增报表」快捷按钮（分类页）。
    """
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
  {build_delete_form_html(f"/config/categories/{cat['id']}/delete",
                          f"确定删除分类 {_escape(cat['name'])}？分类下的报表和子分类将变为未分类。",
                          button_cls=" btn-mini-s",
                          indent=2)}
</div>"""

    def _render_tree(nodes, depth=0):
        html = ""
        for node in nodes:
            html += _render_cat_item(node, depth)
            if node["children"]:
                html += _render_tree(node["children"], depth + 1)
        return html

    cat_list_html = _render_tree(cat_tree)

    if not cat_list_html:
        cat_list_html = '<div style="color:#94a3b8;font-size:14px;padding:12px 0">暂无分类</div>'

    report_add_btn = (_link_btn("/config/reports/add", "新增报表", "btn btn-outline btn-sm")
                      if show_report_add else "")
    return f"""<div class="section">
<div class="section-title">
  <span>📁 报表分类</span>
  <span class="actions">
    {_link_btn("/config/categories/add", "新增分类", "btn btn-primary btn-sm")}
    {report_add_btn}
  </span>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
  {cat_list_html}
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
   <button type="button" class="btn btn-danger btn-sm"
     onclick="batchDeleteReports()">批量删除报表</button>
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
  submitBatchPost('/config/reports/batch-pool', ids, [{{name: 'pool_id', value: poolId}}]);
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
  submitBatchPost('/config/reports/batch-set-category', ids, [{{name: 'category_id', value: catId === '-1' ? '' : catId}}]);
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
  var extra = [{{name: 'cache_switch', value: cacheSwitch}}];
  if (modifyTtl) {{
    extra.push({{name: 'modify_ttl', value: '1'}});
    extra.push({{name: 'cache_ttl_hours', value: document.getElementById('batch_cache_ttl').value}});
  }}
  submitBatchPost('/config/reports/batch-cache', ids, extra);
}}
function batchDeleteReports() {{
  var checkboxes = document.querySelectorAll('.report-checkbox:checked');
  var ids = [];
  for (var i = 0; i < checkboxes.length; i++) {{
    ids.push(checkboxes[i].value);
  }}
  if (ids.length === 0) {{ alert('请至少选择一项'); return; }}
  if (!confirm(`确定批量删除 ${{ids.length}} 个报表？该操作不可撤销`)) return;
  submitBatchPost('/config/reports/batch-delete', ids, []);
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
                build_state_span("是")
                if prefer_cache
                else build_state_span("否", "muted", bold=False)
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
    {build_delete_form_html(f"/config/reports/{rpt_id}/delete", f"确定删除报表 {_escape(r['name'])}？")}
  </td>
</tr>"""
        return rows

    cat_areas = build_category_manage_section_html(all_cats, cat_tree,
                                                   show_report_add=True)

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
  <th style="width:40px"><input type="checkbox" onchange="selectAllInSection(this)"></th>
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
    uncat_section = f"""<div class="section">
<div class="section-title">
  <span>📋 未分类报表 <span style="font-weight:400;font-size:14px;color:#94a3b8">({len(unclassified_reports)} 个报表)</span></span>
  <span class="actions">{_link_btn("/config/reports/add", "新增报表", "btn btn-primary btn-sm")}</span>
</div>
{batch_bar}
<div class="table-wrap">
<table><thead><tr>
  <th style="width:40px"><input type="checkbox" onchange="selectAllInSection(this)"></th>
  <th>名称</th><th>SQL 查询</th><th>默认分页</th><th>连接池</th><th>缓存</th><th>TTL</th><th>备注</th><th>API 接口</th><th>操作</th>
</tr></thead><tbody>
{uncat_rows or build_empty_row_html(10, "暂无未分类报表")}
</tbody></table>
</div>
</div>"""

    return cat_areas + tab_html + uncat_section


# ===================================================================
# API 端点管理渲染函数
# ===================================================================


def build_api_endpoints_list_html(api_endpoints: list[dict],
                                   report_id: int = None,
                                   show_report_name: bool = False,
                                   base_url: str = "",
                                   key_counts: dict = None) -> str:
    """
    渲染 API 接口列表区块。

    参数:
        api_endpoints: API 端点列表
        report_id: 关联报表 ID（为 None 时表示独立管理页，不带编辑/新增按钮）
        show_report_name: 是否显示关联报表名称列（独立管理页使用）
        base_url: 服务器基础 URL（如 http://localhost:8080），仅作服务端兜底
                  渲染值；页面加载后 JS 用 window.location.origin 覆盖
                  （与 API 配置后台/报表查看页一致，显示用户实际访问的地址）
        key_counts: {endpoint_id: key 数量} 映射（多 key 化后列表显示数量徽标；
                    None 时回退旧 api_key 列掩码+复制逻辑）
    """
    _sc_cfg = static_cache.get_static_cache_config()
    _sc_enabled = _sc_cfg.get("enable", True)
    rows = ""
    for ep in api_endpoints:
        ep_id = ep["id"]
        ep_name_raw = ep.get("name", "")
        ep_name = _escape(ep_name_raw)
        ep_path_raw = ep.get("url_path", "")
        ep_path = _escape(ep_path_raw)
        ep_format = _escape(ep.get("output_format", "json"))
        enabled = int(ep.get("enabled", 1))
        enabled_badge = (build_state_span("启用")
                         if enabled else
                         build_state_span("禁用", "warn"))
        api_key_raw = ep.get("api_key") or ""
        api_key_display = _mask_api_key(api_key_raw) if api_key_raw else "—"
        ep_result_mode = ep.get("result_mode", "single")
        ep_result_index = int(ep.get("result_index", 0))
        if ep_result_mode == "all":
            mode_display = '<span style="color:#4f46e5;font-weight:600">全部</span>'
        else:
            mode_display = f'<span style="color:#475569">结果 {ep_result_index}</span>'
        allow_fetch_all = int(ep.get("allow_fetch_all", 1))
        fetch_all_display = (build_state_span("允许")
                             if allow_fetch_all else
                             build_state_span("禁止", "warn"))
        static_cache_on = int(ep.get("static_cache", 1))
        static_cache_display = (build_state_span("开")
                                if static_cache_on else
                                build_state_span("关", "muted"))
        # 名称列：点击进入该接口的配置页（新开窗）
        ep_edit_url = _api_endpoint_url(ep['report_id'], ep_id)
        name_cell = (f'<td><a href="{ep_edit_url}" target="_blank" rel="noopener" '
                     f'title="打开接口配置" '
                     f'style="color:#4f46e5;text-decoration:none;font-weight:600">'
                     f'{ep_name}</a></td>')
        report_name_cell = ""
        if show_report_name:
            rname = _escape(ep.get("report_name", ""))
            rpt_id = int(ep.get("report_id", 0) or 0)
            if rpt_id:
                report_name_cell = (f'<td><a href="/report?id={rpt_id}" '
                                    f'target="_blank" rel="noopener" '
                                    f'title="打开报表查看页" '
                                    f'style="color:#4f46e5;text-decoration:none">'
                                    f'{rname}</a></td>')
            else:
                report_name_cell = f'<td>{rname}</td>'
        # URL 列：三种调用地址（完整/全量/静态），置灰能力未开启的行
        full_disabled = not allow_fetch_all
        full_hint = "未开启「允许全量获取」，请在接口配置中开启" if full_disabled else ""
        if static_cache_on:
            static_disabled = not _sc_enabled
            static_hint = ("全局静态缓存已关闭（app_config.json 的 static_cache.enable）"
                           if static_disabled else "")
        else:
            static_disabled = True
            static_hint = "未开启「静态缓存」，请在接口配置中开启"
        base_api_url, full_url, static_url = _api_url_variants(base_url, ep_path_raw)
        url_cell = ('<td style="min-width:300px">'
                    + _build_api_url_row(f"api-url-{ep_id}", "完整 URL:",
                                         ep_path_raw, "base", base_api_url)
                    + _build_api_url_row(f"api-full-{ep_id}", "全量 URL:",
                                         ep_path_raw, "full", full_url,
                                         disabled=full_disabled,
                                         disabled_hint=full_hint,
                                         edit_url=ep_edit_url)
                    + _build_api_url_row(f"api-static-{ep_id}", "静态 URL:",
                                         ep_path_raw, "static", static_url,
                                         disabled=static_disabled,
                                         disabled_hint=static_hint,
                                         edit_url=ep_edit_url)
                    + '</td>')
        # API Key：多 key 化后显示数量徽标（详情在端点配置页「API Key 管理」区块）；
        # key_counts 未提供时回退旧 api_key 列掩码 + 复制完整值
        api_key_raw = ep.get("api_key") or ""
        if key_counts is not None:
            ep_key_count = key_counts.get(ep_id, 0)
            if ep_key_count:
                key_cell = (f'<td style="white-space:nowrap">'
                            f'<code style="font-size:12px;color:#94a3b8">'
                            f'{ep_key_count} 个 Key</code></td>')
            else:
                key_cell = f'<td><code style="font-size:12px;color:#94a3b8">—</code></td>'
        elif api_key_raw:
            key_cell = (f'<td style="white-space:nowrap">'
                        f'<code style="font-size:12px;color:#94a3b8">{api_key_display}</code> '
                        f'<code id="api-key-raw-{ep_id}" style="display:none">'
                        f'{_escape(api_key_raw)}</code>'
                        f'<button type="button" onclick="copyToClipboard(\'api-key-raw-{ep_id}\')" '
                        f'title="复制完整 API Key" '
                        f'class="btn-mini btn-mini-outline-key">复制</button>'
                        f'</td>')
        else:
            key_cell = f'<td><code style="font-size:12px;color:#94a3b8">—</code></td>'
        # 快捷启用/禁用：POST 到独立管理页 toggle 端点，回跳来源页（禁用需确认）
        toggle_label = "禁用" if enabled else "启用"
        if report_id is not None:
            toggle_return_to = f"/config/reports/{report_id}/edit"
        else:
            toggle_return_to = "/config/api-endpoints"
        toggle_confirm = (" onsubmit=\"return confirm('确定禁用 API 接口 "
                          f"{_escape(ep_name_raw)}？')\"") if enabled else ""
        toggle_btn = f"""<form method="post" action="/config/api-endpoints" style="display:inline"{toggle_confirm}>
      <input type="hidden" name="action" value="toggle">
      <input type="hidden" name="endpoint_id" value="{ep_id}">
      <input type="hidden" name="return_to" value="{toggle_return_to}">
      <button type="submit" class="btn btn-outline btn-sm">{toggle_label}</button>
    </form>"""
        if report_id is not None:
            ops_cell = f"""<td class="ops-cell">
    {toggle_btn}
    {_link_btn(ep_edit_url, "编辑")}
    {build_delete_form_html(_api_endpoint_url(report_id, ep_id, "delete"),
                            f"确定删除 API 接口 {_escape(ep_name_raw)}？")}
  </td>"""
        else:
            ops_cell = f"""<td class="ops-cell">
    {toggle_btn}
    {_link_btn(ep_edit_url, "编辑")}
    {build_delete_form_html("/config/api-endpoints",
                            f"确定删除 API 接口 {_escape(ep_name_raw)}？",
                            extra_hidden='<input type="hidden" name="action" value="delete">\n'
                                         '<input type="hidden" name="endpoint_id" value="' + str(ep_id) + '">')}
  </td>"""
        rows += f"""<tr>
  {name_cell}{report_name_cell}
  <td>{_build_desc_summary_html(ep.get("description") or "") or '—'}</td>
  {url_cell}
  <td>{ep_format}</td>
  <td>{mode_display}</td>
  <td>{fetch_all_display}</td>
  <td>{static_cache_display}</td>
  <td>{enabled_badge}</td>
  {key_cell}
  {ops_cell}
</tr>"""
    extra_col = '<th>关联报表</th>' if show_report_name else ''
    extra_colspan = 1 if show_report_name else 0
    total_cols = 10 + extra_colspan
    title_actions = (_link_btn(f"/config/reports/{report_id}/api_endpoints/new", "新增 API 接口", "btn btn-primary btn-sm")
                     if report_id is not None else "")
    _sc_state = "开启" if _sc_enabled else "关闭"
    _sc_dir = _sc_cfg.get("dir", "static_cache")
    _sc_hint = (f'<div style="margin:6px 0 0 0;font-size:12px;color:#94a3b8">'
                f'静态文件缓存: 全局 {_sc_state} | 存储目录: <code>{_escape(str(_sc_dir))}</code>'
                f'（通过 app_config.json 的 static_cache 段配置）</div>')
    return f"""<div class="section" style="margin-top:24px" id="api-endpoints">
<div class="section-title" style="font-size:16px">
  <span>🔌 API 接口</span>
  <span class="actions">{title_actions}</span>
</div>
{_sc_hint}
<div class="table-wrap">
<table><thead><tr>
  <th>名称</th>{extra_col}<th>说明</th><th>调用地址</th><th>格式</th><th>输出模式</th><th>全量</th><th>静态缓存</th><th>状态</th><th>API Key</th><th>操作</th>
</tr></thead><tbody>
{rows or build_empty_row_html(total_cols, "暂无 API 接口配置")}
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


# 接口说明截断阈值（字符数）：
# - 列表页摘要版（表格单元格窄，单行 ellipsis）：40 字符 + title 悬停全文
# - 折叠区展示版（line-clamp 3 行 + 展开按钮）：80 字符或含换行时截断
_DESC_SUMMARY_TRUNCATE_LEN = 40
_API_DESC_TRUNCATE_LEN = 80


def _build_desc_summary_html(desc_raw: str,
                             max_chars: int = _DESC_SUMMARY_TRUNCATE_LEN) -> str | None:
    """构建接口说明的截断摘要 HTML（title 保留全文，悬停可见）。

    纯展示：超出 max_chars 字符截断为摘要（省略号），title 属性保留全文；
    空说明返回 None（调用方决定占位符）。
    """
    desc = (desc_raw or "").strip()
    if not desc:
        return None
    title = _escape(desc)
    summary = desc if len(desc) <= max_chars else desc[:max_chars] + "…"
    return (f'<span title="{title}" '
            f'style="display:inline-block;max-width:220px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom;'
            f'color:#64748b">{_escape(summary)}</span>')


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
        warning_html = (f'<div class="flash-warn" style="{_WARN_BOX_STYLE}">'
                        f'<span>⚠️ 该报表的 SQL 包含 {result_count} 段 SELECT，但未配置结果集名称</span>'
                        f'<span>请在报表编辑页的「结果名称」字段中设置，便于识别。暂用默认名称：{" / ".join(names)}</span>'
                        f'</div>')

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


_API_TEMPLATE_JS = r'''
<script>
  var TPL_DEFAULTS = {
    single: '{\n  "data": {{data}},\n  "total": {{total}},\n  "page": {{page}},\n  "page_size": {{page_size}},\n  "total_pages": {{total_pages}}\n}',
    all: '{\n  "results": {{results}},\n  "mode": {{mode}},\n  "page": {{page}},\n  "page_size": {{page_size}}\n}'
  };
  var TPL_KEYS = {
    single: ['data', 'total', 'page', 'page_size', 'total_pages', 'full', 'meta'],
    all: ['results', 'mode', 'page', 'page_size', 'full', 'meta']
  };
  var TPL_META_SAMPLE = {
    "generated_at": "2026-08-05 10:00:00 +0800",
    "expires_at": null,
    "last_invalidated_at": null,
    "config_version": "ab12cd34"
  };
  var TPL_SAMPLE = {
    single: {
      data: [{"客户ID": 1, "客户名称": "张三"}, {"客户ID": 2, "客户名称": "李四"}],
      total: 42, page: 1, page_size: 20, total_pages: 3, full: true,
      meta: TPL_META_SAMPLE
    },
    all: {
      results: [{
        "name": "结果1",
        "data": [{"客户ID": 1, "客户名称": "张三"}, {"客户ID": 2, "客户名称": "李四"}],
        "total": 42, "page": 1, "page_size": 42, "total_pages": 1
      }],
      mode: "all", page: 1, page_size: 42, full: true,
      meta: TPL_META_SAMPLE
    }
  };
  function currentTemplateMode() {
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) return radios[i].value;
    }
    return 'single';
  }
  function lineColOf(text, pos) {
    var line = 1, col = 1;
    for (var i = 0; i < pos && i < text.length; i++) {
      if (text.charAt(i) === '\n') { line++; col = 1; } else { col++; }
    }
    return { line: line, col: col };
  }
  function jsonErrorLoc(msg, replaced) {
    var m = msg.match(/line (\d+) column (\d+)/);
    if (m) return { line: +m[1], col: +m[2] };
    m = msg.match(/position (\d+)/);
    if (m) return lineColOf(replaced, +m[1]);
    return null;
  }
  function renderTemplatePreview() {
    var ta = document.getElementById('json-template-input');
    var pre = document.getElementById('template-preview');
    var err = document.getElementById('template-preview-error');
    if (!ta || !pre || !err) return;
    var mode = currentTemplateMode();
    var tpl = ta.value;
    pre.textContent = '';
    err.textContent = '';
    if (!tpl.trim()) {
      pre.textContent = '（留空 = 默认输出）';
      return;
    }
    var re = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;
    var keys = TPL_KEYS[mode];
    var m;
    while ((m = re.exec(tpl)) !== null) {
      if (keys.indexOf(m[1]) === -1) {
        var loc = lineColOf(tpl, m.index);
        err.textContent = '未知占位符 {{' + m[1] + '}} 位于第 ' + loc.line + ' 行第 ' + loc.col + ' 列；可用占位符: ' + keys.join(', ');
        return;
      }
    }
    var sqCbs = document.querySelectorAll('.smart-quote-cb');
    var smartMode = sqCbs.length > 0 && Array.prototype.some.call(sqCbs, function(cb) {
      return cb.checked;
    });
    var replaced = tpl.replace(re, function(mm, key) {
      var v = TPL_SAMPLE[mode][key];
      if (v === undefined) return 'null';
      return JSON.stringify(v);
    });
    if (smartMode) {
      // 智能去引号：判定逻辑单一来源在后端（复用约定），占位预览不做第二套实现
      pre.textContent = replaced + '\n（智能去引号模式：字符串值按勾选形态去引号，以真实数据预览为准）';
      return;
    }
    try {
      var parsed = JSON.parse(replaced);
      pre.textContent = JSON.stringify(parsed, null, 2);
    } catch (e) {
      var loc = jsonErrorLoc(e.message, replaced);
      if (loc) {
        err.textContent = 'JSON 格式非法（第 ' + loc.line + ' 行第 ' + loc.col + ' 列附近）: ' + e.message;
      } else {
        err.textContent = 'JSON 格式非法: ' + e.message;
      }
    }
  }
  function resetTemplateToDefault() {
    var ta = document.getElementById('json-template-input');
    if (!ta) return;
    ta.value = TPL_DEFAULTS[currentTemplateMode()];
    renderTemplatePreview();
  }
  function previewWithRealData() {
    var btn = document.getElementById('preview-live-btn');
    if (!btn) return;
    var pre = document.getElementById('template-preview');
    var err = document.getElementById('template-preview-error');
    var urlPath = btn.getAttribute('data-url');
    if (!urlPath || !pre || !err) return;
    btn.disabled = true;
    btn.textContent = '预览中...';
    var fd = new URLSearchParams();
    var ta = document.getElementById('json-template-input');
    fd.append('json_template', ta ? ta.value : '');
    var ruleTa = document.getElementsByName('rule_json')[0];
    fd.append('rule_json', ruleTa ? ruleTa.value : '');
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) fd.append('result_mode', radios[i].value);
    }
    var idxSel = document.getElementsByName('result_index')[0];
    fd.append('result_index', idxSel ? idxSel.value : '0');
    var rlInput = document.getElementsByName('row_limit')[0];
    fd.append('row_limit', rlInput ? rlInput.value : '0');
    var sqHidden = document.getElementById('smart-quote-flags-input');
    fd.append('smart_quote_flags', sqHidden ? sqHidden.value : '0');
    fetch(urlPath, {method: 'POST', body: fd})
      .then(function(r) {
        return r.json().catch(function() {
          return {ok: false, error: '响应解析失败（HTTP ' + r.status + '）'};
        });
      })
      .then(function(data) {
        if (data && data.ok) {
          try {
            pre.textContent = JSON.stringify(JSON.parse(data.output), null, 2);
          } catch (e) {
            pre.textContent = data.output;
          }
          err.textContent = '';
        } else {
          pre.textContent = '';
          err.textContent = '真实数据预览失败: ' + ((data && data.error) || '未知错误');
        }
      })
      .catch(function(e) {
        err.textContent = '真实数据预览失败: ' + e;
      })
      .then(function() {
        btn.disabled = false;
        btn.textContent = '用真实数据预览';
      });
  }
  function updateTemplateMode() {
    var mode = currentTemplateMode();
    var badgesSingle = document.getElementById('tpl-badges-single');
    var badgesAll = document.getElementById('tpl-badges-all');
    var defSingle = document.getElementById('tpl-default-single');
    var defAll = document.getElementById('tpl-default-all');
    if (badgesSingle) badgesSingle.style.display = mode === 'single' ? 'block' : 'none';
    if (badgesAll) badgesAll.style.display = mode === 'all' ? 'block' : 'none';
    if (defSingle) defSingle.style.display = mode === 'single' ? 'block' : 'none';
    if (defAll) defAll.style.display = mode === 'all' ? 'block' : 'none';
    renderTemplatePreview();
  }
  function updateTemplateState() {
    var fmtSel = document.querySelector('select[name="output_format"]');
    var isCsv = fmtSel && fmtSel.value === 'csv';
    var ta = document.getElementById('json-template-input');
    var btn = document.getElementById('template-reset-btn');
    var liveBtn = document.getElementById('preview-live-btn');
    var hint = document.getElementById('template-csv-hint');
    var section = document.getElementById('template-section');
    if (ta) ta.disabled = isCsv;
    if (btn) btn.disabled = isCsv;
    if (liveBtn) liveBtn.disabled = isCsv;
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
    if (section) section.style.opacity = isCsv ? '0.55' : '1';
  }
  document.addEventListener('DOMContentLoaded', function() {
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', updateTemplateMode);
    }
    var fmtSel = document.querySelector('select[name="output_format"]');
    if (fmtSel) fmtSel.addEventListener('change', updateTemplateState);
    updateTemplateMode();
    updateTemplateState();
  });
</script>
'''


def build_api_endpoint_preview_help_html(report_id: int, endpoint_id: int) -> str:
    """渲染真实数据预览指引页（预览地址被直接 GET 打开时）。

    预览需要携带表单未保存值（json_template/rule_json/result_mode/
    result_index/row_limit），直接打开地址无法执行，给出返回编辑页的指引。
    """
    back_url = _api_endpoint_url(report_id, endpoint_id)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>真实数据预览</title></head>"
        "<body style='font-family:sans-serif;background:#f8fafc;margin:0;"
        "padding:60px 20px;color:#0f172a'>"
        "<div style='max-width:560px;margin:0 auto;background:#fff;"
        "border:1px solid #e2e8f0;border-radius:12px;padding:32px'>"
        "<h2 style='margin-top:0'>真实数据预览</h2>"
        "<p>预览需要携带当前编辑表单中的模板与规则参数，请通过"
        "「用真实数据预览」按钮发起，或点击下方按钮返回编辑页填写。"
        "</p><a href='" + back_url + "' style='display:inline-block;margin-top:12px;"
        "padding:8px 20px;background:#6366f1;color:#fff;border-radius:8px;"
        "text-decoration:none'>返回编辑页</a>"
        "<div style='margin-top:24px;font-size:12px;color:#64748b'>"
        "POST 请求需携带参数：json_template、rule_json、result_mode、"
        "result_index、row_limit（均与编辑表单一致）。</div>"
        "</div></body></html>"
    )


def build_api_endpoint_form_html(report_id: int, report_name: str,
                                 endpoint: dict = None,
                                 flash: str = None,
                                 result_names_list: list = None,
                                 result_count: int = 1,
                                 endpoint_id: int = None,
                                 is_edit: bool = None,
                                 api_keys: list = None) -> str:
    """
    渲染 API 端点编辑/新增表单。

    参数:
        report_id: 关联报表 ID
        report_name: 关联报表名称（显示用）
        endpoint: 现有端点配置（None 表示新增；保存失败回显时传表单临时数据）
        flash: 错误消息
        result_names_list: 结果集名称列表（按行分割）
        result_count: 结果集估算数量
        endpoint_id: 端点 ID（决定 action_url）
        is_edit: 表单模式（None 时按 endpoint 是否为 None 判定）
    """
    if is_edit is None:
        is_edit = endpoint is not None
    if is_edit:
        ep_id = endpoint_id or (endpoint or {}).get("id")
        action_url = _api_endpoint_url(report_id, ep_id)
        title = "编辑 API 接口"
    else:
        action_url = f"/config/reports/{report_id}/api_endpoints/new"
        title = "新增 API 接口"

    flash_html = build_flash_html(flash) if flash else ""

    name = _escape(endpoint["name"]) if endpoint else ""
    description = _escape((endpoint or {}).get("description") or "")
    url_path = endpoint["url_path"] if endpoint else ""
    # 从完整 URL 路径中剥离 /api/ 前缀，仅保留用户输入的后段
    url_path_short = app_config.strip_api_prefix(url_path)
    url_path_short = _escape(url_path_short)
    output_format = (endpoint or {}).get("output_format", "json")
    row_limit = str((endpoint or {}).get("row_limit", 0) or 0)
    allowed_origins = _escape((endpoint or {}).get("allowed_origins") or "")
    enabled_checked = ' checked' if (endpoint is None or int(endpoint.get("enabled", 1))) else ''
    allow_fetch_all_checked = (' checked' if (endpoint is None or int(endpoint.get("allow_fetch_all", 1))) else '')
    static_cache_checked = (' checked' if (endpoint is None or int(endpoint.get("static_cache", 1))) else '')
    # 智能去引号面板默认全不勾（= 标准 JSON，零破坏）；「数字（原生类型）」恒裸
    # 不占位，仅说明文案；存量 json_no_quotes=1 由迁移映射为面板全开（0b111）
    smart_flags = int((endpoint or {}).get("smart_quote_flags", 0) or 0)
    sq_decimal_checked = ' checked' if (smart_flags & 1) else ''
    sq_scientific_checked = ' checked' if (smart_flags & 2) else ''
    sq_thousand_checked = ' checked' if (smart_flags & 4) else ''

    # 结果集输出模式
    result_mode = (endpoint or {}).get("result_mode", "single")
    result_index = int((endpoint or {}).get("result_index", 0))

    # 从三个 DB 字段拼合规则 JSON
    if endpoint:
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
    template_val = _escape((endpoint or {}).get("json_template") or "")

    # 真实数据预览：仅编辑态可用（新增端点无 endpoint_id、无关联已存配置）
    if endpoint_id is not None:
        live_preview_html = (
            '<div style="margin:10px 0">'
            f'<button type="button" id="preview-live-btn" data-url="{_api_endpoint_url(report_id, endpoint_id, "preview")}" '
            'onclick="previewWithRealData()" '
            'style="padding:6px 14px;cursor:pointer;border:1px solid #6366f1;border-radius:6px;background:#eef2ff;font-size:13px;color:#4338ca">用真实数据预览</button>'
            '<span style="font-size:12px;color:#94a3b8;margin-left:8px">以当前表单未保存的模板/规则执行真实查询（最多 3 行数据），结果展示在下方预览区</span>'
            '</div>'
        )
    else:
        live_preview_html = ""

    # API Key 管理：编辑态渲染管理区块（独立表单，放在主表单之外
    # 避免 HTML 嵌套 form——嵌套 form 会提前闭合主表单导致保存按钮失效）；
    # 新增态表单内显示"保存后自动生成"提示
    if is_edit and endpoint_id:
        api_key_block_html = ""
        key_manage_extra = build_api_key_manage_html(
            api_keys or [], report_id, endpoint_id)
    else:
        api_key_block_html = (
            '<div class="flash-warn" style="margin-bottom:16px;padding:10px 14px;'
            'border-radius:8px;border:1px solid #fde68a;font-size:13px">'
            '<strong>🔑 API Key：</strong>保存后将自动生成 API Key（名称=接口名称），'
            '可在编辑页「API Key 管理」区块查看、复制与禁用。</div>'
        )
        key_manage_extra = ""

    return f"""<div class="card">
<h2>{title}</h2>
{flash_html}
<div style="margin-bottom:16px;padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:14px;color:#475569">
  关联报表: <strong>{_escape(report_name)}</strong> (ID: {report_id})
</div>
<form method="post" action="{action_url}" class="config-form">
  <label>接口名称: <input type="text" name="name" value="{name}" required
    placeholder="例如: 客户数据 API"></label>

  <label>接口说明（可选，仅页面展示，不进入 API 输出）:
    <textarea name="description" class="sql-textarea" placeholder="描述该接口的用途、当前状态、使用注意事项，支持换行…" rows="4" style="min-height:80px;font-family:inherit">{description}</textarea>
  </label>

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
    <button type="button" onclick="copyToClipboard('full-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>
  <div id="fetch-all-url-row" style="margin-top:6px;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:13px;color:#475569;display:{'flex' if allow_fetch_all_checked else 'none'};align-items:center;gap:8px;flex-wrap:wrap">
    <span style="font-weight:500;color:#64748b">全量 URL:</span>
    <code id="fetch-all-url-text" style="flex:1;font-family:monospace;font-size:13px;word-break:break-all"></code>
    <button type="button" onclick="copyToClipboard('fetch-all-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>
  <script>
  function updateFullUrl() {{
    var input = document.getElementById('url-path-input');
    var display = document.getElementById('full-url-text');
    var path = input.value || '';
    display.textContent = buildApiUrl('/api/' + path, 'base');
    updateFetchAllUrl();
    updateStaticUrl();
  }}
  function updateFetchAllUrl() {{
    var input = document.getElementById('url-path-input');
    var row = document.getElementById('fetch-all-url-row');
    var checkbox = document.querySelector('input[type="checkbox"][name="allow_fetch_all"]');
    if (!input || !row) return;
    var show = !checkbox || checkbox.checked;
    row.style.display = show ? 'flex' : 'none';
    if (show) {{
      var text = document.getElementById('fetch-all-url-text');
      var path = input.value || '';
      text.textContent = buildApiUrl('/api/' + path, 'full');
    }}
  }}
  function updateStaticUrl() {{
    var input = document.getElementById('url-path-input');
    var row = document.getElementById('static-url-row');
    var checkbox = document.getElementById('static-cache-checkbox');
    if (!input || !row) return;
    var show = checkbox && checkbox.checked && !checkbox.disabled;
    row.style.display = show ? 'flex' : 'none';
    if (show) {{
      var text = document.getElementById('static-url-text');
      var path = input.value || '';
      text.textContent = buildApiUrl('/api/' + path, 'static');
    }}
  }}
  function updateSmartFlags() {{
    var cbs = document.querySelectorAll('.smart-quote-cb');
    var hidden = document.getElementById('smart-quote-flags-input');
    if (!hidden) return;
    var flags = 0;
    cbs.forEach(function(cb) {{
      if (cb.checked) flags |= parseInt(cb.value, 10) || 0;
    }});
    hidden.value = flags;
  }}
  function updateStaticCacheState() {{
    var fmtSel = document.querySelector('select[name="output_format"]');
    if (!fmtSel) return;
    var isCsv = fmtSel.value === 'csv';
    var cb = document.getElementById('static-cache-checkbox');
    var hint = document.getElementById('static-cache-csv-hint');
    if (cb) {{
      cb.disabled = isCsv;
      if (isCsv) cb.checked = false;
    }}
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
    var hintNoQuotes = document.getElementById('json-no-quotes-csv-hint');
    var sqCbs = document.querySelectorAll('.smart-quote-cb');
    if (sqCbs.length) {{
      sqCbs.forEach(function(cb) {{
        cb.disabled = isCsv;
        if (isCsv) cb.checked = false;
      }});
      if (isCsv) updateSmartFlags();
    }}
    if (hintNoQuotes) hintNoQuotes.style.display = isCsv ? 'inline' : 'none';
    updateStaticUrl();
  }}
  document.addEventListener('DOMContentLoaded', function() {{
    updateFullUrl();
    updateFetchAllUrl();
    updateStaticCacheState();
  }});
  </script>

  <label>输出格式:
    <select name="output_format" onchange="updateStaticCacheState();updateTemplateState()">{format_opts}</select>
  </label>

  <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-top:8px">
    <input type="hidden" name="static_cache" value="0">
    <input type="checkbox" name="static_cache" value="1"{static_cache_checked} id="static-cache-checkbox"
      onchange="updateStaticUrl()">
    <span style="font-weight:600">静态文件缓存（.json 变体）</span>
    <span id="static-cache-csv-hint" style="display:none;color:#dc2626;font-size:12px;font-weight:400">仅 JSON 格式支持</span>
  </label>
  <div style="margin:6px 0 12px 0;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;color:#475569;line-height:1.7">
    开启后，调用方在端点 URL 后追加 <code>.json</code> 即可访问静态化输出（全量数据 + meta 节点），
    命中时零查询零计算；缓存失效自动回退并重建。TTL 与报表缓存配置（cache_ttl_hours）一致。
  </div>
  <div id="static-url-row" style="margin-top:6px;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:13px;color:#475569;display:{'flex' if static_cache_checked else 'none'};align-items:center;gap:8px;flex-wrap:wrap">
    <span style="font-weight:500;color:#64748b">静态 URL:</span>
    <code id="static-url-text" style="flex:1;font-family:monospace;font-size:13px;word-break:break-all"></code>
    <button type="button" onclick="copyToClipboard('static-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>

  <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-top:8px">
    <span style="font-weight:600">智能去引号</span>
    <span id="json-no-quotes-csv-hint" style="display:none;color:#dc2626;font-size:12px;font-weight:400">仅 JSON 格式支持</span>
  </label>
  <div style="margin:6px 0 0 0;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;color:#475569;line-height:1.7">
    <input type="hidden" name="smart_quote_flags" id="smart-quote-flags-input" value="{smart_flags}">
    勾选以下形态时，JSON 输出中对应字符串值<strong>去掉引号</strong>（未勾选形态保持带引号）：
    <label style="display:flex;align-items:center;gap:6px;margin-top:6px;font-weight:400">
      <input type="checkbox" class="smart-quote-cb" value="1"{sq_decimal_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      十进制数字（含正负号），如 <code>-1.5</code>；前导零数值化（<code>007</code> → <code>7</code>）
    </label>
    <label style="display:flex;align-items:center;gap:6px;margin-top:4px;font-weight:400">
      <input type="checkbox" class="smart-quote-cb" value="2"{sq_scientific_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      科学计数法，如 <code>1e5</code>（符合 JSON 数字语法，原样输出）
    </label>
    <label style="display:flex;align-items:center;gap:6px;margin-top:4px;font-weight:400">
      <input type="checkbox" class="smart-quote-cb" value="4"{sq_thousand_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      千分位数字，如 <code>1,000</code>（输出去逗号数值化：<code>1,000</code> → <code>1000</code>）
    </label>
    <div style="margin-top:6px">
      开启任一形态时，输出<strong>永远合法 JSON</strong>（RFC 8259）：原生 int/float 始终输出为数字，
      无需勾选；Decimal 数值列在勾选「十进制数字」或「科学计数法」时输出为数字，未勾选时带引号；
      含非数字内容的文本（如日期、空串、<code>true</code>/<code>false</code>）永远带引号。
      模板占位预览在勾选时以真实数据预览为准。
    </div>
  </div>

  {_build_result_mode_ui(result_count, result_names_list, result_mode, result_index)}

  <div id="template-section" style="margin:16px 0;padding:14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
    <div style="font-weight:600;font-size:14px;color:#1e293b;margin-bottom:8px">JSON 输出模板（可选）</div>
    <label style="font-size:13px;color:#475569;display:block">
      <textarea name="json_template" id="json-template-input" rows="8"
        style="width:100%;min-height:150px;font-family:monospace;box-sizing:border-box"
        placeholder='{{"data": {{{{data}}}}, "total": {{{{total}}}}, "page": {{{{page}}}}, "page_size": {{{{page_size}}}}, "total_pages": {{{{total_pages}}}}}}'
        oninput="renderTemplatePreview()">{template_val}</textarea>
    </label>
    <div style="margin:6px 0;font-size:12px;color:#64748b;line-height:1.7">
      留空 = 默认输出。自定义模板以默认 JSON 为起点，用 <code>{{{{占位符}}}}</code> 引用数据，
      值将按实际数据替换（缺键输出 null）。<span id="template-csv-hint" style="display:none;color:#dc2626;font-weight:600">模板仅 JSON 格式支持，CSV 格式下已禁用。</span>
    </div>

    <div style="margin:10px 0;font-size:12px;color:#475569;line-height:2">
      <span style="font-weight:600;color:#1e293b">可用占位符（随「结果集输出模式」切换）：</span>
      <div id="tpl-badges-single">
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{data}}}}</span>数据数组
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{total}}}}</span>总行数
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{page}}}}</span>页码
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{page_size}}}}</span>每页条数
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{total_pages}}}}</span>总页数
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{full}}}}</span>全量标记（fetch_all 时 true）
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{meta}}}}</span>静态缓存 meta（.json 变体）
      </div>
      <div id="tpl-badges-all" style="display:none">
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{results}}}}</span>结果集数组
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{mode}}}}</span>模式（固定 "all"）
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{page}}}}</span>页码
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{page_size}}}}</span>每页条数
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{full}}}}</span>全量标记（fetch_all 时 true）
        <span style="display:inline-block;margin:0 4px 0 0;padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:4px;font-family:monospace">{{{{meta}}}}</span>静态缓存 meta（.json 变体）
      </div>
    </div>

    <details open style="margin:10px 0;font-size:13px;color:#475569">
      <summary style="cursor:pointer;color:#1e293b;font-weight:600">默认 JSON 起点（把默认结构改一改就是模板）</summary>
      <div id="tpl-default-single" style="margin-top:8px">
        <pre style="margin:0;padding:10px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;line-height:1.8;color:#334155;overflow:auto">{{
  "data": {{{{data}}}},              // 数据数组
  "total": {{{{total}}}},            // 总行数
  "page": {{{{page}}}},              // 页码
  "page_size": {{{{page_size}}}},    // 每页条数
  "total_pages": {{{{total_pages}}}} // 总页数
}}</pre>
        <div style="margin-top:6px;font-size:12px;color:#94a3b8">注：原生默认输出在 fetch_all 时含 <code>"full": {{{{full}}}}</code>，.json 静态变体含 <code>"meta": {{{{meta}}}}</code>；如需这些字段，在模板中手动加对应键</div>
      </div>
      <div id="tpl-default-all" style="display:none;margin-top:8px">
        <pre style="margin:0;padding:10px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;line-height:1.8;color:#334155;overflow:auto">{{
  "results": {{{{results}}}},   // 结果集数组（每项含 name/data/total/page/page_size/total_pages）
  "mode": {{{{mode}}}},         // 固定 "all"
  "page": {{{{page}}}},         // 页码
  "page_size": {{{{page_size}}}} // 每页条数
}}</pre>
        <div style="margin-top:6px;font-size:12px;color:#94a3b8">注：fetch_all 时原生输出含 <code>"full": {{{{full}}}}</code>，.json 静态变体含 <code>"meta": {{{{meta}}}}</code></div>
      </div>
    </details>

    <div style="margin:10px 0">
      <button type="button" id="template-reset-btn" onclick="resetTemplateToDefault()"
        style="padding:6px 14px;cursor:pointer;border:1px solid #cbd5e1;border-radius:6px;background:#fff;font-size:13px">还原为默认 JSON 格式</button>
      <span style="font-size:12px;color:#94a3b8;margin-left:8px">还原结果为当前模式的默认模板文本（不含 full/meta，可手动添加）</span>
    </div>
    {live_preview_html}

    <div style="font-size:12px;color:#64748b;margin-top:10px">实时预览（样例数据）：</div>
    <pre id="template-preview" style="margin:4px 0 0 0;padding:12px;background:#0f172a;color:#e2e8f0;border-radius:6px;font-size:12px;line-height:1.6;overflow:auto;max-height:280px"></pre>
    <div id="template-preview-error" style="color:#dc2626;font-size:12px;margin-top:6px"></div>
  </div>

  {_API_TEMPLATE_JS}

  <div class="flash-warn" style="margin-bottom:16px;padding:10px 14px;border-radius:8px;border:1px solid #fde68a;font-size:13px">
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

  <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-top:8px">
    <input type="hidden" name="allow_fetch_all" value="0">
    <input type="checkbox" name="allow_fetch_all" value="1"{allow_fetch_all_checked} onchange="updateFetchAllUrl()">
    <span style="font-weight:600">允许全量获取（fetch_all 参数）</span>
  </label>
  <div style="margin:6px 0 12px 0;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;color:#475569;line-height:1.7">
    <strong>使用示例：</strong>开启后，调用方在请求中携带 <code>fetch_all</code> 参数即可一次获取全部数据（不做翻页）：
    <div style="font-family:monospace;font-size:12px;margin-top:4px">
      GET&nbsp;&nbsp; /api/&lt;路径&gt;?fetch_all=true<br>
      POST&nbsp; body: {{"fetch_all": true}}
    </div>
    <div style="color:#94a3b8;margin-top:4px">值仅接受 true / 1 / yes；关闭后即使传递该参数，也按翻页逻辑返回</div>
  </div>

  {api_key_block_html}

  <label>CORS 允许来源（逗号分隔，留空=不设 CORS）:
    <input type="text" name="allowed_origins" value="{allowed_origins}"
      placeholder="例如: https://example.com,http://localhost:3000"></label>

  <label style="display:flex;align-items:center;gap:8px;font-weight:400">
    <input type="hidden" name="enabled" value="0">
    <input type="checkbox" name="enabled" value="1"{enabled_checked}>
    <span style="font-weight:600">启用</span>
  </label>

  <div class="form-actions">
    <button type="submit" name="action" value="save" class="btn btn-primary">保存</button>
    <button type="submit" name="action" value="save_close" class="btn btn-outline">保存并关闭</button>
    <a href="/config/reports/{report_id}/edit" class="cancel">关闭</a>
  </div>
</form>
{key_manage_extra}
</div>"""


# ===================================================================
# API Key 管理区块（多 key 化 PH-03）
# ===================================================================


def build_api_key_manage_html(keys: list, report_id: int, endpoint_id: int) -> str:
    """构建「API Key 管理」区块 HTML。

    独立于主表单渲染（操作 POST 到
    /config/reports/{report_id}/api_endpoints/{endpoint_id}/api_keys），
    避免 HTML 嵌套 form。每行：名称 + 掩码 + 复制 + 启用/禁用 + 删除；
    底部提供「生成新 Key」（名称留空=端点名）。
    """
    action_url = _api_endpoint_url(report_id, endpoint_id, "api_keys")
    rows = ""
    for k in keys:
        kid = k["id"]
        kname = _escape(k.get("name") or "未命名")
        kraw = k.get("api_key") or ""
        kdisp = _mask_api_key(kraw) if kraw else "—"
        enabled = int(k.get("enabled", 1))
        state = (build_state_span("启用")
                 if enabled else build_state_span("禁用", "warn"))
        toggle_label = "禁用" if enabled else "启用"
        toggle_confirm = (
            " onsubmit=\"return confirm('确定禁用该 API Key？禁用后调用方立即失效。')\""
            if enabled else "")
        toggle_form = (
            f'<form method="post" action="{action_url}" style="display:inline"{toggle_confirm}>'
            f'<input type="hidden" name="action" value="toggle">'
            f'<input type="hidden" name="key_id" value="{kid}">'
            f'<button type="submit" class="btn-mini btn-mini-m">{toggle_label}</button>'
            f'</form>')
        del_form = (
            f'<form method="post" action="{action_url}" style="display:inline" '
            f'onsubmit="return confirm(\'确定删除该 API Key？删除后调用方立即失效。\')">'
            f'<input type="hidden" name="action" value="delete">'
            f'<input type="hidden" name="key_id" value="{kid}">'
            f'<button type="submit" class="btn-mini btn-mini-m" '
            f'style="color:#dc2626">删除</button>'
            f'</form>')
        rows += (
            f'<div style="display:flex;align-items:center;gap:10px;padding:7px 0;'
            f'border-bottom:1px dashed #e2e8f0">'
            f'<span style="min-width:110px;font-size:13px;color:#1e293b;font-weight:600">'
            f'{kname}</span>'
            f'<code style="font-size:12px;color:#94a3b8">{kdisp}</code>'
            f'<code id="api-key-raw-{kid}" style="display:none">{_escape(kraw)}</code>'
            f'<button type="button" onclick="copyToClipboard(\'api-key-raw-{kid}\')" '
            f'title="复制完整 API Key" class="btn-mini btn-mini-outline-key">复制</button>'
            f'{state}{toggle_form}{del_form}'
            f'</div>')
    if not rows:
        rows = (
            '<div style="padding:10px 0;font-size:13px;color:#94a3b8">'
            '暂无 API Key——接口为公开访问（无需鉴权）。生成 Key 后立即生效。</div>')
    return (
        f'<div style="margin:16px 0;padding:14px;background:#f8fafc;border-radius:8px;'
        f'border:1px solid #e2e8f0">'
        f'<div style="font-weight:600;font-size:14px;color:#1e293b;margin-bottom:4px">'
        f'🔑 API Key 管理</div>'
        f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">'
        f'每个调用方可分配独立 Key（名称仅作管理标识）；Key 明文可查看（内控要求），'
        f'通过 Authorization: Bearer &lt;key&gt; 或 ?api_key=xxx 调用。'
        f'禁用/删除后立即失效。</div>'
        f'{rows}'
        f'<form method="post" action="{action_url}" '
        f'style="display:flex;align-items:center;gap:8px;margin-top:10px">'
        f'<input type="text" name="name" placeholder="Key 名称（留空=接口名称）" '
        f'style="flex:1;min-width:160px;padding:6px 10px;border:1px solid #cbd5e1;'
        f'border-radius:6px;font-size:13px">'
        f'<input type="hidden" name="action" value="add">'
        f'<button type="submit" class="btn-mini btn-mini-solid btn-mini-primary">'
        f'生成新 Key</button>'
        f'</form>'
        f'</div>')


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
    db_size: int = 0,
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
        rows_html = build_empty_row_html(6, "暂无匹配的审计日志")

    qs = urllib.parse.urlencode({k: v for k, v in filters.items() if v})
    qs_amp = qs.replace("&", "&amp;") if qs else ""
    page_url_base = f"/audit?{qs_amp}"
    pagination = build_pagination_html(
        report_id=0,
        current=page,
        total_pages=total_pages,
        page_size=page_size,
        total_rows=total,
        page_url_base=page_url_base,
    )

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
        html += build_flash_html(message, is_error="成功" not in message)

    size_info = ""
    if db_size > 0:
        for unit in ("B", "KB", "MB", "GB"):
            if db_size < 1024:
                size_info = f"{db_size:.1f} {unit}"
                break
            db_size /= 1024
        size_info = f'<span style="margin-left:16px;color:#64748b">数据库大小: {size_info}</span>'

    html += f"""
<div class="card">
  <h2>审计日志</h2>
  <div class="audit-info">
    <span>共 {total} 条记录，第 {page}/{total_pages} 页{size_info}</span>
    <div class="audit-actions">
      <a href="/audit?{export_qs}" class="btn btn-sm btn-success">导出 CSV</a>
    </div>
  </div>
  <div class="audit-filters">
    <form method="get" action="/audit" style="display:contents">
      <label>类型: <select name="type">{type_html}</select></label>
      <label>操作者: <input type="text" name="session_user" value="{html_mod.escape(session_user_val)}" placeholder="操作者"></label>
      <label>关键字: <input type="text" name="keyword" value="{html_mod.escape(keyword_val)}" placeholder="关键字{FILTER_HINT_SUFFIX}"></label>
      <div class="date-shortcuts">{range_btns}</div>
      <label>从: <input type="datetime-local" name="date_from" value="{html_mod.escape(date_from)}"></label>
      <label>到: <input type="datetime-local" name="date_to" value="{html_mod.escape(date_to)}"></label>
      <div class="filter-btns">
        <button type="submit" class="btn btn-sm btn-primary">筛选</button>
        {render_filter_help()}
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


# ===================================================================


def build_api_urls_section_html(api_endpoints: list[dict], base_url: str) -> str:
    """
    渲染 API URL 折叠区域，显示每个 API 端点的调用地址。

    参数:
        api_endpoints: API 端点列表
        base_url: 服务器基础 URL（如 http://localhost:8080）
    """
    if not api_endpoints:
        return ""

    # 按接口名称分组（如果只有一个，不分组）
    if len(api_endpoints) == 1:
        ep = api_endpoints[0]
        return _build_single_api_url_html(ep, base_url)

    # 多个 API 时分组显示
    return _build_grouped_api_urls_html(api_endpoints, base_url)


def build_collapse_section_html(title: str, content: str,
                                default_hidden: bool = True,
                                extra_style: str = "",
                                button_text: str = None,
                                multiline: bool = False) -> str:
    """构建折叠区骨架 HTML（debug-info 样式）。

    标题按钮: class="debug-toggle" onclick="toggleSection(this, '标题')"。
    按钮初始文案为 "▶ 标题"（备注等特殊形态经 button_text 覆盖）。
    multiline=True 时外层按多行排版输出（折叠区内容本身多行的场景），
    内容行的缩进由调用方在 content 中自带，保证与现状逐字符一致。
    """
    style_attr = f' style="{extra_style}"' if extra_style else ""
    hidden_cls = " hidden" if default_hidden else ""
    btn_text = button_text if button_text is not None else f"▶ {title}"
    if multiline:
        return (f'<div class="debug-info"{style_attr}>\n'
                f'<button class="debug-toggle" onclick="toggleSection(this, \'{title}\')" type="button">{btn_text}</button>\n'
                f'<div class="debug-content{hidden_cls}">\n'
                f'{content}\n'
                f'</div>\n'
                f'</div>')
    return (f'<div class="debug-info"{style_attr}>'
            f'<button class="debug-toggle" onclick="toggleSection(this, \'{title}\')" type="button">{btn_text}</button>'
            f'<div class="debug-content{hidden_cls}">{content}</div>'
            '</div>')


def _build_api_url_row(code_id: str, label: str, url_path: str,
                       kind: str, url_value: str,
                       disabled: bool = False,
                       disabled_hint: str = "",
                       edit_url: str = "") -> str:
    """构建一行 API URL 展示（标签 + code + 复制按钮，样式与 Debug 信息模块一致）。

    disabled=True 时行置灰：地址保留可见（用户能知道该能力存在但未启用）、
    复制按钮禁用、title 悬浮提示原因，并提供「去开启」链接（新窗口打开接口配置页）。
    """
    code_style = ('font-size:12px;color:#94a3b8;text-decoration:line-through;'
                  if disabled else
                  'font-size:12px;background:#f1f5f9;padding:2px 6px;'
                  'border-radius:4px;color:#4f46e5')
    if disabled:
        copy_btn = ('<button type="button" disabled '
                    'class="btn-mini btn-mini-disabled">复制</button>')
        fix_link = (f'<a href="{_escape(edit_url)}" target="_blank" rel="noopener" '
                    f'title="在接口配置中开启该能力" '
                    f'style="font-size:12px;color:#4f46e5;text-decoration:none;white-space:nowrap">去开启 ↗</a>'
                    if edit_url else "")
    else:
        copy_btn = (f'<button onclick="copyToClipboard(\'{code_id}\')" '
                    f'class="btn-mini btn-mini-solid btn-mini-primary">复制</button>')
        fix_link = ""
    return (f'<div style="margin:2px 0;opacity:{"0.55" if disabled else "1"}">'
            f'<span style="font-weight:500">{label}</span> '
            f'<code id="{code_id}" class="api-url-code" data-path="{_escape(url_path)}" '
            f'data-kind="{kind}" style="{code_style}" '
            f'title="{_escape(disabled_hint) if disabled else ""}">{_escape(url_value)}</code> '
            f'{copy_btn} {fix_link}'
            f'</div>')


def _build_api_admin_actions_html(ep: dict) -> str:
    """构建 API 管理操作行（启用/禁用切换 + 配置入口）。

    报表查看页折叠区内展示：POST toggle 到独立管理页端点（带回跳来源），
    配置按钮新窗口打开编辑表单。管理操作随折叠区默认收起，不打扰浏览者。
    """
    ep_id = int(ep.get("id", 0))
    report_id = int(ep.get("report_id", 0))
    if not ep_id:
        return ""
    enabled = int(ep.get("enabled", 1)) == 1
    toggle_label = "禁用" if enabled else "启用"
    # 禁用对外停服，需确认；启用为无损操作不确认
    confirm_attr = (" onsubmit=\"return confirm('确定禁用 API 接口 "
                    f"{_escape(ep.get('name') or '')}？')\"") if enabled else ""
    return_to = f"/report?id={report_id}"
    return f"""<div style="margin-top:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
  <form method="post" action="/config/api-endpoints" style="display:inline"{confirm_attr}>
    <input type="hidden" name="action" value="toggle">
    <input type="hidden" name="endpoint_id" value="{ep_id}">
    <input type="hidden" name="return_to" value="{return_to}">
    <button type="submit" class="btn btn-sm btn-outline" style="cursor:pointer">{toggle_label}</button>
  </form>
  <a href="{_api_endpoint_url(report_id, ep_id)}" target="_blank" rel="noopener" class="btn btn-sm btn-outline">配置</a>
</div>"""


def build_state_span(text: str, state: str = "ok", bold: bool = True) -> str:
    """构建状态文字徽章 span HTML。

    state: ok=绿 #059669 / warn=红 #dc2626 / muted=灰 #94a3b8。
    bold=False 时省略 font-weight（个别场景原样式无加粗，保持现状）。
    """
    colors = {"ok": "#059669", "warn": "#dc2626", "muted": "#94a3b8"}
    color = colors.get(state, "#059669")
    weight = ";font-weight:600" if bold else ""
    return f'<span style="color:{color}{weight}">{text}</span>'


def _api_endpoint_url(report_id, ep_id, action: str = "edit") -> str:
    """拼装 API 端点配置页 URL（/config/reports/{report_id}/api_endpoints/{ep_id}/{action}）。"""
    return f"/config/reports/{report_id}/api_endpoints/{ep_id}/{action}"


def _api_url_variants(base_url: str, url_path: str) -> tuple[str, str, str]:
    """计算 API 地址三变体（完整/全量/静态），与内联拼接输出逐字符一致。"""
    return (f"{base_url}{url_path}",
            f"{base_url}{url_path}{FETCH_ALL_QUERY}",
            f"{base_url}{url_path}{static_cache.JSON_SUFFIX}")


def _build_api_status_badge(enabled) -> str:
    """构建接口状态徽章 HTML（启用=绿/禁用=红）。"""
    return (build_state_span("启用")
            if int(enabled or 0) == 1 else
            build_state_span("禁用", "warn"))


def _build_api_description_html(ep: dict) -> str:
    """构建接口说明块 HTML（纯展示，保留换行，长文本截断 + 展开/收起）。

    截断策略：说明长度超过阈值或含换行时，以 CSS line-clamp 限 3 行，
    配"展开/收起"按钮（toggleApiDesc 切换）；短说明完整显示。
    """
    desc_raw = (ep.get("description") or "").strip()
    if not desc_raw:
        return ""
    desc = _escape(desc_raw)
    truncate = len(desc_raw) > _API_DESC_TRUNCATE_LEN or "\n" in desc_raw
    if truncate:
        box = (f'<div style="display:-webkit-box;-webkit-line-clamp:3;'
               f'-webkit-box-orient:vertical;overflow:hidden;'
               f'white-space:pre-wrap;word-break:break-word;'
               f'margin:4px 0 2px 0;font-size:13px;color:#475569;line-height:1.6">'
               f'{desc}</div>'
               f'<button type="button" onclick="toggleApiDesc(this)" '
               f'class="btn-mini btn-mini-outline-accent">展开</button>')
    else:
        box = (f'<div style="white-space:pre-wrap;word-break:break-word;'
               f'margin:4px 0 2px 0;font-size:13px;color:#475569;line-height:1.6">'
               f'{desc}</div>')
    return f'<div class="api-desc" style="margin-top:2px">{box}</div>'


def _build_api_url_item_html(ep: dict, base_url: str, name: str = None,
                             default_name: str = "未命名",
                             margin_bottom: str = "4px",
                             indent: int = 2) -> str:
    """构建单个 API 端点的折叠区内容块（名称行 + 说明 + URL 三行 + 管理操作）。

    单端点与分组端点共用（差异：名称缺省值、行间距、源码缩进），
    能力未开启的 URL 行置灰 + 原因提示（不隐藏），与配置列表页标准一致。
    """
    ep_id = ep['id']
    ep_name = name if name is not None else ep.get("name", default_name)
    url_path = ep.get("url_path", "")
    static_on = int(ep.get("static_cache", 1)) == 1
    fetch_all_on = int(ep.get("allow_fetch_all", 1)) == 1
    edit_url = _api_endpoint_url(ep.get('report_id', 0), ep_id)
    sc_enabled = static_cache.get_static_cache_config().get("enable", True)

    # url_path 已包含 /api/ 前缀，直接拼接。
    # 服务端先用 base_url 渲染占位值；页面加载后 JS 用 window.location.origin
    # 覆盖（与 API 配置后台一致，显示用户实际访问的地址）。
    base_api_url, full_url, static_url = _api_url_variants(base_url, url_path)

    rows = _build_api_url_row(f"api-url-{ep_id}", "完整 URL:", url_path, "base", base_api_url)
    rows += _build_api_url_row(
        f"api-full-{ep_id}", "全量 URL:", url_path, "full", full_url,
        disabled=not fetch_all_on,
        disabled_hint="未开启「允许全量获取」，请在接口配置中开启" if not fetch_all_on else "",
        edit_url=edit_url)
    rows += _build_api_url_row(
        f"api-static-{ep_id}", "静态 URL:", url_path, "static", static_url,
        disabled=not (static_on and sc_enabled),
        disabled_hint=(("未开启「静态缓存」，请在接口配置中开启"
                        if not static_on else
                        "全局静态缓存已关闭（app_config.json 的 static_cache.enable）")
                       if (not static_on or not sc_enabled) else ""),
        edit_url=edit_url)

    pad = " " * indent
    return (f'{pad}<div style="margin-bottom:{margin_bottom}"><strong>{_escape(ep_name)}</strong> '
            f'{_build_api_status_badge(ep.get("enabled", 1))}</div>\n'
            f'{pad}{_build_api_description_html(ep)}\n'
            f'{pad}{rows}\n'
            f'{pad}{_build_api_admin_actions_html(ep)}')


def _build_single_api_url_html(ep: dict, base_url: str) -> str:
    """构建单个 API 端点的 URL 显示区域（样式与 Debug 信息模块一致）。

    能力未开启的 URL 行置灰 + 原因提示（不隐藏），与配置列表页标准一致。
    """
    item = _build_api_url_item_html(ep, base_url)
    return build_collapse_section_html(
        "API 调用地址", item, extra_style="margin-top:8px", multiline=True)


def _build_grouped_api_urls_html(api_endpoints: list[dict], base_url: str) -> str:
    """构建多个 API 端点的分组 URL 显示区域（样式与 Debug 信息模块一致）。

    能力未开启的 URL 行置灰 + 原因提示（不隐藏），与配置列表页标准一致。
    """
    # 构建每个 API 的 HTML（与单端点共用 _build_api_url_item_html）
    api_items = ""
    for idx, ep in enumerate(api_endpoints):
        sep = ('<div style="border-top:1px dashed #cbd5e1;margin:8px 0"></div>'
               if idx > 0 else "")
        api_items += sep + "\n" + _build_api_url_item_html(
            ep, base_url, default_name=f"接口 {idx + 1}",
            margin_bottom="2px", indent=0)

    return build_collapse_section_html(
        f"API 调用地址 ({len(api_endpoints)} 个接口)",
        "  " + api_items,
        extra_style="margin-top:8px", multiline=True)
