#!/usr/bin/env python3
"""
server.py — HTTP 服务器入口

职责：
- 创建并启动 HTTPServer
- URL 路由分发到各模块
- Cookie 认证中间件（未登录重定向到登录页）
- 登录页、退出、首页

路由表：
  GET  /              → 首页（重定向到 /report）
  GET  /login         → 登录页
  POST /login         → 登录表单提交
  GET  /logout        → 退出（清除 session）
  /config*            → config.py
  /report*            → report.py
  /export*            → export.py
"""

import sys
import os
import re
import json
import time
import logging
import urllib.parse
import http.server
import html as _html_mod
import threading
import db
import auth
import config
import report
import render
import export as export_mod
import api_handler
import audit_db
import audit_page
import file_permissions
import static_cache
from app_config import get_server_config, get_log_config, get_error_log_config, get_audit_db_config, get_trust_xff

# ---------------------------------------------------------------------------
# 配置（从 app_config.json 加载，支持环境变量 HOST / PORT 覆盖）
# ---------------------------------------------------------------------------

HOST, PORT = get_server_config()
_start_time = time.time()

# ---------------------------------------------------------------------------
# 登录页 HTML
# ---------------------------------------------------------------------------
# 公共基础片段（reset / body 字体栈 / fadeUp 关键帧）来自 render._BASE_CSS，
# 与全站页面（render._COMMON_CSS）保持单一来源。

_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web 报表工具 - 登录</title>
<style>""" + render._BASE_CSS + """
  body {
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; margin: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  }
  .login-box {
    background: #fff; padding: 40px; border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15); width: 380px;
    animation: fadeUp 0.4s ease-out;
  }
  .login-box h1 {
    text-align: center; color: #1e293b; margin-bottom: 8px;
    font-size: 24px; font-weight: 700; letter-spacing: -0.5px;
  }
  .login-subtitle { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 32px; }
  .login-box label { display: block; margin-bottom: 6px; font-weight: 600; color: #475569; font-size: 14px; }
  .login-box input[type=text], .login-box input[type=password] {
    width: 100%; padding: 10px 14px; margin-bottom: 20px;
    border: 2px solid #e2e8f0; border-radius: 8px;
    font-size: 15px; color: #1e293b; transition: border-color 0.2s, box-shadow 0.2s;
    outline: none; background: #f8fafc;
  }
  .login-box input[type=text]:focus, .login-box input[type=password]:focus {
    border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.15); background: #fff;
  }
  .login-box button {
    width: 100%; padding: 12px; background: linear-gradient(135deg, #4f46e5, #6366f1);
    color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: 600;
    cursor: pointer; transition: transform 0.15s, box-shadow 0.2s;
    box-shadow: 0 4px 14px rgba(79,70,229,0.35);
  }
  .login-box button:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(79,70,229,0.4); }
  .login-box button:active { transform: translateY(0); }
  .login-box .error {
    color: #dc2626; text-align: center; margin-bottom: 20px; font-size: 14px;
    padding: 10px; background: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;
  }
  .login-footer { text-align: center; margin-top: 24px; color: #94a3b8; font-size: 12px; }
</style>
</head>
<body>
<div class="login-box">
  <h1>Web 报表工具</h1>
  <p class="login-subtitle">请登录以访问系统</p>
  {error}
  <form method="post" action="/login">
    <label>用户名</label>
    <input type="text" name="username" required autofocus>
    <label>密码</label>
    <input type="password" name="password" required>
    <button type="submit">登 录</button>
  </form>
  <p class="login-footer">Web 报表工具 v1.0</p>
</div>
</body>
</html>"""


def _render_login_page(error: str = "") -> str:
    """渲染登录页，可选显示错误消息"""
    err_html = f'<div class="error">{error}</div>' if error else ""
    return _LOGIN_PAGE.replace("{error}", err_html)


# ---------------------------------------------------------------------------
# 路由表
# ---------------------------------------------------------------------------


class RouteEntry:
    """路由条目。

    将 URL 路径模式与处理方法绑定，附带认证和数据库需求标记。
    所有路由按 ROUTES 列表的顺序进行匹配，首次匹配优先。
    """

    __slots__ = ("pattern", "method", "needs_auth", "needs_db", "handler")

    def __init__(self, pattern: str, method: str,
                 needs_auth: bool, needs_db: bool, handler: str):
        """
        初始化路由条目。

        Args:
            pattern: URL 路径正则模式（如 r'^/login$'）。
            method: HTTP 方法（GET/POST），'*' 表示任意方法。
            needs_auth: 是否需要用户认证。
            needs_db: 是否需要数据库连接。
            handler: 处理方法名（ReportHandler 的方法名）。
        """
        self.pattern = re.compile(pattern)
        self.method = method
        self.needs_auth = needs_auth
        self.needs_db = needs_db
        self.handler = handler

    def __repr__(self) -> str:
        return (f"Route({self.method} {self.pattern.pattern}, "
                f"auth={self.needs_auth}, db={self.needs_db})")


# 路由表 — 顺序优先，首次匹配即生效
ROUTES = [
    RouteEntry(r"^/login$", "GET", False, False, "_handle_login_get"),
    RouteEntry(r"^/login$", "POST", False, False, "_handle_login"),
    RouteEntry(r"^/health$", "GET", False, False, "_handle_health"),
    RouteEntry(r"^/?$", "GET", True, False, "_handle_home_redirect"),
    RouteEntry(r"^/logout$", "GET", True, False, "_handle_logout"),
    RouteEntry(r"^/config/api-endpoints$", "GET", True, True, "_handle_config_api_endpoints"),
    RouteEntry(r"^/config/api-endpoints$", "POST", True, True, "_handle_config_api_endpoints"),
    RouteEntry(r"^/config/reports$", "GET", True, True, "_handle_config_reports"),
    RouteEntry(r"^/config/reports/memo-preview$", "POST", True, False, "_handle_config"),
    RouteEntry(r"^/config/api-endpoints/description-preview$", "POST", True, False, "_handle_config"),
    RouteEntry(r"^/config/categories$", "GET", True, True, "_handle_config_categories"),
    RouteEntry(r"^/config($|/)", "*", True, True, "_handle_config"),
    RouteEntry(r"^/report($|/)", "*", True, True, "_handle_report"),
    RouteEntry(r"^/export($|/)", "*", True, True, "_handle_export"),
    RouteEntry(r"^/api/", "*", False, True, "_handle_api"),
    RouteEntry(r"^/audit($|/)", "*", True, False, "_handle_audit"),
]

# ---------------------------------------------------------------------------
# 白名单静态文件服务（唯一例外，不推广为通用静态服务）
# /static/vendor/<name@version>/<file> — 仅服务 vendor 根目录内文件。
# 资产版本锁 URL，随仓库提交，无鉴权（与 CDN 直出定位一致）。
# ---------------------------------------------------------------------------

_VENDOR_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "static", "vendor")

_VENDOR_STATIC_PREFIX = "/static/vendor/"

# MIME 按扩展名映射（不猜类型，仅白名单扩展名）
_VENDOR_MIME_MAP = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
}


def _vendor_real_path(rel_path: str) -> str | None:
    """将 /static/vendor/ 后的相对路径规范化为 vendor 根内的绝对路径。

    返回安全的文件绝对路径；相对路径逃出 vendor 根（.. 穿越）返回 None。
    """
    root_real = os.path.realpath(_VENDOR_ROOT)
    candidate = os.path.realpath(os.path.join(root_real, rel_path))
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        return None
    return candidate


def _vendor_mime_for(path: str) -> str | None:
    """按扩展名返回 MIME，白名单外扩展名返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    return _VENDOR_MIME_MAP.get(ext)


def _match_route(method: str, path: str) -> RouteEntry | None:
    """在路由表中查找匹配的路由条目。

    Args:
        method: HTTP 方法（GET/POST/OPTIONS）。
        path: URL 路径。

    Returns:
        匹配的 RouteEntry，未匹配返回 None（方法不支持或路径未知）。
    """
    for route in ROUTES:
        if not route.pattern.search(path):
            continue
        if route.method == "*":
            # 通配路由仅实际分发 GET/POST/OPTIONS，其余方法视为不支持
            if method not in ("GET", "POST", "OPTIONS"):
                continue
        elif method != route.method:
            continue
        return route
    return None


_METHOD_ORDER = {m: i for i, m in enumerate(
    ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"))}


def _allowed_methods_for_path(path: str) -> list[str]:
    """计算路径允许的 HTTP 方法列表（用于 405 响应 Allow 头）。"""
    methods: set[str] = set()
    for route in ROUTES:
        if not route.pattern.search(path):
            continue
        if route.method == "*":
            methods.update(("GET", "POST", "OPTIONS"))
        else:
            methods.add(route.method)
    return sorted(methods, key=_METHOD_ORDER.get)


class BodyReadError(Exception):
    """请求体读取/解码失败（客户端请求错误，应返回 400）。"""


# URL 结构保留字符 + 百分号（避免双重编码已编码部分），供 Location 兜底编码使用
_LOCATION_SAFE = "/:?&=@+$#%;,~!*'()[]-._"


def _safe_location(location: str) -> str:
    """确保 Location 头值可被 latin-1 编码（http.server 响应头编码限制）。

    调用方应显式百分号编码（如 flash 消息用 urllib.parse.quote）；此函数仅
    作为兜底：检测到非 ASCII 字符时对整个 Location 做百分号编码（保留 URL
    结构字符），并记录警告提示调用方修复。ASCII 输入原样返回。
    """
    try:
        location.encode("latin-1")
        return location
    except UnicodeEncodeError:
        logging.warning(
            "302 Location 含非 ASCII 字符未编码，自动百分号编码（调用方应显式编码）: %s",
            location)
        return urllib.parse.quote(location, safe=_LOCATION_SAFE)


# ---------------------------------------------------------------------------
# 请求处理器
# ---------------------------------------------------------------------------


class ReportHandler(http.server.BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    # HTTP 请求日志（日志关闭时静默，开启时写入文件）
    def log_message(self, format, *args):
        logging.info("%s - %s", self.client_address[0], format % args)

    # ---- 路由 ----

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")

    def _handle(self, method: str):
        """基于路由表分发请求"""
        self._session_token = None
        parsed = urllib.parse.urlparse(self.path)
        raw_path = parsed.path.rstrip("/") or "/"
        path = urllib.parse.unquote(raw_path)
        query = parsed.query

        # 白名单静态文件服务（路由表之前：仅 /static/vendor/ 前缀走静态，
        # 其余路径零影响；非 GET 返回 405）
        if path.startswith(_VENDOR_STATIC_PREFIX):
            if method != "GET":
                return self._send_html(
                    405, "<h1>405 — 方法不允许</h1>", {"Allow": "GET"})
            return self._serve_static_vendor(path)

        route = _match_route(method, path)
        if route is None:
            allowed = _allowed_methods_for_path(path)
            if allowed:
                return self._send_html(
                    405, "<h1>405 — 方法不允许</h1>",
                    {"Allow": ", ".join(allowed)})
            return self._send_html(404, "<h1>404 — 页面不存在</h1>")

        if route.needs_auth and not self._authenticate():
            return

        if route.needs_db:
            conn = db.get_config_db()
            try:
                getattr(self, route.handler)(method, path, query, conn)
            except BodyReadError as e:
                logging.warning("请求体读取失败: %s", e)
                self._send_html(400, f"请求体读取失败: {e}",
                                {"Content-Type": "text/plain; charset=utf-8"})
            except Exception as e:
                logging.error("未捕获异常: %s", e, exc_info=True)
                self._send_html(500, f"<h1>500 — 服务器内部错误</h1><pre>{_html_mod.escape(str(e))}</pre>")
            finally:
                conn.close()
        else:
            try:
                getattr(self, route.handler)(method, path, query, None)
            except BodyReadError as e:
                logging.warning("请求体读取失败: %s", e)
                self._send_html(400, f"请求体读取失败: {e}",
                                {"Content-Type": "text/plain; charset=utf-8"})
            except Exception as e:
                logging.error("未捕获异常: %s", e, exc_info=True)
                self._send_html(500, f"<h1>500 — 服务器内部错误</h1><pre>{_html_mod.escape(str(e))}</pre>")

    # ---- 认证 ----

    def _authenticate(self) -> bool:
        """检查 session cookie，未认证则重定向到登录页"""
        cookie_header = self.headers.get("Cookie", "")
        cookies = auth.parse_cookie(cookie_header)
        token = cookies.get("session_id")
        user = auth.get_session_user(token) if token else None
        if user is None:
            self._send_redirect("/login")
            return False
        # 滑动过期：刷新 session 时间戳 + 下行 cookie Max-Age
        auth.refresh_session(token)
        self._session_token = token
        return True

    def _get_current_user(self) -> str | None:
        """从 cookie 中获取当前登录用户名。"""
        cookie_header = self.headers.get("Cookie", "")
        cookies = auth.parse_cookie(cookie_header)
        token = cookies.get("session_id")
        return auth.get_session_user(token) if token else None

    def _handle_login_get(self, method, path, query, conn=None):
        """显示登录页"""
        self._send_html(200, _render_login_page())

    def _handle_home_redirect(self, method, path, query, conn=None):
        """首页重定向到 /report"""
        self._send_redirect("/report")

    def _handle_health(self, method, path, query, conn=None):
        """健康检查端点，返回 JSON 状态"""
        uptime = int(time.time() - _start_time)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "uptime": uptime,
        }).encode("utf-8"))

    def _handle_login(self, method=None, path=None, query=None, conn=None):
        """处理登录表单提交"""
        form_body = self._read_body()
        data = urllib.parse.parse_qs(form_body, keep_blank_values=True)
        username = data.get("username", [""])[0]
        password = data.get("password", [""])[0]

        conn = db.get_config_db()
        try:
            user = db.get_user(conn, username)
            if user and auth.verify_password(password, user["password_hash"]):
                token = auth.create_session(username)
                auth._record_auth_event(username, "login")
                self.send_response(302)
                self.send_header("Location", "/report")
                self.send_header("Set-Cookie", auth.make_set_cookie_header(token))
                self.end_headers()
                return
        finally:
            conn.close()

        # 登录失败
        auth._record_auth_event(username, "login_failed")
        self._send_html(200, _render_login_page("用户名或密码错误"))

    def _handle_logout(self, method=None, path=None, query=None, conn=None):
        """处理退出"""
        cookie_header = self.headers.get("Cookie", "")
        cookies = auth.parse_cookie(cookie_header)
        token = cookies.get("session_id")
        current_user = self._get_current_user()
        if current_user:
            auth._record_auth_event(current_user, "logout")
        if token:
            auth.remove_session(token)
        self.send_response(302)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", auth.make_expire_cookie_header())
        self.end_headers()

    # ---- 各功能路由 ----

    def _handle_config_api_endpoints(self, method: str, path: str, query: str, conn):
        """API 端点独立管理页"""
        form_body = self._read_body() if method == "POST" else None
        session_user = self._get_current_user()
        code, body, headers = config.handle_api_endpoints_request(
            conn, method, path, query, form_body, session_user=session_user)
        self._log_web_access(path, method, code, request_body=form_body)
        if code == 302:
            self._send_redirect(body)
        else:
            self._send_html(code, body, headers)

    def _handle_config_reports(self, method: str, path: str, query: str, conn):
        """报表管理独立页（/config/reports）"""
        qs = urllib.parse.parse_qs(query, keep_blank_values=True)
        flash = qs.get("flash", [None])[0]
        body = config.render_reports_page(conn, flash)
        self._log_web_access(path, method, 200)
        self._send_html(200, body, {})

    def _handle_config_categories(self, method: str, path: str, query: str, conn):
        """分类管理已并入报表管理页（/config/reports），旧地址重定向兼容"""
        self._log_web_access(path, method, 302)
        self._send_redirect("/config/reports")

    def _handle_config(self, method: str, path: str, query: str, conn):
        """委托给 config.py，使用 _handle() 传入的共享连接"""
        form_body = self._read_body() if method == "POST" else None
        session_user = self._get_current_user()
        code, body, headers = config.handle_request(conn, method, path, query, form_body, session_user=session_user)
        self._log_web_access(path, method, code,
                             request_body=form_body)

        if code == 302:
            self._send_redirect(body)
        else:
            self._send_html(code, body, headers)

    def _handle_report(self, method: str, path: str, query: str, conn):
        """委托给 report.py，使用 _handle() 传入的共享连接"""
        form_body = self._read_body() if method == "POST" else None
        code, body, headers = report.handle_request(conn, method, path, query, form_body)
        self._log_web_access(path, method, code,
                             request_body=form_body)

        if code == 302:
            self._send_redirect(body)
        else:
            self._send_html(code, body, headers)

    def _handle_export(self, method: str, path: str, query: str, conn):
        """委托给 export.py，使用 _handle() 传入的共享连接"""
        code, body, headers = export_mod.handle_export(conn, query)

        self.send_response(code)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()
        try:
            if isinstance(body, bytes):
                self.wfile.write(body)
            else:
                self.wfile.write(body.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            # 客户端已断开连接，放弃发送响应（与 _handle_api/_send_html 一致）
            logging.info("导出响应发送失败（客户端已断开）")

    def _handle_api(self, method: str, path: str, query: str, conn=None):
        """
        处理 API 请求（不需要 session 认证，使用 API Key 鉴权）。

        调用 api_handler.handle_api_request 时传入 conn，
        由调用方管理连接生命周期。
        """
        query_params = urllib.parse.parse_qs(query, keep_blank_values=True)
        try:
            body = self._read_body() if method == "POST" else ""
        except BodyReadError as e:
            self._send_html(400, f"请求体读取失败: {e}",
                            {"Content-Type": "text/plain; charset=utf-8"})
            return

        client_ip = _get_client_ip(self.headers, self.client_address)
        start = time.time()
        status, resp_body, resp_headers = api_handler.handle_api_request(
            conn=conn,
            path=path,
            method=method,
            headers=dict(self.headers),
            body=body,
            query_params=query_params,
            client_ip=client_ip,
        )
        duration_ms = int((time.time() - start) * 1000)

        # 记录 API 审计日志（与 _log_api_call 共用，内联块语义一致）
        api_key = query_params.get("api_key", [""])[0] or ""
        if not api_key:
            auth_header = dict(self.headers).get("Authorization", "")
            api_key = auth.extract_bearer_token(auth_header) or ""
        self._log_api_call(path, method, status, api_key=api_key,
                           duration_ms=duration_ms,
                           request_body=body if method == "POST" else "")

        self.send_response(status)
        found_content_type = False
        for key, val in resp_headers.items():
            self.send_header(key, val)
            if key.lower() == "content-type":
                found_content_type = True
        if not found_content_type:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            if isinstance(resp_body, str):
                self.wfile.write(resp_body.encode("utf-8"))
            elif isinstance(resp_body, bytes):
                self.wfile.write(resp_body)
            else:
                self.wfile.write(str(resp_body).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            # 客户端已断开连接，放弃发送响应（常见于全量输出等大响应场景）
            logging.info("API 响应发送失败（客户端已断开）: %s %s", path, method)

    # ---- 辅助方法 ----

    def _write_audit_log(self, *, log_type, session_user, action, entity_type,
                         entity_name, http_method, http_path, http_status,
                         duration_ms, ip_address, request_body):
        """统一写入审计日志（get_audit_db → insert_audit_log → close）。

        页面访问（_log_web_access）与 API 调用（_log_api_call）共用的
        写入链路；request_body 为 None 时按 POST 惰性读取；异常静默吞掉，
        避免审计失败影响业务处理。
        """
        try:
            audit_conn = audit_db.get_audit_db()
            try:
                if request_body is None:
                    request_body = self._read_body() if http_method == "POST" else ""
                audit_db.insert_audit_log(
                    audit_conn,
                    type=log_type,
                    session_user=session_user,
                    action=action,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    http_method=http_method,
                    http_path=http_path,
                    http_status=http_status,
                    duration_ms=duration_ms,
                    ip_address=ip_address,
                    request_body=request_body,
                )
            finally:
                audit_conn.close()
        except Exception:
            pass

    def _log_web_access(self, path: str, method: str, status: int,
                        duration_ms: int = 0, request_body: str = None):
        """记录页面访问（web_access 类型）到审计日志。

        参数:
            request_body: 外部传入已读取的请求体。
                          为 None 时尝试通过 _read_body() 读取（注意：
                          只能在流未被消耗时使用）。
        """
        user = self._get_current_user()
        if not user:
            return
        self._write_audit_log(
            log_type="web_access",
            session_user=user,
            action="page_view",
            entity_type="page",
            entity_name=path,
            http_method=method,
            http_path=path,
            http_status=status,
            duration_ms=duration_ms,
            ip_address=_get_client_ip(self.headers, self.client_address),
            request_body=request_body,
        )

    def _log_api_call(self, path: str, method: str, status: int,
                      api_key: str = "", duration_ms: int = 0,
                      request_body: str = None):
        """记录 API 调用（api 类型）到审计日志。"""
        self._write_audit_log(
            log_type="api",
            session_user=f"api_key:{api_key}" if api_key else "anonymous",
            action="api_call",
            entity_type="api_endpoint",
            entity_name=path,
            http_method=method,
            http_path=path,
            http_status=status,
            duration_ms=duration_ms,
            ip_address=_get_client_ip(self.headers, self.client_address),
            request_body=request_body,
        )

    def _handle_audit(self, method: str, path: str, query: str, conn=None):
        """委托给 audit_page.py，使用 _handle() 传入的共享连接"""
        form_body = self._read_body() if method == "POST" else None
        code, body, headers = audit_page.handle_audit_request(
            method, query, form_body)
        self._log_web_access(path, method, code, request_body=form_body)

        if code == 302:
            self._send_redirect(body)
            return
        if isinstance(body, bytes):
            self.send_response(code)
            for key, val in headers.items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_html(code, body, headers)

    def _read_body(self) -> str:
        """读取 POST 请求体；读取或解码失败时抛出 BodyReadError。"""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            raise BodyReadError("无效的 Content-Length")
        if length > 0:
            try:
                return self.rfile.read(length).decode("utf-8")
            except (UnicodeDecodeError, ValueError, OSError) as e:
                raise BodyReadError(f"请求体读取失败: {e}") from e
        return ""

    def _serve_static_vendor(self, path: str):
        """服务 /static/vendor/ 下的白名单静态文件（版本锁 URL，无鉴权）。

        路径穿越/白名单外扩展名/文件缺失 → 404。响应带 immutable
        Cache-Control（资产 URL 锁定版本，首次加载后零请求）。
        """
        rel_path = path[len(_VENDOR_STATIC_PREFIX):]
        real = _vendor_real_path(rel_path)
        mime = _vendor_mime_for(rel_path)
        if real is None or mime is None:
            return self._send_html(404, "<h1>404 — 页面不存在</h1>")
        if not os.path.isfile(real):
            return self._send_html(404, "<h1>404 — 页面不存在</h1>")
        try:
            with open(real, "rb") as f:
                payload = f.read()
        except OSError:
            return self._send_html(404, "<h1>404 — 页面不存在</h1>")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_html(self, status: int, body: str, extra_headers: dict = None):
        """发送 HTML 响应

        extra_headers 中的 Content-Type 可覆盖默认 text/html（如真实数据
        预览返回 JSON），调用方自行保证 body 编码与之匹配。
        """
        extra_headers = extra_headers or {}
        self.send_response(status)
        self.send_header("Content-Type",
                         extra_headers.get("Content-Type", "text/html; charset=utf-8"))
        if self._session_token:
            self.send_header("Set-Cookie", auth.make_set_cookie_header(self._session_token))
        for k, v in extra_headers.items():
            if k.lower() != "content-type":
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_redirect(self, location: str):
        """发送 302 重定向"""
        self.send_response(302)
        self.send_header("Location", _safe_location(location))
        if self._session_token:
            self.send_header("Set-Cookie", auth.make_set_cookie_header(self._session_token))
        self.end_headers()


# ---------------------------------------------------------------------------
# 代理辅助函数
# ---------------------------------------------------------------------------


def _get_client_ip(headers, client_address) -> str:
    """
    获取客户端 IP。

    默认取 socket 对端地址（client_address[0]）；仅当 server.trust_xff
    配置开启时才信任 X-Forwarded-For 首 IP。X-Forwarded-For 可由客户端
    直接伪造，未置于可信代理之后时无条件信任存在 IP 伪造风险。
    """
    if not get_trust_xff():
        return client_address[0]
    xff = headers.get("X-Forwarded-For", "")
    if xff:
        ips = [ip.strip() for ip in xff.split(",")]
        if ips:
            return ips[0]
    return client_address[0]


def _get_forwarded_url(headers, path: str) -> str:
    """
    构建代理透传后的原始 URL。

    优先 X-Forwarded-Host/Proto，其次 Host 头。
    """
    proto = headers.get("X-Forwarded-Proto", "http")
    host = headers.get("X-Forwarded-Host", "") or headers.get("Host", "localhost")
    return f"{proto}://{host}{path}"


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------


def setup_logging():
    """根据 app_config.json 配置初始化日志系统。"""
    enabled, log_path = get_log_config()
    if not enabled:
        logging.basicConfig(level=logging.WARNING, force=True)
    else:
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            filename=log_path,
            filemode="a",
            force=True,
        )
        logging.info("日志系统已初始化，文件: %s", os.path.abspath(log_path))

    error_log_cfg = get_error_log_config()
    if error_log_cfg["enable"]:
        error_handler = logging.FileHandler(error_log_cfg["path"], encoding="utf-8")
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(error_handler)


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------


def main():
    setup_logging()
    # 初始化运行时文件权限（仅 static_cache 缓存落点 {dir}/api）：
    # 启动时对缓存目录树整树刷新属主/权限，覆盖历史遗留 root:root 文件。
    # 以 {dir}/api 为起点而非 {dir}：dir 可能指向包含其他程序的目录，
    # 权限调整不得波及缓存之外的内容。
    if file_permissions.load_permissions():
        cache_root = static_cache.permissions_root()
        file_permissions.refresh_tree(cache_root)
    try:
        # 初始化配置数据库
        conn = db.get_config_db()
        try:
            db.init_db(conn)

            # 自动创建默认管理员（仅首次启动）
            if not db.get_all_users(conn):
                pw_hash = auth.hash_password("admin123")
                db.add_user(conn, "admin", pw_hash)
                logging.info("首次启动检测：默认管理员已创建")
                logging.info("  用户名: admin")
                logging.info("  密  码: admin123")
                logging.warning("  ⚠️  请尽快登录 /config 修改密码")
        finally:
            conn.close()

        # 初始化审计数据库
        try:
            audit_conn = audit_db.get_audit_db()
            try:
                audit_db.init_audit_db(audit_conn)
                logging.info("审计数据库已初始化")
            finally:
                audit_conn.close()
        except Exception as e:
            logging.warning("审计数据库初始化失败: %s", e)

        # 从 SQLite 恢复 session（使重启后用户无需重新登录）
        auth.load_sessions()

        # 启动时清理过期审计日志
        audit_config = get_audit_db_config()
        if audit_config.get("retention_days", 0) > 0:
            try:
                audit_conn = audit_db.get_audit_db()
                try:
                    deleted = audit_db.rotate_audit_logs(audit_conn, audit_config["retention_days"])
                    if deleted > 0:
                        logging.info("启动时自动清理了 %d 条过期审计日志", deleted)
                finally:
                    audit_conn.close()
            except Exception as e:
                logging.warning("启动时审计日志轮转失败: %s", e)
    except KeyboardInterrupt:
        logging.info("启动被用户中断")
        sys.exit(0)

    # 创建 HTTP 服务器（允许地址重用，避免 Ctrl+Z 暂停后端口仍被占用）
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), ReportHandler)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            # 尝试自动清理占用端口的旧进程
            import subprocess
            try:
                subprocess.run(
                    ["fuser", "-k", f"{PORT}/tcp"],
                    capture_output=True, timeout=5
                )
                logging.info("已清理端口 %s，重新绑定...", PORT)
                server = http.server.ThreadingHTTPServer((HOST, PORT), ReportHandler)
            except Exception:
                logging.error("端口 %s 已被占用", PORT)
                logging.error("请手动执行: fuser -k %s/tcp", PORT)
                logging.error("或: kill -9 $(lsof -ti:%s)", PORT)
                sys.exit(1)
        else:
            raise

    logging.info("服务器已启动: http://%s:%s", HOST, PORT)
    logging.info("按 Ctrl+C 停止服务器")

    # 在守护线程中运行 serve_forever，主线程用 join(timeout) 轮询，
    # 确保 Ctrl+C 能立即中断，不会因为 select() 阻塞而延迟
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1)
    except KeyboardInterrupt:
        logging.info("正在关闭服务器...")
        # 关闭 socket 迫使 serve_forever 退出，避免 shutdown 阻塞
        try:
            server.shutdown()
        except KeyboardInterrupt:
            # 第二次 Ctrl+C 可能在 shutdown 阻塞期间发生
            pass
        server.server_close()
        logging.info("服务器已关闭")


if __name__ == "__main__":
    main()
