#!/usr/bin/env bash
# S-002 场景：FR-009 copy 只读与引用约束（未修改 + 不直接地址引用 + 有效只读副本）
for c in C-005 C-006 C-007; do
  bash "tests/regression/T-001/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }
done
echo "S-002 PASS"
