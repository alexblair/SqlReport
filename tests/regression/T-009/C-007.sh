#!/usr/bin/env bash
python3 -c "
import json
d = json.load(open('.adocs/specs/index.json'))
main = [s for s in d['specs'] if s['contract_id'] == 'SPEC-MAIN']
assert len(main) == 1 and main[0]['doc_path'] == '.adocs/specs/总纲规格.md'
"
exit 0
