# 课程状态 · SqlReport 代码知识库

- slug: `sqlreport-kb`
- 模式: document（源 = 仓库代码 + AGENTS.md + README-CN + 4 个 explore 报告）
- 目标能力: compose 代理能独立定位功能/UI/逻辑入口，按共享语义改代码而不重造轮子
- 状态更新: 章节边界维护

## 课程地图

| # | 章节 | 产物 | 状态 |
|---|------|------|------|
| 0 | 索引初始化 | `codegraph init` → `.codegraph/`（100 files / 6037 nodes / 15144 edges） | 完成 |
| 1 | 架构与配置 | `01-architecture.md` | 完成 |
| 2 | 路由与鉴权 | `02-routing-auth.md` | 完成（explore-1 增补） |
| 3 | 报表与变换 | `03-report-transform.md` | 完成（explore-3 增补） |
| 4 | 配置数据层 | `04-config-data.md` | 完成（explore-2 增补） |
| 5 | API | `05-api.md` | 完成（explore-1 增补） |
| 6 | UI 交互 | `06-ui-interactions.md` | 完成（ui-redesign T9 重写 + R2-D：API 列表 api-row 卡片/详情五页签对齐 page-detail——qf-row 快筛、结果集 segment、分页恒显、规则双卡、调试磁贴、备注卡片；**emoji→SVG 图标系统（_icon 函数）、CSS 按钮类补齐、侧栏 button→a 语义修复**） |
| 7 | 缓存调度审计 | `07-cache-scheduler-audit.md` | 完成 |
| 8 | 测试与坑 | `08-testing-conventions.md` | 完成（已同步范围递进/分段全量/路径可移植/两败找根因） |

入口：`docs/compose/knowledge/README.md` + `INDEX.md`

## 概念掌握表

| 概念 | 状态 | 证据 | 置信度 | 复习点 |
|------|------|------|--------|--------|
| codegraph 索引 | mastered | status up to date | 高 | 大改后 sync |
| ROUTES 首次匹配 + needs_db=False 边界 | mastered | server:244-263 + explore-1 | 高 | 新 URL |
| Session 滑动 + 限流 + next 白名单 | mastered | auth + explore-1 | 高 | 改登录 |
| result_transform 单一语义 | mastered | docstring + 三端调用 | 高 | 改筛选 |
| 写护栏三端 + 静态 json 再拦 | mastered | report/export/api + explore | 高 | 改 allow_write |
| 导出默认 gbk、先截断后筛 | mastered | export + explore-1 | 高 | 改导出 |
| 双引擎迁移三处同步 | mastered | AGENTS + config_db + explore-2 | 高 | 改表 |
| API Key 语义（公开 vs 全禁） | mastered | _validate_api_key | 高 | 改鉴权 |
| CORS 空≠允许 | mastered | explore-1 | 高 | 改跨域 |
| render 单一来源 + 嵌套 form | mastered | explore-4 + htmlcheck | 高 | 新 UI |
| ui-redesign 重构（侧栏/令牌/页签/抽屉/导出对话框/术语表） | mastered | docs/compose/spec/ui-redesign.md + 全量 2844 项对账 | 高 | 改任何页面布局/组件前读 06 卷与 visual-spec |
| vendor hash = CSS+JS 拼接哈希 | mastered | explore-4 + R2 核对 | 中高 | 改 CSS 或 JS 都会变 |
| L1/L2/L3 + 保活先算后换 | practiced | explore-2 | 中 | 改缓存 |
| scheduler exclusions ≠ nested_filter | mastered | explore-3 | 高 | 改调度 |
| 审计四类 type | mastered | explore-1 | 高 | 改审计 |
| unittest 入口 | mastered | AGENTS | 高 | — |
| 测试范围递进 + 分段全量防超时 + 禁反复全量 | mastered | AGENTS 硬性 #8 + 08 分卷 | 高 | 改测试流程 |
| 测试/脚本对齐最新需求、禁硬编码主目录 | mastered | AGENTS 硬性 #9–#10 + 08 分卷 | 高 | 写测试/脚本/文档 |
| UI 先可交互 HTML 确认、严格按确认稿、全局视觉一致 | mastered | AGENTS 硬性 #11 + 06 分卷 | 高 | 设计稿/UI 优化 |
| 同一问题失败 2 次停手、根因优先再改 | mastered | AGENTS 硬性 #12 + 08 分卷 | 高 | 调试/测试卡住时 |

## 复习队列

- （空）

## 错误日志

- 用户写 `codegrade init`：环境无此 CLI；PyPI `codegrade` 为 CodeGrade 教学平台 API 客户端。实际使用 **`codegraph init`** 完成索引。
- playwright-cli 默认 chrome 渠道 + Linux root：需 `~/.playwright/cli.config.json` 嵌套 schema `{browser:{launchOptions:{channel:"chrome",chromiumSandbox:false}}}`（扁平键会被静默忽略）；Chrome for Testing 用 /tmp/a 离线包解压至 /opt/chrome-offline 并软链 /opt/google/chrome，依赖补 libgbm1。

## 下一步（可选）

1. 大改前 `codegraph sync`（ui-redesign 后应执行）
2. 改共享语义时按 INDEX「共享语义」表全链路搜调用点
3. 探索报告全文已并入各分卷；若需原始长文可回看会话 actor 结果

## 状态块

```text
slug=sqlreport-kb
chapters=0..8 done
kb=<repo>/docs/compose/knowledge/   # 仓库根相对；主目录可变，勿写死绝对路径
index=codegraph ok (100 files, 6037 nodes)
sources=code+AGENTS+README+4 explore agents
gaps=none blocking
```
