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


class TestEscapeUnified(unittest.TestCase):
    """B7-2：两份 _escape 必须语义一致（消除 Decimal 科学计数法分叉）。"""

    def test_decimal_no_scientific_notation(self):
        from decimal import Decimal
        import config, render
        for v in (Decimal("1E-10"), Decimal("1E+20"), Decimal("123.4500")):
            self.assertEqual(config._escape(v), render._escape(v),
                             f"_escape 对 {v!r} 语义仍不一致")

    def test_both_agree_on_plain_values(self):
        import config, render
        for v in (None, "", "<b>&", "普通文本", 0, True):
            self.assertEqual(config._escape(v), render._escape(v))

    def test_string_bodies_unchanged_byte_for_byte(self):
        """护栏：委托后字符串体必须逐字节不变（现有调用点都传字符串）。"""
        import config, render
        for s in ("", "普通文本", '<a href="x">&amp;</a>', "多行\n文本", "emoji😀"):
            self.assertEqual(config._escape(s), render._escape(s))
            self.assertEqual(config._escape(s),
                             __import__("html").escape(s))


class TestCategoryIndent(unittest.TestCase):
    """B7-3：分类树缩进必须用全角 U+3000（半角在 <option> 里会被折叠）。"""

    def test_indent_is_fullwidth(self):
        import config
        import inspect
        src = inspect.getsource(config)
        # 定位 _get_depth 参与的那行
        self.assertIn("\\u3000", src,
                      "未使用全角 U+3000 缩进；半角空格在 <option> 中会被 HTML 折叠")
        self.assertNotIn('"  " * _get_depth', src,
                         "仍在用半角双空格缩进（<option> 中会被折叠为不可见）")

    def test_rendered_option_contains_fullwidth_indent(self):
        """端到端：渲染出的父子分类 option 必须带全角缩进前缀。"""
        from tests import init_test_db
        from tests.test_base import make_config_db
        import config, config_db
        conn = make_config_db()
        init_test_db(conn)
        parent = config_db.add_category(conn, name="父类")
        _child = config_db.add_category(conn, name="子类", parent_id=parent)
        # 孙类（depth=2）：　　 断言只有在 2 级深度才成立；
        # 本用例改为逐级断言，既覆盖 depth=1 也覆盖 depth=2
        _grand = config_db.add_category(conn, name="孙类", parent_id=_child)
        # ⚠️ :1177 在 render_category_form_page，**不是** _report_form_cat_options
        html = config.render_category_form_page(conn, None)
        self.assertIn("\u3000子类", html, "子分类 option 未带全角缩进")
        self.assertIn("\u3000\u3000孙类", html, "孙分类 option 未带两级全角缩进")
        # 父分类（depth=0）不得带任何缩进前缀
        self.assertIn(">父类</option>", html, "父分类不应带缩进")
        conn.close()


class TestTransformRowsSingleSource(unittest.TestCase):
    """B7-4：「筛选 → 嵌套筛选 → 排序」三步链收口到单一实现。"""

    COLS = ["id", "name", "score", "city"]
    ROWS = [
        (1, "alice", 90, "北京"),
        (2, "bob", 55, "上海"),
        (3, "carol", 77, "北京"),
        (4, "dave", 55, "广州"),
        (5, None, 100, "上海"),
        (6, "eve", None, None),
    ]

    def test_transform_rows_exists_and_returns_list(self):
        """共享层必须导出 transform_rows 且返回列表。"""
        import result_transform
        self.assertTrue(hasattr(result_transform, "transform_rows"))
        out = result_transform.transform_rows(
            self.ROWS, self.COLS, [], [], None)
        self.assertIsInstance(out, list)

    def test_no_transform_is_identity(self):
        """无筛选 / 无排序时恒等（收口后「无排序」路径行为不变的硬依据）。"""
        import result_transform
        for filters, sorts in (([], []), (None, None), ([], None), (None, [])):
            self.assertEqual(
                result_transform.transform_rows(
                    self.ROWS, self.COLS, filters, sorts, None),
                self.ROWS,
                f"空变换不恒等 filters={filters!r} sorts={sorts!r}")

    def test_report_transform_rows_delegates(self):
        """report._transform_rows 必须委托（名字保留，供派生缓存调用）。"""
        import report
        self.assertTrue(hasattr(report, "_transform_rows"))
        self.assertIs(report.transform_rows,
                      __import__("result_transform").transform_rows,
                      "report 未引用共享实现")

    def test_report_delegation_equals_shared(self):
        """委托后 report 与共享层输出逐元素相同。"""
        import report
        import result_transform
        for filters, nested, sorts in (
                ([("city", "=", "北京")], None, [("score", "desc")]),
                ([], {"logic": "and", "conditions": [
                    {"column": "city", "op": "=", "value": "北京"}]}, []),
                (None, {"logic": "or", "conditions": [
                    {"column": "name", "op": "=", "value": "bob"},
                    {"column": "name", "op": "=", "value": "carol"}]},
                 [("name", "asc")]),
                ([("score", ">", "60")], None, None),
        ):
            self.assertEqual(
                report._transform_rows(
                    self.ROWS, self.COLS, filters, sorts, nested),
                result_transform.transform_rows(
                    self.ROWS, self.COLS, filters, sorts, nested))

    def test_export_path_uses_shared_transform(self):
        """导出路径必须调用共享 transform_rows（不再内联三步链）。"""
        import export
        self.assertTrue(hasattr(export, "transform_rows"),
                        "export 未导入共享实现")
        import result_transform
        self.assertIs(export.transform_rows, result_transform.transform_rows)

    def test_nested_filter_only_when_truthy(self):
        """nested_filter 为空/假值时跳过嵌套筛选（语义与收口前一致）。"""
        import result_transform
        base = result_transform.transform_rows(
            self.ROWS, self.COLS, [], [], None)
        for falsy in (None, {}, []):
            self.assertEqual(
                result_transform.transform_rows(
                    self.ROWS, self.COLS, [], [], falsy),
                base,
                f"假值 nested_filter={falsy!r} 不应改变结果")


class TestColumnIndicesReuse(unittest.TestCase):
    """B7-4：report 复用 result_transform.column_indices（真实签名：2 参数 → list）。"""

    def test_signature_is_two_args_returning_list(self):
        """按真实签名断言（plan 里写的 dict/1 参数是错的）。"""
        import result_transform
        self.assertEqual(
            result_transform.column_indices(["n", "v"], ["x", "n", "v"]),
            [1, 2])

    def test_report_uses_shared_helper(self):
        """report 必须导入并复用共享实现，不再自建 col_index_map。"""
        import report
        import result_transform
        self.assertIs(report.column_indices,
                      result_transform.column_indices,
                      "report 未复用 column_indices")

    def test_no_local_col_index_map_left(self):
        """report 中不应再残留 col_index_map 局部推导。"""
        from pathlib import Path
        src = Path("report.py").read_text(encoding="utf-8")
        self.assertNotIn("col_index_map", src,
                         "report.py 仍有 col_index_map 重复实现")

    def test_no_inline_chain_left_in_export(self):
        """export.py 不应再内联三步链。"""
        from pathlib import Path
        src = Path("export.py").read_text(encoding="utf-8")
        self.assertNotIn("filter_rows_nested(rows",
                         src, "export.py 仍内联调用 filter_rows_nested")
        self.assertIn("transform_rows(rows", src,
                      "export.py 未调用共享 transform_rows")
