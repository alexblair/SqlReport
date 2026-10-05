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

import threading



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
    """MySQL 游标包装，提供与 sqlite3.Cursor 兼容的接口子集。

    支持 execute/description/fetchone/fetchall/rowcount/lastrowid/close，
    使 _MySQLConnection.cursor() 返回的游标可直接用于 execute_mysql_query。
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description

    def execute(self, sql: str, params=None):
        import mysql.connector

        # 将 SQLite 的 ? 占位符转为 MySQL 的 %s
        mysql_sql = sql.replace("?", "%s") if params is not None else sql
        try:
            self._cursor.execute(mysql_sql, params or ())
        except mysql.connector.Error:
            self._cursor.close()
            raise
        self.rowcount = self._cursor.rowcount
        self.lastrowid = self._cursor.lastrowid
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return _MySQLRow(row) if row else None

    def fetchall(self):
        return [_MySQLRow(r) for r in self._cursor.fetchall()]

    def close(self):
        self._cursor.close()


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
        cursor = self._conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute(mysql_sql, params or ())
        except mysql.connector.Error:
            cursor.close()
            raise
        return _MySQLCursor(cursor)

    def cursor(self):
        """兼容 sqlite3.Connection.cursor()：返回 _MySQLCursor 包装游标。"""
        cursor = self._conn.cursor(dictionary=True, buffered=True)
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

    def begin(self):
        self._conn.start_transaction()

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
    # 找茬 H1：配置库查询皆短平快，无需 read_timeout（批次5 曾误加 30s）
    if cfg.get("socket"):
        config["unix_socket"] = cfg["socket"]
    elif config["host"] == "localhost":
        config["host"] = "127.0.0.1"
    raw = mysql.connector.connect(**config)
    return _MySQLConnection(raw)


# ---------------------------------------------------------------------------
# MySQL 连接管理（用户查询）
# ---------------------------------------------------------------------------


def _new_raw_connection(pool_config: dict, read_timeout: int | None = None):
    """按连接池配置建立一个**真实**的 MySQL 连接（不经池）。"""
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
    if read_timeout is not None:
        # 批次5#18：Web 交互查询防慢查询黑洞；默认 None 不限制（找茬 H1）
        config["read_timeout"] = read_timeout

    # 使用 127.0.0.1 强制走 TCP，避免 Unix socket auth 插件不匹配
    if config["host"] == "localhost":
        config["host"] = "127.0.0.1"

    return mysql.connector.connect(**config)


# ---------------------------------------------------------------------------
# MySQL 有界连接池（C-2）
# ---------------------------------------------------------------------------

# 池上限。与 ThreadingHTTPServer 的实际并发量级匹配；超出即走直连降级。
# 作为模块常量而非配置项：避免为性能参数新增配置面。
_POOL_MAX_SIZE = 8

# key → 可复用连接列表。ThreadingHTTPServer 多线程并发借还，加锁保护。
_pools: dict[tuple, list] = {}
_pools_lock = threading.Lock()


def _pool_key(pool_config: dict, read_timeout: int | None) -> tuple:
    """池的分组键。

    ⚠️ **read_timeout 必须在键里**：Web 交互路径传 30s，调度器/API 传 None
    不限制（批次 5#18 的既有修复：防慢查询定时任务被 30s 砍断）。若把两种
    连接混进同一个池，调度器的慢报表会拿到 30s 超时的连接而必然失败——
    这是语义错误，不是性能问题。
    """
    return (pool_config["host"], int(pool_config["port"]),
            pool_config["user"], pool_config["database"], read_timeout)


def _is_alive(raw) -> bool:
    """探活。ping 失败或抛异常一律按「已死」处理。"""
    try:
        return bool(raw.ping(reconnect=True))
    except Exception:
        return False


def _discard(raw) -> None:
    """真关闭一条不再可用的连接（吞掉关闭异常，不影响主流程）。"""
    try:
        raw.close()
    except Exception:
        pass


def _return_to_pool(key: tuple, raw) -> None:
    """归还回调：探活后入池，池满或已死则真关闭。

    幂等由 `_PooledConnection._released` 保证，这里只会被调一次。
    """
    if not _is_alive(raw):
        _discard(raw)
        return
    with _pools_lock:
        bucket = _pools.get(key)
        if bucket is None:
            bucket = []
            _pools[key] = bucket
        if len(bucket) >= _POOL_MAX_SIZE:
            # 池已满：真关闭。这是防止连接泄漏撑爆的关键。
            over = True
        else:
            bucket.append(raw)
            over = False
    if over:
        _discard(raw)


def _take_from_pool(key: tuple):
    """从池中取一条活连接；池空或全是死连接时返回 None。"""
    with _pools_lock:
        bucket = _pools.get(key)
        if not bucket:
            return None
        while bucket:
            raw = bucket.pop()
            if _is_alive(raw):
                return raw
            _discard(raw)
    return None


def clear_pools() -> None:
    """关闭并清空全部池连接（测试清理用；生产路径不需要）。"""
    with _pools_lock:
        buckets = list(_pools.values())
        _pools.clear()
    for bucket in buckets:
        for raw in bucket:
            _discard(raw)


class _PooledConnection:
    """池化连接包装：**close() 的语义是「归还池」而非「真关闭」**。

    之所以把归还藏进 close()，是为了让 `report.execute_report` 的
    `finally: conn.close()` 一行都不用改——Redis 契约与调用链全部不受影响。
    其余方法原样透传给底层真实连接。
    """

    __slots__ = ("_raw", "_pool_key", "_released")

    def __init__(self, raw, pool_key: tuple):
        self._raw = raw
        self._pool_key = pool_key
        self._released = False

    def _conn(self):
        if self._released:
            raise RuntimeError("MySQL 连接已归还池中，不可继续使用")
        return self._raw

    # ---- 透传接口（兼容 sqlite3.Connection 与 mysql.connector 子集）----

    def cursor(self, *args, **kwargs):
        return self._conn().cursor(*args, **kwargs)

    def execute(self, *args, **kwargs):
        return self._conn().execute(*args, **kwargs)

    def commit(self):
        return self._conn().commit()

    def rollback(self):
        return self._conn().rollback()

    def start_transaction(self):
        return self._conn().start_transaction()

    def ping(self, *args, **kwargs):
        return self._conn().ping(*args, **kwargs)

    def close(self):
        """归还池。重复调用无副作用（幂等）。"""
        if self._released:
            return
        self._released = True
        _return_to_pool(self._pool_key, self._raw)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def create_mysql_connection(pool_config: dict,
                            read_timeout: int | None = None):
    """
    根据连接池配置创建 MySQL 连接（走有界连接池）。

    返回 _PooledConnection：接口与 mysql.connector 的 Connection 兼容，
    但 **close() 是归还池**。池空、池满、或池中连接已死时自动降级为直连，
    因此池的任何异常都不会导致功能不可用。

    read_timeout: 读取超时秒数；None = 不设置（连接可用至查询自然结束）。
    找茬 H1（批次5/6 审查）：仅 Web 交互报表查询路径传 30——调度器后台
    任务复用本工厂，超时硬编码会把超 30s 的合法重报表定时任务变成必然
    失败，故默认不限制、由调用方按场景声明。**该值同时是池的分组键**，
    两种场景的连接不会混用。

    注意：
    - host='localhost' 使用 Unix socket，host='127.0.0.1' 使用 TCP
    - 如果遇到 auth 插件问题，可在创建连接池时使用 127.0.0.1 替代 localhost
    """
    key = _pool_key(pool_config, read_timeout)
    raw = _take_from_pool(key)
    if raw is None:
        raw = _new_raw_connection(pool_config, read_timeout)
    return _PooledConnection(raw, key)


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
# 写语句检测
# ---------------------------------------------------------------------------

_READ_STATEMENT_KEYWORDS = frozenset(
    {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"})

_WRITE_STATEMENT_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "CALL", "GRANT", "REVOKE", "SET",
})


# `SELECT … INTO OUTFILE '/p'` / `INTO DUMPFILE '/p'` 写的是 **MySQL 服务端磁盘**。
# 首关键词是 SELECT，会被下面的读白名单直接放行 → allow_write 护栏与缓存读门槛都会漏判。
# 只认关键词流里**相邻**的 (INTO, OUTFILE|DUMPFILE)：字符串字面量与注释已被
# `_iter_sql_keywords_with_pos` 排除，故 `SELECT 'INTO OUTFILE'` / `INTO OUTFILE_COL`
# 不会被误判为写（spec 2026-10-05-outfile-write-detect-design §4.1）。
_FILE_WRITE_TARGETS = frozenset({"OUTFILE", "DUMPFILE"})


def _has_into_file_write(keywords) -> bool:
    """关键词序列中是否存在相邻的 (INTO, OUTFILE|DUMPFILE)。

    Args:
        keywords: 关键词可迭代对象——`sql_contains_write` 传字符串列表，
            `sql_has_persistent_write` 传 (关键词, 结束偏移) 元组的生成器。
    """
    previous = None
    for keyword in keywords:
        if previous == "INTO" and keyword in _FILE_WRITE_TARGETS:
            return True
        previous = keyword
    return False


def _iter_sql_keywords_with_pos(statement: str):
    """迭代语句中的 (关键词大写, 关键词结束偏移)。

    跳过注释、字符串字面量、括号、空白。字符串字面量（'...' / "..." / `...`）
    内的内容不产出关键词，注释内含写关键词不影响判定。

    结束偏移供「关键词后面的下一个有效字符是什么」类判定使用
    （如 `REPLACE(` 是函数调用而非语句动词、`SET @x` 是用户变量）。
    """
    i = 0
    n = len(statement)
    while i < n:
        c = statement[i]
        # 字符串字面量：跳过整个字面量（含转义与双引号转义）
        if c in ("'", '"', '`'):
            i += 1
            while i < n:
                c2 = statement[i]
                i += 1
                if c2 == '\\' and i < n:
                    i += 1
                    continue
                if c2 == c:
                    if i < n and statement[i] == c:
                        i += 1
                        continue
                    break
            continue
        # 行注释 -- / #
        if c == '-' and i + 1 < n and statement[i + 1] == '-':
            j = statement.find('\n', i)
            if j == -1:
                return
            i = j + 1
            continue
        if c == '#':
            j = statement.find('\n', i)
            if j == -1:
                return
            i = j + 1
            continue
        # 块注释 /* */
        if c == '/' and i + 1 < n and statement[i + 1] == '*':
            j = statement.find('*/', i + 2)
            if j == -1:
                return
            i = j + 2
            continue
        if c.isalpha() or c == '_':
            j = i
            while j < n and (statement[j].isalnum() or statement[j] == '_'):
                j += 1
            yield statement[i:j].upper(), j
            i = j
            continue
        i += 1


def _iter_sql_keywords(statement: str):
    """迭代语句中的 SQL 关键词（`_iter_sql_keywords_with_pos` 的薄包装）。"""
    for keyword, _ in _iter_sql_keywords_with_pos(statement):
        yield keyword


def sql_contains_write(sql) -> bool:
    """检测 SQL 是否包含写语句（INSERT/UPDATE/DELETE/DDL 等）。

    复用 _split_sql_statements 逐条分割，逐条取关键词判定：
    - 首关键词在白名单 SELECT/SHOW/DESCRIBE/DESC/EXPLAIN → 读
    - 首关键词为 WITH → 扫描该语句全部关键词，命中写关键词即判写
      （覆盖 MySQL 8 CTE+DML）；否则视为 CTE 读
    - 其余首关键词 → 写；无任何关键词的语句（纯注释/空）跳过不计

    判定从严：真实写语句必有写关键词，宁可按写处理（用户可开启
    allow_write 开关），不误放任何实际写操作。
    """
    if not sql or not sql.strip():
        return False
    for statement in _split_sql_statements(sql):
        keywords = list(_iter_sql_keywords(statement))
        if not keywords:
            continue  # 纯注释/空语句：不构成写操作
        if _has_into_file_write(keywords):
            # `SELECT … INTO OUTFILE`/`DUMPFILE`：首关键词是 SELECT，但写的是
            # MySQL 服务端磁盘 → 必须与其它写语句同等拦截（spec 2026-10-05 §4.2）。
            return True
        first = keywords[0]
        if first in _READ_STATEMENT_KEYWORDS:
            continue
        if first == "WITH":
            if any(kw in _WRITE_STATEMENT_KEYWORDS for kw in keywords[1:]):
                return True
            continue
        return True
    return False


# WITH 语句中需要扫描的写动词：**不含 SET**（SET 在 WITH 内只可能出现在表达式中，
# 不是语句动词）。命中还要求动词后面**不紧跟 (**——紧跟 ( 的是 MySQL 字符串函数
# REPLACE() / INSERT()，不是语句动词（报表 17 曾因此被误判为写）。
_WITH_WRITE_VERBS = frozenset({
    "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "CALL", "GRANT", "REVOKE",
})

# SET 语句中出现这些关键词即不是「会话级用户变量」赋值，一律从严按持久写。
_SET_NON_USER_SCOPE_KEYWORDS = frozenset(
    {"GLOBAL", "PERSIST", "SESSION", "NAMES"})


def _skip_ws_and_comments(statement: str, i: int) -> int:
    """从 i 起跳过空白与注释，返回下一个有效字符的下标（到末尾返回 len）。"""
    n = len(statement)
    while i < n:
        c = statement[i]
        if c.isspace():
            i += 1
            continue
        if c == '-' and i + 1 < n and statement[i + 1] == '-':
            j = statement.find('\n', i)
            if j == -1:
                return n
            i = j + 1
            continue
        if c == '#':
            j = statement.find('\n', i)
            if j == -1:
                return n
            i = j + 1
            continue
        if c == '/' and i + 1 < n and statement[i + 1] == '*':
            j = statement.find('*/', i + 2)
            if j == -1:
                return n
            i = j + 2
            continue
        return i
    return n


def sql_has_persistent_write(sql) -> bool:
    """检测 SQL 是否包含**产生持久副作用**的写语句（缓存读门槛专用）。

    与 `sql_contains_write` 的分工（见
    docs/compose/spec/2026-09-30-write-report-cache-gate-design.md）：
    - `sql_contains_write`：**从严**，服务权限与警示（allow_write 拦截、导出 403、
      API 403、表单警示）——真实写语句必有写关键词。
    - 本函数：**精确**，只服务「跳过缓存读会不会让一个待执行的写被短路」。
      会话级语句（临时表、`SET @用户变量`）不产生持久副作用，可放行缓存读取。

    唯一铁律：**只有能静态证明无持久副作用时才排除该语句**；一切未知、无法解析、
    动态构造的语句一律按持久写处理。从严方向永远是安全的——至多维持现状
    （继续跳过缓存），绝不会误放行真正的写。

    判定规则（spec §5）：
    1. 首关键词在读白名单 → 读；
    2. `CREATE` / `DROP` 的**次关键词**为 `TEMPORARY`（修饰词位置）→ 会话级；
       `temporary` 作表名/列名时（`DROP TABLE temporary`）必须判持久写
    3. `SET` 后为**单个 `@`** 用户变量（且不含 GLOBAL/PERSIST/SESSION/NAMES）→ 会话级；
    4. `WITH`：扫描写动词，仅当命中「后面不紧跟 `(`」者 → 持久写；
    5. 其余 → 持久写。

    实现注意：第 3 条基于**首关键词的结束偏移**向后跳过空白与注释再取字符，而不是在
    裸文本上做正则——报表 35 的 9 条 `SET @…` 全部带前导块注释
    （`/*** 入驻数计算 ***/ SET @x := …`），裸文本正则会全部落空、把它们判成持久写，
    使整个缓存修复静默失效。
    """
    if not sql or not sql.strip():
        return False
    for statement in _split_sql_statements(sql):
        keywords = list(_iter_sql_keywords_with_pos(statement))
        if not keywords:
            continue  # 纯注释/空语句：不构成写操作
        if _has_into_file_write(kw for kw, _ in keywords):
            # 同上：写文件是持久副作用，不得被缓存读短路（spec 2026-10-05 §4.2）。
            return True
        first, first_end = keywords[0]
        if first in _READ_STATEMENT_KEYWORDS:
            continue
        # TEMPORARY 必须是 CREATE/DROP 的**次关键词**（修饰词位置）：
        # `DROP TABLE temporary` / `CREATE TABLE t (temporary INT)` 里的 temporary
        # 只是表名/列名，若用「关键词集合里出现 TEMPORARY」判定，真实 DDL 会被
        # 判成会话级、进而被缓存读短路（复核 C-1）。见 spec §5.1。
        if first in ("CREATE", "DROP") \
                and len(keywords) > 1 and keywords[1][0] == "TEMPORARY":
            continue
        if first == "SET":
            k = _skip_ws_and_comments(statement, first_end)
            is_user_variable = (k + 1 < len(statement)
                                and statement[k] == "@"
                                and statement[k + 1] != "@"
                                and not statement[k + 1].isspace())
            if is_user_variable and not any(
                    kw in _SET_NON_USER_SCOPE_KEYWORDS for kw, _ in keywords):
                continue
        if first == "WITH":
            hit = False
            for kw, end in keywords[1:]:
                if kw not in _WITH_WRITE_VERBS:
                    continue
                k = _skip_ws_and_comments(statement, end)
                if k >= len(statement) or statement[k] != "(":
                    hit = True
                    break
            if not hit:
                continue
        return True
    return False


# ---------------------------------------------------------------------------
# MySQL 查询执行
# ---------------------------------------------------------------------------


def execute_mysql_query(conn, sql: str, params: tuple = (),
                        transactional: bool = False) -> list[dict]:
    """
    在 MySQL 连接上执行 SQL 查询。支持多段 SQL（用 ; 分隔）。

    逐条执行每段 SQL，跳过 DDL/DML（cur.description is None）等不返回结果集的语句，
    收集所有 SELECT / 查询类语句的结果。

    当 transactional=True 时，所有语句包装在 BEGIN/COMMIT 中。
    任一语句失败 → ROLLBACK，重新抛出异常。
    注意：DDL（ALTER/CREATE/DROP）在 InnoDB 中会隐式提交当前事务，
    在事务内执行 DDL 可能导致部分语句在 ROLLBACK 后仍无法撤销。

    返回 list[dict]，每项包含 {"columns": list[str], "rows": list[tuple]}。
    若整个 SQL 中没有任何结果集返回，抛出 RuntimeError。
    """
    if transactional:
        if hasattr(conn, 'begin'):
            conn.begin()
        else:
            conn.start_transaction()
    cur = conn.cursor()
    results: list[dict] = []
    try:
        for statement in _split_sql_statements(sql):
            stmt = statement.strip()
            if not stmt:
                continue
            cur.execute(stmt, params)
            if cur.description is not None:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                results.append({"columns": columns, "rows": rows})
        if not results:
            raise RuntimeError("查询未返回任何结果集（SQL 中缺少 SELECT 语句）")
        if transactional:
            conn.commit()
    except Exception:
        if transactional:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        cur.close()
    return results


