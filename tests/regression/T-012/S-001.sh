#!/usr/bin/env bash
# S-001: FR-005 保鲜约束固化验证
for c in C-001; do
  bash "tests/regression/T-012/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
