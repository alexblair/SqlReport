#!/usr/bin/env bash
# C-016 FR-005 嵌套筛选与端点预设 filters 并存（不互相覆盖）
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_api_nested_filter.py::TestResolveParamsNested::test_coexist_with_preset_filters -q
