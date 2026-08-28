#!/usr/bin/env bash
# C-004 FR-002：app_config.md 与 auth.md 逐函数契约覆盖
for kw in get_config reload_config get_server_config safe_int parse_form_urlencoded ensure_api_prefix strip_api_prefix serialize_smart_quotes; do
  grep -q "$kw" .adocs/specs/modules/app_config.md || exit 1
done
for kw in create_session get_session_user refresh_session remove_session hash_password verify_password is_login_blocked parse_cookie extract_bearer_token; do
  grep -q "$kw" .adocs/specs/modules/auth.md || exit 1
done
exit 0
