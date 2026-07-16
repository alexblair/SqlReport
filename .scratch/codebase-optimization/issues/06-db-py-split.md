# 06 — db.py 拆分配置DB + 查询执行

**What to build:** 将 `db.py`（1169行，混合配置DB CRUD 和 MySQL 查询执行两个职责）拆分为 `config_db.py`（配置数据库的双引擎 CRUD，~500行）和 `query_executor.py`（MySQL 查询执行 + 分页 + 缓存，~400行）。`db.py` 保留为薄兼容适配层，从新模块 `import *` 或转发引用。所有现有调用点（report.py、config.py、auth.py、export.py、server.py）暂不改动，通过 db.py 适配层保持透明。

**Blocked by:** 01 — AppContext + render.py 基础模块

**Status:** ready-for-agent

- [ ] 新建 `config_db.py`：提取配置DB相关函数（`init_db`、`get_config_db`、`add_user`、`add_pool`、`add_report` 等）
- [ ] 新建 `query_executor.py`：提取 MySQL 查询相关函数（`execute_mysql_query`、`create_mysql_connection`、`_MySQLRow` 等）
- [ ] `db.py` 改为薄适配层，从新模块转发公开符号
- [ ] 更新 test_db.py 中的导入引用
- [ ] 运行全量测试，确认无回归
