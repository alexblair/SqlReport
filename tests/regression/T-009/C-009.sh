#!/usr/bin/env bash
python3 -c "
import json, os
d = json.load(open('.adocs/specs/index.json'))
required = ['name','doc_path','contract_id','version','last_reviewed_commit']
for s in d['specs']:
    for f in required:
        assert f in s, f'Missing {f} in {s.get(\"name\",\"?\")}'
    assert os.path.exists(s['doc_path']), f'Missing file: {s[\"doc_path\"]}'
"
exit 0
