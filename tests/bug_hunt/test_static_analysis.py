"""test_static_analysis.py — 静态分析自动化测试

在 unittest discover 时自动运行全部 5 个 AST 检查器。
ERROR 级别的发现会导致测试失败；WARNING/INFO 只记录到 stderr，不阻塞流程。

已知误报:
  - `tests/__init__.py` 使用相对导入 `from .test_base import ...`，
    importlib 在包外无法解析，但运行时通过 unittest 包发现机制正常工作。
"""

import unittest
import sys

from tests.bug_hunt.static_analyzer import run_all_checkers


_KNOWN_FALSE_POSITIVES: set[str] = {
    "tests/__init__.py:6:0 - 无法导入模块 'test_base'",
}
"""已知误报集合。因模块路径、相对导入等静态分析无法消除的合法模式。
格式为 finding 字符串中 `[ERROR]` 之后的部分。"""


def _filter_false_positives(findings: list[str]) -> list[str]:
    """过滤掉已知误报。"""
    filtered: list[str] = []
    for f in findings:
        # 去掉 [ERROR] 前缀后与误报集合对比
        after_prefix = f.split("]", 1)[-1].strip() if f.startswith("[") else f
        if after_prefix in _KNOWN_FALSE_POSITIVES:
            continue
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
