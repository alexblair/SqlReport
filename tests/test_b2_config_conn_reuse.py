"""B2：配置库连接复用（请求内复用 + 跨请求池化）。

依据：docs/compose/reports/b2-work-brief.md §2 Task B2-1、§3 Task B2-2。

B2-1 覆盖点：
1. refresh_session(token, conn=...) 传入外部连接时不得自开连接（请求内复用）；
2. refresh_session(token) 不传 conn 时保持旧行为（自建并自关，向后兼容）。

B2-2 覆盖点（配置库 MySQL 连接池化，见 §3.1 包装层次）：
3. 连续 N 次 get_config_db() + close() 后，底层 mysql.connector.connect 只调 1 次；
4. 池满（>_POOL_MAX_SIZE）后不泄漏，多出的被真关闭；
5. 探活失败的连接不会被复用；
6. 借出必须从池中 pop（两个线程不能拿到同一条）；
7. 归还前 rollback()（清掉上一位借出者的未提交隐式事务）；
8. clear_pools() 一并清空配置库专属池。
"""

import threading
import unittest
from unittest import mock

import db
import query_executor as qe


class TestConfigConnReuse(unittest.TestCase):
    def test_refresh_session_accepts_external_conn(self):
        """refresh_session 接受外部连接时，不得自己再开一条。"""
        import auth
        opened = {"n": 0}

        def counting():
            opened["n"] += 1
            return mock.MagicMock()

        # token 在 patch 外创建：create_session 自身会取一次连接，
        # 必须排除在计数之外，才能只度量 refresh_session 的行为。
        tok = auth.create_session("u1")
        with mock.patch.object(auth.db, "get_config_db", side_effect=counting), \
             mock.patch.object(auth.db, "add_session") as add:
            conn = mock.MagicMock()
            auth.refresh_session(tok, conn=conn)
        self.assertEqual(opened["n"], 0, "传了 conn 仍自开连接")
        self.assertTrue(add.called, "未落库")

    def test_refresh_session_without_conn_still_opens_one(self):
        """不传 conn 时保持旧行为（向后兼容）。"""
        import auth
        opened = {"n": 0}

        def counting():
            opened["n"] += 1
            return mock.MagicMock()

        tok = auth.create_session("u2")
        with mock.patch.object(auth.db, "get_config_db", side_effect=counting), \
             mock.patch.object(auth.db, "add_session"):
            auth.refresh_session(tok)
        self.assertEqual(opened["n"], 1)


# ---------------------------------------------------------------------------
# B2-2：配置库 MySQL 连接池化
#
# 测试手法：patch("db._get_db_config") 固定一份 mysql 配置，再数
# `mysql.connector.connect` 被真正调用了多少次——池生效时该计数必须小于
# get_config_db() 的调用次数。池是模块级状态，每个用例前后都 clear_pools()。
# ---------------------------------------------------------------------------

_MYSQL_CFG = {
    "engine": "mysql", "enable": True,
    "host": "127.0.0.1", "port": 3306,
    "user": "root", "password": "p", "database": "sqlreport_config",
}


def _make_raw():
    """造一条能通过探活的假 raw 连接。

    ⚠️ 刻意让 `ping()` 返回 **None**（与 mysql-connector 真实契约一致），
    而不是 True——若返回 True，`bool(ping())` 写法也能通过测试，
    就会掩盖「真实 MySQL 下池恒空」的 bug（2026-10-10 实际踩到过）。
    """
    raw = mock.MagicMock()
    raw.ping.return_value = None
    return raw


def _make_dead_raw():
    """造一条探活会抛异常的假 raw 连接。"""
    raw = mock.MagicMock()
    raw.ping.side_effect = RuntimeError("connection lost")
    return raw


class TestIsAliveMatchesMysqlSemantics(unittest.TestCase):
    """_is_alive 必须匹配 mysql-connector 的真实契约。

    契约：ping() **成功返回 None**（不抛异常），失败才抛异常。
    若写成 `bool(raw.ping(...))`，对真实 MySQL 恒为 False → 连接池永远拿到死连接
    → 池退化成每次直连（实测每请求仍付 71–120ms 建连）。
    """

    def test_ping_returning_none_means_alive(self):
        raw = mock.MagicMock()
        raw.ping.return_value = None   # ← 真实 mysql-connector 的存活语义
        self.assertTrue(qe._is_alive(raw),
                        "ping() 返回 None（真实存活语义）被判成死连接")

    def test_ping_returning_true_also_alive(self):
        raw = mock.MagicMock()
        raw.ping.return_value = True
        self.assertTrue(qe._is_alive(raw))

    def test_ping_raising_means_dead(self):
        self.assertFalse(qe._is_alive(_make_dead_raw()))

    def test_real_surviving_connection_is_pooled(self):
        """端到端：探活通过的连接必须真进池（这是池生效的前提）。"""
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as cm:
            cm.side_effect = lambda **kw: _make_raw()
            conn = db.get_config_db()
            conn.close()
        self.assertEqual(_pooled_count(), 1,
                         "探活通过的连接未入池——池恒空，等于没有池")


def _pooled_count():
    """当前配置库池中留存的连接条数。"""
    return sum(len(b) for b in qe._config_pool.values())


class _ConfigPoolTestBase(unittest.TestCase):
    """公共夹具：每个用例前后清池，避免模块级池跨用例泄漏。"""

    def setUp(self):
        qe.clear_pools()

    def tearDown(self):
        qe.clear_pools()


class TestConfigPoolReuse(_ConfigPoolTestBase):
    """断言 1：连续 N 次 get_config_db() + close() 后，底层建连次数 == 1。"""

    def test_n_cycles_only_one_real_connect(self):
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: _make_raw()
            for _ in range(20):
                conn = db.get_config_db()
                self.assertIsInstance(conn, db._MySQLConnection)
                conn.close()

            self.assertEqual(
                connect_mock.call_count, 1,
                "池未生效：20 次借还却建了 %d 次连" % connect_mock.call_count,
            )
        self.assertEqual(_pooled_count(), 1, "归还后池里应恰好留着那一条")

    def test_returns_mysql_connection_subclass(self):
        """返回值必须是 _MySQLConnection 的子类（config_db 依赖其接口）。"""
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: _make_raw()
            conn = db.get_config_db()
            try:
                self.assertIsInstance(conn, db._MySQLConnection)
                self.assertIsInstance(conn, db._ConfigConnection)
                # config_db.py 的 CRUD 依赖该接口，不能换成用户查询池的类型
                self.assertTrue(hasattr(conn, "executescript"))
            finally:
                conn.close()

    def test_close_is_idempotent(self):
        """close() 语义是「归还池」，重复调用不得报错、不得重复入池。"""
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: _make_raw()
            conn = db.get_config_db()
            conn.close()
            conn.close()
        self.assertEqual(_pooled_count(), 1)


class TestConfigPoolCap(_ConfigPoolTestBase):
    """断言 2：池满（> _POOL_MAX_SIZE）后不泄漏，多出的被真关闭。"""

    def test_pool_overflow_closes_extra(self):
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: _make_raw()
            held = [db.get_config_db() for _ in range(qe._POOL_MAX_SIZE + 2)]
            raws = [c._conn for c in held]
            for c in held:
                c.close()

        self.assertEqual(_pooled_count(), qe._POOL_MAX_SIZE, "池中条数应被上限截住")
        over = raws[qe._POOL_MAX_SIZE:]
        self.assertEqual(len(over), 2)
        for raw in over:
            raw.close.assert_called_once()  # 多出的被真关闭
        for raw in raws[:qe._POOL_MAX_SIZE]:
            raw.close.assert_not_called()  # 池内保留的未被真关


class TestConfigPoolAlive(_ConfigPoolTestBase):
    """断言 3：探活失败的连接不会被复用。"""

    def test_dead_connection_not_reused(self):
        dead = _make_raw()
        # 死亡语义 = ping 抛异常（真实 mysql-connector 契约）；
        # 不能用 return_value=False，因为 _is_alive 已改为“不抛即活”。
        dead.ping.side_effect = RuntimeError("connection lost")
        alive = _make_raw()

        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            # 第一条：归还时探活失败 → 直接真关闭，不入池
            connect_mock.return_value = dead
            db.get_config_db().close()
            dead.close.assert_called_once()
            self.assertEqual(_pooled_count(), 0)

            # 第二条：池空必须重新建连，且拿到的不能是那条死连接
            connect_mock.return_value = alive
            conn2 = db.get_config_db()
            try:
                self.assertIs(conn2._conn, alive)
            finally:
                conn2.close()
            self.assertEqual(connect_mock.call_count, 2)

    def test_ping_exception_treated_as_dead(self):
        """探活抛异常也按「已死」处理（与既有 _is_alive 语义一致）。"""
        raw = _make_raw()
        raw.ping.side_effect = RuntimeError("connection lost")
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = raw
            db.get_config_db().close()
        self.assertEqual(_pooled_count(), 0)
        raw.close.assert_called_once()

    def test_dead_connection_inside_pool_is_skipped(self):
        """池中躺着一条已死的连接时，借出应丢弃它并重新建连。"""
        dead = _make_raw()
        alive = _make_raw()
        key = qe._config_pool_key(dict(_MYSQL_CFG))
        qe._config_pool[key] = [dead]
        dead.ping.side_effect = RuntimeError("connection lost")  # 死亡=抛异常

        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = alive
            conn = db.get_config_db()
            try:
                self.assertIs(conn._conn, alive)
            finally:
                conn.close()
        dead.close.assert_called_once()
        self.assertEqual(connect_mock.call_count, 1)


class TestConfigPoolExclusive(_ConfigPoolTestBase):
    """断言 4：借出必须从池中 pop（两个线程不能拿到同一条）。"""

    def test_borrow_pops_from_pool(self):
        # 刻意用 side_effect 返回**不同的** raw：若用 return_value，每次 connect
        # 都返回同一个 mock 对象，「两条连接是否同一条」就失去意义（池坏掉也测不出来）。
        raws = [_make_raw(), _make_raw()]
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: raws.pop(0)
            first = db.get_config_db()
            self.assertEqual(_pooled_count(), 0, "借出后池中不应还留着它")
            # 第一条尚未归还，池里没东西；第二条必须另建，不能复用同一条 raw
            second = db.get_config_db()
            self.assertIsNot(first._conn, second._conn)
            self.assertEqual(connect_mock.call_count, 2)
            # 第一条归还：应真的进池（而不是被吞掉）
            first.close()
            self.assertEqual(_pooled_count(), 1, "归还的连接未入池")
            # 第三条借用必须把那条 pop 走（池里不得再留着）
            third = db.get_config_db()
            self.assertIs(third._conn, first._conn, "未复用刚归还的那条")
            self.assertEqual(_pooled_count(), 0, "借出后未从池中 pop")
            self.assertEqual(connect_mock.call_count, 2, "第三条不应再建连")
            second.close()
            third.close()


    def test_concurrent_borrow_never_shares_a_connection(self):
        """多线程并发借出：同一条 raw 不得同时被两个线程持有。"""
        lock = threading.Lock()
        n = 8
        start = threading.Barrier(n)
        errors = []
        # 直接观测「借出标记」：借出时把同一时刻的持有点加一，若某个标记被
        # 同时持有（>1），说明池把同一条连接发给了两个线程。
        held = {}
        collisions = []

        # ⚠️ patch 必须提到线程**外面**：在线程内用 mock.patch 时，若线程
        # 在 patch 退出前被 join 超时或异常中断，patch 可能不会拆除，
        # 导致 mysql.connector.connect 全局残留为 MagicMock——
        # 这会让**之后所有**用例拿到假连接（曾使全量套件多出 72 个失败）。
        def worker():
            try:
                start.wait(timeout=10)
                conn = db.get_config_db()
                tag = conn._conn  # mock 对象本身作为「连接身份」
                with lock:
                    held[tag] = held.get(tag, 0) + 1
                    if held[tag] > 1:
                        collisions.append(tag)
                conn.close()
                with lock:
                    held[tag] -= 1
            except Exception as exc:  # pragma: no cover - 失败时给出原因
                errors.append(exc)

        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as cm:
            cm.side_effect = lambda **kw: _make_raw()  # 每次都是新的 raw
            threads = [threading.Thread(target=worker) for _ in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        self.assertEqual(errors, [], "并发借出过程报错")
        self.assertEqual(collisions, [], "两个线程同时持有了同一条连接（跨线程串包）")
        self.assertLessEqual(_pooled_count(), qe._POOL_MAX_SIZE)


class TestConfigPoolReturnRollback(_ConfigPoolTestBase):
    """归还前必须 rollback() 未提交的隐式事务（否则下一个借出者会继承）。"""

    def test_rollback_called_on_return(self):
        raw = _make_raw()
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = raw
            db.get_config_db().close()
        raw.rollback.assert_called_once()

    def test_second_borrower_gets_clean_connection(self):
        """第二次借出前（即上一次归还时）必须已经 rollback 过。"""
        raw = _make_raw()
        events = []

        def on_rollback():
            events.append("rollback")

        def on_ping(reconnect=True):
            events.append("ping")
            return True

        raw.rollback.side_effect = on_rollback
        raw.ping.side_effect = on_ping

        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = raw
            first = db.get_config_db()
            first.close()
            # 归还动作里 rollback 必须先于（或至少独立于）放入池：
            self.assertIn("rollback", events)
            events.clear()

            second = db.get_config_db()
            try:
                self.assertIs(second._conn, raw)  # 复用了同一条
            finally:
                second.close()
        self.assertEqual(events.count("rollback"), 1)

    def test_rollback_failure_discards_connection(self):
        """rollback 抛异常（连接已坏）时不得入池。"""
        raw = _make_raw()
        raw.rollback.side_effect = RuntimeError("gone")
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = raw
            db.get_config_db().close()
        self.assertEqual(_pooled_count(), 0)
        raw.close.assert_called_once()


class TestConfigPoolClearedByClearPools(_ConfigPoolTestBase):
    """新池必须在 clear_pools() 里一并清空，否则测试间连接泄漏。"""

    def test_clear_pools_drains_config_pool(self):
        raw = _make_raw()
        with mock.patch("db._get_db_config", return_value=dict(_MYSQL_CFG)), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.return_value = raw
            db.get_config_db().close()
        self.assertEqual(_pooled_count(), 1)
        qe.clear_pools()
        self.assertEqual(qe._config_pool, {})
        raw.close.assert_called_once()


class TestConfigPoolKeyIsolation(_ConfigPoolTestBase):
    """池键必须含 host 等语义维度：指向不同库的配置不得混池。"""

    def test_different_host_not_shared(self):
        cfg_a = dict(_MYSQL_CFG)
        cfg_b = dict(_MYSQL_CFG, host="db.other.example.com")
        self.assertNotEqual(qe._config_pool_key(cfg_a), qe._config_pool_key(cfg_b))

        current = {"cfg": cfg_a}

        def fake_config():
            return current["cfg"]

        with mock.patch("db._get_db_config", side_effect=fake_config), \
             mock.patch("mysql.connector.connect") as connect_mock:
            connect_mock.side_effect = lambda **kw: _make_raw()
            db.get_config_db().close()
            current["cfg"] = cfg_b
            db.get_config_db().close()
        self.assertEqual(connect_mock.call_count, 2,
                         "不同 host 不该复用同一条连接")


if __name__ == "__main__":
    unittest.main()
