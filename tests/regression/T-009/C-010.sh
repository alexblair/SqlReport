#!/usr/bin/env bash
python3 -c "
import json
d = json.load(open('.adocs/specs/index.json'))
empty = [s['name'] for s in d['specs'] if not s.get('last_reviewed_commit')]
assert not empty, f'Empty commits: {empty}'
"
exit 0
