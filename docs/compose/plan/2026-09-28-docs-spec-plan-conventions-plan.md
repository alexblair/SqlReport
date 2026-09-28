# 文档约定初始化（spec/plan 落位 + docs 入库）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地本项目 spec/plan 存储与格式约定——放开 `docs/` 入库、AGENTS.md 新增约定节、存量文档一次性提交。

**Architecture:** 三个独立小任务顺序执行：① `.gitignore` 精确删除一行 → ② `AGENTS.md` 新增一节 + 一行指针 → ③ 暂存并提交 `docs/`（含存量与新 spec/plan）。无生产代码变更，验证全部用 `git check-ignore` / `grep` / `git status` 断言。

**Tech Stack:** 纯文本编辑 + git；无依赖安装、不触碰 `venv`、不跑测试套件（无代码变更，L0 级验证 = 下列断言命令）。

**Spec:** `docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md`

## Global Constraints

- 全部产出文字用简体中文（AGENTS #2）。
- `.gitignore` **只删除 `docs/` 一行**；同注释块下 `SPEC.md`、`spec.md`、`CONTEXT.md` 必须保持忽略；其它任何忽略行不动。
- `AGENTS.md` 本身保持 git 忽略、**不入库**（spec §6/§7）。
- 禁止创建 `docs/superpowers/` 目录（spec §2）。
- 历史 spec（`ui-redesign*`、`cache-write-test-scenarios.md`）与 `knowledge/`、`reports/` **一律不改**（spec §3/§7）。
- 提交前必须把提交说明给用户过目（spec §6 验证 3）。

## Review Focus

1. **误放开非目标忽略文件**：改完 `.gitignore` 后 `SPEC.md`/`CONTEXT.md` 应仍被忽略、`docs/` 不再被忽略——若 `git check-ignore docs/...` 仍命中或 `SPEC.md` 不再命中，说明删错行。→ Task 1 Step 3 双向断言。
2. **`AGENTS.md` 被意外入库**：约定节写完后 `AGENTS.md` 必须仍被忽略且不在暂存区——否则本地代理指引泄漏进仓库。→ Task 3 Step 1、Step 3 断言。
3. **生成物混入提交**：`docs/compose/spec/__pycache__/*.pyc` 若出现在 `git status`，说明 `__pycache__/` 全局规则失效或被绕过——入库即污染。→ Task 3 Step 1 断言。
4. **新节破坏 AGENTS.md 既有结构**：约定节必须插在「项目知识库」一节之后、「环境与命令」之前；插错位置会让读者在架构章节前突然遇到文档约定。→ Task 2 Step 3 位置断言。
5. **指针行与新节重复成冗余**：#7 或检查单的指针只能是一行路径引用，不得复述约定内容（违背 spec §5 冗余红线）。→ Task 2 Step 4 断言行数与内容。

---

### Task 1: `.gitignore` 放开 `docs/`

**Files:**
- Modify: `.gitignore`（`# 文档与规范（本地使用，不提交）` 注释块内的 `docs/` 行，约 L49）

**Interfaces:**
- Consumes: 无
- Produces: `docs/` 不再被 git 忽略——Task 3 的 `git add docs/` 依赖此状态；`AGENTS.md`、`SPEC.md`、`spec.md`、`CONTEXT.md` 的忽略状态不变。

- [ ] **Step 1: Read 定位目标行**

Read `.gitignore` 的「# 文档与规范」注释块，确认块内四行为 `docs/`、`SPEC.md`、`spec.md`、`CONTEXT.md`，记录 `docs/` 行的逐字上下文（含前后各一行）。

- [ ] **Step 2: 精确删除 `docs/` 行**

用 edit：`old_string` 取 Read 输出中含 `docs/` 的那一行（含换行），`new_string` 为空。失败 1 次即换更小锚点（AGENTS #16③），禁止原样重试。

- [ ] **Step 3: 双向断言**

```bash
cd <仓库根> && git check-ignore docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md; echo "exit=$?"
git check-ignore AGENTS.md SPEC.md spec.md CONTEXT.md; echo "exit=$?"
```
Expected: 第一条 `exit=1`（docs 已放开）；第二条 `exit=0` 且输出含全部四个文件名（AGENTS.md 等仍被忽略）。任一不符 → 回到 Step 2 换锚点修正，不进入 Task 2。

---

### Task 2: `AGENTS.md` 新增「spec / plan 存储与格式约定」节

**Files:**
- Modify: `AGENTS.md`（「项目知识库」一节末尾之后、「## 环境与命令」之前；#7 硬性约束行内加指针；「收尾检查单」加一行）

**Interfaces:**
- Consumes: spec §5 的五块内容清单、§3/§4 的格式模板（内容以 spec 为准，此处不复述）
- Produces: 约定节标题 `## spec / plan 存储与格式约定`——Task 3 提交说明需引用此节名。

- [ ] **Step 1: Read 定位三处插入点**

Read `AGENTS.md`，定位：① 「## 项目知识库」一节的结束行（紧邻 `## 环境与命令` 之前）；② 硬性约束 `7. **知识库入口与自动同步**` 行；③ 「收尾检查单」小节（`### 3. 收尾检查单`）。记录三处逐字锚点（≤3 行）。

- [ ] **Step 2: 写入约定节**

用 edit 在「## 环境与命令」标题前插入新节 `## spec / plan 存储与格式约定`，按 spec §5 五块组织（路径唯一性 / 格式要求 / 开工查证 / 冗余红线 / git 说明），格式模板引用 spec §3、§4（`见 docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md §3/§4`），不整段复制模板正文——复制即冗余（spec §5 冗余红线）。文字全中文。

- [ ] **Step 3: 位置断言**

```bash
grep -n -E '^## (项目知识库|spec / plan 存储与格式约定|环境与命令)' AGENTS.md
```
Expected: 三行（实际标题为 `## 项目知识库（主动阅读 + 变更后同步）` / `## spec / plan 存储与格式约定` / `## 环境与命令`）按行号递增顺序出现，无缺失。不符 → 换锚点修正。

- [ ] **Step 4: 写入指针（一行，不复述内容）**

用 edit：① 在硬性约束 #7 行尾追加 `（新任务先查 spec 生效版，见「spec / plan 存储与格式约定」）`；② 在收尾检查单加一行 `3. **spec 查证**：确认本次任务已按「spec / plan 存储与格式约定」查过生效 spec（有则核对，无任务型改动则注明不适用）。`

断言：
```bash
grep -c 'spec / plan 存储与格式约定' AGENTS.md
```
Expected: ≥3（节标题 1 次 + 指针 2 次）。同时目视确认指针行无约定内容复述（仅路径/节名引用）。

---

### Task 3: 存量与新文档入库提交

**Files:**
- Create（已存在，本 plan 即首个文件）: `docs/compose/plan/2026-09-28-docs-spec-plan-conventions-plan.md`
- 提交范围: `docs/` 全部（knowledge / spec / plan / reports）

**Interfaces:**
- Consumes: Task 1 的 `docs/` 放开状态；Task 2 的约定节名（用于提交说明）
- Produces: 一次 git 提交，包含存量知识库、历史 spec、本 spec 与本 plan。

- [ ] **Step 1: 暂存前断言（三个一起）**

```bash
cd <仓库根> && git status --short docs/ | grep -E '__pycache__|\.pyc' ; echo "pyc=$?"
git check-ignore AGENTS.md; echo "agents=$?"
git status --short docs/ | head -30
```
Expected: `pyc=1`（无生成物）、`agents=0`（AGENTS.md 仍忽略）、第三条列出 docs 下待提交清单（存量 + 新 spec + 新 plan）。`pyc≠1` → 先核对 `.gitignore` 的 `__pycache__/` 规则，禁止带 pyc 提交。

- [ ] **Step 2: 暂存并复核暂存区**

```bash
git add -A docs/ && git status --short --cached | head -40 && git status --short --cached | grep -E 'AGENTS|__pycache__|\.pyc'; echo "leak=$?"
```
Expected: `leak=1`（暂存区无 AGENTS / pyc / pyc 文件）；暂存清单与 Step 1 一致。

- [ ] **Step 3: 提交说明给用户过目（硬门）**

拟简体中文提交说明（例：`docs: 建立 spec/plan 存储与格式约定，docs 整体入库`），用 ask_user_question 请用户确认后才执行 Step 4；未获确认不提交。

- [ ] **Step 4: 提交并终验**

```bash
git commit -m "<用户确认的说明>" && git status --short docs/ | head; echo "clean=$?"
git ls-files AGENTS.md | head -1; echo "tracked=$?"
```
Expected: 提交成功；`clean=0` 后无 docs 残留（或仅剩被忽略生成物）；`tracked=1`（AGENTS.md 未被跟踪）。

- [ ] **Step 5: 约定生效自检（收口）**

```bash
grep -n 'spec / plan 存储与格式约定' AGENTS.md | head -3
head -1 docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md
ls docs/compose/plan/
```
Expected: AGENTS.md 新节可 grep 到；spec 首行 `> 状态: 生效`；plan 目录含本文件。三项全过 → 输出【任务完成】+ 简报（AGENTS #16⑦）。
