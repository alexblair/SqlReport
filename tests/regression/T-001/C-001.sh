#!/usr/bin/env bash
# C-001 FR-001 三层嵌套递归求值
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestFilterRowsNested::test_deep_nesting -q