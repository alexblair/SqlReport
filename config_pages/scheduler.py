"""config.py 拆分：定时任务配置实体：页面渲染与增删改/触发处理器（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import re
import time
import urllib.parse
import db
import app_config
from render import render_page_header, render_page_footer, build_flash_html, build_scheduler_page_html, build_scheduler_task_form_html

def _scheduler_prefill(conn, edit_id):
    """编辑态任务预填（含绑定报表与绑定级启停回显）。"""
    if not edit_id:
        return None
    sched = db.get_schedule(conn, edit_id)
    if not sched:
        return None
    reps = db.get_schedule_reports(conn, edit_id)
    sched = dict(sched)
    sched["report_ids"] = [r["report_id"] for r in reps]
    sched["binding_enabled"] = {r["report_id"]: r["enabled"] for r in reps}
    return sched


def render_scheduler_form_page(conn, sched_id: int = None,
                               flash: str = None,
                               preselect_report_ids: list = None) -> str:
    """定时任务表单独立页（T7.9：/config/scheduler/new 与 /{id}/edit）。

    preselect_report_ids：新建页 report_id 预选（报表编辑页「新建调度」
    入口带 ?report_id=N；仅新建时生效，编辑态以库内绑定为准）。
    """
    flash_html = build_flash_html(flash) if flash else ""
    reports = db.get_all_reports(conn)
    prefill = _scheduler_prefill(conn, sched_id)
    if prefill is None and preselect_report_ids:
        prefill = {"report_ids": [rid for rid in preselect_report_ids
                                  if any(r["id"] == rid for r in reports)]}
    title = "编辑定时任务" if (prefill or {}).get("id") else "新建定时任务"
    crumb_tail = "编辑" if (prefill or {}).get("id") else "新建"
    return (render_page_header(title=f"SqlReport - {title}",
                               active_nav="scheduler",
                               extra_css=config._CONFIG_EXTRA_CSS,
                               nav_badges=config._nav_badges(conn))
            + flash_html
            + '<div class="page-head"><div>'
            + '<div class="crumb"><a href="/config/scheduler">定时任务</a>'
            + f' › {crumb_tail}</div>'
            + f'<h1>{title}</h1>'
            + '<div class="sub">计划、绑定报表、错过补偿与静默窗口</div>'
            + '</div></div>'
            + build_scheduler_task_form_html(prefill, reports)
            + render_page_footer())


def render_scheduler_page(conn, flash: str = None, edit_id: int = None) -> str:
    """渲染定时任务管理页（/config/scheduler 列表主导，T7.9）。

    全局停用时页面仍可查看（横幅提示）。edit_id 遗留参数：给定时回填
    时改走表单独立页（兼容渲染，不再内嵌表单）。
    执行历史不在本页展示（对齐原型 page-scheduler），到审计日志查询。
    """
    if edit_id:
        return render_scheduler_form_page(conn, sched_id=edit_id, flash=flash)
    flash_html = build_flash_html(flash) if flash else ""
    scheduler_enabled = bool(app_config.get_config().get(
        "scheduler", {}).get("enable", False))
    schedules = db.get_all_schedules(conn)
    return (render_page_header(title="SqlReport - 定时任务",
                               active_nav="scheduler",
                               extra_css=config._CONFIG_EXTRA_CSS,
                               nav_badges=config._nav_badges(conn))
            + flash_html
            + '<div class="page-head"><div><h1>定时任务</h1>'
            + '<div class="sub">列表为主 · 新建/编辑进入独立表单页；'
            + '全局停用时仅展示不执行</div></div><div class="actions">'
            + '<a class="btn btn-primary" href="/config/scheduler/new">+ 新建任务</a>'
            + '</div></div>'
            + build_scheduler_page_html(schedules, scheduler_enabled)
            + render_page_footer())


def _scheduler_flash_url(message: str) -> str:
    return f"/config/scheduler?flash={urllib.parse.quote(message)}"


def handle_scheduler_run(conn, schedule_id: int, session_user=None) -> tuple[int, str]:
    """手动触发任务立即执行（B6：绕过熔断与 enabled；B21：全局停用降级）。"""
    import scheduler as _scheduler
    if _scheduler.trigger_manual(schedule_id, session_user=session_user):
        return 302, _scheduler_flash_url("任务已触发执行完成")
    return 302, _scheduler_flash_url("错误: 任务不存在")


def handle_scheduler_toggle(conn, schedule_id: int, session_user=None) -> tuple[int, str]:
    """启停任务；重新启用时若下次执行时间已过期则按当前计划重算。"""
    sched = db.get_schedule(conn, schedule_id)
    if not sched:
        return 302, _scheduler_flash_url("错误: 任务不存在")
    new_enabled = 0 if int(sched.get("enabled", 1)) else 1
    db.set_schedule_enabled(conn, schedule_id, new_enabled,
                            session_user=session_user)
    if new_enabled:
        next_at = sched.get("next_run_at")
        if not next_at or next_at <= time.time():
            try:
                import scheduler as _scheduler
                next_at = _scheduler.compute_next_run(
                    sched["schedule_type"], sched["interval_minutes"],
                    sched["daily_time"], time.time(),
                    last_run_at=sched.get("last_run_at"))
            except Exception:
                next_at = None
            conn_local = conn
            conn_local.execute(
                "UPDATE report_schedules SET next_run_at=? WHERE id=?",
                (next_at, schedule_id))
            conn_local.commit()
    state = "启用" if new_enabled else "停用"
    return 302, _scheduler_flash_url(f"任务已{state}")


def handle_scheduler_delete(conn, schedule_id: int, session_user=None) -> tuple[int, str]:
    """删除任务的定时配置（不影响报表本身）。"""
    if db.delete_schedule(conn, schedule_id, session_user=session_user):
        return 302, _scheduler_flash_url("定时任务已删除")
    return 302, _scheduler_flash_url("错误: 任务不存在")


def handle_scheduler_save(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """保存/更新定时任务（多报表组合，spec §7.2 POST /config/scheduler/save）。

    表单字段：edit_id（编辑态隐藏域，给定时按 id 精确更新、支持改名）、
    name、schedule_type、interval_minutes、daily_time、misfire_policy、
    schedule_enabled、audit_enabled、report_ids（多选）、exclusions（JSON
    文本）。后端校验排除规则结构，非法回显错误且不落库；任务名与既有
    任务冲突时回显错误（防错位顶替更新）。
    """
    import scheduler as _scheduler
    qs = urllib.parse.parse_qs(form_body, keep_blank_values=True)
    data = config._parse_form_data(form_body)
    edit_id = app_config.safe_int(data.get("edit_id"), None)
    name = (data.get("name") or "").strip()
    schedule_type = data.get("schedule_type") or "interval"
    if schedule_type not in ("interval", "daily"):
        schedule_type = "interval"
    daily_time = (data.get("daily_time") or "").strip()
    if not re.match(r"^\d{2}:\d{2}$", daily_time):
        daily_time = "08:00"
    misfire_policy = data.get("misfire_policy") or "skip"
    if misfire_policy not in ("skip", "run_once"):
        misfire_policy = "skip"
    interval_minutes = app_config.safe_int(data.get("interval_minutes"), 60)
    interval_minutes = min(max(interval_minutes, 1), 525600)
    enabled = 1 if data.get("schedule_enabled") else 0
    audit_enabled = 1 if data.get("audit_enabled") else 0
    # 关联报表（多选；表单可能以重复键或逗号分隔传递）
    raw_ids = qs.get("report_ids") or []
    report_ids: list[int] = []
    for x in raw_ids:
        for y in str(x).split(","):
            y = y.strip()
            if y.isdigit():
                report_ids.append(int(y))
    report_ids = list(dict.fromkeys(report_ids))  # 保序去重
    # 排除规则（JSON 文本），后端校验结构合法
    exclusions_raw = (data.get("exclusions") or "").strip()
    if exclusions_raw:
        ok, err = _scheduler.validate_exclusions(exclusions_raw)
        if not ok:
            return 302, _scheduler_flash_url(f"错误: 排除规则无效 - {err}")
    if not name:
        return 302, _scheduler_flash_url("错误: 任务名不能为空")
    if not report_ids:
        return 302, _scheduler_flash_url("错误: 至少选择一个关联报表")
    # 校验全部关联报表存在（创建任务时要求报表已存在，基础规格 B22 调整）
    for rid in report_ids:
        if db.get_report(conn, rid) is None:
            return 302, _scheduler_flash_url(f"错误: 报表 #{rid} 不存在")
    # 绑定级启停（S10）：bind_enabled_<rid> 勾选=参与执行，缺省 1
    binding_enabled = {}
    for rid in report_ids:
        binding_enabled[rid] = 1 if data.get(f"bind_enabled_{rid}") else 0
    now = time.time()
    next_run_at = _scheduler.compute_next_run(
        schedule_type, interval_minutes, daily_time, now)
    try:
        db.upsert_schedule(conn, name=name, schedule_type=schedule_type,
                           interval_minutes=interval_minutes,
                           daily_time=daily_time, misfire_policy=misfire_policy,
                           enabled=enabled, exclusions=exclusions_raw,
                           audit_enabled=audit_enabled, report_ids=report_ids,
                           binding_enabled=binding_enabled,
                           next_run_at=next_run_at, session_user=session_user,
                           schedule_id=edit_id)
    except Exception as e:
        return 302, _scheduler_flash_url(f"错误: {e}")
    return 302, _scheduler_flash_url(f"任务「{name}」已保存")


def handle_scheduler_request(conn, method: str, path: str, query: str,
                             form_body: str = None,
                             session_user=None) -> tuple[int, str, dict]:
    """/config/scheduler* 请求入口（handle_request 前置分发，模式同 api_endpoints）。"""
    route = config.parse_config_path(path)
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)
    flash = qs.get("flash", [None])[0]
    if method == "GET":
        if route["action"] == "new":
            # 报表编辑页「新建调度」入口带 ?report_id=N（仅新建生效，预勾绑定）
            preselect = []
            try:
                rid = int(qs.get("report_id", [None])[0])
                if rid > 0:
                    preselect = [rid]
            except (TypeError, ValueError):
                preselect = []
            return 200, render_scheduler_form_page(
                conn, flash=flash, preselect_report_ids=preselect), {}
        if route["action"] == "edit" and route["id"]:
            return 200, render_scheduler_form_page(
                conn, sched_id=route["id"], flash=flash), {}
        # 遗留 ?edit=N：直接渲染表单页（兼容旧链接/测试）
        edit_id = None
        try:
            edit_id = int(qs.get("edit", [None])[0])
        except (TypeError, ValueError):
            edit_id = None
        if edit_id:
            return 200, render_scheduler_form_page(
                conn, sched_id=edit_id, flash=flash), {}
        return 200, render_scheduler_page(conn, flash), {}
    if method == "POST":
        action = route["action"]
        if action == "run" and route["id"]:
            code, result = handle_scheduler_run(conn, route["id"],
                                                session_user=session_user)
        elif action == "toggle" and route["id"]:
            code, result = handle_scheduler_toggle(conn, route["id"],
                                                   session_user=session_user)
        elif action == "delete" and route["id"]:
            code, result = handle_scheduler_delete(conn, route["id"],
                                                   session_user=session_user)
        elif action == "save":
            code, result = handle_scheduler_save(conn, form_body or "",
                                                 session_user=session_user)
        else:
            code, result = 302, "/config/scheduler"
        return code, result, {}
    return 302, "/config/scheduler", {}
