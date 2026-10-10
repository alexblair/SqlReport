"""config.py 拆分：连接池配置实体：列表/表单页、增删改复制与连通性测试（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import logging
import urllib.parse
import db
from render import build_pool_form_html, build_pool_section_html, render_page_header, render_page_footer, build_flash_html

def _render_pool_form(pool: dict = None, copy_mode: bool = False, is_edit: bool = None,
                      prefill_copy_suffix: bool = True) -> str:
    """渲染连接池编辑/新增/复制表单"""
    return build_pool_form_html(pool, copy_mode, is_edit=is_edit,
                                prefill_copy_suffix=prefill_copy_suffix)


def _render_pool_section(conn) -> str:
    """渲染连接池配置列表（含复制、排序）

    批次2#6：删除确认弹窗披露各池关联报表数（破坏半径前置披露）。
    R2 P9：关联报表列在渲染层由 get_all_reports 按 pool_id 分组（不改 DB）。
    """
    pools = db.get_all_pools(conn)
    pool_reports: dict[int, list[dict]] = {}
    for rpt in db.get_all_reports(conn):
        pid = rpt.get("pool_id")
        if pid is not None:
            pool_reports.setdefault(int(pid), []).append(
                {"id": rpt["id"], "name": rpt.get("name") or f"#{rpt['id']}"})
    return build_pool_section_html(pools,
                                   report_counts=db.count_reports_by_pool(conn),
                                   pool_reports=pool_reports)


def render_pools_page(conn, flash: str = None) -> str:
    """连接池独立列表页（T7.5：自概览拆出；破坏半径披露沿用 build_pool_section）。"""
    flash_html = build_flash_html(flash) if flash else ""
    badges = config._nav_badges(conn)
    body = render_page_header(title="SqlReport - 连接池",
                              active_nav="config-pools",
                              extra_css=config._CONFIG_EXTRA_CSS,
                              nav_badges=badges)
    body += (
        '<div class="page-head"><div><h1>连接池</h1>'
        '<div class="sub">MySQL 连接配置 · 报表运行的数据源</div></div>'
        '<div class="actions">'
        '<a class="btn btn-primary" href="/config/pools/add">+ 新增连接池</a></div></div>'
        + flash_html + _render_pool_section(conn))
    body += render_page_footer()
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
        return config.render_overview(conn, flash="错误: 连接池不存在")
    is_edit = pool_id is not None and not copy_mode
    flash_html = build_flash_html(flash) if flash else ""
    return (render_page_header(title="SqlReport - 配置", active_nav="config-pools", extra_css=config._CONFIG_EXTRA_CSS)
            + flash_html + _render_pool_form(pool, copy_mode, is_edit=is_edit,
                                             prefill_copy_suffix=not echo_pool) + render_page_footer())


def _pool_from_form(data: dict, pool_id: int = None) -> dict:
    """从表单数据构造临时连接池 dict（保存失败时表单回显用户原输入）。"""
    pool = {
        "id": pool_id,  # 批次3#12：测试连接 hidden 字段需要 id 键恒存在
        "name": data.get("name", ""),
        "host": data.get("host", ""),
        "port": data.get("port", "3306"),
        "user": data.get("user", ""),
        # 密码不回显（批次3#12）：失败回显时同样留空
        "password": "",
        "database": data.get("database", ""),
    }
    return pool


def _pool_test_error_hint(e: Exception) -> tuple[str, str]:
    """测试连接失败的人话提示（复用 report.humanize_db_error 的映射）。"""
    try:
        from report import humanize_db_error
        return humanize_db_error(e)
    except Exception:
        return str(e), str(e)


def handle_pool_test(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理「测试连接」表单提交（spec ux-optimization 批次3#12）。

    用当前表单填写的信息试连一次 MySQL（短超时），不落库；
    结果以 flash 回跳回来源页。编辑态密码留空时沿用库中旧密码
    （与 handle_pool_edit 的空值语义一致——否则「没改密码」的池
    永远测不通）。驱动未安装 / 参数缺失同样返回 flash 而非 500。

    批次(本次): 若请求为 AJAX（前端「测试连接」按钮经 fetch 提交，
    携带 test_ajax=1），则返回 JSON 且**不跳转、不刷新页面**，
    表单已填内容得以保留；否则仍走 302 回跳表单页（兼容无 JS 环境）。
    """
    data = config._parse_form_data(form_body)
    host = (data.get("host") or "").strip()
    port_raw = (data.get("port") or "").strip()
    user = (data.get("user") or "").strip()
    database = (data.get("database") or "").strip()
    password = data.get("password") or ""
    pool_id = None
    try:
        pool_id = int(data.get("pool_id") or 0) or None
    except (TypeError, ValueError):
        pool_id = None

    is_ajax = (data.get("test_ajax") or "").strip() == "1"
    back_url = f"/config/pools/{pool_id}/edit" if pool_id else "/config/pools/add"

    def _respond(flash_msg: str, ok: bool) -> tuple[int, str, dict]:
        if is_ajax:
            import json
            return (200, json.dumps({"ok": ok, "flash": flash_msg}, ensure_ascii=False),
                    {"Content-Type": "application/json; charset=utf-8"})
        return 302, f"{back_url}?flash={urllib.parse.quote(flash_msg)}", {}

    # 编辑态留空密码 → 取库中旧值补齐（与保存语义一致）
    if not password and pool_id:
        stored = db.get_pool(conn, pool_id)
        if stored:
            password = stored["password"]

    if not host or not user:
        return _respond("错误: 主机地址和用户名不能为空", False)
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return _respond("错误: 端口必须是数字", False)

    try:
        import mysql.connector
    except ImportError:
        return _respond("错误: 未安装 MySQL 驱动（mysql-connector-python），无法测试连接", False)

    try:
        test_conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password,
            database=database, connection_timeout=3)
        try:
            test_conn.close()
        except Exception:
            pass
        return _respond("连接成功：数据库可达，账号密码正确", True)
    except Exception as e:
        logging.warning("测试连接失败 (%s:%s/%s): %s", host, port, database, e)
        friendly, _ = _pool_test_error_hint(e)
        msg = f"错误: 连接失败——{friendly}"
        return _respond(msg, False)


def handle_pool_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增连接池表单提交

    遵循「保存」/「保存返回上级」双按钮业务逻辑。
    """
    data = config._parse_form_data(form_body)
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"],
                          session_user=session_user)
        return config._save_or_render(
            data, render_pool_form_page, (conn, pid), {},
            success_flash=f"连接池 {data['name']} 已创建 (id={pid})",
            redirect_url="/config/pools", anchor=f"pool-{pid}")
    except Exception as e:
        return 200, render_pool_form_page(conn, flash=f"错误: {e}",
                                          pool=_pool_from_form(data))


def handle_pool_edit(conn, pool_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑连接池表单提交

    遵循「保存」/「保存返回上级」双按钮业务逻辑。
    """
    data = config._parse_form_data(form_body)
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return 302, "/config?flash=错误: 连接池不存在"
    password = data.get("password") or pool["password"]
    try:
        ok = db.update_pool(conn, pool_id, data["name"], data["host"],
                            int(data["port"]), data["user"], password, data["database"],
                            session_user=session_user)
        if ok:
            return config._save_or_render(
                data, render_pool_form_page, (conn, pool_id), {},
                success_flash=f"连接池 {data['name']} 已更新",
                redirect_url="/config/pools", anchor=f"pool-{pool_id}")
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_pool_form_page(conn, pool_id, flash=f"错误: {e}",
                                          pool=_pool_from_form(data, pool_id))


def handle_pool_copy(conn, pool_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理复制连接池（新增一个同名+副本的连接池）"""
    data = config._parse_form_data(form_body)
    src = db.get_pool(conn, pool_id)
    if not src:
        return 200, render_pool_form_page(conn, pool_id, flash="错误: 连接池不存在",
                                          copy_mode=True,
                                          pool=_pool_from_form(data, pool_id))
    try:
        pid = db.add_pool(conn, data["name"], data["host"], int(data["port"]),
                          data["user"], data["password"], data["database"],
                          session_user=session_user)
        return 302, f"/config/pools?flash=连接池 {data['name']} 已创建（复制自 id={pool_id}）"
    except Exception as e:
        return 200, render_pool_form_page(conn, pool_id, flash=f"错误: {e}", copy_mode=True,
                                          pool=_pool_from_form(data, pool_id))


def handle_pool_delete(conn, pool_id: int, session_user=None) -> tuple[int, str]:
    """处理删除连接池。

    批次2#6（spec ux-optimization）：flash 披露断连破坏半径——
    其下 N 个关联报表将失去数据库连接（报表保留但无法执行）。
    """
    pool = db.get_pool(conn, pool_id)
    if not pool:
        return 302, "/config?flash=错误: 连接池不存在"
    ref_count = db.count_reports_by_pool(conn).get(pool_id, 0)
    db.delete_pool(conn, pool_id, session_user=session_user)
    if ref_count > 0:
        return 302, (f"/config/pools?flash=连接池 {pool['name']} 已删除"
                     f"（已断开 {ref_count} 个报表的连接，报表保留但无法执行）")
    return 302, f"/config/pools?flash=连接池 {pool['name']} 已删除"
