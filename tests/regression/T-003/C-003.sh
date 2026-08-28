#!/usr/bin/env bash
# C-003 FR-002：api_handler.md 逐函数契约覆盖关键接口
for kw in handle_api_request generate_api_key _execute_api_query _format_output _validate_api_key _run_normal_api_request; do
  grep -q "$kw" .adocs/specs/modules/api_handler.md || exit 1
done
exit 0
