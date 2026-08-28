#!/usr/bin/env bash
# C-006 FR-009：知识库文档不得直接地址引用 copy 目录内的具体文件（/opdev/SqlReport copy/<文件名> 形式）
! grep -rE '/opdev/SqlReport copy/[A-Za-z0-9_.-]+' .adocs/specs/ 2>/dev/null
