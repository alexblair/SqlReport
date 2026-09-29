#!/usr/bin/env python3
"""
bench.py — 执行层端到端 HTTP 压测

前提：
    1. 已跑 scripts/perf/seed_perf_data.py  （MySQL 性能数据）
    2. 已跑 scripts/perf/init_debug_env.py  （配置库 + 报表 + 基准账号 + API 端点）
    3. DEBUG 服务已在 127.0.0.1:1000 启动

每个场景：1 次预热（不计入，单独记录冷路径耗时）+ 20 次正式请求，取 P50/P95。

除计时外还做一件更重要的事——**断言 cache_info.source 分布**：
    S1（P1，prefer_cache=0）：预热必须是 mysql，正式请求必须是 process
    S5（P4，prefer_cache=1）：预热与正式请求都必须是 redis
这比任何单测都更早发现 Redis 链路被破坏。

用法：
    source venv/bin/activate
    python scripts/perf/bench.py --out perf-logs/baseline.json
"""

import argparse
import http.cookiejar
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

CRED_FILE = _REPO_ROOT / "perf-logs" / "bench-credentials.txt"
WARMUP = 1
SAMPLES = 20
TIMEOUT = 180

# cache_info.source → 页面 cache-badge 文案（render.build_cache_badge_html）
_BADGE_PATTERNS = [
    ("redis_fallback", "数据库不可用"),
    ("redis", "缓存快照"),
    ("process", "本地缓存"),
    ("mysql", "实时查询"),
]


def read_credentials() -> dict:
    """从 perf-logs/bench-credentials.txt 读基准账号与 API 凭据。"""
    if not CRED_FILE.exists():
        sys.exit(f"缺少凭据文件 {CRED_FILE.relative_to(_REPO_ROOT)}；"
                 f"请先跑 scripts/perf/init_debug_env.py")
    kv = {}
    for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    for required in ("user", "pass", "api_path", "api_key"):
        if required not in kv:
            sys.exit(f"凭据文件缺 {required} 键；请重跑 scripts/perf/init_debug_env.py")
    return kv


def load_report_ids() -> dict:
    """按名称从配置库读报表 ID，避免脚本里硬编码会变的 id。"""
    import config_db
    conn = config_db.get_config_db()
    try:
        by_name = {r["name"]: r["id"] for r in config_db.get_all_reports(conn)}
    finally:
        conn.close()
    wanted = {
        "P1": "P1-文本Decimal",
        "P2": "P2-宽表30列",
        "P3": "P3-多结果集",
        "P4": "P4-Redis路径",
    }
    missing = [n for n in wanted.values() if n not in by_name]
    if missing:
        sys.exit(f"配置库缺少报表 {missing}；请重跑 scripts/perf/init_debug_env.py")
    return {k: by_name[v] for k, v in wanted.items()}


class Session:
    """带 Cookie 的极简 HTTP 客户端（纯标准库）。"""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, path: str, *, data: bytes = None,
                headers: dict = None) -> tuple[int, str]:
        url = self.base + path
        req = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def login(self, username: str, password: str) -> None:
        body = urllib.parse.urlencode(
            {"username": username, "password": password, "next": "/"}
        ).encode()
        status, text = self.request(
            "/login", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if status != 200 or "用户名或密码错误" in text:
            sys.exit(f"登录失败（HTTP {status}）。"
                     f"请检查 perf-logs/bench-credentials.txt 是否与配置库一致。")
        if not any(c.name for c in self.jar):
            sys.exit("登录返回成功但没拿到 session cookie，基准环境异常。")


def parse_cache_source(html: str):
    """从报表页 HTML 里解析 cache_info.source，取不到返回 None。"""
    m = re.search(r'<span class="cache-badge[^"]*">(.*?)</span>', html, re.S)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", "", m.group(1))
    for source, marker in _BADGE_PATTERNS:
        if marker in text:
            return source
    return None


def percentile(values: list[float], p: float) -> float:
    """最近秩百分位（nearest-rank）。"""
    ordered = sorted(values)
    idx = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return ordered[min(idx, len(ordered) - 1)]


def run_scenario(sess: Session, name: str, desc: str,
                 make_path, *, api_key: str = None,
                 check_source: bool = False) -> dict:
    """跑一个场景：预热 + 20 次正式请求，返回统计与 cache_source 分布。"""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    sources, errors = [], []

    def once(path):
        t0 = time.perf_counter()
        status, body = sess.request(path, headers=headers)
        dt = (time.perf_counter() - t0) * 1000.0
        return status, body, dt

    # 预热（不计入统计）
    warm_ms = None
    for _ in range(WARMUP):
        status, body, dt = once(make_path(0))
        if status != 200:
            errors.append(f"预热 HTTP {status}")
        warm_ms = dt
        warm_source = parse_cache_source(body) if check_source else None

    timings = []
    for i in range(SAMPLES):
        status, body, dt = once(make_path(i))
        if status != 200:
            errors.append(f"第 {i + 1} 次 HTTP {status}")
        timings.append(dt)
        if check_source:
            sources.append(parse_cache_source(body))

    dist = {}
    for s in sources:
        dist[s] = dist.get(s, 0) + 1

    result = {
        "desc": desc,
        "warm_ms": round(warm_ms, 2) if warm_ms is not None else None,
        "warm_source": warm_source if check_source else None,
        "p50_ms": round(percentile(timings, 50), 2),
        "p95_ms": round(percentile(timings, 95), 2),
        "min_ms": round(min(timings), 2),
        "max_ms": round(max(timings), 2),
        "mean_ms": round(statistics.fmean(timings), 2),
        "n": len(timings),
        "cache_source_dist": dist,
    }
    print(f"  {name:<4} {desc:<34} 预热{result['warm_ms'] or 0:>8.1f}ms  "
          f"P50 {result['p50_ms']:>8.1f}ms  P95 {result['p95_ms']:>8.1f}ms"
          + (f"  来源{dist}" if dist else ""))
    if errors:
        print(f"       ⚠ 错误 {len(errors)} 次：{errors[:3]}", file=sys.stderr)
    return {"result": result, "errors": errors, "sources": sources,
            "warm_source": warm_source if check_source else None}


def main() -> int:
    parser = argparse.ArgumentParser(description="执行层端到端 HTTP 压测")
    parser.add_argument("--base-url", default="http://127.0.0.1:1000")
    parser.add_argument("--out", required=True, help="结果 JSON 输出路径")
    args = parser.parse_args()

    cred = read_credentials()
    ids = load_report_ids()
    print(f"目标：{args.base_url}  报表 ID：{ids}")

    sess = Session(args.base_url)
    sess.login(cred["user"], cred["pass"])
    print("登录成功\n")

    scenarios = {}

    # S1 报表首屏（P1，prefer_cache=0）—— 冷路径主力
    scenarios["S1"] = run_scenario(
        sess, "S1", "报表首屏 10万行 (prefer_cache=0)",
        lambda i: f"/report?id={ids['P1']}", check_source=True)

    # S2 翻页 —— C-3 派生态缓存主战场
    scenarios["S2"] = run_scenario(
        sess, "S2", "翻页 page=2..21",
        lambda i: f"/report?id={ids['P1']}&page={2 + i}")

    # S3 排序
    scenarios["S3"] = run_scenario(
        sess, "S3", "排序 amount 降序",
        lambda i: f"/report?id={ids['P1']}&sort=amount&dir=desc")

    # S4 数值筛选
    scenarios["S4"] = run_scenario(
        sess, "S4", "数值筛选 amount>100",
        lambda i: f"/report?id={ids['P1']}&f_amount=100&op_amount=gt")

    # S5 Redis 路径（P4，prefer_cache=1）
    scenarios["S5"] = run_scenario(
        sess, "S5", "Redis 快照路径 (prefer_cache=1)",
        lambda i: f"/report?id={ids['P4']}", check_source=True)

    # S6 API（url_path 已含 /api 前缀，见 init_debug_env.py 的说明）
    api_path = cred["api_path"]
    scenarios["S6"] = run_scenario(
        sess, "S6", "API JSON 端点",
        lambda i: api_path, api_key=cred["api_key"])

    # S7 导出 CSV
    scenarios["S7"] = run_scenario(
        sess, "S7", "导出 CSV",
        lambda i: f"/export?id={ids['P1']}&format=csv")

    # S8 配置页
    scenarios["S8"] = run_scenario(
        sess, "S8", "配置页",
        lambda i: "/config")

    # ---- 以下为基线测量后补充的场景 ----
    # S9/S10 是 C-3 派生态缓存的真正主战场：无筛选无排序时 filter_rows/
    # sort_rows 直接早返回，普通翻页没有 transform 成本；只有「已排序/已筛选
    # 的报表再翻页」才会每次重跑全量 transform。
    scenarios["S9"] = run_scenario(
        sess, "S9", "排序后翻页 page=2..21（C-3 主战场）",
        lambda i: f"/report?id={ids['P1']}&sort=amount&dir=desc&page={2 + i}")

    scenarios["S10"] = run_scenario(
        sess, "S10", "筛选后翻页 page=2..21（C-3 主战场）",
        lambda i: f"/report?id={ids['P1']}&f_amount=100&op_amount=gt&page={2 + i}")

    # S11 宽表 30 列（5 万行）
    scenarios["S11"] = run_scenario(
        sess, "S11", "宽表 30 列 × 5万行",
        lambda i: f"/report?id={ids['P2']}")

    # S12 多结果集（一条 SQL 三个结果集）
    scenarios["S12"] = run_scenario(
        sess, "S12", "多结果集（3 个结果集）",
        lambda i: f"/report?id={ids['P3']}")

    # ---- 缓存来源断言（Redis 契约守卫）----
    failures = []
    s1 = scenarios["S1"]
    if s1["warm_source"] != "mysql":
        failures.append(f"S1 预热 cache_source 期望 mysql，实际 {s1['warm_source']}")
    unexpected = {k: v for k, v in s1["result"]["cache_source_dist"].items()
                  if k != "process"}
    if unexpected:
        failures.append(f"S1 正式请求期望全为 process，实际 {unexpected}")
    s5 = scenarios["S5"]
    if s5["warm_source"] != "redis":
        failures.append(f"S5 预热 cache_source 期望 redis，实际 {s5['warm_source']}")
    bad5 = {k: v for k, v in s5["result"]["cache_source_dist"].items() if k != "redis"}
    if bad5:
        failures.append(f"S5 正式请求期望全为 redis，实际 {bad5}")
    for name, sc in scenarios.items():
        if sc["errors"]:
            failures.append(f"{name} 有 {len(sc['errors'])} 次非 200")

    payload = {
        "scenarios": {k: v["result"] for k, v in scenarios.items()},
        "meta": {
            "base_url": args.base_url,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "samples": SAMPLES,
            "warmup": WARMUP,
            "report_ids": ids,
        },
        "assert_failures": failures,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n结果已写入 {out}")

    if failures:
        print("\n❌ 断言未通过：", file=sys.stderr)
        for f in failures:
            print(f"   - {f}", file=sys.stderr)
        redis_broken = any("cache_source" in f for f in failures)
        if redis_broken:
            print("   Redis 缓存链路可能被破坏，请勿继续优化。", file=sys.stderr)
        else:
            print("   属场景/环境问题（非 Redis 链路），修正后再重跑基线。",
                  file=sys.stderr)
        return 1
    print("✅ 全部场景 200 且 cache_info.source 分布符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
