# SqlReport 知识库（Compose 可读）

> 供 compose / 编码代理**主动阅读**的项目知识入口。  
> **本 README 是知识库唯一入口**（仓库根 `AGENTS.md` §2 引用此路径）。  
> 代码索引：`codegraph init`（本机已建 `.codegraph/`，勿提交）；**读/分析代码强制先走它**（#18）。  
> 约束总纲见仓库根 `AGENTS.md`（本地、不入库）——**它只有 141 行**，是每次任务都读的最小集；
> 模块细节、流程全文都在本库分卷里，由 `AGENTS.md` §0 路由表指引。

## 如何使用本库

1. **开工第一步看 `AGENTS.md` §0「入口引导」路由表**——按「你要做的事」查到该读哪一卷、改完必更新哪一卷。本库按需读涉及章节，不必整卷读完。
2. 查代码先 `codegraph explore "<中文意图 + 代码词>"`（硬性 #18，纯中文问句查不到）→ 再读分卷核对，再动手。
3. **文档与代码冲突时以代码 / 测试为准**，并回写修正知识库。
4. `INDEX.md` 是模块/路由/页面/共享语义的路由表；**不是**任务查证入口（任务查证看 `docs/compose/spec/` 最新生效 spec）。

## 需求变更后必须自动同步

与 `AGENTS.md` 硬性约束 #7、§0 路由表「改完必更新」列一致：

- 需求 / 功能 / UI / 路由 / 共享语义 / 配置表等变更落地时，**同一次任务内**自动更新受影响分卷与 `INDEX.md`（及必要时本 README、`learn/sqlreport-kb/course-state.md`）。
- 只改代码不改知识库 = 任务未完成。
- 最小充分更新，以代码为准回写。

## 索引

| 文档 | 内容 |
|------|------|
| [INDEX.md](./INDEX.md) | 模块地图、路由总表、页面地图、共享语义 |
| [01-architecture.md](./01-architecture.md) | 架构、启动、应用配置与 DEBUG 隔离、**模块地图**、缓存分层、MySQL 连接池 |
| [02-routing-auth.md](./02-routing-auth.md) | 路由总表、Session、公开路由、鉴权边界、审计 |
| [03-report-transform.md](./03-report-transform.md) | 报表页、筛选排序、导出、全量护栏、**transform 性能要点**、派生态缓存 |
| [04-config-data.md](./04-config-data.md) | 配置 CRUD、双引擎 DAL、迁移、**表结构变更三处同步** |
| [05-api.md](./05-api.md) | 报表即 API、Key、CORS、静态 `.json` |
| [06-ui-interactions.md](./06-ui-interactions.md) | **UI 任务四阶段流程**、UI 组件、页面交互、render 单一来源 |
| [07-cache-scheduler-audit.md](./07-cache-scheduler-audit.md) | 缓存分层、定时任务、审计 type |
| [08-testing-conventions.md](./08-testing-conventions.md) | 测试入口、**`-t .` 陷阱**、性能工具链、**两败必停**、**L2 分段命令表**、易踩坑清单 |
| [09-agent-workflow.md](./09-agent-workflow.md) | **多代理协作纪律（#13–#15）**、**执行效率与取证纪律（P1–P7）**、**代码检索纪律（#18/#19：codegraph 优先 + 改完 sync）**、汇报节奏 |

**跨会话记忆与流程资产**（不在知识库分卷内，但每轮开工必查）：

| 文档 | 内容 |
|------|------|
| `MEMORY.md`（仓库根） | **开工必读**：Rules（用户纠正 + 复盘结论）+ Discovered 环境事实 |
| `docs/compose/consult/TEMPLATE.md` | 外部求援模板：2 轮未解即产出自包含咨询 MD，交用户联网回填 |
| `docs/compose/spec/shots/r3/` | 截图自证管线 `shot-verify.mjs`（像素↔DOM 回验）+ 取证脚本 |
| `docs/compose/reports/ui-r3-retrospective.md` | R3 复盘：token 消耗分解、典型错误根因、开工自检清单 |

## 一句话产品定位

**SqlReport**：纯 Python 标准库 + 极少 pip 依赖的 MySQL 报表引擎——SQL 进，网页报表 + HTTP API 出；无 Django/Flask/React/Node 构建链。

## 关键硬约束（摘自 AGENTS.md）

> **完整条目与指路见仓库根 `AGENTS.md` §1**（19 条，每条一行）；此处只是速览。

- 全部用户可感知文字：**简体中文**
- 禁止重复造轮子：UI/筛选/导出/API/缓存/配置 CRUD 必须复用单一实现
- 先研究后修改；技术选型锁定 `http.server` + 服务端 HTML 字符串
- 禁止研究/修改生产副本 `/alexblair/windir/www/SqlReport/`
- 测试先最小后放大、分段全量防超时、代码未变不反复全量；**`discover` 必须带 `-t .`**；测试/脚本对齐最新需求；**禁止硬编码本仓库主目录**（→ 08 卷）
- **同一问题失败 2 次必须停下分析根因**，禁止第 3 次盲目试错（→ 08 卷）
- **UI/视觉/交互**：先可交互 HTML 确认再实施；严格按确认稿；禁止交付不符、禁止混乱 DOM/CSS 直塞生产（→ 06 卷）
- **子代理**：同任务至多一个活跃子代理；效率预算与轮询退出判据（→ 09 卷）
- **执行效率 P1–P7**：等待协议、取证双产出、编辑三拍、先验证后落笔、纠正即入库、收尾必报（→ 09 卷）
- **代码检索强制 codegraph 优先**（#18：查不到才降级 grep/read）+ **改完代码必 `codegraph sync`**（#19）→ 09 卷「代码检索纪律」

## 索引状态

- CodeGraph v1.4.0：146 文件 / 6870 节点 / 17278 边（python 121 + javascript 25；`codegraph status`）
- 生成时间：见各分卷页脚「最后核对」
