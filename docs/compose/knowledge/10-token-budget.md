# Token 预算与上下文经济学（硬性 #20）

> 对应硬性约束 #20。**只在两种时候读本卷**：① 会话收尾自查 / 复盘；② 准备做长任务、
> 大批量检索或读大文件之前。日常只需记住 AGENTS.md #20 的那几句。
> 数据来源：`~/.dsh/sessions/` 的真实 `usage`，`scripts/agent/session_cost.py` 可复现全部数字。

## 一句话版

**成本 ≈ 步数 × 上下文规模**——实测 4 个会话 Σtotal 69.7M tokens，其中 **98.6% 是历史重发**（cacheRead），模型输出只占 **0.58%**。省 token 的唯一主战场是「上下文 × 步数」，不是「让模型少说话」：**一步塞进历史的东西，后面每一步都要重发一次**（第 k 步新增 A tokens，全程多付 `A × (总步数 − k)`）。

- **单条工具返回 >8k 字符即超阈**：先计数（`grep -c`）、再截断（`head`）、再读（`read offset/limit`）。
- **互不依赖的调用同步发**（一步 2–4 个）；**长会话分段**：>60 步或上下文 >120k tokens → 落盘交接换会话。

## 一、历史实测账本（压成结论）

- 4 场会话 440 步 / 69.7M tokens：单步固定开销 ≈ **1.6 万 tokens**（system + 工具 schema + AGENTS.md + 技能目录每步重发），前 3 步就吃掉单会话 10%–23%；会话长度是主乘数（`Σ ≈ 步数 × 末尾上下文 ÷ 2`，拆 3 段可省一半以上），批处理长期欠用（单调用步 61%–80%），收尾「一项一步」占单场 30% tokens。
- 2026-10-10 单会话（性能/健壮性分批重构：1247 步 / 516.2M tokens / 末步上下文 603k）：**73% 花在「继承上下文」**（B1–B9 同会话串行，见 R3 批次边界条）；`bash` 占新增 54.6%（文本检视 394 次、内联一次性 python 151 次、全量 `unittest` 186 次）；写类工具的**入参**体积（write 182k + edit 112k + update_entry 171k 字符 ≈116k tokens）当前**不统计**——只看返回体积会选错收窄靶点。

## 二、硬规则（可核对）

### R1 单条工具返回 >8k 字符即超阈

判定用 `scripts/agent/session_cost.py`（超阈步会直接列出）。收窄命令表：

| 场景 | 禁止 | 改用 |
|------|------|------|
| 找符号 / 调用链 / 影响面 | `grep -rn` 全库 | `codegraph explore "<中文+代码词>"`（硬性 #18） |
| 不知道命中规模 | 直接全库 grep | `grep -rc "词" --include='*.py' .` 先计数，>40 先缩条件 |
| 找文案 / CSS 类名 | 全库 grep 出 200 行 | `grep -rn -m 5 "字面量" --include='*.py' .` 或 `… \| head -40` |
| 读文件 | 无 `limit` 整读 | `grep -n "关键字" f` → `read f offset=N limit=40` |
| 跑测试 | `-v` 直出全量 | `… > run-logs/<段>-<时间戳>.log 2>&1; grep -E '^(OK\|FAILED\|Ran )' <log>` |
| 看日志 / 后台作业 | `cat run.log`；整段 `job_output` | `grep -n "ERROR\|Traceback" run.log \| tail -20`；后台作业**先落盘再 grep** |

### R2 互不依赖的调用同步发

一步发 2–4 个互不依赖的 `read`/`grep`/`bash`/`codegraph`。
- **可核对阈值：单调用步 ≤40%**——`session_cost.py` 的「批处理率」一行给出，`--check` 也判。
- **中途体检**：完成首个交付物后、开始收尾前各跑一次 `session_cost.py --check`（一行，约 60 字符）。
- 有依赖必须串行，别为凑批处理猜后一步参数。

### R3 长会话分段（>60 步 或 上下文 >120k tokens）

**事件触发，别靠自觉记步数**：`--check` 出现「必须落盘交接并换会话」，或全量测试前发现 >60 步 / 上下文 >120k，就停下写交接、换新会话。交接文件 `docs/compose/reports/handoff-<YYYY-MM-DD>-<主题>.md` 五段：目标与验收（含判据命令）/ 已完成（`文件:行` + 证据：测试 Ran N / 数据）/ 未完成下一步（可直接粘贴的第一条命令）/ 关键事实（端口、账号、契约、已绿测试段）/ 不要重做（已排除假设与已跑命令）。

新会话开工只读这份交接 + 相关分卷章节，**不要**重读整个仓库——这是把 260k 上下文换成 5k 文档的地方。

- **批次边界就是会话边界（2026-10-10 实测，优先级高于步数阈值）**：B1–B9 九批在同一会话跑完 → `Σctx` 515.7M；每批在新会话开工的反事实成本 **137.9M**，即 **377.7M（73%）纯粹是继承上下文的重发**。所以：**一个 goal 不得跨批**（`create_goal` 的 `max_goal_rounds` 按单批预算设，建议 ≤3；本次设 40 → 9 次 `<goal_round>` 自动续跑，把 60 步预算拖成 1247 步）；每批收尾 `--check` 一旦给出交接信号，**本轮即停**，下一批在新会话开工（每批的 brief / handoff 就是下一批的唯一依据）。

### R4 大文件写入集中到会话后段

`write`/`edit` 的返回会**回显改动后的文件内容（hashline 全文）**，直接进上下文。`render.py`(334KB) 这类大文件：多锚点一次批量改完（别「改一处 → 跑一遍 → 再改一处」）；尽量放在会话后段；只读检查用 `read offset/limit`，别为了「拿锚点」而整读。

### R5 收尾自查

```bash
venv/bin/python scripts/agent/session_cost.py --last 1    # 本会话完整报告（超标逐条列出）
venv/bin/python scripts/agent/session_cost.py --check     # 一行体检（中途/收尾都跑）
venv/bin/python scripts/agent/session_cost.py --all       # 全部会话汇总；--selftest 工具自测
# 收尾取证「一次批量发」：把测试 + codegraph status + git diff --stat + --check 串成一条 bash
python -m unittest discover -s tests/ -t . -v > run-logs/final-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran )' run-logs/final-<时间戳>.log
codegraph status | tail -3; git diff --stat
venv/bin/python scripts/agent/session_cost.py --check
venv/bin/python scripts/agent/cleanup_tmp.py --apply      # 批量命令末行：统一清理临时产物
```

超标不必道歉，但要在**收尾简报里报数字**，并把可复用教训写进 `MEMORY.md`（硬性 #7）。


## 三、反向结论：别在 output 上抠门

output 只占 0.58%。所以：

- **推理、写 TODO、写清问题定义极便宜**——该想清楚就想清楚，该问就问（`ask_user_question` 几百 tokens，远低于一次错误实现）。
- 反之，为「省字」而含糊其辞、猜用户意图、少写验收标准 → 返工至少多 10 步 = 16 万 tokens 起。
- 真正昂贵的是**把大段内容灌进历史**：大返回、整卷文档、全库 grep。

## 四、与其他条款的关系

- 硬性 #20（AGENTS.md §1）的五条即本卷 R1–R5 的入口；本卷只展开「一次往上下文里塞多少」，R1 的落盘模板 = 09 卷「验证与汇报纪律」。
- 同一测试段上限 2 次见硬性 #14，两者独立计数、同时适用；硬性 #18 codegraph 优先不变（既是正确性纪律，也是 R1 的第一号手段）。

