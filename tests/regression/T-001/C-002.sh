#!/usr/bin/env bash
# C-002 FR-008：.gitignore 含 .adocs/ 排除规则，未跟踪的 .adocs 新路径仍被忽略（不随默认 add 公开）
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp
