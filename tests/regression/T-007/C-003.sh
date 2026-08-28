#!/usr/bin/env bash
# C-003 FR-003：contract_id MOD- 命名
for pair in "preset_cases:MOD-PRESET_CASES" "static_cache:MOD-STATIC_CACHE" "filter_help:MOD-FILTER_HELP" "json_template:MOD-JSON_TEMPLATE" "file_permissions:MOD-FILE_PERMISSIONS"; do
  mod="${pair%%:*}"; cid="${pair##*:}"
  grep -q "^contract_id: $cid\$" ".adocs/specs/modules/$mod.md" || exit 1
done
exit 0
