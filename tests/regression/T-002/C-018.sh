#!/usr/bin/env bash
# C-018 FR-015 非法操作符 → 抛 ValueError（荷载结构化错误，转 400）
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveNestedFilter::test_invalid_nested_filter_raises_valueerror -q
