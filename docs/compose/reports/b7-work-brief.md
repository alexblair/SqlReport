> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# B7 工作包（P1 语义收口与去重）

> 本文件是 **B7 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B7（§1449 起）
> 开工基线：`Ran 3146 tests, OK (skipped=4)`（B6 后）· 期望收尾 `Ran ≥3156`
> **本文件行号由 Lead 用 AST/grep 现查现核**（plan 里的旧行号已漂移，不要照抄 plan 的行号）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. 只改本任务 `Files` 列出的文件。
4. 本批是**语义收口**：除 B7-3（D4 已裁决的行为修正）外，**可观测输出必须不变**。
5. 用户可感知文字一律简体中文（硬性 #2）。
6. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
7. 测试文件 `tests/test_b7_dedup.py` 由 B7-2 新建，B7-3/B7-4 **追加**（用 `edit`，不要重写）。

---

## 1. Task B7-1：删除 `report.py` 被遮蔽的重复定义（**先做，最小**）

**Files**: `report.py`（删除 `:369-435` 区间的死代码）
**Test**: 追加到新建的 `tests/test_b7_dedup.py`

### 已核实的缺陷（AST 现查）
`report.py` 有 **2 处模块级重名函数**，后定义**静默遮蔽**前定义：

| 函数 | 死定义 | 生效定义 | 证据 |
|---|---|---|---|
| `humanize_db_error` | `:383` | `:436` | `__code__.co_firstlineno == 436` |
| `render_sql_error_section` | `:400` | `:456` | `__code__.co_firstlineno == 456` |

**连带死常量**：`_DB_ERROR_HINTS = {`（`:369`）**全仓仅** `:396`（在死代码内）引用 →
该字典是**孤儿**，一并删除。

⚠️ **两版语义不同，别搞混**：生效版（`:436`）用 `_DB_ERRNO_HINTS`（`:418`）+ 
`_READ_TIMEOUT_MSG_MARKERS`（1969 / "Read timed out" 映射为查询超时），
并同时匹配 `"(NNNN)"` 与行首 `"NNNN "` 两种 errno 形态。
**死掉的那版用 `_DB_ERROR_HINTS`，功能更弱** —— 所以删除死代码**不会**改变行为。

### Step 1 — 写测试（证明「删掉后行为不变」）
```python
# tests/test_b7_dedup.py
import unittest


class TestShadowedDefsRemoved(unittest.TestCase):
    """B7-1：被遮蔽的重复定义必须删除，且生效版本的语义不变。"""

    def test_effective_humanize_uses_errno_hints_table(self):
        """生效版必须走 _DB_ERRNO_HINTS + 超时标记（不是被删掉的旧表）。"""
        import report
        # 生效版必须比死掉那版更强：同时认 "(NNNN)" 与行首 "NNNN " 两种 errno 形态
        class _E(Exception):
            errno = None
        friendly, raw = report.humanize_db_error(_E("2003 Can't connect"))
        self.assertNotEqual(friendly, raw, "行首 errno 形态未映射（生效版应支持）")
        self.assertTrue(hasattr(report, "_DB_ERRNO_HINTS"))
        # 1969 → 查询超时人话
        class _E(Exception):
            errno = 1969
        friendly, raw = report.humanize_db_error(_E("boom"))
        self.assertNotEqual(friendly, raw, "1969 未映射为超时人话")
        self.assertEqual(raw, "boom")

    def test_read_timeout_message_maps_to_timeout_hint(self):
        import report
        friendly, raw = report.humanize_db_error(Exception("Read timed out"))
        self.assertNotEqual(friendly, raw, "Read timed out 未映射")

    def test_unmapped_error_returns_raw_twice(self):
        """未识别异常原样返回（不制造虚假解释）。"""
        import report
        friendly, raw = report.humanize_db_error(Exception("some weird thing"))
        self.assertEqual(friendly, raw)

    def test_orphan_hints_table_removed(self):
        """_DB_ERROR_HINTS 只被死代码引用，应一并删除。"""
        import report
        self.assertFalse(hasattr(report, "_DB_ERROR_HINTS"),
                         "_DB_ERROR_HINTS 是孤儿常量，应随死代码删除")

    def test_no_module_level_shadowing(self):
        """模块级不得再有重名函数定义（后定义遮蔽前定义）。"""
        import ast
        import inspect
        import report
        tree = ast.parse(inspect.getsource(report))
        seen, dups = {}, []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.name in seen:
                    dups.append(n.name)
                seen[n.name] = n.lineno
        self.assertEqual(dups, [], f"仍有被遮蔽的重复定义: {dups}")

    def test_error_section_still_renders(self):
        import report
        html = report.render_sql_error_section("人话提示", "原始错误")
        self.assertIn("人话提示", html)
        self.assertIn("原始错误", html)
```

### Step 2 — 跑确认基线（**改之前**）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b7_dedup.py' -t . 2>&1 | tail -3
```
Expected: **FAIL**（`test_orphan_hints_table_removed` 与 `test_no_module_level_shadowing` 应先红）。

### Step 3 — 删除死代码
⚠️ **本任务已完成（B7-1 已交付）**。下述记录供追溯，**若需重做，按「符号边界」而非行号删**：
初版 brief 写的 `:369-435` 是**错的**——`:418` 是 `_DB_ERRNO_HINTS`、`:433` 是
`_READ_TIMEOUT_MSG_MARKERS`，**两者都在生效路径上**（`:436` 起的 `humanize_db_error` 在用）。
子代理按协议停下报告后，实际删除区间为 **`:367-415`**（净 −48 行）：
- `:367-368` 描述**死掉**的 `_DB_ERROR_HINTS` 的注释（无处可附，一并删）
- `:369-380` 孤儿 `_DB_ERROR_HINTS`、`:383-397` 旧 `humanize_db_error`、`:400-413` 旧 `render_sql_error_section`、`:414-415` 空行

**保留**（行号为删除**后**的新值）：`_DB_ERRNO_HINTS` `:370`、`_READ_TIMEOUT_MSG_MARKERS` `:385`、
生效版 `humanize_db_error` `:388`、`render_sql_error_section` `:408`。

> ⚠️ **教训**：删除类任务的工作包**不能只给行区间**，必须写「这几行属于哪个符号」；
> 否则区间边界一旦包含生效常量就会静默破坏功能。子代理的 AST 复核（`ast.parse` 看区间内顶层对象）
> 是正确做法，后续删除类任务都应要求这一步。

### Step 4 — 跑确认通过 + 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b7_dedup.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_db*.py' -t . 2>&1 | tail -3
```

### 报告（四行）
1. 删除的行区间与净删除行数
2. 新测试 + 两个回归（各精确 `Ran N tests, OK`）
3. `_DB_ERROR_HINTS` 是否确认孤儿并删除
4. 生效版 `humanize_db_error` 的 `co_firstlineno` 变化（会因删除而上移，属预期）

---

## 2. Task B7-2：`_escape` 语义统一

**Files**: `config.py`（`:205-207` 的 `_escape`）
**Test**: `tests/test_b7_dedup.py`

### 已核实的缺陷（Lead 实测）
两份 `_escape` 语义不同——`config._escape` 直接 `escape(str(v))`，
`render._escape` 先过 `format_cell`：

| 输入 | `config._escape` | `render._escape` |
|---|---|---|
| `Decimal("1E-10")` | `'1E-10'` | `'0.0000000001'` |
| `Decimal("1E+20")` | `'1E+20'` | `'100000000000000000000'` |
| `Decimal("123.4500")` | `'123.4500'` | `'123.45'` |
| `1234567.89` / `1e20` | `'1234567.89'` / `'1e+20'` | 同 / `'100000000000000000000'` |

即配置页可能把 `Decimal` 原样显示为科学计数法。

### ✅ Lead 已核实的两条安全前提
1. **不成环**：`config.py:37` **已经** `from render import (...)`；`render.py` **不** import config。
   故让 `config._escape` 委托给 `render._escape` 不引入新依赖方向。
2. **当前调用点字节安全**：`config.py` 内 **13 处** `_escape(...)` **全部传字符串**
   （`p["name"]` / `report["name"]` / `str(eng).upper()` 等）；而 `format_cell` 对**纯字符串恒等**
   （Lead 实测 11 个样本含 `<>&"'`、多行、emoji、`%s`、`{x}` 均逐字节不变）。
   → 委托后**现有页面输出逐字节不变**。

### Step 1 — 写测试
```python
class TestEscapeUnified(unittest.TestCase):
    """B7-2：两份 _escape 必须语义一致（消除 Decimal 科学计数法分叉）。"""

    def test_decimal_no_scientific_notation(self):
        from decimal import Decimal
        import config, render
        for v in (Decimal("1E-10"), Decimal("1E+20"), Decimal("123.4500")):
            self.assertEqual(config._escape(v), render._escape(v),
                             f"_escape 对 {v!r} 语义仍不一致")

    def test_both_agree_on_plain_values(self):
        import config, render
        for v in (None, "", "<b>&", "普通文本", 0, True):
            self.assertEqual(config._escape(v), render._escape(v))

    def test_string_bodies_unchanged_byte_for_byte(self):
        """护栏：委托后字符串体必须逐字节不变（现有 13 处调用点都传字符串）。"""
        import config, render
        for s in ("", "普通文本", '<a href="x">&amp;</a>', "多行\n文本", "emoji😀"):
            self.assertEqual(config._escape(s), render._escape(s))
            self.assertEqual(config._escape(s),
                             __import__("html").escape(s))
```

### Step 2 — 跑确认失败（Decimal 用例应红）
### Step 3 — 实现（**优先选不引入新 import 的写法**）
`config.py` 已从 render 导入大量符号 → **直接把 `_escape` 加进那条 import 列表**，
并删除 `config.py:205-207` 的本地 `def _escape`：
```python
from render import (
    _icon,
    ...
    _MD_CSS,
    _escape,
)
```
> ⚠️ `config._escape` 这个名字 **必须继续可用**（19 个测试文件引用 `config.`；
> 且 `config.py` 内 13 处调用点不改名）。
> 若担心 import 列表与 `def` 共存造成困惑，也可保留薄壳 `def _escape(text): return render._escape(text)`
> —— 但**不要**既 import 又 def 同名（后者会遮蔽前者）。
> ⚠️ 注意 `config.py` 里若还有别处 `from render import ...` 追加导入，确保不重复导入同名符号。

### Step 4 — 跑确认通过 + 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b7_dedup.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_render*.py' -t . 2>&1 | tail -3
```

### 报告（四行）
1. 改动行号 + 选了「加 import」还是「薄壳委托」
2. 新测试 + 两个回归
3. `config._escape` 名字是否仍可用（怎么验证的）
4. 现有 13 处字符串调用点输出是否逐字节不变（怎么验证的）

---

## 3. Task B7-3：分类树缩进改全角（**D4 已裁决**）

**Files**: `config.py`（`:1181` 的 `prefix = "  " * _get_depth(...)`）
**Test**: 追加到 `tests/test_b7_dedup.py`

### 已核实的缺陷
`config.py:1181`：
```python
prefix = "  " * _get_depth(c, all_cats)
parent_opts += f'<option value="{c["id"]}"{sel}>{prefix}{_escape(c["name"])}</option>'
```
用**半角空格**做层级缩进，但 HTML 在 `<option>` 里**会折叠连续空白** →
**当前缩进实际不可见**（这是既存视觉 bug，不是「改了会破坏」）。

### 用户裁决（**不要重新问**）
**D4 = 全角 U+3000**（`\u3000`）——全角空格不被 HTML 折叠，缩进可见且不靠 CSS。

### Step 1 — 写测试
```python
class TestCategoryIndent(unittest.TestCase):
    """B7-3：分类树缩进必须用全角 U+3000（半角在 <option> 里会被折叠）。"""

    def test_indent_is_fullwidth(self):
        import config
        import inspect
        src = inspect.getsource(config)
        # 定位 _get_depth 参与的那行
        self.assertIn("\\u3000", src,
                      "未使用全角 U+3000 缩进；半角空格在 <option> 中会被 HTML 折叠")
        self.assertNotIn('"  " * _get_depth', src,
                         "仍在用半角双空格缩进（<option> 中会被折叠为不可见）")

    def test_rendered_option_contains_fullwidth_indent(self):
        """端到端：渲染出的父子分类 option 必须带全角缩进前缀。"""
        from tests import init_test_db
        from tests.test_base import make_config_db
        import config, config_db
        conn = make_config_db()
        init_test_db(conn)
        parent = config_db.add_category(conn, name="父类")
        _child = config_db.add_category(conn, name="子类", parent_id=parent)
        # ⚠️ :1181 在 render_category_form_page，**不是** _report_form_cat_options
        html = config.render_category_form_page(conn, None)
        self.assertIn("\u3000\u3000", html, "子分类 option 未带全角缩进")
        conn.close()
```
> **Lead 已核实的真实签名**（不要凭命名猜）：
> - `config.render_category_form_page(conn, category_id: int = None, flash: str = None, cat: dict = None) -> str`
> - `config_db.add_category(conn, name: str, parent_id=None, session_user=None) -> int`
>
> ⚠️ **不要用 `_report_form_cat_options`** —— 它是另一条路径（`:253`），不含 `_get_depth` 缩进，
> 用它做端到端断言会误判。

### Step 2 — 跑确认失败
### Step 3 — 实现
把 `config.py:1181` 的 `"  "` 改为 `"\u3000"`（或直接写全角字符，但**建议用 `\u3000` 转义**以免源码里出现不可见字符）。

### Step 4 — 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b7_dedup.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
```

### 报告（三行）
1. 改动行号
2. 新测试 + 回归结果
3. 用 `\u3000` 转义还是字面全角（并说明为何）

---

## 4. Task B7-4：`transform_rows` 收口

**Files**: `report.py`（`_transform_rows` `:1313`）、`result_transform.py`
**Test**: 追加到 `tests/test_b7_dedup.py`

### 待核实现状
`report.py:1313` 有 `_transform_rows`，`result_transform.py` 是共享变换层
（B5-1 刚在其中加过 `_compile_alternation`）。**先读** `report.py:1313` 与
`result_transform.py` 的导出符号，判断是「完全重复」还是「薄包装」：

- 若 `report.py._transform_rows` 只是把参数转交给 `result_transform` 中的若干函数 →
  **原地收敛**（直接调用共享实现，删掉重复逻辑）
- 若语义确有分叉 → **停下报告**，不要强行合并

> ⚠️ `report.py:1313` 被 `execute_report` 调用，且**派生态缓存**（`CachedResult.derived`）
> 依赖它的返回值。**必须先跑 `test_report*.py` 与 `test_result_transform*.py` 建立绿基线再动。**

### 必须遵守
- 筛选/排序/输出语义**三处调用方**（报表页 / 导出 / API）必须继续一致（硬性 #3、知识库 `03-report-transform.md`）
- **不得**把分页逻辑掺进来（分页不属变换层）
- 若有重复，优先「删重复、留单一实现」，而不是「把 A 改成调 B 再把 B 改成调 A」

### 报告（四行）
1. `report._transform_rows` 与 `result_transform` 的**实际关系**（重复 / 包装 / 分叉）
2. 改动行号（若判定为分叉未改，明确说明并给出证据）
3. 新测试 + 回归结果
4. 三处调用方语义是否仍一致

---

## 5. B7 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3156` / `OK (skipped=4)`。

> **注意**：全量套件有低概率 flaky（B5 期间 6 次中 1 次失败，重跑即绿）。
> 遇到失败先**重跑**；仍失败再用 `git stash` 对照定位。

### 执行顺序建议
**B7-1 → B7-2 → B7-3 → B7-4**
（B7-1 纯删除最安全；B7-2 影响面最大但已验证字节安全；B7-3 是唯一行为变更；B7-4 需先判断再动手）
