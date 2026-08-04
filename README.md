<div align="center">
  <h1>SqlReport</h1>
  <p><strong>轻量级 MySQL 网页报表工具 · Lightweight MySQL Web Report Tool</strong></p>
  <p>
    <em>纯 Python 3 标准库，零框架依赖，一键部署</em><br/>
    <em>Pure Python 3 stdlib, zero framework dependencies, one-click deploy</em>
  </p>
  <p>
    <a href="#-features">English</a> ·
    <a href="#-功能特性">中文</a>
  </p>
</div>

---

## 📦 功能特性

| 特性 | 说明 |
|------|------|
| **连接池管理** | 可视化 CRUD 管理 MySQL 连接池，支持调序、复制 |
| **用户管理** | 多用户支持，密码哈希存储（SHA-256 + salt） |
| **报表配置** | 自定义 SQL 查询、绑定连接池、默认每页行数、备注、所属分类；支持复制 |
| **分类树管理** | 无限层级分类，树形缩进展示，支持调序、新增、删除、重命名 |
| **批量操作** | 批量删除报表，分类内全选/反选 |
| **SQL 格式化 & 高亮预览** | 编辑报表时一键格式化 SQL，切换语法高亮预览 |
| **分页表格** | 内存分页、显示总页数、跳转任意页 |
| **多字段排序** | 点击列头排序，支持多列组合排序，带排序管理面板（添加/删除/调序） |
| **多字段筛选** | 支持包含、等于、不等于、大于、小于、大于等于、小于等于、为空、非空 9 种操作符 |
| **字段设置** | 拖拽排序、显示/隐藏列，自由控制表格展示字段 |
| **CSV 导出** | 一键导出完整查询结果，UTF-8 BOM 确保 Excel 正确识别中文 |
| **JSON 导出** | 支持 JSON 格式导出，可选数字无引号模式 |
| **字符集切换** | 导出时可选 GBK / UTF-8 编码，满足不同系统需求 |
| **ZIP 压缩包** | 导出结果可选打包为 ZIP 压缩文件 |
| **配置存储双引擎** | 支持 SQLite / MySQL 两种配置存储方案，通过 `app_config.json` 切换 |
| **编辑-查看双向关联** | 报表页一键跳转编辑页，编辑页可直接查看报表或实时预览未保存的 SQL |
| **健康检查端点** | `GET /health` 返回 JSON 状态（status + uptime），无需认证 |
| **API 接口独立管理** | 独立管理页 `/config/api-endpoints`，展示全局 API 接口列表及关联报表 |
| **API 静态文件缓存** | 端点 URL 后追加 `.json` 获取全量静态输出（零查询零计算），miss 自动回退重建，支持 NGINX 直出集成 |
| **Session 滑动过期** | 24 小时 TTL，每次请求自动刷新，重启后通过 SQLite 持久化恢复 |
| **导出支持排序** | CSV/JSON 导出时应用当前排序状态（与报表页面行为一致） |
| **事务性 SQL 执行** | 支持 BEGIN/COMMIT/ROLLBACK 包装的多语句事务执行 |
| **错误日志独立输出** | WARNING 及以上级别可配置独立日志文件，与普通日志分离 |
| **审计日志自动轮转** | 可配置保留天数，启动时和每次访问时自动清理过期记录 |
| **ThreadingHTTPServer** | 多线程 HTTP 服务器，提升并发处理能力 |
| **全局异常兜底** | 未捕获异常返回 500 错误页，避免直接崩溃 |
| **Redis 可观测性** | 所有静默异常（`except: pass`）改为结构化日志输出 |
| **纯标准库** | 仅依赖 `mysql-connector-python`，其余全部使用 Python 内置模块 |

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Connection Pool Mgmt** | Visual CRUD for MySQL connection pools with reorder and copy |
| **User Management** | Multi-user support with salted SHA-256 password hashing |
| **Report Configuration** | Custom SQL, bind pool, page size, memo, category; with copy support |
| **Category Tree** | Unlimited depth categories, tree-indented display, reorder/add/rename/delete |
| **Batch Operations** | Batch delete reports, select all/deselect per category |
| **SQL Formatter & Preview** | One-click SQL formatting, toggle syntax-highlighted preview |
| **Paginated Tables** | In-memory pagination with total pages and page jump |
| **Multi-column Sorting** | Click column headers, multi-column combo sort with management panel |
| **Multi-field Filtering** | 9 operators: contains, eq, neq, gt, lt, gte, lte, is empty, not empty |
| **Column Settings** | Drag-and-drop column reorder, show/hide fields |
| **CSV Export** | Full dataset export with UTF-8 BOM for Excel compatibility |
| **JSON Export** | JSON format export with optional numeric no-quotes mode |
| **Charset Selection** | GBK or UTF-8 encoding for exports |
| **ZIP Compression** | Package export results as ZIP archive |
| **Dual Config Engine** | SQLite or MySQL for config storage, switchable via `app_config.json` |
| **Report-Editor Link** | Jump from report view to editor, preview unsaved SQL in real time |
| **Health Check** | `GET /health` returns JSON status (status + uptime), no auth required |
| **API Endpoint Indep. Mgmt** | Standalone page `/config/api-endpoints` with global list & linked report |
| **API Static File Cache** | Append `.json` to endpoint URL for static full output (zero query/compute), auto rebuild on miss, NGINX serve-ready |
| **Session Sliding Expiry** | 24h TTL, refreshed on each request, persisted via SQLite across restarts |
| **Export with Sorting** | CSV/JSON exports apply current sort state (consistent with report view) |
| **Transactional SQL** | Multi-statement execution wrapped in BEGIN/COMMIT/ROLLBACK |
| **Error Log Output** | Configurable separate log file for WARNING+ level messages |
| **Audit Log Rotation** | Configurable retention days, auto-cleanup on startup and page visits |
| **ThreadingHTTPServer** | Multi-threaded HTTP server for better concurrency |
| **Global Error Handler** | Uncaught exceptions render a 500 error page instead of crashing |
| **Redis Observability** | All silent exceptions (`except: pass`) upgraded to structured logging |
| **Pure Stdlib** | Only depends on `mysql-connector-python`; everything else is Python built-in |

---

## 🚀 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python 3.11+
- MySQL 5.7+ / 8.0+

### 安装 / Installation

```bash
# 克隆仓库 / Clone the repo
git clone https://github.com/alexblair/SqlReport.git
cd SqlReport

# 一键安装（创建 venv + 安装依赖）/ One-click setup (venv + deps)
./install.sh

# 激活虚拟环境后启动服务 / Activate venv, then start the server
source venv/bin/activate
python server.py
```

一键安装脚本 `install.sh` 会自动创建虚拟环境并安装 `requirements.txt` 中的所有依赖。你也可以手动安装：

```bash
python3 -m venv venv
source venv/bin/activate

# 安装外部依赖 / Install external dependencies
pip install -r requirements.txt
# 或手动逐个安装: pip install mysql-connector-python redis
#   - mysql-connector-python: MySQL 查询连接器（必需）
#   - redis: Redis 快照缓存（可选，启用后需在 app_config.json 设置 "enable": true）
```

服务默认监听 `http://0.0.0.0:8000`。

The server listens at `http://0.0.0.0:8000` by default.

API 静态文件缓存的存储目录 `static_cache/` 在首次写入缓存时自动创建（无需手工建目录）；生产环境建议将该目录纳入备份/清理策略，位置可通过 `app_config.json` 的 `static_cache.dir` 调整（见下文「API 静态文件缓存」章节）。

### 首次登录 / First Login

打开浏览器访问 `http://localhost:8000`，使用默认管理员账户登录：

Open your browser and navigate to `http://localhost:8000`, then log in with the default admin account:

| 用户名 / Username | 密码 / Password |
|-------------------|----------------|
| `admin`           | `admin123`     |

> ⚠️ **首次登录后请立即修改密码！** / Please change password immediately after first login!

登录后进入 `/config` 页面配置连接池、用户和报表。

After login, go to `/config` to configure connection pools, users, and reports.

---

## 🔧 配置文件 / Configuration File

应用通过 `app_config.json`（或 `CONFIG_FILE` 环境变量指定路径）控制配置数据库的存储引擎。

The application uses `app_config.json` (or the `CONFIG_FILE` env var) to select the config database engine.

`config_db` 支持**多配置列表**格式，通过 `enable` 字段切换当前使用的引擎。旧版单 dict 格式仍兼容。

The `config_db` field supports a **list of configurations**, toggled via the `enable` flag. The legacy single-dict format is still supported.

### 完整示例 / Full Example

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 8080
    },
    "static_cache": {
        "enable": true,
        "dir": "static_cache"
    },
    "config_db": [
        {
            "enable": true,
            "engine": "mysql",
            "host": "127.0.0.1",
            "port": 3306,
            "user": "root",
            "password": "your_password",
            "database": "sqlreport_config"
        },
        {
            "enable": false,
            "engine": "sqlite3",
            "path": "config.db"
        }
    ]
}
```

MySQL 模式可选通过 `socket` 指定 Unix socket 路径（与 `host`/`port` 二选一）：

```json
{
    "enable": true,
    "engine": "mysql",
    "socket": "/var/run/mysqld/mysqld.sock",
    "user": "root",
    "password": "your_password",
    "database": "sqlreport_config"
}
```

### 日志配置 / Log Configuration

```json
{
    "log": {
        "enable": false,
        "path": "run.log"
    },
    "error_log": {
        "enable": false,
        "path": "error.log"
    }
}
```

- `log.enable` — `true` 开启常规文件日志，`false` 关闭（默认）
- `log.path` — 日志文件路径，默认为 `run.log`（项目根目录）
- `error_log.enable` — `true` 开启独立错误日志文件（WARNING 及以上级别），`false` 关闭（默认）
- `error_log.path` — 错误日志文件路径，默认为 `error.log`
- 日志包含启动信息、请求记录和错误信息

### 审计日志配置 / Audit Log Configuration

```json
{
    "audit_db": {
        "path": "audit.db",
        "retention_days": 90
    }
}
```

- `path` — 审计数据库文件路径，默认为 `audit.db`
- `retention_days` — 保留天数（0 = 永久保存），启动时和每次访问审计页时自动清理过期记录

> ⚠️ `app_config.json` 包含数据库密码，已加入 `.gitignore`，请勿提交到版本控制。
>
> `app_config.json` contains credentials and is in `.gitignore` — do not commit.

---

## 📄 API 静态文件缓存 / API Static File Cache

为高并发、高流量场景提供**静态化输出**：在 API 端点 URL 后追加 `.json` 即可访问该端点的静态缓存文件——命中时直接返回文件内容，零查询、零计算、零 Redis 存取。

The `.json` variant serves a pre-computed static file of the endpoint's full output. On hit, the server just returns the file bytes.

### 功能说明 / How it works

- **内容**：全量数据（fetch_all 语义，`page:1`、`page_size:total`、`total_pages:1`、`full:true`）+ 顶层平铺 `meta` 节点，与原始 API 输出结构兼容（仅多一个 `meta` 键）
- **命中条件**：文件存在 + 配置版本（SQL/连接池 MD5）一致 + 未过期
- **miss 自愈**：文件缺失、过期、被第三方删除时，自动回退完整 API 计算链路（Redis → MySQL），成功后重建文件，调用方无感知
- **鉴权**：与普通 API 完全一致——端点 `api_key` 为空则公开；非空必须带 key（`Authorization: Bearer` 头或 `?api_key=` 参数），缺失/错误返回 401
- **响应头**：`X-Static-Cache: hit|miss` 标识本次请求是否命中；`Content-Type: application/json; charset=utf-8`
- **仅 GET 触发**：POST 请求、CSV 格式端点、非 200 响应均不参与

### 调用示例 / Usage

```bash
# 静态缓存路径（首次 miss → 回退计算并重建；后续请求 hit 直出）
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers.json"
# 普通 API（无静态缓存）保持不变
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers"
```

响应体示例：

```json
{
  "data": [...],
  "total": 1000,
  "page": 1,
  "page_size": 1000,
  "total_pages": 1,
  "full": true,
  "meta": {
    "generated_at": "2026-08-04 18:30:22 +0800",
    "expires_at": "2026-08-05 18:30:22 +0800",
    "last_invalidated_at": null,
    "config_version": "a1b2c3d4e5f6..."
  }
}
```

`meta` 字段说明（时间均为服务器本地时区、秒级精度）：

| 字段 | 说明 |
|---|---|
| `generated_at` | 文件生成时间 |
| `expires_at` | 失效时间 = 生成时间 + 报表 `cache_ttl_hours`；`cache_ttl_hours=0`（永久）时为 `null` |
| `last_invalidated_at` | 该缓存路径"上次被判定失效"的时刻：因版本不匹配/过期重建时记录本次时刻；因文件缺失（首次/第三方删除）重建时沿用历史记录；无记录时为 `null` |
| `config_version` | 内部字段：配置版本 MD5（SQL + 连接池 + 端点字段/筛选/排序/条数），命中判定用；SQL、连接池或端点变换配置任一变化都会自动失效重建 |

### 配置 / Configuration

```json
"static_cache": {
    "enable": true,
    "dir": "static_cache"
}
```

- `enable`：全局开关，默认 `true`
- `dir`：静态文件存储目录（相对/绝对路径均可），默认 `static_cache`；目录在首次写入时自动创建
- **TTL 无独立配置**：失效时间与端点关联报表的 `cache_ttl_hours` 完全一致（0=永不过期，仅靠手动清理/配置变更失效）
- 端点级开关：API 端点表单的「静态文件缓存（.json 变体）」勾选框（默认开启），可单独关闭某端点
- **失效联动**：报表页「重建缓存」与批量缓存配置「关闭缓存」会同步删除对应静态文件（删除即失效，下次 `.json` 请求惰性重建）

### NGINX 集成 / NGINX Integration

NGINX 三种接入方式，按端点鉴权策略选择：

**场景 1：公开端点（api_key 为空）静态直出 + miss 回退应用（推荐）**

```nginx
# static_cache.dir 配置为 /opt/sqlreport/static_cache（与 app_config.json 一致）
location ~ ^/api/(?<api_file>.+)\.json$ {
    root /opt/sqlreport;
    # /api/customers.json → /opt/sqlreport/static_cache/api/customers.json
    try_files /static_cache/api/$api_file.json @api_upstream;

    default_type application/json;
    add_header X-Static-Cache hit always;
    add_header Cache-Control "public, max-age=300" always;
}

location @api_upstream {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**场景 2：带 api_key 端点 → 全部落应用（鉴权、静态读取都在应用内完成）**

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**场景 3：rewrite 直出变体（无回退，文件不存在返回 404）**

```nginx
location ~ ^/api/(?<api_file>.+)\.json$ {
    rewrite ^/api/(.+)\.json$ /static_cache/$1.json break;
    root /opt/sqlreport;
    default_type application/json;
    add_header X-Static-Cache hit always;
}
```

**域名前缀映射完整案例**：`https://a.com/fishapi/` → `http://127.0.0.1:8101/api/`（后端系统约束的 API 地址开头为 `/api/`），保留完整 API Key 鉴权能力，缓存与系统一致（NGINX 层不设独立缓存）：

```nginx
# /etc/nginx/conf.d/a.com-fishapi.conf
server {
    listen 80;
    server_name a.com;

    location /fishapi/ {
        # 剥掉 /fishapi/ 前缀，换成系统约束的 /api/ 前缀
        # rewrite 不影响查询串，?api_key=xxx 原样透传
        rewrite ^/fishapi/(.*)$ /api/$1 break;

        proxy_pass http://127.0.0.1:8101;
        proxy_http_version 1.1;

        # Host 保留客户端域名（后端日志审计用）
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout  60s;
        proxy_send_timeout  60s;
        client_max_body_size 10m;
    }
}
```

验证：

```bash
nginx -t && systemctl reload nginx
curl -H "Authorization: Bearer sk-XXXX" "https://a.com/fishapi/customers"
curl -i -H "Authorization: Bearer sk-XXXX" "https://a.com/fishapi/customers.json"   # 看 X-Static-Cache
```

**NGINX 集成注意事项**：

1. **鉴权边界**：场景 1/3 的静态直出会绕过应用鉴权，**仅适用于 api_key 为空的公开端点**；配置了 key 的端点必须走场景 2，否则等于公开数据
2. **TTL 由应用保证**：NGINX 直出不检查过期，过期文件会持续直出；需要 NGINX 层也过期时，用 `expires` 指令或部署任务按 `meta.expires_at` 清理
3. **安全**：正则 location 已限定 `.json` 后缀；`try_files` 对 `..` 返回 404；建议禁止该目录的脚本执行
4. 后端端口按实际部署调整（默认 `python server.py` 监听端口见 `app_config.json` 的 `server` 段）

## 🖥️ 页面说明 / Pages

### 配置页 `/config`

三合一配置管理界面，左侧导航切换：

- **连接池** — 添加/编辑/删除/复制 MySQL 连接配置，支持上下调序
- **用户** — 添加/编辑/删除系统用户
- **报表** — 配置 SQL 查询、绑定的连接池、默认每页行数、所属分类、备注
- **分类** — 无限层级树形管理，支持调序、新增、删除、重命名
- **API 接口** — 独立管理页 `/config/api-endpoints`，全局 API 接口列表及关联报表名称

报表编辑表单特色：
- SQL 编辑器带格式化按钮和语法高亮预览切换
- 备注字段用于记录报表用途
- 【查看】按钮：点击新窗口打开该报表的查看页面
- 【预览】按钮：点击新窗口以当前表单中的 SQL（未保存）实时预览查询结果，方便检查 SQL 编写是否正确
- 【保存】成功后返回列表页

报表列表页特色：
- 分类树形展示，缩进表示层级
- 每个报表行内带有上下移动按钮
- 分类级全选/反选，支持批量删除
- 报表可跨分类移动（下拉选择目标分类）
- 备注字段截取前 15 字符预览

### 报表页 `/report`

- 分类树形下拉选择报表
- 自动执行 SQL 查询并缓存结果（带缓存时间戳和重建按钮）
- 分页浏览（可选 10/20/50/100/200 行）
- 多字段排序 — 点击列头 ▲▼ 箭头，支持组合排序，带排序管理面板（拖拽/添加/删除）
- 多字段筛选 — 每列独立操作符（包含/等于/不等于/大于/小于/≥/≤/为空/非空），支持多列同时过滤
- 字段设置面板 — 拖拽调整列顺序、勾选显示/隐藏列、全选/全不选
- 备注显示 — 报表备注可折叠展开
- 【编辑】按钮：点击新窗口跳转到该报表的配置编辑页面
- 强制刷新缓存（重新查询数据库）

### 导出功能 `/export`

- 完整数据集导出（不分页，保留当前筛选和排序）
- 支持 **CSV** 和 **JSON** 两种格式
- UTF-8 BOM 编码（CSV）确保 Excel 正确识别中文
- 字符集可选 GBK / UTF-8
- JSON 数字无引号模式（数值保持数字类型）
- ZIP 压缩包打包下载
- 支持应用自定义字段设置（仅导出选定列并按指定顺序）

---

## 🏗️ 项目结构 / Project Structure

```
SqlReport/
├── server.py              # HTTP 服务器入口、路由分发（ThreadingHTTPServer）
├── config.py              # 配置页 CRUD 处理（连接池/用户/报表/分类/API 端点）
├── report.py              # 报表页、分页、排序、筛选
├── export.py              # CSV/JSON/ZIP 导出（支持排序）
├── auth.py                # 用户认证、Session 管理（滑动过期 + SQLite 持久化）
├── db.py                  # 配置存储（SQLite/MySQL 双引擎）+ 查询连接管理
├── app_config.py          # 应用配置文件加载器
├── app_config.json        # 应用配置文件（含密码，不提交）
├── app_config.example.json# 配置文件模板
├── config_db.py           # 配置数据库引擎选择
├── query_executor.py      # MySQL 查询执行器（事务支持、?→%s 占位符转换）
├── render.py              # HTML 模板（string.Template 常量）
├── audit_db.py            # 审计日志数据库（含自动轮转）
├── redis_cache.py         # Redis 快照缓存层
├── api_handler.py         # API 接口处理器
├── tests/                 # 单元测试
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_base.py
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_export.py
│   ├── test_health.py
│   ├── test_mysql_mock.py
│   ├── test_mysql_transactional.py
│   ├── test_redis_cache.py
│   ├── test_report.py
│   ├── test_server.py
│   └── test_state_machine.py
├── config.db              # SQLite 配置数据库（自动创建，不提交）
├── install.sh             # 自动化依赖安装脚本（venv + pip install）
├── requirements.txt       # pip 依赖清单
├── manage_service.sh      # Systemd 服务管理脚本
├── git-purge.sh           # Git 仓库重写工具（清理历史/更改作者/代理支持）
└── AGENTS.md              # AI 开发代理指引
```

---

## 🧪 运行测试 / Running Tests

```bash
source venv/bin/activate
python -m unittest discover -s tests/ -v
```

---

## ⚙️ 环境变量 / Environment Variables

| 变量 / Variable | 默认值 / Default | 说明 / Description |
|----------------|------------------|-------------------|
| `CONFIG_FILE` | `app_config.json` | 应用配置文件路径 |
| `CONFIG_DB` | `config.db` | SQLite 数据库文件路径（配置文件中的 `path` 优先级更高） |
| `HOST` | `0.0.0.0` | HTTP 服务监听地址 |
| `PORT` | `8000` | HTTP 服务监听端口 |

---

## 📜 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|-------------|------------------|
| Web 服务器 | `http.server.ThreadingHTTPServer` (Python stdlib) |
| 配置存储 | SQLite (Python stdlib `sqlite3`) 或 MySQL (`mysql-connector-python`)，通过 `app_config.json` 切换 |
| 数据查询 | MySQL via `mysql-connector-python` |
| 认证 | Cookie + SHA-256 salt hash + 滑动过期 (Python stdlib `hashlib`, `secrets`, `hmac`, `time`) |
| 前端 | 纯 HTML + 内联 CSS（无 JS 框架） |
| 测试 | `unittest` (Python stdlib) |

---

## 🤝 贡献 / Contributing

欢迎提交 Issue 和 Pull Request！

Issues and PRs are welcome!

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📐 开发规范 / Development Standards

- **依赖同步规则**：新增或删减 pip 依赖包时，必须同步更新以下三处文件：
  1. `requirements.txt` — 依赖清单
  2. `README.md` — 安装说明章节
  3. `install.sh` — 安装脚本中的 `pip install` 命令（若有变更）

---

## 📄 许可 / License

MIT License © 2024 [alexblair](https://github.com/alexblair)

---

<div align="center">
  <sub>Built with ❤️ using only Python standard library</sub>
  <br/>
  <sub>仅用 Python 标准库构建</sub>
</div>
