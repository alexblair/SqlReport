# UI 体系与交互（ui-redesign 重构后 · render 单一来源）

> 与根 `AGENTS.md` 硬性 #17 对齐；现行视觉口径 = UI v2「石墨·鸢尾」（`docs/compose/spec/2026-09-30-ui-v2-design.md`，2026-09-30 已实施）。ui-redesign 的视觉与组件部分已被 UI v2 取代，仅作过程记录。

## 单一来源与设计令牌（必须）

- **设计令牌唯一来源 = `render.py` 的 `_BASE_CSS: :root`**（色板 / 字阶 11·12·13·14·16·18·22·28 / 间距 4px 栅格 / 圆角 / 阴影 / 焦点圈）。页面与分卷**不得另起颜色、间距取值**；颜色、背景、边框、字体、内外边距、尺寸、阴影、透明度一律走 class/令牌，`style="…"` 只允许 display/visibility/gap/flex/align/text-align/overflow 等布局行为性声明。
- 视觉只在两层：`render._BASE_CSS`（令牌 + 基座 + 登录页）+ `render._COMMON_CSS`（页壳/组件/页面级规则）——二者**字面量已外移到 `ui_assets.py`**（B9-1），`render._X` 是兼容名。`report._CSS` / `config._CONFIG_EXTRA_CSS` / `config._REPORTS_EXTRA_CSS` / server 登录页与错误页内联样式均为同名空常量（仅兼容既有引用）。局部样式走 `render_page_header(extra_css=...)`，**不要改 `_COMMON_CSS` 塞局部样式**。
- **公共 CSS/JS 用内容 hash 版本锁目录**：`ensure_common_assets()` 写 `static/vendor/self@{sha8}/common.css|js`，hash = `sha256(CSS+"\n;;;"+JS)` 前 8 位（改 JS 也换 URL）；`/static/vendor/` 直出 + `immutable`。外链 URL 另有进程级缓存（`_COMMON_ASSET_URLS`）：改了 **`ui_assets.py`**/`render.py`/`report.py`/`config.py`（或 `config_pages/`）必须**重启服务再验**，否则仍指向旧 hash 目录。
- **`render.py` 有模块级 `logger`**（`logging.getLogger(__name__)`）：`_get_common_asset_urls` 写盘失败必须 `logger.exception` 留痕——失败会把 `("", "")` 哨兵**永久缓存**，之后每页内联约 100KB 且永不重试（曾静默无信号，B6-5）。**禁止**在模块级调 `basicConfig`（`setup_logging` 之前 render 就可能被 import）。
- **HTML 响应必须 `Cache-Control: no-store`**：页脚脚本内联在 HTML 里，不设禁缓存时用户标签页可能长期执行旧脚本（症状「修复上线了但用户那儿还是坏的」）。
- **`_escape` 只有一份**（`render._escape`，`config` 直接 import 复用，B7-2）：它先 `format_cell` 再 `escape` → `Decimal` 不会显示成科学计数法。**不得**在别处另写 `html.escape(str(v))`。
- **`<option>` 里的层级缩进必须用全角 `\u3000`**（B7-3 / D4）：半角空格会被 HTML 折叠 → 缩进不可见。每级 1 个全角。
- 术语：全部用户可感知文字简体中文；术语表见 `docs/compose/spec/ui-redesign-visual-spec.md` §5（UI v2 未重定术语，该节继续有效；prefer_cache/Redis 快照等实现词禁止直出 UI）。

## 统一 UI 体系（必须复用）

- 页面骨架：`render_page_header(...)` + 区块 `build_*` + `render_page_footer()`。表格/分页/筛选条/排序面板/字段设置/确认删除等已有 `build_*`，**新页面只拼装，不新写一套 class/布局/第二份 CSS**。
- 报表页不再内联 `_COMMON_JS`：页面胶水经 `render_page_footer(extra_js=...)` defer 追加（`report._FOOTER_GLUE`：字段/排序面板、导出对话框、触屏筛选、`openPanel`/`gotoTab` 等）。
- 交互初始化统一走 `initPage()` / `initReportPage()`（DOMContentLoaded 与每次无刷新换页后重跑，**须幂等**）；页面级脚本一律用 `onReady(fn)`，不用裸 `DOMContentLoaded`。
- 危险操作统一 `confirm`（文案模板：动词 + 对象 + 影响范围）；品牌统一 **SqlReport**（branding 前缀仍只改 `<title>`）。
- 测试会把 vendor 根重定向到临时目录（`tests/_bootstrap.py`），**勿依赖真实 `static/vendor/self@*` 路径断言**。

## UI / 视觉 / 交互任务流程（硬性 #17）

适用：设计稿落地、UI 优化、视觉与交互改版、新页面或区块的交互示意——凡「用户会看到的界面怎么变」都算。

| 阶段 | 必须动作 | 禁止 |
|------|----------|------|
| ① 确认素材 | 产出**可交互 HTML**（可点开、可点选/切换等关键交互可演示）交用户确认 | 只给口头描述、静态截图或 markdown 草图就当已确认 |
| ② 用户确认 | 等待用户明确确认（或按确认稿修订后再确认） | 未确认就改 `server`/`render`/`config` 等生产代码 |
| ③ 实施 | **严格按已确认的 HTML/确认结论**落到 `render_page_header` + `build_*` + `extra_css` | 随意发挥、擅自改布局/文案/交互，与确认稿不一致 |
| ④ 一致性 | 确认稿与生产都复用 `_BASE_CSS`/`_COMMON_CSS`/`_COMMON_JS` 与既有 `build_*` 形态 | 把外部草稿或一次性混乱 DOM/CSS 直接拷进生产 |

- 确认稿放 **`docs/compose/spec/` 同目录**，**不进 `static/`**（属过程素材，不被服务直出）；确认稿路径同样禁止写死主目录。先例：`docs/compose/spec/ui-redesign-prototype.html`。
- 确认稿要可交互、结构按既有 `build_*` 输出示意（勿嵌套 form、勿发明新 class 体系）；确认后实现仍以 `render` 单一来源拼装，**不是**把确认稿 HTML 原样粘进 Python 字符串。
- 收尾自检：确认要点（布局/文案/交互/状态）在实现中一一对应、无交付与确认不符；无混乱 DOM/CSS 直塞；本卷与必要的 `tests/test_render.py` 结构用例同步。

## 门禁（改 CSS/JS/HTML 后先跑）

- `tests/test_ui_tokens.py`：令牌齐备、20+ 组前景/背景对比度 ≥4.5:1、页面级补丁为空、渲染产物无表现性内联样式、JS 实际切换的类有元素级 display 规则、内联 JS 语法（`node --check`）、换页重初始化与 init 注册契约。**改 CSS 后必须先跑它。**
- `tests/test_render.py`：HTML 结构用例（分类树 `.cat-children`/`.kids` 等 class 契约）。
- `tests/htmlcheck.py`：无嵌套 form + 标签平衡（**允许 SVG 图形元素自闭合**，`_SVG_SELF_CLOSING_OK`）；主表单含 submit 与保存/保存并关闭；API Key 区不得入主 form span。
- **新门禁必须做 RED-GREEN 自证**：`venv/bin/python tests/bug_hunt/gate_redproof.py`——把历史缺陷打回，门禁必失败（RED）；还原后必通过（GREEN），全绿才算门禁有效。

## 交互改动验收（硬性 #17）

来源：2026-09-30 用户实测「隐藏列 → 还原 → 再排序 → 拖拽报废」跨 3 轮反馈才定位；根因不在某一行，而在验收方式——只做「整页加载后点一次」，看不见换页态、组合操作、第二次交互。完整复盘：`docs/compose/reports/ui-v2-retrospective.md`。

### 提交前逐条过（缺一即未完成）

凡改动碰了 JS 交互（面板/拖拽/筛选/排序/导出/换页）：

1. **两种载入态都验**：整页加载 + 操作一次后的**原位换页态**（分页/筛选/字段/排序/导出/移动都会触发换页）。
2. **验到第二、三次操作**：换页后拖拽、连续两次应用、先隐藏再还原再排序。
3. **组合顺序要验**：字段顺序 × 筛选规则 × 排序 × 导出交叉（`scripts/ui-v2/e2e/e2e-combo.mjs`、`scripts/ui-v2/e2e/swap-reinit.mjs`）。
4. **注册路径唯一**：新增 init 必须进 `initPage()`/`initReportPage()`；页面级脚本用 `onReady(fn)`；换页实现只有 `_swapMain` 一份。
5. **删样式必问语义归属**：默认隐藏（display）、列宽、底色/文字成对——删掉后旧语义由谁承担？改公共 CSS 时必须**同步核对 JS 实际切换的类名**（元素级契约），漏一侧就是「点了没反应」。
6. 改了 `render.py`/`report.py`/`config.py` 后**重启服务再验**（见「内容 hash 版本锁目录」）。

### 换页机制（症状：按钮能点、拖拽报废）

无刷新换页只走公共 `_swapMain` → `_reinitAfterSwap()`；`innerHTML` 赋值**不执行** `<main>` 内联 `<script>`、**不重跑**初始化，靠 `addEventListener` 绑定的交互（字段/排序列表拖拽等）换页后静默失效，而内联 `onclick` 仍能点。

## 失败模式库（真实事故；能机械检测的已做成门禁，勿靠“记住”）

| 症状 | 根因 | 拦截 |
|------|------|------|
| 代码块文字隐形（1.02:1） | 底色与文字色分属两条规则、配对丢失（`<pre class="sql-debug code-block">` 同时命中「深底」「深字」） | `TestContrastGate`（成对声明 + 对比度实算） |
| 整页被「查询中…」遮罩盖住 | 同规则内 `display` 被后面的声明覆盖（先 `display:none` 后 `display:flex`，后者胜） | `TestOverlayDefaultsHidden` + `TestNoDuplicateDeclarations` |
| 面板/对话框/展开区点不开 | 元素级类名契约缺失：JS 切 `.on` 而 CSS 只认 `.open`/`.show`（`.api-more.on`、`.tree .kids.on` 同款） | `TestRevealClassContracts` + `TestJsToggledClassesHaveStyles`；E2E `scripts/ui-v2/e2e/api-row-expand-check.mjs` |
| 按钮能点、拖拽/下拉失效 | 换页只 `innerHTML` 替换：不执行内联脚本、不重跑初始化 | `TestNoRefreshSwapReinit` + `TestPageInitRegistration` |
| 「按钮点了没反应」且控制台无 Log 错误 | JS 块注释里出现 `*/`（如写通配符 `f_*/op_*`），注释提前结束、整块脚本语法错误 | `TestInlineJsSyntax`（`node --check`） |
| 组合操作后 `cols`/`nested_filter` 被静默清空 | 字段设置/排序各自重建 URL，未走统一构造 | `buildReportUrl(overrides)` 单一构造 + `tests/test_report.py::test_apply_sort_settings_preserves_filters_and_cols` |
| 排序项序号从 2 起、`moveSortItem` 越界判断失真 | `#sortList` 占位块未受管，`list.children` 下标整体错位 | `TestNoRefreshSwapReinit::test_sort_placeholder_managed`（`syncSortEmptyState`） |
| 「修复上线了但用户那儿还是坏的」 | HTML 响应未禁缓存，标签页长期跑旧内联脚本 | `TestHtmlFreshness`（`Cache-Control: no-store`） |
| 隐藏页卡里的 mermaid 流程图永远空白（16×16 空框） | `startOnLoad:true` 在 window load 渲染 `display:none` 页卡，量测全 0 并打 `data-processed`，事后 `mermaid.run` 直接跳过 | `TestMermaidTabRenderContract`（须 `startOnLoad:false`，`gotoTab`/`initReportPage` 调 `renderTabMermaid`）+ `scripts/ui-v2/e2e/mermaid-tab-check.mjs` |
| SQL 编辑框整段没有滚动条（长 SQL 被裁） | `.sql-editor` 按「容器」写带 `overflow:hidden`，而生产把该类直接挂在 textarea 上 | `TestSqlEditorScrollContract`（`.sql-editor` 永不设 overflow，滚动契约归 `.sql-textarea{overflow:auto}`）；复测 `scripts/ui-v2/e2e/probe_computed_style.py` |
| **删除/禁用按钮的确认框不弹，直接执行（数据安全）** | **HTML 转义误用于 JS 上下文**：`_escape` 产出 `&#x27;`，浏览器解析 HTML 属性时解码回 `'`，JS 源码语法错 → `onsubmit` 为 null → 表单直接提交。名称含 `'`（如 `O'Brien`）或以 `\` 结尾时触发 | `TestDeleteConfirmJsEscape` + `TestToggleConfirmJsEscape`（把生成的 JS 真的 `exec` 一遍断言文案）；**契约：JS 上下文必须先 `_js_str` 再 `_escape`，即 `_escape(_js_str(raw))`，且调用点传原文** |

## 其他硬约定（压缩；组件/页面/DOM 细节见 `render.py`，codegraph 可查符号）

- **列宽体系**：宽表用 `table.table-fixed` + `<colgroup>`（`col.c-check/c-name/c-sql/c-cfg/c-pool/c-memo/c-path/c-api/c-ops`）；无 colgroup 的表保留「第 2 列 ≥156px」兜底（历史事故：列宽原由内联 `width` 承载，清理后名称列被压成一字一行）。**10 列表格已废弃**（1440 视口右栏仅 856px，必然挤压）。
- **class 不得撞名**：`.sql-head` 是「SQL 列表头」钩子，曾被挪用为代码工具条致表头错乱；代码面工具条统一用 `.code-head`。
- **动态类必须有样式**：JS 运行时切换的 `.hidden`/`.show`/`.fading-out`/`.row-highlight`/`.btn.loading`/`.filter-input-touch`/`query-loading-overlay.show` 必须在公共层定义（遮罩默认 `display:none`，仅 `.show` 显示）；由 JS 切 class 的组件（`.side-panel`/`.modal`）基础态必须隐藏，`.on`/`.open`/`.show` 才显示。
- **侧栏收缩三态记忆**：`sqlreport_sidebar_collapsed` 无值=默认、1=收起、0=展开；改语义须同步 `_SIDEBAR_BOOTSTRAP_JS`、`sbStoreWrite` 与 `_COMMON_CSS` 三处；读写异常向 UI 明示（`window.__sbStorageErr` + `showFlashWarn`），不静默降级。
- **`buildReportUrl(overrides)`**：报表页 URL 唯一构造，显式处理 id/page_size/result/sort/dir/cols，其余参数（`nested_filter`、`sql_query`、`f_*`、`op_*`）一律透传。
- **JSON 导出恒 UTF-8**：`export.handle_export` 解析后强制 `charset="utf8"`（含 ZIP 内 `.json`）；导出面板选 JSON 时把字符集单选置为 UTF-8 并禁用，CSV 仍默认 GBK。镜像控件**不带 `name`**，避免同名参数重复提交。
- **`_PAGE_HEADER_TEMPLATE.substitute` 有两处调用**（`render_page_header` 与 `render_audit_page`）：新增模板占位符必须两处同步传参，漏一处即 `KeyError`。
- 验收脚本自身的坑（陈旧 cookie、`Page.navigate` 清空 `window.*`、选择器想当然、`children` 下标被占位元素污染、拖到自己身上是 no-op）见 `08-testing-conventions.md` 易踩坑 #22、#28 与「两败必停」。

## 改 UI 前阅读顺序

1. 本卷 + 根 `AGENTS.md` 硬性 #17。
2. `docs/compose/spec/2026-09-30-ui-v2-design.md`（**现行**令牌/组件/页面口径）；`docs/compose/spec/ui-redesign-visual-spec.md` 已标注「已被取代」（**例外：§5 术语表继续有效**），其余仅供追溯。
3. `render.py`：`_BASE_CSS`/`_COMMON_CSS` → `_COMMON_JS` → 侧栏/页壳 → 相关 `build_*`（codegraph 可查符号）；页面地图与路由见 `INDEX.md`。
4. `tests/htmlcheck.py` + `tests/test_ui_tokens.py` / `test_render*`。

## 依据时效与冲突处置（硬性 #22）

- **现行依据优先级**：用户当次指示 > 根 `AGENTS.md` > 最新生效 spec（本域 = `docs/compose/spec/2026-09-30-ui-v2-design.md`）> `render.py` 现行代码 > 历史 spec/plan/截图。
- **设计对比图是取证，不是依据**：`docs/compose/spec/ui-v2-draft/shots/` 与 `docs/compose/spec/shots/**` 记录「当时长什么样」（含 before/after 与已废弃变体）；**禁止据历史截图推断「界面应该长什么样」**；资产版本与生成口径见 `docs/compose/spec/ui-v2-draft/shots/VERSION.md`。
- **发现冲突立即确认**：用户要求与上述现行依据不符（或与历史截图一致但与现行 spec 不符）时，**立刻 `ask_user_question` 问一个选择题**（「按用户要求」 vs 「按现行 spec」），并记裁决；**禁止在两者之间反复自我怀疑、反复对比截图兜圈**。
- 裁决后按硬性 #3/#7 回写：改代码则同步本卷；推翻设计则改 spec 并走取代两头改。

## 取证成本纪律（硬性 #17：先定位，后取证）

**Chrome/截图是「证据最硬、成本最高」的手段，不是默认动作**（启动 + 字体/双 rAF 等待 + 像素回验，单次数十秒到分钟级）。默认先用代码层定位：

| 先用这些（秒级） | 只有这些才值得起浏览器（十秒~分钟级） |
|---|---|
| `codegraph explore` 定位符号/调用链；`grep` 查字面量；读源码与门禁 | 需要**运行时计算样式/几何/布局**证据（如元素被 `overflow:hidden` 裁掉、宽度算错） |
| `tests/test_ui_tokens.py` / `test_render*` / `htmlcheck.py` 等静态门禁 | 交互在 **DOM 事件层**（换页后初始化未重跑、拖拽失效、页卡渲染时机） |
| 静态分析（`tests/bug_hunt/`）与单元测试 | 用户报的是**视觉现象**且代码层无法判定 |
| 已有根因假设 → 直接改代码 + 门禁复验 | **修复后的最终视觉确认**（一次即可） |

**硬规则**：

1. **能代码层定性的，不启动浏览器**——先给根因假设与代码证据；只有证据确实需要运行时数据才起 Chrome。
2. **一次会话批量验完**：一个 CDP 会话里跑完全部待验项（`scripts/ui-v2/e2e/probe_computed_style.py`、`mermaid-tab-check.mjs` 即此模式）；**禁止「改一行 → 截一次图」**。
3. **能做成门禁的优先做成门禁**：门禁毫秒级且可回归，截图不能回归。
4. 报结论必须写清证据来源（`文件:行` / 门禁名 / 截图路径）；**不得用未验证截图下 CSS/交互结论**（`MEMORY.md` Rules #1）。
5. 用户报 BUG 时：**代码定位 → 根因假设 →（必要时）一次取证 → 修复 → 门禁复验**，不要先截图再猜。
