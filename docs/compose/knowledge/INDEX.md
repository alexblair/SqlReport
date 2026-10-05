# 模块地图 · 路由 · 页面 · 共享语义

## 1. 模块职责表

> 行数为 2026-10-06 `wc -l` 实测；会随改动漂移，引用前以实测为准。

| 模块 | 行数约 | 职责 |
|------|--------|------|
| `server.py` | 1065 | HTTP 入口、`ROUTES`、鉴权中间件、vendor 静态 |
| `config.py` | 2971 | `/config*` 页面与表单 CRUD |
| `config_db.py` | 2530 | 配置库 DAL、双引擎 schema/迁移 |
| `db.py` | 50 | 兼容转发层（仅 re-export） |
| `report.py` | 2225 | 报表页、分页排序筛选 URL、`execute_report` |
| `result_transform.py` | 622 | **纯函数**筛选/排序/列选择（页/导出/API/预设共用） |
| `filter_help.py` | 286 | 筛选语法帮助文案单一来源 |
| `export.py` | 555 | CSV/JSON/ZIP 导出 |
| `api_handler.py` | 1083 | `/api/*`、Key、CORS、静态 `.json`、预设/模板 |
| `query_executor.py` | 795 | MySQL 事务多语句、有界连接池、`sql_contains_write` / `sql_has_persistent_write` |
| `render.py` | 6571 | **全站 UI 单一来源**（CSS/JS/`build_*`/`_icon` 图标辅助） |
| `redis_cache.py` | 432 | L2 Redis 快照、分布式锁 |
| `static_cache.py` | 272 | API `.json` 静态文件缓存 |
| `scheduler.py` | 734 | 进程内定时任务线程 |
| `auth.py` | 318 | PBKDF2 密码、Session、登录限流 |
| `audit_db.py` / `audit_page.py` | 342/149 | 审计库与审计页 |
| `branding.py` | 317 | 站点标识 / favicon（实例本地 SQLite） |
| `app_config.py` | 589 | `app_config.json` + DEBUG 深合并 |
| `preset_cases.py` / `json_template.py` | 426/224 | 预设导入、API JSON 模板 |
| `markdown_render.py` | 304 | 备注等 Markdown → HTML（含 mermaid） |
| `file_permissions.py` | 225 | 产出文件属主/权限 |

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
| * | `^/config($|/)` | 是 | 是 | `_handle_config` → `config.handle_request`（含 `/config/scheduler/new`、`/config/scheduler/{id}/edit` 表单页、`/config/pools`、`/config/users` 列表） |
| * | `^/report($|/)` | 是 | 是 | `_handle_report` → `report.handle_request` |
| * | `^/export($|/)` | 是 | 是 | `_handle_export` → `export.handle_export` |
| * | `^/api/` | **否** | 是 | `_handle_api` → `api_handler.handle_api_request` |
| * | `^/audit($|/)` | 是 | **否** | `_handle_audit` → `audit_page` |

补充：

- 静态：`/static/vendor/<name@ver>/<file>` 白名单直出（无鉴权）；扩展名 MIME 白名单。
- 新 URL **必须**进 `ROUTES`，注意与更宽正则（如 `/config($|/)`）的先后。

## 3. 页面地图（用户可见 · ui-redesign 重构后）

| 路径 | 内容 |
|------|------|
| `/login` | 登录（SqlReport 品牌、令牌化）；失败限流 5 次/5 分钟；过期提示 + `next` 白名单 |
| `/` | 302 → `/report` |
| `/report`（无 id） | **报表中心**：搜索 + 最近查看 + 左分类树 + 右报表卡片；localStorage 最近查看 |
| `/report?id=` | 报表详情：页头+横幅+备注摘要+**五页签（数据/规则/接口/调试/备注）**；数据页 `tr.qf-row` 独立快筛行、结果集 segment 入工具行、分页 `always` 恒显；规则 grid-2 双卡、接口页签复用列表函数、调试 grid-3 磁贴、备注普通卡片；列设置/排序抽屉、统一导出对话框、多结果集、缓存状态行、护栏横幅 |
| `/report/preview` | POST 预览未保存 SQL |
| `/export?id=N` | CSV/JSON/ZIP 导出（由详情页导出对话框发起） |
| `/config` | 概览仪表盘：统计磁贴、快捷入口、`grid-2`（左系统状态｜右导入演示数据 DEBUG 卡）、站点标识独立行（移出卡，去卡中卡）、首部署引导 |
| `/config/pools*` | 连接池**独立列表页** + 表单（表 6 列含「关联报表」＝渲染层按 pool_id 分组，不改 DB；测试连接/复制/移动/破坏半径披露） |
| `/config/users*` | 用户**独立列表页** + 表单（表 3 列：用户名｜角色说明｜操作——users 表无 role 字段，按平权管理员实义渲染，不虚构角色；会话清理/禁删自身） |
| `/config/reports*` | 报表配置：页头搜索 + **左分类树右报表表** + 勾选浮出批量条 + **R3 列表/卡片双视图全局开关（`#rpt-view-seg`，localStorage `sqlreport_reports_view` 记忆，两视图共享勾选）**；`#sec-categories` 兼容 |
| `/config/reports/add\|{id}/edit\|copy` | page-head+crumb 分区表单（基础/SQL/缓存与护栏/调度与保活，主 form 内 `.grid-2` 双栏）+ sticky 保存底栏（formbar 在 form 底）；表单下接口列表（api-row），端点/Key/预览联动 |
| `/config/api-endpoints` | API 列表（page-head：h1+统计+「+ 新建接口」→首张报表 `api_endpoints/new`，无报表回 `/config/reports/add`；`div.api-row` 主行+`api-more` 展开区真卡片，`.path-chip` 路径徽标）；端点表单分区（基本信息/调用地址/请求与输出/模板）+ Key 区（主 form 外） |
| `/config/scheduler` | 定时任务**列表主导**：7 列单表（任务名/关联报表/计划/下次执行/上次结果/状态/操作），**无「最近执行记录」第二表**（执行历史到审计日志查询），表下 help；全局停用横幅 |
| `/config/scheduler/new`、`/config/scheduler/{id}/edit` | 任务独立表单页（`?edit=N` 兼容渲染；新建支持 `?report_id=N` 预勾绑定，仅新建生效）；排除规则 `rule-row`/`rule-group` 可视化树 + 源码 JSON 模式 |
| `/config/categories` | 重定向 `/config/reports#sec-categories` |
| `/config/site-branding` | 站点标识 POST |
| `/audit` | 审计日志：page-head（actions=导出 CSV + 清理过期）+ 统一筛选条与表格**裸排无 card** |
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
| 用户可见术语（缓存/品牌等） | `docs/compose/spec/ui-redesign-visual-spec.md` §5 术语表（UI v2 未重定术语，该节继续有效） | render 缓存徽标/横幅、标题 |
| 全量输出护栏 | `allow_all_output` + `max_rows` | report / export / api |
| 页面骨架/CSS/JS | `render.render_page_header/footer`（侧栏页壳 `_NAV_GROUPS`、**侧栏三态收缩 `.sb-handle` 全高手柄 + `sqlreport_sidebar_collapsed` 记忆 + 请求级用户名上下文 `set_request_user`**）、`_BASE/_COMMON_*`（设计令牌）、hash 含 CSS+JS | 全站 |
| 表单 flash/302 模式 | 各 `handle_*` 返回 `(code, url, headers)` | config/report |

## 5. 审计四类 type（速查）

| type | 谁写 | 说明 |
|------|------|------|
| `operation` | auth / config CRUD / 部分调度 | 配置与登录类 |
| `web_access` | `server._log_web_access` | 已登录页面访问 |
| `api` | `server._log_api_call` | API 调用（≠ api_handler 内 logging） |
| `scheduler` | `record_operation(log_type=…)` | 定时任务链 |

## 6. 路由处理链速查

```
server._handle
  → 路径归一 + /static/vendor 白名单
  → ROUTES 首次匹配
  → needs_auth → session / 302 login
  → needs_db → get_config_db（audit 除外）
  → handler:
       config.handle_request / report.handle_request
       export.handle_export / api_handler.handle_api_request
       audit_page.handle_audit_request
  → _send_html / _send_redirect（刷新 Session Cookie）
  → _log_web_access / _log_api_call（审计）
```

## 7. 索引与检索

```bash
codegraph status                              # 索引健康 + pendingChanges
codegraph explore "<中文意图 + 代码词>"           # 首选：源码 + 调用链 + 波及面（纯中文查不到）
codegraph node <符号>                         # 单符号源码 + callers/callees
codegraph node --file <路径> --symbols-only    # 文件结构概览
codegraph query <symbol> -l 10                # 只查位置
codegraph callers|callees|impact <symbol>      # 依赖面
codegraph affected <改过的文件>                # 受影响测试
codegraph sync                                # 每次改完代码必跑
```
`.codegraph/` 已在 `.gitignore`（当前 137 文件 / 6894 节点 / 17453 边，v1.4.0）。

> **硬性 #18 / #19**：读/分析代码**强制先走 codegraph**，查不到才降级 grep/read；
> 改完 `.py`/`.js`/`.mjs` **必须 `codegraph sync`**。完整命令表、降级白名单、实测坑见
> `09-agent-workflow.md`「代码检索纪律」。

**本 INDEX 的定位**：只管「模块 / 路由 / 页面 / 共享语义」的现状事实。
**不是任务查证入口**——接到新任务先看 `docs/compose/spec/` 的最新生效 spec；
「该读哪一卷 / 改完必更新哪一卷」看仓库根 `AGENTS.md` §0 入口引导路由表。

**跨会话记忆**：仓库根 `MEMORY.md`（Rules + Discovered），每轮开工前必读；它不是分卷、
也不在 `docs/compose/knowledge/` 内，登记于此以便检索（2026-10-05 闭环
`../reports/ui-r3-retrospective.md` §六 的建议）。

## 8. 分卷来源

| 分卷 | 来源 |
|------|------|
| 01–07 | 初稿 AGENTS.md + README-CN + 源码结构；4 个 explore 代理（路由鉴权导出API / 配置缓存 / 报表变换 / UI）已并入 |
| 01 | 另有 2026-09-29 从 AGENTS.md 迁入：完整模块地图、应用配置与 DEBUG 隔离、MySQL 连接池 |
| 02 | 另有 2026-09-29 从 AGENTS.md 迁入：鉴权边界 |
| 03 | 另有 2026-09-29 从 AGENTS.md 迁入：统一筛选/排序/输出语义；并记入 transform 性能要点与派生态缓存 |
| 04 | 另有 2026-09-29 从 AGENTS.md 迁入：表结构变更三处同步 |
| 06 | 另有 2026-09-29 从 AGENTS.md 迁入：统一 UI 体系、UI 任务四阶段流程与自检清单 |
| 08 | 另有 2026-09-29 从 AGENTS.md 迁入：两败必停全文、L2 分段命令表、测试策略与收尾检查单、`-t .` 陷阱、性能工具链 |
| 09 | 2026-09-29 新建 `09-agent-workflow.md`：多代理协作纪律（#13–#15）与执行效率取证纪律（P1–P7）从 AGENTS.md 迁入 |

**AGENTS.md 瘦身约定**（2026-09-29）：AGENTS.md 只保留「每次任务都要读」的最小集
（硬性约束条目 + 入口引导路由表 + 环境命令 + 收尾检查单，当前约 156 行）。凡
「只在特定类型任务才需要」的内容一律迁入本库分卷，并在 AGENTS.md §0 路由表登记
「什么时候读、改完必更新」。新增分卷须同步三处：本 INDEX、`README.md` 索引表、
AGENTS.md §2 分卷表。
