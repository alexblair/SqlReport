#!/usr/bin/env python3
"""
init_debug_env.py — 初始化 DEBUG 配置库，建性能数据源与报表

背景：
    仓库根的 config.debug.db 是空库（连 report_configs 表都没有），直接起服务
    跑 /report 会 404 或报错。本脚本建表 + 跑迁移 + 建数据源 + 建 4 张性能报表，
    让 bench.py 有可压测的目标。

同时建一个专用基准测试账号（凭据自动生成并写入 perf-logs/bench-credentials.txt，
该目录已 gitignore），这样无需人工提供 web 登录口令。

用法：
    source venv/bin/activate
    python scripts/perf/seed_perf_data.py     # 先造数
    python scripts/perf/init_debug_env.py     # 再初始化配置库

脚本幂等：重复执行时按名称清理同名旧报表与旧数据源再建。
"""

import os
import secrets
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

import app_config        # noqa: E402
import auth              # noqa: E402
import config_db         # noqa: E402
import api_handler       # noqa: E402

CRED_FILE = _REPO_ROOT / "perf-logs" / "bench-credentials.txt"
BENCH_USER = "perf_bench"

# 4 张性能报表：(名称, SQL, prefer_cache, cache_ttl_hours, 用途)
REPORTS = [
    ("P1-文本Decimal", "SELECT * FROM perf_text", 0, 0,
     "10万行，DECIMAL + 混排 mixed + NULL created_at；S1/S3/S4 主力"),
    ("P2-宽表30列", "SELECT * FROM perf_wide", 0, 0,
     "5万行 × 30 列；宽表列查找与单元格字符串化"),
    ("P3-多结果集",
     "SELECT * FROM perf_multi_a; SELECT * FROM perf_multi_b; "
     "SELECT * FROM perf_multi_c", 0, 0,
     "一条 SQL 三个结果集；per-result-set transform 循环"),
    ("P4-Redis路径", "SELECT * FROM perf_text", 1, 24,
     "prefer_cache=1 走 L2 快照；S5 专用"),
]


def ensure_credentials() -> tuple[str, str]:
    """确保基准账号存在，返回 (username, password)。

    已有凭据文件则复用（保证 bench.py 与建库时一致）；否则生成随机密码，
    写入 gitignore 的 perf-logs/ 并新建账号。
    """
    if CRED_FILE.exists():
        content = CRED_FILE.read_text(encoding="utf-8").splitlines()
        kv = dict(line.split("=", 1) for line in content if "=" in line)
        if "user" in kv and "pass" in kv:
            return kv["user"], kv["pass"]

    password = secrets.token_urlsafe(18)
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRED_FILE.write_text(
        f"# 性能压测专用账号（本地生成，perf-logs/ 已 gitignore，勿外传）\n"
        f"user={BENCH_USER}\npass={password}\n",
        encoding="utf-8")
    return BENCH_USER, password


def main() -> int:
    if not app_config.is_debug_mode():
        sys.exit("未激活 DEBUG 模式：请确认仓库根存在 app_config.debug.json")

    conn = config_db.get_config_db()
    try:
        config_db.init_db(conn)
        conn.commit()
        print(f"配置库已初始化：{type(conn).__name__}（engine="
              f"{config_db._get_engine()}）")

        # ---- 数据源（pool）：全部指向 test_mysql 段 ----
        tm = app_config.get_config().get("test_mysql") or {}
        if not tm.get("enable", False):
            sys.exit("test_mysql.enable 不为 true，请先跑 scripts/perf/check_conn.py")

        pool_name = "perf-mysql"
        existing = next((p for p in config_db.get_all_pools(conn)
                         if p["name"] == pool_name), None)
        if existing:
            pool_id = existing["id"]
            print(f"数据源已存在：{pool_name}（id={pool_id}）")
        else:
            pool_id = config_db.add_pool(
                conn, pool_name, tm.get("host", "127.0.0.1"),
                int(tm.get("port", 3306)), tm.get("user", "root"),
                tm.get("password", ""), tm.get("database", ""))
            print(f"数据源已建：{pool_name}（id={pool_id}）")

        # ---- 基准账号 ----
        username, password = ensure_credentials()
        rows = conn.execute("SELECT id FROM users WHERE username=?",
                            (username,)).fetchone()
        if rows:
            # 账号已存在：重置密码为文件中的值，保证 bench.py 能登录
            conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                         (auth.hash_password(password), username))
            conn.commit()
            print(f"基准账号已存在并重置密码：{username}")
        else:
            config_db.add_user(conn, username, auth.hash_password(password))
            print(f"基准账号已建：{username}（密码见 {CRED_FILE.relative_to(_REPO_ROOT)}）")

        # ---- 报表（先清同名旧的，保证幂等）----
        old = {r["name"]: r["id"] for r in config_db.get_all_reports(conn)}
        created = {}
        for name, sql, prefer, ttl, purpose in REPORTS:
            if name in old:
                config_db.delete_report(conn, old[name])
                conn.commit()
                print(f"清理旧报表：{name}（id={old[name]}）")
            rid = config_db.add_report(
                conn, name=name, sql_query=sql, default_page_size=20,
                pool_id=pool_id, memo=purpose,
                # 性能测试要看到全量数据，显式关掉全量护栏，避免 max_rows
                # 截断掩盖 transform 本身的耗时
                prefer_cache=prefer, cache_ttl_hours=ttl,
                allow_write=0, allow_all_output=1, max_rows=0)
            created[name] = rid
            print(f"报表已建：{name}（id={rid}）prefer_cache={prefer} "
                  f"ttl={ttl}h")

        # ---- 输出 bench.py 需要的映射 ----
        print("\n--- bench.py 用的报表 ID ---")
        for name, rid in created.items():
            print(f"{name}={rid}")

        # ---- 给 P4 建一个 API 端点（S6 场景用）----
        # url_path 必须自带 /api 前缀：handle_api_request 按 norm_path 原样查表，
        # ensure_api_prefix 只在配置页创建时生效，查询时不会补全。
        api_path = "/api/perf/redis-path.json"
        old_ep = next((e for e in config_db.get_all_api_endpoints(conn)
                       if e["url_path"] == api_path), None)
        if old_ep:
            config_db.delete_api_endpoint(conn, old_ep["id"])
            conn.commit()
        api_key = api_handler.generate_api_key()
        ep_id = config_db.add_api_endpoint(
            conn, report_id=created["P4-Redis路径"], name="性能压测-Redis路径",
            url_path=api_path, output_format="json", api_key=api_key,
            row_limit=0, static_cache=0)  # static_cache=0：S6 要测实时 API 路径
        conn.commit()
        CRED_FILE.write_text(
            CRED_FILE.read_text(encoding="utf-8")
            + f"api_path={api_path}\napi_key={api_key}\n",
            encoding="utf-8")
        print(f"API 端点已建：{api_path}（id={ep_id}，api_key 见凭据文件）")

        # 自检：4 张报表都能读回
        for name, rid in created.items():
            got = config_db.get_report(conn, rid)
            assert got is not None, f"报表 {name} (id={rid}) 读不回来"
            assert got["pool_id"] == pool_id, f"报表 {name} 的 pool_id 不对"
        print(f"\n自检通过：{len(created)} 张报表可读回，pool_id 一致。")
        print(f"基准账号：{username}（密码见 {CRED_FILE.relative_to(_REPO_ROOT)}）")
        print("下一步：python scripts/perf/bench.py --out <路径>")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
