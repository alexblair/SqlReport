#!/usr/bin/env bash
# C-008: FR-003 分卷 front-matter 七字段齐全+doc_path 存在
python3 -c "
import json, os
with open('.adocs/specs/index.json') as f:
    data = json.load(f)
for r in data.get('specs', []):
    for field in ['name', 'doc_path', 'contract_id', 'fr_refs', 'depends_on', 'version', 'last_reviewed_commit']:
        assert field in r, f'Missing {field} in {r.get(\"name\",\"?\")}'
    assert os.path.isfile(r['doc_path']), f'Missing file: {r[\"doc_path\"]}'
"
