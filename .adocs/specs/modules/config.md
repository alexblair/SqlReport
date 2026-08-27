---
module: config.py
contract_id: MOD-CONFIG
version: 1.0
depends_on: [api_handler, app_config, audit_db, auth, branding, config_db, db, json_template, markdown_render, preset_cases, query_executor, redis_cache, render, report, scheduler, static_cache]
last_reviewed_commit: 9652dab
last_reviewed_at: 2026-08-28
---

# config.py 模块分卷

> 本分卷由 T-004 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`config.py`（2821 行，84 个 def）——**配置页面处理模块**。是 `/config/*` 路由的业务编排核心：渲染配置总览/表单页（连接池、用户、分类、报表、API 端点、定时任务、站点标识、API Key），处理各类表单提交（新增/编辑/复制/删除/测试连接/批量操作/预览），并落库（经 config_db）。被 `server.py` 的 `_handle_config` 直接委托。

## 2. 公开 API 契约（按功能域分组，逐函数）

### 2.1 请求入口

- `parse_config_path(path)` -> dict：解析配置页 URL 路径为动作参数字典。
- `handle_request(conn, method, path, query, form_body=None, session_user=None) -> (code, body, headers)`：配置页面请求入口。先 `handle_scheduler_request` 前置分发（/config/scheduler*），再按 action 分发到各 handle_* 处理器，最后 `_redirect_or_render` 统一返回。

### 2.2 渲染辅助

- `_escape(s)`：HTML 转义；`_link_btn(...)`：生成链接按钮。
- `_render_pool_form(...)` / `_render_user_form(...)` / `_render_report_form(...)`：渲染表单。
- `_render_pool_section(conn)` / `_render_user_section(conn)` / `_render_category_section(conn)`：渲染配置段。
- `_render_branding_section()`：站点标识配置区块（三模式表单 + FileReader）。
- `render_overview(conn, ...)`：配置总览页（含三个配置段）。
- `render_reports_page(conn, flash)`：报表管理独立页（分类树 + 报表列表 + 批量操作；分类管理已并入本页）。
- `render_pool_form_page(...)` / `render_user_form_page(...)` / `render_category_form_page(...)` / `render_report_form_page(...)` / `render_api_endpoint_form_page(...)`：独立表单页。
- `render_scheduler_page(conn, ...)`：定时任务管理页（/config/scheduler）。
- `_get_depth(...)`：分类层级深度（缩进显示）。
- `_report_form_pool_options(...)` / `_report_form_cat_options(...)`：下拉选项 HTML。
- `_report_form_js_highlight()` / `_report_form_js_formatter()` / `_report_form_js_editor_api()`：SQL 编辑器 JS（高亮/格式化/UI 交互）。
- `_report_form_html(...)`：报表表单完整 HTML（含 SQL 编辑器 + 查看/预览按钮）。

### 2.3 表单解析与临时对象（保存失败回显）

- `_parse_form_data(body)`：解析 URL 编码表单。
- `_parse_report_form(body)` / `_parse_endpoint_form(body)`：报表/端点表单公共字段解析。
- `_tolerant_int(val, default)`：容错 int（非法原样返回，用于回显）。
- `_echo_int(val, default)`：严格 int（非法/空返回 default，用于回显数值字段）。
- `_pool_from_form(...)` / `_user_from_form(...)` / `_report_from_form(...)` / `_category_from_form(...)` / `_endpoint_from_form(...)`：从表单构造临时 dict（回显）。
- `_normalize_api_url_path(path)`：规范化 API URL 路径。
- `_parse_rule_json(raw)`：解析规则 JSON，拆出 columns/filters/sorts。
- `_save_or_render(...)`：统一「保存 / 保存并关闭」双按钮保存模式。
- `_estimate_result_count(sql)`：估算 SQL 中 SELECT/WITH 语句数量。
- `_validate_json_template(...)`：校验 JSON 输出模板；`_template_raw_for_format(...)`：CSV 模式不支持模板返回空串。
- `_endpoint_unique_error(e)`：UNIQUE 约束错误转重复路径提示。

### 2.4 连接池动作

- `handle_pool_test(conn, form, ...)`：测试连接（POST）；失败经 `_pool_test_error_hint` 人话提示。
- `handle_pool_add(...)` / `handle_pool_edit(...)` / `handle_pool_copy(...)`（同名+副本）/ `handle_pool_delete(...)`。

### 2.5 用户动作

- `handle_user_add(...)` / `handle_user_edit(...)` / `handle_user_delete(...)`。

### 2.6 报表与分类动作

- `handle_report_add(...)` / `handle_report_edit(...)` / `handle_report_copy(...)` / `handle_report_delete(...)`。
- `handle_report_move_category(...)` / `handle_category_add(...)` / `handle_category_edit(...)` / `handle_category_delete(...)`。
- `handle_batch_set_category(...)` / `handle_batch_pool(...)` / `handle_batch_cache(...)` / `handle_batch_delete(...)`：批量操作（级联删除端点 + 失效静态缓存）。
- `handle_memo_preview(...)` / `handle_description_preview(...)`：Markdown 预览端点。

### 2.7 API 端点与 Key 动作

- `handle_api_key_actions(conn, form, ...)`：API Key 管理（add 生成新 Key / delete / toggle）。
- `handle_api_endpoint_add(...)` / `handle_api_endpoint_edit(...)` / `handle_api_endpoint_delete(...)`。
- `handle_api_endpoint_preview(...)`：真实数据预览（表单未保存值构造临时端点，不落库执行查询）。
- `handle_api_endpoints_request(...)`：/config/api-endpoints 独立页入口。

### 2.8 定时任务动作

- `handle_scheduler_run(...)`：手动触发立即执行（绕过熔断与 enabled；全局停用降级）。
- `handle_scheduler_toggle(...)`：启停（重新启用时过期下次执行时间按当前计划重算）。
- `handle_scheduler_delete(...)`：删除任务定时配置（不影响报表）。
- `handle_scheduler_save(...)`：保存/更新定时任务（多报表组合）。
- `handle_scheduler_request(...)`：/config/scheduler* 请求入口（handle_request 前置分发）。

### 2.9 其他

- `handle_site_branding_save(form, session_user)`：保存站点标识（审计记录前后快照）。
- `handle_import_test_cases(conn, ...)`：预设数据夹具 upsert 导入（preset_cases）。
- `_redirect_or_render(code, result)`：处理器返回值转标准返回格式。

## 3. 数据流

```
server._handle_config → config.handle_request(conn, method, path, query, form_body, session_user)
  ├─ path=/config/scheduler* → handle_scheduler_request → 各 scheduler 动作
  ├─ path=/config/api-endpoints* → handle_api_endpoints_request → API 端点/Key 管理
  ├─ path=/config/site-branding → handle_site_branding_save
  ├─ 其余 → parse_config_path 分发 action → 各 handle_*（pool/user/report/category/batch/memo/description 预览）
  └─ _redirect_or_render(code, result) → (302 重定向 | 200 HTML | 错误)
  各 handle_* 内部：解析表单 → 校验 → config_db CRUD → 审计（audit_db）→ 渲染/重定向
```

## 4. 依赖关系

AST import 实测：`api_handler, app_config, audit_db, auth, branding, config_db, db, json_template, markdown_render, preset_cases, query_executor, redis_cache, render, report, scheduler, static_cache`（16 个内部依赖，为模块中依赖面最广者）。
- `config_db`/`db`：配置数据 CRUD。
- `render`：HTML 模板层；`branding`：站点标识；`markdown_render`：备注/描述预览。
- `preset_cases`：测试用例导入；`api_handler`：端点预览/Key 动作相关。
- `scheduler`：定时任务编排；`redis_cache`：缓存相关配置；`query_executor`：测试连接/预览执行。
- `auth`/`audit_db`：鉴权上下文与审计记录。

## 5. 边界与异常

- 破坏性操作 POST 化（PH-08）：批量删除等经 POST 触发。
- 删除级联：批量删报表 → 级联删端点 + 失效静态缓存；删分类 → 报表/子分类置 NULL。
- 表单回显：保存失败时用 `_pool_from_form`/`_user_from_form` 等保留用户原输入。
- API 端点唯一性：UNIQUE 约束 → 重复路径提示（`_endpoint_unique_error`）。
- 定时任务：手动触发绕过熔断与 enabled；全局停用时降级。
- 预览不落库：端点/报表预览用表单未保存值构造临时对象执行查询。

## 6. 保鲜核对提交点

- last_reviewed_commit: 9652dab（T-003 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 config.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
