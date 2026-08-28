#!/usr/bin/env bash
# C-001 FR-002：核心链路四模块分卷文件存在
for f in report api_handler query_executor result_transform; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
exit 0
