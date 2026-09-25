# -*- coding: utf-8 -*-
"""缓存四场景手工验证脚本 —— 正式单测的蓝本（不参与 discover）。

场景1  Redis 失效时的查询（静默降级直查数据源）
场景2  Redis 有效时的查询（写回 + 二次请求命中 L2）
场景3  Redis 有效、数据源失效（兑底读过期快照 redis_fallback）
场景4  写 SQL + allow_write（本地 sqlite3 替身代替 MySQL 执行，
       验证写执行与 Redis 快照更新 / 护栏拒绝）

设计与实测记录：docs/compose/spec/cache-write-test-scenarios.md

运行前置：
  1) 测试 Redis：redis-server --port 6390 --bind 127.0.0.1 --daemonize yes \\
       --dir <临时目录> （独立实例，不触碰 6379）
  2) venv/bin/python tests/manual_cache_scenarios.py

替身说明：报表执行层只支持 MySQL（report.execute_report →
db.create_mysql_connection）。本脚本将 db.create_mysql_connection 打补丁为
本地 sqlite3 连接包装（接口兼容 execute_mysql_query 所需 begin/cursor/
commit/rollback/close 子集），使写 SQL 落在临时库文件而非 MySQL。
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 临时目录（只建不删，便于事后取证）
WORK = tempfile.mkdtemp(prefix="sr-cache-sc-")
SQLITE_PATH = os.path.join(WORK, "data.db")
CFG_UP = os.path.join(WORK, "redis_up.json")
CFG_DOWN = os.path.join(WORK, "redis_down.json")

# ---- 配置（在导入 report/redis_cache 之前落盘，供 app_config 兜底读取）----
_BASE_CFG = {
    "scheduler": {"enable": False, "tick_seconds": 10},
    "log": {"enable": False},
    "redis": {"enable": True, "host": "127.0.0.1", "db": 0, "password": "",
              "key_prefix": "srsc", "default_ttl_hours": 1,
              "socket_timeout": 3},
}
_cfg_up = dict(_BASE_CFG, redis=dict(_BASE_CFG["redis"], port=6390))
_cfg_down = dict(_BASE_CFG, redis=dict(_BASE_CFG["redis"], port=6391))
for _p, _c in ((CFG_UP, _cfg_up), (CFG_DOWN, _cfg_down)):
    with open(_p, "w", encoding="utf-8") as _f:
        json.dump(_c, _f, ensure_ascii=False)
os.environ["DEBUG_CONFIG_FILE"] = CFG_UP
os.environ.pop("CONFIG_FILE", None)

import app_config          # noqa: E402
import redis_cache         # noqa: E402
import db                  # noqa: E402
import report              # noqa: E402

READ_SQL = "SELECT id, customer, amount, status FROM orders ORDER BY id"
WRITE_SQL = ("UPDATE orders SET status = 'done' WHERE id = 1; "
             "SELECT id, customer, status FROM orders WHERE id = 1")
REDIS_UP = {"enable": True, "host": "127.0.0.1", "port": 6390, "db": 0,
            "password": "", "key_prefix": "srsc", "default_ttl_hours": 1,
            "socket_timeout": 3}
REDIS_DOWN = dict(REDIS_UP, port=6391)   # 无人监听 = Redis 失效

FAILS: list[str] = []


def check(cond, label, evidence=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(label)
    print(f"  [{mark}] {label}" + (f" | {evidence}" if evidence else ""))


# ---- 本地 sqlite3 替身（代替 MySQL 连接）------------------------------
class _ShimCursor:
    """按 _POOL_FAIL["at"] 注入失败：execute=查询期失败（文档承诺兜底路径），
    create=连接建立期失败（已知缺口：不走兜底，见场景3c）。"""

    def __init__(self, real):
        self._real = real

    def execute(self, *args, **kwargs):
        if _POOL_FAIL["at"] == "execute":
            raise sqlite3.OperationalError("模拟查询执行失败: MySQL server has gone away")
        return self._real.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _SqliteMysqlShim:
    """接口兼容 execute_mysql_query 所需的 MySQL 连接子集。"""

    def __init__(self, path):
        # isolation_level=None：事务由显式 BEGIN/COMMIT 控制，行为与 MySQL 一致
        self._conn = sqlite3.connect(path, isolation_level=None)

    def cursor(self):
        return _ShimCursor(self._conn.cursor())

    def begin(self):
        try:
            self._conn.execute("BEGIN")
        except sqlite3.OperationalError:
            pass  # 已在事务中

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


_POOL_FAIL = {"at": "none"}   # none | execute | create
_DB_HITS = {"n": 0}
_CUR_DB = {"path": None}      # 当前场景数据源；None = 场景1/2/4 的 orders 库


def _fake_create(pool_config, read_timeout=None, **kw):
    _DB_HITS["n"] += 1
    if _POOL_FAIL["at"] == "create":
        raise sqlite3.OperationalError(
            "模拟连接建立失败: Can't connect to MySQL server (Errno 111)")
    return _SqliteMysqlShim(_CUR_DB["path"] or SQLITE_PATH)


def setup_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.executescript("""
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT,
                             amount REAL, status TEXT);
        INSERT INTO orders VALUES (1,'Alice',100.0,'pending'),
                                  (2,'Bob',250.0,'pending'),
                                  (3,'Carol',80.0,'pending');
    """)
    conn.commit()
    conn.close()


def sqlite_status(order_id=1):
    conn = sqlite3.connect(SQLITE_PATH)
    row = conn.execute("SELECT status FROM orders WHERE id=?",
                       (order_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def set_sqlite_status(order_id, status):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()


def use_redis(cfg):
    """切换全局 Redis 管理器（reset_redis_manager 为现成测试钩子）。"""
    redis_cache.reset_redis_manager(cfg)


def fresh_cache():
    return report.QueryCache(ttl=300)


def base_report(sql, allow_write=0, prefer_cache=1, rid_hint=None):
    return {
        "id": rid_hint, "name": "场景用报表", "sql_query": sql,
        "pool_id": 1, "prefer_cache": prefer_cache,
        "cache_ttl_hours": 1, "allow_write": allow_write,
        "allow_all_output": 1, "max_rows": 0,
    }


def run_exec(rid, rep, cache, refresh=False, force=False):
    return report.execute_report(
        report_id=rid, sql_query=rep["sql_query"],
        pool_config={"name": "fake-sqlite"}, page=1, page_size=20,
        report=rep, cache=cache, refresh=refresh, force_rebuild=force,
    )


def snap_key(rid, sql, pool_id=1):
    ver = redis_cache.compute_config_version(sql, pool_id)
    return redis_cache.build_snapshot_key("srsc", rid, ver)


# ---- 场景1：Redis 失效时的查询 ----------------------------------------
def scenario_1():
    print("场景1 Redis 失效时的查询")
    use_redis(REDIS_DOWN)
    check(not redis_cache.redis_available(), "redis_available=False",
          f"manager.available={redis_cache.get_redis_manager().available}")
    rep = base_report(READ_SQL, rid_hint=9901)
    cache = fresh_cache()
    _DB_HITS["n"] = 0
    rr = run_exec(9901, rep, cache)
    check(len(rr.results[0]["rows"]) == 3, "查询成功返回3行",
          f"rows={len(rr.results[0]['rows'])} cache_info={rr.cache_info}")
    check(rr.cache_info and rr.cache_info.get("source") == "mysql",
          "来源=直查数据源(降级标签mysql)", str(rr.cache_info))
    check(_DB_HITS["n"] == 1, "数据源被真实访问1次", f"hits={_DB_HITS['n']}")
    rr2 = run_exec(9901, rep, cache)
    check(rr2.cache_info and rr2.cache_info.get("source") == "process",
          "二次请求L1进程缓存命中", str(rr2.cache_info))


# ---- 场景2：Redis 有效时的查询 ----------------------------------------
def scenario_2():
    print("场景2 Redis 有效时的查询")
    use_redis(REDIS_UP)
    check(redis_cache.redis_available(), "redis_available=True")
    rep = base_report(READ_SQL, rid_hint=9902)
    key = snap_key(9902, READ_SQL)
    mgr = redis_cache.get_redis_manager()
    mgr.client.delete(key)          # 冷启动
    cache = fresh_cache()
    _DB_HITS["n"] = 0
    rr = run_exec(9902, rep, cache)
    check(rr.cache_info and rr.cache_info.get("source") == "redis",
          "首查执行数据源并写回Redis", str(rr.cache_info))
    check(_DB_HITS["n"] == 1, "首查数据源执行1次", f"hits={_DB_HITS['n']}")
    snap = mgr.get_snapshot(key)
    check(snap is not None and len(snap.results[0]["rows"]) == 3,
          "Redis快照已落盘", f"rows={len(snap.results[0]['rows']) if snap else 0}")
    # 二次：全新 L1 + 数据源封死（若访问数据源会抛错）→ 必须纯 Redis 命中
    _POOL_FAIL["at"] = "create"
    try:
        rr2 = run_exec(9902, rep, fresh_cache())
        check(rr2.cache_info and rr2.cache_info.get("source") == "redis"
              and rr2.cache_info.get("fresh") is True,
              "二次请求纯命中L2(未触数据源)", str(rr2.cache_info))
        check(len(rr2.results[0]["rows"]) == 3, "二次结果3行一致")
    finally:
        _POOL_FAIL["at"] = "none"


# ---- 场景3：Redis 有效、数据源自发失效（debug 配置 sqlite3）→ 兜底 ------
def scenario_3():
    print("场景3 Redis 有效 + debug配置sqlite3失效 → 正常读取 Redis")
    # 数据源 = debug 配置（app_config.debug.json → config.debug.db）的副本：
    # 只读复制、不碰原库；「失效」用真实文件级故障（移走文件），不注入代码异常。
    debug_src = os.path.join(ROOT, "config.debug.db")
    debug_copy = os.path.join(WORK, "debug_sqlite.db")
    shutil.copyfile(debug_src, debug_copy)
    _CUR_DB["path"] = debug_copy
    debug_sql = "SELECT id, name FROM report_configs ORDER BY id"
    rep = base_report(debug_sql, rid_hint=9903)
    key = snap_key(9903, debug_sql)
    use_redis(REDIS_UP)
    mgr = redis_cache.get_redis_manager()
    mgr.client.delete(key)
    try:
        # 前置：数据源完好时冷查一次 → 建立 Redis 热快照
        rr0 = run_exec(9903, rep, fresh_cache())
        check(rr0.cache_info and rr0.cache_info.get("source") == "redis",
              "前置：冷查建立Redis热快照", str(rr0.cache_info))
        n_rows = len(rr0.results[0]["rows"])
        check(n_rows > 0, "前置：debug库副本可查出报表配置", f"rows={n_rows}")

        # 真实制造数据源失效：移走副本（原 config.debug.db 不受影响）
        os.replace(debug_copy, debug_copy + ".moved")
        check(not os.path.exists(debug_copy), "数据源文件已移走(真实失效)")

        # 3a 常规请求：L2 命中直接返回，数据源零触碰 → 失效完全无感
        _DB_HITS["n"] = 0
        rr = run_exec(9903, rep, fresh_cache())
        check(rr.cache_info and rr.cache_info.get("source") == "redis",
              "3a 常规请求纯命中Redis", str(rr.cache_info))
        check(_DB_HITS["n"] == 0, "3a 数据源零访问(失效无感)",
              f"hits={_DB_HITS['n']}")
        check(len(rr.results[0]["rows"]) == n_rows, "3a 行数与快照一致",
              f"rows={len(rr.results[0]['rows'])}")

        # 3b force_rebuild：真实查库（connect 重建空文件 → 查表失败=查询期
        #    异常）→ 文档承诺的过期快照兜底 redis_fallback
        rr2 = run_exec(9903, rep, fresh_cache(), force=True)
        check(rr2.cache_info and rr2.cache_info.get("source") == "redis_fallback",
              "3b 真实查询失败→redis_fallback兜底", str(rr2.cache_info))
        check(rr2.cache_info.get("fresh") is False, "3b 兜底快照标记stale")
        check(len(rr2.results[0]["rows"]) == n_rows, "3b 兜底行数与快照一致")
        check(_DB_HITS["n"] == 1, "3b 真实尝试访问数据源1次",
              f"hits={_DB_HITS['n']}")

        # 3c 连接建立期失败（同名目录占位 → connect 打不开）：与查询期失败
        #    同等对待，应走文档承诺的过期快照兜底（缺口修复后断言）。
        if os.path.exists(debug_copy):
            os.remove(debug_copy)     # 3b 查询失败后 connect 会重建空文件
        os.mkdir(debug_copy)
        rr3 = run_exec(9903, rep, fresh_cache(), force=True)
        check(rr3.cache_info and rr3.cache_info.get("source") == "redis_fallback",
              "3c 连接期失败同样走redis_fallback兜底", str(rr3.cache_info))
        check(rr3.cache_info.get("fresh") is False, "3c 兜底快照标记stale")
        check(len(rr3.results[0]["rows"]) == n_rows, "3c 兜底行数与快照一致")
    except Exception as e:           # noqa: BLE001
        check(False, "数据源失效仍可读Redis", repr(e))
    finally:
        _POOL_FAIL["at"] = "none"
        _CUR_DB["path"] = None       # 场景4回到 orders 库


# ---- 场景4：写 SQL + allow_write + Redis 缓存更新 ----------------------
def scenario_4():
    print("场景4 写SQL(allow_write) 执行与 Redis 缓存更新")
    use_redis(REDIS_UP)
    write_rep = base_report(WRITE_SQL, allow_write=1, rid_hint=9904)
    key = snap_key(9904, WRITE_SQL)
    mgr = redis_cache.get_redis_manager()
    mgr.client.delete(key)
    set_sqlite_status(1, "pending")

    # 4a 冷启动执行写：UPDATE 落库 + 快照写入写后结果
    rr = run_exec(9904, write_rep, fresh_cache())
    check(sqlite_status(1) == "done", "4a UPDATE真实执行落库",
          f"sqlite status={sqlite_status(1)}")
    check(rr.cache_info and rr.cache_info.get("source") == "redis",
          "4a 写后结果回写Redis", str(rr.cache_info))
    snap = mgr.get_snapshot(key)
    got = snap.results[0]["rows"][0] if snap else None
    check(got is not None and got[2] == "done",
          "4a Redis快照含写后新值", f"snapshot_row={got}")
    check(rr.results[0]["rows"][0][2] == "done", "4a 本次返回写后结果")

    # 4b 热快照行为固化：二次执行命中缓存、不再触发写（观测记录，非缺陷判定）
    set_sqlite_status(1, "pending")             # 人为还原库值作对照
    rr2 = run_exec(9904, write_rep, fresh_cache())
    check(rr2.cache_info and rr2.cache_info.get("source") == "redis",
          "4b 二次请求命中快照", str(rr2.cache_info))
    check(sqlite_status(1) == "pending",
          "4b 热快照下写语句未再执行(设计行为，靠prefer_cache控制)",
          f"sqlite status={sqlite_status(1)}")

    # 4c refresh=True（页面「刷新缓存」语义）：先失效再执行写 → 快照更新
    rr3 = run_exec(9904, write_rep, fresh_cache(), refresh=True)
    check(sqlite_status(1) == "done", "4c refresh路径写语句重新执行",
          f"sqlite status={sqlite_status(1)}")
    snap = mgr.get_snapshot(key)
    got3 = snap.results[0]["rows"][0] if snap else None
    check(got3 is not None and got3[2] == "done", "4c 快照再次更新为写后值",
          f"snapshot_row={got3}")

    # 4d 负向护栏：allow_write=0 → 拒绝执行
    set_sqlite_status(1, "pending")
    deny = base_report(WRITE_SQL, allow_write=0, rid_hint=9905)
    try:
        run_exec(9905, deny, fresh_cache())
        check(False, "4d 未开启允许写入应拒绝")
    except PermissionError as e:
        check(str(e) == report.WRITE_DENIED_MESSAGE, "4d 护栏拒绝且文案一致",
              str(e))
        check(sqlite_status(1) == "pending", "4d 库数据未被改动",
              f"sqlite status={sqlite_status(1)}")


def main():
    # 打补丁：db.create_mysql_connection → 本地 sqlite3 替身
    db.create_mysql_connection = _fake_create
    setup_sqlite()
    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
    print("=" * 60)
    if FAILS:
        print(f"总计 FAIL={len(FAILS)}: {FAILS}")
        return 1
    print("四场景全部 PASS")
    print(f"取证目录(不删除): {WORK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
