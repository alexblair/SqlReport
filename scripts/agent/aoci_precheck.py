#!/usr/bin/env python3
"""aoci_precheck.py — 改前定向读：一次打出目标文件的 AOCI 认知（F/S）。

为什么需要它（硬性 #21，2026-10-09 设计）：
AOCI 的价值在"**改前**知道这个对象为什么要小心"，但实测 25 小时里语义只被读了 2 次，
因为读一次要走 MCP + 可能拉 17K tokens 的 Whole-Index。本工具把读路径压成**一条命令**：
只解析 `aoci.code.txt` 里目标文件的条目，零 MCP 往返、零工具 schema 税，单次约 1K tokens。

三层边界（别混）：AOCI 回答"改它要小心什么"；`codegraph` 回答"改它还会碰到谁"；
knowledge 分卷回答"按什么流程做"。**不用 AOCI 找符号，不用 codegraph 找约束。**

用法（在仓库根执行）：

    venv/bin/python scripts/agent/aoci_precheck.py report.py render.py
    venv/bin/python scripts/agent/aoci_precheck.py --full docs/compose/knowledge/06-ui-interactions.md
    venv/bin/python scripts/agent/aoci_precheck.py --json scripts/agent/session_cost.py
    venv/bin/python scripts/agent/aoci_precheck.py --selftest        # 纯内存自测

输出末行恒为机器可读结论：`命中 {h}/{n}（no-entry {m}）`；
查不到条目时该路径记 `NO-ENTRY` —— 这本身是信号：该对象没有认知，或本轮收尾需要维护。
本工具**只读**，不写任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_INDEX = os.path.join(_ROOT, "aoci.code.txt")

_SECTION_RE = re.compile(r"^===(?P<dir>.*?)===\s*$")
_ENTRY_RE = re.compile(r"^(?P<name>[^\[\]]+?)\[(?P<tag>[^\]]*)\]:\s*(?P<body>.*)$")
_FIELD_SPLIT_RE = re.compile(r"\s\|\s(?=[FRAS]:)")


def parse_fields(body: str) -> dict:
    """把 `F:… | R:… | A:… | S:…` 拆成字段字典（纯函数）。"""
    out: dict = {}
    for part in _FIELD_SPLIT_RE.split(body.strip()):
        m = re.match(r"^([FRAS]):\s*(.*)$", part.strip(), re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def parse_volume(text: str, root: str = _ROOT) -> tuple:
    """解析 Code 卷文本 → (path→entry 字典, 出现顺序列表)。纯函数，不读盘。"""
    entries: dict = {}
    order: list = []
    cur = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SECTION_RE.match(line)
        if m:
            d = m.group("dir").strip()
            if os.path.isabs(d):
                try:
                    d = os.path.relpath(d, root)
                except ValueError:
                    pass
            cur = "" if d in (".", "") else os.path.normpath(d)
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        rel = os.path.normpath(os.path.join(cur, name)) if cur else name
        entry = {"path": rel, "name": name, "tag": m.group("tag").strip()}
        entry.update(parse_fields(m.group("body")))
        entries[rel] = entry
        order.append(rel)
    return entries, order


def resolve(entries: dict, order: list, wanted: list) -> list:
    """把用户给的路径解析成条目（精确优先，其次唯一 basename），纯函数。"""
    by_base: dict = {}
    for p in order:
        by_base.setdefault(os.path.basename(p), []).append(p)

    out = []
    for w in wanted:
        q = w.strip()
        q = os.path.normpath(q) if q else q
        if q in entries:
            out.append({"query": w, "status": "hit", "entry": entries[q]})
            continue
        cands = by_base.get(os.path.basename(q), [])
        if len(cands) == 1:
            out.append({"query": w, "status": "basename", "entry": entries[cands[0]]})
        elif len(cands) > 1:
            out.append({"query": w, "status": "ambiguous", "candidates": cands})
        else:
            out.append({"query": w, "status": "no-entry", "candidates": []})
    return out


def render_text(results: list, full: bool = False) -> str:
    """人类可读输出（只给 F/S，--full 再加 R/A）。"""
    lines = []
    for r in results:
        st = r["status"]
        if st in ("hit", "basename"):
            e = r["entry"]
            note = "（按 basename 匹配）" if st == "basename" else ""
            lines.append(f"== {e['path']} [{e['tag']}]{note} ==")
            for k in ("F", "S") + (("R", "A") if full else ()):
                v = e.get(k, "")
                if v and v != "-":
                    lines.append(f"{k}: {v}")
        elif st == "ambiguous":
            lines.append(f"== {r['query']} : 同名多条，请给完整路径 ==")
            lines.extend(f"   - {c}" for c in r["candidates"])
        else:
            lines.append(f"== {r['query']} : NO-ENTRY（无认知条目或需收尾维护） ==")
        lines.append("")
    hits = sum(1 for r in results if r["status"] in ("hit", "basename"))
    miss = sum(1 for r in results if r["status"] == "no-entry")
    lines.append(f"命中 {hits}/{len(results)}（no-entry {miss}）")
    return "\n".join(lines)


def load_index(path: str, root: str = _ROOT) -> tuple:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_volume(fh.read(), root)


def _selftest() -> int:
    fixture = (
        "#AOCI-CODE-VOLUME: 1\n"
        "===/repo/===\n"
        "a.py[CU9L]: F:入口 | R:code:b.py | A:main | S:顺序不可打乱；S: 不是字段\n"
        "===/repo/pkg/===\n"
        "c.py[PD9L]: F:层 | R:- | A:- | S:显式传连接\n"
        "d.py[PD9L]: F:层2 | R:- | A:- | S:-\n"
    )
    entries, order = parse_volume(fixture, root="/repo")
    assert set(entries) == {"a.py", "pkg/c.py", "pkg/d.py"}, entries
    assert entries["a.py"]["tag"] == "CU9L"
    assert entries["a.py"]["A"] == "main"
    assert entries["a.py"]["S"].startswith("顺序不可打乱"), entries["a.py"]["S"]
    assert entries["pkg/c.py"]["F"] == "层"
    res = resolve(entries, order, ["pkg/c.py", "c.py", "nope.py"])
    assert [r["status"] for r in res] == ["hit", "basename", "no-entry"], res
    txt = render_text(res)
    assert "NO-ENTRY" in txt and "命中 2/3" in txt, txt
    js = json.loads(json.dumps({"results": res}, ensure_ascii=False))
    assert js["results"][0]["entry"]["S"] == "显式传连接"
    print("[selftest] aoci_precheck ok")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AOCI 改前定向读（只读，硬性 #21）")
    ap.add_argument("paths", nargs="*", help="要预检的仓库相对路径")
    ap.add_argument("--index", default=_DEFAULT_INDEX, help="Code 卷路径（默认仓库根 aoci.code.txt）")
    ap.add_argument("--repo", default=_ROOT, help="仓库根（用于解析卷内绝对分节路径）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--full", action="store_true", help="同时输出 R/A 字段")
    ap.add_argument("--selftest", action="store_true", help="纯内存自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.paths:
        ap.print_help()
        return 0
    if not os.path.isfile(args.index):
        print(f"索引不存在：{args.index}", file=sys.stderr)
        return 2

    entries, order = load_index(args.index, args.repo)
    results = resolve(entries, order, args.paths)
    if args.json:
        print(json.dumps({"index": args.index, "results": results}, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, full=args.full))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
