#!/usr/bin/env bash
# C-010 FR-001：主 SPEC 九章节骨架 + contract-json + CONTRACT_v1.json
[ "$(grep -cE '^## ' .adocs/specs/SPEC_v1.md)" = "9" ] && grep -q 'contract-json' .adocs/specs/SPEC_v1.md && [ -f .adocs/contracts/CONTRACT_v1.json ]
