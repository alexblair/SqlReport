#!/usr/bin/env bash
# C-001 FR-002：配置与认证四模块分卷存在
for f in config_db config app_config auth; do
  [ -f ".adocs/specs/modules/$f.md" ] || exit 1
done
exit 0
