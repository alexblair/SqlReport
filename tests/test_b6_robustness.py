"""B6 批次健壮性测试（每个 B6 子任务追加自己的测试类）。"""

import unittest
from unittest import mock


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

