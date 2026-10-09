"""
tests/test_mysql_pool.py — MySQL 有界连接池（C-2）

背景：
    性能基线（spec §10.2 第 4 条）实测 `create_mysql_connection` 每次
    连接建立 **113.5ms**（TCP 握手 + 认证）。缓存未命中时每次查询都要付一次，
    且 `ThreadingHTTPServer` 每请求一线程，并发下连接数无上限。

设计要点（spec §5 C-2）：
    1. **归还语义藏在 close() 里** —— 池化连接的 `close()` 是「归还池」而非
       「真关闭」，因此 `report.execute_report` 的 `finally: conn.close()`
       一行都不用改。既有 patch `report.db.create_mysql_connection` 的测试
       也不受影响。
    2. **read_timeout 必须进池键** —— Web 交互传 30s、调度器不传（防慢查询
       定时任务被砍断，批次 5#18 的既有修复）。混池会让调度器的慢报表拿到
       30s 超时的连接而**必然失败**。这是本文件最重要的护栏。

本文件不依赖真实 MySQL（用假 connector），保证全量 discover 时永远能跑。
"""

import unittest
from unittest.mock import patch, MagicMock

import query_executor
from query_executor import create_mysql_connection, clear_pools


POOL_CFG = {"host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "d"}


def _fake_conn():
    """可用的假 MySQL 连接：ping 探活返回 True。"""
    conn = MagicMock()
    conn.ping.return_value = True
    return conn


class TestPoolBasics(unittest.TestCase):
    def setUp(self):
        clear_pools()

    def tearDown(self):
        clear_pools()

    @patch("mysql.connector.connect")
    def test_borrow_return_borrow_reuses_connection(self, mock_connect):
        """✅ Positive: 借出→归还→再借出，底层 connect 只调 1 次。

        注意必须是「归还后再借」：两个同时借出且都未归还的连接
        不可能共用同一个底层连接（那会变成两个请求共用一条连接）。
        """
        mock_connect.return_value = _fake_conn()

        c1 = create_mysql_connection(POOL_CFG)
        c1.close()
        c2 = create_mysql_connection(POOL_CFG)

        self.assertEqual(mock_connect.call_count, 1)

    @patch("mysql.connector.connect")
    def test_concurrent_borrow_creates_separate_connections(self, mock_connect):
        """✅ Positive: 两个同时借出未归还 → 各自独立建连（不共享连接）。"""
        mock_connect.side_effect = [_fake_conn(), _fake_conn()]

        c1 = create_mysql_connection(POOL_CFG)
        c2 = create_mysql_connection(POOL_CFG)

        self.assertEqual(mock_connect.call_count, 2)
        c1.close()
        c2.close()

    @patch("mysql.connector.connect")
    def test_close_returns_to_pool(self, mock_connect):
        """✅ Positive: close() 是归还不是真关闭；再借出拿到同一个对象。"""
        raw = _fake_conn()
        mock_connect.return_value = raw

        c1 = create_mysql_connection(POOL_CFG)
        c1.close()
        c2 = create_mysql_connection(POOL_CFG)

        self.assertEqual(mock_connect.call_count, 1,
                         "归还后应复用同一底层连接")
        self.assertIs(c2._raw, raw, "应拿到同一个底层连接对象")
        raw.close.assert_not_called()

    @patch("mysql.connector.connect")
    def test_passthrough_methods(self, mock_connect):
        """✅ Positive: cursor/commit/rollback/事务接口原样透传。"""
        raw = _fake_conn()
        mock_connect.return_value = raw

        conn = create_mysql_connection(POOL_CFG)
        conn.cursor()
        conn.commit()
        conn.rollback()
        conn.start_transaction()

        raw.cursor.assert_called()
        raw.commit.assert_called()
        raw.rollback.assert_called()
        raw.start_transaction.assert_called()

    @patch("mysql.connector.connect")
    def test_different_pool_config_uses_different_pool(self, mock_connect):
        """✅ Positive: database 不同 → 不同池。"""
        mock_connect.return_value = _fake_conn()

        create_mysql_connection(POOL_CFG)
        create_mysql_connection(dict(POOL_CFG, database="other"))

        self.assertEqual(mock_connect.call_count, 2)


class TestReadTimeoutIsolation(unittest.TestCase):
    """read_timeout 必须进池键 —— 调度器慢查询护栏的回归守卫。"""

    def setUp(self):
        clear_pools()

    def tearDown(self):
        clear_pools()

    @patch("mysql.connector.connect")
    def test_read_timeout_separates_pools(self, mock_connect):
        """✅ Positive: 30s 与不设超时是两个池，绝不混用。"""
        mock_connect.return_value = _fake_conn()

        create_mysql_connection(POOL_CFG, read_timeout=30)
        create_mysql_connection(POOL_CFG, read_timeout=None)

        self.assertEqual(mock_connect.call_count, 2,
                         "read_timeout 不同必须分池，否则调度器慢查询会被 30s 砍断")

    @patch("mysql.connector.connect")
    def test_read_timeout_value_reaches_connector(self, mock_connect):
        """✅ Positive: 设了 read_timeout 就真的传给驱动；没设就不传该键。"""
        mock_connect.return_value = _fake_conn()

        create_mysql_connection(POOL_CFG, read_timeout=30)
        self.assertEqual(mock_connect.call_args.kwargs["read_timeout"], 30)

        create_mysql_connection(POOL_CFG, read_timeout=None)
        self.assertNotIn("read_timeout", mock_connect.call_args.kwargs)

    @patch("mysql.connector.connect")
    def test_same_read_timeout_shares_pool(self, mock_connect):
        """✅ Positive: 相同 read_timeout 归还后正常复用。"""
        mock_connect.return_value = _fake_conn()

        c1 = create_mysql_connection(POOL_CFG, read_timeout=30)
        c1.close()
        create_mysql_connection(POOL_CFG, read_timeout=30)

        self.assertEqual(mock_connect.call_count, 1)


class TestPoolBoundsAndHealth(unittest.TestCase):
    def setUp(self):
        clear_pools()

    def tearDown(self):
        clear_pools()

    @patch("mysql.connector.connect")
    def test_pool_overflow_falls_back_to_direct(self, mock_connect):
        """✅ Positive: 池满时直连降级，功能不因池不可用而失败。"""
        mock_connect.return_value = _fake_conn()
        limit = query_executor._POOL_MAX_SIZE

        held = [create_mysql_connection(POOL_CFG) for _ in range(limit)]
        extra = create_mysql_connection(POOL_CFG)  # 第 limit+1 个

        self.assertEqual(mock_connect.call_count, limit + 1)
        self.assertIsNotNone(extra.cursor())

    @patch("mysql.connector.connect")
    def test_overflow_connection_not_leaked_on_return(self, mock_connect):
        """✅ Positive: 池满时归还的连接被真关闭，不塞进池（防连接泄漏）。

        场景要这样构造：先借出 _POOL_MAX_SIZE 个**不归还**（池此时仍是空的，
        因为池只跟踪已归还的连接），再借一个；随后逐个归还，前 8 个把池填满，
        最后那个归还时池已满 → 必须真关闭。
        """
        raws = [_fake_conn() for _ in range(query_executor._POOL_MAX_SIZE + 1)]
        mock_connect.side_effect = raws

        held = [create_mysql_connection(POOL_CFG)
                for _ in range(query_executor._POOL_MAX_SIZE)]
        overflow = create_mysql_connection(POOL_CFG)
        for conn in held:
            conn.close()
        overflow.close()

        self.assertTrue(raws[-1].close.called,
                        "池满时归还的连接必须被真关闭，否则连接会泄漏")
        self.assertFalse(raws[0].close.called,
                         "成功入池的连接归还时不应被真关闭")

    @patch("mysql.connector.connect")
    def test_dead_connection_replaced_on_checkout(self, mock_connect):
        """✅ Positive: 借出时探活失败 → 丢弃并新建，不把死连接交给请求。"""
        dead = _fake_conn()
        # 死亡语义 = ping 抛异常（mysql-connector 真实契约：存活时返回 None）。
        # 2026-10-10 修正：原用 return_value=False 表达死亡，但真实驱动从不为
        # 存活连接返回 False，反而使 _is_alive 对**存活**连接恒为 False。
        dead.ping.side_effect = RuntimeError("connection lost")
        fresh = _fake_conn()
        mock_connect.side_effect = [dead, fresh]

        c1 = create_mysql_connection(POOL_CFG)
        c1.close()
        c2 = create_mysql_connection(POOL_CFG)

        self.assertEqual(mock_connect.call_count, 2)
        dead.ping.assert_called()
        dead.close.assert_called()

    @patch("mysql.connector.connect")
    def test_dead_connection_discarded_on_return(self, mock_connect):
        """✅ Positive: 归还时探活失败 → 直接关闭，不入池。"""
        dead = _fake_conn()
        dead.ping.side_effect = RuntimeError("connection lost")  # 死亡=抛异常
        mock_connect.return_value = dead

        conn = create_mysql_connection(POOL_CFG)
        conn.close()

        dead.close.assert_called_once()

    @patch("mysql.connector.connect")
    def test_release_is_idempotent(self, mock_connect):
        """✅ Positive: 同一连接 close() 两次不抛异常也不重复入池。"""
        mock_connect.return_value = _fake_conn()

        c1 = create_mysql_connection(POOL_CFG)
        c1.close()
        c1.close()
        c2 = create_mysql_connection(POOL_CFG)

        # 两次 close 后池里只应有一个连接
        self.assertEqual(mock_connect.call_count, 1)


class TestContextManager(unittest.TestCase):
    def setUp(self):
        clear_pools()

    def tearDown(self):
        clear_pools()

    @patch("mysql.connector.connect")
    def test_with_statement_returns_to_pool(self, mock_connect):
        """✅ Positive: with 退出走 close()，连接回池而非被关闭。"""
        raw = _fake_conn()
        mock_connect.return_value = raw

        with create_mysql_connection(POOL_CFG) as conn:
            conn.cursor()
        create_mysql_connection(POOL_CFG)

        self.assertEqual(mock_connect.call_count, 1)
        raw.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
