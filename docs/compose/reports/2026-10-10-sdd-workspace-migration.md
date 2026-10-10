# SDD 工作区（`.superpowers/`）成因分析与迁移（2026-10-10）

> 状态: 生效
> 用户指示：`.superpowers/` **不单独出现**，以 `docs/compose/` 作为起点；做好迁移、入口引用切换与后续约束。

## 1 结论

仓库根 `.superpowers/` 是**第三方技能自带的过程工作区**，不是本项目文档体系的一部分。
本任务已把其中有长期价值的经验提炼进本报告，删除过程产物与目录本体，并在 `AGENTS.md` §3 增加约束，禁止其作为交付物存在。

## 2 成因（实测，非推测）

| 事实 | 证据 |
|------|------|
| 由全局安装的 superpowers 技能 `subagent-driven-development`（SDD）生成 | `/root/.dsh/skills/subagent-driven-development/SKILL.md` §workspace |
| 路径 `.superpowers/sdd/<plan-basename>/` **硬编码在技能脚本内** | `scripts/sdd-workspace:46` → `base="$root/.superpowers/sdd"`；`scripts/task-brief:7`、`scripts/review-package:8` 同源 |
| **无环境变量或配置可改**该路径（脚本不读任何 `SDD_*`/`SUPERPOWERS_*`） | `grep -n "SDD_\|SUPERPOWERS_\|getenv" sdd-workspace` → 无命中 |
| 设计上就不入 git：脚本自写 `.superpowers/sdd/.gitignore`（内容仅 `*`） | `scripts/sdd-workspace` 末段 `printf '*\n' > "$base/.gitignore"` |
| 本项目仅**追加**忽略了根目录 | `.gitignore:87` `.superpowers/`（原由 2026-10-09 临时产物生命周期任务加入） |

**为什么它会「单独出现」**：SDD 流程把任务简报（`task-N-brief.md`）、子代理报告（`task-N-report.md`）、
审查包（`review-<base7>..<head7>.diff`）与进度账本（`progress.md`）都落在这个固定 scratch 路径下，
与项目约定的 `docs/compose/{spec,plan,reports}` 无关——于是就出现了「仓库根多出一个文档类目录」的现象。

## 3 本次残留内容与处置

处置前该目录仅存**一份已交付 plan 的过程产物**：
`docs/compose/plan/2026-10-09-temp-artifact-lifecycle-plan.md`（其产物 `scripts/agent/cleanup_tmp.py`、
`tests/test_temp_log_policy.py` 均已入库，门禁 GREEN）。

| 文件 | 性质 | 处置 |
|------|------|------|
| `progress.md` | 执行账本（批次/裁定/进度） | 删除；裁定要点见 §4 |
| `task-1-brief.md` … `task-4-brief.md` | 任务简报（过程分派稿） | 删除（其依据 = 上述 plan 与 spec，仍可复现） |
| `task-1-report.md`、`task-2-report.md` | 子代理交付报告 | 删除；可复用经验见 §4 |
| `review-052c5b8..492005f.diff` 等 3 份 | 审查包（提交区间 diff） | 删除；**均可由 git 历史复现**：`25c41d1`、`b65289a`、`4a61caa`、`052c5b8`、`492005f` 五个提交均在库 |
| `plan-path` 标记 | 工作区归属标记 | 删除 |
| `.gitignore`（仅 `*`） | 技能自写 | 删除 |

> 删除理由：这些是**过程产物**而非交付物；其结论与数值在本报告 §4 与既有
> `docs/compose/reports/` 中已沉淀，原始 diff 可由 git 复现，不存在断层。

## 4 从过程产物中提炼的长期经验（唯一应留存的部分）

1. **白名单必须词法锚定仓库根**：`cleanup_tmp.py` 第一版把受管根 `realpath` 化，导致
   `run-logs -> 仓库外` 与 `run-logs -> 仓库根自身` 两种符号链接逃逸都能删到受管范围外
   （修复轮 `052c5b8`）。正确做法：只对**仓库根**取 `realpath`，受管目录名**词法拼接**，
   收集谓词与 `rmdir` 爬升**共用同一锚定函数**，两者不可能各说各话。
2. **dry-run 要有零副作用自证**：dry-run 分支末尾显式再 `lexists` 一遍候选文件，
   只要有一个消失就报错退出——把「只报告不删除」变成可断言的事实，而不是口头承诺。
3. **门禁与存量梳理必须同批提交**：先建门禁会立刻让默认 `discover` 变红；
   正确次序是「建门禁并取证 RED → 改文档 → 确认 GREEN → 一次性提交」，避免红窗口期
   让并发代理撞上假失败。
4. **计划/spec 自身也在扫描集内**：新增文档门禁时，被门禁扫描的文档自身含违规样例
   会「自伤」（本次靠掩码 `<时间戳>`/`<序号>`/`*` 与 `$D` 变量解决）。

## 5 迁移与约束

### 5.1 迁移动作

- 过程产物按 §3 处置，**目录本体删除**（仓库根不再出现 `.superpowers/`）。
- 有长期价值的经验落本报告（§4），位置符合「依据类结论落 `docs/compose/reports/`」既有约定。
- `.gitignore:86-87` 的 `.superpowers/` 条目保留：它是**第三道防线**（防止将来再跑 SDD 时
  过程产物被误提交），注释同步改为指向本报告。

### 5.2 后续约束（写入 `AGENTS.md` §3）

> SDD / 任何流程技能的过程产物**不得作为交付物留在仓库根**：`spec`、`plan`、`reports`
> 一律以 `docs/compose/` 为起点；过程产物跑完即归档（结论进 `docs/compose/reports/`）后删除。

**已知限制**：技能脚本硬编码该路径且无覆盖钩子，**下次跑 SDD 仍会重新生成 `.superpowers/`**。
因此约束的形态是「跑完即清、结论归档」，而非「永不出现」；`.gitignore` 条目兜底防误提交。

## 6 验收

| 项 | 命令 | 结果 |
|---|---|---|
| 目录已删除 | `ls -d .superpowers` | 不存在 |
| 忽略兜底仍在 | `git check-ignore -v .superpowers/sdd/x` | 命中 `.gitignore` 条目 |
| 文档门禁 | `venv/bin/python -m unittest tests.test_doc_budget tests.test_temp_log_policy -v` | 全绿 |
| 全量 | `venv/bin/python -m unittest discover -s tests/ -t . -v` | 全绿 |
