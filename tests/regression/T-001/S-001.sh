#!/usr/bin/env bash
# S-001 场景：FR-008 主仓安全边界全链路（排除条目 + 忽略/未跟踪 + 无导读 + 工作区干净）
for c in C-001 C-002 C-003 C-004; do
  bash "tests/regression/T-001/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
