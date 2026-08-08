"""
test_sql_write_detect.py — 写语句检测函数 + allow_write 迁移测试（PH-04, T3a）

覆盖：
- sql_contains_write：白名单读语句为 False；各写语句为 True；
  注释/字符串内关键词不误判；CTE 读为 False；CTE+DML 为 True；多语句任一为写则 True
- 迁移 14（并入）：reports.allow_write 列存在、存量默认 1、重复执行幂等
"""

import unittest

import config_db
import query_executor
from tests.test_base import init_test_db, make_config_db


class TestSqlContainsWrite(unittest.TestCase):
    """写语句检测函数单元测试。"""

    def test_pure_read_sql_false(self):
        """纯读 SQL（SELECT）→ False。"""
        self.assertFalse(query_executor.sql_contains_write(
            "SELECT * FROM orders WHERE status='active'"))
        self.assertFalse(query_executor.sql_contains_write(
            "SELECT 1; SELECT 2"))

    def test_whitelist_read_keywords_false(self):
        """白名单：SHOW/DESCRIBE/DESC/EXPLAIN 均为读。"""
        for sql in (
            "SHOW TABLES",
            "SHOW CREATE TABLE orders",
            "DESCRIBE orders",
            "DESC orders",
            "EXPLAIN SELECT * FROM orders",
            "EXPLAIN ANALYZE SELECT * FROM orders",
        ):
            with self.subTest(sql=sql):
                self.assertFalse(query_executor.sql_contains_write(sql))

    def test_write_statements_true(self):
        """各写语句 → True。"""
        for sql in (
            "INSERT INTO orders (id) VALUES (1)",
            "UPDATE orders SET status='done' WHERE id=1",
            "DELETE FROM orders WHERE id=1",
            "REPLACE INTO orders (id) VALUES (1)",
            "CREATE TABLE tmp (id INT)",
            "DROP TABLE orders",
            "ALTER TABLE orders ADD COLUMN x INT",
            "TRUNCATE TABLE orders",
            "CALL refresh_proc()",
            "GRANT SELECT ON db.* TO 'u'",
            "REVOKE SELECT ON db.* FROM 'u'",
            "SET @x = 1",
            "SET GLOBAL sql_mode=''",
        ):
            with self.subTest(sql=sql):
                self.assertTrue(query_executor.sql_contains_write(sql))

    def test_keyword_in_comment_not_misdetected(self):
        """注释内写关键词不误判。"""
        self.assertFalse(query_executor.sql_contains_write(
            "-- DELETE FROM orders\nSELECT * FROM orders"))
        self.assertFalse(query_executor.sql_contains_write(
            "# UPDATE orders\nSELECT * FROM orders"))
        self.assertFalse(query_executor.sql_contains_write(
            "/* DROP TABLE orders */ SELECT * FROM orders"))

    def test_keyword_in_string_not_misdetected(self):
        """字符串字面量内写关键词不误判。"""
        self.assertFalse(query_executor.sql_contains_write(
            "SELECT 'UPDATE' AS word"))
        self.assertFalse(query_executor.sql_contains_write(
            'SELECT "DELETE FROM t" AS x'))
        self.assertFalse(query_executor.sql_contains_write(
            "SELECT * FROM logs WHERE msg='insert ok'"))

    def test_cte_read_false(self):
        """CTE 读（WITH ... SELECT）→ False。"""
        self.assertFalse(query_executor.sql_contains_write(
            "WITH x AS (SELECT id FROM orders) SELECT * FROM x"))
        self.assertFalse(query_executor.sql_contains_write(
            "WITH RECURSIVE x (n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x "
            "WHERE n < 10) SELECT * FROM x"))

    def test_cte_dml_true(self):
        """CTE + DML（WITH ... DELETE/UPDATE）→ True。"""
        self.assertTrue(query_executor.sql_contains_write(
            "WITH x AS (SELECT id FROM orders WHERE status='old') "
            "DELETE FROM orders WHERE id IN (SELECT id FROM x)"))
        self.assertTrue(query_executor.sql_contains_write(
            "WITH x AS (SELECT id FROM orders) "
            "UPDATE orders SET status='done' WHERE id IN (SELECT id FROM x)"))

    def test_multiple_statements_any_write_true(self):
        """多语句混合：任一为写 → True。"""
        self.assertTrue(query_executor.sql_contains_write(
            "SELECT * FROM orders; UPDATE orders SET status='x'"))
        self.assertTrue(query_executor.sql_contains_write(
            "UPDATE orders SET status='x'; SELECT * FROM orders"))

    def test_empty_and_none_false(self):
        """空/None/纯注释 → False。"""
        self.assertFalse(query_executor.sql_contains_write(""))
        self.assertFalse(query_executor.sql_contains_write(None))
        self.assertFalse(query_executor.sql_contains_write("   "))
        self.assertFalse(query_executor.sql_contains_write("-- 仅注释"))


class TestMigrationAllowWrite(unittest.TestCase):
    """迁移 14 追加：reports.allow_write。"""

    def _legacy_db(self):
        """构造存量库：report_configs 无 allow_write 列，有存量报表。"""
        conn = make_config_db()
        init_test_db(conn)
        conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES (?, ?)",
            ("存量报表", "SELECT 1"))
        conn.commit()
        return conn

    def _has_column(self, conn, table, col):
        return col in {row[1] for row in
                       conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def test_migration_adds_column_default_1(self):
        """存量库迁移后：allow_write 列存在且存量行默认 1（保持现状）。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        self.assertTrue(self._has_column(conn, "report_configs", "allow_write"))
        val = conn.execute(
            "SELECT allow_write FROM report_configs WHERE id=1").fetchone()[0]
        self.assertEqual(val, 1, "存量默认 1 = 保持现状")
        conn.close()

    def test_migration_idempotent(self):
        """重复执行迁移不报错、不改变列。"""
        conn = self._legacy_db()
        config_db._init_sqlite_migrations(conn)
        config_db._init_sqlite_migrations(conn)
        val = conn.execute(
            "SELECT allow_write FROM report_configs WHERE id=1").fetchone()[0]
        self.assertEqual(val, 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
