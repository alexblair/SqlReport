"""manual_write_gate_regression.py — 写判定分工的真实报表回归（手工运行，不进 discover）

对齐 `tests/manual_cache_scenarios.py` 惯例：`manual_` 前缀不被 `unittest discover`
收集，需显式运行：

    venv/bin/python tests/manual_write_gate_regression.py

用途：对配置库中**全部报表**比对 `sql_contains_write`（旧，从严）与
`sql_has_persistent_write`（新，缓存门槛）的判定，验证 spec §6 的安全属性：

1. **反向误判为 0** —— 没有任何一个「旧判定为读」的报表被新判定锁掉缓存
   （这是本设计最重要的安全证据）；
2. 净解封集合恰为预期（本次为 {17, 19, 35}）；
3. `#37` 这类真持久写报表在新判定下仍为 True（必须继续跳过缓存）。

只读：全程 `SET SESSION TRANSACTION READ ONLY` + `START TRANSACTION READ ONLY`，
不执行任何报表 SQL，不做任何写操作。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mysql.connector  # noqa: E402

from query_executor import (  # noqa: E402
    sql_contains_write,
    sql_has_persistent_write,
)

# 本次（2026-09-30）预期净解封的报表；配置库若新增/改动报表，此集合需同步更新。
EXPECTED_UNBLOCKED = {17, 19, 35}
# 真持久写样本：必须继续被挡住，且新旧判定都应为 True。
PERSISTENT_SAMPLES = {37}

# 独立复算用到的读白名单（**刻意不复用产品常量**，以保留交叉验证的独立性）。
_READ_KEYWORDS = frozenset({"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"})
# WITH 语句里需要扫描的写动词（不含 SET，且「紧跟 (」的是函数调用）
_WITH_VERBS = frozenset({
    "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "CALL", "GRANT", "REVOKE",
})


def independent_session_only(sql):
    """独立复算：该脚本是否每条语句都属于「读 / CREATE|DROP 次关键词 TEMPORARY / SET @用户变量」。

    与产品实现分开写（规则独立重组），用于守住**安全方向**：
    只检查「读报表别被锁缓存」是不够的——**真写被放行并由缓存短路**才是更危险的
    失败模式（复核 C-1 正是从这个缺口漏出的）。
    返回 None 表示全部会话级；否则返回第一处可疑语句的前 70 字符。
    """
    from query_executor import (
        _iter_sql_keywords_with_pos, _skip_ws_and_comments,
        _split_sql_statements)
    for st in _split_sql_statements(sql):
        kws = list(_iter_sql_keywords_with_pos(st))
        if not kws:
            continue
        first, first_end = kws[0]
        if first in _READ_KEYWORDS:
            continue
        if first in ("CREATE", "DROP") and len(kws) > 1 \
                and kws[1][0] == "TEMPORARY":
            continue
        if first == "SET":
            k = _skip_ws_and_comments(st, first_end)
            is_user_var = (k + 1 < len(st) and st[k] == "@"
                           and st[k + 1] != "@" and not st[k + 1].isspace())
            if is_user_var and not any(
                    kw in ("GLOBAL", "PERSIST", "SESSION", "NAMES")
                    for kw, _ in kws):
                continue
        if first == "WITH":
            hit = False
            for kw, end in kws[1:]:
                if kw not in _WITH_VERBS:
                    continue
                k = _skip_ws_and_comments(st, end)
                if k >= len(st) or st[k] != "(":
                    hit = True
                    break
            if not hit:
                continue
        return st.strip()[:70]
    return None


def _enabled_config_db():
    with open("app_config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    for entry in cfg.get("config_db", []):
        if entry.get("enable"):
            return entry
    raise RuntimeError("app_config.json 中没有启用的 config_db 条目")


def main() -> int:
    entry = _enabled_config_db()
    conn = mysql.connector.connect(
        host=entry["host"], port=int(entry["port"]), user=entry["user"],
        password=entry["password"], database=entry["database"],
        connection_timeout=10)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute("START TRANSACTION READ ONLY")
        cur.execute("SELECT id, name, sql_query FROM report_configs ORDER BY id")
        reports = cur.fetchall()
        conn.rollback()
        cur.close()
    finally:
        conn.close()

    unblocked, reverse_misclassified, persistent = [], [], []
    print(f"{'id':>4} {'旧判定':>6} {'新判定':>6}  结论        报表名")
    print("-" * 82)
    for r in reports:
        old = sql_contains_write(r["sql_query"])
        new = sql_has_persistent_write(r["sql_query"])
        if old and not new:
            verdict = "✅ 解封"
            unblocked.append(r["id"])
        elif not old and new:
            verdict = "❌ 反向误判"
            reverse_misclassified.append(r["id"])
        elif old and new:
            verdict = "➖ 保持拦截"
            persistent.append(r["id"])
        else:
            verdict = "➖ 正常"
        print(f"{r['id']:>4} {str(old):>6} {str(new):>6}  {verdict:<10}  {r['name'][:38]}")

    print()
    print(f"报表总数            : {len(reports)}")
    print(f"净解封             : {sorted(unblocked)}")
    print(f"反向误判           : {sorted(reverse_misclassified)}")
    print(f"保持拦截（持久写） : {sorted(persistent)}")

    ok = True
    if reverse_misclassified:
        print(f"FAIL: 反向误判非空 → {sorted(reverse_misclassified)}")
        ok = False
    if set(unblocked) != EXPECTED_UNBLOCKED:
        print(f"FAIL: 净解封集合 {sorted(unblocked)} != 预期 "
              f"{sorted(EXPECTED_UNBLOCKED)}（配置库有变则同步更新 EXPECTED_UNBLOCKED）")
        ok = False
    for rid in PERSISTENT_SAMPLES:
        row = next((r for r in reports if r["id"] == rid), None)
        if row is None:
            print(f"FAIL: 持久写样本 #{rid} 不存在")
            ok = False
        elif not (sql_contains_write(row["sql_query"])
                  and sql_has_persistent_write(row["sql_query"])):
            print(f"FAIL: 持久写样本 #{rid} 未被挡住（缓存将短路它的写）")
            ok = False

    # 安全方向交叉验证：每个被解封的报表，其 SQL 必须能被独立复算证明无持久写
    suspects = 0
    for rid in sorted(unblocked):
        row = next((r for r in reports if r["id"] == rid), None)
        suspect = independent_session_only(row["sql_query"]) if row else None
        if suspect is not None:
            print(f"FAIL: 解封报表 #{rid} 存在疑似持久写语句 → {suspect}")
            suspects += 1
    print(f"解封报表安全方向交叉复算：{len(unblocked)} 个报表，"
          f"疑似持久写 {suspects} 条")
    if suspects:
        ok = False

    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
