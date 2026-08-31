#!/usr/bin/env bash
# C-003 FR-003：表达式模板面板——无参数点击即插入，有参数弹窗后插入
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from render import build_nested_filter_builder_html
html=build_nested_filter_builder_html(["姓名"], None)
assert "insertExpr('now()')" in html, "缺失 now() 插入按钮"
assert "insertExpr('today()')" in html, "缺失 today() 插入按钮"
assert "nfToggleDateForm('add')" in html, "缺失 date_add 弹出入口"
assert "nfToggleDateForm('sub')" in html, "缺失 date_sub 弹出入口"
assert 'id="nf-date-n"' in html and 'id="nf-date-u"' in html, "缺失参数输入表单"
assert "nfInsertDate" in html, "缺失参数表单确定插入逻辑"
print("PASS C-003 FR-003 表达式模板面板点击/弹窗插入")
PY