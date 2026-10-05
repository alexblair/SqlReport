# UI 体系与交互（ui-redesign 重构后 · render 单一来源）

> 与根 `AGENTS.md` 硬性 #11 对齐（完整流程见本卷「UI / 视觉 / 交互任务流程」）。
> 最后同步：**UI v2「石墨·鸢尾」**（`docs/compose/spec/2026-09-30-ui-v2-design.md`，2026-09-30 已实施）
> 历史：ui-redesign（`ui-redesign.md`）视觉与组件部分已被 UI v2 取代，仅作过程记录
> + 2026-09-29 从 AGENTS.md 迁入「统一 UI 体系」与 UI 任务流程完整四阶段。
> + 2026-09-30 复盘同步（硬性 #17 与失败模式库）：14 类缺陷与 10 条流程错误归档在
> `docs/compose/reports/ui-v2-retrospective.md`；门禁 `tests/test_ui_tokens.py` 30 例 +
> 门禁自证 `tests/bug_hunt/gate_redproof.py`（4/4 RED-GREEN）。

## UI v2「石墨·鸢尾」体系（2026-09-30 起，当前生效）

**单一来源**：全部视觉只在 `render._BASE_CSS`（令牌+基座+登录页+独立页）+ `render._COMMON_CSS`（页壳/组件/页面级规则）。
`report._CSS` / `config._CONFIG_EXTRA_CSS` / `config._REPORTS_EXTRA_CSS` / `server` 登录页与错误页内联样式
**已全部删除**（保留同名空常量以兼容既有引用）；`_MINIBTN_CSS` / `_FLASH_WARN_CSS` / `_B6_CSS` 已并入公共层并清零。

**令牌**（`:root`）：中性冷石墨色板 + 单一鸢尾主色 `--accent #5d61e0`；语义四色各配 `-ink/-soft/-line`；
**代码面（深色）**：`--code-bg #0f131b` 与 `--code-ink #e2e6ef` 等 9 个令牌，**底色与文字色必须成对声明**
（历史事故：`<pre class="sql-debug code-block">` 命中「深底」与「深字」两条规则 → 正文 1.02:1 隐形）；
字阶 11/12/13/14/16/18/22/28；间距 4px 栅格；圆角 4/6/10/14；阴影三层。

**关键约定（新增/变更）**：
1. **禁止表现性内联样式**：`style="…"` 只允许布局/行为性声明（display/visibility/gap/flex/align/text-align/overflow 等）；
   颜色、背景、边框、字体、内外边距、尺寸、阴影、透明度一律走 class/令牌。
2. **列宽体系**：宽表用 `table.table-fixed` + `<colgroup>`（`col.c-check/c-name/c-sql/c-cfg/c-pool/c-memo/c-path/c-api/c-ops`）；
   无 colgroup 的表保留「第 2 列 ≥156px」兜底，防止名称列被压成一字一行（历史事故：列宽原由内联 `width` 承载，清理后挤压）。
3. **class 不得撞名**：`.sql-head` 在生产是「SQL 列表头」钩子，曾被挪用为代码工具条 → 表头错乱；
   代码面工具条统一用 `.code-head`。
4. **表头统一**：`table th` 12px / 行高 18px / 高 38px / `--ink-2`；`.table-wrap` 保留「表内滚动 + `max-height:calc(100vh - 130px)`」契约。
5. **报表配置页 = 方案 A**：`.cat-block`（分组卡）+ `.cat-head`（折叠钮/深度色点/名称/计数/hover 操作/全选）+
   `.cat-children`（**层级导轨**：1px 竖线 + 节点横线 + 逐级缩进，替代原内联 `margin-left+border-left`）+
   列表形态 `.rpt-row` 行卡片（名称 / 配置 chips / 连接池 / 接口 / 备注 / SQL 摘要 / hover 操作）+
   卡片形态 `.rpt-card`；两形态同数据各渲一份（`.view-list`/`.view-card` 语义不变），勾选按 value 镜像。
   **10 列表格已废弃**（1440 视口右栏仅 856px，必然挤压）。
6a. **class 名必须与生产 JS 完全一致**：抽屉/对话框/遮罩由 JS 切 `.on`（`.side-panel.on` / `.modal.on` / `.backdrop.on`），
   `.open`/`.show` 仅为确认稿别名，CSS 两套都要认。事故：按确认稿只写 `.open` → 生产点「字段设置/排序设置」毫无反应。
   门禁：`tests/test_ui_tokens.py::TestJsToggledClassesHaveStyles` 从 JS 源码提取 classList 字面量回查 CSS。
6a2. **对话框形态**：生产导出对话框是 `.modal` 内 `head/body/foot` 三个并列兄弟（无包装盒）→ `.modal` 必须 `flex-direction:column`，
   否则三段会被排成一行。新增 `.modal-box` 包装形态时两种都要兼容（门禁 `test_modal_supports_sibling_sections`）。
6c. **JS 块注释里禁止出现 `*/`**（例如写通配符 `f_*/op_*`）：`*/` 会提前结束注释，整块脚本语法错误，
   该页所有函数都变 undefined——表现为「按钮点了没反应」且控制台**没有** Log 级错误。
   门禁：`tests/test_ui_tokens.py::TestInlineJsSyntax` 用 `node --check` 校验 `_COMMON_JS` / `_FOOTER_GLUE`。
6d. **报表页 URL 统一由 `buildReportUrl(overrides)` 构造**：显式处理 id/page_size/result/sort/dir/cols，
   其余参数（`nested_filter`、`sql_query`、`f_*`、`op_*`）一律透传。历史缺陷：字段设置/排序各自重建 URL，
   组合操作时 `cols`、`nested_filter` 被静默清空；且「全选仅调顺序」不发 `cols` → 顺序不生效。
   门禁：`tests/test_report.py::test_apply_sort_settings_preserves_filters_and_cols` + E2E `e2e-combo.mjs`。
6f. **JSON 导出恒 UTF-8**：`export.handle_export` 在解析后强制 `charset="utf8"`（含 ZIP 内 `.json`）；
   导出面板选 JSON 时把字符集单选置为 UTF-8 并禁用（控件禁用后不参与提交）。CSV 仍默认 GBK。
   约定依据：`api_handler.py` 全部 JSON 响应为 `application/json; charset=utf-8`；RFC 8259。
   门禁/用例：`tests/test_export.py::test_06_json_forces_utf8_charset`、`test_json_export_headers_gbk`（已改为 utf-8 口径）。
6g. **HTML 响应必须 `Cache-Control: no-store`**：页脚脚本是内联在 HTML 里的，不设禁缓存时
   用户标签页可能长期执行旧脚本（表现为「修复上线了但用户那儿还是坏的」）。
   静态资产仍走 `/static/vendor/self@<hash>` + `immutable`。门禁 `TestHtmlFreshness`。
6e. **镜像控件不要带 `name`**：导出对话框的隐藏 `<select id="export-format-select">` 曾与 radio 同名 `format`，
   造成同名参数重复提交（靠服务端「取第一个」侥幸正确）。控件只作状态镜像时去掉 `name`。
6h. **无刷新换页（navigateTo）只允许一份实现**：统一走公共 `_swapMain` → `_reinitAfterSwap()`。
   `innerHTML` 赋值**不执行** `<main>` 内联 `<script>`、**不重跑**初始化 → 靠 `addEventListener` 绑定的交互
   （字段/排序列表拖拽等）换页后全部静默失效（按钮因内联 onclick 仍可用，故表现为「按钮能点、拖拽报废」）。
   页面级脚本一律用 `onReady(fn)`（定义在头部内联引导脚本）而非裸 `DOMContentLoaded`。
   门禁：`tests/test_ui_tokens.py::TestNoRefreshSwapReinit`；E2E：`scripts/ui-v2/e2e/swap-reinit.mjs`。
6i. **`#sortList` 的「暂无排序」占位块必须受管**：加排序项要移除、清空要恢复（`syncSortEmptyState`），
   序号按 `.sort-item` 数量重排；否则占位块常驻、序号从 2 起、`list.children` 下标错一位（`moveSortItem` 越界判断失真）。
6b. **同规则内不要重复声明同一属性**：设「默认隐藏」时只保留 `display:none`，
   若同一条规则后面还留着 `display:flex`，后者胜 → 等于没隐藏。
   实测事故：登录后整页被「查询中…」遮罩盖住（`.query-loading-overlay`）。
   门禁：`tests/test_ui_tokens.py::TestOverlayDefaultsHidden` 断言基础规则**最后一条** `display` 为 `none`。
   另：`.side-panel`/`.modal` 等由 JS 切 class 的组件，基础态必须隐藏、`.open`/`.show` 才显示。
6. **动态类必须有样式**：JS 运行时切换的 `.hidden` / `.show` / `.fading-out` / `.row-highlight` / `.btn.loading` /
   `.filter-input-touch` / `query-loading-overlay.show` 必须在公共层定义（遮罩默认 `display:none`，仅 `.show` 显示）。
7. **门禁**：`tests/test_ui_tokens.py` 钉住令牌齐备、20+ 组前景/背景对比度 ≥4.5:1、页面级补丁为空、
   渲染产物无表现性内联样式、方案 A 结构存在。**改 CSS 后必须先跑它。**

## 原则

- **禁止**新写一套 class/布局/第二份 CSS；页面 = `render_page_header` + `build_*` + footer
- 局部样式：`extra_css=`，不要改 `_COMMON_CSS`（设计令牌在 `_BASE_CSS` `:root`）
- 全部用户可感知文字简体中文；**术语表**见 `docs/compose/spec/ui-redesign-visual-spec.md` §5 术语表（UI v2 未重定术语，该节继续有效；prefer_cache/Redis 快照等实现词禁止直出 UI）
- 危险操作：统一确认（`confirm` 文案模板：动词+对象+影响范围）；无第二套框架
- 品牌：侧栏/登录/浏览器标题统一 **SqlReport**（branding 前缀仍只改 `<title>`）

## 统一 UI 体系（必须复用）

- 页面骨架：`render.render_page_header(...)` + 区块 `build_*` + `render.render_page_footer()`。
- 表格、分页、筛选条、排序面板、字段设置、确认删除等已有 `build_*` 函数；**新页面只拼装，不新写一套 class/布局**。
- 公共样式/脚本：`_BASE_CSS` / `_COMMON_CSS` / `_COMMON_JS`（及按钮、flash 等切片）。启动时 `ensure_common_assets()` 写入 `static/vendor/self@{sha256前8位}/common.css|js`，由 `/static/vendor/` 直出。
- 页面特有 CSS 通过 `render_page_header(extra_css=...)` 追加，**不要改全局公共块来塞局部样式**。
- 测试会把 vendor 根重定向到临时目录（`tests/_bootstrap.py`），勿依赖真实 `static/vendor/self@*` 路径断言。

## UI / 视觉 / 交互任务流程（硬性 #11）

适用：设计稿落地、UI 优化、视觉与交互改版、新页面或区块的交互示意——凡「用户会看到的界面怎么变」都算。

| 阶段 | 必须动作 | 禁止 |
|------|----------|------|
| ① 确认素材 | 产出**可交互 HTML**（可点开、可点选/切换等关键交互可演示）交给用户确认 | 只给口头描述、静态截图或 markdown 草图就当已确认 |
| ② 用户确认 | 等待用户明确确认（或按确认稿修订后再确认） | 未确认就改 `server`/`render`/`config` 等生产代码 |
| ③ 实施 | **严格按已确认的 HTML/确认结论**落到 `render_page_header` + `build_*` + `extra_css` | 随意发挥、擅自改布局/文案/交互，与确认稿不一致 |
| ④ 一致性 | 确认稿与生产实现都复用全局视觉：`_BASE_CSS`/`_COMMON_CSS`/`_COMMON_JS`、既有 class、按钮/表单/表格/折叠等 `build_*` 形态 | 把外部草稿或一次性混乱 DOM/CSS 直接拷进生产 |

**确认素材要求**（做 HTML 确认稿时）：

1. **全局视觉特性**：页壳、导航、色彩/字号/间距、按钮与表单样式尽量对齐站内现状；局部差异用页面级 `extra_css` 表达，不另起第二套设计语言。
2. **组件语义对齐**：结构按既有 `build_*` 输出的 DOM 形态示意（勿嵌套 form、勿发明新 class 体系）；确认后实现时仍以 `render` 单一来源拼装，**不是**把确认稿 HTML 原样粘贴进 Python 字符串了事。
3. **可交互**：与本次相关的点击、折叠、切换、hover/禁用等至少可演示；纯静态不可点的稿不能单独充当「已确认」。
4. **路径可移植**：确认稿路径/引用同样禁止写死主目录（硬性 #10）；确认稿属过程素材，不并入生产 `static/` 被服务直出，除非另有明确交付要求。

**完成后自检（绝对禁止项）**：

- [ ] 用户确认过的要点（布局、文案、交互、状态）在实现中均可一一对应，**无交付与确认不符**。
- [ ] 生产 HTML 仍由 `render` + `build_*` 拼装，公共 class/CSS 来自 `_COMMON_*`，**无混乱 DOM/CSS 直塞**、无破坏全站一致。
- [ ] 未把「确认稿原样字符串」当成实现捷径绕过组件体系。
- [ ] 相关本卷已随变更同步（及必要时 `tests/test_render.py` HTML 结构用例）。

**先例**：`docs/compose/spec/ui-redesign-prototype.html`（用户已确认的一轮完整走通），
素材与截图在 `docs/compose/spec/shots/`。

## 骨架与资产

| 符号 | 作用 |
|------|------|
| `_BASE_CSS` | 设计令牌（`:root` 色板/圆角/阴影/焦点圈）+ reset + fadeUp |
| `_COMMON_CSS` | 侧栏页壳 + **侧栏三态收缩**（`html.sb-rail`/`html.sb-wide`/无类=默认；≤1024px 默认图标条、`sb-wide` 为 240px 覆盖层；`pointer:coarse` 手柄加宽 28px）+ **全高手柄 `.sb-handle`/`.sb-arrow`**（右边整条任意高度可点，箭头随指针移动、方向=下一步动作）+ **R3 侧栏账号区修复**（`.account{margin-top:auto}` 账号区吸底——**勿改 spacer 为 flex:1**：生产每导航组后各一个 spacer（共 4 个，确认稿仅 1 个），撑开致组间 283px 空白（R3 反馈 2026-09-29）；吸底与组间距解耦；`html.sb-rail` 与 ≤1024px 媒体查询两处 `.account` 均改**纵向两行**（`flex-direction:column`，头像 26px 上/退出图标 26px 下），`.sb-arrow` 在 rail 态 mousemove 时 y 钳制在 `.account.top-14` 之上） + 通用组件 + 令牌化按钮/表格/卡片/分页/flash + 新组件（page-head/tabs/toolbar/side-panel/modal/formbar/badge/filterbar/batch 相关/api-row 行卡片/grid-2 双栏+card-head/`rule-row`·`rule-group` 排除规则行组等）+ 合成历史切片 |
| `_icon(name)` | 图标辅助函数（替代 emoji 字符），返回设计规范内联 SVG HTML。集合：alert/search/file/settings/list/folder/chart/key/calendar/refresh/check/x/info/edit/plus/copy/trash/download/database/users/eye/play/link/chevron-* |
| `_COMMON_JS` | 折叠/复制/flash/过滤/最近查看/列记忆/loading/Tab 缩进 + **侧栏手柄 `initSidebarHandle`/`sbIsRail`/`sbStoreWrite`**（记忆 key `sqlreport_sidebar_collapsed`：1=收起、0=展开、无值=默认；切换方向按「状态类+matchMedia」联合判定；读写异常**向 UI 明示**——读失败经引导脚本记 `window.__sbStorageErr`、initPage 用既有 `showFlashWarn` 提示一次，写失败 `sbStoreWrite` 内直接 flash-warn，不静默降级）（**三态 setMemToggle/initMemToggles 已删除**） |
| `_SQL_HIGHLIGHT_JS` / `_SQL_FORMATTER_JS` | SQL 高亮/格式化（编辑表单与详情调试按需） |
| `ensure_common_assets` | 写 `static/vendor/self@{sha8}/`，**hash = sha256(CSS+"\n;;;\n"+JS) 前 8 位**（改 JS 也会换 URL） |
| `render_page_header(title, active_nav, extra_css, nav_badges, current_user)` | `<head>`（含 `$sidebar_bootstrap`：`_SIDEBAR_BOOTSTRAP_JS` 内联脚本在 CSS 前读 localStorage 设 `sb-rail`/`sb-wide` 防闪烁，读失败记 `window.__sbStorageErr` 待 UI 明示）+ 侧栏 + container 开头；`current_user` 未传时回退请求上下文 `get_request_user()` |
| `set_request_user` / `get_request_user`（render） | 请求级当前登录用户名（`threading.local`，每请求一线程隔离）；server `_handle` 入口复位 None、`_authenticate` 成功注入——页面渲染层零传参拿到用户名 |
| `render_page_footer(extra_js="")` | 闭合 container/main/app + 外链 common.js + 可选页面级 `defer` 胶水 JS |
| `_NAV_GROUPS` / `render_sidebar` / `render_navbar`(兼容别名) | **侧栏分组导航单一来源**（分析/管理/服务/治理 + 账户区：展开态=头像+当前用户名+「退出」，`sb-rail`=头像(hover 显名)+退出图标；末尾恒有 `.sb-handle` 全高手柄） |

**JS 单轨（C16）**：报表页不再内联 `_COMMON_JS`；页面胶水经 `render_page_footer(extra_js=...)` defer 追加（report._FOOTER_GLUE：字段/排序面板、导出对话框、触屏筛选、openPanel/gotoTab 等）。

## 全局布局（R2）

- `.container { width:100% }` + 宽屏阶梯 `max-width`：1440 →（≥1700px）1680 →（≥2100px）1920 →（≥2600px）2400。
- `.split` 基准 `260px minmax(0,1fr)`；≤1024px 单列 `minmax(0,1fr)`（grid-2/grid-3 同断点收单列）。
- `.section-title` 全局 flex 化（右侧 `.actions` 用 `margin-left:auto` 右贴）。

## 页面地图（重构后）

| 路由 | 渲染 | 核心交互 |
|------|------|----------|
| `/login` | `server._LOGIN_PAGE`（令牌化登录，SqlReport 品牌） | 登录表单、过期/错误、`next` |
| `/` → `/report` | 302 | — |
| `/report`（无 id） | **报表中心** `render_report_selector`：页头搜索 + 最近查看卡片 + 左分类树 + 右报表卡片网格 | 客户端搜索/分类过滤、localStorage 最近查看、空态三步引导 |
| `/report?id=` | `_build_report_html`：**页头(面包屑/h1+紧凑切换器/操作组/缓存状态行) + 横幅 + 备注摘要条 + 五页签（数据/规则/接口/调试/备注）** | 页签切换 `gotoTab`；列设置/排序=右侧抽屉 `openPanel`；导出=统一对话框；高级筛选按钮跳规则页签；筛选/清除/帮助仍在数据页 |
| `/report/preview` | POST 预览 | 协议不变 |
| `/export*` | 对话框 GET 提交 | 格式/字符集/智能引号/ZIP/列范围（选项常显） |
| `/config` | **概览仪表盘** `render_overview`：统计磁贴 + 快捷入口 + `grid-2`（左系统状态 / 右「导入演示数据（DEBUG）」卡）+ 站点标识独立成行（不嵌 card，去卡中卡） | 池/用户 CRUD 已迁出 |
| `/config/pools`（bare→list） | `render_pools_page`（独立列表；表 6 列含「关联报表」=渲染层 `get_all_reports` 按 pool_id 分组的报表名链接，不改 DB） | 增删改/复制/测试连接/移动 |
| `/config/users`（bare→list） | `render_users_page`（表 3 列：用户名｜角色说明｜操作；users 表无 role 字段，角色说明按平权管理员实际语义渲染 + 底部约定 help 行） | 同上；回跳锚点 `/config/users#user-N` |
| `/config/reports` | `render_reports_page`：页头搜索 + **左分类树右报表表**（`split_parts=True` 拆分）；左栏 `build_category_manage_section_html`（见下「报表配置左栏分类树」）；**R3 双视图**：页头 `.segment#rpt-view-seg`「列表/卡片」全局开关 `setReportsView(v,save)`（作用于**全部层级** `.view-list`/`.view-card`，默认列表、localStorage `sqlreport_reports_view` 记忆；两视图同数据各渲一份，勾选按 value 镜像 + `pickedReportIds()` 去重，批量条计数不翻倍）；页级样式 `_REPORTS_EXTRA_CSS`（=`_CONFIG_EXTRA_CSS`+`#sec-reports` 作用域：分组卡头 `.section-title .ico`、SQL 窄列+title、cfg 三列改 **1px 竖分隔线**归组（弃浅蓝底色块，与整表白底冲突）、`.pool-chip` 单行截断连接池、`.rpt-grid`/`.rpt-card` 卡片、列宽表内自适应 1366+ 无横向溢出） | 勾选浮出批量条、`#sec-categories` 兼容；`initConfigFilter`/`initAnchorRowHighlight` 已兼容 `.rpt-card` |
| `/config/reports/{id}/edit` | 分区表单（①基础 ②SQL ③缓存与护栏 ④调度与保活）：page-head+crumb 置于主 form 起始处、主 form 内 `.grid-2` 双栏 + **sticky `formbar` 在 form 底**（保存/保存并关闭在主 form 内）；**④ 卡内含关联定时任务只读摘要 `render.build_report_schedule_summary_html`（复用 `db.get_all_schedules` 的 report_ids 过滤）+「+ 新建调度」→ `/config/scheduler/new?report_id=N`**；查看/预览按钮在 page-head（`previewReport(this.form)` 协议不变）；表单下方（form 外）追加接口列表 api-row | 与 htmlcheck 门禁兼容 |
| `/config/api-endpoints` | `render_api_endpoints_page`：page-head（h1+统计 sub+「+ 新建接口」→首张报表 `api_endpoints/new`，**无报表回 `/config/reports/add`**）；列表 = `build_api_endpoints_list_html` 输出 **真卡片 `div.api-row`**（`.api-main` 主行：名称/路径徽标/关联报表/状态/格式/Key/操作；`.api-more` 展开区：输出模式/全量/静态 meta+**说明全文（不截断，`title` 仅兜底）**+三 URL），点击主行或「展开 ▾」钮切换（`_COMMON_JS` `apiToggleMore`/`apiMainClick`；旧 api-card-table 已删） | toggle/编辑/删除/复制协议不变 |
| 端点表单 | page-head+crumb + 分区（①基本信息 ②调用地址 ③请求与输出 ④JSON 模板），主 form 内 `.grid-2`，`form-actions formbar span-full` 在 form 底 | Key 区仍在主 form 外 |
| `/config/scheduler` | **列表主导** `render_scheduler_page`（页头+新建按钮+全局停用横幅置顶；单表 7 列对齐原型：任务名/关联报表/计划/下次执行/上次结果/状态/操作，已收敛「上次执行/失败计数」两列；**无「最近执行记录」第二张表**，执行历史到审计日志查询；表下 help 提示徽标语义） | 行操作/回跳；POST 协议不变 |
| `/config/scheduler/new`、`/config/scheduler/{id}/edit` | `render_scheduler_form_page`（独立表单页；page-head+crumb；主 form 内 `.grid-2`（左「计划」｜右「关联报表」）→ 独立「排除规则」卡 → `formbar` 在 form 底；排除规则 = `rule-row`/`rule-group` 可视化树编辑器 `exclToggleSource()` 切「源码」JSON 模式，产出 JSON 写隐藏域 `exclusions`；**新建页支持 `?report_id=N` 预勾绑定**（报表编辑页「新建调度」入口带参，仅新建生效、编辑态以库内绑定为准，非法参数忽略）；遗留 `?edit=N` 兼容直渲染表单） | 排除规则树/绑定表 |
| `/audit` | `render_audit_page`：page-head actions=「导出 CSV」+「清理过期」（原筛选条内清理钮移位，POST `action=clean` 参数不变）；filterbar 与表格**裸排无 card 包裹** | 类型/日期快捷/关键字/导出/清理（筛选交互不动） |
| `/health`、`/api/…` | 无页壳 | — |

### 报表详情数据页顺序

页头 → 横幅(flash/预览/截断/写护栏/缓存降级) → 备注摘要条 → 页签 → 数据面板：工具行(行数/页大小/**结果集 segment**/列设置/排序/高级筛选/重建缓存/缓存徽标；`build_controls_bar_html(result_html=...)` 在页大小后插入) → 筛选动作行 → 排序条 → 隐藏 ff 表格 form → 表格(第 1 行列头排序 + 第 2 行 `tr.qf-row` 独立快筛行，`f_/op_` 与 `form="ff"` 协议不变；报表页 CSS 快筛输入选择器由 `th .filter-input` 下沉为 `.qf-row .filter-input`) → 分页(`build_pagination_html(always=True)` 恒显：单页/空结果也渲染)。规则页签=`grid-2` 左右双卡(左=嵌套条件构建器，右=当前规则 JSON 复制/应用)；接口页签=card+card-head(「本报表的 API 接口」+「新增 API 接口」(report_id>0 指向该报表新建表单，空态同样保留) +「管理全部接口」) 内嵌 `build_api_urls_section_html`，其**委托 `build_api_endpoints_list_html`** 输出 api-row 卡片(与列表页同一实现)；调试页签=card「执行信息（Debug）」+ `grid-3` 统计磁贴 + `sql-debug code-block` SQL 代码块；备注页签=普通卡片(card+card-head+md-body，折叠与三态记忆已废除)。结果集切换 JS：`switchResult(btn)` 按钮版(数据属性挂 `.result-selector` 容器，`btn.dataset.index`，sessionStorage 记忆回跳协议不变)。

### 报表配置左栏分类树（R2-A，R3 基准修订 2026-09-29）

**R3 基准=确认稿 r3 左树**（用户裁定，推翻本节原 R2-A 观感描述的部分）：行 13px/`padding 5px 8px`、计数 `font-weight:600`、**操作组默认 `display:none` hover 才 `inline-flex`**、DOM 序=图标→名称→`.ops`→`.cnt`、树顶静态高亮首行「全部报表 N」（`build_category_manage_section_html(total_reports=...)`，None 不渲染）、左树头部=**粗体标题式折叠钮 `.tree-toggle`（ghost 无描边）+ 右侧仅「新增分类」单行**（新增报表入口在页头与未分类区；`show_report_add` 仅存签名兼容）。样式全部 `#sec-reports` 作用域，**卡片头样式限定 `.split > div .section-title`（右栏），左栏 `aside.card .section-title` 保持普通 flex 行**。图标仍为 SVG（emoji 回退会破坏 R2 已确认的 `_icon` 体系，用户确认保留 SVG）。

`build_category_manage_section_html`（render.py）：`.tree/.cat` flex 行 = SVG 文件夹图标 + 名称 + `.cnt` 报表数角标 + `.ops` ghost 操作（✎编辑 ↑↓移动 ✕删除，`btn-ghost btn-icon`）；子分类包 `.kids` 容器逐级缩进，父行点击 `toggleCatNode(ev,row)` 折叠/展开（区块标题 `toggleCatTree` 整体折叠，localStorage 记忆）。**不再使用 ├─ 文本引导线**（原 `config.py` 的 `.tree-guide/.cat-tree-item` 死 CSS 已于 R2 核对时删除，勿再引入）。

**展开/收起类名契约（2026-10-06 修复，勿再回退）**：UI v2 落公共 CSS 时只抄了确认稿类名，把生产 JS 实际切换的类名弄丢了两处，表现为「按钮文案/箭头会动、面板或子分类不动」（用户实测反馈 `/config/api-endpoints` 展开 收起 失效）：

1. **API 行展开区**：`_COMMON_JS` 的 `apiToggleMore` 切的是 `.api-more` 上的 `.on`，而 `_COMMON_CSS` 当时只认 `.api-row.open .api-more` → 现为 `.api-row.open .api-more,.api-more.on{display:block}`（同 `.side-panel.on,.side-panel.open` 的双别名惯例；`.api-row.open` 保留给确认稿/预览稿 `make_preview.py` 用）。
2. **分类树子节点**：`.tree .kids{display:none}` + `.tree .kids.on{display:block}` 是**唯一**的折叠实现（`toggleCatNode` 切 `.on`）。两张树共用该选择器：`/config/reports` 左树 markup 带 `on`（默认展开，点父行折叠）；`/report` 报表中心 `#rc-tree` markup **不带** `on`（默认收起，点右侧 `[data-chevron]` 展开）。
3. **改公共 CSS 的铁律**：元素级对齐——JS 在哪个元素上切哪个类，CSS 就必须有针对**那个元素 + 那个类**的显示规则；类名全局存在不等于该元素可用（`on` 在 `.side-panel` 上有效，在 `.api-more` 上曾是空的）。门禁：`tests/test_ui_tokens.TestRevealClassContracts`（元素级，自证见 `gate_redproof.py` 第 5 条）。

## 组件库（按需全量见 render.py）

**通用**：`build_flash_html` / `build_empty_row_html` / `build_pagination_html` / `build_collapse_section_html`(**三态 mem_key 已废除**，仅保留参数兼容) / `build_config_filter_box_html` / `build_delete_form_html` / `build_move_buttons_html` / `build_export_modal_html`(T7.4 新增)

**报表**：`build_controls_bar_html`(工具行) / `build_table_*` / `build_sort_bar_html` / `build_filter_*` / `build_field_settings_panel_html`+`build_sort_settings_panel_html`(side-panel 抽屉) / `build_nested_filter_builder_html` / `build_current_rules_section_html` / `build_debug_section_html` / `build_memo_section_html` / `build_result_selector_html` / `build_cache_badge_html`(术语化) / `build_redis_banners_html` / `build_report_switcher_html` / `build_api_urls_section_html`

**配置/API/调度**：`build_pool_*` / `build_user_*` / `build_category_*`（`split_parts=True` 支持左树右表）/ `build_api_endpoints_list_html` / `build_api_endpoint_form_html` / `build_api_key_manage_html` / `build_scheduler_page_html` / `build_scheduler_task_form_html` / `build_schedule_flags_badge_html` / `build_report_schedule_summary_html`（报表编辑④卡关联任务摘要+新建调度入口） / `build_state_span` / `render_audit_page` / `render_pools_page` / `render_users_page` / `render_overview` / `render_api_endpoints_page`

## 交互模式（无框架）

1. 服务端整页渲染，无 SPA 框架；页内页签/抽屉/对话框用 `gotoTab` / `openPanel`/`closePanel`/`closeAllPanels`（`_FOOTER_GLUE`，ESC/遮罩关闭）。**客户端无刷新导航已引入**：`_COMMON_JS` 提供 `navigateTo(url)`（fetch + `history.pushState` 原位替换 `<main>` 内容，失败回退整页跳转）与 `_swapMain`；`popstate` 拦截浏览器前进/后退同样原位换页。已接入：分页跳页 `goPage`、筛选搜索、每页条数/报表切换 select、`applySortSettings`/`applyFieldSettings`/`switchResult`、紧凑报表切换器；**上移/下移箭头**（`/config/{section}/{id}/move-up|move-down` 表单）由 submit 拦截器 fetch POST 跟随 302 后原位换页，保持滚动位置不跳顶（无 JS 时回退原生提交）
2. `_COMMON_JS` 初始化统一走 `initPage()`（DOMContentLoaded 与每次 `_swapMain` 换页后重跑，须幂等）：`initApiUrls` `initSidebarHandle`(手柄 `data-sb-bound` 防重复绑定) `initCatTree` `initFlashMessages` `initAnchorRowHighlight` `initQueryLoadingOverlay`(全站提交遮罩方向，表单/按钮带 `data-ov-bound` 防重复绑定) `initConfigFilter` `initRecentReports` `initSqlEditorTabIndent`（**initMemToggles 已删**）
3. 危险操作 POST + confirm 模板；成功 302 + `?flash=`
4. localStorage：树折叠、`data-mem-key`(旧键不再写入)、最近查看、列设置 `sqlreport_cols_{id}`
5. 状态 hidden 透传（筛选/排序/cols/nested_filter）协议不变
6. checkbox：`hidden 0` + checkbox `1`，`parse_qs` 取最后值

## HTML 质量门禁

`tests/htmlcheck.py`：
- 无嵌套 form + 标签平衡；**允许 SVG 图形元素自闭合**（`_SVG_SELF_CLOSING_OK`）
- 主表单含 submit 与保存/保存并关闭；API Key 区不得入主 form span

## 易踩坑（新增/更新）

1. 侧栏 SVG `<path/>` 自闭合——htmlcheck 已放行，勿回退
2. 侧栏导航 `<a>` 标签：`href` 与 `title` 属性间需有空格（f-string 拼接时）
3. `_icon()` 返回 SVG 字符串，必须在 **f-string 内**使用（`f'...{_icon("key")}...'`）；**禁止**在普通字符串字面量中写 `{_icon("key")}`（会被当作纯文本）
4. `build_schedule_flags_badge_html` 中的 `{_icon(...)}` 需加 `f` 前缀否则输出字面量
5. vendor hash 含 JS：改 `_COMMON_JS`/`_FOOTER_GLUE` 之外的公共 JS 需重刷缓存认知（hash 自动变）
6. 报表页胶水在 `render_page_footer(extra_js=...)`；勿再拼 `_FOOTER` 字符串
7. `build_collapse_section_html(mem_key=...)` 参数仍在但**不再输出三态**（测试断言用 `data-mem-key="` 前缀区分 CSS 选择器）
8. 术语/文案改动需同步 `ui-redesign-visual-spec.md` §5 与相关测试（test_cache_ui/test_render*/test_preset）
9. 调度表单页与列表页分离：编辑链接 `/config/scheduler/{id}/edit`，`?edit=N` 为兼容渲染
10. 详见 AGENTS「两败必停」；UI 变更先看确认稿
11. `_PAGE_HEADER_TEMPLATE.substitute` 有**两处**调用（`render_page_header` 与 `render_audit_page`）——新增模板占位符必须两处同步传参，漏一处即 `KeyError`（`sidebar_bootstrap` 曾在审计页踩中）
12. 手柄/折叠类 JS 勿嵌套监听：按钮若在 `.brand` 等父监听器内部，冒泡会二次 toggle（确认稿 v1 实测 bug，靠守卫/单监听器根治）
13. 侧栏收缩记忆三态语义：`sqlreport_sidebar_collapsed` 无值=默认（桌面展开/小屏图标条），改语义须同步 `_SIDEBAR_BOOTSTRAP_JS`、`sbStoreWrite` 与 `_COMMON_CSS` 三处
14. **R3 视觉校验教训**：改 `_COMMON_CSS`/`_COMMON_JS` 会变 vendor hash——截图脚本内联公共资产时**禁止硬编码 `self@{hash}`**，须用 `self@[0-9a-f]+` 正则替换，否则 CSS 静默外链、file:// 下整页无样式（曾致几何断言全部失真）；数值断言以 CDP 同会话回读 DOM 几何为准（tables `scrollWidth-clientWidth`、chip `height≤30`、rail `gap>0`/箭头与账号区不相交）
15. R3 报表页 10 列宽度预算：右栏可用宽 = 视口 − 侧栏240 − 容器padding48 − 左树260 − 间距16；**1280/1366/1440/1920 全部零横向溢出**（操作列不可被挤出视口；2026-09-29 用户 ~1280 视口截图发现溢出后收紧达成，原「1280 允许滚动」口径作废）；改列宽后按此矩阵复测
16. **验收脚本自身的坑**（2026-09-30 复盘）：陈旧 cookie 拿到登录页、`Page.navigate` 清空 `window.*`、
    选择器想当然（`#f_customer` 实际是 `[name="f_customer"]`）、`children` 下标被占位元素污染、
    拖到自己身上是 no-op、自定义列反选默认项 → 每一项都会让你「测了个假绿」。清单见 `08-testing-conventions.md`。

## 交互改动验收（硬性 #17）与失败模式库

**来源**：2026-09-30 用户实测「隐藏列→还原→再排序 → 拖拽报废」跨 3 轮反馈才定位。
根因不在某一行代码，而在验收方式：**只做「整页加载后点一次」，看不见「换页态」「组合操作」「第二次交互」**。
完整复盘：`docs/compose/reports/ui-v2-retrospective.md`。

**凡改动碰了 JS 交互，提交前逐条过（缺一即未完成）**：

1. **两种载入态都验**：整页加载 + 操作一次后的**原位换页态**（分页/筛选/字段/排序/导出/移动都会触发换页）。
2. **验到第二、三次操作**：换页后拖拽、连续两次应用、先隐藏再还原再排序。
3. **组合顺序要验**：字段顺序 × 筛选规则 × 排序 × 导出交叉（脚本 `scripts/ui-v2/e2e/e2e-combo.mjs`、`swap-reinit.mjs`）。
4. **注册路径唯一**：新增 init 必须进 `initPage()`/`initReportPage()`；页面级脚本用 `onReady(fn)`；换页实现只有 `_swapMain` 一份。
5. **删样式必问语义归属**：默认隐藏（`display`）、列宽、底色/文字成对——删掉后旧语义由谁承担？改公共 CSS 时**必须同步核对 JS 实际切换的类名**（元素级契约），漏一侧就是「点了没反应」。
6. 改了 `render.py`/`report.py`/`config.py` 后**重启服务再验**：页面内联 JS 由内存直出；外链公共 CSS/JS 走 `ensure_common_assets` 的**内容哈希目录 + 进程级 URL 缓存**（`_COMMON_ASSET_URLS`），不重启进程就仍指向旧 hash 目录、改了也看不到。

**失败模式库**（每类都是本轮真实事故；能机械检测的已做成门禁，勿靠“记住”）：

| 症状 | 根因 | 拦截 |
|------|------|------|
| 代码块文字隐形 | 底/字分属两条规则 | `TestContrastGate`（成对声明 + 对比度实算） |
| 整页被遮罩盖住 | 同一规则内 `display` 被后面的值覆盖 | `TestNoDuplicateDeclarations` |
| 面板/对话框/展开区点不开 | JS 切 `.on` 而 CSS 只认 `.open/.show`（或反过来：只认确认稿类名） | `TestRevealClassContracts`（元素级：JS 切的类必须有对应 display 规则）+ `TestJsToggledClassesHaveStyles` |
| 对话框三段排成一行 | 结构假设错（并列兄弟当成单个盒子） | `TestJsToggledClassesHaveStyles::test_modal_supports_sibling_sections` |
| 按钮能点、拖拽/下拉失效 | 换页只 `innerHTML` 替换，不执行内联脚本、不重跑初始化 | `TestNoRefreshSwapReinit` + `TestPageInitRegistration` |
| 新加的初始化换页后不跑 | 新 `init*` 没进 `initPage()` | `TestPageInitRegistration` |
| 「按钮点了没反应」且控制台无 Log 错误 | JS 块注释里出现 `*/` | `TestInlineJsSyntax`（node --check） |
| 组合操作后参数丢了 | 各功能各自重建 URL | `buildReportUrl()` 单一构造 + 契约用例 |
| 同名参数重复提交 | 镜像控件带 `name` | `TestFormControlNameUniqueness` |
| 排序项序号从 2 开始/移动错位 | 占位块未受管，下标整体错位 | `TestNoRefreshSwapReinit::test_sort_placeholder_managed` |
| 「修了但我这儿还是坏的」 | 动态 HTML 未禁缓存 | `TestHtmlFreshness` |
| 展开/收起点了没反应（按钮文案/箭头却在动） | CSS 按确认稿只收 `.api-row.open`，生产 JS 切的是 `.api-more.on`；同一提交还删了 `.tree .kids{display:none}`（分类树折叠同款失效） | `TestRevealClassContracts` + e2e `scripts/ui-v2/e2e/api-row-expand-check.mjs` |

**门禁自身也要被验证**：`venv/bin/python tests/bug_hunt/gate_redproof.py` 会把上述 5 条新门禁
对应的历史缺陷打回去（RED 必失败），再还原（GREEN 必通过）；5/5 通过才算门禁有效。

### 改 UI 前阅读顺序

1. 本卷 + AGENTS 硬性 #11
2. `docs/compose/spec/2026-09-30-ui-v2-design.md`（**现行**令牌/组件/页面口径）；`ui-redesign-visual-spec.md` 已标注「已被取代」（**例外：§5 术语表继续有效**），其余仅供追溯
3. `render.py`：`_BASE/_COMMON_CSS` → `_COMMON_JS` → 侧栏/页壳 → 相关 `build_*`
4. `tests/htmlcheck.py` + `test_render*` / `test_html*`

---
最后核对：**R2 核对 2026-09-25**（以最终代码全量对账九项 R2 事实：全局容器阶梯/.split、分类树左栏、双栏表单三页、API 列表 api-row、详情五页签、概览 grid-2、调度 7 列单表、池/用户列、审计 page-head）；R2-D 组2：/config/api-endpoints 对齐原型 page-api（api-card-table 伪卡片表废弃，统一为 .api-row/.api-main/.api-more；path 徽标改名 .path-chip 避开 `th {` 字面量门禁；展开 JS `apiToggleMore`）+ 报表详情 page-detail（qf-row 快筛行 / 结果集 segment / 分页 always 恒显 / 规则 grid-2 双卡 / 接口页签委托列表函数 / 调试 grid-3 磁贴 / 备注普通卡片；共享 CSS 唯一定义 `.grid-3`/`tr.qf-row td`/`.code-block`/`.api-row`）；**R2-D 组1 核对 2026-09-25**：三张表单页（报表编辑 / 端点表单 / 调度新建编辑）对齐原型 `page-report-edit`·`page-api-edit`·`page-scheduler-new` —— page-head+crumb 置于主 form 起始处、主 form 内 `.grid-2` 双栏卡片、`formbar` 在 form 底；报表④卡新增关联调度摘要与「+ 新建调度」入口；调度 crumb 尾段「定时任务 › 新建/编辑」；`grid-2`/`card-head` 为 `_COMMON_CSS` 唯一定义（此前 class 已用未定义）。偏离原型：API 端点列表/API Key 区因 htmlcheck 门禁仍在主 form 外（位于 grid-2+formbar 之后）。**交互核对 2026-09-27**：`navigateTo`/`_swapMain`/`initPage`/移动箭头 submit 拦截已随「无刷新导航」需求落地，见 §交互模式 1–2（sort/分页/筛选/切换等已接入，服务端仍整页渲染）。**侧栏收缩+用户名核对 2026-09-29**：全高手柄三态收缩（确认稿 `docs/sidebar-collapse-user-confirm.html` v2 → `_COMMON_CSS`/`_COMMON_JS`/`_SIDEBAR_BOOTSTRAP_JS`/`_build_sidebar_html`）+ 当前登录用户名请求上下文注入（`render.set_request_user` ← server `_handle` 复位/`_authenticate` 注入，43 处 `render_page_header` 调用零改动）；测试 `tests/test_render.TestSidebarCollapseAndUser`（8 用例）。**R3 核对 2026-09-29**（确认稿 `docs/compose/spec/ui-redesign-r3.html`，用户已确认含两条反馈修订）：① 侧栏账号区修复——账号区吸底改 `.account{margin-top:auto}`（原账号区浮中部被 `top:50%` 箭头压；**首版误改 spacer=flex:1 致组间 283px 空白，已回退**——生产每组后各一个 spacer 共 4 个、确认稿仅 1 个，结构不同勿照抄）、rail 账号区纵向两行（`html.sb-rail` 与 ≤1024px 媒体查询**两处**规则都改）、箭头 y 钳制；② 报表配置页双视图——`render_reports_page` 页头 `#rpt-view-seg` + `setReportsView`/`pickedReportIds`（render.py 批量 script 内）、`_REPORTS_EXTRA_CSS`（config.py，`#sec-reports` 作用域）、`.pool-chip` 替代圆角 `badge-pool`（长池名曾包成圆饼）、列表列重排（cfg 三列归组 + 图标化操作列 + SQL 窄列 title）、`build_category_section_html` 输出 `.view-list`+`.view-card` 双形态（`_render_report_rows` 返回 `(rows, cards)` 元组）；截图 `docs/compose/spec/shots/r3/`（v4-*.png 带标记可自证），几何断言矩阵 1920/1440/1366 零溢出、rail `railGap=6/arrowOverlapsAccount=false`。 **嵌套层级修订（同日）**：子分类整组内缩成**完整圆角子卡片**（`border 1px`+`border-left:3px`层级线+`border-radius:10px`+`overflow:hidden`，标题 `radius 0`/浅灰底、表格 `border 0`）——弃用旧 `.section[style*=border-left] .section-title{border-left:0}` 半截圆角 hack。**UI v2 修订（2026-09-30，以本条为准）**：内联样式已清理，层级改由 `.cat-children` class 承担（`tests/test_render.py` 现断言 class / `.kids`，不再断言内联 `margin-left:24px`），容器样式**不再**需要 `!important`。
