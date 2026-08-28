#!/usr/bin/env bash
for c in C-003 C-004 C-005 C-006 C-007 C-008 C-009 C-010 C-011 C-012 C-013 C-014 C-015; do bash "tests/regression/T-009/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }; done; echo "S-002 PASS"
