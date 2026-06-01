"""
app_config.py — 应用配置文件管理

加载 app_config.json（默认路径或 CONFIG_FILE 环境变量指定）。
配置文件定义了：
  - config_db: 配置数据库的存储引擎（sqlite3/mysql）和相关连接参数
  - server: HTTP 服务监听地址和端口

使用方式:
    from app_config import get_config, get_server_config
    cfg = get_config()
    engine = cfg["config_db"]["engine"]
    host, port = get_server_config()
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
