#!/usr/bin/env bash
# C-015 FR-004 POST 通道解析 nested_filter（请求体字段）
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveNestedFilter::test_post_nested_filter_parsed -q
