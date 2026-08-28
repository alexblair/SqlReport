#!/usr/bin/env bash
grep -q 'P2.*完成' AGENTS.md && grep -q 'P4.*交付前' AGENTS.md && grep -q '随时手动调用' AGENTS.md
