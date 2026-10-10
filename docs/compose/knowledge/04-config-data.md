# 配置 CRUD · 数据层 · 迁移

## 分层

```text
POST form → config.handle_* / handle_request
          → db.*（db.py re-export）/ config_db.* + 审计
          → SQLite 或 MySQL
```

`parse_config_path` → `{section, action, id, report_id, endpoint_id}`  
主正则 `_PATH_PATTERN`；**独立前缀**：`/config/scheduler*`、`/config/site-branding`、`/config/pools/test`、`/config/test-cases/import`。

## config_db 实体与 DAL

| 表/实体 | 主要方法 |
|---------|----------|
| `connection_pools` | add/get/all/update/delete/move_pool；`count_reports_by_pool` |
| `users` | add/get/update/delete_user |
| `report_configs` | add/get/update/delete/move_report；batch pool/cache/delete |
| `report_categories` | add/update/delete/move_category；`get_category_tree`；`batch_set_report_category` |
| `sessions` | add/get/remove_session；`delete_expired_sessions`；`delete_sessions_for_user` |
| `api_endpoints` | add/get_by_path/update/delete；`delete_api_endpoints_by_report`；静态缓存失效 |
| `api_keys` | list/add/delete/set_enabled |
| `report_schedules` + `schedule_reports` | upsert/get_due/mark_result/set_enabled/delete；`get_schedule_reports` |

**双引擎**：

- SQLite：`executescript`；`PRAGMA table_info`；WAL+FK  
- MySQL：按 `;` 拆执行；`SHOW COLUMNS`；`database` 反引号  
- 占位符统一 `?`；时间用 Python `time.strftime` 参数化（避 SQLite 方言）  
- **MySQL 1093**：`DELETE`/`UPDATE` 的**目标表不得出现在子查询 FROM 中**（MySQL 8.0 解析期即报错，与数据无关）；须派生表包装 `SELECT id FROM (SELECT … FROM 目标表 …) AS x`。SQLite 允许自引用 → 单测会绿、线上删报表必挂（2026-10-10 事故）

**迁移**：`init_db` → 引擎 DDL → `_init_sqlite_migrations` / `_init_sqlite` 对应迁移号幂等。  
迁移 14/15：api_keys 多 Key、smart_quote_flags；16：schedules；17：任务多绑定改造。

**级联**：删报表应用层级联端点+静态缓存+调度绑定（**不依赖 SQLite FK**）；孤儿任务清理 `delete_schedules_by_report` 须遵上「MySQL 1093」（单删/批量删均走此路径，异常未捕获时页面 500）。  
`delete_pool` 先将报表 `pool_id` 置 NULL。  
`_UNSET` 哨兵：update 显式 NULL vs 不更新。

**late import `db`**：为 `mock.patch("db._get_engine")` 友好——勿改成顶层 import。  
新符号加 config_db 后**同步 `db.py` 导入列表**。

## 配置页表单模式（`config.py` + `config_pages/`）

> B9-2 后：`config.py` 只管路由解析/共享助手/入口分发，各实体页实现在 `config_pages/<实体>.py`；
> `config.py` 末尾再导出全部名字，**外部一律继续用 `config.X`**（`server.py` 按名字分发）。
> 子模块通过 `import config` 在**调用期**取共享助手（`config._parse_form_data` 等），所以再导出块必须保留。

- GET `render_*_form_page` → POST `handle_*_add/edit/delete/copy/move`
- `_save_or_render`：`action=save` 200 留页；`action=save_close` 302 回列表 + flash
- 批量：`handle_batch_set_category` / `batch_pool` / `batch_cache` / `batch_delete`
- 池测试：`POST /config/pools/test` 不落库；**密码留空=沿用**
- memo/description：fetch POST preview（`needs_db=False`）
- 改用户密码/名 → `remove_sessions_for_user`；**禁止删当前登录用户**
- 复制报表**不继承**调度绑定
- 含写 SQL 才显示 `allow_write`；新建默认 0
- checkbox：hidden 0 + checkbox 1，取最后值

## app_config

| 文件 | 作用 |
|------|------|
| `app_config.json` | 主配置（不入库） |
| `app_config.debug.json` | DEBUG **深合并**（dict 递归；**list 整段替换**） |
| 显式 `CONFIG_FILE` 且无 `DEBUG_CONFIG_FILE` | **跳过** debug |

段：`server/log/error_log/redis/static_cache/file_permissions/audit_db/config_db[]`  
`get_active_db_config`：列表取 `enable=true`（兼容旧 dict）。  
`get_config` 进程缓存；改文件需 `reload_config`。  
`scheduler.enable` 默认 **false**。

## branding / file_permissions

- **branding**：实例本地 `config.db.site_settings` + `branding/favicon.img`；**不进 MySQL 配置库**；保存后必须 `invalidate_site_branding_cache`；颜色须带 `#`；图 ≤256KB PNG/ICO
- **file_permissions**：仅 `{static_cache.dir}/api`；非 root 关闭；**不跟 symlink**；apply 只 warning；默认 dir 0755 / file 0644

## 预设导入（DEBUG）

`POST /config/test-cases/import` → `preset_cases.import_preset_from_file`  
upsert 不删多余行；可覆盖测试池连接字段。

## 表结构变更（易漏，必须三处同步）

改配置表字段时，`config_db.py` 内通常要**同时**：

1. 更新 `_SQLITE_SCHEMA` / `_MYSQL_SCHEMA`；
2. 在 `_init_sqlite_migrations` **和** `_init_mysql_migrations` 各加幂等 `ALTER`；
3. 同步 `tests/test_base.py` 中硬编码 DDL（单元测试基类故意不 import `db` 以免循环依赖；集成测试 `tests/integration/base.py` 用 `config_db._get_schema_sql`）。

漏任一侧会造成引擎间或测试/生产 schema 漂移——且症状往往只在另一引擎或真层才暴露。

## 易踩坑

1. 改表 **三处 + test_base** 同步（见上节）
2. 新代码用 `config_db` 不用 `db` 当业务 DAL
3. 新 `/config` 路径进主正则或独立前缀
4. 删除安全先看 `test_deletion_safety`
5. flash 勿回显明文密码

---
最后核对：explore-2 报告 + 2026-09-29 从 AGENTS.md 迁入「表结构变更」节
