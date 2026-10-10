"""config.py 拆分：报表分类配置实体：区块渲染、表单页与增删改（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import urllib.parse
import db
from render import build_category_opts_html, build_category_section_html, render_page_header, render_page_footer, build_flash_html, _escape

def _render_cat_opts(nodes, depth, cur_cat_id):
    """递归生成分类选项 HTML（树形缩进）"""
    return build_category_opts_html(nodes, depth, cur_cat_id)


def _render_category_section_parts(conn):
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
    # 定时徽标数据源（scheduler T4）：report_id → 任务行（仅启用任务出 ⏰）
    schedules_map: dict[int, dict] = {}
    try:
        for s in db.get_all_schedules(conn):
            for rid in s.get("report_ids") or []:
                schedules_map[rid] = s
    except Exception:
        schedules_map = {}
    return build_category_section_html(cat_reports, unclassified_reports, all_cats,
                                       all_reports, pools, cat_tree,
                                       api_endpoints_map=api_endpoints_map,
                                       schedules_map=schedules_map,
                                       split_parts=True)


def _render_category_section(conn) -> str:
    """（兼容）分类段整体输出 = 左栏 + 右表。"""
    manage_html, tables_html = _render_category_section_parts(conn)
    return manage_html + tables_html


def render_category_form_page(conn, category_id: int = None, flash: str = None, cat: dict = None) -> str:
    """渲染新增/编辑分类表单页

    cat: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    if cat is None:
        cat = db.get_category(conn, category_id) if category_id else None
    if category_id and not cat:
        return config.render_overview(conn, flash="错误: 分类不存在")
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
        # 缩进用全角 U+3000：半角空格在 <option> 中会被 HTML 折叠为不可见（D4 裁决）
        prefix = "\u3000" * config._get_depth(c, all_cats)
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
    return (render_page_header(title="SqlReport - 配置", active_nav="config-reports", extra_css=config._CONFIG_EXTRA_CSS)
            + flash_html + form_html + render_page_footer())


def _category_from_form(data: dict, category_id: int = None) -> dict:
    """从表单数据构造临时分类 dict（保存失败时表单回显用户原输入）。"""
    cat = {
        "name": data.get("name", ""),
        "parent_id": data.get("parent_id", ""),
    }
    if category_id is not None:
        cat["id"] = category_id
    return cat


def handle_category_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增分类"""
    data = config._parse_form_data(form_body)
    try:
        parent_id = int(data["parent_id"]) if data.get("parent_id") else None
        cid = db.add_category(conn, data["name"], parent_id, session_user=session_user)
        return 302, f"/config/reports?flash=分类 {data['name']} 已创建"
    except Exception as e:
        return 200, render_category_form_page(conn, flash=f"错误: {e}",
                                              cat=_category_from_form(data))


def handle_category_edit(conn, category_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑分类"""
    data = config._parse_form_data(form_body)
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
