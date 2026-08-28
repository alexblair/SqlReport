#!/usr/bin/env bash
# C-011 FR-001/004/005/006/007/008：契约与基线（SPEC 九章节 + contract-json + 总纲契约.json + FR-004/005/006/007/008 + .gitignore）
# FR-001
[ "$(grep -cE '^## ' .adocs/specs/总纲规格.md)" = "9" ] && grep -q 'contract-json' .adocs/specs/总纲规格.md && [ -f .adocs/contracts/总纲契约.json ] || exit 1
# FR-004~008
for fid in FR-004 FR-005 FR-006 FR-007 FR-008; do
  python3 -c "import json;print(any(f['id']=='$fid' for f in json.load(open('.adocs/contracts/总纲契约.json'))['FR']))" | grep -q True || exit 1
done
grep -q 'specs/index.json' .adocs/specs/总纲规格.md || exit 1
grep -q '保鲜' .adocs/specs/总纲规格.md || exit 1
grep -q 'ar-flow.mjs' .adocs/specs/总纲规格.md || exit 1
grep -q 'flow_docs_check' .adocs/specs/总纲规格.md || exit 1
grep -qE '^\.adocs/$' .gitignore || exit 1
git check-ignore -q .adocs/untracked-probe.tmp || exit 1
