#!/usr/bin/env bash
# C-016: FR-007 flow_docs_check（CONTRACT 含 FR-007）
python3 -c "import json;print(any(f['id']=='FR-007' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q 'flow_docs_check' .adocs/specs/总纲规格.md
