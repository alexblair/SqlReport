#!/usr/bin/env bash
# C-015 FR-010：契约权威声明知识库以代码真相为准 + README 失真项（git-tool.sh）已在知识库记载
python3 -c "import json;print(any(f['id']=='FR-010' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True && grep -q '以代码真实为准' .adocs/specs/总纲规格.md && grep -q 'git-tool.sh' .adocs/specs/总纲规格.md
