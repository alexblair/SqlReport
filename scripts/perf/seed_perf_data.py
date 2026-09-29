#!/usr/bin/env python3
"""
seed_perf_data.py — 在 sqlreport_test 库造执行层性能测试数据

设计意图：
    现有 test_mysql 的表只有 3~5 行，测不出任何执行层问题。本脚本造出
    覆盖不同 transform 退化模式的数据集：

    perf_text     10 万行 —— amount DECIMAL 且含 NULL（Decimal 慢路径 + None 恒末尾）、
                   mixed 混排数字串/纯文本/空串/NULL（数值/文本分区排序）、
                   created_at DATETIME 含 NULL（日期解析 + None 排序）
    perf_wide      5 万行 × 30 列（宽表列查找与单元格字符串化）
    perf_multi_a/b/c 各 2 万行（一条 SQL 返回 3 个结果集）
    big_table     20 万行（沿用既有表，纯量级基线对照）

用法：
    source venv/bin/activate
    python scripts/perf/seed_perf_data.py                 # 完整规模
    python scripts/perf/seed_perf_data.py --rows-scale 0.1  # 快速迭代用 1/10

脚本幂等：每次先 DROP 再建，可重复执行。行数会自校验，与预期不符即非零退出。
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

import app_config  # noqa: E402

BATCH = 5000

# 完整规模下的目标行数（--rows-scale 会按比例缩放）
TARGETS = {
    "perf_text": 100_000,
    "perf_wide": 50_000,
    "perf_multi_a": 20_000,
    "perf_multi_b": 20_000,
    "perf_multi_c": 20_000,
    "big_table": 200_000,
}

DDL = {
    "perf_text": """
        CREATE TABLE perf_text (
          id INT PRIMARY KEY,
          amount DECIMAL(12,2) NULL,
          mixed VARCHAR(32) NULL,
          label VARCHAR(32) NOT NULL,
          created_at DATETIME NULL
        ) ENGINE=InnoDB""",
    "perf_wide": None,  # 30 列，程序生成
    "perf_multi_a": "CREATE TABLE perf_multi_a (id INT PRIMARY KEY, v INT) ENGINE=InnoDB",
    "perf_multi_b": "CREATE TABLE perf_multi_b (id INT PRIMARY KEY, v INT) ENGINE=InnoDB",
    "perf_multi_c": "CREATE TABLE perf_multi_c (id INT PRIMARY KEY, v INT) ENGINE=InnoDB",
    "big_table": "CREATE TABLE big_table (id INT PRIMARY KEY, name VARCHAR(64), val INT) ENGINE=InnoDB",
}

WIDE_COLS = 30
_BASE_DT = datetime(2026, 1, 1, 8, 0, 0)


def connect():
    """按 test_mysql 段建立连接。"""
    import mysql.connector
    section = app_config.get_config().get("test_mysql") or {}
    if not section.get("enable", False):
        sys.exit("test_mysql.enable 不为 true，请先跑 scripts/perf/check_conn.py")
    return mysql.connector.connect(
        host=section.get("host", "127.0.0.1"),
        port=int(section.get("port", 3306)),
        user=section.get("user", "root"),
        password=section.get("password", ""),
        database=section.get("database", ""),
        connection_timeout=10,
    )


def gen_text(n: int):
    """perf_text 行生成器：amount 15% NULL，mixed 五值轮换，created_at 10% NULL。"""
    mixed_cycle = ["123", "45.6", "abc", "", None]
    for i in range(1, n + 1):
        yield (
            i,
            None if i % 20 < 3 else Decimal(f"{(i % 100000) / 100:.2f}"),
            mixed_cycle[i % 5],
            f"label-{i % 500:04d}",
            None if i % 10 == 0 else _BASE_DT + timedelta(minutes=i),
        )


def gen_wide(n: int):
    """perf_wide 行生成器：30 列 c01..c30。"""
    for i in range(1, n + 1):
        yield (i,) + tuple(f"v{i:06d}{c:02d}" for c in range(1, WIDE_COLS + 1))


def gen_multi(n: int):
    """perf_multi_* 行生成器：单列 v。"""
    for i in range(1, n + 1):
        yield (i, (i * 37) % 100000)


def gen_big(n: int):
    """big_table 行生成器（沿用既有表结构）。"""
    for i in range(1, n + 1):
        yield (i, f"n{i:07d}", i % 1000)


GENERATORS = {
    "perf_text": ("INSERT INTO perf_text (id,amount,mixed,label,created_at) "
                  "VALUES (%s,%s,%s,%s,%s)", gen_text),
    "perf_wide": (None, gen_wide),  # INSERT 依赖生成的列名
    "perf_multi_a": ("INSERT INTO perf_multi_a (id,v) VALUES (%s,%s)", gen_multi),
    "perf_multi_b": ("INSERT INTO perf_multi_b (id,v) VALUES (%s,%s)", gen_multi),
    "perf_multi_c": ("INSERT INTO perf_multi_c (id,v) VALUES (%s,%s)", gen_multi),
    "big_table": ("INSERT INTO big_table (id,name,val) VALUES (%s,%s,%s)", gen_big),
}


def build_table(cur, name: str) -> None:
    """建表（perf_wide 的 30 列在此程序生成）。"""
    cur.execute(f"DROP TABLE IF EXISTS {name}")
    if name == "perf_wide":
        cols = ", ".join(f"c{c:02d} VARCHAR(24) NULL" for c in range(1, WIDE_COLS + 1))
        cur.execute(f"CREATE TABLE perf_wide (id INT PRIMARY KEY, {cols}) ENGINE=InnoDB")
    else:
        cur.execute(DDL[name])


def fill(cur, name: str, n: int) -> int:
    """分批插入 n 行，返回实际插入行数。"""
    insert_sql, gen = GENERATORS[name]
    if name == "perf_wide":
        cols = ", ".join(f"c{c:02d}" for c in range(1, WIDE_COLS + 1))
        insert_sql = (f"INSERT INTO perf_wide (id,{cols}) VALUES "
                      f"({','.join(['%s'] * (WIDE_COLS + 1))})")
    done = 0
    batch = []
    for row in gen(n):
        batch.append(row)
        if len(batch) >= BATCH:
            cur.executemany(insert_sql, batch)
            done += len(batch)
            batch = []
    if batch:
        cur.executemany(insert_sql, batch)
        done += len(batch)
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description="造执行层性能测试数据")
    parser.add_argument("--rows-scale", type=float, default=1.0,
                        help="行数缩放比例，默认 1.0（完整规模）")
    args = parser.parse_args()
    if args.rows_scale <= 0:
        sys.exit("--rows-scale 必须为正数")

    conn = connect()
    cur = conn.cursor(dictionary=True)
    plan = {name: max(1, int(n * args.rows_scale)) for name, n in TARGETS.items()}

    try:
        for name in TARGETS:
            build_table(cur, name)
        conn.commit()

        for name, n in plan.items():
            actual = fill(cur, name, n)
            conn.commit()
            # 自检：实际插入行数必须与计划一致（MEMORY Rules 4）
            assert actual == n, f"{name} 插入行数 {actual} != 计划 {n}"
            cur.execute(f"SELECT COUNT(*) AS c FROM {name}")
            counted = cur.fetchone()["c"]
            assert counted == n, f"{name} 表内实际 {counted} != 计划 {n}"
            print(f"  {name:<14} {counted:>8} 行  OK")

        # perf_text 的分布自检：确认退化模式真的造出来了
        cur.execute("SELECT COUNT(*) AS c FROM perf_text WHERE amount IS NULL")
        null_amt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM perf_text WHERE mixed IS NULL "
                    "OR mixed = ''")
        blank_mixed = cur.fetchone()["c"]
        ratio_amt = null_amt / plan["perf_text"]
        print(f"\n  分布自检：amount 为 NULL {null_amt} 行（占比 {ratio_amt:.1%}，"
              f"目标约 15%）；mixed 为空/NULL {blank_mixed} 行")
        assert 0.10 <= ratio_amt <= 0.20, f"amount NULL 占比 {ratio_amt:.1%} 偏离目标 15%"
        assert blank_mixed > 0, "mixed 未造出空值，混排场景缺失"
    finally:
        cur.close()
        conn.close()

    print(f"\n性能数据造完（rows-scale={args.rows_scale}）。下一步："
          f"python scripts/perf/init_debug_env.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
