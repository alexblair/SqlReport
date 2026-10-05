# UI v2「石墨·鸢尾」实施报告

> 状态: 已实施并验证
> 对应 spec: `../spec/2026-09-30-ui-v2-design.md`
> 对应 plan: `../plan/2026-09-30-ui-v2-plan.md`
> 确认稿（用户已确认方案 A）: `../spec/ui-v2-draft/index.html` · `preview-reports-v2.html`
> 最后更新: 2026-09-30

## 1. 交付内容

| 项 | 结果 |
|---|---|
| 公共视觉层换装 | `render._BASE_CSS`（令牌/基座/登录页/独立页）+ `render._COMMON_CSS`（页壳/组件/页面级规则）成为唯一来源 |
| 页面级补丁下线 | `report._CSS`、`config._CONFIG_EXTRA_CSS`、`config._REPORTS_EXTRA_CSS`、`server` 登录页与错误页内联样式全部删除；`_MINIBTN_CSS` / `_FLASH_WARN_CSS` / `_B6_CSS` 并入公共层并清零 |
| 内联样式清理 | render 270→130、report 26→12、config 55→15、filter_help 26→8（其余为布局/行为性声明，按 spec §5.3 保留） |
| 报表配置页方案 A | 废弃 10 列表格 → **分组卡 `.cat-block` + 层级导轨 `.cat-children` + 行卡片 `.rpt-row`**；卡片形态 `.rpt-card` 保留；两形态同数据各渲一份、勾选按 value 镜像 |
| 代码面（SQL 高亮） | 9 个新令牌，底色与文字色**强制成对声明**；8 个词法色逐个实算对比度 |
| UI 门禁 | 新增 `tests/test_ui_tokens.py`（12 用例）：令牌齐备 / 20+ 组对比度 ≥4.5:1 / 页面级补丁为空 / 产物无表现性内联样式 / 方案 A 结构存在 |

## 2. 验证证据（程序化）

| 检查 | 命令 / 方法 | 结果 |
|---|---|---|
| 全量测试 | `python -m unittest discover -s tests/ -t .` | **Ran 2960, OK (skipped=4)** |
| UI 门禁 | `python -m unittest tests.test_ui_tokens -v` | 26 OK（遮罩默认隐藏 / JS class 覆盖 / 对话框形态 / 内联 JS 语法 / 换页重初始化 5 例）|
| 生产渲染 · 溢出 | headless Chrome 实测 `scrollWidth - clientWidth`，11 页 × 1440（报表配置另测 1280/1920） | **全部 0** |
| 全屏遮挡物 | 10 页扫描「`position:fixed` 且覆盖 ≥80% 视口的可见元素」 | **0 个**（详情页提交后遮罩按预期出现）|
| 交互组合场景 | `scripts/ui-v2/e2e/e2e-combo.mjs`（字段×筛选×排序叠加） | 5/5 通过（含「全选仅调顺序」）|
| 导出交叉选择 | `scripts/ui-v2/e2e/e2e-export.mjs`（格式×字符集×ZIP×智能去引号×自定义列） | 8/8 通过；JSON 恒 UTF-8、CSV 仍默认 GBK |
| 生产渲染 · 报表配置页 | 11 张行卡片 + 4 个分组卡 + 1 条层级导轨；三档视口零溢出 | 通过 |
| 表现性内联样式 | 渲染产物正则扫描（颜色/背景/边框/字号/内外边距/尺寸） | 报表配置页 **0**、概览 **0**、审计 **0**、连接池 **0**、登录 **0**；详情 51 + 接口 64 + 报表中心 1 + 调度 2（合计 118，全部为帮助弹窗与 JS 拼接串，见 §4） |
| 代码面可读性 | CDP 读计算样式 + 截图像素复核 | 正文 **14.88:1**（旧 1.02:1）；关键字 8.42 / 函数 10.1 / 字符串 11.08 / 数字 10.88 / 注释 6.43 |
| 令牌对比度 | `_contrast()` 实算（不钉 hex 字面量） | 主文字 17.9 / 次文字 6.7 / 辅助 4.8 / 主色文字 8.5 / 白字压主色 4.9 |
| 截图 | `../spec/shots/ui-v2-final/live-*.png` | 11 张（PC 1440 + 报表配置 1280/1920） |

## 3. 本轮修掉的三类结构性缺陷（此前反复「改不干净」的根因）

1. **语义靠内联样式承载**：列宽 `style="width:…"`、父子层级 `margin-left/border-left`、配色 `style="color:#4f46e5"`。
   清理内联样式即丢语义 → 名称列被压成一字一行、层级消失。**改为**：列宽体系（`table-fixed` + `<colgroup>` + 156px 兜底）、层级导轨 class、语义令牌。
2. **class 撞名**：`.sql-head` 在生产是「SQL 列表头」钩子，被挪用为代码工具条 → 该列表头字号/高度与别列不一致。**改为**：代码工具条统一 `.code-head`，表头全局统一 12px / 38px。
3. **多 class 各写一半**：`<pre class="sql-debug code-block">` 命中 `.code-block{深色字}` + `.sql-debug{深底色}` → 正文 **1.02:1 隐形**。**改为**：底色与文字色成对声明 + 8 个词法色重定 + 门禁断言。

## 4. 已知遗留（下一轮，不影响本轮验收）

1. **帮助弹窗与 JS 拼接串内的表现性内联样式**：全站合计 118 处，集中在 `filter-help-popup`（筛选语法帮助，报表页/审计页共用）、`nf-help-popup`（嵌套筛选表达式帮助）、`api-meta`/`md-body` 的 Markdown 内容、以及 `btn-mini`/`btn`/`drag-handle`/`field-up` 等 JS 拼接串。
   成因：这些 `style` 跨越相邻字符串字面量拼接，或含 f-string 花括号，自动化清理会破坏 Python 语法；已在 spec §5.3 记为「保留布局性、清理表现性」的收尾项。
2. **其余宽表**（连接池/用户/审计/调度）仍用自动布局表格：已加「第 2 列 ≥156px」兜底，未逐表给 `<colgroup>`。
3. **卡片视图**在报表配置页已可用；其余页面无卡片形态需求。

## 4.5 用户实测回归：登录后整页被「查询中…」遮住（已修 + 已加门禁）

**现象**（用户截图）：登录后进入报表中心，整页被半透明遮罩与「查询中…请稍候」覆盖，无法操作。

**根因**：我在把加载遮罩改为「默认隐藏」时，把 `display:none` 插到了规则**开头**，
而该规则原有的 `display:flex` 仍在同一条规则的**后面** —— CSS 同规则内后者胜，等于没隐藏。
（`.show{display:flex}` 那条反而是多余的。）

**修复**：基础规则只保留 `display:none`，显隐完全交给 `.show`。

**验证**：
- 10 个页面全量扫描「`position:fixed` 且覆盖 ≥80% 视口的可见元素」→ **0 个遮挡物**，且全部零溢出；
- 反向确认功能未被修坏：报表详情页提交查询前遮罩 `display:none`，提交后 `display:flex` + class 含 `show`。

**新增门禁**（`tests/test_ui_tokens.py::TestOverlayDefaultsHidden`，3 用例）：
① 遮罩基础规则的**最后一条** `display` 必须是 `none`（专门防「同规则内被后面的声明覆盖」这类坑）；
② `.show` 规则存在且为 `display:flex`；
③ `.side-panel`/`.modal` 等 JS 切换显隐的组件基础态同样必须隐藏、`.open` 才显示。

> 教训并入知识库 06 卷：**同一条 CSS 规则内重复声明会相互覆盖**，改「默认隐藏」时必须删掉同规则里原有的 `display`。

## 4.6 用户实测回归②：字段设置 / 排序设置 / 导出对话框全部点不开（已修 + 已加门禁）

**现象**（用户截图）：报表页「字段设置 / 排序设置」按钮点了没反应，弹层不再出现。

**根因**：**class 名不一致**——生产 JS 给抽屉/对话框/遮罩加的是 `.on`：
```js
el.classList.add('on');            // 抽屉、对话框
bd.classList.add('on');            // 遮罩
```
而我的确认稿 CSS 只写了 `.side-panel.open{display:flex}` / `.backdrop.show{display:block}`。
确认稿里之所以能用，是因为那是**我自己的胶水 JS**（用的 `.open`）；生产 JS 从未改过。于是 `.on` 加上了，但没有任何规则响应 → 点了等于没点。

**修复**：CSS 同时认两种名字（`.on` 为主、`.open`/`.show` 为别名）：
`.side-panel.on,.side-panel.open{display:flex}` · `.modal.on,.modal.open{display:flex}` · `.backdrop.on,.backdrop.show{display:block}`。

**顺带修掉同一个错法引发的第二处**：导出对话框的 DOM 是 `head / body / foot` **三个并列兄弟**（无包装盒），
我却按「遮罩 + 单个 `.modal-box`」写样式 → 三段被 flex 排成一行（每段 469px 并排）。
已改为「遮罩 + 三段纵向堆叠合成一张卡」（同宽 520、首段上圆角、末段下圆角）。

**实机验证**（CDP 点击 + 计算样式）：

| 操作 | 结果 |
|---|---|
| 初始 | `#fieldSettingsPanel` display none；`#report-backdrop` none |
| 点「字段设置」 | 抽屉 flex 400×900；遮罩 block 1440×900 |
| 按 ESC | 抽屉 none（关闭正常） |
| 点「排序设置」 | 抽屉 flex 400×900 |
| 点「导出」 | 对话框 flex；三段同左缘 460、同宽 520、纵向相接（183→237→662），上/下圆角 14px |

**新增门禁**（`tests/test_ui_tokens.py`）：
- `TestJsToggledClassesHaveStyles`：从生产 JS 源码提取全部 `classList.add/toggle('X')` 字面量，逐个回查公共 CSS 是否有对应规则；
- `test_state_aliases_cover_production_names`：`.on`/`.open`/`.show` 三套名字必须同时可用；
- `test_modal_supports_sibling_sections`：`.modal` 必须纵向排列，且 `> .modal-head/body/foot` 均声明宽度。

## 4.7 用户实测回归③：字段顺序不生效（已修 + 已补组合场景 E2E）

**现象**（用户反馈）：排序弹窗修好后，「字段的选择与字段顺序」配置不生效——尤其「表头 A B 改成 B A」。

**逐场景实测后的三个真因**（都在 JS，且互相叠加）：

| # | 根因 | 影响 | 修法 |
|---|---|---|---|
| 1 | `applyFieldSettings` 只在「勾选数 < 总列数」时才带 `cols=` | **全选状态下只调顺序 → 不发送参数 → 顺序丢失**（用户所指现象） | 只要有勾选就发 `cols`（顺序即列序）；0 列时给出「至少要保留一列」提示 |
| 2 | `applyFieldSettings` / `applySortSettings` 各自重建 URL，只保留 sort 与 f_/op_ | 组合操作时 `cols`、`nested_filter`、`sql_query` 被**静默清空** | 抽出统一 `buildReportUrl()`：显式处理 id/page_size/result/sort/dir/cols，其余参数一律透传；`cols` 在调用方未覆盖时沿用当前值 |
| 3 | 我在 JS **块注释里写了 `f_*/op_*`**，其中的 `*/` 提前结束注释 | 报表页整块 footer 脚本语法错误 → `applyFieldSettings`、`applySortSettings` 等**全部 undefined**，按钮点了完全没反应（控制台无 Log 级错误） | 改写注释；并新增 `node --check` 语法门禁 |

**组合场景实测矩阵**（`scripts/ui-v2/e2e/e2e-combo.mjs`，真实点击 + 校验 URL/列序/数据）：

| 场景 | URL 关键参数 | 结果列序 | 行数 | 判定 |
|---|---|---|---|---|
| ① 隐藏 customer | `cols=id,amount,created_at` | id, amount, created_at | 3 | 通过 |
| ② **全选仅调顺序** | `cols=id,amount,customer,created_at` | **id, amount, customer, created_at** | 3 | 通过（原缺陷） |
| ③ 顺序 + 筛选(customer 含 o) | cols + `op_customer=contains&f_customer=o` | id, amount, customer, created_at | 2 | 通过 |
| ④ 顺序 + 筛选 + 排序(amount desc) | cols + 筛选 + `sort=amount&dir=desc` | id, amount, customer, created_at | 2（Bob→Carol） | 通过 |
| ⑤ 再次调顺序 | 上述参数**全部保留** | 同 ④ | 2 | 通过 |

**导出交叉选择实测矩阵**（`scripts/ui-v2/e2e/e2e-export.mjs`，每例重置状态）：

| 组合 | format 一致 | charset | ZIP | 智能去引号 | 响应 |
|---|---|---|---|---|---|
| CSV + GBK（默认） | ✓ | gbk | — | 禁用/清零 | `text/csv; charset=gbk` |
| CSV + UTF-8 | ✓ | utf8 | — | 禁用 | `text/csv; charset=utf-8`（带 BOM） |
| CSV + ZIP | ✓ | gbk | 1 | 禁用 | `application/zip`（PK 魔数） |
| JSON（默认 charset） | ✓ | gbk | — | **启用** | `application/json; charset=gbk`（既有契约，见下） |
| JSON + UTF-8 | ✓ | utf8 | — | 启用 | `application/json; charset=utf-8` |
| JSON + 智能去引号(十进制) | ✓ | gbk | — | 隐藏位=1 | `"amount": 250.5`（数字裸输出） |
| 自定义列（默认已勾选） | ✓ | gbk | — | 禁用 | 表头按 `cols=customer,amount,id` 顺序输出 |

**顺带加固**：导出表单里隐藏 `<select id="export-format-select">` 原本也带 `name="format"`，
导致 `format` 参数重复提交（radio + select 各一个）。服务端取第一个才侥幸正确，两侧一旦不同步就会导错格式 →
已去掉该 select 的 `name`（它只作提示联动的状态镜像）。

**既有契约（非本轮引入，未改）**：JSON 导出沿用所选 charset（默认 GBK），`tests/test_export.py` 有断言钉住
`application/json; charset=gbk`。若你希望 JSON 固定 UTF-8（RFC 8259 建议），我可以改，但需同步改测试与文档口径。

**固化的资产**：`scripts/ui-v2/e2e/`（5 个 CDP 脚本 + README）：组合场景、导出交叉、弹层开关、全屏遮挡物、排序在缓存/大表上的表现。

## 4.8 收口：JSON 导出固定 UTF-8 + HTML 禁缓存

### ① JSON 导出固定 UTF-8（按既有约定，用户 2026-09-30 决策）

**约定依据**：`api_handler.py` 全部 8 处 JSON 响应都是 `application/json; charset=utf-8`；README/知识库对 API 亦为 UTF-8。
唯独导出路径（`export.py`）沿用面板所选字符集，默认 GBK → JSON 用 GBK 编码，UTF-8 解码即乱码，也不合 RFC 8259。

**改动（三层一致）**：
- 服务端：`export.handle_export` 解析后强制 `if export_format == "json": charset = "utf8"`（含 ZIP 内的 `.json`）——
  即使直接构造 `/export?format=json&charset=gbk` 也一定是 UTF-8；
- 面板：选 JSON 时把字符集单选**置为 UTF-8 并禁用**，并显示提示「JSON 固定 UTF-8（RFC 8259，与 API 响应一致）」；回到 CSV 自动恢复可选；
- 文档：`knowledge/03-report-transform.md` 导出小节的口径已同步（CSV 默认 gbk 不变）；
- 测试：`tests/test_export.py` 里 2 处「JSON+gbk」断言与相关解码改为 UTF-8，用例 `test_06_json_forces_utf8_charset` 改名以反映新契约。

**实测**：

| 请求 | Content-Type | 结果 |
|---|---|---|
| `/export?id=1&format=json&charset=gbk`（直连，绕过面板） | `application/json; charset=utf-8` | UTF-8 解码 + `json.loads` 成功，中文键名正常 |
| `/export?id=1&format=csv`（默认） | `text/csv; charset=gbk` | 既有契约不变 |
| 面板选 JSON | 提交 URL **不含 charset**（控件被禁用） | 响应同第一行 |

### ② HTML 响应禁缓存（消除「你修了但我还看到旧的」）

`_send_html` 现在发送 `Cache-Control: no-store, must-revalidate`。
根因：HTML 里**内联了页脚脚本**，无缓存头时标签页可能长期执行旧脚本——用户已两次遇到「修复上线后依旧表现为坏了」。
静态资产仍走 `/static/vendor/self@<hash>` + `immutable`（内容哈希天然免污染）。
门禁：`tests/test_ui_tokens.py::TestHtmlFreshness` 断言 `_send_html` 必须带 `Cache-Control: no-store`。

## 4.9 用户实测回归④：隐藏→还原→再排序后「拖拽排序报废」（架构级根因，已修）

**用户复现步骤**（逐字）：id=4 报表 → 隐藏 id → 应用（正常）→ 勾回 id → 应用（正常）→ 再排序 → **无法排序，且拖动排序功能报废**。

### 根因（Phase 1 取证结论）

报表页的 `navigateTo` **自己复制了一份换页逻辑**，只做一件事：

```js
oldMain.innerHTML = newMain.innerHTML;   // ← 就这一行
```

而 `innerHTML` 赋值有两条被忽略的语义：

1. **不会执行新 `<main>` 里的内联 `<script>`** —— 而这些脚本正是 `<main>` 内各功能区的初始化（导出对话框格式联动、嵌套筛选构建器、结果集切换、调试 SQL 高亮…）；
2. **不会重跑任何初始化** —— `initDragHandlers()` / `initSortDragHandlers()` 是在 `DOMContentLoaded` 时绑到**当时那个** `#fieldList` / `#sortList` 元素上的；换页后元素被整体重建，**监听器随旧元素一起消失**。

所以：任何一次「应用」（字段设置、排序、筛选、分页…）之后，所有靠 `addEventListener` 绑定的交互都静默失效；而按钮是内联 `onclick`，仍能点 → 表现为**「按钮能点、拖拽报废」**，与用户描述完全一致。公共侧的 `_swapMain`（render.py）虽然调了 `initPage()`，但报表页那份副本**连 `initPage()` 都没有**。

### 修复（统一实现 + 换页重初始化）

| 改动 | 内容 |
|---|---|
| 单一实现 | 报表页 `navigateTo` 删除自有副本，统一委托公共 `_swapMain`（缺失时兜底为整页跳转） |
| `_reinitAfterSwap()` | 换页后：① 逐块重建 `<main>` 内 `<script>` 使其重放；② 调 `initPage()`；③ 调 `initReportPage()` |
| `initReportPage()` | 报表页专有初始化（字段/排序列表拖拽），由 `DOMContentLoaded` 与换页钩子共用 |
| 幂等 | 拖拽绑定加 `dataset.dragBound` 标记（随元素生命周期） |
| `onReady(fn)` | 定义在**头部内联引导脚本**（外链 common.js 是 defer，晚于 body 内联脚本）。首次解析绑 `DOMContentLoaded`，换页重放时 `readyState==='complete'` → 立即执行；把 7 处页面级初始化从「只绑 DOMContentLoaded」改为 `onReady` |

### 顺带修掉的排序面板缺陷

`#sortList` 预置的「暂无排序」占位块**加排序项时不清除**，导致：占位框一直挂在列表顶部、序号从 2 开始、`moveSortItem` 的 `list.children` 下标整体错一位。
现改为：占位块 `.sort-empty` 由 `syncSortEmptyState()` 统管（有项即移除、清空即恢复），序号由 `renumberSortItems()` 重排，`moveSortItem`/`applySortSettings` 只遍历 `.sort-item`。

### 实测（`scripts/ui-v2/e2e/swap-reinit.mjs`，真实点击/合成拖拽）

| 步骤 | 结果 |
|---|---|
| id=4 隐藏 id → 应用 | `cols=customer,status`，表格两列 ✓ |
| **换页后拖拽字段** | id,customer,status → **status,id,customer** ✓（修复前此处失效） |
| 勾回 id → 应用 | `cols=status,id,customer` ✓ |
| 第二次换页后拖拽 | → **customer,id,status** ✓ |
| 加两个排序项 | `customer:desc,status:asc`；占位块已移除、序号 1,2 ✓ |
| 应用排序 | URL `sort=customer&dir=desc&sort=status&dir=asc`，排序条 `① customer ↓ ② status ↑` ✓ |
| 换页后拖拽排序项（**1→0 反向拖**） | `customer:desc,status:asc` → **status:asc,customer:desc** ✓ |
| 换页后页面胶水函数 | `applyFieldSettings/applySortSettings/openPanel/navigateTo` 全为 `function` ✓（内联脚本已重放） |
| 换页后导出对话框联动 | 选 JSON → 字符集禁用 + 提示显示（内联脚本已重放）✓ |
| 换页后嵌套筛选 | 树节点已渲染 ✓ |
| 控制台异常 | **0**（先前修复过程中一度出现 `onReady is not defined`，已由头部前置定义解决）|

> 两个**假结论**教训（已写进 `08-testing-conventions.md` 易踩坑 21）：
> ① 排序项拖拽用 0→1 时顺序不变——`moveSortItem` 是「插到目标项之前」，0→1 本就是 no-op，要验必须**反向拖或跨项拖**；
> ② `typeof toggleResultIndex` 报 `undefined`——该函数只在多结果集报表才输出（id=4 是单结果集），
> 存在性判据要选**始终存在**的页面胶水函数。

新增门禁（`tests/test_ui_tokens.py::TestNoRefreshSwapReinit`，5 例）：换页实现唯一、`_reinitAfterSwap` 重建脚本并调两个钩子、`onReady` 前置、拖拽绑定幂等、排序占位块受管。

## 5. 门禁立功记录

`tests/test_ui_tokens.py` 上线即抓到一处真实缺陷：`--warn-ink #a96000` 在 `--warn-soft #fff4e0` 上只有 **4.42:1**（低于 AA）。
已在**令牌层**修为 `#9a5700`（白底 5.62:1 / 警示软底 5.16:1），而不是只改某个 chip —— 否则 `.flash-warn`、`.badge-warn`、`.banner` 等用法都会漏网。

## 6. 变更文件

- 生产代码：`render.py`（CSS 常量 + 报表配置页结构 + 动态类样式 + `selectAllInSection`/`toggleCatBlock`）、`report.py`、`config.py`、`server.py`、`filter_help.py`
- 测试：`tests/test_ui_tokens.py`（新增）、`tests/bug_hunt/gate_redproof.py`（复盘轮新增）、`tests/test_render.py`、`tests/test_config_extra.py`、`tests/test_ux_b6_polish.py`、`tests/test_report_extra.py`、`tests/test_state_machine.py`、`tests/test_feedback_loop_b5.py`（断言改为语义/正则，不再钉空格与旧 hex）
- 文档：`docs/compose/spec/2026-09-30-ui-v2-design.md`（新增）、`docs/compose/plan/2026-09-30-ui-v2-plan.md`（新增）、`docs/compose/knowledge/06-ui-interactions.md`（UI v2 体系 + 7 条约定）、`docs/compose/knowledge/INDEX.md`；`ui-redesign-visual-spec.md` / `ui-redesign.md` 标注「已被取代」；`docs/compose/reports/ui-v2-retrospective.md`（复盘轮新增）

## 7. 复盘轮（2026-09-30）：14 类缺陷 → 机制

用户要求「把发现的 BUG 和犯的错归纳总结，下次不要再犯」后，本轮不再改产品功能，只做**防复发基建**（完整复盘见 `ui-v2-retrospective.md`）：

| 产出 | 内容 |
|------|------|
| 新增门禁 3 类 4 例 | `TestNoDuplicateDeclarations`（同规则内重复声明属性）、`TestPageInitRegistration`（每个 init 必须被 `initPage()`/`initReportPage()` 调用；内联脚本不得无条件裸绑 `DOMContentLoaded`）、`TestFormControlNameUniqueness`（同名控件不得混用类型）；`test_ui_tokens.py` 26 → **30 例** |
| 门禁自证工具 | `tests/bug_hunt/gate_redproof.py`：把 4 条门禁对应的历史缺陷打回去（RED 必失败）再还原（GREEN 必通过），**4/4 通过**；临时改写 `report.py` 时 try/finally + sha256 校验还原，残留 `.bak` 拒绝启动 |
| 顺带清理 | 删除 `initApiUrls`/`initCatTree` 各自重复的 `DOMContentLoaded` 注册（首次加载执行两遍、换页后一次不跑）——页面级初始化只允许 `initPage()`/`onReady()` 一条路径 |
| 文档 | `06-ui-interactions.md` 新增「交互改动验收（硬性 #17）+ 失败模式库」与易踩坑 16；`08-testing-conventions.md` 新增易踩坑 20–23；`AGENTS.md` 硬性 #17 + 收尾检查单第 6 条；`MEMORY.md` Rules 12–14 |
| 证据 | `tests/test_ui_tokens.py` 30 OK；L1 `test_render*` 374 OK、`test_report*` 190 OK、`test_ux*` 59 OK、静态分析 5 OK；L2 全量 `Ran 2964 OK (skipped=4)`（日志在 `run-logs/ui-v2/`） |
