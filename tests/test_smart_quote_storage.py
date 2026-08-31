"""
test_smart_quote_storage.py — smart_quote_flags 存储迁移与端点表单面板测试

覆盖（对应 .scratch/smart-quotes-json/issues/02 覆盖矩阵）：
- 迁移：SQLite 旧库补列默认 0、存量 json_no_quotes=1 → 面板全开（0b111）数据迁移、
  重复 init 幂等；MySQL mock 缺列 ADD / 有列跳过 + 数据迁移 UPDATE
- CRUD：add 默认 0、update 显式位图、_UNSET 不更新
- 表单：add/edit POST 落库、回显勾选状态、CSV 面板禁用 JS、说明文案
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import config
import config_db
import db
import render
import static_cache
from tests.test_mysql_mock import MockMySQLMixin


# ---------------------------------------------------------------------------
# 临时测试环境
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_smart_quote_storage_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")
_CACHE_DIR = os.path.join(_TMP_ROOT, "cache")


def _test_config() -> dict:
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "static_cache": {"enable": True, "dir": _CACHE_DIR},
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _set_up_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL, password TEXT NOT NULL,
            database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, category_id INTEGER, memo TEXT,
            result_names TEXT DEFAULT '', prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1,
            max_rows INTEGER NOT NULL DEFAULT 100000, keepalive_enabled INTEGER NOT NULL DEFAULT 0, keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL,
            name TEXT NOT NULL, url_path TEXT UNIQUE NOT NULL,
            output_format TEXT NOT NULL DEFAULT 'json', columns TEXT, filters TEXT,
            sorts TEXT, row_limit INTEGER DEFAULT 0, api_key TEXT,
            allowed_origins TEXT, enabled INTEGER NOT NULL DEFAULT 1,
            result_mode TEXT NOT NULL DEFAULT 'single',
            result_index INTEGER NOT NULL DEFAULT 0,
            allow_fetch_all INTEGER NOT NULL DEFAULT 1,
            static_cache INTEGER NOT NULL DEFAULT 1,
            json_no_quotes  INTEGER NOT NULL DEFAULT 0,
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
            json_template TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
        nested_filter    TEXT,
            updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id INTEGER NOT NULL,
            name TEXT NOT NULL, api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE);
    """)
    conn.commit()
    conn.execute("INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
                 "VALUES ('测试池','127.0.0.1',3306,'root','pass','testdb',1)")
    conn.commit()
    conn.close()


_set_up_db()

atexit_cleanup = None


class _SmartStorageBase(MockMySQLMixin, unittest.TestCase):
    """共享 harness：patch 配置 + mock MySQL 连接。"""

    @classmethod
    def setUpClass(cls):
        cls._cfg_patcher = patch("app_config.get_config",
                                 return_value=_test_config())
        cls._cfg_patcher.start()
        cls._mysql_patcher = patch("db.create_mysql_connection")
        cls._mock_factory = cls._mysql_patcher.start()
        cls.addClassCleanup(cls._cfg_patcher.stop)
        cls.addClassCleanup(cls._mysql_patcher.stop)

    def setUp(self):
        conn = _get_conn()
        conn.execute("DELETE FROM api_keys")
        conn.execute("DELETE FROM api_endpoints")
        conn.execute("DELETE FROM report_configs")
        conn.commit()
        conn.close()
        if os.path.isdir(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
        self.conn = _get_conn()
        self.mock_raw, self.mock_cursor = self.make_mock_connection()
        type(self)._mock_factory.side_effect = None
        type(self)._mock_factory.return_value = self.mock_raw

    def _create_report(self):
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id) "
            "VALUES ('r','SELECT 1',20,1)")
        self.conn.commit()

    def _create_endpoint(self, **kw):
        eid = config_db.add_api_endpoint(
            self.conn, 1, kw.get("name", "接口A"), kw.get("url_path", "/api/a"),
            output_format=kw.get("output_format", "json"),
            smart_quote_flags=kw.get("smart_quote_flags", 0),
        )
        return eid


# ---------------------------------------------------------------------------
# 迁移
# ---------------------------------------------------------------------------


class TestMigration(_SmartStorageBase):
    """smart_quote_flags 列迁移（SQLite 幂等 + 数据迁移 + MySQL mock）。"""

    def _legacy_conn(self, with_json_no_quotes: bool = True):
        """构造无 smart_quote_flags 列的存量库（可带 json_no_quotes 列）。"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        schema = tb._SQL_CREATE_API_ENDPOINTS.replace(
            "    smart_quote_flags INTEGER NOT NULL DEFAULT 0,\n", "")
        if not with_json_no_quotes:
            schema = schema.replace(
                "    json_no_quotes  INTEGER NOT NULL DEFAULT 0,\n", "")
        self.assertNotIn("smart_quote_flags", schema)
        conn.execute(schema)
        conn.execute("INSERT INTO report_configs (name,sql_query,default_page_size,pool_id) "
                     "VALUES ('r','SELECT 1',20,1)")
        return conn

    def test_sqlite_legacy_db_gains_column_default_0(self):
        conn = self._legacy_conn()
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '存量端点', '/api/legacy')")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("smart_quote_flags", cols)
        row = conn.execute("SELECT smart_quote_flags FROM api_endpoints").fetchone()
        self.assertEqual(row[0], 0, "存量端点迁移后 smart_quote_flags 默认 0")
        conn.close()

    def test_sqlite_legacy_db_without_json_no_quotes_gains_column(self):
        """无 json_no_quotes 列的极旧库：迁移 14 补列默认 0（列保留，弃用不删）。"""
        conn = self._legacy_conn(with_json_no_quotes=False)
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '极旧端点', '/api/oldest')")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("json_no_quotes", cols)
        self.assertIn("smart_quote_flags", cols)
        row = conn.execute(
            "SELECT json_no_quotes, smart_quote_flags FROM api_endpoints").fetchone()
        self.assertEqual(row[0], 0, "极旧端点迁移后 json_no_quotes 默认 0")
        self.assertEqual(row[1], 0, "极旧端点迁移后 smart_quote_flags 默认 0")
        conn.close()

    def test_mysql_migration_adds_json_no_quotes_column_when_missing(self):
        """MySQL 缺 json_no_quotes 列（迁移 14 前存量）时应执行 ADD COLUMN。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = ("api_endpoints",)
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("report_id", "int(11)", "NO", "MUL", None, ""),
            ("name", "varchar(255)", "NO", "", None, ""),
            ("url_path", "varchar(512)", "NO", "UNI", None, ""),
            ("output_format", "varchar(10)", "NO", "", None, ""),
            ("result_mode", "varchar(10)", "NO", "", None, ""),
            ("result_index", "int(11)", "NO", "", None, ""),
            ("allow_fetch_all", "tinyint(4)", "NO", "", None, ""),
            ("static_cache", "tinyint(4)", "NO", "", None, ""),
            ("json_template", "text", "YES", "", None, ""),
            ("description", "text", "YES", "", None, ""),
        ]
        with patch("db._get_engine", return_value="mysql"):
            db._init_mysql_migrations(db._MySQLConnection(self.mock_raw))
        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE api_endpoints "
            "ADD COLUMN json_no_quotes TINYINT NOT NULL DEFAULT 0", ())
        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE api_endpoints "
            "ADD COLUMN smart_quote_flags TINYINT NOT NULL DEFAULT 0", ())

    def test_sqlite_migration_data_migrates_json_no_quotes(self):
        """存量 json_no_quotes=1 → 面板全开（0b111）且旧列重置为 0；=0 保持 0。

        旧列重置是 KPI 案例缺陷的修复：若不重置，运行期兼容逻辑会把端点
        永久钉死在面板全开，用户后续取消勾选无效。
        """
        conn = self._legacy_conn()
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path, json_no_quotes) "
                     "VALUES (1, '开', '/api/on', 1), (1, '关', '/api/off', 0)")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
        rows = {r["name"]: (r["smart_quote_flags"], r["json_no_quotes"])
                for r in conn.execute(
                    "SELECT name, smart_quote_flags, json_no_quotes FROM api_endpoints")}
        self.assertEqual(rows["开"], (7, 0), "json_no_quotes=1 → 0b111 且旧列重置 0")
        self.assertEqual(rows["关"], (0, 0), "json_no_quotes=0 保持 0")
        conn.close()

    def test_sqlite_migration_idempotent(self):
        """列已存在且已迁移时重复执行不报错、值不变。"""
        conn = self._legacy_conn()
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path, json_no_quotes) "
                     "VALUES (1, 't', '/api/t', 1)")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
            config_db._init_sqlite_migrations(conn)
        row = conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints").fetchone()
        self.assertEqual(row[0], 7, "重复迁移不重置已迁移值")
        conn.close()

    def test_mysql_migration_adds_column_and_updates(self):
        """MySQL 缺列：ADD COLUMN + 数据迁移 UPDATE 均执行。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = ("api_endpoints",)
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("report_id", "int(11)", "NO", "MUL", None, ""),
            ("name", "varchar(255)", "NO", "", None, ""),
            ("url_path", "varchar(512)", "NO", "UNI", None, ""),
            ("output_format", "varchar(10)", "NO", "", None, ""),
            ("result_mode", "varchar(10)", "NO", "", None, ""),
            ("result_index", "int(11)", "NO", "", None, ""),
            ("allow_fetch_all", "tinyint(4)", "NO", "", None, ""),
            ("static_cache", "tinyint(4)", "NO", "", None, ""),
            ("json_no_quotes", "tinyint(4)", "NO", "", None, ""),
            ("json_template", "text", "YES", "", None, ""),
            ("description", "text", "YES", "", None, ""),
        ]
        with patch("db._get_engine", return_value="mysql"):
            db._init_mysql_migrations(db._MySQLConnection(self.mock_raw))
        self.mock_cursor.execute.assert_any_call(
            "ALTER TABLE api_endpoints "
            "ADD COLUMN smart_quote_flags TINYINT NOT NULL DEFAULT 0", ())
        self.mock_cursor.execute.assert_any_call(
            "UPDATE api_endpoints SET smart_quote_flags=7 "
            "WHERE json_no_quotes=1 AND smart_quote_flags=0", ())
        self.mock_cursor.execute.assert_any_call(
            "UPDATE api_endpoints SET json_no_quotes=0 "
            "WHERE json_no_quotes=1 AND smart_quote_flags>0", ())

    def test_mysql_migration_skips_add_when_present_but_updates(self):
        """MySQL 已有列：不重复 ADD，数据迁移 UPDATE 仍执行（幂等）。"""
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.return_value = ("api_endpoints",)
        self.mock_cursor.fetchall.return_value = [
            ("id", "int(11)", "NO", "PRI", None, "auto_increment"),
            ("report_id", "int(11)", "NO", "MUL", None, ""),
            ("name", "varchar(255)", "NO", "", None, ""),
            ("url_path", "varchar(512)", "NO", "UNI", None, ""),
            ("output_format", "varchar(10)", "NO", "", None, ""),
            ("result_mode", "varchar(10)", "NO", "", None, ""),
            ("result_index", "int(11)", "NO", "", None, ""),
            ("allow_fetch_all", "tinyint(4)", "NO", "", None, ""),
            ("static_cache", "tinyint(4)", "NO", "", None, ""),
            ("json_no_quotes", "tinyint(4)", "NO", "", None, ""),
            ("smart_quote_flags", "tinyint(4)", "NO", "", None, ""),
            ("json_template", "text", "YES", "", None, ""),
            ("description", "text", "YES", "", None, ""),
        ]
        with patch("db._get_engine", return_value="mysql"):
            db._init_mysql_migrations(db._MySQLConnection(self.mock_raw))
        calls = [c for c in self.mock_cursor.execute.call_args_list
                 if "ADD COLUMN smart_quote_flags" in c[0][0]]
        self.assertEqual(calls, [], "列已存在时不得重复 ADD")
        self.mock_cursor.execute.assert_any_call(
            "UPDATE api_endpoints SET smart_quote_flags=7 "
            "WHERE json_no_quotes=1 AND smart_quote_flags=0", ())
        self.mock_cursor.execute.assert_any_call(
            "UPDATE api_endpoints SET json_no_quotes=0 "
            "WHERE json_no_quotes=1 AND smart_quote_flags>0", ())


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCrud(_SmartStorageBase):
    """add/update 的 smart_quote_flags 读写。"""

    def test_add_default_zero(self):
        """新增不传 smart_quote_flags → 默认 0（标准 JSON）。"""
        self._create_report()
        eid = self._create_endpoint()
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 0)

    def test_add_explicit_flags(self):
        self._create_report()
        eid = self._create_endpoint(smart_quote_flags=5)
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 5)

    def test_update_explicit_flags(self):
        self._create_report()
        eid = self._create_endpoint()
        self.assertTrue(config_db.update_api_endpoint(
            self.conn, eid, smart_quote_flags=7))
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 7)

    def test_update_unset_keeps_value(self):
        self._create_report()
        eid = self._create_endpoint(smart_quote_flags=3)
        config_db.update_api_endpoint(self.conn, eid, name="改名")
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 3, "_UNSET 不更新 smart_quote_flags")


# ---------------------------------------------------------------------------
# 表单
# ---------------------------------------------------------------------------


class TestForm(_SmartStorageBase):
    """端点表单：add/edit POST 落库、回显勾选、CSV 禁用、文案。"""

    def _post_body(self, **kw):
        base = {
            "name": "接口A",
            "url_path": "aaa",
            "output_format": "json",
            "rule_json": "",
            "row_limit": "0",
            "enabled": "1",
            "allow_fetch_all": "1",
            "static_cache": "1",
            "smart_quote_flags": "0",
            "result_mode": "single",
            "result_index": "0",
            "action": "save_close",
        }
        base.update(kw)
        return "&".join(f"{k}={v}" for k, v in base.items())

    def test_form_add_saves_flags(self):
        self._create_report()
        status, _body = config.handle_api_endpoint_add(
            self.conn, 1, self._post_body(smart_quote_flags="5"))
        self.assertEqual(status, 302)
        eid = self.conn.execute(
            "SELECT id FROM api_endpoints WHERE url_path='/api/aaa'"
        ).fetchone()[0]
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 5)

    def test_form_edit_saves_flags(self):
        self._create_report()
        eid = self._create_endpoint()
        status, _body = config.handle_api_endpoint_edit(
            self.conn, 1, eid, self._post_body(smart_quote_flags="3",
                                               url_path="bbb"))
        self.assertEqual(status, 302)
        self.assertEqual(self.conn.execute(
            "SELECT smart_quote_flags FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0], 3)

    def test_form_html_checked_by_flags(self):
        html = render.build_api_endpoint_form_html(
            1, "报表", endpoint={"name": "n", "url_path": "/api/x",
                                "output_format": "json", "smart_quote_flags": 7,
                                "allow_fetch_all": 1, "static_cache": 1,
                                "result_mode": "single", "result_index": 0})
        self.assertIn('class="smart-quote-cb" value="1" checked',
                      html)
        self.assertIn('class="smart-quote-cb" value="2" checked', html)
        self.assertIn('class="smart-quote-cb" value="4" checked', html)
        self.assertIn('id="smart-quote-flags-input" value="7"', html)

    def test_form_html_default_all_unchecked(self):
        html = render.build_api_endpoint_form_html(
            1, "报表", endpoint=None)
        self.assertNotIn('class="smart-quote-cb" value="1" checked', html)
        self.assertIn('id="smart-quote-flags-input" value="0"', html)

    def test_form_html_csv_disabled_js(self):
        html = render.build_api_endpoint_form_html(
            1, "报表", endpoint=None)
        self.assertIn("querySelectorAll('.smart-quote-cb')", html)
        self.assertIn("cb.disabled = isCsv", html)
        self.assertIn("仅 JSON 格式支持", html)

    def test_form_html_panel_copy(self):
        """说明文案：合法 JSON 承诺、原生 int/float 恒裸、Decimal 行为、无旧「值无引号」名。"""
        html = render.build_api_endpoint_form_html(
            1, "报表", endpoint=None)
        self.assertIn("智能去引号", html)
        self.assertIn("永远合法 JSON", html)
        self.assertIn("原生 int/float 始终输出为数字", html)
        self.assertIn("Decimal 数值列在勾选", html)
        self.assertIn("1,000", html)
        self.assertNotIn("值无引号", html)
        self.assertNotIn("json-no-quotes-checkbox", html)


if __name__ == "__main__":
    unittest.main()
