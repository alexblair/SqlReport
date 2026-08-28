#!/usr/bin/env bash
# C-003: FR-003 T-003 C-001~C-005 核心分卷完整性通过
for c in C-001 C-002 C-003 C-004 C-005; do
  bash "tests/regression/T-003/$c.sh" || exit 1
done
