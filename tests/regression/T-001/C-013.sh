#!/usr/bin/env bash
# C-013 FR-014 禁止新建模块：新 API 须位于 result_transform.py 且仓库无新增非测试模块
cd "$(git rev-parse --show-toplevel)"
venv/bin/python - <<'PY'
import importlib.util, os
ok=True
for fn in ('filter_rows_nested','resolve_expression','validate_nested_filter'):
    spec=importlib.util.find_spec('result_transform')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    if not hasattr(mod, fn):
        print('MISSING', fn); ok=False
# 检查根目录/子目录是否存在新增的非测试 .py 模块（排除 tests/、.adocs/、venv/）
for root,dirs,_ in os.walk('.'):
    if any(root.startswith(p) for p in ('./.git','./venv','./tests','./.adocs')):
        continue
    for f in os.listdir(root):
        if f.endswith('.py') and f not in ('result_transform.py',):
            print('NEW MODULE', os.path.join(root,f)); ok=False
assert ok, 'FR-014 violated'
print('FR-014 OK: 所有新 API 均在 result_transform.py，无新增模块')
PY