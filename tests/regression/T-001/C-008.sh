#!/usr/bin/env bash
# C-008 FR-001：知识库活文档已落地（总纲规格.md 含 contract-json 围栏 + 总纲契约.json 机器契约存在）
[ -f .adocs/specs/总纲规格.md ] && grep -q 'contract-json' .adocs/specs/总纲规格.md && [ -f .adocs/contracts/总纲契约.json ]
