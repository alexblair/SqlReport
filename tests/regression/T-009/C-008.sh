#!/usr/bin/env bash
python3 -c "
import json
d = json.load(open('.adocs/specs/index.json'))
mods = [s for s in d['specs'] if s['contract_id'].startswith('MOD-')]
assert len(mods) >= 20, f'MOD-* count {len(mods)} < 20'
"
exit 0
