#!/usr/bin/env bash
# C-004 FR-003：contract_id MOD- 命名
for pair in "render:MOD-RENDER" "branding:MOD-BRANDING" "export:MOD-EXPORT" "db:MOD-DB" "markdown_render:MOD-MARKDOWN_RENDER"; do
  mod="${pair%%:*}"; cid="${pair##*:}"
  grep -q "^contract_id: $cid\$" ".adocs/specs/modules/$mod.md" || exit 1
done
exit 0
