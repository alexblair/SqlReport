#!/usr/bin/env bash
# C-001: AGENTS.md 含保鲜约束章节
grep -q '知识库保鲜约束' AGENTS.md && \
grep -q 'last_reviewed_commit' AGENTS.md && \
grep -q 'flow_docs_check' AGENTS.md && \
grep -q '代码改动同步' AGENTS.md
