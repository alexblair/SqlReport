#!/usr/bin/env bash
# C-008 FR-002：契约权威声明全量穷尽 + SPEC 含模块分卷术语
python3 -c "import json;print(any(f['id']=='FR-002' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q '模块分卷' .adocs/specs/总纲规格.md
