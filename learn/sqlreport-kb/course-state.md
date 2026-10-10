# 课程状态 · SqlReport 代码知识库

- slug: `sqlreport-kb`
- 模式: document（源 = 仓库代码 + AGENTS.md + README-CN + explore 报告）
- 目标能力: compose 代理能独立定位功能/UI/逻辑入口，按共享语义改代码而不重造轮子
- 状态更新: 章节边界维护

## 课程地图

| # | 章节 | 产物 | 状态 |
|---|------|------|------|
| 0 | 索引初始化 | codegraph 索引（`.codegraph/`，计数见 `README.md`） | 完成 |
| 1 | 架构与配置 | `01-architecture.md` | 完成 |
| 2 | 路由与鉴权 | `02-routing-auth.md` | 完成 |
| 3 | 报表与变换 | `03-report-transform.md` | 完成 |
| 4 | 配置数据层 | `04-config-data.md` | 完成 |
| 5 | API | `05-api.md` | 完成 |
| 6 | UI 交互 | `06-ui-interactions.md` | 完成（ui-redesign / UI v2 重写后，页面地图口径见 06 卷与 ui-v2 spec） |
| 7 | 缓存调度审计 | `07-cache-scheduler-audit.md` | 完成 |
| 8 | 测试与坑 | `08-testing-conventions.md` | 完成 |
| 9 | 代理工作流 | `09-agent-workflow.md` | 完成 |
| 10 | Token 预算 | `10-token-budget.md` | 完成（硬性 #20） |

入口：`docs/compose/knowledge/README.md` + `INDEX.md`。

**文档结构约定**：`AGENTS.md` 只保留「每次任务都要读」的最小集（硬性约束 + §0 入口引导路由表 + 环境命令 + 收尾检查单）；凡「只在特定类型任务才需要」的流程全文一律在本库分卷，新增内容先判断它属于最小集还是分卷。

## 概念掌握表

| 概念 | 状态 | 复习点 |
|------|------|--------|
| codegraph 优先检索 + 改完必 sync（硬性 #18/#19） | mastered | 出现「先 grep 后 explore」时 |
| ROUTES 首次匹配 + needs_db 边界 | mastered | 新 URL |
| Session 滑动 + 限流 + next 白名单 | mastered | 改登录 |
| result_transform 单一语义 | mastered | 改筛选 |
| 写护栏三端 + 静态 `.json` 再拦 | mastered | 改 allow_write |
| 导出默认 gbk、先截断后筛 | mastered | 改导出 |
| 双引擎迁移三处同步 | mastered | 改表 |
| API Key 语义（公开 vs 全禁）、CORS 空≠允许 | mastered | 改鉴权/跨域 |
| render 单一来源 + 嵌套 form | mastered | 新 UI |
| ui-redesign / UI v2「石墨·鸢尾」布局与组件口径 | mastered | 改页面布局/组件/CSS 前读 06 卷与 visual-spec |
| vendor hash = CSS+JS 拼接哈希 | mastered | 改 CSS/JS |
| L1/L2/L3 + 保活先算后换 | mastered | 改缓存 |
| scheduler exclusions ≠ nested_filter | mastered | 改调度 |
| 审计四类 type | mastered | 改审计 |
| unittest 入口 + `-t .` 隔离（硬性 #8） | mastered | 跑全量测试时 |
| 测试范围递进 + 分段全量防超时 + 禁反复全量 | mastered | 改测试流程 |
| 同一问题失败 2 次停手、根因优先再改（硬性 #12） | mastered | 调试卡住时 |
| UI 先可交互 HTML 确认、严格按确认稿（硬性 #17） | mastered | 设计稿/UI 优化 |
| `cache_info.source` / `snapshot_written` 取数来源标注 | mastered | 改缓存徽标时 |
| 派生态缓存（C-3）挂 `CachedResult`、零失效 | mastered | 改 transform / 加缓存层 |
| 导出并入三层缓存（C-4） | mastered | 改导出 |
| MySQL 连接池：`close()` 归还语义、`read_timeout` 进池键 | mastered | 改 query_executor |
| `Decimal` 必须进 isinstance 快速路径 | mastered | 改 result_transform |
| `filter_rows` 单趟化反而更慢 | mastered | 想优化 filter 时 |
| 测试进程会连生产 Redis（无隔离时） | mastered | 写涉及缓存的测试时 |
| 断言「隔离是否生效」的测试不能自己 import tests | mastered | 写环境守卫类测试时 |
| 写判定分工：`sql_contains_write` vs `sql_has_persistent_write` | practiced | 动 allow_write / skip_cache_read / 静态护栏时 |
| 静态护栏是**并集**（权限判定 + 持久写判定） | practiced | 改静态分支条件时 |
| `INTO OUTFILE`/`INTO DUMPFILE` 属持久写 | mastered | 改写判定关键词时 |
| 端到端压测噪声约 ±6%，收益须用隔离 A/B | practiced | 做性能对比时 |

## 复习队列

- 若将来把「临时表名追踪」纳入写判定（会话级 DML 目标为本脚本内建的临时表），需先补单测再改 spec 结论。

## 下一步（可选）

1. 改完代码 `codegraph sync`（硬性 #19，本机无守护进程自动同步）。
2. 改共享语义时按 `INDEX.md`「共享语义」表全链路搜调用点。

## 状态块

```text
slug=sqlreport-kb
chapters=0..10 done
kb=<repo>/docs/compose/knowledge/   # 仓库根相对；主目录可变，勿写死绝对路径
index=codegraph ok（计数与版本以 docs/compose/knowledge/README.md 为准）
sources=code+AGENTS+README+explore agents
gaps=none blocking
last_sync=2026-10-09（SQL 编辑框滚动条契约修复 + 执行效率治理；更早的 last_sync 流水已压缩）
```

> 变更史归档在 `docs/compose/reports/` 与各 spec；本文件只保留当前状态。
