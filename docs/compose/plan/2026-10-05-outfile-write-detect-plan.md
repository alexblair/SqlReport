# `SELECT … INTO OUTFILE` / `DUMPFILE` 写判定缺口修复 + 项目收尾 实施计划

> **给执行代理**：逐任务勾选（`- [x]`）。可用 executing-plans 或 subagent-driven-development。
> **禁止**创建 `docs/superpowers/`（AGENTS §3）。
>
> 状态: 已完成
> 对应 spec: `docs/compose/spec/2026-10-05-outfile-write-detect-design.md`
> 最后更新: 2026-10-05

**Goal:** 让 `SELECT … INTO OUTFILE` / `INTO DUMPFILE` 在两个写判定函数里都判为写（堵住
`allow_write=0` 权限旁路与缓存短路），补上机械门禁；并把本项目遗留的状态头 / 失真引用 /
历史条目一次性收口——**不推送远端**（用户 2026-10-05 明确指示）。

**Architecture:** 单点改动——`query_executor.py` 新增 1 个常量 + 1 个私有谓词，插在两个
判定函数的读白名单分支**之前**。判定挂在既有 tokenizer 的关键词流上，字符串字面量与注释
天然被排除。其余任务全是文档/测试断言的订正，无设计变更。

**Tech Stack:** Python 3 标准库 + `unittest`；无新依赖。

**Spec:** `docs/compose/spec/2026-10-05-outfile-write-detect-design.md`（判定规则 §4.1、
改动点 §4.2、判定矩阵 §4.3、验证策略 §6）

## Global Constraints

- 全部产出文字用**简体中文**（AGENTS #2）。
- 一切命令在**仓库根**、**仓库 venv** 内（`./venv/bin/python`）；禁止系统 Python（#6）。
- `unittest discover` **必须带 `-t .`**（#8）；日志落 `run-logs/`（已 gitignore），唯一文件名，**禁止 `rm`**。
- `sql_contains_write` / `sql_has_persistent_write` 对**其它任何 SQL** 的结论必须零漂移：
  4 个既有测试文件的断言**一行不改**即绿（#9 的反面：不许为了让新代码过而改旧断言）。
- 不改权限文案、不改 Redis 快照契约（spec §2 非目标）。
- 每处代码改动后同一次任务内跑 `codegraph sync`（#19）。
- **不执行 `git push`**（用户 2026-10-05 明确指示）。

## 任务

### T1 RED：把判定矩阵变成失败测试

- [x] **Step 1: 追加测试类**

在 `tests/test_sql_persistent_write.py` 末尾（`TestSqlHasPersistentWriteEdges` 之后、
`if __name__ == "__main__"` 之前）追加 `TestSqlHasPersistentWriteIntoFile`，逐条覆盖 spec §4.3
矩阵：**每条正向形状同时断言两个函数**，反向形状断言两者皆 `False`。
类 docstring 必须写明方案 A（把 OUTFILE 塞进关键词集合）为何无效——首关键词是 `SELECT`
时读白名单先 `continue` 了（spec §3）。

- [x] **Step 2: 跑出 RED 并留证**

```bash
mkdir -p run-logs/outfile
./venv/bin/python -m unittest tests.test_sql_persistent_write -v 2>&1 | tee run-logs/outfile/T1-red-$(date +%Y%m%d-%H%M%S).log | tail -30
```
Expected: 新类失败（正向形状 `assertTrue` 落空）且**既有用例仍全绿**；失败条数与矩阵正向条数一致。

### T2 GREEN：实现判定

- [x] **Step 1: 新增常量与谓词**（`query_executor.py`，紧邻 `_WRITE_STATEMENT_KEYWORDS`）

按 spec §4.1 的代码块实现 `_FILE_WRITE_TARGETS` 与 `_has_into_file_write(keywords)`，
注释写明「写 MySQL 服务端磁盘」与「字符串/注释已由 tokenizer 排除」。

- [x] **Step 2: 接入 `sql_contains_write`**（`query_executor.py:592` 读白名单分支之前）

命中即 `return True`。

- [x] **Step 3: 接入 `sql_has_persistent_write`**（`query_executor.py:679` 之前，注意此处
`keywords` 是 `(词, 结束偏移)` 元组列表，须先取名字）

命中即 `return True`。

- [x] **Step 4: 跑 GREEN + 零漂移四件套**

```bash
./venv/bin/python -m unittest tests.test_sql_persistent_write tests.test_sql_write_detect tests.test_write_guard -v 2>&1 | tee run-logs/outfile/T2-green-$(date +%Y%m%d-%H%M%S).log | tail -15
```
Expected: 三个文件全绿，**既有断言未改一行**。

- [x] **Step 5: 真实语料回归（34 报表）**

```bash
./venv/bin/python tests/manual_write_gate_regression.py 2>&1 | tee run-logs/outfile/T2-regression-$(date +%Y%m%d-%H%M%S).log | tail -20
```
Expected: 与本轮改动前**同结果**（命中 0 条 `INTO OUTFILE`）。

### T3 收尾：收紧被弱化的断言

- [x] **Step 1: 定位并收紧 `test_th_min_width_rule`**

当前断言为「`render._COMMON_CSS` 中存在 `\d+px`」（复核方 I1 判定为弱化）。
改为钉住真实规则（具体 `th` 最小宽度值须**从当前 CSS 实测读出**，不得猜），
并保留「页面级 `th` 宽度」这一原意。

- [x] **Step 2: 跑该模块**

```bash
./venv/bin/python -m unittest tests.test_render_extra -v 2>&1 | tail -8
```
（若该用例不在 `test_render_extra`，以实际所在模块为准。）

### T4 收尾：文档状态与失真引用订正

> 本节无对应 spec：均为状态/引用订正，**不改任何设计**。

- [x] **Step 1: 旧 spec 加指针**：`2026-09-30-write-report-cache-gate-design.md` §5.4 加一行
      「已由 `2026-10-05-outfile-write-detect-design.md` 落地」+ 日期。
- [x] **Step 2: plan 状态头订正**：`2026-09-28-docs-spec-plan-conventions-plan.md` 补
      `> 状态: 已完成`；`2026-09-30-ui-v2-plan.md` `执行中` → `已完成`；
      `2026-10-05-cache-source-label-plan.md` `生效` → `已完成`（合法值见
      `2026-09-28-docs-spec-plan-conventions-design.md:61`）。
      三处各加一行「checkbox 未逐条回勾，完成判定以本文件「执行记录」为准」。
- [x] **Step 3: perf spec 待办回写**：`2026-09-29-execution-layer-performance-design.md:438`
      的「待办：官方入口应改 `-t .`」订正为「已落地（AGENTS 硬性 #8 与 §4；`08-testing-conventions.md`）」。
- [x] **Step 4: 修 3 处失真引用**：
      ① `2026-09-30-ui-v2-plan.md` 验证表 `tests/test_ui_contrast.py` → `tests/test_ui_tokens.py`；
      ② `spec/cache-write-test-scenarios.md:91` 的 `tests/test_cache_write_scenarios.py`
         → 实际落点 `tests/manual_cache_scenarios.py`（**先确认该文件确为四场景实现再改**）；
      ③ `MEMORY.md:116-117` 与 `2026-09-30-write-report-cache-gate-plan.md:360` 的
         `app_config.debug.json1` → 订正为实际默认路径 `app_config.debug.json`
         （`app_config.py:41`；该文件已存在于工作树但被 gitignore）。
- [x] **Step 5: `knowledge/INDEX.md` 纳入 `MEMORY.md`**（ui-r3 复盘建议，索引现状缺失）。
- [x] **Step 6: 闭环 r3 遗留**：`reports/ui-r3-retrospective.md:85` 的「等待用户对 r6 三图最终视觉确认」
      标注为「已由 UI v2 取代，作废」（视觉规范取代关系见 `2026-09-30-ui-v2-design.md` 状态头）。

### T5 收尾：产出「已裁定不做」记录

- [x] **Step 1: 写 `docs/compose/reports/2026-10-05-closeout-decisions.md`**

逐条记录本轮**明确不做**的 5 项及理由（118 处内联样式 / 临时表名追踪 / E2E 进 CI /
其余宽表 colgroup / 静态端点 403），每条给出「依据 + 触发条件」（即：什么情况下应重新考虑）。
目的：防止这些项在后续会话被反复翻出来重新讨论。

### T6 知识库与记忆同步

- [x] **Step 1: `knowledge/03-report-transform.md`** 补一行判定要点：
      「读白名单不豁免 `INTO OUTFILE`/`DUMPFILE`——首关键词是 SELECT 也算持久写」。
- [x] **Step 2: `learn/sqlreport-kb/course-state.md`** 追加本次同步行（状态块 last_sync）。
- [x] **Step 3: `MEMORY.md`** 追加 Rule：写判定第三个易漏形状（`INTO OUTFILE` 属读白名单短路）
      + 订正 §4 的 debug 配置名。
- [x] **Step 4: `codegraph sync`** → `codegraph status` 的 `pendingChanges` 全 0。

### T7 验证与提交

- [x] **Step 1: L1 模块组**（写判定 + 渲染/护栏相邻组）
- [x] **Step 2: L2 分段全量**（按 `08-testing-conventions.md` 分段命令表；代码不再变则只跑一次）
- [x] **Step 3: 提交（**不推送**）**，提交说明用简体中文，列出代码 + 文档 + 测试三类改动。

## 验证计划

| 段 | 命令 | 预期 |
|---|---|---|
| L0 | `./venv/bin/python -m unittest tests.test_sql_persistent_write tests.test_sql_write_detect tests.test_write_guard -v` | OK |
| 真实语料 | `./venv/bin/python tests/manual_write_gate_regression.py` | 与原结果一致 |
| L1 | 写判定 + 护栏 + 渲染相邻模块组 | OK |
| L2 | `./venv/bin/python -m unittest discover -s tests/ -t .` | 全绿（skipped 不变） |
| 索引 | `codegraph status` | `pendingChanges` 全 0 |

## 风险与回退

- **风险**：判定过紧 → 纯读报表被误判为写而永久失去缓存。**对策**：spec §4.3 四类反向用例。
- **回退**：改动集中在 `query_executor.py` 一个常量 + 一个函数 + 两处 `if`，
  测试改动集中在 1 个测试类 → `git revert <commit>` 即可完整回退。

## 执行记录

- 2026-10-05 **T1 RED**：`tests/test_sql_persistent_write.py` 新增 `TestSqlHasPersistentWriteIntoFile`
  （矩阵 §4.3 全量含反向用例）。首跑 `FAILED (failures=8)`，其中 1 条是**用例自身写错**
  （`SET @x := 1; …` 脚本按既有分工本就 `contains_write=True`）；修测试后 RED = `failures=7`，
  恰为矩阵正向条数。日志 `run-logs/outfile/T1-red2-20261005-2250*.log`。
- **T2 GREEN**：`query_executor.py` 新增 `_FILE_WRITE_TARGETS` + `_has_into_file_write()`，
  在两个判定函数的读白名单分支**之前**各插一处。`Ran 88 tests OK`（写判定 + 写检测 + 写护栏三件套，
  **既有断言一行未改**）。日志 `run-logs/outfile/T2-green-20261005-2252*.log`。
- **T2 真实语料**：`tests/manual_write_gate_regression.py`（34 报表，只读）→ 报表总数 34、
  净解封 `[17,19,35]`（与本轮前一致）、**反向误判 0**、保持拦截 `[37]`、`RESULT: PASS`。
  日志 `run-logs/outfile/T2-regression-20261005-2254*.log`。
- **T3**：`test_th_min_width_rule` 收紧为实测真值 `156px` + 「页面确实携带公共样式」；
  RED-PROOF 自证（把值改回 100px → 正则不命中，`RED-PROOF: PASS`）。
  首版直接对 `body` 断言 CSS 规则**必红**（报表页 CSS 走外链），已记入 `knowledge/08` 易踩坑 #24。
- **T4/T5/T6**：五份 plan/spec 状态头与待办订正、3 处失真引用清理、`INDEX.md` 纳入 `MEMORY.md`、
  ui-r3 两处遗留闭环、新增 `reports/2026-10-05-closeout-decisions.md`（裁定不做 6 项）；
  `knowledge/03` 补判定要点、`course-state` 加掌握行与 `last_sync`、`MEMORY.md` 加 Rule 16。
- **T7**：`codegraph sync` → `Index is up to date`（pendingChanges 归零）；
  L2 官方入口 `Ran 3009 tests OK (skipped=4)`（3002 + 新增 7），
  日志 `run-logs/outfile/T4-L2-20261005-2256*.log`。
- **偏差与说明**：
  ① T4 Step 4-② 未按「改引用」处置——核实后确认 `tests/test_cache_write_scenarios.py`
     **从来不存在**（四场景实现一直在 `tests/manual_cache_scenarios.py`），故订正为「建议未落地」而非改名；
  ② T4 Step 6 的「等用户确认 r6 三图」改为按取代关系**作废**（视觉规范已被 UI v2 全部取代）；
  ③ T3 的收尾断言改为「常量真值 + 页面携带公共样式」两段（原因见易踩坑 #24）。
- **未推送**：按用户 2026-10-05 指示只提交本地，`git push` 未执行。
