---
module: audit_db
contract_id: MOD-AUDIT_DB
version: 1.0
depends_on: [app_config, result_transform]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# audit_db.py 模块分卷

> 本分卷由 T-005 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`audit_db.py`（342 行，15 个 def）——**审计日志数据库**。管理独立 SQLite `audit.db`，存储四种审计类型（`operation`/`scheduler`/`web_access`/`api`），提供插入、分页查询、筛选、统计、导出、删除及自动轮转。异常降级为 `logging.warning`，不向上抛出，不阻断业务。

## 2. 公开 API 契约

### 2.1 连接管理

- `get_audit_db_path()` → str：获取审计库文件路径（委托 `app_config.get_audit_db_config`）。
- `get_audit_db()` → sqlite3.Connection：获取审计库连接（兼容 db.py 转发层）。
- `init_audit_db(conn)` → None：幂等创建 `audit_logs` 表 + 3 个索引（DDL 初始化入口）。

### 2.2 写入

- `record_operation(session_user, action, entity_type, entity_id=None, entity_name=None, before_value=None, after_value=None, details=None, log_type="operation")`：业务操作审计统一入口（薄包装）；`session_user` 为空时跳过；异常降级为 warning。
- `insert_audit_log(conn, *, type, session_user=None, action=None, entity_type=None, entity_id=None, entity_name=None, before_value=None, after_value=None, http_method=None, http_path=None, http_status=None, ip_address=None, user_agent=None, duration_ms=None, request_body=None, timestamp=None)` → int：底层插入（返回自增 id）；`before_value`/`after_value` 自动 JSON 序列化。

### 2.3 查询与统计

- `query_audit_logs(conn, filters, page=1, page_size=20)` → list[dict]：分页查询（page 从 1，按 id 降序）。
- `count_audit_logs(conn, filters)` → int：统计符合条件的日志总数。
- `export_audit_logs(conn, filters)` → list[dict]：导出全部（不分页，CSV 用）。
- `get_recent_schedule_events(conn, schedule_id=None, limit=20)` → list[dict]：查询最近定时执行事件（`scheduled_run`/`scheduled_skip`/`scheduled_misfire`）。

### 2.4 删除与轮转

- `rotate_audit_logs(conn, retention_days)` → int：自动清理过期日志（返回删除行数）；`retention_days=0` 不清理。
- `delete_audit_logs(conn, filters)` → int：删除符合条件的日志（返回影响行数）。

### 2.5 内部工具

- `_get_audit_db_path()` → str：从完整配置获取审计库路径。
- `_connect_audit_db()` → sqlite3.Connection：连接审计库（自动建目录 + WAL 模式）。
- `_keyword_to_like_patterns(keyword)` → list：统一匹配表达式 → SQL LIKE 模式列表。
- `_build_where(filters)` → (str, list)：构建 WHERE 子句和参数列表。

## 3. 数据流

```
写入路径:
  auth/config_db/scheduler/server → record_operation() → get_audit_db() → insert_audit_log()
    → serialize_json(before/after) → INSERT INTO audit_logs → conn.close()
    → 异常 → logging.warning（降级，不向上抛出）

查询路径:
  audit_page → query_audit_logs/count_audit_logs/export_audit_logs
    → _build_where(filters) → 参数化 SQL → list[dict]

关键字搜索:
  keyword → result_transform.parse_filter_expr → _keyword_to_like_patterns → LIKE '%...%' 模式

日志轮转:
  server.main / audit_page._rotate_expired → rotate_audit_logs(retention_days)
    → DELETE WHERE timestamp < cutoff → 返回删除行数
```

## 4. 依赖关系

AST import 实测：`app_config, result_transform`。
- `app_config`：`serialize_json`（before/after 序列化）、`get_audit_db_config`/`get_config`（审计库配置）。
- `result_transform`：`parse_filter_expr`（关键字搜索表达式解析，全系统统一语法）。
- 被调用方：auth（认证事件审计）、config_db（配置变更审计）、scheduler（定时任务审计）、audit_page（页面查询/删除/轮转）、server（启动初始化 + 请求审计）。

## 5. 边界与异常

- 独立库：`audit.db` 与 `config.db` 分离，互不影响。
- 异常降级：`record_operation` 内部 try/except → `logging.warning`，不向上抛出。
- WAL 模式：审计库启用 WAL 并发读写。
- 表结构：16 列（通用 + operation 专用 + web_access/api 专用）+ 3 个索引（type/timestamp/session_user）。
- 过期轮转：`retention_days=0` 不清理。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 audit_db.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
