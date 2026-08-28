#!/usr/bin/env bash
# C-003 FR-002 表达式大小写不敏感
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestResolveExpression::test_today_case_insensitive -q