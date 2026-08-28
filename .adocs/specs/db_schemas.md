---
module: db-schemas
contract_id: SPEC-DB-SCHEMAS
version: 1
depends_on: [T-002]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28T15:30:00+08:00
---

## 1. 职责概述

SqlReport 使用两个独立数据库：`config.db`（配置数据，9 张表，17 次迁移）和 `audit.db`（审计日志，1 张表，3 个索引）。双引擎支持：SQLite（开发/单机）和 MySQL（生产），由 `config_db` 数组中首个 `enable=true` 的元素决定。

**数据库文件清单**：

| 文件 | 用途 | 引擎 |
|------|------|------|
| `config.db` | 配置数据（用户/报表/缓存/调度） | SQLite/MySQL |
| `audit.db` | 审计日志（操作/访问/调度） | SQLite |

## 2. 公开 API 契约

### 2.1 config.db — 9 张表

#### connection_pools（连接池）
```sql
CREATE TABLE connection_pools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    host        TEXT    NOT NULL,
    port        INTEGER NOT NULL DEFAULT 3306,
    user        TEXT    NOT NULL,
    password    TEXT    NOT NULL,
    database    TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
);
```
- 语义：MySQL 连接池配置，report_configs 通过 `pool_id` FK 引用
- 去重：`UNIQUE(name)`

#### users（用户）
```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    UNIQUE NOT NULL,
    password_hash   TEXT    NOT NULL
);
```
- 语义：PBKDF2 密码哈希，单用户模式（通常仅 admin）

#### report_categories（报表分类）
```sql
CREATE TABLE report_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    parent_id   INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
);
```
- 语义：无限层级分类树，`parent_id=NULL` 为根节点

#### report_configs（报表配置）
```sql
CREATE TABLE report_configs (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    name                       TEXT    UNIQUE NOT NULL,
    sql_query                  TEXT    NOT NULL,
    default_page_size          INTEGER NOT NULL DEFAULT 20,
    pool_id                    INTEGER,
    category_id                INTEGER,
    memo                       TEXT,
    result_names               TEXT    DEFAULT '',
    prefer_cache               INTEGER NOT NULL DEFAULT 1,
    cache_ttl_hours            INTEGER NOT NULL DEFAULT 0,
    sort_order                 INTEGER NOT NULL DEFAULT 0,
    allow_write                INTEGER NOT NULL DEFAULT 1,
    allow_all_output           INTEGER NOT NULL DEFAULT 1,
    max_rows                   INTEGER NOT NULL DEFAULT 100000,
    keepalive_enabled          INTEGER NOT NULL DEFAULT 0,
    keepalive_ahead_seconds    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pool_id)      REFERENCES connection_pools(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id)  REFERENCES report_categories(id) ON DELETE SET NULL
);
```
- 核心业务表，字段含 SQL 查询、分页、缓存、写入守卫、保活等

#### sessions（会话）
```sql
CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created_at REAL NOT NULL
);
```
- 语义：登录会话 token，滑动过期机制

#### api_endpoints（API 端点）
```sql
CREATE TABLE api_endpoints (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id         INTEGER NOT NULL,
    name              TEXT    NOT NULL,
    url_path          TEXT    UNIQUE NOT NULL,
    output_format     TEXT    NOT NULL DEFAULT 'json',
    columns           TEXT,
    filters           TEXT,
    sorts             TEXT,
    row_limit         INTEGER DEFAULT 0,
    allowed_origins   TEXT,
    enabled           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    result_mode       TEXT    NOT NULL DEFAULT 'single',
    result_index      INTEGER NOT NULL DEFAULT 0,
    allow_fetch_all   INTEGER NOT NULL DEFAULT 1,
    static_cache      INTEGER NOT NULL DEFAULT 1,
    json_no_quotes    INTEGER NOT NULL DEFAULT 0,
    smart_quote_flags INTEGER NOT NULL DEFAULT 0,
    json_template     TEXT,
    description       TEXT,
    FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
);
```
- 语义：报表-as-API 配置，含 CORS/模板/智能引号/静态缓存等

#### api_keys（API 密钥）
```sql
CREATE TABLE api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    api_key     TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE
);
CREATE INDEX idx_api_keys_endpoint ON api_keys(endpoint_id);
```
- 语义：多密钥绑定单端点，支持启用/禁用

#### report_schedules（调度计划）
```sql
CREATE TABLE report_schedules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL DEFAULT '',
    schedule_type    TEXT NOT NULL DEFAULT 'interval',
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    daily_time       TEXT NOT NULL DEFAULT '08:00',
    misfire_policy   TEXT NOT NULL DEFAULT 'skip',
    enabled          INTEGER NOT NULL DEFAULT 1,
    exclusions       TEXT,
    audit_enabled    INTEGER NOT NULL DEFAULT 0,
    next_run_at      REAL,
    last_run_at      REAL,
    last_status      TEXT,
    last_error       TEXT,
    fail_count       INTEGER NOT NULL DEFAULT 0,
    last_duration_ms INTEGER,
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```
- 语义：定时/间隔调度，含排除规则（JSON 树：dow/tod/date/date_range，AND/OR）

#### schedule_reports（调度-报表关联）
```sql
CREATE TABLE schedule_reports (
    schedule_id INTEGER NOT NULL,
    report_id   INTEGER NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (schedule_id, report_id)
);
```
- 语义：多对多关联，order_index 控制执行顺序

### 2.2 audit.db — 1 张表

#### audit_logs（审计日志）
```sql
CREATE TABLE audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    type            TEXT    NOT NULL,
    session_user    TEXT,
    action          TEXT,
    entity_type     TEXT,
    entity_id       INTEGER,
    entity_name     TEXT,
    before_value    TEXT,
    after_value     TEXT,
    http_method     TEXT,
    http_path       TEXT,
    http_status     INTEGER,
    ip_address      TEXT,
    user_agent      TEXT,
    duration_ms     INTEGER,
    request_body    TEXT
);
CREATE INDEX idx_audit_logs_type      ON audit_logs(type);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_user      ON audit_logs(session_user);
```
- 语义：单表多态，4 种审计类型（operation/scheduler/web_access/api）
- 保留策略：`audit_db.retention_days`（默认 90 天），启动时清理过期记录

## 3. 数据流

```
app_config.json → config_db → SQLite/MySQL
                                  ↓
                          业务读写（CRUD）
                                  ↓
report_configs ──FK──→ connection_pools
report_configs ──FK──→ report_categories
api_endpoints  ──FK──→ report_configs (CASCADE)
api_keys       ──FK──→ api_endpoints (CASCADE)
schedule_reports ─PK─→ report_schedules + report_configs
```

## 4. 依赖关系

- **config_db.py**：DDL 定义 + 迁移逻辑（17 步）
- **audit_db.py**：DDL 定义 + 日志写入 + 过期清理
- **app_config.py**：决定使用 SQLite 还是 MySQL
- **所有业务模块**：通过 config_db/audit_db 的函数读写数据

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| SQLite 文件不存在 | 自动创建（含 DDL） |
| MySQL 连接失败 | 回退到 SQLite（若配置中存在） |
| 迁移步骤失败 | 事务回滚，保持原状态 |
| 审计写入失败 | `logging.warning`，不阻塞业务 |
| `before_value`/`after_value` | JSON 序列化存储，读取时反序列化 |

## 6. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | 9 张表 DDL 与字段语义 | last_reviewed_commit |
| CP-002 | 17 次迁移步骤清单 | last_reviewed_commit |
| CP-003 | audit_logs 单表多态设计 | last_reviewed_commit |
| CP-004 | 双引擎（SQLite/MySQL）切换逻辑 | last_reviewed_commit |
