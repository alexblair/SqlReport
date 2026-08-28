#!/usr/bin/env bash
grep -q 'specs/index.json' .adocs/specs/总纲规格.md && python3 -c "import json;print(any(f['id']=='FR-004' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True
