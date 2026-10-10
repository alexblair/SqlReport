# AOCI 体系与 MCP 工具卸载报告（2026-10-10）

> 用户指示：从本项目与 DSH 中整体去除 AOCI 体系与 MCP 工具；同步清除全局规则与知识库中的 AOCI 内容（避免卸载后路径中断）；并去掉此前为照顾 AOCI 兼容性所做的 codegraph 边界划分（**代码分析依然优先 codegraph**）。

## 1 结论

AOCI 已从**项目**（索引资产 / 治理态 / 二进制 / 工具脚本 / 知识库分卷）与 **DSH**（MCP 接线 / npm 插件 / 锁文件）两侧整体移除；规则层、门禁层、工具层与 19 份历史文档全部对齐，无悬空引用。

- 全量测试：**Ran 3178 tests, OK (skipped=4)**，静态分析 ERROR **0**。
- `codegraph`：`sync` 后 `pendingChanges = {added:0, modified:0, removed:0}`。
- 项目内（排除历史文档与 gitignore 的第三方 scratch）`aoci` 引用 **0**；DSH 接线 `.yml`/`package.json`/lock/`.modules.yaml` 引用 **0**。
- 旧约束 **硬性 #21 退役**（进入 `RETIRED_CONSTRAINTS`，编号不复用），`AGENTS.md` 由「15 条硬性约束」变为「14 条」。

## 2 归档（可回滚）

卸载前完整快照落在**仓库外** `/root/aoci-uninstall-archive-20261010/`（约 339MB）：

| 子目录 | 内容 |
|--------|------|
| `repo/` | `aoci.txt`、`aoci.code.txt`（157 条认知）、`aoci.meta.txt`、`.aoci/`（baseline/ledger/governance/transactions/verify_history）、`.tools/`（aoci 二进制 + cosign）、`aoci_precheck.py`、`test_aoci_precheck.py` |
| `tools-aoci/` | `tools/aoci/` 解压副本（含 assets 与 README） |
| `docs/` | `11-aoci-usage.md`、AOCI 专属 spec/plan 与 2026-10-09 有效性评估报告 |
| `configs/` | 改动前的 `AGENTS.md`、`.gitignore`、`.gitattributes`、DSH `cordis.patch.yml`、`package.json`、`pnpm-lock.yaml`、`node_modules/.modules.yaml`、`node_modules/.pnpm/lock.yaml`、`cordis.patch.yml.bak.*` |
| `skills/` | 改动前的 `.dsh/skills/ai-retro-lean-iteration/` |

## 3 项目侧删除清单

- **二进制 / 工具**：`.tools/`（aoci 24MB + `aoci-mcp-overlay.cordis.yml` + cosign verify 缓存）、`tools/aoci/`（24MB 副本）、`tools/`（随之空目录删除）。
- **认知索引 / 治理态**：`aoci.txt`、`aoci.code.txt`、`aoci.meta.txt`、`.aoci/`。
- **读写工具与门禁**：`scripts/agent/aoci_precheck.py`、`tests/test_aoci_precheck.py`（含 `__pycache__`）。
- **知识库分卷**：`docs/compose/knowledge/11-aoci-usage.md`。
- **忽略规则**：`.gitignore` 移除 `.tools/` 与 `/tools/aoci/` 两条 AOCI 专属条目及其注释；`.gitattributes` 的注释改写为通用表述（保留 `* text=auto eol=lf` 本身）。

## 4 规则与知识库对齐

| 对象 | 改动 |
|------|------|
| `AGENTS.md` | 删 §0「改前定向读（硬性 #21）」段、§0 路由表 AOCI 行、§1 硬性 #21、§4 `aoci_precheck` 命令、§5 第 4 项（收尾链）；删整个 `<!-- aoci:begin -->…<!-- aoci:end -->` 块；「15 条」→「14 条」 |
| `docs/compose/knowledge/README.md` | 删 11 卷索引行与「AOCI 认知层」要点 |
| `docs/compose/knowledge/09-agent-workflow.md` | 浏览器/探针 profile 条目去掉「会被 AOCI 遍历并污染受管范围」的理由（保留「一律建在 `run-logs/`」规则） |
| `learn/sqlreport-kb/course-state.md` | 删 11 章节行与 AOCI 纪律行；`chapters=0..11 done` → `0..10 done` |
| `tests/test_doc_budget.py` | `LIVE_CONSTRAINTS` 移除 21；`RETIRED_CONSTRAINTS` 增加 21；退役文案改为与日期无关的「已退役」；注释里的失效 spec 路径去除 |
| `scripts/agent/session_cost.py` | 删 `aoci_steps`/`maintain_calls`/`aoci_read_calls`/`precheck_calls` 的统计、字典字段、渲染行与 3 条自测断言；`dup_maintain` 分支与 `--check` 文案同步收敛（自测 13 项通过） |
| `.dsh/skills/ai-retro-lean-iteration/`（项目技能，2 文件，git 已跟踪） | 删 `aoci_precheck` 收尾步骤、`aoci_report` 登记待办指引、AOCI 取证指标行、AOCI 报告来源与「不维护 AOCI」条目 |

## 5 codegraph 边界划分解绑

此前为让 AOCI 与 codegraph 不重叠而写死的三层边界句（「AOCI 管『改它要小心什么』／codegraph 管『改它还会碰到谁』／分卷管『按什么流程做』」，以及「不用 AOCI 找符号、不用 codegraph 找约束」）已随 `AGENTS.md` §0 段落、`11-aoci-usage.md`、`aoci_precheck.py` docstring 一并消失。

**codegraph 优先未被削弱**：硬性 #18（`codegraph explore` 必须是第一步，确查不到才降级 grep/glob/read）与 #19（改完 `.py`/`.js`/`.mjs` 必 `codegraph sync`）原样保留；§0 路由表「读/分析代码、定位符号、查调用链与影响面 → 先走 codegraph」保留；`09-agent-workflow.md` 的 codegraph 章节与「降级白名单」保留（后者是 codegraph 自身不索引的对象类型，非为 AOCI 所划）。

## 6 DSH 侧改动

| 对象 | 改动 | 生效条件 |
|------|------|----------|
| `~/.dsh/profiles/web/cordis.patch.yml` | 删整个 `- insert:` 块（`mcp-aoci` + `mcp-aoci-ezbook` 两个 MCP server，后者指向另一仓库 `ezbook`）；YAML 解析通过，剩 7 个顶层条目 | **需重启 DSH** 才从会话工具表消失 |
| `~/.dsh/profiles/web/package.json` | 删依赖 `dsh-aoci`（该插件此前**未被激活**：不在 `dsh.profile.bundles` 中） | 下次启动 |
| `node_modules/dsh-aoci` | 目录删除（`.pnpm` 内无实体残留） | — |
| `pnpm-lock.yaml` | `pnpm install --lockfile-only --offline` 重新生成；`dsh-aoci` 计数 0 | — |
| `node_modules/.modules.yaml`、`node_modules/.pnpm/lock.yaml` | 手工对齐（只删 `dsh-aoci` 条目 / 用新 lock 覆盖），**未跑完整 install** 以免扰动正在运行的 GUI | — |
| `cordis.patch.yml.bak.20261008172735` | 含 `mcp-aoci` 的陈旧备份：已归档后删除 | — |

> 当前会话仍能看到 `mcp__aoci__*` 工具，属正常现象——配置已删，**重启 `dsh web` 后即消失**（本次按用户选择未重启）。

## 7 验证证据

1. **测试**：`venv/bin/python -m unittest discover -s tests/ -t . -v` → `Ran 3178 tests … OK (skipped=4)`，退出码 0；静态分析 `[ERROR]` 0 行；日志中已无 `test_aoci_precheck`。`tests/test_doc_budget.py` 的体积/条数/路由/孤儿卷/约束号各项用例全部通过。
2. **索引**：`codegraph sync` → `Synced 4 changed files … Removed: 2`；`codegraph status --json` → `pendingChanges` 三项全 0；`Index is up to date`。
3. **残留检索**：项目内 `grep -ri aoci`（排除 `.git`/`venv`/知识库历史文档与 gitignore 的 `.mimocode`、`.superpowers`）为 **0**；DSH 五个接线文件为 **0**。
4. **DSH 生效前检查**：`cordis.patch.yml` 经 YAML 解析，顶层 id 为 `ui-settings-general, ui-theme, llm-pi-ai, agent-default-model, ui-chat, session-log-deepseek, web-search-free`。

## 8 历史文档处理

`docs/compose/{spec,plan,reports}/` 下 19 份提及 AOCI 的文本文件**保留原文**（不篡改历史），仅在**文件顶部加一行失效声明**：

> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

## 9 遗留（不在本次范围）

1. **重启 DSH** 后才会看不到 AOCI MCP 工具（用户选择本次不重启，以免中断会话）。
2. `~/.dsh/profiles/web/cache/catalog-plugins-zh.json` 仍含插件市场条目 `dsh-aoci-panel`——那是可再生成的目录缓存，非本机接线，未改。
3. `~/.dsh/plugins/dsh-better-edit/runtime/*/hash-store.sqlite` 内含已删除 aoci 文件的路径哈希——属第三方插件运行态数据，会自行过期，未改。
4. `.superpowers/sdd/2026-10-09-temp-artifact-lifecycle-plan/`（gitignore 的流程 scratch）仍含 `11-aoci-usage.md` 字样，未处理。
5. **git 历史**中仍保留 AOCI 相关提交（未做历史重写）。

## 10 复现命令

```bash
# 残留检查（项目）
grep -rn -i aoci . --exclude-dir=.git --exclude-dir=venv --exclude-dir=__pycache__ \
  --exclude-dir=.codegraph --exclude-dir=.mimocode --exclude-dir=.superpowers \
  | grep -v '^./docs/compose/\(spec\|plan\|reports\)/'
# DSH 接线检查
grep -rn -i aoci ~/.dsh/profiles/web/{cordis.patch.yml,package.json,pnpm-lock.yaml}
# 测试与索引
venv/bin/python -m unittest discover -s tests/ -t . -v
codegraph sync && codegraph status --json
```
