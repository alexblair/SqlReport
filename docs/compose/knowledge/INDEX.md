# 模块地图 · 路由 · 页面 · 共享语义

> 现状事实（模块 / 路由 / 页面 / 共享语义）的唯一索引。**不是任务查证入口**——新任务先看 `docs/compose/spec/` 最新生效 spec，「该读哪一卷 / 改完必更新哪一卷」看仓库根 `AGENTS.md` §0。
> 函数、行号、调用链一律以 `codegraph`（硬性 #18）与源码为准，本卷只留路由与约定。

## 1. 模块职责表

单包扁平布局，**无 monorepo**，入口只有 `server.py`。

| 模块 | 职责 |
|------|------|
| `server.py` | HTTP 入口、`ROUTES`、鉴权中间件、vendor 静态 |
| `config.py` | `/config*` 页面与表单 CRUD |
| `config_db.py` | 配置库 DAL、双引擎 schema/迁移 |
| `db.py` | 兼容转发层（仅 re-export；新代码直连 `config_db`/`query_executor`） |
| `report.py` | 报表页、分页排序筛选 URL 解析、`execute_report` |
| `result_transform.py` | **纯函数**筛选/排序/列选择（页/导出/API/预设共用） |
| `filter_help.py` | 筛选语法帮助文案单一来源 |
| `export.py` | CSV/JSON/ZIP 导出 |
| `api_handler.py` | `/api/*`、Key、CORS、静态 `.json`、预设/模板 |
| `query_executor.py` | MySQL 事务多语句、有界连接池、`sql_contains_write` / `sql_has_persistent_write` |
| `render.py` | **全站 UI 单一来源**（CSS/JS/`build_*`/图标辅助） |
| `redis_cache.py` | L2 Redis 快照、分布式锁 |
| `static_cache.py` | API `.json` 静态文件缓存 |
| `scheduler.py` | 进程内定时任务线程 |
| `auth.py` | PBKDF2 密码、Session、登录限流 |
| `audit_db.py` / `audit_page.py` | 审计库与审计页 |
| `branding.py` | 站点标识 / favicon（实例本地 SQLite） |
| `app_config.py` | `app_config.json` + DEBUG 深合并 |
| `preset_cases.py` / `json_template.py` | 预设导入、API JSON 模板 |
| `markdown_render.py` | 备注等 Markdown → HTML（含 mermaid） |
| `file_permissions.py` | 产出文件属主/权限 |

## 2. 路由总表（`server.py` `ROUTES`，顺序首次匹配）

| 方法 | 模式 | auth | db | handler |
|------|------|------|----|---------|
| GET | `^/favicon\.ico$` | 否 | 否 | `_handle_favicon` |
| GET/POST | `^/login$` | 否 | 否 | 登录页/提交 |
| GET | `^/health$` | 否 | 否 | `_handle_health` |
| GET | `^/?$` | 是 | 否 | 首页 → `/report` |
| GET | `^/logout$` | 是 | 否 | `_handle_logout` |
| GET/POST | `^/config/api-endpoints$` | 是 | 是 | 独立 API 管理页 |
| GET | `^/config/reports$` | 是 | 是 | 报表列表 |
| POST | `^/config/reports/memo-preview$` | 是 | 否 | 备注 Markdown 预览 |
| POST | `^/config/api-endpoints/description-preview$` | 是 | 否 | 接口说明预览 |
| GET | `^/config/categories$` | 是 | 是 | 分类页 |
| POST | `^/config/site-branding$` | 是 | 是 | 品牌保存 |
| * | `^/config($|/)` | 是 | 是 | `_handle_config` → `config.handle_request`（含调度/池/用户子页） |
| * | `^/report($|/)` | 是 | 是 | `_handle_report` → `report.handle_request` |
| * | `^/export($|/)` | 是 | 是 | `_handle_export` → `export.handle_export` |
| * | `^/api/` | **否** | 是 | `_handle_api` → `api_handler.handle_api_request` |
| * | `^/audit($|/)` | 是 | **否** | `_handle_audit` → `audit_page` |

- 静态：`/static/vendor/<name@ver>/<file>` 白名单直出（无鉴权）+ 扩展名 MIME 白名单。
- 新 URL **必须**进 `ROUTES`，注意与更宽正则（如 `/config($|/)`）的先后。

## 3. 页面地图（用户可见 · UI v2 重构后）

| 路径 | 内容 |
|------|------|
| `/login` | 登录；失败限流 5 次/5 分钟；过期提示 + `next` 白名单 |
| `/` | 302 → `/report` |
| `/report`（无 id） | **报表中心**：搜索 + 最近查看 + 左分类树 + 右报表卡片 |
| `/report?id=` | 报表详情：五页签（数据/规则/接口/调试/备注）；数据页独立快筛行、多结果集 segment、分页恒显；规则双卡、调试磁贴、备注卡片；列设置/排序抽屉、导出对话框、缓存状态行、护栏横幅 |
| `/report/preview` | POST 预览未保存 SQL |
| `/export?id=N` | CSV/JSON/ZIP 导出（详情页导出对话框发起） |
| `/config` | 概览仪表盘：统计磁贴、快捷入口、系统状态/导入演示数据（DEBUG）、站点标识独立行、首部署引导 |
| `/config/pools*` | 连接池**独立列表页** + 表单（含「关联报表」＝渲染层按 pool_id 分组，不改 DB；测试连接/复制/移动/破坏半径披露） |
| `/config/users*` | 用户**独立列表页** + 表单（users 表无 role 字段，按平权管理员实义渲染；会话清理/禁删自身） |
| `/config/reports*` | 报表配置：搜索 + 左分类树右报表表 + 批量条 + 列表/卡片双视图开关（localStorage 记忆，两视图共享勾选） |
| `/config/reports/add\|{id}/edit\|copy` | 分区表单（基础/SQL/缓存与护栏/调度与保活）+ sticky 保存底栏；表单下接口列表联动 |
| `/config/api-endpoints` | API 列表（统计 + 新建；主行 + 展开区卡片、路径徽标）+ 端点表单分区 + Key 区 |
| `/config/scheduler` | 定时任务**列表主导**：7 列单表，**无第二张执行表**（历史到审计日志查询）；全局停用横幅 |
| `/config/scheduler/new`、`/{id}/edit` | 任务独立表单页（`?edit=N` 兼容；`?report_id=N` 仅新建生效）；排除规则可视化树 + 源码 JSON 模式 |
| `/config/categories` | 重定向 `/config/reports#sec-categories` |
| `/config/site-branding` | 站点标识 POST |
| `/audit` | 审计日志：导出/清理 + 统一筛选条与表格（裸排无 card） |
| `/health` | JSON 健康检查 |
| `/api/...` | 数据 API；`...json` 静态变体 |
| `/favicon.ico` | branding 三模式 |

## 4. 共享语义（改一处必须全链路对齐）

| 语义 | 单一来源 | 调用方 |
|------|----------|--------|
| 筛选值匹配 | `result_transform.parse_filter_expr` | report / export / api / audit |
| 嵌套筛选 | `parse_nested_filter` + `validate_nested_filter` | report / export / api |
| 排序/列选择 | `sort_rows` / `select_columns` | report / export / api |
| 筛选帮助文案 | `filter_help.py` | report / audit |
| 写护栏文案 | `report.WRITE_DENIED_MESSAGE` 等 | report / export / api / config 编辑 |
| 用户可见术语（缓存/品牌等） | `docs/compose/spec/ui-redesign-visual-spec.md` §5 术语表 | render 缓存徽标/横幅、标题 |
| 全量输出护栏 | `allow_all_output` + `max_rows` | report / export / api |
| 页面骨架/CSS/JS | `render.render_page_header/footer`、`_NAV_GROUPS`（侧栏三态收缩 + `set_request_user`）、`_BASE/_COMMON_*`（设计令牌）；hash 含 CSS+JS | 全站 |
| 表单 flash/302 模式 | 各 `handle_*` 返回 `(code, url, headers)` | config / report |

## 5. 审计四类 type（速查）

| type | 谁写 | 说明 |
|------|------|------|
| `operation` | auth / config CRUD / 部分调度 | 配置与登录类 |
| `web_access` | `server._log_web_access` | 已登录页面访问 |
| `api` | `server._log_api_call` | API 调用（≠ api_handler 内 logging） |
| `scheduler` | `record_operation(log_type=…)` | 定时任务链 |

## 6. 路由处理链速查

`server._handle`：路径归一 + `/static/vendor` 白名单 → `ROUTES` 首次匹配 → `needs_auth`（session / 302 login）→ `needs_db`（`get_config_db`，audit 除外）→ 各 `handle_*` → `_send_html` / `_send_redirect`（刷新 Session Cookie）→ `_log_web_access` / `_log_api_call`。细节见 `02-routing-auth.md`。

## 7. 索引与检索

读/分析代码**强制先走 `codegraph`**，查不到才降级 grep/read（硬性 #18）；改完 `.py`/`.js`/`.mjs` **必须 `codegraph sync`**（硬性 #19）。命令表、降级白名单、实测坑见 `09-agent-workflow.md`；`.codegraph/` 已 gitignore，当前计数见 `README.md`。

**跨会话记忆**：仓库根 `MEMORY.md`（Rules + Discovered），每轮开工前必读；不属分卷。
