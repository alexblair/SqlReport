#!/usr/bin/env bash
# S-001: 全 FR 基线覆盖验证
for c in C-001 C-002 C-003 C-004 C-005 C-006 C-007 C-008 C-009 C-010; do
  bash "tests/regression/T-013/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
