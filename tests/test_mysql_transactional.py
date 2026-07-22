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


if __name__ == "__main__":
    unittest.main()
