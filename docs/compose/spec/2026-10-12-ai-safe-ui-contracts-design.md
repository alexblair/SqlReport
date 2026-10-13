# AI 可维护的 UI 契约加固设计（转义 / 事件绑定 / 样式契约）

> 状态: 生效
> 取代关系: 无（首次针对「AI 写、无人读代码」的 UI 契约加固设计）。本设计**不取代**任何既有 spec；它只把 `2026-09-30-ui-v2-design.md` 的视觉口径**原样保留**，仅加固其工程实现层的可验证契约。与 `2026-10-10-perf-robustness-refactor-design.md` 互补——那份管性能与健壮性，本份管「同类缺陷不可能再以静默方式发生」。
> 对应 plan: ../plan/2026-10-12-ai-safe-ui-contracts-plan.md
> 现场盘点: 2026-10-12，全部结论带 `文件:行`，非推测。盘点方法：`grep` 计数 + 逐点读源码（`codegraph` 索引健康，163 文件 / 7,577 节点）。

---

## 1. 背景

项目前提：**开发者不读代码，功能与修复全部由 AI 完成**。因此本项目真正的质量护栏不是「代码写得好不好」，而是**AI 无法违反的机械约束有多少**。

`06-ui-interactions.md` 的失败模式库已积累 14 条真实事故。逐条归因后，它们**不是随机 bug**，而是同一类结构缺陷的不同外衣——缺「契约」。项目已用门禁与规则补了其中大部分，本设计要补的是**剩下的三处真实缺口**，并**明确放弃两处收益不足的改造**。

### 1.1 现场盘点结论（2026-10-12 实测）

| 项 | 实测 | 含义 |
|------|------|------|
| 内联事件属性（`on*=`）中**嵌数据**的站点 | **9 处**（`render.py` 7 + `report.py` 1 + 已合规 1） | 问题面**极小**，不值得全站重构 |
| 其中用对契约 `_escape(_js_str(x))` 的 | **仅 1 处**（`render.py:2431`） | 正确做法**已存在**，只是没有推广 |
| 未用、裸露 `{...}` 插值的 | **8 处** | 见 §2 任务 A |
| JS 切换的 CSS 类 | **12 个** | 已有 3 个门禁在管，见 §4 任务 C |
| 换页重初始化 | `render.py:675 _swapMain` + `render.py:703 _reinitAfterSwap`（重建 `<main>` 内联 `<script>` 并重跑 `initPage`/`initReportPage`） | **已解决**，不需要重构 |

---

## 2. 任务 A：转义契约推广（最高优先级 · 数据安全）

### 2.1 缺陷陈述

`_escape` 产出 HTML 实体（如 `&#x27;`），浏览器解析 HTML 属性时会**解码回 `'`**，从而破坏 JS 字面量 → `onsubmit`/`onclick` 属性变成 `null` 或语法错误 → **事件处理器静默失效，表单直接提交**。

这正是 2026-09-30 已修过的删除确认框事故（`06-ui-interactions.md` 失败模式表倒数第 4 行，`tests/test_b1_p0_quickfix.py::TestDeleteConfirmJsEscape` 为其门禁）。**修复只打在了删除按钮这一个点上，没有成为规则。**

### 2.2 8 处未合规站点（全部须修）

| # | 位置 | 插值 | 风险 |
|---|------|------|------|
| A-1 | `render.py:1938` | `toggleFilterInput('{filter_input_name}', this)` | **高**：`filter_input_name` 由 `f_<SQL 列名>` 派生，列名是**用户自己写的 SQL** |
| A-2 | `render.py:4404` | `toggleSection(this, '{title}')` | **高**：`title` 由调用方传入的任意字符串 |
| A-3 | `render.py:4411` | `toggleSection(this, '{title}')` | **高**：同上（multiline 分支） |
| A-4 | `render.py:3300` | `copyToClipboard('api-key-raw-{ep_id}')` | 低（整数 id），但契约统一 |
| A-5 | `render.py:4080` | `copyToClipboard('api-key-raw-{kid}')` | 低（同上） |
| A-6 | `render.py:4137` | `setAuditDateRange('{rkey}')` | 低（字面量表键） |
| A-7 | `render.py:4439` | `copyToClipboard('{code_id}')` | 低 |
| A-8 | `report.py:1871` | `gotoTab('{key}')` | 低（页签键） |

### 2.3 做法

1. **新增单点原语** `render.js_arg(val) -> str`，实现即 `_escape(_js_str(val))`，放在 `_escape` / `_js_str` 旁（`render.py:1158`–`1176` 区间）。
2. **8 处全部改走它**。**关键安全性质**：`_js_str` 对不含 `\ ' CR LF </` 的值是恒等的，故当前数据下**渲染输出零差异**，全部 3,226 个既有测试应**不需要任何断言修改**（此性质作为门禁断言，见 §2.4 第 4 条）。
3. **新增门禁** `tests/test_ui_tokens.py::TestInlineHandlerArgEscaping`，把「一处修对」变成「不可能再错」：
   - 扫描模块集合 = `render` / `report` / `config` / `api_handler` / `export` / `audit_page` / `ui_assets` + `config_pages/*.py`（**自动发现，非硬编码**，见任务 B）；
   - 规则：正则 `on(?:click|submit|change|input)\s*=\s*"[^"]*\{` 命中且该行同时出现 `{` 插值时，该行必须含 `js_arg(` 或 `_escape(_js_str(`；
   - 不含 `{` 的字面量处理器（如 `onclick="gotoTab('memo')"`）**不报**，不得误伤。
4. **RED-GREEN 自证**：把 A-1 临时改回裸露插值，门禁必须 FAIL；还原后必须 PASS（`tests/bug_hunt/gate_redproof.py`）。

---

## 3. 任务 B：事件绑定门禁补盲区（不改生产代码）

### 3.1 已解决的部分（明确不做）

`_swapMain` / `_reinitAfterSwap`（`render.py:675`/`703`）**已经解决**「按钮能点、拖拽报废」：无刷新换页后重建 `<main>` 内全部内联 `<script>` 并重跑 `initPage()` / `initReportPage()`，且有 `TestNoRefreshSwapReinit` / `TestPageInitRegistration` 两组门禁。

**明确放弃的改造**：把 150 处内联 `on*` 属性改成 `document` 级事件委托。理由：
- 内联属性在 `innerHTML` 重新解析时**天然存活**，本就不需要重初始化；
- 改造要动拖拽绑定（`report.py:623`–`680`），而拖拽正是历史事故高发区（`2026-09-30` 用户跨 3 轮反馈才定位）；
- 收益仅为「形式统一」，风险显著大于收益。**用户已于 2026-10-12 明确认可此收缩。**

### 3.2 真实缺口

`TestPageInitRegistration.test_dom_content_loaded_bindings_are_replay_safe`（`tests/test_ui_tokens.py:602`）的扫描范围是**硬编码三元组** `(render, report, config)`。因此：

- `config_pages/branding.py:61,76,77` 的三处裸 IIFE + 元素级 `addEventListener` —— **不在扫描范围内**；
- `ui_assets.py:1743,1746,1920`（`EXCL_EDITOR_JS` 的 `init()`）—— **不在扫描范围内**。

二者今天碰巧合规（`branding.py` 的 IIFE 有 `if (!file) return;` 守卫；`ui_assets.py` 用了 `readyState` 守卫）。**但下一次 AI 加代码时，没有任何机制会拦它。** 这正是本次要堵的洞。

### 3.3 做法

1. 把该门禁的扫描范围从硬编码三元组改为**自动发现的 UI 模块集合**（与任务 A 门禁共用同一份模块清单，放在 `tests/test_ui_tokens.py` 顶部的单一常量里）。
2. 新增检查：页级内联脚本中的元素级 `addEventListener`，其所属 `<script>` 必须落在 `_reinitAfterSwap` 可重放的位置——即位于 `<main>` 内容内，或位于 `initPage()` / `initReportPage()` 可达链上。
3. **零生产代码改动**（任务 B 本身）。加宽后的门禁若报错，按「报错即缺陷」处理——实测 `ui_assets.py` / `config_pages/*` 全部合规，无需生产修复。

### 3.4 已评估并否决的子项（2026-10-12，留证以免重做）

**T6「元素级 `addEventListener` 必须有存在性守卫」——已实现、实测、否决。**

实测结果：命中 12 处，**11 处为门禁误报**，1 处为真缺陷。误报来自三类无法机械区分的写法：

| 误报来源 | 实例 | 为什么机械判定不成立 |
|---------|------|-------------------|
| `forEach` 回调参数 | `render.py:474` `ta`、`render.py:2180` `cb`、`config_pages/reports.py:79` `ta` | 回调参数来自活 NodeList，**不可能为 null** |
| `createElement` 结果 | `config_pages/branding.py:115` `sw` | 新建元素，**不可能为 null** |
| 多变量守卫 | `config_pages/branding.py:77` `text` | 实际是 `if (!picker \|\| !text) return;`，单变量正则匹配不到 |
| 幂等守卫非空守卫 | `report.py:631/644/667/680` `list` | 已有 `list.dataset.dragBound` 幂等标记，且由既有门禁 `test_drag_binding_is_idempotent` 把守 |

要消除误报必须把判定改成「窗口内任何 `if(...)` 提到该变量名即算守卫」，门禁随即退化为弱启发式——**留着一个假阳性率 92% 的门禁，比没有门禁更糟**（它会训练人忽略告警）。

唯一真缺陷已单独修复：`ui_assets.py` `EXCL_EDITOR_JS` 的 `init()` 里 `hiddenBox().closest("form")` 无守卫，理论上为 null 会抛错并终止该 `init()`，已补 `if(!form)return;`。

**结论：T6 不作为门禁落地。** 换页重放类的真实缺陷已由 §3.3 加宽后的 `DOMContentLoaded` 门禁 + 既有 `TestNoRefreshSwapReinit` / `TestPageInitRegistration` 覆盖，无需再加一层。

---

## 4. 任务 C：样式类名契约（降级为「补一处缺口」）

### 4.1 降级理由

JS 实际只切换 **12 个类**：`active` / `hidden` / `on` / `show` / `open` / `sb-rail` / `sb-wide` / `row-highlight` / `picked` / `filter-input-touch` / `collapsed` / `fading-out`。而项目**已有三道门禁**在管这件事：

- `TestJsToggledClassesHaveStyles`（`test_ui_tokens.py:177`）—— 切换类必须有样式规则或已在 alias 表；
- `TestRevealClassContracts`（`:237`）—— 元素级 `display` 规则必须存在；
- `test_state_aliases_cover_production_names`（`:231`）—— **alias 机制已存在**，`.on`/`.open`/`.show` 混用这个历史事故当年就是用 alias 解的。

**因此放弃「全量迁移到 `data-*`」**：要改 `ui_assets.py` 1,470 行 CSS + 12 个切换点 + 3 个门禁断言，churn 远大于增量收益。

### 4.2 保留动作

1. 用一条断言证明 **alias 表覆盖全部 12 个实际切换类**（现门禁只证明「有 alias 的类合规」，不证明「所有类都在 alias 表视野内」）；
2. 缺的补进 alias 表。

---

## 5. 非目标（Anti-goals）

- ❌ **不引入任何框架**：不引 antd / React / Vue / Jinja2 / Node 构建链。硬性 #5（技术选型锁定）**不修改**。
- ❌ **不重构 `render.py`**：4,786 行 f-string 模板保持原样。本次是**外科手术**，不是模板化迁移。
- ❌ **不改 `_swapMain` / `_reinitAfterSwap`**：它已正确工作。
- ❌ **不动数据层**：`result_transform` / `query_executor` / `redis_cache` 是本项目质量最高的部分，一行不改。
- ❌ **不做事件委托重构**：见 §3.1。
- ❌ **不做 `data-*` 全量迁移**：见 §4.1。

---

## 6. 约束与验收

### 6.1 约束

| 约束 | 内容 |
|------|------|
| 零视觉变更 | 本次全部改动**不得**改变任何页面的渲染输出。A-1/A-2/A-3 的转义修复对当前数据是恒等变换（§2.3 第 2 条），须以「全部既有测试零断言修改」为证。 |
| 零测试作废 | 现有 51,099 行测试 / 3,226 用例**不删不改**；只**新增**门禁类。 |
| 零依赖变更 | `requirements.txt` / `install.sh` / 双 README 均不动（硬性 #5 同步三处规则不触发）。 |
| 新门禁须 RED-GREEN 自证 | 硬性 #17：`tests/bug_hunt/gate_redproof.py`。 |
| 交互改动仍走 #17 验收 | 任务 A 改动了报表页 / 审计页的内联处理器 → 「整页 + 原位换页态 + 第二/三次操作 + 组合序列」照跑（`scripts/ui-v2/e2e/`）。 |

### 6.2 规模预估

约 **180 行**（生产代码 ~30 行 + 门禁 ~150 行），**零重构、零框架、零部署变更**。

---

## 7. 预期效果

| 事故类别 | 处置 |
|---------|------|
| 内联处理器因转义失效而**静默执行删除等破坏性操作** | **结构性消除**（原语 + 门禁 + 自证三重） |
| 新增页面级脚本因换页不重放而静默失效 | **盲区封堵**（扫描范围自动发现） |
| JS 切类名与 CSS 不匹配 | 维持既有门禁覆盖，补 alias 表完整性断言 |

---

## 8. 依据时效与冲突处置

现行依据优先级按根 `AGENTS.md` §3：**用户当次指示 > 根 `AGENTS.md` > 最新生效 spec > 旧 spec > plan**。本设计不改变任何视觉口径；若与 `2026-09-30-ui-v2-design.md` 冲突，以那份为准（本次不应产生冲突——零视觉变更）。