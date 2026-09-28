# UI 体系与交互（ui-redesign 重构后 · render 单一来源）

> 与根 `AGENTS.md` 硬性 #11、「UI / 视觉 / 交互任务流程」对齐。
> 最后同步：ui-redesign 特性（`docs/compose/spec/ui-redesign.md`，T7.1–T7.11 已实施）。

## 原则

- **禁止**新写一套 class/布局/第二份 CSS；页面 = `render_page_header` + `build_*` + footer
- 局部样式：`extra_css=`，不要改 `_COMMON_CSS`（设计令牌在 `_BASE_CSS` `:root`）
- 全部用户可感知文字简体中文；**术语表**见 `docs/compose/spec/ui-redesign-visual-spec.md` §5（prefer_cache/Redis 快照等实现词禁止直出 UI）
- 危险操作：统一确认（`confirm` 文案模板：动词+对象+影响范围）；无第二套框架
- 品牌：侧栏/登录/浏览器标题统一 **SqlReport**（branding 前缀仍只改 `<title>`）

## UI 确认稿 → 实施（硬性 #11，已完成一轮）

1. 先可交互 HTML 确认：`docs/compose/spec/ui-redesign-prototype.html`（用户已确认）
2. 严格按确认稿实施；确认稿素材与截图在 `docs/compose/spec/shots/`
3. 绝对禁止：交付与确认不符、混乱 DOM/CSS 直塞、确认稿原样粘进 `render.py`

## 骨架与资产

| 符号 | 作用 |
|------|------|
| `_BASE_CSS` | 设计令牌（`:root` 色板/圆角/阴影/焦点圈）+ reset + fadeUp |
| `_COMMON_CSS` | 侧栏页壳 + 通用组件 + 令牌化按钮/表格/卡片/分页/flash + 新组件（page-head/tabs/toolbar/side-panel/modal/formbar/badge/filterbar/batch 相关/api-row 行卡片/grid-2 双栏+card-head/`rule-row`·`rule-group` 排除规则行组等）+ 合成历史切片 |
| `_icon(name)` | 图标辅助函数（替代 emoji 字符），返回设计规范内联 SVG HTML。集合：alert/search/file/settings/list/folder/chart/key/calendar/refresh/check/x/info/edit/plus/copy/trash/download/database/users/eye/play/link/chevron-* |
| `_COMMON_JS` | 折叠/复制/flash/过滤/最近查看/列记忆/loading/Tab 缩进…（**三态 setMemToggle/initMemToggles 已删除**） |
| `_SQL_HIGHLIGHT_JS` / `_SQL_FORMATTER_JS` | SQL 高亮/格式化（编辑表单与详情调试按需） |
| `ensure_common_assets` | 写 `static/vendor/self@{sha8}/`，**hash = sha256(CSS+"\n;;;\n"+JS) 前 8 位**（改 JS 也会换 URL） |
| `render_page_header(title, active_nav, extra_css, nav_badges, current_user)` | `<head>` + 侧栏 + container 开头 |
| `render_page_footer(extra_js="")` | 闭合 container/main/app + 外链 common.js + 可选页面级 `defer` 胶水 JS |
| `_NAV_GROUPS` / `render_sidebar` / `render_navbar`(兼容别名) | **侧栏分组导航单一来源**（分析/管理/服务/治理 + 账户区退出） |

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
| `/config/reports` | `render_reports_page`：页头搜索 + **左分类树右报表表**（`split_parts=True` 拆分）；左栏 `build_category_manage_section_html`（见下「报表配置左栏分类树」） | 勾选浮出批量条、`#sec-categories` 兼容 |
| `/config/reports/{id}/edit` | 分区表单（①基础 ②SQL ③缓存与护栏 ④调度与保活）：page-head+crumb 置于主 form 起始处、主 form 内 `.grid-2` 双栏 + **sticky `formbar` 在 form 底**（保存/保存并关闭在主 form 内）；**④ 卡内含关联定时任务只读摘要 `render.build_report_schedule_summary_html`（复用 `db.get_all_schedules` 的 report_ids 过滤）+「+ 新建调度」→ `/config/scheduler/new?report_id=N`**；查看/预览按钮在 page-head（`previewReport(this.form)` 协议不变）；表单下方（form 外）追加接口列表 api-row | 与 htmlcheck 门禁兼容 |
| `/config/api-endpoints` | `render_api_endpoints_page`：page-head（h1+统计 sub+「+ 新建接口」→首张报表 `api_endpoints/new`，**无报表回 `/config/reports/add`**）；列表 = `build_api_endpoints_list_html` 输出 **真卡片 `div.api-row`**（`.api-main` 主行：名称/路径徽标/关联报表/状态/格式/Key/操作；`.api-more` 展开区：输出模式/全量/静态 meta+**说明全文（不截断，`title` 仅兜底）**+三 URL），点击主行或「展开 ▾」钮切换（`_COMMON_JS` `apiToggleMore`/`apiMainClick`；旧 api-card-table 已删） | toggle/编辑/删除/复制协议不变 |
| 端点表单 | page-head+crumb + 分区（①基本信息 ②调用地址 ③请求与输出 ④JSON 模板），主 form 内 `.grid-2`，`form-actions formbar span-full` 在 form 底 | Key 区仍在主 form 外 |
| `/config/scheduler` | **列表主导** `render_scheduler_page`（页头+新建按钮+全局停用横幅置顶；单表 7 列对齐原型：任务名/关联报表/计划/下次执行/上次结果/状态/操作，已收敛「上次执行/失败计数」两列；**无「最近执行记录」第二张表**，执行历史到审计日志查询；表下 help 提示徽标语义） | 行操作/回跳；POST 协议不变 |
| `/config/scheduler/new`、`/config/scheduler/{id}/edit` | `render_scheduler_form_page`（独立表单页；page-head+crumb；主 form 内 `.grid-2`（左「计划」｜右「关联报表」）→ 独立「排除规则」卡 → `formbar` 在 form 底；排除规则 = `rule-row`/`rule-group` 可视化树编辑器 `exclToggleSource()` 切「源码」JSON 模式，产出 JSON 写隐藏域 `exclusions`；**新建页支持 `?report_id=N` 预勾绑定**（报表编辑页「新建调度」入口带参，仅新建生效、编辑态以库内绑定为准，非法参数忽略）；遗留 `?edit=N` 兼容直渲染表单） | 排除规则树/绑定表 |
| `/audit` | `render_audit_page`：page-head actions=「导出 CSV」+「清理过期」（原筛选条内清理钮移位，POST `action=clean` 参数不变）；filterbar 与表格**裸排无 card 包裹** | 类型/日期快捷/关键字/导出/清理（筛选交互不动） |
| `/health`、`/api/…` | 无页壳 | — |

### 报表详情数据页顺序

页头 → 横幅(flash/预览/截断/写护栏/缓存降级) → 备注摘要条 → 页签 → 数据面板：工具行(行数/页大小/**结果集 segment**/列设置/排序/高级筛选/重建缓存/缓存徽标；`build_controls_bar_html(result_html=...)` 在页大小后插入) → 筛选动作行 → 排序条 → 隐藏 ff 表格 form → 表格(第 1 行列头排序 + 第 2 行 `tr.qf-row` 独立快筛行，`f_/op_` 与 `form="ff"` 协议不变；报表页 CSS 快筛输入选择器由 `th .filter-input` 下沉为 `.qf-row .filter-input`) → 分页(`build_pagination_html(always=True)` 恒显：单页/空结果也渲染)。规则页签=`grid-2` 左右双卡(左=嵌套条件构建器，右=当前规则 JSON 复制/应用)；接口页签=card+card-head(「本报表的 API 接口」+「新增 API 接口」(report_id>0 指向该报表新建表单，空态同样保留) +「管理全部接口」) 内嵌 `build_api_urls_section_html`，其**委托 `build_api_endpoints_list_html`** 输出 api-row 卡片(与列表页同一实现)；调试页签=card「执行信息（Debug）」+ `grid-3` 统计磁贴 + `sql-debug code-block` SQL 代码块；备注页签=普通卡片(card+card-head+md-body，折叠与三态记忆已废除)。结果集切换 JS：`switchResult(btn)` 按钮版(数据属性挂 `.result-selector` 容器，`btn.dataset.index`，sessionStorage 记忆回跳协议不变)。

### 报表配置左栏分类树（R2-A）

`build_category_manage_section_html`（render.py）：`.tree/.cat` flex 行 = SVG 文件夹图标 + 名称 + `.cnt` 报表数角标 + `.ops` ghost 操作（✎编辑 ↑↓移动 ✕删除，`btn-ghost btn-icon`）；子分类包 `.kids` 容器逐级缩进，父行点击 `toggleCatNode(ev,row)` 折叠/展开（区块标题 `toggleCatTree` 整体折叠，localStorage 记忆）。**不再使用 ├─ 文本引导线**（原 `config.py` 的 `.tree-guide/.cat-tree-item` 死 CSS 已于 R2 核对时删除，勿再引入）。

## 组件库（按需全量见 render.py）

**通用**：`build_flash_html` / `build_empty_row_html` / `build_pagination_html` / `build_collapse_section_html`(**三态 mem_key 已废除**，仅保留参数兼容) / `build_config_filter_box_html` / `build_delete_form_html` / `build_move_buttons_html` / `build_export_modal_html`(T7.4 新增)

**报表**：`build_controls_bar_html`(工具行) / `build_table_*` / `build_sort_bar_html` / `build_filter_*` / `build_field_settings_panel_html`+`build_sort_settings_panel_html`(side-panel 抽屉) / `build_nested_filter_builder_html` / `build_current_rules_section_html` / `build_debug_section_html` / `build_memo_section_html` / `build_result_selector_html` / `build_cache_badge_html`(术语化) / `build_redis_banners_html` / `build_report_switcher_html` / `build_api_urls_section_html`

**配置/API/调度**：`build_pool_*` / `build_user_*` / `build_category_*`（`split_parts=True` 支持左树右表）/ `build_api_endpoints_list_html` / `build_api_endpoint_form_html` / `build_api_key_manage_html` / `build_scheduler_page_html` / `build_scheduler_task_form_html` / `build_schedule_flags_badge_html` / `build_report_schedule_summary_html`（报表编辑④卡关联任务摘要+新建调度入口） / `build_state_span` / `render_audit_page` / `render_pools_page` / `render_users_page` / `render_overview` / `render_api_endpoints_page`

## 交互模式（无框架）

1. 服务端整页渲染，无 SPA 框架；页内页签/抽屉/对话框用 `gotoTab` / `openPanel`/`closePanel`/`closeAllPanels`（`_FOOTER_GLUE`，ESC/遮罩关闭）。**客户端无刷新导航已引入**：`_COMMON_JS` 提供 `navigateTo(url)`（fetch + `history.pushState` 原位替换 `<main>` 内容，失败回退整页跳转）与 `_swapMain`；`popstate` 拦截浏览器前进/后退同样原位换页。已接入：分页跳页 `goPage`、筛选搜索、每页条数/报表切换 select、`applySortSettings`/`applyFieldSettings`/`switchResult`、紧凑报表切换器；**上移/下移箭头**（`/config/{section}/{id}/move-up|move-down` 表单）由 submit 拦截器 fetch POST 跟随 302 后原位换页，保持滚动位置不跳顶（无 JS 时回退原生提交）
2. `_COMMON_JS` 初始化统一走 `initPage()`（DOMContentLoaded 与每次 `_swapMain` 换页后重跑，须幂等）：`initApiUrls` `initCatTree` `initFlashMessages` `initAnchorRowHighlight` `initQueryLoadingOverlay`(全站提交遮罩方向，表单/按钮带 `data-ov-bound` 防重复绑定) `initConfigFilter` `initRecentReports` `initSqlEditorTabIndent`（**initMemToggles 已删**）
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

### 改 UI 前阅读顺序

1. 本卷 + AGENTS 硬性 #11
2. `docs/compose/spec/ui-redesign-visual-spec.md`（令牌/组件/术语）与 `ui-redesign-ia.md`（页面布局）
3. `render.py`：`_BASE/_COMMON_CSS` → `_COMMON_JS` → 侧栏/页壳 → 相关 `build_*`
4. `tests/htmlcheck.py` + `test_render*` / `test_html*`

---
最后核对：**R2 核对 2026-09-25**（以最终代码全量对账九项 R2 事实：全局容器阶梯/.split、分类树左栏、双栏表单三页、API 列表 api-row、详情五页签、概览 grid-2、调度 7 列单表、池/用户列、审计 page-head）；R2-D 组2：/config/api-endpoints 对齐原型 page-api（api-card-table 伪卡片表废弃，统一为 .api-row/.api-main/.api-more；path 徽标改名 .path-chip 避开 `th {` 字面量门禁；展开 JS `apiToggleMore`）+ 报表详情 page-detail（qf-row 快筛行 / 结果集 segment / 分页 always 恒显 / 规则 grid-2 双卡 / 接口页签委托列表函数 / 调试 grid-3 磁贴 / 备注普通卡片；共享 CSS 唯一定义 `.grid-3`/`tr.qf-row td`/`.code-block`/`.api-row`）；**R2-D 组1 核对 2026-09-25**：三张表单页（报表编辑 / 端点表单 / 调度新建编辑）对齐原型 `page-report-edit`·`page-api-edit`·`page-scheduler-new` —— page-head+crumb 置于主 form 起始处、主 form 内 `.grid-2` 双栏卡片、`formbar` 在 form 底；报表④卡新增关联调度摘要与「+ 新建调度」入口；调度 crumb 尾段「定时任务 › 新建/编辑」；`grid-2`/`card-head` 为 `_COMMON_CSS` 唯一定义（此前 class 已用未定义）。偏离原型：API 端点列表/API Key 区因 htmlcheck 门禁仍在主 form 外（位于 grid-2+formbar 之后）。**交互核对 2026-09-27**：`navigateTo`/`_swapMain`/`initPage`/移动箭头 submit 拦截已随「无刷新导航」需求落地，见 §交互模式 1–2（sort/分页/筛选/切换等已接入，服务端仍整页渲染）。
