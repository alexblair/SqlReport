#!/usr/bin/env bash
# C-001 FR-008：.gitignore 包含 .adocs/ 精确排除条目
grep -qE '^\.adocs/$' .gitignore
