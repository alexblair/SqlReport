# 取证与指标口径（复盘唯一证据来源）

> 本文件是 `ai-retro-lean-iteration` 的支撑件。**目的：把「AI 表现」变成可复现的数值证据**，
> 使每条优化点都能回溯到「会话 · 步 + 实测数值」，而不是印象。
> 全部命令与口径在本项目实测过（来源：`docs/compose/reports/2026-10-06-token-efficiency-retrospective.md`
> 与 `docs/compose/reports/2026-10-09-aoci-effectiveness-evaluation.md`）。

## 1 数据源（实测事实）

| 事实 | 位置 |
|------|------|
| 会话原文（zstd 压缩 JSONL） | `~/.dsh/sessions/--<cwd 的 / 换成 ->--/session-*/session.v4.jsonl.zstd`；本项目为 `--opdev-SqlReport--` |
| 解压 | `zstd -dc <会话文件> > run-logs/`（本机**无** python `zstandard`，用 `zstd` CLI；解压产物只落临时目录，文档里只允许以目录形态引用） |
| 真实用量 | 每条 `assistant/message` 的 `data.usage`（`inputTokens` / `cacheReadTokens` / `cacheWriteTokens` / `outputTokens` / `totalTokens`）——**每步一条，不需要估算** |
| 会话标题 | `~/.dsh/storages/session_projcache/sessions/<id>.json` → `record.rows.title.val` |
| 按会话用量 | 只有 `storages/usage_history.json` 的**按天聚合**，没有按会话用量 → 必须走上面的会话原文 |

## 2 首选工具（复用，禁造新脚本 · 硬性 #3）

```bash
venv/bin/python scripts/agent/session_cost.py --list            # 列出本项目会话（id/标题/步数）
venv/bin/python scripts/agent/session_cost.py --last 3          # 复盘常用：最近 N 个会话
venv/bin/python scripts/agent/session_cost.py --session <id前缀>
venv/bin/python scripts/agent/session_cost.py --all             # 全项目横截面
venv/bin/python scripts/agent/session_cost.py --check           # 一行体检（~60 字符），随时自查
```

工具**已经**输出以下证据，直接引用，不要另写统计脚本：

- 每会话：步数 / `Σtotal` / `input` / `cacheRead` / `output` / **重发占比**
- 上下文：首步 → 末步 ctx、平均每步 tokens
- 工具调用总数与**批处理分布**、**单调用步占比**（对比 #20② 目标）
- **最贵步**：`新增 tokens × 剩余步数 ≈ 重发成本`，并列出该步调用的工具名
- 工具返回体积与错误次数、**重复调用**（同工具同参数，`×N`）
- 预算体检违规项（单步新增超阈 / 单步上下文超阈 / 步数超阈）
- AOCI：改前定向读（precheck）/ MCP 读 / `maintain` 次数（对照硬性 #21）

## 3 指标口径（务必按此表述，避免口径战）

```
ctx(步 i)      = inputTokens + cacheReadTokens + cacheWriteTokens      # 该步请求的上下文规模
新增(步 i)     = ctx(i+1) − ctx(i)                                     # 该步往历史里塞了多少
重发成本(步 i) = 新增(步 i) × 剩余步数                                 # 这笔新增会被后面每步重发
```

**为什么按这个口径**：2026-10-06 实测 4 个会话合计 69.7M tokens，其中 cacheRead 占 **98.56%**，
模型 output 只占 **0.58%**；单步固定地板 ≈ **1.6 万 tokens**（system 提示 + 工具 schema + `AGENTS.md`
+ 技能目录，每步重发一次）。因此：

- 效率 ≈ **步数 × 上下文规模**，与「让模型少说话」几乎无关；
- 优化靶点是**「这一步往历史里塞了什么」**（大 grep、大文件全文回显、单调用步、长会话），
  不是「回答更短」。

## 4 陷阱（已踩过，别重犯）

1. `data.stream` 是流式回放产物（单会话可达 1.5M 字符），**不进模型上下文**——统计时必须剔除；
   早期用「字符数」当代理会把结论带偏。
2. `usage_history.json` 只有按天聚合，**不能**用来算单会话成本。
3. `write` / `edit` 会把改动后全文回显进上下文，一次大文件编辑可加约 2 万 tokens，且**同样被后续每步重发**。
   复盘时这类「自己制造的体积」要单独列。
4. 复盘的会话本身也是成本：**先落盘交接再开工**（> 60 步或上下文 > 120k 换会话，硬性 #20③），
   否则「复盘者比被复盘者更贵」。
5. 会话 id 是前缀匹配；`--all` 是横截面，**不是**某次优化的前后对比——对比要用优化前后**同一业务场景**的会话。

## 5 产物纪律

- 解压出的 `.jsonl` 是临时中间产物 → 落 `run-logs/`（临时目录，只能以**目录形态**被引用）；
  收尾 `venv/bin/python scripts/agent/cleanup_tmp.py --apply`（硬性 #14）。
- **结论 + 数值 + 复现命令**必须落 `docs/compose/reports/YYYY-MM-DD-<主题>.md`（长期依据）；
  临时目录里的具体文件名不得写进文档（门禁 `tests/test_temp_log_policy.py` 会拦）。
- 拿不到数据时**登记待办**（AOCI `aoci_report`）或直接说明缺口，**不许用印象补数**。
