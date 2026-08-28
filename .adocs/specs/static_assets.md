---
module: static-assets
contract_id: SPEC-STATIC-ASSETS
version: 1
depends_on: [T-002]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28T15:30:00+08:00
---

## 1. 职责概述

SqlReport 的静态资源目录 `static/` 存放前端 JS/CSS 库。当前结构极简：仅含 `vendor/` 子目录，无自定义静态资源（HTML/CSS/JS 均内联在 Python 模块中生成）。

**目录结构**：
```
static/
└── vendor/
    └── self@ea63d909/   # session 产物（非标准 vendor 库）
```

## 2. 公开 API 契约

### 2.1 static/vendor/ 目录

当前 `vendor/` 目录仅含一个 session 产物目录 `self@ea63d909/`，不是标准的第三方 JS/CSS 库。

**预期用途**：存放前端第三方库（如 DataTables、jQuery 等），但当前项目将前端资源内联在 Python 生成的 HTML 中，无需外部 vendor 库。

### 2.2 static_cache 配合

`static_cache.py` 管理的静态文件缓存目录由 `app_config.json` 的 `static_cache.dir` 配置决定，与 `static/` 目录独立。

## 3. 数据流

```
static/ → 前端资源（当前仅 vendor/）
    ↓
server.py → /static/ 路由 → 直接文件服务
    ↓
browser → 加载 JS/CSS
```

## 4. 依赖关系

- **server.py**：注册 `/static/` 路由，直接文件服务
- **static_cache.py**：独立的缓存目录（非 `static/`）

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| `static/vendor/` 为空 | 无影响（前端内联） |
| `self@ea63d909/` 是 session 产物 | 非标准 vendor，可清理 |

## 6. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | static/ 目录结构（仅 vendor/） | last_reviewed_commit |
| CP-002 | vendor/ 内容为 session 产物 | last_reviewed_commit |
