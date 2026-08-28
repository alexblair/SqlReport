#!/usr/bin/env bash
# C-002 FR-001 嵌套 AND/OR 混合
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestFilterRowsNested::test_nested_and_or -q