#!/usr/bin/env bash
# C-005 FR-002 月末裁剪
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestResolveExpression::test_date_add_month -q