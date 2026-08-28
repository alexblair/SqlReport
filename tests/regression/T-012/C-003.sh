#!/usr/bin/env bash
grep -q '函数签名' AGENTS.md && grep -q 'API' AGENTS.md && grep -q 'schema' AGENTS.md && grep -q '配置' AGENTS.md && grep -q '运维脚本' AGENTS.md
