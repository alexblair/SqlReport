#!/usr/bin/env bash
# S-001: FR-007 flow_docs_check 工具验证
for c in C-001; do
  bash "tests/regression/T-011/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
