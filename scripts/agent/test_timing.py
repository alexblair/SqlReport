#!/usr/bin/env python3
"""全量测试计时 / 指纹复用 / 快速门禁 工具。

为什么存在：全量 `unittest discover` 曾因单条测试白等真实 300s 节拍而跑到
363s（2026-10-20 实测），且这类「病态等待」很难在日常输出里看见。本工具把
逐条耗时、慢用例告警、结果指纹固化成一条命令。

用法：
  python scripts/agent/test_timing.py            # 跑全量，逐条计时，结论落 run-logs/
  python scripts/agent/test_timing.py --quick    # 快速门禁：只跑静态分析，失败即停（约 8s）
  python scripts/agent/test_timing.py --report   # 只读上次结果，判断当前代码能否复用
  python scripts/agent/test_timing.py --reuse    # 指纹命中则复用上次全量结果（不重跑）
  python scripts/agent/test_timing.py --force    # 忽略指纹强制重跑（与 --reuse 相反）

退出码：0 = 通过（或可复用），1 = 有失败/门禁未过。
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
"""仓库根：scripts/agent/ 上两级。"""

RUN_LOGS = os.path.join(PROJECT_ROOT, "run-logs")
LAST_JSON = os.path.join(RUN_LOGS, "last-full-run.json")

SLOW_TEST_SEC = 5.0
"""单条用例慢阈值：超过即 WARN（历史值：keepalive 用例 301s、mysql 用例 10s）。"""

BUDGET_SEC = 90.0
"""全量预算红线（08-testing-conventions.md 规定）。超过仅告警，不判失败。"""


def _git(*args: str) -> str:
    """执行 git 命令并返回 stdout（失败返回空串，不抛异常）。"""
    try:
        out = subprocess.run(["git", *args], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=30)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _sha(text: str) -> str:
    """返回文本的 sha256 前 16 位。"""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def fingerprint() -> dict:
    """计算「测试所依赖的代码」指纹：HEAD + 工作区差异 + 未跟踪 py 内容。"""
    head = _git("rev-parse", "HEAD").strip()
    diff = _git("diff", "HEAD")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    untracked_py = sorted(p for p in untracked.splitlines() if p.endswith(".py"))
    parts = [head, diff]
    for rel in untracked_py:
        try:
            with open(os.path.join(PROJECT_ROOT, rel), "r",
                      encoding="utf-8", errors="replace") as f:
                parts.append(rel + "\n" + f.read())
        except OSError:
            parts.append(rel)
    return {"head": head, "digest": _sha("\n--\n".join(parts)),
            "untracked_py": untracked_py}


def load_last() -> dict:
    """读取上次全量结果；不存在或损坏时返回空字典。"""
    try:
        with open(LAST_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_last(payload: dict) -> None:
    """写入上次全量结果（run-logs/ 已 gitignore）。"""
    os.makedirs(RUN_LOGS, exist_ok=True)
    with open(LAST_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _fmt(sec: float) -> str:
    """秒数格式化。"""
    return "%.2fs" % sec


class TimedResult(unittest.TextTestResult):
    """逐条用例计时并收集耗时。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.durations: dict[str, float] = {}
        self._t0 = 0.0

    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.durations[test.id()] = time.perf_counter() - self._t0
        super().stopTest(test)


def quick_gate() -> int:
    """快速门禁：只跑静态分析（语法/导入/未定义名），ERROR 即失败。"""
    sys.path.insert(0, PROJECT_ROOT)
    from tests.bug_hunt.static_analyzer import get_py_files, run_all_checkers
    files = get_py_files(PROJECT_ROOT)
    t0 = time.perf_counter()
    findings = run_all_checkers(py_files=files)
    errors = findings["errors"]
    print("[quick] 静态分析 %d 文件耗时 %s，ERROR=%d WARNING=%d INFO=%d" % (
        len(files), _fmt(time.perf_counter() - t0), len(errors),
        len(findings["warnings"]), len(findings["infos"])))
    for e in errors:
        print("  " + e)
    return 0 if not errors else 1


def run_full(stream) -> tuple:
    """跑一次全量 discover，返回 (是否通过, 结果对象, 耗时)。"""
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(PROJECT_ROOT, "tests"),
                            top_level_dir=PROJECT_ROOT)
    runner = unittest.TextTestRunner(stream=stream, verbosity=1,
                                     resultclass=TimedResult)
    t0 = time.perf_counter()
    result = runner.run(suite)
    return result.wasSuccessful(), result, time.perf_counter() - t0


def _report(result, total: float, head: str) -> None:
    """打印结论：Ran / 失败项 / top10 慢用例 / >SLOW 告警 / 预算判定。"""
    d = result.durations
    print("\n===== 计时摘要 =====")
    print("RAN=%d failures=%d errors=%d skipped=%d SEC=%s HEAD=%s" % (
        result.testsRun, len(result.failures), len(result.errors),
        len(result.skipped), _fmt(total), head[:8]))
    print("导入阶段之外的纯执行耗时：%s（预算 %s）" % (_fmt(total), _fmt(BUDGET_SEC)))
    for test_id, sec in sorted(d.items(), key=lambda kv: -kv[1])[:10]:
        print("  %8s  %s" % (_fmt(sec), test_id))
    slow = [(t, s) for t, s in d.items() if s > SLOW_TEST_SEC]
    if slow:
        print("WARN: %d 条用例超过 %.0fs（病态等待嫌疑，加 patch 降节拍）：" % (
            len(slow), SLOW_TEST_SEC))
        for t, s in sorted(slow, key=lambda kv: -kv[1]):
            print("  WARN %8s  %s" % (_fmt(s), t))
    if total > BUDGET_SEC:
        print("WARN: 全量超过预算 %s，见 08-testing-conventions.md 热点清单"
              % _fmt(BUDGET_SEC))


def main(argv=None) -> int:
    """命令入口。"""
    ap = argparse.ArgumentParser(description="全量测试计时/复用/快速门禁")
    ap.add_argument("--quick", action="store_true", help="只跑静态分析快速门禁")
    ap.add_argument("--reuse", action="store_true", help="指纹命中则复用上次结果")
    ap.add_argument("--report", action="store_true", help="只打印上次结果与指纹")
    ap.add_argument("--force", action="store_true", help="强制重跑，忽略指纹")
    args = ap.parse_args(argv)

    if args.quick:
        return quick_gate()

    fp = fingerprint()
    last = load_last()

    if args.report:
        if not last:
            print("[report] 无历史全量结果")
            return 0
        same = last.get("digest") == fp["digest"]
        print("[report] 上次: RAN=%s failures=%s errors=%s skipped=%s SEC=%s at %s" % (
            last.get("ran"), last.get("failures"), last.get("errors"),
            last.get("skipped"), last.get("sec"), last.get("ts")))
        print("[report] 指纹一致：%s（一致则无需重跑全量）" % ("是" if same else "否"))
        return 0

    if args.reuse and not args.force and last and last.get("digest") == fp["digest"]:
        print("[reuse] 代码指纹未变（%s），复用上次结果：RAN=%s failures=%s "
              "errors=%s skip=%s SEC=%s at %s" % (
                  fp["digest"], last.get("ran"), last.get("failures"),
                  last.get("errors"), last.get("skipped"), last.get("sec"),
                  last.get("ts")))
        return 0 if last.get("ok") else 1

    os.makedirs(RUN_LOGS, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(RUN_LOGS, "timing-%s.log" % stamp)
    buffer = []
    with open(log_path, "w", encoding="utf-8") as log:
        class _Tee:
            """同时写日志文件与终端。"""

            def write(self, s: str) -> None:
                log.write(s)
                buffer.append(s)

            def flush(self) -> None:
                log.flush()

        ok, result, total = run_full(_Tee())
    _report(result, total, fp["head"])
    print("日志: %s" % os.path.relpath(log_path, PROJECT_ROOT))
    save_last({"ts": stamp, "digest": fp["digest"], "head": fp["head"],
               "ran": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "skipped": len(result.skipped),
               "sec": round(total, 2), "ok": ok})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
