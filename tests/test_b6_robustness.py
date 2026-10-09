"""B6 批次健壮性测试（每个 B6 子任务追加自己的测试类）。"""

import unittest
from unittest import mock
import threading
import http.server

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


class TestRebuildLock(unittest.TestCase):
    """B6-2：锁必须有持有者校验与原子过期，不得误删他人锁。"""

    def _mgr(self, client, store=None):
        cfg = {"enable": True, "key_prefix": "sr_test"}
        mgr = redis_cache.RedisConnectionManager(cfg)
        mgr._client = client
        mgr._available = True
        return mgr

    @staticmethod
    def _fake_client(store):
        """最小 Redis 假客户端：同时支持原子 set 与旧的 setnx/expire。"""

        class Fake:
            def set(self, k, v, nx=False, ex=None):
                if nx and k in store:
                    return None
                store[k] = v
                return True

            def get(self, k):
                return store.get(k)

            def delete(self, k):
                store.pop(k, None)
                return 1

            def setnx(self, k, v):
                if k in store:
                    return False
                store[k] = v
                return True

            def expire(self, k, t):
                return True

            def ping(self):
                return True

        return Fake()

    def test_release_does_not_delete_foreign_lock(self):
        """锁过期后被他人接管 → release 不得删掉别人的锁。"""
        store = {}
        mgr = self._mgr(self._fake_client(store))
        self.assertTrue(mgr.acquire_lock("lock:x"))
        # 模拟锁过期后被他人获取：直接换掉锁值
        store["lock:x"] = "someone-else"
        mgr.release_lock("lock:x")
        self.assertIn("lock:x", store, "release 删掉了别人的锁！")
        self.assertEqual(store["lock:x"], "someone-else")

    def test_release_own_lock_removes_it(self):
        """本进程自己持有的锁必须被正常释放。"""
        store = {}
        mgr = self._mgr(self._fake_client(store))
        self.assertTrue(mgr.acquire_lock("lock:y"))
        mgr.release_lock("lock:y")
        self.assertNotIn("lock:y", store)

    def test_acquire_lock_uses_atomic_set_with_ttl(self):
        """acquire 必须是一次 set(nx=True, ex=timeout)，不得 setnx+expire 两次往返。"""
        client = mock.MagicMock()
        client.set.return_value = True
        mgr = self._mgr(client)
        self.assertTrue(mgr.acquire_lock("lock:z"))
        client.set.assert_called_once_with("lock:z", mock.ANY, nx=True,
                                           ex=redis_cache._LOCK_TIMEOUT)
        client.setnx.assert_not_called()
        client.expire.assert_not_called()

    def test_lock_value_is_unique_token_not_constant(self):
        """锁值必须是唯一 token；恒为常量则无法区分持有者。"""
        store = {}
        mgr = self._mgr(self._fake_client(store))
        self.assertTrue(mgr.acquire_lock("lock:t"))
        self.assertTrue(store["lock:t"])
        self.assertNotEqual(store["lock:t"], "1",
                            "锁值仍为常量 1，release 无法校验持有者")

    def test_release_without_token_is_noop(self):
        """从未持锁（如 wait_for_lock 超时）不得 delete 任何东西。"""
        client = mock.MagicMock()
        mgr = self._mgr(client)
        mgr.release_lock("lock:never-held")
        client.delete.assert_not_called()

    def test_release_is_idempotent(self):
        """重复 release 只删一次。"""
        store = {}
        calls = []
        fake = self._fake_client(store)
        orig_delete = fake.delete

        def counting_delete(k):
            calls.append(k)
            return orig_delete(k)

        fake.delete = counting_delete
        mgr = self._mgr(fake)
        self.assertTrue(mgr.acquire_lock("lock:r"))
        mgr.release_lock("lock:r")
        mgr.release_lock("lock:r")
        self.assertEqual(calls, ["lock:r"])
        self.assertNotIn("lock:r", store)

    def test_wait_for_lock_timeout_drops_no_lock(self):
        """wait_for_lock 超时（未获锁）不得 delete，也不得遗留 token。"""
        client = mock.MagicMock()
        client.set.return_value = None          # 锁始终被他人占用
        mgr = self._mgr(client)
        with mock.patch.object(redis_cache, "_LOCK_RETRY_INTERVAL", 0.01):
            self.assertFalse(mgr.wait_for_lock("lock:w", max_wait=0.05))
        client.delete.assert_not_called()
        client.set.assert_called_with("lock:w", mock.ANY, nx=True,
                                      ex=redis_cache._LOCK_TIMEOUT)

    def test_lock_timeout_covers_slow_reports(self):
        """TTL 必须覆盖最大合法报表耗时（调度器/API 路径不限超时）。"""
        self.assertGreaterEqual(
            redis_cache._LOCK_TIMEOUT, 300,
            "TTL 过短，慢报表会在持锁期间过期并被他人接管")

    def test_lock_method_signatures_unchanged(self):
        """三方法签名不得变化（report.py 调用与既有 mock 断言依赖）。"""
        import inspect
        expected = {
            "acquire_lock": ["self", "lock_key", "timeout"],
            "release_lock": ["self", "lock_key"],
            "wait_for_lock": ["self", "lock_key", "max_wait"],
        }
        for name, params in expected.items():
            sig = inspect.signature(
                getattr(redis_cache.RedisConnectionManager, name))
            self.assertEqual(list(sig.parameters), params,
                             "%s 签名被改动" % name)


class TestSocketTimeout(unittest.TestCase):
    """B6-4：请求读阶段限时，防慢连接无限占线程。

    为什么不是类属性 timeout：BaseHTTPRequestHandler.setup() 会把 timeout
    设到整个请求 socket，而 wbufsize=0 时 wfile 直接写 socket，于是响应写
    也吃同一个超时。L2 实测（run-logs/b6-4-l2-throttle-20261010.py，
    8 MiB 导出 / 500 KB/s）显示类属性 timeout=10 会把导出截断到
    7283712/8388611 字节；读阶段拆分方案同链路下完整。
    """

    def test_read_phase_timeout_is_configured(self):
        """必须对读阶段设了超时——否则慢连接可无限占线程。"""
        import server
        self.assertIsNotNone(
            getattr(server.ReportHandler, "REQUEST_READ_TIMEOUT", None),
            "ReportHandler 未设读阶段超时，慢连接可无限占线程")

    def test_read_phase_timeout_is_sane(self):
        """取值下限：太小会误杀正常慢客户端；上限：太大留不住线程。

        正常客户端发完请求头远快于 30s；slowloris 会在 30s 内被回收。
        """
        import server
        v = server.ReportHandler.REQUEST_READ_TIMEOUT
        self.assertGreaterEqual(v, 10, "读超时过短，正常慢客户端会被误杀")
        self.assertLessEqual(v, 120, "读超时过长，慢连接仍能长期占线程")

    def test_setup_overridden_and_connection_timeout_applied(self):
        """setup() 必须重写，且真的把读超时设到 socket 上。

        顺序很关键：self.connection 由父类 setup() 赋值，因此不能先
        settimeout——这里用假 connection 验证确实调用了 settimeout。
        """
        import server
        import http.server
        self.assertIn("setup", server.ReportHandler.__dict__,
                      "ReportHandler 未重写 setup，读超时无法落到 socket")
        h = server.ReportHandler.__new__(server.ReportHandler)

        class _Conn:
            def __init__(self):
                self.calls = []

            def settimeout(self, v):
                self.calls.append(v)

            def setsockopt(self, *a):
                pass

            def makefile(self, *a, **k):
                import io
                return io.BytesIO()

        conn = _Conn()
        h.request = conn
        h.client_address = ("127.0.0.1", 0)
        h.disable_nagle_algorithm = False
        h.rbufsize = -1
        h.wbufsize = 0
        h.setup()
        self.assertIn(server.ReportHandler.REQUEST_READ_TIMEOUT, conn.calls,
                      "setup() 未把读超时设到 connection 上")

    def test_no_class_level_whole_socket_timeout(self):
        """回归护栏：不得回退为类属性 timeout。

        类属性 timeout 会被父类 setup() 设到整个 socket 上，连响应写一起
        限时——这正是大导出被截断的根因（见本类 docstring 实测数据）。
        """
        import server
        self.assertIsNone(
            getattr(server.ReportHandler, "timeout", None),
            "类属性 timeout 会连响应写一起限时，慢链路大导出会被截断；"
            "请用 setup() 只对读阶段限时")

    def test_write_phase_timeout_is_cleared(self):
        """读阶段结束后必须把 socket 超时清回 None，响应写才不受限。"""
        import server
        self.assertIn("handle_one_request", server.ReportHandler.__dict__,
                      "未重写 handle_one_request，写阶段无法解除超时")
        h = server.ReportHandler.__new__(server.ReportHandler)
        seen = []

        class _Conn:
            def settimeout(self, v):
                seen.append(v)

        h.connection = _Conn()
        # 父类实现经 super() 调用，这里把父类方法换成抛异常以走 finally 分支
        with mock.patch.object(http.server.BaseHTTPRequestHandler,
                               "handle_one_request", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                h.handle_one_request()
        self.assertIn(None, seen,
                      "handle_one_request 未在读阶段结束后清除超时")

    def test_write_phase_decoupled_from_read_timeout(self):
        """B6-4 行为护栏：读超时**不得**延续到响应写阶段。

        为什么必须是行为测试（Lead 补充）：
        只断言「handle_one_request 调了 settimeout(None)」是不够的 ——
        父类 handle_one_request() 把「读请求」与「调 do_* + flush 响应」
        包在**同一个调用**里，其 finally 要等响应写完才执行。若只在 finally
        里清超时，写阶段仍在吃超时，大导出会被**静默截断**而不报错。
        实测（Lead）：REQUEST_READ_TIMEOUT=2 + 客户端读响应时暂停 3s →
        4 MiB 响应只发出 2588672 字节。

        本测试直接检查 do_* 执行期间 socket 超时已为 None。
        """
        import socket
        import threading
        import time
        import http.server

        import server

        seen = []

        class _H(server.ReportHandler):
            REQUEST_READ_TIMEOUT = 2

            def do_GET(self):
                seen.append(self.connection.gettimeout())
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
                self.wfile.flush()

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = socket.create_connection(("127.0.0.1", port))
            c.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            time.sleep(0.6)
            try:
                c.recv(65536)
            except OSError:
                pass
            c.close()
            time.sleep(0.3)
        finally:
            httpd.shutdown()
            httpd.server_close()

        self.assertTrue(seen, "do_GET 未被调用，测试装置失效")
        self.assertIsNone(
            seen[0],
            "进入 do_* 时 socket 超时仍生效 → 响应写也被限时，"
            "慢链路大导出会被静默截断；应在 parse_request() 后清除")
