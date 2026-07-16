"""
query_executor.py — MySQL 查询执行器

职责：
1. MySQL 连接管理：根据连接池配置创建连接
2. SQL 语句拆分（支持多语句）
3. 执行 MySQL 查询并返回结构化结果
4. 行计数

设计：
- 提供 MySQL 伪连接类，接口兼容 sqlite3.Connection
- 纯函数设计，无全局状态
"""



# ---------------------------------------------------------------------------
# MySQL 行包装
# ---------------------------------------------------------------------------


class _MySQLRow:
    """MySQL 行包装，同时支持 dict 键访问和整数索引（兼容 sqlite3.Row）。"""

    def __init__(self, data):
        if isinstance(data, dict):
            self._data = data
            self._keys = list(data.keys())
        else:
            # Accept sequences (tuples/lists) for SHOW COLUMNS results etc.
            self._keys = list(range(len(data)))
            self._data = dict(zip(self._keys, data))

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            if isinstance(key, slice):
                return [self._data[k] for k in self._keys[key]]
            return self._data[self._keys[key]]
        return self._data[key]

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self):
        return len(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def __repr__(self):
        return repr(self._data)


# ---------------------------------------------------------------------------
# MySQL 游标包装
# ---------------------------------------------------------------------------


class _MySQLCursor:
    """MySQL 游标包装，提供 fetchone/fetchall/rowcount/lastrowid 接口。"""

    def __init__(self, cursor):
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid

    def fetchone(self):
        row = self._cursor.fetchone()
        return _MySQLRow(row) if row else None

    def fetchall(self):
        return [_MySQLRow(r) for r in self._cursor.fetchall()]


# ---------------------------------------------------------------------------
# MySQL 连接包装
# ---------------------------------------------------------------------------


class _MySQLConnection:
    """
    MySQL 连接包装，提供与 sqlite3.Connection 兼容的子集接口。

    自动将 ? 占位符转为 %s，使上层 CRUD 函数无需修改 SQL 字符串即可
    在 SQLite 和 MySQL 间切换。
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=None):
        import mysql.connector

        # 将 SQLite 的 ? 占位符转为 MySQL 的 %s
        mysql_sql = sql.replace("?", "%s") if params is not None else sql
        cursor = self._conn.cursor(dictionary=True)
        try:
            cursor.execute(mysql_sql, params or ())
        except mysql.connector.Error:
            cursor.close()
            raise
        return _MySQLCursor(cursor)

    def executescript(self, sql: str):
        """兼容 sqlite3 的 executescript：按分号拆分逐条执行。"""
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                self.execute(stmt)
        self.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# MySQL 连接工厂（config_db 引擎模式）
# ---------------------------------------------------------------------------


def _connect_mysql_config() -> _MySQLConnection:
    """
    根据 app_config 创建 MySQL 连接（用于 config_db 存储）。

    注意：使用 late import of db 模块，使 unittest.mock.patch("db._get_db_config")
    能正确拦截内部调用。
    """
    import mysql.connector
    from mysql.connector import ClientFlag

    import db as _db
    cfg = _db._get_db_config()
    config = {
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.get("port", 3306),
        "user": cfg.get("user", "root"),
        "password": cfg.get("password", ""),
        "database": cfg.get("database", "sqlreport_config"),
        "connection_timeout": 10,
        "charset": "utf8mb4",
        # 使 rowcount 返回匹配行数而非实际修改行数（与 SQLite 行为一致）
        "client_flags": [ClientFlag.FOUND_ROWS],
    }
    if cfg.get("socket"):
        config["unix_socket"] = cfg["socket"]
    elif config["host"] == "localhost":
        config["host"] = "127.0.0.1"
    raw = mysql.connector.connect(**config)
    return _MySQLConnection(raw)


# ---------------------------------------------------------------------------
# MySQL 连接管理（用户查询）
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


# ---------------------------------------------------------------------------
# SQL 语句拆分
# ---------------------------------------------------------------------------


def _split_sql_statements(sql: str) -> list[str]:
    """
    将 SQL 按 ; 拆分为多条语句，同时正确处理引号和注释内部的 ;。

    支持以下上下文中 ; 不作为分隔符：
    - 单引号字符串 '...'
    - 双引号字符串 "..."
    - 反引号标识符 `...`
    - 行注释 -- ...
    - 行注释 # ...
    - 块注释 /* ... */

    正确处理的转义场景：
    - '' （两个连续单引号 = 转义的单引号）
    - 反斜杠转义
    """
    if sql is None:
        return []
    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)

    def _consume_quoted(delim: str) -> None:
        """消费以 delim 包裹的字符串字面量，处理转义"""
        nonlocal i
        current.append(delim)
        i += 1
        while i < n:
            c2 = sql[i]
            current.append(c2)
            i += 1
            if c2 == delim:
                # '' / "" / `` = 转义的引号，字符串继续
                if i < n and sql[i] == delim:
                    current.append(delim)
                    i += 1
                    continue
                break
            # 反斜杠转义下一个字符
            if c2 == "\\" and i < n:
                current.append(sql[i])
                i += 1

    while i < n:
        c = sql[i]
        # 单引号 / 双引号 / 反引号
        if c in ("'", '"', '`'):
            _consume_quoted(c)
        # 行注释 --
        elif c == '-' and i + 1 < n and sql[i + 1] == '-':
            current.append(c)
            i += 1
            while i < n and sql[i] != '\n':
                current.append(sql[i])
                i += 1
        # 行注释 #
        elif c == '#':
            current.append(c)
            i += 1
            while i < n and sql[i] != '\n':
                current.append(sql[i])
                i += 1
        # 块注释 /* */
        elif c == '/' and i + 1 < n and sql[i + 1] == '*':
            current.append(c)
            i += 1
            while i < n - 1:
                current.append(sql[i])
                if sql[i] == '*' and sql[i + 1] == '/':
                    current.append('/')
                    i += 2
                    break
                i += 1
        # 分号（语句分隔符）
        elif c == ';':
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
        else:
            current.append(c)
            i += 1
    # 最后一段
    remaining = ''.join(current).strip()
    if remaining:
        statements.append(remaining)
    return statements


# ---------------------------------------------------------------------------
# MySQL 查询执行
# ---------------------------------------------------------------------------


def execute_mysql_query(conn, sql: str, params: tuple = ()) -> list[dict]:
    """
    在 MySQL 连接上执行 SQL 查询。支持多段 SQL（用 ; 分隔）。

    逐条执行每段 SQL，跳过 DDL/DML（cur.description is None）等不返回结果集的语句，
    收集所有 SELECT / 查询类语句的结果。

    返回 list[dict]，每项包含 {"columns": list[str], "rows": list[tuple]}。
    若整个 SQL 中没有任何结果集返回，抛出 RuntimeError。
    """
    cur = conn.cursor()
    results: list[dict] = []
    for statement in _split_sql_statements(sql):
        stmt = statement.strip()
        if not stmt:
            continue
        cur.execute(stmt, params)
        if cur.description is not None:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            results.append({"columns": columns, "rows": rows})
    cur.close()
    if not results:
        raise RuntimeError("查询未返回任何结果集（SQL 中缺少 SELECT 语句）")
    return results


# ---------------------------------------------------------------------------
# MySQL 行计数
# ---------------------------------------------------------------------------


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
