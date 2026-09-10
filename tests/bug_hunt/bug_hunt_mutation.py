#!/usr/bin/env python3
"""
bug_hunt_mutation.py — 变异测试工具

对生产 .py 文件做单个变异，运行所有测试检测测试是否能捕获变异。
输出未捕获变异（潜在 BUG）。

工作原理：
  1. 解析目标文件的 AST，找到所有可变异的位置（布尔值、运算符、条件、异常处理等）
  2. 随机选择最多 MAX_MUTATIONS_PER_FILE 个变异点
  3. 对每个变异点：备份原文 → 应用变异 → 运行测试 → 恢复原文
  4. 输出测试未捕获的变异（测试盲区 = 潜在 BUG）

支持的变异操作：
  1. bool_flip      — True ↔ False 翻转
  2. logical_op     — and ↔ or 替换
  3. compare_op     — == ↔ !=, > ↔ >=, < ↔ <= 替换
  4. arith_op       — + ↔ -, * ↔ / 替换（仅在数字上下文）
  5. negate_cond    — if cond → if not cond 条件取反
  6. remove_try     — 删除 try 结构，仅保留 try 块体
  7. return_none    — return expr → return None 返回值清零
  8. remove_except  — 用 pass 替换 except 块内容

用法：
  python bug_hunt_mutation.py

依赖：Python 3.9+（使用 ast.unparse），零外部依赖。
"""

import ast
import os
import re
import sys
import shutil
import subprocess
import time
import random

# =========================================================================
# 配置
# =========================================================================

# 目标文件（按行数从少到多排列）
TARGET_FILES = [
    "auth.py",
    "query_executor.py",
    "export.py",
    "config_db.py",
    "config.py",
    "report.py",
]

# 每个文件最多尝试的变异数
MAX_MUTATIONS_PER_FILE = 20

# 每个变异测试超时（秒）
TIMEOUT_SECONDS = 30

# 测试目录
TESTS_DIR = "tests/"


# =========================================================================
# 工具函数
# =========================================================================


def _get_python():
    """获取 venv 中的 Python 解释器路径。

    优先使用项目虚拟环境中的 Python，确保依赖正确加载。
    """
    venv_python = os.path.join("venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def _pos_to_offset(source: str, lineno: int, col_offset: int) -> int:
    """将 (lineno, col_offset) 转换为源字符串中的字节偏移量。

    lineno 从 1 开始计数，col_offset 从 0 开始计数。
    返回 0-based 字节偏移量，可直接用于 source[start:end] 切片。
    """
    lines = source.splitlines(keepends=True)
    offset = 0
    for i in range(lineno - 1):
        if i < len(lines):
            offset += len(lines[i])
    return offset + col_offset


def _source_range(source: str, node: ast.AST):
    """返回 AST 节点的 (start_offset, end_offset) 字节偏移量。"""
    start = _pos_to_offset(source, node.lineno, node.col_offset)
    end = _pos_to_offset(source, node.end_lineno, node.end_col_offset)
    return start, end


def _apply_mutation(source: str, mutation: dict) -> str:
    """在源字符串上应用单个变异，返回变异后的完整源码。"""
    data = mutation["data"]
    start = data["start"]
    end = data["end"]
    new_text = data["new_text"]
    return source[:start] + new_text + source[end:]


def _validate_source(source: str) -> bool:
    """验证源码是否能通过语法检查。"""
    try:
        ast.parse(source)
        return True
    except SyntaxError as e:
        return False


# =========================================================================
# 变异收集器
# =========================================================================


def collect_mutations(source: str, filepath: str) -> list:
    """收集指定源文件中所有可变异的位置。

    返回列表，每个元素是字典：
        lineno: 行号（int）
        type: 变异类型名称（str）
        description: 人类可读的描述（str）
        data: {"start": int, "end": int, "new_text": str}
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    collector = _MutationCollector(source, filepath)
    collector.visit(tree)
    return collector.mutations


class _MutationCollector(ast.NodeVisitor):
    """AST 遍历器，收集源文件中所有可变异位置。

    每种 visit_* 方法负责搜集一类变异点，记录行号、描述和替换数据。
    """

    def __init__(self, source: str, filepath: str):
        self.source = source
        self.filepath = filepath
        self.mutations = []

    def _add(self, lineno: int, mut_type: str, description: str, data: dict):
        """添加一个变异点。"""
        self.mutations.append({
            "lineno": lineno,
            "type": mut_type,
            "description": description,
            "data": data,
        })

    # ------------------------------------------------------------------
    # 1. 布尔字面量翻转  True ↔ False
    # ------------------------------------------------------------------

    def visit_Constant(self, node: ast.Constant):
        """找到所有布尔常量并记录翻转变异。"""
        if isinstance(node.value, bool):
            old_text = "True" if node.value else "False"
            new_text = "False" if node.value else "True"
            start, end = _source_range(self.source, node)
            self._add(
                node.lineno, "bool_flip",
                f"翻转 {old_text} → {new_text}",
                {"start": start, "end": end, "new_text": new_text},
            )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 2. 逻辑运算符替换  and ↔ or
    # ------------------------------------------------------------------

    def visit_BoolOp(self, node: ast.BoolOp):
        """找到所有 BoolOp 中的 and/or，记录替换变异。

        对于 a and b and c 这样的多操作数表达式，每个运算符独立记录。
        """
        op_name = "and" if isinstance(node.op, ast.And) else "or"
        new_op = "or" if op_name == "and" else "and"
        values = node.values

        for i in range(len(values) - 1):
            # 操作符位于 values[i] 结尾和 values[i+1] 开头之间
            left_end = _pos_to_offset(self.source,
                                      values[i].end_lineno, values[i].end_col_offset)
            right_start = _pos_to_offset(self.source,
                                         values[i + 1].lineno, values[i + 1].col_offset)
            between = self.source[left_end:right_start]

            # 在间隔文本中查找操作符关键词（注意单词边界）
            m = re.search(r'\b(and|or)\b', between)
            if m and m.group(1) == op_name:
                op_start = left_end + m.start()
                op_end = left_end + m.end()
                self._add(
                    node.lineno, "logical_op",
                    f"替换 {op_name} → {new_op}",
                    {"start": op_start, "end": op_end, "new_text": new_op},
                )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 3. 比较运算符替换  ==↔!=, >↔>=, <↔<=
    # ------------------------------------------------------------------

    def visit_Compare(self, node: ast.Compare):
        """找到所有比较运算符，记录替换变异。

        支持链式比较（a == b == c）中的每个运算符独立记录。
        """
        swap_map = {
            ast.Eq: ("==", "!="),
            ast.NotEq: ("!=", "=="),
            ast.Gt: (">", ">="),
            ast.GtE: (">=", ">"),
            ast.Lt: ("<", "<="),
            ast.LtE: ("<=", "<"),
        }

        left = node.left
        for i, op in enumerate(node.ops):
            op_type = type(op)
            if op_type not in swap_map:
                continue

            old_op_str, new_op_str = swap_map[op_type]

            # 左边界：前一个表达式或 left 的结尾
            if i == 0:
                left_end = _pos_to_offset(self.source,
                                          left.end_lineno, left.end_col_offset)
            else:
                left_end = _pos_to_offset(self.source,
                                          node.comparators[i - 1].end_lineno,
                                          node.comparators[i - 1].end_col_offset)

            # 右边界：当前 comparators[i] 的开头
            right_start = _pos_to_offset(self.source,
                                         node.comparators[i].lineno,
                                         node.comparators[i].col_offset)

            # 在间隔中查找操作符
            between = self.source[left_end:right_start]
            idx = between.find(old_op_str)
            if idx >= 0:
                op_start = left_end + idx
                op_end = op_start + len(old_op_str)
                self._add(
                    node.lineno, "compare_op",
                    f"替换 {old_op_str} → {new_op_str}",
                    {"start": op_start, "end": op_end, "new_text": new_op_str},
                )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 4. 算术运算符替换  +↔-, *↔/（仅数字上下文）
    # ------------------------------------------------------------------

    def visit_BinOp(self, node: ast.BinOp):
        """找到算术运算的 BinOp，记录替换变异。

        仅在操作数至少一个是数字常量时触发，避免字符串拼接误伤。
        """
        swap_map = {
            ast.Add: ("+", "-"),
            ast.Sub: ("-", "+"),
            ast.Mult: ("*", "/"),
            ast.Div: ("/", "*"),
        }

        op_type = type(node.op)
        if op_type not in swap_map:
            self.generic_visit(node)
            return

        # 数字上下文检测：至少一个操作数是数字常量
        is_num = False
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, (int, float)):
            is_num = True
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float)):
            is_num = True
        if not is_num:
            self.generic_visit(node)
            return

        old_op_str, new_op_str = swap_map[op_type]

        left_end = _pos_to_offset(self.source,
                                  node.left.end_lineno, node.left.end_col_offset)
        right_start = _pos_to_offset(self.source,
                                     node.right.lineno, node.right.col_offset)
        between = self.source[left_end:right_start]

        idx = between.find(old_op_str)
        if idx >= 0:
            op_start = left_end + idx
            op_end = op_start + len(old_op_str)
            self._add(
                node.lineno, "arith_op",
                f"替换 {old_op_str} → {new_op_str}",
                {"start": op_start, "end": op_end, "new_text": new_op_str},
            )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 5. 条件取反  if cond → if not cond
    # ------------------------------------------------------------------

    def visit_If(self, node: ast.If):
        """对 if 语句的条件部分添加 not。

        简单条件（Name/Attribute/Constant）不加括号，
        复杂条件自动加括号保证优先级正确。
        """
        cond_node = node.test
        cond_text = ast.get_source_segment(self.source, cond_node)
        if cond_text is None:
            self.generic_visit(node)
            return

        if isinstance(cond_node, (ast.Name, ast.Attribute, ast.Constant)):
            new_cond = f"not {cond_text}"
        else:
            new_cond = f"not ({cond_text})"

        start, end = _source_range(self.source, cond_node)
        self._add(
            node.lineno, "negate_cond",
            f"条件取反: if {cond_text} → if {new_cond}",
            {"start": start, "end": end, "new_text": new_cond},
        )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 6. 删除 try 结构（移除异常保护，保留 try 块体）
    # 8. 移除 except 块内容（用 pass 替换）
    # ------------------------------------------------------------------

    def visit_Try(self, node: ast.Try):
        """处理 try/except 相关的两种变异。

        变异 6：移除整个 try/except/else/finally，仅保留 try 块体（dedent 一阶）。
        变异 8：将每个 except handler 的 body 替换为 pass（异常静默）。
        """
        lines = self.source.splitlines(keepends=True)
        try_line = lines[node.lineno - 1]
        try_indent = len(try_line) - len(try_line.lstrip())

        # ========== 变异 6：移除 try 保护 ==========
        if node.body:
            # 收集 try 块体所有行（含中间空白/注释）
            body_indices = set()
            for stmt in node.body:
                for ln in range(stmt.lineno, stmt.end_lineno + 1):
                    body_indices.add(ln - 1)

            if body_indices:
                first_body = min(body_indices)
                last_body = max(body_indices)
                # 包含 first~last 之间的所有行（含空白）
                body_lines = lines[first_body:last_body + 1]

                # Dedent 到 try 关键字所在缩进级别
                # 计算 body 比 try 多缩进了多少
                sample_body_text = body_lines[0]
                body_indent_amount = len(sample_body_text) - len(sample_body_text.lstrip())
                dedent_steps = body_indent_amount - try_indent

                dedented_body = []
                for bline in body_lines:
                    if dedent_steps > 0 and bline[:dedent_steps].strip() == '':
                        dedented_body.append(bline[dedent_steps:])
                    else:
                        dedented_body.append(bline)

                # try 结构的字节范围（从 try: 行到 try 结构结束）
                # range(try_start_line, try_end_line) = range(lineno-1, end_lineno)
                # = 0-indexed 行 lineno-1 到 end_lineno-1 = 1-indexed 行 lineno 到 end_lineno
                try_start_line = node.lineno - 1    # 0-indexed
                try_end_line = node.end_lineno       # 仍为 1-indexed，作为 range 的 exclusive end

                start_offset = 0
                for i in range(try_start_line):
                    start_offset += len(lines[i])
                end_offset = start_offset
                for i in range(try_start_line, try_end_line):
                    end_offset += len(lines[i])

                new_body_text = ''.join(dedented_body)

                self._add(
                    node.lineno, "remove_try",
                    f"移除 try/except 保护（{len(node.handlers)} 个 handler）",
                    {"start": start_offset, "end": end_offset, "new_text": new_body_text},
                )

        # ========== 变异 8：用 pass 替换 except body ==========
        for handler in node.handlers:
            if not handler.body:
                continue

            # 查找 handler 行的缩进
            handler_line = lines[handler.lineno - 1]
            handler_indent = len(handler_line) - len(handler_line.lstrip())

            # 收集 handler body 的所有行
            body_indices = set()
            for stmt in handler.body:
                for ln in range(stmt.lineno, stmt.end_lineno + 1):
                    body_indices.add(ln - 1)

            if not body_indices:
                continue

            first_hb = min(body_indices)
            last_hb = max(body_indices)

            # handler body 的字节范围
            start_offset = 0
            for i in range(first_hb):
                start_offset += len(lines[i])
            end_offset = start_offset
            for i in range(first_hb, last_hb + 1):
                end_offset += len(lines[i])

            # pass 语句，缩进 = handler 缩进 + 4
            pass_indent = handler_indent + 4
            pass_text = " " * pass_indent + "pass\n"

            except_name = handler.type
            if except_name is not None:
                exc_name = ast.get_source_segment(self.source, except_name) or "Exception"
            else:
                exc_name = "bare except"

            self._add(
                handler.lineno, "remove_except",
                f"替换 except {exc_name} body 为 pass",
                {"start": start_offset, "end": end_offset, "new_text": pass_text},
            )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # 7. 返回值清零  return expr → return None
    # ------------------------------------------------------------------

    def visit_Return(self, node: ast.Return):
        """将 return 语句的返回值替换为 None。"""
        if node.value is None:
            return
        val_text = ast.get_source_segment(self.source, node.value)
        if val_text is None:
            return
        start, end = _source_range(self.source, node.value)
        self._add(
            node.lineno, "return_none",
            f"返回值清零: return {val_text} → return None",
            {"start": start, "end": end, "new_text": "None"},
        )


# =========================================================================
# 测试运行器
# =========================================================================


def _run_tests(python_path: str) -> dict:
    """运行完整的测试套件。

    返回：
        {"passed": bool, "output": str, "elapsed": float}
    """
    start = time.time()
    try:
        result = subprocess.run(
            [python_path, "-m", "unittest", "discover", "-s", TESTS_DIR, "-v"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        elapsed = time.time() - start
        # 返回码 0 = 全部通过
        passed = (result.returncode == 0)
        return {
            "passed": passed,
            "output": result.stdout + result.stderr,
            "elapsed": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "passed": False,
            "output": f"[超时 {TIMEOUT_SECONDS}s]",
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "passed": False,
            "output": f"[错误] {e}",
            "elapsed": elapsed,
        }


# =========================================================================
# 主流程
# =========================================================================


def _try_mutation(filepath: str, source: str, mutation: dict) -> str:
    """尝试单个变异：备份 → 写入变异文件 → 运行测试 → 恢复。

    返回值：'caught' | 'uncaught' | 'error:...'
    """
    # 准备变异后的源码
    mutated = _apply_mutation(source, mutation)

    # 验证变异后源码是否合法
    if not _validate_source(mutated):
        return "error:变异后语法错误"

    # 原子操作：备份 → 写入 → 测试 → 恢复
    backup_path = filepath + ".bak"
    shutil.copy2(filepath, backup_path)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(mutated)

        python = _get_python()
        test_result = _run_tests(python)

    finally:
        # 立即恢复原始文件
        shutil.copy2(backup_path, filepath)
        os.remove(backup_path)

    if test_result["passed"]:
        return "uncaught"
    else:
        return "caught"


def _scan_file(filepath: str) -> list:
    """扫描一个文件并对其执行所有变异测试。

    返回：未捕获变异列表 [{"filename":..., "lineno":..., "description":...}, ...]
    """
    basename = os.path.basename(filepath)
    if not os.path.exists(filepath):
        print(f"  文件不存在: {filepath}，跳过")
        return []

    # 读取源码
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    # 收集变异点
    mutations = collect_mutations(source, filepath)
    if not mutations:
        print(f"  → 没有可变异的位置")
        return []

    # 随机选择最多 MAX_MUTATIONS_PER_FILE 个
    if len(mutations) > MAX_MUTATIONS_PER_FILE:
        sampled = random.sample(mutations, MAX_MUTATIONS_PER_FILE)
    else:
        sampled = mutations

    print(f"  → 找到 {len(mutations)} 个可变异位置，选取 {len(sampled)} 个进行测试")

    uncaught = []
    for idx, mutation in enumerate(sampled, 1):
        desc = mutation["description"]
        sys.stdout.write(f"  [{idx}/{len(sampled)}] 行 {mutation['lineno']}: {desc} ... ")
        sys.stdout.flush()

        result = _try_mutation(filepath, source, mutation)

        if result == "uncaught":
            print("OK 测试通过（未捕获！）")
            uncaught.append(mutation)
        elif result == "caught":
            print("FAIL 测试失败（已捕获）")
        else:
            print(f"ERR {result}")

    return uncaught


def main():
    """主入口。"""
    # 环境检查
    python = _get_python()
    print(f"Python: {python}")
    print(f"工作目录: {os.getcwd()}")
    print(f"测试目录: {TESTS_DIR}")

    if not os.path.isdir(TESTS_DIR):
        print(f"错误：测试目录 {TESTS_DIR} 不存在", file=sys.stderr)
        return 1

    # 前置检查：运行一次测试确认初始全部通过
    print("\n" + "=" * 60)
    print("前置检查：运行初始测试...")
    init_result = _run_tests(python)
    if init_result["passed"]:
        print(f"  初始测试全部通过（{init_result['elapsed']:.1f}s）")
    else:
        print(f"  警告：初始测试未全部通过（{init_result['elapsed']:.1f}s）")
        print("  继续执行变异测试，但结果可能包含误报")

    # 依次扫描每个目标文件
    all_uncaught = []
    for filename in TARGET_FILES:
        filepath = os.path.join(os.getcwd(), filename)
        print("\n" + "=" * 60)
        print(f"扫描文件: {filename}")
        print("=" * 60)

        uncaught = _scan_file(filepath)
        # 为每个未捕获变异添加 filepath 信息
        for m in uncaught:
            m["filepath"] = filepath
        all_uncaught.extend(uncaught)

    # =============================================================
    # 输出汇总——仅未捕获变异
    # =============================================================
    print("\n" + "=" * 60)
    print("变异测试汇总")
    print("=" * 60)

    if all_uncaught:
        print(f"\n未捕获变异（潜在 BUG）: {len(all_uncaught)} 个")
        print()
        for m in all_uncaught:
            print(f"  [MUTATION] {os.path.basename(m['filepath'])}:{m['lineno']}: {m['description']}，测试通过（未捕获！）")
    else:
        print("\n没有未捕获的变异——测试覆盖良好！")

    return 0 if not all_uncaught else 1


if __name__ == "__main__":
    sys.exit(main())
