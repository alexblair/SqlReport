"""文档预算门禁 —— 控制「每步都注入」与「开工必读」文档的成本（AGENTS.md 硬性 #20）。

为什么需要门禁：
- `AGENTS.md` 与 `MEMORY.md` **每一轮对话的每一步都会重发一次**（实测 4 个会话
  Σtotal 69.7M tokens，其中 98% 是历史重发）。这两个文件每涨 1KB，整场会话都要付
  「1KB × 步数」的钱；只靠自觉，它们会无限膨胀。
- 知识库分卷的「路由」必须可解析：AGENTS.md §0/§2 路由表、`knowledge/README.md`
  索引表、`INDEX.md` 里引用到的 `NN-*.md`，磁盘上必须真实存在；反之磁盘上的分卷
  也必须在至少一处登记，否则就是没人能找到的孤儿卷。

被测对象由 `_load_docs()` 单独负责读盘，判定逻辑 `_violations()` 是纯函数——
`tests/bug_hunt/gate_redproof.py` 靠**内存变异**（monkeypatch `_load_docs`）证明
本门禁真的会红，不需要改写磁盘文件。

阈值调整原则：只允许「把细节从最小集挪进分卷」后再放宽，不允许直接抬上限。
"""
import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KB = os.path.join(_ROOT, "docs", "compose", "knowledge")

# ---- 预算（字节）----------------------------------------------------------------
LIMIT_AGENTS_MD = 18000      # 每步注入：约束总纲（当前 ≈16.7KB，余量留给新约束；超限先把细节移入分卷）
LIMIT_MEMORY_MD = 26000      # 每轮开工必读：跨会话记忆
LIMIT_VOLUME = 48000         # 单个知识库分卷（按需读，上限宽松些）

_VOLUME_RE = re.compile(r"(?<![\w/-])(\d{2}-[a-z0-9][a-z0-9-]*\.md)")
_VOLUME_FILE_RE = re.compile(r"^\d{2}-[a-z0-9][a-z0-9-]*\.md$")


def _maybe_read(path: str):
    """读文本；文件不存在返回 None（按「无该约束」处理，历史上 AGENTS.md 曾被 ignore）。"""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _load_docs() -> dict:
    """读入被测文档（唯一读盘入口，便于门禁自证时内存变异）。

    容错：缺失的文件直接从判定集合里去掉（缺文件 = 没有注入成本，不算违规），
    这样在没克隆到本地 `AGENTS.md` 的机器上套件也不会因 FileNotFoundError 而红。
    """
    docs = {"files": {}, "volumes": {}}
    for rel in ("AGENTS.md", "MEMORY.md"):
        text = _maybe_read(os.path.join(_ROOT, rel))
        if text is not None:
            docs["files"][rel] = text
    for rel in ("README.md", "INDEX.md"):
        text = _maybe_read(os.path.join(_KB, rel))
        if text is not None:
            docs["files"]["knowledge/" + rel] = text
    if os.path.isdir(_KB):
        for fn in sorted(os.listdir(_KB)):
            if _VOLUME_FILE_RE.match(fn):
                text = _maybe_read(os.path.join(_KB, fn))
                if text is not None:
                    docs["volumes"][fn] = text
    return docs


def _violations(docs: dict) -> list:
    """返回违规清单，格式 `分类|中文说明`（纯函数）。"""
    out: list = []
    agents = docs["files"].get("AGENTS.md", "")
    memory = docs["files"].get("MEMORY.md", "")

    if len(agents.encode("utf-8")) > LIMIT_AGENTS_MD:
        out.append(f"AGENTS_MD|AGENTS.md 注入体积 {len(agents.encode('utf-8'))} 字节 "
                   f"> 上限 {LIMIT_AGENTS_MD}（每步都重发；把细节挪进分卷再放宽）")
    if len(memory.encode("utf-8")) > LIMIT_MEMORY_MD:
        out.append(f"MEMORY|MEMORY.md 体积 {len(memory.encode('utf-8'))} 字节 "
                   f"> 上限 {LIMIT_MEMORY_MD}（开工必读；过期条目请压缩或移入分卷）")

    for name, text in docs["volumes"].items():
        size = len(text.encode("utf-8"))
        if size > LIMIT_VOLUME:
            out.append(f"VOLUME|分卷 {name} 体积 {size} 字节 > 上限 {LIMIT_VOLUME}")

    # 路由可解析：三处索引引用到的分卷必须存在
    routes = {k: v for k, v in docs["files"].items() if k != "MEMORY.md"}
    referenced: set = set()
    for where, text in routes.items():
        for name in _VOLUME_RE.findall(text):
            referenced.add(name)
            if name not in docs["volumes"]:
                out.append(f"ROUTE|{where} 引用了不存在的分卷 {name}")

    # 无孤儿卷：磁盘上的分卷至少被一处索引登记
    for name in docs["volumes"]:
        if name not in referenced:
            out.append(f"ORPHAN|分卷 {name} 未被 AGENTS.md/README.md/INDEX.md 任何一处登记")
    return out


class TestDocBudget(unittest.TestCase):
    """最小集文档体积 + 知识库路由完整性。"""

    def _by(self, category: str) -> list:
        return [v for v in _violations(_load_docs()) if v.startswith(category + "|")]

    def test_agents_md_within_budget(self):
        """AGENTS.md 是每步注入的最小集，超预算必须先把细节挪进分卷。"""
        self.assertEqual(self._by("AGENTS_MD"), [],
                         "AGENTS.md 超出注入预算：#L20 文档预算门禁")

    def test_memory_within_budget(self):
        """MEMORY.md 每轮开工必读，超预算要压缩过期条目。"""
        self.assertEqual(self._by("MEMORY"), [], "MEMORY.md 超出预算")

    def test_volumes_within_budget(self):
        """单个知识库分卷不得无限膨胀。"""
        self.assertEqual(self._by("VOLUME"), [], "知识库分卷超出体积上限")

    def test_routes_resolve(self):
        """三处索引引用到的分卷必须真实存在（防路由断链）。"""
        self.assertEqual(self._by("ROUTE"), [], "知识库路由引用断链")

    def test_no_orphan_volumes(self):
        """磁盘上的分卷必须至少在一处索引登记（防孤儿卷）。"""
        self.assertEqual(self._by("ORPHAN"), [], "存在未登记的知识库分卷")

    def test_load_docs_sees_expected_shape(self):
        """自检读盘入口本身没退化（否则前 5 条会「空转通过」）。"""
        docs = _load_docs()
        if os.path.isfile(os.path.join(_ROOT, "AGENTS.md")):
            self.assertIn("AGENTS.md", docs["files"])   # 文件存在才断言（历史上曾被 ignore，本地可能缺）
        self.assertIn("knowledge/README.md", docs["files"])
        self.assertGreaterEqual(len(docs["volumes"]), 9,
                                "分卷数异常，_load_docs 可能读错目录")


if __name__ == "__main__":
    unittest.main(verbosity=2)
