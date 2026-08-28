#!/usr/bin/env bash
# C-002 FR-002：config_db.md 逐函数契约覆盖关键接口
for kw in get_config_db init_db _get_engine add_pool add_user add_report add_category upsert_schedule get_due_schedules get_api_endpoint_by_path add_api_key delete_expired_sessions; do
  grep -q "$kw" .adocs/specs/modules/config_db.md || exit 1
done
exit 0
