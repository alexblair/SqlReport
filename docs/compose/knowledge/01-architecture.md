# 架构 · 启动 · 配置 · 缓存分层

## 技术选型（锁定）

- Python 3.11+，**无 Web 框架**：`http.server.ThreadingHTTPServer`
- 前端：服务端 HTML 字符串 + 公共 CSS/JS
- 依赖：`mysql-connector-python`、`redis`、`markdown`、`pygments`、`pytest`（测试）
- 配置存储：SQLite / MySQL（`config_db` 列表 + `enable`）

## 启动链路（`server.main` ~:934）

1. `setup_logging` → `render.ensure_common_assets()` 预热公共资产  
2. `file_permissions.load_permissions` + `refresh_tree(static_cache.permissions_root())`  
3. `get_config_db` → `init_db` → 首次创建默认 admin/admin123（仅日志提示）  
4. `init_audit_db` → `auth.load_sessions` → 启动轮转过期审计  
5. `ThreadingHTTPServer((HOST,PORT), ReportHandler)`；端口占用尝试 `fuser -k`  
6. `start_scheduler_from_config()` → daemon `serve_forever` → join 等 Ctrl+C  

安装：`./install.sh` → `source venv/bin/activate`  
服务：`sudo bash manage_service.sh install`（单元 `web-report`）  
本地测试环境：`./test_env.sh start|stop|restart|status|log|fg`——默认 `0.0.0.0:8099`（任意地址可访问），靠 `HOST`/`PORT` 环境变量覆盖（`get_server_config` 中优先级最高，**不改配置文件**）；不设 `CONFIG_FILE` → 自动叠加 `app_config.debug.json`，测试环境落 `config.debug.db`/`audit.debug.db`/`run.debug.log`；PID 文件与控制台日志在 `run-logs/`；停止走 SIGINT（命中 `server.py` 优雅关闭分支）→ SIGTERM → SIGKILL 逐级兜底。可用 `TEST_PORT`/`TEST_HOST`/`TEST_BASE_CONFIG=1` 覆盖。
## 版本线与分支策略（2026-10-05 起）

| 版本线 | 分支 | 固定标签 | 当前提交 | 状态 |
|--------|------|----------|----------|------|
| V1 | `V1` | `v1-final` | `9a975b9` | **冻结**：受 GitHub 仓库规则 `V1-freeze`（id 24514074）保护，禁 update / 禁删除 / 禁强推，实测推送报 `GH013: Repository rule violations found` |
| V2 | `V2`（**默认分支**） | `v2.0.0`（含版本切换指南） | 分支头（持续前进） | 活跃主干：后续提交、修复、发版只进 V2 |

- 旧名 `main` 已改名为 `V1`。**GitHub 的分支改名重定向只覆盖网页/API，不覆盖 `git` 协议的 refspec 匹配**：`git ls-remote origin main` 为空、`git clone -b main …` 失败、老 clone 的 `origin/main` 永不更新。
- **用户侧取版与切换的单一来源是仓库根 `docs/version-switch-guide.md`**（本卷只记布局与纪律，不复制操作步骤）；双 README 的「快速开始/Quick Start」各有一行入口链接。
- 两条线共用同一套配置库结构：V1→V2 未改 `config_db.py`（无 `CREATE TABLE`/`ALTER TABLE`），`requirements.txt` 零差异 → `git checkout` 往返切换不需要重装依赖、不需要迁移数据。**V2 之后若改表结构，回退 V1 必须同时恢复当天的 `config.db` 备份。**
- 维护纪律：开发只在 V2；发版 `git tag -a v2.x.y -m …` 后显式 `git push origin v2.x.y`；**不要向 V1 推送**（会被规则拒绝）；V1 的唯一可信基准是 tag `v1-final`。

## 应用配置（`app_config.py`）

| 文件 | 作用 |
|------|------|
| `app_config.json` | 主配置（**不入库**，模板 `app_config.example.json`） |
| `app_config.debug.json` | DEBUG **深合并**（dict 递归；**list 整段覆盖**），模板 `app_config.debug.example.json` |
| `CONFIG_FILE` / `DEBUG_CONFIG_FILE` | 显式 CONFIG_FILE 且未设 DEBUG_CONFIG_FILE → **跳过** debug 叠加 |

关键 API：`get_config/reload_config/is_debug_mode`、`get_server_config`（HOST/PORT env 最高）、`get_trust_xff`、`get_active_db_config`、`get_redis_config`、`serialize_json` / `serialize_smart_quotes`。

分段：`server{host,port,trust_xff}` `log` `error_log` `redis` `static_cache` `file_permissions` `audit_db` `config_db[]`、`test_mysql`（性能/集成测试数据源）。

### 测试与 DEBUG 的隔离（硬性）

- 测试进程隔离在 `tests/_bootstrap.py`（由 `tests/__init__.py` 调用）：`DEBUG_CONFIG_FILE` 指到不存在路径、vendor 落点与站点标识库重定向到临时目录、**Redis 强制关闭**。**勿在测试里依赖仓库根 debug 配置或真实 Redis。**
- **一切 `discover` 必须带 `-t .`**，否则测试模块被当顶层模块导入、`tests/__init__.py` 不执行、上述隔离全部失效（会连生产 Redis）。`tests/test_test_isolation.py` 是金丝雀会报警。详见 `08-testing-conventions.md`。
- **真层集成测试**（`tests/integration/`）：仅当 DEBUG 配置存在时运行；MySQL 未配置/连不上则 skip，**不视为失败**。
- 敏感/运行时文件均在 `.gitignore`（`app_config*.json` 非 example、`config.db`、`audit.db`、`venv/`、`static_cache/`、`run-logs/`、`perf-logs/`、`static/vendor/self@*/` 等）——**不要提交**。

## 双引擎配置库

- `config_db.get_config_db()`：每请求一次独立连接  
- SQLite：WAL+FK；`path` 或 env `CONFIG_DB` 默认 `config.db`  
- MySQL：host/port 或 socket  
- Schema + 双侧迁移 + `tests/test_base.py` DDL **三处同步**（见 04 卷）  
- `db.py` 仅 re-export；新代码 `import config_db` / `query_executor`

## 模块地图（真正影响写法的部分）

单包扁平布局，**无 monorepo**；入口只有 `server.py`。模块行数见 `INDEX.md` §1（2026-10-06 实测）。

| 职责 | 模块 | 要点 |
|------|------|------|
| 路由 / HTTP | `server.py` | `ROUTES` **按列表顺序首次匹配**；`needs_auth` / `needs_db` 在 `RouteEntry` 上声明。新 URL 必须进 `ROUTES`，注意与既有正则的先后关系 |
| 配置页 CRUD | `config.py` | `/config*` 表单与页面 |
| 配置数据访问 + 表结构 | `config_db.py` | 建表 DDL、**双引擎迁移**、全部配置表 DAL |
| 兼容转发层 | `db.py` | 仅 re-export；**新代码直接 `import config_db` / `query_executor`** |
| 报表页 | `report.py` | 分页/排序/筛选 URL 解析（`parse_filters` / `parse_sorts` / `parse_nested_filter`）、`execute_report`、派生态缓存 |
| 结果变换（纯函数） | `result_transform.py` | **页面 / 导出 / API / 预设共用**的筛选排序列选择；勿在别处重写匹配语义 |
| 筛选语法说明 | `filter_help.py` | 帮助弹窗单一来源，与 `parse_filter_expr` 行为对齐 |
| 导出 | `export.py` | CSV/JSON/ZIP；数据来源走 `execute_report`（复用缓存） |
| API | `api_handler.py` | API Key、CORS、静态 `.json`、预设与 JSON 模板 |
| MySQL 执行 | `query_executor.py` | 事务多语句、连接池；`sql_contains_write` + 报表 `allow_write` 写护栏 |
| HTML / CSS / JS | `render.py` | **全站 UI 单一来源**（见 `06-ui-interactions.md`） |
| 缓存 | `redis_cache.py` / `static_cache.py` | L1 进程 → L2 Redis → DB；API `.json` 静态缓存 |
| 定时任务 | `scheduler.py` | 进程内 daemon 线程，无外部调度器 |
| 认证 / 审计 / 品牌 | `auth.py` / `audit_db.py`+`audit_page.py` / `branding.py` | branding 用**实例本地**独立 SQLite，不进配置库 |
| 应用配置 | `app_config.py` + `app_config.json` | 见「应用配置」节 |

路由/鉴权细节见 `02-routing-auth.md`；筛选/排序/导出/护栏语义见 `03-report-transform.md`；
表结构变更三处同步见 `04-config-data.md`；缓存与调度见 `07-cache-scheduler-audit.md`。

**改任何模块前先读它对应的那一卷**，不要在本表里猜细节。

## 缓存分层

```
L1 process QueryCache (~300s)
  → L2 Redis 快照（版本键+锁+保活）
    → L3 MySQL

L1 之上还有一层请求级 memo：C-3 派生态缓存（`CachedResult.derived`），
不属于这三层中的任何一层，详见 `03-report-transform.md`。

API 静态：static_cache/api/**.json + config_version + TTL；NGINX 可直出
```

缓存分层的完整语义见 `07-cache-scheduler-audit.md`；导出已并入该链路（C-4），
见 `03-report-transform.md`。

## MySQL 连接获取（`query_executor`）

`create_mysql_connection(pool_config, read_timeout=None)` 走**有界连接池**
（上限 `_POOL_MAX_SIZE = 8`，模块常量非配置项）。

| 要点 | 说明 |
|------|------|
| **`close()` 语义是「归还池」** | 返回 `_PooledConnection`，不是 mysql.connector 的 Connection。正因如此 `report.execute_report` 的 `finally: conn.close()` **一行都不用改**，Redis 契约与调用链不受影响 |
| **池键含 `read_timeout`** | Web 交互传 30s、调度器/API 传 `None` 不限制（批次 5#18）。混池会让调度器的慢报表拿到 30s 超时的连接而**必然失败**——语义错误，不可合并 |
| 降级 | 池空 / 池满 / 池中连接已死 → 自动直连。池的任何异常都不导致功能不可用 |
| 探活 | 归还与借出都 `ping(reconnect=True)`；归还时已死则真关闭不入池。探活约 0.13ms |
| 实测 | **本机 MySQL（127.0.0.1）下实测无收益**，单线程慢 3.6ms/次、4/8 并发各慢 2%/3%。保留是为远程 MySQL 部署预留（网络 RTT 下连接成本高一个量级） |

写测试时注意：连接池是**进程级全局**，测试注入的假连接归还后会泄漏给下一个
用例。`BaseReportTest.setUp` 与各导出测试的 `setUp` 已统一 `clear_pools()`。

## 运行时勿提交

`app_config*.json`（非 example）、`config.db`、`audit.db`、`venv/`、`static_cache/`、
`run-logs/`、`perf-logs/`、`static/vendor/self@*/`、`.codegraph/`、`AGENTS.md`、
`.mimocode/`（见 `.gitignore`）。

**注意**：`docs/`（spec / plan / 知识库）**已从 `.gitignore` 移除、随任务正常提交**；
`MEMORY.md` 同样入库。勿把它们当忽略物。

## 易踩坑

- 测试重定向 vendor 根——勿断言真实 `self@*`  
- 集成真库测试仅 DEBUG 且 MySQL 可连才跑  
- 改依赖同步：`requirements.txt` + 双 README + `install.sh`  
- README 项目结构可能过时——以当前目录/代码为准  

---
最后核对：explore 报告 + AGENTS + 源码
