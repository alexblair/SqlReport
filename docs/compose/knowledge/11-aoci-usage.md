# 11 · AOCI 使用手册（Agent 专用）

> **读者**：本仓库 AI Agent（含子代理）。**一句话**：AOCI 是仓库「认知层」——改前知道要小心什么，改完只在收尾维护一次，**不会自己更新**。
> 本卷展开硬性 #21；根 `AGENTS.md` 的 `<!-- aoci:begin -->` 最小块是合同，冲突以最小块为准。
> **遍历边界（2026-10-09 踩坑）**：AOCI 的文件遍历**不读 `.gitignore`**——运行态目录（浏览器 profile、缓存、临时库）即使被 gitignore 也会被走进去算 SHA256 并可能被纳入受管范围。**必须用 `aoci scope rule add … --action exclude` 显式排除**（如 `**/.chrome-*/**`），且 glob 要写递归形态（`**/*.db-wal`，`*.db-wal` 只匹配仓库根）。
> 最后核对：2026-10-09 · AOCI `0.1.0-rc18`（条目数/基线文件数**以 `$A status --json` 为准**，不抄静态数字）

## 1. 接入事实（先读，别凭空猜）

| 事实 | 值 |
|------|-----|
| 二进制 | `.tools/bin/aoci`（v `0.1.0-rc18`）；**不在 PATH**；`tools/aoci/aoci` 是解压副本、**不是权威**；两者均被 gitignore |
| MCP 接入 | DSH profile `~/.dsh/profiles/web/cordis.patch.yml` 静态 insert（`serverName: aoci`，`command: .tools/bin/aoci --repo /opdev/SqlReport mcp`） |
| 认知资产 / 语义 | `aoci.txt`（manifest）→ `aoci.code.txt`（Code 卷）；`.aoci/` = baseline/ledger/governance/transactions；`ai.enabled=false` → 二进制**不生成语义**，FRAS 由模型读完真实证据后创作 |
| 自动化 | **没有 hook**（`.aoci/hooks/`、`.git/hooks/` 只有 `.sample`）；只有每会话注入的 `AGENTS.md` 与常驻 MCP 工具 |
| 只读面板 | `http://127.0.0.1:8899`（`aoci ui --detach --port 8899` 启动或复用；`--stop` 停止） |


## 2. 三层分工与九个 MCP 工具

**AOCI = 改它要小心什么（语义/约束）；`codegraph` = 改它还会碰到谁（符号/调用链，硬性 #18 强制优先）；分卷 = 按什么流程做。不用 AOCI 找符号、不用 codegraph 找约束。**

**改前定向读**：`venv/bin/python scripts/agent/aoci_precheck.py <本次要改的文件…>`（`NO-ENTRY`=无认知）。日常**不再拉** Whole-Index（17K tokens）。

**九工具一句话**：`aoci_rules` 会话合同（**仅最小块失效或压缩后**调）；`aoci_overview` 全貌（**仅压缩恢复**，跟完 `next_cursor` 到 `completed=true`，中途不得用 search/entries 补答）；`aoci_get_entries`/`aoci_search` 局部查询（不替代全貌）；`aoci_header` 规则与**标签字典**；`aoci_maintain` 最终稳定态领**一次**完整批次；`aoci_update_entry` **整批**提交、保留绑定字段；`aoci_remove_entry` 仅治理返回的**显式孤儿**；`aoci_report` 证据不足登记待办（**禁猜写**）。

## 3. 场景速查

| 场景 | 动作 |
|------|------|
| 纯只读（问答/评审/看影响面） | **不调任何维护工具** |
| 改代码 / 改 `.md`（`.md` 也在 baseline 内） | 收尾**一次** maintain + 整批提交；纯措辞改动条目可**原样提交** |
| 新增 / 删除 / 改名 / 大重构 | 仍是一次 maintain 的批量候选（增量别跑 `aoci scan`） |
| 证据不足 | `aoci_report` |
| `repair_required` / `stopped` / 压缩后 | 见 §5 |

**收尾链（硬性 #21）**：`aoci check --json` 看 `executable_targets`（为 0 不调 maintain）→ `maintain` → **整批** `aoci_update_entry`（原样保留 `source_sha256`/`candidate_id`/`code_batch_id`，**禁字段 Patch、禁截子集**）→ `check` 收敛。**同一静止段调 ≥2 次即违规**；`scope status/acknowledge` 仅在 `check` 报 `scope_change_required` 时执行；`remaining` 非零 → 基于新 preimage 重调 maintain。

## 4. 时间轴

```text
1 调查    aoci_precheck → codegraph explore → 读源码
2 改代码  TDD / 测试纪律（硬性 #8/#12/#17）
3 稳定点  不再改、测试绿  ← 唯一该调 maintain 的时刻（同一静止段只此一次）
4 维护    maintain → 创作完整 Entry → 整批 update_entry → verify/check 收敛
```

**禁止**：逐文件 maintain；中间态 maintain；跳过稳定点手写 Entry；已 aligned 后重复 maintain。

## 5. 失败、恢复与边界

| 情况 | 正确处理 |
|------|----------|
| `repair_required` | 只修被命中的候选，再**重新提交同一完整批次** |
| `stopped` | **不是成功，也不等于零写入**：查 `failed_step`/写入证据/Recovery，按 Guide 走；**禁止用「继续写完」覆盖第三方字节** |
| 冲突/审批/裁决/权限/安全信号 | 不得忽略，停下报告 |
| 上下文压缩后 | 先 `aoci_rules`，再带 `refresh_reasons=["context_compaction"]` + 新 `refresh_event_id` 跑**完整** overview，跟完 cursor 提交一次 Attestation，再继续原任务 |
| 用户说「只读 / 不要写 AOCI」 | **以用户为准**：不写，汇报里如实说明剩余不一致 |

禁手改 `aoci*.txt`/`.aoci/`（绕过 CAS/审计/恢复证据）；`run-logs/`、`perf-logs/` 不当长期证据，依据落 `docs/compose/reports/`；**「只读」≠「零写入」**：`verify`/`check` 会追加 Ledger / Verify History。

## 6. 数据库卷：为什么面板显示「未配置数据库」

`code`/`database` 是**两个独立卷**，面板按卷渲染；Database 无内容 → 显示「未配置数据库」。本项目 `facts.database = {enabled:false, applicable:false, asset_state:absent, object_count:0}` → **正常状态**，不影响代码认知。
原因：`config_db` 是 **SQLite/MySQL 双引擎**，AOCI 的 `database source` **不支持 SQLite**；只有走 MySQL 的实例才值得接，且属独立任务（只读凭据**绝不写进仓库**）。

## 7. 多代理

**读**（search/get_entries/check_only）可并行；**写**（maintain/update_entry/remove_entry）必须集中在所有写者停止后的最终稳定态，由**一个**执行者调一次（`AGENTS.md` 硬性 #14）；子代理任务书须写明「不得自行维护 AOCI」。

## 8. CLI 速查

`aoci` 不在 PATH，固定 `./.tools/bin/aoci`（`--repo` 指定仓库根）。

```bash
A=./.tools/bin/aoci
$A check     # 聚合治理门禁；--json 看 executable_targets
$A verify    # Missing/Orphan/Stale/Unbaselined 事实
$A ui --detach --port 8899   # 只读面板，复用实例；--stop 停止
```

## 9. 故障排查 Top5

| 现象 | 动作 |
|------|------|
| 面板「未配置数据库」 | 正常，与 Code 卷无关（§6） |
| `next_action`：「已 aligned，不要再次 Maintain」 | 不要再调 maintain |
| drift / `semantic_change_count > 0` | 最终稳定态走 §3 收尾链 |
| `orphan` 非空 | `aoci_remove_entry` 处理治理返回的孤儿 |
| 九个 MCP 工具消失 | 查 `cordis.patch.yml` 的 `mcp-aoci`；或改用 §8 CLI |

## 10. 常见误解

| 想法 | 事实 |
|------|------|
| 「AOCI 会自动更新」 | 不会：无 hook/守护进程，维护须由 Agent 收尾显式发起 |
| 「verify 全绿 = 语义正确」 | 机器只证结构与治理合同，**不代表模型语义都对** |
| 「只改文档不用维护」 | `.md` 也在 baseline 受管范围 |
| 「手改 `aoci.code.txt` 更快」 | 禁止：绕过 CAS/原子写/审计 |

## 相关

根 `AGENTS.md`（本卷展开**硬性 #21**）；检索 #18/#19 → `09-agent-workflow.md`；预算 #20 → `10-token-budget.md`；官方文档 `tools/aoci/README.zh-CN.md`；**`aoci_rules` 返回值优先于任何静态文档**。
