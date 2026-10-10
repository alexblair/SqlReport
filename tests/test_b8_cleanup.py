"""
test_b8_cleanup.py — B8 工作包 A 组（纯删除 / 等价替换）护栏测试

依据：`docs/compose/reports/b8-work-brief.md` §1 A 组（纯删除/等价替换）、§2 B 组（行为修正）。
三个护栏分别锁定：
- A-1 `render.py` 相邻 `return`（第二行永远不可达）
- A-2 `render.py` 空壳 CSS 常量 `_MINIBTN_CSS` / `_FLASH_WARN_CSS` / `_B6_CSS`
- A-3 `render.py` 畸形 SVG 属性 `rx.5"`（应为 `rx="0.5"`）

A-2 偏差说明（与 brief 原文的差异，已报告）：
brief 给的写法是 `assertNotIn(name, src)` 对 render.py 全文匹配。但 render.py:1302
的 CSS 注释 `/* —— 迷你按钮变体（原 _MINIBTN_CSS） —— */` 位于 `_COMMON_CSS`
字符串字面量内部，其文本本身是 `_COMMON_CSS` 最终值的一部分；删掉它必然改变
`_COMMON_CSS` 的 sha256（硬性要求：逐字节不变 =
bb7ec576421bc83ead99f24446d497ee13780933160443d63f492a015e7fb40a）。
因此本测试改为 AST 绑定层校验：模块级不得再绑定这三个名字，也不得读取它们。
语义等价于「空壳已清理」，且不与 sha256 逐字节不变的要求冲突。
"""
import ast
import builtins
import inspect
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import app_config
import export
import server


class TestB8Cleanup(unittest.TestCase):
    """B8 A 组：纯删除 / 等价替换护栏。"""

    def test_no_consecutive_return_in_render(self):
        """render.py 不得有相邻 return（第二行永远不可达）。"""
        tree = ast.parse(pathlib.Path("render.py").read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                body = getattr(n, "body", [])
                for i in range(len(body) - 1):
                    a, b = body[i], body[i + 1]
                    self.assertFalse(
                        isinstance(a, ast.Return) and isinstance(b, ast.Return),
                        f"render.py:{b.lineno} 相邻 return 死代码")

    def test_no_empty_css_shims(self):
        """render.py 不得再定义或读取空壳 CSS 常量（AST 绑定层校验，见模块 docstring）。"""
        tree = ast.parse(pathlib.Path("render.py").read_text(encoding="utf-8"))
        names = {"_MINIBTN_CSS", "_FLASH_WARN_CSS", "_B6_CSS"}
        bound, loaded = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                (loaded if isinstance(node.ctx, ast.Load) else bound).add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
        for name in sorted(names):
            self.assertNotIn(name, bound, f"{name} 空壳定义未清理")
            self.assertNotIn(name, loaded, f"{name} 仍被引用")

    def test_no_malformed_svg_attrs(self):
        """render.py 不得含畸形 SVG 属性（如 `rx.5`，应为 `rx=\"0.5\"`）。"""
        src = pathlib.Path("render.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r'rx\.\d', "存在畸形 SVG 属性（如 rx.5）")


class _CountingRoutes(list):
    """包装 ROUTES 以统计遍历次数（B-2 单次扫描护栏）。"""

    def __init__(self, items):
        super().__init__(items)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def _make_handler(path):
    """构造 ReportHandler 裸实例（同 tests/test_trust_baseline.py 模式）。"""
    h = server.ReportHandler.__new__(server.ReportHandler)
    h._session_token = None
    h.headers = {}
    h.path = path
    h.client_address = ("127.0.0.1", 5555)
    h.wfile = mock.MagicMock()
    h._sent = []
    h.send_response = lambda code, *a: h._sent.append(("status", code))
    h.send_header = lambda k, v: h._sent.append(("header", k, v))
    h.end_headers = lambda: h._sent.append(("end_headers", None))
    return h


class TestB8BehaviorFixes(unittest.TestCase):
    """B8 B 组：行为修正护栏。

    - B-1 `app_config` DEBUG 覆盖配置缓存：命中不重复读文件，重载路径失效
    - B-2 `server._scan_routes` 一次遍历同时给出匹配条目与 Allow 方法表
    - B-3 `export._encode_content` GBK 分支只剥离开头 BOM
    """

    def tearDown(self):
        # 清全局状态，避免污染其他用例（env 已由各用例的 patch 自行还原）
        app_config._config = None
        app_config._invalidate_debug_config_cache()

    # ---- B-3 -----------------------------------------------------------
    def test_gbk_only_strips_leading_bom(self):
        """B-3：GBK 分支正文中间的 U+FEFF 必须保留（GBK 不可编码 → ?）。"""
        content = "\ufeffa\ufeffb"
        self.assertEqual(export._encode_content(content, "gbk"), b"a?b")
        # 开头 BOM 仍被剥离（既有需求不回归）
        self.assertEqual(export._encode_content("\ufeff你好", "gbk"),
                         "你好".encode("gbk", errors="replace"))
        # UTF-8 分支不经此处，原样保留
        self.assertEqual(export._encode_content(content, "utf8"),
                         content.encode("utf-8"))
        # 源码层面：GBK 分支不得再用 replace() 清 BOM
        src = inspect.getsource(export._encode_content)
        self.assertNotIn("replace(", src)
        self.assertIn("lstrip(", src)

    # ---- B-1 -----------------------------------------------------------
    def _write_json(self, payload):
        fd, path = tempfile.mkstemp(prefix="sr-b8-", suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self.addCleanup(os.unlink, path)
        return path

    def test_debug_config_cache_hits_and_invalidates(self):
        """B-1：缓存命中不重复 open()；env 换路径与 reload_config() 均重新读取。"""
        base = self._write_json({
            "server": {"host": "0.0.0.0", "port": 1000},
            "config_db": [{"enable": True, "engine": "sqlite3",
                           "path": "config.db"}],
        })
        debug = self._write_json({"server": {"port": 9999}})
        real_open = builtins.open
        calls = []

        def counting_open(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("file"))
            return real_open(*args, **kwargs)

        with mock.patch.dict(os.environ, {"CONFIG_FILE": base,
                                          "DEBUG_CONFIG_FILE": debug}):
            app_config._config = None
            app_config._invalidate_debug_config_cache()
            with mock.patch("builtins.open", side_effect=counting_open):
                cfg = app_config.get_config()
                self.assertEqual(cfg["server"]["port"], 9999)
                after_load = len(calls)
            self.assertGreater(after_load, 0)
            with mock.patch("builtins.open", side_effect=counting_open):
                for _ in range(20):
                    self.assertTrue(app_config.is_debug_mode())
                self.assertEqual(len(calls), after_load,
                                 "缓存命中时 is_debug_mode 不得重复 open()")
                # env 换路径 → 缓存键变化 → 立即重新读取
                debug2 = self._write_json({"server": {"port": 4321}})
                with mock.patch.dict(os.environ,
                                     {"DEBUG_CONFIG_FILE": debug2}):
                    self.assertEqual(
                        app_config._load_debug_config()["server"]["port"],
                        4321)
                # reload_config() 清缓存后必须重新读取
                with open(debug, "w", encoding="utf-8") as f:
                    json.dump({"server": {"port": 7777}}, f)
                before = len(calls)
                reloaded = app_config.reload_config()
                self.assertGreater(len(calls), before,
                                   "reload_config 必须重新读文件")
                self.assertEqual(reloaded["server"]["port"], 7777)
                self.assertTrue(app_config.is_debug_mode())

    # ---- B-2 -----------------------------------------------------------
    def _handle_status(self, path, method):
        h = _make_handler(path)
        counting = _CountingRoutes(server.ROUTES)
        with mock.patch.object(server, "ROUTES", counting):
            server.ReportHandler._handle(h, method)
        status = [i[1] for i in h._sent if i[0] == "status"][0]
        headers = {i[1]: i[2] for i in h._sent if i[0] == "header"}
        return status, headers, counting.iterations

    def test_route_table_scanned_once_for_404_and_405(self):
        """B-2：404/405 分支只遍历一次路由表（改动前为两次）。"""
        status, headers, iterations = self._handle_status("/login", "DELETE")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "GET, POST")
        self.assertEqual(iterations, 1, "405 路径扫描路由表次数")
        status, headers, iterations = self._handle_status(
            "/no/such/page", "GET")
        self.assertEqual(status, 404)
        self.assertNotIn("Allow", headers)
        self.assertEqual(iterations, 1, "404 路径扫描路由表次数")

    def test_allow_header_unchanged(self):
        """B-2：405 的 Allow 头内容与顺序逐字节等于改动前（快照）。"""
        expected = {
            ("/login", "DELETE"): "GET, POST",
            ("/report", "DELETE"): "GET, POST, OPTIONS",
            ("/", "PUT"): "GET",
            ("/health", "PUT"): "GET",
            ("/favicon.ico", "DELETE"): "GET",
            ("/api/cust/data", "PUT"): "GET, POST, OPTIONS",
            ("/audit/x", "PUT"): "GET, POST, OPTIONS",
            ("/config", "PUT"): "GET, POST, OPTIONS",
        }
        for (path, method), allow in expected.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(
                    ", ".join(server._allowed_methods_for_path(path)), allow)
                status, headers, _ = self._handle_status(path, method)
                self.assertEqual(status, 405)
                self.assertEqual(headers.get("Allow"), allow)

    def test_thin_wrappers_still_available(self):
        """B-2：_match_route / _allowed_methods_for_path 保留且与单次扫描一致。"""
        for path in ("/login", "/report", "/api/cust/data", "/no/such/page"):
            for method in ("GET", "POST", "PUT", "OPTIONS"):
                with self.subTest(path=path, method=method):
                    route, allowed = server._scan_routes(path, method)
                    self.assertIs(server._match_route(method, path), route)
                    self.assertEqual(
                        server._allowed_methods_for_path(path), allowed)


if __name__ == "__main__":
    unittest.main()


class TestFailCountThresholdWired(unittest.TestCase):
    """B8 第 6 项：熔断阈值必须由常量驱动，不得在 SQL 里写死。

    问题（Lead 现查）：`scheduler.MAX_FAIL_COUNT = 5` 定义了但全仓**零引用**，
    而阈值 `5` 硬编码在 3 处 SQL 字符串里（`scheduler.py` 2 处、
    `config_db.py` 1 处）。未来改常量会「看起来生效、实际不生效」——
    这正是用户口中的「假 BUG」：改完阈值测试仍按 5 走，排查半天。

    本测试从两个层面锁死：
    1. **源码层**：这些 SQL 必须用参数化阈值，不得出现字面量 `fail_count<5`
    2. **行为层**：真的改常量后，到期筛选与熔断判断都随之改变
    """

    # ---- 1. 源码层：不得再有写死的阈值 ----

    def test_no_hardcoded_threshold_in_sql_sources(self):
        """scheduler.py 与 config_db.py 的 SQL 里不得出现写死的 fail_count<5。"""
        import pathlib
        import re
        bad = []
        for name in ("scheduler.py", "config_db.py"):
            src = pathlib.Path(name).read_text(encoding="utf-8")
            for m in re.finditer(r"fail_count\s*<\s*(\d+)", src):
                bad.append(f"{name}: 写死 fail_count<{m.group(1)}")
        self.assertEqual(bad, [], f"阈值仍被写死在 SQL 里：{bad}")

    def test_single_source_of_truth_constant_exists(self):
        """必须存在唯一权威常量，且 scheduler 侧别名与之一致。"""
        import config_db
        import scheduler
        self.assertTrue(hasattr(config_db, "MAX_FAIL_COUNT"),
                        "config_db 未定义 MAX_FAIL_COUNT（SQL 执行方应持有权威值）")
        self.assertEqual(scheduler.MAX_FAIL_COUNT, config_db.MAX_FAIL_COUNT,
                         "scheduler.MAX_FAIL_COUNT 与权威常量不一致（双份常量陷阱）")

    def test_all_threshold_sql_uses_placeholder(self):
        """三处阈值 SQL 都必须用 ? 占位符传参，而不是拼字面量。"""
        import pathlib
        import re
        hits = 0
        for name in ("scheduler.py", "config_db.py"):
            src = pathlib.Path(name).read_text(encoding="utf-8")
            # 找出所有提到 fail_count 比较的 SQL 片段
            for m in re.finditer(r"fail_count\s*<\s*(\?|\d+)", src):
                hits += 1
                self.assertEqual(
                    m.group(1), "?",
                    f"{name}: fail_count 比较未参数化（实际 `fail_count<{m.group(1)}`）")
        # 阈值 SQL 至少两处：config_db.get_due_schedules （tick 与启动扫描共用）
        # 与 scheduler 保活扫描。注：run_startup_scan 原本自写的那份已改为
        # 委托 get_due_schedules，故总数由 3 降为 2（属消除重复实现，非覆盖面缩小）。
        self.assertGreaterEqual(hits, 2, f"阈值 SQL 只找到 {hits} 处，应至少 2 处")

    # ---- 2. 行为层：改常量必须真生效 ----

    def _make_conn(self):
        from tests import init_test_db
        from tests.test_base import make_config_db
        from tests.test_scheduler_db import SQL_CREATE_REPORT_SCHEDULES
        conn = make_config_db()
        init_test_db(conn)
        conn.executescript(SQL_CREATE_REPORT_SCHEDULES)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES ('r1','SELECT 1')")
        conn.commit()
        return conn

    def _add_sched(self, conn, next_run_at, fail_count):
        rid = conn.execute("SELECT id FROM report_configs LIMIT 1").fetchone()["id"]
        import config_db
        sid = config_db.upsert_schedule(conn, name=f"s{fail_count}-{next_run_at}",
                                        report_ids=[rid],
                                        schedule_type="interval",
                                        interval_minutes=60)
        conn.execute("UPDATE report_schedules SET fail_count=?, next_run_at=? WHERE id=?",
                     (fail_count, next_run_at, sid))
        conn.commit()
        return sid

    def test_threshold_change_actually_takes_effect(self):
        """把权威常量改小后，到期筛选必须立即按新阈值过滤（行为级证明）。"""
        import config_db
        conn = self._make_conn()
        try:
            # fail_count=3 的任务：阈值 5 时应到期；阈值 2 时应被过滤掉
            self._add_sched(conn, next_run_at=1000.0, fail_count=3)

            with mock.patch.object(config_db, "MAX_FAIL_COUNT", 5):
                self.assertEqual(len(config_db.get_due_schedules(conn, 1000.0)), 1,
                                 "阈值 5 时 fail_count=3 应可派发")

            with mock.patch.object(config_db, "MAX_FAIL_COUNT", 2):
                self.assertEqual(len(config_db.get_due_schedules(conn, 1000.0)), 0,
                                 "阈值改为 2 后 fail_count=3 必须被熔断——"
                                 "若仍返回 1，说明阈值没生效（假 BUG）")
        finally:
            conn.close()

    def test_startup_scan_respects_constant(self):
        """启动补跑扫描必须复用 get_due_schedules，不得自写一份带阈值的 SQL。"""
        import config_db
        import scheduler
        conn = self._make_conn()
        sched = scheduler.ReportScheduler()
        try:
            self._add_sched(conn, next_run_at=1000.0, fail_count=3)
            seen = {}
            real_due = config_db.get_due_schedules   # 先存原函数，避免 patch 后递归调自身

            def _fake_due(c, now):
                seen["args"] = (c, now)
                return real_due(c, now)

            with mock.patch.object(config_db, "get_config_db", return_value=conn), \
                 mock.patch.object(config_db, "get_due_schedules",
                                   side_effect=_fake_due) as spy:
                sched.run_startup_scan(now=2000.0)

            self.assertTrue(spy.called,
                            "run_startup_scan 未调用 get_due_schedules——"
                            "说明它仍在自写带阈值的 SQL（第二处硬编码点）")
            self.assertEqual(seen["args"][1], 2000.0,
                             "未把 now 透传给共享查询")
        finally:
            sched.shutdown(timeout=1.0)
            conn.close()
