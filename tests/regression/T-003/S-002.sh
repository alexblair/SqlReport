#!/usr/bin/env bash
# S-002 场景：FR-003 分卷规范
for c in C-005 C-006 C-007; do
  bash "tests/regression/T-003/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }
done
echo "S-002 PASS"
