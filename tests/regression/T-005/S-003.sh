#!/usr/bin/env bash
# S-003 场景：真相核对/保鲜锚定 + 契约基线
for c in C-009 C-010 C-011 C-012 C-013 C-014 C-015 C-016; do
  bash "tests/regression/T-005/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }
done
echo "S-003 PASS"
