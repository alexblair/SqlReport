---
module: auth.py
contract_id: MOD-AUTH
version: 1.0
depends_on: [audit_db, db]
last_reviewed_commit: 9652dab
last_reviewed_at: 2026-08-28
---

# auth.py 模块分卷

> 本分卷由 T-004 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`auth.py`（318 行，18 个 def）——**简易 Cookie 认证**。负责 Web 会话管理（session token 创建/校验/滑动过期/持久化）、密码加盐哈希与校验、登录失败限流（滑动窗口）、Cookie/Bearer 解析与 Set-Cookie 生成、认证事件审计。被 `server.py` 的 `_authenticate`/登录/登出处理器直接使用，被 api_handler 的 Bearer token 解析复用。

## 2. 公开 API 契约（逐函数）

### 2.1 登录限流（滑动窗口）

- `register_login_failure(username)`：记录一次登录失败（滑动窗口追加，过期条目剔除）。
- `clear_login_failures(username)`：登录成功后清零失败计数。
- `is_login_blocked(username)` -> bool：窗口内失败次数达到上限（`LOGIN_MAX_FAILURES`）即拒绝（不区分后续密码是否正确）。
- `reset_login_failures()`：清空全部限流状态（测试隔离用）。

### 2.2 密码

- `hash_password(password)` -> str：加盐哈希。
- `verify_password(password, password_hash)` -> bool：校验密码与存储哈希是否匹配。

### 2.3 会话（内存 + SQLite 持久化）

- `load_sessions()`：从 SQLite 加载持久化 session 到内存（应用重启恢复）。
- `create_session(username)` -> str：创建 session token（`secrets.token_hex(32)`）；写入内存 dict + 持久化 SQLite；DB 写入失败不影响登录（降级纯内存）。
- `get_session_user(token)` -> str | None：返回用户名；token 无效或过期（`_SESSION_TTL = 86400` 24h）返回 None。
- `refresh_session(token)`：刷新 session 时间戳（滑动过期）；同步更新 SQLite（REPLACE INTO）。
- `remove_session(token)` -> bool：删除 session（内存 + SQLite）。
- `remove_sessions_for_user(username)` -> int：注销指定用户全部会话（内存 + SQLite），返回清除 token 数。
- `clear_all_sessions()`：清空所有 session（内存 + SQLite）。

### 2.4 HTTP 头解析与生成

- `extract_bearer_token(auth_header)` -> str | None：从 Authorization 头提取 Bearer token；非 Bearer 格式返回 None。
- `parse_cookie(cookie_header)` -> dict：解析 HTTP Cookie 请求头为字典。
- `make_set_cookie_header(token, max_age)` -> str：生成 Set-Cookie 响应头。
- `make_expire_cookie_header()` -> str：生成清除 session cookie 的响应头（max-age=0）。

### 2.5 审计

- `_record_auth_event(username, event)`：记录登录/登出/登录失败事件到审计日志（薄包装，统一走 `audit_db.record_operation`）。

## 3. 数据流

```
登录: handle_login → auth.verify_password(user.password_hash) 匹配
      → create_session(username) → token → Set-Cookie
      → clear_login_failures(username) → _record_auth_event("login")
      （失败 → register_login_failure → _record_auth_event("login_failed")）

请求鉴权: server._authenticate → parse_cookie → get_session_user(token)
      （有效 → refresh_session(token) 滑动过期；无效 → 302 /login?expired=1&next=...）

退出: handle_logout → remove_session(token) → make_expire_cookie_header → 302 /login

API Key 场景: api_handler → auth.extract_bearer_token(Authorization) 提取 Bearer
```

## 4. 依赖关系

AST import 实测：`audit_db, db`。
- `db`：`get_user`/`add_session`（config_db 转发）。
- `audit_db`：认证事件审计记录。
- 内部状态：`_sessions`（内存 dict，线程安全 `_sessions_lock`）、`_login_failures`（限流窗口，`_login_failures_lock`）。

## 5. 边界与异常

- 会话 TTL：`_SESSION_TTL = 86400`（24h），滑动过期（每次请求刷新）。
- DB 降级：session 持久化失败不影响登录（纯内存降级，`logging.warning`）。
- 限流窗口：`_LOGIN_WINDOW_SECONDS` 内失败达 `LOGIN_MAX_FAILURES` 即阻断（不区分密码对错）。
- 过期清理：`delete_expired_sessions`（config_db）清理 >24h 会话。
- token：`secrets.token_hex(32)`（64 十六进制字符，密码学安全随机）。

## 6. 保鲜核对提交点

- last_reviewed_commit: 9652dab（T-003 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 auth.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
