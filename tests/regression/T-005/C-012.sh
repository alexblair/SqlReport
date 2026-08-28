#!/usr/bin/env bash
# C-012 FR-004：契约权威声明 specs/index.json
python3 -c "import json;print(any(f['id']=='FR-004' for f in json.load(open('.adocs/contracts/CONTRACT_v1.json'))['FR']))" | grep -q True && grep -q 'specs/index.json' .adocs/specs/SPEC_v1.md
