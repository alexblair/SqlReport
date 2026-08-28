#!/usr/bin/env bash
for pair in "config_system:SPEC-CONFIG" "db_schemas:SPEC-DB-SCHEMAS" "ops_scripts:SPEC-OPS-SCRIPTS" "static_assets:SPEC-STATIC-ASSETS" "readme_reconciliation:SPEC-README-RECON"; do mod="${pair%%:*}"; cid="${pair##*:}"; grep -q "^contract_id: $cid$" ".adocs/specs/$mod.md" || exit 1; done
exit 0
