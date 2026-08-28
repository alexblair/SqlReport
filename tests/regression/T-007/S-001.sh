#!/usr/bin/env bash
bash tests/regression/T-007/C-001.sh >/dev/null 2>&1 && echo "S-001 PASS" || echo "S-001 FAIL"
