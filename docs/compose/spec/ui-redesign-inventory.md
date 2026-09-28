# 功能/交互覆盖清单（ui-redesign · T1）

> 用途：重构的防遗漏基准。每条含「功能/约定/交互 → 来源 → 新方案去向」。
> 来源基准：`docs/compose/knowledge/`（INDEX §2 路由总表、§3 页面地图、06 UI 分卷）→ 源码核对 → README-CN 功能特性与页面说明。
> 「新方案去向」列由 T3 信息架构方案填写；T3 完成后本清单不得残留空缺。
> 最后更新：2026-09-25（T1 成稿）

## 0. 清单口径

- **路由级**：`server.py` `ROUTES` 全部 17 行（顺序首次匹配）+ 静态 vendor 直出 + 404/405/500 错误页。
- **页面级**：每个用户可见页面的功能、控件、交互、状态与来源。
- **约定级**：跨页面共享的交互约定（必须在新方案中保留或显式改造）。
- **组件级**：`render.py` 单一来源的全部 `build_*` / `render_*` / CSS/JS 资产。
- **功能特性级**：README-CN「功能特性」46 项逐条映射 UI 承载（或标注为非 UI 后端能力）。

## 1. 路由级条目（server.py ROUTES，全 17 行）

| # | 方法 | 模式 | auth | db | 页面/行为 | 来源 | 新方案去向 |
|---|------|------|------|----|-----------|------|------------|
| R1 | GET | `^/favicon\.ico$` | 否 | 否 | favicon（branding 三模式 default/color/custom） | server.py ROUTES、02 卷 | 保留（favicon 机制不变，视觉随 branding 令牌化） |
| R2 | GET/POST | `^/login$` | 否 | 否 | 登录页/提交；失败限流 5 次/5 分钟；过期提示 + `next` 白名单 | server.py:59-167、02 卷 | 重构→/login（统一视觉；限流/过期/next 语义不变） |
| R3 | GET | `^/health$` | 否 | 否 | JSON 健康检查（status+uptime） | 02 卷 | 保持（非 UI） |
| R4 | GET | `^/?$` | 是 | 否 | 首页 302 → `/report` | 02 卷 | 保持（302→报表中心） |
| R5 | GET | `^/logout$` | 是 | 否 | 退出登录 | 02 卷 | 移位→侧栏底部账户区入口（URL 不变） |
| R6 | GET/POST | `^/config/api-endpoints$` | 是 | 是 | 独立 API 管理页 | INDEX §2、config.py:2754 | 重构→API 接口列表页（同 URL，行卡片+展开布局） |
| R7 | GET | `^/config/reports$` | 是 | 是 | 报表列表（含分类树+批量） | config.py:737 | 重构→报表配置页（同 URL，左树右表+浮出批量条） |
| R8 | POST | `^/config/reports/memo-preview$` | 是 | 否 | 备注 Markdown 预览（fetch） | config.py:1890 | 保留（fetch 预览协议不变，挂载编辑表单备注区） |
| R9 | GET | `^/config/categories$` | 是 | 是 | 旧分类页 → 重定向 `/config/reports#sec-categories` | 04 卷、README 页面说明 | 保持（重定向不变；锚点改左树选中定位并保留兼容） |
| R10 | POST | `^/config/api-endpoints/description-preview$` | 是 | 否 | 接口说明 Markdown 预览（fetch） | config.py:1901 | 保留（fetch 预览协议不变，挂载端点说明区） |
| R11 | POST | `^/config/site-branding$` | 是 | 是 | 站点标识保存 | config.py:875 | 移位→概览页设置区块（POST 不变） |
| R12 | * | `^/config($ | /)` | 是 | 是 | 配置门户 + pools/users/报表表单/分类/调度/预设导入等全部 config 分支 | config.handle_request:2107 | 重构→config 子页群：概览收窄、池/用户独立列表、调度表单拆页 |
| R13 | * | `^/report($ | /)` | 是 | 是 | 报表选择页 / 报表详情 / POST refresh_cache / `/report/preview` | report.handle_request:1775 | 重构→报表中心 + 报表详情（Tab 化）；refresh/preview 协议不变 |
| R14 | * | `^/export($ | /)` | 是 | 是 | CSV/JSON/ZIP 导出下载 | export.handle_export:319 | 合并→统一导出对话框（GET 参数协议不变） |
| R15 | * | `^/api/` | 否 | 是 | 数据 API（Bearer/api_key；非页壳） | api_handler:55、05 卷 | 保持（非页壳） |
| R16 | * | `^/audit($ | /)` | 是 | 否 | 审计日志页（只连 audit.db） | audit_page | 重构→审计页（统一筛选条组件，参数不变） |
| R17 | GET | `/static/vendor/<name@ver>/<file>` | 否 | 否 | 白名单静态直出（common.css/js 等） | 02 卷 | 保持（机制不变） |

补充（不在 ROUTES 表独立行但用户可达）：

| 条目 | 说明 | 来源 | 新方案去向 |
|------|------|------|------------|
| E1 | `POST /config/pools/test` 测试连接（不落库，密码留空=沿用） | 04 卷 | 保留（连接池表单按钮，协议不变） |
| E2 | `POST /config/test-cases/import` DEBUG 预设夹具导入（confirm） | config.py:930、04 卷 | 移位→概览 DEBUG 区块（同现状，视觉统一） |
| E3 | 404/405/500 统一 `_render_error_page` | 02 卷、server.py:172 | 重构→统一错误页（令牌化+返回入口） |

## 2. 页面级功能与交互

### 2.1 `/login` 登录页

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 登录表单 | username/password POST `/login`，autofill autocomplete，提交按钮「登 录」 | server.py:59 | 保留（并入统一表单组件） |
| `next` 回跳 | 仅 `/` 开头且非 `//`/`/\` 白名单，隐藏字段透传 | server.py:155-170、02 卷 | 保持（协议不变） |
| 错误/过期/限流状态 | error（红）/notice（黄）两种提示；`expired=1` 过期提示；5 分钟 5 次限流拒绝 | server.py:135、auth.py | 保留（统一状态条组件） |
| 独立页壳 | `_LOGIN_PAGE` + `_BASE_CSS`，紫渐变全屏背景，卡片式表单 | server.py:59-127 | 删除（紫渐变独立壳废除，登录并入全站令牌布局） |
| 版本页脚 | 「Web 报表工具 v1.0」 | server.py:124 | 改名→页脚显示产品名+版本（branding 感知） |

### 2.2 `/report`（无 id）报表选择页

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 分类树状下拉 | 按分类树层级缩进生成 option，`onchange` 自动提交跳转报表 | report.py:1266、render.py:2198 | 重构→报表中心左分类树（点击筛选右网格）；紧凑切换 select 仅留详情页头部 |
| 最近查看卡片 | localStorage `sqlreport_recent` 去重保序、最多 8 条，服务端挂载点渲染 | report.py:1360、render.py:512-527 | 重构→报表中心顶部卡片横排（空则隐藏，key 不变） |
| 分类树选择器 | `build_report_switcher_html` 分组树状选择 | render.py:2156 | 合并→报表中心（左树+右卡片网格，单一入口） |

### 2.3 `/report?id=` 报表详情页（核心页）

页面顺序（06 卷）：header → 切换器 → Redis 横幅 → flash → memo → 调试/规则/API URL 折叠 → 控制栏+排序条+表格+分页+字段/排序面板+隐藏筛选 form → 自定义 `_FOOTER`（再次内联 `_COMMON_JS`）。

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 报表切换器 | 下拉/树状切换报表，自动跳转 | render.py:2156、report.py:1686 | 重构→详情头部紧凑 select + 报表中心入口（整宽切换卡废除） |
| Redis 横幅 | `build_redis_banners_html` 缓存来源/降级提示 | render.py:1275 | 重构→状态横幅（仅异常出现，人话文案） |
| flash 提示 | 302 `?flash=` 注入 + 6s 淡出剥参 | render.py:1092、658 | 保留（统一 flash 组件换装） |
| 备注 memo | Markdown 渲染折叠区 + 三态开关（自动/展开/折叠），按报表 localStorage 记忆 | render.py:1566、437 | 重构→Tab「备注」+数据页单行摘要；三态开关删除（按报表记忆保留为折叠态） |
| 调试区 | `build_debug_section_html` 实际 SQL/连接信息折叠 | render.py:1301 | 移位→Tab「调试」 |
| 当前规则区 | 筛选/排序/列 JSON 展示，复制/应用按钮 | render.py:1488 | 合并→Tab「规则」（与嵌套构建器/排序列表合一） |
| API URL 区 | `build_api_urls_section_html` + `initApiUrls` 复制 | render.py:4177、422 | 移位→Tab「接口」（复制组件统一） |
| 控制栏 | 页大小 10/20/50/100/200 自动提交、刷新、编辑跳转、导出 form | render.py:1859 | 重构→数据页工具行（主操作=刷新；导出入对话框；设置入抽屉） |
| 导出内联 form | `/export` GET：format CSV/JSON、charset GBK/UTF-8、zip、智能去引号 details（十进制/科学计数/千分位 flags 1/2/4）、CSV 提示 | render.py:1890-1980 | 合并→统一导出对话框（参数协议不变，选项常显） |
| 排序条 | `build_sort_bar_html` 列头 ▲▼ 组合排序展示与移除 | render.py:1688 | 保留→数据页排序 chips 行（组件换装） |
| 结果表格 | 表头悬浮吸附、列头点击排序、行内筛选输入（`f_`/`op_`）、10 操作符下拉、`?` 筛选帮助弹窗 | render.py:1725/1832、filter_help.py | 重构→通用数据表组件（吸附表头/列排序/快速筛选/帮助收敛保留） |
| 分页 | 总页数、跳转输入 `goPage`、页码链接 | render.py:1198 | 保留→通用分页组件（跳转防误触） |
| 字段设置面板 | 拖拽/上下移排序、显隐勾选、全选/全不选、应用；列设置 localStorage `sqlreport_cols_{id}` | render.py:1990、543 | 重构→右侧抽屉（遮罩+ESC+焦点管理） |
| 排序设置面板 | 添加/删除/调序、应用 | render.py:2037 | 重构→右侧抽屉（与列设置同组件族） |
| 嵌套筛选构建器 | and/or 分组、条件增删、`now()/today()` 等表达式插入、JSON 载入、应用/清除 | render.py:1348 | 合并→「高级筛选」抽屉（可视化构建/规则预览双视图） |
| 结果集 tab | 多结果集 `result=N` 切换，独立筛选/排序状态 | render.py:1589、3151 | 重构→数据页结果集分段控件（多结果集状态协议不变） |
| 缓存徽标与重建 | 快照时间/TTL/已过期警示；`action=refresh_cache` POST 302 保留 page/sort/cols/result | render.py:1636、report.py:1699 | 重构→轻量缓存状态行 + 刷新确认（术语翻译，refresh 协议不变） |
| 截断横幅 | 全量输出护栏截断提示（max_rows 上限 + 编辑页开启指引） | 03 卷、README 报表页 | 保留→状态横幅组件（文案统一） |
| 写护栏横幅 | `WRITE_ALLOWED_BANNER` / 拒绝提示（三端同文案） | 03 卷 | 保留→状态横幅组件（三端同文案保持） |
| 非法筛选 flash | 数值筛选非法仅 Web 页提示 | report.py:1756 | 保留（协议不变，组件换装） |
| 接口说明折叠 | 每端点「接口说明」Markdown 独立折叠 + 三态开关（按端点 id 记忆），摘要 40 字截断悬停 | README 报表页、06 卷 | 移位→Tab「接口」端点说明卡；三态删除（默认展开） |
| 锚点行高亮 | `initAnchorRowHighlight` | render.py:681 | 保留（行为不变，样式令牌化） |
| loading 遮罩 | `initQueryLoadingOverlay` 仅 `/report` 与 `.btn-refresh`（排除 `/export`） | render.py:690 | 扩展→全站提交遮罩（导出下载除外） |

### 2.4 `/report/preview` 与编辑页联动

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 未保存 SQL 预览 | 编辑页【预览】新窗口 POST 当前表单 SQL，实时查看结果 | README、config.py:1165 | 保留→SQL 分区工具组按钮 |
| 查看-编辑双向关联 | 详情页【编辑】→ 编辑页；编辑页【查看】→ 详情页 | README 编辑-查看双向关联 | 保留→统一操作组位置（详情头部 / 编辑底栏） |
| memo 预览 | 编辑表单备注 Markdown fetch 预览 | config.py:1890 | 保留→备注区 fetch 预览 |

### 2.5 `/export` 导出

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 导出触发 | 控制栏内联 form GET `/export`（非独立页面）；保留筛选/排序/列/结果集 | render.py:1890、03 卷 | 合并→统一导出对话框（唯一入口；GET 协议与参数不变） |
| 格式/字符集/ZIP/智能去引号 | CSV 默认、GBK 默认、zip=1、smart_quotes flags | 03 卷、README 导出 | 保留→对话框字段组（常显，废除 popover 藏匿） |
| 截断标记 | 头 `X-Export-Truncated`、CSV 尾注、JSON `_meta.truncated` | 03 卷 | 保持（非 UI） |

### 2.6 `/config` 配置门户（render_overview）

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 首部署引导 | 无连接池时三步指引横幅（添加池→建报表→发布 API） | config.py:973 onboarding | 移位→报表中心空态 + 概览空态（文案复用） |
| 连接池列表区 | `build_pool_section_html`：列表+报表关联数、添加/编辑/复制/删除（confirm 披露破坏半径）、上下移动、测试连接 | render.py:2438、config.py:691 | 移位→/config/pools 独立列表页 |
| 用户列表区 | `build_user_section_html`：添加/编辑/删除；隐藏自身删除行 | render.py:2482 | 移位→/config/users 独立列表页 |
| 报表管理卡 | 报表总数/分类数 + 入口 `/config/reports` | config.py:1026 | 合并→概览统计磁贴+快捷入口（大卡片留白废除） |
| 分类管理卡 | 分类数 + 入口 `/config/reports#sec-categories` | config.py:1036 | 合并→概览统计磁贴（分类管理在报表配置页左树） |
| API 接口卡 | 接口数 + 前 5 个接口名称/路径/说明摘要（截断+title）+ 入口 | config.py:996 | 合并→概览统计磁贴+快捷入口（内嵌清单废除） |
| 站点标识区 | favicon 三模式（内置/纯色/自定义 PNG·ICO ≤256KB）、标签页前缀、颜色带 `#`、保存即刷 | render_overview `_render_branding_section`、04 卷 | 保留→概览设置区块（表单组件换装） |
| DEBUG 测试数据卡 | 仅 DEBUG：预设夹具导入 confirm POST | config.py:1040 | 保留→概览 DEBUG 区块（仅 DEBUG） |
| flash | 302 后提示 | config.py:984 | 保留（组件换装） |

### 2.7 `/config/pools` 连接池表单

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 新增/编辑/复制表单 | `build_pool_form_html`；保存双按钮 `save`（留页）/`save_close`（302+flash） | render.py:2285、04 卷 | 保留→/config/pools 表单页（分区：连接信息） |
| 测试连接 | 「测试连接」按钮 POST `/config/pools/test`，不落库；密码留空=沿用 | render.py:2337、04 卷 | 保留（结果统一为行内状态条） |
| 删除 | confirm + 关联报表数披露 | config.py:1502 | 保留（统一确认弹层+破坏半径披露） |
| 上下移动 | `build_move_buttons_html` | render.py:2257 | 保留→列表排序模式（组件换装） |

### 2.8 `/config/users` 用户表单

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 新增/编辑/删除 | `build_user_form_html`；改密/改名清 sessions；禁止删除当前登录用户 | render.py:2383、04 卷 | 保留→/config/users 表单页（会话约束不变） |
| 保存双按钮 | save / save_close 模式 | 04 卷 | 重构→sticky 底栏「保存/保存并关闭/取消」（全站表单统一） |
| flash 防泄露 | 不回显明文密码 | 04 卷易踩坑 | 保持（约束不变） |

### 2.9 `/config/reports` 报表列表页（render_reports_page）

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 分类树区块 | `build_category_section_html` 树状分组缩进，整体折叠（localStorage `cat_tree_collapsed` / `data-mem-key`） | render.py:2588、314 | 移位→页左栏常驻分类树（独立折叠区块废除） |
| 报表行操作 | 查看（新窗）/编辑（新窗）/复制/删除 confirm/上下移动 | README 报表列表 | 重构→查看/编辑主链接 +「更多」菜单收纳复制/删除/移动 |
| 徽标 | ⏰ 定时启用、♻ 缓存保活 | render.py:4335、README | 重构→文字徽标「定时」「保活」（emoji 废除） |
| 备注摘要 | 前 15 字符截断预览 | README | 保留（悬停全文） |
| 前端过滤框 | `build_config_filter_box_html` + `initConfigFilter` | render.py:1013、493 | 保留→页头搜索框（组件换装） |
| 批量操作 | 全选/反选（分类级）、批量删除/改连接池/改分类/改缓存策略（含 TTL 输入切换）；跨分类移动下拉 | render.py:2622-2642、config.py:1758-1869 | 重构→选中后底部浮出批量条（功能全保留） |
| 分类管理区块 | `build_category_manage_section_html`：树形增删改名/调序/新增子类 | render.py:2520 | 移位→左栏树节点操作（增删改名/排序/新增子类） |
| 锚点定位 | `#sec-categories` 直达分类区块 | config.py 路由注释 | 改名→左树选中定位（URL 锚点兼容保留） |

### 2.10 报表编辑表单（/config/reports/add|edit|copy）

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| SQL 编辑器 | Tab 缩进 `initSqlEditorTabIndent`、格式化按钮 `_SQL_FORMATTER_JS`、语法高亮预览切换 `_SQL_HIGHLIGHT_JS` | render.py:596/729/755 | 保留→SQL 分区（Tab 缩进/格式化/高亮/预览按钮组保留） |
| 字段 | 名称/SQL/连接池/默认页大小/分类/备注（Markdown 预览） | README、config.py:1165 | 合并→「基础」+「SQL」分区 |
| 全量输出护栏 | `allow_all_output` 开关 + max_rows 输入（开关开启保存前 confirm）；报表含写 SQL 才显示 `allow_write`，新建默认 0 | 04 卷、README | 移位→「输出护栏」分区（逻辑不变） |
| 定时执行折叠区 | 启用、间隔分钟或每天 HH:MM、错过补偿 skip/run_once；保存同步任务行 | README 报表编辑 | 移位→「调度与保活」分区（完整管理链调度页） |
| 缓存保活折叠区 | 提前量秒数，0=不保活；需 Redis | README、07 卷 | 移位→「调度与保活」分区 |
| API 端点区 | 端点表单/预览/说明 Markdown/Key 管理（**主 form 外**） | render.py:3382/3855、05 卷 | 移位→「API 端点」分区（Key 区仍在主 form 外） |
| 保存 | `save` 留页 / `save_close` 返回列表 + flash | 04 卷 | 重构→sticky 底栏三键（save/save_close 协议映射不变） |

### 2.11 `/config/api-endpoints` 与端点表单

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 全局接口列表 | `build_api_endpoints_list_html`：关联报表、路径、启停、删除 confirm、复制 URL | render.py:2865 | 重构→行卡片+展开（主 URL 优先，次要 URL 收起） |
| 端点表单 | 名称/路径/输出格式/智能引号/模板/CORS/预设/分页/`allow_fetch_all`；URL 联动更新（static/fetch-all 复制按钮） | render.py:3382、3674-3816 | 重构→分区表单（基本信息/请求与输出/模板/预设与 Key） |
| 模板预览 | `{{data}}/{{results}}` 实时渲染、重置默认 | render.py:3784 | 保留→模板分区实时预览 |
| 接口说明 | Markdown + fetch 预览（description-preview） | config.py:1901、render.py:3515 | 保留→说明字段（fetch 预览保留） |
| Key 管理 | 多 Key 启停/删除 confirm/新增；`sk-` 前缀；**主 form 之外**（htmlcheck 门禁） | render.py:3855、05 卷 | 保留→独立 Key 区块（主 form 外门禁保持） |
| 真实数据预览 | `previewWithRealData()` | render.py:3477 | 保留→基本信息区按钮 |
| 静态缓存状态 | `updateStaticCacheState`、版本化 `.json` URL 展示 | render.py:3674、05 卷 | 保留→请求输出区状态行（术语翻译） |

### 2.12 `/config/scheduler` 定时任务页

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 任务列表 | `build_scheduler_page_html`：任务名、关联报表（按序）、下次执行、上次结果（耗时）、失败计数、审计标记、熔断标记 | render.py:4454、README | 重构→列表主导（行卡片，信息分级） |
| 单任务操作 | 立即执行/启停/删除（confirm） | config.py:1959-1995 | 保留（按钮换装；删除入「更多」） |
| 任务表单 | `build_scheduler_task_form_html`：interval/daily、多报表绑定、错过补偿、审计开关 | render.py:4746 | 拆分→/config/scheduler/new 与 /{id}/edit 独立表单页 |
| 排除规则编辑器 | 静默窗口树：`dow/tod/date/date_range` 叶子、AND/OR 分组（`children` 结构，≠ nested_filter） | 07 卷、03 卷 | 保留→表单内组件（分组树交互统一） |
| 全局停用横幅 | `scheduler.enable=false` 顶部提示 | 06 卷/README | 保留→页顶状态横幅（人话文案） |
| 🔇 徽标 | 已配置排除规则 | README | 改名→「含静默窗口」文字徽标（emoji 废除） |

### 2.13 `/audit` 审计页

| 功能/交互 | 说明 | 来源 | 新方案去向 |
|-----------|------|------|------------|
| 筛选 | type/date_from/date_to/session_user/keyword（共用 `parse_filter_expr` 语义） | 02 卷、render.py:3933 | 重构→统一筛选条组件（参数与语义不变） |
| 日期快捷 | 快捷选择按钮 | 06 卷页面地图 | 保留→筛选条内快捷 chips |
| 分页 + 导出 CSV | `?export=csv` | render.py:4143、07 卷 | 保留（导出入操作区按钮） |
| 清理 | POST clean + confirm | 07 卷 | 保留（统一确认+危险分级） |
| 进页轮转 | 每次进页 `_rotate_expired`（非 UI 约定） | 02 卷 | 保持（非 UI） |

## 3. 跨页面共享交互约定（新方案须保留或显式改造）

| # | 约定 | 说明 | 来源 | 新方案去向 |
|---|------|------|------|------------|
| C1 | 整页 GET/POST 刷新，无 SPA | 状态经 URL 参数/hidden 透传 | 06 卷 | 保持（整页刷新模式；抽屉/对话框为页内增强） |
| C2 | flash 模式 | 成功 302 + `?flash=`（须 quote）+ 6s 淡出 + `initFlashMessages` 剥参 | 06 卷、02 卷 | 保留→统一 flash 组件（剥参逻辑不变） |
| C3 | 危险操作 confirm | 原生 `confirm` + POST；无第二套 modal | 06 卷原则 | 重构→统一确认弹层（仍基于 build 组件，无框架；文案模板化） |
| C4 | checkbox 双字段 | `hidden 0` + checkbox `1`，`parse_qs` 取最后值 | 04 卷、06 卷 | 保持（checkbox 协议不变） |
| C5 | 保存双按钮 | `action=save` 留页 / `save_close` 302 回列表 | 04 卷 | 重构→sticky 底栏三键（save/save_close 语义映射） |
| C6 | localStorage 约定 | 树折叠 `cat_tree_collapsed`、`data-mem-key`、最近查看 `sqlreport_recent`、列设置 `sqlreport_cols_{id}`、memo/说明三态开关 | render.py:304-570 | 保留（key 不变；三态记忆改为普通折叠记忆） |
| C7 | loading 遮罩 | `initQueryLoadingOverlay`：`preventDefault` 后须自行 `form.submit()`；仅 `/report` 与 `.btn-refresh`，排除 `/export` | render.py:690、06 卷 | 扩展→全站提交遮罩（导出排除；统一封装自提交） |
| C8 | 内联 onclick 体系 | 面板/折叠/复制/批量/嵌套筛选等大量内联事件 | render.py onclick 清单 | 重构→公共 JS 统一事件初始化（减少内联 onclick） |
| C9 | 筛选语法单一来源 | `result_transform.parse_filter_expr` + `filter_help.py` 帮助弹窗（报表/审计/条件构建器共用） | 03 卷 | 语义保持；帮助入口重构→统一帮助抽屉（内容源 filter_help 不变） |
| C10 | URL 状态参数 | `id/page/page_size/sort/dir/f_/op_/cols/result/nested_filter/flash` | 03 卷 | 保持（URL 协议） |
| C11 | Markdown 渲染 | `markdown_render` 消毒 + mermaid + `_MD_CSS` 追加末尾 | 03 卷、06 卷 | 保留（渲染链不变；样式并入令牌） |
| C12 | SQL 高亮/格式化 | `_SQL_HIGHLIGHT_JS` / `_SQL_FORMATTER_JS` 仅编辑表单 | render.py:729/755 | 保留（编辑表单 SQL 分区） |
| C13 | 导航单一来源 | `_NAV_ITEMS`：报表/配置/定时/API/审计/退出 | render.py:907 | 重构→侧栏导航 `_NAV_GROUPS`（替代顶栏 `_NAV_ITEMS`，一处改原则不变） |
| C14 | 页壳骨架 | `render_page_header(title, active_nav, extra_css)` + `render_page_footer`；`$`→`$$` 转义 | render.py:967/1004 | 重构→侧栏+内容区页壳（仍单一来源；extra_css 保留） |
| C15 | 公共资产 | `_BASE_CSS`/`_COMMON_CSS`（=BASE+通用+minibtn+flash+B6）/`_COMMON_JS`；`ensure_common_assets` → `static/vendor/self@{hash8}/`；**hash 只算 CSS** | render.py:287、06 卷 | 重构→设计令牌化公共 CSS（合成/ensure_common_assets 保留；hash 覆盖 CSS+JS） |
| C16 | 报表页 JS 双轨 | 报表页 `_FOOTER` 再次内联 `_COMMON_JS`（config/audit 走外链） | 06 卷 | 重构→JS 单一外链加载（废除报表页内联双轨） |
| C17 | 锚点行高亮 | `initAnchorRowHighlight` | render.py:681 | 保留（行为不变） |
| C18 | 复制到剪贴板 | `copyToClipboard`（Key、URL、规则 JSON 等） | render.py 清单 | 保留（公共 copyToClipboard） |
| C19 | 空态行 | `build_empty_row_html` | render.py:1113 | 保留→通用空态组件（文案统一） |
| C20 | HTML 质量门禁 | 无嵌套 form、标签平衡、主表单含保存、Key 区在主 form 外 | tests/htmlcheck.py、06 卷 | 保持（htmlcheck 门禁） |
| C21 | 全站中文 | 全部用户可感知文字简体中文 | AGENTS #2 | 保持 |
| C22 | 错误页 | 404/405/500 `_render_error_page` 统一样式 | server.py:172 | 重构→统一错误页（同令牌） |
| C23 | 会话过期跳转 | 302 `/login?expired=1&next=…` | 02 卷 | 保持 |
| C24 | 写护栏三端同文案 | 页面横幅/导出 403/API 403 | 03 卷 | 保持 |
| C25 | 截断三端一致 | 页面横幅 / `X-Export-Truncated` / JSON `_meta` | 03 卷 | 保持 |

## 4. render.py 组件资产清单（单一来源全量）

### 4.1 CSS / JS 资产

| 符号 | 作用 | 行 | 新方案去向 |
|------|------|----|------------|
| `_BASE_CSS` | reset/body/fadeUp | 37 | 合并→`_TOKENS_CSS`（reset/fadeUp 并入令牌体系） |
| `_COMMON_CSS` | 合成：BASE+通用+minibtn+flash+B6 | 45/287 | 重构→令牌化重写（合成链机制保留） |
| `_MD_CSS` | Markdown 区块样式（追加末尾） | 210 | 保留（并入 Markdown 分区样式，追加顺序约定不变） |
| `_MINIBTN_CSS` / `_FLASH_WARN_CSS` / `_B6_CSS` | 切片样式 | ~287 合成 | 合并→统一按钮/提示令牌组件（切片与 btn-mini 变体废除） |
| `_COMMON_JS` | 折叠/复制/flash/过滤/最近查看/列记忆/loading/Tab 缩进… | 296 | 重构→公共初始化器集合（折叠/复制/flash/过滤/最近/列记忆/loading/Tab 功能保留） |
| `_SQL_HIGHLIGHT_JS` | SQL 高亮 | 729 | 保留 |
| `_SQL_FORMATTER_JS` | SQL 格式化 | 755 | 保留 |
| `ensure_common_assets` | 写 `static/vendor/self@{sha8}/common.css\ | js` | — | 保持（机制不变） |

### 4.2 通用组件

| 函数 | 作用 | 行 | 新方案去向 |
|------|------|----|------------|
| `render_navbar` / `_NAV_ITEMS` | 顶部导航 | 907/954 | 重构→`render_sidebar` / `_NAV_GROUPS`（顶栏废除） |
| `render_page_header` / `render_page_footer` | 页壳 | 967/1004 | 重构→侧栏页壳（`$` 转义约定保留） |
| `build_flash_html` | flash 条 | 1092 | 保留（换装） |
| `build_empty_row_html` | 空态行 | 1113 | 保留（换装） |
| `build_pagination_html` | 分页+跳转 | 1198 | 保留（换装+跳转防误触） |
| `build_config_filter_box_html` | 列表前端过滤框 | 1013 | 保留→搜索框组件 |
| `build_delete_form_html` | 独立删除 form（confirm） | 2230 | 保留→统一确认弹层封装 |
| `build_move_buttons_html` | 上下移动按钮 | 2257 | 保留→排序模式显隐 |
| `build_collapse_section_html` | 通用折叠区 | 4197 | 保留（分区折叠场景沿用） |
| `build_state_span` | 状态徽章 | 4311 | 保留→状态徽章（颜色+图标+文字双编码） |
| `build_schedule_flags_badge_html` | ⏰/♻/🔇 徽标 | 4335 | 改名→文字徽标（定时/保活/含静默窗口） |

### 4.3 报表页组件

| 函数 | 作用 | 行 | 新方案去向 |
|------|------|----|------------|
| `build_sort_params` / `build_filter_params` / `build_cols_param` / `build_nested_filter_param` | URL 参数拼装 | 1133-1186 | 保持（URL 协议） |
| `build_redis_banners_html` | Redis 横幅 | 1275 | 重构→状态横幅（仅异常出现） |
| `build_debug_section_html` | 调试折叠区 | 1301 | 移位→Tab 调试 |
| `build_nested_filter_builder_html` | 嵌套筛选构建器 | 1348 | 合并→高级筛选抽屉 |
| `build_current_rules_section_html` | 当前规则 JSON 区 | 1488 | 合并→Tab 规则 |
| `build_memo_section_html` | 备注 Markdown 折叠 | 1566 | 重构→Tab 备注+数据页摘要（三态废除） |
| `build_result_selector_html` | 多结果集 tab | 1589 | 重构→结果集分段控件 |
| `build_cache_badge_html` | 缓存徽标 | 1636 | 重构→缓存状态行（术语翻译） |
| `build_sort_bar_html` | 排序条 | 1688 | 保留→排序 chips 行 |
| `build_table_header_html` / `build_table_body_html` | 表格 | 1725/1832 | 重构→通用数据表组件（吸附/排序/快速筛选保留） |
| `build_controls_bar_html` | 控制栏（页大小/导出/面板按钮） | 1859 | 重构→数据页工具行 + 统一导出对话框 |
| `build_field_settings_panel_html` | 字段设置面板 | 1990 | 重构→列设置抽屉 |
| `build_sort_settings_panel_html` | 排序设置面板 | 2037 | 重构→排序抽屉（同组件族） |
| `build_filter_form_html` / `build_clear_filters_href` / `build_filter_action_html` | 筛选 form/清除 | 2099-2124 | 保留→快速筛选行组件（清除入工具行） |
| `build_report_switcher_html` | 报表切换器 | 2156 | 重构→详情头部紧凑 select（整卡废除） |
| `build_api_urls_section_html` | API URL 折叠区 | 4177 | 移位→Tab 接口 |

### 4.4 配置页组件

| 函数 | 作用 | 行 | 新方案去向 |
|------|------|----|------------|
| `build_pool_form_html` / `build_pool_section_html` | 连接池表单/列表 | 2285/2438 | form 保留→分区表单；section 移位→/config/pools 列表页 |
| `build_user_form_html` / `build_user_section_html` | 用户表单/列表 | 2383/2482 | form 保留→分区表单；section 移位→/config/users 列表页 |
| `build_category_opts_html` / `build_category_manage_section_html` / `build_category_section_html` | 分类下拉/管理/报表分组 | 2408/2520/2588 | opts 保留；manage 移位→报表配置左树；section 删除（分组表废除，右栏统一列表） |
| `build_api_endpoints_list_html` | API 列表 | 2865 | 重构→行卡片+展开列表 |
| `build_api_endpoint_form_html` | 端点表单 | 3382 | 重构→分区表单 |
| `build_api_endpoint_preview_help_html` | 预览帮助 | 3355 | 保留→表单内帮助 |
| `build_api_key_manage_html` | Key 管理（主 form 外） | 3855 | 保留（主 form 外门禁保持） |
| `render_audit_page` | 审计页整页 | 3933 | 重构→统一筛选条+通用表格 |
| `build_scheduler_page_html` / `build_scheduler_task_form_html` | 调度页/任务表单 | 4454/4746 | page 重构→列表主导；form 拆分独立表单页 |

## 5. README「功能特性」46 项 → UI 承载映射

| 特性 | UI 承载 | 来源 | 新方案去向 |
|------|---------|------|------------|
| 连接池管理（CRUD/调序/复制） | /config 连接池区 | README F1 | 移位→/config/pools 独立页（视觉统一） |
| 用户管理（PBKDF2） | /config 用户区 | README F2 | 移位→/config/users 独立页 |
| 报表配置（SQL/池/页大小/备注/分类/复制） | 报表编辑表单 | README F3 | 重构→编辑表单分区 |
| 分类树管理（无限层级/调序） | /config/reports 分类区块 | README F4 | 移位→报表配置页左栏树 |
| 批量操作（删除/缓存/池/分类、全选反选） | /config/reports 批量栏 | README F5 | 重构→浮出批量条（功能全保留） |
| SQL 格式化 & 高亮预览 + 未保存预览 | 报表编辑表单 | README F6 | 保留→SQL 分区 |
| 分页表格（内存分页/总页数/跳转） | 报表详情分页 | README F7 | 保留→通用分页组件 |
| 悬浮表头 | 报表表格 | README F8 | 保留→通用表格吸附表头（sticky+阴影令牌化重设计完成） |
| 多字段排序（列头+面板） | 排序条+排序面板 | README F9 | 保留→排序 chips + 排序抽屉 |
| 多字段筛选（10 操作符+统一语法+帮助） | 表格筛选行+帮助弹窗 | README F10 | 保留→快速筛选 + 高级筛选抽屉 + 统一帮助抽屉 |
| 字段设置（拖拽/显隐） | 字段设置面板 | README F11 | 重构→列设置抽屉 |
| CSV 导出（BOM） | 控制栏导出 | README F12 | 保留→统一导出对话框 |
| JSON 导出（智能去引号面板） | 导出 details | README F13 | 保留→导出对话框选项组 |
| 字符集切换（GBK/UTF-8） | 导出 charset | README F14 | 保留→导出对话框 |
| ZIP 压缩包 | 导出 zip | README F15 | 保留→导出对话框 |
| 多结果集 tab（独立筛选排序） | 结果集 tab | README F16 | 保留→结果集分段控件（状态协议不变） |
| 报表即 API（Key/CORS/预设/模板） | 端点表单+Key 管理 | README F17 | 保留→端点分区表单 + Key 区块 |
| API 静态文件缓存（.json） | 端点表单静态区 | README F18 | UI 保留→请求输出区状态；非 UI 部分保持 |
| 配置存储双引擎 | 无 UI（app_config） | README F19 | 保持（非 UI） |
| 站点标识（favicon/前缀） | /config 站点标识区 | README F20 | 保留→概览设置区块（视觉统一） |
| 三层查询缓存 | 徽标/横幅/调试区可见 | README F21 | 保留→缓存状态行 + 状态横幅 + 调试分区（术语翻译） |
| 报表定时执行（完整调度能力） | /config/scheduler + 编辑表单折叠区 | README F22 | 重构→调度列表 + 独立表单页 + 编辑「调度与保活」分区 |
| 缓存保活 | 编辑表单保活折叠区 + ♻ 徽标 | README F23 | 移位→编辑「调度与保活」分区 + 列表保活徽标 |
| 编辑-查看双向关联 | 详情/编辑互跳按钮 | README F24 | 保留→统一操作组位置 |
| 健康检查端点 | 无 UI | README F25 | 保持（非 UI） |
| API 接口独立管理页 | /config/api-endpoints | README F26 | 重构→行卡片列表（同 URL） |
| Session 滑动过期 | 登录过期提示（间接 UI） | README F27 | 保持（登录过期提示语义） |
| 导出支持排序 | 导出携带 sort 参数 | README F28 | 保持（协议） |
| 全量输出护栏（开关/max_rows/横幅） | 编辑表单 + 报表页横幅 | README F29 | 保留→编辑「输出护栏」分区 + 详情状态横幅 |
| 事务性 SQL 执行 | 无 UI（执行层） | README F30 | 保持（非 UI） |
| 错误日志独立输出 | 无 UI | README F31 | 保持（非 UI） |
| 审计日志自动轮转 | 无 UI（/audit 展示） | README F32 | 保持（非 UI；/audit 展示不变） |
| ThreadingHTTPServer | 无 UI | README F33 | 保持（非 UI） |
| 全局异常兜底 | 500 错误页 | README F34 | 重构→统一错误页 |
| Redis 可观测性 | 日志（间接） | README F35 | 保持（非 UI） |
| 纯标准库 | 技术约束 | README F36 | 保持（约束） |
| 预设/JSON 模板（README 独立章节） | 端点表单模板区 + DEBUG 导入卡 | README API 模板章节 | 保留→端点模板分区 + 概览 DEBUG 卡 |
| 筛选语法说明（filter_help） | 帮助弹窗（报表/审计/构建器） | README 页面说明 | 保留→统一帮助抽屉（内容源不变） |
| 审计四类 type + 筛选导出清理 | /audit | 02/07 卷 | 保留→审计页筛选条与操作区 |
| 登录限流/过期/next | /login | 02 卷 | 保留→登录页（协议不变） |

## 6. 遗漏自查（T1 验收用）

- [x] INDEX §2 路由总表 17 行全部列于 §1（R1–R17）
- [x] INDEX §3 页面地图全部条目落入 §2（login/根/report/preview/export/config 全家/audit/health/api/favicon）
- [x] README 功能特性 46 行全部落入 §5（含非 UI 条目显式标注）
- [x] 06 卷交互模式 7 条 + 组件库清单全部落入 §3/§4
- [x] 源码补查：render.py build_*/render_* 全量、onclick/localStorage 清单、config.py handler 清单、report.py 页面函数
- [x] 「新方案去向」无空缺 —— 由 T3 完成后勾选
