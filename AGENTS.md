# AGENTS.md — SqlReport 开发代理指引

面向在本仓库工作的 AI / 开发代理。**只写「没有帮助就会做错」的事**；通用常识、模块细节、流程全文见分卷。
最小集：**14 条硬性约束** + 入口引导 + 环境命令 + 收尾检查单。

---

## 0 入口引导：先读哪一卷、改完必更新哪一卷

**开工**：按「你要做的事」读「先读」列的分卷（只读相关章节，禁止整卷通读）；**收尾**按「改完必更新」列更新分卷（硬性 #7，与代码同一次任务内完成）。
| 你要做的事 | 先读（分卷） | 改完必更新 |
|------------|-------------|-----------|
| 摸不清该动哪些模块 / 模块职责 | `INDEX.md`、`01-architecture.md` | `INDEX.md` |
| 读/分析代码、定位符号、查调用链与影响面 | **先走 `codegraph`**（硬性 #18）→ `09-agent-workflow.md` | — |
| 改路由、鉴权、Session、审计 | `02-routing-auth.md` | 该卷 + `INDEX.md` 路由表 |
| 改筛选/排序/分页/导出/API/全量护栏 | `03-report-transform.md`、`05-api.md` | 对应卷 + `INDEX.md` 共享语义表 |
| 改配置表字段 / 双引擎迁移 / `/config` CRUD | `04-config-data.md` | 该卷 |
| 改 UI、组件、CSS/JS、交互 | `06-ui-interactions.md` | 该卷（+ `test_ui_tokens.py`/`test_render.py`；按硬性 #17 验收） |
| 改缓存分层、定时任务、审计 type | `07-cache-scheduler-audit.md` | 该卷 |
| 改启动链路、`app_config`、依赖安装 | `01-architecture.md` | 该卷 + 双 README（镜像对） |
| 跑测试 / 改测试 / 验证改动、卡住反复失败 | `08-testing-conventions.md` | 该卷（新踩坑必记） |
| 查历史决策、需求依据 | `docs/compose/spec/` 最新生效 spec（§3） | 新 spec / 取代旧 spec |

**分卷全表**：`docs/compose/knowledge/README.md`（入口）· `INDEX.md`（模块/路由/页面/共享语义）。

---

## 1 硬性约束（违反即错误）

**只给结论，「怎么做」在指路的分卷里。编号是历史锚点：退役号（#4/#9/#10/#11/#13/#15/#16）不复用，`硬性 #N` 引用由门禁校验。**

1. **禁止研究与修改** `/alexblair/windir/www/SqlReport/`（生产副本，不在本仓库）。
2. **用户可感知文字一律简体中文**（文档/注释/UI 文案/提交说明/交流）。
3. **禁止重复造轮子**：新增 UI/筛选排序/导出/API/缓存/CRUD 前先找**单一实现来源**再拼装，禁止从零重写。→ `03-report-transform.md`、`06-ui-interactions.md`
5. **技术选型锁定**：纯 Python 3 标准库 + 极少量 pip 依赖；Web 层 `http.server`，前端服务端 HTML 字符串；**不要**引入 Django/Flask/React/Node 构建链。
6. **禁止污染系统环境**：一切测试/运行/安装必须在仓库根 `venv` 内（禁系统 Python、禁全局 site-packages）。
7. **知识库同步**：变更后同任务内更新受影响分卷与 `course-state.md`，只改代码不改知识库视为未完成；文档与代码冲突**以代码为准并回写**；**用户纠正/指示**当轮写入 `MEMORY.md`（复盘结论与代码事实进分卷，它不是垃圾桶）。
8. **测试纪律**：`discover` 必须带 `-t .`（否则隔离失效、会连生产 Redis）；范围 L0→L1→L2 递进，代码未变时全量**一次即可**；需求变更在**同一次任务内**改写受影响断言/夹具。→ `08-testing-conventions.md`
12. **同一问题失败 2 次必须停下找根因**：停手 → 只分析（报错/最小复现/相关模块）→ 写根因假设 → 一次针对性修改 + L0 验证。**禁止第 3 次盲试**；同一工具调用失败 2 次禁止原样重发。→ `08-testing-conventions.md`
14. **产物落盘与清场**：产物落 `run-logs/`/`perf-logs/`（`/tmp` 会被清空）、唯一文件名；**同一测试段上限 2 次**；禁人工 `rm`，收尾跑 `scripts/agent/cleanup_tmp.py --apply`；**依据类结论须落 `docs/compose/reports/`**。→ `09-agent-workflow.md`
17. **交互改动验收**：UI 改动先出确认稿并经用户确认再实施；验收覆盖**整页 + 原位换页态 + 第二/三次操作 + 组合序列**，新门禁须用 `gate_redproof.py` 做 RED-GREEN 自证；**先代码层定位，仅按需才起浏览器取证**。→ `06-ui-interactions.md`
18. **代码检索 codegraph-first**：`codegraph explore`（MCP `codegraph_explore`）必须是第一步，query 带代码词（纯中文查不到）；确查不到才降级 `grep`/`glob`/`read`，降级前先加宽重试；禁 grep+read 循环替代检索。→ `09-agent-workflow.md`
19. **改完 `.py`/`.js`/`.mjs` 必须同任务内 `codegraph sync`**（大重构 `codegraph index`）；收尾以 `codegraph status` 的 `pendingChanges` 全 0 为准。
20. **Token 预算**：成本 ≈ 步数 × 上下文。① 单条返回 >8k 字符即超阈（先计数/截断/分段读；后台作业先落盘再 grep）。② 互不依赖调用**同步发**（一步 2–4 个），单调用步 ≤40%。③ >60 步或上下文 >120k → 落盘交接换会话。④ `session_cost.py --check` 体检，收尾取证**一次批量发**。→ `10-token-budget.md`
22. **用户要求与掌握的最新依据冲突时，立即向用户确认**：不自我怀疑兜圈、不擅自取舍；依据优先级见 §3，UI 历史设计图只是取证不是现行依据。→ `06-ui-interactions.md`

---

## 2 知识库

**入口**：`docs/compose/knowledge/README.md` ·**索引**：`INDEX.md` ·**掌握状态**：`learn/sqlreport-kb/course-state.md` ·**代码索引**：仓库根 `codegraph`（`.codegraph/` 已 gitignore）。

1. **改代码 → 改知识库**（硬性 #7）：同一完成定义；**最小充分更新**，冲突以代码/测试为准并回写。
2. **冗余红线**：spec/plan 引用知识库只写链接，不复制现状事实。
3. **新增分卷必须登记**：`README.md` 与 §0 路由表同时登记，否则门禁判孤儿卷。
4. **文档预算**（门禁 `tests/test_doc_budget.py`）：`AGENTS.md` ≤11000B、`MEMORY.md` ≤13000B、单分卷 ≤22000B、分卷合计 ≤155000B、`course-state.md` ≤8000B；**超限只能压缩或把细节移入分卷，不得抬上限**。

---

## 3 spec / plan 约定

1. **路径唯一**：spec 只在 `docs/compose/spec/`、plan 只在 `docs/compose/plan/`（同日期同主题一一对应）；**禁止 `docs/superpowers/`**；`knowledge/` 只放知识库。
2. **格式**：状态头、取代两头改、plan 模板以 `docs/compose/spec/2026-09-28-docs-spec-plan-conventions-design.md` §3/§4 为准。
3. **开工查证**：`ls -t docs/compose/spec/` 取最新 → 读状态头找生效版 → 冲突按「**当次指示 > 本文件 > 最新生效 spec > 旧/被取代 spec > plan**」裁决并记入新 spec。
4. **取代两头改**：旧 spec 状态头改「已被 X 取代」+ 日期 + 原因，新 spec 写 `取代关系:`；只改新不改旧 = 未完成。
5. `docs/` 与仓库根 `AGENTS.md` 随任务正常提交。

---

## 4 环境与命令

工作目录：**仓库根**（`server.py` 所在目录）。搜索限本项目目录内，禁 `find /` 等全局搜索。

```bash
./install.sh && source venv/bin/activate        # 必须先激活 venv
python server.py                                # 默认 0.0.0.0:8080
python -m unittest discover -s tests/ -t . -v   # 全量（含 bug_hunt 静态分析）；-t . 不可省
codegraph explore "<中文意图 + 代码词>"          # 检索首选
codegraph status                                # 索引健康/pendingChanges
codegraph sync                                  # 改完代码必跑（硬性 #19）
venv/bin/python scripts/agent/session_cost.py --check    # token 体检（#20）
```
- 测试框架以 **`unittest`** 为准；静态分析随 discover 跑（ERROR 即失败）；变异扫描 `tests/bug_hunt/bug_hunt_mutation.py` 手动、勿常规。
- 服务：`sudo bash manage_service.sh install|uninstall`；Git 辅助 `./git-tool.sh`（勿强推共享分支）。
- **改依赖同步三处**：`requirements.txt` + `README.md`/`README-CN.md` + `install.sh`；**改 README 必须中英同步**。

---

## 5 收尾检查单

1. 测试 L0/L1 →（需要时）L2 分段全量绿（本任务内一次）
2. 知识库按 §0「改完必更新」列同步；spec 已按 §3 查证
3. 硬性 #19：`codegraph sync` 后 `pendingChanges` 全 0；硬性 #17：交互改动跑「整页 + 换页态 + 组合序列」
4. **收尾一次批量取证**（禁一项一步）：测试 + `codegraph status` + `git diff --stat` + `session_cost.py --check`；结论**报证据**（Ran N / 文件:行 / 数据），不报「应该是」

