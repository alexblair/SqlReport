> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# B9 工作包（P3 结构拆分 —— **风险最高，最后做**）

> 本文件是 **B9 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B9（§1707 起）
> 开工基线：`Ran 3172 tests, OK (skipped=4)`（B8 后）
> **本文件全部行号与字节基线由 Lead 用 AST/实测现查**（plan 原行号已漂移，不要照抄）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. **本批是纯搬移**：`render.py` / `config.py` 的**对外符号名与取值必须逐字节不变**。
   任何字节变化都视为失败，必须回退重做。
4. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
5. **不要**改动任何逻辑，只搬移定义。
6. 本批拆成 **B9-1（render 常量外移）** 与 **B9-2（config 拆分）** 两个独立子任务；
   **B9-1 必须先做且独立验收通过**，再做 B9-2。

---

## 1. 字节基线（**Lead 已实测记录，用于验收**）

搬移**前后**这些值必须**完全一致**：

| 符号 | sha256（前 16 位） | 长度 |
|---|---|---|
| `_BASE_CSS` | `ae3a4bbd0272f2a2` | 9055 |
| `_COMMON_CSS` | `bb7ec576421bc83e` | 79531 |
| `_COMMON_JS` | `5bcbeaccdfb1c635` | 21412 |
| `_MD_CSS` | `c352588586b20dc3` | 2492 |
| `_SQL_HIGHLIGHT_JS` | `b747870a03686a41` | 1343 |
| `_SQL_FORMATTER_JS` | `b46730d48db26945` | 3116 |
| `_API_TEMPLATE_JS` | `d59b15d3f972c38e` | 7611 |
| `_EXCL_EDITOR_JS` | `acd4d5e83cde6b4a` | 7434 |

**契约级基线**：`render.content_hash8(_COMMON_CSS + "\n;;;\n" + _COMMON_JS)` = **`72429792`**
（这是 vendor 目录名 `self@{hash8}` 的来源，变了会导致静态资源 URL 变化 → **必须不变**）

---

## 2. Task B9-1：`render.py` 七个大常量外移到 `ui_assets.py`

### 已核实的搬移清单（AST 现查，`render.py` 共 6594 行）
| 常量 | 行区间 | 行数 |
|---|---|---|
| `_BASE_CSS` | `L82-281` | 200 |
| `_COMMON_CSS`（原始字面量） | `L283-1468` | 1186 |
| `_MD_CSS` | `L1484-1534` | 51 |
| `_SQL_HIGHLIGHT_JS` | `L2126-2150` | 25 |
| `_SQL_FORMATTER_JS` | `L2152-2193` | 42 |
| `_API_TEMPLATE_JS` | `L4934-5130` | 197 |
| `_EXCL_EDITOR_JS` | `L6255-6440` | 186 |

### ⚠️⚠️ 三处最容易搞错的地方（Lead 已核实）

**① `_COMMON_CSS` 有两次赋值，第二次是自引用拼接**
```python
L283:  _COMMON_CSS = """..."""        # 原始字面量（1186 行）
L1537: _COMMON_CSS = _BASE_CSS + _COMMON_CSS   # 自引用重赋值
```
搬到 `ui_assets.py` 后，**这个拼接语义必须原样保留**
（`ui_assets.COMMON_CSS = BASE_CSS + COMMON_CSS`）。
**注意**：B8 已删掉三个空壳分片，所以现在右边**只有** `_BASE_CSS + _COMMON_CSS`。
**不要**把两次赋值合成一次而改变结果——请搬移后实测 sha256。

**② `_COMMON_JS` 不在搬移清单里**
它长度 21412，**留在 `render.py`**。但它参与 `content_hash8` 计算，
所以 `ui_assets.py` **不要**试图搬它，也**不要**在 `ui_assets` 里重算 vendor hash。

**③ 外部模块从 `render` 导入这些常量 —— 名字必须继续可用**
Lead 已 `grep` 现查：
- `config.py:50/51/60` 从 `render` 导入 `_SQL_HIGHLIGHT_JS`、`_SQL_FORMATTER_JS`、`_MD_CSS`
- `report.py:53/54/73` 从 `render` 导入 `_SQL_HIGHLIGHT_JS`、`_SQL_FORMATTER_JS`、`_MD_CSS`
- `markdown_render.py:298` 仅 docstring 提到 `render._MD_CSS`

→ **`render.py` 必须继续导出这些名字**。做法：`render.py` 里
`from ui_assets import (BASE_CSS, COMMON_CSS, MD_CSS, ...)` 后再
`_BASE_CSS = BASE_CSS` 等（或 `from ui_assets import *` + 显式别名）。
**两种做法都行，但验收标准是「`render._X` 存在且取值 sha256 与基线一致」**。

> ⚠️ 命名风格：`ui_assets.py` 里用**不带下划线**的公开名（`BASE_CSS`/`COMMON_CSS`/…）
> 还是沿用 `_BASE_CSS`？**建议用公开名**（模块已是内部资产层，无需再私有化）；
> 但 `render.py` 侧**必须**保留 `_BASE_CSS` 等下划线名（19+ 处既有引用）。
> 若你选沿用下划线名，也**可以**，只要 `render._X` 可用——**在报告里说明你的选择**。

### Step 1 — 写字节快照测试（**先固化基线，改之前就要能跑**）
```python
# tests/test_b9_moves.py
import hashlib
import unittest


class TestAssetsByteIdentical(unittest.TestCase):
    """B9-1：常量外移是纯搬移，取值与 vendor hash 必须逐字节不变。"""

    BASELINE = {
        "_BASE_CSS": ("ae3a4bbd0272f2a2", 9055),
        "_COMMON_CSS": ("bb7ec576421bc83e", 79531),
        "_COMMON_JS": ("5bcbeaccdfb1c635", 21412),
        "_MD_CSS": ("c352588586b20dc3", 2492),
        "_SQL_HIGHLIGHT_JS": ("b747870a03686a41", 1343),
        "_SQL_FORMATTER_JS": ("b46730d48db26945", 3116),
        "_API_TEMPLATE_JS": ("d59b15d3f972c38e", 7611),
        "_EXCL_EDITOR_JS": ("acd4d5e83cde6b4a", 7434),
    }

    def test_render_constants_match_baseline(self):
        import render
        for name, (want_h, want_len) in self.BASELINE.items():
            val = getattr(render, name, None)
            self.assertIsInstance(val, str, f"render.{name} 不在了")
            self.assertEqual(len(val), want_len, f"{name} 长度变了")
            self.assertEqual(hashlib.sha256(val.encode()).hexdigest()[:16], want_h,
                             f"{name} 字节变了")

    def test_vendor_hash8_unchanged(self):
        """vendor 目录名 self@{hash8} 必须不变（否则静态资源 URL 变化）。"""
        import render
        self.assertEqual(
            render.content_hash8(render._COMMON_CSS + "\n;;;\n" + render._COMMON_JS),
            "72429792")

    def test_ui_assets_exists_and_render_reexports(self):
        """外移后 render 必须继续导出这些名字（config/report 从 render 导入）。"""
        import render
        import ui_assets
        self.assertTrue(hasattr(ui_assets, "COMMON_CSS")
                        or hasattr(ui_assets, "_COMMON_CSS"),
                        "ui_assets 未提供 COMMON_CSS")
        # config / report 的导入路径必须仍可用
        from render import _MD_CSS, _SQL_FORMATTER_JS, _SQL_HIGHLIGHT_JS  # noqa: F401
```

### Step 2 — 跑确认基线（**改之前**）
`test_render_constants_match_baseline` 与 `test_vendor_hash8_unchanged` **应先通过**
（它们是基线护栏）；`test_ui_assets_exists_and_render_reexports` 应 **FAIL**（`ui_assets` 还不存在）。

### Step 3 — 搬移
1. 新建 `ui_assets.py`，把 7 个常量的**字面量原文逐字**搬过去（含三引号内的所有空白与换行）
2. **保留** `L1537` 的拼接语义
3. `render.py` 顶部加 `from ui_assets import ...`，并把 `_X = X` 别名（或 `import ui_assets as ...`）
4. **逐行搬移，不要重新格式化字符串内容**（三引号字符串内任何空格变化都会改 sha256）

> ⚠️ 搬移后立刻跑 `test_render_constants_match_baseline`。**hash 不一致 = 搬移出错**，
> 不要试图「修正」基线，要找出被改动的字符。

### Step 4 — 验收
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b9_moves.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_render*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_ui_tokens.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
```

### 报告（四行）
1. `ui_assets.py` 新增行数 / `render.py` 净减少行数
2. 8 个常量的 sha256 + 长度是否**全部**与基线一致（贴出验证方式）
3. vendor `hash8` 是否仍为 `72429792`
4. 命名选择（公开名 or 下划线名）与 `render._X` 可用性怎么验证的

---

## 3. Task B9-2：`config.py` 按实体拆分（**仅在 B9-1 验收通过后做**）

⚠️ **本任务风险高于 B9-1，且收益主要是可维护性**。现状：`config.py` 2968 行、89 个顶层函数。

### ✅ Lead 已完成 B9-2 侦察（下列事实可直接采信，不用重查）

**依赖面**：`grep -rn 'config\.' tests/*.py` = **517 处**；`tests/` 真正引用的 `config.<name>` 符号 **33 个**。
其中 **8 个是 `config.py` 的 import 副产物**（拆分后最易丢失，必须继续可得）：
`config.db`、`config.json`、`config._escape`、`config._CONFIG_EXTRA_CSS`、
`config._REPORTS_EXTRA_CSS`、`config.build_api_endpoint_form_html`
（另 `config.debug` / `config.py` 本身就不存在，是拼接串误匹配，无需处理）。

**命名空间基线**：`dir(config)` 公开符号共 **139 个**，基线已固化在
`tests/test_b9_moves.py::TestConfigNamespacePreserved` 内（**不依赖会被清空的临时目录**）；
拆分后必须无缺失。

**结构性事实（重要，决定了拆分是否安全）**：
- **无任何 `global` 声明**，也**无模块级可变状态**（只有 `_PATH_PATTERN` 正则与几个常量字符串）
  → 拆开后**不会有跨模块共享状态被复制**的问题
- 函数依赖关系清晰：**只有 21 个 shared 助手**，跨簇边很少

**各簇规模（Lead 用 AST 统计）**：
| 簇 | 函数数 | 行数 | 依赖 shared 助手 |
|---|---|---|---|
| reports | 13 | 562 | — |
| api_endpoints | 11 | 437 | — |
| pools | 13 | 243 | — |
| scheduler | 9 | 224 | — |
| categories | 12 | 195 | `_parse_form_data`、`render_overview` |
| **branding** | **3** | **174** | **0 个 ← 最干净，建议第一个拆** |
| users | 8 | 103 | `_nav_badges`、`_parse_form_data`、`render_overview` |
| shared/other | 20 | 736 | （留 `config.py`） |

> ⚠️ **建议**：先从 **`branding`**（3 个函数、0 个 shared 依赖）开始，
> 它是唯一**不依赖任何 shared 助手**的簇 → 搬迁风险最低，可当作整条链路（新建子包 + re-export
> + 命名空间断言）的**验证样板**。样板跑通后再逐簇搬其他组。

### ⚠️ 最重要的约束
**`config.` 命名空间必须继续暴露原有全部符号**——Lead 已确认**大量测试文件**引用
`config.xxx`（前缀引用），且 `server.py` 的路由分发直接指向 `config.handle_*`。
→ 拆分后 `config.py` 必须作为**兼容再导出层**保留（`from config_pages.pools import *` 等）。

### 拆什么（按 plan 的 8 实体分组）
建议按 URL 段切：`pools` / `users` / `reports` / `categories` / `overview` / `scheduler` / `api_endpoints` / `branding`。
每组的「渲染 + 表单处理」成对移动（它们共享大量局部 helper）。

### ⚠️ 必须先做的清查（**写代码前完成**）
1. `grep -rn 'config\.' tests/*.py | wc -l` —— 量级
2. 找出 **`server.py` 路由表**里指向 `config.handle_*` 的入口（这些函数名不能变）
3. 找出 `config.py` 内**跨实体共享**的 helper（如 `_escape`、`_get_depth`、`_nav_badges`）→
   这些应留在 `config.py` 或放公共模块，**不要**复制到多个实体模块
4. `grep -rn 'from config import' *.py` —— 模块级导入点

### ⚠️ 建议做法（降风险）
- **先用 `from config_pages.x import *` + `__all__`**，逐组搬迁，**每组搬完立刻跑全量**
- **不要一次性搬完 8 组再跑测试**（出错时无法定位是哪组）
- 若某组的 helper 依赖关系纠缠过深 → **该组留在 `config.py`**，在报告里说明
- 若你判断整体拆分在本轮无法安全完成 → **停下报告**，只交付 B9-1

### 验收
```bash
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_server*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_b9_moves.py' -t . 2>&1 | tail -3
```
**外加**：`config.` 命名空间的**符号清单**必须与拆分前**一致**（差集为空）。
请写断言：拆分前列出 `dir(config)` 的公开符号集合，拆分后比对（允许新增，**不允许缺失**）。

### 报告（五行）
1. 拆出哪几个模块、各多少行；`config.py` 剩多少行
2. `config.` 符号集合是否**无缺失**（怎么验证的）
3. 哪几组**未拆**及原因
4. 三个回归结果
5. `server.py` 路由入口是否未改

---

## 4. B9 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```

> **注意**：全量套件有低概率 flaky（B5 期间 6 次中 1 次失败，重跑即绿）。
> 遇到失败先**重跑**；仍失败再用 `git stash` 对照定位。

### 执行顺序
**B9-1（纯搬移 + 字节护栏）→ 验收 → B9-2（config 拆分，可只做部分）**

> ⚠️ B9-2 若无法安全完成，**只交付 B9-1 是完全可接受的**——
> 「结构拆分」的收益是长期可维护性，不值得用「一次性大爆炸改动」去换回归风险。
> 请在报告里明确说明你做到了哪一步。
