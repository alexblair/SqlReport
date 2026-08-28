#!/usr/bin/env bash
# C-007 FR-009：copy 为有效只读副本，23 个 .py 与主仓还原后 md5 全一致
for f in /opdev/SqlReport/*.py; do
  b=$(basename "$f")
  [ -f "/opdev/SqlReport copy/$b" ] || exit 1
  [ "$(md5sum "$f" | cut -d' ' -f1)" = "$(md5sum "/opdev/SqlReport copy/$b" | cut -d' ' -f1)" ] || exit 1
done
exit 0
