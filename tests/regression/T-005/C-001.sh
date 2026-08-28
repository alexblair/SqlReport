#!/usr/bin/env bash
# C-001 FR-002：支撑服务五模块分卷文件存在
for f in redis_cache audit_db audit_page scheduler server; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
exit 0
