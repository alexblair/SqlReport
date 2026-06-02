"""
auth.py — 简易 Cookie 认证

职责：
- 用户密码哈希存储与校验（SHA-256 + salt）
- Session 管理（内存 dict + SQLite 持久化，应用重启后 session 恢复）
- 提供装饰器辅助 HTTP handler 校验登录状态

设计原则：
- 不引入外部依赖，使用 hashlib、secrets、hmac 等标准库
- 内存 dict 作为 session 主存储（快速访问），SQLite 持久化保证重启不丢失
- DB 写入失败不影响请求（降级为纯内存，功能不受损）
- 密码使用随机 salt + SHA-256 迭代哈希，避免彩虹表攻击
"""

import hashlib
import secrets
import hmac
from typing import Optional

import db

# ---------------------------------------------------------------------------
# 密码处理
# ---------------------------------------------------------------------------

# 哈希迭代次数（可调，越大越安全但越慢）
_HASH_ITERATIONS = 100000
_SALT_LENGTH = 16


def hash_password(password: str) -> str:
    """
    对密码进行加盐哈希。

    返回格式: salt$hex_digest（salt 和摘要均为十六进制编码）
    """
    salt = secrets.token_hex(_SALT_LENGTH)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _HASH_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    校验密码是否与存储的哈希匹配。

    使用 hmac.compare_digest 进行常量时间比较，防止时序攻击。
    """
    try:
        salt, hex_digest = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _HASH_ITERATIONS)
    return hmac.compare_digest(digest.hex(), hex_digest)


# ---------------------------------------------------------------------------
# Session 管理
# ---------------------------------------------------------------------------

# 内存 session 存储: {session_token: username}
# 应用重启后通过 load_sessions() 从 SQLite 恢复
_sessions: dict[str, str] = {}

# Session token 字节长度
_SESSION_TOKEN_BYTES = 32


def load_sessions() -> None:
    """
    从 SQLite 加载持久化 session 到内存。

    在服务器启动时调用，使已登录用户无需重新登录。
    优雅降级：DB 不可用时仅打印警告，不阻止启动。
    """
    try:
        conn = db.get_config_db()
        try:
            for s in db.get_all_sessions(conn):
                _sessions[s["token"]] = s["username"]
        finally:
            conn.close()
    except KeyboardInterrupt:
        raise  # Ctrl+C 正常传播
    except Exception as exc:
        print(f"[auth] session 加载失败（降级至纯内存）: {exc}")


def create_session(username: str) -> str:
    """
    为用户创建一个新的 session token。

    写入内存 dict，同时持久化到 SQLite。
    DB 写入失败不影响登录（降级为纯内存）。
    """
    token = secrets.token_hex(_SESSION_TOKEN_BYTES)
    _sessions[token] = username
    try:
        conn = db.get_config_db()
        try:
            db.add_session(conn, token, username)
        finally:
            conn.close()
    except Exception:
        pass  # 降级：纯内存 session
    return token


def get_session_user(token: str) -> Optional[str]:
    """根据 session token 返回用户名，token 无效或过期返回 None。"""
    return _sessions.get(token)


def remove_session(token: str) -> bool:
    """删除 session，成功返回 True。同时从 SQLite 移除。"""
    existed = _sessions.pop(token, None) is not None
    try:
        conn = db.get_config_db()
        try:
            db.remove_session(conn, token)
        finally:
            conn.close()
    except Exception:
        pass
    return existed


def clear_all_sessions() -> None:
    """清空所有 session（内存 + SQLite）。"""
    _sessions.clear()
    try:
        conn = db.get_config_db()
        try:
            db.clear_sessions(conn)
        finally:
            conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTTP Cookie 工具
# ---------------------------------------------------------------------------


def parse_cookie(cookie_header: str) -> dict[str, str]:
    """
    解析 HTTP Cookie 请求头为字典。

    示例: "session_id=abc123; theme=dark" -> {"session_id": "abc123", "theme": "dark"}
    """
    cookies = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            cookies[key.strip()] = val.strip()
    return cookies


def make_set_cookie_header(session_token: str, max_age: int = 86400) -> str:
    """
    生成 Set-Cookie 响应头字符串。

    默认 session 有效期 24 小时（max_age=86400 秒）。
    设置 HttpOnly 和 SameSite=Lax 防止 XSS/CSRF。
    """
    return (
        f"session_id={session_token}; "
        f"Max-Age={max_age}; "
        "Path=/; "
        "HttpOnly; "
        "SameSite=Lax"
    )


def make_expire_cookie_header() -> str:
    """生成清除 session cookie 的响应头（max-age=0）。"""
    return "session_id=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"
