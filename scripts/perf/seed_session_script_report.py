#!/usr/bin/env python3
"""seed_session_script_report.py — 造「会话级脚本」与「真持久写」两个本地夹具

用途：为 `bench_session_script.py` 准备可压测的本地夹具，验证
「写判定分工」对缓存读门槛的效果（见 spec 2026-09-30-write-report-cache-gate-design.md §9.3）。

**只在本地**：目标库是 config.debug.db 里 `perf-mysql` 池（127.0.0.1:3307 `sqlreport_test`），
绝不触碰生产。表名带 `perf_sess_` 前缀，可重复执行（先 DROP 再建）。

用法：
    DEBUG_CONFIG_FILE=app_config.debug.json1 venv/bin/python scripts/perf/seed_session_script_report.py
"""

import os
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

from query_executor import (  # noqa: E402
    sql_contains_write,
    sql_has_persistent_write,
)

# ---------------------------------------------------------------- 夹具定义

SRC_TABLE = "perf_sess_src"
WRITE_TABLE = "perf_sess_write_tgt"
ROW_COUNT = 20000

# 会话级脚本：只建临时表 + 读，无任何持久副作用。
SESSION_SCRIPT_SQL = (
    "DROP TEMPORARY TABLE IF EXISTS perf_sess_tmp;\n"
    f"CREATE TEMPORARY TABLE perf_sess_tmp SELECT id, v FROM {SRC_TABLE};\n"
    "SELECT id, v FROM perf_sess_tmp;\n"
)

# 真持久写：TRUNCATE + INSERT 落到持久表，必须继续跳过缓存。
PERSISTENT_WRITE_SQL = (
    f"TRUNCATE TABLE {WRITE_TABLE};\n"
    f"INSERT INTO {WRITE_TABLE} (v) SELECT v FROM {SRC_TABLE};\n"
    f"SELECT id, v FROM {WRITE_TABLE};\n"
)

REPORT_ID = 9001
REPORT_CFG = {
    "id": REPORT_ID,
    "name": "perf 会话级脚本夹具",
    "pool_id": 4,                       # config.debug.db 的 perf-mysql 池
    "sql_query": SESSION_SCRIPT_SQL,
    "prefer_cache": 1,
    "cache_ttl_hours": 6,
    "allow_write": 1,
    "allow_all_output": 1,
    "max_rows": 0,
}


def debug_pool_config(config_db_path="config.debug.db", pool_name="perf-mysql"):
    """从 debug 配置库读取本地数据源（不硬编码库凭据）。"""
    con = sqlite3.connect(f"file:{config_db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT host,port,user,password,database FROM connection_pools "
            "WHERE name=?", (pool_name,)).fetchone()
        if row is None:
            raise RuntimeError(f"{config_db_path} 里没有连接池 {pool_name!r}")
        return {k: row[k] for k in row.keys()}
    finally:
        con.close()


def main() -> int:
    pool = debug_pool_config()
    if pool["host"] not in ("127.0.0.1", "localhost"):
        print(f"FAIL: 拒绝在非本地数据源上造数（host={pool['host']}）")
        return 1
    print(f"目标数据源: {pool['host']}:{pool['port']}/{pool['database']}")

    import mysql.connector
    conn = mysql.connector.connect(
        host=pool["host"], port=int(pool["port"]), user=pool["user"],
        password=pool["password"], database=pool["database"],
        connection_timeout=10)
    try:
        cur = conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {WRITE_TABLE}")
        cur.execute(f"DROP TABLE IF EXISTS {SRC_TABLE}")
        cur.execute(
            f"CREATE TABLE {SRC_TABLE} ("
            "id INT PRIMARY KEY AUTO_INCREMENT, v VARCHAR(32))")
        cur.execute(
            f"CREATE TABLE {WRITE_TABLE} ("
            "id INT PRIMARY KEY AUTO_INCREMENT, v VARCHAR(32))")
        # 批量灌数（executemany 比逐条 INSERT 快一个量级）
        cur.executemany(
            f"INSERT INTO {SRC_TABLE} (v) VALUES (%s)",
            [(f"v{i:06d}",) for i in range(ROW_COUNT)])
        conn.commit()
        cur.execute(f"SELECT COUNT(*) FROM {SRC_TABLE}")
        n = cur.fetchone()[0]
        cur.close()
    finally:
        conn.close()

    print(f"{SRC_TABLE} 行数 = {n}")
    assert n == ROW_COUNT, f"造数不完整: {n} != {ROW_COUNT}"

    # 分类断言：夹具必须落在各自的设计区间
    session_old = sql_contains_write(SESSION_SCRIPT_SQL)
    session_new = sql_has_persistent_write(SESSION_SCRIPT_SQL)
    write_old = sql_contains_write(PERSISTENT_WRITE_SQL)
    write_new = sql_has_persistent_write(PERSISTENT_WRITE_SQL)
    print(f"会话级脚本 : sql_contains_write={session_old} "
          f"sql_has_persistent_write={session_new}")
    print(f"真持久写   : sql_contains_write={write_old} "
          f"sql_has_persistent_write={write_new}")
    assert session_old is True and session_new is False, "会话级夹具分类不符"
    assert write_old is True and write_new is True, "真写夹具分类不符"

    print("RESULT: PASS（夹具就绪）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
