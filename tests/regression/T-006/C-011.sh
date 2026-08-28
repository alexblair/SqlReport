#!/usr/bin/env bash
# C-011 FR-008：.gitignore 含 .adocs/ 排除规则
python3 -c "import json;print(any(f['id']=='FR-008' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp
