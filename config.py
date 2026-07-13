"""
config.py — 配置页面处理

职责：
- 连接池、用户、报表配置的 CRUD 操作
- 生成配置管理页面 HTML
- 处理表单提交并重定向

URL 路由约定：
  GET  /config          → 配置总览页（三个配置段展示）
  GET  /config/pools/add → 新增连接池表单
  POST /config/pools/add → 提交新增连接池
  GET  /config/pools/{id}/edit → 编辑连接池表单
  POST /config/pools/{id}/edit → 提交编辑连接池
  POST /config/pools/{id}/delete → 删除连接池
  用户和报表路由规则同上，替换 pools 为 users / reports
"""

import re
import urllib.parse
import db
import html as html_mod


# ---------------------------------------------------------------------------
# 路由解析
# ---------------------------------------------------------------------------

# 匹配 /config/pools/add, /config/pools/{id}/edit, /config/pools/{id}/copy,
# /config/pools/{id}/move-up, /config/pools/{id}/move-down, /config/reports/batch-pool
_PATH_PATTERN = re.compile(
    r"^/config/(pools|users|reports|categories)"
    r"(?:/(add|batch-pool|batch-set-category)|/(\d+)/(edit|delete|copy|move-up|move-down))?$"
)


def parse_config_path(path: str) -> dict:
    """
    解析配置页 URL 路径，返回动作参数字典。

    返回格式:
      {"section": "pools|users|reports", "action": "list|add|batch-pool|edit|delete|copy|move-up|move-down",
       "id": int|None}
    """
    match = _PATH_PATTERN.match(path)
    if not match:
        # /config 或 /config/ 视为总览
        if path in ("/config", "/config/"):
            return {"section": None, "action": "overview", "id": None}
        return {"section": None, "action": None, "id": None}

    section = match.group(1)
    # group(2) 匹配 add / batch-pool（无 id）
    simple_action = match.group(2)
    # group(3) 匹配 id, group(4) 匹配 edit/delete/copy/move-up/move-down
    obj_id = int(match.group(3)) if match.group(3) else None
    obj_action = match.group(4)

    if obj_action:
        return {"section": section, "action": obj_action, "id": obj_id}
    if simple_action:
        return {"section": section, "action": simple_action, "id": None}
    return {"section": section, "action": "add", "id": None}


# ---------------------------------------------------------------------------
# HTML 模板片段
# ---------------------------------------------------------------------------

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
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); padding: 24px; margin-bottom: 20px; animation: fadeUp 0.3s ease-out; }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  h2 { font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 16px; letter-spacing: -0.3px; }
  h3 { font-size: 16px; font-weight: 600; color: #334155; margin-bottom: 12px; }
  .section-title {
    font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 16px;
    padding-bottom: 12px; border-bottom: 2px solid #e2e8f0;
    display: flex; align-items: center; justify-content: space-between;
  }
  .section-title .actions { display: flex; gap: 8px; }
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
  form.config-form { max-width: 560px; }
  .config-form label {
    display: block; margin-top: 16px; font-weight: 600; color: #334155; font-size: 14px;
  }
  .config-form label:first-child { margin-top: 0; }
  .config-form input[type=text],
  .config-form input[type=password],
  .config-form input[type=number],
  .config-form textarea,
  .config-form select {
    width: 100%; padding: 10px 14px; margin-top: 6px;
    border: 2px solid #e2e8f0; border-radius: 8px;
    font-size: 14px; color: #1e293b; outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
    background: #f8fafc;
  }
  .config-form input:focus,
  .config-form textarea:focus,
  .config-form select:focus {
    border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.15); background: #fff;
  }
  .config-form textarea { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; resize: vertical; min-height: 100px; }
  .config-form .form-actions { margin-top: 24px; display: flex; align-items: center; gap: 12px; }
  .config-form .form-actions .cancel { color: #64748b; text-decoration: none; font-size: 14px; font-weight: 500; }
  .config-form .form-actions .cancel:hover { color: #334155; }
  .config-form select { cursor: pointer; }
  .sql-textarea {
    width: 100%; padding: 10px 14px; margin-top: 6px;
    border: 2px solid #e2e8f0; border-radius: 8px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px; line-height: 1.5; resize: vertical; min-height: 120px;
    color: #1e293b; outline: none; background: #f8fafc; tab-size: 4;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .sql-textarea:focus {
    border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.15); background: #fff;
  }
  .sql-preview {
    display: none; margin-top: 8px; padding: 10px 14px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px; line-height: 1.5; tab-size: 4; white-space: pre-wrap; word-wrap: break-word;
    border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc;
  }
  .sql-preview.show { display: block; }
  .sql-toolbar { margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap; }
  /* 语法高亮颜色 */
  .sql-hl-keyword  { color: #7c3aed; font-weight: 600; }
  .sql-hl-function { color: #2563eb; }
  .sql-hl-number   { color: #059669; }
  .sql-hl-string   { color: #b91c1c; }
  .sql-hl-comment  { color: #94a3b8; font-style: italic; }
  .empty-state { text-align: center; color: #94a3b8; padding: 32px 14px; font-size: 14px; }
  .section + .section { margin-top: 8px; }
  .ops-cell { white-space: nowrap; }
  .ops-cell form { display: inline; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }
  .badge-pool { background: #eef2ff; color: #4f46e5; }
"""

_HEADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web 报表工具 - 配置</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="navbar">
  <a href="/config" class="brand">My<span>Report</span></a>
  <div class="spacer"></div>
  <a href="/report">报表页</a>
  <a href="/config" class="nav-active">配置管理</a>
  <a href="/logout">退出</a>
</div>
<div class="container">
"""

_FOOTER = "</div></body></html>"


def _escape(text: str) -> str:
    """HTML 转义"""
    return html_mod.escape(str(text) if text is not None else "")


def _link_btn(url: str, label: str, cls: str = "btn btn-outline btn-sm") -> str:
    """生成链接按钮"""
    return f'<a href="{_escape(url)}" class="{cls}">{_escape(label)}</a>'


# ---------------------------------------------------------------------------
# 配置页渲染
# ---------------------------------------------------------------------------


def _render_pool_form(pool: dict = None, copy_mode: bool = False) -> str:
    """渲染连接池编辑/新增/复制表单"""
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


def _render_user_form(user: dict = None) -> str:
    """渲染用户编辑/新增表单"""
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


def _report_form_pool_options(conn, cur_pool_id, is_edit):
    """生成连接池下拉选项和默认提示"""
    pools = db.get_all_pools(conn)
    pool_options = ""
    for p in pools:
        sel = ' selected' if cur_pool_id is not None and str(p["id"]) == str(cur_pool_id) else ''
        pool_options += f'<option value="{p["id"]}"{sel}>{_escape(p["name"])}</option>'

    if is_edit and cur_pool_id is None:
        no_pool_opt = '<option value="" selected disabled>-- 连接池已删除，请重新选择 --</option>'
    else:
        no_pool_opt = '<option value="">-- 请选择 --</option>'
    required_attr = "" if is_edit else "required"
    return pool_options, no_pool_opt, required_attr


def _render_cat_opts(nodes, depth, cur_cat_id):
    """递归生成分类选项 HTML（树形缩进）"""
    html = ""
    for node in nodes:
        indent = "　" * depth
        sel = ' selected' if cur_cat_id != "" and str(node["id"]) == str(cur_cat_id) else ''
        html += f'<option value="{node["id"]}"{sel}>{indent}{_escape(node["name"])}</option>'
        if node["children"]:
            html += _render_cat_opts(node["children"], depth + 1, cur_cat_id)
    return html


def _report_form_cat_options(conn, cur_cat_id):
    """生成报表分类选择列表 HTML"""
    cat_tree = db.get_category_tree(conn)
    return _render_cat_opts(cat_tree, 0, cur_cat_id)


def _report_form_js_highlight():
    """返回 SQL 语法高亮 JS（h + highlight 函数）"""
    return r"""
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


def _report_form_js_formatter():
    """返回 SQL 格式化 JS（fmt 函数）"""
    return r"""
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


def _report_form_js_editor_api():
    """返回 SQL 编辑器 UI 交互 JS（formatSQL、togglePreview、事件监听）"""
    return r"""
window.formatSQL = function(btn) {
  var label = btn.closest("label");
  var ta = label.querySelector(".sql-textarea");
  var prev = label.querySelector(".sql-preview");
  if (!ta) return;
  btn.disabled = true; btn.textContent = "格式化中...";
  var formatted = fmt(ta.value);
  ta.value = formatted;
  if (prev && prev.classList.contains("show")) {
    prev.innerHTML = highlight(h(formatted));
  }
  btn.disabled = false; btn.textContent = "格式化 SQL";
};
window.togglePreview = function(btn) {
  var label = btn.closest("label");
  var ta = label.querySelector(".sql-textarea");
  var prev = label.querySelector(".sql-preview");
  if (!prev) return;
  var show = !prev.classList.contains("show");
  prev.classList.toggle("show", show);
  if (show && ta) {
    prev.innerHTML = highlight(h(ta.value));
  }
  btn.textContent = show ? "隐藏高亮" : "显示高亮";
};

document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll(".sql-textarea").forEach(function(ta) {
    ta.addEventListener("input", function() {
      var label = ta.closest("label");
      var prev = label.querySelector(".sql-preview");
      if (prev && prev.classList.contains("show")) {
        prev.innerHTML = highlight(h(ta.value));
      }
    });
  });
});
"""


def _report_form_html(title, action_url, name, sql_query, default_page_size,
                       required_attr, no_pool_opt, pool_options, category_options, memo_val,
                       result_names_val='',
                       is_edit=False, report_id=None):
    """构建报表表单完整 HTML（含 SQL 编辑器 JS + 查看/预览按钮）"""
    view_btn = (f'<a href="/report?id={report_id}" class="btn btn-outline btn-sm" target="_blank" rel="noopener">查看</a>'
                if is_edit and report_id else "")
    preview_btn = (f'<button type="button" class="btn btn-outline btn-sm" onclick="previewReport(this.form)">预览</button>'
                   if is_edit and report_id else "")
    hidden_id = f'<input type="hidden" name="id" value="{report_id}">' if is_edit and report_id else ""
    return f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form" data-action="{action_url}">
  {hidden_id}
  <label>报表名称: <input type="text" name="name" value="{name}" required></label>
  <label>SQL 查询语句:
    <textarea name="sql_query" class="sql-textarea" placeholder="输入 MySQL 语句..." spellcheck="false" rows="8">{sql_query}</textarea>
    <div class="sql-preview"></div>
    <div class="sql-toolbar">
      <button type="button" class="btn btn-outline btn-sm" onclick="formatSQL(this)">格式化 SQL</button>
      <button type="button" class="btn btn-outline btn-sm" onclick="togglePreview(this)">显示高亮</button>
    </div>
  </label>
  <label>默认分页大小: <input type="number" name="default_page_size" value="{default_page_size}" min="1" required></label>
  <label>使用的连接池:
    <select name="pool_id" {required_attr}>
      {no_pool_opt}
      {pool_options}
    </select>
  </label>
  <label>报表分类:
    <select name="category_id">
      <option value="">无分类</option>
      {category_options}
    </select>
  </label>
  <label>备注（非必填）:
    <textarea name="memo" class="sql-textarea" placeholder="输入备注信息..." rows="4" style="min-height:80px;font-family:inherit">{memo_val}</textarea>
  </label>
  <label>结果名称（每行一个，顺序对应 SELECT 返回；不填则自动编号）:
    <textarea name="result_names" class="sql-textarea" placeholder="例如:&#10;汇总指标&#10;按城市分布&#10;商品TOP10" rows="3" style="min-height:60px;font-family:inherit">{_escape(result_names_val)}</textarea>
  </label>
  <div class="form-actions">
    <button type="submit" class="btn btn-primary">保存</button>
    {view_btn}
    {preview_btn}
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
<script>
(function(){{
{_report_form_js_highlight()}
{_report_form_js_formatter()}
{_report_form_js_editor_api()}
}})();
function previewReport(form) {{
    form.target = '_blank';
    form.action = '/report/preview';
    form.submit();
    form.target = '';
    form.action = form.getAttribute('data-action');
}}
</script>
</div>"""


def _render_report_form(conn, report: dict = None, copy_mode: bool = False) -> str:
    """渲染报表编辑/新增/复制表单"""
    is_edit = report is not None and not copy_mode
    is_copy = report is not None and copy_mode
    if is_edit:
        action_url = f"/config/reports/{report['id']}/edit"
        title = "编辑报表"
    elif is_copy:
        action_url = f"/config/reports/{report['id']}/copy"
        title = "复制报表"
    else:
        action_url = "/config/reports/add"
        title = "新增报表"

    name = _escape(report["name"] if report else "")
    sql_query = _escape(report["sql_query"] if report else "")
    default_page_size = str(report["default_page_size"]) if report else "20"
    cur_pool_id = report["pool_id"] if report else ""
    memo_val = _escape(report.get("memo") or "") if report else ""
    result_names_val = report.get("result_names") or "" if report else ""

    if is_copy:
        name = _escape(report["name"] + " (副本)")

    pool_options, no_pool_opt, required_attr = _report_form_pool_options(
        conn, cur_pool_id, is_edit)
    category_options = _report_form_cat_options(
        conn, report.get("category_id") if report else "")

    return _report_form_html(title, action_url, name, sql_query, default_page_size,
                              required_attr, no_pool_opt, pool_options, category_options, memo_val,
                              result_names_val=result_names_val,
                              is_edit=is_edit, report_id=report["id"] if report else None)


def _render_pool_section(conn) -> str:
    """渲染连接池配置列表（含复制、排序）"""
    pools = db.get_all_pools(conn)
    rows = ""
    pool_count = len(pools)
    for i, p in enumerate(pools):
        move_btns = ""
        if pool_count > 1:
            if i > 0:
                move_btns += f'<form method="post" action="/config/pools/{p["id"]}/move-up" style="display:inline">' \
                             f'<button type="submit" class="btn btn-outline btn-sm" title="上移">↑</button></form> '
            if i < pool_count - 1:
                move_btns += f'<form method="post" action="/config/pools/{p["id"]}/move-down" style="display:inline">' \
                             f'<button type="submit" class="btn btn-outline btn-sm" title="下移">↓</button></form> '
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


def _render_user_section(conn) -> str:
    """渲染用户配置列表"""
    users = db.get_all_users(conn)
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


def _render_category_section(conn) -> str:
    """渲染报表分类配置段（分类管理 + 各分类下的报表列表）"""
    cat_reports, unclassified_reports = db.get_reports_by_category(conn)
    all_cats = db.get_all_categories(conn)
    all_reports = db.get_all_reports(conn)
    pools = db.get_all_pools(conn)
    report_count = len(all_reports)

    # 批量操作：连接池选择 + 分类选择
    pool_opts = '<option value="">-- 请选择 --</option>'
    for p in pools:
        pool_opts += f'<option value="{p["id"]}">{_escape(p["name"])}</option>'
    cat_opts = '<option value="">-- 请选择分类 --</option>'
    for c in all_cats:
        prefix = "　" * _get_depth(c, all_cats)
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
                pool = db.get_pool(conn, pool_id)
                if pool:
                    pool_name = pool["name"]
            pool_badge = (
                f'<span class="badge badge-pool">{_escape(pool_name)}</span>'
                if pool_name
                else '<span style="color:#dc2626;font-size:13px">连接池已删除</span>'
            )
            # 调序按钮
            move_btns = ""
            if total > 1:
                if idx > 0:
                    move_btns += f'<form method="post" action="/config/reports/{rpt_id}/move-up" style="display:inline"><button type="submit" class="btn btn-outline btn-sm" title="上移">↑</button></form> '
                if idx < total - 1:
                    move_btns += f'<form method="post" action="/config/reports/{rpt_id}/move-down" style="display:inline"><button type="submit" class="btn btn-outline btn-sm" title="下移">↓</button></form> '
            # 备注截取前 15 个字
            memo_raw = r.get("memo") or ""
            if memo_raw:
                memo_display = _escape(memo_raw[:15])
                if len(memo_raw) > 15:
                    memo_display += "..."
            else:
                memo_display = '<span style="color:#cbd5e1">—</span>'

            rows += f"""<tr>
  <td><input type="checkbox" class="report-checkbox" value="{rpt_id}" onchange="updateBatchCount()"></td>
   <td><strong><a href="/report?id={rpt_id}" target="_blank" rel="noopener" style="color:#4f46e5;text-decoration:none">{_escape(r['name'])}</a></strong></td>
  <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;">
    <code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px;color:#475569">{_escape(r['sql_query'][:80])}{'...' if len(r['sql_query']) > 80 else ''}</code>
  </td>
  <td>{r['default_page_size']}</td>
  <td>{pool_badge}</td>
  <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;color:#64748b;font-size:13px">{memo_display}</td>
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

    # 构建分类区域
    cat_areas = ""

    # 分类列表（树形结构）
    def _render_cat_item(cat, depth=0):
        children = [c for c in all_cats if c.get("parent_id") == cat["id"]]
        has_children = len(children) > 0
        move_btns = ""
        siblings = [c for c in all_cats if c.get("parent_id") == cat.get("parent_id")]
        idx = next((i for i, c in enumerate(siblings) if c["id"] == cat["id"]), -1)
        n = len(siblings)
        if n > 1:
            if idx > 0:
                move_btns += f'<form method="post" action="/config/categories/{cat["id"]}/move-up" style="display:inline">' \
                             f'<button type="submit" class="btn btn-outline btn-sm" title="上移">↑</button></form> '
            if idx < n - 1:
                move_btns += f'<form method="post" action="/config/categories/{cat["id"]}/move-down" style="display:inline">' \
                             f'<button type="submit" class="btn btn-outline btn-sm" title="下移">↓</button></form> '
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

    cat_list_html = ""
    roots = db.get_category_tree(conn)
    def _render_tree(nodes, depth=0):
        html = ""
        for node in nodes:
            html += _render_cat_item(node, depth)
            if node["children"]:
                html += _render_tree(node["children"], depth + 1)
        return html
    cat_list_html = _render_tree(roots)

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

    # 各分类下的报表展示
    tab_html = ""
    for entry in cat_reports:
        reports = entry.get("reports", [])
        if reports:
            rows = _render_report_rows(reports, in_category=True)
            depth = _get_depth(entry, all_cats)
            indent = "　" * depth
            tab_html += f"""<div class="section">
<div class="section-title">
  <span>📊 {indent}{_escape(entry['name'])} <span style="font-weight:400;font-size:14px;color:#94a3b8">({len(reports)} 个报表)</span></span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th style="width:40px"><input type="checkbox" onchange="var section=this.closest('.section');var c=section.querySelectorAll('.report-checkbox');for(var i=0;i<c.length;i++){{c[i].checked=this.checked;}}updateBatchCount()"></th>
  <th>名称</th><th>SQL 查询</th><th>默认分页</th><th>连接池</th><th>备注</th><th>操作</th>
</tr></thead><tbody>
{rows}
</tbody></table>
</div>
</div>"""

    # 未分类报表
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
  <th>名称</th><th>SQL 查询</th><th>默认分页</th><th>连接池</th><th>备注</th><th>操作</th>
</tr></thead><tbody>
{uncat_rows or '<tr><td colspan="7" class="empty-state">暂无未分类报表</td></tr>'}
</tbody></table>
</div>
</div>"""

    return cat_areas + tab_html + uncat_section


def render_overview(conn, flash: str = None) -> str:
    """渲染配置总览页，包含三个配置段"""
    flash_html = ""
    if flash:
        css_cls = " flash-error" if flash.startswith("错误") else " flash-success"
        flash_html = f'<div class="flash{css_cls}">{_escape(flash)}</div>'
    body = _HEADER + flash_html + _render_pool_section(conn) + _render_user_section(conn) + _render_category_section(conn) + _FOOTER
    return body


def render_pool_form_page(conn, pool_id: int = None, flash: str = None, copy_mode: bool = False) -> str:
    """渲染新增/编辑/复制连接池表单页"""
    pool = db.get_pool(conn, pool_id) if pool_id else None
    if pool_id and not pool:
        return render_overview(conn, flash="错误: 连接池不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    return _HEADER + flash_html + _render_pool_form(pool, copy_mode) + _FOOTER


def render_user_form_page(conn, user_id: int = None, flash: str = None) -> str:
    """渲染新增/编辑用户表单页"""
    user = db.get_user_by_id(conn, user_id) if user_id else None
    if user_id and not user:
        return render_overview(conn, flash="错误: 用户不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    return _HEADER + flash_html + _render_user_form(user) + _FOOTER


def render_category_form_page(conn, category_id: int = None, flash: str = None) -> str:
    """渲染新增/编辑分类表单页"""
    cat = db.get_category(conn, category_id) if category_id else None
    if category_id and not cat:
        return render_overview(conn, flash="错误: 分类不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    name = _escape(cat["name"]) if cat else ""
    cur_parent_id = cat["parent_id"] if cat else ""
    is_edit = category_id is not None
    action = f"/config/categories/{category_id}/edit" if is_edit else "/config/categories/add"
    title = "编辑分类" if is_edit else "新增分类"

    # 父分类选择（排除自身及后代）
    parent_opts = '<option value="">无父分类（顶级分类）</option>'
    all_cats = db.get_all_categories(conn)
    if is_edit:
        # 获取所有后代 id，防止循环引用
        descendants = set()
        def _collect_descendants(cid):
            for c in all_cats:
                if c.get("parent_id") == cid and c["id"] not in descendants:
                    descendants.add(c["id"])
                    _collect_descendants(c["id"])
        _collect_descendants(category_id)
    else:
        descendants = set()
    for c in all_cats:
        if c["id"] == category_id:
            continue
        if c["id"] in descendants:
            continue
        sel = ' selected' if cur_parent_id != "" and str(c["id"]) == str(cur_parent_id) else ''
        prefix = "  " * _get_depth(c, all_cats)
        parent_opts += f'<option value="{c["id"]}"{sel}>{prefix}{_escape(c["name"])}</option>'

    form_html = f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action}" class="config-form">
  <label>分类名称: <input type="text" name="name" value="{name}" required></label>
  <label>父分类:
    <select name="parent_id">
      {parent_opts}
    </select>
  </label>
  <div class="form-actions">
    <button type="submit" class="btn btn-primary">保存</button>
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
</div>"""
    return _HEADER + flash_html + form_html + _FOOTER


def _get_depth(cat: dict, all_cats: list[dict]) -> int:
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


def render_report_form_page(conn, report_id: int = None, flash: str = None, copy_mode: bool = False) -> str:
    """渲染新增/编辑/复制报表表单页"""
    report = db.get_report(conn, report_id) if report_id else None
    if report_id and not report:
        return render_overview(conn, flash="错误: 报表不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    return _HEADER + flash_html + _render_report_form(conn, report, copy_mode) + _FOOTER


# ---------------------------------------------------------------------------
# 表单提交处理
# ---------------------------------------------------------------------------


def _parse_form_data(form_body: str) -> dict:
    """解析 URL 编码的表单数据"""
    parsed = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    return {k: v[0] if v else "" for k, v in parsed.items()}


def handle_pool_add(conn, form_body: str) -> tuple[str, str]:
    """
    处理新增连接池表单提交。

    返回 (HTTP 状态码, 响应体或重定向 URL)。
    """
    data = _parse_form_data(form_body)
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"])
        return "302", f"/config?flash=连接池 {data['name']} 已创建 (id={pid})"
    except Exception as e:
        return "200", render_pool_form_page(conn, flash=f"错误: {e}")


def handle_pool_edit(conn, pool_id: int, form_body: str) -> tuple[str, str]:
    """处理编辑连接池表单提交"""
    data = _parse_form_data(form_body)
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return "302", "/config?flash=错误: 连接池不存在"
    # 密码已回填到表单，用户可修改或保留原值
    password = data.get("password") or pool["password"]
    try:
        ok = db.update_pool(conn, pool_id, data["name"], data["host"],
                            int(data["port"]), data["user"], password, data["database"])
        if ok:
            return "302", f"/config?flash=连接池 {data['name']} 已更新"
        return "302", "/config?flash=错误: 更新失败"
    except Exception as e:
        return "200", render_pool_form_page(conn, pool_id, flash=f"错误: {e}")


def handle_pool_copy(conn, pool_id: int, form_body: str) -> tuple[str, str]:
    """处理复制连接池（新增一个同名+副本的连接池）"""
    data = _parse_form_data(form_body)
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"])
        return "302", f"/config?flash=连接池 {data['name']} 已创建（复制自 id={pool_id}）"
    except Exception as e:
        return "200", render_pool_form_page(conn, pool_id, flash=f"错误: {e}", copy_mode=True)


def handle_pool_delete(conn, pool_id: int) -> tuple[str, str]:
    """处理删除连接池"""
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return "302", "/config?flash=错误: 连接池不存在"
    db.delete_pool(conn, pool_id)
    return "302", f"/config?flash=连接池 {pool['name']} 已删除"


def handle_user_add(conn, form_body: str) -> tuple[str, str]:
    """处理新增用户表单提交"""
    data = _parse_form_data(form_body)
    import auth
    try:
        pw_hash = auth.hash_password(data["password"])
        uid = db.add_user(conn, data["username"], pw_hash)
        return "302", f"/config?flash=用户 {data['username']} 已创建 (id={uid})"
    except Exception as e:
        return "200", render_user_form_page(conn, flash=f"错误: {e}")


def handle_user_edit(conn, user_id: int, form_body: str) -> tuple[str, str]:
    """处理编辑用户表单提交"""
    import auth
    data = _parse_form_data(form_body)
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return "302", "/config?flash=错误: 用户不存在"
    # 如果密码为空，保留原密码
    password_hash = auth.hash_password(data["password"]) if data.get("password") else target["password_hash"]
    ok = db.update_user(conn, user_id, data["username"], password_hash)
    if ok:
        return "302", f"/config?flash=用户 {data['username']} 已更新"
    return "302", "/config?flash=错误: 更新失败"


def handle_user_delete(conn, user_id: int) -> tuple[str, str]:
    """处理删除用户"""
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return "302", "/config?flash=错误: 用户不存在"
    db.delete_user(conn, user_id)
    return "302", f"/config?flash=用户 {target['username']} 已删除"


def handle_report_add(conn, form_body: str) -> tuple[str, str]:
    """处理新增报表表单提交"""
    data = _parse_form_data(form_body)
    try:
        pool_id = int(data["pool_id"]) if data.get("pool_id") else None
        category_id = int(data["category_id"]) if data.get("category_id") else None
        memo = data.get("memo") or None
        result_names = data.get("result_names") or ""
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), pool_id, category_id, memo,
                            result_names=result_names)
        return "302", f"/config?flash=报表 {data['name']} 已创建 (id={rid})"
    except Exception as e:
        return "200", render_report_form_page(conn, flash=f"错误: {e}")


def handle_report_edit(conn, report_id: int, form_body: str) -> tuple[str, str]:
    """处理编辑报表表单提交"""
    data = _parse_form_data(form_body)
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return "302", "/config?flash=错误: 报表不存在"
    try:
        pool_id = int(data["pool_id"]) if data.get("pool_id") else None
        category_id = int(data["category_id"]) if data.get("category_id") else None
        memo = data.get("memo") or None
        result_names = data.get("result_names") or ""
        ok = db.update_report(conn, report_id, data["name"], data["sql_query"],
                              int(data["default_page_size"]), pool_id, category_id, memo,
                              result_names=result_names)
        if ok:
            return "302", f"/config?flash=报表 {data['name']} 已更新"
        return "302", "/config?flash=错误: 更新失败"
    except Exception as e:
        return "200", render_report_form_page(conn, report_id, flash=f"错误: {e}")


def handle_report_copy(conn, report_id: int, form_body: str) -> tuple[str, str]:
    """处理复制报表（新增一个同名+副本的报表）"""
    data = _parse_form_data(form_body)
    try:
        pool_id = int(data["pool_id"]) if data.get("pool_id") else None
        category_id = int(data["category_id"]) if data.get("category_id") else None
        memo = data.get("memo") or None
        result_names = data.get("result_names") or ""
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), pool_id, category_id, memo,
                            result_names=result_names)
        return "302", f"/config?flash=报表 {data['name']} 已创建（复制自 id={report_id}）"
    except Exception as e:
        return "200", render_report_form_page(conn, report_id, flash=f"错误: {e}", copy_mode=True)


def handle_report_delete(conn, report_id: int) -> tuple[str, str]:
    """处理删除报表"""
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return "302", "/config?flash=错误: 报表不存在"
    db.delete_report(conn, report_id)
    return "302", f"/config?flash=报表 {rpt['name']} 已删除"


def handle_report_move_category(conn, report_id: int, form_body: str) -> tuple[str, str]:
    """处理报表移动到指定分类"""
    data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    cat_str = data.get("category_id", [None])[0]
    category_id = int(cat_str) if cat_str else None
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return "302", "/config?flash=错误: 报表不存在"
    db.move_report_to_category(conn, report_id, category_id)
    cat_name = "未分类"
    if category_id is not None:
        cat = db.get_category(conn, category_id)
        if cat:
            cat_name = cat["name"]
    return "302", f"/config?flash=报表 {rpt['name']} 已移至「{cat_name}」"


def handle_category_add(conn, form_body: str) -> tuple[str, str]:
    """处理新增分类"""
    data = _parse_form_data(form_body)
    try:
        parent_id = int(data["parent_id"]) if data.get("parent_id") else None
        cid = db.add_category(conn, data["name"], parent_id)
        return "302", f"/config?flash=分类 {data['name']} 已创建"
    except Exception as e:
        return "200", render_category_form_page(conn, flash=f"错误: {e}")


def handle_category_edit(conn, category_id: int, form_body: str) -> tuple[str, str]:
    """处理编辑分类"""
    data = _parse_form_data(form_body)
    cat = db.get_category(conn, category_id)
    if not cat:
        return "302", "/config?flash=错误: 分类不存在"
    try:
        parent_id = int(data["parent_id"]) if data.get("parent_id") else None
        db.update_category(conn, category_id, data["name"], parent_id)
        return "302", f"/config?flash=分类 {data['name']} 已更新"
    except Exception as e:
        return "200", render_category_form_page(conn, category_id, flash=f"错误: {e}")


def handle_category_delete(conn, category_id: int) -> tuple[str, str]:
    """处理删除分类"""
    cat = db.get_category(conn, category_id)
    if not cat:
        return "302", "/config?flash=错误: 分类不存在"
    db.delete_category(conn, category_id)
    return "302", f"/config?flash=分类 {cat['name']} 已删除"


def handle_batch_set_category(conn, form_body: str) -> tuple[str, str]:
    """处理报表批量设置分类"""
    data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    report_ids = [int(v) for v in data.get("report_ids", []) if v]
    cat_str = data.get("category_id", [None])[0]
    category_id = int(cat_str) if cat_str else None
    if not report_ids:
        return "302", "/config?flash=错误: 未选择任何报表"
    affected = db.batch_set_report_category(conn, report_ids, category_id)
    cat_name = "未分类"
    if category_id is not None:
        cat = db.get_category(conn, category_id)
        if cat:
            cat_name = cat["name"]
    return "302", f"/config?flash=已为 {affected} 个报表设置分类为「{cat_name}」"


def handle_batch_pool(conn, form_body: str) -> tuple[str, str]:
    """处理报表批量修改连接池"""
    data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    report_ids = [int(v) for v in data.get("report_ids", []) if v]
    pool_id_str = data.get("pool_id", [None])[0]
    pool_id = int(pool_id_str) if pool_id_str else None
    if not report_ids:
        return "302", "/config?flash=错误: 未选择报表"
    n = db.batch_update_report_pool(conn, report_ids, pool_id)
    pool_label = pool_id if pool_id else "无"
    return "302", f"/config?flash=已更新 {n} 个报表的连接池为 (id={pool_label})"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def handle_request(conn, method: str, path: str, query: str,
                   form_body: str = None) -> tuple[str, str, dict]:
    """
    配置页面请求入口。

    参数:
      conn     — SQLite 连接
      method   — HTTP 方法 (GET/POST)
      path     — URL 路径
      query    — URL 查询字符串
      form_body — POST 请求体

    返回:
      (HTTP 状态码, 响应体, 额外响应头 dict)
    """
    route = parse_config_path(path)

    # 从 query string 提取 flash 消息
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)
    flash = qs.get("flash", [None])[0]

    # ---- 总览 ----
    if route["action"] == "overview":
        return "200", render_overview(conn, flash), {}

    # ---- 表单页面 (GET) ----
    if method == "GET":
        if route["action"] == "add":
            if route["section"] == "pools":
                return "200", render_pool_form_page(conn), {}
            elif route["section"] == "users":
                return "200", render_user_form_page(conn), {}
            elif route["section"] == "reports":
                return "200", render_report_form_page(conn), {}
            elif route["section"] == "categories":
                return "200", render_category_form_page(conn), {}
        elif route["action"] == "edit" and route["id"]:
            if route["section"] == "pools":
                return "200", render_pool_form_page(conn, route["id"]), {}
            elif route["section"] == "users":
                return "200", render_user_form_page(conn, route["id"]), {}
            elif route["section"] == "reports":
                return "200", render_report_form_page(conn, route["id"]), {}
            elif route["section"] == "categories":
                return "200", render_category_form_page(conn, route["id"]), {}
        elif route["action"] == "copy" and route["id"]:
            if route["section"] == "pools":
                return "200", render_pool_form_page(conn, route["id"], copy_mode=True), {}
            elif route["section"] == "reports":
                return "200", render_report_form_page(conn, route["id"], copy_mode=True), {}

    # ---- POST 处理 ----
    if method == "POST":
        if route["section"] == "pools":
            if route["action"] == "add":
                code, result = handle_pool_add(conn, form_body or "")
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_pool_edit(conn, route["id"], form_body or "")
            elif route["action"] == "copy" and route["id"]:
                code, result = handle_pool_copy(conn, route["id"], form_body or "")
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_pool_delete(conn, route["id"])
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_pool(conn, route["id"], direction)
                return "302", "/config", {}
            else:
                return "302", "/config", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "users":
            if route["action"] == "add":
                code, result = handle_user_add(conn, form_body or "")
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_user_edit(conn, route["id"], form_body or "")
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_user_delete(conn, route["id"])
            else:
                return "302", "/config", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "reports":
            if route["action"] == "add":
                code, result = handle_report_add(conn, form_body or "")
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_report_edit(conn, route["id"], form_body or "")
            elif route["action"] == "copy" and route["id"]:
                code, result = handle_report_copy(conn, route["id"], form_body or "")
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_report_delete(conn, route["id"])
            elif route["action"] == "batch-pool":
                code, result = handle_batch_pool(conn, form_body or "")
                return _redirect_or_render(code, result)
            elif route["action"] == "batch-set-category":
                code, result = handle_batch_set_category(conn, form_body or "")
                return _redirect_or_render(code, result)
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_report(conn, route["id"], direction)
                return "302", "/config", {}
            else:
                return "302", "/config", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "categories":
            if route["action"] == "add":
                code, result = handle_category_add(conn, form_body or "")
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_category_edit(conn, route["id"], form_body or "")
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_category_delete(conn, route["id"])
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_category(conn, route["id"], direction)
                return "302", "/config", {}
            else:
                return "302", "/config", {}
            return _redirect_or_render(code, result)

    return "302", "/config", {}


def _redirect_or_render(code: str, result: str) -> tuple[str, str, dict]:
    """
    将处理器返回的 (状态码, 结果) 转换为标准返回格式。

    如果是 302 重定向，结果即为 Location；否则为 HTML 响应体。
    对 Location 中的 query 参数进行 URL 编码，确保非 ASCII 字符（如中文）正确传输。
    """
    if code == "302" and result.startswith("/"):
        # URL 编码 query 参数（flash 消息可能包含中文）
        if "?" in result:
            path, qs = result.split("?", 1)
            params = urllib.parse.parse_qs(qs, keep_blank_values=True)
            encoded_qs = urllib.parse.urlencode(params, doseq=True)
            encoded_url = f"{path}?{encoded_qs}"
        else:
            encoded_url = result
        return "302", encoded_url, {"Location": encoded_url}
    return code, result, {}
