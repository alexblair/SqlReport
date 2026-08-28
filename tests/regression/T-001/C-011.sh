#!/usr/bin/env bash
# C-011 FR-012 缺 col 空值
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestValidateNestedFilter::test_missing_col -q