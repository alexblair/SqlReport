#!/usr/bin/env bash
# C-009 FR-010：分卷 last_reviewed_commit 非空且每个值均为有效 git 提交点
# 修复：允许多个不同 commit（增量开发的自然结果），但每个必须有效
commits=$(grep -h '^last_reviewed_commit: ' .adocs/specs/modules/*.md | sed 's/.*: //' | sort -u)
[ -n "$commits" ] || exit 1
while IFS= read -r ref; do
  git cat-file -e "$ref^{commit}" 2>/dev/null || { echo "Invalid commit: $ref"; exit 1; }
done <<< "$commits"
exit 0
