#!/usr/bin/env bash
for f in config_system db_schemas ops_scripts static_assets readme_reconciliation; do m=".adocs/specs/$f.md"; for field in module contract_id version depends_on last_reviewed_commit last_reviewed_at; do grep -q "^$field: " "$m" || exit 1; done; for sec in "1. 职责概述" "2. 公开 API 契约" "3. 数据流" "4. 依赖关系" "5. 边界与异常" "6. 保鲜核对提交点"; do grep -q "## $sec" "$m" || exit 1; done; done
exit 0
