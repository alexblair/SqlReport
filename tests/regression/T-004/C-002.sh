#!/usr/bin/env bash
# C-002 FR-008：条件构建器为 vanilla JS，不引入任何第三方依赖
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
import re
from render import build_nested_filter_builder_html
html=build_nested_filter_builder_html(["姓名"], None)
assert '<script src=' not in html, "出现外部 <script src> 引入"
assert 'cdn' not in html.lower(), "出现 cdn 引用"
assert 'require(' not in html, "出现 require()"
assert 'import ' not in html, "出现 import 语句"
assert 'document.getElementById' in html
print("PASS C-002 FR-008 无第三方前端依赖")
PY