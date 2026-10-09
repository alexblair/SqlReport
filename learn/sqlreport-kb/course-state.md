# 课程状态 · SqlReport 代码知识库

- slug: `sqlreport-kb`
- 模式: document（源 = 仓库代码 + AGENTS.md + README-CN + 4 个 explore 报告）
- 目标能力: compose 代理能独立定位功能/UI/逻辑入口，按共享语义改代码而不重造轮子
- 状态更新: 章节边界维护

## 课程地图

| # | 章节 | 产物 | 状态 |
|---|------|------|------|
| 0 | 索引初始化 | `codegraph init` → `.codegraph/`（2026-10-06 实测 137 files / 6894 nodes / 17453 edges） | 完成 |
| 1 | 架构与配置 | `01-architecture.md` | 完成 |
| 2 | 路由与鉴权 | `02-routing-auth.md` | 完成（explore-1 增补） |
| 3 | 报表与变换 | `03-report-transform.md` | 完成（explore-3 增补） |
| 4 | 配置数据层 | `04-config-data.md` | 完成（explore-2 增补） |
| 5 | API | `05-api.md` | 完成（explore-1 增补） |
| 6 | UI 交互 | `06-ui-interactions.md` | 完成（ui-redesign T9 重写 + R2-D：API 列表 api-row 卡片/详情五页签对齐 page-detail——qf-row 快筛、结果集 segment、分页恒显、规则双卡、调试磁贴、备注卡片；**emoji→SVG 图标系统（_icon 函数）、CSS 按钮类补齐、侧栏 button→a 语义修复**；**2026-09-29 侧栏三态收缩（全高手柄+localStorage 记忆+小屏自适应）与当前登录用户名注入**；**R3 侧栏账号区吸底/两行修复 + 报表配置页列表/卡片双视图与列宽预算、截图数值断言校验法（易踩坑 #14–15）**） |
| 7 | 缓存调度审计 | `07-cache-scheduler-audit.md` | 完成（2026-09-29 补 L1 派生态缓存与导出并入缓存链路的说明） |
| 8 | 测试与坑 | `08-testing-conventions.md` | 完成（已同步范围递进/分段全量/路径可移植/两败找根因；2026-09-29 从 AGENTS.md 迁入两败必停全文 + L2 分段命令表 + `-t .` 陷阱 + 性能工具链） |
| 9 | 代理工作流 | `09-agent-workflow.md` | 完成（2026-09-29 新建：多代理协作纪律 #13–#15 + 执行效率取证纪律 P1–P7；**2026-09-30 新增「代码检索纪律 #18/#19」——codegraph 优先检索、查不到才降级 grep、改完必 sync**） |
| 10 | Token 预算 | `10-token-budget.md` | 完成（**2026-10-06 新建**：把 4 个历史会话的真实 `usage` 复盘成可执行纪律——成本 ≈ 步数 × 上下文、98.6% 为历史重发；返回体积阈值/批处理/会话分段交接 = 硬性 #20。配套 `scripts/agent/session_cost.py`（自查工具，含自测）与 `tests/test_doc_budget.py`（文档预算门禁）） |
| 11 | AOCI 使用手册 | `11-aoci-usage.md` | 完成（**2026-10-08 新建**：AOCI 场景矩阵 + 一次任务时间轴 + 九个 MCP 工具 + CLI/面板/Database 卷/失败恢复 = 硬性 #21；根 `AGENTS.md` 同步加路由行与收尾项，并按文档预算把 `aoci:begin` 区块裁剪为最小合同） |

> 第 6 章已于 2026-09-30 随 UI v2「石墨·鸢尾」实施改写（令牌/组件/页面地图口径见 `06-ui-interactions.md` 与 `docs/compose/spec/2026-09-30-ui-v2-design.md`）。

入口：`docs/compose/knowledge/README.md` + `INDEX.md`

**文档结构约定（2026-09-29 起）**：`AGENTS.md` 只保留「每次任务都要读」的最小集
（硬性约束条目 + **§0 入口引导路由表** + 环境命令 + 收尾检查单，当前 160 行）。
凡「只在特定类型任务才需要」的流程全文一律在本库分卷；AGENTS.md §0 路由表登记
「什么时候读哪一卷 / 改完必更新哪一卷」。新增内容时先判断它属于最小集还是分卷。

## 概念掌握表

| 概念 | 状态 | 证据 | 置信度 | 复习点 |
|------|------|------|--------|--------|
| codegraph 索引 | mastered | status up to date | 高 | 每次改完代码 sync（#19） |
| codegraph 优先检索（#18）+ 改完必 sync（#19） | mastered | 09 卷命令表 + sync 端到端实测（改文件→pending 1→sync→新符号可查） | 高 | 出现「先 grep 后 explore」时 |
| ROUTES 首次匹配 + needs_db=False 边界 | mastered | server:244-263 + explore-1 | 高 | 新 URL |
| Session 滑动 + 限流 + next 白名单 | mastered | auth + explore-1 | 高 | 改登录 |
| result_transform 单一语义 | mastered | docstring + 三端调用 | 高 | 改筛选 |
| 写护栏三端 + 静态 json 再拦 | mastered | report/export/api + explore | 高 | 改 allow_write |
| 导出默认 gbk、先截断后筛 | mastered | export + explore-1 | 高 | 改导出 |
| 双引擎迁移三处同步 | mastered | AGENTS + config_db + explore-2 | 高 | 改表 |
| API Key 语义（公开 vs 全禁） | mastered | _validate_api_key | 高 | 改鉴权 |
| CORS 空≠允许 | mastered | explore-1 | 高 | 改跨域 |
| render 单一来源 + 嵌套 form | mastered | explore-4 + htmlcheck | 高 | 新 UI |
| ui-redesign 重构（侧栏/令牌/页签/抽屉/导出对话框/术语表） | mastered | docs/compose/spec/ui-redesign.md + 全量 2844 项对账 | 高 | 改任何页面布局/组件前读 06 卷与 visual-spec |
| UI v2「石墨·鸢尾」实施（2026-09-30） | mastered | spec 2026-09-30-ui-v2-design.md + 06 卷 + 全量 3009 项对账（2026-10-06） | 高 | 改任何页面布局/组件/CSS 前读 06 卷与 ui-v2-design |
| vendor hash = CSS+JS 拼接哈希 | mastered | explore-4 + R2 核对 | 中高 | 改 CSS 或 JS 都会变 |
| L1/L2/L3 + 保活先算后换 | practiced | explore-2 | 中 | 改缓存 |
| scheduler exclusions ≠ nested_filter | mastered | explore-3 | 高 | 改调度 |
| 审计四类 type | mastered | explore-1 | 高 | 改审计 |
| unittest 入口 | mastered | AGENTS | 高 | — |
| 测试范围递进 + 分段全量防超时 + 禁反复全量 | mastered | AGENTS 硬性 #8 + 08 分卷 | 高 | 改测试流程 |
| 测试/脚本对齐最新需求、禁硬编码主目录 | mastered | AGENTS 硬性 #9–#10 + 08 分卷 | 高 | 写测试/脚本/文档 |
| UI 先可交互 HTML 确认、严格按确认稿、全局视觉一致 | mastered | AGENTS 硬性 #11 + 06 分卷 | 高 | 设计稿/UI 优化 |
| 同一问题失败 2 次停手、根因优先再改 | mastered | AGENTS 硬性 #12 + 08 分卷 | 高 | 调试/测试卡住时 |
| L1/L2/L3 + 保活先算后换 | mastered | 07 卷 + spec 2026-09-29 性能设计 §10.1 基线实测 | 高 | 改缓存 |
| `cache_info.source` = 本次取数来源（mysql/process/redis/redis_fallback），`snapshot_written` 仅 mysql 分支 | mastered | spec 2026-10-05 §5.1 + tests/test_cache_source_label.py | 中 | 改取数来源标注/缓存徽标时 |
| 派生态缓存（C-3）挂 CachedResult、零失效逻辑 | mastered | spec §5 C-3 + §10.8 + tests/test_derived_cache.py | 高 | 改 transform 或加缓存层 |
| 导出并入三层缓存（C-4） | mastered | spec §5 C-4 + tests/test_export_cache_path.py | 高 | 改导出 |
| MySQL 连接池：`close()` 语义为归还、read_timeout 进池键 | mastered | 01 卷 + tests/test_mysql_pool.py | 高 | 改 query_executor |
| Decimal 不在 isinstance 快速路径 → DECIMAL 列退化 | mastered | 03 卷 + verify_transform_equivalence 实测 -27% | 高 | 改 result_transform |
| `filter_rows` 单趟化反而更慢（闭包调用开销） | mastered | spec §10.3 实测 +41%~72% | 高 | 想优化 filter 时先看 |
| discover 必须加 `-t .`，否则 tests/__init__.py 不执行 | mastered | 08 卷 + spec §10.7 探针实测 + 金丝雀 test_test_isolation | 高 | 跑全量测试时 |
| 测试进程会连生产 Redis（无隔离时） | mastered | 08 卷易踩坑 #17 + tests/_bootstrap.py | 高 | 写涉及缓存的测试时 |
| 断言「隔离是否生效」的测试不能自己 import tests（自我掩盖） | mastered | 08 卷易踩坑 #18（第一版金丝雀即栽在这） | 高 | 写环境守卫类测试时 |
| 端到端压测噪声约 ±6%，transform 收益须用隔离 A/B | practiced | spec §10.3 | 中 | 做性能对比时 |
| 写判定分工：`sql_contains_write`（从严、权限侧）vs `sql_has_persistent_write`（精确、缓存门槛与静态护栏） | practiced | spec 2026-09-30 §5 | 中 | 动 allow_write / skip_cache_read / 静态护栏时 |
| 静态护栏是**并集**（权限判定 + 持久写判定），不是替换 | practiced | spec 2026-09-30 §3.3 | 高 | 改静态分支条件时 |
| `SELECT … INTO OUTFILE`/`INTO DUMPFILE` 属持久写（读白名单不豁免） | mastered | spec 2026-10-05 §4.1 + `tests/test_sql_persistent_write.py::TestSqlHasPersistentWriteIntoFile` | 高 | 改写判定首关键词/关键词集合时 |
| AOCI 认知层使用纪律（#21） | mastered | 11 卷 + AGENTS 硬性 #21 + 实测（checkpoint / doctor / 面板 `/api/state` / maintain 流程） | 高 | 想「每改一个文件就维护一次」或「改 `.md` 不用维护」时 |

## 复习队列

- 若将来要把「临时表名追踪」纳入判定（会话级 DML 目标为**本脚本内建**的临时表），
  需先补单测再改 spec §5.3 的 YAGNI 结论（当前 34 个真实报表无一需要）。

## 错误日志

- 用户写 `codegrade init`：环境无此 CLI；PyPI `codegrade` 为 CodeGrade 教学平台 API 客户端。实际使用 **`codegraph init`** 完成索引。
- playwright-cli 默认 chrome 渠道 + Linux root：需 `~/.playwright/cli.config.json` 嵌套 schema `{browser:{launchOptions:{channel:"chrome",chromiumSandbox:false}}}`（扁平键会被静默忽略）；Chrome for Testing 用 /tmp/a 离线包解压至 /opt/chrome-offline 并软链 /opt/google/chrome，依赖补 libgbm1。

## 下一步（可选）

1. 改完代码后 `codegraph sync`（硬性 #19，本机无守护进程自动同步）
2. 改共享语义时按 INDEX「共享语义」表全链路搜调用点
3. 探索报告全文已并入各分卷；若需原始长文可回看会话 actor 结果

## 状态块

```text
slug=sqlreport-kb
chapters=0..11 done
kb=<repo>/docs/compose/knowledge/   # 仓库根相对；主目录可变，勿写死绝对路径
index=codegraph ok (137 files, 6894 nodes, 17453 edges, v1.4.0)
sources=code+AGENTS+README+4 explore agents
gaps=none blocking
last_sync=2026-10-09 ② SQL 编辑框缺滚动条修复（用户实测：/config/reports/{id}/edit ② SQL）
           根因：ad109be 把「容器类」.sql-editor{overflow:hidden} 直接挂在 textarea 自身，
           同优先级下后声明的 .sql-textarea 未写 overflow → 计算样式 hidden、滚动条消失；
           无头 Chrome 实测：overflowY=hidden / scrollbarGutter=0 / clientHeight 318 vs scrollHeight 1284
           （同页对照 memo/result_names = auto / 10px）；
           render.py `_COMMON_CSS` 修 2 处（.sql-editor 去 overflow、.sql-textarea 显式 overflow:auto）；
           06 卷新增「编辑框滚动契约」段 + 头部同步计数；
           新门禁 `TestSqlEditorScrollContract`（2 例，test_ui_tokens 总 35 例）；
           gate_redproof 新增第 6 条（9/9 RED-GREEN）；
           取证脚本（仓库内已 gitignore 的 run-logs/ 下自建过程脚本）+ make_focus_shot.py（前后截图）
last_sync=2026-10-06 展开/收起类名契约修复（用户实测：/config/api-endpoints 展开 收起 失效）
           根因：ad109be 只抄确认稿类名（.api-row.open），生产 apiToggleMore 切 .api-more.on；
           同一提交还删了 .tree .kids{display:none}＋.kids.on → 分类树折叠同款失效；
           render.py `_COMMON_CSS` 修 3 行（.api-more.on / .tree .kids / .kids.on）；
           06 卷新增「展开/收起类名契约」段 + 失败模式库 2 条 + 清单第 5/6 条补强；
           MEMORY.md Rules 13/14 修订、新增 Rule 18 与 Discovered 隔离验证实例事实；
           新门禁 `TestRevealClassContracts`（元素级）+ e2e `api-row-expand-check.mjs`；
           gate_redproof 4→5 条；全量 3012 项 OK（74s）、8098 隔离实例浏览器实测 17/17 PASS
last_sync=2026-10-06 文档/知识库时效审计（V2 基线）
           全库对账修正：codegraph 计数 137/6894/17453、AGENTS.md 156 行、INDEX 模块行数、
           03/05 卷行号锚点、08 卷 L2 分段补漏网测试文件 + perf 脚本表 + 实测 3009 项/94s、
           06 卷术语表与嵌套层级内联样式口径、双 README 结构树与 -t .、版本指南 describe 指纹；
           新增易踩坑 #26（run-logs 克隆污染静态分析门禁）
last_sync=2026-10-05 收尾轮（OUTFILE/DUMPFILE 写判定缺口修复 + 全项目遗留收口）
           spec/plan `2026-10-05-outfile-write-detect-*`；03 卷补「读白名单不豁免写文件」；
           reports/2026-10-05-closeout-decisions.md 记录「裁定不做」6 项
last_sync=2026-09-29 执行层性能优化（spec 2026-09-29-execution-layer-performance-design.md）
           同步 01/03/07/08 分卷：连接池、派生态缓存、导出并入缓存、
           transform 性能要点、discover -t . 隔离、性能工具链
last_sync=2026-09-29 AGENTS.md 瘦身重构（395 → 141 行）
           新建 09-agent-workflow.md；01/02/03/04/06/08 迁入对应 AGENTS.md 内容；
           AGENTS.md §0 新增「任务类型 → 先读/改完必更新」入口引导路由表
last_sync=2026-09-30 UI v2 复盘轮（14 类缺陷 + 10 条流程错误 → 机制）
           06 新增「交互改动验收（硬性 #17）+ 失败模式库」与易踩坑 16；
           08 新增易踩坑 20–23（换页态验收 / CDP 脚本自身的坑 / 改代码后重启服务 / 门禁须 RED-GREEN）；
           AGENTS.md 硬性 #17 + 收尾检查单第 6 条；MEMORY.md Rules 12–14；
           新增门禁 3 类 4 例（test_ui_tokens 26→30）与 tests/bug_hunt/gate_redproof.py；
           复盘报告 docs/compose/reports/ui-v2-retrospective.md
last_sync=2026-09-30 codegraph 优先检索纪律（用户硬性要求）
           AGENTS.md 新增硬性 #18（检索/阅读代码强制先走 codegraph，查不到才降级 grep/read）
           与 #19（改完 .py/.js/.mjs 必 codegraph sync）；§0 路由表新增检索行、§4 命令块、收尾清单第 7 条
           09 卷新增「代码检索纪律（#18/#19）」：两条等价通道（MCP/CLI）命令表、查询写法、
          降级白名单、禁止项、同步时机表、本项目 5 条实测坑；同步 INDEX.md §7、knowledge/README.md
last_sync=2026-10-09 执行效率治理（定向复盘最近 2 会话 → 机械拦阻）
          定论：单调用步 76%/73%（律令早有却未触发）、147/149 步超阈 2.5 倍、AOCI maintain 各调 2/3 次重复
          工具：session_cost.py 新增 --check 一行体检、批处理率、AOCI maintain 计数（含 selftest 14 项）
          规则：AGENTS.md #20 增加⑤中途体检⑥收尾批量；10 卷 R2 阈值（单调用步 ≤40%）+ R3 事件触发 + R5 批量
          11 卷：.md 措辞级改动可原样提交；maintain 中间态/重复调用即违规（>1 次仅当 remaining≠0）
```
