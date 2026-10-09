"""B6 批次健壮性测试（每个 B6 子任务追加自己的测试类）。"""

import unittest
from unittest import mock
import threading

import time

import redis_cache


class TestRenderLogging(unittest.TestCase):
    """B6-5：公共资产写入失败必须留痕，而不是静默内联降级。"""

    def test_render_module_has_logger(self):
        import render
        self.assertTrue(hasattr(render, "logger"), "render.py 未引入 logging")

    def test_asset_failure_is_logged(self):
        import render
        render.reset_common_assets_cache()
        with mock.patch.object(render, "ensure_common_assets",
                               side_effect=OSError("read-only")), \
             mock.patch.object(render.logger, "exception") as log, \
             mock.patch.object(render, "_COMMON_ASSET_URLS", None):
            render.reset_common_assets_cache()
            render._get_common_asset_urls()
        self.assertTrue(log.called, "资产失败未留痕")
        render.reset_common_assets_cache()


class TestStaticCacheLock(unittest.TestCase):
    """B6-6：_last_invalidated 在 ThreadingHTTPServer 下须加锁保护。"""

    def test_module_has_lock(self):
        import static_cache
        self.assertTrue(hasattr(static_cache, "_last_invalidated_lock"),
                        "static_cache 未提供 _last_invalidated_lock")

    def test_concurrent_record_keeps_bound(self):
        import threading
        import static_cache

        def w(i):
            for j in range(200):
                static_cache.record_invalidated(f"/p/{i}-{j}")

        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertLessEqual(len(static_cache._last_invalidated),
                             static_cache._MAX_LAST_INVALIDATED)


class TestUiPageSizeCap(unittest.TestCase):
    """B6-7：UI 报表页 page_size 封顶 1000（用户裁决的行为变更）。"""

    def test_cap_constant_is_1000(self):
        import report
        self.assertEqual(report.MAX_UI_PAGE_SIZE, 1000)

    def test_clamp_helper(self):
        import report
        self.assertEqual(report._clamp_ui_page_size(10_000_000_000), 1000)
        self.assertEqual(report._clamp_ui_page_size(1000), 1000)
        self.assertEqual(report._clamp_ui_page_size(200), 200)
        self.assertEqual(report._clamp_ui_page_size(1), 1)
        self.assertEqual(report._clamp_ui_page_size(0), 1)

    def test_both_ui_entry_points_are_clamped(self):
        """⚠️ 两个入口都要夹：只改一处等于没封顶。"""
        import inspect
        import report
        for fn_name in ("handle_request", "_handle_refresh_cache"):
            src = inspect.getsource(getattr(report, fn_name))
            self.assertIn("_clamp_ui_page_size", src,
                          f"{fn_name} 未夹紧 page_size（可绕过封顶）")

    def test_execute_report_not_clamped(self):
        """关键安全断言：内部调用方靠大 page_size 取全量，绝不能在此夹。"""
        import inspect
        import report
        self.assertNotIn("MAX_UI_PAGE_SIZE", inspect.getsource(report.execute_report))

class TestQuestionToPercentS(unittest.TestCase):
    """B6-3：MySQL 兼容层的 ? → %s 必须跳过引号/注释区间，且不重组空白。"""

    @staticmethod
    def _convert(sql):
        from query_executor import _question_to_percent_s
        return _question_to_percent_s(sql)

    def test_literal_question_not_replaced(self):
        """断言 1：单引号字面量内的 ? 不动，区间外的占位符照常替换。"""
        sql = "SELECT * FROM t WHERE memo LIKE '%?%' AND a=?"
        self.assertEqual(
            self._convert(sql),
            "SELECT * FROM t WHERE memo LIKE '%?%' AND a=%s")

    def test_no_double_percent_s_corruption(self):
        """Lead 实测复现：不得再出现 '%%s%' 这种把字面量也换掉的破坏。"""
        out = self._convert("SELECT * FROM t WHERE memo LIKE '%?%' AND a=?")
        self.assertNotIn("%%s", out)

    def test_double_quote_and_backtick_untouched(self):
        """断言 2：双引号字面量与反引号标识符内的 ? 不动。"""
        self.assertEqual(
            self._convert('SELECT "a?b", `c?d`, e FROM t WHERE f=?'),
            'SELECT "a?b", `c?d`, e FROM t WHERE f=%s')

    def test_line_comments_untouched(self):
        """断言 3：-- 与 # 行注释内的 ? 不动，注释之后的占位符照常替换。"""
        self.assertEqual(
            self._convert("SELECT 1 -- 注释含 ?\nWHERE a=?"),
            "SELECT 1 -- 注释含 ?\nWHERE a=%s")
        self.assertEqual(
            self._convert("SELECT 1 # 注释含 ?\nWHERE a=?"),
            "SELECT 1 # 注释含 ?\nWHERE a=%s")

    def test_block_comment_untouched(self):
        """断言 3：/* ? */ 块注释内的 ? 不动。"""
        self.assertEqual(
            self._convert("SELECT /* ? */ 1 WHERE a=?"),
            "SELECT /* ? */ 1 WHERE a=%s")

    def test_escaped_quote_in_literal_untouched(self):
        """断言 4：'' 与反斜杠转义引号内的 ? 不动。"""
        self.assertEqual(
            self._convert("SELECT * FROM t WHERE m='it''s ?' AND a=?"),
            "SELECT * FROM t WHERE m='it''s ?' AND a=%s")
        self.assertEqual(
            self._convert(r"SELECT * FROM t WHERE m='it\'s ?' AND a=?"),
            r"SELECT * FROM t WHERE m='it\'s ?' AND a=%s")

    def test_multiple_placeholders_all_replaced(self):
        """断言 5：区间外的多个占位符全部替换。"""
        self.assertEqual(
            self._convert("INSERT INTO t (a,b,c) VALUES (?, ?, ?)"),
            "INSERT INTO t (a,b,c) VALUES (%s, %s, %s)")

    def test_whitespace_preserved_verbatim(self):
        """逐字符保留：空白/换行/大小写不得被重组（区别于 _split_sql_statements）。"""
        sql = "SELECT  *\n\tFROM  t\n  WHERE a=?\n"
        self.assertEqual(self._convert(sql),
                         "SELECT  *\n\tFROM  t\n  WHERE a=%s\n")

    def test_no_placeholder_returns_identical(self):
        sql = "SELECT  *   FROM t WHERE a = 'x' -- c\n"
        self.assertEqual(self._convert(sql), sql)

    def test_unterminated_literal_does_not_raise(self):
        self.assertEqual(self._convert("SELECT * FROM t WHERE a='x?"),
                         "SELECT * FROM t WHERE a='x?")


class TestMySQLExecutePlaceholderConversion(unittest.TestCase):
    """B6-3：两个 execute 调用点必须用引号感知替换，且 params=None 原样传递。"""

    @staticmethod
    def _cursor_execute_args(sql, params):
        from query_executor import _MySQLCursor
        raw = mock.MagicMock()
        _MySQLCursor(raw).execute(sql, params)
        return raw.execute.call_args[0]

    @staticmethod
    def _conn_execute_args(sql, params):
        from query_executor import _MySQLConnection
        raw = mock.MagicMock()
        _MySQLConnection(raw).execute(sql, params)
        return raw.cursor.return_value.execute.call_args[0]

    def test_cursor_execute_literal_untouched(self):
        args = self._cursor_execute_args(
            "SELECT * FROM t WHERE m LIKE '%?%' AND a=?", (1,))
        self.assertEqual(args[0], "SELECT * FROM t WHERE m LIKE '%?%' AND a=%s")
        self.assertEqual(args[1], (1,))

    def test_connection_execute_literal_untouched(self):
        args = self._conn_execute_args(
            "SELECT * FROM t WHERE m LIKE '%?%' AND a=?", (1,))
        self.assertEqual(args[0], "SELECT * FROM t WHERE m LIKE '%?%' AND a=%s")
        self.assertEqual(args[1], (1,))

    def test_params_none_passes_original_sql(self):
        """断言 6：params=None 时完全不替换（两个调用点都如此）。"""
        sql = "SELECT * FROM t WHERE m LIKE '%?%' AND a=?"
        self.assertEqual(self._cursor_execute_args(sql, None)[0], sql)
        self.assertEqual(self._conn_execute_args(sql, None)[0], sql)

    def test_empty_tuple_params_still_converted(self):
        """既有行为：params=() 时 params is not None 为 True，仍做替换。"""
        args = self._cursor_execute_args("SELECT * FROM t WHERE a=?", ())
        self.assertEqual(args[0], "SELECT * FROM t WHERE a=%s")
        self.assertEqual(args[1], ())


class TestCsvFormulaSanitize(unittest.TestCase):
    """B6-8：导出 CSV 公式中和（默认关闭 + 导出页勾选）。"""

    def test_default_output_byte_identical(self):
        """默认（不勾选）时字节必须与现状完全一致。"""
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False)
        self.assertEqual(out, '"a"\n"=1+1"\n')

    def test_sanitize_prefixes_dangerous_leads(self):
        import export
        for v in ("=1+1", "+3", "-2", "@SUM(A1)"):
            self.assertTrue(export.sanitize_csv_formula(v).startswith("'"),
                            f"{v!r} 未被中和")

    def test_sanitize_leaves_normal_values(self):
        import export
        self.assertEqual(export.sanitize_csv_formula("正常文本"), "正常文本")
        self.assertEqual(export.sanitize_csv_formula("123"), "123")

    def test_opt_in_changes_bytes(self):
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False, sanitize_formula=True)
        self.assertIn("'=1+1", out)


class TestRedisSelfHeal(unittest.TestCase):
    """B6-1：运行期不可用时必须能重连，而不是永久降级到重启。"""

    def setUp(self):
        redis_cache.reset_redis_manager()

    def tearDown(self):
        redis_cache.reset_redis_manager()

    def test_reconnects_when_existing_manager_unavailable(self):
        mgr = mock.MagicMock()
        mgr.available = False
        redis_cache._redis_manager = mgr
        try:
            # 模拟「Redis 启动后恢复」：重连成功并变为可用
            def _ok_connect():
                mgr.available = True
                return True
            mgr.connect.side_effect = _ok_connect
            with mock.patch.object(redis_cache, "get_redis_config",
                                   return_value={"enable": True}), \
                 mock.patch.object(redis_cache, "RedisConnectionManager",
                                   return_value=mgr) as cls:
                redis_cache.get_redis_manager()
            # 必须尝试过恢复（重连 或 start_health_check）
            self.assertTrue(cls.called or mgr.connect.called,
                            "管理器已存在但不可用时未尝试恢复连接")
            # 恢复成功后必须启动健康检查
            self.assertTrue(mgr.start_health_check.called,
                            "恢复成功后未启动健康检查线程")
        finally:
            redis_cache._redis_manager = None
            redis_cache._redis_last_connect_attempt = 0.0

    def test_disabled_redis_keeps_none(self):
        """enable=False 必须保持 _redis_manager is None（语义：未启用 ≠ 连不上）。"""
        redis_cache._redis_manager = None
        with mock.patch.object(redis_cache, "get_redis_config",
                               return_value={"enable": False}):
            self.assertIsNone(redis_cache.get_redis_manager())

    def test_singleton_creation_is_thread_safe(self):
        """并发首访不得创建多个 manager（当前无锁）。"""
        created = []
        bar = threading.Barrier(8)

        def fake_cls(cfg):
            # 拉大竞争窗口：真实代码在构造返回后才赋值 _redis_manager
            time.sleep(0.05)
            m = mock.MagicMock()
            m.available = False
            created.append(m)
            return m

        def worker():
            bar.wait(timeout=10)
            redis_cache.get_redis_manager()

        redis_cache._redis_manager = None
        with mock.patch.object(redis_cache, "get_redis_config",
                               return_value={"enable": True}), \
             mock.patch.object(redis_cache, "RedisConnectionManager",
                               side_effect=fake_cls):
            ts = [threading.Thread(target=worker) for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=10)
        self.assertEqual(len(created), 1,
                         f"并发首访创建了 {len(created)} 个 manager（应为 1）")
        redis_cache._redis_manager = None
        redis_cache._redis_last_connect_attempt = 0.0

    def test_recovery_is_backed_off(self):
        """恢复必须带退避：窗口内不得反复重连（防连接风暴）。"""
        mgr = mock.MagicMock()
        mgr.available = False
        redis_cache._redis_manager = mgr
        redis_cache._redis_last_connect_attempt = 0.0
        try:
            with mock.patch.object(redis_cache, "get_redis_config",
                                   return_value={"enable": True}):
                redis_cache.get_redis_manager()
                first = mgr.connect.call_count
                self.assertEqual(first, 1, "首次应尝试一次恢复")
                for _ in range(20):
                    redis_cache.get_redis_manager()
                self.assertEqual(mgr.connect.call_count, first,
                                 "退避窗口内不应再次重连（连接风暴）")
                # 推进时间越过退避窗口，应允许再次尝试
                redis_cache._redis_last_connect_attempt = (
                    time.monotonic() - redis_cache._HEALTH_CHECK_INTERVAL - 1)
                redis_cache.get_redis_manager()
                self.assertGreater(mgr.connect.call_count, first,
                                   "退避窗口过后应再次尝试恢复")
        finally:
            redis_cache._redis_manager = None
            redis_cache._redis_last_connect_attempt = 0.0
