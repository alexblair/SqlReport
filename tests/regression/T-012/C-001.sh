#!/usr/bin/env bash
grep -q '知识库保鲜约束' AGENTS.md && grep -q 'last_reviewed_commit' AGENTS.md && grep -q 'flow_docs_check' AGENTS.md && grep -q '代码改动同步' AGENTS.md
