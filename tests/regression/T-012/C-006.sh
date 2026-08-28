#!/usr/bin/env bash
test -f .adocs/specs/总纲规格.md && grep -q '## 背景与目标' .adocs/specs/总纲规格.md && grep -q '## 附录A：机器契约' .adocs/specs/总纲规格.md && test -f .adocs/contracts/总纲契约.json
