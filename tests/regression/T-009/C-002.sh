#!/usr/bin/env bash
python3 -c "
import json, subprocess
d = json.load(open('.adocs/specs/index.json'))
main = [s for s in d['specs'] if s['contract_id'] == 'SPEC-MAIN']
assert len(main) == 1 and main[0]['doc_path'] == '.adocs/specs/总纲规格.md'
mods = [s for s in d['specs'] if s['contract_id'].startswith('MOD-')]
assert len(mods) >= 20, f'MOD-* count {len(mods)} < 20'
invalid = []
for s in d['specs']:
    ref = s.get('last_reviewed_commit','')
    if not ref: invalid.append(s['name']); continue
    r = subprocess.run(['git','cat-file','-e',ref+'^{commit}'], capture_output=True)
    if r.returncode != 0: invalid.append(s['name'])
assert not invalid, f'Invalid commits: {invalid}'
"
exit 0
