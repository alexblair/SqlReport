#!/usr/bin/env bash
# C-008 FR-003：contract_id 遵循 MOD- 命名规范
for pair in "redis_cache:MOD-REDIS_CACHE" "audit_db:MOD-AUDIT_DB" "audit_page:MOD-AUDIT_PAGE" "scheduler:MOD-SCHEDULER" "server:MOD-SERVER"; do
  mod="${pair%%:*}"; cid="${pair##*:}"
  grep -q "^contract_id: $cid\$" ".adocs/specs/modules/$mod.md" || exit 1
done
exit 0
