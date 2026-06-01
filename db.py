"""
db.py — 数据库层

职责：
1. SQLite 存储配置数据（连接池、用户、报表配置）
2. MySQL 连接管理（从配置池创建连接执行查询）

设计原则：
- 所有函数显式接收 db 连接参数（依赖注入），方便测试 mock
- 每请求创建独立 SQLite 连接，避免线程安全问题
- MySQL 连接按需创建，不维护长连接池（精简）
"""

import os
import sqlite3

import time
from typing import Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CONFIG_DB = os.environ.get("CONFIG_DB", "config.db")

# ---------------------------------------------------------------------------
# SQLite 初始化
# ---------------------------------------------------------------------------


def get_config_db() -> sqlite3.Connection:
    """创建并返回一个新的 SQLite 连接（每请求使用独立连接，线程安全）。

    设置 timeout=10 秒等待锁释放，避免并发/网络文件系统上出现
    "database is locked" 错误。如果设置 WAL 模式失败（例如数据库
    被锁定），静默降级为 DELETE 日志模式，不影响正常使用。
    """
    conn = sqlite3.connect(CONFIG_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # 无法获取写锁设置 WAL，降级使用默认 journal 模式
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    初始化数据库表结构。

    每次调用都会执行 CREATE TABLE IF NOT EXISTS（幂等），
    并运行必要的迁移检查，确保新列/新表在旧数据库上也被创建。
    """
    conn.executescript("""
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
            sort_order         INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            username   TEXT NOT NULL,
            created_at REAL NOT NULL
        );
    """)
    conn.commit()

    # 迁移 1: report_configs 旧版 NOT NULL + CASCADE → 新版
    cursor = conn.execute("PRAGMA table_info(report_configs)")
    col_info = {}
    for row in cursor.fetchall():
        # PRAGMA table_info 返回: (cid, name, type, notnull, dflt_value, pk)
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

    # 迁移 2: 添加 category_id 列（旧库没有该列）
    if "category_id" not in col_info:
        try:
            conn.execute("ALTER TABLE report_configs ADD COLUMN category_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()  # 列已存在，忽略

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
        except sqlite3.OperationalError:
            conn.rollback()

    # 迁移 5: 清理重复的 report_categories 表（迁移3可能创建了不带 parent_id 的旧表结构）
    # 如果已经存在，上面 ALTER TABLE 已经处理；无需额外操作


# ---------------------------------------------------------------------------
# 连接池 CRUD
# ---------------------------------------------------------------------------

def add_pool(conn: sqlite3.Connection, name: str, host: str, port: int,
             user: str, password: str, database: str) -> int:
    """新增一个 MySQL 连接池配置，返回自增 id。自动分配 sort_order。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM connection_pools").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) VALUES (?,?,?,?,?,?,?)",
        (name, host, port, user, password, database, max_order + 1),
    )
    conn.commit()
    return cur.lastrowid


def get_pool(conn: sqlite3.Connection, pool_id: Optional[int]) -> Optional[dict]:
    """根据 id 查询单个连接池配置，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM connection_pools WHERE id=?", (pool_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_pools(conn: sqlite3.Connection) -> list[dict]:
    """返回所有连接池配置列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM connection_pools ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_pool(conn: sqlite3.Connection, pool_id: int, name: str, host: str,
                port: int, user: str, password: str, database: str) -> bool:
    """更新连接池配置，影响行数 >0 返回 True。"""
    cur = conn.execute(
        "UPDATE connection_pools SET name=?,host=?,port=?,user=?,password=?,database=? WHERE id=?",
        (name, host, port, user, password, database, pool_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_pool(conn: sqlite3.Connection, pool_id: int) -> bool:
    """
    删除连接池配置。

    先将关联报表的 pool_id 置空（断开外键关联，保留报表），再删除连接池。
    返回 True 表示删除成功。
    """
    # 先断开报表关联（report_configs 表可能不存在于测试环境）
    try:
        conn.execute("UPDATE report_configs SET pool_id = NULL WHERE pool_id = ?", (pool_id,))
    except sqlite3.OperationalError:
        pass
    cur = conn.execute("DELETE FROM connection_pools WHERE id=?", (pool_id,))
    conn.commit()
    return cur.rowcount > 0


def move_pool(conn: sqlite3.Connection, pool_id: int, direction: str) -> bool:
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
        swap_id = pools[idx - 1]["id"]
    elif direction == "down" and idx < len(pools) - 1:
        swap_id = pools[idx + 1]["id"]
    else:
        return False
    so_a = pools[idx]["sort_order"] or idx
    so_b = pools[swap_id]["sort_order"] or (idx + (1 if direction == "up" else -1))
    conn.execute("UPDATE connection_pools SET sort_order=? WHERE id=?", (so_b, pool_id))
    conn.execute("UPDATE connection_pools SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# 用户 CRUD
# ---------------------------------------------------------------------------

def add_user(conn: sqlite3.Connection, username: str, password_hash: str) -> int:
    """新增用户，返回自增 id。"""
    cur = conn.execute(
        "INSERT INTO users (username,password_hash) VALUES (?,?)",
        (username, password_hash),
    )
    conn.commit()
    return cur.lastrowid


def get_user(conn: sqlite3.Connection, username: str) -> Optional[dict]:
    """根据用户名查询用户，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    """根据 id 查询用户，不存在返回 None。"""
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_all_users(conn: sqlite3.Connection) -> list[dict]:
    """返回所有用户列表。"""
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def update_user(conn: sqlite3.Connection, user_id: int, username: str,
                password_hash: str) -> bool:
    """更新用户信息，影响行数 >0 返回 True。"""
    cur = conn.execute(
        "UPDATE users SET username=?,password_hash=? WHERE id=?",
        (username, password_hash, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    """删除用户，影响行数 >0 返回 True。"""
    cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# 报表配置 CRUD
# ---------------------------------------------------------------------------

def add_report(conn: sqlite3.Connection, name: str, sql_query: str,
               default_page_size: int, pool_id: Optional[int],
               category_id: Optional[int] = None) -> int:
    """新增报表配置，返回自增 id。自动分配 sort_order。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM report_configs").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,category_id,sort_order) VALUES (?,?,?,?,?,?)",
        (name, sql_query, default_page_size, pool_id, category_id, max_order + 1),
    )
    conn.commit()
    return cur.lastrowid


def get_report(conn: sqlite3.Connection, report_id: int) -> Optional[dict]:
    """根据 id 查询报表配置，不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM report_configs WHERE id=?", (report_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_reports(conn: sqlite3.Connection) -> list[dict]:
    """返回所有报表配置列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM report_configs ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_report(conn: sqlite3.Connection, report_id: int, name: str,
                  sql_query: str, default_page_size: int,
                  pool_id: Optional[int],
                  category_id: Optional[int] = None) -> bool:
    """更新报表配置，影响行数 >0 返回 True。"""
    cur = conn.execute(
        "UPDATE report_configs SET name=?,sql_query=?,default_page_size=?,pool_id=?,category_id=? WHERE id=?",
        (name, sql_query, default_page_size, pool_id, category_id, report_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_report(conn: sqlite3.Connection, report_id: int) -> bool:
    """删除报表配置，影响行数 >0 返回 True。"""
    cur = conn.execute("DELETE FROM report_configs WHERE id=?", (report_id,))
    conn.commit()
    return cur.rowcount > 0


def move_report(conn: sqlite3.Connection, report_id: int, direction: str,
                category_id: int = None) -> bool:
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
        swap_id = reports[idx - 1]["id"]
    elif direction == "down" and idx < len(reports) - 1:
        swap_id = reports[idx + 1]["id"]
    else:
        return False
    so_a = reports[idx]["sort_order"] or idx
    so_b = reports[swap_id]["sort_order"] or (idx + (1 if direction == "up" else -1))
    conn.execute("UPDATE report_configs SET sort_order=? WHERE id=?", (so_b, report_id))
    conn.execute("UPDATE report_configs SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    return True


def batch_update_report_pool(conn: sqlite3.Connection, report_ids: list[int], pool_id: Optional[int]) -> int:
    """批量更新报表的连接池，返回更新的行数。"""
    placeholders = ",".join("?" for _ in report_ids)
    cur = conn.execute(
        f"UPDATE report_configs SET pool_id=? WHERE id IN ({placeholders})",
        [pool_id] + report_ids,
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# 报表层级（分类）CRUD
# ---------------------------------------------------------------------------


def add_category(conn: sqlite3.Connection, name: str, parent_id: Optional[int] = None) -> int:
    """新增报表分类，返回自增 id。"""
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM report_categories").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO report_categories (name, parent_id, sort_order) VALUES (?,?,?)",
        (name, parent_id, max_order + 1),
    )
    conn.commit()
    return cur.lastrowid


def get_category(conn: sqlite3.Connection, category_id: int) -> Optional[dict]:
    """根据 id 查询分类，不存在返回 None。"""
    row = conn.execute("SELECT * FROM report_categories WHERE id=?", (category_id,)).fetchone()
    return dict(row) if row else None


def get_all_categories(conn: sqlite3.Connection) -> list[dict]:
    """返回所有分类列表（按 sort_order 排序）。"""
    rows = conn.execute("SELECT * FROM report_categories ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def update_category(conn: sqlite3.Connection, category_id: int, name: str, parent_id: Optional[int] = None) -> bool:
    """更新分类名称和父分类，影响行数 >0 返回 True。"""
    cur = conn.execute(
        "UPDATE report_categories SET name=?, parent_id=? WHERE id=?",
        (name, parent_id, category_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_category(conn: sqlite3.Connection, category_id: int) -> bool:
    """删除分类，关联报表的 category_id 置 NULL，子分类的 parent_id 置 NULL。"""
    conn.execute("UPDATE report_configs SET category_id=NULL WHERE category_id=?", (category_id,))
    conn.execute("UPDATE report_categories SET parent_id=NULL WHERE parent_id=?", (category_id,))
    cur = conn.execute("DELETE FROM report_categories WHERE id=?", (category_id,))
    conn.commit()
    return cur.rowcount > 0


def move_category(conn: sqlite3.Connection, category_id: int, direction: str) -> bool:
    """
    调整分类排序。direction 为 'up' 或 'down'。
    与相邻项交换 sort_order，返回 True 表示移动成功。
    """
    cats = get_all_categories(conn)
    idx = next((i for i, c in enumerate(cats) if c["id"] == category_id), None)
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        swap_id = cats[idx - 1]["id"]
    elif direction == "down" and idx < len(cats) - 1:
        swap_id = cats[idx + 1]["id"]
    else:
        return False
    so_a = cats[idx]["sort_order"] or idx
    so_b = cats[swap_id]["sort_order"] or (idx + (1 if direction == "up" else -1))
    conn.execute("UPDATE report_categories SET sort_order=? WHERE id=?", (so_b, category_id))
    conn.execute("UPDATE report_categories SET sort_order=? WHERE id=?", (so_a, swap_id))
    conn.commit()
    return True


def get_reports_by_category(conn: sqlite3.Connection) -> list[dict]:
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


def get_reports(conn: sqlite3.Connection, category_id: int = None) -> list[dict]:
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


def move_report_to_category(conn: sqlite3.Connection, report_id: int, category_id: Optional[int]) -> bool:
    """将报表移动到指定分类（None 表示移出分类）。"""
    cur = conn.execute(
        "UPDATE report_configs SET category_id=? WHERE id=?", (category_id, report_id)
    )
    conn.commit()
    return cur.rowcount > 0


def get_category_tree(conn: sqlite3.Connection) -> list[dict]:
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


def get_parent_categories(conn: sqlite3.Connection, category_id: int) -> list[dict]:
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


def batch_set_report_category(conn: sqlite3.Connection, report_ids: list[int], category_id: Optional[int]) -> int:
    """批量设置报表分类，返回受影响行数。"""
    placeholders = ",".join("?" for _ in report_ids)
    cur = conn.execute(
        f"UPDATE report_configs SET category_id=? WHERE id IN ({placeholders})",
        [category_id] + report_ids,
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# MySQL 连接管理
# ---------------------------------------------------------------------------

def create_mysql_connection(pool_config: dict) -> object:
    """
    根据连接池配置创建 MySQL 连接。

    参数 pool_config 需包含 host、port、user、password、database 字段。
    返回 mysql.connector 的 connection 对象。

    注意：
    - host='localhost' 使用 Unix socket，host='127.0.0.1' 使用 TCP
    - 如果遇到 auth 插件问题，可在创建连接池时使用 127.0.0.1 替代 localhost
    """
    import mysql.connector

    config = {
        "host": pool_config["host"],
        "port": pool_config["port"],
        "user": pool_config["user"],
        "password": pool_config["password"],
        "database": pool_config["database"],
        "connection_timeout": 10,
        "charset": "utf8mb4",
    }

    # 使用 127.0.0.1 强制走 TCP，避免 Unix socket auth 插件不匹配
    if config["host"] == "localhost":
        config["host"] = "127.0.0.1"

    return mysql.connector.connect(**config)


def execute_mysql_query(conn, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    """
    在 MySQL 连接上执行 SQL 查询。

    返回 (列名列表, 数据行列表)。适用于 SELECT 查询。
    """
    cur = conn.cursor()
    cur.execute(sql, params)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    return columns, rows


def count_mysql_query(conn, sql: str, params: tuple = ()) -> int:
    """
    将原 SQL 包装为 COUNT(*) 查询并返回总行数。

    自动去除 SQL 末尾的分号，避免子查询包裹时报语法错误。
    注意：简单包装，不支持包含 ORDER BY / LIMIT 的复杂子查询。
    """
    clean_sql = sql.rstrip("; \t\n\r")
    count_sql = f"SELECT COUNT(*) AS cnt FROM ({clean_sql}) AS _sub"
    cur = conn.cursor()
    cur.execute(count_sql, params)
    row = cur.fetchone()
    cur.close()
    return row[0]


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def add_session(conn: sqlite3.Connection, token: str, username: str) -> None:
    """持久化一条 session 记录。"""
    conn.execute(
        "INSERT OR REPLACE INTO sessions (token, username, created_at) VALUES (?,?,?)",
        (token, username, time.time()),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, token: str) -> Optional[str]:
    """根据 token 查询用户名，不存在或已过期返回 None。"""
    # 用 current_timestamp 计算 24h 有效期
    row = conn.execute(
        "SELECT username FROM sessions WHERE token=? AND created_at > ?",
        (token, time.time() - 86400),
    ).fetchone()
    return row[0] if row else None


def remove_session(conn: sqlite3.Connection, token: str) -> bool:
    """删除一条 session，成功返回 True。"""
    cur = conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    return cur.rowcount > 0


def get_all_sessions(conn: sqlite3.Connection) -> list[dict]:
    """返回所有未过期的 session 记录。"""
    rows = conn.execute(
        "SELECT token, username FROM sessions WHERE created_at > ?",
        (time.time() - 86400,),
    ).fetchall()
    return [{"token": r[0], "username": r[1]} for r in rows]


def clear_sessions(conn: sqlite3.Connection) -> None:
    """清空所有 session 记录。"""
    conn.execute("DELETE FROM sessions")
    conn.commit()
