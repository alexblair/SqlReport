"""config.py 拆分：用户配置实体：列表页、表单页、增删改处理器（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import db
import auth
from render import build_user_form_html, build_user_section_html, render_page_header, render_page_footer, build_flash_html

def _render_user_form(user: dict = None, is_edit: bool = None) -> str:
    """渲染用户编辑/新增表单"""
    return build_user_form_html(user, is_edit=is_edit)


def _render_user_section(conn, current_username: str = None) -> str:
    """渲染用户配置列表

    批次2#7：当前登录用户所在行不渲染删除按钮。
    """
    users = db.get_all_users(conn)
    return build_user_section_html(users, current_username=current_username)


def render_users_page(conn, flash: str = None, current_username: str = None) -> str:
    """用户独立列表页（T7.5：自概览拆出）。"""
    flash_html = build_flash_html(flash) if flash else ""
    badges = config._nav_badges(conn)
    body = render_page_header(title="SqlReport - 用户",
                              active_nav="config-users",
                              extra_css=config._CONFIG_EXTRA_CSS,
                              nav_badges=badges)
    body += (
        '<div class="page-head"><div><h1>用户</h1>'
        '<div class="sub">登录账号 · 密码经 PBKDF2 哈希存储</div></div>'
        '<div class="actions">'
        '<a class="btn btn-primary" href="/config/users/add">+ 新增用户</a></div></div>'
        + flash_html + _render_user_section(conn, current_username=current_username))
    body += render_page_footer()
    return body


def render_user_form_page(conn, user_id: int = None, flash: str = None, user: dict = None) -> str:
    """渲染新增/编辑用户表单页

    user: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    """
    if user is None:
        user = db.get_user_by_id(conn, user_id) if user_id else None
    if user_id and not user:
        return config.render_overview(conn, flash="错误: 用户不存在")
    is_edit = user_id is not None
    flash_html = build_flash_html(flash) if flash else ""
    return (render_page_header(title="SqlReport - 配置", active_nav="config-users", extra_css=config._CONFIG_EXTRA_CSS)
            + flash_html + _render_user_form(user, is_edit=is_edit) + render_page_footer())


def _user_from_form(data: dict, user_id: int = None) -> dict:
    """从表单数据构造临时用户 dict（保存失败时表单回显用户原输入）。"""
    user = {"username": data.get("username", "")}
    if user_id is not None:
        user["id"] = user_id
    return user


def handle_user_add(conn, form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增用户表单提交"""
    data = config._parse_form_data(form_body)
    try:
        pw_hash = auth.hash_password(data["password"])
        uid = db.add_user(conn, data["username"], pw_hash, session_user=session_user)
        return 302, f"/config/users?flash=用户 {data['username']} 已创建 (id={uid})#user-{uid}"
    except Exception as e:
        return 200, render_user_form_page(conn, flash=f"错误: {e}",
                                          user=_user_from_form(data))


def handle_user_edit(conn, user_id: int, form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑用户表单提交。

    批次2#7（spec ux-optimization）：密码被修改时注销该用户全部登录会话
    （旧凭据立即作废；管理员改自己的密码同样会踢掉自己——预期安全语义）。
    仅改名不改密不注销（规格语义：踢会话仅由改密触发）。
    """
    data = config._parse_form_data(form_body)
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return 302, "/config?flash=错误: 用户不存在"
    try:
        password_changed = bool(data.get("password"))
        username_changed = data.get("username") != target["username"]
        password_hash = auth.hash_password(data["password"]) if password_changed else target["password_hash"]
        ok = db.update_user(conn, user_id, data["username"], password_hash, session_user=session_user)
        if ok:
            if password_changed or username_changed:
                # 用旧用户名踢会话：token 绑定的是变更前的用户名。
                # 改名同样注销——session 不回查 users 表，旧 token 会以
                # 已不存在的用户名继续通过认证（批次2#7 边界补丁）。
                auth.remove_sessions_for_user(target["username"])
                reason = ("其登录会话已全部注销，需重新登录"
                          if password_changed else
                          f"已改名为 {data['username']}，其登录会话已注销，需重新登录")
                return 302, (f"/config/users?flash=用户 {target['username']} 已更新，{reason}"
                             f"#user-{user_id}")
            return 302, f"/config/users?flash=用户 {data['username']} 已更新#user-{user_id}"
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        return 200, render_user_form_page(conn, user_id, flash=f"错误: {e}",
                                          user=_user_from_form(data, user_id))


def handle_user_delete(conn, user_id: int, session_user=None) -> tuple[int, str]:
    """处理删除用户。

    批次2#7（spec ux-optimization）：
    - 服务端拒绝删除当前登录账号（前端隐藏删除按钮之外的兜底）；
    - 删除成功后注销该用户全部登录会话（内存 + 持久层）。
    """
    target = db.get_user_by_id(conn, user_id)
    if not target:
        return 302, "/config?flash=错误: 用户不存在"
    if session_user and target["username"] == session_user:
        return 302, "/config?flash=错误: 不能删除当前登录账号"
    db.delete_user(conn, user_id, session_user=session_user)
    kicked = auth.remove_sessions_for_user(target["username"])
    suffix = f"（已注销其 {kicked} 个登录会话）" if kicked > 0 else ""
    return 302, f"/config/users?flash=用户 {target['username']} 已删除{suffix}"
