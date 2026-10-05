"""test_sql_persistent_write.py — sql_has_persistent_write 判定矩阵（spec §9.1）

分工：`sql_contains_write`（从严，服务权限/警示）与
`sql_has_persistent_write`（精确，只服务缓存读门槛与静态护栏）。

本文件同时钉死两者的**差异**：同一段 SQL 上「旧判为写、新判为非持久写」的用例
必须成对断言，防止后人把两个函数合并回一个布尔值。
"""

import unittest

import query_executor
from query_executor import sql_contains_write, sql_has_persistent_write


class TestSqlHasPersistentWriteSessionLevel(unittest.TestCase):
    """会话级语句（临时表 / SET @用户变量）→ 非持久写。"""

    def test_temp_table_script_is_not_persistent(self):
        """报表 35 形状：临时表脚本 + SELECT → 新判定 False；旧判定仍 True。"""
        sql = ("DROP TEMPORARY TABLE IF EXISTS tmp_a;\n"
               "CREATE TEMPORARY TABLE tmp_a SELECT id FROM orders;\n"
               "SELECT * FROM tmp_a;")
        self.assertFalse(sql_has_persistent_write(sql))
        self.assertTrue(sql_contains_write(sql), "分工：旧函数仍须判为写")

    def test_drop_temporary_table_if_exists(self):
        self.assertFalse(sql_has_persistent_write(
            "DROP TEMPORARY TABLE IF EXISTS tmp_a"))
        self.assertTrue(sql_contains_write("DROP TEMPORARY TABLE IF EXISTS tmp_a"))

    def test_create_temporary_table_as_select(self):
        self.assertFalse(sql_has_persistent_write(
            "CREATE TEMPORARY TABLE tmp_a SELECT id FROM orders"))

    def test_set_user_variable(self):
        self.assertFalse(sql_has_persistent_write("SET @x = 1"))
        self.assertTrue(sql_contains_write("SET @x = 1"), "分工：旧函数仍须判为写")

    def test_set_user_variable_from_subquery(self):
        self.assertFalse(sql_has_persistent_write(
            "SET @x := (SELECT COUNT(0) FROM tmp_a)"))

    def test_set_user_variable_behind_block_comment(self):
        """Review Focus 3：报表 35 的 9 条 SET 全部带前导块注释。

        注释未剥离会让形状匹配落空、把它们判成持久写，使整个修复静默失效。
        """
        sql = "/*** 入驻数计算 ***/\nSET @tmp_linked := (SELECT COUNT(0) FROM tmp_a);"
        self.assertFalse(sql_has_persistent_write(sql))
        self.assertTrue(sql_contains_write(sql))

    def test_mixed_session_level_script(self):
        sql = ("CREATE TEMPORARY TABLE t SELECT 1;\n"
               "/** c */ SET @x := 1;\n"
               "SELECT * FROM t;")
        self.assertFalse(sql_has_persistent_write(sql))


class TestSqlHasPersistentWriteReadStatements(unittest.TestCase):
    """纯读语句（含 CTE）→ 非持久写。"""

    def test_pure_cte_read(self):
        sql = "WITH x AS (SELECT id FROM orders) SELECT * FROM x"
        self.assertFalse(sql_has_persistent_write(sql))
        self.assertFalse(sql_contains_write(sql))

    def test_replace_function_in_cte_is_read(self):
        """Review Focus 4 / 报表 17 回归：`REPLACE(` 是字符串函数，不是 REPLACE INTO。"""
        sql = "WITH x AS (SELECT REPLACE(a, ',', '') AS a FROM t) SELECT * FROM x"
        self.assertFalse(sql_has_persistent_write(sql))
        self.assertTrue(sql_contains_write(sql), "旧判定的误报在此固定下来")

    def test_insert_function_in_cte_is_read(self):
        """同族：`INSERT(` 也是字符串函数。"""
        sql = "WITH x AS (SELECT INSERT('abc', 1, 1, 'x') AS s FROM t) SELECT * FROM x"
        self.assertFalse(sql_has_persistent_write(sql))
        self.assertTrue(sql_contains_write(sql))

    def test_plain_select_with_function_named_like_write(self):
        self.assertFalse(sql_has_persistent_write(
            "SELECT REPLACE(name, 'a', 'b') FROM t"))

    def test_comment_keywords_not_misdetected(self):
        for sql in ("-- DELETE FROM orders\nSELECT * FROM orders",
                    "# UPDATE orders\nSELECT * FROM orders",
                    "/* DROP TABLE orders */ SELECT * FROM orders"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_has_persistent_write(sql))

    def test_string_literal_keywords_not_misdetected(self):
        for sql in ("SELECT 'UPDATE' AS word",
                    'SELECT "DELETE FROM t" AS x',
                    "SELECT * FROM logs WHERE msg='insert ok'"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_has_persistent_write(sql))


class TestSqlHasPersistentWritePersistent(unittest.TestCase):
    """真持久写 → 必须判 True（从严）。"""

    def test_ddl_is_persistent(self):
        for sql in ("CREATE TABLE t (id INT)",
                    "DROP TABLE orders",
                    "ALTER TABLE orders ADD COLUMN x INT",
                    "TRUNCATE TABLE orders",
                    "CREATE INDEX idx ON orders (id)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_dml_is_persistent(self):
        for sql in ("INSERT INTO orders (id) VALUES (1)",
                    "UPDATE orders SET status='done' WHERE id=1",
                    "DELETE FROM orders WHERE id=1",
                    "REPLACE INTO orders (id) VALUES (1)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_system_variable_set_is_persistent(self):
        """Review Focus 2：`@@` 系统变量不得被当成 `@` 用户变量放行。"""
        for sql in ("SET GLOBAL sql_mode=''",
                    "SET PERSIST sql_mode=''",
                    "SET @@sql_mode=''",
                    "SET @@session.sql_mode=''",
                    "SET SESSION sql_mode=''",
                    "SET NAMES utf8mb4",
                    "SET autocommit=0",
                    "SET sql_mode=''"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_unresolvable_statements_are_persistent(self):
        """Review Focus 5：静态不可判定者一律从严。"""
        for sql in ("PREPARE s FROM 'SELECT 1'",
                    "EXECUTE s",
                    "CALL refresh_proc()",
                    "GRANT SELECT ON db.* TO 'u'",
                    "REVOKE SELECT ON db.* FROM 'u'"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_dml_bearing_cte_is_persistent(self):
        for sql in ("WITH x AS (SELECT id FROM orders) "
                    "DELETE FROM orders WHERE id IN (SELECT id FROM x)",
                    "WITH x AS (SELECT id FROM t) "
                    "UPDATE t SET a=1 WHERE id IN (SELECT id FROM x)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_any_persistent_statement_makes_whole_script_persistent(self):
        sql = ("DROP TEMPORARY TABLE IF EXISTS t;\n"
               "SET @x := 1;\n"
               "UPDATE real_table SET a = 1;\n")
        self.assertTrue(sql_has_persistent_write(sql))

    def test_report_37_shape_is_persistent(self):
        """真持久写报表 #37 的形状必须继续被挡住（缓存不得短路写）。"""
        sql = ("-- 更新唯一索引标识\n"
               "UPDATE t_project_pm_mapping_temp t SET t.mid = CONCAT(t.a, t.b);\n"
               "TRUNCATE `t_project_pm_mapping_order`;\n"
               "INSERT IGNORE `t_project_pm_mapping_order` (sub_company) "
               "SELECT sub_company FROM t_project_pm_mapping_temp;\n"
               "SELECT * FROM t_project_pm_mapping_order LIMIT 1;")
        self.assertTrue(sql_has_persistent_write(sql))
        self.assertTrue(sql_contains_write(sql))

    def test_temporary_named_identifiers_are_persistent(self):
        """真持久写：`temporary` 只是**表名/列名**（不是 TEMPORARY 修饰词）→ 必须判写。

        回归（复核 C-1）：曾用「关键词集合里出现 TEMPORARY」判定，导致
        `DROP TABLE temporary;` 被判成会话级、真实 DDL 被缓存读短路
        （实测 3 次翻页请求只执行 1 次）。TEMPORARY 必须是 CREATE/DROP 的
        **次关键词**（修饰词位置）才算临时表。
        """
        for sql in ("DROP TABLE temporary",
                    "CREATE TABLE temporary (id INT)",
                    "CREATE TABLE t (temporary INT)",
                    "DROP TABLE db1.temporary",
                    "CREATE TABLE `temporary` (id INT)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_has_persistent_write(sql), sql)
                self.assertTrue(sql_contains_write(sql), sql)

    def test_temporary_modifier_still_session_level(self):
        """反向：TEMPORARY 作**修饰词**时仍须判会话级（防止修 C-1 时过度收紧）。"""
        for sql in ("DROP TEMPORARY TABLE IF EXISTS tmp_a",
                    "CREATE TEMPORARY TABLE tmp_a SELECT id FROM orders",
                    "CREATE /* c */ TEMPORARY TABLE tmp_b SELECT 1",
                    "DROP TEMPORARY TABLE tmp_a"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_has_persistent_write(sql), sql)


class TestSqlHasPersistentWriteEdges(unittest.TestCase):
    """空输入与注释-only。"""

    def test_empty_and_comment_only_are_false(self):
        for sql in (None, "", "   ", "-- 仅注释", "/* 仅注释 */"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_has_persistent_write(sql))


class TestSqlHasPersistentWriteIntoFile(unittest.TestCase):
    """`SELECT … INTO OUTFILE` / `INTO DUMPFILE` → 必须判写（spec 2026-10-05 §4.3）。

    为什么不能只把 `OUTFILE`/`DUMPFILE` 加进 `_WRITE_STATEMENT_KEYWORDS`：
    首关键词是 `SELECT` 时，读白名单（`_READ_STATEMENT_KEYWORDS`）在关键词集合
    判定**之前**就 `continue` 掉了，那条路永远轮不到执行（spec §3 方案 A）。
    因此判定必须挂在「相邻关键词对」上，且插在读白名单分支之前。

    正向形状同时断言两个函数：只修一条通道 = 只堵住权限旁路或只堵住缓存短路，
    与复核 C-1「只修一侧被打回」是同一类错误。
    """

    def test_into_outfile_is_write(self):
        """写 MySQL 服务端文件：含注释分隔、小写、子句尾随、WITH 前缀、多语句。"""
        for sql in ("SELECT * FROM t INTO OUTFILE '/tmp/a.csv'",
                    "select id from t into outfile '/tmp/a' fields terminated by ','",
                    "SELECT * FROM t INTO /* c */ OUTFILE '/tmp/a'",
                    "WITH x AS (SELECT 1) SELECT * FROM x INTO OUTFILE '/tmp/a'",
                    "SET @x := 1; SELECT * FROM t INTO OUTFILE '/tmp/a';"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_contains_write(sql), sql)
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_into_dumpfile_is_write(self):
        for sql in ("SELECT * FROM t INTO DUMPFILE '/tmp/a'",
                    "select * from t into dumpfile '/tmp/a'"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_contains_write(sql), sql)
                self.assertTrue(sql_has_persistent_write(sql), sql)

    def test_into_user_variable_stays_read(self):
        """反向：`INTO @变量` 是会话级赋值，**必须继续判读**（否则纯读报表永久失去缓存）。"""
        for sql in ("SELECT * FROM t INTO @a, @b",
                    "SELECT COUNT(0) INTO @n FROM t"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_contains_write(sql), sql)
                self.assertFalse(sql_has_persistent_write(sql), sql)

    def test_user_variable_script_stays_non_persistent(self):
        """带 `SET @x` 的多语句脚本：精确判定仍为「非持久写」。

        `sql_contains_write` 在此为 True 属**既有分工**（SET 首关键词不在读白名单，
        从严判定），与 `INTO OUTFILE` 无关——本用例只钉精确判定，
        避免把两条通道的分工写反。
        """
        sql = "SET @x := 1; SELECT * FROM t INTO @a;"
        self.assertTrue(sql_contains_write(sql), "既有从严分工：SET 语句算写")
        self.assertFalse(sql_has_persistent_write(sql))

    def test_string_literal_and_comment_not_misdetected(self):
        """反向：字面量/注释里的同名词不产出关键词（tokenizer 已排除）。"""
        for sql in ("SELECT 'INTO OUTFILE' AS s",
                    'SELECT "INTO DUMPFILE" AS s',
                    "/* INTO OUTFILE '/p' */ SELECT 1",
                    "-- INTO OUTFILE '/p'\nSELECT 1",
                    "SELECT * FROM t WHERE msg = 'into outfile /tmp/a'"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_contains_write(sql), sql)
                self.assertFalse(sql_has_persistent_write(sql), sql)

    def test_identifier_named_like_outfile_is_not_write(self):
        """反向：单个标识符 `OUTFILE_COL` / 列名 `outfile` ≠ 关键词 `OUTFILE`。"""
        for sql in ("SELECT * FROM t INTO OUTFILE_COL",
                    "SELECT outfile FROM t"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_contains_write(sql), sql)
                self.assertFalse(sql_has_persistent_write(sql), sql)

    def test_table_named_outfile_keeps_write_conclusion(self):
        """表名含 outfile 本就判写，本次改动不得改变该结论。"""
        for sql in ("INSERT INTO outfile_order (id) VALUES (1)",
                    "CREATE TABLE outfile_log (id INT)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_contains_write(sql), sql)
                self.assertTrue(sql_has_persistent_write(sql), sql)



if __name__ == "__main__":
    unittest.main()
