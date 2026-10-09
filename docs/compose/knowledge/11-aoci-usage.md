# 11 · AOCI 使用手册（Agent 专用）

> **读者**：在本仓库干活的 AI Agent（含子代理）与人类维护者。
> **一句话**：AOCI 是仓库的「认知层」——**开工用它少走弯路，改完只在收尾维护一次，它不会自己更新**。
> **本卷是 AOCI 的唯一操作手册**；根 `AGENTS.md` 的 `<!-- aoci:begin -->` 区块按文档预算（硬性 #20）只保留最小合同，细节一律看本卷（硬性 #21）。
> 最后核对：2026-10-08 · AOCI `0.1.0-rc18` · Code 卷 127 条 / 15255 tokens

---

## 0. 本项目的接入事实（先读这一段，避免凭空猜）

| 事实 | 值 |
|------|-----|
| 二进制 | `.tools/bin/aoci`（v `0.1.0-rc18`）；**不在 PATH**，必须用这个仓库内路径 |
| 另一份副本 | `tools/aoci/aoci`（发布包解压件）——**不是权威**，别混用（曾经的 `run-logs/` 下解压副本已不存在，勿再引用） |
| 版本控制 | `.tools/` 与 `tools/aoci/` 都被 `.gitignore` 忽略 → 不要提交、别假设别的机器上有 |
| MCP 接入 | DSH profile 的 `cordis.patch.yml` 里静态 insert（`serverName: aoci`，`command: .tools/bin/aoci --repo /opdev/SqlReport mcp`）；本机路径 `~/.dsh/profiles/web/cordis.patch.yml` |
| 模型可见工具 | 9 个：`mcp__aoci__aoci_rules` / `overview` / `get_entries` / `search` / `header` / `maintain` / `update_entry` / `remove_entry` / `report` |
| 认知资产 | `aoci.txt`（manifest）→ `aoci.meta.txt`、`aoci.code.txt`（Code 卷）；`.aoci/` = baseline / ledger / governance / transactions |
| 只读面板 | `http://127.0.0.1:8899`（`aoci ui --detach --port 8899` 启动或复用；`--stop` 停止） |
| AI 端点 | `ai.enabled=false` → **二进制不会生成任何语义**，FRAS 只能由模型读完真实证据后创作 |
| 自动化程度 | **没有 hook**（`.aoci/hooks/`、`.git/hooks/` 均空）→ 没有自动同步；"自动"的只有每会话注入的 AGENTS.md 指令与常驻 MCP 工具 |

**当前对齐状态（可作为基线自查）**：Code 卷 127 条、baseline 372 文件、`governance_aligned=true`、语义漂移 0、待策展 0、孤儿 0、`aoci report` 待办 0。

---

## 1. 三层检索怎么分工（别搞混，也别人为对立）

| 层 | 工具 | 回答什么问题 | 何时用 |
|----|------|--------------|--------|
| **语义层** | AOCI `aoci_search` / `aoci_get_entries` | 这个对象**为什么存在**、职责、强关系、对外契约、非显然约束与历史决策 | 接手任务、改前评估影响面、收尾写认知 |
| **符号层** | `codegraph`（硬性 #18，**强制优先**） | 符号在哪、谁调用谁、波及哪些文件/测试 | 定位代码、查调用链、找受影响测试 |
| **文档层** | `docs/compose/knowledge/` 分卷 | 流程、约定、踩坑、共享语义 | 按 `AGENTS.md` §0 路由表 |

推荐顺序：**AOCI 语义（1–2 次查询摸清对象）→ codegraph 定位符号 → 读源码核对**。
冲突时以代码/测试为准，并回写知识库（硬性 #7）。

---

## 2. 场景 → 动作速查表（核心表）

| # | 场景 / 环节 | AOCI 动作 | 说明 |
|---|-------------|-----------|------|
| 1 | **任何 Agent Run 开工** | `aoci_rules`（取会话合同）；需要全貌时 `aoci_overview` | 合同不重复调用；scope 按当前任务选 |
| 2 | 纯只读：问答、评审、查历史、看影响面 | **不调用任何维护工具** | 收尾无需 maintain（工具明确要求：只读任务别再调） |
| 3 | 定位 Bug、改前评估 | `aoci_search` / `aoci_get_entries` | 查"这个文件/表为什么存在、动它要注意什么" |
| 4 | 改代码（`.py`/`.js`/`.mjs`） | 收尾 `aoci_maintain` **一次** + `aoci_update_entry` | 见 §3 时间轴；不要逐文件维护 |
| 5 | **改文档（`.md`）** | 同上——**`.md` 也在受管范围**（知识库分卷、`AGENTS.md` 都在 baseline 里） | 纯措辞/预算类改动：条目可**原样提交**（工具允许），不必重写语义；有新增语义事实才改 F/R/A/S |
| 6 | 新增文件 | maintain 会把它作为新增候选 → 需要创作新 Entry | 新增文件不等于"不用管" |
| 7 | 删除 / 改名文件 | maintain 会给出 orphan / missing 候选 | 孤儿用 `aoci_remove_entry`（只对治理返回的显式孤儿）；改名=删+增 |
| 8 | 大重构 / 目录结构调整 | **仍是一次 maintain**（批量候选） | 不要为增量更新跑 `aoci scan`（那是首次 Baseline 与受管范围变更的入口） |
| 9 | 证据不足、无法判断语义 | `aoci_report` 登记待办 | **禁止猜写、禁止套模板、禁止为清待办而编** |
| 10 | 工具返回 `repair_required` / `stopped` | 见 §6，按停点处理，不得忽略 | `stopped` ≠ 成功，也 ≠ 一定没写入 |
| 11 | 数据库结构相关 | 见 §7 | Database 卷与 Code 卷相互独立 |
| 12 | 多代理 / 子代理并行 | 见 §8 | 读可并行，**写必须集中到收尾一处** |
| 13 | 上下文压缩（compaction）后 | `aoci_rules` + 带 `refresh_reasons=["context_compaction"]` 的**完整** `aoci_overview` | 压缩后的"记忆里的索引"不算可靠认知 |

---

## 3. 一次任务的完整生命周期（时间轴）

```text
0 开工      aoci_rules（合同）           ← 需要全貌再加 aoci_overview
1 调查      aoci_search/get_entries → codegraph explore → 读源码
2 改代码    TDD / 按项目测试纪律（硬性 #8/#12/#17）
3 稳定点    不再改、测试绿  ← 这是唯一该调 maintain 的时刻
4 维护      aoci_maintain → 模型创作完整 Entry → 整批 aoci_update_entry
5 收敛      aoci verify / aoci check（drift 归零）
6 汇报      简报里写清条目数 / 漂移 / 命令证据
```

**四条禁止**：

1. ❌ 每改一个文件就 maintain 一次（工具会拒绝，且制造无意义批次）。
2. ❌ 跳过第 3 步直接手写 Entry 或手改 `aoci.code.txt`（绕过 CAS/治理/审计）。
3. ❌ 在"还没改完"的中间态调 maintain（要求是**本任务的最终稳定态**）。
4. ❌ 已经 aligned 后重复调 maintain（checkpoint 会明确写"不要再次 Maintain"）。

---

## 4. 九个 MCP 工具手册

| 工具 | 何时用 | 关键点 / 禁止 |
|------|--------|----------------|
| `aoci_rules` | 每个 Run 开工；合同不在上下文或 AOCI 服务身份变化时 | 同一认知周期内**不要重复调用** |
| `aoci_overview` | 需要全貌 / 仓库已有索引但本会话无可靠认知 | 默认（非 `check_only`）会分块交付：**必须原样跟 `next_cursor` 直到 `completed=true`**，中途不得用 search/entries 补答；`check_only=true` 只取紧凑 checkpoint（便宜，日常首选） |
| `aoci_get_entries` | 已知道具体路径/目录/数据库对象，只取局部 Entry | **不要用少量 Entry 替代完整 Overview**；仅用于局部不确定或用户点名查看 |
| `aoci_search` | 路径未知、按关键词/标签找对象 | `keyword` 匹配整行（含中文也行）；`tag_filter` 形如 `A=Index`、`C>=7`；两者至少给一个 |
| `aoci_header` | 创作 Entry 卡壳：查项目规则、共享对象规则、**标签字典**、校准示例 | 规则不可靠或需要单独核对时调用 |
| `aoci_maintain` | **受管内容达到最终稳定态后**，领取机器签发的完整创作批次 | 只调一次；返回 `repair_required` / `stopped` 必须完整处理；纯只读、中间态、已 aligned → 都不要调 |
| `aoci_update_entry` | 提交当前批次：一个原子事务写完整的候选集合 | 必须**整批提交**，原样保留每项 `source_sha256`、`candidate_id` 与 Code 批次身份（`code_batch_id` = `code_plan.batch_id` = 每个候选的 `batch_id`）；**禁止字段 Patch、禁止自行截取子集** |
| `aoci_remove_entry` | 仅用于治理明确返回的**孤儿候选** | 不删除源码/数据库对象/Evidence/Root/Meta/Volume；不得为删条目而制造孤儿 |
| `aoci_report` | 证据不足、无法可靠生成语义 | 只登记待办（写本地报告与审计），**不改正式索引**；不替代策展/恢复 |

**Token 提醒（硬性 #20）**：完整 Whole-Index 约 15k tokens → 不要每个任务都拉；日常用 `check_only` 或 `aoci_search`。
维护完成后 `remaining` 非零 → 基于新 preimage **重新调用 maintain** 继续，**不得**为省传输而缩减覆盖面。

---

## 5. CLI 速查（人手动、或宿主没接 MCP 时）

`aoci` **不在 PATH**，本仓库固定路径 `.tools/bin/aoci`；`--repo` 可显式指定仓库根。

```bash
cd /opdev/SqlReport
A=./.tools/bin/aoci

# —— 日常只读自查（人来用，或 Agent 取证）
$A status                 # 对齐速览（纯读）
$A doctor                 # 环境与宿主接入诊断（解释"为什么面板这样显示"）
$A check                  # 提交前聚合治理门禁
$A verify                 # Missing/Orphan/Stale/Unbaselined 事实
$A capabilities           # 当前二进制能力清单（布局、MCP 工具数、支持的数据源）
$A ui --detach --port 8899   # 只读面板；已有实例直接复用；--stop 停止

# —— 指南与专项
$A index agent guide --agent <agent> --json   # 非 MCP 宿主的确定性下一步（不要把它复制成自研状态机）
$A database --help                            # 数据库证据/访问/认知生命周期
$A cognition plan --help                      # Bootstrap / 迁移计划（只读预览）
$A mcp                                        # 手工起 stdio MCP Server
```

**"只读"≠"零写入"**：`verify` / `check` / `index score` / `index inventory` 不改正式索引与 Baseline，但 Ledger 启用时会追加本地 Ledger，`verify` 还会写 Verify History——审计写入失败不改变退出码。需要严格零写入请用隔离副本。

---

## 6. 边界、失败与恢复

| 情况 | 正确处理 |
|------|----------|
| **只读 / 已 aligned** | 不调 maintain；checkpoint 若写"不要再次 Maintain"，就真的不要调 |
| `repair_required` | 只修被明确命中的候选，然后**重新提交同一完整批次** |
| `stopped` | **不是成功，也不等于零写入**：查 `failed_step`、正式写入证据与 Recovery，按 Guide 的恢复动作走；**禁止用"继续写完"覆盖第三方字节** |
| 冲突 / 审批 / 人工裁决 / 权限 / 安全信号 | 一律不得忽略，停下来报告 |
| 上下文压缩后 | 先 `aoci_rules`，再用 `refresh_reasons=["context_compaction"]` + 新 `refresh_event_id` 跑**完整** overview，跟完 cursor 并提交一次 Attestation，然后继续原任务 |
| 用户说"不要写 AOCI / 只读 / 别动 aoci.txt" | **以用户为准**：不写入，并在汇报里如实说明剩余不一致 |
| 手改 `aoci*.txt` / `.aoci/` 正式资产 | 禁止（绕过 CAS、原子写、审计与恢复证据） |
| `run-logs/` / `perf-logs/` 下的产物当长期证据 | 禁止：临时目录随时会被 `scripts/agent/cleanup_tmp.py --apply` 清空，Entry 的 F/R/A/S 与 `S` 证据一律不引用其下具体文件；长期依据落 `docs/compose/reports/` |

---

## 7. 数据库认知（Database 卷）：为什么面板显示「未配置数据库」

**机制**：本项目是 **Volumes v1** 布局，`aoci.txt` 是 manifest，`code` 与 `database` 是**两个彼此独立的卷**；面板按卷分别渲染，Database 标签页没有内容就显示"未配置数据库"。

**本仓库实测事实**（`GET /api/state?repo=/opdev/SqlReport` 与 `check_only` checkpoint）：

```text
facts.code     = { enabled:true,  applicable:true,  domain_state:enabled,        asset_state:present, path:aoci.code.txt,     object_count:127 }
facts.database = { enabled:false, applicable:false, domain_state:not_applicable, asset_state:absent,  path:aoci.database.txt, object_count:0 }
database_entry_count = 0   database_binding_count = 0
```

**结论**：Code 卷已经建立（127 条）→ 索引内容当然看得见；Database 卷**从未配置** → 面板如实显示"未配置数据库"。这不是错误，也**不影响代码认知**，属于正常状态。

**本项目为什么没接**：`config_db` 是 SQLite / MySQL 双引擎，而 AOCI 的 `database source` **只支持 PostgreSQL / MySQL / openGauss——SQLite 不在支持列表**。因此只有走 MySQL 的实例才值得接，且属于独立任务（需要只读凭据）。

**将来若要接 MySQL 的 `config_db`**（凭据只从外部环境变量读，**绝不写进仓库**）：

```bash
$A database source add ...        # 声明不含秘密的数据源
$A database source access ...     # 脱敏就绪检查（不返回值）
$A database source inspect ...    # 只读 Catalog 访问测试
$A database snapshot ...          # 采集 Canonical 表证据
$A database cognition bootstrap   # 为已对齐的 Code-only 项目加 Database Cognition
# 之后按 §3 的收尾流程走 maintain + update_entry
```

---

## 8. 多代理 / 子代理协作

- 所有成员共享**同一文件系统与同一份索引**；AOCI 写入有跨进程锁与 CAS，但**并行写会产生互相覆盖的批次**。
- **读**（`aoci_search` / `aoci_get_entries` / `check_only`）子代理可并行，无副作用。
- **写**（`maintain` / `update_entry` / `remove_entry`）必须集中在**所有写者停止后的最终稳定态**，由**一个**执行者调用一次。
- 子代理任务书里要写明：不得自行维护 AOCI；发现的认知缺口回报给收尾执行者。
- 收尾执行者维护前先确认没有其他活跃写入者（`AGENTS.md` 硬性 #13/#14）。

---

## 9. 面板 8899（人工巡查，不是 Agent 通道）

- 看什么：索引头与 Code/Database 卷**原文**、覆盖文件数/行数/token 与压缩比、Overview 分块计划、治理漂移、受管范围、宿主接入、运行中的 `aoci mcp` 进程、Guide 建议的下一步。
- 边界：只监听回环、只答 GET/HEAD、**不加锁、不写任何文件、不是 MCP 传输** → 它**不能替代**工具调用，也不能用来改认知。
- 常用：`--open` 前台打开；`--detach` 后台并复用；`--stop` 停止；`--also /path` 同页看多仓库。

---

## 10. 故障排查表

| 现象 | 含义 | 动作 |
|------|------|------|
| 面板显示「未配置数据库」 | Database 卷未配置（与 Code 卷无关） | 正常；要接见 §7 |
| checkpoint 里 `state: invalid` + `refresh_ready_for_overview` | 本会话尚未做完整认知交付/证明 | 不代表索引坏；需要全貌时按 §4 跑完整 overview |
| `next_action` 说"已 aligned，不要再次 Maintain" | 当前无需维护 | 不要再调 maintain；需要时 verify/check 复证 |
| `semantic_change_count > 0` / drift 列表非空 | 有受管对象变化未维护 | 到最终稳定态走 §3 第 4–5 步 |
| `orphan` 非空 | 索引里的对象已不存在（或放错域） | 用 `aoci_remove_entry` 处理治理返回的孤儿候选 |
| 工具返回 `stopped` | 写入链路异常或命中安全边界 | 见 §6，查证据 + Recovery，报告用户 |
| 九个 MCP 工具消失 | MCP 桥未接入本会话 | 查 profile `cordis.patch.yml` 的 `mcp-aoci`；或改用 §5 的 CLI |

---

## 11. 收尾检查单（AOCI 部分）

1. 本次是否改动了**受管对象**（代码、`.md`、配置）？→ 是：确认**所有写入已结束**后，在最终稳定态调**一次** `aoci_maintain`。
   - **判据（静止段）**：maintain 之前，本任务的所有受管写入必须已结束；**同一静止段内调用 ≥2 次即违规**。
     实测反例（2026-10-09）：两场会话各调 2 次 / 3 次，前几轮被后一轮取代，白付 8.6–14.2KB × 轮次。
   - **允许的第二次**（仅两种）：① 上次返回 `remaining != 0`（机器要求继续）；② maintain 之后**又写入了受管对象**，
     此时不得修补旧批次，必须在新的最终稳定态重跑一轮（AOCI 合同 §16：维护后再改，之前结果失效）。
2. 按返回候选**创作完整 Entry**（读真实证据，禁止模板化）→ **整批** `aoci_update_entry`，保留绑定字段；
   若本次改动只在措辞层面、无新增语义事实，条目可**原样提交**（省 output token，不降低覆盖）。
3. `aoci verify` / `aoci check` 收敛：drift / orphan / unbaselined 归零。
4. 改过 `.py`/`.js`/`.mjs` 仍要**独立**跑 `codegraph sync`（硬性 #19）——AOCI 与 codegraph 是两套，别互相替代。
5. 汇报必须给证据：条目数、漂移数、执行的命令与结果；没有证据不写"应该已同步"。

---

## 12. 常见误解（反合理化）

| 想法 | 事实 |
|------|------|
| "AOCI 会自动跟着代码更新" | 不会。无 hook、无守护进程；维护必须由 Agent 在收尾显式发起（§0、§3） |
| "我只改了文档，不用维护" | `.md` 也在 baseline 受管范围内（§2 #5） |
| "每改一个文件就维护一次更保险" | 反了：只在**任务最终稳定态**调一次（§3） |
| "verify 全绿 = 语义一定正确" | 机器只证明结构与治理合同成立，**不代表每条模型语义都对** |
| "面板说没配数据库 = 索引坏了" | 两个独立卷；Code 卷正常即可（§7） |
| "手改 `aoci.code.txt` 更快" | 禁止：绕过 CAS、原子写、审计与恢复证据（§6） |
| "只读命令不写任何文件" | Ledger / Verify History 可能被追加（§5） |
| "压缩后凭记忆继续就行" | 压缩后必须先重载合同与完整认知（§2 #13、§6） |

---

## 相关

- 硬性约束总纲：仓库根 `AGENTS.md`（本卷对应**硬性 #21**）
- 代码检索纪律：#18/#19 → `09-agent-workflow.md`
- Token 预算：#20 → `10-token-budget.md`
- AOCI 官方文档（随二进制分发，**不入 git**）：`tools/aoci/README.zh-CN.md`（本卷未复制的内部状态机以它和 `--help` 为准）
- 会话级合同：`aoci_rules` 工具返回（**优先级高于任何静态文档**）
