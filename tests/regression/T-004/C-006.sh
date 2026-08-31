#!/usr/bin/env bash
# C-006 FR-016：构建器应用按钮将嵌套筛选 JSON 写入筛选表单 ff 的隐藏输入并提交
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from render import build_nested_filter_builder_html
html=build_nested_filter_builder_html(["姓名"], None)
assert "applyNestedFilter" in html
assert "getElementById('ff')" in html, "未定位筛选表单 ff"
assert 'name="nested_filter"' in html, "应用逻辑未写入 nested_filter 隐藏输入"
assert "ff.submit()" in html, "应用逻辑未提交筛选表单"
print("PASS C-006 FR-016 构建器应用嵌套筛选到筛选表单")
PY