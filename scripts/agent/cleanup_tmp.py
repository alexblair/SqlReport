#!/usr/bin/env python3
"""cleanup_tmp.py — 临时产物清理工具（`run-logs/` 与 `perf-logs/` 的唯一清理入口）。

为什么需要它：AGENTS.md 硬性 #14 要求测试日志与临时产物一律落仓库内已 gitignore 的
`run-logs/` / `perf-logs/`，但人工 `rm` 与并发写入者（后台作业）会互相打架：
一边把还在写的日志删掉，另一边把日志目录越堆越大。本工具把「清空」变成一条
可重复、可审计、默认零副作用的命令：

    - 目标目录**只有** `run-logs/`、`perf-logs/`（仓库根由 `__file__` 推导），
      清空其**内容**、保留目录本身，绝不触碰仓库内其他路径；
    - 默认 **dry-run**：只报告「会删什么、能释放多少」，一个文件都不删；
    - `--apply` 才真删；`--active-window`（默认 600 秒）内的 mtime 判为
      「活跃写入」而跳过（防并发误删），`--force` 忽略该窗口；
    - 幂等：连跑两次，第二次必为 `cleaned 0 files / 0.0 MB`。

用法（在仓库根执行）：

    venv/bin/python scripts/agent/cleanup_tmp.py                 # dry-run：只报告
    venv/bin/python scripts/agent/cleanup_tmp.py --apply         # 真删（收尾批量命令用）
    venv/bin/python scripts/agent/cleanup_tmp.py --apply --force # 忽略活跃窗口，全清
    venv/bin/python scripts/agent/cleanup_tmp.py --selftest      # 内嵌自测（不碰真实目录）

末行恒为机器可读结论：`cleaned {n} files / {mb:.1f} MB; kept {k} active`
（非 `--apply` 时前缀 `[dry-run] `），便于收尾简报直接取证。
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

# ---- 白名单：唯二允许清理的仓库内目录（不得扩充，见设计 spec §3.2）----------------
TEMP_DIRS: tuple[str, ...] = ("run-logs", "perf-logs")
MAX_LIST = 20          # 明细清单最多列出的条数（只影响刷屏，不影响统计与删除）


def repo_root() -> Path:
    """仓库根（本文件位于 <root>/scripts/agent/）——禁止硬编码主目录（硬性 #10）。"""
    return Path(__file__).resolve().parents[2]


def _managed(path: str) -> bool:
    """白名单校验：只允许删除 TEMP_DIRS 目录**内部**的条目，目录本身永不在列。"""
    real = Path(os.path.realpath(path))
    return real.name not in TEMP_DIRS and any(part in TEMP_DIRS for part in real.parts)


def collect(dir_path: Path) -> list[tuple[str, float]]:
    """递归收集 `(绝对路径, mtime)`。

    只收真实文件：符号链接与 `realpath` 不在 `dir_path` 内的条目一律丢弃
    （避免把仓库外的东西当成清理目标）。
    """
    root = Path(os.path.realpath(dir_path))
    if not root.is_dir():
        return []
    out: list[tuple[str, float]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # 符号链接目录直接摘掉：既不遍历，也不会被当成清理候选
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            path = os.path.join(dirpath, name)
            real = Path(os.path.realpath(path))
            if os.path.islink(path):
                continue  # 符号链接本身不删（删它等于删别处）
            try:
                real.relative_to(root)
            except ValueError:
                continue  # realpath 越界 → 丢弃
            try:
                mtime = os.stat(path).st_mtime
            except OSError:
                continue
            out.append((os.path.abspath(path), mtime))
    out.sort()  # 固定顺序，便于取证与对比
    return out


def split_active(records: list[tuple[str, float]], now: float, window: float,
                 force: bool) -> tuple[list[str], list[str]]:
    """按 mtime 拆分记录：返回 `(可删, 保留)`。

    `now` 由调用方传入（便于自测）；`window` 只与 mtime 比较：窗口内视为
    「活跃写入」而保留，`force=True` 时全部可删。
    """
    deletable: list[str] = []
    kept: list[str] = []
    for path, mtime in records:
        if force or (now - mtime) > window:
            deletable.append(path)
        else:
            kept.append(path)
    return deletable, kept


def delete_entries(paths: list[str]) -> tuple[int, int]:
    """删除文件，返回 `(删除文件数, 释放字节)`；父目录自底向上删空（不删白名单目录本身）。"""
    files = 0
    freed = 0
    parents: set[str] = set()
    for path in paths:
        if not _managed(path):
            continue  # 白名单外一律不碰
        try:
            size = os.lstat(path).st_size
            os.remove(path)
        except OSError:
            continue  # 并发下文件可能已被别处删除；以实际删除数为准
        files += 1
        freed += size
        parents.add(os.path.dirname(os.path.abspath(path)))

    # 目录自底向上删空：只删受管目录内部的空目录，绝不动 run-logs/ 与 perf-logs/ 本身
    for start in sorted(parents, key=lambda d: d.count(os.sep), reverse=True):
        cur = start
        while os.path.basename(cur) not in TEMP_DIRS and _managed(cur + os.sep):
            try:
                os.rmdir(cur)  # 仅空目录可删；非空即失败并停止上行
            except OSError:
                break
            cur = os.path.dirname(cur)
    return files, freed


def _selftest() -> int:
    """内嵌自测：不触碰真实 run-logs/perf-logs，全部用合成记录与 tempfile 临时目录。

    六条断言（①–⑥，逐条展开为若干叶子检查）：
    ① 窗口内保留、窗口外可删；② `force=True` 全部可删；③ 空输入返回两个空列表；
    ④ `collect` 对不存在目录返回 `[]`；⑤ `collect` 丢弃符号链接与越界 realpath；
    ⑥ `delete_entries` 删文件并清空二级目录（保留目标目录本身）。
    """
    now = 1_000_000.0
    checks: list[tuple[str, object, object]] = []

    # ① 活跃窗口：窗口内保留、窗口外可删
    recs = [("/x/fresh.log", now - 10.0), ("/x/old.log", now - 3600.0)]
    deletable, kept = split_active(recs, now, 600.0, False)
    checks.append(("① 窗口外可删", deletable, ["/x/old.log"]))
    checks.append(("① 窗口内保留", kept, ["/x/fresh.log"]))

    # ② force=True 忽略窗口，全部可删
    deletable, kept = split_active(recs, now, 600.0, True)
    checks.append(("② force 全可删", (deletable, kept), (["/x/fresh.log", "/x/old.log"], [])))

    # ③ 空输入返回两个空列表
    checks.append(("③ 空输入", split_active([], now, 600.0, False), ([], [])))

    # ④ 不存在的目录收集为空
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "not-here"
        checks.append(("④ 不存在目录返回 []", collect(missing), []))

    # ⑤ 丢弃符号链接与 realpath 越界的条目（用真实临时目录）
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "run-logs"
        (base / "sub").mkdir(parents=True)
        real = base / "sub" / "real.log"
        real.write_text("real", encoding="utf-8")
        outside = Path(td) / "outside.log"
        outside.write_text("outside", encoding="utf-8")
        (base / "link.log").symlink_to(real)      # 符号链接 → 丢弃
        (base / "escape.log").symlink_to(outside)  # realpath 越界 → 丢弃
        got = collect(base)
        checks.append(("⑤ 只收真实文件", got, [(str(real), real.stat().st_mtime)]))

    # ⑥ 删文件并清空二级目录，但保留目标目录本身
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "perf-logs"
        deep = base / "l1" / "l2"
        deep.mkdir(parents=True)
        f1 = deep / "a.log"
        f2 = base / "b.log"
        f1.write_text("aaaa", encoding="utf-8")
        f2.write_text("bb", encoding="utf-8")
        n, freed = delete_entries([str(f1), str(f2)])
        checks.append(("⑥ 删除文件数", n, 2))
        checks.append(("⑥ 释放字节数", freed, 6))
        checks.append(("⑥ 二级目录已清空", not deep.exists() and not (base / "l1").exists(), True))
        checks.append(("⑥ 目标目录本身保留", base.is_dir(), True))

    bad = [(name, got, want) for name, got, want in checks if got != want]
    if bad:
        for name, got, want in bad:
            print(f"[FAIL] {name}: got={got!r} want={want!r}")
        print(f"[FAIL] selftest 失败：{len(bad)}/{len(checks)} 项断言不符")
        return 1
    print(f"[OK] selftest 通过（{len(checks)} 项断言）")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：默认 dry-run，只有 `--apply` 才真删。"""
    ap = argparse.ArgumentParser(description="临时产物清理工具（run-logs/ 与 perf-logs/）")
    ap.add_argument("--apply", action="store_true", help="真正删除；默认只演练（dry-run）")
    ap.add_argument("--force", action="store_true", help="忽略活跃窗口，删除全部候选")
    ap.add_argument("--active-window", type=float, default=600.0, metavar="SEC",
                    help="活跃写入窗口秒数（默认 600）：窗口内 mtime 的条目跳过")
    ap.add_argument("--selftest", action="store_true", help="跑内嵌自测（不触碰真实目录）")
    ap.add_argument("--quiet", action="store_true", help="只输出末行结论")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        # 白名单硬检查：目标目录只能是 TEMP_DIRS 本身（spec §3.2「代码内断言白名单」）
        if TEMP_DIRS != ("run-logs", "perf-logs"):
            print("[ERROR] 清理白名单被篡改，拒绝执行", file=sys.stderr)
            return 1
        base = repo_root()
        now = time.time()
        deletable: list[str] = []
        kept: list[str] = []
        for name in TEMP_DIRS:
            will_go, stay = split_active(collect(base / name), now,
                                         args.active_window, args.force)
            deletable.extend(will_go)
            kept.extend(stay)

        if args.apply:
            n, freed = delete_entries(deletable)
        else:
            # 决策 #1：默认 dry-run —— 只统计「会删什么、能释放多少」，一个文件都不删
            n = len(deletable)
            freed = 0
            for path in deletable:
                try:
                    freed += os.lstat(path).st_size
                except OSError:
                    continue
            # 决策 #1 显式检查（零副作用）：dry-run 后候选文件必须原样还在
            missing = [p for p in deletable if not os.path.lexists(p)]
            if missing:
                print(f"[ERROR] dry-run 零副作用校验失败：{len(missing)} 个候选文件不在了",
                      file=sys.stderr)
                return 1

        if not args.quiet:
            note = "，--force 已忽略活跃窗口" if args.force else ""
            print(f"目标目录：{', '.join(TEMP_DIRS)}（活跃窗口 {args.active_window:g}s{note}）")
            verb = "删除" if args.apply else "将删"
            for path in deletable[:MAX_LIST]:
                print(f"  {verb} {os.path.relpath(path, base)}")
            if len(deletable) > MAX_LIST:
                print(f"  …另有 {len(deletable) - MAX_LIST} 个待删")
            for path in kept[:MAX_LIST]:
                print(f"  保留(活跃) {os.path.relpath(path, base)}")
            if len(kept) > MAX_LIST:
                print(f"  …另有 {len(kept) - MAX_LIST} 个活跃条目")

        prefix = "" if args.apply else "[dry-run] "
        print(f"{prefix}cleaned {n} files / {freed / (1024 * 1024):.1f} MB; "
              f"kept {len(kept)} active")
        return 0
    except OSError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
