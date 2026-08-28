#!/usr/bin/env bash
# C-003 FR-002：audit_db.md 关键接口覆盖
for kw in get_audit_db init_audit_db record_operation insert_audit_log query_audit_logs count_audit_logs export_audit_logs rotate_audit_logs delete_audit_logs get_recent_schedule_events; do
  grep -q "$kw" .adocs/specs/modules/audit_db.md || exit 1
done
exit 0
