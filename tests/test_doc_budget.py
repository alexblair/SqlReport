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
2026-10-09 起改为**有量化目标的下调**（见 `docs/compose/spec/2026-10-09-context-slimming-and-aoci-usage-design.md`）：
退役的硬性约束号登记在 `RETIRED_CONSTRAINTS`，任何 `硬性 #N` 引用必须落在 `LIVE_CONSTRAINTS`，否则视为悬空指引。
阈值调整原则：只允许「把细节从最小集挪进分卷」后再放宽，不允许直接抬上限。
"""
import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KB = os.path.join(_ROOT, "docs", "compose", "knowledge")

# ---- 预算（字节）----------------------------------------------------------------
LIMIT_AGENTS_MD = 11000      # 每步注入：约束总纲（瘦身后 ≈10KB；超限先把细节移入分卷）
LIMIT_MEMORY_MD = 13000      # 每轮开工必读：跨会话记忆（瘦身后 ≈12KB）
LIMIT_VOLUME = 22000         # 单个知识库分卷（按需读）
LIMIT_VOLUMES_TOTAL = 155000 # 知识库分卷合计：防止「分卷慢慢膨胀」绕开单卷上限
LIMIT_COURSE_STATE = 8000    # learn/sqlreport-kb/course-state.md（开工查证会读）

# 硬性约束编号（AGENTS.md §1）：引用必须落在 LIVE；退役号不复用（2026-10-09 瘦身）
LIVE_CONSTRAINTS = frozenset({1, 2, 3, 5, 6, 7, 8, 12, 14, 17, 18, 19, 20, 21, 22})
RETIRED_CONSTRAINTS = frozenset({4, 9, 10, 11, 13, 15, 16})
_CONSTRAINT_REF_RE = re.compile(r"硬性(?:约束)?\s*#(\d{1,2})")

# MEMORY.md 策展门禁（2026-10-09）：记忆不得垃圾桶化——条数有上限、每条带归属、禁止重复行
LIMIT_MEMORY_RULES = 12          # ## Rules 下的条目上限
LIMIT_MEMORY_DISCOVERED = 18     # ## Discovered 下的条目上限
_MEMORY_ITEM_RE = re.compile(r"^\s*(?:\d+\.|-)\s+\*\*")
_MEMORY_ATTR_RE = re.compile(r"用户|实测|20\d\d-\d\d")

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
    cs = _maybe_read(os.path.join(_ROOT, "learn", "sqlreport-kb", "course-state.md"))
    if cs is not None:
        docs["course_state"] = cs
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

    # MEMORY.md 策展：条数上限 + 归属标记 + 禁止重复行（防「垃圾桶化」）
    if memory:
        sections: dict = {}
        cur = None
        for raw in memory.splitlines():
            m = re.match(r"^##\s+(.*)$", raw)
            if m:
                cur = m.group(1).strip()
                sections[cur] = []
            elif cur is not None:
                sections[cur].append(raw)
        for name, limit in (("Rules", LIMIT_MEMORY_RULES), ("Discovered", LIMIT_MEMORY_DISCOVERED)):
            key = next((k for k in sections if k.startswith(name)), None)
            if key is None:
                continue
            items = [ln for ln in sections[key] if _MEMORY_ITEM_RE.match(ln)]
            if len(items) > limit:
                out.append(f"MEMORY_ITEMS|## {key} 条目 {len(items)} 条 > 上限 {limit}"
                           f"（记忆不是垃圾桶：先合并/删除/移入分卷，再加新条目）")
            for ln in items:
                if not _MEMORY_ATTR_RE.search(ln):
                    out.append(f"MEMORY_ATTR|## {key} 条目缺归属标记（需含「用户」/「实测」/日期）：{ln.strip()[:60]}")
        seen: dict = {}
        for raw in memory.splitlines():
            norm = raw.strip()
            if len(norm) < 40 or norm.startswith(("#", ">")):
                continue
            seen[norm] = seen.get(norm, 0) + 1
        for ln, n in seen.items():
            if n > 1:
                out.append(f"MEMORY_DUP|MEMORY.md 有 {n} 次重复行（{ln[:50]}…）：策展时合并")

    total = sum(len(t.encode("utf-8")) for t in docs["volumes"].values())
    if total > LIMIT_VOLUMES_TOTAL:
        out.append(f"VOLUMES_TOTAL|知识库分卷合计 {total} 字节 > 上限 {LIMIT_VOLUMES_TOTAL}"
                   f"（单卷不超也可能总量膨胀；见 2026-10-09 瘦身 spec）")

    cs = docs.get("course_state", "")
    if len(cs.encode("utf-8")) > LIMIT_COURSE_STATE:
        out.append(f"COURSE_STATE|course-state.md 体积 {len(cs.encode('utf-8'))} 字节 "
                   f"> 上限 {LIMIT_COURSE_STATE}（开工查证会读）")

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
    # 硬性约束编号引用必须可解析：退役/改号后不留悬空指引（只认 `硬性 #N` 形态）
    seen: set = set()
    scan = dict(docs["files"])
    scan.update({f"knowledge/{k}": v for k, v in docs["volumes"].items()})
    if cs:
        scan["learn/sqlreport-kb/course-state.md"] = cs
    for where, text in scan.items():
        for num in _CONSTRAINT_REF_RE.findall(text):
            n = int(num)
            if n in LIVE_CONSTRAINTS or (where, n) in seen:
                continue
            seen.add((where, n))
            why = "已于 2026-10-09 退役" if n in RETIRED_CONSTRAINTS else "不存在"
            out.append(f"CONSTRAINT|{where} 引用了{why}的硬性 #{n}")
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

    def test_volumes_total_within_budget(self):
        """分卷合计不得绕开单卷上限（防「单卷都不超、总量偷偷膨胀」）。"""
        self.assertEqual(self._by("VOLUMES_TOTAL"), [], "知识库分卷合计超预算")

    def test_course_state_within_budget(self):
        """course-state.md 开工查证会读，超预算要压缩。"""
        self.assertEqual(self._by("COURSE_STATE"), [], "course-state.md 超出预算")

    def test_constraint_refs_resolve(self):
        """`硬性 #N` 引用必须指向存活约束（退役号不留悬空指引）。"""
        self.assertEqual(self._by("CONSTRAINT"), [], "存在已退役/不存在的硬性约束引用")

    def test_memory_curation(self):
        """MEMORY.md 不得垃圾桶化：条数有上限、条目带归属、无重复行。"""
        for cat in ("MEMORY_ITEMS", "MEMORY_ATTR", "MEMORY_DUP"):
            self.assertEqual(self._by(cat), [], f"MEMORY.md 策展门禁未过：{cat}")
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
