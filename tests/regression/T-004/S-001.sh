#!/usr/bin/env bash
# S-001 场景：FR-002 配置与认证分卷覆盖
for c in C-001 C-002 C-003 C-004; do
  bash "tests/regression/T-004/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
