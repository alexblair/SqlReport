#!/usr/bin/env bash
# C-007 FR-016：构建器 UI 与 JSON 双向同步
set -e
cd "$(dirname "$0")/../../.."
venv/bin/python - <<'PY'
from render import build_nested_filter_builder_html
html=build_nested_filter_builder_html(["姓名","状态"], None)
assert 'id="nf-json"' in html, "缺少 JSON 文本框（UI→JSON）"
assert "nfSyncJson" in html, "树编辑未实时同步 JSON"
assert "nfLoadFromJson" in html, "缺少 从 JSON 载入（JSON→UI）"
assert "JSON.parse" in html, "从 JSON 载入未解析"
print("PASS C-007 FR-016 UI 与 JSON 双向同步")
PY