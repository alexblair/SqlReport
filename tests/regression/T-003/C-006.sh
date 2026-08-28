#!/usr/bin/env bash
# C-006 FR-003：四份分卷六段正文结构齐全
for f in report api_handler query_executor result_transform; do
  m=".adocs/specs/modules/$f.md"
  for sec in "1. 职责概述" "2. 公开 API 契约" "3. 数据流" "4. 依赖关系" "5. 边界与异常" "6. 保鲜核对提交点"; do
    grep -q "## $sec" "$m" || exit 1
  done
done
exit 0
