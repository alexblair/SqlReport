#!/usr/bin/env bash
# C-005 FR-002：server.md 关键接口覆盖
for kw in setup_logging main ReportHandler _handle _authenticate _handle_login _handle_login_get _handle_home_redirect _handle_logout _handle_health _handle_config _handle_report _handle_export _handle_api _handle_audit _serve_static_vendor _sanitize_next_url _render_error_page; do
  grep -q "$kw" .adocs/specs/modules/server.md || exit 1
done
exit 0
