# ---------------------------------------------------------------------------
# 站点标识（branding）：favicon 三模式 + 标题前缀的单一实现来源
# 规格：.scratch/site-branding/spec.md
#
# 职责边界：本模块只做「配置语义解析 + 图标字节产出 + 上传校验落盘 +
# 实例本地 kv 存取」，不做 HTTP 编排、不做审计、不开持久连接
# （读取带进程级缓存，保存方负责调 invalidate_site_branding_cache）。
# ---------------------------------------------------------------------------

import base64
import binascii
import os
import sqlite3
import struct
import threading
import zlib

# 内置默认图标（品牌紫单色块 16x16，原 server._build_favicon_bytes 迁入）
_DEFAULT_RGB = (0x4F, 0x46, 0xE5)
MAX_IMAGE_BYTES = 256 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ICO_MAGIC = b"\x00\x00\x01\x00"
ALLOWED_MODES = ("default", "color", "custom")

_BRANDING_DIR = "branding"
_CUSTOM_FAVICON_NAME = "favicon.img"

_LOCK = threading.Lock()
_BRANDING_CACHE = None  # None=未初始化；dict=已缓存（保存后显式失效）


class BrandingError(ValueError):
    """站点标识配置非法（消息可直接作为 flash 文案展示给管理员）。"""


# ---------------------------------------------------------------------------
# 默认图标生成（自 server.py 迁入，逻辑不变）
# ---------------------------------------------------------------------------

def _png_chunk(typ: bytes, data: bytes) -> bytes:
    body = typ + data
    return (struct.pack(">I", len(data)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


def _solid_png(rgb: tuple, width: int = 16, height: int = 16) -> bytes:
    r, g, b = rgb
    raw = b"".join(b"\x00" + bytes((r, g, b, 0xFF)) * width
                   for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b""))


def wrap_ico(png_bytes: bytes, width: int = 16, height: int = 16) -> bytes:
    """把单张 PNG 包装为合法 ICO 字节流（ICONDIR type=1 count=1）。"""
    ico = (struct.pack("<HHH", 0, 1, 1)
           + struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32,
                         len(png_bytes), 6 + 16))
    return ico + png_bytes


def build_default_favicon() -> bytes:
    """内置品牌紫图标（default 模式与一切回退路径的唯一产物）。"""
    return wrap_ico(_solid_png(_DEFAULT_RGB))


DEFAULT_FAVICON_BYTES = build_default_favicon()


def build_color_favicon(color_value: str) -> bytes:
    """按颜色生成双色图标：外圈 2px 为主色 60% 暗度，内芯为主色。

    颜色非法（非 #RGB/#RRGGBB 形态）抛 BrandingError，由分派层回退默认。
    """
    rgb = normalize_color(color_value)
    if rgb is None:
        raise BrandingError(f"无效的颜色值: {color_value!r}（支持 #RGB/#RRGGBB）")
    dark = tuple(int(c * 0.6) for c in rgb)
    size = 16
    canvas = []
    for y in range(size):
        row = bytearray(b"\x00")
        for x in range(size):
            edge = x < 2 or x >= size - 2 or y < 2 or y >= size - 2
            c = dark if edge else rgb
            row += bytes((c[0], c[1], c[2], 0xFF))
        canvas.append(bytes(row))
    raw = b"".join(canvas)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
           + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b""))
    return wrap_ico(png)


def normalize_color(value) -> tuple | None:
    """规范化 #RGB/#RRGGBB 颜色为 (r,g,b)；其余形态一律返回 None。

    仅接受带 # 前缀形态（无 # 、空串、含非 hex 字符均拒绝，矩阵 M5-M7）。
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("#"):
        return None
    hex_part = text[1:]
    if len(hex_part) == 3:
        hex_part = "".join(ch * 2 for ch in hex_part)
    elif len(hex_part) != 6:
        return None
    try:
        return tuple(int(hex_part[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 自定义图片上传：清洗 / 校验 / 原子落盘 / 读盘
# ---------------------------------------------------------------------------

def clean_base64_image(raw) -> bytes:
    """清洗 base64 输入并解码为图片字节。

    接受 FileReader 产出的 dataURL（剥 ``data:image/*;base64,`` 前缀）
    或裸 base64；解码前先按上限做长度粗筛（避免无谓解码超大 payload），
    解码失败 / 结果为空抛 BrandingError。
    """
    if not isinstance(raw, str):
        raise BrandingError("未选择文件")
    text = raw.strip()
    if not text:
        raise BrandingError("未选择文件")
    if text.startswith("data:") and ";base64," in text:
        text = text.split(";base64,", 1)[1]
    text = "".join(text.split())
    # base64 膨胀系数 4/3：输入超限即可判定解码后必超限，先拒不解码
    if len(text) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        raise BrandingError("图片超过大小上限（256 KB）")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise BrandingError("图片数据不是有效的 base64 编码")
    if not data:
        raise BrandingError("未选择文件")
    return data


def detect_image_type(data: bytes) -> str | None:
    """magic bytes 白名单判定：'png' / 'ico'，其余一律 None。"""
    if data.startswith(PNG_MAGIC):
        return "png"
    if data.startswith(ICO_MAGIC):
        return "ico"
    return None


def custom_favicon_root(root: str = None) -> str:
    """自定义图标落点根目录（root 参数供测试注入临时目录）。"""
    return root or _BRANDING_DIR


def custom_favicon_path(root: str = None) -> str:
    return os.path.join(custom_favicon_root(root), _CUSTOM_FAVICON_NAME)


def save_custom_favicon(b64_text: str, root: str = None) -> None:
    """校验并原子写入自定义图标；任一步失败抛 BrandingError 且旧文件不动。"""
    data = clean_base64_image(b64_text)
    if len(data) > MAX_IMAGE_BYTES:
        raise BrandingError("图片超过大小上限（256 KB）")
    if detect_image_type(data) is None:
        raise BrandingError("仅支持 PNG 或 ICO 格式的图片")
    target_dir = custom_favicon_root(root)
    target = custom_favicon_path(root)
    # 唯一临时名：ThreadingHTTPServer 下并发上传不得共用同一 tmp
    tmp_path = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, target)
    except OSError as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise BrandingError(f"图片保存失败: {e}")


def load_custom_favicon(root: str = None) -> bytes | None:
    """读取已上传图标；不存在或读盘失败返回 None（分派层回退默认）。"""
    try:
        with open(custom_favicon_path(root), "rb") as f:
            return f.read()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 配置存储（实例本地 SQLite）+ 进程级缓存 + 三模式分派
#
# 站点标识是"每部署的身份"（环境前缀正是为了区分多套部署），必须落在
# 实例本地文件；若存共享配置库（MySQL），多部署共用一个库时配置互相
# 污染、无法区分（2026-08-24 用户反馈重构）。沿 audit_db 先例：独立于
# config_db 引擎选择，固定走本地 SQLite 文件，惰性自举建表。
# ---------------------------------------------------------------------------

# 实例本地存储路径（模块级变量供测试注入临时文件）
_SITE_DB_PATH = "config.db"

_SITE_SETTINGS_DDL = """CREATE TABLE IF NOT EXISTS site_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
)"""

# 白名单键（写入过滤；与表单字段一一对应）
SITE_SETTING_KEYS = ("favicon_mode", "favicon_color", "title_prefix")


def _site_conn(path=None):
    """连接实例本地的站点标识库；目录不存在则创建，启用 WAL 支撑并发读写。"""
    target = path or _SITE_DB_PATH
    db_dir = os.path.dirname(target)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def read_site_settings(path=None) -> dict:
    """读取全部站点标识配置 {key: value}；任何异常回退空配置（全默认）。"""
    try:
        conn = _site_conn(path)
        try:
            rows = conn.execute(
                "SELECT key, value FROM site_settings").fetchall()
        finally:
            conn.close()
    except Exception:
        return {}
    return {r[0]: r[1] for r in rows}


def write_site_settings(values: dict, path=None) -> None:
    """事务 UPSERT 一批站点标识配置到实例本地库；白名单外的键忽略。"""
    items = [(k, v) for k, v in values.items() if k in SITE_SETTING_KEYS]
    conn = _site_conn(path)
    try:
        conn.execute(_SITE_SETTINGS_DDL)
        for key, value in items:
            conn.execute(
                "INSERT INTO site_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _read_site_settings() -> dict:
    """进程缓存未命中时的底层读取（异常回退空配置）。"""
    return read_site_settings()


def get_site_branding() -> dict:
    """取当前站点标识三元组（带进程级缓存）。

    返回 {"mode": str, "color": str|None, "prefix": str}；
    mode 非法值视为 default（矩阵 M12）。
    """
    global _BRANDING_CACHE
    if _BRANDING_CACHE is None:
        with _LOCK:
            if _BRANDING_CACHE is None:
                raw = _read_site_settings()
                mode = raw.get("favicon_mode") or "default"
                if mode not in ALLOWED_MODES:
                    mode = "default"
                _BRANDING_CACHE = {
                    "mode": mode,
                    "color": raw.get("favicon_color") or None,
                    "prefix": raw.get("title_prefix") or "",
                }
    return _BRANDING_CACHE


def invalidate_site_branding_cache() -> None:
    """保存站点标识后调用，使下一次读取重新查库。"""
    global _BRANDING_CACHE
    with _LOCK:
        _BRANDING_CACHE = None


def resolve_favicon_bytes(root: str = None) -> bytes:
    """按当前配置产出 favicon 字节；任何环节异常回退内置图标。

    - default → 内置图标（矩阵 M1/M2）
    - color   → 合法 #RGB/#RRGGBB 动态生成，否则回退（M3-M7）
    - custom  → 已上传文件字节；无文件/读盘失败回退（M8-M11）
    """
    cfg = get_site_branding()
    mode = cfg["mode"]
    if mode == "color":
        try:
            return build_color_favicon(cfg["color"])
        except BrandingError:
            return DEFAULT_FAVICON_BYTES
    if mode == "custom":
        data = load_custom_favicon(root)
        if data and detect_image_type(data):
            return data
        return DEFAULT_FAVICON_BYTES
    return DEFAULT_FAVICON_BYTES
