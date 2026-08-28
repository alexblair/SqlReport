#!/usr/bin/env bash
for f in .adocs/specs/config_system.md .adocs/specs/db_schemas.md .adocs/specs/ops_scripts.md .adocs/specs/static_assets.md .adocs/specs/readme_reconciliation.md; do ref=$(grep '^last_reviewed_commit: ' "$f" | sed 's/.*: //' | xargs); [ -n "$ref" ] || exit 1; git cat-file -e "$ref^{commit}" || exit 1; done
exit 0
