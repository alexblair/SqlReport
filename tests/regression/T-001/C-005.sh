#!/usr/bin/env bash
# C-005 FR-009：copy 目录保持只读未被修改（cp -a 继承 mtime，主仓还原后 copy 若再被写则 mtime 变新）
for f in /opdev/SqlReport/*.py; do
  b=$(basename "$f")
  [ -f "/opdev/SqlReport copy/$b" ] || exit 1
  [ "$(stat -c %Y "/opdev/SqlReport copy/$b")" = "$(stat -c %Y "$f")" ] || exit 1
done
exit 0
