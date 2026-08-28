#!/usr/bin/env bash
# C-017 FR-007 API 参数透传：_resolve_params 返回 nested_filter 元组项
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveParamsNested::test_returns_nested_filter_in_tuple -q
