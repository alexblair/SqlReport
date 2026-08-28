#!/usr/bin/env bash
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
assert 'existing_module_specs' in c
assert '\\\\u6A21\\\\u5757\\\\u5206\\\\u5377' in c or '模块分卷' in c
"
