#!/usr/bin/env bash
# C-006 FR-010：真相核对方法子节记录 README 失真项（git-purge.sh 实为 git-tool.sh）
grep -q 'README 与代码真相核对方法' .adocs/specs/总纲规格.md && grep -q 'git-tool.sh' .adocs/specs/总纲规格.md && grep -q 'git-purge.sh' .adocs/specs/总纲规格.md
