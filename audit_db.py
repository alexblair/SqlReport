"""
audit_db.py — 审计数据库模块

管理独立的 audit.db，存储三种类型的审计日志：
  - operation: 用户对配置的 CRUD 操作（连接池/用户/报表/分类）
  - web_access: 用户页面访问
  - api: API 端点调用

提供插入、分页查询、筛选、统计、删除、导出功能。
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 连接
# ---------------------------------------------------------------------------


def get_audit_db_path() -> str:
    """获取审计数据库文件路径（公开接口）。"""
    from app_config import get_audit_db_config
    return get_audit_db_config().get("path", "audit.db")


def _get_audit_db_path() -> str:
    """从 app_config 获取 audit.db 路径，默认为 audit.db。"""
    from app_config import get_config
    cfg = get_config().get("audit_db", {})
    return cfg.get("path", "audit.db")


def _connect_audit_db() -> sqlite3.Connection:
    """连接审计数据库，自动创建目录并启用 WAL 模式。"""
    db_path = _get_audit_db_path()
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_audit_db():
    """获取审计数据库连接（兼容 db.py 转发层）。"""
    return _connect_audit_db()


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


AUDIT_SCHEMA_SQLITE = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        type            TEXT    NOT NULL,
        session_user    TEXT,

        -- operation 类型专用字段
        action          TEXT,
        entity_type     TEXT,
        entity_id       INTEGER,
        entity_name     TEXT,
        before_value    TEXT,
        after_value     TEXT,

        -- web_access / api 类型专用字段
        http_method     TEXT,
        http_path       TEXT,
        http_status     INTEGER,
        ip_address      TEXT,
        user_agent      TEXT,
        duration_ms     INTEGER,
        request_body    TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON audit_logs(type);
    CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(session_user);
"""


def init_audit_db(conn) -> None:
    """幂等地创建 audit_logs 表和索引。"""
    conn.executescript(AUDIT_SCHEMA_SQLITE)
    conn.commit()


# ---------------------------------------------------------------------------
# 插入
# ---------------------------------------------------------------------------


def insert_audit_log(
    conn,
    *,
    type: str,
    session_user: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    entity_name: Optional[str] = None,
    before_value: Any = None,
    after_value: Any = None,
    http_method: Optional[str] = None,
    http_path: Optional[str] = None,
    http_status: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    duration_ms: Optional[int] = None,
    request_body: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> int:
    """插入一条审计日志，返回自增 id。

    参数：
      type — 审计类型（'operation' / 'web_access' / 'api'）
      before_value / after_value — dict 或 JSON 字符串，自动序列化
      request_body — 字符串（WEB/API 请求的完整内容）
      timestamp — ISO 8601 格式，缺省时自动填充当前时间
    """
    ts = timestamp or datetime.now().isoformat()

    sv = json.dumps(before_value, ensure_ascii=False, default=str) if before_value is not None and not isinstance(before_value, str) else before_value
    av = json.dumps(after_value, ensure_ascii=False, default=str) if after_value is not None and not isinstance(after_value, str) else after_value
    rb = request_body

    cur = conn.execute(
        """INSERT INTO audit_logs
           (timestamp,type,session_user,action,entity_type,entity_id,entity_name,
            before_value,after_value,http_method,http_path,http_status,
            ip_address,user_agent,duration_ms,request_body)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, type, session_user, action, entity_type, entity_id, entity_name,
         sv, av, http_method, http_path, http_status,
         ip_address, user_agent, duration_ms, rb),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 查询与删除
# ---------------------------------------------------------------------------


def _build_where(filters: dict) -> tuple[str, list]:
    """根据筛选条件构建 WHERE 子句和参数列表。"""
    clauses = []
    params: list = []

    if filters.get("type"):
        clauses.append("type=?")
        params.append(filters["type"])

    if filters.get("date_from"):
        clauses.append("timestamp>=?")
        params.append(filters["date_from"])

    if filters.get("date_to"):
        clauses.append("timestamp<=?")
        params.append(filters["date_to"])

    if filters.get("session_user"):
        clauses.append("session_user=?")
        params.append(filters["session_user"])

    if filters.get("keyword"):
        kw = f"%{filters['keyword']}%"
        clauses.append(
            "(action LIKE ? OR entity_name LIKE ? OR http_path LIKE ? OR session_user LIKE ?)"
        )
        params.extend([kw, kw, kw, kw])

    where_sql = " AND ".join(clauses) if clauses else "1=1"
    return where_sql, params


def query_audit_logs(
    conn, filters: dict, page: int = 1, page_size: int = 20
) -> list[dict]:
    """分页查询审计日志，page 从 1 开始，按 id 降序返回最新在前。"""
    where_sql, params = _build_where(filters)
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM audit_logs WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def count_audit_logs(conn, filters: dict) -> int:
    """统计符合条件的审计日志总数（用于分页）。"""
    where_sql, params = _build_where(filters)
    row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM audit_logs WHERE {where_sql}", params
    ).fetchone()
    return row[0]


def export_audit_logs(conn, filters: dict) -> list[dict]:
    """导出符合条件的全部审计日志（不分页，用于 CSV 导出）。"""
    where_sql, params = _build_where(filters)
    rows = conn.execute(
        f"SELECT * FROM audit_logs WHERE {where_sql} ORDER BY id DESC", params
    ).fetchall()
    return [dict(r) for r in rows]


def rotate_audit_logs(conn, retention_days: int) -> int:
    """
    自动清理超过保留天数的审计日志。

    Args:
        conn: 审计数据库连接
        retention_days: 保留天数（0 = 不清理）

    Returns:
        删除的记录数
    """
    if retention_days <= 0:
        return 0
    import time
    cutoff = time.time() - retention_days * 86400
    from datetime import datetime
    cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
    cur = conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff_iso,))
    conn.commit()
    return cur.rowcount


def delete_audit_logs(conn, filters: dict) -> int:
    """删除符合条件的审计日志，返回影响行数。"""
    where_sql, params = _build_where(filters)
    cur = conn.execute(f"DELETE FROM audit_logs WHERE {where_sql}", params)
    conn.commit()
    return cur.rowcount
