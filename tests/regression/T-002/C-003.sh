#!/usr/bin/env bash
# C-003 FR-003：系统架构总览子节含入口 server.py 与路由表 ROUTES
grep -q '系统架构总览' .adocs/specs/总纲规格.md && grep -q 'server.py' .adocs/specs/总纲规格.md && grep -q 'ROUTES' .adocs/specs/总纲规格.md
