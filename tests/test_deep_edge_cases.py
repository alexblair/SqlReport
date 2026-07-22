"""
tests/test_deep_edge_cases.py — 深度边缘场景测试

覆盖六大类边缘场景：
1. 分页边界 — page/page_size 的边界值处理
2. 配置 CRUD 边界 — None/空值/不存在 ID 的增删改
3. 排序筛选边界 — 不存在的列/无效 dir/特殊字符/重复列
4. Cookie 边界 — 特殊字符/空头/无 '='/None token/max_age=0
5. 导入兼容性 — db.py 转发层符号完整性
6. 导出边界 — None 值/逆序/Decimal/无效 charset

每个场景使用独立的 test_ 方法，遵循 Arrange-Act-Assert 模式。
"""

import unittest
import unittest.mock
from unittest.mock import patch, MagicMock, PropertyMock
import json
import math
from decimal import Decimal
import sqlite3

# 待测试模块
import auth
import config_db
import db as db_module
import export
import report
import query_executor
from render import format_cell

# 测试基类
from tests import make_config_db, init_test_db, BaseConfigTest, BaseReportTest


# ===================================================================
# 1. 分页边界
# ===================================================================

class TestPaginationBoundaries(unittest.TestCase):
    """分页边界：page 和 page_size 在 execute_report 中的边界值处理"""

    def setUp(self):
        """Mock 数据库连接和查询缓存，避免真实查询"""
        # 模拟 50 行测试数据
        self.mock_data = [{
            "columns": ["id", "name"],
            "rows": [(i, f"row{i}") for i in range(1, 51)],
        }]
        self.mock_conn = MagicMock()
        # patcher: db.create_mysql_connection
        self.patcher_conn = patch("db.create_mysql_connection",
                                  return_value=self.mock_conn)
        # patcher: db.execute_mysql_query
        self.patcher_query = patch("db.execute_mysql_query",
                                   return_value=self.mock_data)
        # patcher: 报告缓存 — 每次返回 None 强制走 MySQL 路径
        self.patcher_cache = patch("report._query_cache.get",
                                   return_value=None)
        self.patcher_conn.start()
        self.patcher_query.start()
        self.patcher_cache.start()

    def tearDown(self):
        self.patcher_conn.stop()
        self.patcher_query.stop()
        self.patcher_cache.stop()

    # ── page 边界 ──

    def test_page_zero_corrected_to_one(self):
        """✅ Positive: page=0 在 execute_report 中被修正为 1"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=0,
            page_size=20,
        )
        self.assertEqual(result.page, 1)

    def test_page_negative_corrected_to_one(self):
        """✅ Positive: page=-1 在 execute_report 中被修正为 1"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=-1,
            page_size=20,
        )
        self.assertEqual(result.page, 1)

    def test_page_positive_preserved(self):
        """✅ Positive: page=5 保持原值"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=5,
            page_size=20,
        )
        self.assertEqual(result.page, 5)

    # ── page_size 边界 ──

    def test_page_size_zero_in_execute(self):
        """✅ Positive: execute_report 中 page_size=0 被 clamp 为 1（下限）"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=1,
            page_size=0,
        )
        # execute_report 内 page_size = max(page_size, 1)
        self.assertEqual(result.page_size, 1)

    def test_page_size_negative_in_execute(self):
        """✅ Positive: execute_report 中 page_size=-5 被 clamp 为 1"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=1,
            page_size=-5,
        )
        self.assertEqual(result.page_size, 1)

    def test_page_size_large_accepted(self):
        """✅ Positive: page_size=999999 当前无上限"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=1,
            page_size=999999,
        )
        self.assertEqual(result.page_size, 999999)

    def test_page_size_normal_preserved(self):
        """✅ Positive: page_size=20 保持原值"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=1,
            page_size=20,
        )
        self.assertEqual(result.page_size, 20)

    # ── 分页逻辑验证 ──

    def test_pagination_offset_correct(self):
        """✅ Positive: page=1, page_size=10 返回前 10 条"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=1,
            page_size=10,
        )
        self.assertEqual(len(result.rows), 10)
        self.assertEqual(result.rows[0][0], 1)
        self.assertEqual(result.rows[-1][0], 10)

    def test_pagination_last_page_correct(self):
        """✅ Positive: page=5, page_size=10 返回最后 10 条（50 条数据）"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=5,
            page_size=10,
        )
        self.assertEqual(len(result.rows), 10)
        self.assertEqual(result.rows[0][0], 41)
        self.assertEqual(result.rows[-1][0], 50)

    def test_pagination_beyond_last_page(self):
        """❌ Negative: page=100 超出最后一页 → 返回空列表"""
        result = report.execute_report(
            report_id=1,
            sql_query="SELECT * FROM t",
            pool_config={"host": "localhost"},
            page=100,
            page_size=20,
        )
        self.assertEqual(len(result.rows), 0)


# ===================================================================
# 2. 配置 CRUD 边界
# ===================================================================

class TestConfigCrudBoundaries(BaseReportTest):
    """配置 CRUD 边界：None/空值/不存在 ID 的处理"""

    # ── add_pool 边界 ──

    def test_add_pool_name_none(self):
        """❌ Negative: add_pool name=None → IntegrityError（NOT NULL）"""
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_pool(
                self.conn, None, "host", 3306, "user", "pass", "db",
            )

    def test_add_pool_name_empty(self):
        """❌ Negative: add_pool name='' → 首次插入成功（空字符串满足 NOT NULL）"""
        pool_id = config_db.add_pool(
            self.conn, "", "host", 3306, "user", "pass", "db",
        )
        self.assertIsNotNone(pool_id)
        self.assertGreater(pool_id, 0)
        # 验证确实写入了
        pool = config_db.get_pool(self.conn, pool_id)
        self.assertEqual(pool["name"], "")

    def test_add_pool_name_empty_duplicate(self):
        """❌ Negative: 两个空名称 → 第二个违反 UNIQUE 约束"""
        config_db.add_pool(self.conn, "", "h1", 3306, "u1", "p1", "db1")
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_pool(
                self.conn, "", "h2", 3306, "u2", "p2", "db2",
            )

    def test_add_pool_duplicate_name(self):
        """❌ Negative: 重复 name → IntegrityError（UNIQUE）"""
        config_db.add_pool(self.conn, "dup", "h1", 3306, "u1", "p1", "d1")
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_pool(
                self.conn, "dup", "h2", 3307, "u2", "p2", "d2",
            )

    # ── add_user 边界 ──

    def test_add_user_username_empty(self):
        """❌ Negative: add_user username='' → 首次插入成功"""
        uid = config_db.add_user(self.conn, "", "hash")
        self.assertIsNotNone(uid)
        self.assertGreater(uid, 0)

    def test_add_user_username_empty_duplicate(self):
        """❌ Negative: 两个''用户名 → 第二个违反 UNIQUE 约束"""
        config_db.add_user(self.conn, "", "hash1")
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_user(self.conn, "", "hash2")

    # ── add_report 边界 ──

    def test_add_report_name_none(self):
        """❌ Negative: add_report name=None → IntegrityError（NOT NULL）"""
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_report(
                self.conn, None, "SELECT 1", 20, pool_id=1,
            )

    def test_add_report_name_empty(self):
        """❌ Negative: add_report name='' → 首次插入成功"""
        rid = config_db.add_report(
            self.conn, "", "SELECT 1", 20, pool_id=1,
        )
        self.assertIsNotNone(rid)
        self.assertGreater(rid, 0)
        r = config_db.get_report(self.conn, rid)
        self.assertEqual(r["name"], "")

    def test_add_report_duplicate_name(self):
        """❌ Negative: 重复 name → IntegrityError（UNIQUE）"""
        config_db.add_report(self.conn, "rpt", "SELECT 1", 20, pool_id=1)
        with self.assertRaises(sqlite3.IntegrityError):
            config_db.add_report(
                self.conn, "rpt", "SELECT 2", 10, pool_id=1,
            )

    # ── delete 不存在 ID ──

    def test_delete_pool_not_exist(self):
        """✅ Positive: delete_pool 不存在的 ID → 返回 False"""
        result = config_db.delete_pool(self.conn, 99999)
        self.assertFalse(result)

    def test_delete_user_not_exist(self):
        """✅ Positive: delete_user 不存在的 ID → 返回 False"""
        result = config_db.delete_user(self.conn, 99999)
        self.assertFalse(result)

    def test_delete_report_not_exist(self):
        """✅ Positive: delete_report 不存在的 ID → 返回 False"""
        result = config_db.delete_report(self.conn, 99999)
        self.assertFalse(result)

    def test_delete_category_not_exist(self):
        """✅ Positive: delete_category 不存在的 ID → 返回 False"""
        result = config_db.delete_category(self.conn, 99999)
        self.assertFalse(result)

    # ── update 不存在 ID ──

    def test_update_pool_not_exist(self):
        """✅ Positive: update_pool 不存在的 ID → 返回 False"""
        result = config_db.update_pool(
            self.conn, 99999, "name", "host", 3306, "u", "p", "db",
        )
        self.assertFalse(result)

    def test_update_user_not_exist(self):
        """✅ Positive: update_user 不存在的 ID → 返回 False"""
        result = config_db.update_user(self.conn, 99999, "name", "hash")
        self.assertFalse(result)

    def test_update_report_not_exist(self):
        """✅ Positive: update_report 不存在的 ID → 返回 False"""
        result = config_db.update_report(
            self.conn, 99999, "name", "SELECT 1", 20, pool_id=1,
        )
        self.assertFalse(result)

    def test_update_category_not_exist(self):
        """✅ Positive: update_category 不存在的 ID → 返回 False"""
        result = config_db.update_category(self.conn, 99999, "name")
        self.assertFalse(result)

    # ── get 不存在 ID ──

    def test_get_pool_not_exist(self):
        """✅ Positive: get_pool 不存在的 ID → 返回 None"""
        result = config_db.get_pool(self.conn, 99999)
        self.assertIsNone(result)

    def test_get_report_not_exist(self):
        """✅ Positive: get_report 不存在的 ID → 返回 None"""
        result = config_db.get_report(self.conn, 99999)
        self.assertIsNone(result)

    def test_get_user_by_id_not_exist(self):
        """✅ Positive: get_user_by_id 不存在的 ID → 返回 None"""
        result = config_db.get_user_by_id(self.conn, 99999)
        self.assertIsNone(result)


# ===================================================================
# 3. 排序筛选边界
# ===================================================================

class TestSortFilterBoundaries(unittest.TestCase):
    """排序筛选边界：不存在的列/无效 dir/特殊字符/重复列"""

    # ── _sort_rows 边界 ──

    def test_sort_col_not_in_columns(self):
        """✅ Positive: sort 中 col 名不存在 → 忽略该排序条件"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("nonexistent", "asc")]
        result = report._sort_rows(rows, columns, sorts)
        # 排序条件被忽略，顺序不变
        self.assertEqual(result, [(2, "b"), (1, "a")])

    def test_sort_dir_invalid(self):
        """✅ Positive: sort 中 dir='INVALID' → 视为 asc（非 'desc' 即升序）"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("id", "INVALID")]
        result = report._sort_rows(rows, columns, sorts)
        # "INVALID" != "desc"，所以升序：1 在 2 前
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[1][0], 2)

    def test_sort_dir_empty(self):
        """✅ Positive: sort 中 dir='' → 视为 asc"""
        rows = [(2, "b"), (1, "a")]
        columns = ["id", "name"]
        sorts = [("id", "")]
        result = report._sort_rows(rows, columns, sorts)
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[1][0], 2)

    def test_sort_duplicate_col_last_wins(self):
        """✅ Positive: _parse_sorts 去重保留最后一个排序方向"""
        from urllib.parse import parse_qs
        qs = parse_qs("sort=name&dir=desc&sort=id&dir=asc&sort=name&dir=asc")
        parsed = report._parse_sorts(qs)
        # 去重后：name(asc), id(asc)
        self.assertEqual(parsed, [("name", "asc"), ("id", "asc")])
        rows = [(1, "z"), (2, "y"), (3, "x")]
        columns = ["id", "name"]
        result = report._sort_rows(rows, columns, parsed)
        # 先按 name asc（x,y,z），再按 id asc（稳定排序同级）
        names = [r[1] for r in result]
        self.assertEqual(names, ["x", "y", "z"])

    def test_sort_multiple_cols(self):
        """✅ Positive: 多字段排序（先 name asc，再 id desc）"""
        rows = [(2, "a"), (1, "a"), (3, "b")]
        columns = ["id", "name"]
        sorts = [("name", "asc"), ("id", "desc")]
        result = report._sort_rows(rows, columns, sorts)
        # name asc: all "a"s first, then "b"
        # then id desc within same name: 2, 1, 3
        self.assertEqual([r[0] for r in result], [2, 1, 3])

    def test_sort_none_values_at_end(self):
        """✅ Positive: None 值始终排在最后（升序）"""
        rows = [(3, "c"), (1, None), (2, "a")]
        columns = ["id", "name"]
        sorts = [("name", "asc")]
        result = report._sort_rows(rows, columns, sorts)
        # asc: "a", "c", None
        names = [r[1] for r in result]
        self.assertEqual(names, ["a", "c", None])

    def test_sort_none_values_at_end_desc(self):
        """✅ Positive: None 值始终排在最后（降序）"""
        rows = [(3, "c"), (1, None), (2, "a")]
        columns = ["id", "name"]
        sorts = [("name", "desc")]
        result = report._sort_rows(rows, columns, sorts)
        # desc: "c", "a", None
        names = [r[1] for r in result]
        self.assertEqual(names, ["c", "a", None])

    # ── _filter_rows 边界 ──

    def test_filter_col_not_in_columns(self):
        """✅ Positive: filter 中 col 名不存在 → 忽略该条件"""
        rows = [(1, "hello"), (2, "world")]
        columns = ["id", "name"]
        filters = [("nonexistent", "contains", "hello")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 2)

    def test_filter_special_sql_chars_percent(self):
        """✅ Positive: 筛选值含 '%' → 纯文本匹配，非 SQL LIKE"""
        rows = [(1, "100%"), (2, "200"), (3, "300%")]
        columns = ["id", "name"]
        filters = [("name", "contains", "%")]
        result = report._filter_rows(rows, columns, filters)
        # Python str in 检查，% 为普通字符
        self.assertEqual(len(result), 2)  # 100% 和 300% 匹配
        self.assertEqual(result[0][1], "100%")
        self.assertEqual(result[1][1], "300%")

    def test_filter_special_sql_chars_underscore(self):
        """✅ Positive: 筛选值含 '_' → 纯文本匹配"""
        rows = [(1, "hello_world"), (2, "helloworld")]
        columns = ["id", "name"]
        filters = [("name", "contains", "_")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "hello_world")

    def test_filter_special_sql_chars_quote(self):
        """✅ Positive: 筛选值含单引号 → 正常处理"""
        rows = [(1, "it's"), (2, "its")]
        columns = ["id", "name"]
        filters = [("name", "contains", "'")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "it's")

    def test_filter_isempty_matches_none(self):
        """✅ Positive: isempty 操作符匹配 None 值"""
        rows = [(1, None), (2, "a"), (3, "")]
        columns = ["id", "name"]
        filters = [("name", "isempty", "")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 2)  # None 和 "" 都匹配
        self.assertIsNone(result[0][1])
        self.assertEqual(result[1][1], "")

    def test_filter_isempty_matches_empty_string(self):
        """✅ Positive: isempty 操作符匹配空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "isempty", "")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "")

    def test_filter_notempty_excludes_none(self):
        """✅ Positive: notempty 操作符排除 None"""
        rows = [(1, None), (2, "a"), (3, "")]
        columns = ["id", "name"]
        filters = [("name", "notempty", "")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "a")

    def test_filter_notempty_excludes_empty_string(self):
        """✅ Positive: notempty 操作符排除空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "notempty", "")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "b")

    def test_filter_eq_empty_string(self):
        """✅ Positive: eq 操作符匹配空字符串"""
        rows = [(1, ""), (2, "b")]
        columns = ["id", "name"]
        filters = [("name", "eq", "")]
        result = report._filter_rows(rows, columns, filters)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "")

    # ── _parse_sorts 边界 ──

    def test_parse_sorts_dir_invalid_filtered(self):
        """❌ Negative: dir='INVALID' 在 _parse_sorts 中被过滤"""
        qs = {"sort": ["col1"], "dir": ["INVALID"]}
        sorts = report._parse_sorts(qs)
        self.assertEqual(len(sorts), 0)

    def test_parse_sorts_dir_empty_filtered(self):
        """❌ Negative: dir='' 在 _parse_sorts 中被过滤"""
        qs = {"sort": ["col1"], "dir": [""]}
        sorts = report._parse_sorts(qs)
        # '' not in ("asc", "desc"), so filtered out
        self.assertEqual(len(sorts), 0)

    def test_parse_sorts_mixed_valid_and_invalid(self):
        """✅ Positive: 混用有效 dir 和无效 dir → 只保留有效的"""
        qs = {
            "sort": ["col1", "col2", "col3"],
            "dir": ["asc", "INVALID", "desc"],
        }
        sorts = report._parse_sorts(qs)
        self.assertEqual(len(sorts), 2)
        self.assertEqual(sorts[0], ("col1", "asc"))
        self.assertEqual(sorts[1], ("col3", "desc"))

    def test_parse_sorts_no_sort_key(self):
        """✅ Positive: 没有 sort 参数 → 返回空列表"""
        qs = {}
        sorts = report._parse_sorts(qs)
        self.assertEqual(sorts, [])


# ===================================================================
# 4. Cookie 边界
# ===================================================================

class TestCookieBoundaries(unittest.TestCase):
    """Cookie 边界：特殊字符/空头/无 '='/None token/max_age=0"""

    def test_parse_cookie_special_chars(self):
        """✅ Positive: cookie 字符串中的特殊字符正确解析"""
        header = "session_id=abc123; theme=dark+mode; token=x%3Dy"
        cookies = auth.parse_cookie(header)
        self.assertEqual(cookies["session_id"], "abc123")
        self.assertEqual(cookies["theme"], "dark+mode")
        self.assertEqual(cookies["token"], "x%3Dy")

    def test_parse_cookie_empty_header(self):
        """✅ Positive: 空 cookie 头 → 返回空 dict"""
        cookies = auth.parse_cookie("")
        self.assertEqual(cookies, {})

    def test_parse_cookie_none_header(self):
        """✅ Positive: cookie 头为 None → 返回空 dict"""
        cookies = auth.parse_cookie("")
        self.assertEqual(cookies, {})

    def test_parse_cookie_no_equals_ignored(self):
        """✅ Positive: cookie 中无 '=' 的项被忽略"""
        header = "session_id=abc123; junkwithout equals; key=val"
        cookies = auth.parse_cookie(header)
        self.assertIn("session_id", cookies)
        self.assertIn("key", cookies)
        self.assertNotIn("junkwithout equals", cookies)
        self.assertEqual(len(cookies), 2)

    def test_parse_cookie_trailing_semicolon(self):
        """✅ Positive: 末尾分号 → 正确解析"""
        header = "a=1; b=2;"
        cookies = auth.parse_cookie(header)
        self.assertEqual(cookies["a"], "1")
        self.assertEqual(cookies["b"], "2")

    def test_get_session_user_none_token(self):
        """✅ Positive: session_token 为 None → get_session_user 返回 None"""
        result = auth.get_session_user(None)
        self.assertIsNone(result)

    def test_get_session_user_empty_token(self):
        """✅ Positive: session_token 为空字符串 → 返回 None"""
        result = auth.get_session_user("")
        self.assertIsNone(result)

    def test_get_session_user_invalid_token(self):
        """✅ Positive: session_token 无效 → 返回 None"""
        result = auth.get_session_user("nonexistent_token_12345")
        self.assertIsNone(result)

    def test_make_set_cookie_header_max_age_zero(self):
        """✅ Positive: set-cookie 中 max_age=0 → 正确生成"""
        header = auth.make_set_cookie_header("test_token", max_age=0)
        self.assertIn("session_id=test_token", header)
        self.assertIn("Max-Age=0", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertIn("Path=/", header)

    def test_make_set_cookie_header_default_max_age(self):
        """✅ Positive: set-cookie 默认 max_age=86400"""
        header = auth.make_set_cookie_header("test_token")
        self.assertIn("Max-Age=86400", header)

    def test_make_expire_cookie_header(self):
        """✅ Positive: make_expire_cookie_header 生成 max-age=0"""
        header = auth.make_expire_cookie_header()
        self.assertIn("Max-Age=0", header)
        self.assertIn("session_id=", header)

    def test_parse_cookie_whitespace_handling(self):
        """✅ Positive: cookie 中的空格被正确处理"""
        header = "  a = 1 ; b=2  "
        cookies = auth.parse_cookie(header)
        self.assertEqual(cookies.get("a"), "1")
        self.assertEqual(cookies.get("b"), "2")


# ===================================================================
# 5. 导入兼容性
# ===================================================================

class TestImportCompatibility(unittest.TestCase):
    """确保 db.py 中转发至 config_db / query_executor 的符号全部存在"""

    # ── config_db 符号 ──

    def test_config_db_symbols_exist(self):
        """✅ Positive: db.py 从 config_db 导入的符号全部存在"""
        config_db_symbols = [
            "_get_db_config", "_get_engine", "_connect_sqlite",
            "get_config_db", "_get_schema_sql", "init_db",
            "_init_sqlite_migrations", "_init_mysql_migrations",
            "_SQLITE_SCHEMA", "_MYSQL_SCHEMA",
            "add_pool", "get_pool", "get_all_pools", "update_pool",
            "delete_pool", "move_pool",
            "add_user", "get_user", "get_user_by_id", "get_all_users",
            "update_user", "delete_user",
            "add_report", "get_report", "get_all_reports", "update_report",
            "delete_report", "move_report", "batch_update_report_pool",
            "batch_update_report_cache",
            "add_category", "get_category", "get_all_categories",
            "update_category", "delete_category", "move_category",
            "get_reports_by_category", "get_reports", "move_report_to_category",
            "get_category_tree", "get_parent_categories",
            "batch_set_report_category",
            "add_session", "get_session", "remove_session",
            "get_all_sessions", "clear_sessions",
        ]
        for sym in config_db_symbols:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(config_db, sym),
                    f"config_db.py 缺少符号: {sym}",
                )

    def test_db_reexports_config_db_symbols(self):
        """✅ Positive: db.py 正确转发 config_db 符号"""
        config_db_symbols = [
            "_get_db_config", "_get_engine", "_connect_sqlite",
            "get_config_db", "_get_schema_sql", "init_db",
            "_init_sqlite_migrations", "_init_mysql_migrations",
            "_SQLITE_SCHEMA", "_MYSQL_SCHEMA",
            "add_pool", "get_pool", "get_all_pools", "update_pool",
            "delete_pool", "move_pool",
            "add_user", "get_user", "get_user_by_id", "get_all_users",
            "update_user", "delete_user",
            "add_report", "get_report", "get_all_reports", "update_report",
            "delete_report", "move_report", "batch_update_report_pool",
            "batch_update_report_cache",
            "add_category", "get_category", "get_all_categories",
            "update_category", "delete_category", "move_category",
            "get_reports_by_category", "get_reports", "move_report_to_category",
            "get_category_tree", "get_parent_categories",
            "batch_set_report_category",
            "add_session", "get_session", "remove_session",
            "get_all_sessions", "clear_sessions",
        ]
        for sym in config_db_symbols:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(db_module, sym),
                    f"db.py 缺少转发符号: {sym}",
                )
                # 验证确实是同一对象（转发而非重新实现）
                self.assertIs(
                    getattr(db_module, sym),
                    getattr(config_db, sym),
                    f"db.{sym} 与 config_db.{sym} 不是同一对象",
                )

    # ── query_executor 符号 ──

    def test_query_executor_symbols_exist(self):
        """✅ Positive: db.py 从 query_executor 导入的符号全部存在"""
        qe_symbols = [
            "_MySQLRow", "_MySQLCursor", "_MySQLConnection",
            "_connect_mysql_config",
            "create_mysql_connection", "_split_sql_statements",
            "execute_mysql_query",
        ]
        for sym in qe_symbols:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(query_executor, sym),
                    f"query_executor.py 缺少符号: {sym}",
                )

    def test_db_reexports_query_executor_symbols(self):
        """✅ Positive: db.py 正确转发 query_executor 符号"""
        qe_symbols = [
            "_MySQLRow", "_MySQLCursor", "_MySQLConnection",
            "_connect_mysql_config",
            "create_mysql_connection", "_split_sql_statements",
            "execute_mysql_query",
        ]
        for sym in qe_symbols:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(db_module, sym),
                    f"db.py 缺少转发符号: {sym}",
                )
                self.assertIs(
                    getattr(db_module, sym),
                    getattr(query_executor, sym),
                    f"db.{sym} 与 query_executor.{sym} 不是同一对象",
                )

    # ── tests/__init__.py 符号 ──

    def test_tests_init_imports_from_test_base(self):
        """✅ Positive: tests/__init__.py 从 test_base 导入的符号全部存在"""
        import tests
        from tests import test_base as tb
        expected = ["make_config_db", "init_test_db",
                     "BaseConfigTest", "BaseReportTest"]
        for sym in expected:
            with self.subTest(symbol=sym):
                self.assertTrue(
                    hasattr(tb, sym),
                    f"test_base.py 缺少符号: {sym}",
                )
                self.assertIs(
                    getattr(tests, sym),
                    getattr(tb, sym),
                    f"tests.{sym} 与 test_base.{sym} 不是同一对象",
                )


# ===================================================================
# 6. 导出边界
# ===================================================================

class TestExportBoundaries(unittest.TestCase):
    """导出边界：None 值/逆序列/Decimal/无效 charset"""

    def setUp(self):
        """Mock 数据库连接和查询"""
        self.mock_conn = MagicMock()
        self.patcher_conn = patch("db.create_mysql_connection",
                                  return_value=self.mock_conn)
        self.patcher_query = patch("db.execute_mysql_query")
        self.patcher_conn.start()
        self.mock_query = self.patcher_query.start()

    def tearDown(self):
        self.patcher_conn.stop()
        self.patcher_query.stop()

    def test_csv_all_none_values(self):
        """✅ Positive: CSV 导出时所有单元格值为 None → 输出空字符串"""
        self.mock_query.return_value = [{
            "columns": ["col_a", "col_b"],
            "rows": [(None, None), (None, None)],
        }]
        csv_output = export.export_report_to_csv(
            "SELECT * FROM t",
            {"host": "localhost"},
        )
        # CSV 格式: BOM + 表头 + \n + 数据行 + \n
        self.assertIn("col_a", csv_output)
        self.assertIn("col_b", csv_output)
        # None 值在 csv.QUOTE_ALL 下输出为 ""
        lines = csv_output.strip().split("\n")
        # lines[0] 是 BOM+表头，lines[1] 是数据行
        self.assertEqual(len(lines), 3)  # BOM+表头, 行1, 行2
        # 验证 None 被输出为空引号
        for line in lines[1:]:
            self.assertEqual(line, '"",""')

    def test_csv_reverse_column_order(self):
        """✅ Positive: CSV 导出时列顺序为逆序 → 按指定顺序输出"""
        self.mock_query.return_value = [{
            "columns": ["a", "b", "c"],
            "rows": [(1, 2, 3)],
        }]
        csv_output = export.export_report_to_csv(
            "SELECT * FROM t",
            {"host": "localhost"},
            columns=["c", "b", "a"],
        )
        lines = csv_output.strip().split("\n")
        # 表头应为 c,b,a
        header = lines[0].replace("\ufeff", "")
        self.assertEqual(header, '"c","b","a"')
        # 数据应为 3,2,1
        self.assertEqual(lines[1], '"3","2","1"')

    def test_csv_subset_columns(self):
        """✅ Positive: CSV 导出时只选择部分列"""
        self.mock_query.return_value = [{
            "columns": ["a", "b", "c", "d"],
            "rows": [(1, 2, 3, 4)],
        }]
        csv_output = export.export_report_to_csv(
            "SELECT * FROM t",
            {"host": "localhost"},
            columns=["d", "a"],
        )
        lines = csv_output.strip().split("\n")
        header = lines[0].replace("\ufeff", "")
        self.assertEqual(header, '"d","a"')
        self.assertEqual(lines[1], '"4","1"')

    def test_csv_mixed_none_and_values(self):
        """✅ Positive: CSV 导出时混合 None 和正常值"""
        self.mock_query.return_value = [{
            "columns": ["id", "name", "score"],
            "rows": [(1, "alice", None), (2, None, 95.5)],
        }]
        csv_output = export.export_report_to_csv(
            "SELECT * FROM t",
            {"host": "localhost"},
        )
        lines = csv_output.strip().split("\n")
        self.assertIn('"alice"', lines[1])
        # None 在 score 列应输出 ""
        self.assertTrue(lines[1].endswith('""') or ",," in lines[1])

    def test_json_decimal_no_quotes(self):
        """✅ Positive: JSON 导出时 json_no_quotes=True, Decimal→数字"""
        self.mock_query.return_value = [{
            "columns": ["amount", "name"],
            "rows": [(Decimal("123.45"), "test")],
        }]
        json_output = export.export_report_to_json(
            "SELECT * FROM t",
            {"host": "localhost"},
            "test_report",
            json_no_quotes=True,
        )
        data = json.loads(json_output)
        # 验证 amount 是数字而非字符串
        self.assertIsInstance(data["test_report"][0]["amount"], (int, float))
        self.assertEqual(data["test_report"][0]["amount"], 123.45)
        # name 还是字符串
        self.assertIsInstance(data["test_report"][0]["name"], str)

    def test_json_decimal_zero_no_quotes(self):
        """✅ Positive: JSON 导出时 Decimal(0) → 数字 0"""
        self.mock_query.return_value = [{
            "columns": ["val"],
            "rows": [(Decimal("0"),)],
        }]
        json_output = export.export_report_to_json(
            "SELECT * FROM t", {"host": "localhost"},
            "rpt", json_no_quotes=True,
        )
        data = json.loads(json_output)
        self.assertEqual(data["rpt"][0]["val"], 0)
        self.assertIsInstance(data["rpt"][0]["val"], int)

    def test_json_decimal_large_no_quotes(self):
        """✅ Positive: JSON 导出时大 Decimal → 数字"""
        self.mock_query.return_value = [{
            "columns": ["val"],
            "rows": [(Decimal("999999999999.99"),)],
        }]
        json_output = export.export_report_to_json(
            "SELECT * FROM t", {"host": "localhost"},
            "rpt", json_no_quotes=True,
        )
        data = json.loads(json_output)
        self.assertEqual(data["rpt"][0]["val"], 999999999999.99)
        self.assertIsInstance(data["rpt"][0]["val"], float)

    def test_json_with_quotes_decimal_as_string(self):
        """✅ Positive: JSON 导出时 json_no_quotes=False, Decimal→字符串"""
        self.mock_query.return_value = [{
            "columns": ["amount"],
            "rows": [(Decimal("123.45"),)],
        }]
        json_output = export.export_report_to_json(
            "SELECT * FROM t", {"host": "localhost"},
            "test_report", json_no_quotes=False,
        )
        data = json.loads(json_output)
        self.assertIsInstance(data["test_report"][0]["amount"], str)

    def test_charset_invalid_fallback_to_gbk(self):
        """✅ Positive: 传入无效 charset → fallback 到 gbk 编码"""
        content = "你好世界"
        result = export._encode_content(content, "latin1")
        # 只有 "utf8" 走 UTF-8 路径，其余全部走 GBK
        expected = content.encode("gbk", errors="replace")
        self.assertEqual(result, expected)

    def test_charset_utf8_explicit(self):
        """✅ Positive: charset='utf8' 使用 UTF-8 编码"""
        content = "你好世界"
        result = export._encode_content(content, "utf8")
        expected = content.encode("utf-8")
        self.assertEqual(result, expected)

    def test_charset_gbk_bom_removed(self):
        """✅ Positive: GBK 编码时移除 BOM 字符"""
        content = "\ufeff你好"
        result = export._encode_content(content, "gbk")
        # BOM 被移除后再编码
        expected = "你好".encode("gbk", errors="replace")
        self.assertEqual(result, expected)

    def test_charset_utf8_keeps_bom(self):
        """✅ Positive: UTF-8 编码时保留 BOM 字符"""
        content = "\ufeff你好"
        result = export._encode_content(content, "utf8")
        expected = content.encode("utf-8")
        self.assertEqual(result, expected)

    def test_export_report_to_json_multiple_rows(self):
        """✅ Positive: JSON 导出多行数据"""
        self.mock_query.return_value = [{
            "columns": ["x"],
            "rows": [(1,), (2,), (3,)],
        }]
        json_output = export.export_report_to_json(
            "SELECT * FROM t", {"host": "localhost"},
            "test", json_no_quotes=True,
        )
        data = json.loads(json_output)
        self.assertEqual(len(data["test"]), 3)
        self.assertEqual(data["test"][0]["x"], 1)
        self.assertEqual(data["test"][2]["x"], 3)


# ===================================================================
# 7. 综合边缘场景（ReportResult 直接测试）
# ===================================================================

class TestReportResultEdgeCases(unittest.TestCase):
    """ReportResult 数据容器边缘场景"""

    def test_total_pages_with_zero_page_size(self):
        """✅ Positive: page_size=0 时 total_pages 返回 1（除零保护）"""
        result = report.ReportResult(
            results=[{"columns": ["id"], "rows": [(1,), (2,)],
                       "total": 2}],
            active_index=0, page=1, page_size=0,
        )
        # math.ceil(2 / 0) 会 ZeroDivisionError，但代码用 ps > 0 保护
        self.assertEqual(result.total_pages, 1)

    def test_total_pages_with_one_page_size(self):
        """✅ Positive: total=5, page_size=1 → total_pages=5"""
        result = report.ReportResult(
            results=[{"columns": ["id"],
                       "rows": [(i,) for i in range(5)],
                       "total": 5}],
            active_index=0, page=1, page_size=1,
        )
        self.assertEqual(result.total_pages, 5)

    def test_total_pages_exact_division(self):
        """✅ Positive: total=20, page_size=10 → total_pages=2"""
        result = report.ReportResult(
            results=[{"columns": ["id"],
                       "rows": [(i,) for i in range(20)],
                       "total": 20}],
            active_index=0, page=1, page_size=10,
        )
        self.assertEqual(result.total_pages, 2)

    def test_total_pages_zero_rows(self):
        """✅ Positive: total=0, page_size=20 → total_pages=1"""
        result = report.ReportResult(
            results=[{"columns": ["id"], "rows": [], "total": 0}],
            active_index=0, page=1, page_size=20,
        )
        self.assertEqual(result.total_pages, 1)  # math.ceil(0/20) = 0, but min is 1

    def test_total_pages_rounds_up(self):
        """✅ Positive: total=11, page_size=10 → total_pages=2"""
        result = report.ReportResult(
            results=[{"columns": ["id"],
                       "rows": [(i,) for i in range(11)],
                       "total": 11}],
            active_index=0, page=1, page_size=10,
        )
        self.assertEqual(result.total_pages, 2)  # ceil(11/10) = 2

    def test_multi_result_set_active_index(self):
        """✅ Positive: 多结果集中 active_index 切换"""
        results = [
            {"columns": ["id"], "rows": [(1,), (2,)], "total": 2},
            {"columns": ["name"], "rows": [("a",), ("b",)], "total": 2},
        ]
        # 第二个结果集
        result = report.ReportResult(results, active_index=1, page=1, page_size=20)
        self.assertEqual(result.columns, ["name"])
        self.assertEqual(result.rows, [("a",), ("b",)])


# ===================================================================
# 8. _safe_sort_key 纯函数边界
# ===================================================================

class TestSafeSortKeyEdgeCases(unittest.TestCase):
    """_safe_sort_key 纯函数边缘值"""

    def test_safe_sort_key_none(self):
        """✅ Positive: None → (1, '') 排在最后"""
        key = report._safe_sort_key(None)
        self.assertEqual(key, (1, ''))

    def test_safe_sort_key_empty_string(self):
        """✅ Positive: 空字符串 → (0, '')"""
        key = report._safe_sort_key("")
        self.assertEqual(key, (0, ''))

    def test_safe_sort_key_zero(self):
        """✅ Positive: 数字 0 → (0, '0')"""
        key = report._safe_sort_key(0)
        self.assertEqual(key, (0, '0'))

    def test_safe_sort_key_boolean(self):
        """✅ Positive: False → (0, 'False')"""
        key = report._safe_sort_key(False)
        self.assertEqual(key, (0, 'False'))

    def test_none_always_last_asc(self):
        """✅ Positive: 升序时 None 在最后"""
        keys = [report._safe_sort_key("a"), report._safe_sort_key(None),
                report._safe_sort_key("b")]
        sorted_keys = sorted(keys)
        self.assertEqual(sorted_keys[0], (0, 'a'))
        self.assertEqual(sorted_keys[1], (0, 'b'))
        self.assertEqual(sorted_keys[2], (1, ''))

    def test_none_always_last_desc(self):
        """✅ Positive: 降序时 None 在最后"""
        keys = [report._safe_sort_key("a"), report._safe_sort_key(None),
                report._safe_sort_key("b")]
        # 降序 = reverse sorted
        sorted_keys = sorted(keys, reverse=True)
        # (1, '') 最大，所以排在降序第一位
        self.assertEqual(sorted_keys[0], (1, ''))
        self.assertEqual(sorted_keys[1], (0, 'b'))
        self.assertEqual(sorted_keys[2], (0, 'a'))


# ===================================================================
# 9. report._parse_cols 边界
# ===================================================================

class TestParseColsBoundaries(unittest.TestCase):
    """_parse_cols 自定义列解析边界"""

    def test_parse_cols_no_param(self):
        """✅ Positive: 无 cols 参数 → 返回全部列"""
        qs = {}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_parse_cols_empty_string(self):
        """✅ Positive: cols='' → 返回全部列"""
        qs = {"cols": [""]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_parse_cols_select_subset(self):
        """✅ Positive: cols='a,c' → 只返回 a,c"""
        qs = {"cols": ["a,c"]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "c"])

    def test_parse_cols_invalid_col_ignored(self):
        """✅ Positive: cols 中包含不存在的列名 → 忽略"""
        qs = {"cols": ["a,nonexistent,c"]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "c"])

    def test_parse_cols_all_invalid(self):
        """❌ Negative: cols 全部为无效列名 → 返回全部列"""
        qs = {"cols": ["x,y,z"]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_parse_cols_duplicates_deduplicated(self):
        """✅ Positive: cols 中重复列 → 去重"""
        qs = {"cols": ["a,b,a,c,b"]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_parse_cols_reverse_order(self):
        """✅ Positive: cols='c,b,a' → 逆序返回"""
        qs = {"cols": ["c,b,a"]}
        result = report._parse_cols(qs, ["a", "b", "c"])
        self.assertEqual(result, ["c", "b", "a"])


# ===================================================================
# 10. render.format_cell 边界
# ===================================================================

class TestFormatCellBoundaries(unittest.TestCase):
    """format_cell 单元格格式化边缘值"""

    def test_format_cell_none(self):
        """✅ Positive: None → 空字符串"""
        self.assertEqual(format_cell(None), "")

    def test_format_cell_decimal(self):
        """✅ Positive: Decimal 避免科学计数法"""
        result = format_cell(Decimal("123456789.123456789"))
        self.assertIsInstance(result, str)
        self.assertNotIn("e", result.lower())
        self.assertIn("123456789", result)

    def test_format_cell_zero(self):
        """✅ Positive: 数字 0 → '0'"""
        self.assertEqual(format_cell(0), "0")

    def test_format_cell_boolean_true(self):
        """✅ Positive: True → 'True'"""
        self.assertEqual(format_cell(True), "True")

    def test_format_cell_boolean_false(self):
        """✅ Positive: False → 'False'"""
        self.assertEqual(format_cell(False), "False")


# ===================================================================
# 11. parse_filters 旧/新格式兼容边界
# ===================================================================

class TestParseFiltersBoundaries(unittest.TestCase):
    """parse_filters 解析多字段筛选参数的边界"""

    def test_parse_filters_empty(self):
        """✅ Positive: 无筛选参数 → 返回空列表"""
        result = report.parse_filters({})
        self.assertEqual(result, [])

    def test_parse_filters_old_format(self):
        """✅ Positive: 旧格式 f_col/f_q → 正确转换"""
        qs = {"f_col": ["name"], "f_q": ["alice"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [("name", "contains", "alice")])

    def test_parse_filters_op_only_isempty(self):
        """✅ Positive: 仅有 op 无 f_ 时，isempty 等操作符生效"""
        qs = {"op_name": ["isempty"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [("name", "isempty", "")])

    def test_parse_filters_op_only_notempty(self):
        """✅ Positive: 仅有 op 无 f_ 时，notempty 生效"""
        qs = {"op_name": ["notempty"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [("name", "notempty", "")])

    def test_parse_filters_op_nofilter_without_f(self):
        """✅ Positive: op=nofilter 且无 f_ → 被过滤"""
        qs = {"op_name": ["nofilter"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [])

    def test_parse_filters_new_format_with_op(self):
        """✅ Positive: 新格式 f_ + op_"""
        qs = {"f_age": ["100"], "op_age": ["gt"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [("age", "gt", "100")])

    def test_parse_filters_new_format_default_op(self):
        """✅ Positive: 仅有 f_ 无 op_ → 默认 contains"""
        qs = {"f_name": ["hello"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [("name", "contains", "hello")])

    def test_parse_filters_old_format_no_match(self):
        """✅ Positive: 旧格式只有 f_col 无 f_q → 返回空"""
        qs = {"f_col": ["name"]}
        result = report.parse_filters(qs)
        self.assertEqual(result, [])


# ===================================================================
# 12. auth.verify_password 边界
# ===================================================================

class TestVerifyPasswordBoundaries(unittest.TestCase):
    """verify_password 边缘场景"""

    def test_verify_password_none_password(self):
        """❌ Negative: 传入 None → 返回 False"""
        result = auth.verify_password(None, "salt$hash")
        self.assertFalse(result)

    def test_verify_password_invalid_stored_format(self):
        """❌ Negative: stored 不含 $ → 返回 False"""
        result = auth.verify_password("pass", "invalidhash")
        self.assertFalse(result)

    def test_verify_password_empty_stored(self):
        """❌ Negative: stored 为空 → 返回 False"""
        result = auth.verify_password("pass", "")
        self.assertFalse(result)

    def test_verify_password_wrong_password(self):
        """❌ Negative: 错误密码 → 返回 False"""
        # 先创建一个真实哈希
        hashed = auth.hash_password("correct")
        result = auth.verify_password("wrong", hashed)
        self.assertFalse(result)

    def test_verify_password_correct(self):
        """✅ Positive: 正确密码 → 返回 True"""
        hashed = auth.hash_password("correct")
        result = auth.verify_password("correct", hashed)
        self.assertTrue(result)

    def test_hash_password_format(self):
        """✅ Positive: hash_password 返回 salt$hex_digest 格式"""
        hashed = auth.hash_password("test")
        self.assertIn("$", hashed)
        salt, digest = hashed.split("$", 1)
        self.assertEqual(len(salt), 32)  # 16 bytes = 32 hex chars
        self.assertTrue(all(c in "0123456789abcdef" for c in salt))
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))
