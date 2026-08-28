#!/usr/bin/env bash
# C-014 FR-009：知识库文档不直接地址引用 copy 目录内具体文件
! grep -rE '/opdev/SqlReport copy/[A-Za-z0-9_.-]+' .adocs/specs/ 2>/dev/null
