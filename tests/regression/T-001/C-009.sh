#!/usr/bin/env bash
# C-009 FR-012 非法列名
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestValidateNestedFilter::test_invalid_column -q