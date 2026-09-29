# 路由 · 鉴权 · 审计入口

## 请求主流程（`ReportHandler._handle` ~:413）

```
1. urlparse → path.rstrip("/") → unquote
2. /static/vendor/ 前缀 → 白名单静态（仅 GET；MIME 白名单；realpath 防穿越；
   Cache-Control: public, max-age=31536000, immutable）
3. _match_route（ROUTES 列表顺序首次匹配；method="*" 仅 GET/POST/OPTIONS）
   无匹配：有 Allow→405；否则 404（统一 _render_error_page）
4. needs_auth → _authenticate
   Cookie session_id → auth.get_session_user
   无效 → 302 /login?expired=1&next=<urlquote(path)>
   有效 → refresh_session + 记 _session_token
   + render.set_request_user(user)（侧栏账户区等渲染层取当前用户名；
     `_handle` 入口先 set_request_user(None) 复位，公开页/未登录为 None）
5. needs_db → get_config_db → handler → finally close；否则 conn=None
6. BodyReadError→400；其它→日志+500（详情不进响应体）
```

`_send_html/_send_redirect`：有 `_session_token` 时下发滑动 Set-Cookie；Location 经 `_safe_location`。

业务委托：config / report / export / api（+审计 type=api）/ audit_page。

`/health`：公开，`{"status":"ok","uptime":int}`。  
客户端 IP：默认 socket；`trust_xff` 才信 XFF 首 IP。

## 路由表（`server.py` `ROUTES`）

> ⚠️ **`ROUTES` 按列表顺序首次匹配**——新 URL 必须进 `ROUTES`，且注意与既有正则的先后关系。
> 改路由前先读 `server.py` 的 `ROUTES` 与 `ReportHandler._handle*`，再改业务模块。

| 方法 | 模式 | auth | db | handler |
|------|------|------|----|---------|
| GET | `^/favicon\.ico$` | 否 | 否 | `_handle_favicon` |
| GET/POST | `^/login$` | 否 | 否 | 登录 |
| GET | `^/health$` | 否 | 否 | `_handle_health` |
| GET | `^/?$` | 是 | 否 | → `/report` |
| GET | `^/logout$` | 是 | 否 | `_handle_logout` |
| GET/POST | `^/config/api-endpoints$` | 是 | 是 | API 管理 |
| GET | `^/config/reports$` | 是 | 是 | 报表列表 |
| POST | `^/config/reports/memo-preview$` | 是 | **否** | `_handle_config` |
| POST | `^/config/api-endpoints/description-preview$` | 是 | **否** | `_handle_config` |
| GET | `^/config/categories$` | 是 | 是 | 分类 |
| POST | `^/config/site-branding$` | 是 | 是 | 品牌 |
| * | `^/config($|/)` | 是 | 是 | `_handle_config` |
| * | `^/report($|/)` | 是 | 是 | `_handle_report` |
| * | `^/export($|/)` | 是 | 是 | `_handle_export` |
| * | `^/api/` | **否** | 是 | `_handle_api` |
| * | `^/audit($|/)` | 是 | **否** | `_handle_audit` |

**公开面**：`/favicon`、`/login`、`/health`、`/static/vendor/*`、`/api/*`（API Key）。  
preview 路由 `conn=None`——config 不能假设总有连接。  
`/audit` 只连 audit.db。

## 登录 / Session（`auth.py`）

| 能力 | 实现 |
|------|------|
| 密码 | PBKDF2-HMAC-SHA256，100k 迭代，`salt$hex`，`hmac.compare_digest` |
| 限流 | 5 分钟 5 次失败拒该用户名（先于密码校验，防枚举） |
| Session | 内存主存 + sessions 表；`_SESSION_TTL=86400` 滑动 |
| 创建/刷新 | `create_session` / `refresh_session`（每次成功认证） |
| Cookie | `session_id=...; Max-Age=86400; Path=/; HttpOnly; SameSite=Lax`（**无 Secure**） |
| 持久化失败 | warning，纯内存降级 |
| 改密/删用户 | 必须 `remove_sessions_for_user` |
| `next` | 仅 `/` 开头且非 `//`、`/\`；否则回落 `/report` |
| 审计 | login / login_failed / logout / login_throttled（空用户名不写 operation） |

## 审计

四类 `audit_logs.type`：

| type | 写入点 |
|------|--------|
| `operation` | auth 登录事件、config CRUD（`config_db._write_audit_log`）、调度部分 |
| `web_access` | `server._log_web_access`（已登录页面访问） |
| `api` | `server._log_api_call` |
| `scheduler` | `record_operation(log_type=scheduler)` |

- 独立 `audit.db` WAL；`needs_db=False` 的 `/audit` 不用配置 conn  
- 筛选键：`type|date_from|date_to|session_user|keyword`  
- keyword 经 `parse_filter_expr` → LIKE，字段：`action OR entity_name OR http_path OR session_user`  
- 失败一律 warning 不阻断业务  
- 每次进 `/audit` 前 `_rotate_expired`；`retention_days<=0` 不清理  
- **POST 体只能读一次**：`_log_web_access(request_body=None)` 危险，须传 `form_body` 或 `""`

## 鉴权边界

- **Session Cookie**：除公开路由（`/login`、`/health`、`/api/`、静态 vendor 等）外均需认证。
- **API 不走 Session**：`Authorization: Bearer <key>` 或 `?api_key=`，常数时间比较见 `api_handler._validate_api_key`。
- `RouteEntry.needs_auth` / `needs_db` 决定是否走 `_authenticate()` 与是否开配置库连接；`needs_db=False` 的 handler 收到 `conn=None`。

## 易踩坑

1. 新路由插错顺序被宽正则吞掉（**`ROUTES` 首次匹配**）
2. flash 必须 quote 才能进 Location
3. Cookie 无 Secure——HTTPS 靠反代
4. `operation` 默认不记 IP；只有 web_access/api 经 server 链路带 IP
5. keyword 不搜 status/body
6. 轮转依赖 ISO timestamp 文本比较

---
最后核对：explore-1 报告 + 2026-09-29 从 AGENTS.md 迁入「路由与鉴权」要点
