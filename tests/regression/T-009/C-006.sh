#!/usr/bin/env bash
[ "$(grep -cE '^## ' .adocs/specs/总纲规格.md)" = "9" ] && grep -q 'contract-json' .adocs/specs/总纲规格.md && [ -f .adocs/contracts/总纲契约.json ]
