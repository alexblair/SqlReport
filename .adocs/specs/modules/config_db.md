---
module: config_db.py
contract_id: MOD-CONFIG_DB
version: 1.0
depends_on: [app_config, audit_db, db, query_executor, static_cache]
last_reviewed_commit: 9652dab
last_reviewed_at: 2026-08-28
---

# config_db.py 模块分卷

> 本分卷由 T-004 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`config_db.py`（2498 行，86 个 def）——**配置数据库 CRUD 操作**（SQLite/MySQL 双引擎）。是项目配置数据的持久层单一来源：负责连接池、用户、报表、分类、API 端点、API Key、定时任务、session 的增删改查，以及双引擎（sqlite3/mysql）的连接创建、建表 DDL 与迁移。被 `db.py` 适配层转发，间接被 server/report/config/api_handler/scheduler 等使用。

## 2. 公开 API 契约（按域分组，逐函数）

### 2.1 引擎与连接

- `_get_db_config()`：从 app_config 获取当前启用的 config_db 配置（支持多配置列表 + enable 切换）。
- `_get_engine()` -> str：返回当前引擎名（`mysql`/`sqlite3`）；late import db 便于 mock 拦截。
- `_connect_sqlite()`：根据 app_config 或环境变量创建 SQLite 连接。
- `get_config_db()`：创建并返回 config_db 连接（按引擎分支）。
- `_get_schema_sql(engine)`：返回对应引擎的建表 DDL。
- `init_db(conn)`：初始化表结构并执行迁移。
- `_init_sqlite_migrations(conn)`：SQLite 专属迁移（PRAGMA table_info）。
- `_init_mysql_migrations(conn)`：MySQL 专属迁移（SHOW COLUMNS 替代 PRAGMA）。
- `_placeholders(n)` -> str：生成 n 个 `?` 占位符（IN (...) 子句）。
- `_write_audit_log(...)`：写审计日志到 audit.db。

### 2.2 连接池（pool）

- `add_pool(name, host, port, user, password, database, charset, ...)` -> id：新增连接池，自动分配 sort_order。
- `get_pool(conn, id)` -> dict | None：按 id 查询；`get_all_pools(conn)`：按 sort_order 排序返回全部。
- `update_pool(...)` -> bool：更新连接池（影响行数 >0）。
- `count_reports_by_pool(conn)`：按连接池聚合关联报表数。
- `delete_pool(conn, id, ...)`：删除连接池。
- `move_pool(conn, id, direction, ...)`：调整排序（`up`/`down`）；`_move_item(...)` 为公共实现。

### 2.3 用户（user）

- `add_user(conn, username, password_hash, is_admin, ...)` -> id。
- `get_user(conn, username)` / `get_user_by_id(conn, id)` -> dict | None。
- `get_all_users(conn)`：全部用户。
- `update_user(...)` / `delete_user(...)` -> bool（影响行数 >0）。

### 2.4 报表（report）

- `add_report(conn, name, pool_id, sql_query, default_page_size, category_id, memo, prefer_cache, cache_ttl_hours, allow_write, allow_all_output, max_rows, result_names, sort_order, ...)` -> id。
- `get_report(conn, id)` / `get_all_reports(conn)`（按 sort_order）。
- `update_report(...)` -> bool。
- `delete_report(conn, id, ...)` -> bool：级联删除该报表的定时任务行与 API 端点（应用层级联）。
- `move_report(...)`：同分类内交换排序。
- `batch_update_report_pool(conn, ids, pool_id)` -> int；`batch_update_report_cache(conn, ids, enabled, ttl_hours)` -> int。

### 2.5 分类（category）

- `add_category(conn, name, parent_id, ...)` / `get_category` / `get_all_categories`（按 sort_order）。
- `update_category(...)` / `delete_category(...)`：删除分类时关联报表 category_id 置 NULL、子分类 parent_id 置 NULL。
- `move_category(...)`：排序。
- `get_reports_by_category(conn)`：返回所有分类及其下的报表（仅直接归属）。
- `get_reports(conn, category_id)` / `move_report_to_category(conn, report_id, category_id)`。
- `get_category_tree(conn)` / `get_parent_categories(conn, category_id)`：分类树与祖先链。
- `batch_set_report_category(conn, ids, category_id)` -> int。

### 2.6 会话（session，SQLite 持久化）

- `add_session(conn, token, username)` / `get_session(conn, token)`（不存在或已过期返回 None）/ `remove_session(conn, token)` -> bool。
- `get_all_sessions(conn)`：全部未过期 session；`clear_sessions(conn)`。
- `delete_expired_sessions(conn)`：删除过期（>24h）session，返回删除行数。
- `delete_sessions_for_user(conn, username)` -> int。

### 2.7 API 端点（api_endpoint）

- `add_api_endpoint(conn, report_id, name, path, method, output_format, ...)` -> id（21 参）。
- `get_api_endpoint(conn, id)` / `get_api_endpoint_by_path(conn, path)`（仅已启用）。
- `get_api_endpoints_by_report(conn, report_id)` / `get_all_api_endpoints(conn)`（含关联报表名）。
- `count_api_endpoints_by_report(conn, report_ids)` -> {report_id: 端点数}。
- `update_api_endpoint(...)` -> bool：仅更新非 `_UNSET` 字段；配置变更后 `_invalidate_after_endpoint_update` 失效静态缓存（`_CACHE_AFFECTING_ENDPOINT_FIELDS` 判定）。
- `delete_api_endpoint(conn, id, ...)` -> bool。
- `_invalidate_api_static_cache(url_path)`：删除静态缓存文件（幂等）；`invalidate_api_static_cache_by_report(conn, report_id, ...)`：使某报表全部端点静态缓存失效（惰性重建）。
- `delete_api_endpoints_by_report(conn, report_id)` -> int；`batch_delete_reports(conn, ids)` -> int（批量删报表及其端点）。

### 2.8 API Key

- `get_api_key(conn, id)` / `list_api_keys(conn, endpoint_id)`（按创建顺序）/ `get_api_key_counts(conn)`。
- `add_api_key(conn, endpoint_id, key, name, enabled=1, ...)` -> id。
- `delete_api_key(...)` / `set_api_key_enabled(conn, id, enabled, ...)` -> bool。

### 2.9 定时任务（schedule）

- `_validate_schedule_fields(...)`：校验字段合法性，非法抛 ValueError。
- `_dump_exclusions(exclusions)`：排除规则树规整为 JSON 文本；空值 None。
- `_sync_schedule_reports(...)`：重写任务与报表绑定（按 order_index；保留绑定级 enabled）。
- `upsert_schedule(conn, id, name, enabled, schedule_type, time_expr, max_failures, ...)` -> task_id：创建或更新（任务独立实体，可绑定多报表）。
- `get_schedule_by_report(conn, report_id)` / `get_schedule(conn, id)` / `get_all_schedules(conn)`（按下次执行时间升序）。
- `get_schedule_reports(conn, schedule_id)`：绑定报表（按 order_index，含 report_name）。
- `get_due_schedules(conn, now)`：到期可执行（next_run_at ≤ now 且 fail_count < 5）。
- `mark_schedule_result(conn, id, success, ...)`：记录执行结果并推进下次执行时间。
- `set_schedule_enabled(...)` / `delete_schedule(conn, id, ...)`（级联清理绑定）-> bool。
- `_report_schedules_table_exists(conn)`：探测表存在（兼容 SQLite/MySQL/mock）。
- `delete_schedules_by_report(conn, report_id)`：删除某报表的定时任务绑定（幂等）。

## 3. 数据流

```
调用方（db.py 适配层转发）
  → get_config_db() → _get_engine() 判定 mysql/sqlite3 → 创建对应连接
  → init_db(conn) → 建表 DDL（_get_schema_sql）+ 迁移（SQLite PRAGMA / MySQL SHOW COLUMNS）
  → CRUD 各域：pool/user/report/category/api_endpoint/api_key/schedule/session
       └─ 写操作伴审计（_write_audit_log → audit.db）
       └─ 端点/报表配置变更 → _invalidate_api_static_cache（静态缓存失效，惰性重建）
```

## 4. 依赖关系

AST import 实测：`app_config, audit_db, db, query_executor, static_cache`。
- `app_config`：数据库配置读取（多配置 + enable 切换）。
- `audit_db`：审计日志写入。
- `db`：兼容适配层相互引用（db.py 从 config_db 转发导出）。
- `query_executor`：MySQL 连接/执行适配。
- `static_cache`：静态缓存失效联动。

## 5. 边界与异常

- 双引擎：SQLite（PRAGMA）与 MySQL（SHOW COLUMNS）迁移差异独立实现；`get_config_db` 按 `_get_engine()` 分支。
- 级联删除：删报表 → 定时任务行 + API 端点 + 静态缓存失效；删分类 → 报表 category_id 置 NULL。
- 幂等失效：静态缓存失效幂等（删除文件不报错）。
- 会话：过期（>24h）session 由 `delete_expired_sessions` 清理。
- 定时任务：`fail_count < 5` 才可执行；`get_due_schedules` 取到期任务。

## 6. 保鲜核对提交点

- last_reviewed_commit: 9652dab（T-003 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 config_db.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
