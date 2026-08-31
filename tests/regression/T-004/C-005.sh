#!/usr/bin/env bash
# C-005 FR-014：禁止新建模块——构建器在 render.py、帮助在 filter_help.py，无新增顶层 .py
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
import subprocess
st=subprocess.run(["git","status","--porcelain"],cwd="/opdev/SqlReport",capture_output=True,text=True).stdout
newpy=[l for l in st.splitlines() if l.startswith("??") and l.endswith(".py")]
import render as rp, filter_help as fh
assert hasattr(rp,"build_nested_filter_builder_html")
assert hasattr(fh,"render_nested_filter_help_popup") and hasattr(fh,"nested_filter_help_content")
assert not newpy, f"存在新增 .py 模块: {newpy}"
print("PASS C-005 FR-014 未新增模块文件")
PY