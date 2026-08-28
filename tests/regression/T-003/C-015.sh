#!/usr/bin/env bash
# C-015 FR-008：.gitignore 含 .adocs/ 排除规则，未跟踪 .adocs 新路径仍被忽略
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp
