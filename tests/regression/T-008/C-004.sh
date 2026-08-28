#!/usr/bin/env bash
[ -f .adocs/specs/static_assets.md ] || exit 1
for kw in static vendor server.py static_cache; do grep -q "$kw" .adocs/specs/static_assets.md || exit 1; done
exit 0
