---
module: app_config.py
contract_id: MOD-APP_CONFIG
version: 1.0
depends_on: []  # 配置加载层，无内部模块依赖（仅标准库）
last_reviewed_commit: 9652dab
last_reviewed_at: 2026-08-28
---

# app_config.py 模块分卷

> 本分卷由 T-004 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`app_config.py`（589 行，31 个 def）——**应用配置文件管理**。是项目配置的单一来源层：负责加载 `app_config.json`（含 DEBUG 覆盖合并）、提供各配置段解析（server/log/redis/error_log/file_permissions/test_mysql/audit_db/config_db）、路径工具（API 前缀规范化）、序列化工具（含「智能去引号」模式）、安全 int 转换等。被绝大多数模块引用（依赖矩阵中无内部模块依赖，属叶模块）。

## 2. 公开 API 契约（逐函数）

### 2.1 配置加载

- `_deep_merge(base, override)`：深层合并两个配置 dict（dict 递归合并，list/标量整体覆盖）。
- `_load_debug_config()`：读取 DEBUG 配置文件（默认 `app_config.debug.json`，可用 `DEBUG_CONFIG_PATH` 覆盖）。
- `_apply_debug_config(config)`：存在 DEBUG 配置则深层合并覆盖并返回合并结果。
- `_load_config()`：从文件加载配置；文件不存在或格式错误返回默认配置（SQLite + config.db）。
- `is_debug_mode()` -> bool：DEBUG 配置覆盖是否激活。
- `get_config()` -> dict：获取应用配置（懒加载，首次调用从文件读取）。
- `reload_config()`：强制重新加载配置文件（测试用）。

### 2.2 配置段解析

- `get_server_config()` -> (host, port)：server 段。
- `get_server_base_url()` -> str：API URL 展示用服务端兜底 base_url（`http://127.0.0.1:{port}`）。
- `get_trust_xff()` -> bool：server 段 trust_xff 开关（是否信任 X-Forwarded-For 首 IP）。
- `get_log_config()` -> (enabled, filepath)：log 段。
- `get_error_log_config()`：error_log 段。
- `get_redis_config()`：redis 段。
- `get_file_permissions_config()`：file_permissions 段。
- `get_test_mysql_config()`：test_mysql 段（DEBUG 专用测试 MySQL）。
- `get_audit_db_config()`：audit_db 段。
- `get_active_db_config()`：从 config_db 配置段取当前启用的数据库配置（多配置 + enable 切换）。

### 2.3 工具函数

- `safe_int(val, default)` -> int：安全转 int，转换失败返回默认值。
- `parse_form_urlencoded(body)` -> dict：解析 URL 编码表单（重复键取最后一个值）。
- `ensure_api_prefix(path)` -> str：确保路径以 `/api/` 开头（已有 /api 前缀则规范化）。
- `strip_api_prefix(path)` -> str：剥离 `/api` 前缀（`/api/x` → `x`；`/api` → `''`；无前缀原样返回）。
- `format_local_time(ts, fmt=None)` -> str：格式化为服务器本地时区时间（秒级精度）。

### 2.4 序列化（含「智能去引号」）

- `serialize_json(obj)` -> str：序列化 JSON（`ensure_ascii=False`，全项目序列化约定一致）。
- `serialize_smart_quotes(obj, enable, features)`：智能去引号模式序列化（结构保留 JSON 语法，字符串标量按勾选特征裸输出）。
- `_smart_parts(...)`：递归拼装输出片段。
- `_smart_scalar(...)`：标量 → 输出片段（字符串按特征判定，其余标准 JSON）。
- `_smart_decimal_text(d)`：Decimal → 不带引号数值文本（`format(f)` 全小数形式，无科学计数法）。
- `_smart_quote_or_strip(...)`：字符串值命中特征 → 合法化转换后裸输出，否则标准 JSON 字符串。
- `_smart_normalize(text)`：合法化转换链（去逗号 → 去前导 `+` → 去前导零）。
- `_smart_valid_number(text)`：RFC 8259 number 语法兜底校验（拒绝 Infinity/NaN/前导零）。
- `_smart_validated(text)`：转换结果经兜底校验；不满足 number 语法 → 回退标准 JSON 字符串。

## 3. 数据流

```
任意模块调用 get_config()/get_active_db_config()/get_redis_config() 等
  → get_config() 懒加载 → _load_config()（app_config.json）→ _apply_debug_config（DEBUG 覆盖深层合并）
  → 各 get_*_config 解析对应段返回
序列化：serialize_json / serialize_smart_quotes（智能去引号链：_smart_parts → _smart_scalar → 合法化/校验）
路径工具：ensure_api_prefix / strip_api_prefix（API 前缀规范化）
```

## 4. 依赖关系

AST import 实测：**无内部模块依赖**（仅 Python 标准库）。被调用方：绝大多数模块（server/report/config/api_handler/auth/audit_db/export/branding/render/static_cache/redis_cache/scheduler/db/file_permissions/json_template/query_executor/config_db 等）。

## 5. 边界与异常

- 配置缺失/格式错误：`_load_config` 返回默认配置（SQLite + config.db），不崩溃。
- DEBUG 覆盖：`_apply_debug_config` 深层合并（list/标量整体覆盖，dict 递归）。
- 智能去引号：`_smart_valid_number` 拒绝 Infinity/NaN/前导零，非法回退标准 JSON 字符串（防非法 JSON）。
- 路径规范化：`ensure_api_prefix`/`strip_api_prefix` 处理 `/api` 各种形态。
- 安全转换：`safe_int` 失败返回默认值。

## 6. 保鲜核对提交点

- last_reviewed_commit: 9652dab（T-003 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 app_config.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
