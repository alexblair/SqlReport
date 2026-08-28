#!/usr/bin/env bash
# C-002 FR-002：export/db/markdown_render 关键接口覆盖
for kw in rows_to_csv export_report_to_csv export_report_to_json handle_export; do
  grep -q "$kw" .adocs/specs/modules/export.md || exit 1
done
for kw in get_config_db init_db get_report get_pool add_report update_report delete_report get_user add_user get_all_pools add_pool get_api_endpoint get_api_key upsert_schedule get_due_schedules; do
  grep -q "$kw" .adocs/specs/modules/db.md || exit 1
done
for kw in render_markdown contains_mermaid extract_mermaid_blocks codehilite_css; do
  grep -q "$kw" .adocs/specs/modules/markdown_render.md || exit 1
done
exit 0
