#!/usr/bin/env bash
# C-001 FR-001：SPEC 九章节骨架完好（9 个 ## 二级标题）
[ "$(grep -cE '^## ' .adocs/specs/总纲规格.md)" = "9" ]
