"""test_max_rows.py — 全量输出护栏（PH-06, T4a）

覆盖矩阵见 .scratch/product-hardening/issues/PH-06.md：
- MR-01~03：迁移 14 追加 allow_all_output（存量默认 1）+ max_rows（默认 100000）与幂等
- TR-01~07：execute_report 截断边界/开关/缺省/裸调用
- TR-08~10：写缓存前截断（缓存=截断快照）、缓存命中标记保留、陈旧全量缓存兜底
- TR-11：ReportResult.truncated 缺省 None 兼容
"""

import unittest
from unittest.mock import patch, MagicMock

from tests.test_base import make_config_db
import config_db
import redis_cache
import report
from report import ReportResult


class TestMigrationMaxRows(unittest.TestCase):
    """迁移 14 追加：reports.allow_all_output + max_rows。"""

    def _legacy_db(self):
        """构造存量库：report_configs 含 allow_write、不含两新列，有存量报表。"""
        conn = make_config_db()
        conn.executescript("""
            CREATE TABLE report_configs (
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
                allow_write        INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("存量报表", "SELECT 1"))
        conn.commit()
        return conn

    def _has_column(self, conn, table, col):
        return col in {row[1] for row in
                       conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def test_migration_adds_columns_with_legacy_defaults(self):
        """存量库迁移后：两列存在且存量行默认 1 / 100000（保持现状）。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        self.assertTrue(self._has_column(conn, "report_configs", "allow_all_output"))
        self.assertTrue(self._has_column(conn, "report_configs", "max_rows"))
        val = conn.execute(
            "SELECT allow_all_output, max_rows FROM report_configs WHERE id=1"
        ).fetchone()
        self.assertEqual(val[0], 1, "存量默认 1 = 允许全量输出（现状语义）")
        self.assertEqual(val[1], 100000, "存量默认 max_rows=100000")
        conn.close()

    def test_migration_idempotent(self):
        """重复执行迁移不报错、不改变列与存量值。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        config_db._init_sqlite_migrations(conn)
        val = conn.execute(
            "SELECT allow_all_output, max_rows FROM report_configs WHERE id=1"
        ).fetchone()
        self.assertEqual(val[0], 1)
        self.assertEqual(val[1], 100000)
        conn.close()


# ===================================================================
# execute_report 截断（单元级，mock 连接）
# ===================================================================


class TestExecuteReportMaxRows(unittest.TestCase):
    """execute_report 全量输出截断单元测试。"""

    def setUp(self):
        """清理全局缓存，避免测试间状态污染（report_id 复用 1 + 同 SQL）。"""
        report._query_cache.clear()

    def tearDown(self):
        report._query_cache.clear()

    def _exec(self, report_cfg, rows_n, sql="SELECT 1", report_id=1, cache=None):
        """mock MySQL 返回 rows_n 行，执行 execute_report 并返回结果。"""
        mock_rows = [(i,) for i in range(rows_n)]
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": mock_rows}]
            return report.execute_report(report_id, sql, {"host": "h"},
                                         report=report_cfg, cache=cache)

    def test_exact_max_rows_no_truncation(self):
        """截断边界：行数 = max_rows → 不截断，truncated 为 None。"""
        r = self._exec({"allow_all_output": 0, "max_rows": 5}, 5)
        self.assertEqual(r.total, 5)
        self.assertIsNone(r.truncated)

    def test_over_max_rows_truncates(self):
        """截断边界：行数 = max_rows+1 → 截断至 max_rows，truncated=True。"""
        r = self._exec({"allow_all_output": 0, "max_rows": 5}, 6)
        self.assertEqual(r.total, 5)
        self.assertIs(r.truncated, True)

    def test_multi_resultset_independent(self):
        """多结果集：各结果集独立截断，任一超限即整体标记。"""
        results = [
            {"columns": ["a"], "rows": [(i,) for i in range(10)]},
            {"columns": ["b"], "rows": [(i,) for i in range(3)]},
        ]
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = results
            r = report.execute_report(
                1, "SELECT 1", {"host": "h"},
                report={"allow_all_output": 0, "max_rows": 5})
        self.assertEqual(r.results[0]["total"], 5)
        self.assertEqual(r.results[0]["rows"][-1][0], 4)
        self.assertEqual(r.results[1]["total"], 3)
        self.assertIs(r.truncated, True)

    def test_allow_all_output_one_no_truncation(self):
        """开关开启（allow_all_output=1）→ 超限也不截断。"""
        r = self._exec({"allow_all_output": 1, "max_rows": 5}, 10)
        self.assertEqual(r.total, 10)
        self.assertIsNone(r.truncated)

    def test_legacy_report_no_fields_no_truncation(self):
        """存量报表（缺两字段）→ 按存量语义不截断（契约不破坏）。"""
        r = self._exec({"prefer_cache": 0}, 10)
        self.assertEqual(r.total, 10)
        self.assertIsNone(r.truncated)

    def test_naked_call_no_truncation(self):
        """裸调用（report=None，测试等）→ 不截断，历史契约。"""
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [(i,) for i in range(10)]}]
            r = report.execute_report(1, "SELECT 1", {"host": "h"})
        self.assertEqual(r.total, 10)
        self.assertIsNone(r.truncated)

    def test_max_rows_zero_no_truncation(self):
        """max_rows=0 → 视为未配置，不截断（DB 层防御非法值）。"""
        r = self._exec({"allow_all_output": 0, "max_rows": 0}, 10)
        self.assertEqual(r.total, 10)
        self.assertIsNone(r.truncated)

    def test_max_rows_negative_no_truncation(self):
        """max_rows 负数 → 视为未配置，不截断。"""
        r = self._exec({"allow_all_output": 0, "max_rows": -1}, 10)
        self.assertEqual(r.total, 10)
        self.assertIsNone(r.truncated)


# ===================================================================
# 缓存交互：写缓存前截断 / 标记传递 / 陈旧缓存兜底
# ===================================================================


class TestMaxRowsCache(unittest.TestCase):
    """截断与缓存协同（PH-06 决策：缓存即截断快照 + 读取兜底）。"""

    def test_cache_stores_truncated_snapshot(self):
        """写缓存前截断：缓存条目行数=max_rows；二次调用（缓存命中）仍截断且无新查询。"""
        cache = report.QueryCache()
        cfg = {"allow_all_output": 0, "max_rows": 5}
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [(i,) for i in range(10)]}]
            r1 = report.execute_report(1, "SELECT 1", {"host": "h"},
                                       report=cfg, cache=cache)
        self.assertEqual(r1.total, 5)
        self.assertIs(r1.truncated, True)
        cached = cache.get(1, "SELECT 1")
        self.assertEqual(len(cached.results[0]["rows"]), 5, "缓存=截断快照（省内存）")
        self.assertIs(cached.truncated, True)

        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            r2 = report.execute_report(1, "SELECT 1", {"host": "h"},
                                       report=cfg, cache=cache)
            mock_query.assert_not_called()  # 缓存命中不发起查询
        self.assertEqual(r2.total, 5)
        self.assertIs(r2.truncated, True, "缓存命中也保留截断标记")

    def test_stale_full_cache_truncated_on_read(self):
        """陈旧全量缓存（全量配置下写入，truncated=False）：读取按当前配置截断并置位。"""
        cache = report.QueryCache()
        big = [{"columns": ["c"], "rows": [(i,) for i in range(10)]}]
        cache.set(1, big, "SELECT 1")
        cfg = {"allow_all_output": 0, "max_rows": 5}
        r = report.execute_report(1, "SELECT 1", {"host": "h"},
                                  report=cfg, cache=cache)
        self.assertEqual(r.total, 5)
        self.assertIs(r.truncated, True)
        self.assertEqual(len(big[0]["rows"]), 10, "兜底截断不污染缓存条目")

    def test_cache_switch_on_discards_truncated_cache(self):
        """开关切回开启（allow_all_output=1，PH-07）：丢弃截断缓存，重新查询全量。

        PH-06 时截断缓存直接展示（数据缺失）；PH-07 起截断标记参与缓存策略
        校验，SQL 未变导致缓存 key 不变时也能避免命中截断旧数据。
        """
        cache = report.QueryCache()
        cache.set(1, [{"columns": ["c"], "rows": [(i,) for i in range(5)]}],
                  "SELECT 1", truncated=True)
        with patch("db.create_mysql_connection") as mock_conn, \
                patch("db.execute_mysql_query") as mock_query:
            mock_conn.return_value = MagicMock()
            mock_query.return_value = [{"columns": ["c"], "rows": [(i,) for i in range(10)]}]
            r = report.execute_report(1, "SELECT 1", {"host": "h"},
                                      report={"allow_all_output": 1, "max_rows": 5},
                                      cache=cache)
        self.assertEqual(r.total, 10, "重新查询取回全量数据")
        self.assertIsNone(r.truncated, "全量输出无截断标记")

    def test_cache_switch_off_keeps_full_cache_reduced(self):
        """开关切回关闭（allow_all_output=0）：全量缓存数据按当前 max_rows 截断展示。"""
        cache = report.QueryCache()
        cache.set(1, [{"columns": ["c"], "rows": [(i,) for i in range(10)]}],
                  "SELECT 1")
        r = report.execute_report(1, "SELECT 1", {"host": "h"},
                                  report={"allow_all_output": 0, "max_rows": 5},
                                  cache=cache)
        self.assertEqual(r.total, 5)
        self.assertIs(r.truncated, True)
        self.assertEqual(len(cache.get(1, "SELECT 1").results[0]["rows"]), 10,
                         "读取兜底截断不污染缓存条目")


# ===================================================================
# ReportResult / ReportSnapshot 契约兼容
# ===================================================================


class TestTruncatedContract(unittest.TestCase):
    """truncated 扩展字段的缺省兼容。"""

    def test_report_result_truncated_default_none(self):
        """ReportResult 不传 truncated → 缺省 None（旧式构造不破坏）。"""
        rr = ReportResult(columns=["c"], rows=[("v",)], total=1,
                          page=1, page_size=20)
        self.assertIsNone(rr.truncated)
        rr2 = ReportResult([{"columns": ["c"], "rows": [("v",)], "total": 1}])
        self.assertIsNone(rr2.truncated)

    def test_report_result_truncated_explicit(self):
        """ReportResult 传 truncated=True → 保留。"""
        rr = ReportResult([{"columns": ["c"], "rows": [("v",)], "total": 1}],
                          truncated=True)
        self.assertIs(rr.truncated, True)

    def test_snapshot_roundtrip_truncated(self):
        """ReportSnapshot 序列化往返保留 truncated。"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["c"], "rows": [("v",)]}],
            sql_query="SELECT 1", updated_at=1.0, config_version="v",
            truncated=True)
        snap2 = redis_cache.ReportSnapshot.from_json(snap.to_json())
        self.assertIs(snap2.truncated, True)

    def test_snapshot_from_json_without_truncated(self):
        """旧快照 JSON（无 truncated 字段）→ 缺省 False（向后兼容）。"""
        snap = redis_cache.ReportSnapshot.from_json(
            '{"results": [], "sql_query": "SELECT 1", '
            '"updated_at": 1.0, "config_version": "v"}')
        self.assertFalse(snap.truncated)


if __name__ == "__main__":
    unittest.main()
