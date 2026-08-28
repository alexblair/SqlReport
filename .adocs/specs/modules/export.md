---
module: export
contract_id: MOD-EXPORT
version: 1.0
depends_on: [db, app_config, render, report, query_executor, result_transform]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# export.py 模块分卷

> 本分卷由 T-006 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`export.py`（~300 行，11 个 def）——**结果集导出**。根据报表配置执行完整查询（不分页），将结果序列化为 CSV 或 JSON，支持字符集选择（GBK/UTF-8）、JSON 智能去引号、ZIP 压缩、max_rows 截断。被 server._handle_export 委托。

## 2. 公开 API 契约

- `rows_to_csv(header, rows, *, bom=True, quoting=QUOTE_ALL, encoding="utf-8", lineterminator="\n")` → str|bytes：表头+行数据 → CSV（导出/API/审计页三处共用）。
- `export_report_to_csv(sql_query, pool_config, filters=None, columns=None, result_index=0, sorts=None, max_rows=None, _truncated_out=None)` → str：执行查询 → CSV 字符串（含 BOM）。
- `export_report_to_json(sql_query, pool_config, report_name, filters=None, smart_quote_flags=0, columns=None, result_index=0, sorts=None, max_rows=None, _truncated_out=None)` → str：执行查询 → JSON 字符串（支持智能去引号）。
- `handle_export(conn, query, pool_override=None)` → (int, str|bytes, dict)：HTTP 导出请求顶层分派入口。

### 内部函数

- `_load_and_transform(sql_query, pool_config, filters, columns, result_index, sorts, max_rows)`：共用查询执行+内存变换管线。
- `_encode_content(content, charset)`：字符串 → GBK/UTF-8 字节。
- `_build_export_filename(report_name, report_id, export_format, is_zip)`：Content-Disposition 三元组。
- `_create_temp_zip(content_bytes, filename, zip_filename)`：临时 ZIP 压缩包。

## 3. 数据流

```
handle_export(conn, query) → 解析查询参数(id/format/charset/smart_quotes/zip/f_*/op_*)
  → db.get_report() → db.get_pool()
  → sql_contains_write 写护栏检查
  → 分派:
      JSON → export_report_to_json → _load_and_transform → serialize_smart_quotes/json.dumps
      CSV  → export_report_to_csv → _load_and_transform → rows_to_csv
  → ZIP 模式: _encode_content → _create_temp_zip → bytes
  → 返回 (200, content_bytes, headers)
```

## 4. 依赖关系

AST import 实测：`db, app_config, render, report, query_executor, result_transform`。
- `db`：`get_report`/`get_pool`/`create_mysql_connection`/`execute_mysql_query`。
- `app_config`：`safe_int`/`serialize_smart_quotes`/`SMART_FLAG_*`。
- `render`：`format_cell`。
- `report`：`parse_filters`/`parse_sorts`/`parse_result_index`/`WRITE_DENIED_MESSAGE`。
- `query_executor`：`sql_contains_write`（写护栏）。
- `result_transform`：`filter_rows`/`sort_rows`/`select_columns`/`column_indices`。

## 5. 边界与异常

- 写护栏：`sql_contains_write` 检查 SQL 中是否含写操作（INSERT/UPDATE/DELETE 等），命中拒绝导出。
- 全量输出护栏：`allow_all_output` 参数控制是否允许不分页全量输出。
- 字符集：GBK 时移除 BOM（GBK 无 BOM 规范）。
- max_rows 截断：PH-07 约束，防止超大结果集。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 export.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
