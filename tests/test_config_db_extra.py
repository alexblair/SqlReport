"""
test_config_db_extra.py — config_db 中 7 条未覆盖路径的边界测试

覆盖路径：
1. get_parent_categories — 父分类不存在（孤儿引用）→ break 退出
2. count_api_endpoints_by_report — 空列表早返
3. _invalidate_after_endpoint_update — before=None 早返
4. batch_delete_reports — 空 report_ids → 返回 0
5. _dump_exclusions — list/dict 类型 → json.dumps 序列化
6. upsert_schedule — 不传 report_ids 也不传 report_id → ValueError
7. _report_schedules_table_exists — mock 连接对象让 sqlite_master 查询失败 → MySQL 降级
"""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_db import (
    get_parent_categories,
    count_api_endpoints_by_report,
    _invalidate_after_endpoint_update,
    batch_delete_reports,
    _dump_exclusions,
    upsert_schedule,
    _report_schedules_table_exists,
    _UNSET,
)


# ---------------------------------------------------------------------------
# 辅助：创建内存库并初始化最小 schema
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    """创建 ':memory:' SQLite 连接，建好测试所需的最小表结构。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("""CREATE TABLE report_categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        parent_id   INTEGER,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (parent_id) REFERENCES report_categories(id)
    )""")

    conn.execute("""CREATE TABLE report_configs (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT    UNIQUE NOT NULL,
        sql_query         TEXT    NOT NULL DEFAULT '',
        default_page_size INTEGER NOT NULL DEFAULT 20,
        pool_id           INTEGER,
        sort_order        INTEGER NOT NULL DEFAULT 0,
        category_id       INTEGER,
        FOREIGN KEY (category_id) REFERENCES report_categories(id)
    )""")

    conn.execute("""CREATE TABLE api_endpoints (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id   INTEGER NOT NULL,
        url_path    TEXT    NOT NULL DEFAULT '',
        name        TEXT    NOT NULL DEFAULT '',
        enabled     INTEGER NOT NULL DEFAULT 1,
        columns     TEXT,
        filters     TEXT,
        sorts       TEXT,
        row_limit   INTEGER,
        output_format TEXT,
        api_key     TEXT,
        nested_filter TEXT,
        FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
    )""")

    # report_schedules 不建表——用于测试 _report_schedules_table_exists 的降级路径
    conn.execute("""CREATE TABLE schedule_reports (
        schedule_id INTEGER NOT NULL,
        report_id   INTEGER NOT NULL,
        enabled     INTEGER NOT NULL DEFAULT 1,
        order_index INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (schedule_id, report_id)
    )""")

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class TestConfigDbExtraBoundary(unittest.TestCase):
    """config_db 未覆盖路径的边界测试。"""

    # ------------------------------------------------------------------
    # 1. get_parent_categories — 孤儿引用（父分类不存在）→ break 退出
    # ------------------------------------------------------------------
    def test_get_parent_categories_orphan_reference_breaks(self):
        """分类 B 的 parent_id 指向不存在的分类 999，验证提前 break 且不抛异常。"""
        conn = _make_conn()
        # 插入一个分类，parent_id 指向不存在的 999
        conn.execute(
            "INSERT INTO report_categories (id, name, parent_id, sort_order) "
            "VALUES (1, 'child', 999, 0)"
        )
        conn.commit()

        result = get_parent_categories(conn, 1)

        # parent_id=999 对应的分类不存在，循环应 break，返回空列表
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # 2. count_api_endpoints_by_report — 空列表早返
    # ------------------------------------------------------------------
    def test_count_api_endpoints_by_report_empty_list(self):
        """传入空 report_ids，验证直接返回空 dict，不执行 SQL。"""
        conn = _make_conn()

        result = count_api_endpoints_by_report(conn, [])

        self.assertEqual(result, {})

    # ------------------------------------------------------------------
    # 3. _invalidate_after_endpoint_update — before=None 早返
    # ------------------------------------------------------------------
    @patch("config_db._invalidate_api_static_cache")
    def test_invalidate_after_endpoint_update_before_none(self, mock_invalidate):
        """before=None 时应直接返回，不调用 _invalidate_api_static_cache。"""
        _invalidate_after_endpoint_update(None, "/new/path")
        mock_invalidate.assert_not_called()

    # ------------------------------------------------------------------
    # 4. batch_delete_reports — 空 report_ids → 返回 0
    # ------------------------------------------------------------------
    def test_batch_delete_reports_empty_ids(self):
        """传入空 report_ids，验证返回 0 且不操作数据库。"""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO report_configs (id, name, sql_query) VALUES (1, 'r1', 'SELECT 1')"
        )
        conn.commit()

        result = batch_delete_reports(conn, [])

        self.assertEqual(result, 0)
        # 验证原数据未被删除
        row = conn.execute("SELECT COUNT(*) AS cnt FROM report_configs").fetchone()
        self.assertEqual(row["cnt"], 1)

    # ------------------------------------------------------------------
    # 5. _dump_exclusions — list/dict 类型 → json.dumps 序列化
    # ------------------------------------------------------------------
    def test_dump_exclusions_list_serialization(self):
        """传入 list 类型，验证返回 JSON 字符串。"""
        data = [{"field": "status", "op": "!=", "value": "closed"}]
        result = _dump_exclusions(data)
        self.assertEqual(result, json.dumps(data, ensure_ascii=False))

    def test_dump_exclusions_dict_serialization(self):
        """传入 dict 类型，验证返回 JSON 字符串。"""
        data = {"exclude_ids": [1, 2, 3]}
        result = _dump_exclusions(data)
        self.assertEqual(result, json.dumps(data, ensure_ascii=False))

    # ------------------------------------------------------------------
    # 6. upsert_schedule — 不传 report_ids 也不传 report_id → ValueError
    # ------------------------------------------------------------------
    def test_upsert_schedule_no_report_ids_raises(self):
        """不传 report_ids 也不传 report_id，验证抛出 ValueError。"""
        conn = _make_conn()
        # 建最小 report_schedules 表以通过后续查询
        conn.execute("""CREATE TABLE IF NOT EXISTS report_schedules (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL DEFAULT '',
            schedule_type    TEXT    NOT NULL DEFAULT 'interval',
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            daily_time       TEXT    NOT NULL DEFAULT '08:00',
            misfire_policy   TEXT    NOT NULL DEFAULT 'skip',
            enabled          INTEGER NOT NULL DEFAULT 1,
            exclusions       TEXT,
            audit_enabled    INTEGER NOT NULL DEFAULT 0,
            next_run_at      TEXT
        )""")
        conn.commit()

        with self.assertRaises(ValueError) as ctx:
            upsert_schedule(conn, name="test_schedule")
        self.assertIn("至少需要绑定一个报表", str(ctx.exception))

    # ------------------------------------------------------------------
    # 7. _report_schedules_table_exists — mock sqlite_master 查询失败 → MySQL 降级
    # ------------------------------------------------------------------
    def test_report_schedules_table_exists_mysql_fallback(self):
        """mock 连接对象：sqlite_master 查询抛异常 → 降级 SHOW TABLES → 命中。"""
        mock_conn = MagicMock()
        # 第一次 execute（sqlite_master）抛异常，模拟非 SQLite 引擎
        mock_conn.execute.side_effect = [
            Exception("not a SQLite database"),  # sqlite_master 查询
            MagicMock(fetchone=MagicMock(return_value=("report_schedules",))),  # SHOW TABLES
        ]

        result = _report_schedules_table_exists(mock_conn)

        self.assertTrue(result)
        self.assertEqual(mock_conn.execute.call_count, 2)

    def test_report_schedules_table_exists_both_fail(self):
        """两次查询均失败，验证返回 False。"""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("connection error")

        result = _report_schedules_table_exists(mock_conn)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
