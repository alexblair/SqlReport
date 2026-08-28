#!/usr/bin/env bash
# C-008: FR-008 .gitignore 含 .adocs/ 排除
grep -q '\.adocs/' .gitignore
