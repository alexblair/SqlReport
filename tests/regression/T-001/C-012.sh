#!/usr/bin/env bash
# C-012 FR-012 非数字值
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestValidateNestedFilter::test_numeric_op_non_numeric -q