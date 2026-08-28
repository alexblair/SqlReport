"""T-002：API 嵌套筛选参数解析单元测试（FR-004/FR-005/FR-007/FR-012/FR-015）。

覆盖：
- GET/POST 双通道解析 nested_filter（URL 编码 JSON / 请求体字段）
- 空/缺失 nested_filter 视为无嵌套筛选（与既有筛选并存，FR-005）
- 非法条件经 validate_nested_filter() 校验抛 ValueError，荷载为结构化错误 JSON（FR-012/FR-015）
"""
import json
import unittest

import api_handler


class TestResolveNestedFilter(unittest.TestCase):
    def test_no_nested_filter_returns_none(self):
        self.assertIsNone(api_handler._resolve_nested_filter("GET", "", {}, {}))

    def test_get_nested_filter_parsed(self):
        payload = {"op": "and", "conditions": [
            {"col": "name", "op": "contains", "value": "a"}]}
        qp = {"nested_filter": [json.dumps(payload)]}
        self.assertEqual(api_handler._resolve_nested_filter("GET", "", qp, {}), payload)

    def test_post_nested_filter_parsed(self):
        payload = {"op": "or", "conditions": [
            {"col": "age", "op": "gt", "value": "10"}]}
        body = json.dumps({"nested_filter": payload})
        self.assertEqual(
            api_handler._resolve_nested_filter(
                "POST", body, {}, {"Content-Type": "application/json"}),
            payload)

    def test_invalid_nested_filter_raises_valueerror(self):
        bad = {"op": "and", "conditions": [
            {"col": "name", "op": "regex", "value": "x"}]}
        qp = {"nested_filter": [json.dumps(bad)]}
        with self.assertRaises(ValueError) as ctx:
            api_handler._resolve_nested_filter("GET", "", qp, {})
        err = json.loads(ctx.exception.args[0])
        self.assertFalse(err["valid"])
        self.assertTrue(any("regex" in e["message"] for e in err["errors"]))

    def test_empty_dict_noop(self):
        self.assertIsNone(
            api_handler._resolve_nested_filter("GET", "", {"nested_filter": ["{}"]}, {}))


class TestResolveParamsNested(unittest.TestCase):
    def _endpoint(self):
        return {"filters": "", "sorts": "", "row_limit": 0,
                "columns": None, "output_format": "json", "allow_fetch_all": 1}

    def test_returns_nested_filter_in_tuple(self):
        payload = {"op": "and", "conditions": [
            {"col": "name", "op": "contains", "value": "a"}]}
        qp = {"nested_filter": [json.dumps(payload)]}
        (filters, _sorts, _page, _ps, _rl, _fmt, _cols, _bom, _fa, nf) = \
            api_handler._resolve_params(self._endpoint(), "GET", "", qp)
        self.assertEqual(nf, payload)
        self.assertEqual(filters, [])

    def test_no_nested_filter_tuple_none(self):
        (filters, _sorts, _page, _ps, _rl, _fmt, _cols, _bom, _fa, nf) = \
            api_handler._resolve_params(self._endpoint(), "GET", "", {})
        self.assertIsNone(nf)

    def test_invalid_tuple_raises_valueerror(self):
        bad = {"op": "and", "conditions": [
            {"col": "name", "op": "nope", "value": "x"}]}
        qp = {"nested_filter": [json.dumps(bad)]}
        with self.assertRaises(ValueError):
            api_handler._resolve_params(self._endpoint(), "GET", "", qp)


if __name__ == "__main__":
    unittest.main()
