#!/usr/bin/env bash
python3 -c "
with open('.opencode/plugins/ar-flow.mjs') as f:
    c = f.read()
idx = c.find('existing_module_specs')
assert idx >= 0
specgen_area = c[max(0,idx-500):idx+500]
assert 'phase0' in specgen_area or 'specgen' in specgen_area.lower()
"
