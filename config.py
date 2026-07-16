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
import auth
import redis_cache
import html as html_mod
# 从 render 模块导入纯 HTML 渲染函数（无 DB 调用）
from render import (
    build_pool_form_html,
    build_user_form_html,
    build_category_opts_html,
    build_pool_section_html,
    build_user_section_html,
    build_category_section_html,
    render_page_header,
    render_page_footer,
    _SQL_HIGHLIGHT_JS,
    _SQL_FORMATTER_JS,
)


# ---------------------------------------------------------------------------
# 路由解析
# ---------------------------------------------------------------------------

# 匹配 /config/pools/add, /config/pools/{id}/edit, /config/pools/{id}/copy,
# /config/pools/{id}/move-up, /config/pools/{id}/move-down, /config/reports/batch-pool
_PATH_PATTERN = re.compile(
    r"^/config/(pools|users|reports|categories)"
    r"(?:/(add|batch-pool|batch-set-category|batch-cache)|/(\d+)/(edit|delete|copy|move-up|move-down))?$"
)


def parse_config_path(path: str) -> dict:
    """
    解析配置页 URL 路径，返回动作参数字典。

    返回格式:
      {"section": "pools|users|reports", "action": "list|add|batch-pool|batch-set-category|batch-cache|edit|delete|copy|move-up|move-down",
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

_CONFIG_EXTRA_CSS = """
  .section-title {
    font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 16px;
    padding-bottom: 12px; border-bottom: 2px solid #e2e8f0;
    display: flex; align-items: center; justify-content: space-between;
  }
  .section-title .actions { display: flex; gap: 8px; }
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
  .sql-hl-keyword  { color: #7c3aed; font-weight: 600; }
  .sql-hl-function { color: #2563eb; }
  .sql-hl-number   { color: #059669; }
  .sql-hl-string   { color: #b91c1c; }
  .sql-hl-comment  { color: #94a3b8; font-style: italic; }
  .section + .section { margin-top: 8px; }
  .ops-cell { white-space: nowrap; }
  .ops-cell form { display: inline; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }
  .badge-pool { background: #eef2ff; color: #4f46e5; }
"""


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
    return build_pool_form_html(pool, copy_mode)


def _render_user_form(user: dict = None) -> str:
    """渲染用户编辑/新增表单"""
    return build_user_form_html(user)


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
    return build_category_opts_html(nodes, depth, cur_cat_id)


def _report_form_cat_options(conn, cur_cat_id):
    """生成报表分类选择列表 HTML"""
    cat_tree = db.get_category_tree(conn)
    return _render_cat_opts(cat_tree, 0, cur_cat_id)


def _report_form_js_highlight():
    """返回 SQL 语法高亮 JS（h + highlight 函数，统一引用 render.py 共享常量）"""
    return _SQL_HIGHLIGHT_JS


def _report_form_js_formatter():
    """返回 SQL 格式化 JS（fmt 函数，统一引用 render.py 共享常量）"""
    return _SQL_FORMATTER_JS


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
                       is_edit=False, report_id=None,
                       prefer_cache=1, cache_ttl_hours=0):
    """构建报表表单完整 HTML（含 SQL 编辑器 JS + 查看/预览按钮）"""
    view_btn = (f'<a href="/report?id={report_id}" class="btn btn-outline btn-sm" target="_blank" rel="noopener">查看</a>'
                if is_edit and report_id else "")
    preview_btn = (f'<button type="button" class="btn btn-outline btn-sm" onclick="previewReport(this.form)">预览</button>'
                   if is_edit and report_id else "")
    hidden_id = f'<input type="hidden" name="id" value="{report_id}">' if is_edit and report_id else ""
    cache_checked = ' checked' if prefer_cache else ''
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
  <label style="margin-top:16px;display:flex;align-items:center;gap:8px;font-weight:400">
    <input type="hidden" name="prefer_cache" value="0">
    <input type="checkbox" name="prefer_cache" value="1"{cache_checked}>
    <span style="font-weight:600">启用 Redis 缓存</span>
    <span style="color:#94a3b8;font-weight:400;font-size:13px">（优先使用缓存数据加速访问）</span>
  </label>
  <label>缓存 TTL（小时）:
    <input type="number" name="cache_ttl_hours" value="{cache_ttl_hours}" min="0" step="1"
           style="width:120px">
    <span style="color:#94a3b8;font-weight:400;font-size:13px;margin-left:8px">0 = 永不过期</span>
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

    prefer_cache = int(report.get("prefer_cache", 1)) if report else 1
    cache_ttl_hours = int(report.get("cache_ttl_hours", 0)) if report else 0

    return _report_form_html(title, action_url, name, sql_query, default_page_size,
                              required_attr, no_pool_opt, pool_options, category_options, memo_val,
                              result_names_val=result_names_val,
                              is_edit=is_edit, report_id=report["id"] if report else None,
                              prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours)


def _render_pool_section(conn) -> str:
    """渲染连接池配置列表（含复制、排序）"""
    pools = db.get_all_pools(conn)
    return build_pool_section_html(pools)


def _render_user_section(conn) -> str:
    """渲染用户配置列表"""
    users = db.get_all_users(conn)
    return build_user_section_html(users)


def _render_category_section(conn) -> str:
    """渲染报表分类配置段（分类管理 + 各分类下的报表列表）"""
    cat_reports, unclassified_reports = db.get_reports_by_category(conn)
    all_cats = db.get_all_categories(conn)
    all_reports = db.get_all_reports(conn)
    pools = db.get_all_pools(conn)
    cat_tree = db.get_category_tree(conn)
    return build_category_section_html(cat_reports, unclassified_reports, all_cats,
                                       all_reports, pools, cat_tree)


def render_overview(conn, flash: str = None) -> str:
    """渲染配置总览页，包含三个配置段"""
    flash_html = ""
    if flash:
        css_cls = " flash-error" if flash.startswith("错误") else " flash-success"
        flash_html = f'<div class="flash{css_cls}">{_escape(flash)}</div>'
    body = (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_pool_section(conn) + _render_user_section(conn)
            + _render_category_section(conn) + render_page_footer())
    return body


def render_pool_form_page(conn, pool_id: int = None, flash: str = None, copy_mode: bool = False) -> str:
    """渲染新增/编辑/复制连接池表单页"""
    pool = db.get_pool(conn, pool_id) if pool_id else None
    if pool_id and not pool:
        return render_overview(conn, flash="错误: 连接池不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_pool_form(pool, copy_mode) + render_page_footer())


def render_user_form_page(conn, user_id: int = None, flash: str = None) -> str:
    """渲染新增/编辑用户表单页"""
    user = db.get_user_by_id(conn, user_id) if user_id else None
    if user_id and not user:
        return render_overview(conn, flash="错误: 用户不存在")
    flash_html = f'<div class="flash flash-error">{_escape(flash)}</div>' if flash else ""
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_user_form(user) + render_page_footer())


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
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + form_html + render_page_footer())


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
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_report_form(conn, report, copy_mode) + render_page_footer())


# ---------------------------------------------------------------------------
# 表单提交处理
# ---------------------------------------------------------------------------


def _parse_form_data(form_body: str) -> dict:
    """解析 URL 编码的表单数据"""
    parsed = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}


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
    try:
        pw_hash = auth.hash_password(data["password"])
        uid = db.add_user(conn, data["username"], pw_hash)
        return "302", f"/config?flash=用户 {data['username']} 已创建 (id={uid})"
    except Exception as e:
        return "200", render_user_form_page(conn, flash=f"错误: {e}")


def handle_user_edit(conn, user_id: int, form_body: str) -> tuple[str, str]:
    """处理编辑用户表单提交"""
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
        prefer_cache = int(data.get("prefer_cache", 1) or 0)
        cache_ttl_hours = int(data.get("cache_ttl_hours", 0) or 0)
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), pool_id, category_id, memo,
                            result_names=result_names,
                            prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours)
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
        prefer_cache = int(data.get("prefer_cache", 1) or 0)
        cache_ttl_hours = int(data.get("cache_ttl_hours", 0) or 0)
        ok = db.update_report(conn, report_id, data["name"], data["sql_query"],
                              int(data["default_page_size"]), pool_id, category_id, memo,
                              result_names=result_names,
                              prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours)
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
        prefer_cache = int(data.get("prefer_cache", 1) or 0)
        cache_ttl_hours = int(data.get("cache_ttl_hours", 0) or 0)
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), pool_id, category_id, memo,
                            result_names=result_names,
                            prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours)
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


def handle_batch_cache(conn, form_body: str) -> tuple[str, str]:
    """处理报表批量更新缓存配置"""
    data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    report_ids = [int(v) for v in data.get("report_ids", []) if v]
    if not report_ids:
        return "302", "/config?flash=错误: 未选择报表"

    cache_switch = data.get("cache_switch", [""])[0]
    modify_ttl = data.get("modify_ttl", [""])[0] == "1"

    prefer_cache = None
    if cache_switch == "1":
        prefer_cache = 1
    elif cache_switch == "0":
        prefer_cache = 0

    cache_ttl_hours = None
    if modify_ttl:
        ttl_val = data.get("cache_ttl_hours", ["0"])[0]
        cache_ttl_hours = int(ttl_val) if ttl_val else 0

    affected = db.batch_update_report_cache(conn, report_ids, prefer_cache, cache_ttl_hours)

    redis_updated = 0
    redis_failed = 0
    try:
        mgr = redis_cache.get_redis_manager()
        if mgr and mgr.available:
            prefix = mgr._config.get("key_prefix", "sr")
            for rid in report_ids:
                try:
                    keys = mgr.scan_snapshots(prefix, rid)
                    if cache_switch == "0":
                        for k in keys:
                            mgr.delete_snapshot(k)
                        redis_updated += 1
                    elif modify_ttl and cache_ttl_hours is not None:
                        for k in keys:
                            mgr.set_expiration(k, cache_ttl_hours)
                        redis_updated += 1
                except Exception:
                    redis_failed += 1
    except Exception:
        pass

    parts = [f"已更新 {affected} 个报表的缓存配置"]
    if redis_updated > 0:
        parts.append(f"Redis 成功 {redis_updated}")
    if redis_failed > 0:
        parts.append(f"Redis 失败 {redis_failed}")
    return "302", f"/config?flash={'，'.join(parts)}"


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
            elif route["action"] == "batch-cache":
                code, result = handle_batch_cache(conn, form_body or "")
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
