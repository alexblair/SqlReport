"""
static_cache.py — API 静态文件缓存（.json 变体）

职责：
1. 配置读取：app_config.json 的 static_cache 段（enable 默认 true、dir 默认 static_cache）
2. 路径映射：{dir}/{url_path}.json，子目录自动创建，realpath 校验防 `..` 穿越（dir 支持相对路径或外部绝对路径）
3. 命中判定：文件存在 + config_version（MD5(sql + pool_id)）一致 + mtime 未超 TTL
4. 原子写：临时文件 + os.replace，并发请求最后写入者生效
5. 失效记录：模块级 dict（url_path → 上次判定失效时刻，进程重启后无记录）
6. 失效函数：invalidate(url_path) 删除文件（幂等）

设计原则：
- 所有文件 IO / 配置异常静默降级并记 logging.warning，绝不向调用方抛异常
- 不写旁路 meta 文件：config_version 存于文件内容 meta 节点，每次请求现算比对
"""

import json
import logging
import os
import tempfile
import time
from collections import OrderedDict

import app_config

# 模块级失效时刻记录：url_path → 上次判定失效的时间戳（进程内存）
# 有界容量：只保留最近 MAX_LAST_INVALIDATED 条，防止长期运行无界增长
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


def try_read(file_path: str, config_version: str, ttl_hours: int) -> str | None:
    """
    命中判定并读取文件内容。

    命中条件（三者全满足）：
    1. 文件存在
    2. 文件内容 meta.config_version 与当前配置版本一致
    3. mtime 未超 TTL（ttl_hours=0 表示永不过期）

    命中返回文件内容字符串，否则返回 None（调用方回退完整计算链路）。
    文件损坏/IO 异常视为 miss，静默降级。
    """
    try:
        if not os.path.isfile(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        meta = json.loads(content).get("meta", {}) if content else {}
        if meta.get("config_version") != config_version:
            return None
        mtime = os.path.getmtime(file_path)
        if ttl_hours > 0 and time.time() - mtime > ttl_hours * 3600:
            return None
        return content
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
    """删除 url_path 的静态缓存文件（幂等，删除即失效，下次请求惰性重建）。"""
    file_path = resolve_file_path(url_path.lstrip("/"))
    if file_path is None:
        return False
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        logging.warning("static_cache invalidate 失败: %s", e)
        return False
