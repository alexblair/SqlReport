#!/usr/bin/env bash
# C-003 FR-003：五份分卷 front-matter 六字段 + 六段正文
for f in render branding export db markdown_render; do
  m=".adocs/specs/modules/$f.md"
  grep -q '^module: ' "$m" || exit 1
  grep -q '^contract_id: MOD-' "$m" || exit 1
  grep -q '^version: ' "$m" || exit 1
  grep -q '^depends_on: ' "$m" || exit 1
  grep -q '^last_reviewed_commit: ' "$m" || exit 1
  grep -q '^last_reviewed_at: ' "$m" || exit 1
  for sec in "1. 职责概述" "2. 公开 API 契约" "3. 数据流" "4. 依赖关系" "5. 边界与异常" "6. 保鲜核对提交点"; do
    grep -q "## $sec" "$m" || exit 1
  done
done
exit 0
