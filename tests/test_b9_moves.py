"""B9-1：render.py 七个大常量外移到 ui_assets.py 的字节护栏测试。

纯搬移任务：符号取值与 vendor hash 必须逐字节不变。
"""
import hashlib
import unittest


class TestAssetsByteIdentical(unittest.TestCase):
    """B9-1：常量外移是纯搬移，取值与 vendor hash 必须逐字节不变。"""

    BASELINE = {
        "_BASE_CSS": ("ae3a4bbd0272f2a2", 9055),
        "_COMMON_CSS": ("bb7ec576421bc83e", 79531),
        "_COMMON_JS": ("5bcbeaccdfb1c635", 21412),
        "_MD_CSS": ("c352588586b20dc3", 2492),
        "_SQL_HIGHLIGHT_JS": ("b747870a03686a41", 1343),
        "_SQL_FORMATTER_JS": ("b46730d48db26945", 3116),
        "_API_TEMPLATE_JS": ("d59b15d3f972c38e", 7611),
        "_EXCL_EDITOR_JS": ("acd4d5e83cde6b4a", 7434),
    }

    def test_render_constants_match_baseline(self):
        import render
        for name, (want_h, want_len) in self.BASELINE.items():
            val = getattr(render, name, None)
            self.assertIsInstance(val, str, f"render.{name} 不在了")
            self.assertEqual(len(val), want_len, f"{name} 长度变了")
            self.assertEqual(hashlib.sha256(val.encode()).hexdigest()[:16], want_h,
                             f"{name} 字节变了")

    def test_vendor_hash8_unchanged(self):
        """vendor 目录名 self@{hash8} 必须不变（否则静态资源 URL 变化）。"""
        import render
        self.assertEqual(
            render.content_hash8(render._COMMON_CSS + "\n;;;\n" + render._COMMON_JS),
            "72429792")

    def test_ui_assets_exists_and_render_reexports(self):
        """外移后 render 必须继续导出这些名字（config/report 从 render 导入）。"""
        import render
        import ui_assets
        self.assertTrue(hasattr(ui_assets, "COMMON_CSS")
                        or hasattr(ui_assets, "_COMMON_CSS"),
                        "ui_assets 未提供 COMMON_CSS")
        # config / report 的导入路径必须仍可用
        from render import _MD_CSS, _SQL_FORMATTER_JS, _SQL_HIGHLIGHT_JS  # noqa: F401


if __name__ == "__main__":
    unittest.main()
