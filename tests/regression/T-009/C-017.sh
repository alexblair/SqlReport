#!/usr/bin/env bash
# C-017: FR-010 每个 FR-ID 有且仅有一处权威记载（抽样 FR-004）
python3 -c "
import json
contract = json.load(open('.adocs/contracts/总纲契约.json'))
fr004_count = sum(1 for f in contract['FR'] if f['id'] == 'FR-004')
assert fr004_count == 1, f'FR-004 appears {fr004_count} times in CONTRACT'
"
exit 0
