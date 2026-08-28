#!/usr/bin/env bash
# S-003: 规则基线（FR-001/002/003/005/006/007/008/009/010）
for c in C-009 C-010 C-011 C-012 C-013 C-014 C-015 C-016 C-017; do
  bash "tests/regression/T-009/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }
done
echo "S-003 PASS"
