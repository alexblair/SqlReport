#!/usr/bin/env bash
# C-003 FR-002：config.md 逐函数契约覆盖关键接口
for kw in handle_request handle_pool_test handle_report_add handle_batch_delete render_scheduler_page handle_scheduler_save handle_api_endpoints_request handle_site_branding_save handle_import_test_cases render_overview; do
  grep -q "$kw" .adocs/specs/modules/config.md || exit 1
done
exit 0
