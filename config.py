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
import time
import urllib.parse
import db
import config_db
import auth
import branding
import redis_cache
import static_cache
import api_handler
import app_config
import preset_cases
import html as html_mod
from json_template import ALL_KEYS, SINGLE_KEYS, validate_template
from query_executor import sql_contains_write
# 从 render 模块导入纯 HTML 渲染函数（无 DB 调用）
from render import (
    _icon,
    build_pool_form_html,
    build_user_form_html,
    build_category_opts_html,
    build_pool_section_html,
    build_user_section_html,
    build_category_section_html,
    build_category_manage_section_html,
    build_config_filter_box_html,
    render_page_header,
    render_page_footer,
    build_flash_html,
    _SQL_HIGHLIGHT_JS,
    _SQL_FORMATTER_JS,
    build_api_endpoints_list_html,
    build_api_endpoint_form_html,
    build_api_endpoint_preview_help_html,
    build_scheduler_page_html,
    build_scheduler_task_form_html,
    build_report_schedule_summary_html,
    _build_desc_summary_html,
    _WARN_BOX_STYLE,
    _MD_CSS,
    _escape,
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
    r"(?:/(add|batch-pool|batch-set-category|batch-cache|batch-delete|memo-preview|test)"
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
        # 定时任务管理页与操作（scheduler T4；独立前缀，不进主正则）
        if path in ("/config/scheduler", "/config/scheduler/"):
            return {"section": "scheduler", "action": "list",
                    "id": None, "report_id": None, "endpoint_id": None}
        if path in ("/config/scheduler/new", "/config/scheduler/new/"):
            return {"section": "scheduler", "action": "new",
                    "id": None, "report_id": None, "endpoint_id": None}
        m2 = re.match(r"^/config/scheduler/(\d+)/edit$", path)
        if m2:
            return {"section": "scheduler", "action": "edit",
                    "id": int(m2.group(1)), "report_id": None,
                    "endpoint_id": None}
        m = re.match(r"^/config/scheduler/(run|toggle|delete)/(\d+)$", path)
        if m:
            return {"section": "scheduler", "action": m.group(1),
                    "id": int(m.group(2)), "report_id": None,
                    "endpoint_id": None}
        if path == "/config/scheduler/save":
            return {"section": "scheduler", "action": "save", "id": None,
                    "report_id": None, "endpoint_id": None}
        # 连接池「测试连接」（批次3#12）：POST 表单试连，不落库
        if path == "/config/pools/test":
            return {"section": "pools", "action": "test", "id": None,
                    "report_id": None, "endpoint_id": None}
        # 站点标识保存（spec site-branding）
        if path == "/config/site-branding":
            return {"section": "site-branding", "action": "save", "id": None,
                    "report_id": None, "endpoint_id": None}
        # 新增测试用例（预设数据夹具一键导入；仅 DEBUG 模式可用）
        if path == "/config/test-cases/import":
            return {"section": "test-cases", "action": "import", "id": None,
                    "report_id": None, "endpoint_id": None}
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
    return {"section": section, "action": "list", "id": None,
            "report_id": None, "endpoint_id": None}


# ---------------------------------------------------------------------------
# HTML 模板片段
# ---------------------------------------------------------------------------

_CONFIG_EXTRA_CSS = ""  # 已并入 render._COMMON_CSS 第 22 节（保留变量名兼容既有引用）


# 报表配置页专属样式（确认稿 r3：列表/卡片双视图 + 视觉重排）。
# 作用域一律限定在 #sec-reports 内，避免影响连接池/用户等其他配置页的同名 class。
_REPORTS_EXTRA_CSS = ""  # 报表配置页样式已并入 render._COMMON_CSS


# 报表表单页等含 Markdown 渲染能力的页面：基础 config CSS + 代码高亮 CSS
# + Markdown 排版 CSS（_MD_CSS 必须在 _CONFIG_EXTRA_CSS 之后，保证列表缩进等规则生效）
_CONFIG_MD_EXTRA_CSS = (_CONFIG_EXTRA_CSS + markdown_render.codehilite_css()
                        + _MD_CSS)


def _link_btn(url: str, label: str, cls: str = "btn btn-outline btn-sm") -> str:
    """生成链接按钮"""
    return f'<a href="{_escape(url)}" class="{cls}">{_escape(label)}</a>'


def handle_import_test_cases(conn, session_user=None) -> tuple[int, str, dict]:
    """【新增测试用例】按钮后端：将预设数据夹具 upsert 导入当前配置库。

    仅 DEBUG 模式可用（app_config.debug.json 激活时）。非 DEBUG 模式直接
    拒绝，避免污染生产配置库。导入采用「按名称 upsert」语义：同名覆盖更新，
    不同名新增；不对库内未出现在夹具中的数据做删除。
    """
    if not app_config.is_debug_mode():
        msg = "错误: 新增测试用例仅在 DEBUG 模式下可用"
        return 302, f"/config?flash={urllib.parse.quote(msg)}", {}
    # DEBUG 专属测试 MySQL（enable 且配置了 host 才返回非空）
    test_mysql = app_config.get_test_mysql_config()
    try:
        result = preset_cases.import_preset_from_file(
            conn, test_mysql_cfg=test_mysql)
    except FileNotFoundError:
        msg = "错误: 未找到预设测试用例文件 tests/preset_test_cases.json"
        return 302, f"/config?flash={urllib.parse.quote(msg)}", {}
    except Exception as e:  # noqa: BLE001
        msg = f"错误: 导入预设测试用例失败: {e}"
        return 302, f"/config?flash={urllib.parse.quote(msg)}", {}

    added = result["added"]
    updated = result["updated"]
    errs = result.get("errors") or []
    parts = [f"已新增 {added} 条、覆盖更新 {updated} 条配置数据"]
    mysql = result.get("test_mysql")
    if mysql:
        if mysql.get("ok"):
            tbls = mysql.get("tables") or []
            parts.append(
                f"测试 MySQL 库 {mysql.get('database') or '(默认)'} "
                f"已建表 {len(tbls)} 张并初始化")
        else:
            parts.append("测试 MySQL 初始化未完成（详见日志）")
    if errs:
        parts.append(f"{len(errs)} 条警告（详见日志）")
        for e in errs[:20]:
            logging.warning("[preset_cases] %s", e)
    flash = "成功: " + "，".join(parts)
    return 302, f"/config?flash={urllib.parse.quote(flash)}", {}


def _nav_badges(conn) -> dict:
    """侧栏徽标计数（概览/列表页共用；逐项容错——任一表缺失不影响其它计数）。"""
    badges = {}
    for key, fn in (
        ("config-reports", lambda: len(db.get_all_reports(conn))),
        ("config-pools", lambda: len(db.get_all_pools(conn))),
        ("config-users", lambda: len(db.get_all_users(conn))),
        ("api", lambda: len(db.get_all_api_endpoints(conn))),
        ("scheduler", lambda: config_db.count_schedules(conn)),
    ):
        try:
            badges[key] = fn()
        except Exception:
            pass
    return badges


def render_overview(conn, flash: str = None,
                    current_username: str = None) -> str:
    """概览仪表盘：统计磁贴 + 快捷入口 + 系统状态 + 站点标识（T7.5 收窄）。

    池/用户 CRUD 已迁至独立列表页（/config/pools、/config/users）。
    current_username 保留签名兼容（用户列表已迁出）。
    """
    flash_html = build_flash_html(flash) if flash else ""
    badges = _nav_badges(conn)
    try:
        n_pools = badges.get("config-pools", 0)
        n_users = badges.get("config-users", 0)
        n_reports = badges.get("config-reports", 0)
        n_cats = len(db.get_all_categories(conn))
        n_api = badges.get("api", 0)
        n_sched = badges.get("scheduler", 0)
    except Exception:
        n_pools = n_users = n_reports = n_cats = n_api = n_sched = 0

    # 系统状态
    try:
        sched_on = bool(app_config.get_config().get("scheduler", {}).get("enable", False))
    except Exception:
        sched_on = False
    try:
        import redis_cache as _rc
        redis_ok = bool(_rc.redis_available())
    except Exception:
        redis_ok = False
    try:
        eng = (app_config.get_active_db_config() or {}).get("engine") or               ("mysql" if (app_config.get_active_db_config() or {}).get("host") else "sqlite")
    except Exception:
        eng = "sqlite"

    sched_badge = ('<span class="badge badge-ok">调度启用</span>' if sched_on
                   else '<span class="badge badge-warn">调度停用</span>')
    redis_badge = ('<span class="badge badge-ok">缓存可用</span>' if redis_ok
                   else '<span class="badge badge-neutral">缓存未启用</span>')

    onboarding = ""
    if n_pools == 0:
        onboarding = (
            '<div class="banner banner-info">'
            '<div><strong>首次使用？三步开始：</strong>'
            '① 添加连接池 → ② 创建报表 → ③ 发布 API 接口</div>'
            '<a class="btn btn-primary btn-sm act" href="/config/pools/add">立即添加连接池</a>'
            '</div>')

    test_cases_card = ""
    if app_config.is_debug_mode():
        test_cases_card = """<div class="card">
<div class="card-head"><h2>导入演示数据（DEBUG）</h2></div>
<p class="muted">将预设测试用例按名称导入当前 DEBUG 配置库，同名覆盖。用于功能验收与脚本测试。</p>
<form method="post" action="/config/test-cases/import">
<button type="submit" class="btn btn-primary" onclick="return confirm('确认将预设测试用例导入当前 DEBUG 配置库？同名数据将被覆盖更新。')">导入演示数据</button>
</form></div>"""

    body = render_page_header(title="SqlReport - 概览", active_nav="config",
                              extra_css=_CONFIG_EXTRA_CSS, nav_badges=badges)
    body += (
        '<div class="page-head"><div><h1>概览</h1>'
        '<div class="sub">系统规模、快捷入口与运行状态</div></div>'
        '<div class="actions">'
        '<a class="btn btn-secondary" href="#branding-section">站点标识设置</a></div></div>'
        + flash_html + onboarding)
    body += (
        '<div class="grid-stat">'
        f'<div class="stat-tile"><div class="num">{n_reports}</div><div class="lbl">个报表</div>'
        '<a href="/config/reports">前往配置 →</a></div>'
        f'<div class="stat-tile"><div class="num">{n_cats}</div><div class="lbl">个分类</div>'
        '<a href="/config/reports">分类管理 →</a></div>'
        f'<div class="stat-tile"><div class="num">{n_api}</div><div class="lbl">个 API 接口</div>'
        '<a href="/config/api-endpoints">管理接口 →</a></div>'
        f'<div class="stat-tile"><div class="num">{n_sched}</div><div class="lbl">个定时任务</div>'
        '<a href="/config/scheduler">查看任务 →</a></div>'
        f'<div class="stat-tile"><div class="num">{n_pools}</div><div class="lbl">个连接池</div>'
        '<a href="/config/pools">管理连接池 →</a></div>'
        f'<div class="stat-tile"><div class="num">{n_users}</div><div class="lbl">个用户</div>'
        '<a href="/config/users">管理用户 →</a></div>'
        '</div>')
    body += (
        '<div class="card"><div class="card-head"><h2>快捷入口</h2></div>'
        '<div class="grid-3">'
        '<a class="btn btn-secondary" href="/config/reports">管理报表</a>'
        '<a class="btn btn-secondary" href="/config/pools">连接池</a>'
        '<a class="btn btn-secondary" href="/config/users">用户</a>'
        '<a class="btn btn-secondary" href="/config/reports#sec-categories">管理分类</a>'
        '<a class="btn btn-secondary" href="/config/api-endpoints">API 接口</a>'
        '<a class="btn btn-secondary" href="/config/scheduler">定时任务</a>'
        '<a class="btn btn-secondary" href="/audit">审计日志</a>'
        '</div></div>')
    # grid-2：左=系统状态，右=导入演示数据（DEBUG，原型 page-config 口径）
    body += (
        '<div class="grid-2"><div class="card">'
        '<div class="card-head"><h2>系统状态</h2></div>'
        f'<div style="display:flex;flex-direction:column;gap:10px">'
        f'<div style="display:flex;gap:10px;align-items:center">{sched_badge}'
        '<span class="muted">定时调度状态（scheduler.enable）</span></div>'
        f'<div style="display:flex;gap:10px;align-items:center">{redis_badge}'
        '<span class="muted">Redis 三层缓存（不可用时自动直连数据库）</span></div>'
        f'<div style="display:flex;gap:10px;align-items:center">'
        f'<span class="badge badge-neutral">{_escape(str(eng).upper())}</span>'
        '<span class="muted">配置存储引擎</span></div>'
        f'<div class="muted">已配置 {n_api} 个 API 接口 · 共 {n_reports} 个报表、{n_cats} 个分类</div>'
        '</div></div>'
        + test_cases_card
        + '</div>')
    # 站点标识独立成行（移出 grid-2，避免卡中卡）
    body += _render_branding_anchor()
    body += render_page_footer()
    return body


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


# ---------------------------------------------------------------------------
# 表单提交处理
# ---------------------------------------------------------------------------


def _parse_form_data(form_body: str) -> dict:
    """解析 URL 编码的表单数据"""
    return app_config.parse_form_urlencoded(form_body)


def _save_or_render(data: dict, render_fn, args: tuple, kwargs: dict,
                    success_flash: str, redirect_url: str,
                    anchor: str = None) -> tuple[int, str]:
    """统一「保存 / 保存并关闭」双按钮保存模式。

    - action=save       → 200 + 渲染表单页（flash=success_flash，留在当前页）
    - action=save_close → 302 + redirect_url?flash=success_flash（默认，返回上级）

    anchor（批次5#16，spec ux-optimization）：可选锚点 id（如 report-3），
    拼接在 query 之后（fragment 必须位于 URL 最末），供前端定位并高亮
    刚保存的行。
    """
    action = data.get("action", "save_close")
    if action == "save":
        return 200, render_fn(*args, flash=success_flash, **kwargs)
    fragment = f"#{anchor}" if anchor else ""
    return 302, f"{redirect_url}?flash={success_flash}{fragment}"


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


def _normalize_api_url_path(path: str) -> str:
    """
    规范化 API URL 路径。

    表单提交的 url_path 不包含 /api/ 前缀（前缀在 UI 上固定显示），
    此函数确保存储到 DB 时补全为 /api/<suffix> 格式。
    同时兼容旧格式（已有 /api/ 前缀）以确保向后兼容。
    """
    return app_config.ensure_api_prefix(path)


def _parse_rule_json(rule_json_str: str) -> tuple[str, str, str, str]:
    """
    解析规则 JSON 字符串，拆出 columns/filters/sorts/nested_filter 四个字段。

    返回:
        (columns, filters_json_str, sorts_json_str, nested_filter_json_str)
        nested_filter_json_str 为嵌套筛选规则 JSON 字符串（不含 key 包装），
        空规则为 ""。
    """
    columns = ""
    filters_str = ""
    sorts_str = ""
    nested_filter_str = ""
    if not rule_json_str or not rule_json_str.strip():
        return columns, filters_str, sorts_str, nested_filter_str
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
    nf_raw = rules.get("nested_filter")
    if nf_raw:
        nested_filter_str = json.dumps(nf_raw, ensure_ascii=False) if isinstance(nf_raw, (dict, list)) else str(nf_raw)
    return columns, filters_str, sorts_str, nested_filter_str


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
        return 200, render_overview(conn, flash,
                                    current_username=session_user), {}

    # ---- 定时任务管理（独立前缀，scheduler T4）----
    if route["section"] == "scheduler":
        return handle_scheduler_request(conn, method, path, query,
                                        form_body=form_body,
                                        session_user=session_user)

    # ---- 表单页面 (GET) ----
    if method == "GET":
        if route["action"] == "list":
            if route["section"] == "pools":
                return 200, render_pools_page(conn, flash), {}
            if route["section"] == "users":
                return 200, render_users_page(conn, flash), {}
            if route["section"] == "reports":
                return 200, render_reports_page(conn, flash), {}
            if route["section"] == "categories":
                return 200, render_reports_page(conn, flash), {}
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

    # 站点标识保存（spec site-branding；/config 路由 needs_auth 已拦截未登录）
    if (method == "POST" and route["section"] == "site-branding"
            and route["action"] == "save"):
        return handle_site_branding_save(conn, form_body or "",
                                         session_user=session_user)

    # 新增测试用例：预设数据夹具一键导入（仅 DEBUG 模式；needs_auth 已拦截未登录）
    if (method == "POST" and route["section"] == "test-cases"
            and route["action"] == "import"):
        return handle_import_test_cases(conn, session_user=session_user)

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
            if route["action"] == "test":
                # 批次3#12：测试连接（不保存配置，仅验证连通性）；
                # handler 返回 (code, body, headers)：AJAX 时为 JSON（不跳转），
                # 非 AJAX 时为 302 跳转回表单页（兼容无 JS 环境）
                code, body, headers = handle_pool_test(conn, form_body or "",
                                                        session_user=session_user)
                return code, body, headers
            if route["action"] == "add":
                code, result = handle_pool_add(conn, form_body or "", session_user=session_user)
            elif route["action"] == "edit" and route["id"]:
                code, result = handle_pool_edit(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "copy" and route["id"]:
                code, result = handle_pool_copy(conn, route["id"], form_body or "", session_user=session_user)
            elif route["action"] == "delete" and route["id"]:
                code, result = handle_pool_delete(conn, route["id"], session_user=session_user)
            elif route["action"] in ("move-up", "move-down") and route["id"]:
                # 批次5#15（spec ux-optimization）：移动成功/失败均带 flash，
                # 回跳附区块锚点定位原位（移动前查一次名称，查不到用 ID）
                direction = "up" if route["action"] == "move-up" else "down"
                pool = db.get_pool(conn, route["id"])
                # 找茬 L2：对象名经 quote 编码后拼 URL——含 # & 的名称
                # 不再截断 flash 文案或锚点（parse_qs 回读时自动解码）
                obj_name = urllib.parse.quote(
                    pool["name"] if pool else str(route["id"]), safe="")
                verb = "已上移" if direction == "up" else "已下移"
                if db.move_pool(conn, route["id"], direction, session_user=session_user):
                    return 302, f"/config/pools?flash={verb} {obj_name}#sec-pools", {}
                return 302, (f"/config?flash=错误: 移动失败（{obj_name}"
                             f" 已在边界或不存在）#sec-pools"), {}
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
                # 批次5#15：同连接池移动——flash + 锚点回跳
                direction = "up" if route["action"] == "move-up" else "down"
                rpt = db.get_report(conn, route["id"])
                obj_name = urllib.parse.quote(
                    rpt["name"] if rpt else str(route["id"]), safe="")
                verb = "已上移" if direction == "up" else "已下移"
                if db.move_report(conn, route["id"], direction, session_user=session_user):
                    return 302, f"/config/reports?flash={verb} {obj_name}#sec-reports", {}
                return 302, (f"/config/reports?flash=错误: 移动失败（{obj_name}"
                             f" 已在边界或不存在）#sec-reports"), {}
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
                # 批次5#15：分类移动——flash + 锚点回跳
                direction = "up" if route["action"] == "move-up" else "down"
                cat = db.get_category(conn, route["id"])
                obj_name = urllib.parse.quote(
                    cat["name"] if cat else str(route["id"]), safe="")
                verb = "已上移" if direction == "up" else "已下移"
                if db.move_category(conn, route["id"], direction, session_user=session_user):
                    return 302, f"/config/reports?flash={verb} {obj_name}#sec-categories", {}
                return 302, (f"/config/reports?flash=错误: 移动失败（{obj_name}"
                             f" 已在边界或不存在）#sec-categories"), {}
            else:
                return 302, "/config/reports", {}
            return _redirect_or_render(code, result)

    return 302, "/config", {}


# 真实数据预览最大返回行数（防大结果集拖慢页面）
_PREVIEW_MAX_ROWS = 3


def _redirect_or_render(code: int, result: str) -> tuple[int, str, dict]:
    """
    将处理器返回的 (状态码, 结果) 转换为标准返回格式。

    如果是 302 重定向，结果即为 Location；否则为 HTML 响应体。
    对 Location 中的 query 参数进行 URL 编码，确保非 ASCII 字符（如中文）正确传输。
    fragment（#锚点，批次5#16）不参与编码，保持在 URL 最末。
    """
    if code == 302 and result.startswith("/"):
        # 先分离 fragment，防止锚点被并入最后一个 query 参数值
        fragment = ""
        if "#" in result:
            result, raw_fragment = result.split("#", 1)
            fragment = f"#{raw_fragment}"
        # URL 编码 query 参数（flash 消息可能包含中文）
        if "?" in result:
            path, qs = result.split("?", 1)
            params = urllib.parse.parse_qs(qs, keep_blank_values=True)
            encoded_qs = urllib.parse.urlencode(params, doseq=True)
            encoded_url = f"{path}?{encoded_qs}{fragment}"
        else:
            encoded_url = result + fragment
        return 302, encoded_url, {"Location": encoded_url}
    return code, result, {}


# >>> B9-2 config_pages 再导出（本块由 run-logs/b9_2_split_config.py 生成） >>>
from config_pages.branding import (
    _render_branding_anchor,
    _render_branding_section,
    handle_site_branding_save,
)
from config_pages.users import (
    _render_user_form,
    _render_user_section,
    _user_from_form,
    handle_user_add,
    handle_user_delete,
    handle_user_edit,
    render_user_form_page,
    render_users_page,
)
from config_pages.pools import (
    _pool_from_form,
    _pool_test_error_hint,
    _render_pool_form,
    _render_pool_section,
    handle_pool_add,
    handle_pool_copy,
    handle_pool_delete,
    handle_pool_edit,
    handle_pool_test,
    render_pool_form_page,
    render_pools_page,
)
from config_pages.categories import (
    _category_from_form,
    _render_cat_opts,
    _render_category_section,
    _render_category_section_parts,
    handle_batch_set_category,
    handle_category_add,
    handle_category_delete,
    handle_category_edit,
    render_category_form_page,
)
from config_pages.scheduler import (
    _scheduler_flash_url,
    _scheduler_prefill,
    handle_scheduler_delete,
    handle_scheduler_request,
    handle_scheduler_run,
    handle_scheduler_save,
    handle_scheduler_toggle,
    render_scheduler_form_page,
    render_scheduler_page,
)
from config_pages.api_endpoints import (
    _endpoint_from_form,
    _endpoint_unique_error,
    _estimate_result_count,
    _parse_endpoint_form,
    _template_raw_for_format,
    _validate_json_template,
    handle_api_endpoint_add,
    handle_api_endpoint_delete,
    handle_api_endpoint_edit,
    handle_api_endpoint_preview,
    handle_api_endpoints_request,
    handle_api_key_actions,
    render_api_endpoint_form_page,
    render_api_endpoints_page,
)
from config_pages.reports import (
    _parse_report_form,
    _render_report_form,
    _report_form_cat_options,
    _report_form_html,
    _report_form_js_editor_api,
    _report_form_js_formatter,
    _report_form_js_highlight,
    _report_form_pool_options,
    _report_from_form,
    handle_report_add,
    handle_report_copy,
    handle_report_delete,
    handle_report_edit,
    handle_report_move_category,
    render_report_form_page,
    render_reports_page,
)
# <<< B9-2 config_pages 再导出 <<<
