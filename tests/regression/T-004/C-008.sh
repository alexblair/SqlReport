#!/usr/bin/env bash
# C-008 FR-010：filter_help 新增的嵌套筛选表达式帮助内容结构正确
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from filter_help import nested_filter_help_content, render_nested_filter_help_popup
c=nested_filter_help_content()
assert "sections" in c and len(c["sections"]) >= 5, "帮助分区不足"
for sec in c["sections"]:
    assert sec["desc"] and sec["examples"], f"分区 {sec['title']} 缺说明或举例"
popup=render_nested_filter_help_popup()
assert "nf-help-popup" in popup and "toggleNestedHelp" in popup
print("PASS C-008 FR-010 嵌套筛选表达式帮助内容完整")
PY