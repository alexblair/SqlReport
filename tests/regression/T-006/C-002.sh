#!/usr/bin/env bash
# C-002 FR-003：front-matter 六字段 + 六段正文齐全
for f in render branding export db markdown_render; do
  m=".adocs/specs/modules/$f.md"
  for field in module contract_id version depends_on last_reviewed_commit last_reviewed_at; do grep -q "^$field: " "$m" || exit 1; done
  for sec in "1. 职责概述" "2. 公开 API 契约" "3. 数据流" "4. 依赖关系" "5. 边界与异常" "6. 保鲜核对提交点"; do grep -q "## $sec" "$m" || exit 1; done
done
exit 0
