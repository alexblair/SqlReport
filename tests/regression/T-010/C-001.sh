#!/usr/bin/env bash
# C-001: specgen 提示词含模块分卷解析指令
grep -q 'existing_module_specs' .opencode/plugins/ar-flow.mjs && \
grep -q 'MOD-' .opencode/plugins/ar-flow.mjs && \
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
assert 'existing_module_specs' in c
# Check for 模块分卷 in either raw or escaped form
assert '\\\\u6A21\\\\u5757\\\\u5206\\\\u5377' in c or '模块分卷' in c
"
