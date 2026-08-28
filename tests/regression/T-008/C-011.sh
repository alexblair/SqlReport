#!/usr/bin/env bash
grep -qE '^\.adocs/$' .gitignore && git check-ignore -q .adocs/untracked-probe.tmp
