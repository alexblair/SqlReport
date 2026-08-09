"""
test_config.py — config.py 单元测试

测试策略：
- 使用 :memory: SQLite，每条测试独立
- 测试 URL 解析、HTML 渲染、表单提交处理

PH-01 缓存新鲜度批次覆盖：
- 新建报表表单 cache_ttl_hours 默认 1
- 编辑存量报表表单回显原值（不重置为默认）
"""

import unittest
import sqlite3
import urllib.parse
import config
import db
import auth
from tests.test_base import BaseConfigTest


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
            sort_order INTEGER NOT NULL DEFAULT 0, allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1, max_rows INTEGER NOT NULL DEFAULT 100000,
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
            allow_fetch_all  INTEGER NOT NULL DEFAULT 1,
            static_cache    INTEGER NOT NULL DEFAULT 1,
            json_template   TEXT,
            description     TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (report_id) REFERENCES report_configs(id) ON DELETE CASCADE
        );
        CREATE TABLE api_keys (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NOT NULL,
            name        TEXT    NOT NULL,
            api_key     TEXT    NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (endpoint_id) REFERENCES api_endpoints(id) ON DELETE CASCADE
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
        self.assertEqual(code, 200)
        self.assertIn("连接池配置", body)
        self.assertIn("新增连接池", body)

    def test_add_pool_form(self):
        """新增连接池表单页面应包含表单元素"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config/pools/add", "")
        self.assertEqual(code, 200)
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
        self.assertEqual(code, 302)
        self.assertIn("Location", headers)
        # 验证数据库
        pools = db.get_all_pools(self.conn)
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "生产库")

    def test_submit_add_pool_action_save_stays_on_form(self):
        """新增连接池点【保存】应留在表单页（200），不关闭页面"""
        form = ("name=保存型连接池&host=h&port=3306&user=u&password=p&database=d"
                "&action=save")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("已创建", body)
        pools = db.get_all_pools(self.conn)
        self.assertEqual(len(pools), 1)
        self.assertIn(f'/config/pools/{pools[0]["id"]}/edit', body)

    def test_submit_edit_pool_action_save_stays_on_form(self):
        """编辑连接池点【保存】应留在表单页（200），不关闭页面"""
        pid = db.add_pool(self.conn, "待改连接池", "h", 3306, "u", "p", "d")
        form = ("name=保存型连接池&host=h&port=3306&user=u&password=p&database=d"
                "&action=save")
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/pools/{pid}/edit", "", form)
        self.assertEqual(code, 200)
        self.assertIn("已更新", body)
        self.assertIn(f'/config/pools/{pid}/edit', body)

    def test_submit_add_pool_duplicate(self):
        """重复名称应回到表单页并显示错误"""
        db.add_pool(self.conn, "dup", "h", 3306, "u", "p", "d")
        form = "name=dup&host=h2&port=3306&user=u2&password=p2&database=d2"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/pools/add", "", form)
        self.assertEqual(code, 200)  # 返回表单页
        self.assertIn("错误", body)

    def test_edit_pool_form(self):
        """编辑连接池表单应回填数据"""
        pid = db.add_pool(self.conn, "要改的池", "host1", 3306, "user1", "pass1", "db1")
        code, body, _ = config.handle_request(self.conn, "GET", f"/config/pools/{pid}/edit", "")
        self.assertEqual(code, 200)
        self.assertIn("编辑连接池", body)
        self.assertIn("host1", body)
        self.assertIn("user1", body)

    def test_submit_edit_pool(self):
        """提交编辑连接池应更新"""
        pid = db.add_pool(self.conn, "old", "host1", 3306, "u", "p", "d")
        form = "name=改后&host=host2&port=3307&user=u2&password=&database=d2"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/pools/{pid}/edit", "", form)
        self.assertEqual(code, 302)
        pool = db.get_pool(self.conn, pid)
        self.assertEqual(pool["name"], "改后")
        # 密码未提供，应保留原密码
        self.assertEqual(pool["password"], "p")

    def test_edit_nonexistent_pool(self):
        """编辑不存在的连接池应重定向"""
        form = "name=x&host=x&port=3306&user=x&password=x&database=x"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/pools/999/edit", "", form)
        self.assertEqual(code, 302)

    def test_delete_pool(self):
        """删除连接池"""
        pid = db.add_pool(self.conn, "待删", "h", 3306, "u", "p", "d")
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/pools/{pid}/delete", "", "")
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)
        user = db.get_user_by_id(self.conn, uid)
        self.assertEqual(user["username"], "bob_new")
        self.assertTrue(auth.verify_password("newpw", user["password_hash"]))

    def test_delete_user(self):
        uid = db.add_user(self.conn, "del", auth.hash_password("pw"))
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/users/{uid}/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIsNone(db.get_user_by_id(self.conn, uid))

    def test_add_duplicate_user(self):
        db.add_user(self.conn, "dup", auth.hash_password("pw"))
        form = "username=dup&password=other"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/users/add", "", form)
        self.assertEqual(code, 200)
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

    def test_add_report_form_default_ttl_one(self):
        """PH-01：新建报表表单 cache_ttl_hours 默认 1（避免永不过期）"""
        code, body, _ = config.handle_request(self.conn, "GET", "/config/reports/add", "")
        self.assertIn('name="cache_ttl_hours" value="1"', body)

    def test_edit_report_form_keeps_original_ttl(self):
        """PH-01：编辑存量报表表单回显原值，不重置为默认 1"""
        rid = db.add_report(self.conn, "TTL报表", "SELECT 1", 20, 1)
        self.conn.execute(
            "UPDATE report_configs SET cache_ttl_hours=5 WHERE id=?", (rid,))
        self.conn.commit()
        code, body, _ = config.handle_request(
            self.conn, "GET", f"/config/reports/{rid}/edit", "")
        self.assertIn('name="cache_ttl_hours" value="5"', body)

    def test_submit_add_report(self):
        form = "name=销售报表&sql_query=SELECT * FROM sales&default_page_size=30&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["name"], "销售报表")
        self.assertEqual(reports[0]["default_page_size"], 30)

    def test_submit_add_report_action_save_stays_on_form(self):
        """新建报表点【保存】应留在表单页（200），不关闭页面"""
        form = ("name=保存型报表&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&action=save")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
        self.assertIn("已创建", body)
        reports = db.get_all_reports(self.conn)
        self.assertEqual(len(reports), 1)

    def test_submit_add_report_action_save_close_redirects(self):
        """新建报表点【保存并关闭】应返回列表页（302）"""
        form = ("name=关闭型报表&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&action=save_close")
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        self.assertIn("/config", body)

    def test_submit_copy_report_action_save_stays_on_form(self):
        """复制报表点【保存】应留在新报表编辑页（200），不关闭页面"""
        rid = db.add_report(self.conn, "被复制报表", "SELECT 1", 20, 1)
        form = ("name=复制保存型&sql_query=SELECT 1&default_page_size=20&pool_id=1"
                "&action=save")
        code, body, headers = config.handle_request(
            self.conn, "POST", f"/config/reports/{rid}/copy", "", form)
        self.assertEqual(code, 200)
        self.assertIn("已创建", body)
        new_report = [r for r in db.get_all_reports(self.conn)
                      if r["name"] == "复制保存型"][0]
        self.assertIn(f'/config/reports/{new_report["id"]}/edit', body)

    def test_submit_edit_report(self):
        rid = db.add_report(self.conn, "旧报表", "SELECT 1", 20, 1)
        form = "name=新报表&sql_query=SELECT 2&default_page_size=50&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 302)
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["name"], "新报表")
        self.assertEqual(rpt["default_page_size"], 50)

    def test_delete_report(self):
        rid = db.add_report(self.conn, "待删报表", "SELECT 1", 20, 1)
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/delete", "", "")
        self.assertEqual(code, 302)
        self.assertIsNone(db.get_report(self.conn, rid))

    def test_submit_add_report_without_pool(self):
        """提交时指定不存在的连接池应报错（外键约束）"""
        form = "name=坏报表&sql_query=SELECT 1&default_page_size=20&pool_id=999"
        code, body, _ = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 200)
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
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["memo"], "新备注")

    def test_submit_add_report_without_memo(self):
        """提交不带备注的报表，memo 应存为 None"""
        form = "name=无备注&sql_query=SELECT 1&default_page_size=20&pool_id=1"
        code, body, headers = config.handle_request(self.conn, "POST", "/config/reports/add", "", form)
        self.assertEqual(code, 302)
        reports = db.get_all_reports(self.conn)
        self.assertIsNone(reports[0]["memo"])


    def test_submit_edit_report_redis_cache_enabled(self):
        """编辑报表时勾选 Redis 缓存应正确保存 prefer_cache=1（hidden+checkbox 同时提交时的 v[-1] 修复验证）"""
        rid = db.add_report(self.conn, "缓存报表", "SELECT 1", 20, 1, prefer_cache=0, cache_ttl_hours=0)
        # 模拟浏览器提交：hidden(0) + checkbox(1) + ttl
        form = "name=缓存报表&sql_query=SELECT 1&default_page_size=20&pool_id=1&prefer_cache=0&prefer_cache=1&cache_ttl_hours=24"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 302)
        rpt = db.get_report(self.conn, rid)
        self.assertEqual(rpt["prefer_cache"], 1)
        self.assertEqual(rpt["cache_ttl_hours"], 24)

    def test_submit_edit_report_redis_cache_disabled(self):
        """编辑报表时取消勾选 Redis 缓存应正确保存 prefer_cache=0"""
        rid = db.add_report(self.conn, "无缓存报表", "SELECT 1", 20, 1, prefer_cache=1, cache_ttl_hours=24)
        # 模拟浏览器提交：仅 hidden(0) 提交（checkbox 未勾选时不提交）
        form = "name=无缓存报表&sql_query=SELECT 1&default_page_size=20&pool_id=1&prefer_cache=0&cache_ttl_hours=0"
        code, body, headers = config.handle_request(self.conn, "POST", f"/config/reports/{rid}/edit", "", form)
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)


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
        self.assertEqual(code, 302)
        location = headers.get("Location", "")
        # 中文 "销售报表" 应被编码为 %xx%xx%xx%xx
        self.assertNotIn("销售报表", location)
        self.assertIn("%", location)
        self.assertTrue(location.startswith("/config?flash="))

    def test_ascii_flash_unchanged(self):
        """纯英文 flash 消息不额外编码"""
        code, body, headers = config.handle_request(
            self.conn, "POST", "/config/pools/999/delete", "", "")
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 200)
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

    def test_add_form_has_preview_button_but_no_view(self):
        """新增报表表单应有【预览】按钮（PH-05 打通新建预览），但无【查看】和隐藏 id"""
        code, body, _ = config.handle_request(self.conn, "GET",
                                               "/config/reports/add", "")
        self.assertIn('onclick="previewReport(this.form)"', body)
        self.assertIn("/report/preview", body)
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

    def test_save_close_is_primary_button(self):
        """PH-10 保存返回上级为主按钮（btn-primary）"""
        rid = db.add_report(self.conn, "主次按钮", "SELECT 1", 20, 1)
        code, body, _ = config.handle_request(self.conn, "GET",
                                               f"/config/reports/{rid}/edit", "")
        self.assertIn('value="save_close" class="btn btn-primary"', body)
        self.assertIn('value="save" class="btn btn-outline"', body)


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
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 302)
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
        self.assertEqual(code, 200)
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
        self.assertEqual(code2, 302)
        ep = db.get_api_endpoint(self.conn, eid)
        self.assertEqual(ep["name"], "往返端点改")
        self.assertEqual(ep["columns"], "id")


class TestApiEndpointsListPage(BaseConfigTest):
    """独立 API 端点管理页面测试"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("testpool", "127.0.0.1", 3306, "root", "secret", "testdb", 1),
        )
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,memo,sort_order) "
            "VALUES (?,?,?,?,?,?)",
            ("测试报表", "SELECT * FROM test_table", 20, 1, "测试备注", 1),
        )
        self.conn.execute(
            "INSERT INTO api_endpoints (report_id,name,url_path,output_format) "
            "VALUES (?,?,?,?)",
            (1, "测试端点", "/test-api", "json"),
        )
        self.conn.commit()

    def test_api_endpoints_page_renders(self):
        """验证 API 端点独立页面可以渲染"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "GET", "/config/api-endpoints", "")
        self.assertEqual(code, 200)
        self.assertIn("API 接口管理", body)
        self.assertIn("测试端点", body)
        self.assertIn("测试报表", body)

    def test_api_endpoints_page_post_delete(self):
        """验证 API 端点独立页面删除操作"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=1")
        self.assertEqual(code, 302)
        self.assertIn("/config/api-endpoints", body)
        self.assertIsNone(db.get_api_endpoint(self.conn, 1))

    def test_api_endpoints_delete_location_latin1_encodable(self):
        """删除成功后 302 Location 必须可 latin-1 编码（http.server 响应头限制）

        回归：delete 分支曾把中文 flash 直拼 Location，send_header 以 latin-1
        编码头时抛 UnicodeEncodeError → 500。
        """
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=1")
        self.assertEqual(code, 302)
        body.encode("latin-1")
        self.assertIn("flash=", body)

    def test_api_endpoints_delete_not_found(self):
        """验证删除不存在的端点返回错误"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=999")
        self.assertEqual(code, 302)
        self.assertIn(urllib.parse.quote("错误"), body)

    def test_api_endpoints_delete_not_found_location_latin1_encodable(self):
        """删除不存在端点的 Location 也必须 latin-1 可编码"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=999")
        self.assertEqual(code, 302)
        body.encode("latin-1")

    def test_api_endpoints_delete_invalid_id(self):
        """验证无效 ID 处理"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=abc")
        self.assertEqual(code, 302)
        self.assertIn(urllib.parse.quote("无效"), body)

    def test_api_endpoints_delete_invalid_id_location_latin1_encodable(self):
        """无效 ID 分支的 Location 也必须 latin-1 可编码"""
        code, body, headers = config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "",
            form_body="action=delete&endpoint_id=abc")
        self.assertEqual(code, 302)
        body.encode("latin-1")


class TestOverviewApiCard(BaseConfigTest):
    """配置总览页 API 卡片显示接口说明摘要"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query) VALUES (?,?)",
            ("测试报表", "SELECT 1"))
        self.conn.commit()
        self.long_desc = ("这是接口A的说明文本，描述接口用途与注意事项，"
                          "内容比较长用于验证摘要截断展示效果")
        db.add_api_endpoint(self.conn, 1, "接口A", "/api/a",
                            description=self.long_desc)

    def test_overview_card_shows_api_with_description(self):
        """气泡列出接口名称与说明摘要（title 全文）"""
        body = config.render_overview(self.conn)
        self.assertIn("接口A", body)
        self.assertIn("title=", body)
        self.assertIn(self.long_desc, body)  # title 中为全文

    def test_overview_card_shows_empty_placeholder(self):
        """无说明接口显示占位符"""
        db.add_api_endpoint(self.conn, 1, "接口B", "/api/b")
        body = config.render_overview(self.conn)
        self.assertIn("接口B", body)
        self.assertIn("—", body)

    def test_overview_card_count_still_present(self):
        """接口总数提示保留"""
        body = config.render_overview(self.conn)
        self.assertIn("已配置 1 个 API 接口", body)


class TestOverviewOnboardingGuide(BaseConfigTest):
    """PH-09 配置总览空状态引导条"""

    def test_overview_shows_guide_when_no_pools(self):
        """无连接池时总览顶部显示三步引导条"""
        body = config.render_overview(self.conn)
        self.assertIn("三步开始", body)
        self.assertIn("立即添加连接池", body)
        self.assertIn('href="/config/pools/add"', body)

    def test_overview_hides_guide_when_pool_exists(self):
        """有连接池时不显示三步引导条"""
        db.add_pool(self.conn, "测试池", "h", 3306, "u", "p", "d")
        body = config.render_overview(self.conn)
        self.assertNotIn("三步开始", body)


class TestApiEndpointToggle(BaseConfigTest):
    """API 端点启用/禁用 toggle 处理"""

    def setUp(self):
        super().setUp()
        self.conn.execute(
            "INSERT INTO report_configs (name,sql_query) VALUES (?,?)",
            ("测试报表", "SELECT 1"))
        self.conn.commit()
        self.eid = db.add_api_endpoint(
            self.conn, 1, "开关端点", "/api/toggle-ep", enabled=1)

    def _post(self, form_body):
        return config.handle_api_endpoints_request(
            self.conn, "POST", "/config/api-endpoints", "", form_body=form_body)

    def test_toggle_disables_enabled(self):
        """启用端点 toggle 后禁用"""
        code, body, headers = self._post(
            f"action=toggle&endpoint_id={self.eid}")
        self.assertEqual(code, 302)
        self.assertEqual(db.get_api_endpoint(self.conn, self.eid)["enabled"], 0)

    def test_toggle_enables_disabled(self):
        """禁用端点 toggle 后启用"""
        db.update_api_endpoint(self.conn, self.eid, enabled=0)
        code, body, headers = self._post(
            f"action=toggle&endpoint_id={self.eid}")
        self.assertEqual(code, 302)
        self.assertEqual(db.get_api_endpoint(self.conn, self.eid)["enabled"], 1)

    def test_toggle_not_found(self):
        """不存在的端点返回错误提示"""
        code, body, headers = self._post("action=toggle&endpoint_id=999")
        self.assertEqual(code, 302)
        self.assertIn(urllib.parse.quote("错误"), body)

    def test_toggle_invalid_id_format(self):
        """无效 ID 格式返回错误提示"""
        code, body, headers = self._post("action=toggle&endpoint_id=abc")
        self.assertEqual(code, 302)
        self.assertIn(urllib.parse.quote("错误"), body)

    @unittest.mock.patch("config_db.static_cache.invalidate")
    def test_toggle_invalidates_cache(self, mock_invalidate):
        """toggle 落库走统一更新函数，触发静态缓存失效"""
        self._post(f"action=toggle&endpoint_id={self.eid}")
        mock_invalidate.assert_called_once()

    @unittest.mock.patch("config_db._write_audit_log")
    def test_toggle_audit_logged(self, mock_audit):
        """toggle 产生审计日志（update_api_endpoint 内建）"""
        self._post(f"action=toggle&endpoint_id={self.eid}")
        args, kwargs = mock_audit.call_args
        self.assertEqual(args[1], "update_api_endpoint")
        self.assertEqual(kwargs["after_value"]["enabled"], 0)

    def test_toggle_return_to_report(self):
        """携带 return_to 时回跳到来源页并带 flash"""
        code, body, headers = self._post(
            f"action=toggle&endpoint_id={self.eid}&return_to=/report?id=1")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/report?id=1"), body)
        self.assertIn("flash=", body)

    def test_toggle_default_return(self):
        """无 return_to 时回跳到独立管理页"""
        code, body, headers = self._post(
            f"action=toggle&endpoint_id={self.eid}")
        self.assertEqual(code, 302)
        self.assertTrue(body.startswith("/config/api-endpoints"), body)


class TestApiEndpointsRoute(unittest.TestCase):
    """路由注册测试"""

    def test_api_endpoints_route_registered(self):
        """验证 API 端点路由已注册"""
        from server import _match_route
        route = _match_route("GET", "/config/api-endpoints")
        self.assertIsNotNone(route)
        self.assertEqual(route.handler, "_handle_config_api_endpoints")

    def test_api_endpoints_post_route_registered(self):
        """验证 API 端点 POST 路由已注册"""
        from server import _match_route
        route = _match_route("POST", "/config/api-endpoints")
        self.assertIsNotNone(route)
        self.assertEqual(route.handler, "_handle_config_api_endpoints")

    def test_config_route_still_matches_subpath(self):
        """验证 /config 模式仍然匹配子路径"""
        from server import _match_route
        route = _match_route("GET", "/config/pools/add")
        self.assertIsNotNone(route)
        self.assertEqual(route.handler, "_handle_config")


if __name__ == "__main__":
    unittest.main()
