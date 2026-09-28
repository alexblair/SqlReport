# 现状 UI / 交互问题分析（ui-redesign · T2）

> 证据来源：① 知识库（INDEX / 01–07 分卷）；② 源码（`render.py` / `report.py` / `config.py` / `server.py` 等）；③ 真实运行实例截图 17 张（`docs/compose/spec/shots/`，演示数据：7 报表 / 6 API / 10 调度，本地服务 127.0.0.1:8080）。
> 截图核验说明：截图文件经 md5 + 像素签名核验（登录页紫色占比 41.6%、调度页黄横幅+靛蓝保存按钮特征），文件名与内容一致；会话内 Read 工具展示层出现过图片串扰，分析以文件核验结果为准。
> 与《功能/交互覆盖清单》（`ui-redesign-inventory.md`）交叉引用，条目编号形如 R/2.x/C/E/F。
> 最后更新：2026-09-25（T2 成稿）

## 1. 量化证据（代码层）

| 指标 | 数值 | 含义 |
|------|------|------|
| `render.py` 内联 `style="…"` | **319 处** | 样式散落在 HTML 字符串，无法集中调优（如 60+ 字符的 flex/grid 长串直接写在标签上） |
| 独立十六进制色值 | **51 种**（仅 render.py） | 无设计令牌；另有 login/`_CONFIG_EXTRA_CSS`/report `_CSS` 等页级色板 |
| 内联事件处理器 | onclick 57 + onchange 27 + onsubmit 7 = **91 处** | 交互逻辑以字符串内联，分散且难统一改 |
| 按钮 class 组合 | **26+ 种**（btn×outline×primary×sm×danger…、btn-mini 6 变体、btn-refresh、page-btn、filter-btns） | 同一语义操作在不同页面长得不一样 |
| `aria-*` / `role=` | **0** | 全站无可访问性语义 |
| `:focus` / `focus-visible` 规则 | 3 | 焦点态几乎缺失，键盘不可用 |
| 面板显隐 | 7 处 `style.display='block'|'none'` 硬切 | 无遮罩、无 ESC、无焦点管理 |
| 页面级 CSS 补丁 | `report.py _CSS`≈102 行、`config.py _CONFIG_EXTRA_CSS`≈132 行、`_MD_CSS`、codehilite… | 公共样式之上层层追加，边界靠约定不靠机制 |
| confirm 使用 | 13 处（其中手写 `onsubmit="return confirm"` 4 处 + `build_delete_form_html` 14 个调用点并存） | 危险操作确认双轨实现 |
| JS 加载 | `_COMMON_JS` 外链（config/audit）+ 报表页 `_FOOTER` 再内联双轨；vendor hash 只算 CSS | 同一份 JS 两条加载路径，改 JS 缓存不失效（06 卷易踩坑） |

## 2. 问题清单（按严重度分组，含证据与交叉引用）

### P0 · 违背「统一组件体系」的个性化实现（本次重构目标之一）

| # | 问题 | 证据 | 覆盖条目 |
|---|------|------|----------|
| P0-1 | **两套视觉语言并存**：登录页为紫渐变全屏+16px 圆角+渐变按钮的独立设计（`_LOGIN_PAGE` 自带 70 行 style）；管理端为深蓝灰导航+8px 扁平按钮。品牌色、圆角、按钮形态均不一致 | `server.py:59-127`；shots/01-login.png vs 其余 | R2、C15 |
| P0-2 | **品牌标识三处打架**：导航硬编码 `MyReport`（My 非粗体+Report 靛蓝），页面标题体系是「Web 报表工具 - …」，login 页脚「Web 报表工具 v1.0」；branding 前缀只改 `<title>` 不改导航品牌 | `render.py:_build_navbar_html` brand 行；shots 全部页顶栏 | R5、C13 |
| P0-3 | **无设计令牌**：51 种 hex 散写；主色 `#4f46e5`、导航渐变 `#1e293b→#334155`、登录渐变 `#667eea→#764ba2`、成功/危险/信息色各自为政；字号/间距/圆角无阶梯 | `render.py:45-210` 色值统计 | C15 |
| P0-4 | **按钮体系碎片化**：26+ 组合；同级操作语义不一致——列表页「删除」一律实心红大按钮抢视觉、「编辑/复制」描边小按钮；控制栏「导出」实心绿突兀；btn-mini 另起一套 6 变体 | 色值+class 统计；shots/05、09、14 | C5、组件级 4.2 |
| P0-5 | **样式与结构耦合**：319 处内联 style（含整段布局 flex/grid），任何视觉调整都要改字符串拼接处 | grep 统计 | C14、4.x |
| P0-6 | **图标系统混乱**：emoji（🔌📊📁⏰♻🔇🔍）与文字符号（↑↓⚙⇅▶）混用，跨平台渲染不可控，语义不统一 | `render.py` emoji 扫描；shots/04、05、07 | 4.1/4.2 |
| P0-7 | **面板/弹层无统一体验**：字段设置、排序设置为 `display:block` 硬切的浮层（无遮罩/ESC/焦点），导出高级选项是 `<details>` 伪 popover，嵌套筛选是页内大块，帮助是原生 `confirm`/弹窗——四种浮层形态并存 | `render.py:1943-2092`、`1890-1980`、`1348`；shots/14、16 | C3、C8、2.3 |

### P1 · 信息架构与页面组织问题

| # | 问题 | 证据 | 覆盖条目 |
|---|------|------|----------|
| P1-1 | **导航扁平且双轨**：顶层 6 项「报表页/配置管理/定时任务/API 接口/审计日志/退出」；定时任务与 API 实为 `/config/*` 子域，配置门户卡片又重复提供入口——同一目的地两条路，层级撒谎 | `_NAV_ITEMS`；`render_overview` 卡片；shots/04 顶栏 | R4–R16、C13 |
| P1-2 | **「退出」混在导航**：会话操作与页面导航同级，无账户语境 | `_NAV_ITEMS` | R5 |
| P1-3 | **配置门户是长混装页**：连接池表+用户表+三张几乎只有一行字的统计卡（报表/分类/API）+站点标识+DEBUG 导入；统计卡信息密度极低（大片留白），池/用户 CRUD 却直接嵌在门户里 | `config.render_overview:973-1054`；shots/04 | R12、2.6 |
| P1-4 | **报表选择页停留在 2010 年代**：全宽下拉 + 纯链接树 + emoji 文件夹；无搜索、无最近查看卡片的实际展示（挂载点存在但常态为空）、大量空白；与「2026 数据工具」差距最大的单页 | `report.render_report_selector`；shots/02 | R13、2.2 |
| P1-5 | **报表详情首屏被非数据元素吃光**：切换器整卡（一行下拉占满宽）→标题→4 条虚线折叠（备注/API地址/Debug/当前规则即使折叠也各占一行）→横幅→控制栏→筛选行→表头两行→才见数据；3 行数据的报表首屏几乎无数据 | shots/03；`_build_report_html` 顺序（06 卷） | 2.3 |
| P1-6 | **报表编辑单列长表单无分区**：基础字段/SQL/备注/结果名称/护栏/调度折叠/保活/端点全部纵向排开，保存按钮在首屏之外；同类「表单+高级区」页面（调度、端点）也无统一分区模式 | `config.render_report_form_page:1165`；shots/09 | 2.10 |
| P1-7 | **调度页新建表单压在列表之上**：进页先见空表单+报表勾选表，任务列表（真正的管理对象）沉到下方；全局停用横幅夹在表单与列表之间 | `build_scheduler_page_html`；shots/07（像素核验） | R16、2.12 |
| P1-8 | **API 列表单行过载**：每行同时展示完整 URL/全量 URL/静态 URL+3 个复制按钮+格式/输出模式/全量/静态/状态/Key/操作 12 列，行高巨大、列宽挤压（名称列竖排折行） | `build_api_endpoints_list_html:2865`；shots/06 | R6、2.11 |
| P1-9 | **报表列表信息列过载且层级重复**：分类树在顶部独立区块，下方又按分类重复分组表头；SQL 查询列大段裸 SQL；操作列 5 控件×每行 | shots/05；`render_reports_page` | R7、2.9 |

### P2 · 交互逻辑不清（可用性问题）

| # | 问题 | 证据 | 覆盖条目 |
|---|------|------|----------|
| P2-1 | **筛选存在三套心智模型**：①列头行内「操作符+输入」；②嵌套筛选构建器（and/or 分组）；③「当前规则」JSON 复制/应用。同一意图三种表达，帮助入口又另设 `?` 与 filter_help 弹窗 | `build_filter_*`、`build_nested_filter_builder_html`、`build_current_rules_section_html`；shots/03、17 | 2.3、C9 |
| P2-2 | **备注三态开关（自动/展开/折叠）语义晦涩**：与折叠箭头职责重叠，「自动」对用户是实现细节；按报表记忆的 localStorage 行为不可见 | `build_memo_section_html`、`initMemToggles`；shots/03 顶部 | 2.3、C6 |
| P2-3 | **导出选项藏匿且耦合**：字符集/智能去引号/压缩包/「应用自定义字段」全在「更多选项▾」popover；其中「应用自定义字段」与字段设置面板状态耦合，popover 内无说明如何生效（实际随导出 form 提交） | `build_controls_bar_html:1890-1980`；shots/16 | 2.3、C8 |
| P2-4 | **控制栏功能混装无主次**：每页行数、导出格式、更多选项、导出（绿）、字段设置、排序设置、重建缓存、缓存徽标、行数统计一字排开；「重建缓存」（破坏性刷新）与日常操作同权重 | shots/03、14 | 2.3 |
| P2-5 | **缓存实现术语直出用户**：徽标「直连 MySQL (prefer_cache | TTL=1h)」「进程缓存 (55s 前刷新…)」、横幅「Redis 不可用，已切换至直连 MySQL 模式」——`prefer_cache` 等内部参数泄漏进 UI | `build_cache_badge_html`、`build_redis_banners_html`；shots/03 | 2.3 |
| P2-6 | **浮层遮挡与状态可见性差**：字段设置面板打开后压在表头之上（无遮罩），关闭靠右上「收起」；打开/关闭无过渡，与页面滚动关系不清 | shots/14；7 处 display 硬切 | C8 |
| P2-7 | **反馈覆盖不均**：loading 遮罩仅 `/report` 与 `.btn-refresh`（明确排除 `/export`）；其余表单提交靠整页刷新，无 pending 态；flash 6s 自动消失，重要错误易错过 | `initQueryLoadingOverlay`；06 卷 | C2、C7 |
| P2-8 | **危险操作确认双轨且文案各异**：13 处 confirm 分散手写/组件生成；删除按钮满屏实心红，「批量删除/清理审计/禁用 Key」等强度不同的操作视觉同级 | grep confirm；shots/04、05、06 | C3 |
| P2-9 | **状态仅靠颜色传达**：缓存「是/否」绿/黑、Key 数「—」灰、启用绿字——无图标/文字语义冗余，色弱不可辨 | shots/05、06 | — |
| P2-10 | **分页与页大小即时跳转**：`onchange=this.form.submit()` 输入即生效；跳页输入误触无防护（轻） | `render.py:1263/1883` | 2.3 |

### P3 · 可访问性与工程债（实施期必须一并解决）

| # | 问题 | 证据 |
|---|------|------|
| P3-1 | 全站 0 个 `aria-*`/`role`，浮层/折叠/面板均为 div+onclick，读屏与键盘完全不可用 | grep 统计 |
| P3-2 | 焦点样式仅 3 处；Tab 序在面板打开时无管理 | grep 统计 |
| P3-3 | 对比度：次级灰 `#94a3b8` on `#f1f5f9`、占位「不筛选」灰字偏弱（目测截图） | shots/03、C15 |
| P3-4 | `_COMMON_JS` 双轨 + hash 只算 CSS：改 JS 不换 URL，immutable 外链缓存不失效 | 06 卷易踩坑 |
| P3-5 | 嵌套 form 历史雷区靠 htmlcheck 事后门禁；Key 区必须在主 form 外等结构性约定散在测试里 | `tests/htmlcheck.py`、06 卷 |

## 3. 总评（给 T3 的设计判断）

现状是「**局部合格、全局失序**」：单个页面（如报表详情）功能完备、信息量大，但

1. **没有系统**——色板、按钮、浮层、图标、术语各自生长，个性化实现正是违背项目「单一来源、禁止重复造轮子」要求的产物（P0 组）；
2. **没有层级**——IA 双轨、页面内垂直堆叠同权重区块，用户第一眼找不到主任务（P1 组）；
3. **没有模型**——筛选三套、导出藏匿、术语泄漏，交互靠发现而非设计（P2 组）。

重构必须以「设计令牌 + 统一组件规范 + 单一导航模型 + 筛选/导出/面板交互收敛」四件事为纲，且在不丢功能前提下允许页面数量与布局推倒重排（与 S1/S2 一致）。

## 4. 截图索引（证据附件）

| 文件 | 内容 | 核验 |
|------|------|------|
| shots/01-login.png | 登录页 | 紫色像素 41.6% ✓ |
| shots/02-report-selector.png | 报表选择页 | 内容 ✓ |
| shots/03-report-detail.png | 报表详情（含 Redis 横幅/控制栏/筛选行） | 内容 ✓ |
| shots/04-config.png | 配置门户（池/用户/卡片/品牌） | 内容 ✓ |
| shots/05-reports-list.png | 报表列表（分类树+批量+分组表） | 内容 ✓ |
| shots/06-api-endpoints.png | API 接口列表 | md5 独立 ✓ |
| shots/07-scheduler.png | 定时任务页 | 黄横幅+靛蓝按钮像素签名 ✓ |
| shots/08-audit.png | 审计页 | 捕获 ✓ |
| shots/09-report-edit.png | 报表编辑表单 | 内容 ✓ |
| shots/10-endpoint-form.png | API 端点编辑表单 | 捕获 ✓ |
| shots/11-pool-form.png / 12-user-form.png | 池/用户表单 | 捕获 ✓ |
| shots/13-report-markdown.png | Markdown 备注报表详情 | 捕获 ✓ |
| shots/14-field-settings-panel.png | 字段设置面板展开态 | md5 独立 ✓ |
| shots/15-sort-settings-panel.png | 排序设置面板展开态 | 捕获 ✓ |
| shots/16-export-options.png | 导出「更多选项」展开态 | md5 独立 ✓ |
| shots/17-current-rules.png | 当前规则折叠展开态 | md5 独立 ✓ |
