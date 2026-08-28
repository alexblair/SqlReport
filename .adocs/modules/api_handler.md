---
type: module
id: MOD-API_HANDLER
module: api_handler.py
tags:
- api
- json
- csv
version: '1.0'
last_reviewed_commit: 78895ce
last_reviewed_at: 2026-08-28
---

# api_handler.py 模块节点

> **依赖**：[[MOD-APP_CONFIG]]、[[MOD-AUTH]]、[[MOD-DB]]、[[MOD-EXPORT]]、[[MOD-JSON_TEMPLATE]]、[[MOD-QUERY_EXECUTOR]]、[[MOD-REDIS_CACHE]]、[[MOD-REPORT]]、[[MOD-RESULT_TRANSFORM]]、[[MOD-STATIC_CACHE]]

## 职责概述

`api_handler.py`（991 行，41 个 def/类）——**API 数据接口请求处理模块**。是 `/api/` 前缀 HTTP 请求的编排核心：负责 API Key 鉴权、API 端点路由（含 `.json` 静态缓存变体）、查询参数解析（预设规则 + POST/GET 覆盖）、结果格式化（JSON 模板/CSV/BOM）、CORS 响应头、API 审计日志。被 `server.py` 的 `_handle_api` 直接委托（无需会话，走 API Key 鉴权）。

## 公开 API 契约

### 2.1 数据结构

**`ApiQueryResult`**（`__init__(data_rows, display_cols, total, page, page_size, total_pages, output_format, add_bom)`）——API 查询结果具名结构（单结果集成功路径），附加 `full`/`truncated`/`smart_quote_flags` 字段。

### 2.2 顶层函数

- `generate_api_key()` -> str：生成随机 API Key（`sk-` 前缀 + 43 字符随机字符串）。

**`handle_api_request(conn, path, method, headers, body, query_params, client_ip="") -> (status, resp_body, resp_headers)`**
- API 请求入口函数。流程：规范化路径 → 校验 `/api` 前缀（404）→ 端点查找（含 `.json` 静态目标解析）→ OPTIONS 预检（204+CORS）→ API Key 鉴权（401）→ 非法 JSON 体拒绝（400）→ 静态缓存分支或普通链路 → 审计日志。
- 静态缓存：仅 GET 且路径以 `.json` 结尾时解析；原路径未命中端点时剥离后缀再查；端点 `output_format=json` 且端点/全局开关开启才进入静态分支，否则回退普通链路；鉴权在静态分支之前统一执行。

### 2.3 内部函数（契约要点）

- `_normalise_path(path)` -> str：规范化路径确保以 `/` 开头。
- `_endpoint_template(endpoint)` -> str：返回端点 JSON 输出模板（未配置空串）。
- `_lookup_endpoint(conn, norm_path)` -> dict | None：`db.get_api_endpoint_by_path` 查端点。
- `_static_base_path(norm_path)` -> str | None：`.json` 结尾（不敏感）时剥离后缀，否则 None。
- `_rows_to_dicts(rows, display_cols, col_indices)` -> list：行元组按列索引映射为 `[{列名: 值}]`；值保持原始类型（含 Decimal），智能去引号在序列化阶段处理。
- `_run_normal_api_request(conn, endpoint, method, body, query_params, headers)` -> tuple：普通 API 链路（`_execute_api_query` → `_format_output` → CORS），静态分支回退共用。
- `_handle_static_request(conn, endpoint, base_path, method, body, query_params, headers)` -> tuple：静态缓存请求处理。命中直接返回文件（`X-Static-Cache: hit`）；miss 全量计算 + 原子落盘；路径穿越（`..`）拒绝回退普通链路；写护栏（allow_write=0 且含写）回退普通链路（execute_report 统一 403），防历史静态文件绕过护栏。
- `_compute_static_config_version(endpoint, report)` -> str：静态缓存配置版本 = MD5(sql + pool_id + 端点变换配置 + 截断策略)。
- `rebuild_static_endpoint_file(conn, endpoint, record_invalidation=True, headers=None)`：对单个端点全量计算并原子落盘静态缓存文件（供后台重建）。
- `_execute_static_miss(conn, endpoint, url_key, file_path, ttl_hours, config_version, headers)` -> tuple：miss 链路（失效记录 → 全量计算 → 200 成功原子落盘，非 200 不落盘）。
- `_build_static_meta(ttl_hours, url_key, config_version, last_invalidated)` -> dict：静态文件 meta 节点。
- `_format_local_time(ts)` -> str：服务器本地时区时间（秒级精度）。
- `_get_result_name(report, result_index, result_obj)` -> str：结果集显示名（优先 result_names，否则自动命名）。
- `_execute_api_query(conn, endpoint, method, body, query_params, headers, force_full=False)` -> ApiQueryResult | tuple：加载报表/连接池 + 解析参数 + `execute_report` 执行 SQL。
- `_format_output(data_rows, display_cols, total, page, ps, total_pages, output_format, add_bom, full, ...)`：按 output_format 构建最终响应（JSON 支持自定义输出模板）。
- `_build_single_context(...)` / `_build_all_context(...)`：构建单结果集 / 全部输出模式的模板上下文（SINGLE_KEYS / ALL_KEYS，mode 恒为 "all"）。
- `_apply_json_template(template, context, smart_quote_flags=0)`：渲染 JSON 输出模板；失败记警告返回 None（调用方回退默认结构）。
- `_serialize_api_payload(obj, smart_quote_flags=0)`：序列化 API JSON 响应体（智能去引号）。
- `_parse_post_body(body, headers)`：解析 POST 请求体（JSON 与 form-urlencoded）。
- `_is_invalid_json_body(body, headers)`：`Content-Type=application/json` 且 body 非空但 JSON 解析失败 → 非法。
- `_validate_api_key(conn, endpoint, headers, query_params)` -> str | None：校验 API Key（`api_key` 参数或 Bearer token）。
- `_endpoint_valid_keys(conn, endpoint)` -> (keys, has_record)：有效 key 列表 + 表内是否有记录。
- `_build_cors_headers(endpoint, headers)` -> dict：按端点配置构建 CORS 头。
- `_parse_json_field(raw)` -> list：尝试解析 JSON 字符串为列表，失败空列表。
- `_parse_preset_rules(endpoint)`：从端点配置解析预设规则（filters/sorts/columns）。
- `_apply_post_overrides(post_data, preset_filters, preset_sorts, page, page_size, row_limit, columns, output_format, add_bom)`：应用 POST 覆盖参数。
- `_apply_get_overrides(query_params, page, page_size, row_limit, columns, output_format, add_bom, fetch_all, full)`：应用 GET URL 覆盖参数。
- `_safe_int(val, default)` -> int：安全转 int。
- `_filter_val_str(val)` -> str：筛选值归一化（None → 空串）。
- `_resolve_flag(query_params, method, body, headers=None, name="fetch_all")` -> bool：解析布尔请求参数。
- `_resolve_fetch_all(endpoint, method, body, query_params, headers=None)` -> bool：解析 fetch_all 全量获取（`_FETCH_ALL_PAGE_SIZE = 10**9`）。
- `_resolve_nested_filter(method, body, query_params, headers) -> dict | None`：解析并校验嵌套筛选参数。GET 从 `query_params["nested_filter"]`（URL 编码 JSON）读取、POST 从请求体 `nested_filter` 字段读取；解析后调用 `validate_nested_filter()` 校验，非法抛 ValueError（荷载为结构化错误 JSON，含 path/message/suggestion）。
- `_resolve_params(endpoint, method, body, query_params, headers=None) -> (filters, sorts, page, page_size, row_limit, output_format, columns, add_bom, fetch_all, nested_filter)`：预设规则 + POST/GET 覆盖合并；新增嵌套筛选解析（`nested_filter` 为解析并校验通过的 dict，无则 None）。校验失败（非法列/操作符/格式）抛 ValueError，由 `_execute_api_query` 转 400（FR-004/FR-005/FR-007/FR-012/FR-015）。
- `_format_json_response(data_rows, total, page, page_size, total_pages, full)` -> (status, body)：构建 JSON 响应。
- `_format_csv_response(data_rows, columns, add_bom=False)`：构建 CSV 响应。
- `_error_response(message, code, headers)`：构建错误响应（按 Accept 头决定 JSON 或纯文本）。
- `_log_api_call(path, client_ip, status, duration)`：记录 API 调用日志（审计）。

## 数据流

```
server._handle_api → api_handler.handle_api_request(conn, path, method, headers, body, query_params, client_ip)
  ├─ _normalise_path → 校验 /api 前缀 → 404 或继续
  ├─ _lookup_endpoint(norm_path)
  │    └─ GET 且未命中且 .json 结尾 → _static_base_path 剥离后缀再查（静态目标）
  ├─ [OPTIONS] → _build_cors_headers → 204
  ├─ _validate_api_key → 401（鉴权失败）
  ├─ [POST 非法 JSON] → 400 INVALID_JSON
  ├─ [静态分支启用] → _handle_static_request（命中直出 / miss 全量计算原子落盘）
  └─ 普通链路 → _run_normal_api_request
       ├─ _execute_api_query: 加载报表/连接池 + _resolve_params（含嵌套筛选校验，非法→400）+ execute_report
       ├─ _format_output: JSON(模板)/CSV/BOM, 单/全量上下文
       ├─ _build_cors_headers 合并
       └─ (status, body, headers)
  └─ _log_api_call 审计（全部路径）
```

## 依赖关系

AST import 实测：`app_config, auth, db, export, json_template, query_executor, redis_cache, report, result_transform, static_cache`。
- `db`：`get_api_endpoint_by_path`/`get_report`/`get_pool`/`get_api_key` 等。
- `report`：`execute_report`（实际 SQL 执行与缓存）。
- `query_executor`：`sql_contains_write`（写护栏检测）。
- `static_cache`：静态缓存文件读写（`resolve_file_path`/`try_read`/`JSON_SUFFIX`/`strip_json_suffix`/配置）。
- `json_template`：JSON 输出模板渲染。
- `result_transform`：筛选/排序/列选择。
- `auth`：`extract_bearer_token` 等。
- `app_config`：`TRUTHY_VALUES`/`API_PREFIX`/`safe_int` 等。

## 边界与异常

- 错误码：404（接口不存在/已禁用）、401（API Key 无效）、400（非法 JSON）、403（写拒绝，由 execute_report 统一抛出）、204（OPTIONS 预检）。
- 错误响应体按 `Accept` 头决定 JSON 或纯文本（`_error_response`）。
- 静态缓存：路径穿越（`..`）拒绝回退普通链路；非 200 不落盘；写护栏防止历史静态文件绕过（与普通 API 行为一致）。
- fetch_all 全量：`_FETCH_ALL_PAGE_SIZE = 10**9`，`_FETCH_ALL_VALUES = app_config.TRUTHY_VALUES`（布尔真值集）。
- 智能去引号：值保持原始类型（含 Decimal），序列化阶段统一处理。
- JSON 输出模板失败回退默认结构（`_apply_json_template` 返回 None）。

## 保鲜核对提交点

- last_reviewed_commit: 78895ce（T-002 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 api_handler.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
