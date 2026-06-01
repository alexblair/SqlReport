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
| **连接池管理** | 可视化 CRUD 管理 MySQL 连接池，支持拖拽排序 |
| **用户管理** | 多用户支持，密码哈希存储（SHA-256 + salt） |
| **报表配置** | 自定义 SQL 查询、绑定连接池、默认每页行数，支持分类树管理 |
| **分类树管理** | 无限层级分类，树形缩进展示，支持调序、新增、删除、重命名 |
| **批量操作** | 批量删除报表，分类内全选/反选 |
| **分页表格** | 内存分页、显示总页数、跳转任意页 |
| **多字段排序** | 点击列头排序，支持多列组合排序 |
| **多字段筛选** | 任意列模糊搜索，支持多字段同时过滤 |
| **CSV 导出** | 一键导出完整查询结果，UTF-8 BOM 确保 Excel 正确识别中文 |
| **纯标准库** | 仅依赖 `mysql-connector-python`，其余全部使用 Python 内置模块 |
| **配置存储双引擎** | 支持 SQLite / MySQL 两种配置存储方案，通过 `app_config.json` 切换 |

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Connection Pool Mgmt** | Visual CRUD for MySQL connection pools with sortable list |
| **User Management** | Multi-user support with salted SHA-256 password hashing |
| **Report Configuration** | Custom SQL queries, bind to connection pool, configurable page size, category tree |
| **Category Tree** | Unlimited depth categories, tree-indented display, reorder/add/rename/delete |
| **Batch Operations** | Batch delete reports, select all/deselect per category |
| **Paginated Tables** | In-memory pagination with total pages display and page jump |
| **Multi-column Sorting** | Click column headers, support multi-column combo sort |
| **Multi-field Filtering** | Fuzzy search on any column, multi-field simultaneous filtering |
| **CSV Export** | One-click export of full query results, UTF-8 BOM for Excel compatibility |
| **Pure Stdlib** | Only depends on `mysql-connector-python`; everything else is Python built-in |
| **Dual Config Engine** | SQLite or MySQL for config storage, switchable via `app_config.json` |

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

# 创建虚拟环境 / Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 安装唯一外部依赖 / Install the only external dependency
pip install mysql-connector-python

# 启动服务 / Start the server
python server.py
```

服务默认监听 `http://0.0.0.0:8000`。

The server listens at `http://0.0.0.0:8000` by default.

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
    }
}
```

- `enable` — `true` 开启文件日志，`false` 关闭（默认）
- `path` — 日志文件路径，默认为 `run.log`（项目根目录）
- 日志包含启动信息、请求记录和错误信息

> ⚠️ `app_config.json` 包含数据库密码，已加入 `.gitignore`，请勿提交到版本控制。
>
> `app_config.json` contains credentials and is in `.gitignore` — do not commit.

---

## 🖥️ 页面说明 / Pages

### 配置页 `/config`

三合一配置管理界面，左侧导航切换：

- **连接池** — 添加/编辑/删除 MySQL 连接配置，支持调序
- **用户** — 添加/编辑/删除系统用户
- **报表** — 配置 SQL 查询、绑定的连接池、默认每页行数、所属分类
- **分类** — 无限层级树形管理，支持拖拽式调序

报表配置页特色：
- 分类树形展示，缩进表示层级
- 每个报表行内带有上下移动按钮
- 分类级全选/反选，支持批量删除
- 报表可跨分类移动（下拉选择目标分类）

### 报表页 `/report`

- 下拉选择报表
- 自动执行 SQL 查询并缓存结果
- 分页浏览（可配置每页行数）
- 点击列头排序（支持多列）
- 任意列模糊搜索
- 强制刷新缓存（重新查询数据库）

### CSV 导出 `/export`

- 完整数据集导出（不分页）
- UTF-8 BOM 编码，Excel 直接打开无乱码
- 所有字段双引号包裹，逗号分隔

---

## 🏗️ 项目结构 / Project Structure

```
SqlReport/
├── server.py              # HTTP 服务器入口、路由分发
├── config.py              # 配置页 CRUD 处理（连接池/用户/报表/分类）
├── report.py              # 报表页、分页、排序、筛选
├── export.py              # CSV 导出
├── auth.py                # 用户认证、Session 管理
├── db.py                  # 配置存储（SQLite/MySQL 双引擎）+ 查询连接管理
├── app_config.py          # 应用配置文件加载器
├── app_config.json        # 应用配置文件（含密码，不提交）
├── app_config.example.json# 配置文件模板
├── tests/                 # 单元测试
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_export.py
│   ├── test_report.py
│   └── test_server.py
├── config.db              # SQLite 配置数据库（自动创建，不提交）
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
| Web 服务器 | `http.server` (Python stdlib) |
| 配置存储 | SQLite (Python stdlib `sqlite3`) 或 MySQL (`mysql-connector-python`)，通过 `app_config.json` 切换 |
| 数据查询 | MySQL via `mysql-connector-python` |
| 认证 | Cookie + SHA-256 salt hash (Python stdlib `hashlib`, `secrets`, `hmac`) |
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

## 📄 许可 / License

MIT License © 2024 [alexblair](https://github.com/alexblair)

---

<div align="center">
  <sub>Built with ❤️ using only Python standard library</sub>
  <br/>
  <sub>仅用 Python 标准库构建</sub>
</div>
