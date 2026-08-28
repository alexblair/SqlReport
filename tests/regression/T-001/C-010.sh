#!/usr/bin/env bash
# C-010 FR-003：契约权威声明分卷组织 + SPEC 含主 SPEC 术语
python3 -c "import json;print(any(f['id']=='FR-003' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q '主 SPEC' .adocs/specs/总纲规格.md
