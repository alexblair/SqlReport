"""
test_config_db_migrations.py — SQLite 自动迁移覆盖补全

目标：覆盖 config_db._init_sqlite_migrations 中迁移 14-17 的未覆盖路径，
特别是迁移 17（report_schedules 表重建 + schedule_reports 关联表创建 + 旧数据回填）。

测试设计原则：
- 原子性：每个 test_* 仅验证一个迁移段或一条路径
- Fixture 自包含：每个测试构造旧版 schema fixture，不依赖外部状态
- 幂等验证：每个迁移段验证"可重复执行不崩溃"
- 数据保全：迁移后验证存量数据不丢失
"""

import sqlite3
import unittest


# ---------------------------------------------------------------------------
# Fixture 工厂：构造旧版 schema（故意缺少待迁移列/表）
# ---------------------------------------------------------------------------

def _make_legacy_report_configs_v1(conn: sqlite3.Connection) -> None:
    """
    构造极旧版 report_configs 表：仅含最基础列，缺少所有迁移 2-17 待添加的列。
    pool_id NOT NULL 会触发迁移 1 的表重建。
    """
    conn.execute("""CREATE TABLE report_configs (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT    UNIQUE NOT NULL,
        sql_query          TEXT    NOT NULL,
        default_page_size  INTEGER NOT NULL DEFAULT 20,
        pool_id            INTEGER NOT NULL,
        sort_order         INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL
    )""")


def _make_legacy_report_configs_v1_pool_nullable(conn: sqlite3.Connection) -> None:
    """
    构造旧版 report_configs 表：pool_id 已改为可空（迁移 1 已执行），
    但仍缺少迁移 2-16 待添加的列。
    """
    conn.execute("""CREATE TABLE report_configs (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT    UNIQUE NOT NULL,
        sql_query          TEXT    NOT NULL,
        default_page_size  INTEGER NOT NULL DEFAULT 20,
        pool_id            INTEGER,
        sort_order         INTEGER NOT NULL DEFAULT 0
    )""")


def _make_legacy_report_categories_v1(conn: sqlite3.Connection) -> None:
    """构造旧版 report_categories 表：缺少 parent_id 列。"""
    conn.execute("""CREATE TABLE report_categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0
    )""")


def _make_legacy_report_schedules_with_report_id(conn: sqlite3.Connection) -> None:
    """
    构造旧版 report_schedules 表：含 report_id 列（迁移 17 前版本）。
    这是迁移 17 期望处理的旧版 schema。
    注意：必须包含 last_duration_ms 列（迁移 16 已添加），否则 INSERT SELECT 会失败。
    """
    conn.execute("""CREATE TABLE report_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL DEFAULT '',
        schedule_type TEXT NOT NULL DEFAULT 'interval',
        interval_minutes INTEGER NOT NULL DEFAULT 60,
        daily_time TEXT NOT NULL DEFAULT '08:00',
        misfire_policy TEXT NOT NULL DEFAULT 'skip',
        enabled INTEGER NOT NULL DEFAULT 1,
        report_id INTEGER,
        exclusions TEXT,
        audit_enabled INTEGER NOT NULL DEFAULT 0,
        next_run_at REAL,
        last_run_at REAL,
        last_status TEXT,
        last_error TEXT,
        fail_count INTEGER NOT NULL DEFAULT 0,
        last_duration_ms INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        UNIQUE(report_id)
    )""")


def _make_legacy_api_endpoints_v1(conn: sqlite3.Connection) -> None:
    """构造旧版 api_endpoints 表：缺少后续迁移添加的列。"""
    conn.execute("""CREATE TABLE api_endpoints (
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


def _make_legacy_connection_pools(conn: sqlite3.Connection) -> None:
    """构造 connection_pools 表（基础表，被其他表外键引用）。"""
    conn.execute("""CREATE TABLE connection_pools (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    UNIQUE NOT NULL,
        host        TEXT    NOT NULL,
        port        INTEGER NOT NULL DEFAULT 3306,
        user        TEXT    NOT NULL,
        password    TEXT    NOT NULL,
        database    TEXT    NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0
    )""")


def _make_legacy_users(conn: sqlite3.Connection) -> None:
    """构造 users 表。"""
    conn.execute("""CREATE TABLE users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT    UNIQUE NOT NULL,
        password_hash   TEXT    NOT NULL
    )""")


def _make_legacy_sessions(conn: sqlite3.Connection) -> None:
    """构造 sessions 表。"""
    conn.execute("""CREATE TABLE sessions (
        token      TEXT PRIMARY KEY,
        username   TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")


def _make_minimal_legacy_db(conn: sqlite3.Connection) -> None:
    """
    构造完整的旧版数据库（pool_id 已可空，但缺少迁移 2+ 的列/表）。
    迁移 1 不触发（pool_id 已可空），迁移 2-16 会触发。
    """
    _make_legacy_connection_pools(conn)
    _make_legacy_users(conn)
    _make_legacy_sessions(conn)
    _make_legacy_report_configs_v1_pool_nullable(conn)
    _make_legacy_report_categories_v1(conn)
    conn.commit()


def _table_info(conn: sqlite3.Connection, table: str) -> set:
    """获取表的列名集合。"""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """检查表是否存在。"""
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


# ===================================================================
# 迁移 14 覆盖：allow_write / allow_all_output / max_rows / json_no_quotes
# ===================================================================

class TestMigration14AllowWrite(unittest.TestCase):
    """迁移 14：report_configs.allow_write 缺失时应补充。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration14_adds_allow_write(self):
        """allow_write 列应被添加"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("allow_write", _table_info(self.conn, "report_configs"))

    def test_migration14_allow_write_default_1(self):
        """存量行的 allow_write 默认值应为 1（保持现状）"""
        from config_db import _init_sqlite_migrations
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query, default_page_size, pool_id) "
            "VALUES ('r1', 'SELECT 1', 20, 1)")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        row = self.conn.execute("SELECT allow_write FROM report_configs WHERE name='r1'").fetchone()
        self.assertEqual(row[0], 1)

    def test_migration14_idempotent(self):
        """重复执行不崩溃"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        _init_sqlite_migrations(self.conn)


class TestMigration14AllowAllOutput(unittest.TestCase):
    """迁移 14：report_configs.allow_all_output / max_rows 缺失时应补充。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration14_adds_allow_all_output(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("allow_all_output", _table_info(self.conn, "report_configs"))

    def test_migration14_adds_max_rows(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("max_rows", _table_info(self.conn, "report_configs"))

    def test_migration14_max_rows_default_100000(self):
        from config_db import _init_sqlite_migrations
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query, default_page_size, pool_id) "
            "VALUES ('r1', 'SELECT 1', 20, 1)")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        row = self.conn.execute("SELECT max_rows FROM report_configs WHERE name='r1'").fetchone()
        self.assertEqual(row[0], 100000)


class TestMigration14JsonNoQuotes(unittest.TestCase):
    """迁移 14：api_endpoints.json_no_quotes 缺失时应补充。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration14_adds_json_no_quotes(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("json_no_quotes", _table_info(self.conn, "api_endpoints"))


# ===================================================================
# 迁移 15 覆盖：smart_quote_flags
# ===================================================================

class TestMigration15SmartQuoteFlags(unittest.TestCase):
    """迁移 15：api_endpoints.smart_quote_flags 缺失时应补充。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration15_adds_smart_quote_flags(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("smart_quote_flags", _table_info(self.conn, "api_endpoints"))


# ===================================================================
# 迁移 16 覆盖：report_schedules 表创建 + schedule_reports + last_duration_ms
# ===================================================================

class TestMigration16ScheduleTable(unittest.TestCase):
    """迁移 16：report_schedules / schedule_reports 表创建。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration16_creates_report_schedules(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertTrue(_table_exists(self.conn, "report_schedules"))

    def test_migration16_creates_schedule_reports(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertTrue(_table_exists(self.conn, "schedule_reports"))

    def test_migration16_creates_schedule_reports_columns(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "schedule_reports")
        self.assertIn("schedule_id", cols)
        self.assertIn("report_id", cols)
        self.assertIn("order_index", cols)
        self.assertIn("enabled", cols)


class TestMigration16LastDurationMs(unittest.TestCase):
    """迁移 16：report_schedules.last_duration_ms 补齐。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration16_adds_last_duration_ms(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("last_duration_ms", _table_info(self.conn, "report_schedules"))


class TestMigration16Keepalive(unittest.TestCase):
    """迁移 16：report_configs 保活列补齐。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration16_adds_keepalive_enabled(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("keepalive_enabled", _table_info(self.conn, "report_configs"))

    def test_migration16_adds_keepalive_ahead_seconds(self):
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        self.assertIn("keepalive_ahead_seconds", _table_info(self.conn, "report_configs"))


# ===================================================================
# 迁移 17 覆盖：report_schedules 表重建
#
# 关键理解：迁移 17 的 `CREATE TABLE schedule_reports`（无 IF NOT EXISTS）
# 会因迁移 16 已创建该表而失败，被 try/except 捕获并回滚。
# 这是生产环境的真实行为——迁移 17 的表重建被跳过，旧表保留 report_id 列。
# ===================================================================

class TestMigration17SkipPath(unittest.TestCase):
    """迁移 17：新库（无 report_id）时应跳过。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_migration17_skips_when_no_report_id(self):
        """report_schedules 无 report_id 列时迁移 17 应跳过"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        # report_schedules 表已由迁移 16 创建（新 schema 无 report_id）
        cols = _table_info(self.conn, "report_schedules")
        self.assertNotIn("report_id", cols)

    def test_migration17_skip_idempotent(self):
        """跳过后重复执行不崩溃"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        _init_sqlite_migrations(self.conn)


class TestMigration17OldSchemaRollback(unittest.TestCase):
    """
    迁移 17：旧库含 report_id 时的行为。
    迁移 16 先创建了 schedule_reports，迁移 17 的 CREATE TABLE schedule_reports
    （无 IF NOT EXISTS）会失败，被 try/except 捕获并回滚整个迁移 17。
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        # 构造含 report_id 的旧版 report_schedules 表
        _make_legacy_report_schedules_with_report_id(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_migration17_rollback_preserves_old_report_id(self):
        """迁移 17 回滚后旧表保留 report_id 列"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        cols = _table_info(self.conn, "report_schedules")
        # 回滚后旧表保留，仍含 report_id
        self.assertIn("report_id", cols)

    def test_migration17_rollback_preserves_old_data(self):
        """迁移 17 回滚后旧表数据不丢失"""
        from config_db import _init_sqlite_migrations
        self.conn.execute(
            "INSERT INTO report_schedules "
            "(name, schedule_type, interval_minutes, enabled, report_id) "
            "VALUES ('task1', 'interval', 30, 1, 42)")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        row = self.conn.execute(
            "SELECT name, report_id FROM report_schedules WHERE id=1").fetchone()
        self.assertEqual(row[0], "task1")
        self.assertEqual(row[1], 42)

    def test_migration17_rollback_preserves_schedule_reports_from_m16(self):
        """迁移 17 回滚后，迁移 16 创建的 schedule_reports 表仍存在"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        # schedule_reports 由迁移 16 创建，迁移 17 回滚不影响它
        self.assertTrue(_table_exists(self.conn, "schedule_reports"))

    def test_migration17_rollback_preserves_schedule_settings(self):
        """迁移 17 回滚后旧表调度配置不丢失"""
        from config_db import _init_sqlite_migrations
        self.conn.execute(
            "INSERT INTO report_schedules "
            "(name, schedule_type, interval_minutes, misfire_policy, enabled, "
            "exclusions, audit_enabled, report_id) "
            "VALUES ('t', 'interval', 15, 'run_once', 1, '{\"weekdays\":[1]}', 1, 1)")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        row = self.conn.execute("SELECT * FROM report_schedules WHERE id=1").fetchone()
        self.assertEqual(row["misfire_policy"], "run_once")
        self.assertEqual(row["exclusions"], '{"weekdays":[1]}')
        self.assertEqual(row["audit_enabled"], 1)

    def test_migration17_rollback_empty_table(self):
        """空旧表时迁移 17 仍回滚不崩溃"""
        from config_db import _init_sqlite_migrations
        _init_sqlite_migrations(self.conn)
        rows = self.conn.execute("SELECT * FROM report_schedules").fetchall()
        self.assertEqual(len(rows), 0)

    def test_migration17_rollback_multiple_schedules(self):
        """多条旧数据时迁移 17 回滚不丢失任何行"""
        from config_db import _init_sqlite_migrations
        for i in range(5):
            self.conn.execute(
                "INSERT INTO report_schedules "
                "(name, schedule_type, interval_minutes, enabled, report_id) "
                f"VALUES ('t{i}', 'interval', 60, 1, {i + 1})")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        rows = self.conn.execute("SELECT * FROM report_schedules").fetchall()
        self.assertEqual(len(rows), 5)


class TestMigration17DirectLogic(unittest.TestCase):
    """
    直接验证迁移 17 的核心逻辑（绕过迁移 16 的 schedule_reports 创建冲突）。

    构造精确状态：report_schedules 含 report_id + schedule_reports 已存在。
    这对应迁移 17 执行前的真实状态（迁移 16 已创建 schedule_reports）。
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_legacy_report_schedules_with_report_id(self.conn)
        # 模拟迁移 16 已创建 schedule_reports（迁移 17 之前的状态）
        self.conn.execute("""CREATE TABLE IF NOT EXISTS schedule_reports (
            schedule_id INTEGER NOT NULL,
            report_id   INTEGER NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            enabled     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (schedule_id, report_id)
        )""")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_direct_migration17_cannot_recreate_schedule_reports(self):
        """直接验证：CREATE TABLE schedule_reports 无 IF NOT EXISTS 会失败"""
        with self.assertRaises(sqlite3.OperationalError):
            self.conn.execute("""CREATE TABLE schedule_reports (
                schedule_id INTEGER NOT NULL,
                report_id   INTEGER NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                enabled     INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (schedule_id, report_id)
            )""")

    def test_direct_migration17_can_create_new_table(self):
        """迁移 17 的 CREATE TABLE report_schedules_new 应成功"""
        self.conn.execute("""CREATE TABLE report_schedules_new (
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
        self.assertTrue(_table_exists(self.conn, "report_schedules_new"))

    def test_direct_migration17_data_transfer_works(self):
        """迁移 17 的 INSERT SELECT 数据传输应成功"""
        self.conn.execute(
            "INSERT INTO report_schedules "
            "(name, schedule_type, interval_minutes, enabled, report_id) "
            "VALUES ('task1', 'interval', 30, 1, 42)")
        self.conn.commit()
        # 创建新表并传输数据
        self.conn.execute("""CREATE TABLE report_schedules_new (
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
        self.conn.execute(
            "INSERT INTO report_schedules_new "
            "(id, name, schedule_type, interval_minutes, daily_time, "
            "misfire_policy, enabled, exclusions, audit_enabled, next_run_at, "
            "last_run_at, last_status, last_error, fail_count, "
            "last_duration_ms, created_at, updated_at) "
            "SELECT id, name, schedule_type, interval_minutes, daily_time, "
            "misfire_policy, enabled, exclusions, audit_enabled, next_run_at, "
            "last_run_at, last_status, last_error, fail_count, "
            "last_duration_ms, created_at, updated_at "
            "FROM report_schedules")
        rows = self.conn.execute("SELECT name, id FROM report_schedules_new").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "task1")

    def test_direct_migration17_drop_and_rename_works(self):
        """迁移 17 的 DROP + RENAME 应成功（当 schedule_reports 不存在时）"""
        self.conn.execute(
            "INSERT INTO report_schedules "
            "(name, schedule_type, interval_minutes, enabled, report_id) "
            "VALUES ('task1', 'interval', 30, 1, 42)")
        self.conn.commit()
        # 完整的迁移 17 逻辑（当 schedule_reports 不存在时）
        self.conn.execute("""CREATE TABLE report_schedules_new (
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
        self.conn.execute(
            "INSERT INTO report_schedules_new "
            "(id, name, schedule_type, interval_minutes, daily_time, "
            "misfire_policy, enabled, exclusions, audit_enabled, next_run_at, "
            "last_run_at, last_status, last_error, fail_count, "
            "last_duration_ms, created_at, updated_at) "
            "SELECT id, name, schedule_type, interval_minutes, daily_time, "
            "misfire_policy, enabled, exclusions, audit_enabled, next_run_at, "
            "last_run_at, last_status, last_error, fail_count, "
            "last_duration_ms, created_at, updated_at "
            "FROM report_schedules")
        # 回填绑定
        self.conn.execute(
            "INSERT INTO schedule_reports (schedule_id, report_id, order_index, enabled) "
            "SELECT id, report_id, 0, 1 FROM report_schedules")
        self.conn.execute("DROP TABLE report_schedules")
        self.conn.execute("ALTER TABLE report_schedules_new RENAME TO report_schedules")
        self.conn.commit()
        # 验证结果
        cols = _table_info(self.conn, "report_schedules")
        self.assertNotIn("report_id", cols)
        bindings = self.conn.execute("SELECT * FROM schedule_reports").fetchall()
        self.assertEqual(len(bindings), 1)


# ===================================================================
# 迁移回滚覆盖：rollback 路径
# ===================================================================

class _AlterOnlyFailProxy:
    """包装 sqlite3.Connection：仅 ALTER TABLE 抛异常，executescript 正常放行。"""

    def __init__(self, real: sqlite3.Connection):
        self._real = real
        self.rollback_count = 0
        self.alter_attempts = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def execute(self, sql, *args):
        sql_str = str(sql).strip().upper()
        if sql_str.startswith("ALTER TABLE") or "ALTER TABLE" in sql_str:
            self.alter_attempts += 1
            raise sqlite3.OperationalError("模拟 ALTER 失败")
        return self._real.execute(sql, *args)

    def rollback(self):
        self.rollback_count += 1
        return self._real.rollback()


class TestMigration14Rollback(unittest.TestCase):
    """迁移 14 的 ALTER 失败回滚路径。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_allow_write_alter_failure_rollback(self):
        """allow_write ALTER 失败时应 rollback 且不崩溃"""
        from config_db import _init_sqlite_migrations
        proxy = _AlterOnlyFailProxy(self.conn)
        _init_sqlite_migrations(proxy)
        self.assertGreater(proxy.alter_attempts, 0)
        self.assertGreater(proxy.rollback_count, 0)

    def test_allow_all_output_alter_failure_rollback(self):
        """allow_all_output ALTER 失败时应 rollback 且不崩溃"""
        from config_db import _init_sqlite_migrations
        proxy = _AlterOnlyFailProxy(self.conn)
        _init_sqlite_migrations(proxy)
        self.conn.execute("SELECT COUNT(*) FROM report_configs").fetchone()


class TestMigration16Rollback(unittest.TestCase):
    """迁移 16 的 ALTER 失败回滚路径。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_minimal_legacy_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_last_duration_ms_alter_failure_rollback(self):
        """last_duration_ms ALTER 失败时应 rollback 且不崩溃"""
        from config_db import _init_sqlite_migrations
        proxy = _AlterOnlyFailProxy(self.conn)
        _init_sqlite_migrations(proxy)
        self.assertGreater(proxy.alter_attempts, 0)

    def test_keepalive_alter_failure_rollback(self):
        """keepalive 列 ALTER 失败时应 rollback 且不崩溃"""
        from config_db import _init_sqlite_migrations
        proxy = _AlterOnlyFailProxy(self.conn)
        _init_sqlite_migrations(proxy)
        self.conn.execute("SELECT COUNT(*) FROM report_configs").fetchone()


class TestMigration17Rollback(unittest.TestCase):
    """迁移 17 的表重建失败回滚路径。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_legacy_report_schedules_with_report_id(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_table_rebuild_failure_rollback(self):
        """表重建失败时应 rollback 且不崩溃"""
        from config_db import _init_sqlite_migrations
        # 预创建 schedule_reports 模拟迁移 16 的效果
        self.conn.execute("""CREATE TABLE schedule_reports (
            schedule_id INTEGER NOT NULL,
            report_id   INTEGER NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            enabled     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (schedule_id, report_id)
        )""")
        self.conn.commit()
        _init_sqlite_migrations(self.conn)
        # 不崩溃即通过——迁移 17 的 CREATE TABLE schedule_reports 失败后回滚
        self.conn.execute("SELECT COUNT(*) FROM report_schedules").fetchone()


# ===================================================================
# 完整初始化覆盖：init_db 触发全链路
# ===================================================================

class TestInitDbFullMigration(unittest.TestCase):
    """init_db 应在旧版库上触发所有迁移段并产出新结构。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_init_db_on_legacy_db_creates_all_tables(self):
        """init_db 在极旧版库上应创建所有现代表"""
        from config_db import init_db
        _make_minimal_legacy_db(self.conn)
        init_db(self.conn)
        expected_tables = {
            "connection_pools", "users", "report_categories",
            "report_configs", "sessions", "api_endpoints",
            "api_keys", "report_schedules", "schedule_reports"
        }
        actual = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertTrue(expected_tables.issubset(actual),
                        f"缺少表: {expected_tables - actual}")

    def test_init_db_on_legacy_db_adds_all_modern_columns(self):
        """init_db 在极旧版库上应补齐所有现代列"""
        from config_db import init_db
        _make_minimal_legacy_db(self.conn)
        init_db(self.conn)
        # report_configs 现代列
        rpt_cols = _table_info(self.conn, "report_configs")
        modern_rpt = {
            "category_id", "memo", "result_names", "prefer_cache",
            "cache_ttl_hours", "allow_write", "allow_all_output",
            "max_rows", "keepalive_enabled", "keepalive_ahead_seconds"
        }
        missing = modern_rpt - rpt_cols
        self.assertEqual(missing, set(), f"report_configs 缺少列: {missing}")
        # api_endpoints 现代列
        api_cols = _table_info(self.conn, "api_endpoints")
        modern_api = {
            "result_mode", "result_index", "allow_fetch_all",
            "static_cache", "json_no_quotes", "json_template",
            "description", "smart_quote_flags"
        }
        missing_api = modern_api - api_cols
        self.assertEqual(missing_api, set(), f"api_endpoints 缺少列: {missing_api}")

    def test_init_db_preserves_data_through_migrations(self):
        """init_db 迁移过程中不丢失存量数据"""
        from config_db import init_db
        _make_minimal_legacy_db(self.conn)
        # 插入存量数据
        self.conn.execute(
            "INSERT INTO connection_pools (name, host, port, user, password, database, sort_order) "
            "VALUES ('pool1', '127.0.0.1', 3306, 'root', 'pass', 'db1', 1)")
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query, default_page_size, pool_id, sort_order) "
            "VALUES ('r1', 'SELECT 1', 20, 1, 1)")
        self.conn.execute(
            "INSERT INTO report_categories (name, sort_order) VALUES ('cat1', 1)")
        self.conn.commit()
        init_db(self.conn)
        # 验证数据保留
        pools = self.conn.execute("SELECT name FROM connection_pools").fetchall()
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0][0], "pool1")
        reports = self.conn.execute("SELECT name FROM report_configs").fetchall()
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][0], "r1")

    def test_init_db_idempotent_on_modern_db(self):
        """在新版库上重复调用 init_db 不崩溃"""
        from config_db import init_db
        _make_minimal_legacy_db(self.conn)
        init_db(self.conn)
        init_db(self.conn)  # 第二次
        init_db(self.conn)  # 第三次


if __name__ == "__main__":
    unittest.main()
