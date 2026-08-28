#!/usr/bin/env bash
# C-004 FR-008：排除落地后，除 P3 测试资产 tests/regression/ 外 git 工作区无意外改动
! git status --porcelain | grep -vE '^\?\? tests/regression/' | grep -q .
