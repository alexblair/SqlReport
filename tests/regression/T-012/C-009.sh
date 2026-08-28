#!/usr/bin/env bash
# C-009: FR-004 index.json 含 >=29 份分卷
python3 -c "
import json
with open('.adocs/specs/index.json') as f:
    data = json.load(f)
assert len(data.get('specs', [])) >= 29, f'Only {len(data.get(\"specs\",[]))} specs'
"
