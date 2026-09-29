#!/usr/bin/env python3
"""
verify_transform_equivalence.py — transform 优化的逐行一致性验证

为什么需要它（spec §6.2）：
    C-1b/C-1c 改的是筛选与排序的错误模式是**静默改变行序与行内容**——
    不报错，只是用户看到的顺序变了。单测覆盖的是小数据与手挑用例，
    这里补一层「真实 10 万行 + 条件矩阵 + 与优化前实现逐行比对」。

参考实现从 **git 02a95a1（优化前基线快照）** 取出，不是凭记忆重写——
重写就变成「用新实现验证新实现」了。

用法：
    source venv/bin/activate
    python scripts/perf/verify_transform_equivalence.py
"""

import importlib.util
import itertools
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

BASELINE_COMMIT = "02a95a1"   # spec §10.1 基线快照
REF_DUMP = _REPO_ROOT / "perf-logs" / f"result_transform_{BASELINE_COMMIT}.py"

import app_config        # noqa: E402
import db                # noqa: E402
import result_transform as current   # noqa: E402


def load_reference():
    """从 git 基线取出优化前的 result_transform 并加载为独立模块。"""
    REF_DUMP.parent.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:result_transform.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True).stdout
    REF_DUMP.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("rt_baseline", REF_DUMP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rows(table: str = "perf_text"):
    """从 MySQL 取真实性能数据。"""
    tm = app_config.get_config()["test_mysql"]
    pool = {"host": tm["host"], "port": tm["port"], "user": tm["user"],
            "password": tm["password"], "database": tm["database"]}
    conn = db.create_mysql_connection(pool)
    try:
        res = db.execute_mysql_query(conn, f"SELECT * FROM {table}")
    finally:
        conn.close()
    return res[0]["columns"], res[0]["rows"]


def build_cases(columns, rows):
    """构造 (说明, filters, sorts) 组合矩阵。"""
    has = set(columns)
    cases = []

    cases.append(("无筛选无排序", None, None))
    cases.append(("空筛选列表", [], []))

    text_cols = [c for c in columns if isinstance(rows[0][columns.index(c)], str)]
    for col in text_cols[:2]:
        sample = str(rows[len(rows) // 2][columns.index(col)])
        for op, val in (("contains", sample[:3]), ("notcontains", sample[:3]),
                        ("eq", sample), ("neq", sample),
                        ("isempty", None), ("notempty", None)):
            cases.append((f"{col} {op}", [(col, op, val or "")], None))
        cases.append((f"{col} 通配 contains", [(col, "contains", "*" + sample[0])], None))

    numeric_cols = [c for c in ("amount", "id") if c in has]
    for col in numeric_cols:
        for op, val in (("gt", "100"), ("lt", "100"), ("gte", "100"),
                        ("lte", "100")):
            cases.append((f"{col} {op} {val}", [(col, op, val)], None))
        for direction in ("asc", "desc"):
            cases.append((f"sort {col} {direction}", None, [(col, direction)]))

    for col in columns:
        for direction in ("asc", "desc"):
            cases.append((f"sort {col} {direction}", None, [(col, direction)]))

    # 多条件组合与多字段排序
    if text_cols and numeric_cols:
        tc, nc = text_cols[0], numeric_cols[0]
        sample = str(rows[len(rows) // 2][columns.index(tc)])
        cases.append((f"两条件 AND（{tc}+{nc}）",
                      [(tc, "contains", sample[:2]), (nc, "gt", "100")], None))
        cases.append((f"三条件 AND",
                      [(tc, "contains", sample[:2]), (nc, "gt", "100"),
                       (nc, "lt", "50000")], None))
    sort_cols = [c for c in columns if c != "id"][:3]
    if len(sort_cols) >= 2:
        cases.append((f"双字段排序 {sort_cols[0]}+{sort_cols[1]}", None,
                      [(sort_cols[1], "asc"), (sort_cols[0], "desc")]))
    if len(sort_cols) >= 3:
        cases.append((f"三字段排序", None,
                      [(sort_cols[2], "asc"), (sort_cols[1], "desc"),
                       (sort_cols[0], "asc")]))
    # 条件 + 排序叠加
    if text_cols:
        tc = text_cols[0]
        sample = str(rows[len(rows) // 2][columns.index(tc)])
        cases.append((f"筛选+排序叠加", [(tc, "contains", sample[0])],
                      [(text_cols[0], "desc")]))
    return cases


def main() -> int:
    print(f"加载优化前参考实现（git {BASELINE_COMMIT}）…")
    ref = load_reference()
    print("加载性能数据…")
    columns, rows = load_rows()
    print(f"数据：{len(rows)} 行 × {len(columns)} 列 —— {columns}\n")

    cases = build_cases(columns, rows)
    print(f"逐行比对 {len(cases)} 个组合（每组跑两遍实现并全量对比）…\n")

    failures = []
    total_rows_compared = 0
    for i, (desc, filters, sorts) in enumerate(cases, 1):
        t0 = time.perf_counter()
        ref_out = ref.filter_rows(rows, columns, filters)
        ref_out = ref.sort_rows(ref_out, columns, sorts)
        t_ref = time.perf_counter() - t0

        t0 = time.perf_counter()
        cur_out = current.filter_rows(rows, columns, filters)
        cur_out = current.sort_rows(cur_out, columns, sorts)
        t_cur = time.perf_counter() - t0

        total_rows_compared += len(ref_out)
        if len(ref_out) != len(cur_out):
            failures.append(
                f"[{desc}] 行数不一致：参考 {len(ref_out)} vs 当前 {len(cur_out)}")
            print(f"  {i:>3}. {desc:<28} ❌ 行数不一致")
            continue
        for idx, (a, b) in enumerate(zip(ref_out, cur_out)):
            if a != b:
                failures.append(f"[{desc}] 第 {idx} 行不同：参考 {a!r} vs 当前 {b!r}")
                print(f"  {i:>3}. {desc:<28} ❌ 第 {idx} 行不同")
                break
        else:
            delta = (t_cur / t_ref - 1) * 100 if t_ref else 0.0
            flag = "✅" if delta <= 0 else "⚠"
            print(f"  {i:>3}. {desc:<28} ✅ {len(ref_out):>6} 行  "
                  f"参考 {t_ref*1000:6.1f}ms / 当前 {t_cur*1000:6.1f}ms "
                  f"({delta:+.1f}%)")

    print(f"\n共比对 {len(cases)} 个组合、{total_rows_compared} 行次。")
    if failures:
        print(f"\n❌ 发现 {len(failures)} 处不一致：", file=sys.stderr)
        for f in failures:
            print(f"   - {f}", file=sys.stderr)
        print("\n语义已被破坏。请回到根因分析，"
              "不要修改参考实现去迁就当前实现。", file=sys.stderr)
        return 1
    print("✅ 全部组合与优化前实现逐行完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
