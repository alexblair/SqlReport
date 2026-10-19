"""test_error_guide.py — 执行失败「错误引导」契约（spec 2026-10-19 确认稿 v2）

用户原话（2026-10-19）：「所有执行失败都出现按钮，文案上加入引导……你要时刻理解
『用户是不懂你的程序的，你需要给他最精准的解决方案，引导他解决问题，而不是仅仅
抛出错误。』」

覆盖：
- `_ERROR_GUIDES` 字典结构（每条都有 title/cause/fix；数字键与 `_DB_ERRNO_HINTS` 对齐）
- `error_guide` 选择优先级（显式 guide_key > PermissionError > 错误码 > unknown）
- `render_sql_error_section` 三段式版式 + 【编辑】入口（有报表才出现、新窗口打开）
- 转义（原始错误里的 HTML 不得生效）
- 页面级：写操作拦截、连接池缺失两条真实出口都带编辑入口
"""
import unittest
from unittest.mock import patch

import db
import report
from report import (
    WRITE_DENIED_MESSAGE,
    _DB_ERRNO_HINTS,
    _ERROR_GUIDES,
    error_guide,
    render_sql_error_section,
)
from tests import BaseConfigTest
from tests import BaseConfigTest, htmlcheck

class TestErrorGuideDict(unittest.TestCase):
    """字典是唯一文案来源，结构必须完整（新增错误类型只加词条）。"""

    def test_every_entry_has_three_parts(self):
        for key, guide in _ERROR_GUIDES.items():
            with self.subTest(key=key):
                self.assertTrue(guide.get("title"), f"{key} 缺 title")
                self.assertTrue(guide.get("cause"), f"{key} 缺 cause")
                self.assertTrue(guide.get("fix"), f"{key} 缺 fix")

    def test_errno_keys_align_with_hints_table(self):
        """数字词条必须都能在 _DB_ERRNO_HINTS 里找到主文案，防两处文案各写一份。"""
        for key in _ERROR_GUIDES:
            if not key.isdigit():
                continue
            with self.subTest(key=key):
                self.assertIn(int(key), _DB_ERRNO_HINTS,
                              f"词条 {key} 在 _DB_ERRNO_HINTS 里没有对应人话")

    def test_write_denied_message_not_duplicated(self):
        """写拦截词条直接引用常量，改文案不会两处不一致。"""
        self.assertEqual(_ERROR_GUIDES["write_denied"]["message"],
                         WRITE_DENIED_MESSAGE)
        self.assertNotIn("请到编辑页开启", WRITE_DENIED_MESSAGE,
                         "短版文案已去掉冗余尾巴（按钮就在旁边）")


class TestErrorGuideSelection(unittest.TestCase):
    """错误 → 词条的选择优先级。"""

    def test_permission_error_maps_to_write_denied(self):
        e = PermissionError(WRITE_DENIED_MESSAGE)
        guide = error_guide(WRITE_DENIED_MESSAGE, WRITE_DENIED_MESSAGE, e)
        self.assertEqual(guide["key"], "write_denied")
        self.assertIn("允许执行写操作", guide["message"])
        self.assertIn("勾选", guide["fix"])

    def test_errno_selects_numeric_entry(self):
        guide = error_guide("人话", "1146 (42S02): Table 'x' doesn't exist")
        self.assertEqual(guide["key"], "1146")
        # 主文案统一来自 _DB_ERRNO_HINTS，不由词条自带
        self.assertEqual(guide["message"], _DB_ERRNO_HINTS[1146])

    def test_unknown_falls_back_to_friendly(self):
        guide = error_guide("奇怪的失败", "奇怪的失败")
        self.assertEqual(guide["key"], "unknown")
        self.assertEqual(guide["message"], "奇怪的失败")

    def test_explicit_guide_key_wins(self):
        guide = error_guide("x", "y", guide_key="pool_missing")
        self.assertEqual(guide["key"], "pool_missing")
        self.assertTrue(guide["title"])

    def test_none_error_is_safe(self):
        """没有异常对象（纯字符串路径）不得抛错。"""
        guide = error_guide("人话", "1064 (42000) syntax")
        self.assertEqual(guide["key"], "1064")


class TestRenderSqlErrorSection(unittest.TestCase):
    """版式与【编辑】入口契约。"""

    def test_three_part_layout(self):
        html = render_sql_error_section("人话", "原始错误")
        self.assertIn("查询执行失败", html)
        self.assertIn("可能原因", html)
        self.assertIn("如何解决", html)
        self.assertIn("查看原始错误信息", html)

    def test_edit_entry_present_when_report_known(self):
        html = render_sql_error_section("人话", "原始错误", report_id=17)
        self.assertIn("/config/reports/17/edit", html)
        self.assertIn("编辑报表", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener"', html)
        # 文案内入口与按钮各自一个链接
        self.assertEqual(html.count('href="/config/reports/17/edit"'), 2)
        self.assertIn("【编辑】", html)

    def test_no_edit_entry_without_report(self):
        """预览（report_id=0）没有可编辑的报表，不造假入口。"""
        html = render_sql_error_section("人话", "原始错误")
        self.assertNotIn("/config/reports/", html)
        self.assertNotIn("编辑报表", html)

    def test_report_id_tolerates_garbage(self):
        html = render_sql_error_section("人话", "原始错误", report_id="abc")
        self.assertNotIn("/config/reports/abc", html)

    def test_html_in_raw_is_escaped(self):
        html = render_sql_error_section("人话", "<script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_tag_balance(self):
        for rid in (0, 17):
            with self.subTest(report_id=rid):
                html = render_sql_error_section("人话", "原始错误", report_id=rid)
                self.assertEqual([], htmlcheck.check_tag_balance(html))


class TestPageLevelEditEntry(BaseConfigTest):
    """真实出口：写拦截与连接池缺失都必须给到编辑页入口。"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "127.0.0.1", 3306, "u", "p", "d", 1))
        self.conn.commit()

    def test_write_blocked_page_links_to_edit(self):
        rid = db.add_report(self.conn, "写报表", "UPDATE t SET a=1", 20, 1,
                            allow_write=0)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", f"id={rid}")
        self.assertEqual(code, 200)
        self.assertIn(WRITE_DENIED_MESSAGE, body)
        self.assertIn(f"/config/reports/{rid}/edit", body)
        self.assertIn("可能原因", body)
        self.assertIn("如何解决", body)

    def test_pool_missing_page_links_to_edit(self):
        rid = db.add_report(self.conn, "无池报表", "SELECT 1", 20, 1,
                            allow_write=0)
        # 连接池被删而报表仍指向它：临时关外键造出这个历史脏数据
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("UPDATE report_configs SET pool_id=999 WHERE id=?", (rid,))
        self.conn.commit()
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", f"id={rid}")
        self.assertEqual(code, 200)
        self.assertIn("连接池", body)
        self.assertIn(f"/config/reports/{rid}/edit", body)
        self.assertIn("编辑报表", body)

    @patch("report.execute_report")
    def test_preview_with_id_links_to_edit(self, mock_exec):
        """编辑页预览（有 id）同样能一键回到编辑页。"""
        mock_exec.return_value = None
        mock_exec.side_effect = Exception("1064 (42000): You have an error")
        rid = db.add_report(self.conn, "预览报表", "SELECT 1", 20, 1,
                            allow_write=0)
        code, body, _ = report.handle_request(
            self.conn, "POST", "/report/preview", "",
            f"id={rid}&sql_query=SELECT+1")
        self.assertEqual(code, 200)
        self.assertIn("语法", body)
        self.assertIn(f"/config/reports/{rid}/edit", body)


if __name__ == "__main__":
    unittest.main()
