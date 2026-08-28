#!/usr/bin/env bash
for c in C-001 C-002; do bash "tests/regression/T-009/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }; done; echo "S-001 PASS"
