#!/usr/bin/env bash
# C-006 FR-001：主 SPEC 九章节 + contract-json + 总纲契约.json
[ "$(grep -cE '^## ' .adocs/specs/总纲规格.md)" = "9" ] && grep -q 'contract-json' .adocs/specs/总纲规格.md && [ -f .adocs/contracts/总纲契约.json ]
