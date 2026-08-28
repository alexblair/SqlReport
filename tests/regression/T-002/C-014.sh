#!/usr/bin/env bash
# C-014 FR-004 GET 通道解析 nested_filter（URL 编码 JSON）
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveNestedFilter::test_get_nested_filter_parsed -q
