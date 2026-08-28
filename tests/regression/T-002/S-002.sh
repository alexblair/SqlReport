#!/usr/bin/env bash
# S-002 场景：真相核对与 copy 只读约束（以代码真实为准 + README 失真项 + 无 copy 文件地址引用）
for c in C-006 C-007 C-014; do
  bash "tests/regression/T-002/$c.sh" >/dev/null 2>&1 || { echo "S-002 FAIL at $c"; exit 1; }
done
echo "S-002 PASS"
