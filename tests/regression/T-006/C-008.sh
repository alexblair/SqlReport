#!/usr/bin/env bash
# C-008 FR-004/005/006/007/008：契约权威声明 + .gitignore
for fid in FR-004 FR-005 FR-006 FR-007 FR-008; do
  python3 -c "import json;print(any(f['id']=='$fid' for f in json.load(open('.adocs/contracts/CONTRACT_v1.json'))['FR']))" | grep -q True || exit 1
done
grep -q 'specs/index.json' .adocs/specs/SPEC_v1.md || exit 1
grep -q '保鲜' .adocs/specs/SPEC_v1.md || exit 1
grep -q 'ar-flow.mjs' .adocs/specs/SPEC_v1.md || exit 1
grep -q 'flow_docs_check' .adocs/specs/SPEC_v1.md || exit 1
grep -qE '^\.adocs/$' .gitignore || exit 1
git check-ignore -q .adocs/untracked-probe.tmp || exit 1
