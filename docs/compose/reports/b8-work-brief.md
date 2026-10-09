# B8 工作包（P2 死代码与整批清理）

> 本文件是 **B8 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B8（§1640 起）
> 开工基线：`Ran 3167 tests, OK (skipped=4)`（B7 后）
> **本文件全部条目由 Lead 逐项 `grep` 现查确认仍然存在**（plan 原行号已漂移，不要照抄）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. **删除类改动**：必须写「这几行属于哪个符号」+ 用 `ast.parse` 复核区间内顶层对象
   （B7-1 曾因只给行区间而差点删掉生效常量）。
4. **`A-1`~`A-5` 是纯删除/等价替换**（可观测输出不变）；**`B-1`~`B-3` 是行为修正**（另有说明）。
5. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
6. 测试文件 `tests/test_b8_cleanup.py` 由本批**新建**，条目按 A→B 顺序**追加**（用 `edit`）。

---

## 1. A 组：纯删除 / 等价替换（可观测输出必须不变）

### A-1 `render.py` 连续 `return html`（死代码）

**已核实**：`render.py:4583-4584` 两行连续 `return html`（第二行永远不可达）。

```bash
sed -n '4578,4588p' render.py    # 先看上下文确认
```
删除**不可达的那一行**（保留前一行）。删前用 `ast` 确认该函数体内确有相邻 `ast.Return`。

**护栏测试**：
```python
def test_no_consecutive_return_in_render(self):
    """render.py 不得有相邻 return（第二行永远不可达）。"""
    tree = ast.parse(pathlib.Path("render.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            body = getattr(n, "body", [])
            for i in range(len(body) - 1):
                a, b = body[i], body[i + 1]
                self.assertFalse(
                    isinstance(a, ast.Return) and isinstance(b, ast.Return),
                    f"render.py:{b.lineno} 相邻 return 死代码")
```

### A-2 `render.py` 三个空壳 CSS 常量

**已核实**（`grep -n '^_MINIBTN_CSS\|^_FLASH_WARN_CSS\|^_B6_CSS' render.py`）：
```
1471: _MINIBTN_CSS = ""
1475: _FLASH_WARN_CSS = ""
1538: _B6_CSS = ""
1540: _COMMON_CSS = _BASE_CSS + _COMMON_CSS + _MINIBTN_CSS + _FLASH_WARN_CSS + _B6_CSS
```
三者都已并入 `_COMMON_CSS`，仅作空壳保留。

> ⚠️ **关键取舍**：plan 说「删除并改拼接式」。但注释明写「保留变量名兼容既有引用」。
> **Lead 现查结论**：全仓（含 `tests/`）对这 3 个名字的引用**除 `:1540` 拼接处外没有别的**
> （`grep -rn '_MINIBTN_CSS\|_FLASH_WARN_CSS\|_B6_CSS' *.py tests/*.py` → 仅定义 3 处 + 拼接 1 处）。
> 因此可安全删除：删 3 个 `= ""` 定义，把 `:1540` 改为
> `_COMMON_CSS = _BASE_CSS + _COMMON_CSS`。
> **若你 grep 后发现别处仍有引用 → 停下报告**，不要硬删。

**护栏测试**：
```python
def test_no_empty_css_shims(self):
    src = pathlib.Path("render.py").read_text(encoding="utf-8")
    for name in ("_MINIBTN_CSS", "_FLASH_WARN_CSS", "_B6_CSS"):
        self.assertNotIn(name, src, f"{name} 空壳未清理")
```
> ⚠️ `_COMMON_CSS` 的**最终值必须逐字节不变**：Lead 已记录改动前基准
> **`sha256 = bb7ec576421bc83ead99f24446d497ee13780933160443d63f492a015e7fb40a`，长度 79531**。
> 改完请用同样方式算出新 hash 并**断言完全相同**（这是本项唯一的正确性保证）。
> 另注：`:283` 是 `_COMMON_CSS` 的**原始字面量**，`:1540` 是**自引用重赋值**
> （`_COMMON_CSS = _BASE_CSS + _COMMON_CSS + …`）。删空壳后 `:1540` 写
> `_COMMON_CSS = _BASE_CSS + _COMMON_CSS` 即可，**不要**动 `:283` 的字面量。

### A-3 `render.py` 畸形 SVG 属性 `rx.5`

**已核实**：`render.py:46` 的 `"chart"` 图标有 3 处 `rx.5"`（应为 `rx="0.5"`）。
```bash
grep -n 'rx\.' render.py    # 应只命中 :46
```
改为 `rx="0.5"`（3 处）。这是**真 bug**：属性名非法，浏览器忽略圆角。

**护栏测试**：
```python
def test_no_malformed_svg_attrs(self):
    src = pathlib.Path("render.py").read_text(encoding="utf-8")
    self.assertNotRegex(src, r'rx\.\d', "存在畸形 SVG 属性（如 rx.5）")
```

### A-4 `render.py` 未使用的 `api_cell`

**已核实**：`render.py:4490` 与 `:4493` 给 `api_cell` 赋值，但**全文件再无读取**
（`grep -c 'api_cell' render.py` = **2**，都用在同一批赋值；真正渲染用的是 `api_plain`）。
其中 `:4490` 那个赋值**含较贵的拼接**（`_escape(tooltip)`，tooltip 由上层循环拼出）。

删除两处 `api_cell = ...` 赋值行（**保留** `api_plain`）。
> ⚠️ 若你 grep 后发现 `api_cell` 在别处被读取 → **停下报告**。
> ⚠️ 删除后 HTML 输出必须**逐字节不变**（因为 `api_cell` 从未被渲染）。

### A-5 `server.py` 死函数 `_get_forwarded_url`

**已核实**：`server.py:967` 定义，**生产代码零调用**（`grep -c '_get_forwarded_url' server.py` = 1，
即只有定义）；仅 `tests/test_auth_session.py` 有 3 个直调用例（`:471/:480/:485`）。

> ⚠️⚠️ **本项需你裁决后执行**：删函数会**连带删掉 3 个既有测试**。
> 两条路：
> - **路 A（推荐，符合 plan 意图）**：删函数 + 删那 3 个测试与文件里对它的文档描述
>   （`tests/test_auth_session.py:12` 的模块 docstring 提到它）。
> - **路 B**：保留函数（有人可能视其为运维工具）。
>
> **默认按路 A 执行**；但**若你判断这 3 个测试代表真实需求 → 停下报告**，我会重新裁决。
> 删除测试时**不要**动同文件里 `_get_client_ip` 的任何用例（那是**在用的**）。

---

## 2. B 组：行为修正（有明确缺陷，需实测证明）

### B-1 `app_config.is_debug_mode` 每次调用都读文件

**已核实**：`app_config.py:147-156` 的 `is_debug_mode()` 每次调用都走 `_load_debug_config()`，
而后者**无缓存**（每次 `open()` + `json.load()`）。调用点：`config.py:900`、`config.py:1038`
（配置页请求路径上）。

**修法**：加模块级缓存 + 失效。

> ⚠️⚠️ **Lead 现查的风险（务必处理）**：`tests/test_debug_config_override.py` 有 **4 个用例**
> （`:75/:86/:110/:125`）的模式是：
> ```python
> with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": ...}):
>     app_config._config = None          # ← 只重置了 _config
>     self.assertTrue(app_config.is_debug_mode())
> ```
> 它们**只重置 `_config`**。若 `is_debug_mode` 用独立缓存，这些用例会**因缓存不失效而失败**。
> → 缓存必须在 **`reload_config()`** 与 **`get_config()` 的 `_config is None` 重载路径**都能失效；
>   最稳妥的做法是**让 `_load_debug_config` 自身带缓存**，并在 `reload_config()` 里清它。
> **并且：这 4 个用例的夹具可能需要在同一任务内更新**（硬性 #8）——
> 若它们代表「env 改变后应立刻反映」这一**真实需求**，则**不要**为了通过而削弱断言；
> 正确的做法是让缓存与 env 变化保持一致，或在用例里显式调用失效函数。
> **若你判定无法在不削弱语义的前提下通过 → 停下报告**。

**测试**：断言 `is_debug_mode()` 在缓存命中时**不重复 `open()`**
（用 `mock.patch("builtins.open")` 计数或 patch `_load_debug_config` 计数），
并断言 `reload_config()` 后重新读取。

### B-2 `server.py` 路由未命中做两次扫描

**已核实**：`server.py:455` `route is None` 时调 `_allowed_methods_for_path(path)`
（`:278-288`），后者**重新遍历一遍 `ROUTES`**。即 404/405 路径扫两遍路由表。

**修法**：合并为一次扫描——让匹配函数在未命中时**顺带**返回该路径允许的方法
（例如返回 `(route|None, allowed_methods)`），避免第二次遍历。

> ⚠️ **可观测行为必须不变**：405 的 `Allow` 头内容与顺序、
> 404 与 405 的分流条件，都要与改动前**完全一致**。
> ⚠️ `_match_route` 与 `_allowed_methods_for_path` 可能被测试直接引用 →
> 先 `grep -rn '_match_route\|_allowed_methods_for_path' tests/*.py`，
> **保持这两个名字可用**（可保留为薄包装）。

**测试**：断言 405 响应的 `Allow` 头与改动前一致；断言 404/405 分流正确；
可加一条「路由表只扫描一次」的计数断言（patch `ROUTES` 或计数）。

### B-3 `export.py` GBK BOM 清除用了 `replace` 而非 `lstrip`

**已核实**：`export.py:329` `clean = content.replace("\ufeff", "")`。

**Lead 实测的差异**：
```
content = "\ufeffa\ufeffb"
replace("\ufeff","")  → 'ab'        ← 吃掉数据中间的 U+FEFF（零宽字符）
lstrip("\ufeff")      → 'a\ufeffb'  ← 只去开头 BOM（正确）
```
即 `replace` 会**损坏单元格里合法出现的 U+FEFF**。

**修法**：改为 `clean = content.lstrip("\ufeff")`。

> ⚠️ 只影响 **GBK 分支**（`charset != "utf8"`）；UTF-8 分支直接 `encode` 不经此处。
> ⚠️ 若既有测试断言了 `replace` 行为 → 判断它是「测缺陷」还是「测需求」（见 §0 第 3 条）。

**测试**：断言 `"\ufeffa\ufeffb"` 经 GBK 分支后**中间那个 U+FEFF 仍在**
（GBK 无法编码 U+FEFF，故用 `errors="replace"` 会变成 `?`——**请实测确认期望输出**再写断言）。

---

## 3. B8 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```

### 执行顺序建议
**A-1 → A-2 → A-3 → A-4 → A-5 → B-3 → B-1 → B-2**
（A 组纯删除最安全；B-3 单行；B-1 有测试夹具风险；B-2 需重构扫描逻辑）

> **注意**：全量套件有低概率 flaky（B5 期间 6 次中 1 次失败，重跑即绿）。
> 遇到失败先**重跑**；仍失败再用 `git stash` 对照定位。

### plan 里已存在的条目但 **Lead 现查认为不需要做**
- **`db.py` 补转出**（plan 第 5 项）：`invalidate_api_static_cache_by_report` 与
  `delete_schedules_by_report` **确实未在 `db.py` 转出**，但全仓调用者都走
  `config_db.` 或 `report.config_db.`（`config.py:1910`、`report.py:1057`），
  **没有 `db.` 调用者** → 补转出只是 API 面扩大，**不修错**。**本轮跳过**，
  原因记入报告（避免无调用者的 re-export 膨胀）。
- **`scheduler.MAX_FAIL_COUNT`**（plan 第 6 项）：`MAX_FAIL_COUNT = 5`（`scheduler.py:32`）
  已存在，但 SQL 里有 **3 处硬编码 `fail_count<5`**（`:555`、`:654` 等）。
  → **本项保留**：建议改为用常量拼 SQL。但这属于「能让常量真生效」的改动，
  请作为 **B-4** 处理（若你判断 SQL 拼接有注入/可读性顾虑 → 停下报告）。
- **抽取 `_report_hidden_params`**（plan 第 12 项）：三处 hidden 参数块的字段集**并不相同**
  （第二处多 `action`/`page`/`page_size`），强行抽取会把参数列表变复杂。
  **本轮跳过**，原因记入报告。
