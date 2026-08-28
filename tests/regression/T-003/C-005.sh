#!/usr/bin/env bash
# C-005 FR-003：四份分卷 front-matter 统一六字段齐全
for f in report api_handler query_executor result_transform; do
  m=".adocs/specs/modules/$f.md"
  grep -q '^module: ' "$m" || exit 1
  grep -q '^contract_id: MOD-' "$m" || exit 1
  grep -q '^version: ' "$m" || exit 1
  grep -q '^depends_on: ' "$m" || exit 1
  grep -q '^last_reviewed_commit: ' "$m" || exit 1
  grep -q '^last_reviewed_at: ' "$m" || exit 1
done
exit 0
