#!/usr/bin/env bash
for c in C-006 C-007; do bash "tests/regression/T-008/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }; done; echo "S-002 PASS"
