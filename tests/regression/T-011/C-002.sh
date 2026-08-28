#!/usr/bin/env bash
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
assert 'task_id' in c
assert 'optional' in c.lower() or '.optional()' in c
"
