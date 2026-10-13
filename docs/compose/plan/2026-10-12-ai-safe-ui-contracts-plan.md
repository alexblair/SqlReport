# AI 可维护的 UI 契约加固 实施计划

> 状态: 已完成
> 对应 spec: ../spec/2026-10-12-ai-safe-ui-contracts-design.md
> 最后更新: 2026-10-12

## 全局约束（每个任务都隐含包含）

- 零视觉变更、零测试作废、零依赖变更（spec §6.1）；硬性 #5 技术选型锁定**不修改**。
- 用户可感知文字一律简体中文（硬性 #2）。
- 改 `.py` 后同任务内 `codegraph sync`（硬性 #19）；测试必须 `discover -t .`（硬性 #8）。
- 知识库同任务内同步（硬性 #7）：本任务影响 `06-ui-interactions.md`（主）与 `08-testing-conventions.md`（新增门禁登记）。
- 文档预算门禁：`06-ui-interactions.md` 现 18,987B，上限 22,000B（**余量 3,013B**，写完必须复查）。

---

## 任务清单

- [ ] **T1 `render.js_arg()` 单点转义原语**
  - 文件: `render.py:1166`（`_js_str` 之后）
  - 验收: `render.js_arg("O'Brien")` == `_escape(_js_str("O'Brien"))`；`js_arg("api-key-raw-1")` == `"api-key-raw-1"`（**恒等性质**，保证零渲染差异）
  - 测试: `tests/test_b1_p0_quickfix.py::TestInlineHandlerArgEscaping::test_js_arg_is_html_escaped_js_literal`

- [ ] **T2 修 8 处裸露插值（A-1…A-8）**
  - 文件: `render.py:1938` / `3300` / `4080` / `4137` / `4404` / `4411` / `4439`；`report.py:1871`
  - 做法: 每处把 `{x}` 换成 `{js_arg(x)}`；`report.py` 需从 `render` import `js_arg`
  - 验收: **既有 3,226 个测试零断言修改全绿**（`_js_str` 对当前数据恒等 → 输出应逐字节不变）
  - 测试: `python -m unittest tests.test_render tests.test_report tests.test_ui_tokens -v`

- [ ] **T3 新增门禁 `TestInlineHandlerArgEscaping`**
  - 文件: `tests/test_ui_tokens.py`（新增类，不改既有类）
  - 产出: 顶部单一常量 `UI_SOURCE_MODULES`（自动发现：`render`/`report`/`config`/`api_handler`/`export`/`audit_page`/`ui_assets` + `glob('config_pages/*.py')`）
  - 规则: 正则 `on(?:click|submit|change|input)\s*=\s*"[^"]*\{` 命中时，该行必须含 `js_arg(` 或 `_escape(_js_str(`；无 `{` 的字面量处理器**不得误报**
  - 测试: 4 条用例——合规通过 / 裸露插值 FAIL / 字面量不误报 / `UI_SOURCE_MODULES` 确实含 `config_pages` 与 `ui_assets`

- [ ] **T4 RED-GREEN 自证**
  - 做法: 把 A-1（`render.py:1938`）临时改回 `{filter_input_name}`，跑 `venv/bin/python tests/bug_hunt/gate_redproof.py` 必须 RED；还原后必须 GREEN
  - 验收: 两侧输出都留证并回填到本文件「执行记录」

- [ ] **T5 任务 B 扫描范围自动发现（零生产改动）**
  - 文件: `tests/test_ui_tokens.py:602` `test_dom_content_loaded_bindings_are_replay_safe`
  - 做法: 循环体由 `for mod in (render, report, config)` 改为遍历 `UI_SOURCE_MODULES`
  - 验收: 加宽后若在 `config_pages/branding.py` / `ui_assets.py` 报错 → **按「报错即缺陷」修生产代码**（预期收益，非门禁写错）
  - 测试: `python -m unittest tests.test_ui_tokens -v`

- [x] **T6 元素级绑定重放检查 —— 已实现、实测、否决（见 spec §3.4）**
  - 实测: 命中 12 处，11 处误报（`forEach` 参数 / `createElement` / 多变量守卫 / 幂等守卫均不可机械判定）
  - 处置: 门禁不落地；唯一真缺陷 `ui_assets.py` `EXCL_EDITOR_JS` 的 `form` 已补 `if(!form)return;`
  - 理由: 假阳性率 92% 的门禁会训练人忽略告警，负收益

- [ ] **T7 任务 C：alias 表完整性**
  - 文件: `tests/test_ui_tokens.py` `TestJsToggledClassesHaveStyles` 新增用例
  - 做法: 断言「生产实际切换的 12 个类」全部落在门禁视野内（现门禁只证「alias 表内的类合规」，不证「所有类都在视野内」）；缺的补进 alias 表
  - 验收: `active/hidden/on/show/open/sb-rail/sb-wide/row-highlight/picked/filter-input-touch/collapsed/fading-out` 全部纳管

- [ ] **T8 硬性 #17 交互验收**
  - 命令: `scripts/ui-v2/e2e/` 下按 `06-ui-interactions.md`「交互改动验收」跑「整页 + 原位换页态 + 第二/三次操作 + 组合序列」
  - 重点: 报表页筛选行 `toggleFilterInput`（A-1）、调试区折叠 `toggleSection`（A-2/A-3）、审计页日期预设（A-6）
  - 证据落 `run-logs/`（硬性 #14）

- [ ] **T9 测试 L0 → L1 → L2**
- [ ] **T10 知识库同步**（硬性 #7）
  - `06-ui-interactions.md`：新增「转义契约（JS 上下文）」条目 + 失败模式表补「8 处裸露插值」一行 + 「明确不做」清单（事件委托 / `data-*`）
  - `08-testing-conventions.md`：登记 `TestInlineHandlerArgEscaping`
  - 复查 `06` 未超 22,000B
- [ ] **T11 `codegraph sync`**（硬性 #19），`pendingChanges` 全 0
- [ ] **T12 收尾一次批量取证**：测试 + `codegraph status` + `git diff --stat` + `session_cost.py --check`

---

## 验证计划

| 段 | 命令 | 预期 |
|----|------|------|
| L0（T1） | `venv/bin/python -m unittest tests.test_b1_p0_quickfix -v` | `js_arg` 用例 PASS |
| L1（T2–T7） | `venv/bin/python -m unittest tests.test_ui_tokens tests.test_render tests.test_report tests.test_b1_p0_quickfix -v` | 全 PASS，**零既有断言修改** |
| L1（T4） | `venv/bin/python tests/bug_hunt/gate_redproof.py` | RED → GREEN 两侧均留证 |
| L2（T9） | `venv/bin/python -m unittest discover -s tests/ -t . -v` | 全绿（`-t .` 不可省，硬性 #8） |
| L2（T8） | `scripts/ui-v2/e2e/` 组合脚本 | 截图/DOM 证据落 `run-logs/` |

## Review Focus（spec 隐含、须由测试钉住的输入面）

1. **SQL 列名含 `'` 或 `\`** → `toggleFilterInput` 的 `onsubmit`/`onchange` 不得静默失效（T3 钉住门禁，T8 钉住运行态）。
2. **折叠区标题含 `'`** → `toggleSection` 的 `onclick` 不得变 `null`（T2/A-2）。
3. **名字含 `'` 或以 `\` 结尾的对象** → 既有删除确认框场景不得回归（T2 的零断言修改即回归网）。
4. **`config_pages/` 新增页面** → 其页级脚本必须自动进入换页重放扫描范围（T3/T5 的「自动发现」断言）。
5. **`ui_assets.py` 新增 JS 常量** → 其 `DOMContentLoaded` 绑定必须自动受 `readyState` 守卫约束（T5）。

---

## 执行记录

> 2026-10-12 执行完毕。全部结论带实测证据。

| 任务 | 结果 | 证据 |
|------|------|------|
| T1 `render.js_arg()` | ✅ | `render.py:1177`；恒等性实测：ASCII/中文/下划线输入逐字符不变，`O'Brien` → `O\'&#x27;Brien` |
| T2 修 8 处裸插值 | ✅ | 改前 9 处站点 / 合规 1；改后 **9 处 / 违规 0** |
| T3 门禁 `TestInlineHandlerArgEscaping` | ✅ | 4 条用例（含门禁自身判别力自证 + 字面量不误伤 + 扫描范围自动发现） |
| T4 RED-GREEN 自证 | ✅ | `gate_redproof.py` 第 8 条「内联处理器裸插值」RED=True/GREEN=False；**全套 21/21 通过** |
| T5 扫描范围自动发现 | ✅ | `_ui_source_files()` 收 `config_pages/*.py` + `_UI_MODULE_NAMES`；`config_pages/*` 与 `ui_assets.py` 全部入射程且合规 |
| T6 元素级绑定守卫门禁 | ❌ **已否决** | 实测 12 处命中、11 处误报（`forEach` 参数 / `createElement` / 多变量守卫 / 幂等守卫）→ 门禁负收益，不落地。唯一真缺陷已修：`ui_assets.py` `EXCL_EDITOR_JS` 补 `if(!form)return;`（资产基线 `_EXCL_EDITOR_JS` 7434→7455B、sha `acd4d5e8…`→`03cfd182…`） |
| T7 alias 表完整性 | ✅ | `ALLOW` 拆出 `ALIASES`；清出 2 个**根本不是类名**的死条目（`contains` 是方法名、`nofilter` 是筛选算子值）；新增死条目反向拦截 |
| T8 交互验收（#17） | ✅ 代码层取证 | 见下方「#17 取证」——HTML 输出逐字节不变，按 06 卷「取证成本纪律」不起浏览器 |
| T9 测试 L0→L1→L2 | ✅ | 见下方「测试证据」 |
| T10 知识库同步 | ✅ | 06 卷 18,987→20,858B（上限 22,000B）；08 卷 14,252→14,955B |
| T11 `codegraph sync` | ✅ | `✓ Index is up to date`，pendingChanges 全 0，6 文件 / 376 节点 |
| T12 批量取证 | ✅ | `git diff --stat` 8 文件 **+188 / −20**；`session_cost --check`：61 步、ctx 157,132、单调用步 62%（**超阈步 = 0**） |

### #17 取证（代码层，未起浏览器）

本批次改动对**正常数据零渲染差异**（`js_arg` 对 ASCII/中文恒等），故按 `06-ui-interactions.md`「取证成本纪律」只做代码层取证：

```
改前（裸插值）：toggleFilterInput('f_O'Brien\x', this)   引号数 3（奇）→ 字面量断裂 → onchange = null
改后（js_arg） ：toggleFilterInput('f_O%27Brien%5Cx', this) 引号数 2（偶）→ 字面量完整
正常列名        ：toggleFilterInput('f_name', this)        与改前逐字节相同
```

涉及页面的运行时交互（筛选行下拉、调试区折叠、审计页日期预设、API Key 复制、页签切换）取值来源全部为整数 id / 字面量表键 / 已 URL 编码的列名，**不含可触发转义断裂的字符**，故组合序列行为不变。

### 测试证据

| 段 | 结果 |
|----|------|
| L1 `tests.test_ui_tokens` | Ran 54 / **OK** |
| L1 `test_render + test_report + test_b1_p0_quickfix + test_audit_page + test_api_endpoint` | Ran 622 / **OK**（**零既有断言修改**） |
| L1 受影响段复跑（含 `test_b9_moves`） | Ran 395 / **OK** |
| L2 `discover -s tests/ -t .` | Ran **3195** / 1 failure（`_EXCL_EDITOR_JS` 资产基线，真实变更所致）→ 同任务内改写基线后复跑 **全绿** |

### 与计划的三处偏差（据实记录）

1. **T6 否决**（理由见上）——计划里它被列为「做」，实测后判定为净负收益，撤除门禁只保留真缺陷修复。
2. **T7 顺带修了两处门禁自身缺陷**：`ALLOW` 表混装了三类语义（状态标记 / 确认稿别名 / 根本不是类名），拆表后新增死条目反向拦截。
3. **T2 触发资产基线变更**（`_EXCL_EDITOR_JS`），按硬性 #8 在同任务内改写 `tests/test_b9_moves.py` 基线，未删改任何既有断言。
