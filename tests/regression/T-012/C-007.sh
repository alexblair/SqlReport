#!/usr/bin/env bash
# C-007: FR-002 index.json 含 >=20 条 MOD-* 模块索引（按 contract_id 字段匹配）
python3 -c "
import json
with open('.adocs/specs/index.json') as f:
    data = json.load(f)
mods = [r for r in data.get('specs', []) if r.get('contract_id','').startswith('MOD-')]
assert len(mods) >= 20, f'Only {len(mods)} MOD- entries, need >=20'
"
