"""门禁：测试代码里不允许 >1s 的真实等待（病态等待回归）。

为什么存在：2026-10-20 全量实测 363s，其中单条用例
`tests.test_scheduler_extra.TestTickLoopExceptions.test_keepalive_exception_does_not_break_loop`
白等真实 300s（`scheduler.py:39 _KEEPALIVE_INTERVAL_SECONDS = 300`），占全量 83%。
这类等待在逐条输出里看不出来，一旦被新用例带回来，全量又会悄悄涨回分钟级。

规则（两类，都只看字面量）：
1. `time.sleep(n)`：n > 1.0 即失败——这是无条件睡眠，必然白等。
2. `*.wait/join/acquire(timeout=n)`：n > 30.0 即失败——这类是「上限」，会提前返回；
   正常用 2~10s 做安全网即可，写 30s 以上说明用例在赌超时。
确需真实等待的极少数场景，在同一行写注释 `slow-wait-ok: <原因>` 显式豁免。

注意：本条只能截住「测试自己写的长等待」。生产常量导致的真实节拍等待
（如 `scheduler.py:39 _KEEPALIVE_INTERVAL_SECONDS = 300` 被测试二次触发）静态上看
不见，靠 `scripts/agent/test_timing.py` 的逐条 >5s WARN 兜底。
"""

import ast
import os
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_SLEEP_SEC = 1.0
MAX_TIMEOUT_SEC = 30.0
ALLOW_MARK = "slow-wait-ok"
SKIP_DIRS = {"__pycache__", "integration"}
SKIP_PREFIX = ("manual_",)
SELF_NAME = os.path.basename(os.path.abspath(__file__))

SLEEP_ATTRS = {"sleep"}
TIMEOUT_ATTRS = {"wait", "wait_for", "join", "acquire"}


def iter_candidate_files(tests_dir: str = TESTS_DIR):
    """产出需要检查的测试文件路径（跳过真层、手工脚本与本门禁自身）。"""
    for root, dirs, files in os.walk(tests_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            if name == SELF_NAME or name.startswith(SKIP_PREFIX):
                continue
            yield os.path.join(root, name)


def _literal_seconds(node):
    """从 AST 节点取字面量秒数；非字面量返回 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value)
    return None


def find_slow_waits(source: str, relpath: str) -> list:
    """在源码里找超限的字面量等待，返回 ["文件:行 说明", ...]。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # 语法错误由 SyntaxChecker 负责，这里不重复报
    lines = source.splitlines()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr in SLEEP_ATTRS:
            limit = MAX_SLEEP_SEC
        elif func.attr in TIMEOUT_ATTRS:
            limit = MAX_TIMEOUT_SEC
        else:
            continue
        candidates = list(node.args)
        candidates.extend(kw.value for kw in node.keywords
                          if kw.arg in ("timeout", "interval"))
        sec = None
        for cand in candidates:
            sec = _literal_seconds(cand)
            if sec is not None:
                break
        if sec is None or sec <= limit:
            continue
        line_no = getattr(func, "lineno", 0) or 0
        text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if ALLOW_MARK in text:
            continue
        found.append("%s:%d %s(%s)" % (relpath, line_no, func.attr,
                                       _trim(sec)))
    return found


def _trim(sec: float) -> str:
    """秒数紧凑显示（1.5 / 300）。"""
    return ("%d" % sec) if sec == int(sec) else ("%g" % sec)


class TestNoSlowWaits(unittest.TestCase):
    """拦住回归：测试只能等毫秒级，不许等真实节拍。"""

    def test_scanner_sees_enough_files(self):
        """扫描器至少要摸到 50 个测试文件，否则说明路径/过滤写错了。"""
        files = list(iter_candidate_files())
        self.assertGreater(len(files), 50,
                           "只扫到 %d 个测试文件，疑似 TESTS_DIR/SKIP 配置错误"
                           % len(files))

    def test_no_slow_literal_wait_in_tests(self):
        """tests/ 内不得出现长字面量等待（sleep>1s 或 timeout>30s）。"""
        offenders = []
        for path in iter_candidate_files():
            relpath = os.path.relpath(path, TESTS_DIR).replace(os.sep, "/")
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                offenders.extend(find_slow_waits(f.read(), relpath))
        self.assertEqual([], offenders,
                         "发现 %d 处长等待（改用 patch 降节拍，"
                         "或在同行注明 '%s: 原因'）：\n%s"
                         % (len(offenders), ALLOW_MARK,
                            "\n".join("  " + o for o in offenders)))

    def test_detector_catches_synthetic_waits(self):
        """自证：合成代码里的 sleep/wait/join 必须被抓到，正常等待不报。"""
        bad = (
            "import time\n"
            "import threading\n"
            "def f(ev, th):\n"
            "    time.sleep(300)\n"
            "    ev.wait(120)\n"
            "    th.join(timeout=2)\n"
            "    ev.wait(0.05)\n"
            "    ev.wait(timeout=10)\n"
        )
        hits = find_slow_waits(bad, "synthetic.py")
        self.assertEqual(2, len(hits), hits)
        self.assertTrue(any("sleep(300)" in h for h in hits), hits)
        self.assertTrue(any("wait(120)" in h for h in hits), hits)
        self.assertFalse(any("wait(0.05)" in h for h in hits), hits)
        self.assertFalse(any("join(2)" in h for h in hits), hits)

    def test_allow_mark_exempts_line(self):
        """同行注明 slow-wait-ok 的行被豁免。"""
        src = "import time\ntime.sleep(3)  # slow-wait-ok: 等待外部进程退出\n"
        self.assertEqual([], find_slow_waits(src, "synthetic.py"))


if __name__ == "__main__":
    unittest.main()
