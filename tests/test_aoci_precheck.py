"""改前定向读工具门禁 —— `scripts/agent/aoci_precheck.py`（AGENTS.md 硬性 #21）。

为什么需要门禁：
- AOCI 的读侧工具是"改前查询"的唯一廉价入口；它一旦解析错（分节、字段、路径），
  认知会**静默查不到**（表现为 NO-ENTRY），而 agent 会据此以为"该文件没有约束"。
- 卷格式（`===/repo/dir/===` 分节 + `name[TAG]: F:… | R:… | A:… | S:…`）是机器契约，
  必须有用例钉住；字段值里出现 `；S: …` 这类伪字段时不得被切坏。

判定逻辑全部走脚本内的**纯函数**（`parse_volume` / `resolve` / `render_text`），
不需要写任何临时文件；真实索引存在时再做一次集成断言。
"""
import importlib.util
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "agent", "aoci_precheck.py")

_spec = importlib.util.spec_from_file_location("aoci_precheck", _SCRIPT)
pre = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pre)

FIXTURE = (
    "#AOCI-CODE-VOLUME: 1\n"
    "===/repo/===\n"
    "render.py[CU9L]: F:公共渲染层 | R:code:report.py | A:render_page_header | S:令牌唯一来源；S: 伪字段\n"
    "===/repo/docs/knowledge/===\n"
    "06-ui-interactions.md[SG7S]: F:UI 体系 | R:- | A:页面地图 | S:换页态必须验\n"
)


class TestAociPrecheckParse(unittest.TestCase):
    """解析层：分节归属、字段切分、路径归一。"""

    def test_volume_sections_resolve_to_repo_relative_paths(self):
        entries, order = pre.parse_volume(FIXTURE, root="/repo")
        self.assertEqual(set(entries), {"render.py", "docs/knowledge/06-ui-interactions.md"})
        self.assertEqual(order[0], "render.py")

    def test_fields_split_and_pseudo_field_ignored(self):
        entries, _ = pre.parse_volume(FIXTURE, root="/repo")
        e = entries["render.py"]
        self.assertEqual(e["tag"], "CU9L")
        self.assertEqual(e["F"], "公共渲染层")
        self.assertEqual(e["A"], "render_page_header")
        # 值里的 `；S: 伪字段` 属于 S 正文，不得被切成新字段
        self.assertIn("伪字段", e["S"])
        self.assertNotIn("；", e["F"])

    def test_absolute_section_path_is_relativized(self):
        text = "===/repo/src/===\napp.py[CG3T]: F:入口 | R:- | A:- | S:-\n"
        entries, _ = pre.parse_volume(text, root="/repo")
        self.assertIn("src/app.py", entries)


class TestAociPrecheckResolve(unittest.TestCase):
    """解析层：精确命中 / 唯一 basename / 无条目。"""

    def setUp(self):
        self.entries, self.order = pre.parse_volume(FIXTURE, root="/repo")

    def test_exact_and_basename_and_missing(self):
        res = pre.resolve(self.entries, self.order,
                          ["render.py", "docs/knowledge/06-ui-interactions.md", "ghost.py"])
        self.assertEqual([r["status"] for r in res], ["hit", "hit", "no-entry"])
        self.assertEqual(res[2]["candidates"], [])

    def test_ambiguous_basename_is_reported_not_guessed(self):
        text = ("===/repo/a/===\napp.py[CG3T]: F:一 | R:- | A:- | S:-\n"
                "===/repo/b/===\napp.py[CG3T]: F:二 | R:- | A:- | S:-\n")
        entries, order = pre.parse_volume(text, root="/repo")
        res = pre.resolve(entries, order, ["app.py"])
        self.assertEqual(res[0]["status"], "ambiguous")
        self.assertEqual(len(res[0]["candidates"]), 2)

    def test_render_text_summarizes_hits(self):
        res = pre.resolve(self.entries, self.order, ["render.py", "ghost.py"])
        out = pre.render_text(res)
        self.assertIn("NO-ENTRY", out)
        self.assertIn("命中 1/2", out)
        self.assertIn("S:", out)          # 默认输出 F/S
        self.assertNotIn("A: render_page_header", out)   # 非 --full 不输出 A
        self.assertIn("A: render_page_header", pre.render_text(res, full=True))


class TestAociPrecheckCli(unittest.TestCase):
    """CLI 层：自测退出码 + 真实索引集成（索引缺失时跳过）。"""

    def test_selftest_returns_zero(self):
        self.assertEqual(pre.main(["--selftest"]), 0)

    def test_real_index_has_core_entries(self):
        if not os.path.isfile(pre._DEFAULT_INDEX):
            self.skipTest("本机无 aoci.code.txt（AOCI 未初始化）")
        entries, order = pre.load_index(pre._DEFAULT_INDEX)
        self.assertGreaterEqual(len(order), 50)
        self.assertIn("render.py", entries)
        self.assertTrue(entries["render.py"]["F"])
        self.assertTrue(entries["render.py"]["S"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
