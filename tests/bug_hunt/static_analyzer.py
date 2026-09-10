#!/usr/bin/env python3
"""
static_analyzer.py — Python 静态分析工具模块，自动发现代码中的 BUG

继承自 bug_hunt_static.py，作为可导入模块供 test_static_analysis.py 使用。

包含检查器:
  - SyntaxChecker:       语法错误检查（py_compile）
  - ImportChecker:       导入错误检查（importlib + AST）
  - UndefinedNameChecker: 未定义名称检查（AST 作用域分析）
  - UnusedImportChecker:  未使用导入检查（AST 引用计数）
  - DocstringChecker:     文档字符串缺失检查（AST）

导出:
  - run_all_checkers(project_root) -> dict[str, list[str]]
    — 运行所有检查器，返回 {checker_name: [findings]}
  - 5 个 BugFinder 子类可直接实例化使用
"""

import ast
import os
import re
import sys
import py_compile
import importlib


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
"""通过 `tests/bug_hunt/static_analyzer.py` → `tests/` → 项目根路径。"""

IGNORE_DIRS: set[str] = {"venv", ".codegraph", "__pycache__", ".git",
                          ".opencode", ".tmp"}
"""递归扫描 .py 文件时跳过的目录名。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def get_py_files(project_root: str = PROJECT_ROOT) -> list[str]:
    """递归收集 project_root 下所有 .py 文件，跳过 IGNORE_DIRS。

    Args:
        project_root: 项目绝对路径，默认自动推导。

    Returns:
        排序后的 .py 文件绝对路径列表。
    """
    py_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                py_files.append(os.path.join(dirpath, fn))
    return sorted(py_files)


def get_rel_path(filepath: str, project_root: str = PROJECT_ROOT) -> str:
    """返回 filepath 相对于 project_root 的路径。"""
    return os.path.relpath(filepath, project_root)


def is_empty_or_comments(source_lines: list[str]) -> bool:
    """判断源文件是否只包含空行和注释（含 shebang 行）。"""
    for line in source_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return False
    return True


# ---------------------------------------------------------------------------
# 检查器基类
# ---------------------------------------------------------------------------

class BugFinder:
    """所有检查器的基类。

    职责:
      - 持有 project_root 路径
      - 提供 report() 方法统一记录发现的问题
      - 子类实现 check() 方法执行具体检查
    """

    def __init__(self, project_root: str = PROJECT_ROOT):
        self.project_root: str = project_root
        self.findings: list[str] = []

    def report(self, level: str, filepath: str, lineno: int,
               col_offset: int, message: str) -> None:
        """记录一条发现到 findings 列表。

        Args:
            level: 日志级别（ERROR / WARNING / INFO）。
            filepath: 文件绝对路径（会被转为相对路径）。
            lineno: 行号（从 1 开始）。
            col_offset: 列号（从 0 开始）。
            message: 描述信息。
        """
        rel_path = get_rel_path(filepath, self.project_root)
        self.findings.append(
            f"[{level}] {rel_path}:{lineno}:{col_offset} - {message}"
        )

    def check(self, py_files: list[str]) -> None:
        """运行本检查器的检查逻辑。由子类实现。"""
        raise NotImplementedError

    def clear(self) -> None:
        """清空 findings，用于重复运行检查器。"""
        self.findings.clear()


# ---------------------------------------------------------------------------
# SyntaxChecker — 语法错误检查
# ---------------------------------------------------------------------------

class SyntaxChecker(BugFinder):
    """使用 py_compile.compile() 检查所有 .py 文件的语法正确性。"""

    def check(self, py_files: list[str]) -> None:
        for fp in py_files:
            try:
                py_compile.compile(fp, doraise=True)
            except py_compile.PyCompileError as exc:
                msg = str(exc)
                lineno = 0
                m = re.search(r'line\s+(\d+)', msg)
                if m:
                    lineno = int(m.group(1))
                self.report("ERROR", fp, lineno, 0, f"语法错误: {msg}")


# ---------------------------------------------------------------------------
# ImportChecker — 导入错误检查
# ---------------------------------------------------------------------------

class ImportChecker(BugFinder):
    """检查文件中每个导入语句是否可成功解析。

    使用 importlib 实际尝试导入模块，并验证 from X import Y 中 Y 是否
    在 X 模块中存在。通过将项目根目录临时加入 sys.path 来支持本地模块。
    """

    def __init__(self, project_root: str = PROJECT_ROOT):
        super().__init__(project_root)
        self._module_cache: dict[str, tuple[bool, object | None]] = {}

    def _import_module(self, module_name: str) -> tuple[bool, object | None]:
        """尝试导入模块并缓存结果。"""
        if module_name in self._module_cache:
            return self._module_cache[module_name]
        try:
            mod = importlib.import_module(module_name)
            self._module_cache[module_name] = (True, mod)
            return True, mod
        except (ImportError, Exception):
            self._module_cache[module_name] = (False, None)
            return False, None

    def check(self, py_files: list[str]) -> None:
        sys.path.insert(0, self.project_root)
        try:
            for fp in py_files:
                self._check_file(fp)
        finally:
            sys.path.pop(0)

    def _check_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=filepath)
            except SyntaxError:
                return
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import_node(filepath, node, alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    self._check_from_import(filepath, node, module,
                                            alias.name, alias.asname or alias.name)

    def _check_import_node(self, filepath: str, node: ast.AST,
                           module_name: str) -> None:
        """检查 'import X' 或 'import X.Y.Z' 语句。"""
        top_module = module_name.split(".")[0]
        success, _ = self._import_module(top_module)
        if not success:
            self.report("ERROR", filepath, node.lineno, node.col_offset,
                        f"无法导入模块 '{module_name}'")

    def _check_from_import(self, filepath: str, node: ast.AST,
                           module: str, name: str,
                           imported_name: str) -> None:
        """检查 'from X import Y' 语句。"""
        if not module:
            return
        success, mod = self._import_module(module)
        if not success:
            self.report("ERROR", filepath, node.lineno, node.col_offset,
                        f"无法导入模块 '{module}'")
            return
        if mod is not None and not hasattr(mod, name):
            self.report("WARNING", filepath, node.lineno, node.col_offset,
                        f"模块 '{module}' 中没有名称 '{name}'"
                        f"（导入为 {imported_name}）")


# ---------------------------------------------------------------------------
# UndefinedNameChecker — 未定义名称检查
# ---------------------------------------------------------------------------

class UndefinedNameChecker(BugFinder):
    """检查函数/方法体中是否存在使用前未定义的名称。

    通过 AST 分析，收集每个作用域内的已定义名称，
    然后对每个 Load 类型的 Name 节点验证其定义存在性。
    """

    def __init__(self, project_root: str = PROJECT_ROOT):
        super().__init__(project_root)
        self._builtins: set[str] = set(dir(__builtins__))

    def check(self, py_files: list[str]) -> None:
        for fp in py_files:
            self._check_file(fp)

    def _check_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=filepath)
            except SyntaxError:
                return
        module_globals = self._collect_module_globals(tree)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_func_def(node, module_globals, filepath, inherited=set())
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._check_func_def(
                            item, module_globals, filepath,
                            inherited={node.name}
                        )

    @staticmethod
    def _collect_module_globals(tree: ast.Module) -> set[str]:
        """收集模块级定义的所有名称。"""
        names: set[str] = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    names.update(_extract_store_names(target))
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    names.add(stmt.target.id)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    names.add(alias.asname or alias.name)
        return names

    @staticmethod
    def _get_func_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        params: set[str] = set()
        for arg in node.args.args:
            params.add(arg.arg)
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        for arg in node.args.kwonlyargs:
            params.add(arg.arg)
        for arg in node.args.posonlyargs:
            params.add(arg.arg)
        return params

    @staticmethod
    def _collect_func_body_defs(
        node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        defined: set[str] = set()
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                defined.add(child.name)
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                defined.add(child.id)
            if isinstance(child, ast.ExceptHandler) and child.name:
                defined.add(child.name)
        return defined

    def _check_func_def(self, node, module_globals, filepath, inherited):
        params = self._get_func_params(node)
        body_defs = self._collect_func_body_defs(node)
        global_names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                global_names.update(child.names)
        available = (params | body_defs | module_globals |
                     self._builtins | inherited)
        available.difference_update(global_names)
        self._check_load_names(node, available, filepath)
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_inherited = inherited | params | body_defs | module_globals
                self._check_func_def(child, module_globals, filepath,
                                     child_inherited)
            elif isinstance(child, ast.ClassDef):
                for item in child.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        item_inherited = (inherited | params | body_defs |
                                          module_globals)
                        self._check_func_def(item, module_globals, filepath,
                                             item_inherited)

    def _check_load_names(self, node, available, filepath):
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id not in available:
                    self.report("WARNING", filepath, child.lineno,
                                child.col_offset,
                                f"可能未定义的名称 '{child.id}'")


def _extract_store_names(node: ast.AST) -> set[str]:
    """从赋值目标 AST 节点递归提取所有变量名。"""
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            names.update(_extract_store_names(elt))
    elif isinstance(node, ast.Starred):
        names.update(_extract_store_names(node.value))
    return names


# ---------------------------------------------------------------------------
# UnusedImportChecker — 未使用导入检查
# ---------------------------------------------------------------------------

class UnusedImportChecker(BugFinder):
    """检查文件中是否存在未被引用的导入语句。"""

    def check(self, py_files: list[str]) -> None:
        for fp in py_files:
            self._check_file(fp)

    def _check_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=filepath)
            except SyntaxError:
                return
        imports: dict[str, tuple[ast.AST, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name.split(".")[0]
                    imports[local_name] = (node, alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    full = f"{node.module or ''}.{alias.name}"
                    imports[local_name] = (node, full)
        exported = _collect_all_names(tree)
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
        for name, (node, orig_name) in imports.items():
            if name not in used_names and name not in exported:
                self.report("INFO", filepath, node.lineno, node.col_offset,
                            f"未使用的导入 '{orig_name}'")


def _collect_all_names(tree: ast.Module) -> set[str]:
    """从 __all__ 列表定义中提取导出的名称。"""
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(stmt.value, (ast.List, ast.Tuple)):
                        return {
                            el.value for el in stmt.value.elts
                            if isinstance(el, ast.Constant)
                            and isinstance(el.value, str)
                        }
    return set()


# ---------------------------------------------------------------------------
# DocstringChecker — docstring 缺失检查
# ---------------------------------------------------------------------------

class DocstringChecker(BugFinder):
    """检查模块、类、函数/方法是否缺少文档字符串。"""

    def check(self, py_files: list[str]) -> None:
        for fp in py_files:
            self._check_file(fp)

    def _check_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
            try:
                tree = ast.parse(source, filename=filepath)
            except SyntaxError:
                return
        source_lines = source.split("\n")
        if is_empty_or_comments(source_lines):
            return
        if not ast.get_docstring(tree):
            self.report("INFO", filepath, 1, 0, "缺少模块级 docstring")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    self.report("INFO", filepath, node.lineno,
                                node.col_offset,
                                f"类 '{node.name}' 缺少 docstring")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    self.report("INFO", filepath, node.lineno,
                                node.col_offset,
                                f"函数/方法 '{node.name}' 缺少 docstring")


# ---------------------------------------------------------------------------
# 统一运行入口
# ---------------------------------------------------------------------------

def run_all_checkers(project_root: str = PROJECT_ROOT,
                     py_files: list[str] | None = None
                     ) -> dict[str, list[str]]:
    """运行全部 5 个检查器，返回按级别分组的发现。

    Args:
        project_root: 项目根路径，默认自动推导。
        py_files: 要检查的 .py 文件列表，默认自动收集。

    Returns:
        {"errors": [...], "warnings": [...], "infos": [...]}
    """
    if py_files is None:
        py_files = get_py_files(project_root)

    checkers: list[BugFinder] = [
        SyntaxChecker(project_root),
        ImportChecker(project_root),
        UndefinedNameChecker(project_root),
        UnusedImportChecker(project_root),
        DocstringChecker(project_root),
    ]

    for checker in checkers:
        try:
            checker.check(py_files)
        except Exception as exc:
            print(f"[INTERNAL] 检查器 {type(checker).__name__} 执行异常: {exc}",
                  file=sys.stderr)

    by_level: dict[str, list[str]] = {"errors": [], "warnings": [], "infos": []}
    for checker in checkers:
        for finding in checker.findings:
            if finding.startswith("[ERROR]"):
                by_level["errors"].append(finding)
            elif finding.startswith("[WARNING]"):
                by_level["warnings"].append(finding)
            elif finding.startswith("[INFO]"):
                by_level["infos"].append(finding)
    return by_level
