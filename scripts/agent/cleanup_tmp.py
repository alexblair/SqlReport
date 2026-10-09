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
import contextlib
import io
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


def _repo_real(repo: Path | str | None = None) -> str:
    """仓库根的真实路径；显式传入 `repo` 时以它为准（自测可指向隔离根，不碰真仓库）。"""
    return os.path.realpath(repo_root() if repo is None else repo)


def _managed_root(name: str, repo: Path | str | None = None) -> Path:
    """受管根：`<repo_real>/<name>`（`repo_real = realpath(repo_root())`）。

    关键：只对仓库根取 `realpath`，受管目录名是**词法拼接**、绝不跟随符号链接。
    否则 `<repo>/run-logs -> /mnt/big`（逃逸）或 `<repo>/run-logs -> <repo>`（自指）
    会把受管根解析成仓库外目录乃至仓库根本身，白名单随即失效（修复轮缺陷 1/2）。
    """
    return Path(os.path.join(_repo_real(repo), name))


def _managed_roots(repo: Path | str | None = None) -> list[Path]:
    """两个受管根（词法锚定仓库根）；受管根本身永不在可删集合内。"""
    return [_managed_root(name, repo) for name in TEMP_DIRS]


def _strictly_inside(real: str, root: Path) -> bool:
    """`real`（真实路径）是否**严格**位于 `root` 之内；`root` 自身不算。"""
    if real == str(root):
        return False
    try:
        Path(real).relative_to(root)
    except ValueError:
        return False
    return True


def _inside_managed(real: str, repo: Path | str | None = None,
                    name: str | None = None) -> bool:
    """`real`（真实路径）是否严格位于某个受管根之内（给了 `name` 就只认那一个）。

    这是**接受谓词**，也是 `delete_entries()` 里 `rmdir` 爬升的**同一个**判定：
    两者共用 `_managed_root()` 的锚定，不可能各说各话（缺陷 2 的根治点）。
    """
    if name is not None:
        return _strictly_inside(real, _managed_root(name, repo))
    return any(_strictly_inside(real, _managed_root(n, repo)) for n in TEMP_DIRS)


def _managed_name(real: str, repo: Path | str | None = None) -> str | None:
    """`real` 命中的受管目录名；不属于任何受管根时为 `None`。"""
    for name in TEMP_DIRS:
        if _strictly_inside(real, _managed_root(name, repo)):
            return name
    return None


def _managed(path: str, repo: Path | str | None = None, name: str | None = None) -> bool:
    """白名单校验：只允许删除受管目录**内部**的条目，受管根自身永不在列。

    `realpath(path)` 必须严格位于 `<repo_real>/run-logs` 或 `<repo_real>/perf-logs`
    之内。受管目录是符号链接时一律拒绝：那时候选的 realpath 要么落在仓库外，
    要么首分量不是受管目录名（自指场景）。
    """
    return _inside_managed(os.path.realpath(path), repo, name)


def collect(dir_path: Path, repo: Path | str | None = None,
            name: str | None = None) -> list[tuple[str, float]]:
    """递归收集 `(绝对路径, mtime)`。

    只收真实文件：符号链接与 `realpath` 不在 `dir_path` 内的条目一律丢弃。
    传入 `repo` 时再叠加仓库锚定（`name` 默认取 `dir_path` 的名字）：候选 realpath
    必须严格位于 `<repo_real>/<name>` 之内。受管根是符号链接时（指向仓库外或
    仓库根自身），这里就会一个候选都不剩——删除阶段因此无物可删。
    """
    root = Path(os.path.realpath(dir_path))
    if not root.is_dir():
        return []
    want = name if name is not None else (Path(dir_path).name if repo is not None else None)
    out: list[tuple[str, float]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # 符号链接目录直接摘掉：既不遍历，也不会被当成清理候选
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            real = Path(os.path.realpath(path))
            if os.path.islink(path):
                continue  # 符号链接本身不删（删它等于删别处）
            try:
                real.relative_to(root)
            except ValueError:
                continue  # realpath 越界 → 丢弃
            if repo is not None and not _inside_managed(str(real), repo, want):
                continue  # 仓库锚定不通过（符号链接受管根等）→ 丢弃
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


def delete_entries(paths: list[str], repo: Path | str | None = None,
                   self_deleted: set[str] | None = None) -> tuple[int, int]:
    """删除文件，返回 `(删除文件数, 释放字节)`；父目录自底向上删空到受管根为止（不删根本身）。

    只接受 `_managed()` 通过的路径（即收集阶段的产物）；`rmdir` 爬升与接受谓词共用
    `_inside_managed()`，所以不可能出现「删得进、却爬出受管根」的分歧（缺陷 2）。
    `self_deleted` 传入时登记本次成功删除的绝对路径（dry-run 归因：本工具干的 vs
    第三方）；不传则内部即弃，归因集合按调用隔离、绝不跨调用串味（缺陷 3）。
    """
    mine = self_deleted if self_deleted is not None else set()
    files = 0
    freed = 0
    parents: set[str] = set()
    for path in paths:
        if not _managed(path, repo):
            continue  # 白名单外一律不碰
        try:
            size = os.lstat(path).st_size
            os.remove(path)
        except OSError:
            continue  # 并发下文件可能已被别处删除；以实际删除数为准
        files += 1
        freed += size
        mine.add(os.path.abspath(path))
        parents.add(os.path.dirname(os.path.abspath(path)))

    # 目录自底向上删空：只在**同名受管根内部**爬升，到达 <repo>/run-logs、<repo>/perf-logs 即停
    for start in sorted(parents, key=lambda d: d.count(os.sep), reverse=True):
        name = _managed_name(os.path.realpath(start), repo)
        if name is None:
            continue
        cur = start
        while _inside_managed(os.path.realpath(cur), repo, name):
            try:
                os.rmdir(cur)  # 仅空目录可删；非空即失败并停止上行
            except OSError:
                break
            cur = os.path.dirname(cur)
    return files, freed


def _selftest() -> int:
    """内嵌自测：不触碰真实 run-logs/perf-logs，全部用合成记录与 tempfile 临时目录。

    九组断言（①–⑥ 为 brief 原始六条，⑦–⑨ 为修复轮新增，逐条展开为若干叶子检查）：
    ① 窗口内保留、窗口外可删；② `force=True` 全部可删；③ 空输入返回两个空列表；
    ④ `collect` 对不存在目录返回 `[]`；⑤ `collect` 丢弃符号链接与越界 realpath；
    ⑥ `delete_entries` 删文件、把嵌套同名架子一路清到受管根（保留受管根本身），
    且白名单锚定 `repo_root()`：受管根之外的 `run-logs`/`perf-logs` 同名分量一律拒绝；
    ⑦ 逃逸形态 A（受管根符号链接到仓库外）：一个候选都不接受、仓外文件不动；
    ⑧ 逃逸形态 B（受管根符号链接到仓库根自身）：仓内路径全拒绝，`rmdir` 爬升
    停在受管根、不越过仓库根；⑨ 归因集合按调用隔离，跨调用不误判第三方消失。
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

    # ⑥ 锚定仓库根的白名单删除：清空嵌套目录、保留受管根本身（自测内改用隔离根）
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td2:
        base = Path(td) / "perf-logs"
        deep = base / "l1" / "l2"
        deep.mkdir(parents=True)
        f1 = deep / "a.log"
        f2 = base / "b.log"
        f1.write_text("aaaa", encoding="utf-8")
        f2.write_text("bb", encoding="utf-8")
        # 受管根内部嵌套同名架子（真实遗留形态 perf-logs/_t-iso-*/perf-logs/_t）：
        # 爬升必须一路删到受管根，而不是见到同名 basename 就停
        nested = base / "_t-iso" / "perf-logs" / "_t"
        nested.mkdir(parents=True)
        f3 = nested / "c.log"
        f3.write_text("ccc", encoding="utf-8")
        # 同名分量但在受管根之外的诱饵：必须拒绝（白名单锚定 repo_root 的正面取证）
        decoy = Path(td2) / "run-logs" / "d.log"
        decoy.parent.mkdir(parents=True)
        decoy.write_text("dddd", encoding="utf-8")

        original_repo_root = repo_root
        globals()["repo_root"] = lambda: Path(td)  # 隔离根：不碰真实 run-logs/perf-logs
        try:
            n, freed = delete_entries([str(f1), str(f2), str(f3), str(decoy)])
            checks.append(("⑥ 受管根内路径受管", _managed(str(base / "x.log")), True))
            checks.append(("⑥ 受管根自身不受管", _managed(str(base)), False))
            checks.append(("⑥ 同名诱饵不受管", _managed(str(decoy)), False))
        finally:
            globals()["repo_root"] = original_repo_root

        checks.append(("⑥ 删除文件数", n, 3))
        checks.append(("⑥ 释放字节数", freed, 9))
        checks.append(("⑥ 嵌套同名架子一路清到受管根", not (base / "_t-iso").exists(), True))
        checks.append(("⑥ 二级目录已清空", not deep.exists() and not (base / "l1").exists(), True))
        checks.append(("⑥ 目标目录本身保留", base.is_dir(), True))
        checks.append(("⑥ 同名诱饵未被删", decoy.exists(), True))

    # ⑦ 逃逸形态 A：受管根符号链接到仓库外 → 白名单必须一个候选都不接受
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        outside = base / "outside"
        outside.mkdir()
        victim = outside / "victim.log"
        victim.write_text("victim", encoding="utf-8")
        (base / "run-logs").symlink_to(outside, target_is_directory=True)
        checks.append(("⑦ 外部符号链接根：收集为空", collect(base / "run-logs", repo=base), []))
        checks.append(("⑦ 外部符号链接根：候选不受管",
                       _managed(str(victim), repo=base), False))
        n7, freed7 = delete_entries([str(victim)], repo=base)
        checks.append(("⑦ 外部符号链接根：删除数为 0", (n7, freed7), (0, 0)))
        checks.append(("⑦ 仓外文件仍在", victim.is_file(), True))
        checks.append(("⑦ 仓库根未被 rmdir", base.is_dir(), True))

    # ⑧ 逃逸形态 B：受管根符号链接到仓库根自身 → 仓内路径全拒绝，rmdir 不得爬出受管根
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "docs").mkdir()
        doc = base / "docs" / "keep.txt"
        doc.write_text("keep", encoding="utf-8")
        (base / "run-logs").symlink_to(base, target_is_directory=True)
        sneaky = base / "run-logs" / "sneaky.txt"   # 词法在受管根内，realpath 落在仓库根
        sneaky.write_text("sneaky", encoding="utf-8")
        deep = base / "perf-logs" / "x"
        deep.mkdir(parents=True)
        leg = deep / "leg.log"
        leg.write_text("leg", encoding="utf-8")
        got = [p for p, _ in collect(base / "perf-logs", repo=base)]
        checks.append(("⑧ 合法受管根仍收集", got, [str(leg)]))
        checks.append(("⑧ 自指符号链接根：收集为空", collect(base / "run-logs", repo=base), []))
        checks.append(("⑧ 仓内路径不受管", _managed(str(doc), repo=base), False))
        checks.append(("⑧ 词法受管但 realpath 越界不受管", _managed(str(sneaky), repo=base), False))
        checks.append(("⑧ 受管根本身不受管", _managed(str(base / "run-logs"), repo=base), False))
        n8, _ = delete_entries([str(doc), str(sneaky)], repo=base)
        checks.append(("⑧ 自指符号链接根：删除数为 0", n8, 0))
        checks.append(("⑧ 仓内文件仍在", doc.is_file(), True))
        checks.append(("⑧ 仓库根未被 rmdir", base.is_dir(), True))
        checks.append(("⑧ docs/ 未被 rmdir", (base / "docs").is_dir(), True))
        n9, _ = delete_entries([str(leg)], repo=base)
        checks.append(("⑧ 合法受管目录仍可清理", n9, 1))
        checks.append(("⑧ 爬升停在受管根（perf-logs 保留）", (base / "perf-logs").is_dir(), True))
        checks.append(("⑧ 爬升未越过仓库根", base.is_dir() and (base / "docs").is_dir(), True))

    # ⑨ 归因集合按调用隔离：上一轮的自删不得污染下一轮 dry-run 的第三方消失判定
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "perf-logs").mkdir()
        ghost = base / "perf-logs" / "ghost.log"
        ghost.write_text("g", encoding="utf-8")
        stale = [(str(ghost), now - 3600.0)]
        original_collect = collect
        globals()["collect"] = lambda dir_path, repo=None, name=None: list(stale)
        err = io.StringIO()
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                first = main(["--apply", "--quiet"], repo=base)
                second = main(["--quiet"], repo=base)
        finally:
            globals()["collect"] = original_collect
        checks.append(("⑨ 第一轮 apply 删除成功", first, 0))
        checks.append(("⑨ 第二轮 dry-run 归因不串味（rc=0）", second, 0))
        checks.append(("⑨ 第二轮判定为第三方消失（WARN）", "[WARN]" in err.getvalue(), True))
        checks.append(("⑨ 第二轮不报自因错误（无 ERROR）", "[ERROR]" in err.getvalue(), False))
        checks.append(("⑨ 第二轮仍打结论行", "cleaned" in out.getvalue(), True))
    bad = [(name, got, want) for name, got, want in checks if got != want]
    if bad:
        for name, got, want in bad:
            print(f"[FAIL] {name}: got={got!r} want={want!r}")
        print(f"[FAIL] selftest 失败：{len(bad)}/{len(checks)} 项断言不符")
        return 1
    print(f"[OK] selftest 通过（{len(checks)} 项断言）")
    return 0


def main(argv: list[str] | None = None, repo: Path | str | None = None) -> int:
    """CLI 入口：默认 dry-run，只有 `--apply` 才真删。

    `repo` 是仓库根（默认 `repo_root()`）；显式传入供自测指向隔离根，不是 CLI 开关。
    """
    ap = argparse.ArgumentParser(description="临时产物清理工具（run-logs/ 与 perf-logs/）")
    ap.add_argument("--apply", action="store_true", help="真正删除；默认只演练（dry-run）")
    ap.add_argument("--force", action="store_true", help="忽略活跃窗口，删除全部候选")
    ap.add_argument("--active-window", type=float, default=600.0, metavar="SEC",
                    help="活跃写入窗口秒数（默认 600）：窗口内 mtime 的条目跳过")
    ap.add_argument("--selftest", action="store_true", help="跑内嵌自测（不触碰真实目录）")
    ap.add_argument("--quiet", action="store_true", help="只输出末行结论")
    args = ap.parse_args(argv)

    try:
        if args.selftest:
            return _selftest()  # 同样在 try 内：tempfile 等 OSError 收敛为一行错误 + 退出 1
        # 白名单硬检查：目标目录只能是 TEMP_DIRS 本身（spec §3.2「代码内断言白名单」）
        if TEMP_DIRS != ("run-logs", "perf-logs"):
            print("[ERROR] 清理白名单被篡改，拒绝执行", file=sys.stderr)
            return 1
        base = repo_root() if repo is None else Path(repo)
        now = time.time()
        self_deleted: set[str] = set()   # 归因集合：本调用私有，绝不跨调用残留（缺陷 3）
        deletable: list[str] = []
        kept: list[str] = []
        for name in TEMP_DIRS:
            will_go, stay = split_active(collect(base / name, repo=base, name=name), now,
                                         args.active_window, args.force)
            deletable.extend(will_go)
            kept.extend(stay)

        if args.apply:
            n, freed = delete_entries(deletable, repo=base, self_deleted=self_deleted)
        else:
            # 决策 #1：默认 dry-run —— 只统计「会删什么、能释放多少」，一个文件都不删
            n = len(deletable)
            freed = 0
            for path in deletable:
                try:
                    freed += os.lstat(path).st_size
                except OSError:
                    continue
            # 决策 #1 显式检查（零副作用）：dry-run 分支从不调用 delete_entries，
            # 候选消失只可能是第三方写入者干的（本工具从不在 dry-run 分支删文件）；
            # 只有「本工具自己删过」（self_deleted，本调用私有）才是硬失败（防未来回归）。
            missing = [p for p in deletable if not os.path.lexists(p)]
            if missing:
                ours = [p for p in missing if os.path.abspath(p) in self_deleted]
                if ours:
                    print(f"[ERROR] dry-run 零副作用校验失败：本工具删除了 {len(ours)} 个候选文件",
                          file=sys.stderr)
                    return 1
                shown = ", ".join(os.path.relpath(p, base) for p in missing[:MAX_LIST])
                more = f" …等 {len(missing)} 个" if len(missing) > MAX_LIST else ""
                print(f"[WARN] dry-run 期间第三方移除了候选文件：{shown}{more}"
                      f"（已从统计扣除，不影响结论）", file=sys.stderr)
                n -= len(missing)

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
