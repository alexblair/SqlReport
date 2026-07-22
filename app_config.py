"""
app_config.py — 应用配置文件管理

加载 app_config.json（默认路径或 CONFIG_FILE 环境变量指定）。
配置文件定义了：
  - config_db: 配置数据库的存储引擎（sqlite3/mysql）和相关连接参数
  - server: HTTP 服务监听地址和端口
  - log: 日志文件开关和路径

config_db 支持多配置列表，通过 enable 字段切换当前使用的引擎：

    "config_db": [
        {"enable": true,  "engine": "mysql",  "host": "...", ...},
        {"enable": false, "engine": "sqlite3", "path": "config.db"}
    ]

兼容旧格式（单 dict），自动识别并处理。

使用方式:
    from app_config import get_config, get_server_config, get_active_db_config, get_log_config
    cfg = get_config()
    db_cfg = get_active_db_config()
    engine = db_cfg["engine"]
    host, port = get_server_config()
    log_enabled, log_path = get_log_config()
"""

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = "app_config.json"
_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8080

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
            "config_db": [
                {
                    "enable": True,
                    "engine": "sqlite3",
                    "path": "config.db",
                }
            ]
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


def get_server_config() -> tuple[str, int]:
    """解析配置文件中的 server 段，返回 (host, port)。

    配置文件示例:
        "server": {
            "host": "0.0.0.0",
            "port": 8080
        }

    缺失时返回 (_DEFAULT_HOST, _DEFAULT_PORT)。
    环境变量 HOST / PORT 优先级最高（便于容器化部署）。
    """
    cfg = get_config()
    server_cfg = cfg.get("server", {})
    host = os.environ.get("HOST", server_cfg.get("host", _DEFAULT_HOST))
    port_str = os.environ.get("PORT", str(server_cfg.get("port", _DEFAULT_PORT)))
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        port = _DEFAULT_PORT
    return host, port


def get_active_db_config() -> dict[str, Any]:
    """从 config_db 配置段中获取当前启用的数据库配置。

    支持两种格式：
      1. 列表格式（新）— 遍历列表返回第一个 enable=true 的条目
      2. 字典格式（旧，向后兼容）— 直接返回

    未找到启用配置或配置段缺失时返回默认 SQLite 配置。
    """
    raw = get_config().get("config_db")

    if isinstance(raw, list):
        for entry in raw:
            if entry.get("enable", False):
                return entry
        return {"engine": "sqlite3", "path": "config.db", "enable": True}

    if isinstance(raw, dict):
        return raw

    return {"engine": "sqlite3", "path": "config.db", "enable": True}


def get_log_config() -> tuple[bool, str]:
    """解析 log 配置段，返回 (enabled, filepath)。

    配置文件示例:
        "log": {
            "enable": true,
            "path": "run.log"
        }

    缺失时返回 (False, "run.log")。
    """
    cfg = get_config().get("log", {})
    enabled = cfg.get("enable", False)
    path = cfg.get("path", "run.log")
    return bool(enabled), str(path)


def get_redis_config() -> dict:
    """解析 redis 配置段。

    配置文件示例:
        "redis": {
            "enable": false,
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "password": "",
            "key_prefix": "sr",
            "default_ttl_hours": 24,
            "socket_timeout": 5
        }

    缺失或未启用时返回 {"enable": False}。
    """
    return get_config().get("redis", {"enable": False})


def get_audit_db_config() -> dict:
    """解析 audit_db 配置段。

    配置文件示例:
        "audit_db": {
            "path": "audit.db"
        }

    缺失时返回默认值 {"path": "audit.db"}。
    """
    cfg = get_config().get("audit_db", {})
    return {
        "path": cfg.get("path", "audit.db"),
    }
