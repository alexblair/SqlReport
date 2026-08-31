#!/usr/bin/env bash
# S-001 场景：条件构建器 UI 全能力串联
set -e
cd "$(dirname "$0")/../../.."
bash tests/regression/T-004/C-001.sh
bash tests/regression/T-004/C-002.sh
bash tests/regression/T-004/C-003.sh
bash tests/regression/T-004/C-004.sh
bash tests/regression/T-004/C-006.sh
bash tests/regression/T-004/C-007.sh
bash tests/regression/T-004/C-005.sh
bash tests/regression/T-004/C-008.sh
echo "PASS S-001 条件构建器 UI 全能力"