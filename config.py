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
import json
import logging
import urllib.parse
import db
import config_db
import auth
import redis_cache
import static_cache
import api_handler
import app_config
import html as html_mod
from json_template import ALL_KEYS, SINGLE_KEYS, validate_template
from query_executor import sql_contains_write
# 从 render 模块导入纯 HTML 渲染函数（无 DB 调用）
from render import (
    build_pool_form_html,
    build_user_form_html,
    build_category_opts_html,
    build_pool_section_html,
    build_user_section_html,
    build_category_section_html,
    build_category_manage_section_html,
    render_page_header,
    render_page_footer,
    build_flash_html,
    _SQL_HIGHLIGHT_JS,
    _SQL_FORMATTER_JS,
    build_api_endpoints_list_html,
    build_api_endpoint_form_html,
    build_api_endpoint_preview_help_html,
    _build_desc_summary_html,
    _WARN_BOX_STYLE,
    _MD_CSS,
)
from report import parse_result_names
import markdown_render


# ---------------------------------------------------------------------------
# 路由解析
# ---------------------------------------------------------------------------

# 匹配 /config/pools/add, /config/pools/{id}/edit, /config/pools/{id}/copy,
# /config/pools/{id}/move-up, /config/pools/{id}/move-down, /config/reports/batch-pool,
# /config/reports/{id}/move-category
# API 端点子动作含 api_keys（API Key 管理 POST 端点）
_PATH_PATTERN = re.compile(
    r"^/config/(pools|users|reports|categories)"
    r"(?:/(add|batch-pool|batch-set-category|batch-cache|batch-delete|memo-preview)"
    r"|/(\d+)/(edit|delete|copy|move-category|move-up|move-down)"
    r"|/(\d+)/api_endpoints/(new|(\d+)/(edit|delete|preview|api_keys)))?$"
)


def parse_config_path(path: str) -> dict:
    """
    解析配置页 URL 路径，返回动作参数字典。

    返回格式:
      {"section": "pools|users|reports|categories",
       "action": "list|add|batch-pool|batch-set-category|batch-cache|batch-delete|edit|delete|copy|move-up|move-down|api_new|api_edit|api_delete|api_preview|api_keys",
       "id": int|None,
       "report_id": int|None,
       "endpoint_id": int|None}
    """
    match = _PATH_PATTERN.match(path)
    if not match:
        # /config 或 /config/ 视为总览
        if path in ("/config", "/config/"):
            return {"section": None, "action": "overview", "id": None,
                    "report_id": None, "endpoint_id": None}
        # API 接口说明 Markdown 预览（无报表 id，独立前缀；api-desc-markdown T4）
        if path == "/config/api-endpoints/description-preview":
            return {"section": "api-endpoints", "action": "description-preview",
                    "id": None, "report_id": None, "endpoint_id": None}
        return {"section": None, "action": None, "id": None,
                "report_id": None, "endpoint_id": None}

    section = match.group(1)
    # group(2) 匹配 add / batch-pool（无 id）
    simple_action = match.group(2)
    # group(3) 匹配 id, group(4) 匹配 edit/delete/copy/move-up/move-down
    obj_id = int(match.group(3)) if match.group(3) else None
    obj_action = match.group(4)
    # group(5) 匹配 api_endpoints 场景下的 report_id
    api_report_id = int(match.group(5)) if match.group(5) else None
    # group(6) 匹配 "new"
    api_new = match.group(6)
    # group(7) 匹配 api endpoint 的 id
    api_endpoint_id = int(match.group(7)) if match.group(7) else None
    # group(8) 匹配 edit/delete
    api_sub_action = match.group(8)

    if api_report_id:
        if api_new == "new":
            return {"section": section, "action": "api_new",
                    "id": api_report_id, "report_id": api_report_id,
                    "endpoint_id": None}
        if api_sub_action == "edit" and api_endpoint_id:
            return {"section": section, "action": "api_edit",
                    "id": api_report_id, "report_id": api_report_id,
                    "endpoint_id": api_endpoint_id}
        if api_sub_action == "delete" and api_endpoint_id:
            return {"section": section, "action": "api_delete",
                    "id": api_report_id, "report_id": api_report_id,
                    "endpoint_id": api_endpoint_id}
        if api_sub_action == "preview" and api_endpoint_id:
            return {"section": section, "action": "api_preview",
                    "id": api_report_id, "report_id": api_report_id,
                    "endpoint_id": api_endpoint_id}
        if api_sub_action == "api_keys" and api_endpoint_id:
            return {"section": section, "action": "api_keys",
                    "id": api_report_id, "report_id": api_report_id,
                    "endpoint_id": api_endpoint_id}
        return {"section": section, "action": None, "id": None,
                "report_id": None, "endpoint_id": None}

    if obj_action:
        return {"section": section, "action": obj_action, "id": obj_id,
                "report_id": None, "endpoint_id": None}
    if simple_action:
        return {"section": section, "action": simple_action, "id": None,
                "report_id": None, "endpoint_id": None}
    return {"section": section, "action": "add", "id": None,
            "report_id": None, "endpoint_id": None}


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
  form.config-form { max-width: 1200px; }
  @media (min-width: 1100px) {
    form.config-form {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-auto-flow: dense;
      column-gap: 32px;
      row-gap: 16px;
    }
    form.config-form label { margin-top: 0; }
    form.config-form .span-full { grid-column: 1 / -1; }
  }
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
  .memo-preview {
    display: none; margin-top: 8px; padding: 12px 14px;
    border: 1px dashed #cbd5e1; border-radius: 8px; background: #fff;
    font-size: 14px; line-height: 1.7;
  }
  .memo-preview.show { display: block; }
  /* .memo-preview 内 markdown 排版（pre/code/列表/表格等）统一由 .md-body
     （_MD_CSS，追加在 _CONFIG_MD_EXTRA_CSS 末尾）负责，避免双实现漂移 */
  .sql-toolbar { margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap; }
  .section + .section { margin-top: 8px; }
  .ops-cell { white-space: nowrap; }
  .ops-cell form { display: inline; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }
  .badge-pool { background: #eef2ff; color: #4f46e5; }
  /* 分类树引导线（文件树风格）：等宽字体保证 ├─/└─/│ 逐层对齐 */
  .cat-tree-item {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-bottom: 1px solid #f1f5f9;
    transition: background 0.15s;
  }
  .cat-tree-item:hover { background: #f8fafc; }
  .cat-tree-item:last-child { border-bottom: none; }
  .tree-guide {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px; color: #a5b4fc; white-space: pre; user-select: none;
  }
"""

# 报表表单页等含 Markdown 渲染能力的页面：基础 config CSS + 代码高亮 CSS
# + Markdown 排版 CSS（_MD_CSS 必须在 _CONFIG_EXTRA_CSS 之后，保证列表缩进等规则生效）
_CONFIG_MD_EXTRA_CSS = (_CONFIG_EXTRA_CSS + markdown_render.codehilite_css()
                        + _MD_CSS)


def _escape(text: str) -> str:
    """HTML 转义"""
    return html_mod.escape(str(text) if text is not None else "")


def _link_btn(url: str, label: str, cls: str = "btn btn-outline btn-sm") -> str:
    """生成链接按钮"""
    return f'<a href="{_escape(url)}" class="{cls}">{_escape(label)}</a>'


# ---------------------------------------------------------------------------
# 配置页渲染
# ---------------------------------------------------------------------------


def _render_pool_form(pool: dict = None, copy_mode: bool = False, is_edit: bool = None,
                      prefill_copy_suffix: bool = True) -> str:
    """渲染连接池编辑/新增/复制表单"""
    return build_pool_form_html(pool, copy_mode, is_edit=is_edit,
                                prefill_copy_suffix=prefill_copy_suffix)


def _render_user_form(user: dict = None, is_edit: bool = None) -> str:
    """渲染用户编辑/新增表单"""
    return build_user_form_html(user, is_edit=is_edit)


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
                       prefer_cache=1, cache_ttl_hours=0,
                       allow_write=0, sql_has_write=False,
                       allow_all_output=0, max_rows=100000):
    """构建报表表单完整 HTML（含 SQL 编辑器 JS + 查看/预览按钮）。

    allow_write: 「允许执行写操作」当前值（存量 1、新建 0）。
    sql_has_write: SQL 是否含写语句。含写时显示开关 checkbox 与警示；
                   否则仅渲染隐藏 allow_write=0（保底提交，维持新建默认 0）。
    allow_all_output: 「允许全部输出」当前值（存量 1、新建 0）。
    max_rows: 全量输出关闭时的截断行数上限（默认 100000，仅关闭全量输出时生效）。
    """
    view_btn = (f'<a href="/report?id={report_id}" class="btn btn-outline btn-sm" target="_blank" rel="noopener">查看</a>'
                if is_edit and report_id else "")
    # PH-05：预览按钮对新建/复制/编辑表单均可用（无 id 时 POST sql_query+pool_id 构造预览）
    preview_btn = ('<button type="button" class="btn btn-outline btn-sm" onclick="previewReport(this.form)">预览</button>'
                   if not is_edit or report_id else "")
    hidden_id = f'<input type="hidden" name="id" value="{report_id}">' if is_edit and report_id else ""
    cache_checked = ' checked' if prefer_cache else ''
    if sql_has_write:
        aw_checked = ' checked' if allow_write else ''
        allow_write_html = (f'<label class="span-full" style="display:flex;align-items:center;gap:8px;font-weight:400">'
                            f'<input type="hidden" name="allow_write" value="0">'
                            f'<input type="checkbox" name="allow_write" value="1"{aw_checked}>'
                            f'<span style="font-weight:600">允许执行写操作</span>'
                            f'<span style="color:#94a3b8;font-weight:400;font-size:13px">（SQL 含写语句；未开启时将拒绝执行）</span>'
                            f'</label>')
        if not allow_write:
            allow_write_html += ('<div class="flash-warn span-full" style="'
                                 + _WARN_BOX_STYLE + '">'
                                 '⚠️ 该 SQL 包含写操作语句，未开启时将拒绝执行</div>')
    else:
        allow_write_html = '<input type="hidden" name="allow_write" value="0">'
    # PH-07 全量输出护栏：checkbox + max_rows 输入（hidden 0 保底；开启时保存前 confirm）
    aao_checked = ' checked' if allow_all_output else ''
    if allow_all_output:
        aao_confirm = ' onsubmit="return confirm(\'确定开启全部输出？当查询结果超过限制行数时将不截断，可能占用大量内存与网络带宽。\')"'
    else:
        aao_confirm = ''
    allow_all_output_html = (
        f'<label style="display:flex;align-items:center;gap:8px;font-weight:400">'
        f'<input type="hidden" name="allow_all_output" value="0">'
        f'<input type="checkbox" name="allow_all_output" value="1"{aao_checked}>'
        f'<span style="font-weight:600">允许全部输出</span>'
        f'<span style="color:#94a3b8;font-weight:400;font-size:13px">（关闭时查询结果超过限制行数将被截断，仅显示前 N 行）</span>'
        f'</label>'
        f'<label>全量输出截断上限（行）:'
        f'<input type="number" name="max_rows" value="{max_rows}" min="1" step="1" style="width:140px">'
        f'<span style="color:#94a3b8;font-weight:400;font-size:13px;margin-left:8px">仅关闭「允许全部输出」时生效</span>'
        f'</label>')
    return f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form" data-action="{action_url}"{aao_confirm}>
  {hidden_id}
  <label>报表名称: <input type="text" name="name" value="{name}" required></label>
  <label class="span-full">SQL 查询语句:
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
  <label class="span-full">备注（非必填）:
    <textarea name="memo" class="sql-textarea" placeholder="输入备注信息... 支持 Markdown（标题/列表/代码块/```mermaid 流程图）" rows="4" style="min-height:80px;font-family:inherit">{memo_val}</textarea>
    <div class="memo-preview md-body" id="memo-preview"></div>
    <div class="sql-toolbar">
      <button type="button" class="btn btn-outline btn-sm" onclick="toggleMemoPreview(this)">预览备注</button>
    </div>
  </label>
  <label class="span-full">结果名称（每行一个，顺序对应 SELECT 返回；不填则自动编号）:
    <textarea name="result_names" class="sql-textarea" placeholder="例如:&#10;汇总指标&#10;按城市分布&#10;商品TOP10" rows="3" style="min-height:60px;font-family:inherit">{_escape(result_names_val)}</textarea>
  </label>
  <label style="display:flex;align-items:center;gap:8px;font-weight:400">
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
  {allow_write_html}
  {allow_all_output_html}
  <div class="form-actions span-full">
    <button type="submit" name="action" value="save" class="btn btn-primary">保存</button>
    <button type="submit" name="action" value="save_close" class="btn btn-outline">保存返回上级</button>
    {view_btn}
    {preview_btn}
    <a href="/config/reports" class="cancel">取消</a>
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
var _memoPreviewSeq = 0;
function renderPreviewMermaid() {{
    var nodes = document.querySelectorAll('#memo-preview .mermaid');
    if (!nodes.length) return;
    if (window.mermaid) {{
        mermaid.run({{ nodes: nodes }});
        return;
    }}
    var s = document.createElement('script');
    s.src = '{markdown_render.MERMAID_JS_URL}';
    s.onload = function() {{
        mermaid.initialize({{ startOnLoad: false, securityLevel: 'strict' }});
        mermaid.run({{ nodes: nodes }});
    }};
    document.head.appendChild(s);
}}
function refreshMemoPreview(btn) {{
    var prev = document.getElementById('memo-preview');
    var ta = document.querySelector('textarea[name="memo"]');
    if (!prev || !ta) return;
    var seq = ++_memoPreviewSeq;
    var body = new URLSearchParams();
    body.append('memo', ta.value);
    fetch('/config/reports/memo-preview', {{ method: 'POST', body: body }})
      .then(function(r) {{ return r.text(); }})
      .then(function(html) {{
        if (seq !== _memoPreviewSeq) return;
        prev.innerHTML = html;
        renderPreviewMermaid();
        if (btn && btn.textContent === '预览中...') btn.textContent = '隐藏预览';
      }})
      .catch(function() {{
        if (seq !== _memoPreviewSeq) return;
        prev.textContent = '预览失败，请稍后重试';
        if (btn && btn.textContent === '预览中...') btn.textContent = '隐藏预览';
      }});
}}
function scheduleMemoPreview() {{
    var prev = document.getElementById('memo-preview');
    if (!prev || !prev.classList.contains('show')) return;
    if (window._memoPreviewTimer) clearTimeout(window._memoPreviewTimer);
    window._memoPreviewTimer = setTimeout(function() {{ refreshMemoPreview(); }}, 300);
}}
function toggleMemoPreview(btn) {{
    var prev = document.getElementById('memo-preview');
    var ta = document.querySelector('textarea[name="memo"]');
    if (!prev || !ta) return;
    var show = !prev.classList.contains('show');
    if (!show) {{
        prev.classList.remove('show');
        btn.textContent = '预览备注';
        return;
    }}
    prev.classList.add('show');
    btn.textContent = '预览中...';
    if (!ta.dataset.memoPreviewBound) {{
        ta.dataset.memoPreviewBound = '1';
        ta.addEventListener('input', scheduleMemoPreview);
    }}
    refreshMemoPreview(btn);
}}
</script>
</div>"""


def _render_report_form(conn, report: dict = None, copy_mode: bool = False, is_edit: bool = None,
                        prefill_copy_suffix: bool = True) -> str:
    """渲染报表编辑/新增/复制表单"""
    if is_edit is None:
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

    if is_copy and prefill_copy_suffix:
        name = _escape(report["name"] + " (副本)")

    pool_options, no_pool_opt, required_attr = _report_form_pool_options(
        conn, cur_pool_id, is_edit)
    category_options = _report_form_cat_options(
        conn, report.get("category_id") if report else "")

    prefer_cache = _tolerant_int(report.get("prefer_cache"), 1) if report else 1
    # 新建报表默认 TTL 1 小时（避免永不过期导致长期看到过期数据）；编辑/复制沿用原值
    cache_ttl_hours = _tolerant_int(report.get("cache_ttl_hours"), 1) if report else 1
    # PH-05 写护栏：SQL 含写 → 显示开关（存量默认 1 保持现状；新建默认 0）
    raw_sql = report["sql_query"] if report else ""
    allow_write = _tolerant_int(report.get("allow_write"), 1) if report else 0
    sql_has_write = sql_contains_write(raw_sql)
    # PH-07 全量输出护栏：存量默认 1 保持现状；新建默认 0；max_rows 默认 100000
    allow_all_output = _tolerant_int(report.get("allow_all_output"), 1) if report else 0
    max_rows = _tolerant_int(report.get("max_rows"), 100000) if report else 100000

    return _report_form_html(title, action_url, name, sql_query, default_page_size,
                              required_attr, no_pool_opt, pool_options, category_options, memo_val,
                              result_names_val=result_names_val,
                              is_edit=is_edit, report_id=report.get("id") if report else None,
                              prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours,
                              allow_write=allow_write, sql_has_write=sql_has_write,
                              allow_all_output=allow_all_output, max_rows=max_rows)


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
    # 获取所有 API 端点，按 report_id 分组
    all_endpoints = db.get_all_api_endpoints(conn)
    api_endpoints_map: dict[int, list[dict]] = {}
    for ep in all_endpoints:
        rid = ep["report_id"]
        api_endpoints_map.setdefault(rid, []).append(ep)
    return build_category_section_html(cat_reports, unclassified_reports, all_cats,
                                       all_reports, pools, cat_tree,
                                       api_endpoints_map=api_endpoints_map)


def render_reports_page(conn, flash: str = None) -> str:
    """渲染报表管理独立页（PH-13：分类树 + 报表列表 + 批量操作；分类管理已并入本页）"""
    flash_html = build_flash_html(flash) if flash else ""
    return (render_page_header(title="Web 报表工具 - 报表管理", active_nav="config-reports",
                                extra_css=_CONFIG_EXTRA_CSS)
            + flash_html
            + '<h2 style="margin-bottom:0">报表管理</h2>'
            + _render_category_section(conn)
            + render_page_footer())


def render_overview(conn, flash: str = None) -> str:
    """渲染配置总览页，包含三个配置段"""
    flash_html = ""
    if flash:
        flash_html = build_flash_html(flash)
    # PH-09 空状态引导：无连接池时总览顶部显示首次部署三步指引
    pools = db.get_all_pools(conn)
    onboarding_html = ""
    if not pools:
        onboarding_html = (
            '<div class="card" style="border:1px dashed #c7d2fe;background:#f5f7ff;'
            'padding:14px 20px;margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
            '<span style="font-size:14px;color:#475569">🚀 首次使用？三步开始：'
            '① 添加连接池 → ② 创建报表 → ③ 发布 API 接口</span>'
            '<span style="flex:1"></span>'
            f'{_link_btn("/config/pools/add", "立即添加连接池", "btn btn-primary btn-sm")}'
            '</div>')
    api_endpoints = db.get_all_api_endpoints(conn)
    api_endpoints_count = len(api_endpoints)
    # 气泡内列出接口名称与说明摘要（截断 + title 全文），最多展示 5 个
    items_html = ""
    for ep in api_endpoints[:5]:
        desc_html = _build_desc_summary_html(ep.get("description") or "")
        desc_part = desc_html or '<span style="color:#cbd5e1">—</span>'
        items_html += (f'<div style="margin:4px 0;display:flex;gap:8px;align-items:center">'
                       f'<span style="font-weight:600;white-space:nowrap">{_escape(ep.get("name") or "")}</span>'
                       f'<code style="font-size:12px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:4px">{_escape(ep.get("url_path") or "")}</code>'
                       f'<span style="flex:1;min-width:0">{desc_part}</span></div>')
    if len(api_endpoints) > 5:
        items_html += (f'<div style="color:#94a3b8;font-size:12px;margin-top:4px">'
                       f'…等共 {api_endpoints_count} 个接口</div>')
    api_card = f"""<div class="card" style="margin-top:8px">
<div class="section-title" style="font-size:16px;margin-bottom:8px">
  <span>🔌 API 接口管理</span>
  <span class="actions">{_link_btn("/config/api-endpoints", "管理 API 接口", "btn btn-outline btn-sm")}</span>
</div>
<p style="color:#64748b;margin:0">已配置 {api_endpoints_count} 个 API 接口</p>
{items_html}
</div>"""
    # PH-13 报表区块收敛：报表总数 + 分类数 + 入口按钮（分类树/报表列表/批量操作迁至独立页）
    reports_count = len(db.get_all_reports(conn))
    categories_count = len(db.get_all_categories(conn))
    reports_card = f"""<div class="card" style="margin-top:8px">
<div class="section-title" style="font-size:16px;margin-bottom:8px">
  <span>📊 报表管理</span>
  <span class="actions">{_link_btn("/config/reports", "管理报表", "btn btn-outline btn-sm")}</span>
</div>
<p style="color:#64748b;margin:0">共 {reports_count} 个报表，{categories_count} 个分类</p>
</div>"""
    # PH-14 分类入口卡片：分类树/排序/CRUD 在独立页
    categories_card = f"""<div class="card" style="margin-top:8px">
<div class="section-title" style="font-size:16px;margin-bottom:8px">
  <span>📁 分类管理</span>
  <span class="actions">{_link_btn("/config/reports", "管理分类", "btn btn-outline btn-sm")}</span>
</div>
<p style="color:#64748b;margin:0">共 {categories_count} 个分类（支持树形层级与排序）</p>
</div>"""
    body = (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + onboarding_html + _render_pool_section(conn) + _render_user_section(conn)
            + reports_card + categories_card + api_card + render_page_footer())
    return body


def render_pool_form_page(conn, pool_id: int = None, flash: str = None, copy_mode: bool = False,
                          pool: dict = None) -> str:
    """渲染新增/编辑/复制连接池表单页

    pool: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    echo_pool = pool is not None
    if pool is None:
        pool = db.get_pool(conn, pool_id) if pool_id else None
    if pool_id and not pool:
        return render_overview(conn, flash="错误: 连接池不存在")
    is_edit = pool_id is not None and not copy_mode
    flash_html = build_flash_html(flash) if flash else ""
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_pool_form(pool, copy_mode, is_edit=is_edit,
                                             prefill_copy_suffix=not echo_pool) + render_page_footer())


def render_user_form_page(conn, user_id: int = None, flash: str = None, user: dict = None) -> str:
    """渲染新增/编辑用户表单页

    user: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    if user is None:
        user = db.get_user_by_id(conn, user_id) if user_id else None
    if user_id and not user:
        return render_overview(conn, flash="错误: 用户不存在")
    is_edit = user_id is not None
    flash_html = build_flash_html(flash) if flash else ""
    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html + _render_user_form(user, is_edit=is_edit) + render_page_footer())


def render_category_form_page(conn, category_id: int = None, flash: str = None, cat: dict = None) -> str:
    """渲染新增/编辑分类表单页

    cat: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    if cat is None:
        cat = db.get_category(conn, category_id) if category_id else None
    if category_id and not cat:
        return render_overview(conn, flash="错误: 分类不存在")
    flash_html = build_flash_html(flash) if flash else ""
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
  <div class="form-actions span-full">
    <button type="submit" class="btn btn-primary">保存</button>
    <a href="/config/reports" class="cancel">取消</a>
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


def render_report_form_page(conn, report_id: int = None, flash: str = None, copy_mode: bool = False,
                            report: dict = None) -> str:
    """渲染新增/编辑/复制报表表单页

    report: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    echo_report = report is not None
    if report is None:
        report = db.get_report(conn, report_id) if report_id else None
    if report_id and not report:
        return render_overview(conn, flash="错误: 报表不存在")
    is_edit = report_id is not None and not copy_mode
    flash_html = build_flash_html(flash) if flash else ""
    body = render_page_header(title="Web 报表工具 - 配置", active_nav="config", extra_css=_CONFIG_MD_EXTRA_CSS)
    body += flash_html + _render_report_form(conn, report, copy_mode, is_edit=is_edit,
                                             prefill_copy_suffix=not echo_report)
    # 编辑模式下显示 API 接口列表
    if report_id and not copy_mode:
        api_endpoints = db.get_api_endpoints_by_report(conn, report_id)
        base_url = app_config.get_server_base_url()
        body += build_api_endpoints_list_html(
            api_endpoints, report_id, base_url=base_url,
            key_counts=config_db.get_api_key_counts(conn))
    body += render_page_footer()
    return body


# ---------------------------------------------------------------------------
# 表单提交处理
# ---------------------------------------------------------------------------


def _parse_form_data(form_body: str) -> dict:
    """解析 URL 编码的表单数据"""
    return app_config.parse_form_urlencoded(form_body)


def _parse_report_form(data: dict) -> dict:
    """解析报表表单公共字段（add/edit/copy 共用读路径）。"""
    return {
        "pool_id": int(data["pool_id"]) if data.get("pool_id") else None,
        "category_id": int(data["category_id"]) if data.get("category_id") else None,
        "memo": data.get("memo") or None,
        "result_names": data.get("result_names") or "",
        "prefer_cache": int(data.get("prefer_cache", 1) or 0),
        "cache_ttl_hours": int(data.get("cache_ttl_hours", 0) or 0),
        # 表单始终携带隐藏 allow_write=0（checkbox 勾选时提交 0,1，取最后一个为 1）
        "allow_write": int(data.get("allow_write", 0) or 0),
        # 全量输出护栏（PH-07）：hidden 0 + checkbox 1，勾选时提交 0,1 取最后为 1；
        # max_rows 非法/空值时回退默认 100000（仅关闭全量输出时生效）
        "allow_all_output": int(data.get("allow_all_output", 0) or 0),
        "max_rows": app_config.safe_int(data.get("max_rows"), 100000),
    }


def _save_or_render(data: dict, render_fn, args: tuple, kwargs: dict,
                    success_flash: str, redirect_url: str) -> tuple[int, str]:
    """统一「保存 / 保存并关闭」双按钮保存模式。

    - action=save       → 200 + 渲染表单页（flash=success_flash，留在当前页）
    - action=save_close → 302 + redirect_url?flash=success_flash（默认，返回上级）
    """
    action = data.get("action", "save_close")
    if action == "save":
        return 200, render_fn(*args, flash=success_flash, **kwargs)
    return 302, f"{redirect_url}?flash={success_flash}"


def _tolerant_int(value, default=None):
    """容错 int 转换：非法值原样返回（用于保存失败时回显用户输入）。"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _echo_int(value, default):
    """严格 int 转换：非法或空值返回 default（用于回显端点数值字段）。"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _pool_from_form(data: dict, pool_id: int = None) -> dict:
    """从表单数据构造临时连接池 dict（保存失败时表单回显用户原输入）。"""
    pool = {
        "name": data.get("name", ""),
        "host": data.get("host", ""),
        "port": data.get("port", "3306"),
        "user": data.get("user", ""),
        "password": data.get("password", ""),
        "database": data.get("database", ""),
    }
    if pool_id is not None:
        pool["id"] = pool_id
    return pool


def _user_from_form(data: dict, user_id: int = None) -> dict:
    """从表单数据构造临时用户 dict（保存失败时表单回显用户原输入）。"""
    user = {"username": data.get("username", "")}
    if user_id is not None:
        user["id"] = user_id
    return user


def _report_from_form(data: dict, report_id: int = None) -> dict:
    """从表单数据构造临时报表 dict（保存失败时表单回显用户原输入）。"""
    report = {
        "name": data.get("name", ""),
        "sql_query": data.get("sql_query", ""),
        "default_page_size": data.get("default_page_size", "20"),
        "pool_id": _tolerant_int(data.get("pool_id")),
        "category_id": _tolerant_int(data.get("category_id")),
        "memo": data.get("memo", ""),
        "result_names": data.get("result_names", ""),
        "prefer_cache": _tolerant_int(data.get("prefer_cache"), 1),
        "cache_ttl_hours": data.get("cache_ttl_hours", "0"),
        "allow_write": _tolerant_int(data.get("allow_write"), 0),
        "allow_all_output": _tolerant_int(data.get("allow_all_output"), 0),
        "max_rows": _tolerant_int(data.get("max_rows"), 100000),
    }
    if report_id is not None:
        report["id"] = report_id
    return report


def _category_from_form(data: dict, category_id: int = None) -> dict:
    """从表单数据构造临时分类 dict（保存失败时表单回显用户原输入）。"""
    cat = {
        "name": data.get("name", ""),
        "parent_id": data.get("parent_id", ""),
    }
    if category_id is not None:
        cat["id"] = category_id
    return cat


def _normalize_api_url_path(path: str) -> str:
    """
    规范化 API URL 路径。

    表单提交的 url_path 不包含 /api/ 前缀（前缀在 UI 上固定显示），
    此函数确保存储到 DB 时补全为 /api/<suffix> 格式。
    同时兼容旧格式（已有 /api/ 前缀）以确保向后兼容。
    """
    return app_config.ensure_api_prefix(path)


def _parse_rule_json(rule_json_str: str) -> tuple[str, str, str]:
    """
    解析规则 JSON 字符串，拆出 columns/filters/sorts 三个字段。

    返回:
        (columns, filters_json_str, sorts_json_str)
    """
    columns = ""
    filters_str = ""
    sorts_str = ""
    if not rule_json_str or not rule_json_str.strip():
        return columns, filters_str, sorts_str
    try:
        rules = json.loads(rule_json_str)
    except json.JSONDecodeError:
        raise ValueError("规则 JSON 格式无效")
    if not isinstance(rules, dict):
        raise ValueError("规则 JSON 必须是一个对象")
    columns = rules.get("columns", "") or ""
    f_raw = rules.get("filters")
    if f_raw:
        filters_str = json.dumps(f_raw, ensure_ascii=False) if isinstance(f_raw, list) else str(f_raw)
    s_raw = rules.get("sorts")
    if s_raw:
        sorts_str = json.dumps(s_raw, ensure_ascii=False) if isinstance(s_raw, list) else str(s_raw)
    return columns, filters_str, sorts_str


def handle_pool_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增连接池表单提交

    遵循「保存」/「保存返回上级」双按钮业务逻辑。
    """
    data = _parse_form_data(form_body)
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"],
                          session_user=session_user)
        return _save_or_render(
            data, render_pool_form_page, (conn, pid), {},
            success_flash=f"连接池 {data['name']} 已创建 (id={pid})",
            redirect_url="/config")
    except Exception as e:
        return 200, render_pool_form_page(conn, flash=f"错误: {e}",
                                          pool=_pool_from_form(data))


def handle_pool_edit(conn, pool_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑连接池表单提交

    遵循「保存」/「保存返回上级」双按钮业务逻辑。
    """
    data = _parse_form_data(form_body)
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return 302, "/config?flash=错误: 连接池不存在"
    password = data.get("password") or pool["password"]
    try:
        ok = db.update_pool(conn, pool_id, data["name"], data["host"],
                            int(data["port"]), data["user"], password, data["database"],
                            session_user=session_user)
        if ok:
            return _save_or_render(
                data, render_pool_form_page, (conn, pool_id), {},
                success_flash=f"连接池 {data['name']} 已更新",
                redirect_url="/config")
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_pool_form_page(conn, pool_id, flash=f"错误: {e}",
                                          pool=_pool_from_form(data, pool_id))


def handle_pool_copy(conn, pool_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理复制连接池（新增一个同名+副本的连接池）"""
    data = _parse_form_data(form_body)
    src = db.get_pool(conn, pool_id)
    if not src:
        return 200, render_pool_form_page(conn, pool_id, flash="错误: 连接池不存在",
                                          copy_mode=True,
                                          pool=_pool_from_form(data, pool_id))
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"],
                          session_user=session_user)
        return 302, f"/config?flash=连接池 {data['name']} 已创建（复制自 id={pool_id}）"
    except Exception as e:
        return 200, render_pool_form_page(conn, pool_id, flash=f"错误: {e}", copy_mode=True,
                                          pool=_pool_from_form(data, pool_id))


def handle_pool_delete(conn, pool_id: int, session_user=None) -> tuple[int, str]:
    """处理删除连接池"""
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return 302, "/config?flash=错误: 连接池不存在"
    db.delete_pool(conn, pool_id, session_user=session_user)
    return 302, f"/config?flash=连接池 {pool['name']} 已删除"


def handle_user_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增用户表单提交"""
    data = _parse_form_data(form_body)
    try:
        pw_hash = auth.hash_password(data["password"])
        uid = db.add_user(conn, data["username"], pw_hash, session_user=session_user)
        return 302, f"/config?flash=用户 {data['username']} 已创建 (id={uid})"
    except Exception as e:
        return 200, render_user_form_page(conn, flash=f"错误: {e}",
                                          user=_user_from_form(data))


def handle_user_edit(conn, user_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑用户表单提交"""
    data = _parse_form_data(form_body)
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return 302, "/config?flash=错误: 用户不存在"
    try:
        password_hash = auth.hash_password(data["password"]) if data.get("password") else target["password_hash"]
        ok = db.update_user(conn, user_id, data["username"], password_hash, session_user=session_user)
        if ok:
            return 302, f"/config?flash=用户 {data['username']} 已更新"
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_user_form_page(conn, user_id, flash=f"错误: {e}",
                                          user=_user_from_form(data, user_id))


def handle_user_delete(conn, user_id: int, session_user=None) -> tuple[int, str]:
    """处理删除用户"""
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return 302, "/config?flash=错误: 用户不存在"
    db.delete_user(conn, user_id, session_user=session_user)
    return 302, f"/config?flash=用户 {target['username']} 已删除"


def handle_report_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增报表表单提交

    遵循「保存」/「保存并关闭」双按钮业务逻辑：
    - action=save         → 保存后返回 200，停留在编辑页（可继续编辑）
    - action=save_close   → 保存后 302 返回列表页（默认）
    """
    data = _parse_form_data(form_body)
    try:
        rf = _parse_report_form(data)
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), rf["pool_id"],
                            rf["category_id"], rf["memo"],
                            result_names=rf["result_names"],
                            prefer_cache=rf["prefer_cache"],
                            cache_ttl_hours=rf["cache_ttl_hours"],
                            allow_write=rf["allow_write"],
                            allow_all_output=rf["allow_all_output"],
                            max_rows=rf["max_rows"],
                            session_user=session_user)
        return _save_or_render(
            data, render_report_form_page, (conn, rid), {},
            success_flash=f"报表 {data['name']} 已创建 (id={rid})",
            redirect_url="/config/reports")
    except Exception as e:
        return 200, render_report_form_page(conn, flash=f"错误: {e}",
                                            report=_report_from_form(data))


def handle_report_edit(conn, report_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑报表表单提交"""
    data = _parse_form_data(form_body)
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return 302, "/config/reports?flash=错误: 报表不存在"
    try:
        rf = _parse_report_form(data)
        ok = db.update_report(conn, report_id, data["name"], data["sql_query"],
                              int(data["default_page_size"]), rf["pool_id"],
                              rf["category_id"], rf["memo"],
                              result_names=rf["result_names"],
                              prefer_cache=rf["prefer_cache"],
                              cache_ttl_hours=rf["cache_ttl_hours"],
                              allow_write=rf["allow_write"],
                              allow_all_output=rf["allow_all_output"],
                              max_rows=rf["max_rows"],
                              session_user=session_user)
        if ok:
            return _save_or_render(
                data, render_report_form_page, (conn, report_id), {},
                success_flash=f"报表 {data['name']} 已更新",
                redirect_url="/config/reports")
        return 302, "/config/reports?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_report_form_page(conn, report_id, flash=f"错误: {e}",
                                            report=_report_from_form(data, report_id))


def handle_report_copy(conn, report_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理复制报表（新增一个同名+副本的报表）

    遵循「保存」/「保存并关闭」双按钮业务逻辑，与新建报表一致。
    """
    data = _parse_form_data(form_body)
    src = db.get_report(conn, report_id)
    if not src:
        return 200, render_report_form_page(conn, report_id, flash="错误: 报表不存在",
                                            copy_mode=True,
                                            report=_report_from_form(data, report_id))
    try:
        rf = _parse_report_form(data)
        rid = db.add_report(conn, data["name"], data["sql_query"],
                            int(data["default_page_size"]), rf["pool_id"],
                            rf["category_id"], rf["memo"],
                            result_names=rf["result_names"],
                            prefer_cache=rf["prefer_cache"],
                            cache_ttl_hours=rf["cache_ttl_hours"],
                            allow_write=rf["allow_write"],
                            allow_all_output=rf["allow_all_output"],
                            max_rows=rf["max_rows"],
                            session_user=session_user)
        return _save_or_render(
            data, render_report_form_page, (conn, rid), {},
            success_flash=f"报表 {data['name']} 已创建（复制自 id={report_id}）",
            redirect_url="/config/reports")
    except Exception as e:
        return 200, render_report_form_page(conn, report_id, flash=f"错误: {e}", copy_mode=True,
                                            report=_report_from_form(data, report_id))


def handle_report_delete(conn, report_id: int, session_user=None) -> tuple[int, str]:
    """处理删除报表"""
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return 302, "/config/reports?flash=错误: 报表不存在"
    db.delete_report(conn, report_id, session_user=session_user)
    return 302, f"/config/reports?flash=报表 {rpt['name']} 已删除"


def handle_report_move_category(conn, report_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理报表移动到指定分类"""
    data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    cat_str = data.get("category_id", [None])[0]
    try:
        category_id = int(cat_str) if cat_str else None
    except (ValueError, TypeError):
        return 302, "/config/reports?flash=错误: 分类 ID 无效"
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return 302, "/config/reports?flash=错误: 报表不存在"
    if category_id is not None and not db.get_category(conn, category_id):
        return 302, "/config/reports?flash=错误: 目标分类不存在"
    try:
        db.move_report_to_category(conn, report_id, category_id, session_user=session_user)
    except Exception as e:
        return 302, f"/config/reports?flash=错误: 移动分类失败: {e}"
    cat_name = "未分类"
    if category_id is not None:
        cat = db.get_category(conn, category_id)
        if cat:
            cat_name = cat["name"]
    return 302, f"/config/reports?flash=报表 {rpt['name']} 已移至「{cat_name}」"


def handle_category_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增分类"""
    data = _parse_form_data(form_body)
    try:
        parent_id = int(data["parent_id"]) if data.get("parent_id") else None
        cid = db.add_category(conn, data["name"], parent_id, session_user=session_user)
        return 302, f"/config/reports?flash=分类 {data['name']} 已创建"
    except Exception as e:
        return 200, render_category_form_page(conn, flash=f"错误: {e}",
                                              cat=_category_from_form(data))


def handle_category_edit(conn, category_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑分类"""
    data = _parse_form_data(form_body)
    cat = db.get_category(conn, category_id)
    if not cat:
        return 302, "/config/reports?flash=错误: 分类不存在"
    try:
        parent_id = int(data["parent_id"]) if data.get("parent_id") else None
        db.update_category(conn, category_id, data["name"], parent_id, session_user=session_user)
        return 302, f"/config/reports?flash=分类 {data['name']} 已更新"
    except Exception as e:
        return 200, render_category_form_page(conn, category_id, flash=f"错误: {e}",
                                              cat=_category_from_form(data, category_id))


def handle_category_delete(conn, category_id: int, session_user=None) -> tuple[int, str]:
    """处理删除分类"""
    cat = db.get_category(conn, category_id)
    if not cat:
        return 302, "/config/reports?flash=错误: 分类不存在"
    db.delete_category(conn, category_id, session_user=session_user)
    return 302, f"/config/reports?flash=分类 {cat['name']} 已删除"


def handle_batch_set_category(conn, form_body: str) -> tuple[int, str]:
    """处理报表批量设置分类"""
    try:
        data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
        report_ids = [int(v) for v in data.get("report_ids", []) if v]
        cat_str = data.get("category_id", [None])[0]
        category_id = int(cat_str) if cat_str else None
    except (ValueError, TypeError):
        return 302, "/config/reports?flash=错误: 报表 ID 或分类 ID 无效"
    if not report_ids:
        return 302, "/config/reports?flash=错误: 未选择任何报表"
    if category_id is not None and not db.get_category(conn, category_id):
        return 302, "/config/reports?flash=错误: 目标分类不存在"
    try:
        affected = db.batch_set_report_category(conn, report_ids, category_id)
    except Exception as e:
        return 302, f"/config/reports?flash=错误: 批量设置分类失败: {e}"
    cat_name = "未分类"
    if category_id is not None:
        cat = db.get_category(conn, category_id)
        if cat:
            cat_name = cat["name"]
    return 302, f"/config/reports?flash=已为 {affected} 个报表设置分类为「{cat_name}」"


def handle_batch_pool(conn, form_body: str) -> tuple[int, str]:
    """处理报表批量修改连接池"""
    try:
        data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
        report_ids = [int(v) for v in data.get("report_ids", []) if v]
        pool_id_str = data.get("pool_id", [None])[0]
        pool_id = int(pool_id_str) if pool_id_str else None
    except (ValueError, TypeError):
        return 302, "/config/reports?flash=错误: 报表 ID 或连接池 ID 无效"
    if not report_ids:
        return 302, "/config/reports?flash=错误: 未选择报表"
    if pool_id is not None and not db.get_pool(conn, pool_id):
        return 302, "/config/reports?flash=错误: 目标连接池不存在"
    try:
        n = db.batch_update_report_pool(conn, report_ids, pool_id)
    except Exception as e:
        return 302, f"/config/reports?flash=错误: 批量修改连接池失败: {e}"
    pool_label = pool_id if pool_id else "无"
    return 302, f"/config/reports?flash=已更新 {n} 个报表的连接池为 (id={pool_label})"


def handle_batch_cache(conn, form_body: str) -> tuple[int, str]:
    """处理报表批量更新缓存配置"""
    try:
        data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
        report_ids = [int(v) for v in data.get("report_ids", []) if v]
        cache_switch = data.get("cache_switch", [""])[0]
        modify_ttl = data.get("modify_ttl", [""])[0] == "1"
        cache_ttl_hours = None
        if modify_ttl:
            ttl_val = data.get("cache_ttl_hours", ["0"])[0]
            cache_ttl_hours = int(ttl_val) if ttl_val else 0
    except (ValueError, TypeError):
        return 302, "/config/reports?flash=错误: 报表 ID 或缓存 TTL 无效"
    if not report_ids:
        return 302, "/config/reports?flash=错误: 未选择报表"

    prefer_cache = None
    if cache_switch == "1":
        prefer_cache = 1
    elif cache_switch == "0":
        prefer_cache = 0

    try:
        affected = db.batch_update_report_cache(conn, report_ids, prefer_cache, cache_ttl_hours)
    except Exception as e:
        return 302, f"/config/reports?flash=错误: 批量更新缓存配置失败: {e}"

    redis_updated = 0
    redis_failed = 0
    try:
        mgr = redis_cache.get_redis_manager()
        if mgr and mgr.available:
            prefix = mgr.key_prefix
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

    # 静态文件缓存联动：关闭缓存时删除对应报表所有端点的静态文件（删除即失效，惰性重建）
    if cache_switch == "0":
        for rid in report_ids:
            try:
                config_db.invalidate_api_static_cache_by_report(conn, rid)
            except Exception as e:
                logging.warning("static_cache 批量关缓存联动失败: %s", e)

    parts = [f"已更新 {affected} 个报表的缓存配置"]
    if redis_updated > 0:
        parts.append(f"Redis 成功 {redis_updated}")
    if redis_failed > 0:
        parts.append(f"Redis 失败 {redis_failed}")
    return 302, f"/config/reports?flash={'，'.join(parts)}"


def handle_batch_delete(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理报表批量删除（级联删除关联 API 端点并失效静态缓存）"""
    try:
        data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
        report_ids = [int(v) for v in data.get("report_ids", []) if v]
    except (ValueError, TypeError):
        return 302, "/config/reports?flash=错误: 报表 ID 无效"
    if not report_ids:
        return 302, "/config/reports?flash=错误: 未选择报表"
    try:
        affected = db.batch_delete_reports(conn, report_ids, session_user=session_user)
    except Exception as e:
        return 302, f"/config/reports?flash=错误: 批量删除报表失败: {e}"
    return 302, f"/config/reports?flash=已删除 {affected} 个报表"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def handle_memo_preview(form_body: str) -> tuple[int, str, dict]:
    """报表备注 Markdown 预览端点处理。

    将 memo 原文渲染为已消毒的 HTML 片段返回（纯渲染、无落库、无数据库依赖）。
    渲染逻辑与报表页共用 render_markdown()，杜绝双实现漂移。
    """
    data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
    memo = (data.get("memo") or [""])[-1]
    return 200, markdown_render.render_markdown(memo), {}


def handle_description_preview(form_body: str) -> tuple[int, str, dict]:
    """API 接口说明 Markdown 预览端点处理（api-desc-markdown T4）。

    将 description 原文渲染为已消毒的 HTML 片段返回（纯渲染、无落库、无数据库依赖）。
    渲染逻辑与查看页共用 render_markdown()，杜绝双实现漂移（镜像 handle_memo_preview）。
    """
    data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
    description = (data.get("description") or [""])[-1]
    return 200, markdown_render.render_markdown(description), {}


def handle_request(conn, method: str, path: str, query: str,
                   form_body: str = None, session_user=None) -> tuple[int, str, dict]:
    """
    配置页面请求入口。

    参数:
      conn     — SQLite 连接
      method   — HTTP 方法 (GET/POST)
      path     — URL 路径
      query    — URL 查询字符串
      form_body — POST 请求体
      session_user — 当前用户名（用于审计日志）

    返回:
      (HTTP 状态码, 响应体, 额外响应头 dict)
    """
    route = parse_config_path(path)

    # 从 query string 提取 flash 消息
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)
    flash = qs.get("flash", [None])[0]

    # ---- 总览 ----
    if route["action"] == "overview":
        return 200, render_overview(conn, flash), {}

    # ---- 表单页面 (GET) ----
    if method == "GET":
        if route["action"] == "add":
            if route["section"] == "pools":
                return 200, render_pool_form_page(conn), {}
            elif route["section"] == "users":
                return 200, render_user_form_page(conn), {}
            elif route["section"] == "reports":
                return 200, render_report_form_page(conn), {}
            elif route["section"] == "categories":
                return 200, render_category_form_page(conn), {}
        elif route["action"] == "edit" and route["id"]:
            if route["section"] == "pools":
                return 200, render_pool_form_page(conn, route["id"]), {}
            elif route["section"] == "users":
                return 200, render_user_form_page(conn, route["id"]), {}
            elif route["section"] == "reports":
                return 200, render_report_form_page(conn, route["id"]), {}
            elif route["section"] == "categories":
                return 200, render_category_form_page(conn, route["id"]), {}
        elif route["action"] == "copy" and route["id"]:
            if route["section"] == "pools":
                return 200, render_pool_form_page(conn, route["id"], copy_mode=True), {}
            elif route["section"] == "reports":
                return 200, render_report_form_page(conn, route["id"], copy_mode=True), {}
        # API 端点表单
        if route["action"] == "api_new" and route["report_id"]:
            return 200, render_api_endpoint_form_page(
                conn, route["report_id"]), {}
        if route["action"] == "api_edit" and route["endpoint_id"]:
            return 200, render_api_endpoint_form_page(
                conn, route["report_id"], route["endpoint_id"]), {}
        if route["action"] == "api_preview" and route["endpoint_id"]:
            # GET 直开预览地址：无表单值可执行，返回指引页
            return 200, build_api_endpoint_preview_help_html(
                route["report_id"], route["endpoint_id"]), {}
        if route["action"] == "api_keys" and route["endpoint_id"]:
            # GET 直开 Key 管理地址：重定向回编辑页
            return _redirect_or_render(
                302, (f"/config/reports/{route['report_id']}"
                      f"/api_endpoints/{route['endpoint_id']}/edit"))

    # ---- POST 处理 ----
    # 备注 Markdown 预览（纯渲染无落库，与报表页共用 render_markdown 单一来源）
    if (method == "POST" and route["section"] == "reports"
            and route["action"] == "memo-preview"):
        return handle_memo_preview(form_body or "")

    # API 接口说明 Markdown 预览（纯渲染无落库，api-desc-markdown T4）
    if (method == "POST" and route["section"] == "api-endpoints"
            and route["action"] == "description-preview"):
        return handle_description_preview(form_body or "")

    # API 端点 POST 处理（放在 reports section 中匹配前先拦截）
    if method == "POST" and route["section"] == "reports" and route["report_id"]:
        if route["action"] == "api_new" and route["report_id"]:
            code, result = handle_api_endpoint_add(
                conn, route["report_id"], form_body or "", session_user=session_user)
            return _redirect_or_render(code, result)
        elif route["action"] == "api_edit" and route["endpoint_id"]:
            code, result = handle_api_endpoint_edit(
                conn, route["report_id"], route["endpoint_id"], form_body or "", session_user=session_user)
            return _redirect_or_render(code, result)
        elif route["action"] == "api_delete" and route["endpoint_id"]:
            code, result = handle_api_endpoint_delete(
                conn, route["report_id"], route["endpoint_id"], session_user=session_user)
            return _redirect_or_render(code, result)
        elif route["action"] == "api_preview" and route["endpoint_id"]:
            # 真实数据预览：返回 JSON（非 HTML），不重定向
            return handle_api_endpoint_preview(
                conn, route["report_id"], route["endpoint_id"], form_body or "",
                session_user=session_user)
        elif route["action"] == "api_keys" and route["endpoint_id"]:
            # API Key 管理动作（add/delete/toggle），返回重定向
            return handle_api_key_actions(
                conn, route["report_id"], route["endpoint_id"], form_body or "",
                session_user=session_user)

    if method == "POST":
        if route["section"] == "pools":
            if route["action"] == "add":
                code, result = handle_pool_add(conn, form_body or "", session_user=session_user)
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_pool_edit(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "copy" and route["id"]:
                code, result = handle_pool_copy(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_pool_delete(conn, route["id"], session_user=session_user)
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_pool(conn, route["id"], direction, session_user=session_user)
                return 302, "/config", {}
            else:
                return 302, "/config", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "users":
            if route["action"] == "add":
                code, result = handle_user_add(conn, form_body or "", session_user=session_user)
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_user_edit(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_user_delete(conn, route["id"], session_user=session_user)
            else:
                return 302, "/config", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "reports":
            if route["action"] == "add":
                code, result = handle_report_add(conn, form_body or "", session_user=session_user)
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_report_edit(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "copy" and route["id"]:
                code, result = handle_report_copy(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_report_delete(conn, route["id"], session_user=session_user)
            elif route["action"] == "batch-pool":
                code, result = handle_batch_pool(conn, form_body or "")
                return _redirect_or_render(code, result)
            elif route["action"] == "batch-set-category":
                code, result = handle_batch_set_category(conn, form_body or "")
                return _redirect_or_render(code, result)
            elif route["action"] == "batch-cache":
                code, result = handle_batch_cache(conn, form_body or "")
                return _redirect_or_render(code, result)
            elif route["action"] == "batch-delete":
                code, result = handle_batch_delete(conn, form_body or "", session_user=session_user)
                return _redirect_or_render(code, result)
            elif route["action"] == "move-category" and route["id"]:
                code, result = handle_report_move_category(conn, route["id"], form_body or "", session_user=session_user)
                return _redirect_or_render(code, result)
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_report(conn, route["id"], direction, session_user=session_user)
                return 302, "/config/reports", {}
            else:
                return 302, "/config/reports", {}
            return _redirect_or_render(code, result)

        elif route["section"] == "categories":
            if route["action"] == "add":
                code, result = handle_category_add(conn, form_body or "", session_user=session_user)
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_category_edit(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_category_delete(conn, route["id"], session_user=session_user)
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                direction = "up" if route["action"] == "move-up" else "down"
                db.move_category(conn, route["id"], direction, session_user=session_user)
                return 302, "/config/reports", {}
            else:
                return 302, "/config/reports", {}
            return _redirect_or_render(code, result)

    return 302, "/config", {}


def _estimate_result_count(sql_query: str) -> int:
    """估算 SQL 中 SELECT/WITH 语句的数量。"""
    sql = sql_query.strip()
    if not sql:
        return 1
    count = 0
    for stmt in db._split_sql_statements(sql):
        stmt = stmt.strip().upper()
        if stmt.startswith("SELECT") or stmt.startswith("WITH"):
            count += 1
    return max(count, 1)


def render_api_endpoint_form_page(conn, report_id: int,
                                   endpoint_id: int = None,
                                   flash: str = None,
                                   endpoint: dict = None,
                                   is_edit: bool = None) -> str:
    """渲染新增/编辑 API 端点表单页

    endpoint: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    is_edit: 表单模式（None 时按 endpoint_id 判定）
    """
    report = db.get_report(conn, report_id)
    if not report:
        return render_overview(conn, flash="错误: 报表不存在")
    if endpoint is None:
        endpoint = db.get_api_endpoint(conn, endpoint_id) if endpoint_id else None
    if endpoint_id and not endpoint:
        return render_overview(conn, flash="错误: API 接口不存在")

    result_names_raw = (report.get("result_names") or "").strip()
    result_names_list = parse_result_names(result_names_raw)
    result_count = len(result_names_list) if result_names_list else _estimate_result_count(report["sql_query"])

    # 编辑态查询该端点的 API Key 列表（多 key 管理区块）
    api_keys = config_db.list_api_keys(conn, endpoint_id) if endpoint_id else []

    return (render_page_header(title="Web 报表工具 - 配置", active_nav="config",
                                extra_css=_CONFIG_EXTRA_CSS)
            + build_api_endpoint_form_html(report_id, report["name"],
                                            endpoint, flash,
                                            result_names_list=result_names_list,
                                            result_count=result_count,
                                            endpoint_id=endpoint_id,
                                            is_edit=is_edit,
                                            api_keys=api_keys)
            + render_page_footer())


def _template_raw_for_format(output_format: str, data: dict) -> str:
    """按输出格式取模板文本：CSV 模式不支持模板，返回空串（不校验、不落库，
    保留库中原值，切回 JSON 后模板仍可用）。"""
    return "" if output_format == "csv" else data.get("json_template", "")


def _validate_json_template(raw: str, result_mode: str,
                            smart_quote_flags: int = 0) -> str | None:
    """校验 JSON 输出模板文本；返回错误消息（None=合法或未启用）。

    键集随表单 result_mode 判定（single/all），与渲染链路保持一致。
    smart_quote_flags>0（「智能去引号」面板勾选）时替换后的 JSON 合法性
    校验恒执行（智能模式输出永远合法，升级点）。
    """
    if not raw or not raw.strip():
        return None
    keys = SINGLE_KEYS if result_mode == "single" else ALL_KEYS
    ok, err = validate_template(raw, keys, smart_quote_flags=smart_quote_flags)
    return None if ok else err


def _endpoint_from_form(data: dict, url_path: str, result_mode: str) -> dict:
    """从表单数据构造临时端点 dict（保存失败时表单回显用户原输入）。"""
    try:
        columns, filters_str, sorts_str = _parse_rule_json(data.get("rule_json", ""))
    except ValueError:
        columns = ""
        filters_str = data.get("rule_json", "") or ""
        sorts_str = ""
    return {
        "name": data.get("name", ""),
        "description": data.get("description", "") or "",
        "url_path": url_path,
        "output_format": data.get("output_format", "json"),
        "columns": columns,
        "filters": filters_str,
        "sorts": sorts_str,
        "row_limit": _echo_int(data.get("row_limit"), 0),
        "api_key": data.get("api_key") or "",
        "allowed_origins": data.get("allowed_origins") or "",
        "enabled": _echo_int(data.get("enabled"), 0),
        "allow_fetch_all": _echo_int(data.get("allow_fetch_all"), 1),
        "static_cache": _echo_int(data.get("static_cache"), 1),
        "smart_quote_flags": _echo_int(data.get("smart_quote_flags"), 0),
        "result_mode": result_mode,
        "result_index": _echo_int(data.get("result_index"), 0),
        "json_template": data.get("json_template", "") or "",
    }


def _parse_endpoint_form(data: dict) -> dict:
    """从表单数据解析 API 端点全部字段（add/edit 共用读路径）。

    产出字段含 name/url_path/output_format/columns/filters_str/sorts_str/
    row_limit/enabled/allow_fetch_all/static_cache/result_mode/
    result_index/template_raw/api_key/allowed_origins/description。
    """
    output_format = data.get("output_format", "json")
    result_mode = data.get("result_mode", "single")
    columns, filters_str, sorts_str = _parse_rule_json(data.get("rule_json", ""))
    return {
        "name": data["name"],
        "url_path": _normalize_api_url_path(data["url_path"]),
        "output_format": output_format,
        "columns": columns,
        "filters_str": filters_str,
        "sorts_str": sorts_str,
        "row_limit": int(data.get("row_limit", 0) or 0),
        "enabled": int(data.get("enabled", 0) or 0),
        "allow_fetch_all": int(data.get("allow_fetch_all", 1) or 0),
        "static_cache": int(data.get("static_cache", 1) or 0),
        "smart_quote_flags": int(data.get("smart_quote_flags", 0) or 0),
        "result_mode": result_mode,
        "result_index": int(data.get("result_index", 0) or 0),
        # CSV 模式忽略模板字段（模板仅 JSON 有效）：不校验、不落库
        "template_raw": _template_raw_for_format(output_format, data),
        "api_key": data.get("api_key") or None,
        "allowed_origins": data.get("allowed_origins") or None,
        "description": data.get("description") or None,
    }


def _endpoint_unique_error(err_msg: str, url_path: str = "") -> str:
    """将 UNIQUE 约束错误转换为重复路径提示，非唯一错误原样返回。"""
    if "UNIQUE" in err_msg or "unique" in err_msg:
        return f"URL 路径 '{url_path}' 已存在"
    return err_msg


def handle_api_key_actions(conn, report_id: int, endpoint_id: int,
                           form_body: str = "",
                           session_user=None) -> tuple[int, str, dict]:
    """处理 API Key 管理动作（POST：add 生成新 Key / delete / toggle）。

    操作成功后重定向回端点编辑页并携带 flash。
    """
    edit_url = f"/config/reports/{report_id}/api_endpoints/{endpoint_id}/edit"
    endpoint = db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        flash_msg = "错误: API 接口不存在"
        return _redirect_or_render(
            302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")
    if int(endpoint.get("report_id", 0)) != report_id:
        flash_msg = "错误: API 接口不属于该报表"
        return _redirect_or_render(
            302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")

    data = _parse_form_data(form_body or "")
    action = data.get("action", "")
    key_id_raw = data.get("key_id", "")
    name = (data.get("name") or "").strip()
    try:
        if action == "add":
            key_name = name or endpoint["name"]
            config_db.add_api_key(conn, endpoint_id, key_name,
                                  api_handler.generate_api_key(),
                                  session_user=session_user)
            flash_msg = f"API Key 已生成（{key_name}）"
        elif action in ("delete", "toggle"):
            # 归属校验：key 必须属于当前端点，否则拒绝（防跨端点越权操作）
            key_row = config_db.get_api_key(conn, int(key_id_raw))
            if not key_row:
                flash_msg = "错误: API Key 不存在"
            elif int(key_row.get("endpoint_id", 0)) != endpoint_id:
                flash_msg = "错误: API Key 不属于该接口"
            elif action == "delete":
                config_db.delete_api_key(conn, int(key_id_raw),
                                         session_user=session_user)
                flash_msg = "API Key 已删除"
            else:
                new_enabled = 0 if int(key_row.get("enabled", 1)) else 1
                config_db.set_api_key_enabled(conn, int(key_id_raw), new_enabled,
                                              session_user=session_user)
                flash_msg = (f"API Key {key_row['name']} "
                             f"已{'启用' if new_enabled else '禁用'}")
        else:
            flash_msg = "错误: 未知操作"
    except (ValueError, TypeError):
        flash_msg = "错误: 无效的 Key ID"
    return _redirect_or_render(
        302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")


def handle_api_endpoint_add(conn, report_id: int,
                             form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增 API 端点表单提交"""
    data = _parse_form_data(form_body)
    try:
        pf = _parse_endpoint_form(data)
        tpl_err = _validate_json_template(
            pf["template_raw"], pf["result_mode"],
            smart_quote_flags=pf["smart_quote_flags"])
        if tpl_err:
            return 200, render_api_endpoint_form_page(
                conn, report_id,
                endpoint=_endpoint_from_form(data, pf["url_path"], pf["result_mode"]),
                is_edit=False,
                flash=f"错误: JSON 输出模板无效: {tpl_err}")
        eid = db.add_api_endpoint(
            conn, report_id, pf["name"], pf["url_path"],
            output_format=pf["output_format"],
            columns=pf["columns"] or None,
            filters=pf["filters_str"] or None,
            sorts=pf["sorts_str"] or None,
            row_limit=pf["row_limit"],
            allowed_origins=pf["allowed_origins"],
            result_mode=pf["result_mode"],
            result_index=pf["result_index"],
            allow_fetch_all=pf["allow_fetch_all"],
            static_cache=pf["static_cache"],
            smart_quote_flags=pf["smart_quote_flags"],
            json_template=pf["template_raw"] or None,
            description=pf["description"],
            session_user=session_user,
        )
        # 多 key 化：表单不再有 api_key 输入框。旧客户端 POST 仍带 api_key
        # 字段时（兼容路径）写入 api_keys 表（name=端点名）；否则自动生成一条。
        if pf["api_key"]:
            config_db.add_api_key(conn, eid, pf["name"], pf["api_key"],
                                  session_user=session_user)
        else:
            config_db.add_api_key(conn, eid, pf["name"],
                                  api_handler.generate_api_key(),
                                  session_user=session_user)
        if not pf["enabled"]:
            db.update_api_endpoint(conn, eid, enabled=0, session_user=session_user)
        return _save_or_render(
            data, render_api_endpoint_form_page,
            (conn, report_id, eid), {},
            success_flash=f"API 接口 {pf['name']} 已创建 (id={eid})",
            redirect_url=f"/config/reports/{report_id}/edit")
    except Exception as e:
        err_msg = _endpoint_unique_error(str(e), data.get("url_path", ""))
        return 200, render_api_endpoint_form_page(
            conn, report_id,
            endpoint=_endpoint_from_form(data,
                                         _normalize_api_url_path(data.get("url_path", "")),
                                         data.get("result_mode", "single")),
            is_edit=False,
            flash=f"错误: {err_msg}")


def handle_api_endpoint_edit(conn, report_id: int, endpoint_id: int,
                              form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑 API 端点表单提交"""
    data = _parse_form_data(form_body)
    try:
        endpoint = db.get_api_endpoint(conn, endpoint_id)
        if not endpoint:
            return 302, "/config?flash=错误: API 接口不存在"
        pf = _parse_endpoint_form(data)
        tpl_err = _validate_json_template(
            pf["template_raw"], pf["result_mode"],
            smart_quote_flags=pf["smart_quote_flags"])
        if tpl_err:
            tmp = _endpoint_from_form(data, pf["url_path"], pf["result_mode"])
            tmp["id"] = endpoint_id
            return 200, render_api_endpoint_form_page(
                conn, report_id, endpoint_id, endpoint=tmp, is_edit=True,
                flash=f"错误: JSON 输出模板无效: {tpl_err}")
        update_kwargs = dict(
            name=pf["name"],
            url_path=pf["url_path"],
            output_format=pf["output_format"],
            columns=pf["columns"] or None,
            filters=pf["filters_str"] or None,
            sorts=pf["sorts_str"] or None,
            row_limit=pf["row_limit"],
            api_key=pf["api_key"],
            allowed_origins=pf["allowed_origins"],
            enabled=pf["enabled"],
            allow_fetch_all=pf["allow_fetch_all"],
            result_mode=pf["result_mode"],
            result_index=pf["result_index"],
            static_cache=pf["static_cache"],
            smart_quote_flags=pf["smart_quote_flags"],
            description=pf["description"],
            session_user=session_user,
        )
        if pf["output_format"] != "csv":
            update_kwargs["json_template"] = pf["template_raw"] or None
        ok = db.update_api_endpoint(conn, endpoint_id, **update_kwargs)
        if ok:
            return _save_or_render(
                data, render_api_endpoint_form_page,
                (conn, report_id, endpoint_id), {},
                success_flash=f"API 接口 {pf['name']} 已更新",
                redirect_url=f"/config/reports/{report_id}/edit")
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        err_msg = _endpoint_unique_error(str(e), data.get("url_path", ""))
        tmp = _endpoint_from_form(data,
                                  _normalize_api_url_path(data.get("url_path", "")),
                                  data.get("result_mode", "single"))
        tmp["id"] = endpoint_id
        return 200, render_api_endpoint_form_page(
            conn, report_id, endpoint_id, endpoint=tmp, is_edit=True,
            flash=f"错误: {err_msg}")


def handle_api_endpoint_delete(conn, report_id: int,
                                endpoint_id: int, session_user=None) -> tuple[int, str]:
    """处理删除 API 端点"""
    endpoint = db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        return 302, "/config?flash=错误: API 接口不存在"
    if int(endpoint.get("report_id", 0)) != report_id:
        return 302, (f"/config/reports/{report_id}/edit"
                       f"?flash=错误: API 接口不属于该报表")
    db.delete_api_endpoint(conn, endpoint_id, session_user=session_user)
    return 302, (f"/config/reports/{report_id}/edit"
                   f"?flash=API 接口 {endpoint['name']} 已删除")


# 真实数据预览最大返回行数（防大结果集拖慢页面）
_PREVIEW_MAX_ROWS = 3


def handle_api_endpoint_preview(conn, report_id: int, endpoint_id: int,
                                form_body: str, session_user=None) -> tuple[int, str, dict]:
    """真实数据预览：用表单未保存值构造临时端点（不落库）执行查询。

    预览复用线上渲染链路（api_handler._execute_api_query + _format_output），
    保证预览即最终输出；行数强制限制为 _PREVIEW_MAX_ROWS 行。

    返回 (200, JSON, {"Content-Type": "application/json; charset=utf-8"})，
    JSON 形如 {"ok": true, "output": <渲染后响应文本>} 或
    {"ok": false, "error": <结构化错误消息（模板非法含行列号）>}。
    """
    json_headers = {"Content-Type": "application/json; charset=utf-8"}

    def fail(message: str) -> tuple:
        return 200, json.dumps({"ok": False, "error": message},
                               ensure_ascii=False), json_headers

    if not (form_body or "").strip():
        # 直接 GET 打开预览地址：无表单值可执行，返回可交互指引页
        return 200, build_api_endpoint_preview_help_html(
            report_id, endpoint_id), {"Content-Type": "text/html; charset=utf-8"}

    endpoint = config_db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        return fail("API 接口不存在")
    if int(endpoint.get("report_id", 0)) != report_id:
        return fail("API 接口不属于该报表")
    if endpoint.get("output_format", "json") == "csv":
        return fail("模板仅 JSON 格式支持，CSV 格式下无法预览")

    data = _parse_form_data(form_body or "")
    result_mode = data.get("result_mode", "single")
    template_raw = data.get("json_template", "") or ""
    smart_quote_flags = int(data.get("smart_quote_flags", 0) or 0)
    tpl_err = _validate_json_template(
        template_raw, result_mode, smart_quote_flags=smart_quote_flags)
    if tpl_err:
        return fail(tpl_err)

    # 构造临时端点：表单未保存值覆盖 DB 配置，不落库
    tmp = dict(endpoint)
    tmp["json_template"] = template_raw or None
    tmp["result_mode"] = result_mode
    tmp["result_index"] = int(data.get("result_index", 0) or 0)
    tmp["smart_quote_flags"] = smart_quote_flags
    columns, filters_str, sorts_str = _parse_rule_json(data.get("rule_json", ""))
    tmp["columns"] = columns or None
    tmp["filters"] = filters_str or None
    tmp["sorts"] = sorts_str or None
    form_row_limit = int(data.get("row_limit", 0) or 0)
    tmp["row_limit"] = min(form_row_limit, _PREVIEW_MAX_ROWS) if form_row_limit > 0 else _PREVIEW_MAX_ROWS

    try:
        result = api_handler._execute_api_query(conn, tmp, "GET", "", {}, {})
    except Exception as e:
        logging.warning("真实数据预览查询执行失败: %s", e)
        return fail(f"查询执行失败: {e}")

    if isinstance(result, tuple):
        status, resp_body, _ = result
        if status != 200:
            try:
                msg = json.loads(resp_body).get("error", resp_body)
            except (json.JSONDecodeError, TypeError, AttributeError):
                msg = resp_body
            return fail(f"查询执行失败: {msg}")
        # result_mode=all 成功：resp_body 已是模板渲染后的最终 JSON
        return 200, json.dumps({"ok": True, "output": resp_body},
                               ensure_ascii=False), json_headers

    status, out_body, _ = api_handler._format_output(
        result.data_rows, result.display_cols, result.total, result.page,
        result.page_size, result.total_pages, result.output_format,
        result.add_bom, result.full, template=tmp["json_template"] or "", meta=None,
        truncated=result.truncated, smart_quote_flags=result.smart_quote_flags)
    if status != 200:
        return fail("预览输出构建失败")
    return 200, json.dumps({"ok": True, "output": out_body},
                           ensure_ascii=False), json_headers


def handle_api_endpoints_request(conn, method: str, path: str, query: str,
                                  form_body: str = None,
                                  session_user=None) -> tuple[int, str, dict]:
    """处理 /config/api-endpoints 请求（独立 API 端点管理页）。"""
    if method == "POST":
        data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
        action = data.get("action", [""])[0]
        endpoint_id = data.get("endpoint_id", [None])[0]
        if action == "delete" and endpoint_id:
            try:
                endpoint_id = int(endpoint_id)
                endpoint = db.get_api_endpoint(conn, endpoint_id)
                if endpoint:
                    db.delete_api_endpoint(conn, endpoint_id, session_user=session_user)
                    flash_msg = "API 接口已删除"
                else:
                    flash_msg = "错误: API 接口不存在"
            except (ValueError, TypeError):
                flash_msg = "错误: 无效的接口 ID"
            return 302, f"/config/api-endpoints?flash={urllib.parse.quote(flash_msg)}", {}
        if action == "toggle" and endpoint_id:
            try:
                endpoint_id = int(endpoint_id)
                endpoint = db.get_api_endpoint(conn, endpoint_id)
                if endpoint:
                    new_enabled = 0 if int(endpoint.get("enabled", 1)) else 1
                    db.update_api_endpoint(conn, endpoint_id, enabled=new_enabled,
                                           session_user=session_user)
                    flash_msg = f"API 接口 {endpoint['name']} 已{'启用' if new_enabled else '禁用'}"
                else:
                    flash_msg = "错误: API 接口不存在"
            except (ValueError, TypeError):
                flash_msg = "错误: 无效的接口 ID"
            return_to = data.get("return_to", [None])[0]
            if return_to and return_to.startswith("/") and not return_to.startswith("//"):
                sep = "&" if "?" in return_to else "?"
                return 302, f"{return_to}{sep}flash={urllib.parse.quote(flash_msg)}", {}
            return 302, f"/config/api-endpoints?flash={urllib.parse.quote(flash_msg)}", {}
        return 302, "/config/api-endpoints", {}

    api_endpoints = db.get_all_api_endpoints(conn)
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)
    flash = qs.get("flash", [None])[0]
    flash_html = build_flash_html(flash) if flash else ""

    base_url = app_config.get_server_base_url()
    body = (render_page_header(title="Web 报表工具 - API 接口", active_nav="api", extra_css=_CONFIG_EXTRA_CSS)
            + flash_html
            + '<h2 style="margin-bottom:0">API 接口管理</h2>'
            + build_api_endpoints_list_html(api_endpoints, show_report_name=True,
                                            base_url=base_url,
                                            key_counts=config_db.get_api_key_counts(conn))
            + render_page_footer())
    return 200, body, {}


def _redirect_or_render(code: int, result: str) -> tuple[int, str, dict]:
    """
    将处理器返回的 (状态码, 结果) 转换为标准返回格式。

    如果是 302 重定向，结果即为 Location；否则为 HTML 响应体。
    对 Location 中的 query 参数进行 URL 编码，确保非 ASCII 字符（如中文）正确传输。
    """
    if code == 302 and result.startswith("/"):
        # URL 编码 query 参数（flash 消息可能包含中文）
        if "?" in result:
            path, qs = result.split("?", 1)
            params = urllib.parse.parse_qs(qs, keep_blank_values=True)
            encoded_qs = urllib.parse.urlencode(params, doseq=True)
            encoded_url = f"{path}?{encoded_qs}"
        else:
            encoded_url = result
        return 302, encoded_url, {"Location": encoded_url}
    return code, result, {}
