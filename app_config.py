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
import re
import time
import urllib.parse
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = "app_config.json"
_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8080

# API 路径统一前缀
API_PREFIX = "/api/"

# 真值字符串集合（大小写敏感，与历史调用点语义一致）
TRUTHY_VALUES = frozenset({"true", "1", "yes"})

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
    except FileNotFoundError:
        print(f"[app_config] 警告: 配置文件 {path} 不存在，使用默认配置")
        return {
            "config_db": [
                {
                    "enable": True,
                    "engine": "sqlite3",
                    "path": "config.db",
                }
            ]
        }
    except json.JSONDecodeError as e:
        print(f"[app_config] 警告: 配置文件 {path} 格式错误 ({e})，使用默认配置")
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


def get_server_base_url() -> str:
    """返回 API URL 展示用的服务端兜底 base_url（http://127.0.0.1:{port}）。

    仅作无 JS 时的服务端渲染兜底值，页面加载后 JS 用 window.location.origin 覆盖。
    """
    _, port = get_server_config()
    return f"http://127.0.0.1:{port}"


def get_trust_xff() -> bool:
    """解析配置文件 server 段的 trust_xff 开关（是否信任 X-Forwarded-For 首 IP）。

    配置文件示例:
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
            "trust_xff": false
        }

    默认 False：客户端 IP 取 socket 对端地址（X-Forwarded-For 首 IP 可被伪造）。
    仅当部署在可信反向代理（如 Nginx）之后且代理已覆写 XFF 时才应开启。
    """
    cfg = get_config()
    server_cfg = cfg.get("server", {})
    return bool(server_cfg.get("trust_xff", False))


def safe_int(val, default: int) -> int:
    """安全转换为 int，转换失败（非数字/None）返回默认值。"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def parse_form_urlencoded(body: str) -> dict:
    """解析 URL 编码的表单/请求体为 dict（重复键取最后一个值）。"""
    parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}


def ensure_api_prefix(path: str) -> str:
    """确保路径以 /api/ 开头：已有 /api 前缀时规范化，否则补全。

    兼容旧格式（已有 /api 前缀）以确保向后兼容；空路径抛 ValueError。
    """
    path = path.strip()
    if not path:
        raise ValueError("URL 路径不能为空")
    if path.startswith(API_PREFIX):
        return path
    if path.startswith("/api"):
        return API_PREFIX + path[4:].lstrip("/")
    return API_PREFIX + path.lstrip("/")


def strip_api_prefix(path: str) -> str:
    """剥离路径的 /api 前缀，仅保留后段（/api/x → x；/api → ''；无前缀原样返回）。"""
    if path.startswith(API_PREFIX):
        return path[len(API_PREFIX):]
    if path.startswith("/api"):
        return path[4:]
    return path


def format_local_time(ts, with_tz: bool = True) -> str:
    """格式化为服务器本地时区时间（秒级精度）。

    with_tz=True 时含时区偏移（如 2026-08-04 18:30:22 +0800）；
    with_tz=False 时不含时区偏移（如 2026-08-04 18:30:22）。
    """
    if with_tz:
        return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(ts))
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def serialize_json(obj, **kwargs) -> str:
    """序列化 JSON 字符串（ensure_ascii=False，与全项目序列化约定一致）。

    未显式传 cls 时注入 default=str（默认约定：不可 JSON 序列化类型转为
    字符串）；显式传自定义 cls 时不注入 default，避免 default=str 遮蔽
    编码器自定义的 default 方法（json.dumps 的 default 参数会覆盖 cls
    实例的 default）。
    """
    if "cls" in kwargs:
        return json.dumps(obj, ensure_ascii=False, **kwargs)
    return json.dumps(obj, ensure_ascii=False, default=str, **kwargs)


# ---------------------------------------------------------------------------
# 「智能去引号」序列化（smart_quote_flags 位图）
# ---------------------------------------------------------------------------
# 位图：1=十进制数字（含正负号）、2=科学计数法、4=千分位数字。
# 语义：仅字符串载体按勾选特征判定裸输出；原生 int/float/Decimal/bool/None 恒按
# 标准 JSON；面板全部不勾选（flags=0）时输出与 serialize_json 逐字节等价。
# 产品承诺：勾选任一特征时输出永远合法 JSON（RFC 8259 number 语法）。
SMART_FLAG_DECIMAL = 1
SMART_FLAG_SCIENTIFIC = 2
SMART_FLAG_THOUSAND = 4
_SMART_FLAG_ALL = SMART_FLAG_DECIMAL | SMART_FLAG_SCIENTIFIC | SMART_FLAG_THOUSAND

# 判定正则（互斥设计：每个文本形态至多命中一项；符号/指数/逗号为区分特征）
_SMART_DECIMAL_RE = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?$")
_SMART_SCIENTIFIC_RE = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?[eE][+-]?[0-9]+$")
_SMART_THOUSAND_RE = re.compile(r"^[+-]?[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?$")

# 兜底校验：RFC 8259 §6 number ABNF 直译（仅 minus、禁止前导零、
# frac/exp 各至少 1 位数字）。不得用 json.loads——Python 放行 Infinity/NaN
# （RFC 明确禁止），此处必须严格拒绝。
_SMART_NUMBER_RE = re.compile(
    r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")


def serialize_smart_quotes(obj, flags: int = 0, indent=None) -> str:
    """「智能去引号」模式序列化：结构保留 JSON 语法，字符串标量按勾选特征裸输出。

    flags（位图）：1=十进制数字（含正负号）、2=科学计数法、4=千分位数字；
    未勾选特征的值一律保持标准 JSON 字符串（带引号）。flags=0 时与
    serialize_json 输出逐字节等价（纯增量，零破坏）。

    字符串命中勾选特征时执行合法化转换（去逗号 → 去前导 + → 去前导零，
    文本级操作，不过 float/int 防精度丢失），转换后经 RFC 8259 number
    语法兜底校验，失败回退带引号——**输出永远合法 JSON**。

    恒定输出（不参与判定）：原生 int/float/Decimal/bool/None 按标准 JSON
    （Decimal 跟随 default=str 带引号，与现状语义一致）；bytes 在面板开启时
    UTF-8 decode（errors=replace）后按字符串判定。

    indent: None=紧凑输出；整数 N=每层缩进 N 空格（与 json.dumps(indent=N)
    形状一致，值按判定裸出）。
    """
    if not isinstance(flags, int) or flags & ~_SMART_FLAG_ALL:
        raise ValueError(
            f"非法 smart_quote_flags: {flags!r}（仅支持位 1/2/4）")
    if flags == 0:
        return serialize_json(obj, indent=indent)
    return "".join(_smart_parts(obj, flags, indent, 0))


def _smart_parts(obj, flags, indent, level):
    """递归拼装输出片段；dict/list 结构 + 标量按判定输出。"""
    if isinstance(obj, dict):
        if not obj:
            return ["{}"]
        parts = ["{"]
        for i, (k, v) in enumerate(obj.items()):
            if i:
                parts.append(", " if indent is None else ",")
            if indent is not None:
                parts.append("\n")
                parts.append(" " * (indent * (level + 1)))
            parts.append(json.dumps(k, ensure_ascii=False))
            parts.append(": ")
            parts.extend(_smart_parts(v, flags, indent, level + 1))
        if indent is not None:
            parts.append("\n")
            parts.append(" " * (indent * level))
        parts.append("}")
        return parts
    if isinstance(obj, (list, tuple)):
        if not obj:
            return ["[]"]
        parts = ["["]
        for i, v in enumerate(obj):
            if i:
                parts.append(", " if indent is None else ",")
            if indent is not None:
                parts.append("\n")
                parts.append(" " * (indent * (level + 1)))
            parts.extend(_smart_parts(v, flags, indent, level + 1))
        if indent is not None:
            parts.append("\n")
            parts.append(" " * (indent * level))
        parts.append("]")
        return parts
    return [_smart_scalar(obj, flags)]


def _smart_scalar(val, flags) -> str:
    """标量 → 输出片段：字符串按特征判定；其余按标准 JSON。"""
    if isinstance(val, bytes):
        return _smart_quote_or_strip(
            val.decode("utf-8", errors="replace"), flags)
    if isinstance(val, str):
        return _smart_quote_or_strip(val, flags)
    # 原生类型（int/float/Decimal/bool/None/date 等）：标准 JSON 序列化
    return json.dumps(val, ensure_ascii=False, default=str)


def _smart_quote_or_strip(s: str, flags: int) -> str:
    """字符串值：命中勾选特征 → 合法化转换后裸输出；否则标准 JSON 字符串。"""
    if flags & SMART_FLAG_DECIMAL and _SMART_DECIMAL_RE.match(s):
        return _smart_validated(_smart_normalize(s))
    if flags & SMART_FLAG_SCIENTIFIC and _SMART_SCIENTIFIC_RE.match(s):
        return _smart_validated(_smart_normalize(s))
    if flags & SMART_FLAG_THOUSAND and _SMART_THOUSAND_RE.match(s):
        return _smart_validated(_smart_normalize(s))
    return json.dumps(s, ensure_ascii=False)


def _smart_normalize(s: str) -> str:
    """合法化转换链（文本级）：去逗号 → 去前导 + → 去前导零。"""
    s = s.replace(",", "")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        body = s[1:]
        sign = "-"
    else:
        body = s
        sign = ""
    # 去前导零：0 单独保留、0.5 保留（0 后为小数点）；007 → 7
    i = 0
    while i < len(body) - 1 and body[i] == "0" and body[i + 1].isdigit():
        i += 1
    return sign + body[i:]


def _smart_valid_number(s: str) -> bool:
    """RFC 8259 number 语法兜底校验（严格，拒绝 Infinity/NaN/前导零等）。"""
    return bool(_SMART_NUMBER_RE.match(s))


def _smart_validated(s: str) -> str:
    """转换结果经兜底校验；不满足 number 语法 → 回退标准 JSON 字符串。"""
    if _smart_valid_number(s):
        return s
    return json.dumps(s, ensure_ascii=False)


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


def get_error_log_config() -> dict:
    """解析 error_log 配置段。

    配置文件示例:
        "error_log": {
            "enable": true,
            "path": "error.log"
        }

    缺失时返回 {"enable": False, "path": "error.log"}。
    """
    cfg = get_config().get("error_log", {})
    return {
        "enable": bool(cfg.get("enable", False)),
        "path": str(cfg.get("path", "error.log")),
    }


def get_file_permissions_config() -> dict:
    """解析 file_permissions 配置段。

    配置文件示例:
        "file_permissions": {
            "enable": true,
            "user": "nginx",
            "group": "nginx",
            "dir_mode": "0755",
            "file_mode": "0644"
        }

    dir_mode/file_mode 可选（八进制字符串），缺省值由调用方决定
    （file_permissions 默认 0755/0644）。
    缺失或未启用时返回 {"enable": False}。
    """
    return get_config().get("file_permissions", {"enable": False})


def get_audit_db_config() -> dict:
    """解析 audit_db 配置段。

    配置文件示例:
        "audit_db": {
            "path": "audit.db",
            "retention_days": 90
        }

    retention_days: 保留天数（0 = 永久保存）。
    缺失时返回默认值 {"path": "audit.db", "retention_days": 0}。
    """
    cfg = get_config().get("audit_db", {})
    retention = int(cfg.get("retention_days", 0))
    return {
        "path": str(cfg.get("path", "audit.db")),
        "retention_days": max(0, retention),
    }
