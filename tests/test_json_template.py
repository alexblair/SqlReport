"""
test_json_template.py — JSON 输出模板引擎测试

模板语法：JSON 占位符替换。模板本身是一段 JSON 文本，
值位置以 {{占位符}} 引用上下文数据，替换后必须是合法 JSON。
"""

import json
import unittest

from json_template import (
    SINGLE_KEYS, ALL_KEYS,
    is_template_enabled, validate_template, render_template,
)


class TestIsTemplateEnabled(unittest.TestCase):
    """模板留空 = 未启用。"""

    def test_empty(self):
        self.assertFalse(is_template_enabled(""))
        self.assertFalse(is_template_enabled(None))

    def test_blank(self):
        self.assertFalse(is_template_enabled("   \n\t "))

    def test_nonblank(self):
        self.assertTrue(is_template_enabled("{}"))
        self.assertTrue(is_template_enabled("  {  }  "))


class TestRenderBasic(unittest.TestCase):
    """合法模板渲染正确。"""

    def _ctx(self, **overrides):
        ctx = {
            "data": [{"单价": 500, "物资名称": "示例"}],
            "total": 1, "page": 1, "page_size": 20, "total_pages": 1,
            "full": False, "meta": None,
        }
        ctx.update(overrides)
        return ctx

    def test_rename_data_key(self):
        template = '{"rand99": {{data}}, "total": {{total}}}'
        ok, output, error = render_template(template, self._ctx())
        self.assertTrue(ok, error)
        parsed = json.loads(output)
        self.assertEqual(list(parsed.keys()), ["rand99", "total"])
        self.assertEqual(parsed["rand99"], [{"单价": 500, "物资名称": "示例"}])
        self.assertEqual(parsed["total"], 1)

    def test_placeholder_at_any_position(self):
        # 占位符出现在数组元素、对象值、多层嵌套位置
        template = ('[{{data}}, {{total}}, {"page": {{page}}, '
                    '"nested": {"x": {{total_pages}}}}]')
        ok, output, error = render_template(
            template, self._ctx(data=[1], total=5, page=2, total_pages=3))
        self.assertTrue(ok, error)
        parsed = json.loads(output)
        self.assertEqual(parsed, [[1], 5, {"page": 2, "nested": {"x": 3}}])

    def test_string_value_placeholder(self):
        # mode 是字符串值，替换为带引号 JSON 片段
        ctx = {"results": [], "mode": "all", "page": 1, "page_size": 20,
               "full": False}
        ok, output, error = render_template(
            '{"m": {{mode}}, "results": {{results}}}', ctx)
        self.assertTrue(ok, error)
        parsed = json.loads(output)
        self.assertEqual(parsed["m"], "all")

    def test_full_false_replaced_with_false(self):
        ok, output, error = render_template(
            '{"full": {{full}}}', self._ctx())
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"full": False})

    def test_meta_missing_is_null(self):
        # meta 键缺失（普通链路不提供）→ 替换为 null，而非报错
        ctx = self._ctx()
        del ctx["meta"]
        ok, output, error = render_template('{"meta": {{meta}}}', ctx)
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"meta": None})

    def test_meta_object_rendered(self):
        meta = {"generated_at": "2026-08-05 10:00:00 +0800",
                "expires_at": None, "config_version": "abc"}
        ok, output, error = render_template(
            '{"meta": {{meta}}}', self._ctx(meta=meta))
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output)["meta"], meta)

    def test_meta_non_object_value_rendered(self):
        # 缺口 20：meta 为非对象值（列表/字符串/数值）时按普通值序列化，不抛异常
        ok, output, error = render_template(
            '{"meta": {{meta}}}', self._ctx(meta=[1, 2, 3]))
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"meta": [1, 2, 3]})

        ok, output, error = render_template(
            '{"meta": {{meta}}}', self._ctx(meta="str-meta"))
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"meta": "str-meta"})

        ok, output, error = render_template(
            '{"meta": {{meta}}}', self._ctx(meta=42))
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"meta": 42})

    def test_chinese_keys_and_values(self):
        template = ('{"物资列表": {{data}}, "总行数": {{total}}}')
        ok, output, error = render_template(template, self._ctx())
        self.assertTrue(ok, error)
        parsed = json.loads(output)
        self.assertEqual(list(parsed.keys()), ["物资列表", "总行数"])
        self.assertEqual(parsed["物资列表"], [{"单价": 500, "物资名称": "示例"}])

    def test_non_ascii_kept_not_escaped(self):
        # ensure_ascii=False 语义：输出直接含中文字符而非 \uXXXX
        ok, output, error = render_template(
            '{{data}}', self._ctx(data=[{"名称": "物资"}]))
        self.assertTrue(ok, error)
        self.assertIn("物资", output)
        self.assertNotIn("\\u", output)


class TestRenderErrors(unittest.TestCase):
    """错误路径：未知占位符与非法 JSON，错误含行列号。"""

    def _ctx(self):
        return {"data": [1], "total": 1, "page": 1, "page_size": 20,
                "total_pages": 1, "full": False, "meta": None}

    def test_unknown_placeholder_reported(self):
        ok, output, error = render_template(
            '{"a": {{data}}, "b": {{nope}}}', self._ctx())
        self.assertFalse(ok)
        self.assertIn("nope", error)
        self.assertIn("行", error)
        self.assertIn("列", error)

    def test_key_inside_keyset_missing_is_null(self):
        # 键集内键缺失（如普通链路无 meta）→ null；键集外键 → 报错
        ctx = self._ctx()
        del ctx["meta"]
        ok, output, error = render_template('{"m": {{meta}}}', ctx)
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"m": None})
        ok, output, error = render_template('{"x": {{nope}}}', ctx)
        self.assertFalse(ok)

    def test_unknown_placeholder_line_col_correct(self):
        template = '{\n  "a": {{data}},\n  "b": {{bad}}\n}'
        ok, output, error = render_template(template, self._ctx())
        self.assertFalse(ok)
        self.assertIn("第 3 行", error)

    def test_invalid_json_trailing_comma(self):
        template = '{"a": {{data}},}'
        ok, output, error = render_template(template, self._ctx())
        self.assertFalse(ok)
        self.assertIn("JSON", error)
        self.assertIn("行", error)

    def test_invalid_json_line_col_correct(self):
        template = '{\n  "a": 1,\n  "b": {{data}}x\n}'
        ok, output, error = render_template(template, self._ctx())
        self.assertFalse(ok)
        self.assertIn("第 3 行", error)

    def test_missing_quote(self):
        template = '{"a": {{total}}'
        ok, output, error = render_template(template, self._ctx())
        self.assertFalse(ok)

    def test_adjacent_placeholders_matched_independently(self):
        # 缺口 21：相邻占位符 {{a}}{{b}} 各自独立匹配替换
        ok, output, error = render_template(
            '"{{total}}{{page}}"', {"total": 1, "page": 2,
                                    "data": [], "page_size": 20,
                                    "total_pages": 1, "full": False, "meta": None})
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), "12")

    def test_unclosed_placeholder_left_as_text(self):
        # 缺口 21：未闭合占位符（缺 }}}）不匹配正则，原样保留为文本
        ok, output, error = render_template(
            '{"raw": "{{unclosed"}', self._ctx())
        self.assertTrue(ok, error)
        self.assertEqual(json.loads(output), {"raw": "{{unclosed"})

    def test_render_blank_template(self):
        ok, output, error = render_template("   ", self._ctx())
        self.assertFalse(ok)
        self.assertIn("模板为空", error)


class TestValidate(unittest.TestCase):
    """校验：留空通过、未知键拒绝、跨模式键拒绝、合法通过。"""

    def test_blank_template_ok(self):
        ok, error = validate_template("", SINGLE_KEYS)
        self.assertTrue(ok, error)

    def test_valid_single_template_ok(self):
        ok, error = validate_template(
            '{"rand99": {{data}}, "total": {{total}}}', SINGLE_KEYS)
        self.assertTrue(ok, error)

    def test_valid_all_template_ok(self):
        ok, error = validate_template(
            '{"results": {{results}}, "mode": {{mode}}}', ALL_KEYS)
        self.assertTrue(ok, error)

    def test_single_rejects_all_keys(self):
        ok, error = validate_template('{"results": {{results}}}', SINGLE_KEYS)
        self.assertFalse(ok)
        self.assertIn("results", error)

    def test_all_rejects_single_keys(self):
        ok, error = validate_template('{"data": {{data}}}', ALL_KEYS)
        self.assertFalse(ok)
        self.assertIn("data", error)

    def test_rejects_unknown_key(self):
        ok, error = validate_template('{"x": {{foo}}}', SINGLE_KEYS)
        self.assertFalse(ok)
        self.assertIn("foo", error)

    def test_rejects_invalid_json(self):
        ok, error = validate_template('{"a": {{data}},}', SINGLE_KEYS)
        self.assertFalse(ok)
        self.assertIn("JSON", error)

    def test_invalid_keyset_raises_value_error(self):
        # 缺口 22：非法键集（不在 SINGLE_KEYS/ALL_KEYS 内）直接抛 ValueError
        with self.assertRaises(ValueError):
            validate_template('{"data": {{data}}}', ("bogus",))
        with self.assertRaises(ValueError):
            validate_template('{"data": {{data}}}', None)


if __name__ == "__main__":
    unittest.main()
