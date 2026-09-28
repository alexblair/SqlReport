# SqlReport 知识库（Compose 可读）

> 供 compose / 编码代理**主动阅读**的项目知识入口。  
> **本 README 是知识库唯一入口**（仓库根 `AGENTS.md`「项目知识库」一节引用此路径）。  
> 代码索引：`codegraph init`（本机已建 `.codegraph/`，勿提交）。  
> 约束总纲见仓库根 `AGENTS.md`（本地、不入库）。

## 如何使用本库

1. 改功能前：先读 `AGENTS.md` → 对应主题卷 → 再用 `codegraph explore` / 读源码核对。
2. **文档与代码冲突时以代码 / 测试为准**，并回写修正知识库。
3. 主题卷按需读，不必一次读完；`INDEX.md` 是路由表。

## 需求变更后必须自动同步

与 `AGENTS.md` 硬性约束 #7、§「项目知识库」一致：

- 需求 / 功能 / UI / 路由 / 共享语义 / 配置表等变更落地时，**同一次任务内**自动更新受影响分卷与 `INDEX.md`（及必要时本 README、`learn/sqlreport-kb/course-state.md`）。
- 只改代码不改知识库 = 任务未完成。
- 同步范围以 AGENTS.md「何时必须自动同步更新」表为准；最小充分更新，以代码为准回写。

## 索引

| 文档 | 内容 |
|------|------|
| [INDEX.md](./INDEX.md) | 模块地图、路由总表、页面地图、共享语义 |
| [01-architecture.md](./01-architecture.md) | 架构、启动、配置、缓存分层 |
| [02-routing-auth.md](./02-routing-auth.md) | 路由、Session、公开路由、鉴权 |
| [03-report-transform.md](./03-report-transform.md) | 报表页、筛选排序、导出、全量护栏 |
| [04-config-data.md](./04-config-data.md) | 配置 CRUD、双引擎 DAL、迁移 |
| [05-api.md](./05-api.md) | 报表即 API、Key、CORS、静态 `.json` |
| [06-ui-interactions.md](./06-ui-interactions.md) | UI 组件、页面交互、render 单一来源 |
| [07-cache-scheduler-audit.md](./07-cache-scheduler-audit.md) | 缓存、定时任务、审计 |
| [08-testing-conventions.md](./08-testing-conventions.md) | 测试、验证顺序、易踩坑清单 |

## 一句话产品定位

**SqlReport**：纯 Python 标准库 + 极少 pip 依赖的 MySQL 报表引擎——SQL 进，网页报表 + HTTP API 出；无 Django/Flask/React/Node 构建链。

## 关键硬约束（摘自 AGENTS.md）

- 全部用户可感知文字：**简体中文**
- 禁止重复造轮子：UI/筛选/导出/API/缓存/配置 CRUD 必须复用单一实现
- 先研究后修改；技术选型锁定 `http.server` + 服务端 HTML 字符串
- 禁止研究/修改生产副本 `/alexblair/windir/www/SqlReport/`
- 测试先最小后放大、分段全量防超时、代码未变不反复全量；测试/脚本对齐最新需求；**禁止硬编码本仓库主目录**（见 08 分卷）
- **同一问题失败 2 次必须停下分析根因**，禁止第 3 次盲目试错（见 08 分卷 / AGENTS 硬性 #12）
- **UI/视觉/交互**：先可交互 HTML 确认再实施；严格按确认稿；确认稿与实现须对齐全局组件视觉；禁止交付不符、禁止混乱 DOM/CSS 直塞生产（见 06 分卷）

## 索引状态

- CodeGraph：100 文件 / 6037 节点 / 15144 边（`codegraph status`）
- 生成时间：见各分卷页脚「最后核对」
