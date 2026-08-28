---
module: server
contract_id: MOD-SERVER
version: 1.0
depends_on: [db, auth, branding, config, report, scheduler, render, export, api_handler, audit_db, audit_page, file_permissions, static_cache, app_config]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# server.py 模块分卷

> 本分卷由 T-005 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`server.py`（1110 行，50 个 def）——**HTTP 服务器入口**。基于 `http.server.ThreadingHTTPServer`，负责：有序路由分发（首次匹配优先）、Session Cookie 认证中间件、登录/退出/首页/健康检查、静态文件白名单服务（vendor）、favicon 三模式动态服务、审计日志写入、统一错误页。是全局唯一请求入口，其余业务模块均通过委托模式被调用。

## 2. 公开 API 契约

### 2.1 入口函数

- `setup_logging()` → None：根据 app_config 初始化日志系统（常规 + 错误日志双 Handler）。
- `main()` → None：入口函数：日志 → 公共资产 → 文件权限 → 数据库初始化 → 审计库 → session 恢复 → 审计轮转 → HTTP 服务器 → 启动调度器 → serve_forever。

### 2.2 类

- `RouteEntry(pattern, method, needs_auth, needs_db, handler)`：路由条目（URL 模式、HTTP 方法、认证/DB 需求、处理方法名）。
- `ReportHandler(BaseHTTPRequestHandler)`：主 HTTP 请求处理器。
- `BodyReadError(Exception)`：请求体读取/解码失败（映射 HTTP 400）。

### 2.3 HTTP 路由表（ROUTES，顺序优先）

| 方法 | 路径模式 | 认证 | DB | 处理器 |
|---|---|---|---|---|
| GET | `/static/vendor/*` | ✗ | ✗ | `_serve_static_vendor`（路由表前拦截） |
| GET | `/favicon.ico` | ✗ | ✗ | `_handle_favicon`（三模式动态） |
| GET | `/login` | ✗ | ✗ | `_handle_login_get` |
| POST | `/login` | ✗ | ✗ | `_handle_login`（限流 → 密码校验 → session → 跳转） |
| GET | `/health` | ✗ | ✗ | `_handle_health`（JSON 健康检查 + uptime） |
| GET | `/` | ✓ | ✗ | `_handle_home_redirect`（→ 302 /report） |
| GET | `/logout` | ✓ | ✗ | `_handle_logout`（清除 session → 302 /login） |
| GET/POST | `/config/api-endpoints` | ✓ | ✓ | `_handle_config_api_endpoints` |
| GET | `/config/reports` | ✓ | ✓ | `_handle_config_reports` |
| POST | `/config/reports/memo-preview` | ✓ | ✗ | `_handle_config` |
| POST | `/config/api-endpoints/description-preview` | ✓ | ✗ | `_handle_config` |
| GET | `/config/categories` | ✓ | ✓ | → 302 `/config/reports` |
| POST | `/config/site-branding` | ✓ | ✓ | `_handle_config_site_branding` |
| * | `/config/...` | ✓ | ✓ | `_handle_config`（通配） |
| * | `/report/...` | ✓ | ✓ | `_handle_report`（通配） |
| * | `/export/...` | ✓ | ✓ | `_handle_export`（通配） |
| * | `/api/...` | ✗ | ✓ | `_handle_api`（API Key 鉴权） |
| * | `/audit/...` | ✓ | ✗ | `_handle_audit` |

### 2.4 ReportHandler 内部方法（按职责域）

**认证：**
- `_authenticate()` → bool：Session cookie 校验，未认证重定向 `/login?expired=1&next=...`；成功刷新滑动过期。
- `_get_current_user()` → str|None：从 cookie 获取用户名。

**路由处理器：**
- `_handle_login_get` / `_handle_login`：登录页显示 / 登录提交（限流 → 密码 → session → 跳转）。
- `_handle_home_redirect` / `_handle_logout` / `_handle_health`：首页重定向 / 退出 / 健康检查。
- `_handle_config` / `_handle_config_api_endpoints` / `_handle_config_reports` / `_handle_config_categories` / `_handle_config_site_branding`：配置管理各子路径。
- `_handle_report` / `_handle_export` / `_handle_api` / `_handle_audit`：报表/导出/API/审计。

**I/O 辅助：**
- `_read_body()` → str：读取 POST 请求体（失败抛 BodyReadError）。
- `_write_body(payload)`：写出响应体（HEAD 跳过，BrokenPipe 静默）。
- `_send_html(status, body, extra_headers=None)`：发送 HTML 响应（自动注入 Set-Cookie）。
- `_send_redirect(location)`：302 重定向（含 Location 头安全编码兜底）。
- `_serve_static_vendor(path)`：白名单静态文件服务（immutable cache）。

**审计：**
- `_write_audit_log(**kwargs)`：统一审计日志写入（异常静默）。
- `_log_web_access(path, method, status, ...)`：页面访问审计。
- `_log_api_call(path, method, status, api_key, ...)`：API 调用审计。

**安全工具：**
- `_render_login_page(error="")` / `_render_login_page_ex(error, expired, next_url)`：登录页渲染（含过期提示 + next 透传）。
- `_sanitize_next_url(next_url)` → str：next 回跳白名单（仅站内绝对路径）。
- `_safe_next_target(next_url)` → str：登录跳转目标（合法 next 或默认 `/report`）。
- `_render_error_page(status, title)` → str：统一错误页模板。
- `_vendor_real_path(rel_path)` → str|None：静态文件路径安全规范化（防 `..` 穿越）。
- `_safe_location(location)` → str：Location 头 latin-1 安全编码。
- `_get_client_ip(headers, client_address)` → str：客户端 IP（仅 trust_xff=True 时信任 XFF）。
- `_get_forwarded_url(headers, path)` → str：代理透传原始 URL。

## 3. 数据流

```
HTTP 请求 → ThreadingHTTPServer → ReportHandler._handle(method)
  ├─ 路径解析: path.split('?') → _get_forwarded_url (X-Forwarded-Host/Proto)
  ├─ 静态文件: /static/vendor/* → _serve_static_vendor（白名单 MIME + immutable cache）
  ├─ favicon: /favicon.ico → _handle_favicon（三模式：default/color/custom）
  ├─ 路由匹配: _match_route(method, path) → RouteEntry
  │    无匹配 → 404 / 405（Allow 头）
  ├─ 认证: needs_auth → _authenticate()（Session cookie 校验 + 滑动刷新）
  │    未认证 → 302 /login?expired=1&next=...
  ├─ DB 连接: needs_db → db.get_config_db()
  ├─ 处理器: handler(method, path, query, conn) → 各 _handle_* 委托
  │    ├─ _handle_config → config.handle_request()
  │    ├─ _handle_report → report.handle_request()
  │    ├─ _handle_export → export.handle_export()
  │    ├─ _handle_api → api_handler.handle_api_request()
  │    └─ _handle_audit → audit_page.handle_audit_request()
  ├─ 异常处理: _send_error(status) / _render_error_page(status, title)
  └─ 审计: _log_web_access / _log_api_call

启动流程: main()
  setup_logging → ensure_common_assets → file_permissions.load_permissions
  → db.init_db（含自动创建 admin）→ audit_db.init_audit_db
  → auth.load_sessions → audit_db.rotate_audit_logs
  → ThreadingHTTPServer((HOST, PORT), ReportHandler)
  → scheduler.start_scheduler_from_config → serve_forever
```

## 4. 依赖关系

AST import 实测：`db, auth, branding, config, report, scheduler, render, export, api_handler, audit_db, audit_page, file_permissions, static_cache, app_config`（14 个内部依赖，为模块中依赖面最广之一）。
- 认证/会话：`auth`（Session 管理）。
- 路由委托：`config`/`report`/`export`/`api_handler`/`audit_page`。
- 初始化：`db`（配置库）/`audit_db`（审计库）/`scheduler`（调度器）/`file_permissions`（文件权限）。
- 静态资源：`branding`（favicon）/`render`（公共 CSS/JS）/`static_cache`（静态资产）。

## 5. 边界与异常

- 路由表顺序优先：首次匹配即生效，`/static/vendor/*` 在路由表前直接拦截。
- 405 处理：`_allowed_methods_for_path` 计算允许方法列表 + Allow 头。
- Location 头安全编码：`_safe_location` latin-1 兜底 + 非 ASCII 自动百分号编码。
- next 回跳白名单：`_sanitize_next_url` 仅站内绝对路径（/ 开头，非 //），防开放重定向。
- BodyReadError：请求体读取/解码失败 → HTTP 400。
- BrokenPipe：`_write_body` 静默忽略。
- 优雅退出：KeyboardInterrupt → scheduler.shutdown → server.shutdown → server_close。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 server.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
