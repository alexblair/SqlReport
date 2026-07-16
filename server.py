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
import logging
import urllib.parse
import http.server
import threading
import db
import auth
import config
import report
import export as export_mod
from app_config import get_server_config, get_log_config

# ---------------------------------------------------------------------------
# 配置（从 app_config.json 加载，支持环境变量 HOST / PORT 覆盖）
# ---------------------------------------------------------------------------

HOST, PORT = get_server_config()

# ---------------------------------------------------------------------------
# 登录页 HTML
# ---------------------------------------------------------------------------

_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web 报表工具 - 登录</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; margin: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  }
  .login-box {
    background: #fff; padding: 40px; border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15); width: 380px;
    animation: fadeUp 0.4s ease-out;
  }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
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
    RouteEntry(r"^/?$", "GET", True, False, "_handle_home_redirect"),
    RouteEntry(r"^/logout$", "GET", True, False, "_handle_logout"),
    RouteEntry(r"^/config($|/)", "*", True, True, "_handle_config"),
    RouteEntry(r"^/report($|/)", "*", True, True, "_handle_report"),
    RouteEntry(r"^/export($|/)", "*", True, True, "_handle_export"),
]


def _match_route(method: str, path: str) -> RouteEntry | None:
    """在路由表中查找匹配的路由条目。

    Args:
        method: HTTP 方法（GET/POST）。
        path: URL 路径。

    Returns:
        匹配的 RouteEntry，未匹配返回 None。
    """
    for route in ROUTES:
        if not route.pattern.search(path):
            continue
        if route.method != "*" and method != route.method:
            continue
        return route
    return None


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

    def _handle(self, method: str):
        """基于路由表分发请求"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parsed.query

        route = _match_route(method, path)
        if route is None:
            return self._send_html(404, "<h1>404 — 页面不存在</h1>")

        if route.needs_auth and not self._authenticate():
            return

        if route.needs_db:
            conn = db.get_config_db()
            try:
                getattr(self, route.handler)(method, path, query, conn)
            finally:
                conn.close()
        else:
            getattr(self, route.handler)(method, path, query, None)

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
        return True

    def _handle_login_get(self, method, path, query, conn=None):
        """显示登录页"""
        self._send_html(200, _render_login_page())

    def _handle_home_redirect(self, method, path, query, conn=None):
        """首页重定向到 /report"""
        self._send_redirect("/report")

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
                self.send_response(302)
                self.send_header("Location", "/report")
                self.send_header("Set-Cookie", auth.make_set_cookie_header(token))
                self.end_headers()
                return
        finally:
            conn.close()

        # 登录失败
        self._send_html(200, _render_login_page("用户名或密码错误"))

    def _handle_logout(self, method=None, path=None, query=None, conn=None):
        """处理退出"""
        cookie_header = self.headers.get("Cookie", "")
        cookies = auth.parse_cookie(cookie_header)
        token = cookies.get("session_id")
        if token:
            auth.remove_session(token)
        self.send_response(302)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", auth.make_expire_cookie_header())
        self.end_headers()

    # ---- 各功能路由 ----

    def _handle_config(self, method: str, path: str, query: str, conn):
        """委托给 config.py，使用 _handle() 传入的共享连接"""
        form_body = self._read_body() if method == "POST" else None
        code, body, headers = config.handle_request(conn, method, path, query, form_body)

        if code == "302":
            self._send_redirect(body)
        else:
            self._send_html(int(code), body, headers)

    def _handle_report(self, method: str, path: str, query: str, conn):
        """委托给 report.py，使用 _handle() 传入的共享连接"""
        form_body = self._read_body() if method == "POST" else None
        code, body, headers = report.handle_request(conn, method, path, query, form_body)
        self._send_html(int(code), body, headers)

    def _handle_export(self, method: str, path: str, query: str, conn):
        """委托给 export.py，使用 _handle() 传入的共享连接"""
        code, body, headers = export_mod.handle_export(conn, query)

        code_int = int(code)
        self.send_response(code_int)
        for key, val in headers.items():
            self.send_header(key, val)
        self.end_headers()
        if isinstance(body, bytes):
            self.wfile.write(body)
        else:
            self.wfile.write(body.encode("utf-8"))

    # ---- 辅助方法 ----

    def _read_body(self) -> str:
        """读取 POST 请求体"""
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length).decode("utf-8")
        return ""

    def _send_html(self, status: int, body: str, extra_headers: dict = None):
        """发送 HTML 响应"""
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_redirect(self, location: str):
        """发送 302 重定向"""
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------


def setup_logging():
    """根据 app_config.json 配置初始化日志系统。"""
    enabled, log_path = get_log_config()
    if not enabled:
        logging.basicConfig(level=logging.WARNING, force=True)
        return

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


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------


def main():
    setup_logging()
    try:
        # 初始化数据库
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

        # 从 SQLite 恢复 session（使重启后用户无需重新登录）
        auth.load_sessions()
    except KeyboardInterrupt:
        logging.info("启动被用户中断")
        sys.exit(0)

    # 创建 HTTP 服务器（允许地址重用，避免 Ctrl+Z 暂停后端口仍被占用）
    http.server.HTTPServer.allow_reuse_address = True
    try:
        server = http.server.HTTPServer((HOST, PORT), ReportHandler)
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
                server = http.server.HTTPServer((HOST, PORT), ReportHandler)
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


if __name__ == "__main__":
    main()
