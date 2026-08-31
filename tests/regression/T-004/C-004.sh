#!/usr/bin/env bash
# C-004 FR-009/FR-010：每个值输入框旁内嵌悬浮提示与示例；帮助来自 filter_help 且通俗易懂
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from render import build_nested_filter_builder_html
from filter_help import render_nested_filter_help_popup, nested_filter_help_content
html=build_nested_filter_builder_html(["姓名"], None)
assert "toggleNestedHelp(this)" in html, "值输入框缺少内嵌帮助按钮"
assert 'class="nf-example"' in html, "值输入框缺少内嵌示例提示"
assert 'id="nf-help-popup"' in html, "缺少共享帮助弹窗"
content=nested_filter_help_content()
flat=str(content)
assert "now()" in flat and "date_add" in flat, "帮助内容缺少表达式举例"
assert "不需要" in flat or "无需" in flat, "帮助文案未用通俗语言"
print("PASS C-004 FR-009/FR-010 内嵌提示与通俗帮助")
PY