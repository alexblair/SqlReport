import unittest


class TestShadowedDefsRemoved(unittest.TestCase):
    """B7-1：被遮蔽的重复定义必须删除，且生效版本的语义不变。"""

    def test_effective_humanize_uses_errno_hints_table(self):
        """生效版必须走 _DB_ERRNO_HINTS + 超时标记（不是被删掉的旧表）。"""
        import report
        # 生效版必须比死掉那版更强：同时认 "(NNNN)" 与行首 "NNNN " 两种 errno 形态
        class _E(Exception):
            errno = None
        friendly, raw = report.humanize_db_error(_E("2003 Can't connect"))
        self.assertNotEqual(friendly, raw, "行首 errno 形态未映射（生效版应支持）")
        self.assertTrue(hasattr(report, "_DB_ERRNO_HINTS"))
        # 1969 → 查询超时人话
        class _E(Exception):
            errno = 1969
        friendly, raw = report.humanize_db_error(_E("boom"))
        self.assertNotEqual(friendly, raw, "1969 未映射为超时人话")
        self.assertEqual(raw, "boom")

    def test_read_timeout_message_maps_to_timeout_hint(self):
        import report
        friendly, raw = report.humanize_db_error(Exception("Read timed out"))
        self.assertNotEqual(friendly, raw, "Read timed out 未映射")

    def test_unmapped_error_returns_raw_twice(self):
        """未识别异常原样返回（不制造虚假解释）。"""
        import report
        friendly, raw = report.humanize_db_error(Exception("some weird thing"))
        self.assertEqual(friendly, raw)

    def test_orphan_hints_table_removed(self):
        """_DB_ERROR_HINTS 只被死代码引用，应一并删除。"""
        import report
        self.assertFalse(hasattr(report, "_DB_ERROR_HINTS"),
                         "_DB_ERROR_HINTS 是孤儿常量，应随死代码删除")

    def test_no_module_level_shadowing(self):
        """模块级不得再有重名函数定义（后定义遮蔽前定义）。"""
        import ast
        import inspect
        import report
        tree = ast.parse(inspect.getsource(report))
        seen, dups = {}, []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.name in seen:
                    dups.append(n.name)
                seen[n.name] = n.lineno
        self.assertEqual(dups, [], f"仍有被遮蔽的重复定义: {dups}")

    def test_error_section_still_renders(self):
        import report
        html = report.render_sql_error_section("人话提示", "原始错误")
        self.assertIn("人话提示", html)
        self.assertIn("原始错误", html)
