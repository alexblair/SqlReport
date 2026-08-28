---
type: module
id: MOD-REPORT
module: report.py
tags:
- 报表
- 缓存
- 查询
version: '1.0'
last_reviewed_commit: 15c88ccd1b263c66a5491991d0aad7569425e7b2
last_reviewed_at: 2026-08-29
---

# report.py 模块节点

> **依赖**：[[MOD-APP_CONFIG]]、[[MOD-CONFIG_DB]]、[[MOD-DB]]、[[MOD-MARKDOWN_RENDER]]、[[MOD-QUERY_EXECUTOR]]、[[MOD-REDIS_CACHE]]、[[MOD-RENDER]]、[[MOD-RESULT_TRANSFORM]]、[[MOD-STATIC_CACHE]]

## 职责概述

`report.py`（1903 行，40 个 def/类）——**报表页面处理模块**。是 Web 报表功能的核心编排层：负责报表查询的执行（含多级缓存）、结果集筛选/排序/分页、报表页 HTML 渲染、报表选择页、多结果集切换、预览模式与缓存重建。被 `server.py` 的 `_handle_report` 直接委托，同时被 `api_handler.py`（API 查询）、`scheduler.py`（定时任务）复用 `execute_report`。

## 公开 API 契约

### 2.1 缓存类

**`CachedResult`**（`__init__(results: list[dict], sql_query: str, source: str = None, source_timestamp: float = None)`）
- 单次报表查询的缓存结果，保存原始 SQL 返回的全量数据（支持多结果集）。
- 字段：`results`（`[{"columns": [...], "rows": [...]}, ...]`）、`sql_query`、`source`（`"redis"`/`"process"`/`None`）、`source_timestamp`、`timestamp`、`truncated`。

**`QueryCache`**（`__init__(ttl: int = 300)`）——进程内报表查询结果缓存（LRU 语义）。
- `get(report_id: int, sql_query: str = None) -> CachedResult | None`：取缓存条目，TTL 内有效。
- `set(report_id: int, results, sql_query, source=None, source_timestamp=None, truncated=None)`：写缓存。
- `invalidate(report_id: int)`：失效单报表缓存。
- `clear()`：清空全部缓存。
- 模块级全局实例 `_query_cache`；`execute_report` 可注入独立实例（测试隔离）。

**`ReportResult`**（`__init__(results=None, active_index=0, page=1, page_size=20, **kwargs)`）
- 封装报表查询结果（支持多结果集），兼容新旧两式调用（自动识别 `results[0]` 为 str 时按旧式列+行解析）。
- 属性：`columns`/`rows`/`total`/`total_pages`——均取当前激活结果集（`active_index`）。
- 含 `cache_info`（`{source, timestamp, fresh}`）与 `truncated` 标记。

### 2.2 参数解析函数

- `parse_filters(qs)` -> list：从 `parse_qs` 结果解析多字段筛选（`f_<col>` 列名 + `op_<col>` 操作符，`_parse_filters` 为其内部实现）。
- `parse_nested_filter(qs) -> dict | None`：从 `parse_qs` 结果解析**嵌套筛选**（FR-005/FR-007/FR-013）。读取 `nested_filter`（URL 编码 JSON），`urllib.parse.unquote` 解码后 `json.loads`；空/缺失返回 `None`；解析或结构校验（`validate_nested_filter`）失败抛 `ValueError`，荷载为结构化错误 JSON（`{valid:false, errors:[...]}`）。报表页 `handle_request` 捕获后忽略并 flash 提示（不阻断渲染）；导出 `handle_export` 捕获后返回 400。
- `parse_sorts(qs)` -> list：解析多字段排序（`sort`/`dir` 重复键）。
- `_parse_cols(qs, all_columns)` -> list：解析自定义列顺序（`cols` 参数，仅保留存在列）。
- `_qs_val(qs, key, default=None)`：安全取 parse_qs 首个值。
- `parse_result_index(qs, key="result", default=0) -> int`：安全解析结果集索引，非法值回退 default；支持 `-1` 哨兵（全部结果集模式）。
- `parse_result_names(raw, count=None)` -> list：解析结果集名称文本（每行一个，剔除空行）。

### 2.3 错误处理与渲染辅助

- `humanize_db_error(e)` -> str：把数据库异常翻译为业务用户可读文案（`_DB_ERROR_HINTS`/`_DB_ERRNO_HINTS` 按 errno 匹配，如 1064 语法错误、1146 表不存在；超时标记 `_READ_TIMEOUT_MSG_MARKERS`）。
- `render_sql_error_section(friendly, raw)` -> str：渲染 SQL 执行错误区块：人话主文案 + `<details>` 折叠原始错误。
- `_render_page_header(title=None)`：报表页头部（公共 CSS + 特有 CSS + 高亮 + Markdown 排版）。
- `_js_string(s)` -> str：把 Python 字符串安全内嵌 `<script>` 的 JS 字符串字面量。

### 2.4 核心执行函数

**`execute_report(report_id, sql_query, pool_config, page=1, page_size=20, sorts=None, filters=None, refresh=False, active_index=0, report=None, conn=None, cache=None, force_rebuild=False, read_timeout=None, nested_filter=None) -> ReportResult`**
- 报表查询执行（缓存优先）。`report` 必须含 `prefer_cache`/`cache_ttl_hours`/`allow_write`/`allow_all_output`/`max_rows` 等配置字段。
- 缓存链路：进程内 `QueryCache` → Redis 快照 → 分布式重建锁 → MySQL 查询 → 写回各层；MySQL 失败兜底过期 Redis 快照（`source="redis_fallback"`）。
- `refresh=True`：先删后查（清进程缓存+Redis 快照+静态文件联动失效）；`force_rebuild=True`：先算后换（跳过全部缓存读，查询成功后原子覆盖，零空窗，供调度器 refresh-ahead）。
- 截断：`limit_rows`（`allow_all_output=0` 且 `max_rows>0`）时结果集截断至 max_rows，truncated 标记随缓存存储；读取兜底非就地截断不污染缓存。
- 每结果集独立执行 `filter_rows`（→ 嵌套筛选 `filter_rows_nested`，`nested_filter` 非空时）→ `sort_rows` → 分页。嵌套筛选与既有 filters 并存（FR-005），`filter_rows_nested` 为纯函数不污染缓存（FR-006）。
- `read_timeout`：仅 Web 交互路径传 30s，调度器/API 默认 None。

**`_cache_matches_limit_policy(truncated, limit_rows) -> bool`**：缓存条目的 truncated 标记与当前截断策略是否一致（策略不截断但缓存已截断 → 视为不可用走重建，防 PH-07 陈旧截断数据）。

**`_apply_max_rows(all_results, max_rows, inplace=True) -> (bool, list)`**：每结果集独立截断至 max_rows 行；inplace 就地截断（写缓存前）或返回新列表（读取兜底）。

### 2.5 页面渲染函数

- `render_report_selector(conn)` -> str：渲染报表选择页（按分类层级树状呈现）。
- `render_report_page(conn, report_id, page=1, page_size=None, pool_override=None, sorts=None, filters=None, refresh=False, cols=None, sql_override=None, report_override=None, active_index=0, result_names_override=None, flash="", nested_filter=None) -> str`：渲染报表数据展示页（多字段排序/筛选/自定义列/多结果集/预览）。`nested_filter` 非空时随筛选表单隐藏 input 与分页/排序/清除筛选链接保留（FR-005/FR-007），并透传 `execute_report` 在内存行上应用（FR-006）。
- `_build_report_html(conn, report, result, pool_config=None, sorts=None, filters=None)` -> str：构建完整报表 HTML（多结果集下拉切换）。
- `_build_report_switcher(conn, current_id=None)` -> str：构建报表切换下拉框（分类树）。
- `_handle_refresh_cache(conn, form_data) -> (302, url, {})`：处理「重建缓存」POST，回跳保留视图状态 + flash。
- `_filter_warning_flash(filters, existing_flash="") -> str`：检测非法数值筛选并生成提示 flash（`invalid_numeric_filters`）。

### 2.6 请求入口

**`handle_request(conn, method, path, query, form_body=None, pool_override=None) -> (int, str, dict)`**
- 报表页面请求入口。
- `POST /report/preview`：预览模式（不保存配置），支持有 id（报表配置取自库、allow_write 以表单为准）与无 id（构造临时报表配置）两种；缺 pool_id/SQL 回退选择页。
- `POST /report` + `action=refresh_cache`：缓存重建（PH-08 破坏性操作 POST 化）。
- 无 `id` → 渲染选择页；解析 page/page_size/sorts/filters/cols/active_index 后调 `render_report_page`，带 `_filter_warning_flash`。

## 数据流

```
server._handle_report
  → report.handle_request(conn, method, path, query, form_body)
    ├─ [POST /report/preview] → render_report_page(sql_override/report_override)
    ├─ [POST /report + refresh_cache] → _handle_refresh_cache → execute_report(..., True, ...) → 302 回跳
    └─ [GET /report?id=N] → render_report_page(conn, report_id, page, page_size, sorts, filters, cols, active_index)
         └─ execute_report(report_id, sql, pool_config, ...)
              ├─ 写护栏: report.allow_write=0 且 sql_contains_write(sql) → PermissionError
              ├─ 缓存读: QueryCache.get → (miss) Redis 快照 → (miss) Redis 重建锁 → MySQL
              ├─ MySQL: db.create_mysql_connection + db.execute_mysql_query(transactional=True)
              │         （失败 → 过期 Redis 快照兜底）
              ├─ 截断: _apply_max_rows（写缓存前就地 / 读取兜底非就地）
              ├─ 逐结果集: filter_rows(筛选) → sort_rows(排序) → 分页
              └─ ReportResult(results, active_index, page, page_size, cache_info, truncated)
         → _build_report_html(HTML 渲染, 多结果集下拉)
```

## 依赖关系

AST import 实测：`app_config, config_db, db, markdown_render, query_executor, redis_cache, render, result_transform, static_cache`。
- `db`：`get_report`/`get_pool`/`create_mysql_connection`/`execute_mysql_query`（数据访问与 MySQL 连接）。
- `query_executor`：`sql_contains_write`（写护栏检测）。
- `redis_cache`：`redis_available`/`get_redis_manager`/`compute_config_version`/`build_snapshot_key`/`build_lock_key`/`ReportSnapshot`（Redis 快照缓存）。
- `result_transform`：`filter_rows`/`sort_rows`/`calc_total_pages`/`invalid_numeric_filters`/`select_columns`（内存变换）。
- `render`：`render_page_header` 等（HTML 模板层）。
- `app_config`：`safe_int` 等配置工具。
- `static_cache`/`config_db`：缓存重建时静态文件联动失效（`config_db.invalidate_api_static_cache_by_report`）。

## 边界与异常

- **写护栏**（PH-05）：`allow_write=0` 且 SQL 含写 → `PermissionError(WRITE_DENIED_MESSAGE)`，拦截置于缓存读取之前，防止已缓存结果绕过。
- **全量输出护栏**（PH-06）：`allow_all_output=0` 且 `max_rows>0` → 结果集截断；陈旧全量数据统一兜底截断。
- **缓存降级**：Redis 不可用 → 降级 MySQL；MySQL 失败 → 过期 Redis 快照兜底（`redis_fallback`，fresh=False）。
- **分布式锁**：`wait_for_lock` 超时未获锁不误删他人锁；释放锁覆盖成功/兜底/抛异常/锁等待命中全部路径。
- **result 越界**：clamp 到 `0..len-1`，保留 `-1` 哨兵（全部结果集）语义。
- **read_timeout**：仅 Web 交互路径 30s，调度器/API 不限制（超长定时任务不受截断）。
- **预览模式**：SQL 来自表单时不写 Redis（`is_preview`），有 id 预览以表单 allow_write 为准。

## 保鲜核对提交点

- last_reviewed_commit: 78895ce（T-002 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 report.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
