"""
test_config_extra.py — 配置管理域测试补充批次 T2

覆盖缺口：
1. 批量操作三个 handler（batch-pool / batch-set-category / batch-cache，含行为分支；
   批量删除报表 handler（batch-delete，含级联删除端点/静态缓存失效/审计））
2. 分类 CRUD handler（新增/编辑/删除，含非法值、重名、删除含报表的分类）
3. 排序 config 层（report/分类/连接池 move-up/move-down，SQLite 侧见 test_db.py）
4. 连接池复制 POST（含复制不存在的池）
5. 报表移动分类（含移到不存在的分类、缺分类参数）
6. 表单非法值（int() 转换 ValueError 返回错误响应而非 500）
7. rule_json 非法 JSON 被拒绝
9. return_to 外部跳转防护（open redirect 防护）
10. 报表内嵌 API 端点删除路由（POST /config/reports/{rid}/api_endpoints/{eid}/delete）
12. 分类树构建（get_category_tree）与祖先链
13. 批量操作 JS 交互逻辑（按实现断言渲染出的 JS/HTML）
14. 保存失败表单回显（修复后：失败分支回显用户已填值）
15. 用户编辑/删除失败边界
16. 报表复制 save_close 行为、编辑不存在的报表
17. 批量清理缓存与 Redis 联动（Redis 存在时清理行为）

策略与 tests/test_config.py 一致：:memory: SQLite（BaseConfigTest），
@patch 强制 SQLite，Redis/静态缓存联动通过 mock 隔离。

302 重定向的 body 为 URL 编码后的 Location，断言 flash 内容统一经
_flash() 解码后再匹配（保持与产品实现一致的断言方式）。
"""

import unittest
import sqlite3
import urllib.parse
from unittest.mock import patch, MagicMock

import config
import db
import auth
from tests.test_base import BaseConfigTest


def _flash(body: str) -> str:
    """从重定向 Location 中提取解码后的 flash 消息。

    直接调用 handler（不经过 handle_request）时返回的 Location 未编码，
    同样适用：parse_qs 对未编码中文与 %xx 编码都能正确还原。
    """
    if "?" not in body:
        return ""
    qs = body.split("?", 1)[1]
    return urllib.parse.parse_qs(qs, keep_blank_values=True).get("flash", [""])[0]


# ---------------------------------------------------------------------------
# 缺口 1：批量操作三个 handler
# ---------------------------------------------------------------------------


class TestBatchSetCategoryHandler(BaseConfigTest):
    """批量设置分类 handler（handle_batch_set_category）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类A")
        db.add_category(self.conn, "分类B")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1)
        db.add_report(self.conn, "报表2", "SELECT 1", 20, 1)
        db.add_report(self.conn, "报表3", "SELECT 1", 20, 1)

    def _post(self, form_body):
        return config.handle_request(self.conn, "POST",
                                     "/config/reports/batch-set-category",
                                     "", form_body)

    def test_move_reports_to_category(self):
        """选中报表应全部移动到目标分类，flash 含分类名"""
        code, body, headers = self._post("report_ids=1&report_ids=2&category_id=2")
        self.assertEqual(code, 302)
        self.assertIn("已为 2 个报表设置分类", _flash(body))
        self.assertIn("分类B", _flash(body))
        self.assertEqual(db.get_report(self.conn, 1)["category_id"], 2)
        self.assertEqual(db.get_report(self.conn, 2)["category_id"], 2)
        self.assertIsNone(db.get_report(self.conn, 3)["category_id"])

    def test_no_selection_returns_error(self):
        """未选择任何报表应返回错误 flash"""
        code, body, headers = self._post("category_id=2")
        self.assertEqual(code, 302)
        self.assertIn("错误: 未选择任何报表", _flash(body))

    def test_empty_category_moves_to_unclassified(self):
        """category_id 为空表示移出分类（未分类）"""
        db.move_report_to_category(self.conn, 1, 2)
        code, body, headers = self._post("report_ids=1&category_id=")
        self.assertEqual(code, 302)
        self.assertIn("未分类", _flash(body))
        self.assertIsNone(db.get_report(self.conn, 1)["category_id"])

    def test_missing_category_flash_is_unclassified(self):
        """目标分类为空时 flash 显示未分类，数据库写入正常"""
        code, body, headers = self._post("report_ids=1")
        self.assertEqual(code, 302)
        self.assertIn("未分类", _flash(body))
        self.assertIsNone(db.get_report(self.conn, 1)["category_id"])

    def test_invalid_report_ids_return_error(self):
        """report_ids 含非数字值应返回错误 flash 而非 500"""
        code, body, headers = self._post("report_ids=abc&category_id=1")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_missing_target_category_returns_error(self):
        """批量设置到不存在的分类应返回错误 flash 而非 500"""
        code, body, headers = self._post("report_ids=1&category_id=999")
        self.assertEqual(code, 302)
        self.assertIn("目标分类不存在", _flash(body))


class TestBatchPoolHandler(BaseConfigTest):
    """批量修改连接池 handler（handle_batch_pool）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池1", "h1", 3306, "u", "p", "d")
        db.add_pool(self.conn, "池2", "h2", 3306, "u", "p", "d")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1)
        db.add_report(self.conn, "报表2", "SELECT 1", 20, 1)

    def _post(self, form_body):
        return config.handle_request(self.conn, "POST",
                                     "/config/reports/batch-pool", "", form_body)

    def test_update_pool_of_selected_reports(self):
        """选中报表连接池应批量更新，flash 含影响行数与目标池 id"""
        code, body, headers = self._post("report_ids=1&report_ids=2&pool_id=2")
        self.assertEqual(code, 302)
        self.assertIn("已更新 2 个报表", _flash(body))
        self.assertIn("(id=2)", _flash(body))
        self.assertEqual(db.get_report(self.conn, 1)["pool_id"], 2)
        self.assertEqual(db.get_report(self.conn, 2)["pool_id"], 2)

    def test_no_selection_returns_error(self):
        """未选择任何报表应返回错误 flash"""
        code, body, headers = self._post("pool_id=2")
        self.assertEqual(code, 302)
        self.assertIn("错误: 未选择报表", _flash(body))

    def test_empty_pool_id_clears_pool(self):
        """pool_id 为空表示清除连接池关联"""
        code, body, headers = self._post("report_ids=1&pool_id=")
        self.assertEqual(code, 302)
        self.assertIsNone(db.get_report(self.conn, 1)["pool_id"])

    def test_missing_target_pool_returns_error(self):
        """批量改到不存在的连接池应返回错误 flash 而非 500"""
        code, body, headers = self._post("report_ids=1&pool_id=999")
        self.assertEqual(code, 302)
        self.assertIn("目标连接池不存在", _flash(body))


class TestBatchCacheHandler(BaseConfigTest):
    """批量更新缓存配置 handler（handle_batch_cache）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1,
                      prefer_cache=1, cache_ttl_hours=0)
        db.add_report(self.conn, "报表2", "SELECT 1", 20, 1,
                      prefer_cache=0, cache_ttl_hours=3)
        # 隔离 Redis 与静态缓存联动，避免依赖环境
        self.mgr_patcher = patch("redis_cache.get_redis_manager",
                                 return_value=None)
        self.mgr_patcher.start()
        self.static_patcher = patch(
            "config_db.invalidate_api_static_cache_by_report")
        self.static_patcher.start()
        self.addCleanup(self.mgr_patcher.stop)
        self.addCleanup(self.static_patcher.stop)

    def _post(self, form_body):
        return config.handle_request(self.conn, "POST",
                                     "/config/reports/batch-cache", "", form_body)

    def test_enable_cache_switch_on(self):
        """cache_switch=1 应开启所有选中报表的缓存"""
        code, body, headers = self._post("report_ids=1&report_ids=2&cache_switch=1")
        self.assertEqual(code, 302)
        self.assertIn("已更新 2 个报表的缓存配置", _flash(body))
        self.assertEqual(db.get_report(self.conn, 1)["prefer_cache"], 1)
        self.assertEqual(db.get_report(self.conn, 2)["prefer_cache"], 1)
        # TTL 未勾选修改时保持原值
        self.assertEqual(db.get_report(self.conn, 2)["cache_ttl_hours"], 3)

    def test_disable_cache_switch_off(self):
        """cache_switch=0 应关闭所有选中报表的缓存"""
        code, body, headers = self._post("report_ids=1&report_ids=2&cache_switch=0")
        self.assertEqual(code, 302)
        self.assertEqual(db.get_report(self.conn, 1)["prefer_cache"], 0)
        self.assertEqual(db.get_report(self.conn, 2)["prefer_cache"], 0)

    def test_modify_ttl_only(self):
        """仅勾选修改 TTL 时应只更新 TTL，不改变缓存开关"""
        code, body, headers = self._post(
            "report_ids=1&modify_ttl=1&cache_ttl_hours=7")
        self.assertEqual(code, 302)
        rpt = db.get_report(self.conn, 1)
        self.assertEqual(rpt["cache_ttl_hours"], 7)
        self.assertEqual(rpt["prefer_cache"], 1)  # 开关保留

    def test_switch_off_and_modify_ttl_together(self):
        """关闭缓存 + 修改 TTL 同时生效"""
        code, body, headers = self._post(
            "report_ids=1&cache_switch=0&modify_ttl=1&cache_ttl_hours=9")
        self.assertEqual(code, 302)
        rpt = db.get_report(self.conn, 1)
        self.assertEqual(rpt["prefer_cache"], 0)
        self.assertEqual(rpt["cache_ttl_hours"], 9)

    def test_no_selection_returns_error(self):
        """未选择任何报表应返回错误 flash"""
        code, body, headers = self._post("cache_switch=1")
        self.assertEqual(code, 302)
        self.assertIn("错误: 未选择报表", _flash(body))

    def test_switch_and_ttl_both_empty(self):
        """开关与 TTL 均未指定时无字段更新，返回 0 个报表提示"""
        code, body, headers = self._post("report_ids=1")
        self.assertEqual(code, 302)
        self.assertIn("已更新 0 个报表的缓存配置", _flash(body))

    def test_invalid_ttl_returns_error(self):
        """cache_ttl_hours 非数字应返回错误 flash 而非 500"""
        code, body, headers = self._post("report_ids=1&modify_ttl=1&cache_ttl_hours=abc")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))
        self.assertIn("TTL", _flash(body))


class TestBatchDeleteHandler(BaseConfigTest):
    """批量删除报表 handler（handle_batch_delete）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1)
        db.add_report(self.conn, "报表2", "SELECT 1", 20, 1)

    def _post(self, form_body, session_user=None):
        return config.handle_request(self.conn, "POST",
                                     "/config/reports/batch-delete", "",
                                     form_body, session_user=session_user)

    def test_delete_selected_reports(self):
        """选中报表应全部删除，flash 含删除数量"""
        code, body, headers = self._post("report_ids=1&report_ids=2")
        self.assertEqual(code, 302)
        self.assertIn("已删除 2 个报表", _flash(body))
        self.assertIsNone(db.get_report(self.conn, 1))
        self.assertIsNone(db.get_report(self.conn, 2))

    def test_no_selection_returns_error(self):
        """未选择任何报表应返回错误 flash"""
        code, body, headers = self._post("")
        self.assertEqual(code, 302)
        self.assertIn("错误: 未选择报表", _flash(body))

    def test_invalid_report_ids_return_error(self):
        """report_ids 含非数字值应返回错误 flash 而非 500"""
        code, body, headers = self._post("report_ids=abc")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_nonexistent_report_is_noop(self):
        """不存在的报表 id 不报错，仅统计实际删除数"""
        code, body, headers = self._post("report_ids=1&report_ids=999")
        self.assertEqual(code, 302)
        self.assertIn("已删除 1 个报表", _flash(body))
        self.assertIsNone(db.get_report(self.conn, 1))

    def test_cascades_delete_api_endpoints(self):
        """删除报表应级联删除其 API 端点"""
        db.add_api_endpoint(self.conn, 1, "端点A", "/api/a")
        db.add_api_endpoint(self.conn, 2, "端点B", "/api/b")
        code, body, headers = self._post("report_ids=1")
        self.assertEqual(code, 302)
        self.assertIsNone(db.get_api_endpoint_by_path(self.conn, "/api/a"))
        self.assertIsNotNone(db.get_api_endpoint_by_path(self.conn, "/api/b"))

    def test_static_cache_invalidated(self):
        """删除报表应失效其端点静态缓存文件"""
        db.add_api_endpoint(self.conn, 1, "端点A", "/api/a")
        with patch("static_cache.invalidate") as mock_inv:
            code, body, headers = self._post("report_ids=1")
        self.assertEqual(code, 302)
        mock_inv.assert_called_once_with("/api/a")

    def test_writes_audit_log(self):
        """删除报表应逐条写入审计日志"""
        with patch("audit_db.record_operation") as mock_audit:
            code, body, headers = self._post("report_ids=1&report_ids=2",
                                             session_user="admin")
        self.assertEqual(code, 302)
        self.assertEqual(mock_audit.call_count, 2)
        for call in mock_audit.call_args_list:
            self.assertEqual(call.args[1], "delete_report")
            self.assertEqual(call.args[2], "report")


class TestBatchCacheRedisLinkage(BaseConfigTest):
    """缺口 17：批量清理缓存与 Redis 联动（Redis 存在时清理行为）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1,
                      prefer_cache=1, cache_ttl_hours=0)
        self.mgr = MagicMock()
        self.mgr.available = True
        self.mgr.key_prefix = "sr"
        self.mgr.scan_snapshots.return_value = [
            "sr:snapshot:1:abc", "sr:snapshot:1:def"]
        self.mgr_patcher = patch("redis_cache.get_redis_manager",
                                 return_value=self.mgr)
        self.mgr_patcher.start()
        self.static_patcher = patch(
            "config_db.invalidate_api_static_cache_by_report")
        self.static_patcher.start()
        self.addCleanup(self.mgr_patcher.stop)
        self.addCleanup(self.static_patcher.stop)

    def _post(self, form_body):
        return config.handle_request(self.conn, "POST",
                                     "/config/reports/batch-cache", "", form_body)

    def test_disable_cache_deletes_redis_snapshots(self):
        """关闭缓存时应删除该报表全部 Redis 快照 key"""
        code, body, headers = self._post("report_ids=1&cache_switch=0")
        self.assertEqual(code, 302)
        self.mgr.scan_snapshots.assert_called_once_with("sr", 1)
        self.assertEqual(self.mgr.delete_snapshot.call_count, 2)
        self.assertIn("Redis 成功 1", _flash(body))

    def test_modify_ttl_sets_expiration(self):
        """修改 TTL 时应为每个 Redis 快照设置过期时间"""
        code, body, headers = self._post(
            "report_ids=1&modify_ttl=1&cache_ttl_hours=5")
        self.assertEqual(code, 302)
        self.assertEqual(self.mgr.set_expiration.call_count, 2)
        self.mgr.set_expiration.assert_any_call("sr:snapshot:1:abc", 5)
        self.mgr.set_expiration.assert_any_call("sr:snapshot:1:def", 5)

    def test_redis_unavailable_skips_redis_ops(self):
        """Redis 不可用时清理行为静默降级，flash 不含 Redis 计数"""
        self.mgr.available = False
        code, body, headers = self._post("report_ids=1&cache_switch=0")
        self.assertEqual(code, 302)
        self.assertIn("已更新 1 个报表的缓存配置", _flash(body))
        self.assertNotIn("Redis", _flash(body))
        self.mgr.delete_snapshot.assert_not_called()

    def test_redis_manager_none_still_succeeds(self):
        """Redis 管理器为 None（未配置）时批量操作仍成功"""
        with patch("redis_cache.get_redis_manager", return_value=None):
            code, body, headers = self._post("report_ids=1&cache_switch=0")
        self.assertEqual(code, 302)
        self.assertIn("已更新 1 个报表的缓存配置", _flash(body))
        self.assertEqual(db.get_report(self.conn, 1)["prefer_cache"], 0)


# ---------------------------------------------------------------------------
# 缺口 2：分类 CRUD handler
# ---------------------------------------------------------------------------


class TestCategoryCrud(BaseConfigTest):
    """分类新增/编辑/删除 handler 分支"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")

    def test_add_category(self):
        """新增分类应创建并重定向"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=销售分类&parent_id=")
        self.assertEqual(code, 302)
        self.assertIn("已创建", _flash(body))
        cats = db.get_all_categories(self.conn)
        self.assertEqual(len(cats), 1)
        self.assertEqual(cats[0]["name"], "销售分类")

    def test_add_category_with_parent(self):
        """新增子分类应正确挂载父分类"""
        db.add_category(self.conn, "根分类")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=子分类&parent_id=1")
        self.assertEqual(code, 302)
        cat = db.get_category(self.conn, 2)
        self.assertEqual(cat["parent_id"], 1)

    def test_add_category_duplicate_name(self):
        """重名分类应返回表单页并显示错误"""
        db.add_category(self.conn, "重复名")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=重复名&parent_id=")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(len(db.get_all_categories(self.conn)), 1)

    def test_add_category_invalid_parent_id(self):
        """parent_id 为非数字应返回错误响应而非 500"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=新分类&parent_id=abc")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_add_category_nonexistent_parent(self):
        """父分类不存在应返回表单页错误（FK 约束被 except 捕获）"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=孤儿&parent_id=999")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_edit_category_rename(self):
        """编辑分类应更新名称与父分类"""
        db.add_category(self.conn, "旧名")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/1/edit", "", "name=新名&parent_id=")
        self.assertEqual(code, 302)
        self.assertIn("已更新", _flash(body))
        self.assertEqual(db.get_category(self.conn, 1)["name"], "新名")

    def test_edit_category_missing(self):
        """编辑不存在的分类应重定向并提示错误"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/999/edit", "", "name=x&parent_id=")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_edit_category_duplicate_name(self):
        """编辑为重名应返回表单页错误（except 捕获 IntegrityError）"""
        db.add_category(self.conn, "甲")
        db.add_category(self.conn, "乙")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/2/edit", "", "name=甲&parent_id=")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_edit_category_set_parent_excludes_self_and_descendants(self):
        """编辑分类时父分类下拉应排除自身及后代（防循环引用）"""
        db.add_category(self.conn, "根")
        db.add_category(self.conn, "子", parent_id=1)
        db.add_category(self.conn, "孙", parent_id=2)
        body = config.render_category_form_page(self.conn, 2)
        self.assertIn('value="1"', body)          # 根可作为父分类
        self.assertNotIn('value="2"', body)       # 自身排除
        self.assertNotIn('value="3"', body)       # 后代排除

    def test_delete_category_with_reports(self):
        """删除含报表的分类：报表变为未分类，子分类父级置空"""
        db.add_category(self.conn, "待删")
        db.add_category(self.conn, "子分类", parent_id=1)
        db.add_report(self.conn, "报表", "SELECT 1", 20, 1, category_id=1)
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/1/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIn("已删除", _flash(body))
        rpt = db.get_report(self.conn, 1)
        self.assertIsNotNone(rpt)
        self.assertIsNone(rpt["category_id"])
        sub = db.get_category(self.conn, 2)
        self.assertIsNone(sub["parent_id"])

    def test_delete_category_missing(self):
        """删除不存在的分类应重定向并提示错误"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/999/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))


# ---------------------------------------------------------------------------
# 缺口 3：排序 config 层（handler move-up / move-down）
# ---------------------------------------------------------------------------


class TestSortingConfig(BaseConfigTest):
    """报表/分类/连接池排序 handler 行为"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池1", "h", 3306, "u", "p", "d")
        db.add_pool(self.conn, "池2", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类1")
        db.add_category(self.conn, "分类2")
        db.add_report(self.conn, "报表1", "SELECT 1", 20, 1, category_id=1)
        db.add_report(self.conn, "报表2", "SELECT 1", 20, 1, category_id=1)

    def test_report_move_up_handler(self):
        """POST /config/reports/{id}/move-up 应交换同分类内 sort_order 并 302"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/2/move-up", "", "")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/config/reports")
        order = [r["id"] for r in db.get_reports(self.conn, 1)]
        self.assertEqual(order, [2, 1])

    def test_report_move_down_handler(self):
        """POST /config/reports/{id}/move-down 应交换同分类内 sort_order"""
        config.handle_request(self.conn, "POST", "/config/reports/1/move-down", "", "")
        order = [r["id"] for r in db.get_reports(self.conn, 1)]
        self.assertEqual(order, [2, 1])

    def test_category_move_up_handler(self):
        """POST /config/categories/{id}/move-up 应交换分类排序并 302 到分类页"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/2/move-up", "", "")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/config/categories")
        order = [c["id"] for c in db.get_all_categories(self.conn)]
        self.assertEqual(order, [2, 1])

    def test_category_move_down_handler(self):
        """POST /config/categories/{id}/move-down 应 302 到分类页"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/1/move-down", "", "")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/config/categories")
        order = [c["id"] for c in db.get_all_categories(self.conn)]
        self.assertEqual(order, [2, 1])

    def test_pool_move_up_handler(self):
        """POST /config/pools/{id}/move-up 应交换连接池排序"""
        config.handle_request(self.conn, "POST", "/config/pools/2/move-up", "", "")
        order = [p["id"] for p in db.get_all_pools(self.conn)]
        self.assertEqual(order, [2, 1])

    def test_move_missing_object_redirects(self):
        """移动不存在的报表仍返回 302（db 层返回 False，handler 不感知）"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/999/move-up", "", "")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/config/reports")

    def test_batch_unknown_action_redirects(self):
        """batch 类未知动作（order 缺字段场景的兜底）回退 302 /config"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/batch-xyz", "", "")
        self.assertEqual(code, 302)
        self.assertEqual(body, "/config")


# ---------------------------------------------------------------------------
# 缺口 4：连接池复制 POST
# ---------------------------------------------------------------------------


class TestPoolCopy(BaseConfigTest):
    """连接池复制 handler 行为"""

    def setUp(self):
        super().setUp()
        self.pid = db.add_pool(self.conn, "源池", "h", 3306, "u", "p", "d")

    def test_copy_pool_creates_new_pool(self):
        """复制连接池应创建副本（默认名「源池 (副本)」）并 302"""
        form = "name=源池 (副本)&host=h&port=3306&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/pools/{self.pid}/copy", "", form)
        self.assertEqual(code, 302)
        self.assertIn("复制自", _flash(body))
        pools = db.get_all_pools(self.conn)
        self.assertEqual(len(pools), 2)
        self.assertEqual(pools[1]["name"], "源池 (副本)")

    def test_copy_pool_keeps_renamed_form_value(self):
        """复制时表单改名应生效"""
        form = "name=新副本&host=h&port=3306&user=u&password=p&database=d"
        config.handle_request(self.conn, "POST",
                              f"/config/pools/{self.pid}/copy", "", form)
        names = {p["name"] for p in db.get_all_pools(self.conn)}
        self.assertIn("新副本", names)

    def test_copy_nonexistent_pool_returns_error(self):
        """复制不存在的连接池应返回表单页错误且不创建新池"""
        form = "name=幽灵副本&host=h&port=3306&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/999/copy", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(len(db.get_all_pools(self.conn)), 1)

    def test_copy_pool_invalid_port_returns_form(self):
        """复制时 port 非法应返回表单页错误而非 500"""
        form = "name=坏副本&host=h&port=abc&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/pools/{self.pid}/copy", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_copy_pool_duplicate_name_returns_error(self):
        """复制为已存在名称应返回表单页错误"""
        db.add_pool(self.conn, "占用名", "h", 3306, "u", "p", "d")
        form = "name=占用名&host=h&port=3306&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/pools/{self.pid}/copy", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)


# ---------------------------------------------------------------------------
# 缺口 5：报表移动分类
# ---------------------------------------------------------------------------


class TestReportMoveCategory(BaseConfigTest):
    """报表移动分类 handler 行为（直接调用，路由不可达，见缺陷报告）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类1")
        db.add_category(self.conn, "分类2")
        self.rid = db.add_report(self.conn, "报表", "SELECT 1", 20, 1)

    def test_move_to_category(self):
        """移到指定分类应更新 category_id 并 flash 分类名"""
        code, body = config.handle_report_move_category(
            self.conn, self.rid, "category_id=2")
        self.assertEqual(code, 302)
        self.assertIn("已移至", _flash(body))
        self.assertIn("分类2", _flash(body))
        self.assertEqual(db.get_report(self.conn, self.rid)["category_id"], 2)

    def test_move_without_category_param(self):
        """缺 category 参数表示移出分类（未分类）"""
        code, body = config.handle_report_move_category(self.conn, self.rid, "")
        self.assertEqual(code, 302)
        self.assertIn("未分类", _flash(body))
        self.assertIsNone(db.get_report(self.conn, self.rid)["category_id"])

    def test_move_missing_report(self):
        """报表不存在应重定向并提示错误"""
        code, body = config.handle_report_move_category(self.conn, 999, "category_id=2")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_move_to_nonexistent_category_returns_error(self):
        """移到不存在的分类应返回错误 flash 而非 500，分类不变"""
        code, body = config.handle_report_move_category(self.conn, self.rid, "category_id=999")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))
        self.assertIsNone(db.get_report(self.conn, self.rid)["category_id"])

    def test_move_category_route_reachable(self):
        """POST /config/reports/{id}/move-category 路由应可达并移动分类"""
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/reports/{self.rid}/move-category", "",
            "category_id=2")
        self.assertEqual(code, 302)
        self.assertIn("已移至", _flash(body))
        self.assertEqual(db.get_report(self.conn, self.rid)["category_id"], 2)


# ---------------------------------------------------------------------------
# 缺口 6：表单非法值（int() ValueError → 错误响应而非 500）
# ---------------------------------------------------------------------------


class TestFormInvalidValues(BaseConfigTest):
    """int() 转换失败时应返回表单页错误而非冒泡 500"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")

    def test_add_pool_invalid_port(self):
        """新增连接池 port 非数字应返回 200 表单页 + 错误，且不新增"""
        form = "name=坏池&host=h&port=abc&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        names = {p["name"] for p in db.get_all_pools(self.conn)}
        self.assertEqual(names, {"池"})

    def test_edit_pool_invalid_port(self):
        """编辑连接池 port 非数字应返回 200 表单页 + 错误"""
        pid = db.add_pool(self.conn, "池2", "h", 3306, "u", "p", "d")
        form = "name=池2&host=h&port=abc&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/pools/{pid}/edit", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_add_report_invalid_page_size(self):
        """新增报表 default_page_size 非数字应返回 200 表单页 + 错误"""
        form = "name=坏报表&sql_query=SELECT 1&default_page_size=abc&pool_id=1"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(len(db.get_all_reports(self.conn)), 0)

    def test_edit_report_invalid_page_size(self):
        """编辑报表 default_page_size 非数字应返回 200 表单页 + 错误"""
        rid = db.add_report(self.conn, "报表", "SELECT 1", 20, 1)
        form = "name=报表&sql_query=SELECT 1&default_page_size=xyz&pool_id=1"
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_add_report_invalid_pool_id(self):
        """pool_id 非数字应返回 200 表单页 + 错误"""
        form = "name=坏报表&sql_query=SELECT 1&default_page_size=20&pool_id=abc"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)


# ---------------------------------------------------------------------------
# 缺口 7：rule_json 非法 JSON 被拒绝
# ---------------------------------------------------------------------------


class TestRuleJsonInvalid(BaseConfigTest):
    """API 端点 rule_json 非法时应返回错误而非 500"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        self.rid = db.add_report(self.conn, "报表", "SELECT 1", 20, 1)

    def test_malformed_json_rejected(self):
        """语法非法的 rule_json 应返回表单页错误"""
        form = ("name=坏端点&url_path=/bad&output_format=json"
                "&rule_json={bad&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/new", "", form)
        self.assertEqual(code, 200)
        self.assertIn("规则 JSON", body)
        self.assertEqual(len(db.get_api_endpoints_by_report(self.conn, self.rid)), 0)

    def test_non_object_json_rejected(self):
        """JSON 顶层不是对象应被拒绝"""
        form = ("name=坏端点&url_path=/bad2&output_format=json"
                "&rule_json=[1,2,3]&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/new", "", form)
        self.assertEqual(code, 200)
        self.assertIn("必须是一个对象", body)

    def test_malformed_json_on_edit_rejected(self):
        """编辑时 rule_json 非法同样被拒绝且不影响原配置"""
        eid = db.add_api_endpoint(self.conn, self.rid, "原端点", "/api/keep")
        form = ("name=原端点&url_path=/keep&output_format=json"
                "&rule_json={nope&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/{eid}/edit", "", form)
        self.assertEqual(code, 200)
        self.assertIn("规则 JSON", body)
        ep = db.get_api_endpoint(self.conn, eid)
        self.assertEqual(ep["url_path"], "/api/keep")


# ---------------------------------------------------------------------------
# 缺口 9：return_to 外部跳转防护（open redirect）
# ---------------------------------------------------------------------------


class TestReturnToGuard(BaseConfigTest):
    """return_to 参数外部跳转防护"""

    def setUp(self):
        super().setUp()
        self.rid = db.add_report(self.conn, "报表", "SELECT 1", 20, None)
        self.eid = db.add_api_endpoint(self.conn, self.rid, "端点", "/api/t")
        self.eid2 = db.add_api_endpoint(self.conn, self.rid, "端点2", "/api/t2")

    def _toggle(self, form_body):
        return config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "", form_body)

    def test_external_http_url_rejected(self):
        """http:// 外部域名应被拒绝，回退到默认管理页"""
        code, body, headers = self._toggle(
            f"action=toggle&endpoint_id={self.eid}&return_to=http://evil.com/steal")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/api-endpoints"), body)
        self.assertNotIn("evil.com", body)

    def test_external_https_url_rejected(self):
        """https:// 外部域名应被拒绝"""
        code, body, headers = self._toggle(
            f"action=toggle&endpoint_id={self.eid}&return_to=https://evil.com")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/api-endpoints"), body)

    def test_protocol_relative_url_rejected(self):
        """// 协议相对地址应被拒绝"""
        code, body, headers = self._toggle(
            f"action=toggle&endpoint_id={self.eid}&return_to=//evil.com/x")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/api-endpoints"), body)

    def test_relative_path_accepted(self):
        """站内相对路径应被接受"""
        code, body, headers = self._toggle(
            f"action=toggle&endpoint_id={self.eid}&return_to=/report?id=5")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/report?id=5"), body)

    def test_single_slash_scheme_like_rejected(self):
        """以 / 开头但带反斜杠的伪协议路径（/\\evil.com）不匹配白名单"""
        code, body, headers = self._toggle(
            f"action=toggle&endpoint_id={self.eid}&return_to=/\\evil.com")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/"))


# ---------------------------------------------------------------------------
# 缺口 10：报表内嵌 API 端点删除路由
# ---------------------------------------------------------------------------


class TestApiEndpointDeleteRoute(BaseConfigTest):
    """POST /config/reports/{rid}/api_endpoints/{eid}/delete 路由"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        self.rid = db.add_report(self.conn, "报表", "SELECT 1", 20, 1)
        self.eid = db.add_api_endpoint(self.conn, self.rid, "端点", "/api/del")

    def test_delete_via_route(self):
        """路由删除端点应 302 回报表编辑页并删除端点"""
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/{self.eid}/delete",
            "", "")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith(f"/config/reports/{self.rid}/edit"), body)
        self.assertIsNone(db.get_api_endpoint(self.conn, self.eid))

    def test_delete_nonexistent_endpoint(self):
        """删除不存在的端点应重定向并提示错误"""
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/999/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_delete_endpoint_of_other_report_rejected(self):
        """用其他报表路径删除端点：应校验归属并拒绝删除"""
        rid2 = db.add_report(self.conn, "报表2", "SELECT 1", 20, 1)
        eid2 = db.add_api_endpoint(self.conn, rid2, "端点2", "/api/other")
        code, body, headers = config.handle_request(
            self.conn, "POST",
            f"/config/reports/{self.rid}/api_endpoints/{eid2}/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIn("不属于该报表", _flash(body))
        self.assertIsNotNone(db.get_api_endpoint(self.conn, eid2))

    def test_edit_route_of_missing_report_redirects(self):
        """报表不存在的 API 新增表单 POST 返回总览页 + 错误（非 500）"""
        code, body, headers = config.handle_request(
            self.conn, "POST",
            "/config/reports/999/api_endpoints/new", "",
            "name=x&url_path=/x&output_format=json")
        self.assertEqual(code, 200)
        self.assertIn("报表不存在", body)


# ---------------------------------------------------------------------------
# 缺口 12：分类树构建与祖先链（SQLite 侧，见 config_db.py）
# ---------------------------------------------------------------------------


class TestCategoryTree(BaseConfigTest):
    """get_category_tree 与 get_parent_categories 正确性"""

    def test_tree_builds_hierarchy(self):
        """树应按父子关系正确挂载且顶级节点保持 sort_order 顺序"""
        db.add_category(self.conn, "根1")
        db.add_category(self.conn, "根2")
        db.add_category(self.conn, "子1", parent_id=1)
        db.add_category(self.conn, "孙1", parent_id=3)
        tree = db.get_category_tree(self.conn)
        self.assertEqual([c["id"] for c in tree], [1, 2])
        root1 = tree[0]
        self.assertEqual([c["id"] for c in root1["children"]], [3])
        self.assertEqual([c["id"] for c in root1["children"][0]["children"]], [4])
        self.assertEqual(tree[1]["children"], [])

    def test_tree_orphan_goes_to_root(self):
        """父分类缺失的分类应置于顶层而非丢失"""
        # FK 约束下无法经 add_category 插入孤儿，临时关闭外键模拟脏数据
        self.conn.execute("PRAGMA foreign_keys=OFF")
        db.add_category(self.conn, "孤儿", parent_id=999)
        self.conn.execute("PRAGMA foreign_keys=ON")
        tree = db.get_category_tree(self.conn)
        self.assertEqual([c["id"] for c in tree], [1])

    def test_tree_cycle_does_not_crash(self):
        """父子循环引用不崩溃（无根节点时顶层为空）"""
        db.add_category(self.conn, "甲")
        db.add_category(self.conn, "乙")
        db.update_category(self.conn, 2, "乙", 1)
        db.update_category(self.conn, 1, "甲", 2)
        tree = db.get_category_tree(self.conn)
        # 循环中每个节点都是别人的子节点 → 顶层无根
        self.assertEqual(tree, [])

    def test_parent_categories_chain_root_to_parent(self):
        """祖先链应从根到父排列且不含自身"""
        db.add_category(self.conn, "根")
        db.add_category(self.conn, "子", parent_id=1)
        db.add_category(self.conn, "孙", parent_id=2)
        ancestors = db.get_parent_categories(self.conn, 3)
        self.assertEqual([c["id"] for c in ancestors], [1, 2])

    def test_parent_categories_of_root_is_empty(self):
        """顶级分类无祖先"""
        db.add_category(self.conn, "根")
        self.assertEqual(db.get_parent_categories(self.conn, 1), [])

    def test_parent_categories_missing_category(self):
        """不存在的分类返回空祖先链"""
        self.assertEqual(db.get_parent_categories(self.conn, 999), [])

    def test_parent_categories_cycle_no_infinite_loop(self):
        """祖先链遇循环引用能终止，且不含查询节点自身"""
        db.add_category(self.conn, "甲")
        db.add_category(self.conn, "乙")
        db.update_category(self.conn, 2, "乙", 1)
        db.update_category(self.conn, 1, "甲", 2)
        ancestors = db.get_parent_categories(self.conn, 1)
        ids = [c["id"] for c in ancestors]
        self.assertNotIn(1, ids)  # 不包含自身
        self.assertLessEqual(len(ancestors), 2)


# ---------------------------------------------------------------------------
# 缺口 13：批量操作 JS 交互逻辑（按实现断言渲染输出）
# ---------------------------------------------------------------------------


class TestBatchJsInteraction(BaseConfigTest):
    """配置页批量操作前端 JS 交互（服务端渲染出的 JS 文本断言）"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        db.add_category(self.conn, "分类")
        db.add_report(self.conn, "报表", "SELECT 1", 20, 1)
        # PH-13：批量操作 JS 随报表管理独立页渲染
        self.body = config.render_reports_page(self.conn)

    def test_checkbox_and_count_present(self):
        """报表行应含复选 checkbox 与选中计数元素"""
        self.assertIn('class="report-checkbox"', self.body)
        self.assertIn('id="batch_count"', self.body)

    def test_batch_update_pool_js(self):
        """批量修改连接池：无选择时 alert，提交到 batch-pool 路由"""
        self.assertIn("function batchUpdatePool()", self.body)
        self.assertIn("alert('请至少选择一项')", self.body)
        self.assertIn("alert('请选择目标连接池')", self.body)
        self.assertIn("submitBatchPost('/config/reports/batch-pool'", self.body)

    def test_batch_set_category_js(self):
        """批量设置分类：无选择时 alert，-1 映射为空值提交到 batch-set-category"""
        self.assertIn("function batchSetCategory()", self.body)
        self.assertIn("alert('请选择目标分类')", self.body)
        self.assertIn("catId === '-1' ? '' : catId", self.body)
        self.assertIn("submitBatchPost('/config/reports/batch-set-category'", self.body)

    def test_batch_update_cache_js_confirm_dialog(self):
        """批量更新缓存：需确认对话框，未选开关/勾选时 alert"""
        self.assertIn("function batchUpdateCache()", self.body)
        self.assertIn("confirm(`确定批量更新", self.body)
        self.assertIn("alert('请选择缓存开关或勾选修改TTL')", self.body)

    def test_batch_cache_ttl_input_toggle(self):
        """修改 TTL 复选框联动输入框 disabled 状态"""
        self.assertIn("function toggleTtlInput()", self.body)
        self.assertIn("inp.disabled = !cb.checked", self.body)
        self.assertIn('id="batch_modify_ttl"', self.body)
        self.assertIn('id="batch_cache_ttl"', self.body)

    def test_submit_batch_post_builds_hidden_form(self):
        """submitBatchPost 应动态构建 POST 表单提交 report_ids 与扩展字段"""
        self.assertIn("function submitBatchPost(actionUrl, ids, extraFields)", self.body)
        self.assertIn("inp.type = 'hidden'; inp.name = 'report_ids'", self.body)
        self.assertIn("form.submit()", self.body)

    def test_update_batch_count_wired_to_checkbox(self):
        """复选框 onchange 应联动更新选中计数"""
        self.assertIn('onchange="updateBatchCount()"', self.body)
        self.assertIn("function updateBatchCount()", self.body)

    def test_select_all_in_section_present(self):
        """表头全选复选框联动 section 内全部复选框"""
        self.assertIn('onchange="selectAllInSection(this)"', self.body)
        self.assertIn("function selectAllInSection(el)", self.body)


# ---------------------------------------------------------------------------
# 缺口 14：保存失败表单回显（疑似缺陷：异常分支未携带用户已填写的表单值）
# ---------------------------------------------------------------------------


class TestSaveFailureEcho(BaseConfigTest):
    """保存失败时表单应回显用户已填写值

    修复后（config.py 失败分支携带 _pool_from_form / _report_from_form 回显数据），
    用户已填写的字段应原样保留在表单中。
    """

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")

    def test_report_save_failure_shows_error(self):
        """真实行为：非法分页值保存失败 → 200 + 错误 flash（非 500）"""
        form = ("name=用户已填报表&sql_query=SELECT 9&default_page_size=abc&pool_id=1")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_report_save_failure_echoes_user_input(self):
        """保存失败后报表表单应回显用户填写的名称"""
        form = ("name=用户已填报表&sql_query=SELECT 9&default_page_size=abc&pool_id=1")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn('value="用户已填报表"', body)

    def test_pool_save_failure_shows_error(self):
        """真实行为：非法 port 保存失败 → 200 + 错误 flash"""
        form = "name=用户已填池&host=10.1.1.1&port=abc&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_pool_save_failure_echoes_user_input(self):
        """保存失败后连接池表单应回显用户填写的名称与主机"""
        form = "name=用户已填池&host=10.1.1.1&port=abc&user=u&password=p&database=d"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn('value="用户已填池"', body)
        self.assertIn("10.1.1.1", body)


# ---------------------------------------------------------------------------
# 缺口 15：用户编辑/删除失败边界
# ---------------------------------------------------------------------------


class TestUserBoundary(BaseConfigTest):
    """用户编辑/删除失败边界"""

    def setUp(self):
        super().setUp()
        self.uid = db.add_user(self.conn, "bob", auth.hash_password("oldpw"))

    def test_edit_nonexistent_user(self):
        """编辑不存在的用户应重定向并提示错误"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/999/edit", "",
            "username=x&password=new")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_delete_nonexistent_user(self):
        """删除不存在的用户应重定向并提示错误"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/999/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_edit_user_blank_password_keeps_old(self):
        """编辑用户密码留空应保留原密码哈希"""
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/users/{self.uid}/edit", "",
            "username=bob&password=")
        self.assertEqual(code, 302)
        user = db.get_user_by_id(self.conn, self.uid)
        self.assertTrue(auth.verify_password("oldpw", user["password_hash"]))

    def test_edit_user_missing_username_returns_error(self):
        """编辑用户缺 username 应返回表单页错误而非 500"""
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/users/{self.uid}/edit", "",
            "password=new")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(db.get_user_by_id(self.conn, self.uid)["username"], "bob")

    def test_edit_user_duplicate_username_returns_error(self):
        """编辑用户重名应返回表单页错误而非 500，原用户名不变"""
        db.add_user(self.conn, "dup", auth.hash_password("x"))
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/users/{self.uid}/edit", "",
            "username=dup&password=new")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(db.get_user_by_id(self.conn, self.uid)["username"], "bob")

    def test_add_user_missing_username(self):
        """新增用户缺 username 应返回表单页错误而非 500"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/add", "", "password=x")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_add_user_missing_password(self):
        """新增用户缺 password 应返回表单页错误而非 500"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/users/add", "", "username=nopw")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)


# ---------------------------------------------------------------------------
# 缺口 16：报表复制 save_close、编辑不存在的报表
# ---------------------------------------------------------------------------


class TestReportCopyCloseBoundary(BaseConfigTest):
    """报表复制 save_close 行为与编辑不存在报表边界"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")
        self.rid = db.add_report(self.conn, "源报表", "SELECT 1", 20, 1)

    def test_copy_save_close_redirects(self):
        """复制报表点【保存并关闭】应 302 返回列表页"""
        form = ("name=副本&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&action=save_close")
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/reports/{self.rid}/copy", "", form)
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config"), body)
        self.assertIn("已创建", _flash(body))
        self.assertEqual(len(db.get_all_reports(self.conn)), 2)

    def test_copy_missing_report_returns_error(self):
        """复制不存在的报表应返回表单页错误且不创建新报表"""
        form = "name=幽灵副本&sql_query=SELECT 1&default_page_size=20&pool_id=1"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/999/copy", "", form)
        self.assertEqual(code, 200)
        self.assertIn("错误", body)
        self.assertEqual(len(db.get_all_reports(self.conn)), 1)

    def test_edit_nonexistent_report_post(self):
        """POST 编辑不存在的报表应重定向并提示错误"""
        form = "name=x&sql_query=SELECT 1&default_page_size=20&pool_id=1"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/999/edit", "", form)
        self.assertEqual(code, 302)
        self.assertIn("错误", _flash(body))

    def test_edit_nonexistent_report_get(self):
        """GET 编辑不存在的报表应返回总览页 + 错误 flash"""
        code, body, headers = config.handle_request(
            self.conn, "GET", "/config/reports/999/edit", "")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)

    def test_copy_nonexistent_report_get(self):
        """GET 复制不存在的报表应返回总览页 + 错误 flash"""
        code, body, headers = config.handle_request(
            self.conn, "GET", "/config/reports/999/copy", "")
        self.assertEqual(code, 200)
        self.assertIn("错误", body)


# ---------------------------------------------------------------------------
# PH-14：分类管理独立页（render_categories_page）与回跳目标
# ---------------------------------------------------------------------------


class TestCategoriesPage(BaseConfigTest):
    """PH-14：/config/categories 独立页渲染与分类回跳目标"""

    def setUp(self):
        super().setUp()
        db.add_pool(self.conn, "池", "h", 3306, "u", "p", "d")

    def test_categories_page_header_and_title(self):
        """独立页应含分类管理标题与配置菜单高亮"""
        body = config.render_categories_page(self.conn)
        self.assertIn("分类管理", body)
        self.assertIn('href="/config" class="nav-active"', body)

    def test_categories_page_has_add_category_button(self):
        """独立页应有「新增分类」按钮"""
        body = config.render_categories_page(self.conn)
        self.assertIn("/config/categories/add", body)
        self.assertIn("新增分类", body)

    def test_categories_page_hides_report_add_button(self):
        """独立页不应显示报表页的「新增报表」快捷按钮（show_report_add=False）"""
        body = config.render_categories_page(self.conn)
        self.assertNotIn("新增报表", body)

    def test_categories_page_renders_tree_with_badge(self):
        """分类树应渲染子分类数量角标"""
        db.add_category(self.conn, "根")
        db.add_category(self.conn, "子", parent_id=1)
        body = config.render_categories_page(self.conn)
        self.assertIn("根", body)
        self.assertIn("1 子分类", body)

    def test_categories_page_empty_state(self):
        """无分类时应显示暂无分类占位"""
        body = config.render_categories_page(self.conn)
        self.assertIn("暂无分类", body)

    def test_categories_page_flash_message(self):
        """flash 消息应渲染在独立页"""
        body = config.render_categories_page(self.conn, "分类 甲 已创建")
        self.assertIn("分类 甲 已创建", body)

    def test_category_add_redirects_to_categories_page(self):
        """新增分类成功应 302 到 /config/categories"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/add", "", "name=销售分类&parent_id=")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/categories"))

    def test_category_edit_redirects_to_categories_page(self):
        """编辑分类成功应 302 到 /config/categories"""
        db.add_category(self.conn, "旧名")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/1/edit", "", "name=新名&parent_id=")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/categories"))

    def test_category_delete_redirects_to_categories_page(self):
        """删除分类成功应 302 到 /config/categories"""
        db.add_category(self.conn, "待删")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/categories/1/delete", "", "")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/categories"))

    def test_overview_has_categories_card(self):
        """总览应含分类管理入口卡片"""
        body = config.render_overview(self.conn)
        self.assertIn("分类管理", body)
        self.assertIn("href=\"/config/categories\"", body)


if __name__ == "__main__":
    unittest.main()
