#!/usr/bin/env bash
# C-001 FR-016：条件构建器字段下拉来自报表列配置（含中文列名）
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from render import build_nested_filter_builder_html
cols=["姓名","项目状态","创建日期"]
html=build_nested_filter_builder_html(cols, None)
for c in cols:
    assert c in html, f"列 {c} 未出现在构建器下拉中"
print("PASS C-001 FR-016 字段下拉含中文列名")
PY