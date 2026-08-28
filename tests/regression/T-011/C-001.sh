#!/usr/bin/env bash
# C-001: flow_docs_check 工具存在于插件中
grep -q 'flow_docs_check' .opencode/plugins/ar-flow.mjs && \
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
assert 'flow_docs_check' in c
# Check for 保鲜核对 in escaped form (\\u4FDD\\u9C9C\\u6838\\u5BF9)
assert '\\\\u4FDD\\\\u9C9C\\\\u6838\\\\u5BF9' in c or '保鲜核对' in c
"
