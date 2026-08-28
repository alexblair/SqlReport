#!/usr/bin/env bash
# C-006 FR-003：五份分卷 front-matter 六字段齐全
for f in redis_cache audit_db audit_page scheduler server; do
  m=".adocs/specs/modules/$f.md"
  grep -q '^module: ' "$m" || exit 1
  grep -q '^contract_id: MOD-' "$m" || exit 1
  grep -q '^version: ' "$m" || exit 1
  grep -q '^depends_on: ' "$m" || exit 1
  grep -q '^last_reviewed_commit: ' "$m" || exit 1
  grep -q '^last_reviewed_at: ' "$m" || exit 1
done
exit 0
