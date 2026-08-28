#!/usr/bin/env bash
# C-001 FR-002：五模块分卷文件存在 + redis_cache/audit_db 关键接口覆盖
for f in redis_cache audit_db audit_page scheduler server; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
for kw in ReportSnapshot get_redis_manager redis_available reset_redis_manager compute_config_version build_snapshot_key build_lock_key RedisConnectionManager acquire_lock release_lock wait_for_lock get_snapshot set_snapshot scan_snapshots; do
  grep -q "$kw" .adocs/specs/modules/redis_cache.md || exit 1
done
for kw in get_audit_db init_audit_db record_operation insert_audit_log query_audit_logs count_audit_logs export_audit_logs rotate_audit_logs delete_audit_logs get_recent_schedule_events; do
  grep -q "$kw" .adocs/specs/modules/audit_db.md || exit 1
done
exit 0
