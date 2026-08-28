#!/usr/bin/env bash
# C-007 FR-011 中文列名/值
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestFilterRowsNested::test_chinese_columns -q