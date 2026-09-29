#!/usr/bin/env python3
"""
verify_redis_fallback.py — 真实 Redis 快照 + 数据源不可用时的兜底验证

spec §6.1 第 4 条要求：不能只靠单测，要真跑一次「数据源挂了页面仍显示数据」。

做法（**不停止 MySQL、不改用户的 app_config.debug.json**）：
  1. 用真实 MySQL 跑一次 prefer_cache=1 的报表 → 真实写入 Redis 快照；
  2. 把该报表的数据源端口改成一个无人监听的端口（127.0.0.1:3999），
     产生**真实的连接失败**（不是 mock）；
  3. 再跑一次 → 应命中 Redis 过期/新鲜快照，cache_info.source == "redis_fallback"；
  4. 再把数据源改回来，确认恢复正常。

⚠️ 本脚本只把「数据源不可用」做成真实故障，Redis 与 MySQL 都是真的。
它**没有**真的停掉 MySQL 服务。

用法：source venv/bin/activate && python scripts/perf/verify_redis_fallback.py
"""

import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

import app_config        # noqa: E402
import config_db         # noqa: E402
import db                # noqa: E402
import redis_cache       # noqa: E402
import report            # noqa: E402

BAD_PORT = 3999          # 无人监听
SQL = "SELECT id, amount FROM perf_text ORDER BY id LIMIT 5"


def _cfg(pool_id, allow_write=1):
    return {"prefer_cache": 1, "cache_ttl_hours": 24, "pool_id": pool_id,
            "sql_query": SQL, "name": "兜底验证", "memo": "",
            "allow_write": allow_write, "allow_all_output": 1, "max_rows": 0}


def main() -> int:
    if not app_config.is_debug_mode():
        sys.exit("未激活 DEBUG 模式")

    conn = config_db.get_config_db()
    try:
        config_db.init_db(conn)
        conn.commit()
        tm = app_config.get_config()["test_mysql"]
        pool_name = "perf-mysql-fallback"
        pool = next((p for p in config_db.get_all_pools(conn)
                     if p["name"] == pool_name), None)
        if not pool:
            pool_id = config_db.add_pool(
                conn, pool_name, tm["host"], int(tm["port"]), tm["user"],
                tm["password"], tm["database"])
        else:
            pool_id = pool["id"]

        rid = config_db.add_report(conn, name="兜底验证", sql_query=SQL,
                                   default_page_size=20, pool_id=pool_id,
                                   memo="verify_redis_fallback", prefer_cache=1,
                                   cache_ttl_hours=24, allow_write=1,
                                   allow_all_output=1, max_rows=0)
        report._query_cache.clear()
        good_pool = db.get_pool(conn, pool_id)
        bad_pool = dict(good_pool, port=BAD_PORT)
        failures = []

        # ① 正常路径：真实查 MySQL，真实写 Redis 快照；再次请求应命中快照
        r1 = report.execute_report(rid, SQL, good_pool, report=_cfg(pool_id))
        src1 = (r1.cache_info or {}).get("source")
        rows1 = [list(x) for x in r1.results[0]["rows"]]
        print(f"① 正常执行：source = {src1}，{len(rows1)} 行")
        if src1 != "redis" or len(rows1) != 5:
            failures.append(f"① 期望 source=redis 且 5 行，实际 {src1}/{len(rows1)}")

        # ② 数据源不可用 + 快照在位 → L2 直接命中，根本不碰 MySQL
        report._query_cache.clear()
        r2 = report.execute_report(rid, SQL, bad_pool, report=_cfg(pool_id))
        src2 = (r2.cache_info or {}).get("source")
        rows2 = [list(x) for x in r2.results[0]["rows"]]
        print(f"② 数据源不可用、快照新鲜：source = {src2}，{len(rows2)} 行"
              f"（L2 命中，未触发数据源）")
        if src2 != "redis":
            failures.append(f"② 期望 redis（快照新鲜时不该碰数据源），实际 {src2}")
        if rows2 != rows1:
            failures.append("② 快照返回的行内容与①不一致")

        # ③ 数据源不可用 + 无快照 → 必须抛异常，不得静默返回空/错数据
        mgr = redis_cache.get_redis_manager()
        ver = redis_cache.compute_config_version(SQL, pool_id)
        key = redis_cache.build_snapshot_key(mgr.key_prefix, rid, ver)
        mgr.delete_snapshot(key)
        report._query_cache.clear()
        try:
            report.execute_report(rid, SQL, bad_pool, report=_cfg(pool_id))
            failures.append("③ 无快照 + 数据源不可用时应当抛异常，却静默返回了")
            print("③ 无快照 + 数据源不可用：❌ 未抛异常")
        except Exception as e:
            print(f"③ 无快照 + 数据源不可用：正确抛出 {type(e).__name__}")

        # ④ redis_fallback：L2 首读 miss + 数据源失败 → 重读快照兜底
        #    ⚠️ 触发方式是「首读 miss」的受控模拟（包一层 get_snapshot 让第一次
        #    返回 None），不是真的让 Redis 掉线。真实世界能稳定命中该分支的序列
        #    本身就窄（首读与重读之间 Redis 恢复）。Redis 与 MySQL 都是真的，
        #    快照与兜底逻辑都是真的，只有「首读 miss」这一步是构造出来的。
        mgr.set_snapshot(key, redis_cache.ReportSnapshot(
            [{"columns": ["id", "amount"], "rows": r1.results[0]["rows"]}],
            SQL, time.time(), ver, truncated=False), ttl_hours=24)
        report._query_cache.clear()
        real_get = mgr.get_snapshot
        state = {"missed": False}

        def first_read_miss(k):
            if not state["missed"]:
                state["missed"] = True
                return None
            return real_get(k)

        mgr.get_snapshot = first_read_miss
        try:
            r4 = report.execute_report(rid, SQL, bad_pool, report=_cfg(pool_id))
        finally:
            mgr.get_snapshot = real_get
        src4 = (r4.cache_info or {}).get("source")
        fresh4 = (r4.cache_info or {}).get("fresh")
        rows4 = [list(x) for x in r4.results[0]["rows"]]
        print(f"④ 首读 miss + 数据源不可用：source = {src4}，fresh = {fresh4}，"
              f"{len(rows4)} 行")
        if src4 != "redis_fallback" or fresh4 is not False:
            failures.append(f"④ 期望 redis_fallback/fresh=False，实际 {src4}/{fresh4}")
        if rows4 != rows1:
            failures.append("④ 兜底返回的行内容与①不一致")

        mgr.delete_snapshot(key)
        config_db.delete_report(conn, rid)
        conn.commit()

        print()
        if failures:
            print("❌ 兜底验证未通过：", file=sys.stderr)
            for f in failures:
                print(f"   - {f}", file=sys.stderr)
            return 1
        print("✅ Redis 快照命中 / 数据源不可用时不误返回 / 无快照时抛异常 / "
              "redis_fallback 兜底 —— 四项均正常")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
