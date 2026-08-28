#!/usr/bin/env bash
grep -q 'existing_module_specs' .opencode/plugins/ar-flow.mjs && grep -q 'MOD-' .opencode/plugins/ar-flow.mjs
