> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

> 状态: 生效
> 取代关系: 本设计**修订** `2026-10-06-token-budget-design.md` 的「文档预算」口径（限额下调 + 新增分卷总量与 `#N` 断链门禁）；其余部分（Token 经济学结论、R1–R5 纪律）不变。
> 对应 plan: ../plan/2026-10-09-context-slimming-and-aoci-usage-plan.md
> 依据: 2026-10-09 AOCI 只读性能评估（结论：机制健康但"只写不读"）与全仓体积盘点，数字见 plan §执行记录。

## 1 目标与非目标

**目标**
1. 以**最小改造与执行成本**让 AOCI 真正被用起来，并与 `codegraph` 划清场景边界（不重复、不对立）。
2. 对常读文档做力度 A 瘦身：去掉"旧 AI 能力弱"时代的保姆式细则与重复内容，纪律改由机制（门禁/脚本/工具）承担，保留全部"没有帮助就会做错"的项目特有约束。

**非目标**：不改任何生产代码语义；不重编号硬性约束；不引入新依赖；不动 `tests/` 的既有断言语义。

## 2 AOCI 使用面设计

### 2.1 三层边界（各管一段）

| 层 | 工具 | 回答 | 单次成本 | 触发时机 |
|----|------|------|---------|---------|
| 语义层 | AOCI **定向读**（`scripts/agent/aoci_precheck.py`，等价 MCP `aoci_get_entries`） | 这个对象**为什么存在、有什么非显然约束/踩过的坑** | ~1K tokens（只取目标文件条目） | **改前一次**，仅覆盖本次要改的文件 |
| 符号层 | `codegraph`（硬性 #18 不变） | 符号在哪、谁调用、**波及哪些文件与测试** | 中 | 定位与影响面 |
| 流程层 | `docs/compose/knowledge/` 分卷（§0 路由表） | 流程、约定、验收方式 | 中 | 按路由表读 1 卷 |

**边界一句话**：AOCI 回答"改它要小心什么"，codegraph 回答"改它还会碰到谁"；**不用 AOCI 找符号，不用 codegraph 找约束**。

### 2.2 四项改造（最小成本）

1. **读路径命令化**：新增 `scripts/agent/aoci_precheck.py <路径...> [--json]`，直接解析 `aoci.code.txt`（不产生 MCP 往返、无 schema 税），输出每个路径的 `[标签] F/S`；无条目输出 `NO-ENTRY`。
2. **不重复付合同钱**：`aoci_rules` 仅在 AGENTS.md 最小块失效或上下文压缩后调用；`aoci_overview` 仅在压缩恢复需要全貌时调用（默认改前走定向读，禁止日常拉 17K 全量）。
3. **砍仪式**：`scope status/acknowledge` 仅在 `aoci check` 报 `scope_change_required` 时执行；`aoci verify`+`check`+`index agent guide` 合并为**一条**收尾命令；`maintain` 前先看 `check --json` 的 `executable_targets`，为 0 则不调用。
4. **可验收出口**：`session_cost.py` 输出 "AOCI 读次数（precheck/search/get_entries/overview）vs maintain 次数"；收尾简报固定一行「改前查了 N 个文件，命中约束：…」。

## 3 瘦身设计（力度 A）

### 3.1 四条原则
① 只留"没有帮助就会做错"；② 纪律交给机制（门禁/脚本/工具），不靠文档自觉；③ 同一事实只留一处（AGENTS.md 只写结论 + 指路）；④ 历史账本移出常读文档。

### 3.2 硬性约束 21 → 14（保留编号、退役 7 条，**不做全仓重编号**）

实测全仓 `#N` 引用 423 处 / 37 个文件，重编号成本高、风险大，故保留编号并允许空洞，新增"编号断链"门禁代替。

| 处置 | 条目 |
|------|------|
| 退役并入 | #4 → #3；#9 → #8；#11 → #17；#16 的等待协议 → #20、纠正即入库 → #7 |
| 退役移入分卷 | #10 → 08 卷；#13、#15 → 09 卷（DSH 已有 Agent Teams / 共享任务 / 后台作业，只留 3 行） |
| 保留并压缩 | #1 #2 #3 #5 #6 #7 #8 #12 #14 #17 #18 #19 #20 #21 |

### 3.3 体积目标与门禁

| 对象 | 现 | 目标 |
|------|----|------|
| `AGENTS.md`（每步注入） | 17.9 KB | ≤11 KB |
| `MEMORY.md`（每轮必读） | 25.7 KB | ≤13 KB |
| `06-ui-interactions.md` | 42.1 KB | ≤16 KB |
| `08-testing-conventions.md` | 30.6 KB | ≤13 KB |
| `09-agent-workflow.md` | 22.7 KB | ≤8 KB |
| `10-token-budget.md` | 12.6 KB | ≤6 KB |
| `11-aoci-usage.md` | 18.0 KB | ≤7 KB |
| `INDEX.md` / `01` / `03` / `README.md` | 41.8 KB | ≤32 KB |
| `learn/sqlreport-kb/course-state.md` | 14.9 KB | ≤8 KB |
| **知识库目录合计** | **246 KB** | **≤155 KB** |

`tests/test_doc_budget.py` 限额下调为 `11000 / 13000 / 22000`，新增 `LIMIT_VOLUMES_TOTAL=155000`、`LIMIT_COURSE_STATE=8000`，并新增两类检查：**分卷总量**与**`#N` 引用断链**（引用号必须属于存活集合或已退役集合，退役集合显式登记）。

### 3.4 内容归位规则（实施判据）
- **MEMORY.md**：只留①用户直接纠正②不可从代码/约束推断的环境事实；已沉淀为硬性约束或分卷的复盘结论一律删除并改为指路。
- **分卷**：代码事实（页面地图、组件清单、函数清单）指向 `render.py`/`INDEX.md`；历史实测账本压成结论行；与硬性约束重复的正文删除，只留"怎么做"。
- **不得删**：项目特有红线（禁碰生产副本、venv 隔离、`-t .`、两败必停、临时产物策略、交互验收、codegraph 纪律、AOCI 纪律）。

## 4 验收判据

1. `python -m unittest tests.test_doc_budget tests.test_aoci_precheck -v` 全绿，新限额生效。
2. `python -m unittest discover -s tests/ -t . -v` 收尾一次通过。
3. 全仓 `#N` 引用 0 断链（门禁抓）；被删章节的外部引用 grep 为 0。
4. `codegraph sync` 后 `codegraph status` 的 `pendingChanges` 全 0。
5. AOCI 最终稳定态一次 `maintain` → 整批 `update_entry` → `check` 收敛。
6. 简报给出逐文件体积对比、命令与结果、`aoci_precheck.py` 实跑样例。

## 5 风险与缓解

| 风险 | 缓解 |
|------|------|
| 删到"会做错"的内容 | §3.4 判据 + 逐条保留清单 + 用户复核 spec |
| 约束编号引用断链 | 新门禁机械抓 + 退役号显式登记 |
| 分卷锚点/路由断链 | 既有 `test_doc_budget` 的 ROUTE/ORPHAN 检查兜底 |
| AOCI 条目语义随文档变化过期 | 收尾一次 maintain 整批更新（不改流程） |
