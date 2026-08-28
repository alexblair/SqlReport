#!/usr/bin/env bash
# C-010 FR-010：各分卷 last_reviewed_commit 非空且为主仓真实 git 提交点
for f in .adocs/specs/modules/*.md; do
  ref=$(grep '^last_reviewed_commit: ' "$f" | sed 's/.*: //' | xargs)
  [ -n "$ref" ] || exit 1
  git cat-file -e "$ref^{commit}" || exit 1
done
exit 0
