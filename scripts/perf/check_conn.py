#!/usr/bin/env python3
"""
check_conn.py — 性能测试前的连接健康检查（只读，不建表不改数据）

用途：
    在造数与压测之前确认 MySQL 数据源与 Redis 缓存都真的连得上。
    任何一个不通就以非零码退出，并把「缺什么、去哪补」直接打印出来，
    避免后续步骤在错误的假设上跑很久才失败。

检查项：
    1. MySQL —— 取 app_config 的 test_mysql 段，做一次 SELECT 1 并列出表
    2. Redis —— 取 app_config 的 redis 段，做一次 PING 并报告 key 数量

用法：
    source venv/bin/activate
    python scripts/perf/check_conn.py

退出码：
    0 = 两项均通过；1 = 至少一项失败（原因打印到 stderr）
"""

import os
import sys
from pathlib import Path

# 仓库根推导（AGENTS #10：禁止硬编码本项目主目录绝对路径）
_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

import app_config  # noqa: E402


def _mask(value) -> str:
    """凭据打码，避免把密码原文打进日志。"""
    if value is None:
        return "<未配置>"
    text = str(value)
    if not text:
        return "<空>"
    if len(text) <= 2:
        return "*" * len(text)
    return text[:1] + "*" * (len(text) - 2) + text[-1:]


def _describe(section: dict, keys: tuple) -> str:
    """把配置段的实际取值打出来（密码打码），便于定位缺哪个键。"""
    return "  ".join(
        f"{k}={_mask(section.get(k)) if k in ('password',) else section.get(k, '<未配置>')}"
        for k in keys
    )


def check_mysql(cfg: dict) -> bool:
    """检查 test_mysql 段连通性。返回 True/False。"""
    section = cfg.get("test_mysql") or {}
    if not section:
        print("[MySQL] FAIL  app_config 配置里没有 test_mysql 段", file=sys.stderr)
        print("        → 请在 app_config.debug.json 增加 test_mysql 段"
              "（参考 app_config.debug.example.json）", file=sys.stderr)
        return False
    if not section.get("enable", False):
        print("[MySQL] FAIL  test_mysql.enable 不为 true，当前配置：", file=sys.stderr)
        print("        " + _describe(section,
                                 ("enable", "host", "port", "user", "password",
                                  "database")), file=sys.stderr)
        print("        → 请把 test_mysql.enable 改为 true", file=sys.stderr)
        return False

    print("[MySQL] 当前配置：" + _describe(
        section, ("host", "port", "user", "password", "database")))
    try:
        import mysql.connector
    except ImportError as e:
        print(f"[MySQL] FAIL  驱动未安装：{e}", file=sys.stderr)
        print("        → 请在仓库根 venv 中执行 pip install -r requirements.txt",
              file=sys.stderr)
        return False

    conn = None
    try:
        conn = mysql.connector.connect(
            host=section.get("host", "127.0.0.1"),
            port=int(section.get("port", 3306)),
            user=section.get("user", "root"),
            password=section.get("password", ""),
            database=section.get("database", ""),
            connection_timeout=10,
        )
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT VERSION() AS ver, DATABASE() AS db")
        row = cur.fetchone()
        cur.execute("SHOW TABLES")
        tables = [list(r.values())[0] for r in cur.fetchall()]
    except Exception as e:
        print(f"[MySQL] FAIL  {type(e).__name__}: {e}", file=sys.stderr)
        print("        → 确认 MySQL 已启动、端口/账号/密码/库名正确；"
              "若端口不对请改 app_config.debug.json 的 test_mysql 段",
              file=sys.stderr)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    print(f"[MySQL] OK    版本={row['ver']} 当前库={row['db']} 表数={len(tables)}")
    print(f"        已有表：{', '.join(tables) if tables else '（空库）'}")
    return True


def check_redis(cfg: dict) -> bool:
    """检查 redis 段连通性。返回 True/False。"""
    section = cfg.get("redis") or {}
    if not section:
        print("[Redis] SKIP  app_config 配置里没有 redis 段（性能压测需要 Redis 参与）",
              file=sys.stderr)
        return False
    if not section.get("enable", False):
        print("[Redis] FAIL  redis.enable 不为 true，S5 场景无法测", file=sys.stderr)
        print("        " + _describe(section,
                                 ("enable", "host", "port", "db", "password",
                                  "key_prefix")), file=sys.stderr)
        print("        → 请把 app_config.debug.json 的 redis.enable 改为 true",
              file=sys.stderr)
        return False

    print("[Redis] 当前配置：" + _describe(
        section, ("host", "port", "db", "password", "key_prefix")))
    try:
        import redis
    except ImportError as e:
        print(f"[Redis] FAIL  驱动未安装：{e}", file=sys.stderr)
        print("        → 请在仓库根 venv 中执行 pip install -r requirements.txt",
              file=sys.stderr)
        return False

    try:
        client = redis.Redis(
            host=section.get("host", "127.0.0.1"),
            port=int(section.get("port", 6379)),
            db=int(section.get("db", 0)),
            password=section.get("password") or None,
            socket_timeout=int(section.get("socket_timeout", 5)),
        )
        alive = client.ping()
        size = client.dbsize()
    except Exception as e:
        print(f"[Redis] FAIL  {type(e).__name__}: {e}", file=sys.stderr)
        print("        → 确认 Redis 已启动；报 AuthenticationError 时密码不对，"
              "请改 app_config.debug.json 的 redis.password", file=sys.stderr)
        return False

    prefix = section.get("key_prefix", "sr")
    try:
        sample = client.keys(f"{prefix}:*")[:3]
    except Exception:
        sample = []
    print(f"[Redis] OK    PING={alive} 库内 key 数={size} 前缀={prefix}")
    if sample:
        print(f"        样例 key：{[k.decode() if isinstance(k, bytes) else k for k in sample]}")
    return True


def main() -> int:
    print(f"DEBUG 模式激活：{app_config.is_debug_mode()}")
    print(f"配置来源：CONFIG_FILE={os.environ.get('CONFIG_FILE', 'app_config.json')}"
          f"  DEBUG_CONFIG_FILE={os.environ.get('DEBUG_CONFIG_FILE', 'app_config.debug.json')}")
    print("-" * 68)

    cfg = app_config.get_config()
    mysql_ok = check_mysql(cfg)
    redis_ok = check_redis(cfg)
    print("-" * 68)

    if mysql_ok and redis_ok:
        print("连接健康检查全部通过，可以进入造数与压测。")
        return 0
    failed = [n for n, ok in (("MySQL", mysql_ok), ("Redis", redis_ok)) if not ok]
    print(f"连接健康检查未通过：{'、'.join(failed)}", file=sys.stderr)
    print("请补齐 app_config.debug.json 后重跑；不要自行改代码绕过。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
