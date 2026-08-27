"""
test_real_report_exec.py — 报表执行全链路真层测试（DEBUG 模式激活时运行）

在真实 SQLite 文件库与真实 MySQL 测试库上执行 execute_report 全链路：
建数据源表 → 插入数据 → 执行查询 → 验证分页 / 排序 / 过滤 / 类型转换。

设计要点：
- sqlite 真层：独立临时文件库作报表数据源，patch db.create_mysql_connection
  返回该真实连接（仅替换"连接工厂"，数据与查询全部真实）；
- mysql 真层：同一 DEBUG mysql 测试库建 sample 表，走 create_mysql_connection
  真实 TCP 连接；
- 未激活 DEBUG 模式时整层 skip。
"""

import unittest
from unittest.mock import patch

from decimal import Decimal

import db
import report as report_mod

from tests.integration.base import (
    RealDbBase, make_real_sqlite_conn, _cleanup_tmp_db, _tmp_db_paths,
)

_CREATE_SAMPLE = """
CREATE TABLE sample_report_data (
    id       INTEGER PRIMARY KEY,
    name     VARCHAR(64),
    amount   DECIMAL(12,2),
    created  VARCHAR(32)
)
"""

_INSERT_ROWS = [
    (1, "甲", 100.50, "2026-01-01"),
    (2, "乙", 200.75, "2026-01-02"),
    (3, "丙", 50.00, "2026-01-03"),
    (4, "丁", 999.99, "2026-01-04"),
    (5, "戊", 1.00, "2026-01-05"),
]


def _insert_sample(conn) -> None:
    for row in _INSERT_ROWS:
        conn.execute(
            "INSERT INTO sample_report_data (id,name,amount,created) VALUES (?,?,?,?)",
            row)
    conn.commit()


def _pool_config(name="real_test_pool", host="127.0.0.1", port=3306,
                 user="u", password="p", database="db") -> dict:
    return {
        "name": name, "host": host, "port": port,
        "user": user, "password": password, "database": database,
    }


class _RealReportExecMixin:
    """引擎无关的报表执行断言集（非 TestCase）。"""

    engine = None

    def _execute(self, sql, page=1, page_size=20, sorts=None, filters=None):
        """调用 execute_report 真实执行并返回首结果集。"""
        result = report_mod.execute_report(
            report_id=1,
            sql_query=sql,
            pool_config=_pool_config(),
            page=page, page_size=page_size,
            sorts=sorts, filters=filters,
            report={"prefer_cache": 0, "allow_write": 1,
                    "allow_all_output": 1, "max_rows": 0},
            cache=report_mod.QueryCache(),
        )
        self.assertIsNotNone(result.results)
        return result

    def test_query_and_pagination(self):
        sql = "SELECT id, name, amount FROM sample_report_data ORDER BY id"
        res = self._execute(sql, page=1, page_size=2)
        self.assertEqual(res.page_size, 2)
        rs = res.results[0]
        self.assertEqual(rs["total"], 5)
        self.assertEqual(len(rs["rows"]), 2)
        self.assertEqual(rs["columns"], ["id", "name", "amount"])

        res2 = self._execute(sql, page=3, page_size=2)
        self.assertEqual(len(res2.results[0]["rows"]), 1)  # 末页 1 行
        self.assertEqual(res2.results[0]["rows"][0][1], "戊")

    def test_filter(self):
        sql = "SELECT id, name, amount FROM sample_report_data"
        res = self._execute(sql, filters=[("amount", "gt", 100)])
        rs = res.results[0]
        self.assertEqual(rs["total"], 3)  # 100.50 / 200.75 / 999.99
        names = [r[1] for r in rs["rows"]]
        self.assertEqual(names, ["甲", "乙", "丁"])

    def test_sort_desc(self):
        sql = "SELECT id, name, amount FROM sample_report_data"
        res = self._execute(sql, sorts=[("amount", "desc")])
        rs = res.results[0]
        self.assertEqual(rs["rows"][0][1], "丁")
        self.assertEqual(rs["rows"][0][2], 999.99)
        self.assertEqual(rs["rows"][-1][1], "戊")

    def test_type_conversion_decimal(self):
        sql = "SELECT amount FROM sample_report_data WHERE id=1"
        res = self._execute(sql)
        val = res.results[0]["rows"][0][0]
        # 引擎差异：MySQL DECIMAL → Decimal；SQLite 无 DECIMAL 类型 → float
        self.assertIsInstance(val, (Decimal, float))
        self.assertEqual(float(val), float(Decimal("100.50")))

    def test_multi_statement_query(self):
        # 多段 SQL（含 CTE 与两个 SELECT）→ 返回两个结果集
        sql = ("SELECT id, name FROM sample_report_data WHERE id <= 2;"
               "SELECT COUNT(*) AS cnt FROM sample_report_data;")
        res = self._execute(sql)
        self.assertEqual(len(res.results), 2)
        self.assertEqual(res.results[1]["rows"][0][0], 5)


class RealReportExecSqliteTest(_RealReportExecMixin, RealDbBase):
    """真实 SQLite 文件库报表执行真层测试。"""

    engine = "sqlite3"

    def setUp(self):
        # 固定报表数据源文件库：建表插数一次，之后各用例共用该文件
        conn = make_real_sqlite_conn()
        self._data_path = _tmp_db_paths.pop()
        conn.executescript(_CREATE_SAMPLE)
        _insert_sample(conn)
        conn.close()

    def tearDown(self):
        _cleanup_tmp_db(getattr(self, "_data_path", None))

    def _new_data_conn(self):
        """连接同一报表数据源文件库（适配器包装，补齐事务接口）。"""
        return make_real_sqlite_conn(self._data_path)

    def _execute(self, sql, page=1, page_size=20, sorts=None, filters=None):
        """每次新建真实 sqlite 数据源连接（execute_report 结束时会 close）。"""
        data_conn = self._new_data_conn()
        with patch("db.create_mysql_connection", return_value=data_conn):
            try:
                return super()._execute(sql, page=page, page_size=page_size,
                                        sorts=sorts, filters=filters)
            finally:
                try:
                    data_conn.close()
                except Exception:
                    pass


class RealReportExecMysqlTest(_RealReportExecMixin, RealDbBase):
    """真实 MySQL 测试库报表执行真层测试（需 DEBUG 配置启用 mysql 引擎）。"""

    engine = "mysql"

    def setUp(self):
        self.conn.execute(_CREATE_SAMPLE)
        _insert_sample(self.conn)
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.execute("DROP TABLE IF EXISTS sample_report_data")
            self.conn.commit()
        except Exception:
            pass

    def _execute(self, sql, page=1, page_size=20, sorts=None, filters=None):
        """mysql 真层：连接工厂已真实指向测试库，无需 patch。"""
        return super()._execute(sql, page=page, page_size=page_size,
                                sorts=sorts, filters=filters)


if __name__ == "__main__":
    unittest.main()
