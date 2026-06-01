"""
app_config.py — 应用配置文件管理

加载 app_config.json（默认路径或 CONFIG_FILE 环境变量指定）。
配置文件定义了 config_db 的存储引擎（sqlite3/mysql）和相关连接参数。

使用方式:
    from app_config import get_config
    cfg = get_config()
    engine = cfg["config_db"]["engine"]
"""

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = "app_config.json"

# ---------------------------------------------------------------------------
# 内部状态
# ---------------------------------------------------------------------------

_config: dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def _load_config() -> dict[str, Any]:
    """从文件加载配置，文件不存在或格式错误时返回默认配置（SQLite + config.db）。"""
    path = os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "config_db": {
                "engine": "sqlite3",
                "path": "config.db",
            }
        }


def get_config() -> dict[str, Any]:
    """获取应用配置（懒加载，首次调用时从文件读取）。"""
    global _config
    if _config is None:
        _config = _load_config()
    return _config


def reload_config() -> dict[str, Any]:
    """强制重新加载配置文件（测试用）。"""
    global _config
    _config = _load_config()
    return _config
