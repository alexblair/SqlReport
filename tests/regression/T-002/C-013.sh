#!/usr/bin/env bash
# C-013 FR-008：.gitignore 含 .adocs/ 排除规则，未跟踪 .adocs 新路径仍被忽略
# 修正说明：治理资产显式跟踪后，断言从「未跟踪」更新为「排除规则仍匹配未跟踪新路径」（T-001/C-002 同步修正）
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp
