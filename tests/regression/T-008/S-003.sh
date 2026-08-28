#!/usr/bin/env bash
for c in C-008 C-009 C-010 C-011 C-012 C-013 C-014 C-015; do bash "tests/regression/T-008/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }; done; echo "S-003 PASS"
