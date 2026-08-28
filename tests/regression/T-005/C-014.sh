#!/usr/bin/env bash
# C-014 FR-006：契约权威声明 flow 插件增强
python3 -c "import json;print(any(f['id']=='FR-006' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q 'ar-flow.mjs' .adocs/specs/总纲规格.md
