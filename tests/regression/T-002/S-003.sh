#!/usr/bin/env bash
# S-003 场景：契约基线声明 + 治理资产排除（FR-002/004/005/006/007 基线 + FR-008 排除语义）
for c in C-008 C-009 C-010 C-011 C-012 C-013; do
  bash "tests/regression/T-002/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }
done
echo "S-003 PASS"
