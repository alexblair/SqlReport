# AGENTS.md — SqlReport 开发代理指引

面向在本仓库工作的 AI / 开发代理。**只写「没有帮助就会做错」的事**；通用编程常识、模块细节、流程全文都不在这里——见下表按需读分卷。

**本文件是「每次任务都要读」的最小集**：硬性约束条目 + 入口引导 + 环境命令 + 收尾检查单。其余内容全部在 `docs/compose/knowledge/`，由下面的路由表指引。

---

## 0. 入口引导：什么时候读哪一卷、改完必更新哪一卷

**开工第一步：按「你要做的事」找到对应行，读「先读」列的分卷**（只读涉及章节，禁止整卷通读）。
**收尾前：把「改完必更新」列的分卷更新掉**（硬性约束 #7，代码与知识库同一次任务内完成）。

| 你要做的事 | 先读（分卷） | 改完必更新 |
|------------|-------------|-----------|
| 摸不清该动哪些模块 / 模块职责 | `INDEX.md`、`01-architecture.md` | `INDEX.md` |
| 读/分析代码、定位符号、查调用链与影响面 | **强制先走 `codegraph`**（硬性 #18）→ `09-agent-workflow.md`「代码检索纪律」 | — |
| 新增/改路由、鉴权边界、Session、审计 | `02-routing-auth.md` | 该卷 + `INDEX.md` 路由表 |
| 改筛选/排序/分页/导出/API/全量护栏语义 | `03-report-transform.md`、`05-api.md` | 对应卷 + `INDEX.md` 共享语义表 |
| 改配置表字段 / 双引擎迁移 / `/config` CRUD | `04-config-data.md` | 该卷 |
| 改 UI、页面布局、组件、CSS/JS、交互 | `06-ui-interactions.md` | 该卷（+ `tests/test_ui_tokens.py` 门禁、`tests/test_render.py` 结构用例；按硬性 #17 验收） |
| 改缓存分层、定时任务、审计 type | `07-cache-scheduler-audit.md` | 该卷 |
| 改启动链路、`app_config`、依赖安装方式 | `01-architecture.md` | 该卷 + 双 README（镜像对） |
| 跑测试 / 改测试 / 验证改动 | `08-testing-conventions.md` | 该卷（新踩坑必记） |
| 任务卡住、同一问题反复失败 | `08-testing-conventions.md`「两败必停」 | — |
| 派发子代理、多代理协作 | `09-agent-workflow.md` | — |
| 性能测量 / 压测 / 优化 | `08-testing-conventions.md`「性能测量工具链」+ `03-report-transform.md` | 该卷 |
| 会话 token 超标 / 长任务分段 / 大批量检索前 | `10-token-budget.md` | — |
| 查历史决策、需求依据 | `docs/compose/spec/` 最新生效 spec（见 §3 开工查证） | 新 spec / 取代旧 spec |

**分卷全表**：`docs/compose/knowledge/README.md`（入口）· `INDEX.md`（模块/路由/页面/共享语义）。

---

## 1. 硬性约束（违反即错误）

**每条只给结论；「怎么做」在指路的分卷里。**

1. **禁止研究与修改** `/alexblair/windir/www/SqlReport/`（生产副本，不在本仓库）。
2. **全部用户可感知文字用简体中文**：文档、注释、UI 文案、提交说明、与用户交流。
3. **禁止重复造轮子**：新增 UI、筛选/排序、导出、API、缓存、配置 CRUD 前，先在现有代码找到**单一实现来源**并引用/拼装。细则见 `03-report-transform.md`（transform 三端共用）、`06-ui-interactions.md`（UI 组件）。
4. **先研究、后修改**：变更前读清相关模块的函数签名、路由、测试基类、共享 CSS/JS；禁止从零重写已有结构。→ 路由表「先读」列。
5. **技术选型锁定**：纯 Python 3 标准库 + 极少量 pip 依赖；Web 层 `http.server`，前端服务端 HTML 字符串。**不要**引入 Django/Flask/React/Node 构建链或框架级依赖。
6. **禁止污染系统环境**：一切测试/运行/安装必须在仓库根 `venv` 内；禁系统 Python、禁全局 site-packages。
7. **知识库入口与自动同步**：入口 `docs/compose/knowledge/README.md`。变更后**同一次任务内**更新受影响分卷与 `learn/sqlreport-kb/course-state.md`——只改代码不改知识库视为未完成。文档与代码冲突时**以代码为准并回写知识库**。→ §0 路由表「改完必更新」列。
8. **测试先最小、后放大；全量不重复**：L0 单文件 → L1 模块组 → L2 分段全量；代码未再变时完整测试**通过一次即可**，禁止反复全量。**`discover` 必须带 `-t .`**（否则测试隔离失效、会连生产 Redis）。详见 `08-testing-conventions.md`。
9. **测试与脚本对齐最新需求**：需求变更的**同一次任务**内改写受影响断言/夹具/脚本；禁止保留废弃旧逻辑制造假失败。
10. **禁止硬编码项目主目录**：用「仓库根（`server.py` 所在目录）」相对表述或 `__file__` 推导。例外：约束 #1 的生产副本路径本身。
11. **UI/视觉/交互任务先出可交互 HTML 确认稿**：未确认不得改生产页面；实施严格按确认稿，不得随意发挥；禁止混乱 DOM/CSS 直塞生产。完整四阶段与自检清单见 `06-ui-interactions.md`。
12. **同一问题失败 2 次必须停下找根因**：停手 → 只分析（报错/最小复现/相关模块/是否过时测试）→ 写出根因假设 → 再做一次针对性修改 + L0 验证。**禁止第 3 次盲试**。工具层同样：同一工具调用失败 2 次禁止原样重发；被中断的调用不计失败次数，但恢复时先查上一动作是否生效。详见 `08-testing-conventions.md`。
13. **子代理派发纪律**：同任务**全局至多一个活跃子代理**；派前 Task/Actor 盘点；`cancel` 回执**不作数**（以 `status` + 文件 mtime 双确认为准）。详见 `09-agent-workflow.md`。
14. **验证前清场与产物落盘**：跑测/截图前查 `status`，无活跃写入者直接执行；**同一测试段执行上限 2 次**（首跑 + 1 次收口，代码变更即重置）；日志与临时产物一律落**仓库内已 gitignore 的目录**（`run-logs/` / `perf-logs/`，本环境 `/tmp` 会被清空）、唯一文件名、**禁止 `rm`**。详见 `09-agent-workflow.md`。
15. **子代理效率预算**：任务书写明轮次预算（单页 ≤40 / 总 ≤120）、重复禁令、轮询退出判据、`timeout_ms`；父会话 turnCount >150 必须介入。详见 `09-agent-workflow.md`。
16. **执行效率与取证纪律（P1–P7）**：等待协议（>30s 后台落盘 + 带判据短轮询，**禁止整段前台 sleep**）、测试取证双产出（落盘与取数同拍）、编辑三拍（Read 定位 → `old_string` 逐字复制 → Edit，1 败即换小锚点）、先验证后落笔、研究预算、纠正即入库（当轮写入 `MEMORY.md`）、收尾必报（进度表 +【任务完成】简报）。详见 `09-agent-workflow.md`。
17. **交互改动必须验「两种载入态 + 多轮 + 组合」**：凡改动碰了 JS 交互（面板/拖拽/筛选/排序/导出/换页），验收须同时覆盖**整页加载**与**操作一次后的原位换页态**，并验到**第二/三次操作**与**组合序列**（如 改字段顺序 → 加筛选 → 再排序 → 导出交叉）。换页后 `innerHTML` 不执行内联 `<script>`、不重跑初始化（内联 `onclick` 仍能点，故表现为「按钮能点、拖拽报废」）；新增初始化必须进 `initPage()`/`initReportPage()`，页面级脚本用 `onReady(fn)`；能机械检测的一律做成门禁（新门禁须用 `tests/bug_hunt/gate_redproof.py` 做 RED-GREEN 自证）。详见 `06-ui-interactions.md` 硬性 #17 与失败模式库。
18. **代码检索/阅读强制走 codegraph（codegraph-first）**：任何「读/分析代码、定位符号、查调用链或影响面」的**第一步必须是 codegraph**——`codegraph explore`（接入 MCP 时用 `codegraph_explore` 工具，二者输出同源）。**query 必须带代码词（符号名/文件名/英文技术词）**，**纯中文问句一律查不到**（实测 0 命中），别据此降级。**只有 codegraph 确实查不到才降级** `grep`/`glob`/`read`，且降级前必须把查询**加宽重试**（补符号名/文件名/英文词）。禁止用 grep+read 循环替代 codegraph，禁止用 grep 复核 codegraph 已给出的结论。可直接降级的对象（未索引文件、字符串字面量）与完整命令表见 `09-agent-workflow.md`「代码检索纪律」。
19. **改完代码必须 `codegraph sync`**：新增/修改/删除任何 `.py`/`.js`/`.mjs` 后，**同一次任务内**跑 `codegraph sync`（大范围重构或目录结构变动跑 `codegraph index` 全量重建）。本机 codegraph 守护进程未常驻，**不存在自动同步**；未 sync 就继续分析，读到的是旧索引。收尾以 `codegraph status` 显示 `pendingChanges` 全 0 为准。
20. **Token 预算（返回体积 / 批处理 / 会话分段）**：实测 4 个会话 69.7M tokens 中 **98.6% 是历史重发**，成本 ≈ 步数 × 上下文——一步塞进历史的，后面每步都重发。① 单条工具返回 >8k 字符即超阈：先 `grep -c` 计数、`head` 截断、`read` 带 `offset/limit`；② 互不依赖的调用**同步发**（一步 2–4 个），禁止一步一条命令的碎步探索；③ 会话 >60 步或上下文 >120k tokens → 按交接模板落盘换新会话；④ `write`/`edit` 回显全文，大文件改到会话后段一次批量改完；⑤ 收尾跑 `scripts/agent/session_cost.py --last 1` 自查。详见 `10-token-budget.md`。

---

## 2. 知识库

**入口（唯一）**：`docs/compose/knowledge/README.md`
**索引**：`INDEX.md`（模块地图、ROUTES、页面地图、共享语义）
**掌握状态**：`learn/sqlreport-kb/course-state.md`
**代码索引**：仓库根 `codegraph`（v1.4.0，`.codegraph/` 已 gitignore，勿提交）。**读/分析代码强制先走它**（硬性 #18），**改完代码强制 sync**（硬性 #19）——命令表与降级白名单见 `09-agent-workflow.md`「代码检索纪律」。

| 分卷 | 内容 | 何时读 |
|------|------|--------|
| `01-architecture.md` | 技术选型、启动链路、应用配置、双引擎、**模块地图**、缓存分层、连接池 | 摸模块 / 改启动 / 改配置 |
| `02-routing-auth.md` | 请求主流程、**ROUTES 全表**、Session、审计 | 改路由 / 鉴权 |
| `03-report-transform.md` | execute_report、URL 参数、筛选语法、导出、护栏、**transform 性能要点**、派生态缓存 | 改筛选/排序/导出 |
| `04-config-data.md` | config_db 实体与 DAL、config 表单、app_config、**表结构变更三处同步** | 改表 / 改 CRUD |
| `05-api.md` | API Key、CORS、静态 `.json`、预设、JSON 模板 | 改 API |
| `06-ui-interactions.md` | **UI 任务四阶段流程**、骨架与资产、页面地图、组件库、HTML 门禁 | 改 UI |
| `07-cache-scheduler-audit.md` | L1/L2/L3 数据流、定时任务、审计 type | 改缓存 / 调度 |
| `08-testing-conventions.md` | 测试入口、**`-t .` 陷阱**、性能工具链、**两败必停**、**L2 分段命令表**、易踩坑 | 跑测 / 排错 |
| `09-agent-workflow.md` | **多代理协作纪律**、**执行效率 P1–P7**、汇报节奏 | 派子代理 / 需要取证纪律 |
| `10-token-budget.md` | **Token 预算（#20）**：真实 usage 账本、返回体积阈值、批处理、会话分段交接、收窄命令表 | 收尾自查 / 长任务 / 大批量检索 |

### 同步规则

1. **改代码 → 改知识库**：同一完成定义。
2. **以代码/测试为准**：旧分卷与实现不一致时立即改分卷，不要只留注释。
3. **最小充分更新**：只改受影响分卷与 `INDEX`/`README` 的过时表述；禁止整库重写。
4. **冗余红线**：spec/plan 引用知识库**只写链接**，不复制路由表/共享语义等现状事实。
5. **代码索引同步**：每次改完 `.py`/`.js`/`.mjs` 跑 `codegraph sync`（硬性 #19）；大改后 `codegraph index`。本卷只是知识库（`.md`），codegraph **不索引** `.md`，故改文档不需要 sync。

---

## 3. spec / plan 存储与格式约定

1. **路径唯一**：spec 只在 `docs/compose/spec/`，plan 只在 `docs/compose/plan/`（同日期同主题一一对应）。**禁止创建 `docs/superpowers/`**（writing-plans 等 skill 的默认路径被本节覆盖）。`knowledge/` 只放知识库。
2. **格式**：状态头模板、取代两头改规则、plan 模板与状态值，以 `docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md` §3/§4 为准（此处不复制）。
3. **开工查证**：`ls -t docs/compose/spec/` 取最新 → 读状态头找生效版 → 冲突时按裁决顺序（**当次指示 > 本文件 > 最新生效 spec > 旧/被取代 spec > plan**）处理，并在新 spec 记录裁决结果。`knowledge/INDEX.md` 只管模块/路由/共享语义，**不是**任务查证入口。
4. **取代两头改**：新设计推翻旧设计时，① 改旧 spec 状态头为「已被 X 取代」+ 日期 + 原因；② 在新 spec 写 `取代关系:`。只改新不改旧 = 未完成。
5. **git**：`docs/` 与仓库根 `AGENTS.md` 随任务正常提交（2026-10-06 起取消忽略、入库）。

---

## 4. 环境与命令

工作目录：**仓库根**（`server.py` 所在目录）。
**搜索范围**：一切 grep/glob/find 限本项目目录内；禁止 `find /` 等全局搜索（曾因此超时越界，属用户明令）。

```bash
# 安装（venv + requirements.txt）
./install.sh
source venv/bin/activate          # 必须先激活，否则视为污染系统环境

# 启动（默认 0.0.0.0:8080；HOST/PORT 可覆盖）
python server.py

# 全量测试（官方入口；含 bug_hunt 静态分析）—— -t . 不可省
python -m unittest discover -s tests/ -t . -v

# 单文件 / 单用例
python -m unittest tests.test_filter_help -v
python -m unittest tests.test_auth.TestSession.test_sliding_expiry_keeps_session_alive -v

# 代码索引（硬性 #18 检索优先 / #19 改完必 sync）
codegraph explore "<中文意图 + 代码词>"          # 首选：源码 + 调用链 + 波及面（纯中文查不到）
codegraph status                              # 索引健康 + pendingChanges
codegraph node <符号>                         # 单符号源码 + callers/callees
codegraph query <关键词> -l 10                # 只查位置，不回源码
codegraph callers|callees|impact <符号>        # 依赖面
codegraph affected <改过的文件>                # 受影响测试文件
codegraph sync                                # 每次改完代码必跑
```

- 测试框架以 **`unittest`** 为准；`requirements.txt` 虽列 `pytest`，环境未必装，勿默认用 pytest。
- 无 CI / 无 lint / 无 typecheck；**静态分析靠** `tests/bug_hunt/test_static_analysis.py`（随 discover 跑，ERROR 会使测试失败）。
- 破坏性变异扫描（手动、勿当常规）：`python tests/bug_hunt/bug_hunt_mutation.py`。
- 服务安装：`sudo bash manage_service.sh install|uninstall`（systemd 单元 `web-report`）。
- Git 辅助：`./git-tool.sh`（交互式；勿对共享分支强制推送）。
- **改依赖必须同步三处**：`requirements.txt` + `README.md`/`README-CN.md` 安装说明 + `install.sh`。
- **改 README 必须中英同步**（镜像对，同一次提交改两侧）。
- 测试/验证的详细策略与 L2 分段命令表见 `08-testing-conventions.md`。

---

## 5. 收尾检查单

1. L0（必要时 L1）绿 → 需要时 L2 分段全量绿（本任务内一次即可）
2. **知识库同步**：按 §0 路由表「改完必更新」列逐项确认已更新
3. 需要时手动跑 bug_hunt 变异脚本
4. **spec 查证**：确认已按 §3 查过生效 spec（无任务型改动则注明不适用）
5. 用户可感知的结论要**报证据**（测试 Ran N / 数据对比 / 文件:行），不报「应该是」
6. 交互类改动：按 #17 跑「整页 + 换页态 + 组合序列」，新增/改动门禁跑 `tests/bug_hunt/gate_redproof.py` 自证
7. **代码索引同步**（#19）：改过 `.py`/`.js`/`.mjs` 就跑 `codegraph sync`，`codegraph status` 确认 `pendingChanges` 全 0
8. **Token 自查**（#20）：`venv/bin/python scripts/agent/session_cost.py --last 1`；超阈步与步数在简报里报数字

---

## 6. 文档中的过时线索（勿盲信）

- README「项目结构」的过时项（`git-purge.sh`、测试文件清单）已于 2026-10-06 修正：改列真实文件（`git-tool.sh` 等）、测试树收敛为目录说明；仓库根 `AGENTS.md` 同日取消 git 忽略、入库并入结构树。仍以**当前目录**为准。
- README 结构树不再逐文件罗列测试（80+ 文件）；以 `tests/` 实际文件与 discover 为准。
- 文档与代码冲突时：**以可执行代码 / 测试为准**，并修正文档（中英 README 同步）；若冲突在知识库分卷，**必须回写**。
