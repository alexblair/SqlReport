"""
static_cache.py — API 静态文件缓存（.json 变体）

职责：
1. 配置读取：app_config.json 的 static_cache 段（enable 默认 true、dir 默认 static_cache）
2. 路径映射：{dir}/{url_path}.json，子目录自动创建，realpath 校验防 `..` 穿越（dir 支持相对路径或外部绝对路径）
3. 命中判定：文件存在 + 版本一致（默认输出比对内容 meta.config_version；
   自定义输出模板未引用 {{meta}} 时比对文件名内嵌版本 {url_path}.v{版本8}.json，
   版本不匹配即 miss，不依赖进程内存）+ mtime 未超 TTL
4. 原子写：临时文件 + os.replace，并发请求最后写入者生效
5. 失效记录：模块级 dict（url_path → 上次判定失效时刻，仅供 meta.last_invalidated_at 展示，不参与命中判定）
6. 失效函数：invalidate(url_path) 删除稳定文件与全部版本文件（幂等）

设计原则：
- 所有文件 IO / 配置异常静默降级并记 logging.warning，绝不向调用方抛异常
- config_version 不写旁路 meta 文件：默认输出存于内容 meta 节点每次请求现算比对；
  模板端点文件无 meta 时版本体现在文件名（write_versioned_file 双写稳定文件，
  保持稳定路径 data.json 语义），版本变化 → 文件名变化 → 自动 miss 重建
"""

import glob
import json
import logging
import os
import tempfile
import time
from collections import OrderedDict

import app_config

# 模块级失效时刻记录：url_path → 上次判定失效的时间戳（进程内存）
# 有界容量：只保留最近 MAX_LAST_INVALIDATED 条，防止长期运行无界增长
# 注意：仅用于 meta.last_invalidated_at 展示；命中判定不再依赖该记录
_MAX_LAST_INVALIDATED = 512
_last_invalidated: OrderedDict[str, float] = OrderedDict()


def get_static_cache_config() -> dict:
    """读取 static_cache 配置段。

    配置示例:
        "static_cache": {
            "enable": true,
            "dir": "static_cache"
        }

    缺失或字段缺失时按默认值（enable=True、dir="static_cache"）。
    dir 支持相对路径或外部绝对路径，路径解析通过 os.path.realpath() 完成。
    """
    cfg = app_config.get_config().get("static_cache", {}) or {}
    return {
        "enable": bool(cfg.get("enable", True)),
        "dir": str(cfg.get("dir", "static_cache")),
    }


def resolve_file_path(url_path: str) -> str | None:
    """将 url_path（无前导 /）映射为缓存文件绝对路径。

    映射规则：{配置目录}/{url_path}.json，子目录按 URL 层级创建。
    写入前校验 realpath 落在配置目录内（防 `..` 路径穿越），
    非法路径返回 None。
    """
    base = os.path.realpath(get_static_cache_config()["dir"])
    target = os.path.realpath(os.path.join(base, f"{url_path}.json"))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _versioned_path(file_path: str, version8: str) -> str:
    """由稳定文件路径推导带版本文件名：{url_path}.json → {url_path}.v{版本8}.json。

    版本取 config_version 前 8 位（2^32 分之一冲突概率，冲突时仅退化为一次
    多余重建，由内容 meta 判定兜底，不产生错误结果）。
    """
    return f"{file_path[:-5]}.v{version8}.json"


def content_has_object_meta(content: str) -> bool:
    """内容是否含对象类型 meta 顶层键（可承载 config_version 自证版本）。

    仅对象（dict）meta 才能承载 config_version 走稳定文件 + 内容判定路径；
    模板把 meta 改写为非对象值（如 {"meta": {{data}}}，键集内合法）时视为
    无 meta → 写入版本化文件，靠文件名版本判定，避免稳定文件每次命中判定
    抛异常导致 miss 重建循环。
    内容不可解析时保守返回 True（走稳定文件 + 内容 meta 判定路径）。

    供 try_read 的版本判定与 api_handler 写入方式选择共用，避免两处
    各自解析漂移。
    """
    try:
        return isinstance(json.loads(content).get("meta"), dict)
    except (json.JSONDecodeError, TypeError):
        return True


def _remove_stale_versioned(file_path: str, keep: str) -> None:
    """删除该 url_path 下除 keep 外的全部旧版本文件（失败静默降级）。

    并发保护：mtime 新于 keep 的版本文件不清理——那可能是并发写入方
    刚写入的更新版本（最后写入者生效），删除会导致其下次 miss 重建。
    旧版本文件残留不影响命中判定（读取按精确版本路径），仅占用磁盘，
    由本清理函数与 invalidate 兜底清除。
    """
    try:
        keep_mtime = os.path.getmtime(keep)
        for stale in glob.glob(f"{file_path[:-5]}.v*.json"):
            if stale == keep:
                continue
            if os.path.getmtime(stale) > keep_mtime:
                continue
            os.remove(stale)
    except OSError as e:
        logging.warning("static_cache 清理旧版本文件失败: %s", e)


def try_read(file_path: str, config_version: str, ttl_hours: int) -> str | None:
    """
    命中判定并读取文件内容。

    命中条件（三者全满足）：
    1. 文件存在
    2. 版本一致：
       - 文件含对象类型 meta 节点（默认输出）→ meta.config_version 与当前配置版本一致
       - 文件无 meta 节点（自定义输出模板未引用 {{meta}}，或 meta 被改写为
         非对象值）→ 文件名为 {url_path}.v{版本8}.json 且版本前缀与当前配置版本一致
    3. mtime 未超 TTL（ttl_hours=0 表示永不过期）

    命中返回文件内容字符串，否则返回 None（调用方回退完整计算链路）。
    文件损坏/IO 异常视为 miss，静默降级。
    """
    try:
        if not os.path.isfile(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        meta = json.loads(content).get("meta") if content else None
        if isinstance(meta, dict) and meta.get("config_version") is not None:
            if meta.get("config_version") != config_version:
                return None
            read_path = file_path
            read_content = content
        else:
            # 无 meta 节点（模板未引用 {{meta}} 或 meta 被改写为非对象值）：
            # 无法自证版本。版本体现在文件名（write_versioned_file 写入），
            # 改库即版本变化 → 精确版本路径不存在 → miss，不依赖进程内存状态。
            version_path = _versioned_path(file_path, config_version[:8])
            if not os.path.isfile(version_path):
                return None
            read_path = version_path
            with open(version_path, "r", encoding="utf-8") as f:
                read_content = f.read()
        mtime = os.path.getmtime(read_path)
        if ttl_hours > 0 and time.time() - mtime > ttl_hours * 3600:
            return None
        return read_content
    except Exception as e:
        logging.warning("static_cache 读取失败: %s", e)
        return None


def write_file(file_path: str, content: str) -> bool:
    """原子写入缓存文件（临时文件 + os.replace），失败返回 False。

    并发写入时最后 replace 者生效，文件内容始终完整（同版本内容等价）。
    """
    try:
        base_dir = os.path.dirname(file_path)
        os.makedirs(base_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=base_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, file_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        return True
    except Exception as e:
        logging.warning("static_cache 写入失败: %s", e)
        return False


def write_versioned_file(file_path: str, version8: str, content: str) -> bool:
    """原子写入带版本缓存文件，并同步稳定文件（无 meta 模板端点专用）。

    双写语义：
    - 版本文件 {url_path}.v{version8}.json：try_read 的命中判定以它为准，
      版本变化 → 精确路径不存在 → miss，改库自动失效且不依赖进程内存
    - 稳定文件 {url_path}.json：保持既有"文件存在即缓存存在"的外部语义
      （refresh 联动删除、第三方检查等），内容与版本文件一致
    写入成功后清理旧版本文件（残留不影响判定，仅防磁盘堆积）。
    """
    version_path = _versioned_path(file_path, version8)
    if not (write_file(version_path, content) and write_file(file_path, content)):
        return False
    _remove_stale_versioned(file_path, keep=version_path)
    return True


def record_invalidated(url_path: str) -> None:
    """记录 url_path 的静态文件被判定失效的时刻（进程内存，有界容量）。"""
    _last_invalidated[url_path] = time.time()
    _last_invalidated.move_to_end(url_path)
    if len(_last_invalidated) > _MAX_LAST_INVALIDATED:
        _last_invalidated.popitem(last=False)


def get_last_invalidated(url_path: str) -> float | None:
    """返回 url_path 上次失效时刻；进程重启后无记录返回 None。"""
    return _last_invalidated.get(url_path)


def invalidate(url_path: str) -> bool:
    """删除 url_path 的静态缓存文件（稳定文件 + 全部版本文件，幂等，删除即失效）。"""
    file_path = resolve_file_path(url_path.lstrip("/"))
    if file_path is None:
        return False
    try:
        removed = False
        if os.path.exists(file_path):
            os.remove(file_path)
            removed = True
        for stale in glob.glob(f"{file_path[:-5]}.v*.json"):
            os.remove(stale)
            removed = True
        return True
    except Exception as e:
        logging.warning("static_cache invalidate 失败: %s", e)
        return False
