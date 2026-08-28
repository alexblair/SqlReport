---
module: file_permissions
contract_id: MOD-FILE_PERMISSIONS
version: 1.0
depends_on: [app_config]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# file_permissions.py 模块分卷

> 本分卷由 T-007 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`file_permissions.py`（~200 行，9 个 def）——**运行时文件权限管理**。仅作用于 `static_cache.permissions_root()`（即 `{static_cache.dir}/api`）以下的目录与文件。解决 root 进程创建的文件 NGINX worker 无法读取的问题。

## 2. 公开 API 契约

- `load_permissions()` → bool：从 app_config 加载并解析权限配置，返回是否启用。
- `is_enabled()` → bool：当前权限管理是否已启用。
- `apply_to(path, is_dir=None)`：对单个路径应用配置的属主与权限位（符号链接跳过，失败静默降级）。
- `apply_dirs_from(root, leaf)`：对 root 到 leaf 每一级目录应用目录权限（安全边界：leaf 必须在 root 下）。
- `apply_tree(root)`：递归应用权限到 root 下全部目录与文件。
- `refresh_tree(root)`：递归刷新目录树权限（root 不存在时先创建，启动时调用）。

### 内部函数

- `_resolve_uid(user)` → int|None：用户名/数字 uid → uid。
- `_resolve_gid(group)` → int|None：组名/数字 gid → gid。
- `_parse_mode(value, default)` → int：解析八进制权限位。

### 常量

- `_uid`/`_gid`：目标属主/属组（load_permissions 解析）。
- `_dir_mode = 0o755` / `_file_mode = 0o644`：默认权限位。
- `_enabled`：功能是否已启用。

## 3. 数据流

```
程序启动 → load_permissions()（读取配置，解析 uid/gid/mode，校验 root）
  → 失败 → _enabled=False，apply_* 全部 no-op

写入缓存时（由 static_cache.write_file 调用）
  → apply_dirs_from(root, leaf)（逐级修正祖先目录权限）
  → apply_tree(base_dir)（刷新目录树）
  → apply_to(tmp_file)（临时文件在 os.replace 前应用权限）
  → os.replace(tmp, target)

启动时 → refresh_tree(root)（创建目录 + 整树刷新权限）
```

## 4. 依赖关系

AST import 实测：`app_config`。
- `app_config`：`get_file_permissions_config()`（权限配置段）。
- 被调用方：static_cache（缓存文件权限管理）、server（启动初始化 refresh_tree）。

## 5. 边界与异常

- 安全边界：`apply_dirs_from` 校验 leaf 必须在 root 下。
- 符号链接跳过：`apply_to` 不跟随符号链接。
- 异常静默降级：所有权限操作失败 catch → logging.warning → 不影响业务。
- 功能可禁用：`_enabled=False` 时所有 apply_* 为 no-op。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 file_permissions.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
