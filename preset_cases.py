# -*- coding: utf-8 -*-
"""预设测试用例（数据夹具）一键导入模块。

本模块实现「配置页 → 新增测试用例」按钮背后的数据导入能力：

- 从一份 JSON 夹具文件读取全量预设数据（连接池 / 分类 / 报表 / API 端点
  / API Key / 定时任务）。
- 按「名称」判定是否为「同一个测试用例」：存在则覆盖更新，不存在则新增
  （upsert 语义），从而适应最新用例。
- 自动解析实体间引用（如报表引用的连接池 / 分类名称、API 端点引用的报表
  名称、Key 引用的端点路径、定时任务绑定的多张报表）。
- 通过 PRAGMA table_info 动态获取列集合，仅写入夹具提供的字段，未提供字段
  交给表默认值，兼容性最强。

夹具 JSON 结构（顶层键为各实体分组，顺序即导入顺序）：

    {
      "connection_pools": [ {"name": "...", "host": "...", "port": 3306, ...}, ... ],
      "report_categories": [ {"name": "...", "parent": "<父分类名称或 null>", ...}, ... ],
      "report_configs":   [ {"name": "...", "pool": "<池名>", "category": "<分类名|null>", ...}, ... ],
      "api_endpoints":    [ {"report": "<报表名>", "name": "...", "url_path": "...", ...}, ... ],
      "api_keys":         [ {"endpoint": "<端点 url_path>", "name": "...", "api_key": "...", ...}, ... ],
      "report_schedules": [ {"name": "...", "reports": ["<报表名>", ...], ...}, ... ]
    }

数据优先级：夹具文件整体覆盖式落库（同名 upsert），但不会对库内「未出现在
夹具中」的既有数据做删除，保证导入是可叠加、可重复执行的。
"""

import json
import os
import sqlite3
import time

# 测试 MySQL 驱动（业务查询同款）。置于模块级句柄，便于测试用 mock 替换，
# 避免依赖真实 mysql.connector 安装环境。
try:
    import mysql.connector as _mysql_connector
except ImportError:  # pragma: no cover - 仅无驱动环境
    _mysql_connector = None

# 夹具文件默认路径：仓库 tests/ 目录下。
DEFAULT_PRESET_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "preset_test_cases.json"
)

# 各实体分组的导入配置。
#   table      : 目标表名
#   match_key  : 判定「同一测试用例」的列（字符串或列名列表，按名称覆盖）
#   refs       : 引用字段 → (外键列, 目标表, 目标匹配列)；导入时按名称查 id
#   children   : 子表（如定时任务↔报表的多对多关联）的级联处理配置
ENTITY_GROUPS = {
    "connection_pools": {
        "table": "connection_pools",
        "match_key": "name",
        "refs": {},
    },
    "report_categories": {
        "table": "report_categories",
        "match_key": "name",
        "refs": {
            "parent": ("parent_id", "report_categories", "name"),
        },
    },
    "report_configs": {
        "table": "report_configs",
        "match_key": "name",
        "refs": {
            "pool": ("pool_id", "connection_pools", "name"),
            "category": ("category_id", "report_categories", "name"),
        },
    },
    "api_endpoints": {
        "table": "api_endpoints",
        "match_key": "url_path",
        "refs": {
            "report": ("report_id", "report_configs", "name"),
        },
    },
    "api_keys": {
        "table": "api_keys",
        "match_key": ["endpoint_id", "name"],
        "refs": {
            "endpoint": ("endpoint_id", "api_endpoints", "url_path"),
        },
    },
    "report_schedules": {
        "table": "report_schedules",
        "match_key": "name",
        "refs": {},
        "children": {
            "reports": {
                "junction": "schedule_reports",
                "fk_self": "schedule_id",
                "fk_other": "report_id",
                "target_table": "report_configs",
                "target_match": "name",
            },
        },
    },
}


def load_preset(path: str = None) -> dict:
    """加载预设测试用例 JSON 文件，返回解析后的 dict。

    path 为 None 时使用 DEFAULT_PRESET_PATH。
    """
    path = path or DEFAULT_PRESET_PATH
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_columns(conn, table: str) -> dict:
    """返回 {列名: {notnull, default, type}}。"""
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {}
    for row in cur.fetchall():
        cols[row[1]] = {"notnull": row[3], "default": row[4], "type": row[2]}
    return cols


def _resolve_ref(conn, ref_spec, value):
    """按名称解析引用目标 id；目标不存在返回 ('MISSING', value)。"""
    if value in (None, ""):
        return None
    _, target_table, target_col = ref_spec
    row = conn.execute(
        f"SELECT id FROM {target_table} WHERE {target_col}=?", (value,)
    ).fetchone()
    if row is None:
        return ("MISSING", value)
    return row[0]


def _match_where_clause(match_key):
    """返回匹配用 WHERE 子句（占位符），取值由调用方从记录中抽取。"""
    if isinstance(match_key, (list, tuple)):
        return " AND ".join(f"{c}=?" for c in match_key)
    return f"{match_key}=?"


def _match_values(match_key, data):
    """抽取匹配键对应的记录值（按名称判定覆盖）。"""
    if isinstance(match_key, (list, tuple)):
        return [data.get(c) for c in match_key]
    return [data.get(match_key)]


def _upsert_group(conn, group_cfg, records, summary, errors):
    """对单个实体分组执行 upsert，更新 summary 与 errors。"""
    table = group_cfg["table"]
    match_key = group_cfg["match_key"]
    cols = _get_columns(conn, table)
    refs = group_cfg.get("refs", {})
    children = group_cfg.get("children", {})

    # 分类需父级先入：无父的分类排前，保证 parent 引用可解析
    if table == "report_categories":
        records = sorted(records, key=lambda r: (r.get("parent") is not None,))

    for rec in records:
        data = dict(rec)
        # 解析引用 → 设置外键列，并从 data 移除引用字段本身
        for ref_field, ref_spec in refs.items():
            fk_col = ref_spec[0]
            raw = data.pop(ref_field, None)
            fk_val = _resolve_ref(conn, ref_spec, raw)
            if isinstance(fk_val, tuple) and fk_val[0] == "MISSING":
                msg = (f"[{table}] 记录 «{rec.get('name', rec.get('url_path', '?'))}» "
                       f"引用目标缺失: {ref_field}={fk_val[1]}，该引用置空")
                errors.append(msg)
                fk_val = None
            data[fk_col] = fk_val

        # JSON 列：dict/list 自动序列化
        for c in list(data.keys()):
            if c in cols and isinstance(data[c], (dict, list)):
                data[c] = json.dumps(data[c], ensure_ascii=False)

        # 仅保留表中真实存在的列
        data = {c: v for c, v in data.items() if c in cols}

        # 匹配既有记录（按名称）
        where = _match_where_clause(match_key)
        mvals = _match_values(match_key, data)
        existing = conn.execute(
            f"SELECT id FROM {table} WHERE {where}", mvals
        ).fetchone()

        if existing:
            sid = existing[0]
            upd_cols = [
                c for c in data.keys()
                if c in cols and c not in ("id", "created_at", "updated_at")
            ]
            if upd_cols:
                set_clause = ", ".join(f"{c}=?" for c in upd_cols)
                conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id=?",
                    [data[c] for c in upd_cols] + [sid],
                )
            summary["updated"] += 1
            target_id = sid
        else:
            ins_cols = [
                c for c in data.keys()
                if c in cols and c != "id"
            ]
            if ins_cols:
                placeholders = ", ".join("?" for _ in ins_cols)
                cur = conn.execute(
                    f"INSERT INTO {table} ({', '.join(ins_cols)}) "
                    f"VALUES ({placeholders})",
                    [data.get(c) for c in ins_cols],
                )
                target_id = cur.lastrowid
            else:
                target_id = None
            summary["added"] += 1

        # 级联子表（如定时任务绑定报表）
        for child_field, child_cfg in children.items():
            child_vals = rec.get(child_field) or []
            _sync_child(conn, child_cfg, target_id, child_vals, errors, rec)


def _sync_child(conn, child_cfg, self_id, child_names, errors, rec):
    """级联同步多对多关联表（先删后插，保持与夹具一致）。"""
    junction = child_cfg["junction"]
    fk_self = child_cfg["fk_self"]
    fk_other = child_cfg["fk_other"]
    target_table = child_cfg["target_table"]
    target_match = child_cfg["target_match"]
    conn.execute(f"DELETE FROM {junction} WHERE {fk_self}=?", (self_id,))
    order = 0
    for name in child_names:
        row = conn.execute(
            f"SELECT id FROM {target_table} WHERE {target_match}=?", (name,)
        ).fetchone()
        if row is None:
            errors.append(
                f"[{junction}] 定时任务 «{rec.get('name', '?')}» 绑定报表缺失: {name}")
            continue
        conn.execute(
            f"INSERT INTO {junction} ({fk_self}, {fk_other}, order_index) "
            f"VALUES (?,?,?)",
            (self_id, row[0], order),
        )
        order += 1
    conn.commit()


def _override_pools_with_test_mysql(data: dict, test_mysql_cfg: dict) -> None:
    """将夹具中的连接池连接信息覆盖为 test_mysql 的值。

    保证导入的报表定义（其 SQL 指向 business 库）实际查询的就是被建表/灌数的
    那份测试 MySQL，从而「表与字段真实存在」。仅覆盖连接字段，保留池名称等元数据。
    """
    host = test_mysql_cfg.get("host")
    port = int(test_mysql_cfg.get("port", 3306))
    user = test_mysql_cfg.get("user")
    password = test_mysql_cfg.get("password", "")
    database = test_mysql_cfg.get("database")
    for p in data.get("connection_pools", []) or []:
        p["host"] = host
        p["port"] = port
        p["user"] = user
        p["password"] = password
        p["database"] = database


def setup_test_mysql_tables(test_mysql_cfg: dict) -> dict:
    """连接 DEBUG 的测试用 MySQL，校验写权限，建表并初始化测试数据。

    流程：
      1. 连接目标 MySQL（库不存在则尝试 CREATE DATABASE IF NOT EXISTS）；
      2. 写权限校验：建哨兵表 → 插入 → 删除，任一失败即判定无写权限；
      3. 依次按配置执行各测试表的 DDL 与种子 SQL。

    返回（结构化结果，供导入流程汇总到提示信息）：
      {
        "ok": bool, "write_ok": bool, "database": str,
        "tables": [{"name":, "seed_rows":}], "errors": [str, ...]
      }

    依赖 mysql.connector（业务查询同款驱动）；未安装时 ok=False 并在 errors
    标注，不抛异常（导入流程仍完成 config_db 元数据部分）。
    """
    if _mysql_connector is None:
        return {
            "ok": False, "write_ok": False, "database": None,
            "tables": [],
            "errors": ["mysql.connector 未安装，无法初始化测试 MySQL（业务查询同款驱动）"],
        }
    summary = {
        "ok": False, "write_ok": False,
        "database": test_mysql_cfg.get("database"),
        "tables": [], "errors": [],
    }
    base = {
        "host": test_mysql_cfg["host"],
        "port": int(test_mysql_cfg.get("port", 3306)),
        "user": test_mysql_cfg["user"],
        "password": test_mysql_cfg.get("password", ""),
        "connection_timeout": 10,
        "charset": "utf8mb4",
    }
    try:
        conn = _mysql_connector.connect(**base)
    except _mysql_connector.Error as e:
        summary["errors"].append(f"连接测试 MySQL 失败: {e}")
        return summary
    try:
        cur = conn.cursor()
        db = test_mysql_cfg.get("database")
        if db:
            try:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}`")
                cur.execute(f"USE `{db}`")
            except _mysql_connector.Error as e:
                summary["errors"].append(f"创建/切换测试库 {db} 失败: {e}")
                return summary
        # 写权限校验：建哨兵表 + 插入 + 删除
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS `__sr_perm_check` (`id` INT)")
            cur.execute("INSERT INTO `__sr_perm_check` (`id`) VALUES (1)")
            cur.execute("DROP TABLE IF EXISTS `__sr_perm_check`")
            conn.commit()
            summary["write_ok"] = True
        except _mysql_connector.Error as e:
            summary["errors"].append(f"测试 MySQL 写权限不足（无法建表/插入）: {e}")
            return summary
        # 建表 + 初始化测试数据（先清后灌，保证重复导入幂等、数据一致）
        for t in (test_mysql_cfg.get("tables") or []):
            name = t.get("name")
            ddl = t.get("ddl")
            seed = t.get("seed") or []
            try:
                if ddl:
                    cur.execute(ddl)
                    # 清空既有数据，避免种子主键冲突；测试表无外键依赖，安全
                    cur.execute(f"DELETE FROM `{name}`")
                for sql in seed:
                    cur.execute(sql)
                conn.commit()
                summary["tables"].append({"name": name, "seed_rows": len(seed)})
            except _mysql_connector.Error as e:
                conn.rollback()
                summary["errors"].append(f"测试表 {name} 初始化失败: {e}")
        summary["ok"] = True
    finally:
        conn.close()
    return summary


def import_preset_test_cases(conn, data: dict, path: str = None,
                             test_mysql_cfg: dict = None) -> dict:
    """将预设测试用例 upsert 导入当前 config_db，并（可选）初始化测试 MySQL。

    参数:
      conn : SQLite 连接（config_db 连接）
      data : 解析后的夹具 dict（load_preset 的返回值）
      path : 仅用于错误提示的源文件路径
      test_mysql_cfg : 来自 app_config.get_test_mysql_config() 的测试 MySQL
                       配置（含 tables 定义）。为空（未启用/未安装驱动）时
                       跳过测试 MySQL 初始化，仅完成 config_db 元数据导入。

    返回:
      {
        "added": int, "updated": int,
        "groups": {分组名: {"added":, "updated":}},
        "errors": [str, ...],
        "path": str,
        "test_mysql": dict|None
      }
    """
    summary = {"added": 0, "updated": 0, "groups": {}, "errors": [], "path": path or "",
               "test_mysql": None}
    errors = summary["errors"]

    # 测试 MySQL 启用时，让导入的连接池指向它，确保报表查询的是被建表的库
    if test_mysql_cfg:
        _override_pools_with_test_mysql(data, test_mysql_cfg)

    for group_name, group_cfg in ENTITY_GROUPS.items():
        records = data.get(group_name) or []
        if not isinstance(records, list):
            errors.append(f"分组 {group_name} 格式错误：应为数组")
            continue
        before_added = summary["added"]
        before_updated = summary["updated"]
        try:
            _upsert_group(conn, group_cfg, records, summary, errors)
        except Exception as e:  # noqa: BLE001
            errors.append(f"分组 {group_name} 导入异常: {e}")
        conn.commit()
        summary["groups"][group_name] = {
            "added": summary["added"] - before_added,
            "updated": summary["updated"] - before_updated,
            "count": len(records),
        }

    # 可选：初始化测试 MySQL（建表 + 灌数据），与 config_db 元数据导入解耦
    if test_mysql_cfg:
        try:
            mysql_summary = setup_test_mysql_tables(test_mysql_cfg)
            summary["test_mysql"] = mysql_summary
            if mysql_summary.get("errors"):
                errors.extend(mysql_summary["errors"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"测试 MySQL 初始化异常: {e}")

    return summary


def import_preset_from_file(conn, path: str = None,
                            test_mysql_cfg: dict = None) -> dict:
    """从文件加载并导入预设测试用例，返回 import_preset_test_cases 的结果。

    test_mysql_cfg 透传至 import_preset_test_cases（见其说明）。
    """
    path = path or DEFAULT_PRESET_PATH
    data = load_preset(path)
    return import_preset_test_cases(conn, data, path=path,
                                    test_mysql_cfg=test_mysql_cfg)
