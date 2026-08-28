#!/usr/bin/env bash
# C-004 FR-002 date_add(now(),7,day)
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestResolveExpression::test_date_add -q