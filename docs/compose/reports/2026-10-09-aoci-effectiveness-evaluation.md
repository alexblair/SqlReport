# AOCI 有效性评估（2026-10-09）

> 评估窗口：2026-10-08 14:43 → 2026-10-09 17:00（本地，约 26 小时）· AOCI `0.1.0-rc18`。
> 结论基于机器事实与会话日志，非推测。评估期间的原始日志在 `run-logs/` 下（临时目录，随时被 `cleanup_tmp.py` 清空）；**本文件是长期依据**（结论 + 数值 + 复现命令）。

## 1 结论

AOCI 的机器部分可靠（结构、治理、CAS、原子写、审计、恢复链路完整），条目语义质量高；但评估时**读侧几乎为零**——25 小时内语义内容只被读 **2 次**（1 次 `overview` 状态探针 + 1 次收尾自检 `get_entries`），`aoci_search` **0 次**，而写侧 **35 次**。即：它是一个"只写不读"的高质量认知账本，价值停留在潜在状态。

## 2 关键数值（评估窗口）

| 项 | 实测值 |
|----|--------|
| 操作账本 | 87 事件；`maintain` 15 次（12 `repair_required` + 3 `error`）、`update_entries_batch` 19 次（8 次 `candidate_invalid` 被拒，恢复均成功） |
| 机器耗时 | 383.9 s ≈ 6.4 min |
| 会话侧调用 | **读 6**（`rules` 4 + `overview` 1 + `get_entries` 1）vs **写 35**（`maintain` 15 + `update_entry` 20） |
| 固定上下文税 | AOCI 九工具 schema 34,711 字符 ≈ 10.8k tokens / 每次请求（两套 server 注册） |
| 常驻噪音 | `code_skipped` 151 条（149 张截图 + 2 个 SQLite 运行态文件被划为 `index` 角色） |
| 语义准确性 | 抽检 7 条 S 字段：6 条与源码一致，1 条（`api_handler` 处理顺序）与代码不符 |
| 真实任务里的位置 | 两个 bug 修复会话中，首次触碰 AOCI 均在**收尾**（step 83 / 同轮 `update_entry` 之后） |

## 3 当轮整改（已落地）

1. **读路径命令化**：`scripts/agent/aoci_precheck.py <路径…>`（约 1K tokens，只解析 `aoci.code.txt`，零 MCP 往返与 schema 税）。
2. **边界固化**：AOCI = 改它要小心什么（语义/约束）；`codegraph` = 改它还会碰到谁（符号/调用链/波及面）；分卷 = 按什么流程做。
3. **砍仪式**：`scope status/acknowledge` 仅在 `check` 报 `scope_change_required` 时执行；`aoci_rules`/`aoci_overview` 仅在最小块失效或压缩恢复时调用。
4. **指标可见**：`session_cost.py` 输出「改前定向读（预检）/ MCP 读 vs `maintain`」，形成可验收出口。
5. **全文瘦身**：`AGENTS.md` 17933 → 10992 B、`MEMORY.md` 25725 → 9771 B、知识库分卷合计 ≈187.9K → 96.3K B（详见 `../plan/2026-10-09-context-slimming-and-aoci-usage-plan.md`）。

## 4 复现命令

```bash
A=./.tools/bin/aoci
$A verify --json                            # Missing / Orphan / Stale / Unbaselined
$A check --json                             # aligned / next_action / findings 分类
$A index agent guide --agent <id> --json    # complete / stage / executable_targets
venv/bin/python scripts/agent/aoci_precheck.py report.py render.py   # 改前定向读
venv/bin/python scripts/agent/session_cost.py --check                # 读/预检 vs maintain
```

## 5 收尾状态（2026-10-09 维护后）

- `verify`：`structure_valid=true`，Missing / Orphan / Stale / Unbaselined **全 0**
- `check`：**`governance_aligned=true`、`next_action=none`**（余 151 条 `code_skipped` 为告警，不阻断）
- `guide`：**`complete=true`、`stage=aligned`、`executable_targets=0`**
- Code 卷条目 131 → **137**（4 轮共 29 条整批提交）

## 6 遗留（需维护者裁决，不属本评估自动范围）

1. **151 条 `code_skipped`**：需一次**需真人审批**的受管范围变更才能消掉。已登记期望规则 `proj-shots-observe`（`docs/compose/spec/shots/**` → observe）、`proj-sqlite-shm-exclude`、`proj-sqlite-wal-exclude`（→ exclude）；preview 落在 `.aoci/scope-change/` 下，激活前 `check` 会停在 `blocked`。
2. **`tests/` 93 个文件为 `observe` 角色**（不进认知）：是否纳入属可维护性问题，纳入会显著增加条目量，需权衡。
