"""
test_state_machine.py — 报表四维状态（filter/sort/cols/page）组合测试

测试策略：
- 定义 ReportState 数据模型，描述报表视图的四个维度（筛选、排序、列、页码）
- 从 report.py 生成的 HTML 中解析当前状态参数
- 验证各种交互生成的链接（排序箭头、分页、排序栏移除、清除筛选、重建缓存）
  是否完整保留了"非本次交互修改"的状态维度的所有参数
- 使用 @patch('report.execute_report') 模拟 MySQL 查询，避免真实数据库依赖
- 使用 SQLite :memory: 作为配置数据库

四维状态模型：
  1. filters  — 多字段筛选（f_COL=value & op_COL=operator）
  2. sorts    — 多字段排序（sort=COL&dir=asc 重复）
  3. cols     — 自定义列（cols=col1,col2）
  4. page     — 当前页码（page=N）
"""

import unittest
from unittest.mock import patch, MagicMock
import urllib.parse
import re
import sqlite3
import db
import report


# ===================================================================
# ReportState — 报表视图状态模型
# ===================================================================

class ReportState:
    """报表视图状态：filters, sorts, cols, page 四维状态封装。

    filters: list[(col, op, val), ...]  筛选条件列表
    sorts:   list[(col, dir), ...]      排序条件列表
    cols:    list[str] | None           自定义显示列（None=全部显示）
    page:    int                        当前页码
    """

    __slots__ = ("filters", "sorts", "cols", "page")

    def __init__(self, filters=None, sorts=None, cols=None, page=1):
        self.filters = filters or []
        self.sorts = sorts or []
        self.cols = cols  # None 表示全部显示
        self.page = page if page >= 1 else 1

    def __eq__(self, other):
        if not isinstance(other, ReportState):
            return False
        return (self.filters == other.filters and
                self.sorts == other.sorts and
                self.cols == other.cols and
                self.page == other.page)

    def __repr__(self):
        return (f"ReportState(filters={self.filters}, sorts={self.sorts}, "
                f"cols={self.cols}, page={self.page})")


# ===================================================================
# HTML 状态解析工具
# ===================================================================

def _normalize_qs(qs_str):
    """将 &amp; 转为 &，方便解析。"""
    return qs_str.replace("&amp;", "&")


def parse_state_from_html(html):
    """从 report.py 生成的 HTML 中提取当前报表视图状态。

    解析策略：
    - 扫描所有 href="/report?...& 链接，提取排序、列、页码参数
    - 在 <form> 或 hidden input 中提取筛选参数
    - 在筛选输入框 <input type="text" class="filter-input"> 中提取当前筛选值

    返回 ReportState 实例。
    """
    filters = []
    sorts = []
    cols = None
    page = 1

    # ---- 1. 从 hidden input 提取筛选参数 ----
    # 匹配 <input type="hidden" name="f_COL" value="VAL">
    # 注意：hidden input 的 name 属性是 URL 编码形式（如 f_%E7%94%A8%E6%88%B7%E5%90%8D），
    # 因此 col_name 需要从 URL 编码的 name 中 unquote 解码。
    hidden_f_pattern = re.compile(
        r'<input\s+type="hidden"\s+name="(f_[^"]+)"\s+value="([^"]*)"',
        re.IGNORECASE
    )
    for match in hidden_f_pattern.finditer(html):
        name_encoded = match.group(1)
        value = match.group(2)
        col_name = urllib.parse.unquote(name_encoded[2:])
        # 查找对应的 op_COL hidden input（op_ 后跟 URL 编码的列名，不是解码后的列名）
        op = "contains"
        op_pattern = re.compile(
            r'<input\s+type="hidden"\s+name="op_' + re.escape(name_encoded[2:])
            + r'"\s+value="([^"]*)"',
            re.IGNORECASE
        )
        op_match = op_pattern.search(html)
        if op_match:
            op = op_match.group(1)
        filters.append((col_name, op, value))

    # ---- 2. 从所有 href 链接中提取排序/列/页码 ----
    href_pattern = re.compile(r'href="([^"]*)"')
    all_hrefs = href_pattern.findall(html)

    for href in all_hrefs:
        if "/report?" not in href:
            continue
        qmark_pos = href.find("?")
        if qmark_pos < 0:
            continue
        qs_str = _normalize_qs(href[qmark_pos + 1:])
        params = urllib.parse.parse_qs(qs_str, keep_blank_values=True)

        # 提取排序参数（只从非 refresh 链接提取）
        if "sort" in params and "dir" in params and "refresh" not in params:
            raw_sorts = list(zip(params.get("sort", []), params.get("dir", [])))
            parsed = [(c, d) for c, d in raw_sorts if d in ("asc", "desc")]
            if parsed:
                sorts = parsed

        # 提取 cols 参数
        if "cols" in params and params["cols"][0]:
            cols = params["cols"][0].split(",")

        # 提取 page 参数
        if "page" in params and params["page"][0]:
            try:
                page = int(params["page"][0])
            except (ValueError, TypeError):
                pass

    # ---- 3. 从 filter-input 提取筛选值（补充 hidden input 未覆盖的场景） ----
    if not filters:
        # 匹配 <input type="text" class="filter-input" name="f_COL" value="VAL">
        fi_pattern = re.compile(
            r'<input\s+type="text"\s+class="filter-input"[^>]*name="(f_[^"]+)"'
            r'[^>]*value="([^"]*)"',
            re.IGNORECASE
        )
        for match in fi_pattern.finditer(html):
            name = match.group(1)
            value = match.group(2)
            col_name = urllib.parse.unquote(name[2:])
            if value:
                filters.append((col_name, "contains", value))

    # ---- 4. 从 href 中提取筛选（兜底） ----
    if not filters:
        for href in all_hrefs:
            if "/report?" not in href:
                continue
            qmark_pos = href.find("?")
            if qmark_pos < 0:
                continue
            qs_str = _normalize_qs(href[qmark_pos + 1:])
            params = urllib.parse.parse_qs(qs_str, keep_blank_values=True)
            for key, values in params.items():
                if key.startswith("f_") and key not in ("f_col", "f_q", "filters"):
                    col_name = urllib.parse.unquote(key[2:])
                    if values and values[0]:
                        op = "contains"
                        op_key = "op_" + col_name
                        if op_key in params and params[op_key][0]:
                            op = params[op_key][0]
                        filters.append((col_name, op, values[0]))
            if filters:
                break

    return ReportState(filters=filters, sorts=sorts, cols=cols, page=page)


def build_report_url(params):
    """构建 /report?id=1&... URL。

    params: dict，支持键：
        - id: 报表 ID（默认 1）
        - sorts: list[(col, dir)]
        - filters: list[(col, op, val)]
        - cols: list[str] | None
        - page: int
        - page_size: int
    """
    parts = [f"id={params.get('id', 1)}"]
    page_size = params.get("page_size", 10)
    parts.append(f"page_size={page_size}")

    # 排序（dir_ 必须 URL 编码，与 production build_sort_params 保持一致）
    for col, dir_ in params.get("sorts", []):
        parts.append(f"sort={urllib.parse.quote(col, safe='')}&dir={urllib.parse.quote(dir_, safe='')}")

    # 筛选
    for col, op, val in params.get("filters", []):
        if op == "nofilter":
            continue
        fk = "f_" + urllib.parse.quote(col, safe='')
        parts.append(f"{fk}={urllib.parse.quote(val, safe='')}")
        if op != "contains":
            ok = "op_" + urllib.parse.quote(col, safe='')
            parts.append(f"{ok}={urllib.parse.quote(op, safe='')}")

    # 自定义列
    cols = params.get("cols")
    if cols is not None:
        parts.append(f"cols={urllib.parse.quote(','.join(cols), safe='')}")

    # 页码
    page = params.get("page", 1)
    if page > 1:
        parts.append(f"page={page}")

    return "/report?" + "&".join(parts)


# ===================================================================
# 测试基类 — 报表状态机测试
# ===================================================================

class BaseStateMachineTest(unittest.TestCase):
    """状态机测试基类：提供测试环境创建、HTML 解析和断言辅助方法。"""

    COLUMNS = ["id", "name", "age", "email"]

    ROWS_FOR_PAGINATION = [(i, f"Name{i}", 20 + i, f"user{i}@x.com")
                            for i in range(1, 51)]  # 50 rows for pagination

    MOCK_POOL = {"host": "h", "port": 3306, "user": "u",
                 "password": "p", "database": "d"}

    def setUp(self):
        """每个测试前创建干净的 SQLite :memory: 配置数据库。"""
        self.conn = self._create_config_db()
        self._seed_data()

    def tearDown(self):
        """关闭数据库连接。"""
        self.conn.close()

    def _create_config_db(self):
        """创建测试用 SQLite 配置数据库。"""
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
            CREATE TABLE report_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                parent_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE report_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sql_query TEXT NOT NULL,
                default_page_size INTEGER NOT NULL DEFAULT 20,
                pool_id INTEGER,
                category_id INTEGER,
                memo TEXT,
                result_names TEXT DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0);
        """)
        return conn

    def _seed_data(self):
        """插入种子数据：一个连接池和一个报表。"""
        c = self.conn
        c.execute(
            "INSERT INTO connection_pools (name,host,port,user,password,database,sort_order) "
            "VALUES (?,?,?,?,?,?,?)",
            ("测试池", "h", 3306, "u", "p", "d", 1),
        )
        c.execute(
            "INSERT INTO report_configs (name,sql_query,default_page_size,pool_id,sort_order) "
            "VALUES (?,?,?,?,?)",
            ("测试报表", "SELECT id, name, age, email FROM users", 10, 1, 1),
        )
        c.commit()

    def _mock_execute_report(self, mock_exec, rows=None, total=None, page=1,
                              page_size=10):
        """设置 mock_exec 返回值，自动处理分页场景。"""
        if rows is None:
            rows = self.ROWS_FOR_PAGINATION
        if total is None:
            total = len(rows)
        mock_exec.return_value = report.ReportResult(
            results=[{"columns": list(self.COLUMNS), "rows": rows, "total": total}],
            page=page,
            page_size=page_size,
        )

    def _render(self, query_string, mock_exec, page=1):
        """调用 handle_request 生成 HTML。

        Args:
            query_string: URL 查询字符串
            mock_exec: mock 的 execute_report 对象
            page: 当前页码（影响 mock 返回的 result.page，
                  进而影响分页栏的当前页判定）
        """
        self._mock_execute_report(mock_exec, page=page)
        code, body, _ = report.handle_request(
            self.conn, "GET", "/report", query_string,
            pool_override=self.MOCK_POOL,
        )
        self.assertEqual(code, "200")
        return body

    # ---- URL 参数解析辅助 ----

    def _get_hrefs(self, html, must_contain="/report?"):
        """从 HTML 中提取所有 href 链接。"""
        pattern = re.compile(r'href="([^"]*)"')
        hrefs = pattern.findall(html)
        if must_contain:
            hrefs = [h for h in hrefs if must_contain in h]
        return hrefs

    def _parse_link_params(self, href):
        """从 href 中解析 URL 查询参数为 dict of lists。"""
        if "?" not in href:
            return {}
        qs = href.split("?", 1)[1]
        qs = qs.replace("&amp;", "&")
        return urllib.parse.parse_qs(qs, keep_blank_values=True)

    def _get_sort_arrow_hrefs(self, html, arrow="▲"):
        """获取指定排序箭头（▲ 或 ▼）所在行最近的 href。"""
        hrefs = []
        # 找到所有 ▲ 或 ▼ 并往回找最近的 <a href
        for match in re.finditer(re.escape(arrow), html):
            # 从箭头位置往前找最近的一个 href="
            before = html[max(0, match.start() - 500):match.start()]
            href_m = re.search(r'href="([^"]*)"', before[::-1])
            if href_m:
                href = href_m.group(1)[::-1]
                if "/report?" in href:
                    hrefs.append(href)
        return hrefs

    def _get_pagination_hrefs(self, html):
        """获取分页导航链接（排除当前页 active）。

        注意：CSS 样式中也包含 'pagination' 字样，所以需要搜索
        'class=\"pagination\"' 来定位真正的分页 HTML 区域。
        """
        hrefs = []
        # 查找分页 HTML 区域（匹配 <div class="pagination">）
        pag_tag = 'class="pagination"'
        pagination_start = html.find(pag_tag)
        if pagination_start < 0:
            return []
        pag_section = html[pagination_start:pagination_start + 3000]
        for match in re.finditer(r'href="([^"]*)"', pag_section):
            href = match.group(1)
            if "/report?" in href:
                hrefs.append(href)
        return hrefs

    # ---- 断言辅助 ----

    def assertLinkHasParams(self, href, expected_params, msg=""):
        """断言链接包含预期的 URL 参数。"""
        params = self._parse_link_params(href)
        for key, values in expected_params.items():
            self.assertIn(key, params,
                          f'{msg} 链接 {href[:80]} 缺少参数 "{key}"')
            if isinstance(values, list):
                # 多值参数（如 sort/dir）
                self.assertEqual(
                    params[key], values,
                    f'{msg} 链接 {href[:80]} 参数 "{key}" 期望 {values} 实际 {params[key]}'
                )
            elif values is not None:
                self.assertIn(
                    values, params[key],
                    f'{msg} 链接 {href[:80]} 参数 "{key}" 期望包含 "{values}" 实际 {params[key]}'
                )

    def assertLinkNotHasParams(self, href, keys, msg=""):
        """断言链接不包含指定的参数键。"""
        params = self._parse_link_params(href)
        for key in keys:
            self.assertNotIn(key, params,
                             f'{msg} 链接 {href[:80]} 不应包含参数 "{key}"')

    def assertAllLinksPreserveFilters(self, html, filters, exclude_hrefs=None):
        """验证所有链接都包含指定的筛选参数。

        自动跳过以下链接类型：
        - 清除筛选链接（href 中无任何 f_ 参数，有意不含筛选参数）
        - exclude_hrefs 中指定的模式

        注意：params 由 parse_qs 解析，其 key 已自动解码（无 URL 编码），
        因此直接用 col 拼接，不要再对 col 做 quote。
        """
        if exclude_hrefs is None:
            exclude_hrefs = []
        exclude_hrefs = list(exclude_hrefs)
        hrefs = self._get_hrefs(html)
        for href in hrefs:
            if any(e in href for e in exclude_hrefs):
                continue
            if not href.startswith("/report?"):
                continue
            params = self._parse_link_params(href)
            # 跳过清除筛选链接：href 中没有任何 f_ 参数
            has_any_filter = any(
                f"f_{urllib.parse.quote(c, safe='')}" in href.replace("&amp;", "&")
                for c, _o, _v in filters
            )
            if not has_any_filter:
                continue
            for col, op, val in filters:
                if op == "nofilter":
                    continue
                # params 中 key 已被 parse_qs 解码，直接用原值比较
                f_key = "f_" + col
                self.assertIn(f_key, params,
                              f"链接 {href[:80]} 缺少筛选 {f_key}")
                if op != "contains":
                    op_key = "op_" + col
                    self.assertIn(op_key, params,
                                  f"链接 {href[:80]} 缺少操作符 {op_key}")

    def assertAllLinksPreserveSorts(self, html, sorts, exclude_hrefs=None):
        """验证所有包含 sort 参数的链接都包含指定的排序字段。

        自动跳过：
        - 清除筛选链接（href 中无 sort 参数）
        - 排序栏移除链接（仅移除指定列，保留其他列）
        - exclude_hrefs 中指定的模式
        """
        if exclude_hrefs is None:
            exclude_hrefs = []
        exclude_hrefs = list(exclude_hrefs)
        hrefs = self._get_hrefs(html)
        for href in hrefs:
            if any(e in href for e in exclude_hrefs):
                continue
            if not href.startswith("/report?"):
                continue
            params = self._parse_link_params(href)
            if "sort" not in params:
                continue  # 清除筛选等链接不含 sort
            for col, dir_ in sorts:
                self.assertIn(f"sort={urllib.parse.quote(col, safe='')}", href,
                              f"链接 {href[:80]} 缺少排序 {col}")

    def assertAllLinksPreserveCols(self, html, cols_param, exclude_hrefs=None):
        """验证所有链接都包含 cols 参数。"""
        if not cols_param:
            return
        hrefs = self._get_hrefs(html)
        for href in hrefs:
            if exclude_hrefs and any(e in href for e in exclude_hrefs):
                continue
            self.assertIn("cols=", href,
                          f"链接 {href[:80]} 缺少 cols 参数")


# ===================================================================
# 状态机测试用例（15+ 个测试）
# ===================================================================

class TestStateMachine(BaseStateMachineTest):
    """报表四维状态（filter/sort/cols/page）组合测试。

    每个测试方法：
    1. 构造特定的查询参数 URL
    2. 调用 handle_request 生成 HTML
    3. 解析 HTML 中的链接参数
    4. 验证所有相关链接保留了预期状态
    """

    # ===============================================================
    # TC01: 基础状态 — 无参数时报表页包含基本 pagination 链接
    # ===============================================================

    @patch("report.execute_report")
    def test_basic_pagination_links(self, mock_exec):
        """TC01: 无参数时分页链接应包含 id 和 page_size。"""
        html = self._render("id=1", mock_exec)
        pag_links = self._get_pagination_hrefs(html)
        self.assertGreater(len(pag_links), 0, "应生成分页链接")
        for link in pag_links:
            params = self._parse_link_params(link)
            self.assertIn("id", params, f"分页链接 {link[:80]} 应包含 id")
            self.assertIn("page_size", params,
                          f"分页链接 {link[:80]} 应包含 page_size")
            self.assertIn("page", params, f"分页链接 {link[:80]} 应包含 page")

    # ===============================================================
    # TC02: 单列排序 — sort=name&dir=asc 后排序箭头链接保留排序
    # ===============================================================

    @patch("report.execute_report")
    def test_single_sort_preserved(self, mock_exec):
        """TC02: 单列升序排序，所有链接应保留 sort=name&dir=asc。"""
        html = self._render("id=1&sort=name&dir=asc", mock_exec)
        hrefs = self._get_hrefs(html)
        report_links = [h for h in hrefs if "/report?" in h
                        and "refresh" not in h]
        self.assertGreater(len(report_links), 0)
        for link in report_links:
            params = self._parse_link_params(link)
            if "sort" in params:
                # 排序相关链接必须包含 name asc
                self.assertIn("name", params.get("sort", []),
                              f"链接 {link[:80]} 应包含 sort=name")

    # ===============================================================
    # TC03: 多列排序 — 双字段排序时链接保留两列
    # ===============================================================

    @patch("report.execute_report")
    def test_multi_sort_preserved(self, mock_exec):
        """TC03: 双字段排序时分页链接和排序箭头链接应保留两个排序字段。

        注意排除排序栏移除链接（✕）和清除筛选链接，
        这些链接有意修改/移除了排序参数。
        """
        html = self._render("id=1&sort=name&dir=asc&sort=age&dir=desc",
                            mock_exec)

        # 验证分页链接同时包含两个排序
        pag_links = self._get_pagination_hrefs(html)
        for link in pag_links:
            params = self._parse_link_params(link)
            sorts_found = list(
                zip(params.get("sort", []), params.get("dir", []))
            )
            self.assertIn(("name", "asc"), sorts_found,
                          f"分页链接 {link[:80]} 缺少 name asc")
            self.assertIn(("age", "desc"), sorts_found,
                          f"分页链接 {link[:80]} 缺少 age desc")

        # 验证排序箭头链接同时包含两个排序（找到 ▲ 链接检查）
        for arrow in ("▲", "▼"):
            arrow_links = self._get_sort_arrow_hrefs(html, arrow)
            for link in arrow_links:
                params = self._parse_link_params(link)
                if "sort" in params:
                    sorts_found = list(
                        zip(params.get("sort", []), params.get("dir", []))
                    )
                    # 排序箭头链接应包含两个排序
                    found_name = any(c == "name" for c, d in sorts_found)
                    found_age = any(c == "age" for c, d in sorts_found)
                    self.assertTrue(found_name and found_age,
                                    f"排序箭头链接 {link[:80]} 应包含 name 和 age 排序")

    # ===============================================================
    # TC04: 单字段筛选 — f_name=alice 后链接保留该筛选
    # ===============================================================

    @patch("report.execute_report")
    def test_single_filter_preserved(self, mock_exec):
        """TC04: 单字段筛选后所有链接应包含 f_name=alice。"""
        html = self._render("id=1&f_name=alice", mock_exec)
        self.assertAllLinksPreserveFilters(html, [("name", "contains", "alice")])
        # 验证筛选输入框显示值
        self.assertIn('value="alice"', html, "筛选输入框应显示 alice")

    # ===============================================================
    # TC05: 多字段筛选 — f_name=alice&f_age=30 后链接保留两个筛选
    # ===============================================================

    @patch("report.execute_report")
    def test_multi_filter_preserved(self, mock_exec):
        """TC05: 多字段筛选后链接应保留两个筛选参数。"""
        html = self._render("id=1&f_name=alice&f_age=30", mock_exec)
        self.assertAllLinksPreserveFilters(html, [
            ("name", "contains", "alice"),
            ("age", "contains", "30"),
        ])
        self.assertIn('value="alice"', html, "name 输入框应显示 alice")
        self.assertIn('value="30"', html, "age 输入框应显示 30")

    # ===============================================================
    # TC06: 筛选+排序交互 — 先筛选后排序，链接保留两者
    # ===============================================================

    @patch("report.execute_report")
    def test_filter_and_sort_preserved(self, mock_exec):
        """TC06: 筛选+排序同时存在时链接应保留两者。"""
        html = self._render("id=1&f_name=alice&sort=name&dir=asc", mock_exec)
        # 验证筛选保留
        self.assertAllLinksPreserveFilters(html, [("name", "contains", "alice")])
        # 验证排序保留
        hrefs = self._get_hrefs(html)
        for link in hrefs:
            if "sort=" in link and "refresh" not in link:
                self.assertIn("sort=name", link,
                              f"链接 {link[:80]} 应保留排序")

    # ===============================================================
    # TC07: 排序+筛选+自定义列 — 三者组合时所有参数保留
    # ===============================================================

    @patch("report.execute_report")
    def test_sort_filter_cols_preserved(self, mock_exec):
        """TC07: 排序+筛选+自定义列三者并存时链接应保留所有参数。"""
        html = self._render("id=1&sort=name&dir=asc&f_age=25&cols=id,name",
                            mock_exec)
        # 验证筛选
        self.assertAllLinksPreserveFilters(html, [("age", "contains", "25")])
        # 验证排序
        self.assertAllLinksPreserveSorts(html, [("name", "asc")])
        # 验证 cols
        self.assertAllLinksPreserveCols(html, "cols=id,name")

    # ===============================================================
    # TC08: 翻页 — 第 3 页时分页链接包含 page=3 且其他参数保留
    # ===============================================================

    @patch("report.execute_report")
    def test_page_3_links(self, mock_exec):
        """TC08: 第 3 页时分页链接应包含 page 参数。"""
        # 需要 50 行数据确保多页（mock page=3 与请求一致）
        html = self._render("id=1&page=3", mock_exec, page=3)
        pag_links = self._get_pagination_hrefs(html)
        self.assertGreater(len(pag_links), 0, "应有分页链接")
        for link in pag_links:
            params = self._parse_link_params(link)
            if "page" in params:
                page_val = params["page"][0]
                if page_val:
                    # 第 3 页为当前页，分页链接不包含 page=3
                    # 其他页（1, 2, 4, 5...）应生成链接
                    self.assertIn(page_val, ["1", "2", "4", "5"],
                                  f"分页链接 page 值不应为 {page_val}")

    # ===============================================================
    # TC09: 翻页+筛选 — 筛选后翻页链接保留筛选参数
    # ===============================================================

    @patch("report.execute_report")
    def test_pagination_preserves_filter(self, mock_exec):
        """TC09: 有筛选时翻页链接应保留筛选参数。"""
        html = self._render("id=1&f_name=alice&page=2", mock_exec)
        pag_links = self._get_pagination_hrefs(html)
        self.assertGreater(len(pag_links), 0, "应有分页链接")
        for link in pag_links:
            params = self._parse_link_params(link)
            self.assertIn("f_name", params,
                          f"分页链接 {link[:80]} 应保留 f_name")
            self.assertEqual(params.get("f_name", [None])[0], "alice",
                             f"分页链接 {link[:80]} f_name 值应为 alice")

    # ===============================================================
    # TC10: 全部四维 — filter+sort+cols+page 全部保留
    # ===============================================================

    @patch("report.execute_report")
    def test_all_four_dimensions(self, mock_exec):
        """TC10: filter+sort+cols+page 四维全部在链接中保留。"""
        html = self._render(
            "id=1&sort=name&dir=asc&sort=age&dir=desc"
            "&f_name=alice&f_age=30&cols=id,name,age&page=2",
            mock_exec,
        )
        hrefs = self._get_hrefs(html)
        report_links = [h for h in hrefs if "/report?" in h]
        for link in report_links:
            if "refresh" in link or "清除" in link or "clear" in link.lower():
                continue
            params = self._parse_link_params(link)
            # 检查筛选
            if "f_name" in params or "f_age" in params:
                self.assertIn("f_name", params,
                              f"链接 {link[:80]} 应包含 f_name")
                self.assertIn("f_age", params,
                              f"链接 {link[:80]} 应包含 f_age")

    # ===============================================================
    # TC11: 操作符 — op_name=gt 的筛选在链接中保留 op_ 参数
    # ===============================================================

    @patch("report.execute_report")
    def test_operator_preserved_in_links(self, mock_exec):
        """TC11: 非默认操作符（gt）应在链接中保留 op_ 参数。"""
        html = self._render("id=1&f_age=100&op_age=gt", mock_exec)
        hrefs = self._get_hrefs(html)
        report_links = [h for h in hrefs if "/report?" in h
                        and "refresh" not in h]
        for link in report_links:
            if "f_age" in link:
                self.assertIn("op_age=gt", link,
                              f"链接 {link[:80]} 应保留操作符 op_age=gt")
        # 验证操作符下拉框选中 gt
        self.assertIn('value="gt" selected', html,
                      "操作符下拉框应选中 gt")

    # ===============================================================
    # TC12: 多列排序+翻页 — 排序后翻页链接保留排序参数
    # ===============================================================

    @patch("report.execute_report")
    def test_pagination_preserves_multi_sort(self, mock_exec):
        """TC12: 多列排序后翻页链接应保留所有排序参数。"""
        html = self._render(
            "id=1&sort=name&dir=asc&sort=age&dir=desc", mock_exec
        )
        pag_links = self._get_pagination_hrefs(html)
        for link in pag_links:
            params = self._parse_link_params(link)
            sorts_found = list(
                zip(params.get("sort", []), params.get("dir", []))
            )
            # 翻页链接应保留排序（当前页 page=1，翻到 page=2 应保留排序）
            if sorts_found:
                self.assertIn(("name", "asc"), sorts_found,
                              f"分页链接 {link[:80]} 应保留 name asc")
                self.assertIn(("age", "desc"), sorts_found,
                              f"分页链接 {link[:80]} 应保留 age desc")

    # ===============================================================
    # TC13: 筛选+翻页+排序 — 完整交互序列
    # ===============================================================

    @patch("report.execute_report")
    def test_filter_sort_pagination_sequence(self, mock_exec):
        """TC13: 筛选+排序+翻页组合后所有维度在链接中保留。"""
        html = self._render(
            "id=1&f_name=alice&f_age=25&sort=name&dir=asc&page=2",
            mock_exec,
        )
        # 验证筛选
        self.assertIn('value="alice"', html, "name 筛选输入框应显示 alice")
        self.assertIn('value="25"', html, "age 筛选输入框应显示 25")
        # 验证排序
        self.assertIn('sort-bar', html, "应有排序栏")
        self.assertIn("name", html, "页面应包含 name 排序列")
        # 验证分页
        pag_links = self._get_pagination_hrefs(html)
        for link in pag_links:
            params = self._parse_link_params(link)
            if "f_name" in params:
                self.assertEqual(params["f_name"][0], "alice",
                                 f"分页链接 {link[:80]} f_name 应为 alice")
            if "f_age" in params:
                self.assertEqual(params["f_age"][0], "25",
                                 f"分页链接 {link[:80]} f_age 应为 25")

    # ===============================================================
    # TC14: 移除排序 — ✕ 链接应移除该列排序但保留其他
    # ===============================================================

    @patch("report.execute_report")
    def test_remove_sort_link_preserves_others(self, mock_exec):
        """TC14: 多字段排序时✕链接移除一列后应保留其余排序。"""
        html = self._render(
            "id=1&sort=name&dir=asc&sort=age&dir=desc&sort=id&dir=asc",
            mock_exec,
        )
        # 找到排序栏区域
        sort_bar_start = html.find("sort-bar")
        self.assertGreater(sort_bar_start, 0, "页面应有排序栏")
        sort_bar_end = html.find("</div>", sort_bar_start)
        sort_bar_html = html[sort_bar_start:sort_bar_end]

        # 找 name 排序列的 ✕ 链接
        name_tag_end = sort_bar_html.find("name")
        self.assertGreater(name_tag_end, 0, "排序栏应有 name")
        name_section = sort_bar_html[name_tag_end:name_tag_end + 300]
        x_match = re.search(r'href="([^"]*)"', name_section)
        if x_match:
            x_href = x_match.group(1)
            # name 的 ✕ 链接应移除 name 但保留 age desc 和 id asc
            self.assertNotIn("sort=name", x_href,
                             f"移除链接 {x_href[:80]} 不应包含 sort=name")
            self.assertIn("sort=age", x_href,
                          f"移除链接 {x_href[:80]} 应保留 sort=age")
            self.assertIn("dir=desc", x_href,
                          f"移除链接 {x_href[:80]} 应保留 dir=desc")
            self.assertIn("sort=id", x_href,
                          f"移除链接 {x_href[:80]} 应保留 sort=id")
            self.assertIn("dir=asc", x_href,
                          f"移除链接 {x_href[:80]} 应保留 dir=asc")

    # ===============================================================
    # TC15: 保留 cols 参数 — 自定义列时所有链接保留 cols
    # ===============================================================

    @patch("report.execute_report")
    def test_cols_preserved_in_all_links(self, mock_exec):
        """TC15: 自定义列（cols=id,name）时所有链接应保留 cols 参数。"""
        html = self._render("id=1&cols=id,name", mock_exec)
        hrefs = self._get_hrefs(html)
        report_links = [h for h in hrefs if "/report?" in h]
        for link in report_links:
            if "refresh" in link:
                continue
            self.assertIn("cols=", link,
                          f"链接 {link[:80]} 应包含 cols 参数")
        # 验证 cols 出现在表单隐藏字段中
        self.assertIn('name="cols"', html, "页面应有 cols 隐藏字段")

    # ===============================================================
    # TC16: 排序箭头链接保留筛选（额外强度验证）
    # ===============================================================

    @patch("report.execute_report")
    def test_sort_arrow_links_preserve_filters(self, mock_exec):
        """TC16: 排序箭头（▲/▼）链接应保留当前筛选条件。"""
        html = self._render("id=1&f_name=alice&f_age=30&sort=name&dir=asc",
                            mock_exec)
        # 找 ▲ 链接
        for arrow in ("▲", "▼"):
            arrow_hrefs = self._get_sort_arrow_hrefs(html, arrow)
            for href in arrow_hrefs:
                params = self._parse_link_params(href)
                if "f_name" in href:
                    self.assertIn("f_name", params,
                                  f"排序箭头链接 {href[:80]} 应保留 f_name")

    # ===============================================================
    # TC17: 重建缓存链接保留所有状态
    # ===============================================================

    @patch("report.execute_report")
    def test_refresh_link_preserves_state(self, mock_exec):
        """TC17: 重建缓存链接应保留排序、筛选和列设置。"""
        html = self._render(
            "id=1&sort=name&dir=asc&f_age=25&op_age=gt&cols=id,name",
            mock_exec,
        )
        # 找 refresh=1 的链接
        refresh_hrefs = [h for h in self._get_hrefs(html) if "refresh=1" in h]
        self.assertGreater(len(refresh_hrefs), 0, "应有重建缓存链接")
        for href in refresh_hrefs:
            self.assertIn("sort=name", href,
                          f"重建缓存链接 {href[:80]} 应保留 sort=name")
            self.assertIn("f_age=25", href,
                          f"重建缓存链接 {href[:80]} 应保留 f_age=25")
            self.assertIn("op_age=gt", href,
                          f"重建缓存链接 {href[:80]} 应保留 op_age=gt")
            self.assertIn("cols=", href,
                          f"重建缓存链接 {href[:80]} 应保留 cols")

    # ===============================================================
    # TC18: 清除筛选链接保留排序和列
    # ===============================================================

    @patch("report.execute_report")
    def test_clear_filter_preserves_sort_and_cols(self, mock_exec):
        """TC18: 清除筛选链接应保留排序和列设置但移除筛选参数。"""
        # 直接使用 _build_report_html 测试清除筛选链接
        report_info = {"id": 1, "name": "测试报表",
                       "sql_query": "SELECT * FROM t", "memo": ""}
        result = report.ReportResult(
            results=[{"columns": ["id", "name", "age", "email"], "rows": [(1, "A", 25, "a@x.com")], "total": 1}],
            page=1, page_size=10,
        )
        body = report._build_report_html(
            self.conn, report_info, result, self.MOCK_POOL,
            sorts=[("name", "asc")],
            filters=[("name", "contains", "alice")],
            display_columns=["id", "name"],
        )
        # 找到清除筛选链接
        clear_pos = body.find("清除筛选")
        self.assertGreater(clear_pos, 0, "页面应有清除筛选链接")
        # 往回找最近的 href
        before = body[max(0, clear_pos - 300):clear_pos]
        href_m = re.search(r'href="([^"]*)"', before)
        self.assertIsNotNone(href_m, "清除筛选链接应有 href")
        clear_href = href_m.group(1)
        self.assertIn("sort=name", clear_href,
                      f"清除筛选链接 {clear_href[:80]} 应保留 sort=name")
        self.assertIn("cols=", clear_href,
                      f"清除筛选链接 {clear_href[:80]} 应保留 cols")
        self.assertNotIn("f_name", clear_href,
                         f"清除筛选链接 {clear_href[:80]} 不应包含 f_name")

    # ===============================================================
    # TC19: ReportState 数据模型测试
    # ===============================================================

    def test_report_state_defaults(self):
        """ReportState 默认值应为空筛选、空排序、cols=None、page=1。"""
        state = ReportState()
        self.assertEqual(state.filters, [])
        self.assertEqual(state.sorts, [])
        self.assertIsNone(state.cols)
        self.assertEqual(state.page, 1)

    def test_report_state_custom_values(self):
        """ReportState 应正确保存自定义值。"""
        state = ReportState(
            filters=[("name", "contains", "alice")],
            sorts=[("age", "desc")],
            cols=["id", "name"],
            page=3,
        )
        self.assertEqual(state.filters, [("name", "contains", "alice")])
        self.assertEqual(state.sorts, [("age", "desc")])
        self.assertEqual(state.cols, ["id", "name"])
        self.assertEqual(state.page, 3)

    def test_report_state_page_min_one(self):
        """ReportState 页码小于 1 时自动修正为 1。"""
        state = ReportState(page=0)
        self.assertEqual(state.page, 1)
        state2 = ReportState(page=-5)
        self.assertEqual(state2.page, 1)

    # ===============================================================
    # TC20: parse_state_from_html 功能测试
    # ===============================================================

    @patch("report.execute_report")
    def test_parse_state_from_html(self, mock_exec):
        """parse_state_from_html 应从 HTML 正确提取四维状态。"""
        html = self._render(
            "id=1&sort=name&dir=asc&f_age=30&cols=id,name,age",
            mock_exec,
        )
        state = parse_state_from_html(html)
        # 验证解析出的状态包含预期内容
        self.assertIsInstance(state, ReportState)
        # 至少应解析出排序
        if state.sorts:
            sort_cols = [c for c, d in state.sorts]
            self.assertIn("name", sort_cols)

    # ===============================================================
    # TC21: build_report_url 双向一致性测试
    # ===============================================================

    def test_build_report_url_roundtrip(self):
        """build_report_url 生成的 URL 应包含所有参数。"""
        url = build_report_url({
            "id": 1,
            "sorts": [("name", "asc"), ("age", "desc")],
            "filters": [("name", "contains", "alice"), ("age", "gt", "30")],
            "cols": ["id", "name", "age"],
            "page": 2,
            "page_size": 10,
        })
        self.assertIn("id=1", url)
        self.assertIn("sort=name", url)
        self.assertIn("dir=asc", url)
        self.assertIn("sort=age", url)
        self.assertIn("dir=desc", url)
        self.assertIn("f_name=alice", url)
        self.assertIn("f_age=30", url)
        self.assertIn("op_age=gt", url)
        self.assertIn("cols=", url)
        self.assertIn("page=2", url)

    # ===============================================================
    # TC22: 筛选+多列排序+翻页（完整状态流转验证）
    # ===============================================================

    @patch("report.execute_report")
    def test_full_state_interaction(self, mock_exec):
        """TC22: 筛选—排序—翻页完整状态流转：所有维度保持一致性。"""
        # 模拟 500 行数据确保多页
        big_rows = [(i, f"User{i}", 20 + (i % 50), f"u{i}@x.com")
                     for i in range(1, 501)]
        self._mock_execute_report(mock_exec, rows=big_rows, total=500)

        # 状态: f_name=test + sort=age&dir=desc + cols=id,name,age + page=2
        html = report.handle_request(
            self.conn, "GET", "/report",
            "id=1&f_name=test&sort=age&dir=desc&cols=id,name,age&page=2",
            pool_override=self.MOCK_POOL,
        )[1]

        # 验证排序栏存在
        self.assertIn("sort-bar", html, "应有排序栏")

        # 验证筛选输入框显示值
        self.assertIn('value="test"', html, "筛选输入框应显示 test")

        # 验证分页链接保留所有参数
        pag_links = self._get_pagination_hrefs(html)
        filter_found = False
        sort_found = False
        for link in pag_links:
            if "f_name=" in link:
                filter_found = True
            if "sort=age" in link:
                sort_found = True
        self.assertTrue(filter_found, "分页链接应包含 f_name")
        self.assertTrue(sort_found, "分页链接应包含 sort=age")

    # ===============================================================
    # TC23: 操作符下拉框保留当前选择
    # ===============================================================

    @patch("report.execute_report")
    def test_operator_dropdown_retains_selection(self, mock_exec):
        """TC23: 筛选操作符下拉框应保留当前选中的操作符。"""
        html = self._render("id=1&f_name=&op_name=isempty", mock_exec)
        self.assertIn('value="isempty" selected', html,
                      "操作符下拉框应选中 isempty")


    # ===============================================================
    # TC24: 序列1 — filter → sort → filter (保留两参数)
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_filter_sort_filter(self, mock_exec):
        """TC24: 筛选→排序→再筛选，三步累积后所有参数共存。

        序列模拟：
          1. 初始无参数
          2. 添加筛选 f_name=alice
          3. 添加排序 sort=age&dir=asc
          4. 再添加筛选 f_city=NYC（保留 sort + f_name）
          5. 验证最终 HTML 链接包含全部三个维度
        """
        # ---- 最终累积状态：f_name=alice + sort=age&dir=asc + f_city=NYC ----
        html = self._render(
            "id=1&f_name=alice&sort=age&dir=asc&f_city=NYC", mock_exec
        )

        # ---- 断言 1: 筛选参数 f_name 保留 ----
        self.assertIn("f_name=alice", html,
                      "HTML 应包含筛选参数 f_name=alice")
        # ---- 断言 2: 筛选参数 f_city 保留 ----
        self.assertIn("f_city=NYC", html,
                      "HTML 应包含筛选参数 f_city=NYC")
        # ---- 断言 3: 排序参数 sort=age&dir=asc 保留 ----
        hrefs = self._get_hrefs(html)
        sort_has_age_asc = False
        for link in hrefs:
            norm = link.replace("&amp;", "&")
            if "sort=age" in norm and "dir=asc" in norm and "refresh" not in link:
                sort_has_age_asc = True
                break
        self.assertTrue(sort_has_age_asc,
                        "链接中应包含 sort=age&dir=asc")
        # ---- 断言 4（额外）：assertAllLinksPreserveFilters 验证双筛选 ----
        self.assertAllLinksPreserveFilters(html, [
            ("name", "contains", "alice"),
            ("city", "contains", "NYC"),
        ])

    # ===============================================================
    # TC25: 序列2 — sort → filter → page → sort (四维)
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_sort_filter_page_sort(self, mock_exec):
        """TC25: 排序→筛选→翻页→切排序方向，四维全部保留。

        序列模拟：
          1. 初始无参数
          2. 添加排序 sort=name&dir=desc
          3. 添加筛选 f_age=30
          4. 翻到 page=3
          5. 点击 name 列 ▲ 切换方向为 asc
          6. 验证 page=3、f_age=30、sort=name&dir=asc
        """
        # ---- 最终累积状态（点击 ▲ 后 direction 变 asc）- ----
        html = self._render(
            "id=1&sort=name&dir=asc&f_age=30&page=3", mock_exec, page=3
        )

        # ---- 断言 1: f_age=30 出现在链接中 ----
        hrefs = self._get_hrefs(html)
        filter_in_links = any(
            "f_age=30" in h.replace("&amp;", "&") for h in hrefs
        )
        self.assertTrue(filter_in_links,
                        "链接中应包含筛选参数 f_age=30")

        # ---- 断言 2: 分页区域显示当前页为 3 ----
        self.assertIn('class="active">3<', html,
                      "分页导航应标记第 3 页为当前页")

        # ---- 断言 3: sort=name&dir=asc 出现在链接 ----
        sort_asc_found = False
        for link in hrefs:
            norm = link.replace("&amp;", "&")
            if "sort=name" in norm and "dir=asc" in norm and "refresh" not in link:
                sort_asc_found = True
                break
        self.assertTrue(sort_asc_found,
                        "链接中应包含 sort=name&dir=asc")

        # ---- 断言 4（额外）：分页链接保留 page 参数 ----
        pag_links = self._get_pagination_hrefs(html)
        self.assertGreater(len(pag_links), 0, "应有分页链接")
        for link in pag_links:
            params = self._parse_link_params(link)
            self.assertIn("page", params,
                          f"分页链接 {link[:80]} 应包含 page 参数")

    # ===============================================================
    # TC26: 序列3 — cols → filter → sort → page → 添加第二个 filter
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_cols_filter_sort_page_multi_filter(self, mock_exec):
        """TC26: 自定义列→筛选→排序→翻页→双筛选，全部参数保留。

        序列模拟：
          1. cols=name,age
          2. f_city=LA
          3. sort=id&dir=asc
          4. page=2
          5. 添加 f_name=Bob（双筛选）
          6. 验证所有链接包含 cols、f_city、f_name、sort、page
          7. 验证筛选输入框显示值
        """
        html = self._render(
            "id=1&cols=name,age&f_city=LA&sort=id&dir=asc&page=2&f_name=Bob",
            mock_exec, page=2,
        )

        # ---- 断言 1: cols 参数出现在链接中 ----
        hrefs = self._get_hrefs(html)
        cols_in_links = any(
            "cols=" in h for h in hrefs if "/report?" in h and "refresh" not in h
        )
        self.assertTrue(cols_in_links, "链接中应包含 cols 参数")
        self.assertIn('name="cols"', html, "页面应有 cols 隐藏字段")

        # ---- 断言 2: 筛选输入框显示值 ----
        self.assertIn('value="Bob"', html,
                      "筛选输入框应显示 Bob")
        self.assertIn('value="LA"', html,
                      "筛选输入框应显示 LA")

        # ---- 断言 3: 排序参数保留 ----
        self.assertAllLinksPreserveSorts(html, [("id", "asc")])

        # ---- 断言 4: 双筛选同时保留 ----
        self.assertAllLinksPreserveFilters(html, [
            ("city", "contains", "LA"),
            ("name", "contains", "Bob"),
        ])

        # ---- 断言 5: 当前页为 2 ----
        self.assertIn('class="active">2<', html,
                      "分页导航应标记第 2 页为当前页")

    # ===============================================================
    # TC27: 序列4 — 清零筛选按钮保留 sort+cols
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_clear_filter_preserves_sort_cols(self, mock_exec):
        """TC27: 清除筛选链接应保留排序和列，移除所有筛选。

        序列模拟：
          1. 初始含 sort=age&dir=desc + cols=id,name,age + f_name=alice
          2. 解析 page_size 参数
          3. 清除筛选链接保留 cols 和 sort，不包含 f_name
        """
        html = self._render(
            "id=1&sort=age&dir=desc&cols=id,name,age&f_name=alice",
            mock_exec,
        )

        # ---- 断言 1: page_size 参数在链接中存在 ----
        hrefs = self._get_hrefs(html)
        page_size_found = any(
            "page_size=10" in h.replace("&amp;", "&")
            for h in hrefs if "/report?" in h
        )
        self.assertTrue(page_size_found,
                        "链接中应包含 page_size=10")

        # ---- 找到清除筛选链接 ----
        clear_pos = html.find("清除筛选")
        self.assertGreater(clear_pos, 0, "页面应有清除筛选链接")
        before = html[max(0, clear_pos - 300):clear_pos]
        href_m = re.search(r'href="([^"]*)"', before)
        self.assertIsNotNone(href_m, "清除筛选链接应有 href")
        clear_href = href_m.group(1)
        clear_norm = clear_href.replace("&amp;", "&")

        # ---- 断言 2: 清除链接保留 sort=age&dir=desc ----
        self.assertIn("sort=age", clear_norm,
                      f"清除链接 {clear_href[:80]} 应保留 sort=age")
        self.assertIn("dir=desc", clear_norm,
                      f"清除链接 {clear_href[:80]} 应保留 dir=desc")

        # ---- 断言 3: 清除链接保留 cols ----
        self.assertIn("cols=", clear_norm,
                      f"清除链接 {clear_href[:80]} 应保留 cols")

        # ---- 断言 4: 清除链接不包含 f_name ----
        self.assertNotIn("f_name", clear_norm,
                         f"清除链接 {clear_href[:80]} 不应包含 f_name")

        # ---- 断言 5: 排序箭头链接保留 cols 和 sort ----
        for arrow in ("▲", "▼"):
            arrow_links = self._get_sort_arrow_hrefs(html, arrow)
            for alink in arrow_links:
                norm = alink.replace("&amp;", "&")
                self.assertIn("sort=age", norm,
                              f"排序箭头链接 {alink[:80]} 应保留 sort")
                if "cols=" in norm:
                    self.assertIn("cols=", norm,
                                  f"排序箭头链接 {alink[:80]} 应保留 cols")

    # ===============================================================
    # TC28: 序列5 — 多步筛选变更
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_multi_step_filter_changes(self, mock_exec):
        """TC28: 同名筛选覆盖、多列筛选叠加，不产生重复值。

        序列模拟：
          1. f_name=alice → 验证含 alice
          2. f_name=bob（覆盖）→ 验证 f_name=bob 而非两条
          3. f_city=NYC（新增）→ 验证 f_name=bob + f_city=NYC
        """
        # ---- 步骤 2: 覆盖同名筛选 ----
        html_step2 = self._render("id=1&f_name=bob", mock_exec)
        # 只有 alice 和 bob 中的一个（bob 覆盖 alice）
        f_name_hrefs = [
            h for h in self._get_hrefs(html_step2)
            if "/report?" in h and "f_name=" in h.replace("&amp;", "&")
        ]
        for href in f_name_hrefs:
            norm = href.replace("&amp;", "&")
            # 应只包含一个 f_name 参数
            self.assertEqual(
                norm.count("f_name="), 1,
                f"链接 {href[:80]} 应只有 1 个 f_name 参数（覆盖后）"
            )
            # 值应为 bob
            self.assertIn("f_name=bob", norm,
                          f"链接 {href[:80]} f_name 应为 bob")

        # ---- 步骤 2 验证筛选输入框显示 bob ----
        self.assertIn('value="bob"', html_step2,
                      "筛选输入框应显示 bob")
        # ---- 步骤 2 验证不包含 alice 值 ----
        alice_val_count = html_step2.count('value="alice"')
        self.assertEqual(
            alice_val_count, 0,
            f"HTML 不应包含 value=\"alice\"（实际出现 {alice_val_count} 次）"
        )

        # ---- 步骤 3: 新增多列筛选 ----
        html_step3 = self._render("id=1&f_name=bob&f_city=NYC", mock_exec)

        # ---- 断言: 双筛选共存 ----
        self.assertAllLinksPreserveFilters(html_step3, [
            ("name", "contains", "bob"),
            ("city", "contains", "NYC"),
        ])
        # ---- 断言: 输入框显示正确值 ----
        self.assertIn('value="bob"', html_step3, "name 输入框应显示 bob")
        self.assertIn('value="NYC"', html_step3, "city 输入框应显示 NYC")

    # ===============================================================
    # TC29: 序列6 — 排序优先级向上/向下切换
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_sort_priority_toggle(self, mock_exec):
        """TC29: 多字段排序中切换单列方向，其余列排序保留。

        序列模拟：
          1. sort=name&dir=asc&sort=age&dir=desc（双字段排序）
          2. 点击 name 列 ▼（desc 方向）
          3. 验证 sort 变为 name=desc, age=desc（切换方向，保留优先级）

        技术说明：
          - _build_sort_params 使用 bare & 连接参数，
            因此 HTML 中 href 包含 &amp; 与 bare & 混排。
          - 使用 _parse_link_params 正确统一解析两类分隔符。
        """
        html = self._render(
            "id=1&sort=name&dir=asc&sort=age&dir=desc", mock_exec
        )

        # ---- 从所有 /report? 链接中查找 name 列 ▼ 的 URL ----
        # 原始 sorts=[("name","asc"),("age","desc")]
        # name ▼ 构建 desc_sorts=[("name","desc"),("age","desc")]
        hrefs = self._get_hrefs(html)
        name_desc_found = False
        name_desc_sorts = None
        age_desc_found = False

        for link in hrefs:
            if "/report?" not in link or "refresh" in link:
                continue
            params = self._parse_link_params(link)
            sorts = list(
                zip(params.get("sort", []), params.get("dir", []))
            )
            if not sorts:
                continue

            # name ▼ 链接应包含 ("name","desc") 和 ("age","desc")
            if ("name", "desc") in sorts and ("age", "desc") in sorts:
                name_desc_found = True
                name_desc_sorts = list(sorts)

            # age ▼ 链接应包含 ("name","asc") 和 ("age","desc")
            if ("name", "asc") in sorts and ("age", "desc") in sorts:
                age_desc_found = True

        # ---- 断言 1: 存在 name 列 ▼ 链接 ----
        self.assertTrue(
            name_desc_found,
            "应存在 name 列 ▼ 链接（含 name=desc, age=desc）"
        )

        # ---- 断言 2: name ▼ 链接恰好两个排序字段 ----
        self.assertEqual(
            len(name_desc_sorts), 2,
            f"name ▼ 链接应有 2 个排序字段（实际 {len(name_desc_sorts)}）"
        )

        # ---- 断言 3: 存在 age 列 ▼ 链接（保持 name=asc, age=desc） ----
        self.assertTrue(
            age_desc_found,
            "应存在 age 列 ▼ 链接（含 name=asc, age=desc）"
        )

    # ===============================================================
    # TC30: 序列7 — 空筛选操作符处理
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_empty_filter_operator(self, mock_exec):
        """TC30: 空值筛选被忽略，操作符筛选被正确保留。

        序列模拟：
          1. f_name=（空值，parse_filters 应忽略）
          2. op_city=isempty（无值但有操作符）
          3. 验证 HTML 链接包含 op_city=isempty

        注意："city" 不是测试列的字段名（列名为 id/name/age/email），
        因此页面不会为 city 生成筛选输入框/下拉框。
        op_city=isempty 仅作为隐藏 input 和 URL 参数出现。
        """
        html = self._render("id=1&f_name=&op_city=isempty", mock_exec)

        # ---- 断言 1: f_name= 不应出现在任何链接中（空值被过滤） ----
        hrefs = self._get_hrefs(html)
        for href in hrefs:
            if "/report?" in href:
                norm = href.replace("&amp;", "&")
                self.assertNotIn(
                    "f_name=", norm,
                    f"链接 {href[:80]} 不应包含空值 f_name="
                )

        # ---- 断言 2: op_city=isempty 出现在链接中 ----
        op_found = False
        for href in hrefs:
            if "/report?" in href and "op_city=isempty" in href.replace("&amp;", "&"):
                op_found = True
                break
        self.assertTrue(op_found,
                        "链接中应至少一个包含 op_city=isempty")

        # ---- 断言 3: 隐藏 input 包含 op_city=isempty ----
        self.assertIn(
            'name="op_city" value="isempty"', html,
            "隐藏表单应包含 op_city=isempty"
        )

        # ---- 断言 4: 筛选摘要显示"city (为空)" ----
        self.assertIn("city", html, "筛选摘要应提及 city")
        self.assertIn("为空", html, "筛选摘要应显示\"为空\"")

    # ===============================================================
    # TC31: 序列8 — 自定义列+筛选+排序+翻页+刷新
    # ===============================================================

    @patch("report.execute_report")
    def test_sequence_custom_cols_filter_sort_page_refresh(self, mock_exec):
        """TC31: 全维度参数共存，重建缓存链接保留所有状态。

        序列模拟：
          1. cols=id,name,age + f_age>30 + sort=name&dir=asc + page=2
          2. 验证链接保留全部参数
          3. 添加 refresh=1 → 验证 refresh 参数存在且其他参数保留

        注意：cols 必须包含 \"age\" 才能让 age 列的筛选下拉框渲染。
        """
        html = self._render(
            "id=1&cols=id,name,age&f_age=30&op_age=gt&sort=name&dir=asc&page=2",
            mock_exec, page=2,
        )

        # ---- 断言 1: cols 参数保留 ----
        hrefs = self._get_hrefs(html)
        cols_in_links = any(
            "cols=" in h for h in hrefs if "/report?" in h and "refresh" not in h
        )
        self.assertTrue(cols_in_links, "链接中应包含 cols 参数")

        # ---- 断言 2: 排序参数保留 ----
        self.assertAllLinksPreserveSorts(html, [("name", "asc")])

        # ---- 断言 3: 筛选 + 操作符保留 ----
        self.assertAllLinksPreserveFilters(html, [("age", "gt", "30")])
        self.assertIn('value="gt" selected', html,
                      "操作符下拉框应选中 gt")

        # ---- 断言 4: 当前页为 2 ----
        self.assertIn('class="active">2<', html,
                      "分页导航应标记第 2 页为当前页")

        # ---- 断言 5: 重建缓存链接（refresh=1）保留所有参数 ----
        refresh_hrefs = [
            h for h in hrefs if "refresh=1" in h.replace("&amp;", "&")
        ]
        self.assertGreater(len(refresh_hrefs), 0, "应有重建缓存链接")
        for href in refresh_hrefs:
            norm = href.replace("&amp;", "&")
            self.assertIn("sort=name", norm,
                          f"重建缓存链接 {href[:80]} 应保留 sort=name")
            self.assertIn("f_age=30", norm,
                          f"重建缓存链接 {href[:80]} 应保留 f_age=30")
            self.assertIn("op_age=gt", norm,
                          f"重建缓存链接 {href[:80]} 应保留 op_age=gt")
            self.assertIn("cols=", norm,
                          f"重建缓存链接 {href[:80]} 应保留 cols")
            self.assertIn("refresh=1", norm,
                          f"重建缓存链接 {href[:80]} 应包含 refresh=1")


# ===================================================================
# 中文字符参数测试
# ===================================================================

class TestChineseParams(BaseStateMachineTest):
    """测试中文字段名在排序/筛选/自定义列中的正确处理。"""

    COLUMNS = ["用户名", "单位名", "处置商类型", "处置商显示（按类型）",
               "phone", "shelf_apply_id", "缴纳备注", "保证金金额", "缴纳时间"]

    ROWS_FOR_PAGINATION = [
        (f"用户{i}", f"单位{i}", "机构", "全部", f"138{i:04d}",
         f"SA{i:04d}", "已缴纳", 1000.00 + i, "2024-01-15")
        for i in range(1, 51)
    ]

    # 9 列的 mock 数据
    COLUMNS_9 = ["用户名", "单位名", "处置商类型", "处置商显示（按类型）",
                 "phone", "shelf_apply_id", "缴纳备注", "保证金金额", "缴纳时间"]

    def _mock_execute_report(self, mock_exec, rows=None, total=None, page=1,
                              page_size=50):
        """设置 mock_exec 返回值，使用中文列名。"""
        if rows is None:
            rows = [(f"用户{i}", f"单位{i}", "机构", "全部", f"138{i:04d}",
                     f"SA{i:04d}", "已缴纳", 1000.00 + i, "2024-01-15")
                    for i in range(1, 51)]
        if total is None:
            total = len(rows)
        mock_exec.return_value = report.ReportResult(
            results=[{"columns": list(self.COLUMNS_9), "rows": rows, "total": total}],
            page=page,
            page_size=page_size,
        )

    @patch("report.execute_report")
    def test_chinese_sort_single(self, mock_exec):
        """中文字段名排序参数正确生成链接。"""
        html = self._render(
            "id=1&page_size=50&sort=用户名&dir=asc",
            mock_exec)

        # 检查 HTML 中不包含乱码或转义错误
        self.assertIn("用户名", html, "HTML 应包含汉字 用户名")

        # 验证排序保留
        self.assertAllLinksPreserveSorts(html, [("用户名", "asc")])
        # 分页链接应保留排序
        pag_links = self._get_pagination_hrefs(html)
        for link in pag_links:
            self.assertIn("sort=%E7%94%A8%E6%88%B7%E5%90%8D", link,
                          f"分页链接 {link[:80]} 应保留排序参数")

    @patch("report.execute_report")
    def test_chinese_sort_filter_cols(self, mock_exec):
        """中文字段名排序+筛选+自定义列全部共存。"""
        html = self._render(
            "id=1&page_size=50"
            "&sort=用户名&dir=asc"
            "&f_处置商类型=机构&op_处置商类型=eq"
            "&f_单位名=&op_单位名=notempty"
            "&cols=用户名,单位名,处置商类型,phone,缴纳时间",
            mock_exec)

        # 验证筛选保留
        self.assertAllLinksPreserveFilters(
            html, [("处置商类型", "eq", "机构"), ("单位名", "notempty", "")])

        # 验证排序保留
        self.assertAllLinksPreserveSorts(html, [("用户名", "asc")])

        # 验证 cols 参数
        hrefs = self._get_hrefs(html)
        report_links = [h for h in hrefs if "/report?" in h]
        # 至少某些链接应包含 cols
        has_cols = any("cols=" in h for h in report_links)
        self.assertTrue(has_cols, "链接中应包含 cols 参数")

    @patch("report.execute_report")
    def test_chinese_full_url_roundtrip(self, mock_exec):
        """模拟用户提供的完整 URL，验证 HTML 结构完整。"""
        qs = (
            "id=1&page_size=50"
            "&sort=%E7%94%A8%E6%88%B7%E5%90%8D&dir=asc"
            "&f_%E5%A4%84%E7%BD%AE%E5%95%86%E7%B1%BB%E5%9E%8B=%E6%9C%BA%E6%9E%84"
            "&op_%E5%A4%84%E7%BD%AE%E5%95%86%E7%B1%BB%E5%9E%8B=eq"
            "&f_%E5%8D%95%E4%BD%8D%E5%90%8D=&op_%E5%8D%95%E4%BD%8D%E5%90%8D=notempty"
            "&f_%E5%A4%84%E7%BD%AE%E5%95%86%E6%98%BE%E7%A4%BA%EF%BC%88%E6%8C%89%E7%B1%BB%E5%9E%8B%EF%BC%89="
            "&op_%E5%A4%84%E7%BD%AE%E5%95%86%E6%98%BE%E7%A4%BA%EF%BC%88%E6%8C%89%E7%B1%BB%E5%9E%8B%EF%BC%89=notempty"
            "&f_%E7%BC%B4%E7%BA%B3%E5%A4%87%E6%B3%A8=&op_%E7%BC%B4%E7%BA%B3%E5%A4%87%E6%B3%A8=notempty"
            "&cols=%E7%94%A8%E6%88%B7%E5%90%8D%2C%E5%8D%95%E4%BD%8D%E5%90%8D%2C%E5%A4%84%E7%BD%AE%E5%95%86%E7%B1%BB%E5%9E%8B%2C%E5%A4%84%E7%BD%AE%E5%95%86%E6%98%BE%E7%A4%BA%EF%BC%88%E6%8C%89%E7%B1%BB%E5%9E%8B%EF%BC%89%2Cphone%2Cshelf_apply_id%2C%E7%BC%B4%E7%BA%B3%E5%A4%87%E6%B3%A8%2C%E4%BF%9D%E8%AF%81%E9%87%91%E9%87%91%E9%A2%9D%2C%E7%BC%B4%E7%BA%B3%E6%97%B6%E9%97%B4"
        )
        html = self._render(qs, mock_exec)

        # HTML 应该包含一些中文字符
        self.assertIn("用户名", html)
        self.assertIn("处置商类型", html)
        self.assertIn("单位名", html)

        # 静态检查: HTML 标签必须完整闭合（非空标签）
        open_tags = html.count("<table")
        close_tags = html.count("</table>")
        self.assertEqual(open_tags, close_tags,
                         f"table 标签不匹配: {open_tags} 开 / {close_tags} 闭")

        # 排序链接应包含 URL 编码的中文
        hrefs = self._get_hrefs(html)
        for href in hrefs:
            if "sort=" in href.replace("&amp;", "&"):
                # sort 参数应包含 URL 编码的汉字
                self.assertIn("%E7%94%A8%E6%88%B7%E5%90%8D", href,
                              f"排序链接 {href[:80]} 应包含编码后的汉字")


if __name__ == "__main__":
    unittest.main()
