# SqlReport — DEEPSEEK V4 FLASH 完整复现提示词

> **目标**: 使用此提示词文档，配合 DEEPSEEK V4 FLASH（或兼容模型），从零开始完整复现 SqlReport 项目。
> **模型**: `opencode/deepseek-v4-flash-free` 或兼容的 AI 代码生成模型
> **说明**: 以下内容为项目全量规范，AI 应按章节顺序逐模块实现，确保所有功能点、测试、文档一次性交付。

---

## 1. 项目概述

**名称**: SqlReport — 轻量级 MySQL 网页报表工具

**核心功能**:
1. **连接池管理** — 可视化 CRUD 管理 MySQL 连接配置（主机、端口、用户、密码、数据库）
2. **用户管理** — 多用户支持，密码加盐哈希存储，Cookie Session 认证
3. **报表配置** — 自定义 SQL 查询，绑定连接池，配置默认分页大小，支持分类层级
4. **分页表格展示** — 内存分页，显示总页数，跳转任意页，多字段排序，多字段模糊筛选
5. **CSV 导出** — 一键导出完整查询结果，UTF-8 BOM 编码，兼容 Excel

**技术栈约束（硬性）**:
- Python 3.11+ 标准库 ONLY — 禁止任何 Web 框架（Flask/Django 等）
- 唯一允许的外部依赖: `mysql-connector-python`
- Web 服务器: `http.server`（Python 标准库）
- 配置数据库: SQLite（`sqlite3` 标准库）
- 前/后端: 纯 HTML + 内联 CSS，零 JavaScript 框架
- 测试: `unittest` 标准库（禁止 pytest）
- 全部代码须简体中文注释，所有沟通文档使用简体中文

**项目源码文件清单**（共 7 个 .py + 6 个测试 + 辅助脚本）:

```
SqlReport/
├── server.py              # HTTP 服务器入口、路由分发、认证中间件
├── config.py              # 配置页面 CRUD 处理 + HTML 渲染
├── report.py              # 报表执行、缓存、分页、排序、筛选
├── export.py              # CSV 导出
├── auth.py                # 认证（密码哈希 + Session + Cookie）
├── db.py                  # SQLite 配置存储 + MySQL 连接管理
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_export.py
│   ├── test_report.py
│   └── test_server.py
├── manage_service.sh      # systemd 服务管理
├── git-purge.sh           # Git 历史清理脚本
├── AGENTS.md              # AI 开发代理指引（本文档的子集）
├── opencode.json          # 模型配置
├── .gitignore
└── README.md              # 中英文双语 README
```

---

## 2. 全局编码规范（必须严格遵守）

### 2.1 硬性规则

| 规则 | 说明 |
|------|------|
| **零外部依赖** | 仅 `mysql-connector-python`。其余全部使用 Python 3.11+ 标准库 |
| **全面注释** | 每个 .py 文件顶部必须有模块职责 docstring。每个函数、类、非平凡代码块必须有注释 |
| **函数 < 50 行** | 单一职责。纯函数优先，I/O 隔离 |
| **依赖注入** | DB 连接对象显式传入函数，禁止全局导入 |
| **早 return** | 减少嵌套深度 |
| **测试先行** | 每个功能点必须有对应的单元测试，全部通过后方可交付 |

### 2.2 代码风格

- Python 3.11+ 语法（`match` 语句可用，f-strings, `datetime` 改进）
- 类型注解（`typing` 模块）
- 模块 docstring 使用 `""" """`
- HTML 模板全部在 Python 源码中以内联字符串方式（禁止外部 HTML 文件）
- CSS 全部内联在 `<style>` 标签中，统一使用现代扁平设计风格
- 无 JavaScript 框架，无 jQuery，仅用原生 DOM API

### 2.3 VENV 环境要求

```bash
python3 -m venv venv && source venv/bin/activate
pip install mysql-connector-python
```

所有命令（安装、运行、测试）必须在激活的 venv 内执行。

---

## 3. 数据库设计（SQLite — 配置存储）

### 3.1 数据库文件

默认路径: `config.db`（环境变量 `CONFIG_DB` 可覆盖）

### 3.2 表结构

#### connection_pools（连接池配置）

```sql
CREATE TABLE connection_pools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    host        TEXT    NOT NULL,
    port        INTEGER NOT NULL DEFAULT 3306,
    user        TEXT    NOT NULL,
    password    TEXT    NOT NULL,
    database    TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
);
```

#### users（系统用户）

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    UNIQUE NOT NULL,
    password_hash   TEXT    NOT NULL
);
```

#### report_categories（报表分类，支持树形层级）

```sql
CREATE TABLE report_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    parent_id   INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES report_categories(id) ON DELETE SET NULL
);
```

#### report_configs（报表配置）

```sql
CREATE TABLE report_configs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    UNIQUE NOT NULL,
    sql_query          TEXT    NOT NULL,
    default_page_size  INTEGER NOT NULL DEFAULT 20,
    pool_id            INTEGER,
    category_id        INTEGER,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
);
```

#### sessions（Session 持久化，24 小时过期）

```sql
CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created_at REAL NOT NULL
);
```

### 3.3 CRUD 函数清单（在 db.py 中实现）

**连接池**:
- `add_pool(conn, name, host, port, user, password, database) -> int`
- `get_pool(conn, pool_id) -> dict|None`
- `get_all_pools(conn) -> list[dict]`
- `update_pool(conn, pool_id, name, host, port, user, password, database) -> bool`
- `delete_pool(conn, pool_id) -> bool`（关联报表 pool_id 置 NULL）
- `move_pool(conn, pool_id, direction) -> bool`

**用户**:
- `add_user(conn, username, password_hash) -> int`
- `get_user(conn, username) -> dict|None`
- `get_user_by_id(conn, user_id) -> dict|None`
- `get_all_users(conn) -> list[dict]`
- `update_user(conn, user_id, username, password_hash) -> bool`
- `delete_user(conn, user_id) -> bool`

**报表配置**:
- `add_report(conn, name, sql_query, default_page_size, pool_id, category_id=None) -> int`
- `get_report(conn, report_id) -> dict|None`
- `get_all_reports(conn) -> list[dict]`
- `update_report(conn, report_id, name, sql_query, default_page_size, pool_id, category_id=None) -> bool`
- `delete_report(conn, report_id) -> bool`
- `move_report(conn, report_id, direction, category_id=None) -> bool`
- `batch_update_report_pool(conn, report_ids, pool_id) -> int`
- `move_report_to_category(conn, report_id, category_id) -> bool`
- `batch_set_report_category(conn, report_ids, category_id) -> int`

**报表分类**:
- `add_category(conn, name, parent_id=None) -> int`
- `get_category(conn, category_id) -> dict|None`
- `get_all_categories(conn) -> list[dict]`
- `update_category(conn, category_id, name, parent_id=None) -> bool`
- `delete_category(conn, category_id) -> bool`
- `move_category(conn, category_id, direction) -> bool`
- `get_reports_by_category(conn) -> (list[dict], list[dict])`（分类列表+未分类报表）
- `get_reports(conn, category_id=None) -> list[dict]`
- `get_category_tree(conn) -> list[dict]`（返回嵌套树形结构）
- `get_parent_categories(conn, category_id) -> list[dict]`

**Session**:
- `add_session(conn, token, username)`
- `get_session(conn, token) -> str|None`（自动检查 86400 秒过期）
- `remove_session(conn, token) -> bool`
- `get_all_sessions(conn) -> list[dict]`
- `clear_sessions(conn)`

**MySQL 管理**:
- `create_mysql_connection(pool_config) -> connection`
- `execute_mysql_query(conn, sql, params=()) -> (columns, rows)`
- `count_mysql_query(conn, sql, params=()) -> int`

### 3.4 数据库迁移策略

`init_db()` 必须幂等（`CREATE TABLE IF NOT EXISTS`）。包含迁移逻辑:
1. 如果旧版 `report_configs` 的 `pool_id` 列有 `NOT NULL` 约束，执行表重建
2. 如果缺少 `category_id` 列，执行 `ALTER TABLE ADD COLUMN`
3. 如果缺少 `report_categories` 表，创建它
4. 如果 `report_categories` 缺少 `parent_id` 列，添加它

---

## 4. 认证模块（auth.py）

### 4.1 密码哈希

- 算法: `hashlib.pbkdf2_hmac("sha256", ...)`
- 迭代次数: `100000`
- Salt: `secrets.token_hex(16)`（32 个十六进制字符）
- 存储格式: `salt$hex_digest`
- 校验: `hmac.compare_digest()` 常量时间比较

### 4.2 Session 管理

- 内存 dict 主存储: `_sessions: dict[str, str]`（token -> username）
- SQLite 持久化（降级友好: DB 写入失败不影响登录）
- Token 生成: `secrets.token_hex(32)`（64 个十六进制字符）
- 启动时 `load_sessions()` 从 SQLite 恢复
- `create_session(username) -> token`
- `get_session_user(token) -> str|None`
- `remove_session(token) -> bool`
- `clear_all_sessions()`

### 4.3 Cookie 工具

- `parse_cookie(header) -> dict`
- `make_set_cookie_header(token, max_age=86400) -> str`
  - 含 `HttpOnly`, `SameSite=Lax`, `Path=/`
- `make_expire_cookie_header() -> str`（`Max-Age=0`）

---

## 5. HTTP 服务器（server.py）

### 5.1 路由表

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/login` | 登录页 | 否 |
| POST | `/login` | 登录表单提交 | 否 |
| GET | `/` | 首页（302 → /report） | 是 |
| GET | `/logout` | 退出（清除 session） | 是 |
| GET/POST | `/config*` | 配置页 | 是 |
| GET | `/report*` | 报表页 | 是 |
| GET | `/export*` | CSV 导出 | 是 |

### 5.2 认证中间件

所有 `/config*`, `/report*`, `/export*` 路径自动检查 Cookie `session_id`:
- 有效 → 继续处理
- 无效 → 302 重定向到 `/login`

### 5.3 启动逻辑

```python
def main():
    - 初始化 SQLite 数据库（init_db）
    - 首次启动自动创建默认管理员（admin / admin123）
    - 从 SQLite 恢复 sessions
    - 创建 HTTPServer，端口 8000（默认），支持端口占用自动清理（fuser -k）
    - 守护线程 + join(timeout=1) 模式，确保 Ctrl+C 立即响应
```

### 5.4 默认管理员

- 用户名: `admin`
- 密码: `admin123`
- 仅在 `get_all_users()` 返回空列表时创建

### 5.5 配置

```python
HOST = "0.0.0.0"  # 环境变量: HOST
PORT = 8000        # 环境变量: PORT
CONFIG_DB = "config.db"  # 环境变量: CONFIG_DB
```

---

## 6. 配置页面（config.py）

### 6.1 URL 路由解析

正则: `^/config/(pools|users|reports|categories)(?:/(add|batch-pool|batch-set-category)|/(\d+)/(edit|delete|copy|move-up|move-down))?$`

解析结果格式: `{"section": "pools|users|reports|categories", "action": "...", "id": int|None}`

### 6.2 页面功能

**连接池管理**:
- 列表展示（名称、地址、用户、数据库、操作）
- 支持排序拖拽（↑↓ 按钮，交换 sort_order）
- 新增/编辑/复制/删除
- 复制时名称自动追加" (副本)"

**用户管理**:
- 列表展示（用户名、操作）
- 新增/编辑/删除
- 编辑时密码留空则不修改

**报表分类管理**:
- 分类批量操作（多选复选框）
- 批量修改连接池
- 批量设置分类
- 分类树形展示
- 报表可拖拽到其他分类（下拉选择）

**报表管理**:
- 按分类分组展示
- 添加/编辑/复制/删除
- 支持排序拖拽
- SQL 编辑器（格式化按钮 + 语法高亮预览）
- 连接池选择下拉

### 6.3 所有表单处理函数

```python
handle_pool_add(conn, form_body) -> (code, result)
handle_pool_edit(conn, pool_id, form_body) -> (code, result)
handle_pool_copy(conn, pool_id, form_body) -> (code, result)
handle_pool_delete(conn, pool_id) -> (code, result)

handle_user_add(conn, form_body) -> (code, result)
handle_user_edit(conn, user_id, form_body) -> (code, result)
handle_user_delete(conn, user_id) -> (code, result)

handle_report_add(conn, form_body) -> (code, result)
handle_report_edit(conn, report_id, form_body) -> (code, result)
handle_report_copy(conn, report_id, form_body) -> (code, result)
handle_report_delete(conn, report_id) -> (code, result)
handle_report_move_category(conn, report_id, form_body) -> (code, result)

handle_category_add(conn, form_body) -> (code, result)
handle_category_edit(conn, category_id, form_body) -> (code, result)
handle_category_delete(conn, category_id) -> (code, result)

handle_batch_pool(conn, form_body) -> (code, result)
handle_batch_set_category(conn, form_body) -> (code, result)
```

返回值格式: `("302", "/config?flash=消息")` 或 `("200", "<html>...")`

### 6.4 配置页面入口

```python
def handle_request(conn, method, path, query, form_body=None) -> (code, body, headers)
```

返回格式: `("200", "<html>", {})` 或 `("302", "/config?flash=...", {"Location": "..."})`

---

## 7. 报表页面（report.py）

### 7.1 URL 参数

| 参数 | 说明 |
|------|------|
| `id` | 报表 ID |
| `page` | 页码（从 1 开始） |
| `page_size` | 每页行数（默认从报表配置读取） |
| `sort` | 排序列名（可重复，多列） |
| `dir` | 排序方向 asc/desc（与 sort 配对） |
| `f_{colname}` | 筛选值（如 f_name=alice，多字段可重复） |
| `refresh` | 1 时强制刷新缓存 |

### 7.2 查询缓存

```python
class QueryCache:
    def __init__(self, ttl=300)  # 5 分钟过期
    def get(report_id, sql_query) -> CachedResult|None
    def set(report_id, columns, rows, sql_query)
    def invalidate(report_id)
    def clear()
```

### 7.3 数据流

1. `handle_request` → 解析 URL 参数
2. `render_report_page` → 获取报表配置 + 连接池信息
3. `execute_report` → 检查缓存 → 查询 MySQL（全量） → 缓存
4. 在缓存数据上执行 `_filter_rows`（多字段 AND 模糊筛选）
5. 在筛选结果上执行 `_sort_rows`（多字段稳定排序）
6. 在排序结果上截取分页（offset + limit）
7. 构建 HTML（表头含排序链接 + 筛选输入框，表格体，分页控件）

### 7.4 多字段筛选

```python
def _filter_rows(rows, columns, filters):
    # filters: list[(col, query), ...]
    # AND 逻辑，不区分大小写 LIKE '%query%'
```

### 7.5 多字段排序

```python
def _sort_rows(rows, columns, sorts):
    # sorts: list[(col, dir), ...] 按优先级从高到低
    # 使用稳定排序，从最低优先级到最高优先级
```

### 7.6 报表选择页

- 下拉框（按分类树形层级 optgroup 呈现）
- 列表视图（按分类层级缩进）
- 无报表时显示"暂无可用报表"

### 7.7 分页控制

- 上一页/下一页箭头
- 页码按钮（显示当前页附近 7 页 + 首尾页 + 省略号）
- 跳转输入框（GO 按钮）
- 每页行数选择（10/20/50/100/200）
- 全部清除筛选链接

### 7.8 报表页面入口

```python
def handle_request(conn, method, path, query, form_body=None, pool_override=None) -> (code, body, headers)
```

---

## 8. CSV 导出（export.py）

### 8.1 导出格式

- UTF-8 BOM（`\ufeff`）开头
- 逗号分隔
- 所有字段双引号包裹
- 字段内双引号转义为 `""`
- 行尾 `\n`

### 8.2 HTTP 响应头

```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="report_{id}.csv"; filename*=UTF-8''{urlencoded_name}
```

### 8.3 导出入口

```python
def handle_export(conn, query, pool_override=None) -> (code, body, headers)
def export_report_to_csv(sql_query, pool_config, filters=None) -> str
```

### 8.4 筛选兼容

导出时复用 report.py 的 `_filter_rows` 函数，使 CSV 导出支持与报表页面相同的多字段筛选。

---

## 9. 测试规范（tests/）

### 9.1 测试策略

- SQLite 使用 `:memory:` 内存数据库
- MySQL 相关使用 `unittest.mock.patch` + `MagicMock`
- 每个测试类 `setUp`/`tearDown` 独立创建/销毁数据库
- 配置数据库全局标志 `db._initialized` 在 tearDown 中重置

### 9.2 测试文件与覆盖

**test_db.py** — db.py 单元测试（约 414 行）:
- TestInitDB: 表创建、幂等性
- TestConnectionPoolCRUD: 增/查/改/删/去重/未找到
- TestUserCRUD: 增/查/改/删
- TestReportCRUD: 增/查/改/删/级联置空
- TestMySQLManager: mock 执行查询/COUNT（含分号处理）
- TestSessionCRUD: 增/查/删/清空/过期

**test_auth.py** — auth.py 单元测试（约 137 行）:
- TestPasswordHash: 正确密码/错误密码/哈希格式/畸形哈希/同一密码不同哈希/空密码
- TestSession: 创建查询/无效token/删除/删除不存在/清空
- TestCookieUtils: 解析空/单/多个/带空格/生成 Set-Cookie/过期

**test_config.py** — config.py 单元测试（约 336 行）:
- TestPathParsing: 各路径解析
- TestPoolFlow: 总览/新增表单/提交新增/重复名称/编辑表单/提交编辑/编辑不存在/删除
- TestUserFlow: 总览/新增/编辑/删除/重复
- TestReportFlow: 总览/表单含池选择/新增/编辑/删除/不存在池
- TestFlashMessage: flash 消息展示
- TestUnknownAction: 未知路径 302
- TestChineseRedirect: 中文 flash URL 编码/ASCII 不变

**test_report.py** — report.py 单元测试（约 507 行）:
- TestReportSelector: 列表/空列表
- TestReportExecution: 表格渲染/空结果/不存在/分页控件/第二页/自定义分页/无效ID/查询错误
- TestReportResult: 总页数计算/单页/整除/零分页
- TestExecuteReport: 分页/筛选排序/多字段筛选/多字段排序/缓存刷新/负页码修正/分号处理

**test_export.py** — export.py 单元测试（约 211 行）:
- TestExportToCSV: 内容含BOM/特殊字符转义/响应头/筛选导出/缺少ID/无效ID/报表不存在/查询错误
- TestExportReportToCSV: 空结果

**test_server.py** — server.py 集成测试（约 167 行）:
- TestServerIntegration: 登录页/密码错误/成功/未认证重定向/完整认证流程
- TestLoginPage: 渲染无错误/有错误/空错误

### 9.3 运行命令

```bash
source venv/bin/activate && python -m unittest discover -s tests/ -v
```

Prefer `unittest` over pytest。

---

## 10. 附加脚本

### 10.1 manage_service.sh

功能: 安装/卸载 systemd 服务
- 服务名: `web-report`
- 自动检测脚本所在目录为项目目录
- 使用 venv 中的 Python 启动 `server.py`
- 支持 SELinux 检测警告

### 10.2 git-purge.sh

功能: 从 Git 历史中彻底删除文件
- 步骤: .gitignore → git rm --cached → filter-branch → 清理
- 可选: `--push` 强制推送（支持 Token 注入 + 代理）
- 代理优先级: `--proxy` > `ALL_PROXY` > `HTTPS_PROXY` > `HTTP_PROXY`
- Token 优先级: `--token` > `GITHUB_TOKEN` > `GH_TOKEN`

---

## 11. 配置文件

### 11.1 opencode.json

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/deepseek-v4-flash-free",
  "small_model": "opencode/deepseek-v4-flash-free"
}
```

### 11.2 .gitignore

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
venv/
.env
.tmp/
config.db
.DS_Store
Thumbs.db
.opencode
```

---

## 12. 实现顺序（建议）

按以下顺序依次编码，每完成一个模块运行对应测试:

1. **db.py** — 数据库层（SQLite 表、CRUD、MySQL 连接管理）。测试: `test_db.py`
2. **auth.py** — 认证模块。测试: `test_auth.py`
3. **server.py** — HTTP 服务器。测试: `test_server.py`（需要先有 db + auth）
4. **config.py** — 配置页面。测试: `test_config.py`
5. **report.py** — 报表页面。测试: `test_report.py`
6. **export.py** — CSV 导出。测试: `test_export.py`
7. **manage_service.sh** + **git-purge.sh** — 辅助脚本
8. **AGENTS.md** + **README.md** + **.gitignore** + **opencode.json** — 项目文档

---

## 13. 交付标准

1. **全部 7 个 .py 源文件** 编码完成
2. **全部 6 个测试文件** 编写完整，`python -m unittest discover -s tests/ -v` 全部通过
3. **每个函数有 docstring 和注释**（简体中文）
4. **模块 docstring** 在文件顶部
5. **HTML 页面样式统一**（渐变导航栏、卡片布局、圆角表格、现代配色）
6. **AGENTS.md** 项目指引文件
7. **README.md** 中英文双语（功能列表、快速开始、页面说明、项目结构、技术栈）
8. **manage_service.sh** 和 **git-purge.sh** 辅助脚本
9. **opencode.json** 和 **.gitignore** 配置
10. **tests/__init__.py** 测试包标记

---

## 14. 设计风格参考

### 配色方案
- 导航栏: 深色渐变 `linear-gradient(135deg, #1e293b, #334155)`
- 主导色: 靛蓝 `#4f46e5`（按钮、链接、焦点边框）
- 背景: 浅灰 `#f1f5f9`
- 卡片: 白色 `#fff`，圆角 `12px`，柔和阴影
- 成功: 绿色 `#059669`
- 危险: 红色 `#dc2626`
- 字体: `-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`
- 等宽字体: `"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace`

### 动画
- 卡片淡入: `fadeUp 0.3s ease-out`
- 按钮 hover: `translateY(-1px)` 微浮效果
- 输入框 focus: 靛蓝边框 + 发光阴影

### 布局
- 页面固定在导航栏下方（`position: sticky; top: 0`）
- 内容区 `max-width: 1200px; margin: 0 auto`
- 表格水平滚动（`overflow-x: auto`）

---

## 15. 关键注意事项

1. **线程安全**: 每请求创建独立的 SQLite 连接（`get_config_db()` 每次返回新连接）
2. **降级友好**: Session SQLite 持久化失败时降级到纯内存，不阻止登录
3. **幂等启动**: `init_db()` 可重复调用
4. **中文支持**: CSV UTF-8 BOM，所有 UI 中文，flash 消息 URL 编码
5. **SQL 安全**: 分号和尾随空格在传递给 MySQL 前自动去除
6. **数值格式化**: Decimal 和 float 避免科学计数法（`0E-10` → `0`）
7. **外键约束**: 删除连接池/分类时关联字段置 NULL 而非级联删除
8. **404 处理**: 未知路径返回简单 `<h1>404</h1>`
9. **Ctrl+C 处理**: 守护线程 + join(timeout=1) 确保立即关闭
10. **端口占用**: 尝试 `fuser -k {PORT}/tcp` 自动清理

---

*End of DEEPSEEK V4 FLASH Prompt Document*
