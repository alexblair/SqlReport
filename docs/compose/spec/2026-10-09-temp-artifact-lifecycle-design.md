> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# 临时产物生命周期与「依据分层」设计

> 状态: 生效
> 取代关系: 本设计**修订** `AGENTS.md` 硬性 #14 与分卷 `09-agent-workflow.md` §验证纪律中「产物一律落 `run-logs/`/`perf-logs/`、**禁止 `rm`**」的表述（改为「收尾由统一工具清理」）；**取代** `2026-09-29-execution-layer-performance-design.md` 中以 `perf-logs/baseline-*.json` 充当「原始数据依据」的取证方式（改为报告内「结论 + 数值 + 复现命令」）。与硬性 #17/#20/#21 并存互补，不取代 `2026-10-06-token-budget-design.md` 的令牌纪律（本设计只是把清理挂到它的收尾批量命令上）。
> 对应 plan: ../plan/2026-10-09-temp-artifact-lifecycle-plan.md
> 现场盘点: 2026-10-09，数字与命令见 §2，非推测。

## 1 开工查证（AGENTS.md §3）

按 `ls -t docs/compose/spec/*.md` 取最新 6 份逐份读状态头：

| spec | 状态 | 是否涉及本主题 |
|------|------|----------------|
| `2026-10-06-token-budget-design.md` | 生效 | **是（互补）**：其 R5「收尾取证一次批量发」是本设计清理动作的挂载点 |
| `2026-09-30-ui-v2-design.md` | 生效 | 否（视觉体系） |
| `2026-09-29-execution-layer-performance-design.md` | 生效 | **是（部分被取代）**：其「原始数据：`perf-logs/baseline-*.json`」取证方式已产生断层 |
| `2026-09-28-docs-spec-plan-conventions-design.md` | 生效 | 部分（本 spec/plan 沿用其格式与路径约定） |
| `cache-write-test-scenarios.md` | 历史稿（无状态头） | 否 |
| `ui-redesign.md` | 历史过程稿 | 否 |

**裁决结论**：既有 spec 均未规定「临时产物的清理时机」「依据类内容的归属」。硬性 #14 只规定「产物落 gitignore 目录 + 禁止 `rm`」，**与本次需求直接冲突**——因此本设计修订 #14 条款本体，而不是新增一条与其并存的补充条款。`2026-09-29-execution-layer-performance-design.md` 的原始数据引用方式按「取代两头改」同步改其状态头。

## 2 问题（实测，非推测）

### 2.1 堆积（2026-10-09 现场）

| 目录 | 文件数 | 体积 | 内容 |
|------|--------|------|------|
| `run-logs/` | 110 | **170MB** | `chrome-profile*`、`probe/`、`cp-*/`（浏览器 profile）、`aoci/extract/`（AOCI 解压副本，≈24MB）、若干 `*.log/*.html/*.json/*.py` |
| `perf-logs/` | 0 | 16K（空目录） | 已被清过 |

### 2.2 断层**已经发生**（被文档引用、但文件已丢失）

> 本表所有产物名均为掩码形态——精确名字保留在本 spec 首个提交 `5455c0e` 的历史里，不在正文钉住会消失的文件。

| 文档引用位置 | 引用的临时产物 | 现状 |
|---|---|---|
| `spec/2026-09-29-execution-layer-performance-design.md:295` | `perf-logs/baseline-<id>.json`（自称「原始数据」） | **已丢失** |
| `knowledge/08-testing-conventions.md:327` | `run-logs/repro_*.py`（作为样例脚本） | 仍在，但按本设计必被清 |
| `plan/2026-10-05-cache-source-label-plan.md:610` | `run-logs/sdd/<任务>/progress.md`（执行账本） | **已丢失** |
| `plan/2026-10-05-cache-source-label-plan.md:586` | `run-logs/accept-8099-*.html`、`accept-8099-page*.py`（验收证据） | **已丢失** |
| `plan/2026-10-05-cache-source-label-plan.md:562` | `run-logs/final-discover-<时间戳>.log`（全量测试证据） | **已丢失** |
| `knowledge/10-token-budget.md:124` / `MEMORY.md:105` | `run-logs/handoff/`（跨会话交接文档；该址已废止，§7 第 3 项改为 `docs/compose/reports/handoff-<日期>-<主题>.md`） | **已丢失** |

文档中引用这两个目录的形态统计（`grep` 实测）：**具体文件名 24 处**（断层风险源）、占位符/通配符 33 处（合法命令模板）、仅目录名 25 处（合法）。

### 2.3 与现行硬性 #14 冲突

`AGENTS.md` #14 与 `09-agent-workflow.md` §验证纪律要求：产物一律落 `run-logs/`/`perf-logs/`、**禁止 `rm`**。若不改约束本体，任何「主动清理」都是违规行为。

### 2.4 已存在的门禁耦合

`tests/bug_hunt/static_analyzer.py` 的 `IGNORE_DIRS` 依赖该约定（注释明写 2026-10-09 实测）——本设计**保留**「临时产物仍落这两目录」的部分，故该门禁无需改动。

## 3 设计（决策）

### 3.1 三层归属（唯一来源，杜绝依据住进临时目录）

| 层 | 内容 | 位置 | 生命周期 |
|---|---|---|---|
| 瞬时 | 测试日志、探针 JSON/HTML/PNG、浏览器 profile、缓存、AOCI 解压副本 | `run-logs/`、`perf-logs/`（gitignore） | **任务收尾全清** |
| 依据 | 结论、数值、对比表、复现命令、验收摘要、跨会话交接 | `docs/compose/reports/<日期>-<主题>.md`（**入库**） | 永久 |
| 规则 | 设计 / 计划 / 知识 | `spec/`、`plan/`、`knowledge/` | 既有约定 |

**核心口径**：原始文件不入 git；入 git 的是「从原始文件提炼出的结论 + 数值 + 复现命令」。体积小、不会断层、也不需要新的存储目录（复用现存 `docs/compose/reports/`）。

### 3.2 清理动作：`scripts/agent/cleanup_tmp.py`

- 目标目录**硬编码为且仅为** `run-logs/`、`perf-logs/`（由 `__file__` 推导仓库根，代码内断言白名单），清空其**内容**、保留目录本身。
- 默认 **dry-run**（只报体积）；`--apply` 真删；`--active-window <秒>`（默认 600）内 mtime 的条目判为「活跃写入」跳过并列出（等价于原「禁止 rm」要防的并发误删）；`--force` 忽略该窗口。
- 输出一行机器可读结论 `cleaned N files / X MB; kept M active` + 跳过清单；`--selftest` 纯内存自测（对齐 `scripts/agent/session_cost.py` 先例）。
- 纯标准库、幂等、无外部依赖；不触碰仓库内任何其他路径。

### 3.3 断层门禁：`tests/test_temp_log_policy.py`

照 `tests/test_doc_budget.py` 的既有模式（可 monkeypatch 的 `_load_docs()` + 纯函数 `_violations()`），随 `discover` 跑：

- 扫描：`AGENTS.md`、`MEMORY.md`、`docs/**/*.md`、`learn/**/*.md`。
- 禁止：引用 `run-logs|perf-logs` 下的**具体产物文件名**。
- 允许：仅目录名；含 `<...>`/`*` 的占位符或通配符；测试内白名单（每条必须带一行理由，**上限 3 条**，超出即应改写文档而不是加白名单）。
- 失败信息格式：`file:line → 命中引用 → 建议改法（改为结论/占位符）`。
- 存量 24 处一次性梳理：历史证据引用 → 保留结论与数值、删掉指向已消失文件的路径（并注明「原始日志为临时产物，已清理」）；命令模板 → 改占位符；确实长期复用的固定约定名 → 进白名单。

### 3.4 触发点：挂进已有收尾批量命令（零增步）

清理是 `2026-10-06-token-budget-design.md` R5「收尾取证一次批量发」那条命令的**末尾追加一个调用**，不新增轮次、不做 per-step 清理、不引入 cron/hook：

```bash
python -m unittest discover -s tests/ -t . -v > run-logs/final-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran )' run-logs/final-<时间戳>.log
codegraph status | tail -3; git diff --stat
venv/bin/python scripts/agent/session_cost.py --check
venv/bin/python scripts/agent/cleanup_tmp.py --apply      # ← 唯一增量；判据行已取完再清
```

收尾简报必须含 `cleaned ...` 一行作为「任务整体完成」的证据。任务中断未收尾时临时文件保留（有意），由**下一次**任务收尾连带清掉。

### 3.5 跨会话交接换址

`10-token-budget.md` R3 的交接文档改落 `docs/compose/reports/handoff-<日期>-<主题>.md`（几 KB，入库），`run-logs/handoff/` 不再承载交接（该目录已丢失一次，正是本次断层的样本）。

## 4 参数依据

- **活跃写入窗口 600s**：与 #13/#14 的等待协议（≤3 次 × 5–10s 采样、后台作业 `nohup` 后 `sleep 1` 确认落盘）同量级；超过 10 分钟无写入的产物一律视为遗弃。
- **白名单上限 3 条**：白名单是漏洞的正式形态，阈值取「固定可再生产物约定」的最小集合（现有候选仅 `perf-logs/bench-credentials.txt`、`run-logs/probe/verify.debug.json` 两个）。
- **不做按龄保留（`>N 天`）**：可再生产物不清就永远堆着，且「按龄」需要人判断哪些还有用——正是本设计要消除的负担。

## 5 边界（不做什么）

- 不引入 cron/systemd/钩子自动清理（DSH 无 hook，且副作用超出任务边界）。
- 不做 per-step 或按文件挑选的清理（违反 #20 的 token 纪律）。
- 不把原始大文件入库（只入提炼后的结论）。
- 不新建存储目录（复用 `docs/compose/reports/`）。
- 不放松 `static_analyzer.IGNORE_DIRS` 等既有门禁。
- 不改 `docs/compose/spec/ui-v2-draft/` 等已确认稿与既有截图资产。

## 6 验收

| 项 | 命令 | 预期 |
|---|---|---|
| 清理工具自测 | `venv/bin/python scripts/agent/cleanup_tmp.py --selftest` | 全过 |
| 清理幂等 | `cleanup_tmp.py --apply` 连跑两次 | 第二次 `cleaned 0 files / 0 MB`，退出码 0 |
| 活跃保护 | 造一个 10 分钟内 mtime 的文件后 `--apply` | 该文件被跳过、列入 kept |
| 门禁 RED→GREEN | `python -m unittest tests.test_temp_log_policy -v` | 现状 RED（24 处）→ 梳理后 GREEN |
| 门禁自证 | `venv/bin/python tests/bug_hunt/gate_redproof.py` | 新增的本门禁条目 RED→GREEN 均符合 |
| 全量 | `python -m unittest discover -s tests/ -t . -v` | 全绿（含静态分析门禁） |
| 收尾 | 收尾批量命令 | 末尾输出 `cleaned ...` 一行 |

## 7 改动清单

1. `AGENTS.md` 硬性 #14（改约束本体：保留「落 gitignore 目录」，删「禁止 `rm`」，增「收尾统一清理 + 依据不得落临时目录」）。
2. `docs/compose/knowledge/09-agent-workflow.md`（§验证纪律同步 #14；收尾步骤加清理）。
3. `docs/compose/knowledge/10-token-budget.md`（R3 交接换址；R5 批量命令追加清理调用）。
4. `docs/compose/knowledge/11-aoci-usage.md`（AOCI Entry 的证据/关系不得指向临时产物；`run-logs/aoci/extract/aoci` 那处失效引用改写）。
5. `docs/compose/knowledge/08-testing-conventions.md`（日志落盘与取证口径；那处过程脚本引用按 `MEMORY.md` 「产出者溯源」判据认定为**过程脚本、不提升**，引用改写为不含临时路径的知识性描述）。
6. `MEMORY.md`、`learn/sqlreport-kb/course-state.md`（同任务内同步）。
7. 新增 `scripts/agent/cleanup_tmp.py`、`tests/test_temp_log_policy.py`；`tests/bug_hunt/gate_redproof.py` 增一条自证。
8. 存量 24 处文档引用一次性梳理（含 `2026-09-29-execution-layer-performance-design.md` 状态头按「取代两头改」补记）。
9. `.gitignore` 注释微调（说明「可由 `cleanup_tmp.py` 随时清空」）。
10. 收尾：`codegraph sync`（新增 `.py`）+ 一次 `aoci_maintain`（`.md`/`.py` 均受管）。
