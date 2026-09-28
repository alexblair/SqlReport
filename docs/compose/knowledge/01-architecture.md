# 架构 · 启动 · 配置 · 缓存分层

## 技术选型（锁定）

- Python 3.11+，**无 Web 框架**：`http.server.ThreadingHTTPServer`
- 前端：服务端 HTML 字符串 + 公共 CSS/JS
- 依赖：`mysql-connector-python`、`redis`、`markdown`、`pygments`、`pytest`（测试）
- 配置存储：SQLite / MySQL（`config_db` 列表 + `enable`）

## 启动链路（`server.main` ~:979）

1. `setup_logging` → `render.ensure_common_assets()` 预热公共资产  
2. `file_permissions.load_permissions` + `refresh_tree(static_cache.permissions_root())`  
3. `get_config_db` → `init_db` → 首次创建默认 admin/admin123（仅日志提示）  
4. `init_audit_db` → `auth.load_sessions` → 启动轮转过期审计  
5. `ThreadingHTTPServer((HOST,PORT), ReportHandler)`；端口占用尝试 `fuser -k`  
6. `start_scheduler_from_config()` → daemon `serve_forever` → join 等 Ctrl+C  

安装：`./install.sh` → `source venv/bin/activate`  
服务：`sudo bash manage_service.sh install`（单元 `web-report`）

## 应用配置（`app_config.py`）

| 文件 | 作用 |
|------|------|
| `app_config.json` | 主配置（**不入库**，模板 example） |
| `app_config.debug.json` | DEBUG **深合并**（dict 递归；**list 整段覆盖**） |
| `CONFIG_FILE` / `DEBUG_CONFIG_FILE` | 显式 CONFIG_FILE 且未设 DEBUG_CONFIG_FILE → **跳过** debug |

关键 API：`get_config/reload_config/is_debug_mode`、`get_server_config`（HOST/PORT env 最高）、`get_trust_xff`、`get_active_db_config`、`get_redis_config`、`serialize_json` / `serialize_smart_quotes`。

分段：`server{host,port,trust_xff}` `log` `error_log` `redis` `static_cache` `file_permissions` `audit_db` `config_db[]`。

测试在 `tests/__init__.py` 把 `DEBUG_CONFIG_FILE` 指到不存在路径——勿依赖仓库根 debug 配置。

## 双引擎配置库

- `config_db.get_config_db()`：每请求一次独立连接  
- SQLite：WAL+FK；`path` 或 env `CONFIG_DB` 默认 `config.db`  
- MySQL：host/port 或 socket  
- Schema + 双侧迁移 + `tests/test_base.py` DDL **三处同步**（见 04 卷）  
- `db.py` 仅 re-export；新代码 `import config_db` / `query_executor`

## 模块地图（摘要）

| 模块 | 行约 | 职责 |
|------|------|------|
| server | 1110 | 路由/鉴权/vend 静态 |
| config | 2833 | /config* CRUD |
| config_db | 2530 | DAL+迁移 |
| report | 1903 | 报表页+execute_report |
| result_transform | 598 | 筛选排序列纯函数 |
| export | 503 | CSV/JSON/ZIP |
| api_handler | 1074 | API+静态 json |
| render | 4968 | 全站 UI |
| query_executor | 490 | 事务+写检测 |
| scheduler | 734 | 定时任务 |
| auth/audit_*/branding | — | 认证审计品牌 |
| redis_cache/static_cache | — | L2/静态缓存 |

完整表见 `INDEX.md`。

## 缓存分层

```
L1 process QueryCache (~300s)
  → L2 Redis 快照（版本键+锁+保活）
    → L3 MySQL

API 静态：static_cache/api/**.json + config_version + TTL；NGINX 可直出
```

详见 `07-cache-scheduler-audit.md`、`05-api.md`。

## 运行时勿提交

`app_config.json`、`config.db`、`audit.db`、`venv/`、`static_cache/`、`static/vendor/self@*/`、`.codegraph/`、`docs/`、`AGENTS.md`、`.mimocode/`（见 `.gitignore`）。

## 易踩坑

- 测试重定向 vendor 根——勿断言真实 `self@*`  
- 集成真库测试仅 DEBUG 且 MySQL 可连才跑  
- 改依赖同步：`requirements.txt` + 双 README + `install.sh`  
- README 项目结构可能过时——以当前目录/代码为准  

---
最后核对：explore 报告 + AGENTS + 源码
