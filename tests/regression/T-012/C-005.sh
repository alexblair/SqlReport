#!/usr/bin/env bash
# C-005: FR-010 FR-005 在 CONTRACT FR 段恰好定义 1 次
count=$(python3 -c "
import json
with open('.adocs/contracts/总纲契约.json') as f:
    data = json.load(f)
fr_count = sum(1 for fr in data.get('FR', []) if fr.get('id') == 'FR-005')
print(fr_count)
")
[ "$count" = "1" ]
