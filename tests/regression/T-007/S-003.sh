#!/usr/bin/env bash
for c in C-004 C-005 C-006 C-007 C-008 C-009 C-010 C-011; do bash "tests/regression/T-007/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }; done; echo "S-003 PASS"
