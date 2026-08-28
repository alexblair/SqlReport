#!/usr/bin/env bash
for c in C-001 C-002 C-003 C-004 C-005; do bash "tests/regression/T-008/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }; done; echo "S-001 PASS"
