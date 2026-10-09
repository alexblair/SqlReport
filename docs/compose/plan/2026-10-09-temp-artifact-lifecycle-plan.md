# 临时产物生命周期与「依据分层」实施计划

> 状态: 待执行
> 对应 spec: ../spec/2026-10-09-temp-artifact-lifecycle-design.md
> 最后更新: 2026-10-09

**For agentic workers:** 按任务顺序执行（Task 1→5）；每步一个动作、带可核对结果。步骤用 `- [ ]` 跟踪。

**目标**：临时产物（`run-logs/`、`perf-logs/`）在任务整体完成时被一次清理；依据类内容一律落 `docs/compose/reports/`；文档引用临时产物的断层由静态门禁拦住。

**架构**：① 一个纯标准库清理工具，挂进既有收尾批量命令（零增步）；② 一条文档门禁（照 `tests/test_doc_budget.py` 的 `_load_docs()` + 纯函数 `_violations()` 模式）；③ 一次存量引用梳理。

**技术栈**：Python 3 标准库 · `unittest`（`discover -s tests/ -t .`）· codegraph（改 `.py` 后 `sync`）。

## 全局约束

- 一切测试/运行在仓库根 `venv` 内；`discover` 必须带 `-t .`。
- 纯标准库，不新增依赖；不引入 cron/systemd/hook（spec §5）。
- 临时产物仍只落 `run-logs/`、`perf-logs/`；清理**只能**通过 `scripts/agent/cleanup_tmp.py`（人工 `rm` 仍禁止）。
- 用户可感知文字一律简体中文。
- 每步验证后提交；提交信息用中文。

## 评审重点（spec 隐含、但没有任务直接测到的失效模式）

1. `run-logs/` 内有**符号链接**指向仓库外 → 清理工具不得删除仓库外文件（Task 1 的 symlink 断言）。
2. 目标目录**不存在** → 工具必须幂等退出 0，不得报错（Task 1）。
3. 另一个 agent **正在写**日志（mtime 新）→ 必须跳过并在 `kept` 中列出（Task 1）。
4. **dry-run 必须零副作用**（默认不带 `--apply` 不得删任何东西）（Task 1）。
5. 文档写「落 `run-logs/`。」这类**中文标点紧跟目录名**的形态 → 门禁不得误报（Task 2）。
6. `AGENTS.md`/`MEMORY.md` 在别的克隆机上**缺失** → 门禁不得因 `FileNotFoundError` 变红（Task 2）。

---

### Task 1: 清理工具 `scripts/agent/cleanup_tmp.py`

**Files:**
- Create: `scripts/agent/cleanup_tmp.py`

**Interfaces:**
- Produces（后续任务与文档引用这些确切名字）：
  - `TEMP_DIRS: tuple[str, ...] = ("run-logs", "perf-logs")`
  - `def repo_root() -> Path`（由 `__file__` 上溯到仓库根）
  - `def collect(dir_path: Path) -> list[tuple[str, float]]`（递归收集「绝对路径, mtime」；`os.walk(followlinks=False)`；丢弃符号链接与 `realpath` 不在 `dir_path` 内的条目）
  - `def split_active(records: list[tuple[str, float]], now: float, window: float, force: bool) -> tuple[list[str], list[str]]`（返回 `(可删, 保留)`）
  - `def delete_entries(paths: list[str]) -> tuple[int, int]`（返回「删除文件数, 释放字节」，目录自底向上删空）
  - `def _selftest() -> int`、`def main(argv: list[str] | None = None) -> int`
  - CLI：`--apply` / `--force` / `--active-window SEC`（默认 600）/ `--selftest` / `--quiet`
  - 末行输出：`cleaned {n} files / {mb:.1f} MB; kept {k} active`（dry-run 时前缀 `[dry-run] `）

- [ ] **Step 1: 先写自测（RED）**

在 `scripts/agent/cleanup_tmp.py` 中先只写 `_selftest()` 与 CLI 骨架，断言六条（后两条用标准库 `tempfile.mkdtemp()` 建真实临时目录）：
① `split_active` 在 `window` 内保留、窗口外可删；② `force=True` 时全部可删；③ 空输入返回两个空列表；④ `collect` 对不存在的目录返回 `[]`；⑤ `collect` **丢弃符号链接**与其 `realpath` 不在目标目录内的条目；⑥ `delete_entries` 删完返回「文件数 > 0」且二级目录被清空。

- [ ] **Step 2: 跑自测确认失败**

Run: `venv/bin/python scripts/agent/cleanup_tmp.py --selftest`
Expected: 非 0 退出（函数未实现）

- [ ] **Step 3: 实现 `repo_root` / `collect` / `split_active` / `delete_entries`**

要点：`now` 由调用方传入（便于自测）；`window` 只与 mtime 比较；symlink 与越界 `realpath` 在 `collect` 阶段就丢弃。

- [ ] **Step 4: 实现 `main`（argparse + dry-run 默认 + 输出行）**

`--apply` 才真删；`--selftest` 直接返回 `_selftest()`；任何 `OSError` 记 1 行错误并返回 1，不抛栈。

- [ ] **Step 5: 自测转绿**

Run: `venv/bin/python scripts/agent/cleanup_tmp.py --selftest`
Expected: `[OK] selftest 通过（N 项断言）`，退出 0

- [ ] **Step 6: 验活跃保护与幂等（用临时子目录，不碰真身）**

Run:
```bash
D=perf-logs/_t; mkdir -p $D && date > $D/fresh.log && touch -d '2 hours ago' $D/old.log
venv/bin/python scripts/agent/cleanup_tmp.py            # dry-run：预期 0 删除（验证零副作用）
ls $D                                                                                 # 预期：old.log / fresh.log 都还在
venv/bin/python scripts/agent/cleanup_tmp.py --apply    # 预期：old.log 被删、fresh.log 进 kept
venv/bin/python scripts/agent/cleanup_tmp.py --apply    # 预期：cleaned 0 files / 0.0 MB; kept 1 active（fresh.log 仍在活跃窗口内）
touch -d '2 hours ago' $D/fresh.log
venv/bin/python scripts/agent/cleanup_tmp.py --apply    # 预期：cleaned 1 files; kept 0 active
```
Expected: dry-run 后两个文件仍在；第一条 `--apply` 输出含 `kept 1 active` 且只删 `old.log`；第二条 `cleaned 0 files`；最后一条删掉 `fresh.log`；全部退出 0

- [ ] **Step 7: 提交**

```bash
git add scripts/agent/cleanup_tmp.py
git commit -m "feat(agent): 临时产物清理工具（活跃写入保护 + 幂等 + 自测）"
```

---

### Task 2: 断层门禁 `tests/test_temp_log_policy.py`（先 RED）

**Files:**
- Create: `tests/test_temp_log_policy.py`

**Interfaces:**
- Consumes: 无
- Produces（Task 5 的 `gate_redproof` 依赖这些确切名字）：
  - `REF_RE = re.compile(r"(?:run-logs|perf-logs)/([A-Za-z0-9_./<>*\-]*)")`
  - `ALLOWED: tuple[tuple[str, str], ...]`（每条 `(相对目录后的片段, 理由)`；**至多 3 条**，当前 2 条：`bench-credentials.txt`、`probe/verify.debug.json`）
  - `def _load_docs() -> dict[str, str]`（唯一读盘入口，键为仓库相对路径，缺失文件跳过）
  - `def _violations(docs: dict[str, str]) -> list[tuple[str, int, str]]`（纯函数，返回 `(文件, 行号, 命中引用)`）
  - 用例：`tests.test_temp_log_policy.TestTempLogPolicy.test_no_concrete_temp_artifact_refs`（gate_redproof 用它）、`test_allowlist_is_minimal`、`test_chinese_punctuation_not_flagged`、`test_missing_docs_tolerated`

- [ ] **Step 1: 写测试（RED）**

扫描集：`AGENTS.md`、`MEMORY.md`、`docs/**/*.md`、`learn/**/*.md`。放行条件（与 spec §3.3 一致）：片段含 `<` 或 `*`；或为空 / 以 `/` 结尾 / 以 `-` 结尾；或命中后一个字符是 `$`；或最后一段不含 `.`（目录引用）；或在 `ALLOWED` 中。失败信息格式 `file:line → 引用 → 建议改法`。

- [ ] **Step 2: 跑测试确认 RED，并记录条数**

Run: `venv/bin/python -m unittest tests.test_temp_log_policy -v`
Expected: `test_no_concrete_temp_artifact_refs` **FAIL**，命中 **25** 条 / 8 个文件（`08-testing-conventions.md:327`、`2026-09-29-execution-layer-performance-plan.md:507,544`、`2026-09-30-write-report-cache-gate-plan.md:375,376`、`2026-10-05-cache-source-label-plan.md:483,489,496,502,562,567,586,610`、`2026-10-06-token-efficiency-retrospective.md:32`、`2026-09-29-execution-layer-performance-design.md:295`、`2026-10-09-temp-artifact-lifecycle-design.md:36,37,38,40,132`、`course-state.md:110`）

- [ ] **Step 3: 补三条护栏用例并转绿（除主用例外）**

`test_allowlist_is_minimal`（`len(ALLOWED) <= 3`）、`test_chinese_punctuation_not_flagged`（喂 `落 \`run-logs/\`。` 期望 0 命中）、`test_missing_docs_tolerated`（`_violations({})` 期望 `[]` 且不抛异常）。

Run: `venv/bin/python -m unittest tests.test_temp_log_policy -v`
Expected: 三条护栏用例 PASS；主用例仍 FAIL（等 Task 4）

- [ ] **Step 4: 暂不提交（避免红窗口）**

门禁落在 `tests/test_*.py`，会被默认 `discover` 收录。若此时提交，Task 3–4 完成前仓库一直是红的（并发代理会撞上假失败）。因此本任务**只写文件不提交**，证据（RED 命中 25 条）记在 §执行记录，与 Task 4 的梳理在 Task 4 Step 6 一并提交转绿。

---

### Task 3: 规则本体改写

**Files:**
- Modify: `AGENTS.md`（硬性 #14）
- Modify: `docs/compose/knowledge/09-agent-workflow.md`（§验证纪律 + 收尾）
- Modify: `docs/compose/knowledge/10-token-budget.md`（R3 交接换址；R5 批量命令追加清理调用）
- Modify: `docs/compose/knowledge/11-aoci-usage.md`（证据边界；§副本表第 15 行失效引用改写）
- Modify: `MEMORY.md`、`learn/sqlreport-kb/course-state.md`、`.gitignore`

**Interfaces:**
- Consumes: Task 1 的 `scripts/agent/cleanup_tmp.py`、`--apply`、`--active-window`；Task 2 的门禁语义（目录名/占位符合法）
- Produces: 规则条款文本（Task 4/5 的文档与简报引用它）

- [ ] **Step 1: 改 `AGENTS.md` 硬性 #14**

保留「日志与临时产物一律落仓库内已 gitignore 的 `run-logs/`/`perf-logs/`（本环境 `/tmp` 会被清空）、唯一文件名」；删除「**禁止 `rm`**」；新增：① 任务整体完成时由收尾批量命令调用 `venv/bin/python scripts/agent/cleanup_tmp.py --apply` 统一清理；② 任何作为依据/规则/知识沉淀的内容不得存放于临时目录，必须写入 `docs/compose/reports/`（结论 + 数值 + 复现命令）；③ 禁止人工 `rm`，清理只走该工具。

- [ ] **Step 2: 同步 `09-agent-workflow.md`**

§验证纪律（硬性 #14）与收尾章节：补「收尾清理」一步（指向 Task 1 工具），并写明依据类内容的归属（`docs/compose/reports/`）。

- [ ] **Step 3: 同步 `10-token-budget.md`**

R3 的交接落盘路径由 `run-logs/handoff/<YYYY-MM-DD>-<主题>.md` 改为 `docs/compose/reports/handoff-<YYYY-MM-DD>-<主题>.md`；R5 的收尾批量命令末行追加 `venv/bin/python scripts/agent/cleanup_tmp.py --apply`，并注明「0 额外轮次」。

- [ ] **Step 4: 同步 `11-aoci-usage.md`**

新增一条边界：AOCI Entry 的 F/R/A/S 与证据不得把 `run-logs/`、`perf-logs/` 下的产物作为长期依据（临时目录随时清空）；把「另一份副本」那行里的 `run-logs/aoci/extract/aoci` 改掉（该副本已不存在）。

- [ ] **Step 5: 同步 `MEMORY.md` / `learn/sqlreport-kb/course-state.md` / `.gitignore`**
`course-state.md:110` 里的过程脚本引用（`run-logs/repro_*.py`）改为不含临时路径的表述（该脚本按「产出者溯源」判为过程脚本、不提升）；`.gitignore` 注释补「可由 `scripts/agent/cleanup_tmp.py` 随时清空」；并把 `.superpowers/`（SDD 工作区，非交付物）加入 `.gitignore`。

- [ ] **Step 6: 门禁复跑（确认只降不升）**

Run: `venv/bin/python -m unittest tests.test_temp_log_policy -v`
Expected: 命中数 ≤ 25（`course-state.md:110` 已消）；主用例仍 FAIL

- [ ] **Step 7: 提交**

```bash
git add AGENTS.md docs/compose/knowledge/09-agent-workflow.md docs/compose/knowledge/10-token-budget.md docs/compose/knowledge/11-aoci-usage.md MEMORY.md learn/sqlreport-kb/course-state.md .gitignore
git commit -m "docs(rules): 硬性 #14 改为收尾统一清理，依据类内容强制落 reports/"
```

---

### Task 4: 存量引用梳理 → 门禁 GREEN

**Files:**
- Modify: `docs/compose/knowledge/08-testing-conventions.md`（口径 + 第 327 行）
- Modify: `docs/compose/spec/2026-09-29-execution-layer-performance-design.md`（第 295 行 + 状态头「取代两头改」）
- Modify: `docs/compose/plan/2026-09-29-execution-layer-performance-plan.md`、`docs/compose/plan/2026-09-30-write-report-cache-gate-plan.md`、`docs/compose/plan/2026-10-05-cache-source-label-plan.md`
- Modify: `docs/compose/reports/2026-10-06-token-efficiency-retrospective.md`
- Modify: `docs/compose/spec/2026-10-09-temp-artifact-lifecycle-design.md`（§2.2 表格掩码）
- Modify: `docs/compose/plan/2026-10-09-temp-artifact-lifecycle-plan.md`（本计划自身也在扫描集内：示例改用 `$D` 变量与掩码）

**Interfaces:**
- Consumes: Task 2 的 `_violations()` 与放行规则
- Produces: 门禁 GREEN（Task 5 依赖）

- [ ] **Step 1: 改历史证据引用（spec/plan/reports）**

原则：**保留结论与数值，删掉指向已消失文件的路径**；确需展示文件名时改占位符（`<时间戳>`、`<段名>`、`*`），并注明「原始日志为临时产物，已清理」。覆盖：`2026-09-29-execution-layer-performance-plan.md:507,544`、`2026-09-30-write-report-cache-gate-plan.md:375,376`、`2026-10-05-cache-source-label-plan.md:483,489,496,502,562,567,586,610`、`2026-10-06-token-efficiency-retrospective.md:32`、`2026-09-29-execution-layer-performance-design.md:295`（改为结论 + 复现命令）。改法统一：把 `perf-logs/`、`run-logs/` 后接的具体文件名换成占位符形态（如 `perf-logs/<段>-<序号>-<时间戳>.log`、`run-logs/accept-<序号>-<轮次>.html`）。

- [ ] **Step 2: 补「取代两头改」**

`2026-09-29-execution-layer-performance-design.md` 状态头加一行：`> 部分条款已被 2026-10-09-temp-artifact-lifecycle-design.md 取代（原始数据取证方式，2026-10-09）`。

- [ ] **Step 3: 改 `08-testing-conventions.md`**

第 327 行的样例脚本引用改写为不含临时路径的知识性描述；日志取证口径同步 Task 3 的 #14 新表述。

- [ ] **Step 4: spec 全文与计划自身掩码**

把 spec **全文**（§2.2 表格与 §7 第 5 项等）的具体产物名改为掩码形态（如 `perf-logs/baseline-<id>.json`、`run-logs/final-discover-<时间戳>.log`、`run-logs/sdd/<任务>/progress.md`、`run-logs/repro_*.py`），保持「断层样本」语义不变；**精确名字保留在本 spec 首个提交 `5455c0e` 的历史里**，不在正文钉住会消失的文件。本**计划文件自身**同样在扫描集内：确认 Task 1 Step 6 已用 `$D` 变量、Task 5 的注入串已用拼接、Task 3 的过程脚本引用已掩码，全文不再出现具体临时文件名。

- [ ] **Step 5: 门禁转绿**

Run: `venv/bin/python -m unittest tests.test_temp_log_policy -v`
Expected: 全部 PASS（命中 0）

- [ ] **Step 6: 一并提交（门禁 + 梳理，同一提交确保无红窗口）**

```bash
git add tests/test_temp_log_policy.py docs/compose/knowledge/08-testing-conventions.md docs/compose/spec docs/compose/plan docs/compose/reports
git commit -m "test(docs)+docs: 临时产物引用门禁（RED 25→GREEN 0）与存量引用梳理"
```

---

### Task 5: 门禁自证 + 收尾

**Files:**
- Modify: `tests/bug_hunt/gate_redproof.py`（追加一条 `_check`）

**Interfaces:**
- Consumes: Task 2 的 `tests.test_temp_log_policy.TestTempLogPolicy.test_no_concrete_temp_artifact_refs` 与 `_load_docs`
- Produces: RED-GREEN 自证记录 + 收尾证据（任务完成）

- [ ] **Step 1: 追加门禁自证条目**

在 `gate_redproof.py` 的汇总打印（`print(f"{'门禁':26} ...")` 之前）追加：`import tests.test_temp_log_policy as temp_policy`（与其他 `# noqa: E402` 导入同区），`mutate` = 把 `temp_policy._load_docs` 换成返回 `{"FAKE.md": "见 run-logs/ghost-" + "20260101" + ".log"}` 的假函数（**必须用字符串拼接**：本计划自身也在门禁扫描集内，不能明文写具体文件名），`restore` = 还原原函数；`_check("文档引用临时产物", mutate, restore, "tests.test_temp_log_policy.TestTempLogPolicy.test_no_concrete_temp_artifact_refs")`。

- [ ] **Step 2: 跑自证**

Run: `venv/bin/python tests/bug_hunt/gate_redproof.py`
Expected: 末行 `结论：N/N 条门禁通过 RED-GREEN 证明`，新增条目 `PASS`

- [ ] **Step 3: 代码索引同步**

Run: `codegraph sync && codegraph status | tail -3`
Expected: `pendingChanges` 全 0

- [ ] **Step 4: 全量测试（官方入口，本任务内一次）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . -v > run-logs/final-discover-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' run-logs/final-discover-<时间戳>.log`
Expected: `Ran N tests — OK`（含 bug_hunt 静态分析门禁）

- [ ] **Step 5: 真跑清理（一次性清掉 170MB 堆积，验证收尾动作）**

Run: `venv/bin/python scripts/agent/cleanup_tmp.py --apply`
Expected: 输出 `cleaned ... files / ... MB; kept 0 active`；随后 `ls run-logs perf-logs` 只剩空目录

- [ ] **Step 6: 收尾取证一次批量发（含清理，作为零增步证据）**

Run:
```bash
codegraph status | tail -3; git diff --stat; venv/bin/python scripts/agent/session_cost.py --check
```
Expected: 一条命令出全部判据；清理已在 Step 5 证明，无需重复

- [ ] **Step 7: 提交 + AOCI 维护**

```bash
git add tests/bug_hunt/gate_redproof.py
git commit -m "test(gate): 临时产物引用门禁的 RED-GREEN 自证"
```
随后在**最终稳定态**调一次无参数 `aoci_maintain`，按返回候选整批 `aoci_update_entry`（受管对象含本次改动的 `.md` 与新增 `.py`），并以 Verify/Check 收敛。

## 验证计划

| 层 | 命令 | 预期 |
|---|---|---|
| L0 工具 | `venv/bin/python scripts/agent/cleanup_tmp.py --selftest` | 全过，退出 0 |
| L0 幂等/活跃 | Task 1 Step 6 的两条命令 | `kept 1 active` → 第二次 `cleaned 0 files` |
| L0 门禁 | `venv/bin/python -m unittest tests.test_temp_log_policy -v` | RED(25) → GREEN(0) |
| L0 自证 | `venv/bin/python tests/bug_hunt/gate_redproof.py` | 新增条目 PASS |
| L1 模块组 | `venv/bin/python -m unittest tests.test_doc_budget tests.test_temp_log_policy -v` | 全绿（文档预算未被顶破） |
| L2 全量 | `venv/bin/python -m unittest discover -s tests/ -t . -v` | 全绿（本任务内一次） |

## 执行记录

- 2026-10-09 计划完成。开工查证与实测数字见对应 spec §1/§2。
- RED 证据待回填：Task 2 Step 2 的门禁命中数与文件清单。
