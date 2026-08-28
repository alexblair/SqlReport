#!/usr/bin/env bash
# C-004 FR-002：audit_page.md + scheduler.md 关键接口覆盖
for kw in handle_audit_request _rotate_expired _handle_clean _export_csv _collect_filters; do
  grep -q "$kw" .adocs/specs/modules/audit_page.md || exit 1
done
for kw in ReportScheduler start shutdown run_tick run_startup_scan trigger_schedule run_keepalive_tick evaluate_exclusions validate_exclusions compute_next_run start_scheduler_from_config shutdown_scheduler trigger_manual; do
  grep -q "$kw" .adocs/specs/modules/scheduler.md || exit 1
done
exit 0
