<div align="center">

# 🐬 SqlReport

### SQL 进去，报表和 API 出来 —— 零依赖、一条命令启动的 MySQL 报表引擎

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-brightgreen)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-1%20(pip)-blueviolet)](requirements.txt)
[![Framework](https://img.shields.io/badge/framework-none-important)](https://docs.python.org/3/library/http.server.html)
[![MySQL](https://img.shields.io/badge/MySQL-5.7%20%2F%208.0-orange)](https://www.mysql.com/)

纯 Python 3 标准库 · 零框架 · 零构建 · 单文件部署

```
git clone https://github.com/alexblair/SqlReport.git && cd SqlReport
./install.sh && source venv/bin/activate
python server.py
```

**60 秒后，打开浏览器 → 登录 → 写一条 SQL → 你的同事就能在网页上筛选、排序、导出，第三方系统就能通过 API 拿数据。**

[功能特性](#-功能特性) · [快速开始](#-快速开始) · [中文](./README-CN.md) · [English](./README.md)

</div>

---

## 💡 为什么需要它？

> 你只是想给业务同事一个**查数据的页面**，给第三方系统一个**拿数据的接口**。
> 你不想部署一个需要 Postgres + Redis + Celery + headless browser 的"BI 全家桶"，
> 不想为一两个图表背上每周的运维成本，更不想写一个完整的 Web 应用。

**SqlReport 只做一件事：把你的 SQL 变成网页报表和 HTTP API。**
它是给"写 SQL 的人"用的工具 —— 开发者、运维、数据工程师、会 SQL 的运营。

- 🚀 **部署轻到极致**：只依赖 1 个 pip 包，`python server.py` 就启动，没有 Docker、没有 JVM、没有 Node、没有构建步骤
- 📡 **报表即 API**：一条 SQL 既是网页报表，也是一个带鉴权、可跨域的 HTTP API 端点，第三方系统直接调
- ⚡ **高并发不费资源**：三层缓存（进程 / Redis / 数据库）+ API 静态文件缓存，`.json` 后缀直接出静态文件，可交给 NGINX 直出
- 🔒 **合规开箱即用**：完整审计日志、PBKDF2 密码哈希、滑动过期 Session、事务性 SQL 执行，MIT 许可无 AGPL 顾虑

### 与主流开源 BI 的定位差异

| | **SqlReport** | Metabase | Apache Superset | Redash |
|---|---|---|---|---|
| 目标用户 | **写 SQL 的人** | 非技术业务用户 | 数据团队 | SQL 分析师 |
| 部署 | 1 个 Python 文件 + 1 个 pip 包 | JVM 应用 + 元数据库 | Web + Postgres + Redis + Celery + headless browser | Web + Postgres + Redis + workers |
| 起表时间 | **分钟级**（一条 SQL 即可） | 分钟级 | 小时级（先建语义层） | 分钟级 |
| 报表即 API | ✅ 原生（API Key + CORS + 模板） | 需额外开发 | 需额外开发 | 需额外开发 |
| API 静态缓存 / NGINX 直出 | ✅ 原生（`.json` 变体） | ❌ | ❌ | ❌ |
| 三层查询缓存 | ✅ 进程 + Redis + DB 兜底 | 进程内 | Redis | Redis |
| 图表可视化 | ❌ 表格为主（战术选择） | ✅ 25+ 图表 | ✅ 40+ 图表 | 基础图表 |
| 审计日志 | ✅ 内置 | 付费版 | 需配置 | 部分 |
| 许可证 | **MIT** | AGPL（法律部门常禁用） | Apache 2.0 | BSD-2（已停滞） |
| 维护状态 | 活跃开发 | 活跃 | 活跃 | 基本停滞 |

> **为什么不加图表？** 内部报表中 80% 以上的需求是"看数据、筛数据、导出数据"，表格 + 筛选 + 排序 + 导出已经覆盖。
> 与其做出一堆平庸的图表与 Superset 硬碰，不如把表格体验做到极致，并留出 API 这条真正的差异化能力。

---

## 📦 功能特性

| 特性 | 说明 |
|------|------|
| **连接池管理** | 可视化 CRUD 管理 MySQL 连接池，支持调序、复制 |
| **用户管理** | 多用户支持，密码哈希存储（PBKDF2-SHA-256 + salt） |
| **报表配置** | 自定义 SQL 查询、绑定连接池、默认每页行数、备注、所属分类；支持复制 |
| **分类树管理** | 无限层级分类，树形缩进展示，支持调序、新增、删除、重命名 |
| **批量操作** | 批量删除报表、批量修改缓存策略/连接池/分类，分类内全选/反选 |
| **SQL 格式化 & 高亮预览** | 编辑报表时一键格式化 SQL，切换语法高亮预览；未保存的 SQL 可实时预览查询结果 |
| **分页表格** | 内存分页、显示总页数、跳转任意页 |
| **多字段排序** | 点击列头排序，支持多列组合排序，带排序管理面板（添加/删除/调序） |
| **多字段筛选** | 9 种操作符（包含/等于/不等于/大于/小于/≥/≤/为空/非空）；筛选值支持 `*` 通配、英文逗号多值（或）、`\` 转义，报表页/导出/API/审计页共用同一语法 |
| **字段设置** | 拖拽排序、显示/隐藏列，自由控制表格展示字段 |
| **CSV 导出** | 一键导出完整查询结果，UTF-8 BOM 确保 Excel 正确识别中文 |
| **JSON 导出** | 支持 JSON 格式导出，可选数字无引号模式 |
| **字符集切换** | 导出时可选 GBK / UTF-8 编码，满足不同系统需求 |
| **ZIP 压缩包** | 导出结果可选打包为 ZIP 压缩文件 |
| **多结果集** | 单条多语句 SQL 可返回多个结果集，页面按 tab 独立展示，每个 tab 独立维护筛选/排序状态 |
| **报表即 API** | 报表一键发布为 HTTP API：API Key 鉴权、CORS 跨域、JSON/CSV 输出、预设规则、请求覆盖、自定义 JSON 输出模板 |
| **API 静态文件缓存** | 端点 URL 后追加 `.json` 获取全量静态输出（零查询零计算），miss 自动回退重建，支持 NGINX 直出集成 |
| **配置存储双引擎** | 支持 SQLite / MySQL 两种配置存储方案，通过 `app_config.json` 切换 |
| **三层查询缓存** | L1 进程内存（300s TTL）→ L2 Redis 快照（版本化键 + 分布式锁）→ L3 数据库直连（Redis 兜底） |
| **编辑-查看双向关联** | 报表页一键跳转编辑页，编辑页可直接查看报表或实时预览未保存的 SQL |
| **健康检查端点** | `GET /health` 返回 JSON 状态（status + uptime），无需认证 |
| **API 接口独立管理** | 独立管理页 `/config/api-endpoints`，展示全局 API 接口列表及关联报表 |
| **Session 滑动过期** | 24 小时 TTL，每次请求自动刷新，重启后通过 SQLite 持久化恢复 |
| **导出支持排序** | CSV/JSON 导出时应用当前排序状态（与报表页面行为一致） |
| **全量输出护栏** | 报表级「允许全部输出」开关（新建默认关闭、存量默认开启）；关闭时结果超过 max_rows（默认 10 万）即截断，报表页/导出/API 行为一致，页面横幅提示 + truncated / X-Export-Truncated 标记 |
| **事务性 SQL 执行** | 支持 BEGIN/COMMIT/ROLLBACK 包装的多语句事务执行，任一失败整体回滚 |
| **错误日志独立输出** | WARNING 及以上级别可配置独立日志文件，与普通日志分离 |
| **审计日志自动轮转** | 可配置保留天数，启动时和每次访问时自动清理过期记录 |
| **ThreadingHTTPServer** | 多线程 HTTP 服务器，提升并发处理能力 |
| **全局异常兜底** | 未捕获异常返回 500 错误页，避免直接崩溃 |
| **Redis 可观测性** | 所有静默异常（`except: pass`）改为结构化日志输出 |
| **纯标准库** | 仅依赖 `mysql-connector-python`，其余全部使用 Python 内置模块 |

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- MySQL 5.7+ / 8.0+

### 安装

```bash
# 克隆仓库
git clone https://github.com/alexblair/SqlReport.git
cd SqlReport

# 一键安装（创建 venv + 安装依赖）
./install.sh

# 激活虚拟环境后启动服务
source venv/bin/activate
python server.py
```

一键安装脚本 `install.sh` 会自动创建虚拟环境并安装 `requirements.txt` 中的所有依赖。你也可以手动安装：

```bash
python3 -m venv venv
source venv/bin/activate

# 安装外部依赖
pip install -r requirements.txt
# 或手动逐个安装: pip install mysql-connector-python redis
#   - mysql-connector-python: MySQL 查询连接器（必需）
#   - redis: Redis 快照缓存（可选，启用后需在 app_config.json 设置 "enable": true）
```

服务默认监听 `http://0.0.0.0:8080`（可通过 `HOST` / `PORT` 环境变量或配置文件的 `server` 节覆盖）。

API 静态文件缓存的存储目录 `static_cache/` 在首次写入缓存时自动创建（无需手工建目录）；生产环境建议将该目录纳入备份/清理策略，位置可通过 `app_config.json` 的 `static_cache.dir` 调整（支持相对路径或**外部绝对路径**，详见下文「API 静态文件缓存」章节）。

### 首次登录

打开浏览器访问 `http://localhost:8080`，使用默认管理员账户登录：

| 用户名 | 密码 |
|--------|------|
| `admin` | `admin123` |

> ⚠️ **首次登录后请立即修改密码！**

登录后进入 `/config` 门户页，通过入口卡片配置连接池、用户、报表与分类。

---

## 🔧 配置文件

应用通过 `app_config.json`（或 `CONFIG_FILE` 环境变量指定路径）控制配置数据库的存储引擎。

`config_db` 支持**多配置列表**格式，通过 `enable` 字段切换当前使用的引擎。旧版单 dict 格式仍兼容。

### 完整示例

`static_cache.dir` 支持相对路径或外部绝对路径（如 `/var/cache/sqlreport_static`）；目录在首次写入时自动创建。

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "trust_xff": false
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

`server.trust_xff`（默认 `false`）：审计日志的客户端 IP 默认取 socket 对端地址；仅当部署于可信反向代理（如 Nginx，已覆写 `X-Forwarded-For`）之后才设为 `true` 以信任该请求头首 IP，防止客户端伪造来源 IP。

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

### 日志配置

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

### 审计日志配置

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

---

## 📄 API JSON 输出模板

API 端点支持自定义 JSON 输出结构：管理员在端点配置页维护一段 JSON 模板，值位置用 `{{占位符}}` 引用数据，**留空 = 默认输出**（`{"data": ..., "total": N, ...}`）。

### 用法

以默认 JSON 为起点，改键名/位置即可。例如把默认结构改为只输出数据数组与总数：

```json
{
  "count": {{total}},
  "items": {{data}}
}
```

渲染结果为：

```json
{"count": 42, "items": [{"id": 1, "name": "张三"}, ...]}
```

### 占位符

占位符键集随「结果集输出模式」切换：

- **single（单结果集）**：`{{data}}` 数据数组、`{{total}}` 总行数、`{{page}}` 页码、`{{page_size}}` 每页条数、`{{total_pages}}` 总页数、`{{full}}` 全量标记、`{{meta}}` 静态缓存 meta
- **all（全部结果集）**：`{{results}}` 结果集数组（每项含 name/data/total/page/page_size/total_pages）、`{{mode}}` 模式（固定 "all"）、`{{page}}`、`{{page_size}}`、`{{full}}`、`{{meta}}`

规则：

- 模板中**不出现的字段即不输出**；默认输出在 `fetch_all` 时才带 `"full": true`，模板需要时手动加 `{{full}}`
- 键集内键缺失输出 `null`（如普通链路无 meta 时 `{{meta}}` 得 null）；**键集外占位符保存时被拒绝**（页面提示所在行列）
- **CSV 格式不支持模板**（表单已禁用）；模板渲染运行期失败自动回退默认输出，不影响接口可用性
- 与静态缓存联动：模板文本变化自动纳入 config_version 计算，`.json` 静态变体随即失效重建；模板含 `{{meta}}` 时输出 meta 节点，不含则不附加

### 真实数据预览

编辑端点页（已保存的端点）模板区旁有「用真实数据预览」按钮：以当前表单**未保存**的模板与规则（筛选/排序/字段选择）执行真实查询（最多 3 行数据，不落库、不影响线上端点），把渲染结果展示在预览区；模板非法时显示含行列位置的结构化错误，查询执行失败时显示结构化错误消息。新增端点（尚未保存）不提供该按钮。

### 数字无引号

API 端点表单提供「数字无引号」勾选框（默认关闭，与报表 JSON 导出的同名选项共用同一实现）。开启后 JSON 输出中数值型字段保持数字类型（如 `123.45`、`25`），而非默认的全部转字符串（如 `"123.45"`）；数字字符串（如 `"007"`）仍保留引号。对默认输出结构与自定义 JSON 模板同时生效；CSV 输出不受影响；静态缓存 `.json` 变体随该开关自动失效重建（配置变更即失效，下次请求重建）。

---

## 📄 API 静态文件缓存

为高并发、高流量场景提供**静态化输出**：在 API 端点 URL 后追加 `.json` 即可访问该端点的静态缓存文件——命中时直接返回文件内容，零查询、零计算、零 Redis 存取。

### 功能说明

- **内容**：全量数据（fetch_all 语义，`page:1`、`page_size:total`、`total_pages:1`、`full:true`）+ 顶层平铺 `meta` 节点，与原始 API 输出结构兼容（仅多一个 `meta` 键）
- **命中条件**：文件存在 + 配置版本（SQL/连接池 MD5）一致 + 未过期
- **miss 自愈**：文件缺失、过期、被第三方删除时，自动回退完整 API 计算链路（Redis → MySQL），成功后重建文件，调用方无感知
- **鉴权**：与普通 API 完全一致——端点 `api_key` 为空则公开；非空必须带 key（`Authorization: Bearer` 头或 `?api_key=` 参数），缺失/错误返回 401
- **响应头**：`X-Static-Cache: hit|miss` 标识本次请求是否命中；`Content-Type: application/json; charset=utf-8`
- **仅 GET 触发**：POST 请求、CSV 格式端点、非 200 响应均不参与

### 调用示例

```bash
# 静态缓存路径（首次 miss → 回退计算并重建；后续请求 hit 直出）
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers.json"
# 普通 API（无静态缓存）保持不变
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers"
```

普通 API 请求支持 `refresh=1`（严格值校验：`true`/`1`/`yes`，大小写不敏感）**绕过 L1/L2 缓存直查 MySQL 并回写缓存**——调用方需要始终拿最新数据时使用；可与 `fetch_all` 叠加。静态 `.json` 变体**忽略 `refresh`**，缓存有效期内始终直出缓存文件。

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
| `config_version` | 内部字段：配置版本 MD5（SQL + 连接池 + 端点字段/筛选/排序/条数/JSON 模板），命中判定用；任一变化都会自动失效重建 |

### 配置

```json
"static_cache": {
    "enable": true,
    "dir": "static_cache"
}
```

- `enable`：全局开关，默认 `true`
- `dir`：静态文件存储目录，支持**相对路径或外部绝对路径**（默认 `static_cache`）。路径解析通过 `os.path.realpath()` 完成，绝对路径如 `/var/cache/sqlreport_static` 直接使用，相对路径如 `../external_cache` 相对进程工作目录解析；无论何种形式，目录在首次写入缓存时**自动创建**（`os.makedirs(exist_ok=True)`）。写入失败（如权限不足、磁盘满）时，系统仅记录 `logging.warning` 并自动回退到普通 API 链路，不影响正常请求。
- **TTL 无独立配置**：失效时间与端点关联报表的 `cache_ttl_hours` 完全一致（0=永不过期，仅靠手动清理/配置变更失效）
- 端点级开关：API 端点表单的「静态文件缓存（.json 变体）」勾选框（默认开启），可单独关闭某端点
- **失效联动**：报表页「重建缓存」与批量缓存配置「关闭缓存」会同步删除对应静态文件（删除即失效，下次 `.json` 请求惰性重建）

### 缓存文件权限

程序以 root 运行时，`.json` 缓存文件默认以 `0600 root:root` 建立（`tempfile.mkstemp`），NGINX 等非 root 进程直出（见下节）时无法读取。通过 `file_permissions` 配置段指定缓存目录/文件的属主与权限位，启动时对缓存目录树做一次整树刷新，此后新增文件均按配置权限建立：

```json
"file_permissions": {
    "enable": true,
    "user": "nginx",
    "group": "nginx",
    "dir_mode": "0755",
    "file_mode": "0644"
}
```

- `enable`：默认关闭；关闭或整个段缺失时行为与未引入该功能完全一致
- `user` / `group`：缓存目录与文件的属主/属组（支持名称或数字 uid/gid），启动时解析
- `dir_mode` / `file_mode`：可选，八进制字符串（JSON 无八进制字面量）；缺省 `0755` / `0644`。目录需含 `x` 权限（NGINX 需进入），文件需含 `r` 权限（NGINX 需读取）
- 仅配置 `user`/`group` 时 mode 用默认 `0755`/`0644`（否则 `0600` 下 NGINX 仍无法读取）
- 程序非 root、用户/组不存在时降级关闭并记 `logging.warning`，不阻塞启动与写入
- 权限仅作用于 static_cache 缓存目录树，不含 `config.db`/`audit.db`/日志文件

### NGINX 集成

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
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**场景 2：带 api_key 端点 → 全部落应用（鉴权、静态读取都在应用内完成）**

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
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

---

## 🖥️ 页面说明

### 配置页 `/config`

配置总览门户，入口卡片直达各管理页面：

- **连接池** — 添加/编辑/删除/复制 MySQL 连接配置，支持上下调序
- **用户** — 添加/编辑/删除系统用户
- **报表** — 独立管理页 `/config/reports`：配置 SQL 查询、绑定的连接池、默认每页行数、所属分类、备注
- **分类** — 独立管理页 `/config/categories`：无限层级树形管理，支持调序、新增、删除、重命名
- **API 接口** — 独立管理页 `/config/api-endpoints`，全局 API 接口列表及关联报表名称

报表编辑表单特色：
- SQL 编辑器带格式化按钮和语法高亮预览切换
- 备注字段用于记录报表用途
- 全量输出护栏：「允许全部输出」开关 + 截断上限（max_rows，默认 10 万，仅关闭开关时生效）；开启开关时保存前需确认
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
- 多字段筛选 — 每列独立操作符（包含/等于/不等于/大于/小于/≥/≤/为空/非空），支持多列同时过滤；筛选值支持**统一匹配表达式**：`*` 通配（任意位置/多次）、英文逗号多值（段间"或"）、`\` 转义（`\*`/`\,`/`\\` 按字面匹配，适用于数据含这些字符的场景），仅"包含/等于/不等于"参与解析，多列条件之间"且"；报表页、导出、API 预设与审计页关键字共用同一语法（帮助弹窗 `?` 查看示例）；审计页关键字中 `%`/`_` 按字面量匹配
- 字段设置面板 — 拖拽调整列顺序、勾选显示/隐藏列、全选/全不选
- 备注显示 — 报表备注可折叠展开
- 【编辑】按钮：点击新窗口跳转到该报表的配置编辑页面
- 强制刷新缓存（重新查询数据库）；缓存徽标展示快照时间、TTL，快照超过 TTL 时显示**「已过期（下次请求自动刷新）」**警示（`cache_ttl_hours=0` = 永不过期）
- 截断提示条 — 结果被全量输出护栏截断至 max_rows 时，页面顶部横幅提示截断上限及在编辑页开启全量输出的方法

### 导出功能 `/export`

- 完整数据集导出（不分页，保留当前筛选和排序）
- 支持 **CSV** 和 **JSON** 两种格式
- UTF-8 BOM 编码（CSV）确保 Excel 正确识别中文
- 字符集可选 GBK / UTF-8
- JSON 数字无引号模式（数值保持数字类型）
- ZIP 压缩包打包下载
- 支持应用自定义字段设置（仅导出选定列并按指定顺序）
- 应用全量输出护栏：关闭全量输出且结果超过 max_rows 时导出被截断，并带响应头 `X-Export-Truncated: true`

---

## 🏗️ 项目结构

```
SqlReport/
├── server.py              # HTTP 服务器入口、路由分发（ThreadingHTTPServer）
├── config.py              # 配置页 CRUD 处理（连接池/用户/报表/分类/API 端点）
├── report.py              # 报表页、分页、排序、筛选
├── result_transform.py    # 结果集变换（筛选/排序/列选择，页面/导出/API 共用）
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
├── audit_page.py          # 审计日志页面处理（浏览/清理/CSV 导出）
├── redis_cache.py         # Redis 快照缓存层
├── api_handler.py         # API 接口处理器（API 端点查询 + 静态缓存 + 具名结果结构）
├── file_permissions.py    # 运行时文件权限管理（static_cache 目录属主/权限）
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
│   ├── test_file_permissions.py
│   └── test_state_machine.py
├── config.db              # SQLite 配置数据库（自动创建，不提交）
├── install.sh             # 自动化依赖安装脚本（venv + pip install）
├── requirements.txt       # pip 依赖清单
├── manage_service.sh      # Systemd 服务管理脚本
├── git-purge.sh           # Git 仓库重写工具（清理历史/更改作者/代理支持）
└── AGENTS.md              # AI 开发代理指引
```

---

## 🧪 运行测试

```bash
source venv/bin/activate
python -m unittest discover -s tests/ -v
```

---

## ⚙️ 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CONFIG_FILE` | `app_config.json` | 应用配置文件路径 |
| `CONFIG_DB` | `config.db` | SQLite 数据库文件路径（配置文件中的 `path` 优先级更高） |
| `HOST` | `0.0.0.0` | HTTP 服务监听地址 |
| `PORT` | `8080` | HTTP 服务监听端口 |

---

## 📜 技术栈

| 层级 | 技术 |
|------|------|
| Web 服务器 | `http.server.ThreadingHTTPServer` (Python stdlib) |
| 配置存储 | SQLite (Python stdlib `sqlite3`) 或 MySQL (`mysql-connector-python`)，通过 `app_config.json` 切换 |
| 数据查询 | MySQL via `mysql-connector-python` |
| 认证 | Cookie + PBKDF2-SHA-256 salt hash + 滑动过期 (Python stdlib `hashlib`, `secrets`, `hmac`, `time`) |
| 前端 | 纯 HTML + 内联 CSS（无 JS 框架） |
| 测试 | `unittest` (Python stdlib) |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📐 开发规范

- **依赖同步规则**：新增或删减 pip 依赖包时，必须同步更新以下三处文件：
  1. `requirements.txt` — 依赖清单
  2. `README.md` / `README-CN.md` — 安装说明章节
  3. `install.sh` — 安装脚本中的 `pip install` 命令（若有变更）

- **README 双语同步规则**：`README.md`（英文）与 `README-CN.md`（中文）作为镜像对同步维护——任何一处修改，必须在同一次提交中以等价翻译同步到另一处。功能新增、缺陷修复、配置变更一律禁止只改其一。

---

## 📄 许可

MIT License © 2024 [alexblair](https://github.com/alexblair)

---

<div align="center">
  <sub>仅用 Python 标准库构建</sub>
</div>
