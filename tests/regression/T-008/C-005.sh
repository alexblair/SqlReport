#!/usr/bin/env bash
[ -f .adocs/specs/readme_reconciliation.md ] || exit 1
for kw in git-purge.sh git-tool.sh "tests/" README 核对; do grep -qF "$kw" .adocs/specs/readme_reconciliation.md || exit 1; done
exit 0
