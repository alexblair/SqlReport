#!/usr/bin/env bash
# C-004 FR-009：不引用 copy 目录
! grep -rE '/opdev/SqlReport copy/[A-Za-z0-9_.-]+' .adocs/specs/modules/ 2>/dev/null
