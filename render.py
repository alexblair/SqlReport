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
