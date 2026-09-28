> 状态: 生效

# 本项目 spec / plan 存储路径与格式约定（项目初始化）

> 取代关系: 本设计不取代任何既有 spec；与既有过程稿（`ui-redesign*.md`、`cache-write-test-scenarios.md`）并存，历史稿不追溯改造。

## 1. 背景与冲突识别

本项目存在两套文档体系的潜在冲突，本设计逐条裁决：

| # | 冲突点 | 来源 A（本项目既有） | 来源 B（全局/技能默认） | 裁决 |
|---|--------|----------------------|--------------------------|------|
| 1 | spec 路径 | `docs/compose/spec/`（历史 6 份 spec 所在） | `docs/superpowers/specs/`（brainstorming 技能与全局 AGENTS.md 默认） | **A 胜**：统一 `docs/compose/spec/`，`docs/superpowers/` 永不创建 |
| 2 | plan 路径 | 历史无独立 plan 目录（过程稿约定「落盘于 `docs/compose/`」） | `docs/superpowers/plans/` | **新定**：`docs/compose/plan/`（与 spec 单复数一致） |
| 3 | spec 状态头 | YAML frontmatter 与 `> 状态：` 行并存 | 全局 AGENTS.md「spec 状态头必写」格式 | **B 胜（仅新 spec）**：新 spec 必写全局状态头；历史 spec 不追溯 |
| 4 | 开工查证入口 | `docs/compose/knowledge/INDEX.md`（模块/路由/共享语义） | 全局要求查 `docs/INDEX.md` 或 specs 列表 | **不建新索引**：查证 = `ls docs/compose/spec/` + 读状态头；`knowledge/INDEX.md` 职责不变 |
| 5 | git 提交 | `.gitignore` 忽略整个 `docs/`（「本地使用，不提交」） | 技能要求「spec 写完提交 git」 | **用户裁决：`docs/` 整体从忽略名单移除**，存量一次性入库 |
| 6 | 文档冗余 | 知识库 `docs/compose/knowledge/` 为现状事实唯一来源 | spec/plan 易复制现状内容 | **职责分离**：spec 只写决策与理由，plan 只写执行账本，现状事实一律链接知识库 |

裁决依据：全局 AGENTS.md 裁决顺序（用户当次指示 > 项目 AGENTS.md > 生效 spec > 旧 spec > plan）。用户当次指示（2026-09-28）明确了「路径/格式遵循项目 AGENTS.md、避免冗余、docs 整体入库」三条。

## 2. 职责分工与目录结构（已确认 §1）

| 目录 | 职责 | 生命周期 | 冗余红线 |
|------|------|----------|----------|
| `docs/compose/spec/` | 任务时点的设计决策（为什么这样设计、取代链） | 一次性写定；被推翻时标「已被取代」，永久留档 | 禁止复制知识库内容；只写决策与理由，不写现状事实 |
| `docs/compose/plan/` | 实施计划（分步任务、验收、文件清单），每份 plan 对应一份 spec | 随实施完成即终态 | 只引用 spec 与知识库，不复述其内容 |
| `docs/compose/knowledge/` | 与代码同步的现状事实（AGENTS.md #7 唯一知识库入口） | 活文档，随代码同任务内同步 | spec/plan 不承担现状同步；代码落地后的事实回写知识库 |
| `docs/compose/reports/` | 交付报告（既有惯例，不动） | 交付即定稿 | — |

- `docs/superpowers/` **永不创建**；brainstorming / writing-plans 技能的默认路径在本项目被项目 AGENTS.md 新节显式覆盖。
- `docs/compose/plan/` 为空时 git 不跟踪，随首个 plan 文件自然入库。

## 3. spec 格式规范（已确认 §2）

**命名**：`docs/compose/spec/YYYY-MM-DD-<主题>-design.md`（历史 spec 不改名）。

**新 spec 顶部必写**（逐字采用全局 AGENTS.md 格式）：

```markdown
> 状态: 生效 | 已被 <新spec文件名> 取代
> 取代日期: YYYY-MM-DD（仅当已取代时写）
> 取代原因: 一句话（仅当已取代时写）
```

**取代两头改规则**：新设计 B 推翻旧设计 A 时，必须同时 ① 改 A 的状态头为「已被 B 取代」+ 日期 + 原因；② 在 B 中写 `取代关系: 本设计取代 <A文件名> 的 <部分/全部>`。只改新不改旧 = 未完成。

**历史 6 份 spec 不追溯**：不补状态头、不改名；状态以文件内既有 `status:` / `> 状态：` 行为准（如 `ui-redesign.md` 标 `delivered`）。开工查证读到旧格式时，按全局裁决顺序处理并在新 spec 记录裁决结果。

**冗余红线**：spec 正文不复制路由表 / 共享语义等现状事实，需要时链接 `../knowledge/INDEX.md` 对应小节；UI 类 spec 的可交互确认稿 HTML 仍按既有惯例放 `docs/compose/spec/` 同目录（AGENTS #11 确认稿不进 `static/`）。

## 4. plan 格式规范（已确认 §3）

**命名**：`docs/compose/plan/YYYY-MM-DD-<主题>-plan.md`，与对应 spec 同日期同主题，一一对应。

**模板**（writing-plans 技能产出直接落此格式）：

```markdown
# <主题> 实施计划

> 状态: 待执行 | 执行中 | 已完成 | 已作废（被 <原因> 取代）
> 对应 spec: ../spec/YYYY-MM-DD-<主题>-design.md
> 最后更新: YYYY-MM-DD

## 任务清单
- [ ] T1 <任务>（文件: 函数 / 验收标准 / 测试命令）
## 验证计划
- L0/L1/L2 各段命令与预期（对齐 AGENTS.md 测试策略）
## 执行记录
- （执行中回填：完成的任务、偏差、测试证据行）
```

**规则**：plan 是执行账本（checkbox + 证据回填），不复述 spec 决策理由；实施中发现需改设计 → 回到 spec 走取代/修订流程，不在 plan 里私改设计。plan 完成后状态置「已完成」并保留，作为下次任务的进度面。多步任务用 AGENTS.md 的 Task/清单机制时，plan 文件是其落盘副本。

## 5. AGENTS.md 增补与开工查证（已确认 §4）

在项目 `AGENTS.md`「项目知识库」一节之后新增「**spec / plan 存储与格式约定**」一节，内容五块：

1. **路径唯一性**：spec=`docs/compose/spec/`、plan=`docs/compose/plan/`；禁止创建 `docs/superpowers/`，skill 默认路径被本节覆盖；`docs/compose/knowledge/` 只归 #7 知识库，两边不互相存放。
2. **格式要求**：spec 状态头模板 + 取代两头改；plan 模板与状态；历史 spec 不追溯的例外说明。
3. **开工查证（替代全局 `docs/INDEX.md` 入口）**：接新任务 → `ls -t docs/compose/spec/` 取最新 → 读状态头找生效版 → 与任务冲突时按全局裁决顺序处理并在新 spec 记录裁决结果。`knowledge/INDEX.md` 只管模块/路由/共享语义，不是任务查证入口。
4. **冗余红线**：spec/plan 引用知识库不复制；代码落地后的事实回写知识库（#7 同步义务不因有 spec 而豁免）。
5. **git 说明**：`docs/` 已从 `.gitignore` 移除，spec/plan/知识库随任务正常提交；`__pycache__` 等生成物仍被既有规则忽略。

同时在「硬性约束」#7 或「收尾检查单」补一行指针：「新任务先查 spec 生效版，见『spec / plan 存储与格式约定』」——只一行，不重复内容。

## 6. 变更清单与验证（已确认 §5）

**文件变更（全部在本仓库内）**：

| 动作 | 内容 |
|------|------|
| 改 `.gitignore` | 仅删除 `docs/` 一行（`# 文档与规范（本地使用，不提交）` 注释下；`SPEC.md`、`spec.md`、`CONTEXT.md` 保持忽略） |
| 改 `AGENTS.md` | 新增「spec / plan 存储与格式约定」一节 + #7/检查单一行指针 |
| 建目录 | `docs/compose/plan/`（本次初始化的 plan 即首个文件） |
| 写 spec | 本文件 |
| 写 plan | `docs/compose/plan/2026-09-28-docs-spec-plan-conventions-plan.md` |
| 提交 | 只提交 `docs/` 存量与新增 spec/plan；`AGENTS.md` 保持忽略不入库 |

**验证（绿了才报完成）**：

1. `git check-ignore AGENTS.md` 仍命中（未误伤）；`git check-ignore docs/compose/spec/<本文件>` 不再命中；
2. `git status --short docs/` 显示存量 + 新增待提交清单，无 `__pycache__` / `.pyc`；
3. `git add -A docs/ && git status` 复核暂存区；提交说明用简体中文，提交前给用户过目；
4. 约定生效自检：AGENTS.md 新节可 grep 到；spec/plan 文件存在且状态头 / 状态行合规。

## 7. 非目标（YAGNI）

- 不迁移、不改名、不补状态头历史 spec；不动 `knowledge/` 与 `reports/` 的既有结构。
- 不建 `docs/INDEX.md` 总索引、不建 `docs/superpowers/`、不引入文档生成工具。
- 不改 AGENTS.md 中与本文无关的任何既有条款；不放开 `AGENTS.md` 本身的 git 忽略。
