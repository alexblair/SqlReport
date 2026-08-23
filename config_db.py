"""
config_db.py — 配置数据库 CRUD 操作

职责：
1. 根据 app_config.json 选择 SQLite 或 MySQL 作为配置存储引擎
2. 提供连接池配置、用户、报表配置、分类、session 的 CRUD 操作
3. 支持 SQLite（默认）和 MySQL 双引擎

设计：
- 所有函数显式接收 db 连接参数（依赖注入），方便测试 mock
- 模块级函数，不依赖类实例
"""

import os
import json
import logging
import sqlite3
import time
from typing import Optional

import static_cache

from app_config import get_active_db_config as _get_active_db_config


# 哨兵对象，用于区分"未传此参数"和"传了 None（设为 NULL）"
_UNSET = object()


def _placeholders(n: int) -> str:
    """生成 n 个 ? 占位符（逗号分隔），用于 IN (...) 子句。"""
    return ",".join("?" for _ in range(n))


# ---------------------------------------------------------------------------
# 审计日志辅助
# ---------------------------------------------------------------------------


def _write_audit_log(session_user, action, entity_type,
                     entity_id=None, entity_name=None,
                     before_value=None, after_value=None,
                     log_type="operation"):
    """写入一条审计日志到 audit.db。

    薄包装：统一走 audit_db.record_operation（保持本名称供测试 patch 与
    既有调用点使用）；异常降级为 logging.warning，避免审计失败影响业务操作。

    log_type: 审计类型，默认 operation；定时任务执行链（scheduler.py）传
    scheduler，使审计页可独立按"定时任务"类型筛选（B19/B20）。
    """
    from audit_db import record_operation
    record_operation(session_user, action, entity_type,
                     entity_id=entity_id, entity_name=entity_name,
                     before_value=before_value, after_value=after_value,
                     log_type=log_type)


# ---------------------------------------------------------------------------
# 引擎判断
# ---------------------------------------------------------------------------


def _get_db_config() -> dict:
    """从 app_config 获取当前启用的 config_db 配置（支持多配置列表 + enable 切换）。"""
    return _get_active_db_config()


def _get_engine() -> str:
    """
    返回当前配置的 config_db 引擎名（mysql / sqlite3）。

    注意：使用 late import of db 模块，使 unittest.mock.patch("db._get_db_config")
    能正确拦截内部调用。
    """
    import db as _db
    return _db._get_db_config().get("engine", "sqlite3")


# ---------------------------------------------------------------------------
# SQLite 连接
# ---------------------------------------------------------------------------


def _connect_sqlite() -> sqlite3.Connection:
    """
    根据 app_config 或环境变量创建 SQLite 连接。

    注意：使用 late import of db 模块，使 unittest.mock.patch("db._get_db_config")
    能正确拦截内部调用。
    """
    import db as _db
    cfg = _db._get_db_config()
    db_path = cfg.get("path") or os.environ.get("CONFIG_DB", "config.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# 工厂: get_config_db
# ---------------------------------------------------------------------------


def get_config_db():
    """
    创建并返回一个 config_db 连接。

    根据 app_config.json 中的 engine 字段自动选择 SQLite 或 MySQL。
    每请求应调用一次（独立连接，线程安全）。

    注意：使用 late import of db 模块，使 unittest.mock.patch("db._get_engine")
    和 patch("db._connect_mysql_config") / patch("db._connect_sqlite")
    能正确拦截内部调用。
    """
    import db as _db
    engine = _db._get_engine()
    if engine == "mysql":
        return _db._connect_mysql_config()
    return _db._connect_sqlite()


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS connection_pools (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        host        TEXT    NOT NULL,
        port        INTEGER NOT NULL DEFAULT 3306,
        user        TEXT    NOT NULL,
        password    TEXT    NOT NULL,
        database    TEXT    NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT    UNIQUE NOT NULL,
        password_hash   TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS report_categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        parent_id   INTEGER,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS report_configs (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT    UNIQUE NOT NULL,
        sql_query          TEXT    NOT NULL,
        default_page_size  INTEGER NOT NULL DEFAULT 20,
        pool_id            INTEGER,
        category_id        INTEGER,
        memo               TEXT,
        result_names       TEXT DEFAULT '',
        prefer_cache       INTEGER NOT NULL DEFAULT 1,
        cache_ttl_hours    INTEGER NOT NULL DEFAULT 0,
        sort_order         INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
        FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token      TEXT PRIMARY KEY,
        username   TEXT NOT NULL,
        created_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS api_endpoints (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id        INTEGER NOT NULL,
        name             TEXT    NOT NULL,
        url_path         TEXT    UNIQUE NOT NULL,
        output_format    TEXT    NOT NULL DEFAULT 'json',
        columns          TEXT,
        filters          TEXT,
        sorts            TEXT,
        row_limit        INTEGER DEFAULT 0,
        api_key          TEXT,
        allowed_origins  TEXT,
        enabled          INTEGER NOT NULL DEFAULT 1,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        result_mode      TEXT    NOT NULL DEFAULT 'single',
        result_index     INTEGER NOT NULL DEFAULT 0,
        allow_fetch_all  INTEGER NOT NULL DEFAULT 1,
        static_cache     INTEGER NOT NULL DEFAULT 1,
        json_no_quotes   INTEGER NOT NULL DEFAULT 0,
        smart_quote_flags INTEGER NOT NULL DEFAULT 0,
        json_template    TEXT,
        description      TEXT,
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL,
        name        TEXT    NOT NULL,
        api_key     TEXT    NOT NULL,
        enabled     INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_api_keys_endpoint ON api_keys(endpoint_id);
"""

_MYSQL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS connection_pools (
        id          INTEGER AUTO_INCREMENT PRIMARY KEY,
        name        VARCHAR(255) UNIQUE NOT NULL,
        host        VARCHAR(255) NOT NULL,
        port        INTEGER NOT NULL DEFAULT 3306,
        user        VARCHAR(255) NOT NULL,
        password    VARCHAR(255) NOT NULL,
        `database`  VARCHAR(255) NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER AUTO_INCREMENT PRIMARY KEY,
        username        VARCHAR(255) UNIQUE NOT NULL,
        password_hash   VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS report_categories (
        id          INTEGER AUTO_INCREMENT PRIMARY KEY,
        name        VARCHAR(255) UNIQUE NOT NULL,
        parent_id   INTEGER,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS report_configs (
        id                 INTEGER AUTO_INCREMENT PRIMARY KEY,
        name               VARCHAR(255) UNIQUE NOT NULL,
        sql_query          TEXT    NOT NULL,
        default_page_size  INTEGER NOT NULL DEFAULT 20,
        pool_id            INTEGER,
        category_id        INTEGER,
        memo               TEXT,
        result_names       TEXT,
        prefer_cache       TINYINT NOT NULL DEFAULT 1,
        cache_ttl_hours    INTEGER NOT NULL DEFAULT 0,
        sort_order         INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
        FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS sessions (
        token      VARCHAR(255) PRIMARY KEY,
        username   VARCHAR(255) NOT NULL,
        created_at DOUBLE NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS api_endpoints (
        id               INTEGER AUTO_INCREMENT PRIMARY KEY,
        report_id        INTEGER NOT NULL,
        name             VARCHAR(255) NOT NULL,
        url_path         VARCHAR(512) UNIQUE NOT NULL,
        output_format    VARCHAR(10) NOT NULL DEFAULT 'json',
        columns          TEXT,
        filters          TEXT,
        sorts            TEXT,
        row_limit        INTEGER DEFAULT 0,
        api_key          VARCHAR(255),
        allowed_origins  TEXT,
        enabled          TINYINT NOT NULL DEFAULT 1,
        created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        result_mode      VARCHAR(10) NOT NULL DEFAULT 'single',
        result_index     INTEGER NOT NULL DEFAULT 0,
        allow_fetch_all  TINYINT NOT NULL DEFAULT 1,
        static_cache     TINYINT NOT NULL DEFAULT 1,
        json_no_quotes   TINYINT NOT NULL DEFAULT 0,
        smart_quote_flags TINYINT NOT NULL DEFAULT 0,
        json_template    TEXT,
        description      TEXT,
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS api_keys (
        id          INTEGER AUTO_INCREMENT PRIMARY KEY,
        endpoint_id INTEGER NOT NULL,
        name        VARCHAR(255) NOT NULL,
        api_key     VARCHAR(255) NOT NULL,
        enabled     TINYINT NOT NULL DEFAULT 1,
        created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE,
        INDEX idx_api_keys_endpoint (endpoint_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def _get_schema_sql(engine: str) -> str:
    """返回对应引擎的建表 DDL。"""
    return _MYSQL_SCHEMA if engine == "mysql" else _SQLITE_SCHEMA


# ---------------------------------------------------------------------------
# 初始化 & 迁移
# ---------------------------------------------------------------------------


def init_db(conn) -> None:
    """
    初始化数据库表结构并执行迁移。

    根据 conn 的实际类型自动判断引擎，执行对应的 DDL 和迁移逻辑。
    幂等：可安全重复调用。

    注意：使用 late import of db 模块，使 unittest.mock.patch("db._get_engine")
    能正确拦截内部调用。
    """
    import db as _db
    engine = _db._get_engine()
    schema = _get_schema_sql(engine)

    # 建表
    if engine == "mysql":
        for stmt in schema.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
    else:
        conn.executescript(schema)
    conn.commit()

    if engine == "mysql":
        _init_mysql_migrations(conn)
    else:
        _init_sqlite_migrations(conn)


def _init_sqlite_migrations(conn) -> None:
    """SQLite 专属迁移逻辑。"""
    import sqlite3

    # 迁移 1: report_configs 旧版 NOT NULL + CASCADE → 新版
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    col_info = {}
    for row in cursor.fetchall():
        col_info[row[1]] = {"notnull": row[3]}
    if col_info.get("pool_id", {}).get("notnull") == 1:
        conn.executescript("""
            ALTER TABLE report_configs RENAME TO report_configs_old;
            CREATE TABLE report_configs (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                name               TEXT    UNIQUE NOT NULL,
                sql_query          TEXT    NOT NULL,
                default_page_size  INTEGER NOT NULL DEFAULT 20,
                pool_id            INTEGER,
                category_id        INTEGER,
                sort_order         INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
            );
            INSERT INTO report_configs (id, name, sql_query, default_page_size, pool_id, sort_order)
                SELECT id, name, sql_query, default_page_size, pool_id, sort_order
                FROM report_configs_old;
            DROP TABLE report_configs_old;
        """)
        conn.commit()

    cursor = conn.execute("PRAGMA table_info(report_configs)")
    col_info = {}
    for row in cursor.fetchall():
        col_info[row[1]] = {"notnull": row[3]}

    # 迁移 2: 添加 category_id 列（旧库没有该列）
    if "category_id" not in col_info:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN category_id INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 3: 创建 report_categories 表（旧库没有该表）
    conn.execute("""CREATE TABLE IF NOT EXISTS report_categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        parent_id   INTEGER,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
    )""")
    conn.commit()

    # 迁移 4: 旧 report_categories 加 parent_id 列
    cursor = conn.execute("PRAGMA table_info(report_categories)")
    cat_cols = {row[1] for row in cursor.fetchall()}
    if "parent_id" not in cat_cols:
        try:
            conn.execute("ALTER TABLE report_categories ADD COLUMN parent_id INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 5: 添加 memo 列到 report_configs
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    rpt_cols = {row[1] for row in cursor.fetchall()}
    if "memo" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN memo TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 6: 添加 result_names 列到 report_configs
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    rpt_cols = {row[1] for row in cursor.fetchall()}
    if "result_names" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN result_names TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 7: 添加 prefer_cache 和 cache_ttl_hours 列到 report_configs
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    rpt_cols = {row[1] for row in cursor.fetchall()}
    if "prefer_cache" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN prefer_cache INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()
    if "cache_ttl_hours" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN cache_ttl_hours INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()


    # 迁移 8: 创建 api_endpoints 表
    conn.execute("""CREATE TABLE IF NOT EXISTS api_endpoints (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id        INTEGER NOT NULL,
        name             TEXT    NOT NULL,
        url_path         TEXT    UNIQUE NOT NULL,
        output_format    TEXT    NOT NULL DEFAULT 'json',
        columns          TEXT,
        filters          TEXT,
        sorts            TEXT,
        row_limit        INTEGER DEFAULT 0,
        api_key          TEXT,
        allowed_origins  TEXT,
        enabled          INTEGER NOT NULL DEFAULT 1,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
    )""")
    conn.commit()

    # 迁移 9: 添加 result_mode 和 result_index 列到 api_endpoints
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "result_mode" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN result_mode TEXT NOT NULL DEFAULT 'single'")
            conn.commit()
        except Exception:
            conn.rollback()
    if "result_index" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN result_index INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 10: 添加 allow_fetch_all 列到 api_endpoints（fetch_all 全量获取开关，默认开启）
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "allow_fetch_all" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN allow_fetch_all INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 11: 添加 static_cache 列到 api_endpoints（静态文件缓存开关，默认开启）
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "static_cache" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN static_cache INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 12: 添加 json_template 列到 api_endpoints（JSON 输出模板，空=未启用）
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "json_template" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN json_template TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 13: 添加 description 列到 api_endpoints（接口说明，纯展示字段）
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "description" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN description TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 14: API Key 多 key 化（PH-02 建立）——建 api_keys 表 + 旧列数据迁入。
    # PH-04/PH-06 的新列并入同一迁移批次，不得新建迁移号（预留段见下）。
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL,
        name        TEXT    NOT NULL,
        api_key     TEXT    NOT NULL,
        enabled     INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_endpoint ON api_keys(endpoint_id)")
    # 数据迁移（幂等：已迁入的 key 跳过；旧列置空后无重复源）：
    # api_endpoints.api_key 非空 → 插入 api_keys（name=端点名），旧列置空作兼容回退
    rows = conn.execute(
        "SELECT id, name, api_key FROM api_endpoints "
        "WHERE api_key IS NOT NULL AND api_key != ''").fetchall()
    for eid, name, key in rows:
        exists = conn.execute(
            "SELECT 1 FROM api_keys WHERE endpoint_id=? AND api_key=?",
            (eid, key)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO api_keys (endpoint_id, name, api_key, enabled) "
                "VALUES (?,?,?,1)", (eid, name, key))
            conn.execute("UPDATE api_endpoints SET api_key='' WHERE id=?", (eid,))
    conn.commit()
    # 迁移 14 续：PH-04 reports.allow_write（存量默认 1 = 保持现状；
    # 新建默认 0 由表单/写入路径控制）
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    report_cols = {row[1] for row in cursor.fetchall()}
    if "allow_write" not in report_cols:
        try:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN allow_write INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()
    # 迁移 14 续：PH-06 reports.allow_all_output（存量默认 1 = 保持现状；
    # 新建默认 0 由表单/写入路径控制）+ max_rows（默认 100000，仅关闭全量输出时生效）
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    report_cols = {row[1] for row in cursor.fetchall()}
    if "allow_all_output" not in report_cols:
        try:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN allow_all_output INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()
    if "max_rows" not in report_cols:
        try:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN max_rows INTEGER NOT NULL DEFAULT 100000")
            conn.commit()
        except Exception:
            conn.rollback()
    # 迁移 14 续：api_endpoints.json_no_quotes（API「值无引号」选项，
    # 默认 0 = 关闭，与报表导出 json_no_quotes 同语义）
    cursor = conn.execute("PRAGMA table_info(api_endpoints)")
    api_cols = {row[1] for row in cursor.fetchall()}
    if "json_no_quotes" not in api_cols:
        try:
            conn.execute(
                "ALTER TABLE api_endpoints "
                "ADD COLUMN json_no_quotes INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()
    # 迁移 15：api_endpoints.smart_quote_flags（「智能去引号」复选面板位图，
    # 1=十进制数字、2=科学计数法、4=千分位数字，默认 0 = 标准 JSON）。
    # 存量 json_no_quotes=1（旧「值无引号」开启）迁移为面板全开（0b111）后
    # **重置旧列 json_no_quotes=0**——一次性转换完成即消费旧标记。若不重置，
    # 运行期兼容逻辑（json_no_quotes=1 → flags=max(flags,7)）会把端点永久钉死
    # 在面板全开，用户后续取消勾选无效（KPI 案例缺陷根因）。重复执行幂等。
    if "smart_quote_flags" not in api_cols:
        try:
            conn.execute(
                "ALTER TABLE api_endpoints "
                "ADD COLUMN smart_quote_flags INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()
    if "smart_quote_flags" not in api_cols:
        try:
            conn.execute(
                "UPDATE api_endpoints SET smart_quote_flags=7 "
                "WHERE json_no_quotes=1 AND smart_quote_flags=0")
            conn.commit()
        except Exception:
            conn.rollback()
    try:
        conn.execute(
            "UPDATE api_endpoints SET json_no_quotes=0 "
            "WHERE json_no_quotes=1 AND smart_quote_flags>0")
        conn.commit()
    except Exception:
        conn.rollback()

    # 迁移 16：报表定时任务 report_schedules 表 + report_configs 缓存保活列。
    # 定时执行（interval/daily）与缓存保活（refresh-ahead）共用本批次；
    # 删除报表时由应用层级联清理任务行（SQLite FK 默认 OFF，不依赖外键）。
    conn.execute("""CREATE TABLE IF NOT EXISTS report_schedules (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL DEFAULT '',
        schedule_type    TEXT    NOT NULL DEFAULT 'interval',
        interval_minutes INTEGER NOT NULL DEFAULT 60,
        daily_time       TEXT    NOT NULL DEFAULT '08:00',
        misfire_policy   TEXT    NOT NULL DEFAULT 'skip',
        enabled          INTEGER NOT NULL DEFAULT 1,
        exclusions       TEXT,
        audit_enabled    INTEGER NOT NULL DEFAULT 0,
        next_run_at      REAL,
        last_run_at      REAL,
        last_status      TEXT,
        last_error       TEXT,
        fail_count       INTEGER NOT NULL DEFAULT 0,
        last_duration_ms INTEGER,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS schedule_reports (
        schedule_id INTEGER NOT NULL,
        report_id   INTEGER NOT NULL,
        order_index INTEGER NOT NULL DEFAULT 0,
        enabled     INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (schedule_id, report_id)
    )""")
    conn.commit()
    # 旧库升级：迁移 16 早批次的 report_schedules 无耗时列（幂等补齐）
    cursor = conn.execute("PRAGMA table_info(report_schedules)")
    sched_cols = {row[1] for row in cursor.fetchall()}
    if "last_duration_ms" not in sched_cols:
        try:
            conn.execute(
                "ALTER TABLE report_schedules ADD COLUMN last_duration_ms INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    rpt_cols = {row[1] for row in cursor.fetchall()}
    if "keepalive_enabled" not in rpt_cols:
        try:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN keepalive_enabled INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()
    if "keepalive_ahead_seconds" not in rpt_cols:
        try:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()
    # ---- 迁移 17：定时任务组合与排除逻辑（规格 scheduler-composition-exclusion）
    # 旧库（report_schedules 仍含 report_id 列）升级：表重建去掉 report_id
    # 列与 UNIQUE，并新建 schedule_reports 关联表，旧 report_id 回填为绑定。
    # 新库初始 DDL 已是新结构，此处自动跳过（report_id 列不存在）。
    try:
        cur = conn.execute("PRAGMA table_info(report_schedules)")
        cols = {row[1] for row in cur.fetchall()}
        if "report_id" in cols:
            conn.execute("""CREATE TABLE report_schedules_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                schedule_type TEXT NOT NULL DEFAULT 'interval',
                interval_minutes INTEGER NOT NULL DEFAULT 60,
                daily_time TEXT NOT NULL DEFAULT '08:00',
                misfire_policy TEXT NOT NULL DEFAULT 'skip',
                enabled INTEGER NOT NULL DEFAULT 1,
                exclusions TEXT,
                audit_enabled INTEGER NOT NULL DEFAULT 0,
                next_run_at REAL,
                last_run_at REAL,
                last_status TEXT,
                last_error TEXT,
                fail_count INTEGER NOT NULL DEFAULT 0,
                last_duration_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )""")
            conn.execute(
                "INSERT INTO report_schedules_new "
                "(id, schedule_type, interval_minutes, daily_time, misfire_policy, "
                "enabled, next_run_at, last_run_at, last_status, last_error, "
                "fail_count, last_duration_ms, created_at, updated_at) "
                "SELECT id, schedule_type, interval_minutes, daily_time, "
                "misfire_policy, enabled, next_run_at, last_run_at, last_status, "
                "last_error, fail_count, last_duration_ms, created_at, updated_at "
                "FROM report_schedules")
            conn.execute(
                "CREATE TABLE schedule_reports ("
                "schedule_id INTEGER NOT NULL, report_id INTEGER NOT NULL, "
                "order_index INTEGER NOT NULL DEFAULT 0, "
                "enabled INTEGER NOT NULL DEFAULT 1, "
                "PRIMARY KEY (schedule_id, report_id))")
            conn.execute(
                "INSERT INTO schedule_reports (schedule_id, report_id, "
                "order_index, enabled) SELECT id, report_id, 0, 1 "
                "FROM report_schedules")
            conn.execute("DROP TABLE report_schedules")
            conn.execute(
                "ALTER TABLE report_schedules_new RENAME TO report_schedules")
            conn.commit()
    except Exception:
        conn.rollback()
        # 迁移失败静默吞掉会导致下次启动反复重试同一失败段（2026-08-23
        # 审查）：必须留痕，便于定位卡死的升级路径。
        logging.exception("迁移 17（SQLite 表重建）失败，已回滚")
    # ---- 预留：后续批次 ADD COLUMN 幂等段写于此（同一迁移批次）----


def _init_mysql_migrations(conn) -> None:
    """MySQL 专属迁移逻辑（使用 SHOW COLUMNS 替代 PRAGMA table_info）。"""
    from query_executor import _MySQLConnection, _connect_mysql_config, execute_mysql_query

    # 迁移 1: 检查 report_configs.pool_id 是否为 NOT NULL
    cursor = conn.execute("SHOW COLUMNS FROM report_configs")
    col_info = {}
    for row in cursor.fetchall():
        # SHOW COLUMNS: Field, Type, Null, Key, Default, Extra
        col_info[row[0]] = {"null": row[2]}
    if col_info.get("pool_id", {}).get("null") == "NO":
        # MySQL 不支持 RENAME 后重建的轻量方式，直接修改列
        conn.execute(
            "ALTER TABLE report_configs MODIFY COLUMN pool_id INTEGER NULL"
        )
        conn.commit()

    cursor = conn.execute("SHOW COLUMNS FROM report_configs")
    col_info = {}
    for row in cursor.fetchall():
        col_info[row[0]] = {}

    # 迁移 2: 添加 category_id 列
    if "category_id" not in col_info:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN category_id INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 3: 迁移 4 已由建表 DDL 覆盖，无需额外操作

    # 迁移 4: 检查 report_categories 是否有 parent_id 列
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_categories")
        cat_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        cat_cols = set()
    if "parent_id" not in cat_cols:
        try:
            conn.execute("ALTER TABLE report_categories ADD COLUMN parent_id INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 5: 添加 memo 列到 report_configs
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        rpt_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        rpt_cols = set()
    if "memo" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN memo TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 6: 添加 result_names 列到 report_configs
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        rpt_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        rpt_cols = set()
    if "result_names" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN result_names TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 7: 添加 prefer_cache 和 cache_ttl_hours 列到 report_configs
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        rpt_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        rpt_cols = set()
    if "prefer_cache" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN prefer_cache TINYINT NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()
    if "cache_ttl_hours" not in rpt_cols:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN cache_ttl_hours INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 8: 创建 api_endpoints 表
    try:
        cursor = conn.execute("SHOW TABLES LIKE 'api_endpoints'")
        if not cursor.fetchone():
            conn.execute("""CREATE TABLE api_endpoints (
                id               INTEGER AUTO_INCREMENT PRIMARY KEY,
                report_id        INTEGER NOT NULL,
                name             VARCHAR(255) NOT NULL,
                url_path         VARCHAR(512) UNIQUE NOT NULL,
                output_format    VARCHAR(10) NOT NULL DEFAULT 'json',
                columns          TEXT,
                filters          TEXT,
                sorts            TEXT,
                row_limit        INTEGER DEFAULT 0,
                api_key          VARCHAR(255),
                allowed_origins  TEXT,
                enabled          TINYINT NOT NULL DEFAULT 1,
                created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            conn.commit()
    except Exception:
        conn.rollback()

    # 迁移 9: 添加 result_mode 和 result_index 列到 api_endpoints
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        api_cols = set()
    if "result_mode" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN result_mode VARCHAR(10) NOT NULL DEFAULT 'single'")
            conn.commit()
        except Exception:
            conn.rollback()
    if "result_index" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN result_index INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 10: 添加 allow_fetch_all 列到 api_endpoints（fetch_all 全量获取开关，默认开启）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        api_cols = set()
    if "allow_fetch_all" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN allow_fetch_all TINYINT NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 11: 添加 static_cache 列到 api_endpoints（静态文件缓存开关，默认开启）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        api_cols = set()
    if "static_cache" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN static_cache TINYINT NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 12: 添加 json_template 列到 api_endpoints（JSON 输出模板，空=未启用）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        api_cols = set()
    if "json_template" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN json_template TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 13: 添加 description 列到 api_endpoints（接口说明，纯展示字段）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        api_cols = set()
    if "description" not in api_cols:
        try:
            conn.execute("ALTER TABLE api_endpoints ADD COLUMN description TEXT")
            conn.commit()
        except Exception:
            conn.rollback()

    # 迁移 14: API Key 多 key 化（PH-02 建立）——建 api_keys 表 + 旧列数据迁入。
    # PH-04/PH-06 的新列并入同一迁移批次，不得新建迁移号（预留段见下）。
    try:
        cursor = conn.execute("SHOW TABLES LIKE 'api_keys'")
        api_keys_exists = bool(cursor.fetchone())
    except Exception:
        api_keys_exists = False
    if not api_keys_exists:
        try:
            conn.execute("""CREATE TABLE api_keys (
                id          INTEGER AUTO_INCREMENT PRIMARY KEY,
                endpoint_id INTEGER NOT NULL,
                name        VARCHAR(255) NOT NULL,
                api_key     VARCHAR(255) NOT NULL,
                enabled     TINYINT NOT NULL DEFAULT 1,
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE,
                INDEX idx_api_keys_endpoint (endpoint_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            conn.commit()
        except Exception:
            conn.rollback()
    # 数据迁移（幂等：已迁入的 key 跳过；旧列置空后无重复源）：
    # api_endpoints.api_key 非空 → 插入 api_keys（name=端点名），旧列置空作兼容回退
    try:
        cursor = conn.execute(
            "SELECT id, name, api_key FROM api_endpoints "
            "WHERE api_key IS NOT NULL AND api_key != ''")
        rows = cursor.fetchall()
        for row in rows:
            eid, name, key = row[0], row[1], row[2]
            cursor2 = conn.execute(
                "SELECT 1 FROM api_keys WHERE endpoint_id=%s AND api_key=%s",
                (eid, key))
            if not cursor2.fetchone():
                conn.execute(
                    "INSERT INTO api_keys (endpoint_id, name, api_key, enabled) "
                    "VALUES (%s,%s,%s,1)", (eid, name, key))
                conn.execute(
                    "UPDATE api_endpoints SET api_key='' WHERE id=%s", (eid,))
        conn.commit()
    except Exception:
        conn.rollback()
    # 迁移 14 续：PH-04 reports.allow_write（存量默认 1 = 保持现状；
    # 新建默认 0 由表单/写入路径控制）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        report_cols = {row[0] for row in cursor.fetchall()}
        if "allow_write" not in report_cols:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN allow_write INTEGER NOT NULL DEFAULT 1")
            conn.commit()
    except Exception:
        conn.rollback()
    # 迁移 14 续：PH-06 reports.allow_all_output（存量默认 1 = 保持现状；
    # 新建默认 0 由表单/写入路径控制）+ max_rows（默认 100000，仅关闭全量输出时生效）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        report_cols = {row[0] for row in cursor.fetchall()}
        if "allow_all_output" not in report_cols:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN allow_all_output INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        if "max_rows" not in report_cols:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN max_rows INTEGER NOT NULL DEFAULT 100000")
            conn.commit()
    except Exception:
        conn.rollback()
    # 迁移 14 续：api_endpoints.json_no_quotes（API「值无引号」选项，
    # 默认 0 = 关闭，与报表导出 json_no_quotes 同语义）
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
        if "json_no_quotes" not in api_cols:
            conn.execute(
                "ALTER TABLE api_endpoints "
                "ADD COLUMN json_no_quotes TINYINT NOT NULL DEFAULT 0")
            conn.commit()
    except Exception:
        conn.rollback()
    # 迁移 15：api_endpoints.smart_quote_flags（「智能去引号」复选面板位图，
    # 1=十进制数字、2=科学计数法、4=千分位数字，默认 0 = 标准 JSON）。
    # 存量 json_no_quotes=1（旧「值无引号」开启）迁移为面板全开（0b111）后
    # **重置旧列 json_no_quotes=0**——一次性转换完成即消费旧标记，防止运行期
    # 兼容逻辑把端点永久钉死在面板全开（KPI 案例缺陷根因）。重复执行幂等。
    try:
        cursor = conn.execute("SHOW COLUMNS FROM api_endpoints")
        api_cols = {row[0] for row in cursor.fetchall()}
        if "smart_quote_flags" not in api_cols:
            conn.execute(
                "ALTER TABLE api_endpoints "
                "ADD COLUMN smart_quote_flags TINYINT NOT NULL DEFAULT 0")
            conn.commit()
        conn.execute(
            "UPDATE api_endpoints SET smart_quote_flags=7 "
            "WHERE json_no_quotes=1 AND smart_quote_flags=0")
        conn.commit()
        conn.execute(
            "UPDATE api_endpoints SET json_no_quotes=0 "
            "WHERE json_no_quotes=1 AND smart_quote_flags>0")
        conn.commit()
    except Exception:
        conn.rollback()
    # 迁移 16：报表定时任务 report_schedules 表 + report_configs 缓存保活列
    #（与 SQLite 迁移 16 同构；删除报表时应用层级联清理任务行）。
    try:
        cursor = conn.execute("SHOW TABLES LIKE 'report_schedules'")
        if not cursor.fetchone():
            conn.execute("""CREATE TABLE report_schedules (
                id               INTEGER AUTO_INCREMENT PRIMARY KEY,
                name             VARCHAR(128) NOT NULL DEFAULT '',
                schedule_type    VARCHAR(10) NOT NULL DEFAULT 'interval',
                interval_minutes INTEGER NOT NULL DEFAULT 60,
                daily_time       VARCHAR(5) NOT NULL DEFAULT '08:00',
                misfire_policy   VARCHAR(10) NOT NULL DEFAULT 'skip',
                enabled          TINYINT NOT NULL DEFAULT 1,
                exclusions       TEXT,
                audit_enabled    TINYINT NOT NULL DEFAULT 0,
                next_run_at      DOUBLE,
                last_run_at      DOUBLE,
                last_status      VARCHAR(10),
                last_error       TEXT,
                fail_count       INTEGER NOT NULL DEFAULT 0,
                last_duration_ms BIGINT,
                created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            conn.execute("""CREATE TABLE IF NOT EXISTS schedule_reports (
                schedule_id INTEGER NOT NULL,
                report_id   INTEGER NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                enabled     TINYINT NOT NULL DEFAULT 1,
                PRIMARY KEY (schedule_id, report_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            conn.commit()
        # 与 SQLite 迁移 16 同构：早批次表缺耗时列时幂等补齐
        #（2026-08-21 事故：线上 MySQL 表建于 T2 批次，T4 新增列未同步，
        #  回写 1054 → next_run_at 永不推进 → 每 tick 重复执行）
        cursor = conn.execute("SHOW COLUMNS FROM report_schedules")
        sched_cols = {row[0] for row in cursor.fetchall()}
        if "last_duration_ms" not in sched_cols:
            try:
                conn.execute(
                    "ALTER TABLE report_schedules "
                    "ADD COLUMN last_duration_ms BIGINT")
                conn.commit()
            except Exception:
                conn.rollback()
    except Exception:
        conn.rollback()
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_configs")
        report_cols = {row[0] for row in cursor.fetchall()}
        if "keepalive_enabled" not in report_cols:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN keepalive_enabled TINYINT NOT NULL DEFAULT 0")
            conn.commit()
        if "keepalive_ahead_seconds" not in report_cols:
            conn.execute(
                "ALTER TABLE report_configs "
                "ADD COLUMN keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    except Exception:
        conn.rollback()
    # ---- 迁移 17：定时任务组合与排除逻辑（规格 scheduler-composition-exclusion）
    # 旧 MySQL 库（report_schedules 仍含 report_id 列与 UNIQUE 索引）升级：
    # 先回填 schedule_reports，再 DROP COLUMN report_id 并补 name/exclusions/
    # audit_enabled 列。新库初始 DDL 已是新结构，此处自动跳过。
    try:
        cursor = conn.execute("SHOW COLUMNS FROM report_schedules")
        sched_cols = {row[0] for row in cursor.fetchall()}
        if "report_id" in sched_cols:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schedule_reports ("
                "schedule_id INTEGER NOT NULL, report_id INTEGER NOT NULL, "
                "order_index INTEGER NOT NULL DEFAULT 0, "
                "enabled TINYINT NOT NULL DEFAULT 1, "
                "PRIMARY KEY (schedule_id, report_id)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
            conn.execute(
                "INSERT INTO schedule_reports (schedule_id, report_id, "
                "order_index, enabled) SELECT id, report_id, 0, 1 "
                "FROM report_schedules")
            conn.commit()
            idx = conn.execute(
                "SELECT DISTINCT index_name FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = "
                "'report_schedules' AND non_unique = 0 AND column_name = "
                "'report_id'").fetchall()
            for r in idx:
                conn.execute(
                    f"ALTER TABLE report_schedules DROP INDEX {r[0]}")
            conn.execute(
                "ALTER TABLE report_schedules DROP COLUMN report_id")
            conn.execute(
                "ALTER TABLE report_schedules ADD COLUMN name "
                "VARCHAR(128) NOT NULL DEFAULT ''")
            conn.execute(
                "ALTER TABLE report_schedules ADD COLUMN exclusions TEXT")
            conn.execute(
                "ALTER TABLE report_schedules ADD COLUMN audit_enabled "
                "TINYINT NOT NULL DEFAULT 0")
            conn.commit()
    except Exception:
        conn.rollback()
        # 同 SQLite 段：迁移失败必须留痕（否则反复重试无迹可循）
        logging.exception("迁移 17（MySQL 列改造）失败，已回滚")
    # ---- 预留：后续批次 ADD COLUMN 幂等段写于此（同一迁移批次）----


# ---------------------------------------------------------------------------
# 连接池 CRUD
# ---------------------------------------------------------------------------

def add_pool(conn, name: str, host: str, port: int,
             user: str, password: str, database: str,
             session_user=None) -> int:
    """新增一个 MySQL 连接池配置，返回自增 id。自动分配 sort_order。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM connection_pools").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO connection_pools (name,host,port,user,password,`database`,sort_order) VALUES (?,?,?,?,?,?,?)",
        (name, host, port, user, password, database, max_order + 1),
    )
    conn.commit()
    _write_audit_log(session_user, "create_pool", "pool", cur.lastrowid, name,
                     after_value={"name": name, "host": host, "port": port, "user": user, "database": database})
    return cur.lastrowid


def get_pool(conn, pool_id) -> Optional[dict]:
    """根据 id 查询单个连接池配置，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM connection_pools WHERE id=?", (pool_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_pools(conn) -> list[dict]:
    """返回所有连接池配置列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM connection_pools ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_pool(conn, pool_id: int, name: str, host: str,
                port: int, user: str, password: str, database: str,
                session_user=None) -> bool:
    """更新连接池配置，影响行数 >0 返回 True。"""
    before = get_pool(conn, pool_id) if session_user else None
    cur = conn.execute(
        "UPDATE connection_pools SET name=?,host=?,port=?,user=?,password=?,`database`=? WHERE id=?",
        (name, host, port, user, password, database, pool_id),
    )
    conn.commit()
    _write_audit_log(session_user, "update_pool", "pool", pool_id, name,
                     before_value=before,
                     after_value={"name": name, "host": host, "port": port, "user": user, "database": database})
    return cur.rowcount > 0


def count_reports_by_pool(conn) -> dict[int, int]:
    """按连接池聚合关联报表数（spec ux-optimization 批次2#6）。

    返回 {pool_id: 报表数}；pool_id 为 NULL 的报表不计入。
    供删除确认弹窗披露破坏半径（单条 GROUP BY，避免逐池查询）。
    """
    rows = conn.execute(
        "SELECT pool_id, COUNT(*) AS cnt FROM report_configs"
        " WHERE pool_id IS NOT NULL GROUP BY pool_id"
    ).fetchall()
    return {r["pool_id"]: r["cnt"] for r in rows}


def delete_pool(conn, pool_id: int, session_user=None) -> bool:
    """
    删除连接池配置。

    先将关联报表的 pool_id 置空（断开外键关联，保留报表），再删除连接池。
    返回 True 表示删除成功。
    """
    before = get_pool(conn, pool_id) if session_user else None
    # 先断开报表关联（report_configs 表可能不存在于测试环境）
    try:
        conn.execute("UPDATE report_configs SET pool_id = NULL WHERE pool_id = ?", (pool_id,))
    except Exception:
        pass
    cur = conn.execute("DELETE FROM connection_pools WHERE id=?", (pool_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_pool", "pool", pool_id,
                     before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def _move_item(conn, get_items, table, obj_id, direction, audit_action,
               entity_type, session_user=None,
               id_col="id", sort_col="sort_order", entity_id_extra=None) -> bool:
    """move_pool / move_report / move_category 的公共实现（等价重构）。

    get_items(conn) 返回按 sort_order 排序的行列表（dict，含 id_col/sort_col/name 键）。
    取列表 → 找 idx → up/down 判定 swap_idx → 两条 UPDATE 交换 sort_order → commit → 审计。
    找不到对象、direction 非法或已到边界时返回 False 且不 commit。
    审计 entity_id 默认为 obj_id；entity_id_extra 非 None 时用作审计 entity_id（预留槽）。
    """
    items = get_items(conn)
    idx = next((i for i, it in enumerate(items) if it[id_col] == obj_id), None)
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        swap_idx = idx - 1
    elif direction == "down" and idx < len(items) - 1:
        swap_idx = idx + 1
    else:
        return False
    swap_id = items[swap_idx][id_col]
    so_a = items[idx][sort_col] or idx
    so_b = items[swap_idx][sort_col] or swap_idx
    conn.execute(f"UPDATE {table} SET {sort_col}=? WHERE {id_col}=?", (so_b, obj_id))
    conn.execute(f"UPDATE {table} SET {sort_col}=? WHERE {id_col}=?", (so_a, swap_id))
    conn.commit()
    _write_audit_log(session_user, audit_action, entity_type,
                     obj_id if entity_id_extra is None else entity_id_extra,
                     items[idx].get("name"))
    return True


def move_pool(conn, pool_id: int, direction: str, session_user=None) -> bool:
    """
    调整连接池排序。direction 为 'up' 或 'down'。
    与相邻项交换 sort_order，返回 True 表示移动成功。
    """
    return _move_item(conn, get_all_pools, "connection_pools", pool_id,
                      direction, "move_pool", "pool", session_user)


# ---------------------------------------------------------------------------
# 用户 CRUD
# ---------------------------------------------------------------------------

def add_user(conn, username: str, password_hash: str, session_user=None) -> int:
    """新增用户，返回自增 id。"""
    cur = conn.execute(
        "INSERT INTO users (username,password_hash) VALUES (?,?)",
        (username, password_hash),
    )
    conn.commit()
    _write_audit_log(session_user, "create_user", "user", cur.lastrowid, username)
    return cur.lastrowid


def get_user(conn, username: str) -> Optional[dict]:
    """根据用户名查询用户，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn, user_id: int) -> Optional[dict]:
    """根据 id 查询用户，不存在返回 None。"""
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_all_users(conn) -> list[dict]:
    """返回所有用户列表。"""
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def update_user(conn, user_id: int, username: str,
                password_hash: str, session_user=None) -> bool:
    """更新用户信息，影响行数 >0 返回 True。"""
    before = get_user_by_id(conn, user_id) if session_user else None
    cur = conn.execute(
        "UPDATE users SET username=?,password_hash=? WHERE id=?",
        (username, password_hash, user_id),
    )
    conn.commit()
    _write_audit_log(session_user, "update_user", "user", user_id, username,
                     before_value=before, after_value={"username": username})
    return cur.rowcount > 0


def delete_user(conn, user_id: int, session_user=None) -> bool:
    """删除用户，影响行数 >0 返回 True。"""
    before = get_user_by_id(conn, user_id) if session_user else None
    cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_user", "user", user_id,
                     before.get("username") if before else None,
                     before_value=before)
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# 报表配置 CRUD
# ---------------------------------------------------------------------------

def add_report(conn, name: str, sql_query: str,
               default_page_size: int, pool_id,
               category_id=None,
               memo=None,
               result_names=None,
               prefer_cache: int = 1,
               cache_ttl_hours: int = 0,
               allow_write: int = 0,
               allow_all_output: int = 0,
               max_rows: int = 100000,
               keepalive_enabled: int = 0,
               keepalive_ahead_seconds: int = 0,
               session_user=None) -> int:
    """新增报表配置，返回自增 id。自动分配 sort_order。

    allow_write: 是否允许执行写语句。新建默认 0（写护栏，PH-05）；
                 存量数据由迁移 14 统一置 1（保持现状）。
    allow_all_output: 是否允许全量输出。新建默认 0（全量输出护栏，PH-06/07），
                      关闭时结果超过 max_rows 即截断；存量数据由迁移 14 统一置 1。
    max_rows: 全量输出关闭时的截断行数上限（默认 100000）。
    keepalive_enabled / keepalive_ahead_seconds: 缓存保活开关与提前量秒数
                 （scheduler T2/T4；仅 prefer_cache=1 且 Redis 可用时生效）。
    """
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM report_configs").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,category_id,memo,result_names,prefer_cache,cache_ttl_hours,allow_write,allow_all_output,max_rows,keepalive_enabled,keepalive_ahead_seconds,sort_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, sql_query, default_page_size, pool_id, category_id, memo, result_names or '', prefer_cache, cache_ttl_hours, allow_write, allow_all_output, max_rows, int(bool(keepalive_enabled)), int(keepalive_ahead_seconds), max_order + 1),
    )
    conn.commit()
    _write_audit_log(session_user, "create_report", "report", cur.lastrowid, name,
                     after_value={"name": name, "sql_query": sql_query,
                                  "default_page_size": default_page_size,
                                  "pool_id": pool_id, "category_id": category_id,
                                  "memo": memo, "prefer_cache": prefer_cache,
                                  "cache_ttl_hours": cache_ttl_hours,
                                  "allow_write": allow_write,
                                  "allow_all_output": allow_all_output,
                                  "max_rows": max_rows,
                                  "keepalive_enabled": int(bool(keepalive_enabled)),
                                  "keepalive_ahead_seconds": int(keepalive_ahead_seconds)})
    return cur.lastrowid


def get_report(conn, report_id: int) -> Optional[dict]:
    """根据 id 查询报表配置，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM report_configs WHERE id=?", (report_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_reports(conn) -> list[dict]:
    """返回所有报表配置列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM report_configs ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_report(conn, report_id: int, name: str,
                  sql_query: str, default_page_size: int,
                  pool_id,
                  category_id=None,
                  memo=None,
                  result_names=None,
                  prefer_cache: int = 1,
                  cache_ttl_hours: int = 0,
                  allow_write: int = 1,
                  allow_all_output: int = 1,
                  max_rows: int = 100000,
                  keepalive_enabled: int = 0,
                  keepalive_ahead_seconds: int = 0,
                  session_user=None) -> bool:
    """更新报表配置，影响行数 >0 返回 True。

    allow_write: 编辑表单提交值；缺省 1 兼容历史调用（保持存量语义）。
    allow_all_output: 编辑表单提交值；缺省 1 兼容历史调用（保持存量语义）。
    max_rows: 编辑表单提交值；缺省 100000。
    keepalive_enabled / keepalive_ahead_seconds: 缓存保活开关与提前量秒数
                 （scheduler T4 表单；缺省 0/0 兼容历史调用）。
    """
    before = get_report(conn, report_id) if session_user else None
    cur = conn.execute(
        "UPDATE report_configs SET name=?,sql_query=?,default_page_size=?,pool_id=?,category_id=?,memo=?,result_names=?,prefer_cache=?,cache_ttl_hours=?,allow_write=?,allow_all_output=?,max_rows=?,keepalive_enabled=?,keepalive_ahead_seconds=? WHERE id=?",
        (name, sql_query, default_page_size, pool_id, category_id, memo, result_names or '', prefer_cache, cache_ttl_hours, allow_write, allow_all_output, max_rows, int(bool(keepalive_enabled)), int(keepalive_ahead_seconds), report_id),
    )
    conn.commit()
    _write_audit_log(session_user, "update_report", "report", report_id, name,
                     before_value=before,
                     after_value={"name": name, "sql_query": sql_query,
                                  "default_page_size": default_page_size,
                                  "pool_id": pool_id, "category_id": category_id,
                                  "memo": memo, "prefer_cache": prefer_cache,
                                  "cache_ttl_hours": cache_ttl_hours,
                                  "allow_write": allow_write,
                                  "allow_all_output": allow_all_output,
                                  "max_rows": max_rows,
                                  "keepalive_enabled": int(bool(keepalive_enabled)),
                                  "keepalive_ahead_seconds": int(keepalive_ahead_seconds)})
    return cur.rowcount > 0


def delete_report(conn, report_id: int, session_user=None) -> bool:
    """删除报表配置及其定时任务行与 API 端点（应用层级联），影响行数 >0 返回 True。

    批次2#5（spec ux-optimization）：对齐 batch_delete_reports 的级联语义——
    先经 delete_api_endpoints_by_report 清理 API 端点并失效其静态缓存，
    修复单删遗留孤儿端点导致 API 调用方 500 的缺陷。
    """
    before = get_report(conn, report_id) if session_user else None
    delete_api_endpoints_by_report(conn, report_id)
    delete_schedules_by_report(conn, report_id)
    cur = conn.execute("DELETE FROM report_configs WHERE id=?", (report_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_report", "report", report_id,
                     before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def move_report(conn, report_id: int, direction: str,
                category_id: int = None, session_user=None) -> bool:
    """
    调整报表排序（同一分类内交换）。direction 为 'up' 或 'down'。
    category_id: 可选，指定分类上下文；为 None 时从报表自身推断。
    与相邻项交换 sort_order，返回 True 表示移动成功。
    """
    # 如果没传 category_id，从报表本身推断
    if category_id is None:
        report = get_report(conn, report_id)
        if report is None:
            return False
        category_id = report.get("category_id")
    return _move_item(conn, lambda c: get_reports(c, category_id),
                      "report_configs", report_id, direction,
                      "move_report", "report", session_user)


def batch_update_report_pool(conn, report_ids: list[int], pool_id) -> int:
    """批量更新报表的连接池，返回更新的行数。"""
    placeholders = _placeholders(len(report_ids))
    cur = conn.execute(
        f"UPDATE report_configs SET pool_id=? WHERE id IN ({placeholders})",
        [pool_id] + report_ids,
    )
    conn.commit()
    return cur.rowcount


def batch_update_report_cache(
    conn,
    report_ids: list[int],
    prefer_cache,
    cache_ttl_hours,
) -> int:
    """
    批量更新报表的缓存配置（开关 + TTL），返回更新的行数。

    只更新 non-None 的字段，保留 None 字段的原值。
    """
    sets = []
    params = []
    if prefer_cache is not None:
        sets.append("prefer_cache=?")
        params.append(prefer_cache)
    if cache_ttl_hours is not None:
        sets.append("cache_ttl_hours=?")
        params.append(cache_ttl_hours)
    if not sets:
        return 0
    placeholders = _placeholders(len(report_ids))
    cur = conn.execute(
        f"UPDATE report_configs SET {','.join(sets)} WHERE id IN ({placeholders})",
        params + report_ids,
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# 报表层级（分类）CRUD
# ---------------------------------------------------------------------------


def add_category(conn, name: str, parent_id=None, session_user=None) -> int:
    """新增报表分类，返回自增 id。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM report_categories").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO report_categories (name, parent_id, sort_order) VALUES (?,?,?)",
        (name, parent_id, max_order + 1),
    )
    conn.commit()
    _write_audit_log(session_user, "create_category", "category", cur.lastrowid, name)
    return cur.lastrowid


def get_category(conn, category_id: int) -> Optional[dict]:
    """根据 id 查询分类，不存在返回 None。"""
    row = conn.execute("SELECT * FROM report_categories WHERE id=?", (category_id,)).fetchone()
    return dict(row) if row else None


def get_all_categories(conn) -> list[dict]:
    """返回所有分类列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM report_categories ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_category(conn, category_id: int, name: str, parent_id=None, session_user=None) -> bool:
    """更新分类名称和父分类，影响行数 >0 返回 True。"""
    before = get_category(conn, category_id) if session_user else None
    cur = conn.execute(
        "UPDATE report_categories SET name=?, parent_id=? WHERE id=?",
        (name, parent_id, category_id),
    )
    conn.commit()
    _write_audit_log(session_user, "update_category", "category", category_id, name,
                     before_value=before, after_value={"name": name, "parent_id": parent_id})
    return cur.rowcount > 0


def delete_category(conn, category_id: int, session_user=None) -> bool:
    """删除分类，关联报表的 category_id 置 NULL，子分类的 parent_id 置 NULL。"""
    before = get_category(conn, category_id) if session_user else None
    conn.execute("UPDATE report_configs SET category_id=NULL WHERE category_id=?", (category_id,))
    conn.execute("UPDATE report_categories SET parent_id=NULL WHERE parent_id=?", (category_id,))
    cur = conn.execute("DELETE FROM report_categories WHERE id=?", (category_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_category", "category", category_id,
                     before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def move_category(conn, category_id: int, direction: str, session_user=None) -> bool:
    """
    调整分类排序。direction 为 'up' 或 'down'。
    与相邻项交换 sort_order，返回 True 表示移动成功。

    限定在同父兄弟范围内移动（与渲染端 idx 计算一致）：多级分类下若在
    全局列表中取相邻项，父分类的相邻项往往是其子分类，交换后显示顺序不变。
    """
    cat = get_category(conn, category_id)
    if cat is None:
        return False
    pid = cat.get("parent_id")

    def _siblings(c):
        return [x for x in get_all_categories(c) if x.get("parent_id") == pid]

    return _move_item(conn, _siblings, "report_categories", category_id,
                      direction, "move_category", "category", session_user)


def get_reports_by_category(conn):
    """
    返回所有分类及其下的报表列表（仅直接归属，不含子分类的报表）。
    每个分类包含 reports 字段，未分类的报表另外返回。
    """
    categories = get_all_categories(conn)
    result = []
    for cat in categories:
        cat["reports"] = get_reports(conn, category_id=cat["id"])
        result.append(cat)
    unassigned = get_reports(conn, category_id=None)
    return result, unassigned


def get_reports(conn, category_id: int = None) -> list[dict]:
    """按分类查询报表列表（按 sort_order 排序）。"""
    if category_id is None:
        rows = conn.execute(
            "SELECT * FROM report_configs WHERE category_id IS NULL ORDER BY sort_order, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM report_configs WHERE category_id=? ORDER BY sort_order, id",
            (category_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def move_report_to_category(conn, report_id: int, category_id, session_user=None) -> bool:
    """将报表移动到指定分类（None 表示移出分类）。"""
    before = get_report(conn, report_id) if session_user else None
    cur = conn.execute(
        "UPDATE report_configs SET category_id=? WHERE id=?", (category_id, report_id)
    )
    conn.commit()
    _write_audit_log(session_user, "move_report_to_category", "report", report_id,
                     before.get("name") if before else None,
                     before_value={"category_id": before.get("category_id")} if before else None,
                     after_value={"category_id": category_id})
    return cur.rowcount > 0


def get_category_tree(conn) -> list[dict]:
    """
    返回分类树（按 sort_order 排序）。
    每个分类包含 children 列表，顶级分类（parent_id IS NULL）在顶层。
    """
    all_cats = get_all_categories(conn)
    # 建立 id->category 映射
    cat_map = {}
    for c in all_cats:
        c["children"] = []
        cat_map[c["id"]] = c
    # 挂载子分类
    roots = []
    for c in all_cats:
        pid = c.get("parent_id")
        if pid is not None and pid in cat_map:
            cat_map[pid]["children"].append(c)
        else:
            roots.append(c)
    return roots


def get_parent_categories(conn, category_id: int) -> list[dict]:
    """返回指定分类的所有祖先（从根到父），不包含自身。"""
    ancestors = []
    current = get_category(conn, category_id)
    seen = {category_id} if current else set()
    while current and current.get("parent_id") is not None:
        pid = current["parent_id"]
        if pid in seen:
            break
        seen.add(pid)
        parent = get_category(conn, pid)
        if parent:
            ancestors.insert(0, parent)
            current = parent
        else:
            break
    return ancestors


def batch_set_report_category(conn, report_ids: list[int], category_id) -> int:
    """批量设置报表分类，返回受影响行数。"""
    placeholders = _placeholders(len(report_ids))
    cur = conn.execute(
        f"UPDATE report_configs SET category_id=? WHERE id IN ({placeholders})",
        [category_id] + report_ids,
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def add_session(conn, token: str, username: str) -> None:
    """持久化一条 session 记录。"""
    conn.execute(
        "REPLACE INTO sessions (token, username, created_at) VALUES (?,?,?)",
        (token, username, time.time()),
    )
    conn.commit()


def get_session(conn, token: str) -> Optional[str]:
    """根据 token 查询用户名，不存在或已过期返回 None。"""
    # 用 current_timestamp 计算 24h 有效期
    row = conn.execute(
        "SELECT username FROM sessions WHERE token=? AND created_at > ?",
        (token, time.time() - 86400),
    ).fetchone()
    return row[0] if row else None


def remove_session(conn, token: str) -> bool:
    """删除一条 session，成功返回 True。"""
    cur = conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    return cur.rowcount > 0


def get_all_sessions(conn) -> list[dict]:
    """返回所有未过期的 session 记录。"""
    rows = conn.execute(
        "SELECT token, username, created_at FROM sessions WHERE created_at > ?",
        (time.time() - 86400,),
    ).fetchall()
    return [{"token": r[0], "username": r[1], "created_at": r[2]} for r in rows]


def clear_sessions(conn) -> None:
    """清空所有 session 记录。"""
    conn.execute("DELETE FROM sessions")
    conn.commit()


def delete_expired_sessions(conn) -> int:
    """删除所有已过期（超过 24 小时）的 session 记录，返回删除行数。"""
    cur = conn.execute("DELETE FROM sessions WHERE created_at <= ?",
                       (time.time() - 86400,))
    conn.commit()
    return cur.rowcount


def delete_sessions_for_user(conn, username: str) -> int:
    """删除指定用户名的全部 session 记录，返回删除行数。

    批次2#7（spec ux-optimization）：删除用户 / 修改密码后注销其登录态，
    需与 auth.remove_sessions_for_user 配对使用（内存 + 持久层同清）。
    """
    cur = conn.execute("DELETE FROM sessions WHERE username=?", (username,))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# API 端点 CRUD
# ---------------------------------------------------------------------------


def add_api_endpoint(conn, report_id: int, name: str, url_path: str,
                     output_format: str = 'json',
                     columns: str = None, filters: str = None,
                     sorts: str = None, row_limit: int = 0,
                     api_key: str = None,
                     allowed_origins: str = None,
                     enabled: int = 1,
                     result_mode: str = 'single',
                     result_index: int = 0,
                     allow_fetch_all: int = 1,
                     static_cache: int = 1,
                     json_no_quotes: int = 0,
                     smart_quote_flags: int = 0,
                     json_template: str = None,
                     description: str = None,
                     session_user=None) -> int:
    """
    新增 API 端点配置，返回自增 id。

    参数:
        report_id: 关联报表 ID
        name: 显示名称
        url_path: 自定义 URL 路径，必须以 /api/ 开头，全局唯一
        output_format: json 或 csv
        columns: 字段列表逗号分隔，None=全部字段
        filters: JSON 字符串，[{"col":"...","op":"...","val":"..."}, ...]
        sorts: JSON 字符串，[{"col":"...","dir":"..."}, ...]
        row_limit: 最大返回行数，0=不限制
        api_key: 鉴权密钥，None=无需鉴权
        allowed_origins: CORS 允许来源逗号分隔
        result_mode: 'single' 或 'all'
        result_index: 结果集索引（0-based），仅 result_mode='single' 时有效
        allow_fetch_all: 是否接受 fetch_all 全量获取参数，1=接受（默认），0=忽略
        static_cache: 是否启用静态文件缓存（.json 变体），1=开启（默认），0=关闭
        json_no_quotes: 值无引号（JSON 所有值不加引号），1=开启，0=关闭（默认）；
                        仅 JSON 格式生效，与报表导出 json_no_quotes 同语义；
                        弃用（被 smart_quote_flags 取代），保留兼容
        smart_quote_flags: 「智能去引号」复选面板位图：1=十进制数字（含正负号）、
                        2=科学计数法、4=千分位数字，0=标准 JSON（默认）；仅 JSON 格式生效
        json_template: JSON 输出模板文本（占位符语法），None/空=未启用
        description: 接口说明（多行文本，纯展示字段，不进入 API 输出），None=无说明
    """
    cur = conn.execute(
        """INSERT INTO api_endpoints
           (report_id, name, url_path, output_format, columns, filters,
            sorts, row_limit, api_key, allowed_origins, enabled,
            result_mode, result_index, allow_fetch_all, static_cache,
            json_no_quotes, smart_quote_flags, json_template, description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (report_id, name, url_path, output_format, columns, filters,
         sorts, row_limit, api_key, allowed_origins, enabled,
         result_mode, result_index, allow_fetch_all, static_cache,
         json_no_quotes, smart_quote_flags, json_template, description),
    )
    conn.commit()
    _write_audit_log(session_user, "create_api_endpoint", "api_endpoint",
                     cur.lastrowid, name,
                     after_value={"name": name, "url_path": url_path,
                                  "report_id": report_id, "output_format": output_format,
                                  "result_mode": result_mode, "result_index": result_index,
                                  "allow_fetch_all": allow_fetch_all,
                                  "static_cache": static_cache,
                                  "json_no_quotes": json_no_quotes,
                                  "smart_quote_flags": smart_quote_flags,
                                  "json_template": json_template})
    return cur.lastrowid


def get_api_endpoint(conn, endpoint_id: int) -> dict | None:
    """根据 id 查询 API 端点，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM api_endpoints WHERE id=?", (endpoint_id,)
    ).fetchone()
    return dict(row) if row else None


def get_api_endpoint_by_path(conn, url_path: str) -> dict | None:
    """根据 URL 路径查询 API 端点（仅已启用），不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM api_endpoints WHERE url_path=? AND enabled=1",
        (url_path,),
    ).fetchone()
    return dict(row) if row else None


def get_api_endpoints_by_report(conn, report_id: int) -> list[dict]:
    """根据报表 ID 查询该报表下的所有 API 端点列表。"""
    rows = conn.execute(
        "SELECT * FROM api_endpoints WHERE report_id=? ORDER BY id",
        (report_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_api_endpoints(conn) -> list[dict]:
    """返回所有 API 端点列表（含关联报表名）。"""
    rows = conn.execute("""
        SELECT ae.*, rc.name AS report_name
        FROM api_endpoints ae
        LEFT JOIN report_configs rc ON ae.report_id = rc.id
        ORDER BY ae.id
    """).fetchall()
    return [dict(r) for r in rows]


def count_api_endpoints_by_report(conn, report_ids: list[int]) -> dict[int, int]:
    """按报表 ID 列表聚合各报表的 API 端点数，返回 {report_id: 端点数}。

    批次2#5（spec ux-optimization）：单条 GROUP BY 查询供渲染层批量取数，
    避免逐报表查询造成 N+1。无端点的报表不出现在结果中，
    调用方用 .get(report_id, 0) 兜底；report_ids 为空时直接返回空 dict。
    """
    if not report_ids:
        return {}
    placeholders = _placeholders(len(report_ids))
    rows = conn.execute(
        f"SELECT report_id, COUNT(*) AS cnt FROM api_endpoints"
        f" WHERE report_id IN ({placeholders}) GROUP BY report_id",
        list(report_ids),
    ).fetchall()
    return {r["report_id"]: r["cnt"] for r in rows}


def _invalidate_api_static_cache(paths) -> None:
    """使指定 url_path 的静态缓存文件失效（删除文件，幂等）。"""
    for p in paths:
        if p:
            static_cache.invalidate(p)


def invalidate_api_static_cache_by_report(conn, report_id: int,
                                          endpoints: list = None) -> None:
    """使某报表下全部 API 端点的静态缓存文件失效（幂等，惰性重建）。

    endpoints 显式传入端点快照（如删除前取出的列表）时以快照为准，
    避免删除后查询为空导致漏失效。
    """
    if endpoints is None:
        endpoints = get_api_endpoints_by_report(conn, report_id)
    for ep in endpoints:
        _invalidate_api_static_cache([ep.get("url_path")])


def _invalidate_after_endpoint_update(before: dict | None, url_path) -> None:
    """API 端点配置变更后使静态缓存失效。

    任何字段变更（url_path/name/enabled/columns/filters/sorts/row_limit/
    output_format/api_key 等）都可能影响静态缓存内容，统一删除缓存文件：
    - url_path 变化 → 删除旧路径与新路径（旧文件成为孤儿，新路径可能残留）
    - 其他字段变更 → 删除当前路径缓存文件
    """
    if before is None:
        return
    old_path = before.get("url_path") or ""
    new_path = url_path if url_path is not _UNSET else old_path
    paths = set()
    if old_path:
        paths.add(old_path)
    if new_path:
        paths.add(new_path)
    _invalidate_api_static_cache(paths)


def _CACHE_AFFECTING_ENDPOINT_FIELDS() -> frozenset:
    """影响静态缓存输出内容的端点字段集合。

    静态缓存文件内容是"SQL 结果 + 端点变换规则"的产物，只有这些字段变更
    才需要删除缓存文件；纯元数据字段（如 description 接口说明）只影响页面
    展示，变更不应触发失效重建。
    """
    return frozenset((
        "name", "url_path", "output_format", "columns", "filters", "sorts",
        "row_limit", "api_key", "allowed_origins", "enabled",
        "result_mode", "result_index", "allow_fetch_all", "static_cache",
        "json_no_quotes", "smart_quote_flags", "json_template",
    ))


def update_api_endpoint(conn, endpoint_id: int,
                        name: str = _UNSET, url_path: str = _UNSET,
                        output_format: str = _UNSET,
                        columns: str = _UNSET, filters: str = _UNSET,
                        sorts: str = _UNSET, row_limit: int = _UNSET,
                        api_key: str = _UNSET,
                        allowed_origins: str = _UNSET,
                        enabled: int = _UNSET,
                        result_mode: str = _UNSET,
                        result_index: int = _UNSET,
                        allow_fetch_all: int = _UNSET,
                        static_cache: int = _UNSET,
                        json_no_quotes: int = _UNSET,
                        smart_quote_flags: int = _UNSET,
                        json_template: str = _UNSET,
                        description: str = _UNSET,
                        session_user=None) -> bool:
    """
    更新 API 端点配置。仅更新非 _UNSET 的字段，影响行数 >0 返回 True。

    使用 _UNSET 哨兵而非 None 作为默认值，使得调用方可以显式传入 None
    来表示"将此字段设为 NULL"。不传此参数则跳过更新。
    """
    before = get_api_endpoint(conn, endpoint_id)
    sets = []
    params = []
    if name is not _UNSET:
        sets.append("name=?")
        params.append(name)
    if url_path is not _UNSET:
        sets.append("url_path=?")
        params.append(url_path)
    if output_format is not _UNSET:
        sets.append("output_format=?")
        params.append(output_format)
    if columns is not _UNSET:
        sets.append("columns=?")
        params.append(columns)
    if filters is not _UNSET:
        sets.append("filters=?")
        params.append(filters)
    if sorts is not _UNSET:
        sets.append("sorts=?")
        params.append(sorts)
    if row_limit is not _UNSET:
        sets.append("row_limit=?")
        params.append(row_limit)
    if api_key is not _UNSET:
        sets.append("api_key=?")
        params.append(api_key)
    if allowed_origins is not _UNSET:
        sets.append("allowed_origins=?")
        params.append(allowed_origins)
    if enabled is not _UNSET:
        sets.append("enabled=?")
        params.append(enabled)
    if result_mode is not _UNSET:
        sets.append("result_mode=?")
        params.append(result_mode)
    if result_index is not _UNSET:
        sets.append("result_index=?")
        params.append(result_index)
    if allow_fetch_all is not _UNSET:
        sets.append("allow_fetch_all=?")
        params.append(allow_fetch_all)
    if static_cache is not _UNSET:
        sets.append("static_cache=?")
        params.append(static_cache)
    if json_no_quotes is not _UNSET:
        sets.append("json_no_quotes=?")
        params.append(json_no_quotes)
    if smart_quote_flags is not _UNSET:
        sets.append("smart_quote_flags=?")
        params.append(smart_quote_flags)
    if json_template is not _UNSET:
        sets.append("json_template=?")
        params.append(json_template)
    if description is not _UNSET:
        sets.append("description=?")
        params.append(description)
    if not sets:
        return False
    engine = _get_engine()
    if engine != "mysql":
        sets.append("updated_at=datetime('now','localtime')")
    params.append(endpoint_id)
    cur = conn.execute(
        f"UPDATE api_endpoints SET {','.join(sets)} WHERE id=?",
        params,
    )
    conn.commit()
    # 仅输出影响字段变更才使静态缓存失效；纯元数据字段（description）跳过
    fields_changed = {s.split("=")[0] for s in sets if not s.startswith("updated_at")}
    if cur.rowcount > 0 and fields_changed & _CACHE_AFFECTING_ENDPOINT_FIELDS():
        _invalidate_after_endpoint_update(before, url_path)
    entity_name = name if name is not _UNSET else (before or {}).get("name")
    after = get_api_endpoint(conn, endpoint_id)
    _write_audit_log(session_user, "update_api_endpoint", "api_endpoint",
                     endpoint_id, entity_name,
                     before_value=before,
                     after_value=after)
    return cur.rowcount > 0


def delete_api_endpoint(conn, endpoint_id: int, session_user=None) -> bool:
    """删除 API 端点，影响行数 >0 返回 True。"""
    before = get_api_endpoint(conn, endpoint_id)
    cur = conn.execute("DELETE FROM api_endpoints WHERE id=?", (endpoint_id,))
    conn.commit()
    if cur.rowcount > 0:
        _invalidate_api_static_cache({before.get("url_path")} if before else set())
    _write_audit_log(session_user, "delete_api_endpoint", "api_endpoint",
                     endpoint_id, before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# API Key 多 key 化 CRUD（PH-02）
# ---------------------------------------------------------------------------


def get_api_key(conn, key_id: int) -> dict | None:
    """根据 id 查询 API Key，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM api_keys WHERE id=?", (key_id,)
    ).fetchone()
    return dict(row) if row else None


def list_api_keys(conn, endpoint_id: int) -> list[dict]:
    """列出某端点的全部 API Key（按创建顺序）。"""
    rows = conn.execute(
        "SELECT * FROM api_keys WHERE endpoint_id=? ORDER BY id",
        (endpoint_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_api_key_counts(conn) -> dict[int, int]:
    """按端点统计 API Key 数量（列表页徽标用）。"""
    rows = conn.execute(
        "SELECT endpoint_id, COUNT(*) AS c FROM api_keys GROUP BY endpoint_id"
    ).fetchall()
    return {r["endpoint_id"]: r["c"] for r in rows}


def add_api_key(conn, endpoint_id: int, name: str, key: str,
                session_user=None) -> int:
    """新增 API Key（enabled=1），返回自增 id。"""
    cur = conn.execute(
        "INSERT INTO api_keys (endpoint_id, name, api_key, enabled) "
        "VALUES (?,?,?,1)",
        (endpoint_id, name, key),
    )
    conn.commit()
    _write_audit_log(session_user, "create_api_key", "api_key", cur.lastrowid, name,
                     after_value={"endpoint_id": endpoint_id, "name": name})
    return cur.lastrowid


def delete_api_key(conn, key_id: int, session_user=None) -> bool:
    """删除 API Key，影响行数 >0 返回 True。"""
    before = get_api_key(conn, key_id)
    cur = conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_api_key", "api_key", key_id,
                     before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def set_api_key_enabled(conn, key_id: int, enabled: int,
                        session_user=None) -> bool:
    """启用/禁用 API Key，影响行数 >0 返回 True。"""
    before = get_api_key(conn, key_id)
    cur = conn.execute("UPDATE api_keys SET enabled=? WHERE id=?",
                       (1 if enabled else 0, key_id))
    conn.commit()
    _write_audit_log(session_user, "update_api_key", "api_key", key_id,
                     before.get("name") if before else None,
                     before_value=before, after_value=get_api_key(conn, key_id))
    return cur.rowcount > 0


def delete_api_endpoints_by_report(conn, report_id: int, session_user=None) -> int:
    """删除某报表下的所有 API 端点，返回删除行数。"""
    before_list = [dict(ep) for ep in get_api_endpoints_by_report(conn, report_id)]
    cur = conn.execute(
        "DELETE FROM api_endpoints WHERE report_id=?", (report_id,)
    )
    conn.commit()
    if cur.rowcount > 0:
        invalidate_api_static_cache_by_report(conn, report_id, endpoints=before_list)
    _write_audit_log(session_user, "delete_api_endpoints_by_report", "api_endpoint",
                     entity_name=f"report_id={report_id}",
                     before_value=before_list if before_list else None)
    return cur.rowcount


def batch_delete_reports(conn, report_ids: list[int], session_user=None) -> int:
    """批量删除报表及其 API 端点，返回删除的报表数。

    级联删除报表下全部 API 端点并失效其静态缓存文件（删除即失效，惰性重建）；
    审计按报表逐条记录（与 delete_report 语义一致）。
    """
    if not report_ids:
        return 0
    placeholders = _placeholders(len(report_ids))
    rows = conn.execute(
        f"SELECT id, name FROM report_configs WHERE id IN ({placeholders})",
        report_ids,
    ).fetchall()
    affected = 0
    for row in rows:
        rid = row["id"]
        endpoints = get_api_endpoints_by_report(conn, rid)
        if endpoints:
            conn.execute("DELETE FROM api_endpoints WHERE report_id=?", (rid,))
            invalidate_api_static_cache_by_report(conn, rid, endpoints=endpoints)
        delete_schedules_by_report(conn, rid)
        cur = conn.execute("DELETE FROM report_configs WHERE id=?", (rid,))
        if cur.rowcount > 0:
            affected += 1
            _write_audit_log(session_user, "delete_report", "report", rid,
                             row["name"], before_value=dict(row))
    conn.commit()
    return affected


# ---------------------------------------------------------------------------
# 定时任务 CRUD（report_schedules，迁移 16）
# ---------------------------------------------------------------------------

_SCHEDULE_TYPES = ("interval", "daily")
_MISFIRE_POLICIES = ("skip", "run_once")


def _validate_schedule_fields(schedule_type: str, interval_minutes: int,
                              daily_time: str, misfire_policy: str) -> None:
    """校验定时任务字段合法性，非法值抛 ValueError。

    schedule_type ∈ {interval, daily}；misfire_policy ∈ {skip, run_once}；
    interval_minutes ≥ 1；daily_time 必须为 HH:MM（00:00-23:59）。
    """
    if schedule_type not in _SCHEDULE_TYPES:
        raise ValueError(f"非法调度类型: {schedule_type}")
    if misfire_policy not in _MISFIRE_POLICIES:
        raise ValueError(f"非法 misfire 策略: {misfire_policy}")
    if int(interval_minutes) < 1:
        raise ValueError("interval_minutes 必须 ≥ 1")
    parts = str(daily_time).split(":")
    if (len(parts) != 2 or not all(p.isdigit() for p in parts)
            or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59)):
        raise ValueError(f"非法每日时刻: {daily_time}")


def _dump_exclusions(exclusions) -> Optional[str]:
    """把排除规则树规整为可存储的 JSON 文本；空值返回 None。"""
    if exclusions is None:
        return None
    if isinstance(exclusions, str):
        s = exclusions.strip()
        return s or None
    return json.dumps(exclusions, ensure_ascii=False)


def _sync_schedule_reports(conn, schedule_id: int, report_ids: list,
                           binding_enabled: dict = None) -> None:
    """重写任务与报表的绑定（按 order_index 顺序；保留绑定级 enabled）。

    纯 DELETE+INSERT（两引擎通用 SQL）：INSERT OR REPLACE 是 SQLite 方言，
    MySQL 下语法错误（ADR-0002 禁 CRUD 层引擎分支）；重复 report_id 在
    Python 层保序去重，避免 (schedule_id, report_id) 主键冲突。

    binding_enabled（dict report_id→enabled，UI 显式传入）优先；未给出的
    绑定从既有行保留原 enabled（S10：保存任务不得丢失手工维护的绑定启停）。
    """
    existing = {}
    if not binding_enabled:
        for r in conn.execute(
                "SELECT report_id, enabled FROM schedule_reports "
                "WHERE schedule_id=?", (schedule_id,)).fetchall():
            existing[int(r[0])] = int(r[1])
    conn.execute("DELETE FROM schedule_reports WHERE schedule_id=?",
                 (schedule_id,))
    seen = dict.fromkeys(int(rid) for rid in report_ids)
    for idx, rid in enumerate(seen):
        if binding_enabled:
            enabled = int(bool(binding_enabled.get(rid, 1)))
        else:
            enabled = existing.get(rid, 1)
        conn.execute(
            "INSERT INTO schedule_reports "
            "(schedule_id, report_id, order_index, enabled) VALUES (?,?,?,?)",
            (schedule_id, rid, idx, enabled))


def upsert_schedule(conn, name: str = "", schedule_type: str = "interval",
                    interval_minutes: int = 60, daily_time: str = "08:00",
                    misfire_policy: str = "skip", enabled: int = 1,
                    report_ids: list = None, report_id: int = None,
                    exclusions=None, audit_enabled: int = 0,
                    next_run_at=None, session_user=None,
                    schedule_id: int = None,
                    binding_enabled: dict = None) -> int:
    """创建或更新定时任务（任务为独立实体，可绑定多张报表）。返回任务 id。

    schedule_id 显式给定时按 id 精确更新（管理页编辑路径，支持改名，
    不存在抛 ValueError）；否则视为创建：name 与既有任务重名 → 抛
    ValueError（按名字顶替更新是数据事故源，2026-08-23 审查移除该隐式
    定位）。无名创建按首报表现有绑定定位更新（兼容旧报表编辑页「定时
    执行」折叠区对既有任务的二次保存）。report_ids 为有序报表 id 列表
    （写入 schedule_reports，按 order_index 顺序执行）；旧式单报表入参
    report_id 仍兼容，等价于 report_ids=[report_id]。binding_enabled 为
    绑定级启停映射（report_id→0/1，S10）：显式给出时按此落库，未给出
    的绑定保留既有 enabled；None 时全部保留既有状态。变更调度参数时由
    调用方负责重算并传入 next_run_at（None 表示待排程，调度器启动扫描
    会兜底推进）。
    """
    _validate_schedule_fields(schedule_type, interval_minutes, daily_time,
                              misfire_policy)
    if not report_ids:
        report_ids = [report_id] if report_id is not None else []
    if not report_ids:
        raise ValueError("定时任务至少需要绑定一个报表")
    # 保序去重：重复勾选同一报表会导致主键冲突
    report_ids = list(dict.fromkeys(int(r) for r in report_ids))
    name = (name or "").strip()
    before = None
    existing = None
    if schedule_id is not None:
        existing = get_schedule(conn, schedule_id)
        if existing is None:
            raise ValueError(f"定时任务 #{schedule_id} 不存在")
    elif not name:
        # 无名任务：按首报表现有绑定定位（旧报表编辑页折叠区兼容路径）
        existing = conn.execute(
            "SELECT schedule_id FROM schedule_reports WHERE report_id=? "
            "LIMIT 1", (report_ids[0],)).fetchone()
    sid = None
    if existing is not None:
        if schedule_id is not None:
            sid = schedule_id
        elif isinstance(existing, dict):
            sid = existing["id"]
        else:
            sid = existing[0]
        # 重名校验（排除自身）：改名撞上其他任务名 → 拒绝，防错位更新
        dup = conn.execute(
            "SELECT id FROM report_schedules WHERE name=? AND id<>?",
            (name, sid)).fetchone() if name else None
        if dup is not None:
            raise ValueError(f"任务名「{name}」已被任务 #{dup[0]} 使用")
        if session_user:
            before = get_schedule(conn, sid)
        conn.execute(
            "UPDATE report_schedules SET name=?, schedule_type=?, "
            "interval_minutes=?, daily_time=?, misfire_policy=?, enabled=?, "
            "exclusions=?, audit_enabled=?, next_run_at=?, updated_at=? "
            "WHERE id=?",
            (name, schedule_type, int(interval_minutes), str(daily_time),
             misfire_policy, int(bool(enabled)), _dump_exclusions(exclusions),
             int(bool(audit_enabled)), next_run_at,
             time.strftime("%Y-%m-%d %H:%M:%S"), sid))
        action = "update_schedule"
        _sync_schedule_reports(conn, sid, report_ids, binding_enabled)
    else:
        if name:
            dup = conn.execute(
                "SELECT id FROM report_schedules WHERE name=?",
                (name,)).fetchone()
            if dup is not None:
                raise ValueError(f"任务名「{name}」已存在（任务 #{dup[0]}），"
                                 f"请换名或编辑既有任务")
        cur = conn.execute(
            "INSERT INTO report_schedules "
            "(name, schedule_type, interval_minutes, daily_time, misfire_policy, "
            "enabled, exclusions, audit_enabled, next_run_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (name, schedule_type, int(interval_minutes), str(daily_time),
             misfire_policy, int(bool(enabled)), _dump_exclusions(exclusions),
             int(bool(audit_enabled)), next_run_at))
        sid = cur.lastrowid
        action = "create_schedule"
        _sync_schedule_reports(conn, sid, report_ids, binding_enabled)
    conn.commit()
    _write_audit_log(session_user, action, "schedule", sid,
                     name or f"report#{report_ids[0]}",
                     before_value=before,
                     after_value={"name": name,
                                  "report_ids": list(report_ids),
                                  "schedule_type": schedule_type,
                                  "interval_minutes": int(interval_minutes),
                                  "daily_time": str(daily_time),
                                  "misfire_policy": misfire_policy,
                                  "enabled": int(bool(enabled)),
                                  "exclusions": exclusions,
                                  "audit_enabled": int(bool(audit_enabled)),
                                  "next_run_at": next_run_at})
    return sid


def get_schedule_by_report(conn, report_id: int) -> Optional[dict]:
    """按报表查询其所属（首个）定时任务，不存在返回 None。

    多对多下一张报表可出现在多个任务中，本函数取首个匹配，供旧报表编辑页
    「定时执行」折叠区回显（T5 迁移到独立任务管理页后弃用）。
    """
    row = conn.execute(
        "SELECT s.* FROM report_schedules s "
        "JOIN schedule_reports sr ON sr.schedule_id=s.id "
        "WHERE sr.report_id=? LIMIT 1", (report_id,)).fetchone()
    return dict(row) if row else None


def get_schedule_reports(conn, schedule_id: int) -> list[dict]:
    """返回任务绑定的报表列表（按 order_index 升序），含 report_name。"""
    rows = conn.execute(
        "SELECT sr.*, r.name AS report_name FROM schedule_reports sr "
        "LEFT JOIN report_configs r ON r.id=sr.report_id "
        "WHERE sr.schedule_id=? ORDER BY sr.order_index, sr.report_id",
        (schedule_id,)).fetchall()
    return [dict(r) for r in rows]


def get_schedule(conn, schedule_id: int) -> Optional[dict]:
    """按任务 id 查询定时任务，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM report_schedules WHERE id=?", (schedule_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_schedules(conn) -> list[dict]:
    """返回全部定时任务（按下次执行时间升序，未排程靠后）。

    附带 report_ids / report_names 列表（任务可绑定多报表），供
    /config/scheduler 管理页与列表徽标使用。
    """
    rows = conn.execute(
        "SELECT * FROM report_schedules "
        "ORDER BY (next_run_at IS NULL), next_run_at, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        reps = get_schedule_reports(conn, d["id"])
        d["report_ids"] = [x["report_id"] for x in reps]
        d["report_names"] = [x.get("report_name") for x in reps]
        out.append(d)
    return out


def get_due_schedules(conn, now: float) -> list[dict]:
    """返回已到期且可执行的启用任务（next_run_at ≤ now 且 fail_count < 5）。"""
    rows = conn.execute(
        "SELECT * FROM report_schedules WHERE enabled=1 AND fail_count<5 "
        "AND next_run_at IS NOT NULL AND next_run_at<=?",
        (now,)).fetchall()
    return [dict(r) for r in rows]


def mark_schedule_result(conn, schedule_id: int, status: str,
                         error: str = None, next_run_at=None,
                         last_run_at: float = None,
                         last_duration_ms: int = None) -> None:
    """记录一次执行结果并推进下次执行时间。

    status ∈ {success, fail, skipped}：success 重置 fail_count 与 last_error；
    fail 递增 fail_count 并记录错误摘要；skipped（静默窗口命中）只推进
    next_run_at 与 last_run_at，fail_count 与 last_error 保持不变。
    last_run_at/next_run_at 为 epoch 秒；last_duration_ms 为本次执行耗时。
    """
    if status not in ("success", "fail", "skipped"):
        raise ValueError(f"非法执行状态: {status}")
    # updated_at 用 Python 本地时间参数化：SQLite 方言 datetime('now',...)
    # 在 MySQL 引擎下是语法错误（2026-08-21 事故根因），两引擎通用字符串
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    if status == "success":
        conn.execute(
            "UPDATE report_schedules SET last_status='success', last_error=NULL, "
            "fail_count=0, last_run_at=?, next_run_at=?, last_duration_ms=?, "
            "updated_at=? WHERE id=?",
            (last_run_at, next_run_at, last_duration_ms, now_str, schedule_id))
    elif status == "skipped":
        conn.execute(
            "UPDATE report_schedules SET last_status='skipped', last_error=NULL, "
            "last_run_at=?, next_run_at=?, last_duration_ms=?, updated_at=? "
            "WHERE id=?",
            (last_run_at, next_run_at, last_duration_ms, now_str, schedule_id))
    else:
        summary = (error or "")[:500]
        conn.execute(
            "UPDATE report_schedules SET last_status='fail', last_error=?, "
            "fail_count=fail_count+1, last_run_at=?, next_run_at=?, "
            "last_duration_ms=?, updated_at=? WHERE id=?",
            (summary, last_run_at, next_run_at, last_duration_ms, now_str,
             schedule_id))
    conn.commit()


def set_schedule_enabled(conn, schedule_id: int, enabled: int,
                         session_user=None) -> bool:
    """切换任务启停（不影响执行状态字段），影响行数 >0 返回 True。"""
    before = get_schedule(conn, schedule_id) if session_user else None
    # updated_at 用 Python 本地时间参数化：SQLite 方言 datetime('now',...)
    # 在 MySQL 引擎下是语法错误（2026-08-21 事故同源，本处为修复遗漏），
    # 两引擎通用字符串。
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "UPDATE report_schedules SET enabled=?, updated_at=? WHERE id=?",
        (int(bool(enabled)), now_str, schedule_id))
    conn.commit()
    _write_audit_log(session_user, "toggle_schedule", "schedule", schedule_id,
                     before.get("name") if before else None,
                     before_value=before,
                     after_value={"enabled": int(bool(enabled))})
    return cur.rowcount > 0


def delete_schedule(conn, schedule_id: int, session_user=None) -> bool:
    """删除定时任务（级联清理 schedule_reports 绑定），影响行数 >0 返回 True。"""
    before = get_schedule(conn, schedule_id) if session_user else None
    conn.execute("DELETE FROM schedule_reports WHERE schedule_id=?",
                 (schedule_id,))
    cur = conn.execute("DELETE FROM report_schedules WHERE id=?", (schedule_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_schedule", "schedule", schedule_id,
                     before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def _report_schedules_table_exists(conn) -> bool:
    """探测 report_schedules 表是否存在（兼容 SQLite / MySQL / 测试 mock）。

    先按 SQLite sqlite_master 探测；表不存在或查询失败（非 SQLite 引擎）
    再降级 SHOW TABLES。均不可判定时视为不存在，调用方跳过级联清理。
    """
    try:
        if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='report_schedules'").fetchone() is not None:
            return True
        return False
    except Exception:
        pass
    try:
        return conn.execute(
            "SHOW TABLES LIKE 'report_schedules'").fetchone() is not None
    except Exception:
        return False


def delete_schedules_by_report(conn, report_id: int) -> None:
    """删除某报表的定时任务绑定（应用层级联，幂等）。

    仅拆该报表的绑定；若某任务因此无任何绑定（孤儿任务），连带删除该任务。
    report_schedules 表不存在时静默跳过（兼容迁移 16 之前的存量库
    与手工建表的测试内存库）。不自行 commit/rollback——事务边界由
    调用方统一控制，避免误伤同事务中其他已执行的变更。
    """
    if not _report_schedules_table_exists(conn):
        return
    conn.execute("DELETE FROM schedule_reports WHERE report_id=?", (report_id,))
    # 清理无任何绑定的孤儿任务
    conn.execute(
        "DELETE FROM report_schedules WHERE id IN ("
        "SELECT s.id FROM report_schedules s "
        "LEFT JOIN schedule_reports sr ON sr.schedule_id=s.id "
        "WHERE sr.schedule_id IS NULL)")
