"""
tests/test_export_cache_path.py — 导出复用 execute_report（C-4）

背景：
    性能基线（spec §10.2 第 2 条）测出导出是全站最大热点（1519.7ms，
    第二名的 15 倍），根因是 `export.py:_load_and_transform` 直接
    `create_mysql_connection` + `execute_mysql_query`，**完全不经过
    L1/L2/L3 三层缓存**。而 API 路径（api_handler.py:454）早就在用
    `execute_report`，导出是唯一异类。

**本任务的第一风险不是性能，是安全护栏**：
    `execute_report` 的全量输出护栏（allow_all_output / max_rows）由
    `report` 参数驱动——传 None 则护栏恒失效。所以「report 参数确实是
    report_config」必须被断言钉死，不能靠人记得传。

本文件不修改 `report.execute_report`，只断言「导出正确地调用它」。
"""

import unittest
from unittest.mock import patch, MagicMock

import export
from report import ReportResult


POOL = {"host": "h", "port": 3306, "user": "u",
        "password": "p", "database": "d"}

REPORT_CFG = {"name": "报表E", "sql_query": "SELECT * FROM t", "pool_id": 1,
              "prefer_cache": 0, "cache_ttl_hours": 0,
              "allow_write": 1, "allow_all_output": 1, "max_rows": 0}


def _report_result(rows, columns=("id", "v"), truncated=None, index=0):
    """构造与 execute_report 返回结构一致的 ReportResult。"""
    return ReportResult(
        [{"columns": list(columns), "rows": rows}],
        active_index=index, page=1, page_size=100,
        cache_info={"source": "process"}, truncated=truncated)


class TestExportUsesExecuteReport(unittest.TestCase):
    """新路径：report_id 存在时走 execute_report（吃缓存）。"""

    @patch("export.report.execute_report")
    def test_export_uses_execute_report(self, mock_exec):
        """✅ Positive: 传了 report_id → 调 execute_report 而不是自己连 MySQL。"""
        mock_exec.return_value = _report_result([(1, "a"), (2, "b")])

        with patch("export.db.create_mysql_connection") as mock_conn:
            out = export.export_report_to_csv(
                "SELECT * FROM t", POOL, report_id=7, report_config=REPORT_CFG)

        mock_exec.assert_called_once()
        mock_conn.assert_not_called()
        self.assertIn('"1"', out)   # QUOTE_ALL，数据确实被序列化
        self.assertIn('"2"', out)

    @patch("export.report.execute_report")
    def test_passes_report_config_so_max_rows_guard_stays_on(self, mock_exec):
        """✅ 安全护栏：report 参数必须是 report_config，不能是 None。

        execute_report 的 limit_rows = report is not None and
        not allow_all_output and max_rows>0。传 None 等于护栏永久失效。
        """
        mock_exec.return_value = _report_result([(1, "a")])
        cfg = dict(REPORT_CFG, allow_all_output=0, max_rows=50)

        export.export_report_to_csv("SELECT * FROM t", POOL,
                                    report_id=7, report_config=cfg)

        kwargs = mock_exec.call_args.kwargs
        self.assertIs(kwargs["report"], cfg,
                      "全量输出护栏依赖 report 参数，不能传 None")
        self.assertEqual(kwargs["allow_all_output"] if "allow_all_output"
                         in kwargs else cfg["allow_all_output"], 0)

    @patch("export.report.execute_report")
    def test_all_rows_page_size_sentinel(self, mock_exec):
        """✅ Positive: page_size 传超大哨兵值，保证返回全量行。"""
        mock_exec.return_value = _report_result([(1, "a")])

        export.export_report_to_csv("SELECT * FROM t", POOL,
                                    report_id=7, report_config=REPORT_CFG)

        kwargs = mock_exec.call_args.kwargs
        self.assertEqual(kwargs["page"], 1)
        self.assertGreaterEqual(kwargs["page_size"], 10 ** 9)
        self.assertEqual(kwargs["page_size"],
                         export._EXPORT_ALL_ROWS_PAGE_SIZE)

    @patch("export.report.execute_report")
    def test_read_timeout_not_passed(self, mock_exec):
        """✅ Positive: 导出不设查询超时（与改前一致，read_timeout 不传）。"""
        mock_exec.return_value = _report_result([(1, "a")])

        export.export_report_to_csv("SELECT * FROM t", POOL,
                                    report_id=7, report_config=REPORT_CFG)

        self.assertNotIn("read_timeout", mock_exec.call_args.kwargs)

    @patch("export.report.execute_report")
    def test_filters_and_sorts_passed_through(self, mock_exec):
        """✅ Positive: 筛选/排序原样透传（execute_report 内部会应用）。"""
        mock_exec.return_value = _report_result([(1, "a")])
        filters = [("v", "contains", "a")]
        sorts = [("id", "desc")]

        export.export_report_to_csv("SELECT * FROM t", POOL, filters,
                                    None, 0, sorts,
                                    report_id=7, report_config=REPORT_CFG)

        kwargs = mock_exec.call_args.kwargs
        self.assertEqual(kwargs["filters"], filters)
        self.assertEqual(kwargs["sorts"], sorts)


class TestExportLegacyPathPreserved(unittest.TestCase):
    """旧路径：report_id 为 None 时行为完全不变（向后兼容）。"""

    @patch("export.report.execute_report")
    @patch("export.db.execute_mysql_query")
    @patch("export.db.create_mysql_connection")
    def test_without_report_id_keeps_legacy_path(self, mock_conn, mock_query,
                                                 mock_exec):
        """✅ Positive: report_id=None → 仍走自带连接，不调 execute_report。"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,), (2,)]}]
        mock_conn.return_value = MagicMock()

        out = export.export_report_to_csv("SELECT * FROM t", POOL)

        mock_exec.assert_not_called()
        mock_conn.assert_called_once()
        self.assertIn('"1"', out)

    @patch("export.report.execute_report")
    @patch("export.db.execute_mysql_query")
    @patch("export.db.create_mysql_connection")
    def test_legacy_path_still_applies_filters(self, mock_conn, mock_query,
                                               mock_exec):
        """✅ Positive: 旧路径的筛选/排序行为未被新分支影响。"""
        mock_query.return_value = [{"columns": ["id", "v"],
                                    "rows": [(1, "a"), (2, "b")]}]
        mock_conn.return_value = MagicMock()

        out = export.export_report_to_csv(
            "SELECT * FROM t", POOL, [("v", "eq", "a")], None, 0, None)

        mock_exec.assert_not_called()
        self.assertIn('"1"', out)
        self.assertNotIn('"2"', out)


class TestExportTruncationFlag(unittest.TestCase):
    """截断标记来自 ReportResult.truncated，驱动尾注与响应头。"""

    @patch("export.report.execute_report")
    def test_truncated_flag_drives_tail_note(self, mock_exec):
        """✅ Positive: truncated=True → 输出末尾追加截断说明。"""
        mock_exec.return_value = _report_result([(1, "a")], truncated=True)
        sink = []

        out = export.export_report_to_csv(
            "SELECT * FROM t", POOL, max_rows=50, _truncated_out=sink,
            report_id=7, report_config=dict(REPORT_CFG, allow_all_output=0,
                                            max_rows=50))

        self.assertIn("# 注意：查询结果超过 50 行上限", out)
        self.assertEqual(sink, [True])

    @patch("export.report.execute_report")
    def test_not_truncated_has_no_tail_note(self, mock_exec):
        """✅ Positive: 未截断 → 无尾注，_truncated_out 不被写。"""
        mock_exec.return_value = _report_result([(1, "a")], truncated=False)
        sink = []

        out = export.export_report_to_csv(
            "SELECT * FROM t", POOL, max_rows=50, _truncated_out=sink,
            report_id=7, report_config=REPORT_CFG)

        self.assertNotIn("# 注意", out)
        self.assertEqual(sink, [])


class TestExportMultiResultClamp(unittest.TestCase):
    """多结果集：result_index 越界回退 0（与改前一致）。"""

    @patch("export.report.execute_report")
    def test_result_index_clamped(self, mock_exec):
        """✅ Positive: result_index 越界 → 取第 0 个结果集。"""
        mock_exec.return_value = ReportResult(
            [{"columns": ["id"], "rows": [(1,)]},
             {"columns": ["id"], "rows": [(2,), (3,)]}],
            active_index=1, page=1, page_size=100)

        out = export.export_report_to_csv("SELECT * FROM t", POOL, None,
                                          None, 99, None,
                                          report_id=7,
                                          report_config=REPORT_CFG)

        self.assertIn('"1"', out)
        self.assertNotIn('"2"', out)

    @patch("export.report.execute_report")
    def test_result_index_selects_requested_set(self, mock_exec):
        """✅ Positive: result_index 合法 → 取指定结果集。"""
        mock_exec.return_value = ReportResult(
            [{"columns": ["id"], "rows": [(1,)]},
             {"columns": ["id"], "rows": [(2,), (3,)]}],
            active_index=1, page=1, page_size=100)

        out = export.export_report_to_csv("SELECT * FROM t", POOL, None,
                                          None, 1, None,
                                          report_id=7,
                                          report_config=REPORT_CFG)

        self.assertIn('"2"', out)
        self.assertIn('"3"', out)
        self.assertNotIn('"1"', out)


class TestExportColumnProjectionPreserved(unittest.TestCase):
    """列投影（导出特有）不能因为走缓存而丢失。"""

    @patch("export.report.execute_report")
    def test_custom_columns_still_projected(self, mock_exec):
        """✅ Positive: 自定义列顺序与筛选在两条路径上都生效。"""
        mock_exec.return_value = _report_result([(1, "a"), (2, "b")],
                                                columns=("id", "v"))

        out = export.export_report_to_csv("SELECT * FROM t", POOL, None,
                                          ["v"], 0, None,
                                          report_id=7,
                                          report_config=REPORT_CFG)

        header = out.splitlines()[0]
        self.assertIn("v", header)
        self.assertNotIn("id", header)


if __name__ == "__main__":
    unittest.main()
