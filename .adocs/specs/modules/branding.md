---
module: branding
contract_id: MOD-BRANDING
version: 1.0
depends_on: []
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# branding.py 模块分卷

> 本分卷由 T-006 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`branding.py`（~350 行，15 个 def）——**站点标识品牌**。favicon 三模式（default/color/custom）与标题前缀的单一实现来源：配置语义解析、图标字节产出（PNG/ICO 生成）、上传校验落盘、实例本地 KV 存取（config.db 独立表）、进程级缓存（双重检查锁）。不做 HTTP 编排、不做审计。

## 2. 公开 API 契约

### 2.1 图标生成

- `wrap_ico(png_bytes, width=16, height=16)` → bytes：将单张 PNG 包装为合法 ICO 字节流。
- `build_default_favicon()` → bytes：内置品牌紫 16x16 默认图标（ICO）。
- `build_color_favicon(color_value)` → bytes：按 `#RGB/#RRGGBB` 生成双色 favicon ICO。
- `normalize_color(value)` → tuple|None：`#RGB/#RRGGBB` → `(r,g,b)`，非法返回 None。

### 2.2 自定义图标上传

- `clean_base64_image(raw)` → bytes：清洗 base64 输入（含 dataURL 前缀剥离）并解码。
- `detect_image_type(data)` → str|None：magic bytes 白名单判定 `'png'`/`'ico'`/`None`。
- `custom_favicon_root(root=None)` → str：自定义图标落点根目录。
- `custom_favicon_path(root=None)` → str：自定义图标完整文件路径。
- `save_custom_favicon(b64_text, root=None)`：校验并原子写入（临时文件 + `os.replace`）。
- `load_custom_favicon(root=None)` → bytes|None：读取已上传自定义图标字节。

### 2.3 站点设置 KV

- `read_site_settings(path=None)` → dict：从本地 SQLite 读取全部站点标识配置。
- `write_site_settings(values, path=None)`：事务 UPSERT 一批配置（白名单过滤）。

### 2.4 缓存与解析

- `get_site_branding()` → dict：获取 `{mode, color, prefix}`（进程级缓存，双重检查锁）。
- `invalidate_site_branding_cache()`：使缓存失效。
- `resolve_favicon_bytes(root=None)` → bytes：按当前配置三模式分派产出 favicon 字节。

### 2.5 异常

- `BrandingError(ValueError)`：站点标识配置非法异常。

### 2.6 常量

- `_DEFAULT_RGB = (0x4F, 0x46, 0xE5)`：品牌紫色值。
- `MAX_IMAGE_BYTES = 256 * 1024`：自定义图片大小上限。
- `ALLOWED_MODES = ("default", "color", "custom")`。
- `SITE_SETTING_KEYS = ("favicon_mode", "favicon_color", "title_prefix")`：写入白名单键。
- `DEFAULT_FAVICON_BYTES`：模块加载时预计算的默认 ICO。

## 3. 数据流

```
配置写入: form 参数 → write_site_settings() → 本地 SQLite(config.db) → invalidate_cache()
配置读取: get_site_branding() → [缓存命中? 直接返回] → _read_site_settings() → SQLite → 缓存
favicon 产出: resolve_favicon_bytes() → get_site_branding() → 模式分派:
  default → DEFAULT_FAVICON_BYTES
  color   → build_color_favicon() → _solid_png() → wrap_ico()
  custom  → load_custom_favicon() → 磁盘文件
自定义上传: base64 → clean_base64_image() → detect_image_type() → save_custom_favicon() → 磁盘
```

## 4. 依赖关系

AST import 实测：**无内部模块依赖**（仅标准库 + 延迟导入 `config_db` 用于本地 SQLite 连接）。
- 被调用方：server（favicon 动态服务）、config（站点标识保存）、render（标题前缀/favicon 模式）。

## 5. 边界与异常

- favicon 异常回退：`resolve_favicon_bytes` 异常时回退默认图标。
- 自定义图片校验：magic bytes 白名单（PNG/ICO）+ 大小上限（256KB）+ 原子写入。
- 缓存双重检查锁：线程安全。
- 配置写入白名单：仅 `favicon_mode`/`favicon_color`/`title_prefix` 三键。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 branding.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
