#!/usr/bin/env bash
# C-010 FR-012 非法操作符
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestValidateNestedFilter::test_invalid_op -q