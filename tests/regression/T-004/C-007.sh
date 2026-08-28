#!/usr/bin/env bash
# C-007 FR-003：contract_id 遵循 MOD- 命名规范
grep -q '^contract_id: MOD-CONFIG_DB$' .adocs/specs/modules/config_db.md || exit 1
grep -q '^contract_id: MOD-CONFIG$' .adocs/specs/modules/config.md || exit 1
grep -q '^contract_id: MOD-APP_CONFIG$' .adocs/specs/modules/app_config.md || exit 1
grep -q '^contract_id: MOD-AUTH$' .adocs/specs/modules/auth.md || exit 1
exit 0
