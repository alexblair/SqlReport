#!/usr/bin/env bash
# S-001 FR-002 支撑服务分卷覆盖
for c in C-001 C-002; do
  bash "tests/regression/T-005/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
