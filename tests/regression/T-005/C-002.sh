#!/usr/bin/env bash
# C-002 FR-002：redis_cache.md 关键接口覆盖
for kw in ReportSnapshot get_redis_manager redis_available reset_redis_manager compute_config_version build_snapshot_key build_lock_key RedisConnectionManager acquire_lock release_lock wait_for_lock get_snapshot set_snapshot scan_snapshots; do
  grep -q "$kw" .adocs/specs/modules/redis_cache.md || exit 1
done
exit 0
