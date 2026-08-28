#!/usr/bin/env bash
[ -f .adocs/specs/config_system.md ] || exit 1
for kw in server log redis static_cache file_permissions config_db audit_db scheduler load_config; do grep -q "$kw" .adocs/specs/config_system.md || exit 1; done
exit 0
