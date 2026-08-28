#!/usr/bin/env bash
# C-014 FR-007：契约权威声明 flow_docs_check
python3 -c "import json;print(any(f['id']=='FR-007' for f in json.load(open('.adocs/contracts/CONTRACT_v1.json'))['FR']))" | grep -q True && grep -q 'flow_docs_check' .adocs/specs/SPEC_v1.md
