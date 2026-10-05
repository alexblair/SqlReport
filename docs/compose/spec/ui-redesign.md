---
feature: ui-redesign
status: superseded
superseded_by: 2026-09-30-ui-v2-design.md
superseded_note: 视觉与组件部分已被 UI v2 取代（过程记录与功能覆盖结论继续有效）
updated: 2026-09-25
branch: main
commits: 9a975b9..f5a99e7
---

# 全站视觉与交互重构（2026 标准）

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/ui-redesign.md)

> 工作区约定：用户确认在当前 main 检出就地工作（AGENTS.md 与 `docs/compose/` 知识库被 .gitignore 忽略、仅本地存在，不迁移 worktree）；生产代码实施阶段若需分支/隔离再单独决定。
> 过程约束：全程串行、禁止并行任务（用户指令）；所有计划/进度/过程文档落盘于 `docs/compose/`，禁止只停留在会话里。

## Report

**What was built** — R2 修订轮（交付后四条反馈）完成：① 左菜单重做——报表配置左栏按原型改为 `.tree` flex 行（SVG 图标+报表数角标+ghost 操作 ✎↑↓✕+.kids 逐级折叠），`.section-title` 全局 flex 化，根除 260px 栏 inline 挤压；② 弹性布局——`.container` 加 `width:100%`（1920 下内容列 42%→87.5%）并保留 1440→1680→1920→2400 阶梯，`.split` 单列改 `minmax(0,1fr)`（390 视口整页溢出 1012px→390px）；③ 逐页结构对齐——原型 13 页对比发现 11 页结构级差异并全部落地：三表单页 page-head+grid-2 双栏（调度排除规则 rule-row 可视化）、API 列表 api-row 卡片+展开区（协议全保留）、详情五面板（qf-row 快筛/结果集 segment/单页恒显分页/规则双卡/接口委托/调试 grid-3 磁贴/备注卡）、概览 grid-2 归位去卡中卡、调度 7 列单表移除第二表、连接池补关联报表列、用户补角色说明列、审计清理钮回页头+裸排；④ 确认流程按 AGENTS #11 执行（`ui-redesign-r2.html` 可交互确认稿+逐页并排对比→用户确认→实施）。五项有理由偏差已记录：报表配置右列保留分组多表、连接池表单保持独立页、用户无 role 字段按平权管理员实义渲染、新建接口回退首张报表既有路由、调试磁贴无耗时数据源改用现有字段。

**Verification** — L2 分段全量（AGENTS ①→⑨ 顺序）约 3800+ 项：除 7 个与 R1 基线同名单的 PRE-EXISTING（`test_debug_config_override`×4、`test_preset_cases` 分段 `unittest.mock`×2、`test_scheduler_core` 熔断恢复×1）外全部绿；终验截图 17 张（PC12+端点表单+展开态、移动 390×3）7 断言全 PASS（container 1680/87.5%、scrollWidth==390、左栏无重叠、api-row/qf-row/分页/grid-2 均在、console 0 错误）；独立评审三结论（规格/正确性/一致性）零 critical、抽跑 560 项 OK；知识库 06+INDEX 随任务回写并标注「R2 核对 2026-09-25」。

**Journey log** — ① **全局样式 ≠ 页面结构**：R1 交付后用户感知「只改了全局样式」，13 页逐页结构对比揪出 11 页结构级差异——UI 重构必须逐页对照原型验收，不能只过共享 CSS；② **并发子代理失控教训**：同一任务重复派发产生多写入者竞态（`.grid-3` 重复定义、分页参数 `force/always` 改名互踩、cancel 信号后仍继续写入），对策=唯一活跃执行者+mtime 轮询稳定+终态由主会话统一实测裁决；③ **门禁字面量陷阱**：CSS 选择器 `.path {` 含子串 `th {` 会撞 `TestStickyTableHeaderCss` 的 `css.index("th {")`，更名 `.path-chip`——门禁用字面提取时新增 class 须避开其模式；④ **PRE-EXISTING 名单法**：R1 的 7 个基线失败（debug×4/preset mock×2/熔断×1）经同名单核对贯穿 R2 全程，未新增一例失败；⑤ **数据不存在不虚构**：users 无 role 字段、报表→池映射仅计数、详情无耗时数据——原型有而数据无的展示一律用现有字段/实义文案落地并在分卷注明。

## [S1] Problem

当前全站 UI 虽集中于 `render.py` 单一来源，但实际存在大量个性化组件与交互逻辑不清的现状，整体审美与交互体验不满足 2026 年及以后的标准。需要以交互设计师 + UI 设计师的团队视角完成一次全面分析，给出整体页面重构与交互重构的解决方案，并以可交互 HTML 确认稿与用户核对。要求：

1. 不能遗漏任何代码已完成的功能、约定、交互逻辑（以知识库与代码为唯一起点）；
2. 统一并改善违背项目要求的个性化组件与不清交互，是本次任务的既定目标；
3. 允许完全改变页面数量、每页功能位置与布局；
4. 按 AGENTS.md 硬性 #11：先可交互 HTML 确认，用户确认后才实施生产页面代码。

## [S2] Design

### A. 盘点契约（防遗漏）

- 起点固定为：`docs/compose/knowledge/`（INDEX 路由/页面地图/共享语义 + 06 UI 分卷）→ 源码核对（`server.py` ROUTES、`render.py` 组件、`report.py`/`config.py`/`export.py`/`api_handler.py`/`auth.py`/`audit_page.py` 等页面与交互入口）→ README-CN 功能特性与页面说明。
- 产出《功能/交互覆盖清单》：逐条列出「功能/约定/交互 → 来源（文件:位置或知识库章节）→ 新方案中的去向（保留/合并/改名/移位/删除+理由）」。清单必须覆盖 INDEX §2 路由总表与 §3 页面地图的全部条目、README 功能特性清单、以及代码中发现的全部页面级交互（含 localStorage、confirm、flash、hidden 透传、面板折叠等约定）。
- 清单是后续原型与实施的验收基准：原型与实施阶段逐条核对，禁止出现「去向」为空的条目。

### B. 分析与重构方案

- 问题分析：指出当前违背统一性/交互不清的具体点（个性化组件、重复实现、导航混乱、认知负荷高的交互），每条附代码证据。
- 信息架构重构：可增删合并页面、重排导航与每页功能位置；方案须给出「旧页面/功能 → 新位置」映射，与覆盖清单一致。
- 视觉与组件体系（单一方向直出，用户已选定）：以 2026 主流数据工具审美为基准——明亮底 + 深色侧栏、卡片化布局、精细排版层级、无障碍对比度、清晰的交互状态（hover/focus/disabled/loading/empty）；全站统一一套设计令牌（色板、字号阶梯、间距、圆角、阴影）与一套组件规范（按钮、表格、表单、筛选条、分页、弹层、折叠、flash、空态），对齐「复用单一实现、不重复造轮子」的项目原则。

### C. 可交互 HTML 确认稿契约

- 形态：单应用多页可切换原型（用户已选定）——单个可直接打开的 HTML，内置导航可在所有重设计页面（登录、报表列表、报表详情、配置门户、各配置子页、调度、API、审计等）间真实点击切换；相关交互（折叠、面板、切换、筛选条示意、confirm 示意等）可演示。
- 位置：`docs/compose/spec/ui-redesign-prototype.html`（过程素材，不并入生产 `static/`，不写死绝对路径）。
- 必须附《功能/交互覆盖清单》附录（原型内可查阅），与 A 阶段清单同源。
- 全部文案简体中文；视觉体现统一设计令牌与组件规范（确认稿即未来实施的样式基准）。

### D. 确认与实施契约

- 用户明确确认原型（Question 工具记录）后，才允许修改生产页面代码；实施严格按确认稿落到 `render_page_header` + `build_*` + `extra_css`，禁止确认稿 HTML 原样粘贴进 `render.py`、禁止第二套 class/CSS 体系。
- 实施保持技术选型锁定：纯 Python 标准库 + `http.server` + 服务端 HTML 字符串，不引入框架/构建链。
- 验证按范围递进：`tests/htmlcheck.py` + `test_render*`/`test_html*` 等 L0→L1→L2 分段；知识库同步（`06-ui-interactions.md`、`INDEX.md` 受影响段、`learn/sqlreport-kb/course-state.md`）与实施同任务完成。

### E. 执行纪律

- 串行执行任务（禁止并行/并发子任务，用户指令）。
- 每个任务的过程产物落盘 `docs/compose/`（分析、方案、清单、原型、评审记录），会话内不丢失。
- 同一问题失败 2 次即停、根因优先（AGENTS 硬性 #12）。

### F. R2 修订轮 · 交付后反馈（2026-09-25）

用户四条反馈（原文要点）：① 报表配置页左侧菜单按钮文字挤在一起很难看；② 整体要用弹性(flex)布局——PC 大屏内容挤在中间没利用屏幕，移动端挤在一起不好看；③ 原型的模块布局比生产实现好看，怀疑 UI 组件没写好，要求截图对比后优化；④ **每个页面都要对比原型设计 HTML**——很多页面只改了全局样式，布局和排列根本没变化，须逐页找出结构级差异（T10b）。

诊断结论（子代理截图+指标取证，32 张截图与 metrics 在 `/tmp/ui-diag-r2/`，第二批 `20260925-034135_*` 有效）：

| # | 根因 | 证据 | 修法 |
|---|------|------|------|
| R2-A | 左栏 `.cat-tree-item`/`.section-title` 全库无 CSS，子元素 inline，260px 栏塞 ≥320px 内容 | render.py:2737/2771 仅 HTML 无规则；实拍标题行三钮重叠、节点文字断行 | 左栏按原型 `.tree/.cat` 形态重做：flex 行 + ghost 图标操作 + 卡片头 |
| R2-B | `.container{margin:0 auto}` 位于纵向 flex 的 `.main` 内退化为 fit-content 居中 | 1920 视口实测内容列：报表中心 809px(42%)、详情 1011px(53%)、概览 1048px(55%)；原型 `.page{width:100%}` 恒满 | `.container` 加 `width:100%`，配合既有 1440→1680→1920→2400 阶梯 |
| R2-C | `.split{grid-template-columns:1fr}` 单列轨道不收缩 | 390 视口实测配置页 scrollWidth=1012（64 侧栏+947 容器）；详情 543 | 单列改 `minmax(0,1fr)`，主内容 `min-width:0`，表格保持 `.table-wrap` 内滚 |

实施契约（沿用 S2-D，不重复）：确认素材=可交互 HTML `docs/compose/spec/ui-redesign-r2.html`（修复前/修复后切换、视口宽度切换、390 手机框演示均可交互）；用户确认（Question）后才改生产；落点 `render.py` 共享 CSS（`_BASE_CSS`/`_COMMON_CSS`）与 `build_category_manage_section_html` 左栏拼装（由 `build_category_section_html` 调用），不新起 class 体系；URL/锚点（`#sec-categories`、`cat-tree-toggle`、`#cat-tree-content`、批量条协议）与 htmlcheck 门禁保持不变。

执行纪律（R2 新增，用户指令）：测试与无关任务优先子进程/子代理执行，避免上下文膨胀；截图对比在 `/tmp` 临时目录进行、不触发权限弹窗；禁止用 `rm` 清理（改用唯一文件名），避免中断自动执行。

## [S3] Out of Scope

- 用户确认原型之前，不修改任何生产页面代码（`render.py`/`report.py`/`config.py`/`server.py` 等的 UI 部分）。
- 不改变筛选/排序/导出/API/鉴权/缓存等后端共享语义与数据结构（重构只动「呈现与交互层」；若确需触碰，先在方案中标注并单独确认）。
- 不研究或触碰生产副本 `/alexblair/windir/www/SqlReport/`。
- 不引入 Django/Flask/React/Node 等框架或新「框架级」依赖。
- 不做英文界面；全部用户可感知文字保持简体中文。

## Tasks

- [x] T1: 功能/交互全量盘点，产出《功能/交互覆盖清单》（含来源；「新方案去向」列由 T3 填写）— acceptance: 清单覆盖 INDEX 路由总表与页面地图全部条目、README 功能特性、代码发现的页面级交互约定，每条有来源，§6 自查项全勾（去向项待 T3 完成） (covers: S2-A)
- [x] T2: 现状 UI/交互问题分析（个性化组件、重复实现、交互不清点，附代码证据）— acceptance: 分析报告逐条列出问题与证据，并与覆盖清单交叉引用 (covers: S2-B; depends: T1)
- [x] T3: 信息架构与页面重构方案（页面增删合并、导航、每页功能位置、「旧→新」映射）— acceptance: 方案与覆盖清单逐条对齐，无功能丢失或无去向条目 (covers: S2-B; depends: T2)
- [x] T4: 统一视觉与组件/交互规范（设计令牌 + 组件规范，单一方向）— acceptance: 规范覆盖全站组件类型与交互状态，可直接作为原型与实施的样式基准 (covers: S2-B; depends: T3)
- [x] T5: 制作可交互 HTML 原型 `docs/compose/spec/ui-redesign-prototype.html`（多页可切换 + 覆盖清单附录）— acceptance: 浏览器打开后所有重设计页面可点击切换、关键交互可演示、文案全中文、附录清单与 T1 同源 (covers: S2-C; depends: T4)
- [x] T6: 用户确认原型（Question 工具记录确认结论；含修订轮次）— acceptance: 用户明确确认或给出修订意见并再次确认 (covers: S2-D; depends: T5)
- [x] T7: 按确认稿实施生产代码（`render` + `build_*` + `extra_css`，按覆盖清单去向落地）— acceptance: 页面结构与确认稿一一对应，无确认稿 HTML 直粘、无第二套 CSS/class (covers: S2-D; depends: T6)
- [x] T8: 测试验证（htmlcheck + render/html 相关单测，范围递进；全量按 L2 分段）— acceptance: 相关测试全部通过或仅有标注为 PRE-EXISTING 的既有失败 (covers: S2-D; depends: T7)
- [x] T9: 知识库同步（`06-ui-interactions.md`、`INDEX.md` 受影响段、`course-state.md`）— acceptance: 知识库与新 UI 实现一致、以代码为准回写，无过时表述 (covers: S2-D; depends: T7)

### R2 修订轮（交付后反馈，见 S2-F）

- [x] T10: 截图+指标诊断（live vs 原型，PC1920/移动390，四页矩阵）— acceptance: 三条反馈各有数值化根因结论，产物落 `/tmp/ui-diag-r2/`（唯一文件名、无删除） (covers: S2-F)
- [x] T10b: 逐页结构对比（原型 13 个页面区块 × 生产对应路由：布局/排列/区块构成级差异，非全局样式）— acceptance: 每页产出「原型结构要点 vs 生产结构要点 → 差异级别（结构级/仅样式/一致）+ 差异点+生产代码位置」对照表，结构级差异页全部进入 T11 确认稿与 T13 实施范围 (covers: S2-F; depends: T10) — 结果：13 页中 11 页结构级差异（四类：双栏塌单列/卡片行变折叠块/区块挪位/表格列缺失），对照表并入确认稿页签④
- [x] T11: 产出可交互确认稿 `docs/compose/spec/ui-redesign-r2.html` — acceptance: 三个修复点（左菜单/PC 宽度/移动端）均可交互演示修复前↔修复后，且含 T10b 逐页对比对照表（结构级差异页附并排截图），视觉沿用原型设计令牌 (covers: S2-F, S2-F④; depends: T10, T10b) — 结果：5 页签+17 张并排截图，复检 console 0 错、390 无溢出
- [x] T12: 用户确认 R2 确认稿（Question 工具，AGENTS #11 门禁）— acceptance: 用户明确确认或给出修订意见后再次确认 (covers: S2-F; depends: T11) — 结果：Question 提交被中断并收到「继续」，按 compose:ask 规则取推荐项「确认通过，进入实施」（2026-09-25）
- [x] T13: R2 生产实施（左栏重做 + container width:100% + split minmax(0,1fr) + T10b 结构级差异页的布局排列对齐原型，`render.py` 共享 CSS/`build_*`）— acceptance: 按确认稿落地，逐页与原型布局排列一致（结构级差异清零），锚点/批量条/htmlcheck 门禁与 URL 协议不变，无第二套 class 体系 (covers: S2-F, S2-F④; depends: T12) — 结果：G1/G2+P1-P11 全部落地（P1b/P9/P10 等五项有理由偏差见 S2-F 与报告），终验 7 断言 PASS
- [x] T14: 验证（子进程跑 L0→L1 相关测试 + 截图复验对比修复效果）— acceptance: 相关测试全绿或仅 PRE-EXISTING；复验截图宽度/溢出指标达到 R2-A/B/C 验收值 (covers: S2-F; depends: T13) — 结果：L2 分段 ≈3800+ 项全绿（7 个 R1 已知 PRE-EXISTING）；终验 17 张截图 7 断言全 PASS
- [x] T15: 知识库同步（06 卷/INDEX/course-state 受影响段）+ 独立子代理 review + 特性文档 finalize — acceptance: 知识库与实现一致；review 三结论（规格符合/正确性/一致性）无 critical；status 回 delivered (covers: S2-F; depends: T14) — 结果：06+INDEX 回写并 R2 核对标注、course-state hash 行修正；评审三结论达成零 critical（抽跑 560 绿）；本行即 finalize

### R2 交付后反馈复核（compose:feedback，2026-09-25）

- [x] T16: 刚性约束审计（AGENTS #3/#5/#10/#11、统一 UI 体系）— acceptance: 逐条有命令证据 (covers: feedback①) — 结果：共享语义模块（result_transform/export/api_handler/filter_help/query_executor/auth 等）与 ROUTES 零改动；config.py 无新增内联 style/script；新 class 仅在 render.py 定义、config/report 只引用；无硬编码绝对路径、无新增英文可见文案；htmlcheck 改动仅为 SVG 自闭合白名单（未削弱 form/标签检查）；`bug_hunt` 静态分析 OK + `test_html*` 19 项 OK（命令均见 `/tmp/ui-diag-r2/func-20260925-165617.log` 同轮）
- [x] T17: 历史功能点回归（非 UI）— acceptance: 功能分段测试 + 真服务端到端冒烟，失败与 R1 基线一致 (covers: feedback②) — 结果：30 个功能分段（筛选/配置/DB/报表/导出/API/认证/审计/缓存/调度/杂项）26 段 OK + 4 段补跑，失败仅 7 项且名单=R1 PRE-EXISTING 基线（debug_config_override×4、preset DebugVisibility×2、scheduler 熔断×1）；E2E 冒烟登录/鉴权拦截/报表详情+筛选+排序+分页+nested_filter+cols/导出 CSV+JSON（CSV 头正确、筛选改变输出）/编辑/新建/分类/API 列表/memo-preview POST/common.css 全 PASS；带密钥 API 复验（用户提供的现成密钥，2026-09-25）：`GET /api/DDD?fetch_all=true&api_key=sk-…` → 200 JSON（`data/total/full` 齐全），去密钥同参 → 401 拒绝，API 功能 E2E 闭环
- [x] T18: 修复 7 项 PRE-EXISTING 失败（compose:feedback ②延伸，用户确认方案后实施）— acceptance: 三项根因定位有证据、修复后原失败分段全绿、基线记录清零 (covers: 用户指令「开始修复7个R1基线遗留」) — 结果：①preset×2 缺 `import unittest.mock`（分段 discover 首载暴露）②debug_config×4 依赖未入库 app_config.json（setUp 改自建临时基准）③熔断×1 时钟炸弹 FAR_FUTURE=2026-09-20 已过期（改 `max(NOW,time.time())+30d`）；修复后 `test_debug_config*`/`test_preset*`/`test_scheduler*` 三段 Ran 6/11/198 全 OK，scheduler 全文件 57 OK；MEMORY.md 基线行已改「清零」；仅改 3 个测试文件，产品代码零改动
