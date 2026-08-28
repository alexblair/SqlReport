---
module: db
contract_id: MOD-DB
version: 1.0
depends_on: [config_db, query_executor, audit_db]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# db.py 模块分卷

> 本分卷由 T-006 逆向产出，内容以主仓还原后代码真实为准（FR-10）。

## 1. 职责概述

`db.py`（~100 行，0 个自有 def）——**数据库兼容适配层**。作为 `config_db.py`、`query_executor.py`、`audit_db.py` 的转发层，保持所有现有导入路径兼容。本模块不包含任何自有函数或类，纯粹是 `import` + `# noqa` 的重导出聚合。新代码应直接导入具体模块。

## 2. 公开 API 契约

### 2.1 从 config_db 重导出

- 连接/引擎：`_get_db_config`/`_get_engine`/`_connect_sqlite`/`get_config_db`/`init_db`
- 迁移：`_init_sqlite_migrations`/`_init_mysql_migrations`/`_SQLITE_SCHEMA`/`_MYSQL_SCHEMA`
- 连接池 CRUD：`add_pool`/`get_pool`/`get_all_pools`/`update_pool`/`delete_pool`/`move_pool`
- 用户 CRUD：`add_user`/`get_user`/`get_user_by_id`/`get_all_users`/`update_user`/`delete_user`
- 报表 CRUD：`add_report`/`get_report`/`get_all_reports`/`update_report`/`delete_report`/`batch_delete_reports`/`move_report`/`batch_update_report_pool`/`batch_update_report_cache`
- 分类 CRUD：`add_category`/`get_category`/`get_all_categories`/`update_category`/`delete_category`/`move_category`/`get_reports_by_category`/`get_reports`/`move_report_to_category`/`get_category_tree`/`get_parent_categories`/`batch_set_report_category`
- 会话：`add_session`/`get_session`/`remove_session`/`get_all_sessions`/`clear_sessions`/`delete_expired_sessions`/`delete_sessions_for_user`
- API 端点：`add_api_endpoint`/`get_api_endpoint`/`get_api_endpoint_by_path`/`get_api_endpoints_by_report`/`get_all_api_endpoints`/`count_api_endpoints_by_report`/`update_api_endpoint`/`delete_api_endpoint`/`delete_api_endpoints_by_report`
- 定时任务：`upsert_schedule`/`get_schedule`/`get_schedule_by_report`/`get_all_schedules`/`get_schedule_reports`/`get_due_schedules`/`set_schedule_enabled`/`delete_schedule`/`mark_schedule_result`
- API 密钥：`get_api_key`/`list_api_keys`/`add_api_key`/`delete_api_key`/`set_api_key_enabled`/`get_api_key_counts`
- 统计：`count_reports_by_pool`

### 2.2 从 query_executor 重导出

- `_MySQLRow`/`_MySQLCursor`/`_MySQLConnection`
- `_connect_mysql_config`/`create_mysql_connection`/`_split_sql_statements`/`execute_mysql_query`

### 2.3 从 audit_db 重导出

- `get_audit_db`/`init_audit_db`
- `insert_audit_log`/`query_audit_logs`/`count_audit_logs`/`export_audit_logs`/`delete_audit_logs`

## 3. 数据流

```
任何旧代码 import db → db.XXX → 实际转发到 config_db / query_executor / audit_db 对应函数
无自有逻辑，纯重导出。
```

## 4. 依赖关系

AST import 实测：`config_db, query_executor, audit_db`。
- 本模块是三模块的纯转发层，无自有逻辑。
- 被调用方：server/auth/export/report/config 等大量旧代码（通过 `import db` 使用）。

## 5. 边界与异常

- 纯转发层：无自有函数/类，不引入新行为。
- 兼容性保护：保持所有旧导入路径可用。
- 新代码建议：直接导入具体模块（config_db/query_executor/audit_db），不经过 db 转发。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 db.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
