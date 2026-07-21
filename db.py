"""
db.py — 数据库层（兼容适配层）

职责：
作为 config_db.py 和 query_executor.py 的转发层，保持所有现有
导入路径兼容。新代码应直接导入 config_db 或 query_executor。
"""

# 从 config_db 导入所有配置数据库函数
from config_db import (  # noqa: F401, F403
    _get_db_config, _get_engine, _connect_sqlite,
    get_config_db, _get_schema_sql, init_db,
    _init_sqlite_migrations, _init_mysql_migrations,
    _SQLITE_SCHEMA, _MYSQL_SCHEMA,
    add_pool, get_pool, get_all_pools, update_pool, delete_pool, move_pool,
    add_user, get_user, get_user_by_id, get_all_users, update_user, delete_user,
    add_report, get_report, get_all_reports, update_report, delete_report,
    move_report, batch_update_report_pool, batch_update_report_cache,
    add_category, get_category, get_all_categories, update_category,
    delete_category, move_category,
    get_reports_by_category, get_reports, move_report_to_category,
    get_category_tree, get_parent_categories, batch_set_report_category,
    add_session, get_session, remove_session, get_all_sessions, clear_sessions,
    add_api_endpoint, get_api_endpoint, get_api_endpoint_by_path,
    get_api_endpoints_by_report, get_all_api_endpoints,
    update_api_endpoint, delete_api_endpoint, delete_api_endpoints_by_report,
)

# 从 query_executor 导入 MySQL 查询执行函数
from query_executor import (  # noqa: F401, F403
    _MySQLRow, _MySQLCursor, _MySQLConnection,
    _connect_mysql_config,
    create_mysql_connection, _split_sql_statements,
    execute_mysql_query, count_mysql_query,
)
