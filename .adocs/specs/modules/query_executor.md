---
module: query_executor.py
contract_id: MOD-QUERY_EXECUTOR
version: 1.0
depends_on: [app_config, db]
last_reviewed_commit: 78895ce
last_reviewed_at: 2026-08-28
---

# query_executor.py 模块分卷

> 本分卷由 T-003 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`query_executor.py`（490 行，33 个 def/类）——**MySQL 查询执行器**。提供：
1. MySQL 连接/游标/行的**兼容包装层**（`_MySQLConnection`/`_MySQLCursor`/`_MySQLRow`），对上层暴露与 `sqlite3` 兼容的接口子集——这是项目「SQLite/MySQL 双引擎」的关键适配点；
2. 多段 SQL 拆分（正确处理引号/注释内的分号）与写语句检测（`sql_contains_write`）；
3. 统一执行入口 `execute_mysql_query`（支持事务包装与多结果集收集）。
被 `db.py`（适配层）转发调用，间接被 report/api_handler/config/export/scheduler 使用。

## 2. 公开 API 契约

### 2.1 兼容包装类（sqlite3 接口子集）

**`_MySQLRow(data)`**
- 同时支持 dict 键访问与整数索引（兼容 `sqlite3.Row`）。
- 方法：`__getitem__`/`__iter__`/`__len__`/`keys()`/`values()`/`__repr__`。

**`_MySQLCursor(cursor)`**
- 包装 MySQL 游标，暴露 sqlite3.Cursor 兼容子集。
- 属性 `description`（列描述）；方法 `execute(sql, params=None)`/`fetchone()`/`fetchall()`/`close()`。

**`_MySQLConnection(conn)`**
- 包装 MySQL 连接，暴露 sqlite3.Connection 兼容子集。
- 方法：`execute(sql, params=None)`/`cursor()`（返回 `_MySQLCursor` 包装）/`executescript(sql)`（按分号拆分逐条执行）/`commit()`/`begin()`/`rollback()`/`close()`/`__enter__`/`__exit__`。

### 2.2 连接创建

- `_connect_mysql_config()`：根据 app_config 创建 MySQL 连接（用于 config_db 存储）。
- `create_mysql_connection(pool_config: dict, read_timeout: int | None = None)`：根据连接池配置创建 MySQL 连接；`read_timeout` 传参（None 不限制，Web 交互传 30s）。

### 2.3 SQL 处理

- `_split_sql_statements(sql)` -> list：将 SQL 按 `;` 拆分为多条语句，正确处理引号（`'`/`"`/反引号）和注释（`--`/`#`/`/* */`）内部的 `;`。
- `_iter_sql_keywords(statement)` -> iterator：迭代语句中的 SQL 关键词（跳过注释、字符串字面量、括号、空白），用于关键词级判定。
- `sql_contains_write(sql)` -> bool：检测 SQL 是否包含写语句（INSERT/UPDATE/DELETE/DDL 等）。判定规则：
  - 首关键词在白名单 `_READ_STATEMENT_KEYWORDS = {SELECT, SHOW, DESCRIBE, DESC, EXPLAIN}` → 读；
  - 首关键词为 `WITH` → 扫描该语句全部关键词，命中写关键词（`_WRITE_STATEMENT_KEYWORDS`）即判写（覆盖 MySQL 8 CTE+DML），否则视为 CTE 读；
  - 其余首关键词 → 写；纯注释/空语句跳过不计。
  - 判定从严：宁按写处理（用户可开 allow_write），不误放实际写操作。

### 2.4 执行入口

**`execute_mysql_query(conn, sql: str, params: tuple = (), transactional: bool = False) -> list[dict]`**
- 在 MySQL 连接上执行 SQL，支持多段 SQL（`;` 分隔）。
- 逐条执行每段 SQL，跳过 DDL/DML（`cur.description is None`）等不返回结果集的语句，收集所有查询类语句结果。
- `transactional=True`：所有语句包装 BEGIN/COMMIT；任一语句失败 → ROLLBACK 后重新抛出。
- 返回 `[{"columns": [...], "rows": [...]}, ...]`；整个 SQL 无任何结果集返回 → `RuntimeError("查询未返回任何结果集（SQL 中缺少 SELECT 语句）")`。
- 注意：DDL（ALTER/CREATE/DROP）在 InnoDB 中隐式提交当前事务，事务内执行 DDL 可能导致部分语句 ROLLBACK 后仍无法撤销。

## 3. 数据流

```
调用方（db.execute_mysql_query 转发）
  → query_executor.execute_mysql_query(conn, sql, params, transactional)
      ├─ [transactional] conn.begin()/start_transaction()
      ├─ cur = conn.cursor()
      ├─ 对每段语句: _split_sql_statements(sql) 拆分 → cur.execute(stmt, params)
      │    └─ cur.description is not None → columns=[desc[0]...] + rows=cur.fetchall() → results.append(...)
      ├─ 无结果集 → RuntimeError
      ├─ [transactional] conn.commit()
      └─ 异常 → [transactional] conn.rollback() → raise
  SQL 写检测：sql_contains_write(sql)
    → _split_sql_statements → 逐条 _iter_sql_keywords → 关键词级判定（读白名单/WITH 扫描/其余判写）
```

## 4. 依赖关系

AST import 实测：`app_config, db`。
- `app_config`：MySQL 连接配置（`_connect_mysql_config`）。
- `db`：兼容适配层引用（本项目 db.py 从 config_db 转发，query_executor 与 db 存在相互引用以适配双引擎）。
- 无第三方驱动硬依赖：MySQL 连接通过 app_config 配置按需创建（`create_mysql_connection`），上层统一经 `db.py` 适配层访问，实现 SQLite/MySQL 双引擎透明切换。

## 5. 边界与异常

- 多段 SQL 拆分：正确处理引号内/注释内 `;`（`_split_sql_statements`）。
- 写检测从严：首关键词非读白名单即判写；WITH 需扫描全部关键词；纯注释语句跳过。
- 无结果集：`RuntimeError`（SQL 中缺少 SELECT）。
- 事务：任一语句失败 ROLLBACK 重抛；DDL 隐式提交警告（InnoDB）。
- 兼容包装：`_MySQLConnection`/`_MySQLCursor`/`_MySQLRow` 保证 sqlite3 接口子集（双引擎透明）。

## 6. 保鲜核对提交点

- last_reviewed_commit: 78895ce（T-002 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 query_executor.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
