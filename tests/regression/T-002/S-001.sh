#!/usr/bin/env bash
# S-001 场景：SPEC 活文档格式与分卷规范（九章节 + contract-json + 架构总览 + 分卷 front-matter + contract_id 命名）
for c in C-001 C-002 C-003 C-004 C-005; do
  bash "tests/regression/T-002/$c.sh" >/dev/null 2>&1 || { echo "S-001 FAIL at $c"; exit 1; }
done
echo "S-001 PASS"
