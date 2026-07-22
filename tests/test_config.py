"""
test_config.py — config.py 单元测试

测试策略：
- 使用 :memory: SQLite，每条测试独立
- 测试 URL 解析、HTML 渲染、表单提交处理
"""

import unittest
import sqlite3
import config
import db
import auth


def _make_conn():
    """创建带完整表结构的测试内存数据库"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL,
            password TEXT NOT NULL,
            database TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE report_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL,
            default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER,
            category_id INTEGER,
            memo TEXT,
            result_names TEXT DEFAULT '',
            prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (pool_id) REFERENCES connection_pools(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES report_categories(id) ON DELETE SET NULL
        );
        CREATE TABLE api_endpoints (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id        INTEGER NOT NULL,
            name             TEXT    NOT NULL,
            url_path         TEXT    UNIQUE NOT NULL,
            output_format    TEXT    NOT NULL DEFAULT 'json',
            columns          TEXT,
            filters          TEXT,
            sorts            TEXT,
            row_limit        INTEGER DEFAULT 0,
            api_key          TEXT,
            allowed_origins  TEXT,
            enabled          INTEGER NOT NULL DEFAULT 1,
            result_mode      TEXT    NOT NULL DEFAULT 'single',
            result_index     INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
        );
    """)
    return conn


class TestPathParsing(unittest.TestCase):
    """URL 路径解析测试"""

    def _e(self, section, action, id_val, report_id=None, endpoint_id=None):
        """辅助构建期望的路径解析结果。"""
        return {"section": section, "action": action, "id": id_val,
                "report_id": report_id, "endpoint_id": endpoint_id}

    def test_overview_path(self):
        self.assertEqual(config.parse_config_path("/config"),
                         self._e(None, "overview", None))
        self.assertEqual(config.parse_config_path("/config/"),
                         self._e(None, "overview", None))

    def test_pool_add_path(self):
        self.assertEqual(config.parse_config_path("/config/pools/add"),
                         self._e("pools", "add", None))

    def test_pool_edit_path(self):
        self.assertEqual(config.parse_config_path("/config/pools/5/edit"),
                         self._e("pools", "edit", 5))

    def test_pool_delete_path(self):
        self.assertEqual(config.parse_config_path("/config/pools/3/delete"),
                         self._e("pools", "delete", 3))

    def test_user_add_path(self):
        self.assertEqual(config.parse_config_path("/config/users/add"),
                         self._e("users", "add", None))

    def test_report_edit_path(self):
        self.assertEqual(config.parse_config_path("/config/reports/7/edit"),
                         self._e("reports", "edit", 7))

    def test_unmatched_path(self):
        result = config.parse_config_path("/config/unknown/123")
        self.assertEqual(result["action"], None)


class TestPoolFlow(unittest.TestCase):
    """连接池配置流程测试"""

    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def test_overview_contains_pool_section(self):
        """总览页面应包含连接池配置区块"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config", "")
        self.assertEqual(code, "200")
        self.assertIn("连接池配置", body)
        self.assertIn("新增连接池", body)

    def test_add_pool_form(self):
        """新增连接池表单页面应包含表单元素"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config/pools/add", "")
        self.assertEqual(code, "200")
        self.assertIn("新增连接池", body)
        self.assertIn('name="name"', body)
        self.assertIn('name="host"', body)
        self.assertIn('name="port"', body)
        self.assertIn('name="password"', body)
        self.assertIn('method="post"', body)

    def test_submit_add_pool(self):
        """提交新增连接池应成功并重定向"""
        form = "name=生产库&host=10.0.0.1&port=3306&user=root&password=secret&database=mydb"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, "302")
        self.assertIn("Location", headers)
        # 验证数据库
        pools = db.get_all_pools(self.conn)
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "生产库")

    def test_submit_add_pool_duplicate(self):
        """重复名称应回到表单页并显示错误"""
        db.add_pool(self.conn, "dup", "h", 3306, "u", "p", "d")
        form = "name=dup&host=h2&port=3306&user=u2&password=p2&database=d2"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, "200")  # 返回表单页
        self.assertIn("错误", body)

    def test_edit_pool_form(self):
        """编辑连接池表单应回填数据"""
        pid = db.add_pool(self.conn, "要改的池", "host1", 3306, "user1", "pass1", "db1")
        code, body, _ = config.handle_request(self.conn, "GET", f"/config/pools/{pid}/edit", "")
        self.assertEqual(code, "200")
        self.assertIn("编辑连接池", body)
        self.assertIn("host1", body)
        self.assertIn("user1", body)

    def test_submit_edit_pool(self):
        """提交编辑连接池应更新"""
        pid = db.add_pool(self.conn, "old", "host1", 3306, "u", "p", "d")
        form = "name=改后&host=host2&port=3307&user=u2&password=&database=d2"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/pools/{pid}/edit", "", form)
        self.assertEqual(code, "302")
        pool = db.get_pool(self.conn, pid)
        self.assertEqual(pool["name"], "改后")
        # 密码未提供，应保留原密码
        self.assertEqual(pool["password"], "p")

    def test_edit_nonexistent_pool(self):
        """编辑不存在的连接池应重定向"""
        form = "name=x&host=x&port=3306&user=x&password=x&database=x"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/pools/999/edit", "", form)
        self.assertEqual(code, "302")

    def test_delete_pool(self):
        """删除连接池"""
        pid = db.add_pool(self.conn, "待删", "h", 3306, "u", "p", "d")
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/pools/{pid}/delete", "", "")
        self.assertEqual(code, "302")
        self.assertIsNone(db.get_pool(self.conn, pid))


class TestUserFlow(unittest.TestCase):
    """用户配置流程测试"""

    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def test_overview_contains_user_section(self):
        code, body, _ = config.handle_request(self.conn, "GET", "/config", "")
        self.assertIn("用户配置", body)

    def test_submit_add_user(self):
        form = "username=alice&password=pass123"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/users/add", "", form)
        self.assertEqual(code, "302")
        users = db.get_all_users(self.conn)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "alice")
        # 密码应被哈希存储
        self.assertTrue(auth.verify_password("pass123", users[0]["password_hash"]))

    def test_submit_edit_user(self):
        h = auth.hash_password("oldpw")
        uid = db.add_user(self.conn, "bob", h)
        form = "username=bob_new&password=newpw"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/users/{uid}/edit", "", form)
        self.assertEqual(code, "302")
        user = db.get_user_by_id(self.conn, uid)
        self.assertEqual(user["username"], "bob_new")
        self.assertTrue(auth.verify_password("newpw", user["password_hash"]))

    def test_delete_user(self):
        uid = db.add_user(self.conn, "del", auth.hash_password("pw"))
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/users/{uid}/delete", "", "")
        self.assertEqual(code, "302")
        self.assertIsNone(db.get_user_by_id(self.conn, uid))

    def test_add_duplicate_user(self):
        db.add_user(self.conn, "dup", auth.hash_password("pw"))
        form = "username=dup&password=other"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/users/add", "", form)
        self.assertEqual(code, "200")
        self.assertIn("错误", body)


class TestReportFlow(unittest.TestCase):
    """报表配置流程测试"""

    def setUp(self):
        self.conn = _make_conn()
        # 准备一个连接池供报表使用
        db.add_pool(self.conn, "报表池", "h", 3306, "u", "p", "d")

    def tearDown(self):
        self.conn.close()

    def test_overview_contains_report_section(self):
        code, body, _ = config.handle_request(self.conn, "GET", "/config", "")
        self.assertIn("报表分类", body)

    def test_add_report_form_contains_pool_select(self):
        """新增报表表单应包含连接池下拉选择"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config/reports/add", "")
        self.assertIn("报表池", body)
        self.assertIn('name="pool_id"', body)

    def test_submit_add_report(self):
        form = "name=销售报表&sql_query=SELECT * FROM sales&default_page_size=30&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, "302")
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["name"], "销售报表")
        self.assertEqual(reports[0]["default_page_size"], 30)

    def test_submit_edit_report(self):
        rid = db.add_report(self.conn, "旧报表", "SELECT 1", 20, 1)
        form = "name=新报表&sql_query=SELECT 2&default_page_size=50&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, "302")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["name"], "新报表")
        self.assertEqual(rpt["default_page_size"], 50)

    def test_delete_report(self):
        rid = db.add_report(self.conn, "待删报表", "SELECT 1", 20, 1)
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/delete", "", "")
        self.assertEqual(code, "302")
        self.assertIsNone(db.get_report(self.conn, rid))

    def test_submit_add_report_without_pool(self):
        """提交时指定不存在的连接池应报错（外键约束）"""
        form = "name=坏报表&sql_query=SELECT 1&default_page_size=20&pool_id=999"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, "200")
        self.assertIn("错误", body)

    def test_add_report_form_contains_memo(self):
        """新增报表表单应包含备注 textarea"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config/reports/add", "")
        self.assertIn('name="memo"', body)
        self.assertIn("备注", body)

    def test_submit_add_report_with_memo(self):
        """提交带备注的报表应正确存储"""
        form = ("name=备注报表&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&memo=这是报表的备注说明")
        code, body, headers = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, "302")
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["memo"], "这是报表的备注说明")

    def test_edit_report_form_prefills_memo(self):
        """编辑报表表单应回填备注值"""
        rid = db.add_report(self.conn, "备注报表", "SELECT 1", 20, 1, memo="已有备注")
        code, body, _ = config.handle_request(self.conn, "GET", f"/config/reports/{rid}/edit", "")
        self.assertIn("已有备注", body)

    def test_submit_edit_report_with_memo(self):
        """编辑报表时更新备注应生效"""
        rid = db.add_report(self.conn, "改备注", "SELECT 1", 20, 1, memo="旧备注")
        form = "name=改备注&sql_query=SELECT 1&default_page_size=20&pool_id=1&memo=新备注"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, "302")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["memo"], "新备注")

    def test_submit_add_report_without_memo(self):
        """提交不带备注的报表，memo 应存为 None"""
        form = "name=无备注&sql_query=SELECT 1&default_page_size=20&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, "302")
        reports = db.get_all_reports(self.conn)
        self.assertIsNone(reports[0]["memo"])


    def test_submit_edit_report_redis_cache_enabled(self):
        """编辑报表时勾选 Redis 缓存应正确保存 prefer_cache=1（hidden+checkbox 同时提交时的 v[-1] 修复验证）"""
        rid = db.add_report(self.conn, "缓存报表", "SELECT 1", 20, 1, prefer_cache=0, cache_ttl_hours=0)
        # 模拟浏览器提交：hidden(0) + checkbox(1) + ttl
        form = "name=缓存报表&sql_query=SELECT 1&default_page_size=20&pool_id=1&prefer_cache=0&prefer_cache=1&cache_ttl_hours=24"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, "302")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["prefer_cache"], 1)
        self.assertEqual(rpt["cache_ttl_hours"], 24)

    def test_submit_edit_report_redis_cache_disabled(self):
        """编辑报表时取消勾选 Redis 缓存应正确保存 prefer_cache=0"""
        rid = db.add_report(self.conn, "无缓存报表", "SELECT 1", 20, 1, prefer_cache=1, cache_ttl_hours=24)
        # 模拟浏览器提交：仅 hidden(0) 提交（checkbox 未勾选时不提交）
        form = "name=无缓存报表&sql_query=SELECT 1&default_page_size=20&pool_id=1&prefer_cache=0&cache_ttl_hours=0"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, "302")
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["prefer_cache"], 0)
        self.assertEqual(rpt["cache_ttl_hours"], 0)


class TestFlashMessage(unittest.TestCase):
    """Flash 消息传递测试"""

    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def test_flash_shown_on_overview(self):
        """查询参数 flash 应在总览页展示"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config", "flash=操作成功")
        self.assertIn("操作成功", body)


class TestUnknownAction(unittest.TestCase):
    """未知路径应返回 302 到 /config"""

    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def test_unknown_path(self):
        code, body, headers = config.handle_request(self.conn, "GET", "/config/unknown/action", "")
        self.assertEqual(code, "302")


class TestChineseRedirect(unittest.TestCase):
    """中文 Flash 消息重定向的 URL 编码测试"""

    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def test_chinese_flash_is_urlencoded(self):
        """中文 flash 消息在 Location 中应为 URL 编码"""
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")
        form = "name=销售报表&sql_query=SELECT 1&default_page_size=20&pool_id=1"
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, "302")
        location = headers.get("Location", "")
        # 中文 "销售报表" 应被编码为 %xx%xx%xx%xx
        self.assertNotIn("销售报表", location)
        self.assertIn("%", location)
        self.assertTrue(location.startswith("/config?flash="))

    def test_ascii_flash_unchanged(self):
        """纯英文 flash 消息不额外编码"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/999/delete", "", "")
        self.assertEqual(code, "302")
        location = headers.get("Location", "")
        self.assertIn("/config?flash=", location)


class TestReportFormButtons(unittest.TestCase):
    """报表编辑表单【查看】和【预览】按钮测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")

    def tearDown(self):
        self.conn.close()

    def test_edit_form_has_view_button(self):
        """编辑报表表单应包含【查看】按钮，链接到 /report?id={id}"""
        rid = db.add_report(self.conn, "可查看报表", "SELECT 1", 20, 1)
        code, body, _ = config.handle_request(self.conn, "GET",
                                               f"/config/reports/{rid}/edit", "")
        self.assertEqual(code, "200")
        self.assertIn(f'/report?id={rid}', body)
        self.assertIn('查看', body)
        self.assertIn('target="_blank"', body)
        self.assertIn('rel="noopener"', body)

    def test_edit_form_has_preview_button(self):
        """编辑报表表单应包含【预览】按钮"""
        rid = db.add_report(self.conn, "可预览报表", "SELECT 1", 20, 1)
        code, body, _ = config.handle_request(self.conn, "GET",
                                               f"/config/reports/{rid}/edit", "")
        self.assertIn('预览', body)
        self.assertIn("previewReport(this.form)", body)
        self.assertIn("/report/preview", body)

    def test_add_form_has_no_view_or_preview_button(self):
        """新增报表表单不应包含【查看】和【预览】按钮"""
        code, body, _ = config.handle_request(self.conn, "GET",
                                               "/config/reports/add", "")
        self.assertNotIn('onclick="previewReport(this.form)"', body)
        self.assertNotIn('name="id"', body)
        # "查看"链接（target="_blank"）在 JS 高亮预览功能中存在，判断方式改为检查具体按钮
        self.assertNotIn('/report?id=', body)

    def test_edit_form_has_hidden_id_input(self):
        """编辑报表表单应包含隐藏的 id 输入"""
        rid = db.add_report(self.conn, "ID测试", "SELECT 1", 20, 1)
        code, body, _ = config.handle_request(self.conn, "GET",
                                               f"/config/reports/{rid}/edit", "")
        self.assertIn(f'value="{rid}"', body)
        self.assertIn('type="hidden"', body)
        self.assertIn('name="id"', body)


# ===================================================================
# API 端点规则 JSON 测试
# ===================================================================


class TestApiEndpointRuleJsonFlow(unittest.TestCase):
    """API 端点 rule_json 输入/输出测试"""

    def setUp(self):
        self.conn = _make_conn()
        db.add_pool(self.conn, "API池", "h", 3306, "u", "p", "d")
        db.add_report(self.conn, "API报表", "SELECT 1", 20, 1)

    def tearDown(self):
        self.conn.close()

    def test_create_with_full_rule_json(self):
        """创建 API 端点时传入完整 rule_json，验证三字段正确拆分存储"""
        form = ("name=测试端点&url_path=/test&output_format=json"
                "&rule_json={\"filters\":[{\"col\":\"status\",\"op\":\"eq\",\"val\":\"active\"}],"
                "\"sorts\":[{\"col\":\"created_at\",\"dir\":\"desc\"}],"
                "\"columns\":\"id,name\"}"
                "&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/1/api_endpoints/new", "", form)
        self.assertEqual(code, "302")
        endpoints = db.get_api_endpoints_by_report(self.conn, 1)
        self.assertEqual(len(endpoints), 1)
        ep = endpoints[0]
        self.assertEqual(ep["columns"], "id,name")
        self.assertIn("status", ep["filters"])
        self.assertIn("desc", ep["sorts"])

    def test_create_with_partial_rule_json(self):
        """传入只含 filters 的部分 JSON，验证其他字段为空"""
        form = ("name=部分规则&url_path=/partial&output_format=json"
                "&rule_json={\"filters\":[{\"col\":\"age\",\"op\":\"gt\",\"val\":\"18\"}]}"
                "&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/1/api_endpoints/new", "", form)
        self.assertEqual(code, "302")
        ep = db.get_api_endpoints_by_report(self.conn, 1)[0]
        self.assertIn("age", ep["filters"])
        self.assertIsNone(ep["columns"])
        self.assertIsNone(ep["sorts"])

    def test_create_with_empty_json(self):
        """传入空 JSON，验证三个字段均为空"""
        form = ("name=空规则&url_path=/empty&output_format=json"
                "&rule_json={}"
                "&row_limit=0&enabled=1")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/1/api_endpoints/new", "", form)
        self.assertEqual(code, "302")
        ep = db.get_api_endpoints_by_report(self.conn, 1)[0]
        self.assertIsNone(ep["columns"])
        self.assertIsNone(ep["filters"])
        self.assertIsNone(ep["sorts"])

    def test_edit_roundtrip(self):
        """创建后编辑加载，验证三字段正确拼回 rule_json"""
        # 先创建
        eid = db.add_api_endpoint(
            self.conn, 1, "往返端点", "/api/roundtrip",
            columns="id,name,email",
            filters='[{"col":"status","op":"eq","val":"active"}]',
            sorts='[{"col":"created_at","dir":"desc"}]',
        )
        # 编辑页面加载应含完整的 rule_json
        code, body, _ = config.handle_request(
            self.conn, "GET",
            f"/config/reports/1/api_endpoints/{eid}/edit", "")
        self.assertEqual(code, "200")
        self.assertIn('"id,name,email"', body)
        self.assertIn('"status"', body)
        self.assertIn('"created_at"', body)
        # 提交编辑也应正常工作
        form = ("name=往返端点改&url_path=/roundtrip&output_format=json"
                "&rule_json={\"columns\":\"id\",\"filters\":[],\"sorts\":[]}"
                "&row_limit=0&enabled=1")
        code2, body2, headers2 = config.handle_request(
            self.conn, "POST",
            f"/config/reports/1/api_endpoints/{eid}/edit", "", form)
        self.assertEqual(code2, "302")
        ep = db.get_api_endpoint(self.conn, eid)
        self.assertEqual(ep["name"], "往返端点改")
        self.assertEqual(ep["columns"], "id")


if __name__ == "__main__":
    unittest.main()
