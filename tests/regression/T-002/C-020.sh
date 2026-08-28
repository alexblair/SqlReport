#!/usr/bin/env bash
# C-020 FR-014 禁止新建模块：嵌套筛选逻辑均在既有 api_handler/report_transform 模块内
cd "$(git rev-parse --show-toplevel)"
venv/bin/python - <<'PY'
import importlib.util
ok = True
# 解析与校验入口位于既有 api_handler 模块
spec = importlib.util.find_spec('api_handler')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
for fn in ('_resolve_nested_filter', 'validate_nested_filter'):
    if not hasattr(mod, fn):
        print('MISSING', fn); ok = False
# 应用引擎位于既有 result_transform 模块（T-001 已沉淀，复用优先）
spec2 = importlib.util.find_spec('result_transform')
mod2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(mod2)
if not hasattr(mod2, 'filter_rows_nested'):
    print('MISSING filter_rows_nested'); ok = False
assert ok, 'FR-014 violated'
print('FR-014 OK: 嵌套筛选解析/校验在 api_handler，应用引擎复用 result_transform.filter_rows_nested，无新建模块')
PY
