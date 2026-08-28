---
module: static_cache
contract_id: MOD-STATIC_CACHE
version: 1.0
depends_on: [app_config, file_permissions]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# static_cache.py 模块分卷

> 本分卷由 T-007 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`static_cache.py`（~250 行，14 个 def）——**API 静态文件缓存**（`.json` 变体）。配置读取、路径映射（防 `..` 穿越）、版本命中判定、原子写入（临时文件 + os.replace）、缓存失效（删除稳定文件 + 全部版本文件）。所有 IO/配置异常静默降级。

## 2. 公开 API 契约

- `strip_json_suffix(path)` → str：剥离路径末尾 `.json` 后缀。
- `get_static_cache_config()` → dict：读取 `static_cache` 配置段（enable/dir）。
- `permissions_root()` → str：返回缓存权限根目录 `{dir}/api`。
- `resolve_file_path(url_path)` → str|None：url_path → 缓存文件绝对路径（防穿越）。
- `content_has_object_meta(content)` → bool：判断内容是否含对象类型 meta 顶层键。
- `try_read(file_path, config_version, ttl_hours)` → str|None：命中判定并读取缓存（版本一致 + mtime 未超 TTL）。
- `write_file(file_path, content)` → bool：原子写入缓存文件。
- `write_versioned_file(file_path, version8, content)` → bool：原子写入带版本文件 + 稳定文件（双写）。
- `record_invalidated(url_path)`：记录失效时刻（进程内存，有界容量 512）。
- `get_last_invalidated(url_path)` → float|None：获取上次失效时刻。
- `invalidate(url_path)` → bool：删除稳定文件 + 全部版本文件（幂等）。

### 内部函数

- `_versioned_path(file_path, version8)` → str：稳定路径 → 带版本文件名。
- `_remove_stale_versioned(file_path, keep)`：清理旧版本文件（并发安全）。

### 常量

- `JSON_SUFFIX = ".json"`。
- `_MAX_LAST_INVALIDATED = 512`：失效记录有界容量。
- `_last_invalidated`：`OrderedDict`，url_path → 失效时间戳。

## 3. 数据流

```
请求 url_path → resolve_file_path()（路径映射 + 穿越校验）
  → try_read()（命中判定：文件存在 + 版本一致 + TTL）
    → 有 meta.config_version → 比对内容中的版本
    → 无 meta → 比对版本化文件名 {url_path}.v{version8}.json
  → miss → 调用方计算 → write_file() / write_versioned_file()
    → file_permissions.apply_*（权限应用）
    → _remove_stale_versioned()（清理旧版本）
  → invalidate(url_path)（显式失效）
```

## 4. 依赖关系

AST import 实测：`app_config, file_permissions`。
- `app_config`：`get_config()`（static_cache 配置段）。
- `file_permissions`：`apply_dirs_from`/`apply_tree`/`apply_to`（缓存文件权限管理）。
- 被调用方：api_handler（端点静态缓存读写）、scheduler（keepalive 重建）、server（启动初始化）。

## 5. 边界与异常

- 路径安全：`resolve_file_path` 防 `..` 穿越，不安全返回 None。
- 异常静默降级：所有 IO/配置异常 catch → logging.warning → 返回 None/False。
- 并发安全：`_remove_stale_versioned` 通过 mtime 比对避免误删。
- 有界容量：失效记录最多 512 条（OrderedDict FIFO）。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 static_cache.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
