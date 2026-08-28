#!/usr/bin/env bash
# C-015 FR-007：契约权威声明 flow_docs_check
python3 -c "import json;print(any(f['id']=='FR-007' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q 'flow_docs_check' .adocs/specs/总纲规格.md
