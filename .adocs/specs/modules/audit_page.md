---
module: audit_page
contract_id: MOD-AUDIT_PAGE
version: 1.0
depends_on: [audit_db, render, app_config, export]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# audit_page.py 模块分卷

> 本分卷由 T-005 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`audit_page.py`（149 行，6 个 def）——**审计日志页面处理**。从 server.py 抽离为独立模块：GET 浏览（自动轮转 + 分页查询 + 渲染）、POST 清理（重定向 + flash 消息）、CSV 导出（下载响应）。只返回 `(status, body, headers)` 元组，不直接写 socket。

## 2. 公开 API 契约

- `handle_audit_request(method, query, form_body=None)` → (int, str|bytes, dict)：审计日志页请求统一入口。分派逻辑：POST action=clean → 重定向 302；GET export=csv → CSV 下载 200；默认 → HTML 页面 200。

### 内部函数

- `_rotate_expired()`：按 `retention_days` 配置自动轮转过期日志；失败仅 warning。
- `_handle_clean(data)` → (302, redirect_url, {})：POST 清理（按筛选条件删除）。
- `_export_csv(filters)` → (200, csv_bytes, headers)：导出 CSV（utf-8-sig 编码、QUOTE_ALL、CRLF）。
- `_collect_filters(params)` → dict：从查询参数/表单提取非空筛选条件。
- `_qs_int(qs, key, default)` → int：安全提取整数参数。

### 常量

- `_FILTER_KEYS`：支持的筛选键元组 `("type", "date_from", "date_to", "session_user", "keyword")`。
- `_CSV_HEADER` / `_CSV_FIELDS`：CSV 导出表头（中文 11 列）与对应字典键名。

## 3. 数据流

```
server._handle_audit → handle_audit_request(method, query, form_body)
  ├─ _rotate_expired()（每次请求前自动清理过期日志）
  │    └─ audit_db.rotate_audit_logs()
  ├─ POST action=clean → _handle_clean(data)
  │    ├─ _collect_filters(data)
  │    ├─ audit_db.delete_audit_logs(conn, filters)
  │    └─ return 302, redirect_url, {}
  ├─ GET export=csv → _export_csv(filters)
  │    ├─ audit_db.export_audit_logs(conn, filters)
  │    ├─ export.rows_to_csv(header, rows, ...) → bytes
  │    └─ return 200, csv_bytes, {Content-Type, Content-Disposition}
  └─ GET 默认 → 页面浏览
       ├─ audit_db.count_audit_logs(conn, filters) → total
       ├─ audit_db.query_audit_logs(conn, filters, page, page_size) → rows
       ├─ os.path.getsize(audit_db.get_audit_db_path()) → db_size
       └─ render.render_audit_page(rows, total, page, page_size, filters, message, db_size) → HTML
```

## 4. 依赖关系

AST import 实测：`audit_db, render, app_config, export`。
- `audit_db`：连接、查询、统计、轮转、删除、导出（全量）。
- `render`：`render_audit_page`（HTML 模板层）。
- `app_config`：`get_audit_db_config`（retention_days）、`safe_int`。
- `export`：`rows_to_csv`（通用 CSV 序列化，支持 BOM/quoting/编码）。

## 5. 边界与异常

- 无副作用返回：所有分支返回 `(status, body, headers)` 元组，不直接操作 socket。
- 连接管理：所有 audit_db 连接 try/finally 确保 close。
- 容错策略：`_rotate_expired` 失败仅记日志不上抛；异常转 flash 错误消息。
- 筛选条件复用：`_collect_filters` 同时服务 GET 查询参数和 POST 表单数据。
- db_size 获取失败返回 0。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 audit_page.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
