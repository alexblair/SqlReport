"""
test_mysql_transactional.py — execute_mysql_query 事务包装测试

测试策略：
- 使用 mock 创建 MySQL 连接，不依赖真实数据库
- 通过 MockMySQLMixin 控制游标行为
- 直接测试 query_executor.execute_mysql_query（而非 db 转发层）
"""

import unittest
from unittest.mock import MagicMock

import query_executor


class MockMySQLMixin:
    @staticmethod
    def make_mock_connection(mock_cursor=None):
        mock_conn = MagicMock()
        cursor = mock_cursor or MagicMock()
        mock_conn.cursor.return_value = cursor
        return mock_conn, cursor

    @staticmethod
    def make_mock_cursor(description=None, fetchall_return=None):
        mock_cursor = MagicMock()
        if description is not None:
            mock_cursor.description = description
        if fetchall_return is not None:
            mock_cursor.fetchall.return_value = fetchall_return
        return mock_cursor


class TestExecuteMySQLQueryTransactional(MockMySQLMixin, unittest.TestCase):
    """测试 execute_mysql_query 的 transactional 参数。"""

    def setUp(self):
        self.mock_conn, self.mock_cursor = self.make_mock_connection()
        self.mock_conn.begin = MagicMock()
        self.mock_conn.commit = MagicMock()
        self.mock_conn.rollback = MagicMock()

    def test_transactional_commit_on_success(self):
        """transactional=True 且全部成功时，应 begin + commit，不 rollback。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]

        query_executor.execute_mysql_query(
            self.mock_conn, "SELECT 1; SELECT 2", transactional=True
        )

        self.mock_conn.begin.assert_called_once_with()
        self.mock_conn.commit.assert_called_once_with()
        self.mock_conn.rollback.assert_not_called()
        self.assertEqual(self.mock_cursor.execute.call_count, 2)

    def test_transactional_rollback_on_failure(self):
        """transactional=True 且中间语句失败时，应 begin + rollback，不 commit。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]
        self.mock_cursor.execute.side_effect = [
            None,
            RuntimeError("fail"),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            query_executor.execute_mysql_query(
                self.mock_conn, "SELECT 1; SELECT 2", transactional=True
            )

        self.assertEqual(str(ctx.exception), "fail")
        self.mock_conn.begin.assert_called_once_with()
        self.mock_conn.rollback.assert_called_once_with()
        self.mock_conn.commit.assert_not_called()

    def test_non_transactional_compatibility(self):
        """transactional=False（默认）时，不调用 begin/commit/rollback。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]

        query_executor.execute_mysql_query(self.mock_conn, "SELECT 1")

        self.mock_conn.begin.assert_not_called()
        self.mock_conn.commit.assert_not_called()
        self.mock_conn.rollback.assert_not_called()
        self.mock_cursor.execute.assert_called_once_with("SELECT 1", ())

    def test_transactional_rollback_failure_does_not_mask_original(self):
        """rollback 自身失败时，不应掩盖原始异常。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]
        self.mock_cursor.execute.side_effect = RuntimeError("original")
        self.mock_conn.rollback.side_effect = RuntimeError("rollback fail")

        with self.assertRaises(RuntimeError) as ctx:
            query_executor.execute_mysql_query(
                self.mock_conn, "SELECT 1", transactional=True
            )

        self.assertEqual(str(ctx.exception), "original")
        self.mock_conn.rollback.assert_called_once_with()

    def test_transactional_begin_commit_order(self):
        """begin 在第一条 execute 之前，commit 在最后一条 execute 之后。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]

        call_order = []

        def track_begin():
            call_order.append("begin")

        def track_commit():
            call_order.append("commit")

        def track_execute(*args, **kwargs):
            call_order.append(f"execute:{args[0]}")

        self.mock_conn.begin.side_effect = track_begin
        self.mock_conn.commit.side_effect = track_commit
        self.mock_cursor.execute.side_effect = track_execute

        query_executor.execute_mysql_query(
            self.mock_conn, "SELECT 1; SELECT 2", transactional=True
        )

        self.assertEqual(call_order, [
            "begin",
            "execute:SELECT 1",
            "execute:SELECT 2",
            "commit",
        ])

    def test_transactional_single_select_statement(self):
        """单条 SELECT 也应正确包装事务。"""
        self.mock_cursor.description = [("id",)]
        self.mock_cursor.fetchall.return_value = [(1,)]

        result = query_executor.execute_mysql_query(
            self.mock_conn, "SELECT 1", transactional=True
        )

        self.assertEqual(len(result), 1)
        self.mock_conn.begin.assert_called_once_with()
        self.mock_conn.commit.assert_called_once_with()
        self.mock_conn.rollback.assert_not_called()

    def test_non_transactional_with_mixed_statements(self):
        """非事务模式下，多条语句正常执行，忽略 DDL/DML。"""
        _call_idx = 0
        descriptions = [None, [("id",)], None]

        def track_execute(*args, **kwargs):
            nonlocal _call_idx
            idx = _call_idx
            _call_idx += 1
            self.mock_cursor.description = descriptions[idx]
            if descriptions[idx] is not None:
                self.mock_cursor.fetchall.return_value = [(1,)]

        self.mock_cursor.execute.side_effect = track_execute

        result = query_executor.execute_mysql_query(
            self.mock_conn, "CREATE TABLE t (id INT); SELECT 1; INSERT INTO t VALUES (1)"
        )

        self.assertEqual(len(result), 1)
        self.mock_conn.begin.assert_not_called()
        self.mock_conn.commit.assert_not_called()
        self.mock_conn.rollback.assert_not_called()
        self.assertEqual(self.mock_cursor.execute.call_count, 3)


# ---------------------------------------------------------------------------
# 缺口5：execute_mysql_query 无结果集 → RuntimeError 语义
# ---------------------------------------------------------------------------


class TestExecuteMySQLQueryNoResult(MockMySQLMixin, unittest.TestCase):
    """无任何结果集时抛出 RuntimeError；混合语句只收集 SELECT 结果。"""

    def test_all_ddl_raises_runtime_error(self):
        """全部为 DDL（description=None）→ RuntimeError"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None
        with self.assertRaises(RuntimeError) as ctx:
            query_executor.execute_mysql_query(conn, "CREATE TABLE t (id INT)")
        self.assertIn("未返回任何结果集", str(ctx.exception))
        self.assertIn("SELECT", str(ctx.exception))

    def test_all_dml_raises_runtime_error(self):
        """全部为 DML（UPDATE）→ RuntimeError"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None
        with self.assertRaises(RuntimeError):
            query_executor.execute_mysql_query(conn, "UPDATE t SET a=1")

    def test_empty_sql_raises_runtime_error(self):
        """空 SQL / 纯注释 → RuntimeError（无结果集收集）"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None  # 注释语句执行后无结果集
        with self.assertRaises(RuntimeError):
            query_executor.execute_mysql_query(conn, "")
        with self.assertRaises(RuntimeError):
            query_executor.execute_mysql_query(conn, "-- 只有注释")

    def test_comment_only_never_executes(self):
        """纯注释：整段被拆为 1 条语句提交执行（无结果集 → RuntimeError）"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None  # 注释语句执行后 description 为空
        with self.assertRaises(RuntimeError):
            query_executor.execute_mysql_query(conn, "-- 只有注释")
        # 真实行为：注释段仍会被 execute 提交给驱动（MySQL 端视为空语句）
        self.assertEqual(cursor.execute.call_count, 1)

    def test_mixed_ddl_and_select_returns_select_only(self):
        """DDL + SELECT 混合 → 仅收集 SELECT 结果集"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None
        state = {"i": 0}

        def do_execute(*args, **kwargs):
            if state["i"] == 1:
                cursor.description = [("id",)]
                cursor.fetchall.return_value = [(1,)]
            state["i"] += 1

        cursor.execute.side_effect = do_execute
        results = query_executor.execute_mysql_query(
            conn, "CREATE TABLE t (id INT); SELECT * FROM t")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["columns"], ["id"])
        self.assertEqual(results[0]["rows"], [(1,)])
        self.assertEqual(cursor.execute.call_count, 2)

    def test_runtime_error_in_transaction_rolls_back(self):
        """真实缺陷修复：transactional=True 且无结果集 → RuntimeError 在 COMMIT 之前抛出 → ROLLBACK 不 COMMIT"""
        conn, cursor = self.make_mock_connection()
        cursor.description = None
        conn.begin = MagicMock()
        conn.commit = MagicMock()
        conn.rollback = MagicMock()

        with self.assertRaises(RuntimeError):
            query_executor.execute_mysql_query(
                conn, "UPDATE t SET a=1", transactional=True)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
