#!/usr/bin/env bash
# C-007 FR-003：contract_id 遵循 MOD-<模块大写下划线> 规范
grep -q '^contract_id: MOD-REPORT$' .adocs/specs/modules/report.md || exit 1
grep -q '^contract_id: MOD-API_HANDLER$' .adocs/specs/modules/api_handler.md || exit 1
grep -q '^contract_id: MOD-QUERY_EXECUTOR$' .adocs/specs/modules/query_executor.md || exit 1
grep -q '^contract_id: MOD-RESULT_TRANSFORM$' .adocs/specs/modules/result_transform.md || exit 1
exit 0
