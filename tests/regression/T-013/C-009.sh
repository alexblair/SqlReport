#!/usr/bin/env bash
# C-009: FR-009 无 copy 文件引用
! grep -rE '/opdev/SqlReport copy/[A-Za-z0-9_.-]+' .adocs/specs/ 2>/dev/null
