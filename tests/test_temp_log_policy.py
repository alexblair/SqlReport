"""临时产物引用门禁 —— 禁止文档把「随时会被清空的临时文件」钉成长期引用（AGENTS.md 硬性 #14）。

为什么需要门禁：
- `run-logs/` 与 `perf-logs/` 是**临时产物目录**（本环境 `/tmp` 会被清空，故产物落仓库内
  已 gitignore 的目录），由 `scripts/agent/cleanup_tmp.py --apply` 在任务收尾时统一清理。
- 文档里一旦写下具体文件名（如 `perf-logs/t4b-1.log`），清理后该引用就变成**断链**：
  后来者按图索骥找不到文件，也无法复现结论。
- 因此：**结论 + 数值 + 复现命令**必须写进 `docs/compose/reports/`（长期依据），
  临时目录只允许以目录 / 占位符形态被引用。

被测对象由 `_load_docs()` 单独负责读盘，判定逻辑 `_violations()` 是纯函数——
`tests/bug_hunt/gate_redproof.py` 靠**内存变异**（monkeypatch `_load_docs`）证明
本门禁真的会红，不需要改写磁盘文件。
"""
import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只匹配「临时目录 + 其后片段」；左侧边界排除 `my-run-logs/` 这类同后缀目录。
# 片段字符集覆盖文件名/占位符（`<>`、`*`）与非 ASCII（中文名），但止于空白/引号/括号/句读——
# 若把空白也吞进来，紧跟其后的整条命令行会被并入片段，白名单形态（`probe/verify.debug.json`）反而失效。
REF_RE = re.compile(
    r"(?<![0-9A-Za-z_/\-])(?:run-logs|perf-logs)/"
    r"([^\s`\"'()\[\]{}|;，。、；：！？（）【】「」『』…—]*)"
)

# 白名单：**确有长期价值**、不随清理消失的少数例外（至多 3 条，只降不升）。
ALLOWED: tuple[tuple[str, str], ...] = (
    ("bench-credentials.txt", "压测账号凭据文件名，只作为名称约定出现，与产物生命周期无关"),
    ("probe/verify.debug.json", "前端探针的输出名约定，文档引用的是约定而非某次产物"),
)
_ALLOWED_SEGMENTS = {seg for seg, _reason in ALLOWED}

_SCAN_ROOTS = ("AGENTS.md", "MEMORY.md")


def _maybe_read(path: str):
    """读文本；文件不存在返回 None（缺失文件 = 无该引用，不算违规）。"""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _load_docs() -> dict:
    """读入被测文档（唯一读盘入口，便于门禁自证时内存变异）。

    扫描集：`AGENTS.md`、`MEMORY.md`、`docs/**/*.md`、`learn/**/*.md`。
    容错：缺失的文件直接从判定集合里去掉，这样在裁剪过的检出上也不会 FileNotFoundError。
    """
    docs: dict = {}
    for rel in _SCAN_ROOTS:
        text = _maybe_read(os.path.join(_ROOT, rel))
        if text is not None:
            docs[rel] = text
    for base in ("docs", "learn"):
        root = os.path.join(_ROOT, base)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in sorted(filenames):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(dirpath, name)
                text = _maybe_read(path)
                if text is not None:
                    docs[os.path.relpath(path, _ROOT)] = text
    return docs


def _ref_is_illegal(segment: str, line: str, end: int) -> bool:
    """判断一次命中是否为「具体的临时产物引用」（纯判定，无副作用）。"""
    if "<" in segment or "*" in segment:      # 占位符形态：不指向某个具体文件
        return False
    if segment == "" or segment.endswith("/") or segment.endswith("-"):
        return False                          # 纯目录 / 未写完的路径
    if end < len(line) and line[end] == "$":  # `run-logs/$D/` 之类的变量拼接
        return False
    if "." not in segment.rsplit("/", 1)[-1]:
        return False                          # 最后一段不含 `.` = 目录引用
    if segment in _ALLOWED_SEGMENTS:          # 长期有效的名称约定
        return False
    return True


def _violations(docs: dict) -> list:
    """返回违规清单 `(文件, 行号, 命中引用)`（纯函数）。"""
    out: list = []
    for rel in sorted(docs):
        for lineno, line in enumerate(docs[rel].splitlines(), 1):
            for match in REF_RE.finditer(line):
                segment = match.group(1)
                if _ref_is_illegal(segment, line, match.end()):
                    out.append((rel, lineno, segment))
    return out


class TestTempLogPolicy(unittest.TestCase):
    """文档不得把具体的临时产物钉成长期引用。"""

    def test_no_concrete_temp_artifact_refs(self):
        """`run-logs/`、`perf-logs/` 只允许目录或占位符形态（AGENTS.md 硬性 #14）。"""
        violations = _violations(_load_docs())
        details = "\n".join(
            f"  {rel}:{lineno} → {segment} → 改为目录或占位符形态"
            f"（如 perf-logs/<段>-<序号>-<时间戳>.log），结论与数值另落 docs/compose/reports/"
            for rel, lineno, segment in violations
        )
        self.assertEqual(
            violations, [],
            f"文档引用了具体的临时产物（共 {len(violations)} 处）——"
            f"临时目录随时会被 scripts/agent/cleanup_tmp.py 清空：\n{details}",
        )

    def test_allowlist_is_minimal(self):
        """白名单只能收敛：新增条目须先证明该名称与临时产物生命周期无关。"""
        self.assertLessEqual(
            len(ALLOWED), 3,
            f"ALLOWED 白名单膨胀到 {len(ALLOWED)} 条（上限 3）——"
            f"应当改文档引用形态，而不是往白名单里加例外",
        )

    def test_chinese_punctuation_not_flagged(self):
        """中文句读紧贴目录不会误伤（全角标点不在片段字符集内）。"""
        docs = {"示例.md": "结果落到 `run-logs/`。\n再看 `perf-logs/`，然后收工。"}
        self.assertEqual(_violations(docs), [])

    def test_chinese_named_artifact_flagged(self):
        """中文名具体产物同样要拦下（旧字符集只收 ASCII，中文名会漏成空片段）。"""
        docs = {"示例.md": "见 `run-logs/验收-20261009.html`。"}
        self.assertEqual(_violations(docs), [("示例.md", 1, "验收-20261009.html")])

    def test_lookalike_dirs_not_flagged(self):
        """同后缀目录（`my-run-logs/`、`perf-logs-old/`）不是本项目的临时目录。"""
        docs = {"示例.md": "见 `my-run-logs/x.md` 与 `perf-logs-old/a.log`。"}
        self.assertEqual(_violations(docs), [])

    def test_missing_docs_tolerated(self):
        """空集合（文件缺失）不抛异常也不产生违规。"""
        self.assertEqual(_violations({}), [])

    def test_load_docs_sees_expected_shape(self):
        """自检读盘入口本身没退化（否则主用例会「空转通过」）。"""
        docs = _load_docs()
        for rel in ("AGENTS.md", "MEMORY.md"):
            if os.path.isfile(os.path.join(_ROOT, rel)):
                self.assertIn(rel, docs)   # 文件存在才断言（裁剪过的检出上可能缺）
        # 实测 2026-10-09 全量检出扫描到 48 份；取 30 留文档增删余量，
        # 同时足以抓住「读错根目录 / 漏扫 docs」这类退化。
        self.assertGreaterEqual(
            len(docs), 30,
            f"扫描到的文档数异常（{len(docs)}）——_load_docs 可能读错目录，主用例会空转通过",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
