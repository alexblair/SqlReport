"""
test_smart_quotes_api.py — API 端点「智能去引号」链路测试（T4）

覆盖矩阵（conv-test-full-coverage，功能点 → 测试方法）：
- 默认输出单结果集：flags 生效（"007"→7、"1e5"→1e5、"1,000"→1000、文本带引号、
  Decimal 数值化裸出）→ test_default_output_flags_effective
- flags=0 输出与现状逐字节一致（json_no_quotes=0 基线）→ test_flags_zero_byte_identical
- result_mode=all 模式生效 → test_all_mode_flags_effective
- 模板模式：flags>0 渲染成功且输出可 json.loads（智能模式保留校验）→
  test_template_flags_render_valid_json / test_template_flags_invalid_structure_falls_back
  / test_template_flags_unknown_placeholder_falls_back
- validate_template：flags>0 时非法 JSON 模板仍报错（与旧全裸跳过相反）→
  TestValidateSmartQuotes（直接调用 json_template.validate_template）
- 真实数据预览（preview）：flags 生效输出 → test_preview_form_flags_effective
- 兼容映射：迁移后状态（json_no_quotes=1 + smart_quote_flags=7）与纯 flags=7 输出
  逐字节一致；未迁移（json_no_quotes=1 + flags=0）经极端防御等价面板全开 →
  test_compat_migrated_equals_full_open / test_compat_unmigrated_equals_full_open
- 静态缓存：smart_quote_flags 变更 → config_version 变化 → .json 失效重建；
  hit 直出与 miss 一致 → test_config_version_includes_flags / test_static_toggle_invalidates
  / test_static_miss_and_hit
- output_format=csv + flags → CSV 输出不受影响 → test_csv_ignores_flags
- 模板占位预览降级（纯前端，T2 已测）→ 不重复
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
from json_template import SINGLE_KEYS, validate_template
from tests.test_mysql_mock import MockMySQLMixin

# ---------------------------------------------------------------------------
# 临时测试环境（与 test_api_json_no_quotes.py 同构）
# ---------------------------------------------------------------------------

_TMP_ROOT = tempfile.mkdtemp(prefix="test_smart_quotes_api_")
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
    """创建测试数据库表结构（含 smart_quote_flags 列）。"""
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
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
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


class _SmartQuotesApiBase(MockMySQLMixin, unittest.TestCase):
    """共享 harness：patch 配置 + mock MySQL 查询（含数字形态字符串）。"""

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
        # 列：id/name/amount(Decimal)/code(前导零数字串)/sci(科学计数法)/thou(千分位)
        self.mock_cursor.description = [
            ("id",), ("name",), ("amount",), ("code",), ("sci",), ("thou",)]
        self.mock_cursor.fetchall.return_value = [
            (1, "张三", Decimal("123.45"), "007", "1e5", "1,000"),
            (2, "李四", Decimal("0.50"), "008", "2e-3", "-1,234.50"),
        ]
        type(self)._mock_factory.side_effect = None
        type(self)._mock_factory.return_value = self.mock_raw

    def _create_report(self, sql="SELECT id, name, amount, code, sci, thou FROM users",
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

    def _create_endpoint(self, report_id=None, url_path="/api/sq", **kwargs):
        conn = _get_conn()
        if report_id is None:
            report_id = conn.execute(
                "SELECT id FROM report_configs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        eid = db.add_api_endpoint(conn, report_id, "智能去引号端点", url_path, **kwargs)
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
# 默认输出（单结果集）
# ---------------------------------------------------------------------------


class TestDefaultOutput(_SmartQuotesApiBase):
    """默认结构输出的智能去引号行为。"""

    def test_default_output_flags_effective(self):
        """flags=7：数字形态字符串裸输出并合法化转换，文本带引号。"""
        self._create_report()
        self._create_endpoint(smart_quote_flags=7)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        # 文本带引号（与旧全裸相反）
        self.assertIn('"name": "张三"', body)
        self.assertIn('"name": "李四"', body)
        # 前导零数字串 → 合法化：007 → 7
        self.assertIn('"code": 7', body)
        self.assertIn('"code": 8', body)
        # 科学计数法原样裸输出（本身即合法 JSON 数字）
        self.assertIn('"sci": 1e5', body)
        self.assertIn('"sci": 2e-3', body)
        # 千分位去逗号数值化：1,000 → 1000、-1,234.50 → -1234.50
        self.assertIn('"thou": 1000', body)
        self.assertIn('"thou": -1234.5', body)
        # Decimal（DECIMAL 列）勾选数字特征后数值化裸输出
        self.assertIn('"amount": 123.45', body)
        self.assertIn('"amount": 0.5', body)
        # 输出永远合法 JSON
        parsed = json.loads(body)
        self.assertEqual(parsed["data"][0]["code"], 7)
        self.assertEqual(parsed["data"][1]["thou"], -1234.5)
        self.assertEqual(parsed["data"][0]["amount"], 123.45)

    def test_flags_zero_byte_identical(self):
        """flags=0 输出与 json_no_quotes=0（标准 JSON）逐字节一致。"""
        self._create_report()
        self._create_endpoint(url_path="/api/a", smart_quote_flags=0)
        self._create_endpoint(url_path="/api/b", json_no_quotes=0)
        status_a, body_a, _ = self._request("/api/a")
        status_b, body_b, _ = self._request("/api/b")
        self.assertEqual(status_a, 200)
        self.assertEqual(body_a, body_b, "flags=0 必须与标准 JSON 逐字节一致")
        parsed = json.loads(body_a)
        self.assertEqual(parsed["data"][0]["code"], "007")

    def test_partial_flags_only_decimal(self):
        """仅勾选十进制（flags=1）：科学/千分位形态保持带引号。"""
        self._create_report()
        self._create_endpoint(smart_quote_flags=1)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertIn('"code": 7', body)
        self.assertIn('"sci": "1e5"', body)
        self.assertIn('"thou": "1,000"', body)

    def test_decimal_bare_when_only_scientific(self):
        """回归（用户报告）：仅勾选科学计数法（flags=2）时 DECIMAL 列数值化裸出。"""
        self._create_report()
        self._create_endpoint(smart_quote_flags=2)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertIn('"amount": 123.45', body)
        self.assertIn('"amount": 0.5', body)
        self.assertIn('"sci": 1e5', body)

    def test_decimal_bare_when_only_thousand(self):
        """回归（用户报告）：仅勾选千分位（flags=4）时 DECIMAL 列数值化裸出。"""
        self._create_report()
        self._create_endpoint(smart_quote_flags=4)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertIn('"amount": 123.45', body)
        self.assertIn('"thou": 1000', body)


# ---------------------------------------------------------------------------
# result_mode=all
# ---------------------------------------------------------------------------


class TestAllMode(_SmartQuotesApiBase):
    """result_mode=all 输出智能去引号生效。"""

    def test_all_mode_flags_effective(self):
        self._create_report()
        self._create_endpoint(result_mode="all", smart_quote_flags=7)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["mode"], "all")
        row = parsed["results"][0]["data"][0]
        self.assertEqual(row["name"], "张三")
        self.assertEqual(row["code"], 7)
        self.assertEqual(row["sci"], 100000.0)
        self.assertEqual(row["thou"], 1000)
        self.assertIn('"code": 7', body)


# ---------------------------------------------------------------------------
# JSON 模板模式
# ---------------------------------------------------------------------------


class TestTemplateMode(_SmartQuotesApiBase):
    """模板模式 + flags：渲染成功、输出合法、校验保留。"""

    def test_template_flags_render_valid_json(self):
        self._create_report()
        self._create_endpoint(
            smart_quote_flags=7, json_template='{"rows": {{data}}}')
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertIn('"rows"', body)
        self.assertNotIn('"total"', body)
        self.assertIn('"code": 7', body)
        self.assertIn('"name": "张三"', body)
        # 智能模式输出永远可解析
        json.loads(body)

    def test_template_flags_invalid_structure_falls_back(self):
        """智能模式保留校验：非法模板渲染失败 → 回退默认结构。"""
        self._create_report()
        self._create_endpoint(
            smart_quote_flags=7, json_template='{"rows": {{data}},}')
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        # 回退默认结构（含 total），且 flags 仍生效
        self.assertNotIn('"rows"', body)
        self.assertIn('"total"', body)
        parsed = json.loads(body)
        self.assertEqual(parsed["data"][0]["code"], 7)

    def test_template_flags_unknown_placeholder_falls_back(self):
        """未知占位符校验不变：渲染失败 → 回退默认结构。"""
        self._create_report()
        self._create_endpoint(
            smart_quote_flags=7, json_template='{"x": {{foo}}}')
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertNotIn('"x"', body)
        self.assertIn('"data"', body)

    def test_template_all_mode_flags(self):
        """模板 + all 模式 + flags：{{results}} 渲染成功且可解析。"""
        self._create_report()
        self._create_endpoint(
            result_mode="all", smart_quote_flags=7,
            json_template='{"sets": {{results}}}')
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        self.assertIn('"sets"', body)
        self.assertIn('"code": 7', body)
        json.loads(body)


class TestValidateSmartQuotes(unittest.TestCase):
    """validate_template 在 flags>0 时恒执行合法性校验（升级点）。"""

    def test_valid_template_ok(self):
        ok, error = validate_template(
            '{"rows": {{data}}}', SINGLE_KEYS, smart_quote_flags=7)
        self.assertTrue(ok, error)

    def test_invalid_structure_rejected(self):
        """flags>0：非法 JSON 模板仍报错（与旧全裸跳过相反）。"""
        ok, error = validate_template(
            '{"a": {{data}},}', SINGLE_KEYS, smart_quote_flags=7)
        self.assertFalse(ok)
        self.assertIn("JSON", error)
        self.assertIn("行", error)

    def test_unknown_placeholder_rejected(self):
        ok, error = validate_template(
            '{"x": {{foo}}}', SINGLE_KEYS, smart_quote_flags=7)
        self.assertFalse(ok)
        self.assertIn("foo", error)


# ---------------------------------------------------------------------------
# 兼容映射（迁移后状态）
# ---------------------------------------------------------------------------


class TestCompatMapping(_SmartQuotesApiBase):
    """旧 json_no_quotes=1 迁移为面板全开后与 flags=7 输出等价。"""

    def test_compat_migrated_equals_full_open(self):
        """迁移后（json_no_quotes=1 + smart_quote_flags=7）与纯 flags=7 逐字节一致。"""
        self._create_report()
        self._create_endpoint(url_path="/api/mig", json_no_quotes=1,
                              smart_quote_flags=7)
        self._create_endpoint(url_path="/api/full", smart_quote_flags=7)
        status, body_mig, _ = self._request("/api/mig")
        self.assertEqual(status, 200)
        status, body_full, _ = self._request("/api/full")
        self.assertEqual(status, 200)
        self.assertEqual(body_mig, body_full,
                         "迁移后旧列不得干扰面板全开行为")
        # 面板全开语义：文本带引号、数字裸
        self.assertIn('"name": "张三"', body_mig)
        self.assertIn('"code": 7', body_mig)
        self.assertNotIn('"name": 张三', body_mig)

    def test_legacy_column_no_longer_forces_full_open(self):
        """回归（KPI 案例）：json_no_quotes=1 残留端点取消勾选（flags=0）后
        输出恢复标准 JSON——面板是引号的唯一控制，旧列不再运行期强制全开。

        缺陷根因：迁移 15 转换后未重置旧列 + 运行期 max(flags,7) 强制逻辑，
        导致用户永远无法取消勾选（数字恒全裸）；修复后旧列不参与行为。
        """
        self._create_report()
        self._create_endpoint(json_no_quotes=1)  # 残留旧列，flags=0
        self._create_endpoint(url_path="/api/plain", smart_quote_flags=0)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        status, body_plain, _ = self._request("/api/plain")
        self.assertEqual(status, 200)
        self.assertEqual(body, body_plain,
                         "json_no_quotes 残留不得再驱动输出（与 flags=0 逐字节一致）")
        # 标准 JSON：数字字符串带引号（不再全裸）、原生数字裸
        self.assertIn('"code": "007"', body)
        self.assertNotIn('"code": 7', body)
        self.assertIn('"amount": "123.45"', body)


# ---------------------------------------------------------------------------
# 静态缓存
# ---------------------------------------------------------------------------


class TestStaticCache(_SmartQuotesApiBase):
    """.json 静态变体的智能去引号与版本失效。"""

    def test_static_miss_and_hit(self):
        """flags：miss 生成文件含智能输出，随后 hit 直出一致。"""
        self._create_report()
        self._create_endpoint(smart_quote_flags=7, static_cache=1)
        status, body, headers = self._request("/api/sq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        self.assertIn('"code": 7', body)
        self.assertIn('"name": "张三"', body)
        self.assertIn('"meta"', body)
        file_path = self._static_file("/api/sq")
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, encoding="utf-8") as fh:
            self.assertIn('"code": 7', fh.read())

        status2, body2, headers2 = self._request("/api/sq.json")
        self.assertEqual(status2, 200)
        self.assertEqual(headers2.get("X-Static-Cache"), "hit")
        self.assertEqual(body2, body)

    def test_config_version_includes_flags(self):
        """config_version 必须纳入 smart_quote_flags（防 TTL 内陈旧命中）。"""
        self._create_report()
        conn = _get_conn()
        ep = {"columns": None, "filters": None, "sorts": None, "row_limit": 0,
              "json_template": "", "result_mode": "single", "result_index": 0,
              "json_no_quotes": 0, "smart_quote_flags": 0}
        ep2 = dict(ep, smart_quote_flags=7)
        rep = {"sql_query": "SELECT 1", "pool_id": 1,
               "allow_all_output": 1, "max_rows": 0}
        v1 = api_handler._compute_static_config_version(ep, rep)
        v2 = api_handler._compute_static_config_version(ep2, rep)
        self.assertNotEqual(v1, v2,
                            "smart_quote_flags 变化必须改变 config_version")
        conn.close()

    def test_static_toggle_invalidates(self):
        """面板勾选变更 → config_version 变化 → 旧文件失效重建。"""
        self._create_report()
        eid = self._create_endpoint(static_cache=1)
        status, body, headers = self._request("/api/sq.json")
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        self.assertIn('"code": "007"', body)

        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, smart_quote_flags=7)
        conn.close()

        status, body, headers = self._request("/api/sq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss",
                         "面板变更必须使缓存失效重建")
        self.assertIn('"code": 7', body)
        self.assertIn('"name": "张三"', body)

    def test_static_legacy_uncancel_rebuilds(self):
        """回归（KPI 案例）：json_no_quotes=1 历史端点取消勾选（flags 7→0）
        后 .json 静态缓存失效重建为标准 JSON 输出。"""
        self._create_report()
        eid = self._create_endpoint(json_no_quotes=1, smart_quote_flags=7,
                                    static_cache=1)
        status, body, headers = self._request("/api/sq.json")
        self.assertEqual(headers.get("X-Static-Cache"), "miss")
        self.assertIn('"code": 7', body)  # 全开态

        conn = _get_conn()
        config_db.update_api_endpoint(conn, eid, smart_quote_flags=0)
        conn.close()

        status, body, headers = self._request("/api/sq.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Static-Cache"), "miss",
                         "取消勾选必须使缓存失效重建（config_version 只跟 flags）")
        self.assertIn('"code": "007"', body)  # 恢复标准 JSON


# ---------------------------------------------------------------------------
# CSV 不受影响
# ---------------------------------------------------------------------------


class TestCsvIgnored(_SmartQuotesApiBase):
    """output_format=csv + flags → CSV 输出不受影响。"""

    def test_csv_ignores_flags(self):
        self._create_report()
        self._create_endpoint(output_format="csv", smart_quote_flags=7)
        status, body, _ = self._request("/api/sq")
        self.assertEqual(status, 200)
        # CSV 值天然裸语义：与 flags 无关，Decimal 保持原值、文本原样
        self.assertIn("1,张三,123.45", body)
        self.assertIn("2,李四,0.50", body)


# ---------------------------------------------------------------------------
# 真实数据预览
# ---------------------------------------------------------------------------


class TestPreview(_SmartQuotesApiBase):
    """真实数据预览透传表单未保存的 smart_quote_flags 值。"""

    def test_preview_form_flags_effective(self):
        rid = self._create_report()
        eid = self._create_endpoint(report_id=rid)
        form = "&".join([
            "json_template=",
            "rule_json=",
            "result_mode=single",
            "result_index=0",
            "row_limit=0",
            "smart_quote_flags=7",
        ])
        code, body, _ = config.handle_api_endpoint_preview(
            self.conn, rid, eid, form)
        self.assertEqual(code, 200)
        resp = json.loads(body)
        self.assertEqual(resp["ok"], True)
        out = resp["output"]
        # 面板生效后的最终文本：文本带引号、数字裸
        self.assertIn('"code": 7', out)
        self.assertIn('"name": "张三"', out)
        json.loads(out)

    def test_preview_form_flags_off(self):
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
        self.assertEqual(resp["ok"], True)
        parsed = json.loads(resp["output"])
        self.assertEqual(parsed["data"][0]["code"], "007")


if __name__ == "__main__":
    unittest.main()
