#!/usr/bin/env bash
python3 -c "
import json
contract = json.load(open('.adocs/contracts/总纲契约.json'))
count = sum(1 for f in contract['FR'] if f['id'] == 'FR-004')
assert count == 1, f'FR-004 appears {count} times in CONTRACT'
"
exit 0
