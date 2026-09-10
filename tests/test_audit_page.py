"""
test_audit_page.py — audit_page 模块（审计日志页 handler）测试

覆盖：
- handle_audit_request 渲染：正常 / 空日志 / 分页参数（缺口1）
- 审计日志自动轮转边界（rotate_audit_logs / _rotate_expired）（缺口2）
- 审计写入失败降级（record_operation / server._write_audit_log）（缺口3）
- 审计分页边界（页数越界、每页数量限制）（缺口18）
"""

import logging
import os
import sqlite3
import tempfile
import time
import unittest
import urllib.parse
from datetime import datetime, timedelta
from unittest.mock import patch

from filter_help import FILTER_HINT_SUFFIX

import audit_db
import audit_page
import server as srv
from audit_db import init_audit_db, insert_audit_log


def _make_audit_conn():
    """创建已建表的 :memory: 审计连接。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_audit_db(conn)
    return conn


def _make_audit_file_conn():
    """创建已建表的临时文件审计库连接（供会被 close 的调用方使用后重开验证）。

    调用方（record_operation / _rotate_expired）会在 finally 中关闭连接；
    用文件库可让测试在连接被关闭后重新打开同一库做断言。
    返回 (conn, db_path)；测试结束后需 os.unlink(db_path)。
    """
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="t5_audit_")
    f.close()
    conn = sqlite3.connect(f.name)
    conn.row_factory = sqlite3.Row
    init_audit_db(conn)
    return conn, f.name


_AUDIT_CFG = {"path": "/nonexistent/audit_for_test.db", "retention_days": 0}


def _patch_audit_env(conn):
    """返回处理页所需的三处 patch（audit 连接 + 两处配置入口）。"""
    return [
        patch("audit_db.get_audit_db", return_value=conn),
        patch("audit_page.get_audit_db_config", return_value=dict(_AUDIT_CFG)),
        patch("app_config.get_audit_db_config", return_value=dict(_AUDIT_CFG)),
    ]


class _AuditConnTestCase(unittest.TestCase):
    """公共 setUp：内存审计库 + audit 配置/连接 patch。"""

    def setUp(self):
        self.conn = _make_audit_conn()
        self._patches = _patch_audit_env(self.conn)
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.conn.close()

    def _insert(self, n, prefix="op"):
        """按 id 升序插入 n 条 operation 日志（action=op_0..op_{n-1}）。"""
        for i in range(n):
            insert_audit_log(
                self.conn, type="operation", session_user="admin",
                action=f"{prefix}_{i}", entity_type="pool",
                entity_name=f"实体{i}")


class TestAuditPageRender(_AuditConnTestCase):
    """缺口1：审计日志页渲染（正常 / 空日志 / 分页参数）"""

    def test_render_normal(self):
        """正常渲染：200 + HTML 含审计标题与日志行（id 降序最新在前）"""
        self._insert(3)
        code, body, headers = audit_page.handle_audit_request("GET", "")
        self.assertEqual(code, 200)
        self.assertIn("审计日志", body)
        self.assertIn("op_2", body)   # 最新在前
        self.assertIn("实体2", body)
        self.assertIn("操作", body)

    def test_render_empty_log(self):
        """空日志：200 + 空态提示，不抛异常"""
        code, body, _ = audit_page.handle_audit_request("GET", "")
        self.assertEqual(code, 200)
        self.assertIn("暂无匹配的审计日志", body)

    def test_render_pagination_params(self):
        """分页参数 page/page_size 生效：id 降序，第 2 页为 op_2、op_1（第 3、4 新）"""
        self._insert(5)
        code, body, _ = audit_page.handle_audit_request("GET", "page=2&page_size=2")
        self.assertEqual(code, 200)
        self.assertIn("op_2", body)
        self.assertIn("op_1", body)
        self.assertNotIn("op_4", body)
        self.assertNotIn("op_3", body)

    def test_render_with_filter_type(self):
        """type 筛选：仅渲染匹配类型的日志"""
        insert_audit_log(self.conn, type="web_access", session_user="admin",
                         action="page_view", entity_name="/config",
                         http_method="GET", http_path="/config", http_status=200)
        self._insert(2)
        code, body, _ = audit_page.handle_audit_request("GET", "type=web_access")
        self.assertEqual(code, 200)
        self.assertIn("page_view", body)
        self.assertNotIn("op_0", body)

    def test_render_flash_message(self):
        """flash 参数：渲染提示消息"""
        code, body, _ = audit_page.handle_audit_request(
            "GET", "flash=%E6%B8%85%E7%90%86%E6%88%90%E5%8A%9F")
        self.assertEqual(code, 200)
        self.assertIn("清理成功", body)

    def test_render_filter_help_entry(self):
        """筛选表单旁含 ? 帮助入口（默认收起，单一来源渲染）"""
        code, body, _ = audit_page.handle_audit_request("GET", "")
        self.assertEqual(code, 200)
        self.assertIn("filter-help-btn", body)
        self.assertIn("filter-help-popup", body)
        self.assertIn("display:none", body)
        self.assertIn("toggleFilterHelp", body)

    def test_render_keyword_placeholder_hint(self):
        """关键字输入框 placeholder 带统一语法提示（引用单一来源常量）"""
        code, body, _ = audit_page.handle_audit_request("GET", "")
        self.assertEqual(code, 200)
        self.assertIn(f'placeholder="关键字{FILTER_HINT_SUFFIX}"', body)

    def test_post_clean_redirects(self):
        """POST clean：302 重定向回审计页并带结果消息（Location 为 URL 编码）"""
        conn, path = _make_audit_file_conn()
        try:
            for i in range(2):
                insert_audit_log(conn, type="operation", session_user="admin",
                                 action=f"op_{i}", entity_type="pool")
            with patch("audit_db.get_audit_db", return_value=conn):
                code, body, _ = audit_page.handle_audit_request(
                    "POST", "", "action=clean")
            # _handle_clean 已关闭 conn；重开同一文件库验证删除
            check = sqlite3.connect(path)
            check.row_factory = sqlite3.Row
            try:
                self.assertEqual(audit_db.count_audit_logs(check, {}), 0)
            finally:
                check.close()
            self.assertEqual(code, 302)
            self.assertIn("/audit?", body)
            self.assertIn("清理成功", urllib.parse.unquote(body))
        finally:
            os.unlink(path)

    def test_export_csv(self):
        """export=csv：200 + CSV 字节 + 下载头"""
        self._insert(1)
        code, body, headers = audit_page.handle_audit_request("GET", "export=csv")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, bytes)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))  # utf-8-sig BOM
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertIn("op_0", body.decode("utf-8-sig"))


class TestAuditRotation(_AuditConnTestCase):
    """缺口2：审计日志自动轮转边界（阈值触发/不触发）"""

    def _insert_old(self, days_ago=30):
        ts = (datetime.now() - timedelta(days=days_ago)).isoformat()
        insert_audit_log(self.conn, type="operation", session_user="admin",
                         action="old", entity_type="pool", timestamp=ts)

    def test_rotate_disabled_returns_zero(self):
        """retention_days<=0 → 不清理（0 与负数均不触发）"""
        self._insert(3)
        self.assertEqual(audit_db.rotate_audit_logs(self.conn, 0), 0)
        self.assertEqual(audit_db.rotate_audit_logs(self.conn, -7), 0)
        self.assertEqual(audit_db.count_audit_logs(self.conn, {}), 3)

    def test_rotate_removes_only_expired(self):
        """超过保留天数的删除，保留期内保留"""
        self._insert_old(days_ago=30)
        self._insert(2)   # 今天
        deleted = audit_db.rotate_audit_logs(self.conn, 7)
        self.assertEqual(deleted, 1)
        self.assertEqual(audit_db.count_audit_logs(self.conn, {}), 2)

    def test_rotate_threshold_boundary(self):
        """边界：恰好 cutoff 之前 1 秒删除、之后 1 秒保留（严格小于）"""
        cutoff = datetime.fromtimestamp(time.time() - 7 * 86400)
        insert_audit_log(self.conn, type="operation", session_user="admin",
                         action="before", timestamp=(cutoff - timedelta(seconds=1)).isoformat())
        insert_audit_log(self.conn, type="operation", session_user="admin",
                         action="after", timestamp=(cutoff + timedelta(seconds=1)).isoformat())
        deleted = audit_db.rotate_audit_logs(self.conn, 7)
        self.assertEqual(deleted, 1)
        remain = audit_db.query_audit_logs(self.conn, {})
        self.assertEqual([r["action"] for r in remain], ["after"])

    def test_rotate_expired_skips_when_disabled(self):
        """_rotate_expired 在 retention_days<=0 时不触碰数据库"""
        with patch("audit_page.get_audit_db_config",
                   return_value={"path": "x", "retention_days": 0}), \
                patch("audit_db.get_audit_db") as m:
            audit_page._rotate_expired()
            m.assert_not_called()

    def test_rotate_expired_deletes_and_logs(self):
        """_rotate_expired 启用时删除过期记录并记录 info 日志"""
        conn, path = _make_audit_file_conn()
        try:
            ts = (datetime.now() - timedelta(days=30)).isoformat()
            insert_audit_log(conn, type="operation", session_user="admin",
                             action="old", entity_type="pool", timestamp=ts)
            with patch("audit_page.get_audit_db_config",
                       return_value={"path": path, "retention_days": 7}), \
                    patch("audit_db.get_audit_db", return_value=conn), \
                    self.assertLogs(level=logging.INFO) as cm:
                audit_page._rotate_expired()
            # _rotate_expired 会在 finally 中关闭 conn；重开同一文件库验证删除
            check = sqlite3.connect(path)
            check.row_factory = sqlite3.Row
            try:
                self.assertEqual(audit_db.count_audit_logs(check, {}), 0)
            finally:
                check.close()
            self.assertTrue(any("审计日志自动清理" in m for m in cm.output))
        finally:
            os.unlink(path)

    def test_rotate_expired_db_error_degrades(self):
        """_rotate_expired 数据库异常仅告警，不抛出"""
        with patch("audit_page.get_audit_db_config",
                   return_value={"path": "x", "retention_days": 7}), \
                patch("audit_db.get_audit_db", side_effect=Exception("db 打不开")), \
                self.assertLogs(level=logging.WARNING) as cm:
            audit_page._rotate_expired()   # 不抛
        self.assertTrue(any("轮转失败" in m for m in cm.output))


class TestAuditWriteDegradation(unittest.TestCase):
    """缺口3：审计写入失败降级（DB 错误时应用仍正常响应）"""

    def test_record_operation_skips_empty_user(self):
        """session_user 为空 → 跳过写入，不连数据库"""
        with patch("audit_db.get_audit_db") as m:
            audit_db.record_operation("", "login", "user")
            m.assert_not_called()

    def test_record_operation_db_connect_error_degrades(self):
        """审计库连接失败 → warning 告警，不抛异常"""
        with patch("audit_db.get_audit_db", side_effect=Exception("连接失败")), \
                self.assertLogs(level=logging.WARNING) as cm:
            audit_db.record_operation("admin", "login", "user")   # 不抛
        self.assertTrue(any("审计日志写入失败" in m for m in cm.output))

    def test_record_operation_insert_error_degrades(self):
        """审计表不可用（无表）→ warning 告警，不抛异常"""
        bare = sqlite3.connect(":memory:")
        try:
            with patch("audit_db.get_audit_db", return_value=bare), \
                    self.assertLogs(level=logging.WARNING) as cm:
                audit_db.record_operation("admin", "login", "user")   # 不抛
            self.assertTrue(any("审计日志写入失败" in m for m in cm.output))
        finally:
            bare.close()

    def test_record_operation_success(self):
        """正常路径：写入一条 operation 日志"""
        conn, path = _make_audit_file_conn()
        try:
            with patch("audit_db.get_audit_db", return_value=conn):
                audit_db.record_operation("admin", "login", "user", entity_name="admin")
            # record_operation 会在 finally 中关闭 conn；重开同一文件库验证
            check = sqlite3.connect(path)
            check.row_factory = sqlite3.Row
            try:
                rows = check.execute("SELECT * FROM audit_logs").fetchall()
            finally:
                check.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action"], "login")
        finally:
            os.unlink(path)

    def test_record_operation_log_type_scheduler(self):
        """log_type=scheduler：写入定时任务类型审计日志（B19/B20）。"""
        conn, path = _make_audit_file_conn()
        try:
            with patch("audit_db.get_audit_db", return_value=conn):
                audit_db.record_operation(
                    "system", "scheduled_run", "schedule",
                    entity_id=1, entity_name="report#1",
                    after_value={"trigger": "scheduler", "status": "success",
                                 "duration_ms": 10, "error": None},
                    log_type="scheduler")
            check = sqlite3.connect(path)
            check.row_factory = sqlite3.Row
            try:
                rows = check.execute("SELECT * FROM audit_logs").fetchall()
            finally:
                check.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["type"], "scheduler")
            self.assertEqual(rows[0]["action"], "scheduled_run")
            self.assertEqual(rows[0]["entity_type"], "schedule")
        finally:
            os.unlink(path)

    def test_server_write_audit_log_silent_on_db_error(self):
        """server._write_audit_log：审计 DB 异常静默吞掉，不抛"""
        handler = srv.ReportHandler.__new__(srv.ReportHandler)
        with patch("audit_db.get_audit_db", side_effect=Exception("磁盘满")):
            handler._write_audit_log(
                log_type="web_access", session_user="admin", action="page_view",
                entity_type="page", entity_name="/x", http_method="GET",
                http_path="/x", http_status=200, duration_ms=0,
                ip_address="1.2.3.4", request_body=None)   # 不抛

    def test_server_write_audit_log_insert_error_silent(self):
        """server._write_audit_log：插入异常静默吞掉（业务响应不受影响）"""
        bare = sqlite3.connect(":memory:")
        try:
            handler = srv.ReportHandler.__new__(srv.ReportHandler)
            with patch("audit_db.get_audit_db", return_value=bare):
                handler._write_audit_log(
                    log_type="api", session_user="api_key:x", action="api_call",
                    entity_type="api_endpoint", entity_name="/api/x",
                    http_method="GET", http_path="/api/x", http_status=200,
                    duration_ms=1, ip_address="127.0.0.1", request_body="")   # 不抛
        finally:
            bare.close()


class TestAuditPageSchedulerType(_AuditConnTestCase):
    """定时任务独立审计类型：筛选下拉、type=scheduler 筛选、详情渲染。"""

    def _insert_scheduler(self, action="scheduled_run", status="success",
                          trigger="scheduler", duration_ms=42, error=None,
                          policy=None, missed_at=None, resumed_at=None):
        av = {"trigger": trigger, "status": status,
              "duration_ms": duration_ms}
        if error:
            av["error"] = error
        if policy:
            av["policy"] = policy
        if missed_at is not None:
            av["missed_at"] = missed_at
        if resumed_at is not None:
            av["resumed_at"] = resumed_at
        insert_audit_log(
            self.conn, type="scheduler", session_user="system",
            action=action, entity_type="schedule", entity_id=1,
            entity_name="report#1", after_value=av)

    def test_type_filter_option_present(self):
        """筛选下拉含"定时任务"选项。"""
        _, body, _ = audit_page.handle_audit_request("GET", "")
        self.assertIn('<option value="scheduler">定时任务</option>', body)

    def test_filter_type_scheduler_shows_only_scheduler(self):
        """type=scheduler：仅渲染定时任务日志，不显示 operation/api。"""
        self._insert(2)                                   # operation 日志
        self._insert_scheduler(status="success")          # scheduler 日志
        insert_audit_log(self.conn, type="api", session_user="api_key:x",
                         action="api_call", entity_name="/api/a",
                         http_path="/api/a", http_status=200)
        code, body, _ = audit_page.handle_audit_request(
            "GET", "type=scheduler")
        self.assertEqual(code, 200)
        self.assertIn("scheduled_run", body)
        self.assertIn("report#1", body)
        self.assertIn("定时", body)          # 类型徽标
        self.assertNotIn("op_1", body)
        self.assertNotIn("api_call", body)

    def test_scheduler_detail_shows_trigger_status_duration(self):
        """详情列：触发=定时、结果=成功、耗时=42ms。"""
        self._insert_scheduler()
        _, body, _ = audit_page.handle_audit_request("GET", "type=scheduler")
        self.assertIn("触发: 定时", body)
        self.assertIn("结果: 成功", body)
        self.assertIn("耗时: 42ms", body)

    def test_scheduler_detail_failure_with_error(self):
        """失败记录：结果=失败 + 错误信息展示。"""
        self._insert_scheduler(status="fail", error="MySQL down",
                               duration_ms=88)
        _, body, _ = audit_page.handle_audit_request("GET", "type=scheduler")
        self.assertIn("结果: 失败", body)
        self.assertIn("MySQL down", body)

    def test_scheduler_detail_manual_trigger_label(self):
        """手动触发 trigger=manual → 详情显示"触发: 手动"。"""
        self._insert_scheduler(trigger="manual")
        _, body, _ = audit_page.handle_audit_request("GET", "type=scheduler")
        self.assertIn("触发: 手动", body)

    def test_scheduler_misfire_skip_detail(self):
        """misfire skip：详情含"跳过（推进到下次计划）"。"""
        self._insert_scheduler(action="scheduled_misfire", policy="skip",
                               missed_at=1000.0, resumed_at=2000.0)
        _, body, _ = audit_page.handle_audit_request("GET", "type=scheduler")
        self.assertIn("跳过（推进到下次计划）", body)


class TestAuditPagePaginationBounds(_AuditConnTestCase):
    """缺口18：审计分页边界（页数越界、每页数量限制）"""

    def test_page_beyond_range_returns_empty(self):
        """页数越界（999）→ 200 + 空态，不抛异常"""
        self._insert(3)
        code, body, _ = audit_page.handle_audit_request("GET", "page=999")
        self.assertEqual(code, 200)
        self.assertIn("暂无匹配的审计日志", body)

    def test_page_zero_returns_first_page(self):
        """page=0 → SQLite 负 OFFSET 按 0 处理 → 等价第 1 页（真实行为）"""
        self._insert(3)
        code, body, _ = audit_page.handle_audit_request("GET", "page=0")
        self.assertEqual(code, 200)
        self.assertIn("op_2", body)

    def test_page_non_numeric_falls_back_to_default(self):
        """page=abc → safe_int 回退默认 1"""
        self._insert(3)
        code, body, _ = audit_page.handle_audit_request("GET", "page=abc")
        self.assertEqual(code, 200)
        self.assertIn("op_2", body)

    def test_page_size_zero_clamped_to_one(self):
        """page_size=0 → 钳制为 1 正常渲染，不再除零崩溃（修复：与 report.py 一致）"""
        self._insert(3)
        code, body, _ = audit_page.handle_audit_request("GET", "page_size=0")
        self.assertEqual(code, 200)
        self.assertIn("op_2", body)
        self.assertIn("第 1/3 页", body)

    def test_page_size_huge_returns_all_rows(self):
        """每页数量无上限限制：超大 page_size 返回全部（行为记录）"""
        self._insert(3)
        code, body, _ = audit_page.handle_audit_request("GET", "page_size=100000")
        self.assertEqual(code, 200)
        self.assertIn("op_0", body)
        self.assertIn("op_2", body)

    def test_export_csv_filter_combined(self):
        """筛选 + 导出组合：仅导出匹配行"""
        insert_audit_log(self.conn, type="api", session_user="api_key:x",
                         action="api_call", entity_name="/api/a",
                         http_path="/api/a", http_status=200)
        self._insert(1)
        code, body, _ = audit_page.handle_audit_request("GET", "type=api&export=csv")
        self.assertEqual(code, 200)
        text = body.decode("utf-8-sig")
        self.assertIn("api_call", text)
        self.assertNotIn("op_0", text)


if __name__ == "__main__":
    unittest.main()
