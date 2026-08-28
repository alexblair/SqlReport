#!/usr/bin/env bash
# C-004 FR-003：模块分卷规范子节含统一 front-matter 六字段
grep -q '模块分卷目录与统一元数据规范' .adocs/specs/总纲规格.md || exit 1
for f in module contract_id version depends_on last_reviewed_commit last_reviewed_at; do
  grep -q "$f" .adocs/specs/总纲规格.md || exit 1
done
exit 0
