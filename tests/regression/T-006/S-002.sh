#!/usr/bin/env bash
for c in C-002 C-003; do bash "tests/regression/T-006/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }; done; echo "S-002 PASS"
