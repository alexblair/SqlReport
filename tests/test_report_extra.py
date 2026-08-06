"""
test_report_extra.py — 报表执行与预览域补充测试（T3 批次）

覆盖缺口清单（编号对应批次说明）：
1.  refresh=1 预填 + 302 全流程（URL 参数带入表单 → 执行 → 重定向）
2.  refresh 预填失败时降级（缺参数、非法参数）
3.  refresh 与静态缓存联动（URL 参数参与缓存键或失效）
4.  is_preview 时跳过 Redis 写入（预览不应污染缓存）
5.  预览失败展示（SQL 错误时预览页渲染错误信息而非崩溃）
6.  预览分页/筛选/排序参数可用性
7.  多结果集执行语义（execute_report 返回多结果集时的组织方式）
8.  多结果集 tab 独立筛选/排序
9.  active_index=-1 哨兵行为（URL 参数）
10. parse_result_index 非法值（非数字、越界）回退
11. parse_result_names 补齐/截断
12. Redis 快照命中路径（execute_report 层：缓存命中直接返回）
13. Redis 回退路径（redis_fallback）
14. 锁等待路径（cache 锁占用时行为）
15. page/page_size 为 None 时直传默认
16. page/page_size 非数字 URL 参数
17. render_report_page page_size<1 处理
18. applyRulesJson JS 契约（已知缺陷测试：前端 s_ 前缀与后端 sort/dir 契约不一致）
19. 分类树深层级递归与环保护（环 = 已知缺陷测试）
20. 报表选择页分类跳转链接 href 正确性（含中文/特殊字符分类名编码）
21. contains 空值筛选行为
22. 进程缓存 SQL 不匹配时物理逐出
23. 预览缺 id=abc（无效报表 id 的预览）
24. API 区渲染异常降级（render 报错时页面仍可出）
25. 正式报表页无预览 badge、预览页有预览 badge
26. preview result_names_override 参数
27. page_url_base 死参数（仅报告，不测）

已知缺陷测试以 docstring 标注"已知缺陷"：断言期望安全行为，
当前实现不满足 → 测试失败即暴露缺陷（详见批次回传报告）。
"""

import unittest
from unittest.mock import patch, MagicMock

import report
import config_db
import redis_cache
from render import _COMMON_JS
from tests import BaseReportTest


# ===================================================================
# 缺口 1/2/3：refresh 预填 + 302 全流程、降级、静态缓存联动
# ===================================================================

class TestRefreshPrefillFlow(BaseReportTest):
    """refresh=1 预填缓存 + 302 重定向全流程"""

    def setUp(self):
        super().setUp()
        report._query_cache.clear()

    def tearDown(self):
        report._query_cache.clear()
        super().tearDown()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_refresh_302_and_prefill(self, mock_conn_f, mock_query):
        """1. refresh=1 → 302 且 Location 剔除 refresh；预填后无 refresh 请求命中缓存不重查"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,), (2,)]}]
        mock_conn_f.return_value = MagicMock()

        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&refresh=1")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/report?id=1")
        self.assertNotIn("refresh", body)
        self.assertEqual(mock_query.call_count, 1, "refresh 预填应真实执行一次查询")

        code2, body2, _ = report.handle_request(self.conn, "GET", "/report", "id=1")
        self.assertEqual(code2, 200)
        self.assertIn("测试报表", body2)
        self.assertIn("<td>1</td>", body2)
        self.assertIn("<td>2</td>", body2)
        self.assertEqual(mock_query.call_count, 1, "预填后的请求应命中进程缓存")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_refresh_preserves_other_params_in_redirect(self, mock_conn_f, mock_query):
        """1. 302 Location 保留 sort/filters/cols 等 URL 参数（URL 参数带入预填）"""
        mock_query.return_value = [{"columns": ["id", "name"], "rows": [(1, "Alice")]}]
        mock_conn_f.return_value = MagicMock()

        code, body, _ = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&refresh=1&sort=name&dir=asc&f_name=ali&cols=id,name")
        self.assertEqual(code, 302)
        for piece in ("id=1", "sort=name", "dir=asc", "f_name=ali", "cols=id%2Cname"):
            self.assertIn(piece, body, f"302 Location 应保留参数 {piece}")
        self.assertNotIn("refresh", body)

    def test_refresh_missing_pool_falls_back_302(self):
        """2. refresh=1 但关联连接池已删除 → 跳过预填仍 302（不崩溃）"""
        self.conn.execute("DELETE FROM connection_pools")
        self.conn.commit()
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&refresh=1")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/report?id=1")

    def test_refresh_missing_report_falls_back_302(self):
        """2. refresh=1 但报表不存在 → 不预填仍 302"""
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=999&refresh=1")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/report?id=999")

    @patch("report.execute_report")
    def test_refresh_prefill_failure_still_302(self, mock_exec):
        """2. 预填执行失败（MySQL 异常）→ 降级为 warning，仍 302"""
        mock_exec.side_effect = Exception("MySQL 连接超时")
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&refresh=1")
        self.assertEqual(code, 302)

    @patch("report.execute_report")
    def test_refresh_invalid_value_renders_normally(self, mock_exec):
        """2. refresh=2（非 TRUTHY 值）→ 不重定向，正常渲染且 refresh=False"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&refresh=2")
        self.assertEqual(code, 200)
        self.assertIn("测试报表", body)
        self.assertFalse(mock_exec.call_args[0][7], "refresh=2 应解析为 False")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.config_db.invalidate_api_static_cache_by_report")
    def test_refresh_invalidates_api_static_cache(self, mock_inv, mock_conn_f, mock_query):
        """3. refresh=1 预填时联动删除该报表全部 API 端点静态缓存"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&refresh=1")
        self.assertEqual(code, 302)
        mock_inv.assert_called_once_with(self.conn, 1)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.config_db.invalidate_api_static_cache_by_report")
    def test_refresh_no_conn_skips_static_invalidation(self, mock_inv, mock_conn_f, mock_query):
        """3. conn 为 None 时跳过静态缓存联动（不崩溃）"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        report.execute_report(
            1, "SELECT * FROM test_table", {"host": "h"}, refresh=True,
            report={"prefer_cache": 1, "cache_ttl_hours": 0,
                    "sql_query": "SELECT * FROM test_table", "pool_id": 1},
            conn=None)
        mock_inv.assert_not_called()


# ===================================================================
# 缺口 4/12/13/14：Redis 快照命中、回退、锁等待、is_preview
# ===================================================================

class TestExecuteReportRedisPaths(unittest.TestCase):
    """execute_report 层的 Redis 缓存路径"""

    def setUp(self):
        report._query_cache.clear()
        self.pool = {"host": "h", "port": 3306, "user": "u",
                     "password": "p", "database": "d"}
        self.report_cfg = {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": 1,
                           "sql_query": "SELECT saved", "name": "R",
                           "memo": "", "result_names": ""}

    def tearDown(self):
        report._query_cache.clear()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_redis_snapshot_hit_skips_mysql(self, mock_avail, mock_mgr_f,
                                            mock_conn_f, mock_query):
        """12. Redis 快照命中 → 直接返回快照数据，不查 MySQL，进程缓存标注 redis 来源"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(10,)]}],
            sql_query="SELECT saved", updated_at=123.0, config_version="v1")
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = snap
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows, [(10,)])
        mock_query.assert_not_called()
        self.assertEqual(result.cache_info["source"], "redis")
        cached = report._query_cache.get(1)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.source, "redis")
        self.assertEqual(cached.source_timestamp, 123.0)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_mysql_failure_falls_back_to_stale_snapshot(self, mock_avail, mock_mgr_f,
                                                        mock_conn_f, mock_query):
        """13. MySQL 查询失败 → 兜底读过期 Redis 快照（redis_fallback，不抛异常）"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(99,)]}],
            sql_query="SELECT saved", updated_at=1.0, config_version="v1")
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.side_effect = [None, snap]
        mock_mgr_f.return_value = mock_mgr
        mock_conn_f.return_value = MagicMock()
        mock_query.side_effect = RuntimeError("MySQL 连接失败")

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        self.assertEqual(result.rows, [(99,)])
        self.assertEqual(result.cache_info["source"], "redis_fallback")
        self.assertFalse(result.cache_info["fresh"])

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_lock_wait_reloads_snapshot(self, mock_avail, mock_mgr_f,
                                        mock_conn_f, mock_query):
        """14. 锁被占用 → wait_for_lock 等待后重新读取 Redis 快照（不再查 MySQL）"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(7,)]}],
            sql_query="SELECT saved", updated_at=2.0, config_version="v1")
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.acquire_lock.return_value = False
        mock_mgr.wait_for_lock.return_value = True
        mock_mgr.get_snapshot.side_effect = [None, snap]
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        self.assertEqual(result.rows, [(7,)])
        mock_mgr.wait_for_lock.assert_called_once()
        mock_query.assert_not_called()
        self.assertEqual(result.cache_info["source"], "redis")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_preview_sql_does_not_write_redis(self, mock_avail, mock_mgr_f,
                                              mock_conn_f, mock_query):
        """4. is_preview（SQL 与保存不一致）→ 不写 Redis 快照"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = None
        mock_mgr.acquire_lock.return_value = True
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT preview", self.pool, report=self.report_cfg)

        mock_mgr.set_snapshot.assert_not_called()
        self.assertEqual(result.cache_info["source"], "mysql")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_saved_sql_writes_redis_snapshot(self, mock_avail, mock_mgr_f,
                                             mock_conn_f, mock_query):
        """4. 非预览（SQL 与保存一致）→ 写 Redis 快照"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = None
        mock_mgr.acquire_lock.return_value = True
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        mock_mgr.set_snapshot.assert_called_once()
        self.assertEqual(result.cache_info["source"], "redis")
        self.assertTrue(result.cache_info["fresh"])

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_lock_released_when_mysql_fails_without_fallback(self, mock_avail, mock_mgr_f,
                                                             mock_conn_f, mock_query):
        """14. MySQL 失败且无兜底快照时也应释放 Redis 锁（修复：try/finally 覆盖 raise 路径）

        修复前：report.py:849 `raise` 直接抛出，绕过 release_lock，
        锁仅靠 30s TTL 过期 → 后续请求在 wait_for_lock 阻塞最多 60s。
        """
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = None
        mock_mgr.acquire_lock.return_value = True
        mock_mgr_f.return_value = mock_mgr
        mock_conn_f.return_value = MagicMock()
        mock_query.side_effect = RuntimeError("MySQL 连接失败")

        with self.assertRaises(RuntimeError):
            report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        mock_mgr.release_lock.assert_called_once()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_lock_wait_hit_snapshot_releases_lock(self, mock_avail, mock_mgr_f,
                                                  mock_conn_f, mock_query):
        """14. 锁等待后命中 Redis 快照路径不泄漏锁（lock_held=True → finally 释放）"""
        snap = redis_cache.ReportSnapshot(
            results=[{"columns": ["id"], "rows": [(8,)]}],
            sql_query="SELECT saved", updated_at=3.0, config_version="v1")
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.acquire_lock.return_value = False
        mock_mgr.wait_for_lock.return_value = True
        mock_mgr.get_snapshot.side_effect = [None, snap]
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        self.assertEqual(result.rows, [(8,)])
        mock_mgr.release_lock.assert_called_once()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    @patch("report.redis_cache.get_redis_manager")
    @patch("report.redis_cache.redis_available", return_value=True)
    def test_lock_wait_timeout_does_not_release_foreign_lock(self, mock_avail, mock_mgr_f,
                                                             mock_conn_f, mock_query):
        """14. wait_for_lock 超时未获锁（他人仍持锁）→ 不误删他人持有的锁"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(5,)]}]
        mock_conn_f.return_value = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.key_prefix = "sr"
        mock_mgr.get_snapshot.return_value = None
        mock_mgr.acquire_lock.return_value = False
        mock_mgr.wait_for_lock.return_value = False
        mock_mgr_f.return_value = mock_mgr

        result = report.execute_report(1, "SELECT saved", self.pool, report=self.report_cfg)

        self.assertEqual(result.rows, [(5,)], "等待锁超时后应直查 MySQL")
        mock_mgr.release_lock.assert_not_called()


# ===================================================================
# 缺口 7/8/9/10/11：多结果集执行语义与索引/名称解析
# ===================================================================

class TestMultiResultSetExecution(unittest.TestCase):
    """execute_report 多结果集组织、独立筛选/排序、active_index 哨兵"""

    def setUp(self):
        report._query_cache.clear()
        self.pool = {"host": "h", "port": 3306, "user": "u",
                     "password": "p", "database": "d"}

    def tearDown(self):
        report._query_cache.clear()

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_pagination_applies_only_to_active_result(self, mock_conn_f, mock_query):
        """7. 只有激活结果集按 page/page_size 切片，其余结果集全量"""
        mock_query.return_value = [
            {"columns": ["id", "name"], "rows": [(i, f"n{i}") for i in range(1, 101)]},
            {"columns": ["id", "age"], "rows": [(i, 20 + i) for i in range(1, 11)]},
        ]
        mock_conn_f.return_value = MagicMock()

        result = report.execute_report(1, "SELECT multi", self.pool,
                                       page=1, page_size=10, active_index=1)

        self.assertEqual(len(result.results), 2)
        self.assertEqual(len(result.results[0]["rows"]), 100, "非激活结果集应全量")
        self.assertEqual(len(result.results[1]["rows"]), 10, "激活结果集按 page_size 切片")
        self.assertEqual(result.columns, ["id", "age"])
        self.assertEqual(result.rows, [(i, 20 + i) for i in range(1, 11)])

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_active_result_page_sliced(self, mock_conn_f, mock_query):
        """7. 激活结果集第二页切片正确"""
        mock_query.return_value = [
            {"columns": ["id"], "rows": [(i,) for i in range(1, 26)]},
            {"columns": ["id"], "rows": [(i,) for i in range(51, 76)]},
        ]
        mock_conn_f.return_value = MagicMock()

        result = report.execute_report(1, "SELECT multi", self.pool,
                                       page=2, page_size=10, active_index=0)

        self.assertEqual(len(result.results[0]["rows"]), 10)
        self.assertEqual(result.results[0]["rows"][0], (11,))
        self.assertEqual(len(result.results[1]["rows"]), 25)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_filters_sorted_independently_per_resultset(self, mock_conn_f, mock_query):
        """8. 筛选/排序对每个结果集独立应用（列不存在的结果集跳过该筛选）"""
        mock_query.return_value = [
            {"columns": ["id", "name"], "rows": [(1, "Alice"), (2, "Bob")]},
            {"columns": ["id", "age"], "rows": [(1, 30), (2, 25)]},
        ]
        mock_conn_f.return_value = MagicMock()

        result = report.execute_report(
            1, "SELECT multi", self.pool,
            filters=[("name", "contains", "ali")],
            sorts=[("id", "desc")], active_index=1)

        self.assertEqual(result.results[0]["total"], 1, "含 name 列的结果集被过滤")
        self.assertEqual(result.results[0]["rows"], [(1, "Alice")])
        self.assertEqual(result.results[1]["total"], 2, "无 name 列的结果集不过滤")
        self.assertEqual(result.results[1]["rows"], [(2, 25), (1, 30)],
                         "id desc 排序对无过滤的结果集仍生效")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_active_index_minus_one_returns_all_rows(self, mock_conn_f, mock_query):
        """9. active_index=-1 哨兵 → 所有结果集统一分页（全览模式，不区分激活集）"""
        mock_query.return_value = [
            {"columns": ["id"], "rows": [(i,) for i in range(1, 26)]},
            {"columns": ["id"], "rows": [(i,) for i in range(101, 126)]},
        ]
        mock_conn_f.return_value = MagicMock()

        result = report.execute_report(1, "SELECT all", self.pool,
                                       page=1, page_size=5, active_index=-1)

        self.assertEqual(result.results[0]["rows"], [(1,), (2,), (3,), (4,), (5,)],
                         "active_index=-1 时每个结果集都按当前页切片")
        self.assertEqual(result.results[1]["rows"], [(101,), (102,), (103,), (104,), (105,)])
        self.assertEqual(result.results[0]["total"], 25, "total 保持全量行数")
        self.assertEqual(result.results[1]["total"], 25)

        result_page2 = report.execute_report(1, "SELECT all", self.pool,
                                             page=2, page_size=5, active_index=-1)
        self.assertEqual(result_page2.results[0]["rows"], [(6,), (7,), (8,), (9,), (10,)],
                         "page=2 时切片前进")

    def test_parse_result_index_negative_clamped_to_zero(self):
        """9. URL result=-1 被 clamp 为 0（哨兵不通过 URL 暴露）"""
        self.assertEqual(report.parse_result_index({"result": ["-1"]}), 0)
        self.assertEqual(report.parse_result_index({"result": ["-5"]}), 0)

    def test_parse_result_index_non_numeric_falls_back(self):
        """10. result=abc → 回退 default（默认 0）"""
        self.assertEqual(report.parse_result_index({"result": ["abc"]}), 0)
        self.assertEqual(report.parse_result_index({"result": ["abc"]}, default=2), 2)

    def test_parse_result_index_missing_or_empty(self):
        """10. 缺 key / 空值 → 回退 default"""
        self.assertEqual(report.parse_result_index({}), 0)
        self.assertEqual(report.parse_result_index({"result": [""]}), 0)
        # {"result": []} 空列表会在 parse_result_index 触发 IndexError
        # （report.py:248 qs[key][0]）；真实 URL/表单解析（parse_qs）不会产生
        # 空列表值，仅手工构造 dict 可触发，不可达故不测。

    def test_parse_result_names_pad_when_fewer(self):
        """11. names 少于 count → 自动补"结果{i+1}" """
        self.assertEqual(report.parse_result_names("日报\n月报", 3),
                         ["日报", "月报", "结果3"])

    def test_parse_result_names_truncate_when_more(self):
        """11. names 多于 count → 截断"""
        self.assertEqual(report.parse_result_names("a\nb\nc\nd", 2), ["a", "b"])

    def test_parse_result_names_blank_lines_skipped(self):
        """11. 空行剔除 + 补齐"""
        self.assertEqual(report.parse_result_names("a\n\nb\n", 4),
                         ["a", "b", "结果3", "结果4"])

    def test_parse_result_names_no_count(self):
        """11. count=None → 原样返回（剔空行）"""
        self.assertEqual(report.parse_result_names("a\nb"), ["a", "b"])
        self.assertEqual(report.parse_result_names(""), [])


class TestOutOfRangeResultIndex(BaseReportTest):
    """缺口 10：越界 result 的页面级回退（已知缺陷测试）"""

    @patch("report.execute_report")
    def test_out_of_range_result_index_renders_safely(self, mock_exec):
        """10. result=99 越界（仅 1 个结果集）→ 页面应安全渲染而非崩溃（修复：上界 clamp 到 0）"""
        mock_exec.return_value = report.ReportResult(
            results=[{"columns": ["id"], "rows": [(1,)], "total": 1}],
            active_index=99, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&result=99",
            pool_override={"host": "h"})
        self.assertEqual(code, 200)
        self.assertIn("测试报表", body)
        self.assertIn("<td>1</td>", body)

    @patch("report.execute_report")
    def test_empty_result_set_renders_safely(self, mock_exec):
        """10. 空结果集（len==0）→ 页面安全渲染而非 IndexError 500"""
        mock_exec.return_value = report.ReportResult(
            results=[], active_index=0, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", "id=1&result=0",
            pool_override={"host": "h"})
        self.assertEqual(code, 200)
        self.assertIn("测试报表", body)

    def test_execute_report_clamps_out_of_range_active_index(self):
        """10. execute_report 层对越界 active_index 做上界 clamp（保留 -1 哨兵）"""
        from unittest.mock import MagicMock as MM
        with patch("report.db.execute_mysql_query") as mock_query, \
                patch("report.db.create_mysql_connection") as mock_conn_f:
            mock_query.return_value = [
                {"columns": ["id"], "rows": [(1,)]},
                {"columns": ["name"], "rows": [("A",)]},
            ]
            mock_conn_f.return_value = MM()
            result = report.execute_report(1, "SELECT multi", {"host": "h"},
                                           active_index=99)
        self.assertEqual(result.active_index, 1, "越界 99 → clamp 到 len(results)-1")
        self.assertEqual(result.columns, ["name"])


# ===================================================================
# 缺口 15/16/17：page/page_size 默认值与非法值
# ===================================================================

class TestPageSizeParameters(BaseReportTest):
    """page/page_size 默认值与非法值处理"""

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_execute_report_none_page_defaults(self, mock_conn_f, mock_query):
        """15. page=None → 1；page_size=None → 20（直传默认）"""
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        result = report.execute_report(1, "SELECT 1", {"host": "h"},
                                       page=None, page_size=None)
        self.assertEqual(result.page, 1)
        self.assertEqual(result.page_size, 20)

    @patch("report.execute_report")
    def test_non_numeric_page_size_uses_default(self, mock_exec):
        """16. page_size=abc（非数字）→ 使用报表 default_page_size"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1&page_size=abc")
        self.assertEqual(code, 200)
        self.assertEqual(mock_exec.call_args[0][4], 20)

    @patch("report.execute_report")
    def test_page_size_zero_clamped_to_one(self, mock_exec):
        """16. page_size=0 → handle_request clamp 为 1"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=1)
        report.handle_request(self.conn, "GET", "/report", "id=1&page_size=0")
        self.assertEqual(mock_exec.call_args[0][4], 1)

    @patch("report.execute_report")
    def test_non_numeric_page_defaults_to_one(self, mock_exec):
        """16. page=abc（非数字）→ 1"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        report.handle_request(self.conn, "GET", "/report", "id=1&page=abc")
        self.assertEqual(mock_exec.call_args[0][3], 1)

    @patch("report.execute_report")
    def test_render_page_size_less_than_one_uses_default(self, mock_exec):
        """17. render_report_page(page_size=0 / -3) → 回退 default_page_size"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        report.render_report_page(self.conn, 1, page_size=0, pool_override={"host": "h"})
        self.assertEqual(mock_exec.call_args[0][4], 20)
        report.render_report_page(self.conn, 1, page_size=-3, pool_override={"host": "h"})
        self.assertEqual(mock_exec.call_args[0][4], 20)


# ===================================================================
# 缺口 5/6/23/25/26：预览端点
# ===================================================================

class TestPreviewEndpointExtended(BaseReportTest):
    """预览端点：失败展示、参数可用性、非法 id、badge、result_names"""

    def setUp(self):
        super().setUp()
        report._query_cache.clear()

    def tearDown(self):
        report._query_cache.clear()
        super().tearDown()

    @patch("report.execute_report")
    def test_preview_sql_error_renders_error_page(self, mock_exec):
        """5. 预览 SQL 执行失败 → 预览页渲染错误信息而非崩溃"""
        mock_exec.side_effect = Exception("SQL 语法错误: near 'FROM'")
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=1&sql_query=SELECT+FROM")
        self.assertEqual(code, 200)
        self.assertIn("查询执行失败", body)
        self.assertIn("SQL 语法错误", body)

    @patch("report.execute_report")
    def test_preview_renders_pagination_and_sort_links(self, mock_exec):
        """6. 预览页分页/排序链接可用（跳转正式报表并保留 result 参数）"""
        mock_exec.return_value = report.ReportResult(
            columns=["id", "name"], rows=[(i, f"n{i}") for i in range(1, 31)],
            total=30, page=1, page_size=10)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=1&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("共 30 行", body)
        self.assertIn('href="/report?id=1&amp;page_size=10', body,
                      "预览页分页链接应指向正式报表页")
        self.assertIn("排序", body)

    def test_preview_missing_id_returns_selector(self):
        """23. 预览缺 id → 返回报表选择页"""
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("选择报表", body)

    def test_preview_invalid_id_returns_selector(self):
        """23. 预览 id=abc → 返回报表选择页（不崩溃）"""
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=abc&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("选择报表", body)

    @patch("report.execute_report")
    def test_preview_id_not_exist_renders_error(self, mock_exec):
        """23. 预览 id 有效数字但报表不存在 → 渲染"报表不存在"错误"""
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=999&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("报表不存在", body)

    @patch("report.execute_report")
    def test_formal_page_has_no_preview_badge(self, mock_exec):
        """25. 正式报表页无预览 badge"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1")
        self.assertEqual(code, 200)
        self.assertNotIn("当前显示的是未保存的临时 SQL", body)

    @patch("report.execute_report")
    def test_preview_page_has_preview_badge(self, mock_exec):
        """25. 预览页有预览 badge"""
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=1&sql_query=SELECT+1")
        self.assertIn("预览模式", body)
        self.assertIn("当前显示的是未保存的临时 SQL", body)

    @patch("report.execute_report")
    def test_preview_result_names_override(self, mock_exec):
        """26. 预览 result_names 覆盖报表配置的结果集名称"""
        mock_exec.return_value = report.ReportResult(
            results=[{"columns": ["id"], "rows": [(1,)], "total": 1},
                     {"columns": ["id"], "rows": [(2,)], "total": 1}],
            active_index=0, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            "id=1&sql_query=SELECT+1&result_names=临时表A%0A临时表B")
        self.assertEqual(code, 200)
        self.assertIn("临时表A", body)
        self.assertIn("临时表B", body)

    @patch("report.execute_report")
    def test_preview_result_names_absent_uses_report_config(self, mock_exec):
        """26. 预览不带 result_names → 使用报表配置中的 result_names"""
        self.conn.execute("UPDATE report_configs SET result_names=? WHERE id=1",
                          ("配置名X\n配置名Y",))
        self.conn.commit()
        mock_exec.return_value = report.ReportResult(
            results=[{"columns": ["id"], "rows": [(1,)], "total": 1},
                     {"columns": ["id"], "rows": [(2,)], "total": 1}],
            active_index=0, page=1, page_size=20)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "", "id=1&sql_query=SELECT+1")
        self.assertIn("配置名X", body)
        self.assertIn("配置名Y", body)


# ===================================================================
# 缺口 18：applyRulesJson JS 契约（已知缺陷测试）
# ===================================================================

class TestApplyRulesJsonContract(unittest.TestCase):
    """applyRulesJson 生成的 URL 参数与后端解析契约的一致性"""

    @staticmethod
    def _extract_js_function(js: str, name: str) -> str:
        start = js.find(f"function {name}(")
        if start < 0:
            return ""
        brace = js.find("{", start)
        depth = 0
        i = brace
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[brace:i + 1]
            i += 1
        return ""

    def test_apply_rules_json_sort_uses_sort_dir_params(self):
        """18. JS 生成排序参数应使用 sort/dir（与后端 parse_sorts 契约一致）"""
        body = self._extract_js_function(_COMMON_JS, "applyRulesJson")
        self.assertTrue(body, "应在 _COMMON_JS 中找到 applyRulesJson 函数")
        self.assertIn("'sort'", body)
        self.assertIn("'dir'", body)
        self.assertNotIn("params.set('s_'", body)

    def test_rules_sort_params_recognized_by_parse_sorts(self):
        """18. 规则应用后生成的 sort/dir 参数应被 parse_sorts 识别并生效（修复：s_ 前缀契约不一致）"""
        rules = {"sorts": [{"col": "name", "dir": "desc"}, {"col": "id", "dir": "asc"}]}
        # 模拟 applyRulesJson 的排序处理逻辑（与 JS 源码一致：sort/dir 成对追加）
        qs = {"sort": [s["col"] for s in rules["sorts"]],
              "dir": [s["dir"] for s in rules["sorts"]]}
        sorts = report.parse_sorts(qs)
        self.assertEqual(sorts, [("name", "desc"), ("id", "asc")])

    def test_rules_filter_params_recognized(self):
        """18. 对照组：筛选规则 f_col/op_col 与后端 parse_filters 一致（应通过）"""
        qs = {"f_name": ["alice"], "op_name": ["contains"],
              "f_age": ["30"], "op_age": ["gt"]}
        filters = report._parse_filters(qs)
        self.assertIn(("name", "contains", "alice"), filters)
        self.assertIn(("age", "gt", "30"), filters)


# ===================================================================
# 缺口 19/20：分类树深层级、环保护、跳转链接
# ===================================================================

class TestCategoryTreeSelector(BaseReportTest):
    """报表选择页：深分类树、环保护、跳转链接"""

    def test_deep_category_tree_renders(self):
        """19. 200 层深分类链渲染不崩溃"""
        prev = None
        for i in range(1, 201):
            prev = config_db.add_category(self.conn, f"深{i}", parent_id=prev)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "")
        self.assertEqual(code, 200)
        self.assertIn("深200", body)

    def test_category_cycle_with_root_renders_without_crash(self):
        """19. 分类环（A↔B 且挂在根 X 下）应被保护不崩溃（已知缺陷）"""
        x = config_db.add_category(self.conn, "根X")
        a = config_db.add_category(self.conn, "环A", parent_id=x)
        b = config_db.add_category(self.conn, "环B", parent_id=a)
        config_db.update_category(self.conn, a, "环A", parent_id=b)
        config_db.update_category(self.conn, b, "环B", parent_id=a)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "")
        self.assertEqual(code, 200)
        self.assertIn("选择报表", body)

    def test_selector_category_report_links_escaped(self):
        """20. 分类报表跳转链接 href 正确；特殊字符分类名被 HTML 转义"""
        cat = config_db.add_category(self.conn, "报表&分类<销售>")
        rid = config_db.add_report(self.conn, "特殊报表", "SELECT 1", 20,
                                   pool_id=self.pool_id, category_id=cat)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "")
        self.assertEqual(code, 200)
        self.assertIn(f'href="/report?id={rid}"', body)
        self.assertIn("报表&amp;分类&lt;销售&gt;", body)
        self.assertNotIn("报表&分类<销售>", body)

    def test_selector_uncategorized_report_link(self):
        """20. 未分类报表链接 href=/report?id=N"""
        rid = config_db.add_report(self.conn, "无分类报表", "SELECT 2", 20,
                                   pool_id=self.pool_id, category_id=None)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "")
        self.assertIn(f'href="/report?id={rid}"', body)


# ===================================================================
# 缺口 21：contains 空值筛选行为
# ===================================================================

class TestFilterEmptyValue(unittest.TestCase):
    """contains 空值筛选行为"""

    def test_parse_filters_skips_empty_value(self):
        """21. URL f_name=（空值）不产生筛选条件"""
        self.assertEqual(report.parse_filters({"f_name": [""]}), [])

    def test_filter_rows_contains_empty_matches_all(self):
        """21. filter_rows contains 空串 → 匹配所有行（空串是任意字符串子串）"""
        from result_transform import filter_rows
        rows = [("Alice",), ("Bob",), (None,)]
        result = filter_rows(rows, ["name"], [("name", "contains", "")])
        self.assertEqual(len(result), 3)

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_execute_report_contains_empty_matches_all(self, mock_conn_f, mock_query):
        """21. execute_report 层 contains 空值 → 全量返回"""
        mock_query.return_value = [{"columns": ["name"], "rows": [("A",), ("B",)]}]
        mock_conn_f.return_value = MagicMock()
        result = report.execute_report(1, "SELECT 1", {"host": "h"},
                                       filters=[("name", "contains", "")])
        self.assertEqual(result.total, 2)


# ===================================================================
# 缺口 22：进程缓存 SQL 不匹配时物理逐出
# ===================================================================

class TestProcessCacheSqlEviction(unittest.TestCase):
    """进程缓存 SQL 不匹配时的物理逐出行为"""

    def test_query_cache_get_mismatched_sql_evicts(self):
        """22. get 时 SQL 不匹配 → 返回 None 且缓存项被物理删除"""
        cache = report.QueryCache()
        cache.set(1, [{"columns": ["id"], "rows": [(1,)]}], "SELECT A")
        self.assertIsNone(cache.get(1, "SELECT B"))
        self.assertIsNone(cache.get(1, "SELECT A"), "SQL 不匹配的缓存项应已被逐出")

    @patch("report.db.execute_mysql_query")
    @patch("report.db.create_mysql_connection")
    def test_execute_report_sql_change_rebuilds(self, mock_conn_f, mock_query):
        """22. execute_report 层 SQL 变化 → 重新查询 MySQL"""
        cache = report.QueryCache()
        mock_query.return_value = [{"columns": ["id"], "rows": [(1,)]}]
        mock_conn_f.return_value = MagicMock()
        report.execute_report(1, "SELECT A", {"host": "h"}, cache=cache)
        report.execute_report(1, "SELECT B", {"host": "h"}, cache=cache)
        report.execute_report(1, "SELECT B", {"host": "h"}, cache=cache)
        self.assertEqual(mock_query.call_count, 2, "SQL A 一次 + SQL B 一次")


# ===================================================================
# 缺口 24：API 区渲染异常降级
# ===================================================================

class TestApiSectionDegrade(BaseReportTest):
    """API 区渲染异常降级"""

    @patch("report.execute_report")
    @patch("report.db.get_api_endpoints_by_report")
    def test_api_section_error_degrades_gracefully(self, mock_ep, mock_exec):
        """24. get_api_endpoints_by_report 抛异常 → 页面仍可渲染（API 区域留空）"""
        mock_ep.side_effect = RuntimeError("config_db 异常")
        mock_exec.return_value = report.ReportResult(
            columns=["id"], rows=[(1,)], total=1, page=1, page_size=20)
        code, body, _ = report.handle_request(self.conn, "GET", "/report", "id=1")
        self.assertEqual(code, 200)
        self.assertIn("测试报表", body)
        self.assertIn("<td>1</td>", body)


if __name__ == "__main__":
    unittest.main()
