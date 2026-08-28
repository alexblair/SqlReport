#!/usr/bin/env bash
# C-019 FR-012 非合法 JSON → 抛 ValueError 且荷载含修正建议
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveParamsNested::test_malformed_json_raises_valueerror -q
