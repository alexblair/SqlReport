#!/usr/bin/env bash
# C-009 FR-004：契约权威声明 specs/index.json 机器索引
python3 -c "import json;print(any(f['id']=='FR-004' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q 'specs/index.json' .adocs/specs/总纲规格.md
