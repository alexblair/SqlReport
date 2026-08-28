#!/usr/bin/env bash
# C-003 FR-008：README 双语镜像均不加知识库导读（无指向 .adocs 的引用）
! grep -n '\.adocs' README.md && ! grep -n '\.adocs' README-CN.md
