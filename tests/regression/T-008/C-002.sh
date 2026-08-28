#!/usr/bin/env bash
[ -f .adocs/specs/db_schemas.md ] || exit 1
for kw in connection_pools users report_configs report_categories sessions api_endpoints api_keys report_schedules schedule_reports audit_logs config_db audit_db; do grep -q "$kw" .adocs/specs/db_schemas.md || exit 1; done
exit 0
