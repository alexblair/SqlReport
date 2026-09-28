# 统一视觉与组件 / 交互规范（ui-redesign · T4）

> 单一方向：**明亮工作台 + 深色侧栏**。本文是 T5 原型与 T7 实施的唯一样式/组件基准；一切取值以此为准，禁止临场发明第二套。
> 与 IA（`ui-redesign-ia.md`）配套阅读；覆盖清单去向已定的功能全部按本规范换装。
> 最后更新：2026-09-25

## 0. 设计原则

1. **数据优先**：页面第一视觉是数据与主操作，不是装饰；首屏尽量见到数据。
2. **一套令牌**：颜色/字号/间距/圆角/阴影只允许从本文取值；代码中禁止散写 hex（品牌图与 Markdown 代码高亮除外，走语义令牌）。
3. **一套组件**：全站交互控件只允许使用 §3 组件清单；新需求先扩展本规范再实现。
4. **状态可感知**：hover / focus-visible / disabled / loading / empty / error 每个组件齐备；状态用「颜色+图标/文字」双编码。
5. **术语说人话**：用户可见文案按 §5 术语表；实现词（prefer_cache、L1/L2、prefer…）禁止直出。

## 1. 设计令牌

### 1.1 色板

| 令牌 | 值 | 用途 |
|------|----|------|
| `--bg-app` | `#f3f4f8` | 内容区背景 |
| `--bg-surface` | `#ffffff` | 卡片/表格/表单面 |
| `--bg-subtle` | `#f8fafc` | 表头、次级面板 |
| `--bg-hover` | `#f1f5f9` | 行/项 hover |
| `--sidebar-bg` | `#0f172a` | 侧栏底 |
| `--sidebar-ink` | `#cbd5e1` | 侧栏常规字 |
| `--sidebar-ink-active` | `#ffffff` | 侧栏激活字 |
| `--sidebar-active-bg` | `rgba(99,102,241,0.18)` | 侧栏激活底 |
| `--brand` | `#4f46e5` | 主色（延续现状 indigo） |
| `--brand-hover` | `#4338ca` | 主色 hover |
| `--brand-soft` | `#eef2ff` | 主色浅底（选中、soft 按钮） |
| `--ink` | `#0f172a` | 主文字 |
| `--ink-2` | `#475569` | 次文字 |
| `--ink-3` | `#64748b` | 辅助文字（≥4.5:1 于白底） |
| `--line` | `#e5e7eb` | 分隔线/描边 |
| `--line-strong` | `#d1d5db` | 输入框描边 |
| `--ok` | `#059669` / 软底 `#ecfdf5` | 成功/启用/缓存正常 |
| `--warn` | `#d97706` / 软底 `#fffbeb` | 警示/将过期/停用横幅 |
| `--danger` | `#dc2626` / 软底 `#fef2f2` | 危险/失败/删除 |
| `--info` | `#2563eb` / 软底 `#eff6ff` | 信息横幅 |
| `--focus-ring` | `0 0 0 3px rgba(79,70,229,.35)` | 焦点圈 |

### 1.2 字体与字阶

- 正文字体：`system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`
- 等宽：`ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace`（SQL、路径、Key、数字列可选）

| 令牌 | 字号/行高 | 字重 | 用途 |
|------|-----------|------|------|
| `--fs-title` | 20px / 28px | 700 | 页标题 h1 |
| `--fs-h2` | 16px / 24px | 600 | 区块标题 h2 |
| `--fs-h3` | 14px / 20px | 600 | 卡内小节 h3 |
| `--fs-body` | 14px / 22px | 400 | 正文、表格 |
| `--fs-sm` | 13px / 20px | 400 | 辅助说明 |
| `--fs-xs` | 12px / 16px | 500 | 徽标、表头（不用 uppercase，中文语境去字距） |

### 1.3 间距 / 圆角 / 阴影 / 动效

- 间距（4 基准）：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40`
- 圆角：`sm 6px`（输入/按钮）、`md 10px`（卡片/对话框）、`lg 14px`（抽屉面板头）、`full 999px`（chips）
- 阴影：
  - `--sh-1: 0 1px 2px rgba(15,23,42,.06)` 卡片
  - `--sh-2: 0 8px 24px rgba(15,23,42,.12)` 抽屉/对话框/浮出条
  - `--sh-pop: 0 4px 12px rgba(15,23,42,.10)` 菜单
- 动效：`--t-fast 120ms`、`--t-med 200ms`，`ease-out`；仅透明度/位移 ≤8px；尊重 `prefers-reduced-motion`

## 2. 布局骨架

```
┌──────────┬──────────────────────────────────────┐
│  侧栏     │  页头（h1 + 操作组 + 面包屑/副标题）   │
│  240px   ├──────────────────────────────────────┤
│  深色     │  内容区（max-width:1440px, padding 24）│
│  固定     │  卡片 / 表格 / 表单分区                │
│          ├──────────────────────────────────────┤
│  品牌     │ （可选）底部浮出层：批量条/保存栏        │
│  分组导航 │                                      │
│  ────     │                                      │
│  账户区   │                                      │
└──────────┴──────────────────────────────────────┘
```

- 侧栏：宽 240px，`position:fixed`；分组标题 `--fs-xs` 灰；激活项左侧 3px 品牌条+软底。
- 账户区吸底：用户名 + 「退出」。
- 内容区背景 `--bg-app`，卡片 `--bg-surface`。
- 断点：<1024px 侧栏收成 64px 图标栏（tooltip 兜底 title）；<768 侧栏改顶部抽屉（原型可只示意 ≥1024）。

## 3. 组件规范

> 每个组件：解剖、变体、状态。DOM 语义对应未来 `build_*` 输出；**原型与实施共用同一 class 命名**（下表「class」列）。

### 3.1 按钮 `.btn`

- 层级：`btn-primary`（每屏 ≤1 个主操作）、`btn-secondary`（白底描边，常规）、`btn-ghost`（无底，行内轻操作）、`btn-danger`（确认前不加实心红铺满；列表默认 secondary，确认弹层内才用 danger 实心）、`btn-link`。
- 尺寸：`btn-md` 32px、`btn-sm` 26px；图标+文字 gap 6px。
- 状态：hover 提亮一档；`disabled` 透明度 .5+不响应；`loading` 文字保留+右侧 14px spinner，按钮锁宽。
- 变体：`btn-icon` 32×32 方形（仅常用图标：刷新/复制/更多）。

### 3.2 表单 `.field` / `.input` / `.select` / `.textarea`

- 结构：label（`--fs-sm` 600）→ 控件 → help/error（`--fs-xs`）。
- 控件：高 34px（`input/select`），描边 `--line-strong`，聚焦焦点圈；error 态描边 `--danger`+错误文案。
- checkbox/radio：原生控件+14px 标签，组用 `.check-group`（网格自动换行）。
- 双字段 checkbox 协议（hidden 0 + checkbox 1）**保持**，仅视觉换装。

### 3.3 表格 `.table`

- 表头：`--bg-subtle`、`--fs-xs`、字重 600、**不 uppercase**；排序列头可点，激活排序显示 `↑1/↓2` 序号 chip。
- 行：高 40px；hover `--bg-hover`；选中行 `--brand-soft`；粘性表头 `position:sticky; top:0` + 底部 1px `--line` + `--sh-1`。
- 单元格操作右对齐；行内主链接 `--brand` 文字钮。
- 空态：`.table-empty` 居中插画级文案 + 可选主操作（复用空态组件）。
- 数字列可 `font-variant-numeric: tabular-nums`。

### 3.4 卡片 `.card` 与区块

- `padding:20px`、圆角 `md`、`--sh-1`；区块标题行 = h2 + 右侧操作组（`.card-head`）。
- 统计磁贴 `.stat-tile`：白卡+大数字（`--fs-title`）+标签（`--fs-sm`），横向网格 4–6 个。

### 3.5 状态与徽标

- `.badge`：`.badge-ok / warn / danger / info / neutral`，软底+同色深字+小图标点；用于「定时」「保活」「含静默窗口」「启用/停用」「N 个 Key」。
- `.status-dot`：8px 圆点+文字（缓存状态、池连通性）。
- **禁止 emoji 图标**；旧 ⏰♻🔇→ 文字徽标（本规范承接）。

### 3.6 横幅 `.banner`

- 变体 info/success/warn/danger；左图标+标题（可）+正文+可选行动按钮；置于页头下方。
- 仅承载**用户需知道的状态**（截断、写护栏、缓存不可用、调度全局停用、flash 结果）。

### 3.7 Tab `.tabs` / `.tab`

- 详情页一级导航：数据 | 规则 | 接口 | 调试 | 备注（缺失项不渲染）。
- 激活：下边 2px `--brand` 指示条 + 字重 600；`role="tablist/tab/tabpanel"`，左右键切换（原型至少 focusable）。
- 结果集切换用 `.segment`（分段控件），不与页面 Tab 混用。

### 3.8 抽屉 `.drawer`（列设置 / 排序 / 高级筛选 / 帮助）

- 右侧滑入 420px（帮助 480px），`--sh-2`；遮罩 `rgba(15,23,42,.45)`。
- 头：标题 + 关闭钮；底：操作区（重置/应用）。
- 交互：ESC 关闭、遮罩点击关闭、打开时焦点移入面板、关闭归还焦点；`role="dialog" aria-modal="true"`。
- 列设置/排序：列表行含显隐 checkbox、上移/下移（替代拖拽也可接受——保留现有上下移交互，原型用上下移+全选组）。

### 3.9 对话框 `.modal`

- 居中 480px（导出 560px），结构同抽屉；按钮右对齐：取消（secondary）+ 确认（primary 或 danger）。
- **确认文案模板**：`{动词}{对象}？{影响范围/不可逆提示}`。例：「删除报表「订单概览」？将同时下线其 2 个 API 端点。」
- 导出对话框：格式段（CSV/JSON）、字符集段、智能去引号（JSON 时启用）、压缩包、列范围（当前列设置摘要+「去列设置」链接）、确认=「导出」。

### 3.10 Flash 与 toast

- 保留 302 `?flash=` 协议；渲染为页顶 `.banner.success|danger`，**6s 后可手动 × 关闭，不强制消失前 3s**（较现状降低错过率：改为 8s 或保留按钮——取：8s 自动淡出+×立即关）。

### 3.11 分页 `.pagination`

- 总数文案 + 页码组（首/上/…/下/尾）+ 跳转输入。跳转输入 `change` 后确认条目 >总页时提示一次再跳（防误触）；页大小用 `.select` 紧邻总数。

### 3.12 筛选条 `.filterbar` 与快速筛选行

- `.filterbar`（审计、列表搜索）：搜索 input + 类型 select + 日期 chips（今天/近7天/近30天/自定义起止）+ 应用/清除。
- 报表快速筛选行：每列头下方 `select(op) + input`（现状保留），「高级筛选」「帮助」「清除」收进数据页工具行右侧。

### 3.13 批量条 `.batchbar`

- 选中 ≥1 行时从内容区底部浮出：`已选 N 项` + 操作钮组 + 取消选择；`--sh-2`、白底、圆角 `md`；操作含危险项用 secondary，点击后进统一确认弹层。

### 3.14 Sticky 表单底栏 `.formbar`

- 表单页吸底：左=未保存指示（有修改时黄点「有未保存更改」），右=取消 / 保存并关闭 / 保存（primary）。
- 协议映射：保存=`action=save`（200 留页）、保存并关闭=`save_close`（302+flash）、取消=返回列表（有修改则确认）。

### 3.15 侧栏 `.sidebar`

- 品牌行（logo 字标 + 产品名，来源=branding 配置）；分组：分析/管理/服务/治理；项高度 36px；账户区：用户名 + 退出。

### 3.16 搜索 `.search`

- 高 34px、左图标、clear ×；列表页防抖 200ms 客户端过滤（沿用 initConfigFilter 语义）。

### 3.17 空态 `.empty`

- 标题一句 + 说明一句 + 主操作按钮；用于：无报表/无任务/无接口/筛选无结果（按钮变「清除筛选」）。

### 3.18 遮罩与加载

- 全站提交遮罩 `.loading-mask`：表单 POST 提交时显示（导出/下载排除）；报表数据刷新用行内 `.btn.loading`+表格骨架（原型示意 spinner 即可）。
- 禁止仅按钮 loading 而页面可重复提交（提交后同时 `disabled`）。

### 3.19 复制 `.copy-btn`

- 图标+「复制」sm 按钮；成功后 1.5s 变「已复制」`--ok`；统一 `copyToClipboard` 封装。

### 3.20 代码与 SQL

- `.code-block`：`--bg-subtle`、等宽 13px、圆角 sm、可滚动；SQL 编辑区 12–14px 等宽、min-height 220px；格式化/高亮/预览按钮组在区下方左侧。

### 3.21 Markdown 区

- 沿用消毒渲染与 mermaid；外层 `.md-body` 间距按令牌；出现于备注 Tab、接口说明、预览弹层。

### 3.22 帮助抽屉

- 全站 `?`/「帮助」入口 → 右侧抽屉；内容源 `filter_help.py`（实施期由后端注入）；原型内置筛选语法说明页内容示意。

## 4. 图标政策

- 使用内联 SVG 线性图标（stroke 1.5、24 viewBox、currentColor），只允许以下集合：search, refresh, download, settings, list, calendar, database, users, key, chart, folder, file, copy, edit, trash, more, chevron-*, x, check, alert, info, play, eye, plus。
- 禁止 emoji 作为 UI 图标；正文示例中的符号保留。

## 5. 术语表（用户可见文案）

| 实现词/旧文案 | 新文案 |
|---------------|--------|
| prefer_cache / 进程缓存 (55s 前刷新…) | 数据更新于 X 分钟前 |
| TTL=1h | 缓存 1 小时 |
| Redis 不可用，已切换至直连 MySQL 模式 | 缓存服务暂不可用，已直连数据库查询（不影响使用） |
| 直连 MySQL (prefer_cache \| TTL=1h) | 未启用缓存 · 实时查询 |
| 已过期（下次请求自动刷新） | 缓存已过期，下次访问自动刷新 |
| L1/L2/L3 | （不出现在 UI） |
| ⏰ / ♻ / 🔇 | 徽标：定时 / 保活 / 含静默窗口 |
| 允许全部输出 | 允许导出全部行（关闭时超出上限将截断） |
| 定时调度全局已停用（app_config.json → …） | 定时调度当前为停用状态，任务仅保存不自动执行 |
| 结果 0 / 结果 1（API 输出模式） | 单结果集 / 全部结果集 |
| 新增测试用例 | 导入演示数据（DEBUG） |

## 6. 交互规则（全站）

1. 焦点：凡可交互元素必须 `:focus-visible` 显示焦点圈；打开抽屉/对话框锁焦点，关闭还原。
2. ESC/遮罩：所有浮层（抽屉、对话框、菜单）支持 ESC 与遮罩关闭；**表单类抽屉关闭前有修改则确认**。
3. 提交：POST 表单统一提交遮罩+禁用重复提交；成功走 302+flash（协议不变）。
4. 危险操作：一律统一确认弹层+§3.9 文案模板；列表默认不使用实心红大按钮。
5. 即时提交控件（页大小、结果集、分类切换）保持即时；**跳页输入**与**批量删除**需确认。
6. flash：8s 自动消失 + 手动 ×。
7. 键盘：表格行主链接可 Tab 达成；Tab 组件支持左右键（原型示意）。
8. 中文排版：不使用 letter-spacing 大写英文表头风格；按钮文案不加空格变形（废除「登 录」写法→「登录」）。

## 7. 无障碍基线

- 对比度：正文≥4.5:1、大字/图标≥3:1（本令牌已按此取色）。
- aria 最小集：`nav[aria-label]`、`role=tablist`、`role=dialog aria-modal`、`aria-expanded`（折叠/行展开）、`aria-live=polite`（flash、复制成功、批量条计数）。
- 状态不单靠颜色：徽标必须含文字。

## 8. 与现状兼容点（实施期硬边界）

- indigo 主色延续；URL、参数协议、双字段 checkbox、save/save_close、htmlcheck 门禁、filter_help 单一来源、markdown 消毒链全部不变。
- `_COMMON_CSS/JS` 合成与 `ensure_common_assets` 机制保留；报表页 JS 双轨废除（C16 去向），hash 需覆盖 CSS+JS。
- 导航从 `_NAV_ITEMS` 顶栏改为 `_NAV_GROUPS` 侧栏，仍是**单一来源一处改**。
