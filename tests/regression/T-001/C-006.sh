#!/usr/bin/env bash
# C-006 FR-006 不修改入参
cd "$(git rev-parse --show-toplevel)"
venv/bin/python -m pytest tests/test_nested_filter.py::TestFilterRowsNested::test_not_modifies_original -q