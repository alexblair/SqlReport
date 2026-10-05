#!/usr/bin/env python3
"""bench_session_script.py — 会话级脚本报表的缓存门槛 A/B + 三端一致性

**只在本地 debug 环境跑**：Redis db0 / 前缀 `sr_debug`、sqlite `config.debug.db`、
MySQL `127.0.0.1:3307/sqlreport_test`。脚本启动即校验数据源 host ∈ {127.0.0.1, localhost}，
拒绝指向生产。

用法：
    DEBUG_CONFIG_FILE=app_config.debug.json1 venv/bin/python \
        scripts/perf/bench_session_script.py --arm old --pages 20
    DEBUG_CONFIG_FILE=app_config.debug.json1 venv/bin/python \
        scripts/perf/bench_session_script.py --arm new --pages 20
    DEBUG_CONFIG_FILE=app_config.debug.json1 venv/bin/python \
        scripts/perf/bench_session_script.py --check-consumers

两个 arm：
  old —— 把 `report.sql_has_persistent_write` 猴补为恒 True，复现「写判定 → 跳过全部读缓存」
         的改造前行为（同一进程、同一数据、同一脚本，唯一变量就是门槛）。
  new —— 真实函数。

三端一致性（--check-consumers）：报表页 / 导出 / API 三条真实代码路径在缓存已热时，
**都不得再触达数据源**（用 `db.execute_mysql_query` 计数取证）。
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

import export            # noqa: E402
import report            # noqa: E402
import redis_cache       # noqa: E402
from scripts.perf.seed_session_script_report import (   # noqa: E402
    REPORT_CFG,
    REPORT_ID,
    SESSION_SCRIPT_SQL,
    debug_pool_config,
)

PAGE_SIZE = 20


def _assert_local(pool):
    if pool["host"] not in ("127.0.0.1", "localhost"):
        raise SystemExit(f"拒绝在非本地数据源上压测（host={pool['host']}）")


class MySQLCounter:
    """统计真实跑库次数（包装 report.db.execute_mysql_query）。"""

    def __enter__(self):
        self.n = 0
        self._orig = report.db.execute_mysql_query

        def wrapper(*a, **kw):
            self.n += 1
            return self._orig(*a, **kw)

        report.db.execute_mysql_query = wrapper
        return self

    def __exit__(self, *exc):
        report.db.execute_mysql_query = self._orig
        return False


def _reset_caches():
    """清 L1 + 本报表在 debug Redis 的全部快照，保证 arm 之间冷启动可比。"""
    report._query_cache.clear()
    mgr = redis_cache.get_redis_manager()
    if mgr:
        for key in mgr.scan_snapshots(mgr.key_prefix, REPORT_ID):
            mgr.delete_snapshot(key)


def _arm_patch(arm):
    if arm != "old":
        return lambda: None
    orig = report.sql_has_persistent_write
    report.sql_has_persistent_write = lambda sql: True
    return lambda: setattr(report, "sql_has_persistent_write", orig)


def _p50_p95(samples):
    s = sorted(samples)
    return (statistics.median(s),
            s[min(len(s) - 1, int(0.95 * (len(s) - 1)))])


def run_arm(arm, pages):
    _assert_local(debug_pool_config())
    _reset_caches()
    restore = _arm_patch(arm)
    try:
        pool = debug_pool_config()
        sources, times, slices = [], [], {}
        with MySQLCounter() as counter:
            t0 = time.perf_counter()
            r = report.execute_report(
                REPORT_ID, SESSION_SCRIPT_SQL, pool, page=1,
                page_size=PAGE_SIZE, report=REPORT_CFG)
            warm_ms = (time.perf_counter() - t0) * 1000
            first_source = (r.cache_info or {}).get("source")
            for page in range(2, pages + 2):
                t0 = time.perf_counter()
                r = report.execute_report(
                    REPORT_ID, SESSION_SCRIPT_SQL, pool, page=page,
                    page_size=PAGE_SIZE, report=REPORT_CFG)
                times.append((time.perf_counter() - t0) * 1000)
                sources.append((r.cache_info or {}).get("source"))
                slices[page] = r.results[0]["rows"][:3]
            mysql_execs = counter.n
    finally:
        restore()
    p50, p95 = _p50_p95(times)
    return {"arm": arm, "warm_ms": round(warm_ms, 2),
            "first_source": first_source, "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2), "mysql_execs": mysql_execs,
            "sources": sources, "slices": slices}


def check_consumers():
    """报表页 / 导出 / API 三条真实路径在缓存已热时都不得再触达数据源。"""
    _assert_local(debug_pool_config())
    _reset_caches()
    pool = debug_pool_config()
    ok = True
    with MySQLCounter() as counter:
        report.execute_report(REPORT_ID, SESSION_SCRIPT_SQL, pool, page=1,
                              page_size=PAGE_SIZE, report=REPORT_CFG)
        warmed = counter.n
        print(f"[预热] 数据源执行 {warmed} 次（应为 1）")

        r = report.execute_report(REPORT_ID, SESSION_SCRIPT_SQL, pool, page=2,
                                  page_size=PAGE_SIZE, report=REPORT_CFG)
        src = (r.cache_info or {}).get("source")
        print(f"[报表页] 第二次 source={src} 数据源执行增量="
              f"{counter.n - warmed}")
        ok &= (counter.n == warmed and src in ("process", "redis"))

        before = counter.n
        export._load_and_transform(SESSION_SCRIPT_SQL, pool,
                                   report_id=REPORT_ID,
                                   report_config=REPORT_CFG)
        print(f"[导出] 数据源执行增量={counter.n - before}")
        ok &= (counter.n == before)

        endpoint = {"report_id": REPORT_ID, "name": "perf 会话级脚本夹具",
                    "url_path": "/api/perf/session-script", "enabled": 1,
                    "static_cache": 0, "output_format": "json",
                    "columns": "", "filters": "", "sorts": "", "row_limit": 0,
                    "json_template": "", "result_mode": "single",
                    "result_index": 0, "allow_fetch_all": 0,
                    "smart_quote_flags": 0, "nested_filter": "",
                    "api_key": None, "allowed_origins": None}
        from unittest.mock import patch
        before = counter.n
        with patch("api_handler.db.get_report", return_value=REPORT_CFG), \
                patch("api_handler.db.get_pool", return_value=pool):
            import api_handler
            api_handler._execute_api_query(None, endpoint, "GET", "", {}, {})
        print(f"[API] 数据源执行增量={counter.n - before}")
        ok &= (counter.n == before)

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("old", "new"))
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--check-consumers", action="store_true")
    args = ap.parse_args()

    if args.check_consumers:
        return check_consumers()
    if not args.arm:
        ap.error("需要 --arm {old,new} 或 --check-consumers")

    result = run_arm(args.arm, args.pages)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = _REPO_ROOT / "perf-logs" / f"T4-{args.arm}-{stamp}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"arm={result['arm']} 请求数={args.pages}")
    print(f"  预热(冷)      : {result['warm_ms']} ms  source={result['first_source']}")
    print(f"  翻页 P50/P95  : {result['p50_ms']} / {result['p95_ms']} ms")
    print(f"  数据源执行次数: {result['mysql_execs']}（请求总数 {args.pages + 1}）")
    print(f"  source 序列   : {result['sources'][:6]}"
          f"{' ...' if len(result['sources']) > 6 else ''}")
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
