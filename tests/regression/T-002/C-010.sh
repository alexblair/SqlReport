#!/usr/bin/env bash
# C-010 FR-005：契约权威声明保鲜机制
python3 -c "import json;print(any(f['id']=='FR-005' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q '保鲜' .adocs/specs/总纲规格.md
