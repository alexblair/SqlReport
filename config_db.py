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
import sqlite3
import time
from typing import Optional

from app_config import get_active_db_config as _get_active_db_config


# 哨兵对象，用于区分"未传此参数"和"传了 None（设为 NULL）"
_UNSET = object()


# ---------------------------------------------------------------------------
# 审计日志辅助
# ---------------------------------------------------------------------------


def _write_audit_log(session_user, action, entity_type,
                     entity_id=None, entity_name=None,
                     before_value=None, after_value=None):
    """如果 session_user 不为 None，写入一条 operation 类型审计日志到 audit.db。

    异常被静默吞掉，避免审计失败影响业务操作。
    """
    if session_user is None:
        return
    from audit_db import get_audit_db, insert_audit_log
    try:
        audit_conn = get_audit_db()
        try:
            insert_audit_log(
                audit_conn,
                type="operation",
                session_user=session_user,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                before_value=before_value,
                after_value=after_value,
            )
        finally:
            audit_conn.close()
    except Exception:
        pass


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
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
    );
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
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
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


def move_pool(conn, pool_id: int, direction: str, session_user=None) -> bool:
    """
    调整连接池排序。direction 为 'up' 或 'down'。
    与相邻项交换 sort_order，返回 True 表示移动成功。
    """
    pools = get_all_pools(conn)
    idx = None
    for i, p in enumerate(pools):
        if p["id"] == pool_id:
            idx = i
            break
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        swap_idx = idx - 1
    elif direction == "down" and idx < len(pools) - 1:
        swap_idx = idx + 1
    else:
        return False
    swap_id = pools[swap_idx]["id"]
    so_a = pools[idx]["sort_order"] or idx
    so_b = pools[swap_idx]["sort_order"] or swap_idx
    conn.execute("UPDATE connection_pools SET sort_order=? WHERE id=?", (so_b, pool_id))
    conn.execute("UPDATE connection_pools SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    _write_audit_log(session_user, "move_pool", "pool", pool_id,
                     pools[idx].get("name"))
    return True


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
               session_user=None) -> int:
    """新增报表配置，返回自增 id。自动分配 sort_order。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM report_configs").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,category_id,memo,result_names,prefer_cache,cache_ttl_hours,sort_order) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (name, sql_query, default_page_size, pool_id, category_id, memo, result_names or '', prefer_cache, cache_ttl_hours, max_order + 1),
    )
    conn.commit()
    _write_audit_log(session_user, "create_report", "report", cur.lastrowid, name,
                     after_value={"name": name, "sql_query": sql_query,
                                  "default_page_size": default_page_size,
                                  "pool_id": pool_id, "category_id": category_id,
                                  "memo": memo, "prefer_cache": prefer_cache,
                                  "cache_ttl_hours": cache_ttl_hours})
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
                  session_user=None) -> bool:
    """更新报表配置，影响行数 >0 返回 True。"""
    before = get_report(conn, report_id) if session_user else None
    cur = conn.execute(
        "UPDATE report_configs SET name=?,sql_query=?,default_page_size=?,pool_id=?,category_id=?,memo=?,result_names=?,prefer_cache=?,cache_ttl_hours=? WHERE id=?",
        (name, sql_query, default_page_size, pool_id, category_id, memo, result_names or '', prefer_cache, cache_ttl_hours, report_id),
    )
    conn.commit()
    _write_audit_log(session_user, "update_report", "report", report_id, name,
                     before_value=before,
                     after_value={"name": name, "sql_query": sql_query,
                                  "default_page_size": default_page_size,
                                  "pool_id": pool_id, "category_id": category_id,
                                  "memo": memo, "prefer_cache": prefer_cache,
                                  "cache_ttl_hours": cache_ttl_hours})
    return cur.rowcount > 0


def delete_report(conn, report_id: int, session_user=None) -> bool:
    """删除报表配置，影响行数 >0 返回 True。"""
    before = get_report(conn, report_id) if session_user else None
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
    reports = get_reports(conn, category_id)
    idx = next((i for i, r in enumerate(reports) if r["id"] == report_id), None)
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        swap_idx = idx - 1
    elif direction == "down" and idx < len(reports) - 1:
        swap_idx = idx + 1
    else:
        return False
    swap_id = reports[swap_idx]["id"]
    so_a = reports[idx]["sort_order"] or idx
    so_b = reports[swap_idx]["sort_order"] or swap_idx
    conn.execute("UPDATE report_configs SET sort_order=? WHERE id=?", (so_b, report_id))
    conn.execute("UPDATE report_configs SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    _write_audit_log(session_user, "move_report", "report", report_id,
                     reports[idx].get("name"))
    return True


def batch_update_report_pool(conn, report_ids: list[int], pool_id) -> int:
    """批量更新报表的连接池，返回更新的行数。"""
    placeholders = ",".join("?" for _ in report_ids)
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
    placeholders = ",".join("?" for _ in report_ids)
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
    """
    cats = get_all_categories(conn)
    idx = next((i for i, c in enumerate(cats) if c["id"] == category_id), None)
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        swap_idx = idx - 1
    elif direction == "down" and idx < len(cats) - 1:
        swap_idx = idx + 1
    else:
        return False
    swap_id = cats[swap_idx]["id"]
    so_a = cats[idx]["sort_order"] or idx
    so_b = cats[swap_idx]["sort_order"] or swap_idx
    conn.execute("UPDATE report_categories SET sort_order=? WHERE id=?", (so_b, category_id))
    conn.execute("UPDATE report_categories SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    _write_audit_log(session_user, "move_category", "category", category_id,
                     cats[idx].get("name"))
    return True


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
    seen = set()
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
    placeholders = ",".join("?" for _ in report_ids)
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
    """
    cur = conn.execute(
        """INSERT INTO api_endpoints
           (report_id, name, url_path, output_format, columns, filters,
            sorts, row_limit, api_key, allowed_origins, enabled,
            result_mode, result_index)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (report_id, name, url_path, output_format, columns, filters,
         sorts, row_limit, api_key, allowed_origins, enabled,
         result_mode, result_index),
    )
    conn.commit()
    _write_audit_log(session_user, "create_api_endpoint", "api_endpoint",
                     cur.lastrowid, name,
                     after_value={"name": name, "url_path": url_path,
                                  "report_id": report_id, "output_format": output_format,
                                  "result_mode": result_mode, "result_index": result_index})
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
                        session_user=None) -> bool:
    """
    更新 API 端点配置。仅更新非 _UNSET 的字段，影响行数 >0 返回 True。

    使用 _UNSET 哨兵而非 None 作为默认值，使得调用方可以显式传入 None
    来表示"将此字段设为 NULL"。不传此参数则跳过更新。
    """
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
    entity_name = name if name is not _UNSET else (get_api_endpoint(conn, endpoint_id) or {}).get("name")
    _write_audit_log(session_user, "update_api_endpoint", "api_endpoint",
                     endpoint_id, entity_name)
    return cur.rowcount > 0


def delete_api_endpoint(conn, endpoint_id: int, session_user=None) -> bool:
    """删除 API 端点，影响行数 >0 返回 True。"""
    before = get_api_endpoint(conn, endpoint_id) if session_user else None
    cur = conn.execute("DELETE FROM api_endpoints WHERE id=?", (endpoint_id,))
    conn.commit()
    _write_audit_log(session_user, "delete_api_endpoint", "api_endpoint",
                     endpoint_id, before.get("name") if before else None,
                     before_value=before)
    return cur.rowcount > 0


def delete_api_endpoints_by_report(conn, report_id: int, session_user=None) -> int:
    """删除某报表下的所有 API 端点，返回删除行数。"""
    before_list = []
    if session_user:
        for ep in get_api_endpoints_by_report(conn, report_id):
            before_list.append(dict(ep))
    cur = conn.execute(
        "DELETE FROM api_endpoints WHERE report_id=?", (report_id,)
    )
    conn.commit()
    _write_audit_log(session_user, "delete_api_endpoints_by_report", "api_endpoint",
                     entity_name=f"report_id={report_id}",
                     before_value=before_list if before_list else None)
    return cur.rowcount
