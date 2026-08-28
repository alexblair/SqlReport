#!/usr/bin/env bash
# C-001 FR-002：五模块分卷文件存在 + 全部关键接口覆盖
for f in preset_cases static_cache filter_help json_template file_permissions; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
for kw in load_preset setup_test_mysql_tables import_preset_test_cases import_preset_from_file; do grep -q "$kw" .adocs/specs/modules/preset_cases.md || exit 1; done
for kw in strip_json_suffix get_static_cache_config permissions_root resolve_file_path try_read write_file write_versioned_file invalidate record_invalidated get_last_invalidated; do grep -q "$kw" .adocs/specs/modules/static_cache.md || exit 1; done
for kw in filter_help_content render_filter_help FILTER_HINT_SUFFIX; do grep -q "$kw" .adocs/specs/modules/filter_help.md || exit 1; done
for kw in is_template_enabled render_template validate_template SINGLE_KEYS ALL_KEYS; do grep -q "$kw" .adocs/specs/modules/json_template.md || exit 1; done
for kw in load_permissions is_enabled apply_to apply_dirs_from apply_tree refresh_tree; do grep -q "$kw" .adocs/specs/modules/file_permissions.md || exit 1; done
exit 0
