# Token 预算纪律（硬性 #20）设计

> 状态: 生效
> 取代关系: 本设计取代 `2026-09-28-docs-spec-plan-conventions-design.md` 的「`AGENTS.md` 保持 git 忽略不入库」条款（2026-10-06 用户指示）；其余与 #14/#15/#16/#18/#19 并存互补，不取代别的文件。
> 对应 plan: ../plan/2026-10-06-token-budget-plan.md
> 证据报告: ../reports/2026-10-06-token-efficiency-retrospective.md

## 1 开工查证（AGENTS.md §3）

2026-10-06 按 `ls -t docs/compose/spec/*.md` 取最新 4 份，逐份读状态头：

| spec | 状态 | 是否涉及本主题 |
|------|------|----------------|
| `cache-write-test-scenarios.md` | 历史文档（无状态头，标注「may not reflect current implementation」） | 否 |
| `2026-09-30-ui-v2-design.md` | 生效 | 否（UI 视觉体系） |
| `2026-09-29-execution-layer-performance-design.md` | 生效 | 否（服务端执行层性能，非代理流程） |
| `2026-09-30-write-report-cache-gate-design.md` | 生效 | 否（写报表缓存门槛） |

**裁决结论**：无既有生效 spec 规定「代理流程的 token 预算 / 返回体积 / 会话分段」，
因而本设计新增硬性 #20；同日用户指示取消 `AGENTS.md` 的 git 忽略，故本设计取代 `2026-09-28-docs-spec-plan-conventions-design.md` 的那一条款。与知识库 `09-agent-workflow.md` 的 P1–P7 是
**互补**关系（详见 §5）。

## 2 问题（实测，非推测）

4 个历史会话的真实 `usage` 复盘：440 步 / **69,666,456 tokens**，其中
cacheRead 98.56%、output 仅 **0.58%** → 成本 ≈ 步数 × 上下文规模；
单条大返回会被后续每一步重发一次（最贵一步的重发成本 2.33M tokens = 该会话 9.7%）。
完整账本与逐条证据见报告，不在此复述。

**缺口**：既有纪律只约束「查询轮次」（#16 P5）与「重复执行」（#14/#15），
**没有**约束「单条返回体积」「一步发几个调用」「会话能跑多长」「大文件编辑的回显成本」。

## 3 设计（规则本体在分卷，此处只记决策）

新增 `docs/compose/knowledge/10-token-budget.md`，含 R1–R5：

| 编号 | 规则 | 可核对手段 |
|------|------|-----------|
| R1 | 单条工具返回 >8k 字符即超阈：先 `grep -c` 计数、`head` 截断、`read offset/limit` | `session_cost.py` 列出超阈步 |
| R2 | 互不依赖的调用同步发（一步 2–4 个） | `session_cost.py` 的批处理分布 |
| R3 | >60 步或上下文 >120k tokens → 落盘交接（`run-logs/handoff/`）换新会话 | 工具的步数/上下文体检 |
| R4 | `write`/`edit` 回显全文 → 大文件改动置会话后段、批量完成 | 工具的「最贵步」清单 |
| R5 | 收尾自查 `session_cost.py --last 1`，数字进简报 | AGENTS.md §5 第 8 条 |

配套两件可执行资产：
- `scripts/agent/session_cost.py`（工具，含 `--selftest` 纯内存自测）——让复盘成本本身变低；
- `tests/test_doc_budget.py`（门禁）——把「每步都注入的文档」增长变成机械可拦的失败。

## 4 阈值依据

| 阈值 | 取值 | 依据 |
|------|------|------|
| 单步新增 | 8,000 tokens | 实测「大返回步」在 10k–24k；8k 约等于一次 `read` 200 行的量级，作为「该收窄了」的报警线 |
| 会话步数 | 60 步 | 4 个会话 94–147 步、平均 195k tokens/步；60 步配 120k 上下文约在 700 万 tokens 量级，还留得住精度 |
| 上下文 | 120,000 tokens | 超过后每步都在为历史付全价；实测会话 2 末段 300k 时单步 302k tokens |
| `AGENTS.md` | 18,000 字节 | 每步注入；改前 15,612、本次加 #20 后 16,720，留 ~1.3KB 余量。**超限的处理是「把细节移进分卷」，不是抬上限** |
| `MEMORY.md` | 26,000 字节 | 每轮开工必读；当前 ~20.6KB |
| 单个分卷 | 48,000 字节 | 按需读；当前最大 `06-ui-interactions.md` 39,988 |

## 5 边界（不做什么）

- **不改 harness、不引入依赖**：不碰工具 schema（29.6k 字符/步，非本仓库可控），不新增 pip 包。
- **不削弱既有纪律**：#18 codegraph 优先、#16 P2 落盘取数、#14 测试段上限 2 次、#15 子代理预算
  全部原样保留；R1 与 P5「研究预算」独立计数、同时适用（一个是「几次查询」，一个是「一次多大」）。
- **不追求「让模型少说话」**：output 只占 0.58%，压 output 收益可忽略，反而增加返工风险。

## 6 验收

- [x] 门禁 `tests/test_doc_budget.py` 6 用例全绿；并纳入 `tests/bug_hunt/gate_redproof.py`，
      **8/8 条门禁通过 RED-GREEN 自证**（含新增 3 条：AGENTS.md 超预算 / 路由断链 / 孤儿卷）
- [x] 工具 `scripts/agent/session_cost.py --selftest` 10 项断言通过，且能复现本报告全部数字
- [x] 四处索引同步：`AGENTS.md`（#20 + §0 路由表 + §2 分卷表 + §5 检查单）、`knowledge/README.md`、
      `knowledge/INDEX.md`、`learn/sqlreport-kb/course-state.md`
- [x] `MEMORY.md` 记入 Rules #19 与「DSH 会话记录可直接读」环境事实
