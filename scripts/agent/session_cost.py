#!/usr/bin/env python3
"""session_cost.py — DSH 会话 token 成本分析器（AGENTS.md 硬性 #20 的自查工具）。

为什么需要它：DSH 会话记录里每条 assistant 消息都带真实 `usage`
（inputTokens / cacheReadTokens / outputTokens）。实测 4 个历史会话（2026-10-06）：

    Σtotal 69.7M tokens，其中 cacheRead 占 98%，output 仅 0.6%。

也就是说 **成本 ≈ 步数 × 上下文规模**：一步塞进历史的东西，后面每一步都要重发一次。
本工具把「哪一步塞了多少、被重发了多少次、因此多花多少 token」直接算出来，
让复盘与自查不靠感觉。

用法（在仓库根执行）：

    venv/bin/python scripts/agent/session_cost.py --list       # 列出本项目会话
    venv/bin/python scripts/agent/session_cost.py --last 1     # 分析最近 1 个会话（收尾自查）
    venv/bin/python scripts/agent/session_cost.py --session <id>
    venv/bin/python scripts/agent/session_cost.py --all        # 汇总本项目全部会话
    venv/bin/python scripts/agent/session_cost.py --selftest   # 纯内存自测（不读磁盘）
    venv/bin/python scripts/agent/session_cost.py --check      # 中途体检：一行结论（步数/上下文/批处理率）

输出只给长度与片段，绝不整贴正文 —— 工具自身即 token 效率示范。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---- 阈值（硬性 #20 / 知识库 10-token-budget.md）--------------------------------
MAX_ADD_TOKENS = 8000      # 单步新增上下文上限（超出即「超阈步」）
MAX_STEPS = 60             # 单会话步数上限（超出建议落盘交接、换会话续做）
MAX_PEAK_TOKENS = 120000   # 单步上下文上限（超出后每步都在为历史付全价）
TOP_N = 6                  # 报告里列出的最贵步数
MAX_ONE_CALL_RATIO = 40    # 单调用步占比上限（%）：碎步是成本主乘数（硬性 #20②）


def project_root() -> Path:
    """仓库根（本文件位于 <root>/scripts/agent/）——禁止硬编码主目录（硬性 #10）。"""
    return Path(__file__).resolve().parents[2]


def session_slug(cwd: str | Path) -> str:
    """把工作目录映射成 DSH 会话目录名：/opdev/SqlReport → --opdev-SqlReport--。"""
    rel = str(Path(cwd).resolve()).strip("/").replace("/", "-")
    return f"--{rel}--"


def session_home() -> Path:
    """DSH 数据目录（可用 DSH_HOME 覆盖）。"""
    return Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))


def iter_sessions(home: Path, cwd: str | Path) -> list[dict[str, Any]]:
    """列出某工作目录下的会话（按修改时间倒序）。"""
    base = home / "sessions" / session_slug(cwd)
    out: list[dict[str, Any]] = []
    if not base.is_dir():
        return out
    for d in base.iterdir():
        blob = d / "session.v4.jsonl.zstd"
        if blob.is_file():
            out.append({"id": d.name, "path": blob, "mtime": blob.stat().st_mtime})
    return sorted(out, key=lambda x: -x["mtime"])


def load_title(home: Path, sid: str) -> str:
    """从 projcache 读会话标题（读不到就返回空串，不报错）。"""
    cache = home / "storages" / "session_projcache" / "sessions"
    for cand in (sid, f"session-{sid}", sid.removeprefix("session-")):
        f = cache / f"{cand}.json"
        if f.is_file():
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))["record"]
                title = rec.get("rows", {}).get("title", {}).get("val")
                if title:
                    return str(title)
            except Exception:
                return ""
    return ""


def load_records(path: Path) -> list[dict[str, Any]]:
    """读会话记录：`.zstd` 用 zstd CLI 解压（本机无 python zstandard 模块）。"""
    if str(path).endswith(".zstd"):
        raw = subprocess.run(["zstd", "-dc", str(path)],
                             capture_output=True, check=True).stdout.decode("utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    return [json.loads(ln) for ln in raw.splitlines() if ln.strip()]


def _text_of(content: Any) -> str:
    """把消息 content 里的 text 段拼起来（忽略 reasoning/tool-call 段）。"""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text") or "" for p in (content or [])
                     if isinstance(p, dict) and p.get("type") == "text")


def _ctx(u: dict[str, Any]) -> int:
    """一次请求的上下文规模 = input + cacheRead + cacheWrite。"""
    return (u.get("inputTokens", 0) + u.get("cacheReadTokens", 0)
            + u.get("cacheWriteTokens", 0))


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    """把会话记录压成成本摘要（纯函数，便于自测）。"""
    seq: list[dict[str, Any]] = []
    buf: list[tuple[str, str]] = []
    tools: dict[str, dict[str, int]] = {}
    errors: list[dict[str, Any]] = []
    users: list[str] = []
    by_id: dict[str, str] = {}
    dup_counter: dict[str, int] = {}

    for r in records:
        t = r.get("type")
        d = r.get("data") or {}
        if t == "user/message" and (d.get("source") or {}).get("kind") == "user":
            users.append(_text_of(d.get("content")).strip())
        elif t == "tool/call":
            name = str(d.get("name"))
            args = str(d.get("arguments") or "")
            buf.append((name, args))
            by_id[str(d.get("callId"))] = name
            tools.setdefault(name, {"n": 0, "chars": 0, "err": 0})["n"] += 1
            key = f"{name}|{args[:400]}"
            dup_counter[key] = dup_counter.get(key, 0) + 1
        elif t == "tool/result":
            m = d.get("message") or {}
            txt = _text_of(m.get("content"))
            cid = m.get("toolCallId") or (m.get("source") or {}).get("callId")
            name = by_id.get(str(cid), "?")
            tools.setdefault(name, {"n": 0, "chars": 0, "err": 0})["chars"] += len(txt)
            if m.get("isError"):
                tools[name]["err"] += 1
                errors.append({"tool": name, "chars": len(txt), "snip": txt[:150]})
            if buf:
                last = buf[-1]
                if last[0] == name:
                    buf[-1] = (name, f"{last[1]}||result_chars={len(txt)}")
        elif t == "assistant/message" and d.get("usage"):
            seq.append({"step": len(seq) + 1, "u": d["usage"], "calls": buf})
            buf = []

    for s in seq:
        s["ctx"] = _ctx(s["u"])
        s["total"] = s["u"].get("totalTokens", 0)
    for i, s in enumerate(seq):
        s["add"] = (seq[i + 1]["ctx"] - s["ctx"]) if i + 1 < len(seq) else 0

    n = len(seq)
    steps_hist: dict[int, int] = {}
    for s in seq:
        steps_hist[len(s["calls"])] = steps_hist.get(len(s["calls"]), 0) + 1
    total = sum(s["total"] for s in seq)
    peak = seq[-1]["ctx"] if seq else 0
    violations = []
    for s in seq:
        if s["add"] > MAX_ADD_TOKENS:
            violations.append({"kind": "单步新增超阈", "step": s["step"],
                               "value": s["add"], "limit": MAX_ADD_TOKENS,
                               "calls": [c[0] for c in s["calls"]][:4]})
    for s in seq:
        if s["ctx"] > MAX_PEAK_TOKENS:
            violations.append({"kind": "单步上下文超阈", "step": s["step"],
                               "value": s["ctx"], "limit": MAX_PEAK_TOKENS, "calls": []})
            break
    if n > MAX_STEPS:
        violations.append({"kind": "会话步数超阈", "step": n, "value": n,
                           "limit": MAX_STEPS, "calls": []})
    one_call = sum(1 for s in seq if len(s["calls"]) == 1)
    return {
        "steps": n,
        "total": total,
        "input": sum(s["u"].get("inputTokens", 0) for s in seq),
        "cache_read": sum(s["u"].get("cacheReadTokens", 0) for s in seq),
        "cache_write": sum(s["u"].get("cacheWriteTokens", 0) for s in seq),
        "output": sum(s["u"].get("outputTokens", 0) for s in seq),
        "ctx_first": seq[0]["ctx"] if seq else 0,
        "ctx_last": peak,
        "calls_hist": steps_hist,
        "calls_total": sum(len(s["calls"]) for s in seq),
        "top_add": sorted(seq, key=lambda x: -x["add"])[:TOP_N],
        "top_total": sorted(seq, key=lambda x: -x["total"])[:TOP_N],
        "tools": tools,
        "errors": errors,
        "users": users,
        "one_call_steps": one_call,
        "dups": {k: v for k, v in dup_counter.items() if v > 1},
        "violations": violations,
    }


def render(summary: dict[str, Any], label: str) -> str:
    """把摘要渲染成紧凑的简体中文报告。"""
    out: list[str] = []
    s = summary
    n = s["steps"]
    if not n:
        return f"### {label}\n（无 usage 记录）"
    re_send = 100 * s["cache_read"] // max(s["total"], 1)
    out.append(f"### {label}")
    out.append(f"步数={n} Σtotal={s['total']:,} | input={s['input']:,} "
               f"cacheRead={s['cache_read']:,} output={s['output']:,} "
               f"| 重发占比={re_send}%")
    out.append(f"上下文：首步={s['ctx_first']:,} → 末步={s['ctx_last']:,}；"
               f"平均每步≈{s['total'] // n:,} tokens")
    hist = ", ".join(f"{k}调用:{v}步" for k, v in sorted(s["calls_hist"].items()))
    out.append(f"工具调用 {s['calls_total']} 次，批处理分布 {hist}")
    one = s.get("one_call_steps", 0)
    out.append(f"批处理率：单调用步 {one}/{n} = {100 * one // max(n, 1)}%"
               f"（#20② 目标 ≤{MAX_ONE_CALL_RATIO}%；一步 2–4 个互不依赖调用最省）")
    if s["users"]:
        out.append("人类消息：" + " ／ ".join(u[:60].replace("\n", " ") for u in s["users"][:4]))
    out.append("")
    out.append(f"最贵步（重发成本 = 该步新增 × 剩余步数）：")
    for st in s["top_add"]:
        rem = n - st["step"]
        names = "; ".join(c[0] for c in st["calls"])[:60] or "（纯输出）"
        out.append(f"- 第{st['step']}步：新增 {st['add']:,} tokens × 剩 {rem} 步 "
                   f"≈ {st['add'] * rem:,} tokens ── {names}")
    out.append("")
    out.append("工具返回体积 / 错误：")
    for name, v in sorted(s["tools"].items(), key=lambda kv: -kv[1]["chars"]):
        out.append(f"- {name}: {v['n']} 次，返回 {v['chars']:,} 字符，错误 {v['err']}")
    if s["errors"]:
        out.append("错误返回：")
        for e in s["errors"][:5]:
            out.append(f"- {e['tool']}（{e['chars']} 字符）: {e['snip'][:120]!r}")
    if s["dups"]:
        out.append("重复调用（同工具同参数）：")
        for k, v in sorted(s["dups"].items(), key=lambda kv: -kv[1])[:5]:
            out.append(f"- ×{v} {k[:90]}")
    out.append("")
    if s["violations"]:
        out.append("预算体检：**超标**（阈值见 10-token-budget.md）")
        for v in s["violations"][:6]:
            extra = f" calls={v['calls']}" if v.get("calls") else ""
            out.append(f"- {v['kind']}：第{v['step']}步 实测 {v['value']:,} > 上限 {v['limit']:,}{extra}")
        out.append(f"- 建议：返回体积先收窄（grep -c / head / read offset），"
                   f"独立调用同步发，> {MAX_STEPS} 步落盘交接换会话")
    else:
        out.append("预算体检：通过（无单步超阈、步数与上下文均在阈值内）")
    return "\n".join(out)


def check(summary: dict[str, Any]) -> int:
    """中途体检：只打一行结论（约 60 字符），供会话中途随时自查（硬性 #20③）。"""
    n = summary["steps"]
    if not n:
        print("CHECK 无 usage 记录 → 无法体检")
        return 0
    one = summary.get("one_call_steps", 0)
    ratio = 100 * one // max(n, 1)
    over_steps = n > MAX_STEPS
    over_ctx = summary["ctx_last"] > MAX_PEAK_TOKENS
    over_batch = ratio > MAX_ONE_CALL_RATIO
    if over_steps or over_ctx:
        verdict = "必须落盘交接并换会话"
    elif over_batch:
        verdict = "先收窄返回体积 / 提高批处理"
    else:
        verdict = "续做"
    print(f"CHECK 步数={n} ctx={summary['ctx_last']:,} 单调用步={ratio}% "
          f"超阈步={sum(1 for v in summary['violations'] if v['kind'] == '单步新增超阈')} "
          f"→ {verdict}")
    return 1 if (over_steps or over_ctx or over_batch) else 0


def _check(args: Any) -> int:
    """`--check`：体检指定/最近会话，只输出一行（供中途自查，成本约 60 字符）。"""
    home = Path(args.home) if args.home else session_home()
    cwd = Path(args.cwd) if args.cwd else project_root()
    if args.file:
        return check(analyze(load_records(Path(args.file))))
    sessions = iter_sessions(home, cwd)
    if args.session:
        hit = [s for s in sessions
               if s["id"].lstrip("session-").startswith(args.session.lstrip("session-"))]
        sessions = hit or sessions
    if not sessions:
        print(f"未找到会话：{home / 'sessions' / session_slug(cwd)}")
        return 1
    return check(analyze(load_records(sessions[0]["path"])))


def _selftest() -> int:
    """纯内存自测：构造合成会话，断言成本模型与体检判定。"""
    def usage(inp: int, cr: int, out_: int) -> dict[str, int]:
        return {"inputTokens": inp, "cacheReadTokens": cr, "outputTokens": out_,
                "cacheWriteTokens": 0, "totalTokens": inp + cr + out_}

    recs: list[dict[str, Any]] = [
        {"type": "session", "data": {}},
        {"type": "user/message", "data": {"source": {"kind": "user"},
                                          "content": [{"type": "text", "text": "任务"}]}},
        {"type": "tool/call", "data": {"callId": "c1", "name": "bash", "arguments": "{}"}},
        {"type": "tool/result", "data": {"message": {"toolCallId": "c1", "isError": False,
                                                     "content": [{"type": "text",
                                                                  "text": "x" * 4000}]}}},
        {"type": "assistant/message", "data": {"usage": usage(1000, 9000, 100)}},
        {"type": "tool/call", "data": {"callId": "c2", "name": "read", "arguments": "{}"}},
        {"type": "tool/result", "data": {"message": {"toolCallId": "c2", "isError": True,
                                                     "content": [{"type": "text",
                                                                  "text": "boom"}]}}},
        {"type": "assistant/message", "data": {"usage": usage(50, 80000, 200)}},
        {"type": "assistant/message", "data": {"usage": usage(50, 200000, 300)}},
    ]
    s = analyze(recs)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = check(s)
    check_line = buf.getvalue().strip()
    checks = [
        ("步数", s["steps"], 3),
        ("Σtotal", s["total"], 1000 + 9000 + 100 + 50 + 80000 + 200 + 50 + 200000 + 300),
        ("首步上下文", s["ctx_first"], 10000),
        ("末步上下文", s["ctx_last"], 200050),
        ("单步最大新增", s["top_add"][0]["add"], 200050 - 80050),
        ("工具计数", s["tools"]["bash"]["n"], 1),
        ("读取的 tool/result 命中调用方", s["tools"]["read"]["err"], 1),
        ("错误条数", len(s["errors"]), 1),
        ("超阈步数（新增 >8000 的上限判定）",
         len([v for v in s["violations"] if v["kind"] == "单步新增超阈"]), 2),
        ("超阈步上下文判定",
         len([v for v in s["violations"] if v["kind"] == "单步上下文超阈"]), 1),
        ("中途体检退出码（末步 200k 上下文 → 判超标）", rc, 1),
        ("中途体检输出为单行", len(check_line.splitlines()), 1),
        ("单调用步数", s["one_call_steps"], 2),
    ]
    bad = [(name, got, want) for name, got, want in checks if got != want]
    if bad:
        for name, got, want in bad:
            print(f"[FAIL] {name}: got={got} want={want}")
        return 1
    print(f"[OK] selftest 通过（{len(checks)} 项断言）；"
          f"合成会话 Σtotal={s['total']:,} tokens")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(description="DSH 会话 token 成本分析器（硬性 #20 自查）")
    ap.add_argument("--list", action="store_true", help="列出本项目会话")
    ap.add_argument("--last", type=int, metavar="N", help="分析最近 N 个会话")
    ap.add_argument("--all", action="store_true", help="分析本项目全部会话")
    ap.add_argument("--session", metavar="ID", help="按会话 id（前缀匹配）分析")
    ap.add_argument("--file", metavar="PATH", help="直接分析已解压的 .jsonl")
    ap.add_argument("--cwd", metavar="DIR", help="目标工作目录（默认仓库根）")
    ap.add_argument("--home", metavar="DIR", help="DSH 数据目录（默认 $DSH_HOME 或 ~/.dsh）")
    ap.add_argument("--selftest", action="store_true", help="跑纯内存自测")
    ap.add_argument("--check", action="store_true",
                    help="中途体检：只输出一行（步数/上下文/批处理率）")
    args = ap.parse_args(argv)

    if args.check:
        return _check(args)

    if args.selftest:
        return _selftest()

    home = Path(args.home) if args.home else session_home()
    cwd = Path(args.cwd) if args.cwd else project_root()

    if args.file:
        path = Path(args.file)
        return _report(load_records(path), str(path))

    sessions = iter_sessions(home, cwd)
    if not sessions:
        print(f"未找到会话：{home / 'sessions' / session_slug(cwd)}")
        return 1
    if args.list:
        for s in sessions:
            title = load_title(home, s["id"]) or "（无标题）"
            print(f"{s['id']}  {title}")
        return 0

    picked = sessions
    if args.session:
        picked = [s for s in sessions if s["id"].lstrip("session-").startswith(
            args.session.lstrip("session-"))]
        if not picked:
            print(f"未找到会话 {args.session}")
            return 1
    elif args.last:
        picked = sessions[:args.last]
    elif not args.all:
        picked = sessions[:1]

    rc = 0
    grand = 0
    for s in picked:
        recs = load_records(s["path"])
        title = load_title(home, s["id"]) or s["id"]
        summary = analyze(recs)
        grand += summary["total"]
        rc |= _report(summary, f"{s['id'][:20]}… {title}")
        print()
    if len(picked) > 1:
        print(f"合计 {len(picked)} 个会话：Σtotal={grand:,} tokens")
    return rc


def _report(summary: dict[str, Any], label: str) -> int:
    """打印一个会话的报告，返回进程退出码（有超阈即 1，便于 CI）。"""
    print(render(summary, label))
    return 1 if summary["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
