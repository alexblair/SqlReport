"""test_static_analysis.py — 静态分析自动化测试

在 unittest discover 时自动运行全部 5 个 AST 检查器。
ERROR 级别的发现会导致测试失败；WARNING/INFO 只记录到 stderr，不阻塞流程。

已知误报:
  - `tests/__init__.py` 使用相对导入 `from .test_base import ...`，
    importlib 在包外无法解析，但运行时通过 unittest 包发现机制正常工作。
"""

import unittest
import sys

import os
import shutil
import tempfile

from tests.bug_hunt.static_analyzer import (
    PROJECT_ROOT, ImportChecker, UndefinedNameChecker, run_all_checkers,
)


_KNOWN_FALSE_POSITIVES: set[str] = {
    # tests/__init__.py 使用相对导入 `from .test_base import ...`，静态分析在包外
    # 无法解析；unittest 包发现机制可正常解析。import 行号随源码变化，用通配忽略行号。
    "tests/__init__.py:: - 无法导入模块 'test_base'",
    # tests/integration/__init__.py 同样使用包内相对导入，unittest 包发现
    # 机制可正常解析，静态分析在包外解析时误报
    "tests/integration/__init__.py:: - 无法导入模块 'base'",
}
"""已知误报集合。因模块路径、相对导入等静态分析无法消除的合法模式。
格式为 finding 字符串中 `[ERROR]` 之后的部分。
以 `::` 结尾的条目作为通配前缀匹配（忽略行号列号），用于非生产代码目录。"""

_WILDCARD_FALSE_POSITIVES: set[str] = {
    # docs/tools/ 不是生产代码，yaml 是延迟导入，非必需依赖
    "docs/tools/capture.py:: - 无法导入模块 'yaml'",
}
"""已知误报集合。因模块路径、相对导入等静态分析无法消除的合法模式。
格式为 finding 字符串中 `[ERROR]` 之后的部分。"""


def _filter_false_positives(findings: list[str]) -> list[str]:
    """过滤掉已知误报。"""

    def _is_known(fp: str, s: str) -> bool:
        """s 是否匹配已知误报（精确或通配）。"""
        if s == fp:
            return True
        # 通配匹配：fp 格式 "filepath::message_text"，忽略行号列号
        if "::" in fp:
            fpath, msg = fp.split("::", 1)
            if s.startswith(fpath + ":") and msg in s:
                return True
        return False

    filtered: list[str] = []
    for f in findings:
        after_prefix = f.split("]", 1)[-1].strip() if f.startswith("[") else f
        matched_any = False
        for fp in _KNOWN_FALSE_POSITIVES | _WILDCARD_FALSE_POSITIVES:
            if _is_known(fp, after_prefix):
                matched_any = True
                break
        if not matched_any:
            filtered.append(f)
    return filtered


class TestStaticAnalysis(unittest.TestCase):
    """静态分析测试：运行所有检查器，ERROR 级别发现视为测试失败。

    每次运行先清空检查器状态，然后对生产代码做全量静态扫描。
    """

    @classmethod
    def setUpClass(cls):
        cls.findings = run_all_checkers()

    def test_no_syntax_errors(self):
        """语法检查：不允许任何 .py 文件有语法错误。"""
        errors = [f for f in self.findings["errors"]
                  if "语法错误" in f]
        if errors:
            self.fail("发现语法错误:\n" + "\n".join(errors))

    def test_no_import_errors(self):
        """导入检查：不允许任何无法解析的 import 语句。"""
        errors = [f for f in self.findings["errors"]
                  if "无法导入" in f]
        errors = _filter_false_positives(errors)
        if errors:
            self.fail("发现导入错误:\n" + "\n".join(errors))

    def test_no_other_errors(self):
        """其他 ERROR 发现也视为测试失败。"""
        non_syntax_import = [f for f in self.findings["errors"]
                             if "语法错误" not in f
                             and "无法导入" not in f]
        if non_syntax_import:
            self.fail("发现其他 ERROR:\n" + "\n".join(non_syntax_import))

    def test_warnings_reported(self):
        """报告 WARNING 发现数量（不失败）。"""
        if self.findings["warnings"]:
            print(f"\n  [静态分析] WARNING 发现 ({len(self.findings['warnings'])} 个):",
                  file=sys.stderr)
            for w in self.findings["warnings"]:
                print(f"    {w}", file=sys.stderr)

    def test_infos_reported(self):
        """报告 INFO 发现数量（不失败）。"""
        if self.findings["infos"]:
            print(f"\n  [静态分析] INFO 发现 ({len(self.findings['infos'])} 个):",
                  file=sys.stderr)
            for info in self.findings["infos"]:
                print(f"    {info}", file=sys.stderr)


class TestAnalyzerFalsePositiveRegressions(unittest.TestCase):
    """锁定 2026-10-20 修掉的静态分析误报。

    背景：`__builtins__` 在本仓库加载器下是 dict，`dir(dict)` 不含
    `int/len/str`，曾一次性误报 6558 条 WARNING，把真 ERROR 淹在日志里；
    相对导入不解析又多报 8 条 ERROR。改完必须防止回退。
    """

    def _write(self, source: str) -> str:
        d = tempfile.mkdtemp(prefix="sa_regress_")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "sample_mod.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write(source)
        return p

    def test_builtin_names_are_not_reported_undefined(self):
        p = self._write("def f(x):\n    return len(x) + int('1') + str(x)\n")
        checker = UndefinedNameChecker()
        checker.check([p])
        self.assertEqual(checker.findings, [])

    def test_real_undefined_name_still_reported(self):
        p = self._write("def f():\n    return nope_xyz_20261020 + 1\n")
        checker = UndefinedNameChecker()
        checker.check([p])
        self.assertTrue(any("nope_xyz_20261020" in f for f in checker.findings),
                        f"真未定义名称必须仍被报出，实际: {checker.findings}")

    def test_module_magic_and_global_decl_are_available(self):
        p = self._write(
            "STATE = None\n\ndef f():\n    global STATE\n"
            "    STATE = __file__, __name__\n"
        )
        checker = UndefinedNameChecker()
        checker.check([p])
        self.assertEqual(checker.findings, [])

    def test_relative_import_is_resolved(self):
        init_py = os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.pardir, "__init__.py"))
        checker = ImportChecker(project_root=PROJECT_ROOT)
        checker.check([init_py])
        bad = [f for f in checker.findings if "无法导入" in f]
        self.assertEqual(bad, [], f"相对导入应可解析，实际: {bad}")
