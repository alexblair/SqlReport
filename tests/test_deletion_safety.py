"""
test_deletion_safety.py — 删除安全域测试（spec ux-optimization 批次2 #5/#6/#7）

规格出处：.scratch/ux-optimization/spec.md 批次2「删除安全（管理员破坏半径披露）」。

覆盖矩阵（功能点 → 缺口编号 → 测试方法，格式见 docs/conv/test/full-coverage.md）：

#5 单删报表级联对齐批量删
  DS-05-01 delete_report 级联删除该报表全部 api_endpoints
      → TestDeleteReportCascade.test_delete_report_removes_api_endpoints
  DS-05-02 delete_report 失效端点静态缓存（invalidate 按 url_path 调用）
      → TestDeleteReportCascade.test_delete_report_invalidates_static_cache
  DS-05-03 delete_report 无端点时正常删除（不抛错）
      → TestDeleteReportCascade.test_delete_report_without_endpoints_ok
  DS-05-04 count_api_endpoints_by_report【已移除，见文件头注记 1】
  DS-05-05 handle_report_delete flash 有端点分支（含 N 个 API 接口及其静态缓存）
      → TestHandleReportDeleteFlash.test_flash_with_endpoints
  DS-05-06 handle_report_delete flash 无端点保持原文案
      → TestHandleReportDeleteFlash.test_flash_without_endpoints_keeps_original_text
  DS-05-07 batch_delete_reports 行为不变对照回归（端点级联+缓存失效）
      → TestBatchDeleteReportsRegression.test_batch_delete_unchanged_cascades_endpoints
        TestBatchDeleteReportsRegression.test_batch_delete_unchanged_invalidates_static_cache
  DS-05-08 报表列表单删 confirm 注入端点数（两分支）
      → TestReportRowConfirmText.test_confirm_with_endpoints
        TestReportRowConfirmText.test_confirm_without_endpoints

#6 删连接池引用披露
  DS-06-01 count_reports_by_pool 分组计数（NULL 不计入）
      → TestCountReportsByPool.test_group_counts_by_pool
        TestCountReportsByPool.test_empty_db_returns_empty_dict
  DS-06-02 连接池 confirm 两分支（0 引用原文案 / N 引用披露失去连接）
      → TestPoolSectionDisclosure.test_confirm_zero_refs / test_confirm_nonzero_refs
        TestPoolSectionDisclosure.test_backward_compatible_without_counts（缺省参数兼容）
  DS-06-03 连接池列表渲染接线（渲染上下文注入真实引用计数）
      → TestPoolSectionDisclosure.test_render_pool_section_wires_counts
  DS-06-04 handle_pool_delete flash 两分支（已断开 N 个报表的连接，报表保留但无法执行 / 原文案）
      → TestHandlePoolDeleteFlash.test_flash_with_linked_reports
        TestHandlePoolDeleteFlash.test_flash_without_linked_reports

#7 用户操作安全
  DS-07-01 remove_sessions_for_user 内存清除该用户全部 token 并返回清除数
      → TestRemoveSessionsForUser.test_memory_clears_only_target_user
  DS-07-02 remove_sessions_for_user 同步删除持久层 sessions 行
      → TestRemoveSessionsForUser.test_persistent_rows_deleted
  DS-07-03 remove_sessions_for_user 目标无会话返回 0
      → TestRemoveSessionsForUser.test_unknown_user_returns_zero
  DS-07-04 handle_user_delete 服务端拒绝删除当前登录账号（不执行删除）
      → TestUserDeleteSafety.test_reject_delete_self
  DS-07-05 handle_user_delete 正常删除后注销其全部会话（内存+持久层）+ flash 计数
      → TestUserDeleteSafety.test_delete_other_kicks_sessions_and_flash
  DS-07-06 handle_user_delete 被删用户无会话时 flash 保持简洁原文案
      → TestUserDeleteSafety.test_delete_other_without_sessions_plain_flash
  DS-07-07 handle_user_edit 改密成功后踢会话 + flash 提示重新登录
      → TestUserEditPasswordKick.test_change_password_kicks_sessions
  DS-07-08 handle_user_edit 不改密不踢会话（原 flash 文案）
      → TestUserEditPasswordKick.test_edit_without_password_keeps_sessions
  DS-07-09 用户表当前登录用户行不渲染删除按钮（其余行保留）
      → TestUserSectionSelfDelete.test_self_row_has_no_delete_button
        TestUserSectionSelfDelete.test_other_rows_keep_delete_button
  DS-07-10 session_user 未传时向后兼容（所有行均渲染删除按钮）
      → TestUserSectionSelfDelete.test_backward_compatible_without_session_user
  DS-07-11 用户删除 confirm 文案统一为会话立即失效提示
      → TestUserSectionSelfDelete.test_confirm_mentions_session_invalidation

策略与 tests/test_config_extra.py 一致：:memory: SQLite（BaseConfigTest），
auth 持久层通过 @patch("db.get_config_db") 指向测试内存库；
302 flash 断言统一经 _flash() 解码后匹配。
"""

import sqlite3
import unittest
import time
from unittest.mock import patch

import config
import config_db
import db
import auth
import render
from tests.test_base import BaseConfigTest


# ---------------------------------------------------------------------------
# 实现期契约修订注记（主进程复核 2026-08-24，依据见各测试 docstring）：
# 1. DS-05-04 count_api_endpoints_by_report 不再单独建函数——报表列表渲染
#    上下文已有全量 api_endpoints_map（config._render_category_section 构建），
#    confirm 注入直接复用，零新增查询；独立计数函数无第二消费方（YAGNI）。
#    对应三个用例随实现决策移除。
# 2. flash/confirm 文案统一用户可见术语「API 接口」（合并页列名与
#    管理页标题均用「接口」），规格中「端点」为实现视角措辞。
# 3. 池删除 flash 取更完整文案「已断开 N 个报表的连接，报表保留但无法执行」，
#    与 confirm 披露口径一致。
# 4. build_pool_section_html 参数名定为 report_counts、
#    build_user_section_html 参数名定为 current_username。
# ---------------------------------------------------------------------------


class _NoCloseConn:
    """包装 sqlite3 连接：拦截 close()（auth 层会 close get_config_db 返回值，
    测试共享连接不能被真关闭），其余属性透传。"""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


# ---------------------------------------------------------------------------
# 实现期契约修订注记（2026-08-24 复核，依据见各测试 docstring）：
# 1. DS-05-04 count_api_endpoints_by_report 不再单独建函数——报表列表渲染
#    上下文已有全量 api_endpoints_map（config._render_category_section 构建），
#    confirm 注入直接复用该映射零新增查询；独立计数函数无第二消费方（YAGNI）。
#    对应三个用例随实现决策移除。
# 2. flash 文案统一用户可见术语「API 接口」（合并页列名与管理页标题均用
#    「接口」，规格中「端点」为实现视角措辞）；confirm 注入文案规格 d 项
#    本身即为用户可见措辞「N 个 API 接口」，与页面列名一致。
#    池删除 flash 取更完整口径「已断开 N 个报表的连接，报表保留但无法执行」，
#    与 confirm 披露一致。
# 3. build_pool_section_html 参数名定为 report_counts、
#    build_user_section_html 参数名定为 current_username。
# ---------------------------------------------------------------------------


def _flash(body: str) -> str:
    """从重定向 Location 中提取解码后的 flash 消息（同 test_config_extra._flash）。"""
    if "?" not in body:
        return ""
    qs = body.split("?", 1)[1]
    import urllib.parse
    return urllib.parse.parse_qs(qs, keep_blank_values=True).get("flash", [""])[0]


def _seed_report(conn, name: str, pool_id: int = None) -> int:
    """插入一个最小报表配置，返回 id。"""
    conn.execute(
        "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id) "
        "VALUES (?,?,?,?)",
        (name, "SELECT 1", 20, pool_id),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _seed_endpoint(conn, report_id: int, name: str, url_path: str) -> int:
    """插入一个最小 API 端点，返回 id。"""
    conn.execute(
        "INSERT INTO api_endpoints (report_id,name,url_path,output_format) "
        "VALUES (?,?,?,?)",
        (report_id, name, url_path, "json"),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------------
# 缺口 DS-05-01 ~ DS-05-03：delete_report 级联语义对齐 batch_delete_reports
# ---------------------------------------------------------------------------


class TestDeleteReportCascade(BaseConfigTest):
    """单删报表应级联清理 API 端点并失效静态缓存（对齐批量删语义）"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) "
            "VALUES ('池','h',3306,'u','p','d')"
        )
        self.conn.commit()
        self.rid = _seed_report(self.conn, "报表A", pool_id=1)

    def test_delete_report_removes_api_endpoints(self):
        """DS-05-01：删除报表后其下 API 端点一并删除，不留孤儿"""
        _seed_endpoint(self.conn, self.rid, "端点A", "/api/a")
        ok = db.delete_report(self.conn, self.rid)
        self.assertTrue(ok)
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM api_endpoints WHERE report_id=?", (self.rid,)
        ).fetchone()[0]
        self.assertEqual(rows, 0, "孤儿 API 端点应随报表一并删除")

    def test_delete_report_invalidates_static_cache(self):
        """DS-05-02：删除报表应按端点 url_path 失效静态缓存文件"""
        _seed_endpoint(self.conn, self.rid, "端点A", "/api/a")
        _seed_endpoint(self.conn, self.rid, "端点B", "/api/b")
        with patch("static_cache.invalidate") as mock_inv:
            db.delete_report(self.conn, self.rid)
        called_paths = {c.args[0] for c in mock_inv.call_args_list}
        self.assertIn("/api/a", called_paths)
        self.assertIn("/api/b", called_paths)

    def test_delete_report_without_endpoints_ok(self):
        """DS-05-03：无端点报表删除不受影响（行为兼容）"""
        ok = db.delete_report(self.conn, self.rid)
        self.assertTrue(ok)
        self.assertIsNone(db.get_report(self.conn, self.rid))


# -+
# 缺口 DS-05-04：count_api_endpoints_by_report 聚合计数
# 【已移除】实现决策：渲染层复用既有 api_endpoints_map（见文件头注记 1）。
# -+


# ---------------------------------------------------------------------------
# 缺口 DS-05-05 ~ DS-05-06：handle_report_delete flash 两分支
# ---------------------------------------------------------------------------


class TestHandleReportDeleteFlash(BaseConfigTest):
    """单删报表 flash 回报清理明细"""

    def setUp(self):
        super().setUp()
        self.rid = _seed_report(self.conn, "报表A")

    def _post(self, rid):
        return config.handle_request(
            self.conn, "POST", f"/config/reports/{rid}/delete", "", "",
            session_user="admin")

    def test_flash_with_endpoints(self):
        """DS-05-05：有端点时报表删除 flash 披露端点数与静态缓存清理"""
        _seed_endpoint(self.conn, self.rid, "端点A", "/api/a")
        _seed_endpoint(self.conn, self.rid, "端点B", "/api/b")
        with patch("static_cache.invalidate"):
            code, body, headers = self._post(self.rid)
        self.assertEqual(code, 302)
        self.assertIn("报表 报表A 已删除（含 2 个 API 接口及其静态缓存）", _flash(body))

    def test_flash_without_endpoints_keeps_original_text(self):
        """DS-05-06：无端点时保持原文案「报表 X 已删除」不变"""
        code, body, headers = self._post(self.rid)
        self.assertEqual(code, 302)
        self.assertEqual(_flash(body), "报表 报表A 已删除")


# ---------------------------------------------------------------------------
# 缺口 DS-05-07：batch_delete_reports 行为不变回归对照
# ---------------------------------------------------------------------------


class TestBatchDeleteReportsRegression(BaseConfigTest):
    """batch_delete_reports 既有语义回归保护（本批次不得改变其行为）"""

    def setUp(self):
        super().setUp()
        self.rid = _seed_report(self.conn, "报表A")

    def test_batch_delete_unchanged_cascades_endpoints(self):
        """DS-05-07：批量删仍级联清理端点"""
        _seed_endpoint(self.conn, self.rid, "端点A", "/api/a")
        affected = db.batch_delete_reports(self.conn, [self.rid])
        self.assertEqual(affected, 1)
        rows = self.conn.execute("SELECT COUNT(*) FROM api_endpoints").fetchone()[0]
        self.assertEqual(rows, 0)
        self.assertIsNone(db.get_report(self.conn, self.rid))

    def test_batch_delete_unchanged_invalidates_static_cache(self):
        """DS-05-07：批量删仍失效静态缓存"""
        _seed_endpoint(self.conn, self.rid, "端点A", "/api/a")
        with patch("static_cache.invalidate") as mock_inv:
            db.batch_delete_reports(self.conn, [self.rid])
        mock_inv.assert_called_once_with("/api/a")


# ---------------------------------------------------------------------------
# 缺口 DS-05-08：报表列表单删 confirm 注入端点数
# ---------------------------------------------------------------------------


class TestReportRowConfirmText(unittest.TestCase):
    """build_category_section_html 报表行删除 confirm 文案（纯数据 → HTML）"""

    def _render(self, endpoints_map):
        # cat_reports 条目结构：{id, name, ..., reports: [报表行]}（render 层约定）
        cat_reports = [{"id": 1, "name": "分类", "parent_id": None,
                        "sort_order": 0,
                        "reports": [{"id": 10, "name": "报表A",
                                     "sql_query": "SELECT 1",
                                     "default_page_size": 20,
                                     "pool_id": None}]}]
        return render.build_category_section_html(
            cat_reports, [], [], [{"id": 10, "name": "报表A"}], [],
            [{"id": 1, "name": "分类", "children": []}],
            api_endpoints_map=endpoints_map)

    def test_confirm_with_endpoints(self):
        """DS-05-08：有端点行 confirm 注入「其下 N 个 API 接口将一并删除」"""
        eps = {10: [{"url_path": "/api/a"}, {"url_path": "/api/b"}]}
        html = self._render(eps)
        self.assertIn("确定删除报表 报表A？其下 2 个 API 接口将一并删除", html)

    def test_confirm_without_endpoints(self):
        """DS-05-08：无端点行保持原文案「确定删除报表 X？」"""
        html = self._render({})
        self.assertIn("确定删除报表 报表A？", html)
        self.assertNotIn("将一并删除", html)


# ---------------------------------------------------------------------------
# 缺口 DS-06-01：count_reports_by_pool 引用计数
# ---------------------------------------------------------------------------


class TestCountReportsByPool(BaseConfigTest):
    """count_reports_by_pool 连接池被报表引用计数"""

    def test_empty_db_returns_empty_dict(self):
        """无报表时返回空 dict"""
        self.assertEqual(config_db.count_reports_by_pool(self.conn), {})

    def test_group_counts_by_pool(self):
        """按 pool_id 分组计数；pool_id 为 NULL 的报表不计入"""
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) "
            "VALUES ('P1','h',3306,'u','p','d')")
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) "
            "VALUES ('P2','h',3306,'u','p','d')")
        self.conn.commit()
        _seed_report(self.conn, "R1", pool_id=1)
        _seed_report(self.conn, "R2", pool_id=1)
        _seed_report(self.conn, "R3", pool_id=2)
        _seed_report(self.conn, "R4", pool_id=None)
        result = config_db.count_reports_by_pool(self.conn)
        self.assertEqual(result, {1: 2, 2: 1})


# ---------------------------------------------------------------------------
# 缺口 DS-06-02 ~ DS-06-03：连接池 confirm 披露与渲染接线
# ---------------------------------------------------------------------------


class TestPoolSectionDisclosure(BaseConfigTest):
    """连接池列表删除 confirm 引用披露"""

    def _add_pool(self, name):
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) "
            "VALUES (?,?,?,?,?,?)", (name, 'h', 3306, 'u', 'p', 'd'))
        self.conn.commit()

    def test_confirm_zero_refs(self):
        """DS-06-02：0 引用保持原文案「确定删除连接池 X？」"""
        pools = [{"id": 1, "name": "P1", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        html = render.build_pool_section_html(pools, report_counts={})
        self.assertIn("确定删除连接池 P1？", html)
        self.assertNotIn("失去数据库连接", html)

    def test_confirm_nonzero_refs(self):
        """DS-06-02：N>0 引用披露「其下 N 个报表将失去数据库连接（报表保留但无法执行）」"""
        pools = [{"id": 1, "name": "P1", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        html = render.build_pool_section_html(pools, report_counts={1: 3})
        self.assertIn("确定删除连接池 P1？其下 3 个报表将失去数据库连接（报表保留但无法执行）", html)

    def test_backward_compatible_without_counts(self):
        """未传计数参数时保持原文案（向后兼容既有调用方）"""
        pools = [{"id": 1, "name": "P1", "host": "h", "port": 3306,
                  "user": "u", "database": "d"}]
        html = render.build_pool_section_html(pools)
        self.assertIn("确定删除连接池 P1？", html)
        self.assertNotIn("失去数据库连接", html)

    def test_render_pool_section_wires_counts(self):
        """DS-06-03：config._render_pool_section 渲染上下文注入真实引用计数"""
        self._add_pool("P1")
        _seed_report(self.conn, "R1", pool_id=1)
        _seed_report(self.conn, "R2", pool_id=1)
        html = config._render_pool_section(self.conn)
        self.assertIn("其下 2 个报表将失去数据库连接", html)


# ---------------------------------------------------------------------------
# 缺口 DS-06-04：handle_pool_delete flash 断开数量回报
# ---------------------------------------------------------------------------


class TestHandlePoolDeleteFlash(BaseConfigTest):
    """删除连接池 flash 回报断开的报表关联数"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database) "
            "VALUES ('P1','h',3306,'u','p','d')")
        self.conn.commit()
        self.pool_id = 1

    def _post(self, pid):
        return config.handle_request(
            self.conn, "POST", f"/config/pools/{pid}/delete", "", "",
            session_user="admin")

    def test_flash_with_linked_reports(self):
        """DS-06-04：有关联报表时 flash 披露断连数与后果（注记 3）"""
        _seed_report(self.conn, "R1", pool_id=self.pool_id)
        _seed_report(self.conn, "R2", pool_id=self.pool_id)
        code, body, headers = self._post(self.pool_id)
        self.assertEqual(code, 302)
        self.assertEqual(
            _flash(body),
            "连接池 P1 已删除（已断开 2 个报表的连接，报表保留但无法执行）")
        # 报表保留但断连
        self.assertIsNotNone(db.get_report(self.conn, 1))

    def test_flash_without_linked_reports(self):
        """DS-06-04：无关联报表时保持原文案「连接池 X 已删除」"""
        code, body, headers = self._post(self.pool_id)
        self.assertEqual(code, 302)
        self.assertEqual(_flash(body), "连接池 P1 已删除")


# ---------------------------------------------------------------------------
# 缺口 DS-07-01 ~ DS-07-03：remove_sessions_for_user
# ---------------------------------------------------------------------------

_SESSION_DDL = """CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created_at REAL NOT NULL
)"""


class TestRemoveSessionsForUser(unittest.TestCase):
    """auth.remove_sessions_for_user：内存 + 持久层同步注销"""

    def setUp(self):
        auth._sessions.clear()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SESSION_DDL)
        now = time.time()
        for tok, user in (("tok-a1", "alice"), ("tok-a2", "alice"),
                          ("tok-b1", "bob")):
            self.conn.execute(
                "INSERT INTO sessions (token,username,created_at) VALUES (?,?,?)",
                (tok, user, now))
            auth._sessions[tok] = (user, now)
        self.conn.commit()
        # auth 层会 close get_config_db() 返回值，共享连接须经 NoClose 包装
        self.patcher = patch("db.get_config_db",
                             return_value=_NoCloseConn(self.conn))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(auth._sessions.clear)

    def test_memory_clears_only_target_user(self):
        """DS-07-01：仅清除目标用户的内存 token，返回清除数"""
        removed = auth.remove_sessions_for_user("alice")
        self.assertEqual(removed, 2)
        self.assertNotIn("tok-a1", auth._sessions)
        self.assertNotIn("tok-a2", auth._sessions)
        self.assertIn("tok-b1", auth._sessions, "其他用户会话不应受影响")

    def test_persistent_rows_deleted(self):
        """DS-07-02：持久层 sessions 表中该用户行同步删除"""
        auth.remove_sessions_for_user("alice")
        rows = self.conn.execute(
            "SELECT token FROM sessions WHERE username='alice'").fetchall()
        self.assertEqual(rows, [])
        remain = self.conn.execute(
            "SELECT token FROM sessions WHERE username='bob'").fetchall()
        self.assertEqual(len(remain), 1, "其他用户持久层行不应受影响")

    def test_unknown_user_returns_zero(self):
        """DS-07-03：目标无任何会话时返回 0（幂等）"""
        self.assertEqual(auth.remove_sessions_for_user("nobody"), 0)


# ---------------------------------------------------------------------------
# 缺口 DS-07-04 ~ DS-07-06：handle_user_delete 自删拒绝与会话注销
# ---------------------------------------------------------------------------


class TestUserDeleteSafety(BaseConfigTest):
    """用户删除：服务端拒绝自删 + 删除后注销其全部会话"""

    def setUp(self):
        super().setUp()
        db.add_user(self.conn, "admin", auth.hash_password("pw-admin"))
        db.add_user(self.conn, "bob", auth.hash_password("pw-bob"))
        auth._sessions.clear()
        self.addCleanup(auth._sessions.clear)

    def _patch_auth_db(self):
        """把 auth 持久层指向测试内存库（sessions 表已由 init_test_db 建立）。

        auth 层会 close get_config_db() 返回值，共享连接须经 NoClose 包装。
        """
        patcher = patch("db.get_config_db", return_value=_NoCloseConn(self.conn))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reject_delete_self(self):
        """DS-07-04：session_user == 目标用户名 → 拒绝且不执行删除"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/1/delete", "", "",
            session_user="admin")
        self.assertEqual(code, 302)
        self.assertEqual(_flash(body), "错误: 不能删除当前登录账号")
        self.assertIsNotNone(db.get_user_by_id(self.conn, 1),
                             "被拒绝时用户必须仍然存在")

    def test_delete_other_kicks_sessions_and_flash(self):
        """DS-07-05：删除他人后其内存+持久层会话全部失效，flash 含注销数"""
        self._patch_auth_db()
        token = auth.create_session("bob")
        self.assertEqual(auth.get_session_user(token), "bob")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/2/delete", "", "",
            session_user="admin")
        self.assertEqual(code, 302)
        self.assertIn("用户 bob 已删除（已注销其 1 个登录会话）", _flash(body))
        self.assertIsNone(db.get_user_by_id(self.conn, 2))
        self.assertIsNone(auth.get_session_user(token), "被删用户的会话应立即失效")
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE username='bob'").fetchone()[0]
        self.assertEqual(rows, 0, "持久层会话行应同步删除")

    def test_delete_other_without_sessions_plain_flash(self):
        """DS-07-06：被删用户无会话时 flash 保持「用户 X 已删除」"""
        self._patch_auth_db()
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/2/delete", "", "",
            session_user="admin")
        self.assertEqual(code, 302)
        self.assertEqual(_flash(body), "用户 bob 已删除")


# ---------------------------------------------------------------------------
# 缺口 DS-07-07 ~ DS-07-08：handle_user_edit 改密踢会话
# ---------------------------------------------------------------------------


class TestUserEditPasswordKick(BaseConfigTest):
    """用户编辑改密后注销其全部会话"""

    def setUp(self):
        super().setUp()
        db.add_user(self.conn, "bob", auth.hash_password("old-pw"))
        auth._sessions.clear()
        self.addCleanup(auth._sessions.clear)
        patcher = patch("db.get_config_db", return_value=_NoCloseConn(self.conn))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_change_password_kicks_sessions(self):
        """DS-07-07：密码字段非空且更新成功 → 会话全注销 + flash 提示重新登录"""
        token = auth.create_session("bob")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/1/edit", "", "username=bob&password=new-pw",
            session_user="admin")
        self.assertEqual(code, 302)
        self.assertIn("用户 bob 已更新，其登录会话已全部注销，需重新登录", _flash(body))
        self.assertIsNone(auth.get_session_user(token), "改密后旧会话应失效")
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE username='bob'").fetchone()[0]
        self.assertEqual(rows, 0)
        # 新密码生效
        updated = db.get_user_by_id(self.conn, 1)
        self.assertTrue(auth.verify_password("new-pw", updated["password_hash"]))

    def test_edit_without_password_keeps_sessions(self):
        """DS-07-08【契约修订】：不改密但改名 → 仍注销会话。

        session 不回查 users 表，旧 token 会以已不存在的用户名继续通过
        认证（_authenticate 仅查 session 存在性）——故改名即注销，
        与改密同路径（批次2#7 边界补丁，见 handle_user_edit 注释）。
        """
        token = auth.create_session("bob")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/1/edit", "", "username=bobby&password=",
            session_user="admin")
        self.assertEqual(code, 302)
        self.assertIn("已改名为 bobby", _flash(body))
        self.assertIsNone(auth.get_session_user(token),
                          "改名后旧用户名的会话应失效")


# ---------------------------------------------------------------------------
# 缺口 DS-07-09 ~ DS-07-11：用户表自删按钮显隐与 confirm 文案
# ---------------------------------------------------------------------------


class TestUserSectionSelfDelete(unittest.TestCase):
    """build_user_section_html 当前登录用户行隐藏删除按钮"""

    def _users(self):
        return [{"id": 1, "username": "admin"}, {"id": 2, "username": "bob"}]

    def test_self_row_has_no_delete_button(self):
        """DS-07-09：当前登录用户行不渲染删除按钮（服务端兜底仍在）"""
        html = render.build_user_section_html(self._users(), current_username="admin")
        self.assertNotIn("/config/users/1/delete", html)
        self.assertIn('href="/config/users/1/edit"', html, "自身行仍可编辑")

    def test_other_rows_keep_delete_button(self):
        """DS-07-09：其他用户行的删除按钮保留"""
        html = render.build_user_section_html(self._users(), current_username="admin")
        self.assertIn("/config/users/2/delete", html)

    def test_backward_compatible_without_session_user(self):
        """DS-07-10：session_user 未传时所有行均渲染删除按钮（向后兼容）"""
        html = render.build_user_section_html(self._users())
        self.assertIn("/config/users/1/delete", html)
        self.assertIn("/config/users/2/delete", html)

    def test_confirm_mentions_session_invalidation(self):
        """DS-07-11：confirm 文案统一为「确定删除用户 X？其全部登录会话将立即失效」"""
        html = render.build_user_section_html(self._users(), current_username="admin")
        self.assertIn("确定删除用户 bob？其全部登录会话将立即失效", html)


if __name__ == "__main__":
    unittest.main()
