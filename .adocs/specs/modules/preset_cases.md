---
module: preset_cases
contract_id: MOD-PRESET_CASES
version: 1.0
depends_on: []
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# preset_cases.py 模块分卷

> 本分卷由 T-007 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`preset_cases.py`（~500 行，11 个 def）——**预设测试用例（数据夹具）一键导入**。从 JSON 夹具文件 upsert 导入连接池、分类、报表、API 端点、API Key、定时任务至 SQLite config_db，可选初始化测试 MySQL。被 config.handle_import_test_cases 委托。

## 2. 公开 API 契约

- `load_preset(path=None)` → dict：加载预设测试用例 JSON 文件。
- `setup_test_mysql_tables(test_mysql_cfg)` → dict：连接测试 MySQL，校验写权限，建表并初始化测试数据。
- `import_preset_test_cases(conn, data, path=None, test_mysql_cfg=None)` → dict：将预设 upsert 导入 config_db + 可选初始化测试 MySQL。
- `import_preset_from_file(conn, path=None, test_mysql_cfg=None)` → dict：从文件加载并导入（便捷封装）。

### 内部函数

- `_get_columns(conn, table)` → dict：PRAGMA table_info 获取表列元信息。
- `_resolve_ref(conn, ref_spec, value)`：按名称解析外键引用目标 id。
- `_match_where_clause(match_key)`：构造匹配用 WHERE 子句。
- `_match_values(match_key, data)`：抽取匹配键对应的记录值。
- `_upsert_group(conn, group_cfg, records, summary, errors)`：单实体分组 upsert。
- `_sync_child(conn, child_cfg, self_id, child_names, errors, rec)`：级联同步多对多关联（先删后插）。
- `_override_pools_with_test_mysql(data, test_mysql_cfg)`：连接池覆盖为 test_mysql 配置。

### 常量

- `DEFAULT_PRESET_PATH`：`tests/preset_test_cases.json`。
- `ENTITY_GROUPS`：各实体分组导入配置字典（table/match_key/refs/children）。

## 3. 数据流

```
JSON 夹具 → load_preset() → import_preset_test_cases()
  → _override_pools_with_test_mysql()（可选）
  → 遍历 ENTITY_GROUPS → _upsert_group()
     → _get_columns() → _resolve_ref() → INSERT/UPDATE → _sync_child()
  → setup_test_mysql_tables()（可选：建表 + 灌数据）
```

## 4. 依赖关系

AST import 实测：**无内部模块依赖**。
- 外部可选依赖：`mysql.connector`（运行时 try-import）。
- 被调用方：config.handle_import_test_cases。

## 5. 边界与异常

- 幂等：基于名称匹配的 upsert（INSERT OR UPDATE）。
- 级联同步：多对多关联表先删后插。
- MySQL 可选：未安装或连接失败不影响 config_db 导入。
- 异常降级：错误收集到 summary/errors 列表，不向上抛出。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 preset_cases.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
