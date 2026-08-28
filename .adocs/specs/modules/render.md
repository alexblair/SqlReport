---
module: render
contract_id: MOD-RENDER
version: 2.0
depends_on: [app_config, branding, redis_cache, static_cache, filter_help, markdown_render]
last_reviewed_commit: 8b76e7e
last_reviewed_at: 2026-08-28
---

# render.py 模块分卷

> 本分卷由覆盖率补全阶段逆向产出，内容以主仓代码真实为准。

## 1. 职责概述

`render.py`（~2000 行，60+ def）——**HTML 渲染模板层**。基于 `string.Template` 的公共 HTML 渲染函数库：统一页面头/尾/导航栏/CSS/JS 资源、构建表格/分页/筛选/排序/控制栏/字段设置/报表切换/定时任务等 UI 组件、管理公共 CSS/JS 外链化（sha256 哈希版本锁）。被 report/config/audit_page/scheduler 等模块共享。

### 1.1 核心架构：公共资产外链化

页面头/尾模板优先从 `/static/vendor/self@{hash8}/` 加载外链 CSS/JS（immutable 缓存），写入失败时回退内联 `<style>`/`<script>`。`_COMMON_CSS` = `_BASE_CSS` + 导航栏/按钮/Flash 等公共样式；`_COMMON_JS` = 折叠区三态记忆 + 字段拖拽等交互组件。

## 2. 公开 API 契约（按功能域分组）

### 2.1 页面骨架

- `render_navbar(active="")` → str：导航栏 HTML（active 指定高亮页）。
- `render_page_header(title, active_nav="", extra_css="")` → str：`<head>` + 导航栏 + container 开头。外链优先，回退内联。
- `render_page_footer()` → str：页面尾部（container 闭合 + 脚本）。外链优先，回退内联。

### 2.2 表格与数据展示

- `format_cell(val)` → str：格式化单元格值（Decimal/float/None）。
- `build_empty_row_html(colspan, text, with_icon=False, icon="📭")` → str：空状态提示行。
- `build_table_header_html(...)` → str：表头（排序双箭头 + 筛选操作符下拉 + 筛选输入框）。
- `build_table_body_html(rows, display_indices, filters=None, clear_filters_href=None)` → str：表格数据行。
- `build_state_span(text, state="ok", bold=True)` → str：状态徽章 span。

### 2.3 分页与排序

- `build_pagination_html(...)` → str：分页 HTML（携带排序/筛选/自定义列参数）。
- `build_sort_params(sorts)` → str：sorts 编码为 URL 查询串。
- `build_sort_bar_html(...)` → str：排序栏（当前排序列及优先级）。
- `build_sort_settings_panel_html(sorts, all_columns)` → str：排序管理面板。

### 2.4 筛选

- `build_filter_params(filters, skip_col=None)` → str：filters 编码为 URL 查询串。
- `filter_hidden_inputs(filters)` → str：筛选参数隐藏 input 标签。
- `build_filter_form_html(form_id, form_hidden_str)` → str：隐藏筛选表单。
- `build_filter_action_html(...)` → tuple：筛选操作按钮和清除筛选提示。
- `build_clear_filters_href(...)` → str：清除筛选目标 URL。

### 2.5 控制栏与字段设置

- `build_controls_bar_html(...)` → str：控制栏（分页/导出/缓存/字段/排序按钮）。
- `build_field_settings_panel_html(all_columns, display_columns)` → str：字段设置面板（拖拽排序 + 显隐勾选）。
- `build_cols_param(display_columns, all_columns)` → str：cols URL 参数。

### 2.6 报表 UI 组件

- `build_result_selector_html(...)` → str：多结果集切换下拉框。
- `build_redis_banners_html(cache_info)` → str：Redis 降级/兜底提示横幅。
- `build_cache_badge_html(cache_info, prefer_cache=False, cache_ttl_hours=0)` → str：缓存状态标签。
- `build_debug_section_html(...)` → str：Debug 信息折叠区。
- `build_current_rules_section_html(...)` → str：当前规则输出折叠区。
- `build_memo_section_html(memo_raw, report_id=None)` → str：备注折叠区（Markdown 渲染，三态记忆）。
- `build_report_switcher_html(reports_data, all_cats, cat_tree, current_id=None)` → str：报表切换下拉框（分类层级树状）。
- `build_flash_html(flash, is_error=None)` → str：flash 提示条。

### 2.7 配置页组件

- `build_pool_form_html(pool=None, copy_mode=False, ...)` → str：连接池编辑/新增/复制表单。
- `build_user_form_html(user=None, is_edit=None)` → str：用户编辑/新增表单。
- `build_category_opts_html(nodes, depth, cur_cat_id)` → str：分类选项（树形缩进，递归）。
- `build_pool_section_html(pools, report_counts=None)` → str：连接池配置列表。
- `build_user_section_html(users, current_username=None)` → str：用户配置列表。
- `build_category_manage_section_html(...)` → str：分类管理区块。
- `build_category_section_html(...)` → str：报表分类配置段（含批量操作浮动条）。
- `build_delete_form_html(action_url, confirm_msg, ...)` → str：删除确认表单（POST + confirm）。
- `build_move_buttons_html(item_id, section, index, total)` → str：上下移动按钮。

### 2.8 API 端点 UI

- `build_api_endpoints_list_html(...)` → str：API 接口列表区块。
- `build_api_endpoint_form_html(...)` → str：API 端点编辑/新增表单。
- `build_api_endpoint_preview_help_html(report_id, endpoint_id)` → str：真实数据预览指引。
- `build_api_key_manage_html(keys, report_id, endpoint_id)` → str：API Key 管理区块。
- `build_api_urls_section_html(api_endpoints, base_url)` → str：API URL 折叠区。

### 2.9 定时任务 UI

- `build_scheduler_page_html(schedules, scheduler_enabled, recent_events=None)` → str：定时任务管理页主体。
- `build_scheduler_task_form_html(prefill, reports)` → str：新建/编辑定时任务表单。
- `build_schedule_flags_badge_html(sched_flag, keepalive_flag)` → str：功能徽标（⏰/♻）。

### 2.10 审计页

- `build_collapse_section_html(title, content, ...)` → str：折叠区骨架（三态记忆控件）。
- `render_audit_page(rows, total, page, page_size, filters, message="", db_size=0)` → str：完整审计日志页面。

### 2.11 公共资产（外链化）

- `self_assets_root()` → str：self 资产根目录（static/vendor 绝对路径）。
- `content_hash8(content)` → str：内容 sha256 前 8 位（版本锁目录名）。
- `ensure_common_assets(root=None)` → (css_url, js_url)：公共 CSS/JS 写入 `self@{hash8}/` 目录。
- `reset_common_assets_cache()`：重置进程级资产缓存（测试隔离）。

### 2.12 内部辅助函数

| 函数 | 说明 |
|------|------|
| `_get_branding_prefix()` | 站点标识标题前缀（已 HTML 转义） |
| `_build_navbar_html(active)` | 导航栏内部实现 |
| `_collect_all_sections(conn)` | 收集全部配置区块（用于导航栏节锚点） |
| `_render_common_footer()` | 公共页脚内部实现 |
| `_get_common_asset_urls()` | 获取公共 CSS/JS 外链 URL（写入失败返回空） |
| `_escape(s)` | HTML 转义 |

## 3. 数据流

```
report.handle_request → render.render_page_header/footer (页面骨架)
  → _get_common_asset_urls()（外链 CSS/JS，失败回退内联）
  → build_controls_bar_html (分页+导出+缓存+字段+排序)
  → build_table_header_html + build_table_body_html (表格)
  → build_pagination_html (分页)

config.handle_request → build_pool_section/user_section/category_section (配置段)
  → build_pool_form/user_form/category_opts (表单)
  → build_api_endpoints_list/api_endpoint_form (API 端点)
  → build_scheduler_page_html/task_form (定时任务)

资产: ensure_common_assets → content_hash8 → static/vendor/self@{hash8}/ → 浏览器 immutable 缓存
```

## 4. 依赖关系

AST import 实测：`app_config, branding, redis_cache, static_cache, filter_help, markdown_render`。

| 依赖方 | 使用的 API | 说明 |
|--------|-----------|------|
| `app_config` | `format_local_time`, `strip_api_prefix` | 时间格式化、URL 前缀剥离 |
| `branding` | `get_site_branding` | 标题前缀/favicon 模式 |
| `redis_cache` | `redis_available` | Redis 可用性检查 |
| `static_cache` | `get_static_cache_config`, `JSON_SUFFIX` | 静态缓存配置 |
| `filter_help` | `render_filter_help`, `FILTER_HINT_SUFFIX` | 筛选帮助提示 |
| `markdown_render` | `render_markdown`, `MERMAID_JS_URL` | Markdown 渲染 |

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| 零外部 HTML 依赖 | 模板为内联字符串常量（`string.Template`） |
| 公共资产外链化 | sha256 哈希版本锁，写入失败回退内联 |
| 三态记忆控件 | 折叠区 localStorage 持久化（自动/展开/折叠） |
| 页面特有 CSS/JS | 通过参数传入，不包含在公共模板中 |
| `ensure_common_assets` 写入失败 | 返回 (None, None)，`_get_common_asset_urls()` 回退内联 |

## 6. 保鲜核对提交点

- last_reviewed_commit: 8b76e7e
- last_reviewed_at: 2026-08-28
- 后续代码改动 render.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
