"""
test_api_json_no_quotes.py — API 端点「值无引号」选项测试

覆盖矩阵（见 .sessions/specs/api-json-no-quotes.md）：
- 迁移：SQLite 旧库补列默认 0、重复 init 幂等；MySQL mock 缺列 ADD / 有列跳过
- CRUD：add 默认 0；update 显式 0/1；_UNSET 不更新
- 表单：add/edit POST 落库；回显与默认未勾选
- 输出：单结果集默认结构 / result_mode=all / 模板模式（开 → 所有值裸输出，
  关 → 全字符串现状；模板模式用例见工单 03 恢复）
- 静态缓存：miss 文件裸值、hit 直出一致；config_version toggle 失效重建
- CSV 忽略；预览表单未保存值生效；update 变更触发缓存文件删除

覆盖矩阵（conv-test-full-coverage，功能点 → 缺口编号 → 测试方法）：
- 迁移幂等 → test_sqlite_legacy_db_gains_column_default_0 / test_sqlite_migration_idempotent
  / test_mysql_migration_adds_column_when_missing / test_mysql_migration_skips_when_present
- CRUD 默认值 → test_add_default_off / test_update_explicit_values / test_update_unset_keeps_value
- 表单保存与回显 → test_form_add_saves_flag / test_form_add_default_off / test_form_edit_turns_off
  / test_echo_keeps_form_value / test_form_html_default_not_checked / test_form_html_checked_when_enabled
- 默认结构输出（开=裸值/关=字符串化）→ test_on_all_values_bare / test_off_keeps_decimal_stringified
- result_mode=all → test_on_all_mode / test_off_all_mode_decimal_stringified
- 模板模式（开=裸值+不校验/关=现状）→ test_on_template_mode / test_on_template_all_mode
  / test_off_template_mode_decimal_stringified（校验跳过详见 tests/test_json_template.py TestRenderNoQuotes/TestValidateNoQuotes）
- 静态缓存（miss/hit/toggle/update/模板组合/版本纳入）→ test_static_miss_and_hit_with_no_quotes
  / test_static_template_no_quotes_miss_and_hit / test_static_miss_off_decimal_stringified
  / test_toggle_invalidates_static_file / test_update_invalidates_static_file / test_config_version_includes_flag
- CSV 忽略 → test_csv_ignores_flag
- 预览（表单未保存值）→ test_preview_form_flag_effective / test_preview_form_flag_off
- 报表导出裸值（serialize_no_quote 纯函数）→ tests/test_no_quote_serializer.py 全部
- 名称统一文案 → test_form_html_default_not_checked（「值无引号」/无旧名/非严格 JSON 警示）
"""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import atexit
from decimal import Decimal
from unittest.mock import patch

import app_config
import api_handler
import config
import config_db
import db
import report as report_mod
import static_cache
from tests.test_mysql_mock import MockMySQLMixin

# ---------------------------------------------------------------------------
# 临时测试环境（与 test_api_extra.py 同构）
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_api_no_quotes_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")
_CACHE_DIR = os.path.join(_TMP_ROOT, "cache")


def _test_config() -> dict:
    """返回测试用 app_config 内容（static_cache.dir 指向临时目录）。"""
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "static_cache": {"enable": True, "dir": _CACHE_DIR},
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    """获取指向共享临时文件的配置数据库连接。"""
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _set_up_db():
    """创建测试数据库表结构。"""
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
            max_rows INTEGER NOT NULL DEFAULT 100000);
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
            json_template TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
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

# 临时目录在进程退出时清理（setUpClass 多次执行，不能在其中 rmtree 共享目录）
atexit.register(shutil.rmtree, _TMP_ROOT, ignore_errors=True)


class _ApiNoQuotesBase(MockMySQLMixin, unittest.TestCase):
    """共享 harness：patch 配置 + mock MySQL 查询（含 Decimal 值）。"""

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
        static_cache._last_invalidated.clear()
        report_mod._query_cache.clear()

        self.conn = _get_conn()  # sqlite 配置库连接（表单/预览用例）
        self.mock_raw, self.mock_cursor = self.make_mock_connection()
        # 列：id/name/amount(Decimal)/age(int)/code(数字字符串)
        self.mock_cursor.description = [
            ("id",), ("name",), ("amount",), ("age",), ("code",)]
        self.mock_cursor.fetchall.return_value = [
            (1, "张三", Decimal("123.45"), 25, "007"),
            (2, "李四", Decimal("0.50"), 30, "008"),
        ]
        type(self)._mock_factory.side_effect = None
        type(self)._mock_factory.return_value = self.mock_raw

    def _create_report(self, sql="SELECT id, name, amount, age, code FROM users",
                       ttl_hours=0, name="测试报表"):
        conn = _get_conn()
        conn.execute(
            "INSERT INTO report_configs "
            "(name,sql_query,default_page_size,pool_id,prefer_cache,cache_ttl_hours,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, sql, 20, 1, 0, ttl_hours, 1))
        conn.commit()
        rid = conn.execute(
            "SELECT id FROM report_configs WHERE name=?", (name,)).fetchone()[0]
        conn.close()
        return rid

    def _create_endpoint(self, report_id=None, url_path="/api/nq", **kwargs):
        conn = _get_conn()
        if report_id is None:
            report_id = conn.execute(
                "SELECT id FROM report_configs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        eid = db.add_api_endpoint(conn, report_id, "无引号端点", url_path, **kwargs)
        conn.close()
        return eid

    def _request(self, path, method="GET", query=None, headers=None, body=""):
        return api_handler.handle_api_request(
            _get_conn(), path, method, headers or {}, body, query or {},
            client_ip="127.0.0.1")

    def _static_file(self, url_path):
        """解析静态缓存文件绝对路径。"""
        return static_cache.resolve_file_path(url_path.lstrip("/"))


# ---------------------------------------------------------------------------
# 迁移
# ---------------------------------------------------------------------------


class TestMigration(_ApiNoQuotesBase):
    """json_no_quotes 列迁移（SQLite 幂等 + MySQL mock）。"""

    def test_sqlite_legacy_db_gains_column_default_0(self):
        """存量库（无 json_no_quotes 列）迁移后列存在，存量行默认 0。"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        old_schema = tb._SQL_CREATE_API_ENDPOINTS.replace(
            "    json_no_quotes  INTEGER NOT NULL DEFAULT 0,\n", "")
        self.assertNotIn("json_no_quotes", old_schema)
        conn.execute(old_schema)
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path) "
                     "VALUES (1, '存量端点', '/api/legacy-nq')")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_endpoints)")}
        self.assertIn("json_no_quotes", cols)
        row = conn.execute(
            "SELECT json_no_quotes FROM api_endpoints").fetchone()
        self.assertEqual(row[0], 0, "存量端点迁移后 json_no_quotes 默认 0")
        conn.close()

    def test_sqlite_migration_idempotent(self):
        """列已存在时重复执行迁移不报错、值不受影响。"""
        import tests.test_base as tb
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(tb._SQL_CREATE_CONNECTION_POOLS)
        conn.execute(tb._SQL_CREATE_REPORT_CONFIGS)
        conn.execute(tb._SQL_CREATE_API_ENDPOINTS)
        conn.execute("INSERT INTO report_configs (name,sql_query,default_page_size,pool_id) "
                     "VALUES ('r','SELECT 1',20,1)")
        conn.execute("INSERT INTO api_endpoints (report_id, name, url_path, json_no_quotes) "
                     "VALUES (1, 't', '/api/t', 1)")
        conn.commit()
        with patch("db._get_engine", return_value="sqlite3"):
            config_db._init_sqlite_migrations(conn)
            config_db._init_sqlite_migrations(conn)
        row = conn.execute(
            "SELECT json_no_quotes FROM api_endpoints").fetchone()
        self.assertEqual(row[0], 1, "重复迁移不重置已有值")
        conn.close()

    def test_mysql_migration_adds_column_when_missing(self):
        """MySQL 缺 json_no_quotes 列时应执行 ADD COLUMN。"""
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
            "ADD COLUMN json_no_quotes TINYINT NOT NULL DEFAULT 0", ()
        )

    def test_mysql_migration_skips_when_present(self):
        """MySQL 已有 json_no_quotes 列时不执行 ADD COLUMN。"""
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
        calls = [c for c in self.mock_cursor.execute.call_args_list
                 if "ADD COLUMN json_no_quotes" in c[0][0]]
        self.assertEqual(calls, [], "列已存在时不得重复 ADD")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCrud(_ApiNoQuotesBase):
    """add/update 的 json_no_quotes 读写。"""

    def test_add_default_off(self):
        """新增不传 json_no_quotes → 默认 0（关闭）。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        self.assertEqual(
            conn.execute(
                "SELECT json_no_quotes FROM api_endpoints WHERE id=?",
                (eid,)).fetchone()[0], 0)
        conn.close()

    def test_update_explicit_values(self):
        """update 显式 0/1 生效。"""
        self._create_report()
        eid = self._create_endpoint()
        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, json_no_quotes=1)
        self.assertEqual(
            conn.execute(
                "SELECT json_no_quotes FROM api_endpoints WHERE id=?",
                (eid,)).fetchone()[0], 1)
        config_db.update_api_endpoint(conn, eid, json_no_quotes=0)
        self.assertEqual(
            conn.execute(
                "SELECT json_no_quotes FROM api_endpoints WHERE id=?",
                (eid,)).fetchone()[0], 0)
        conn.close()

    def test_update_unset_keeps_value(self):
        """update 其他字段不触碰 json_no_quotes。"""
        self._create_report()
        eid = self._create_endpoint(json_no_quotes=1)
        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, name="改名")
        self.assertEqual(
            conn.execute(
                "SELECT json_no_quotes FROM api_endpoints WHERE id=?",
                (eid,)).fetchone()[0], 1)
        conn.close()


# ---------------------------------------------------------------------------
# 表单保存
# ---------------------------------------------------------------------------


class TestForm(_ApiNoQuotesBase):
    """端点新增/编辑表单的 json_no_quotes 读写。"""

    def _post_new(self, extra=None):
        data = {
            "name": "新接口",
            "url_path": "nq-new",
            "output_format": "json",
            "rule_json": "",
            "row_limit": "0",
            "allowed_origins": "",
            "enabled": "1",
            "action": "save_close",
        }
        if extra:
            data.update(extra)
        import urllib.parse
        return config.handle_request(
            self.conn, "POST", "/config/reports/1/api_endpoints/new", "",
            urllib.parse.urlencode(data))

    def _post_edit(self, eid, extra=None):
        data = {
            "name": "新接口",
            "url_path": "nq-new",
            "output_format": "json",
            "rule_json": "",
            "row_limit": "0",
            "allowed_origins": "",
            "enabled": "1",
            "action": "save_close",
        }
        if extra:
            data.update(extra)
        import urllib.parse
        return config.handle_request(
            self.conn, "POST",
            f"/config/reports/1/api_endpoints/{eid}/edit", "",
            urllib.parse.urlencode(data))

    def test_form_add_saves_flag(self):
        """新增表单勾选 → 落库 1。"""
        self._create_report()
        self._post_new(extra={"json_no_quotes": "1"})
        conn = _get_conn()
        val = conn.execute(
            "SELECT json_no_quotes FROM api_endpoints").fetchone()[0]
        conn.close()
        self.assertEqual(val, 1)

    def test_form_add_default_off(self):
        """新增表单不勾选 → 落库 0。"""
        self._create_report()
        self._post_new()
        conn = _get_conn()
        val = conn.execute(
            "SELECT json_no_quotes FROM api_endpoints").fetchone()[0]
        conn.close()
        self.assertEqual(val, 0)

    def test_form_edit_turns_off(self):
        """编辑表单取消勾选 → 落库 0。"""
        self._create_report()
        eid = self._create_endpoint(json_no_quotes=1)
        self._post_edit(eid)  # 不传 json_no_quotes → hidden 0
        conn = _get_conn()
        val = conn.execute(
            "SELECT json_no_quotes FROM api_endpoints WHERE id=?",
            (eid,)).fetchone()[0]
        conn.close()
        self.assertEqual(val, 0)

    def test_echo_keeps_form_value(self):
        """保存失败回显 dict 保留表单 json_no_quotes 值。"""
        import urllib.parse
        raw = urllib.parse.urlencode({
            "name": "回显", "url_path": "echo",
            "output_format": "json", "json_no_quotes": "1",
        })
        data = config._parse_form_data(raw)
        tmp = config._endpoint_from_form(
            data, "/api/echo", data.get("result_mode", "single"))
        self.assertEqual(tmp["json_no_quotes"], 1)

    def test_form_html_default_not_checked(self):
        """新增态表单不勾选（默认关闭）。"""
        from render import build_api_endpoint_form_html
        html = build_api_endpoint_form_html(1, "测试报表")
        self.assertIn('name="json_no_quotes"', html)
        self.assertNotIn(
            '<input type="checkbox" name="json_no_quotes" value="1" checked',
            html.replace('id="json-no-quotes-checkbox"', ''))
        # 名称统一：「值无引号」，无旧名残留；含非严格 JSON 警示
        self.assertIn("值无引号", html)
        self.assertNotIn("数字无引号", html)
        self.assertIn("不再保证是严格合法 JSON", html)

    def test_form_html_checked_when_enabled(self):
        """编辑态启用时勾选。"""
        from render import build_api_endpoint_form_html
        html = build_api_endpoint_form_html(
            1, "测试报表", endpoint={"id": 1, "name": "t", "url_path": "/api/t",
                                     "json_no_quotes": 1, "result_mode": "single"})
        self.assertIn(
            'value="1" checked id="json-no-quotes-checkbox"', html)


# ---------------------------------------------------------------------------
# 输出链路（handle_api_request 为 seam）
# ---------------------------------------------------------------------------


class TestOutput(_ApiNoQuotesBase):
    """单结果集 / all / 模板模式的「值无引号」输出。"""

    def test_off_keeps_decimal_stringified(self):
        """关闭（默认）：Decimal 保持字符串（现状契约）。"""
        self._create_report()
        self._create_endpoint()
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["data"][0]["amount"], "123.45")
        self.assertEqual(parsed["data"][0]["age"], 25)

    def test_on_all_values_bare(self):
        """开启：所有值（数字与字符串）裸输出不带引号。"""
        self._create_report()
        self._create_endpoint(json_no_quotes=1)
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        # 值无引号模式：字符串/数字字符串/Decimal 全部裸输出（文本断言）
        self.assertIn('"name": 张三', body)
        self.assertIn('"code": 007', body)
        self.assertIn('"amount": 123.45', body)
        self.assertIn('"amount": 0.5', body)
        self.assertIn('"age": 25', body)

    def test_on_all_mode(self):
        """result_mode=all：results[i].data 所有值裸输出。"""
        self._create_report()
        self._create_endpoint(result_mode="all", json_no_quotes=1)
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        self.assertIn('"name": 张三', body)
        self.assertIn('"code": 007', body)
        self.assertIn('"amount": 123.45', body)

    def test_off_all_mode_decimal_stringified(self):
        """result_mode=all 关闭：Decimal 字符串化。"""
        self._create_report()
        self._create_endpoint(result_mode="all")
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["results"][0]["data"][0]["amount"], "123.45")

    def test_on_template_mode(self):
        """模板模式开启：{{data}} 内所有值裸输出（不校验，不回退）。"""
        self._create_report()
        self._create_endpoint(
            json_no_quotes=1, json_template='{"rows": {{data}}}')
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        # 模板结构生效（非回退默认结构）
        self.assertIn('"rows"', body)
        self.assertNotIn('"total"', body)
        self.assertIn('"name": 张三', body)
        self.assertIn('"code": 007', body)
        self.assertIn('"amount": 123.45', body)

    def test_off_template_mode_decimal_stringified(self):
        """模板模式关闭：{{data}} 内 Decimal 字符串化。"""
        self._create_report()
        self._create_endpoint(
            json_template='{"rows": {{data}}}')
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["rows"][0]["amount"], "123.45")

    def test_on_template_all_mode(self):
        """模板 + all 模式开启：{{results}} 内所有值裸输出（不校验）。"""
        self._create_report()
        self._create_endpoint(
            result_mode="all", json_no_quotes=1,
            json_template='{"sets": {{results}}}')
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        self.assertIn('"sets"', body)
        self.assertNotIn('"mode"', body)
        self.assertIn('"name": 张三', body)
        self.assertIn('"amount": 123.45', body)

    def test_csv_ignores_flag(self):
        """output_format=csv + json_no_quotes=1 → CSV 输出不受影响。"""
        self._create_report()
        self._create_endpoint(output_format="csv", json_no_quotes=1)
        status, body, _ = self._request("/api/nq")
        self.assertEqual(status, 200)
        # CSV 输出与 json_no_quotes 无关：Decimal 保持原值、不加引号
        self.assertIn("1,张三,123.45", body)
        self.assertIn("2,李四,0.50", body)


# ---------------------------------------------------------------------------
# 静态缓存
# ---------------------------------------------------------------------------


class TestStaticCache(_ApiNoQuotesBase):
    """.json 静态变体的「值无引号」与版本失效。"""

    def test_static_miss_and_hit_with_no_quotes(self):
        """开启：miss 生成文件含裸值，随后 hit 直出一致。"""
        self._create_report()
        self._create_endpoint(json_no_quotes=1, static_cache=1)
        status, body, headers = self._request("/api/nq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        # 值无引号：字符串/数字全部裸输出（文本断言）
        self.assertIn('"name": 张三', body)
        self.assertIn('"amount": 123.45', body)
        # meta 节点附加且不影响 data 语义
        self.assertIn('"meta"', body)

        file_path = self._static_file("/api/nq")
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, encoding="utf-8") as fh:
            file_content = fh.read()
        self.assertIn('"amount": 123.45', file_content)
        self.assertIn('"name": 张三', file_content)

        status2, body2, headers2 = self._request("/api/nq.json")
        self.assertEqual(status2, 200)
        self.assertEqual(headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(body2, body)

    def test_static_miss_off_decimal_stringified(self):
        """关闭：静态文件 Decimal 字符串化。"""
        self._create_report()
        self._create_endpoint(static_cache=1)
        status, body, _ = self._request("/api/nq.json")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["data"][0]["amount"], "123.45")
        with open(self._static_file("/api/nq"), encoding="utf-8") as fh:
            self.assertIn('"amount": "123.45"', fh.read())

    def test_static_template_no_quotes_miss_and_hit(self):
        """模板 + 值无引号：miss 落盘裸值模板输出，hit 直出一致。"""
        self._create_report()
        self._create_endpoint(
            json_no_quotes=1, static_cache=1,
            json_template='{"rows": {{data}}}')
        status, body, headers = self._request("/api/nq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        self.assertIn('"rows"', body)
        self.assertIn('"name": 张三', body)
        file_path = self._static_file("/api/nq")
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, encoding="utf-8") as fh:
            self.assertIn('"name": 张三', fh.read())
        status2, body2, headers2 = self._request("/api/nq.json")
        self.assertEqual(status2, 200)
        self.assertEqual(headers2.get("X-Static-Cache"), "hit",
                         "无引号模式模板文件须能命中（版本化判定）")
        self.assertEqual(body2, body)

    def test_toggle_invalidates_static_file(self):
        """开关切换 → config_version 变化 → 旧文件失效重建（裸值生效）。"""
        self._create_report()
        eid = self._create_endpoint(static_cache=1)
        status, body, headers = self._request("/api/nq.json")
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        self.assertIn('"amount": "123.45"', body)

        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, json_no_quotes=1)
        conn.close()

        status, body, headers = self._request("/api/nq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss",
                         "开关变更必须使缓存失效重建")
        self.assertIn('"amount": 123.45', body)
        self.assertIn('"name": 张三', body)

    def test_update_invalidates_static_file(self):
        """update 变更 json_no_quotes → 静态缓存文件被删除。"""
        self._create_report()
        eid = self._create_endpoint(static_cache=1)
        self._request("/api/nq.json")
        file_path = self._static_file("/api/nq")
        self.assertTrue(os.path.exists(file_path))
        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, json_no_quotes=1)
        conn.close()
        self.assertFalse(
            os.path.exists(file_path),
            "输出影响字段变更必须删除静态缓存文件")

    def test_config_version_includes_flag(self):
        """config_version 必须纳入 json_no_quotes（防 TTL 内陈旧命中）。"""
        self._create_report()
        conn = _get_conn()
        ep = {"columns": None, "filters": None, "sorts": None, "row_limit": 0,
              "json_template": "", "result_mode": "single", "result_index": 0,
              "json_no_quotes": 0}
        ep2 = dict(ep, json_no_quotes=1)
        rep = {"sql_query": "SELECT 1", "pool_id": 1,
               "allow_all_output": 1, "max_rows": 0}
        v1 = api_handler._compute_static_config_version(ep, rep)
        v2 = api_handler._compute_static_config_version(ep2, rep)
        self.assertNotEqual(v1, v2,
                            "json_no_quotes 变化必须改变 config_version")
        conn.close()


# ---------------------------------------------------------------------------
# 预览
# ---------------------------------------------------------------------------


class TestPreview(_ApiNoQuotesBase):
    """真实数据预览携带表单未保存的 json_no_quotes 值。"""

    def test_preview_form_flag_effective(self):
        """表单勾选未保存 → 预览输出所有值裸输出。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid)
        form = "&".join([
            "json_template=",
            "rule_json=",
            "result_mode=single",
            "result_index=0",
            "row_limit=0",
            "json_no_quotes=1",
        ])
        code, body, _ = config.handle_api_endpoint_preview(
            self.conn, rid, eid, form)
        self.assertEqual(code, 200)
        resp = json.loads(body)
        self.assertEqual(resp["ok"], True)
        out = resp["output"]
        # 值无引号：字符串/数字全部裸输出（文本断言）
        self.assertIn('"name": 张三', out)
        self.assertIn('"amount": 123.45', out)

    def test_preview_form_flag_off(self):
        """表单未勾选 → 预览输出 Decimal 字符串化（现状）。"""
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid)
        form = "&".join([
            "json_template=",
            "rule_json=",
            "result_mode=single",
            "result_index=0",
            "row_limit=0",
        ])
        code, body, _ = config.handle_api_endpoint_preview(
            self.conn, rid, eid, form)
        self.assertEqual(code, 200)
        resp = json.loads(body)
        out = json.loads(resp["output"])
        self.assertEqual(out["data"][0]["amount"], "123.45")


if __name__ == "__main__":
    unittest.main()
