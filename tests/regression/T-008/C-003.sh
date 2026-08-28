#!/usr/bin/env bash
[ -f .adocs/specs/ops_scripts.md ] || exit 1
for kw in install.sh manage_service.sh git-tool.sh install uninstall commit push pull purge; do grep -q "$kw" .adocs/specs/ops_scripts.md || exit 1; done
exit 0
