#!/usr/bin/env bash
# C-008 FR-002 表达式参与比较
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestFilterRowsNested::test_expression_val -q