#!/usr/bin/env bash
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
idx = c.find('flow_docs_check')
assert idx >= 0
# Extract the tool definition area (next 2000 chars)
tool_area = c[idx:idx+3000]
# Verify no write file operations
assert 'writeFile' not in tool_area or tool_area.count('writeFile') == 0, 'Has writeFile'
"
