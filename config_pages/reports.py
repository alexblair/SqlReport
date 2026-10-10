"""config.py 拆分：报表配置实体：表单构建（HTML/JS）、列表/表单页与增删改复制（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import urllib.parse
import db
import config_db
import app_config
from query_executor import sql_contains_write
from render import _icon, build_config_filter_box_html, render_page_header, render_page_footer, build_flash_html, _SQL_HIGHLIGHT_JS, _SQL_FORMATTER_JS, build_api_endpoints_list_html, build_report_schedule_summary_html, _WARN_BOX_STYLE, _escape
import markdown_render
from config_pages.categories import _render_cat_opts, _render_category_section_parts

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

onReady(function() {
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
                       allow_all_output=0, max_rows=100000,
                       keepalive_enabled=0, keepalive_ahead_seconds=0,
                       sched_summary_html=''):
    """构建报表表单完整 HTML（含 SQL 编辑器 JS + 查看/预览按钮）。

    allow_write: 「允许执行写操作」当前值（存量 1、新建 0）。
    sql_has_write: SQL 是否含写语句。含写时显示开关 checkbox 与警示；
                   否则仅渲染隐藏 allow_write=0（保底提交，维持新建默认 0）。
    allow_all_output: 「允许全部输出」当前值（存量 1、新建 0）。
    max_rows: 全量输出关闭时的截断行数上限（默认 100000，仅关闭全量输出时生效）。
    keepalive_enabled / keepalive_ahead_seconds: 缓存保活折叠区当前值（scheduler T4）。
    sched_summary_html: 「④ 调度与保活」卡内的关联任务只读摘要
                         （render.build_report_schedule_summary_html 产出）。
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
        allow_write_html = (f'<label class="span-full" style="display:flex;align-items:center;gap:8px">'
                            f'<input type="hidden" name="allow_write" value="0">'
                            f'<input type="checkbox" name="allow_write" value="1"{aw_checked}>'
                            f'<span>允许执行写操作</span>'
                            f'<span>（SQL 含写语句；未开启时将拒绝执行）</span>'
                            f'</label>')
        if not allow_write:
            allow_write_html += ('<div class="flash-warn span-full" style="'
                                 + _WARN_BOX_STYLE + '">'
                                 f'{_icon("alert")} 该 SQL 包含写操作语句，未开启时将拒绝执行</div>')
    else:
        allow_write_html = '<input type="hidden" name="allow_write" value="0">'
    # PH-07 全量输出护栏：checkbox + max_rows 输入（hidden 0 保底；开启时保存前 confirm）
    aao_checked = ' checked' if allow_all_output else ''
    if allow_all_output:
        aao_confirm = ' onsubmit="return confirm(\'确定开启全部输出？当查询结果超过限制行数时将不截断，可能占用大量内存与网络带宽。\')"'
    else:
        aao_confirm = ''
    allow_all_output_html = (
        f'<label style="display:flex;align-items:center;gap:8px">'
        f'<input type="hidden" name="allow_all_output" value="0">'
        f'<input type="checkbox" name="allow_all_output" value="1"{aao_checked}>'
        f'<span>允许全部输出</span>'
        f'<span>（关闭时查询结果超过限制行数将被截断，仅显示前 N 行）</span>'
        f'</label>'
        f'<label>全量输出截断上限（行）:'
        f'<input type="number" name="max_rows" value="{max_rows}" min="1" step="1">'
        f'<span>仅关闭「允许全部输出」时生效</span>'
        f'</label>')
    # 缓存保活折叠区（scheduler T4）
    ka_checked = ' checked' if keepalive_enabled else ''
    keepalive_html = f"""
  <details class="span-full">
    <summary style="cursor:pointer">{_icon("refresh")} 缓存保活</summary>
    <div>
      <label style="display:flex;align-items:center;gap:8px">
        <input type="hidden" name="keepalive_enabled" value="0">
        <input type="checkbox" name="keepalive_enabled" value="1"{ka_checked}>
        <span>启用缓存保活</span>
        <span>（需同时勾选上方「启用 Redis 缓存」且 Redis 可用；到期前自动重建快照，避免首个请求变慢）</span>
      </label>
      <label>提前重建（秒）:
        <input type="number" name="keepalive_ahead_seconds" value="{keepalive_ahead_seconds}" min="0" step="1">
        <span>快照剩余有效期不足该秒数时提前后台重建；0 = 不保活</span>
      </label>
    </div>
  </details>"""
    # 页面头（spec page-report-edit）：crumb + h1 + 查看/预览（预览按钮留在 form 内
    # 以维持 previewReport(this.form) 协议，故 page-head 整体置于主 form 起始处）
    crumb_tail = {"编辑报表": "报表编辑", "新增报表": "报表新增",
                  "复制报表": "报表复制"}.get(title, title)
    return f"""<form method="post" action="{action_url}" class="config-form" data-action="{action_url}"{aao_confirm}>
  {hidden_id}
  <div class="page-head span-full">
    <div>
      <div class="crumb"><a href="/config">配置</a> › {crumb_tail}</div>
      <h1>{title}</h1>
      <div class="sub">分区表单：基础 → SQL → 缓存护栏 → 调度与保活 → API 端点</div>
    </div>
    <div class="actions">{view_btn}{preview_btn}</div>
  </div>
  <div class="grid-2 span-full">
    <div>
      <div class="card">
        <div class="card-head"><div class="form-section">① 基础</div></div>
        <label>报表名称: <input type="text" name="name" value="{name}" required></label>
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
        <label>默认分页大小: <input type="number" name="default_page_size" value="{default_page_size}" min="1" required></label>
        <label class="span-full">备注（非必填）:
          <textarea name="memo" class="sql-textarea" placeholder="输入备注信息... 支持 Markdown（标题/列表/代码块/```mermaid 流程图）" rows="4" style="min-height:80px">{memo_val}</textarea>
          <div class="memo-preview md-body" id="memo-preview"></div>
          <div class="sql-toolbar">
            <button type="button" class="btn btn-outline btn-sm" onclick="toggleMemoPreview(this)">预览备注</button>
          </div>
        </label>
      </div>
    </div>
    <div>
      <div class="card">
        <div class="card-head"><div class="form-section">② SQL</div></div>
        <label class="span-full">SQL 查询语句:
          <textarea name="sql_query" class="sql-textarea sql-editor" data-tab-indent="1" placeholder="输入 MySQL 语句..." spellcheck="false" rows="14">{sql_query}</textarea>
          <div class="sql-preview"></div>
          <div class="sql-toolbar">
            <button type="button" class="btn btn-outline btn-sm" onclick="formatSQL(this)">格式化 SQL</button>
            <button type="button" class="btn btn-outline btn-sm" onclick="togglePreview(this)">显示高亮</button>
          </div>
        </label>
        <label class="span-full">结果名称（每行一个，顺序对应 SELECT 返回；不填则自动编号）:
          <textarea name="result_names" class="sql-textarea" placeholder="例如:&#10;汇总指标&#10;按城市分布&#10;商品TOP10" rows="3" style="min-height:60px">{_escape(result_names_val)}</textarea>
        </label>
      </div>
      <div class="card">
        <div class="card-head"><div class="form-section">③ 缓存与护栏</div></div>
        <label style="display:flex;align-items:center;gap:8px">
          <input type="hidden" name="prefer_cache" value="0">
          <input type="checkbox" name="prefer_cache" value="1"{cache_checked}>
          <span>启用 Redis 缓存</span>
          <span>（优先使用缓存数据加速访问）</span>
        </label>
        <label>缓存 TTL（小时）:
          <input type="number" name="cache_ttl_hours" value="{cache_ttl_hours}" min="0" step="1">
          <span>0 = 永不过期</span>
        </label>
        {allow_write_html}
        {allow_all_output_html}
      </div>
      <div class="card">
        <div class="card-head">
          <div class="form-section">④ 调度与保活</div>
          <div class="actions">
            <a class="btn btn-outline btn-sm" href="/config/scheduler">完整任务管理 →</a>
          </div>
        </div>
        {sched_summary_html}
        {keepalive_html}
      </div>
    </div>
  </div>
  <div class="formbar span-full">
    <a href="/config/reports" class="cancel">← 取消</a>
    <div class="right">
      <button type="submit" name="action" value="save_close" class="btn btn-outline">保存并关闭</button>
      <button type="submit" name="action" value="save" class="btn btn-primary">保存</button>
    </div>
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
</script>"""


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

    prefer_cache = config._tolerant_int(report.get("prefer_cache"), 1) if report else 1
    # 新建报表默认 TTL 1 小时（避免永不过期导致长期看到过期数据）；编辑/复制沿用原值
    cache_ttl_hours = config._tolerant_int(report.get("cache_ttl_hours"), 1) if report else 1
    # PH-05 写护栏：SQL 含写 → 显示开关（存量默认 1 保持现状；新建默认 0）
    raw_sql = report["sql_query"] if report else ""
    allow_write = config._tolerant_int(report.get("allow_write"), 1) if report else 0
    sql_has_write = sql_contains_write(raw_sql)
    # PH-07 全量输出护栏：存量默认 1 保持现状；新建默认 0；max_rows 默认 100000
    allow_all_output = config._tolerant_int(report.get("allow_all_output"), 1) if report else 0
    max_rows = config._tolerant_int(report.get("max_rows"), 100000) if report else 100000
    # scheduler T4：缓存保活回显（编辑/复制沿用原值；新建默认关）
    keepalive_enabled = config._tolerant_int(report.get("keepalive_enabled"), 0) if report else 0
    keepalive_ahead = (config._tolerant_int(report.get("keepalive_ahead_seconds"), 600)
                       if report else 600)

    # ④ 调度与保活卡：复用 get_all_schedules 的 report_ids 过滤出本报表关联任务
    sched_summary_html = ""
    if is_edit and report and report.get("id"):
        try:
            _rid = report["id"]
            _scheds = [s for s in db.get_all_schedules(conn)
                       if _rid in (s.get("report_ids") or [])]
        except Exception:
            _scheds = []
        sched_summary_html = build_report_schedule_summary_html(_rid, _scheds)

    return _report_form_html(title, action_url, name, sql_query, default_page_size,
                              required_attr, no_pool_opt, pool_options, category_options, memo_val,
                              result_names_val=result_names_val,
                              is_edit=is_edit, report_id=report.get("id") if report else None,
                              prefer_cache=prefer_cache, cache_ttl_hours=cache_ttl_hours,
                              allow_write=allow_write, sql_has_write=sql_has_write,
                              allow_all_output=allow_all_output, max_rows=max_rows,
                              keepalive_enabled=keepalive_enabled,
                              keepalive_ahead_seconds=keepalive_ahead,
                              sched_summary_html=sched_summary_html)


def render_reports_page(conn, flash: str = None) -> str:
    """渲染报表管理独立页（PH-13：分类树 + 报表列表 + 批量操作；分类管理已并入本页）

    批次5#15：页面主体包一层 id="sec-reports" 锚点，供移动/保存操作回跳定位。
    批次6#21：flash 之下、第一个区块之上插入纯前端检索过滤框
    （render.build_config_filter_box_html，公共 JS initConfigFilter 生效）。
    """
    flash_html = build_flash_html(flash) if flash else ""
    manage_html, tables_html = _render_category_section_parts(conn)
    header = render_page_header(title="SqlReport - 报表管理",
                                active_nav="config-reports",
                                extra_css=config._REPORTS_EXTRA_CSS,
                                nav_badges=config._nav_badges(conn))
    return (header
            + '<div class="page-head"><div>'
            + '<h1>报表配置</h1>'
            + '<div class="sub">报表管理 · 左栏分类树，右栏报表列表；勾选行后浮出批量操作</div>'
            + '</div><div class="actions">'
            # 确认稿 r3：列表/卡片全局开关（作用于全部层级；默认列表、localStorage 记忆）
            # 复用公共 .segment 分段控件（_COMMON_CSS），不另起一套
            + '<div class="segment" id="rpt-view-seg" role="group" aria-label="视图切换">'
            + '<button type="button" data-view="list" class="active" '
            + 'onclick="setReportsView(\'list\', true)">列表视图</button>'
            + '<button type="button" data-view="card" '
            + 'onclick="setReportsView(\'card\', true)">卡片视图</button>'
            + '</div>'
            + '<a class="btn btn-secondary" href="/config/categories/add">+ 新增分类</a>'
            + '<a class="btn btn-primary" href="/config/reports/add">+ 新增报表</a>'
            + '</div></div>'
            + flash_html
            + build_config_filter_box_html()
            + '<div id="sec-reports"><div class="split">'
            + '<aside class="card">' + manage_html + '</aside>'
            + '<div>' + tables_html + '</div>'
            + '</div></div>'
            + render_page_footer())


def render_report_form_page(conn, report_id: int = None, flash: str = None, copy_mode: bool = False,
                            report: dict = None) -> str:
    """渲染新增/编辑/复制报表表单页

    report: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    echo_report = report is not None
    if report is None:
        report = db.get_report(conn, report_id) if report_id else None
    if report_id and not report:
        return config.render_overview(conn, flash="错误: 报表不存在")
    is_edit = report_id is not None and not copy_mode
    flash_html = build_flash_html(flash) if flash else ""
    body = render_page_header(title="SqlReport - 配置", active_nav="config-reports", extra_css=config._CONFIG_MD_EXTRA_CSS)
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
        # 缓存保活（scheduler T4）：hidden 0 + checkbox 1；ahead 非法回退 600
        "keepalive_enabled": int(data.get("keepalive_enabled", 0) or 0),
        "keepalive_ahead_seconds": max(
            0, app_config.safe_int(data.get("keepalive_ahead_seconds"), 600)),
    }


def _report_from_form(data: dict, report_id: int = None) -> dict:
    """从表单数据构造临时报表 dict（保存失败时表单回显用户原输入）。"""
    report = {
        "name": data.get("name", ""),
        "sql_query": data.get("sql_query", ""),
        "default_page_size": data.get("default_page_size", "20"),
        "pool_id": config._tolerant_int(data.get("pool_id")),
        "category_id": config._tolerant_int(data.get("category_id")),
        "memo": data.get("memo", ""),
        "result_names": data.get("result_names", ""),
        "prefer_cache": config._tolerant_int(data.get("prefer_cache"), 1),
        "cache_ttl_hours": data.get("cache_ttl_hours", "0"),
        "allow_write": config._tolerant_int(data.get("allow_write"), 0),
        "allow_all_output": config._tolerant_int(data.get("allow_all_output"), 0),
        "max_rows": config._tolerant_int(data.get("max_rows"), 100000),
    }
    if report_id is not None:
        report["id"] = report_id
    return report


def handle_report_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增报表表单提交

    遵循「保存」/「保存并关闭」双按钮业务逻辑：
    - action=save         → 保存后返回 200，停留在编辑页（可继续编辑）
    - action=save_close   → 保存后 302 返回列表页（默认）
    """
    data = config._parse_form_data(form_body)
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
                            keepalive_enabled=rf["keepalive_enabled"],
                            keepalive_ahead_seconds=rf["keepalive_ahead_seconds"],
                            session_user=session_user)
        return config._save_or_render(
            data, render_report_form_page, (conn, rid), {},
            success_flash=f"报表 {data['name']} 已创建 (id={rid})",
            redirect_url="/config/reports", anchor=f"report-{rid}")
    except Exception as e:
        return 200, render_report_form_page(conn, flash=f"错误: {e}",
                                            report=_report_from_form(data))


def handle_report_edit(conn, report_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑报表表单提交"""
    data = config._parse_form_data(form_body)
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
                              keepalive_enabled=rf["keepalive_enabled"],
                              keepalive_ahead_seconds=rf["keepalive_ahead_seconds"],
                              session_user=session_user)
        if ok:
            return config._save_or_render(
                data, render_report_form_page, (conn, report_id), {},
                success_flash=f"报表 {data['name']} 已更新",
                redirect_url="/config/reports", anchor=f"report-{report_id}")
        return 302, "/config/reports?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_report_form_page(conn, report_id, flash=f"错误: {e}",
                                            report=_report_from_form(data, report_id))


def handle_report_copy(conn, report_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理复制报表（新增一个同名+副本的报表）

    遵循「保存」/「保存并关闭」双按钮业务逻辑，与新建报表一致。
    """
    data = config._parse_form_data(form_body)
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
                            keepalive_enabled=rf["keepalive_enabled"],
                            keepalive_ahead_seconds=rf["keepalive_ahead_seconds"],
                            session_user=session_user)
        # 复制报表不继承定时任务（新报表从零配置，避免双跑）
        return config._save_or_render(
            data, render_report_form_page, (conn, rid), {},
            success_flash=f"报表 {data['name']} 已创建（复制自 id={report_id}）",
            redirect_url="/config/reports", anchor=f"report-{rid}")
    except Exception as e:
        return 200, render_report_form_page(conn, report_id, flash=f"错误: {e}", copy_mode=True,
                                            report=_report_from_form(data, report_id))


def handle_report_delete(conn, report_id: int, session_user=None) -> tuple[int, str]:
    """处理删除报表。

    批次2#5（spec ux-optimization）：flash 披露一并清理的 API 端点数
    （级联删除在 db.delete_report 内完成，含静态缓存失效）。
    """
    rpt = db.get_report(conn, report_id)
    if not rpt:
        return 302, "/config/reports?flash=错误: 报表不存在"
    ep_count = len(db.get_api_endpoints_by_report(conn, report_id))
    db.delete_report(conn, report_id, session_user=session_user)
    if ep_count > 0:
        return 302, (f"/config/reports?flash=报表 {rpt['name']} 已删除"
                     f"（含 {ep_count} 个 API 接口及其静态缓存）")
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
