#!/usr/bin/env bash
# C-010: FR-010 每个 FR-ID 在 CONTRACT 中恰好定义 1 次
python3 -c "
import json
with open('.adocs/contracts/总纲契约.json') as f:
    data = json.load(f)
for fr in data.get('FR', []):
    count = sum(1 for f2 in data['FR'] if f2.get('id') == fr.get('id'))
    assert count == 1, f'{fr[chr(34)+chr(105)+chr(100)+chr(34)]} appears {count} times'
"
