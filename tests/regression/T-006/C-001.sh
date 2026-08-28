#!/usr/bin/env bash
# C-001 FR-002：五模块分卷文件存在 + 全部关键接口覆盖
for f in render branding export db markdown_render; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
for kw in render_navbar render_page_header render_page_footer render_audit_page format_cell build_flash_html build_pagination_html build_table_header_html build_table_body_html build_controls_bar_html ensure_common_assets reset_common_assets content_hash8; do grep -q "$kw" .adocs/specs/modules/render.md || exit 1; done
for kw in wrap_ico build_default_favicon build_color_favicon normalize_color clean_base64_image detect_image_type save_custom_favicon load_custom_favicon read_site_settings write_site_settings get_site_branding invalidate_site_branding_cache resolve_favicon_bytes; do grep -q "$kw" .adocs/specs/modules/branding.md || exit 1; done
for kw in rows_to_csv export_report_to_csv export_report_to_json handle_export; do grep -q "$kw" .adocs/specs/modules/export.md || exit 1; done
for kw in get_config_db init_db get_report get_pool add_report update_report delete_report get_user add_user get_all_pools add_pool get_api_endpoint get_api_key upsert_schedule get_due_schedules; do grep -q "$kw" .adocs/specs/modules/db.md || exit 1; done
for kw in render_markdown contains_mermaid extract_mermaid_blocks codehilite_css; do grep -q "$kw" .adocs/specs/modules/markdown_render.md || exit 1; done
exit 0
