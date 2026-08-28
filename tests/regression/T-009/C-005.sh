#!/usr/bin/env bash
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp && ! grep -rE '/opdev/SqlReport copy/[A-Za-z0-9_.-]+' .adocs/specs/ 2>/dev/null
