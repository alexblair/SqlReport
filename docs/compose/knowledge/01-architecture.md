# 架构 · 启动 · 配置 · 缓存分层

## 技术选型（锁定）

纯 Python 3 标准库 + 极少量 pip 依赖（`mysql-connector-python`、`redis`、`markdown`、`pygments`）；Web 层 `http.server.ThreadingHTTPServer`，前端服务端 HTML 字符串 + 公共 CSS/JS；**禁止**引入 Django/Flask/React/Node 构建链（硬性 #5）。配置存储双引擎：SQLite / MySQL，由 `config_db` 列表 + `enable` 选择。

## 启动链路（`server.main`）

1. `setup_logging` → `render.ensure_common_assets()` 预热公共资产
2. `file_permissions.load_permissions` + 刷新静态缓存权限根
3. `get_config_db` → `init_db` → 首次创建默认 admin（仅日志提示）
4. `init_audit_db` → `auth.load_sessions` → 启动轮转过期审计
5. `ThreadingHTTPServer((HOST, PORT), ReportHandler)`；端口占用尝试 `fuser -k`
6. `start_scheduler_from_config()` → daemon `serve_forever` → join 等 Ctrl+C

各步函数签名与行号见 `server.py`（`codegraph` 可查）。

**安装 / 部署 / 服务单元**：`./install.sh` → `source venv/bin/activate`；服务 `sudo bash manage_service.sh install`，systemd 单元名 **`web-report`**。

**本地测试环境**：`./test_env.sh start|stop|restart|status|log|fg`，默认 `0.0.0.0:8099`；`HOST`/`PORT` 环境变量优先级最高（不改配置文件）。不设 `CONFIG_FILE` 时自动叠加 `app_config.debug.json`，落 `*.debug.db` / `run.debug.log`；PID 与控制台日志在 `run-logs/`。停止走 SIGINT（命中 `server.py` 优雅关闭分支）→ SIGTERM → SIGKILL 逐级兜底；可用 `TEST_PORT`/`TEST_HOST`/`TEST_BASE_CONFIG=1` 覆盖。

**双 README 约定**：`README.md`（英）与 `README-CN.md` 是镜像对，改一处必须中英同步；改依赖同步三处：`requirements.txt` + 双 README + `install.sh`。版本线纪律（V1 冻结 / V2 主干）见仓库根 `MEMORY.md` Rule 7，用户侧切换步骤的单一来源是 `docs/version-switch-guide.md`，本卷不复制。

## 应用配置（`app_config.py`）

| 文件 | 作用 |
|------|------|
| `app_config.json` | 主配置（**不入库**，模板 `app_config.example.json`） |
| `app_config.debug.json` | DEBUG **深合并**（dict 递归；**list 整段覆盖**），模板 `app_config.debug.example.json` |
| `CONFIG_FILE` / `DEBUG_CONFIG_FILE` | 显式 CONFIG_FILE 且未设 DEBUG_CONFIG_FILE → **跳过** debug 叠加 |

`get_server_config` 中 `HOST`/`PORT` 环境变量优先级最高。读取 API（`get_config`/`reload_config`/`is_debug_mode`/`get_trust_xff`/`get_active_db_config`/`get_redis_config`/`serialize_*`）与分段字段（`server`/`log`/`redis`/`static_cache`/`file_permissions`/`audit_db`/`config_db[]`/`test_mysql` 等）见 `app_config.py`。

### 测试与 DEBUG 的隔离（硬性）

- `tests/_bootstrap.py`（由 `tests/__init__.py` 调用）隔离测试进程：`DEBUG_CONFIG_FILE` 指到不存在路径、vendor 落点与站点标识库重定向到临时目录、**Redis 强制关闭**。**勿在测试里依赖仓库根 debug 配置或真实 Redis。**
- **一切 `discover` 必须带 `-t .`**（硬性 #8），否则测试模块被当顶层导入、隔离全部失效并会连生产 Redis；`tests/test_test_isolation.py` 是金丝雀。详见 `08-testing-conventions.md`。
- 真库集成测试（`tests/integration/`）仅在 DEBUG 配置存在时运行；MySQL 未配置/连不上则 skip，**不视为失败**。

## 双引擎配置库

- `config_db.get_config_db()`：每请求一次独立连接。
- SQLite：WAL+FK，`path` 或 env `CONFIG_DB`，默认 `config.db`；MySQL：host/port 或 socket。
- Schema + 双侧迁移 + `tests/test_base.py` DDL **三处同步**（见 `04-config-data.md`）。
- `db.py` 仅 re-export；新代码直接 `import config_db` / `query_executor`。

## 模块依赖方向

单包扁平布局，**无 monorepo**；入口只有 `server.py`（模块职责与行数见 `INDEX.md` §1）。

- `server.py` → 各 `handle_*`（`config` / `report` / `export` / `api_handler` / `audit_page`）。
- 页面、导出、API 的数据来源统一走 `report.execute_report` → `result_transform`（纯函数）→ `query_executor`（MySQL）+ `redis_cache`/`static_cache`（缓存）；禁止在调用方重写筛选/排序语义（见 `03-report-transform.md`）。
- 全站 HTML/CSS/JS 只从 `render.py` 出（见 `06-ui-interactions.md`）。
- `branding.py` 用**实例本地**独立 SQLite，不进配置库。
- 路由/鉴权见 `02-routing-auth.md`；表结构变更见 `04-config-data.md`；缓存与调度见 `07-cache-scheduler-audit.md`。

**改任何模块前先读它对应的那一卷**，不要在本卷猜细节。

## 缓存分层

```text
L1 process QueryCache（进程内，TTL ~300s）
  → L2 Redis 快照（版本键 + 分布式锁 + 保活）
    → L3 MySQL
```

- L1 之上还有请求级 **派生态缓存** `CachedResult.derived`（不属这三层中的任何一层），见 `03-report-transform.md`。
- API 静态：`static_cache/api/**.json` + `config_version` + TTL，NGINX 可直出；完整语义见 `07-cache-scheduler-audit.md`。

## MySQL 连接获取（`query_executor`）

- `create_mysql_connection(pool_config, read_timeout=None)` 走**有界连接池**（上限是模块常量，非配置项）。
- **`close()` 语义是「归还池」**（返回 `_PooledConnection`），故调用方 `finally: conn.close()` 无需改动。
- **池键含 `read_timeout`**：Web 交互 30s、调度器/API 不限制。混池会让调度器慢报表拿到 30s 超时连接而**必然失败**，不可合并。
- 池空/池满/池中连接已死 → 自动降级直连，池的任何异常都不导致功能不可用。
- 连接池是**进程级全局**：注入假连接的测试须 `clear_pools()`（`BaseReportTest.setUp` 已统一处理），否则泄漏给下一个用例。
- **`_is_alive` 必须写「ping 不抛即活」，不得写 `bool(raw.ping(...))`**：mysql-connector 的 `ping()` 成功返回 **None**（失败才抛异常），`bool(None)==False` 会使**真实 MySQL 下所有连接都被判死** → 池恒空、退化成每次直连（实测每请求仍付 71–120ms）。假连接返回 True 会掩盖此 bug，测试断言请用 `ping.side_effect=异常` 表达「死」。
- **配置库池**（`_config_pool`，2026-10-10 B2-2 新增）：与用户查询池**分开**（配置来源不同）；`_connect_mysql_config()` 取池中 raw 后返回 `_ConfigConnection`（`_MySQLConnection` 子类，`close()`=归还+幂等），**不得**改成返回 `_PooledConnection`（会丢掉 `executescript` 等 `config_db` 依赖的接口）。归还前先 `rollback()`，防下一个借出者继承未提交事务。
- **请求内复用**（2026-10-10 B2-1）：`_handle` 把连接提到 `_authenticate()` 之前存入 `self._req_conn`，`auth.refresh_session(token, conn=...)` 复用；**认证失败分支必须归还连接**否则泄漏。实测认证请求 159.7ms → **3.6ms**。

## 运行时勿提交

`app_config*.json`（非 example）、`config.db`、`audit.db`、`venv/`、`static_cache/`、`run-logs/`、`perf-logs/`、`static/vendor/self@*/`、`.codegraph/`（见 `.gitignore`）。

**注意**：`docs/`（spec / plan / 知识库）、`MEMORY.md`、仓库根 `AGENTS.md` 已入库、随任务正常提交，勿当忽略物。

## 易踩坑

- 测试重定向 vendor 根——勿断言真实 `self@*`；集成真库测试仅 DEBUG 且 MySQL 可连才跑。
- 改依赖同步三处：`requirements.txt` + 双 README + `install.sh`。
- README 项目结构可能过时——以当前目录/代码为准。
