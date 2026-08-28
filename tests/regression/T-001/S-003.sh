#!/usr/bin/env bash
# S-003 场景：FR-001~FR-007、FR-010 契约基线声明（活文档 + 全量穷尽 + 分卷 + 索引 + 保鲜 + 插件增强 + 核对工具 + 代码真相）
for c in C-008 C-009 C-010 C-011 C-012 C-013 C-014 C-015; do
  bash "tests/regression/T-001/$c.sh" >/dev/null 2>&1 || { echo "S-003 FAIL at $c"; exit 1; }
done
echo "S-003 PASS"
