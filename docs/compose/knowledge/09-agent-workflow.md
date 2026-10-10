# 多代理协作 · 执行效率与取证纪律

> 对应硬性约束 #14、#18–#19、#20。**仅在派发子代理、需要严格取证纪律、或要检索/阅读代码时才读本卷**；
> 日常单会话开发只需 AGENTS.md 的硬约束条目与本卷标题下的「一句话版」。

## 何时读本卷

| 场景 | 读哪节 |
|------|--------|
| 要派发 / 监控子代理 | 「多代理协作」 |
| 只是自己写代码、跑测试 | 「验证与汇报纪律」 |
| 读/分析代码、找函数、看谁调用它、改它会影响谁 | 「代码检索纪律（#18/#19）」——**先 codegraph，不要先 grep** |
| 任务卡住、同一问题反复失败 | 两败必停 → `08-testing-conventions.md`（硬性 #12） |
| 会话变长、单条返回过大 | `10-token-budget.md`（硬性 #20） |

## 一句话版

- **查代码先走 codegraph**（`explore` 一个命令 = 源码 + 调用链 + 波及面）；**改完 `.py`/`.js`/`.mjs` 跑 `codegraph sync`**。
- 等待 >30s 的任务用**后台作业 + 带判据短轮询**，**禁止整段前台 sleep**（硬性 #20）。
- 验证前先确认无活跃写入者；同一测试段 ≤2 次（硬性 #14）。
- **浏览器/探针 profile 一律建在 `run-logs/` 下**（如 CDP 取证 `--user-data-dir=run-logs/chrome-profile-<用途>`）：建在 `docs/` 等受管目录会被 AOCI 遍历并污染受管范围（2026-10-09 实操踩坑：`docs/compose/spec/shots/r3/` 下遗留 199MB `.chrome-*` profile），而 `cleanup_tmp.py` 只覆盖 `run-logs/`+`perf-logs/`。
- 收尾只报证据（测试 Ran N / 数据 / `文件:行`），不报「应该是」。
- **复盘 AI 历史运行表现 → 做最小改动优化**：用项目技能 `.dsh/skills/ai-retro-lean-iteration/SKILL.md`（范围确认硬门禁 + 取证命令表 + 三份交付物模板）。

---

## 多代理协作

- **读写范围不重叠**：任务书写清验收标准与写入范围（涉及 `文件:函数` 清单），同一范围全局只允许一个活跃写者。
- **写集中在一处**：所有写者停止后，在收尾统一写入与验证；写入窗口内不并发跑测试。
- DSH 原生有 Agent Teams / 共享任务：用任务条目记账，派发前先查已有任务，中断不必原样重发。
- **`cancel` 回执不作数**：以「状态 + 目标文件 mtime」双确认（cancel → status 确认 idle/completed → mtime 前后一致）才允许重派。
- **子代理回报限额（2026-10-10 实测）**：4 个只读盘点子代理一次性回传 6 条报告（单条 7.5k–11k 字符，合计 54.5k 字符），在第 37 步注入 **27,020 tokens**，重发成本 ≈ **32.7M**——这是单点最大的上下文注入。规则：**子代理只回 ≤2k 字符摘要**（结论 + `文件:行` + 复现命令），明细落 `run-logs/<主题>-<时间戳>.md`，Lead 需要时按 `read offset/limit` 取用。

## 验证与汇报纪律（硬性 #14）

1. **先清场后验证**：跑测试/截图前确认无活跃写入者。写入窗口内跑出的失败必须复跑确认，不许直接当真或当假。
2. **测试结果落盘**：`python -m unittest … > run-logs/<域>-<时间戳>.log 2>&1` 后 `grep` 取数，中断可续查。
3. **同一测试段上限 2 次**：首跑 + 1 次收口复跑；第 3 次只能引用已有日志。源码/测试文件变更后计数重置（L0/L1/L2 分段见 `08-testing-conventions.md`，硬性 #8）。
4. **收尾简报给证据**：进度行「编号 | 状态 | 证据（测试 Ran N / 截图 N 张 / `文件:行`）」；任务完成以【任务完成】+ 简报（做了什么/证据/产物）收尾，**禁止「应该是」式结论**；收尾前跑 `venv/bin/python scripts/agent/cleanup_tmp.py --apply` 统一清理临时产物（依据类内容先落 `docs/compose/reports/`）。

---

## 代码检索纪律（硬性 #18 / #19）

适用：**一切「读代码 / 分析代码 / 定位符号 / 查调用链 / 评估改动影响面」的动作**。

codegraph 是本项目已建好的 SQLite 符号知识图谱（`.codegraph/` 已 gitignore），预先算好 AST 与调用关系：**一次 explore 通常顶一轮 grep+read 循环**，还能跨动态分发（回调 / 模板拼接）给出 grep 跟不动的链路。

### 查询写法（硬性 #18）

- **query 必须带代码词**（符号名 / 文件名 / 英文技术词）：**纯中文问句一律返回 `No relevant code found`**。
  有效：`codegraph explore "筛选 parse_filters"`；无效：`codegraph explore "筛选 解析"`。
- 不知道符号名：先「中文意图 + 猜的英文词」探一次 → `codegraph query <关键词>` 找符号名 → 再 `explore`。
- 问「X 如何变成 Y / 整条链路」→ 一次把两端符号都写进 query。
- 输出**按文件分组、逐行带行号**，与 `read` 同形 → **当作已读**，不要再 `read` 同一段。
- 改某符号前先看 `explore` 顶部的 **Blast radius** 段（或 `impact`）：列出波及符号与覆盖它的测试 → 硬性 #3「先找到单一实现来源」。
- 返回太多用 `--max-files N` 收窄；只要位置不要源码用 `query`。

### 两条等价通道（同一份索引、同一套输出）

| 用途 | MCP 工具 | CLI（本项目默认） |
|------|------|------|
| **主入口** | `codegraph_explore` | `codegraph explore "<中文意图 + 代码词>"` |
| 读文件 / 读符号 | `codegraph_node`（`file` 模式 ≡ Read） | `codegraph node <符号>` / `codegraph node --file <路径>` |
| 符号名 → 位置 | `codegraph_search` | `codegraph query <关键词> -l 10` |
| 谁调用它 / 它调用谁 | `codegraph_callers` / `codegraph_callees` | `codegraph callers <符号>` / `codegraph callees <符号>` |
| 影响面 / 受影响测试 | `codegraph_impact` | `codegraph impact <符号> -d 2` / `codegraph affected <文件...>` |
| 文件树 / 索引健康 / 同步 | `codegraph_files` / `codegraph_status` | `codegraph files` / `codegraph status` / `codegraph sync` |

选哪条通道都不违反 #18；**本项目默认用 CLI**（无 MCP 依赖、输出完全一致）。

### 降级白名单

以下对象 codegraph **不索引**，可直接 `grep`/`read`/`glob`，不必先试：

- **非代码文本**：`.md`、`.json`、`.html`、`.css`、`.sh`、`.txt`、`.log`。
  （注意：`render.py` 里的 HTML/CSS/JS 是 **Python 源码里的字符串**，**要索引**，用 `explore` 查。）
- **资源与非源码目录**：`venv/`、`*.db`、截图/报告目录、构建产物。
- **具体字符串字面量**：某个中文文案 / CSS 类名出现在哪——先 `explore` 一次相关文件，确无结果再 `grep -n`。
- **运行期数据**：日志、审计表、DB 内容——用测试/脚本，不属于「分析代码」。

**降级前必须先加宽重试一次**（补符号名 / 文件名 / 英文技术词）——纯中文问句查不到是正常的，不是降级理由；重试仍无结果才降级。

### 禁止项（违反即返工）

1. 禁止用「`grep -rn` 找行号 → 再 `read` 一大段」替代 `explore`。
2. 禁止用 grep **复核** codegraph 已给出的结论（同一事实查两遍 = 白花往返）。
3. 禁止把 explore 返回的源码当「摘要」——它是**磁盘逐字原文 + 行号**，可直接当已读、可直接做编辑锚点。
4. 禁止用 `grep -n '^def'` / `grep -n '^class'` / `wc -l` / `head -N` 扫源码结构替代 `explore` / `node --file`（2026-10-10 实测：源码文本检视 288 次 vs codegraph 调用 28 次，检视类 bash 占新增 tokens 22.7%）。

### 同步纪律（硬性 #19）

| 时机 | 动作 |
|------|------|
| 改完任何 `.py`/`.js`/`.mjs` | `codegraph sync`（增量，实测 <1s） |
| 收尾校验 | `codegraph status` → `pendingChanges` 三项**全 0** |
| 大重构 / 搬目录 / 大批增删文件 | `codegraph index`（全量重建，`-q` 静默） |
| 索引卡住 / 升级 codegraph 后 | `codegraph unlock` 清陈旧锁 |

**没有自动同步**，禁止假设「它会自己跟上」——这正是 #19 存在的原因。只改 `.md` 不需要 sync；同一任务里也改了代码就必须 sync。卡在 `indexing` 不动 = 后台进程随沙箱调用结束而死 → `codegraph unlock` 后**在单条命令内**跑完 `index` 并同命令校验。

---

最后核对：2026-09-29 从 AGENTS.md 迁入；2026-09-30 新增「代码检索纪律（#18/#19）」；本次按力度 A 瘦身——删除「简报五件套 / 父会话开工三步 / 父会话监控 / 预算与监控 / P1–P7 执行模板 / 实测坑 / MCP 接入」等旧工具规程，纪律改由 DSH 原生机制承担。
