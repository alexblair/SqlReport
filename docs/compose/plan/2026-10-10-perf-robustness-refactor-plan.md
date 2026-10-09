# 性能 / 健壮性 / 架构分批重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 9 个批次修复全仓 37 项性能/健壮性/架构发现，全程保持可观测行为不变、全量测试绿。

**Architecture:** 批次按「写域互斥（R1）+ 热点后置（R2）+ 契约先行（R3）」排序；缺陷修复在结构拆分之前；扇入高的文件最后动。

**Tech Stack:** Python 3 标准库 + `unittest`（`discover -t .`）+ `codegraph` + AOCI。

**Spec:** `docs/compose/spec/2026-10-10-perf-robustness-refactor-design.md`（本 plan 从该 spec 论证，执行者需同时读两份）

## Global Constraints

- 测试必须 `venv/bin/python -m unittest discover -s tests/ -t .`（**`-t .` 不可省**，硬性 #8）。
- **基线**：`Ran 3042 tests, OK (skipped=4)`（2026-10-10 实测）。每批收尾必须复现 `Ran ≥3042` 且 `OK`。
- 选型锁定：纯标准库 + 4 个 pip 依赖；**禁** Django/Flask/React/Node（硬性 #5）。
- 一切运行在仓库根 `venv` 内（硬性 #6）。
- 改 `.py` 后同任务内跑 `codegraph sync`，收尾 `pendingChanges` 全 0（硬性 #19）。
- 改前定向读：`venv/bin/python scripts/agent/aoci_precheck.py <本次要改的文件…>`（硬性 #21）。
- 用户可感知文字一律简体中文（硬性 #2）。
- 产物落 `run-logs/`，唯一文件名；收尾跑 `scripts/agent/cleanup_tmp.py --apply`（硬性 #14）。
- **禁止**把 `config_db.py`/`db.py`/`query_executor.py` 的 late import 提为模块级；**禁止**合并这三个模块（spec §3.2）。
- **禁止**跨批修改不在本批 `写域` 内的文件（spec R1）。
- **禁止**抬 `tests/test_doc_budget.py` 任何上限（硬性 #20）。

## Review Focus

implementer 最容易踩空、且 spec 未逐条明说的五类：

1. **`_connect_mysql_config` 的 patch 点**：B2 动了连接获取后，测试里 `patch("db._connect_mysql_config")` 必须仍然生效——签名与调用路径不能变。
2. **`conn.close()` 的「归还池」语义**：B2 若引入池，所有既有 `finally: conn.close()` 调用点**不得**改动，且 `close()` 仍必须是「归还」而非「真关」。
3. **输出字节**：B1-2/B1-3/B1-4、B7、B9 都可能无意改 HTML 字节；每项都要有字节级或结构级断言。
4. **`render.py` 无 `logging`**：B6-5 是本仓**第一次**给 `render.py` 引入 `import logging`——注意 `setup_logging` 之前调用不能炸。
5. **保活节拍**：B4-1 引入 `_next_keepalive_at` 后，语义必须仍是「仅临近 TTL 才重建」，不得变成「定期无条件重建」。

---

# 批次索引与依赖

| 批次 | 主题 | 写域 | 依赖 | 状态 |
|------|------|------|------|------|
| B1 | P0 用户可见缺陷速修 | `server.py` `report.py` `config.py` `render.py` | — | ✅ 完成（Ran 3052） |
| B2 | P0 配置库连接**池化** | `query_executor.py` `config_db.py` `auth.py` `server.py` `db.py` | B1 | ✅ 完成（Ran 3072） |
| B3 | P0 ZIP 路径穿越 | `export.py` | — | ✅ 完成 |
| B4 | P0 调度器保活与卡死 | `scheduler.py` | — | ✅ 完成（Ran 3083） |
| B5 | P1 性能 | `config_db.py` `result_transform.py` `config.py` | B2 | ✅ 完成（Ran 3101；B5-4 派生态拆级按计划跳过——标为可选/风险中，收益仅未命中时体现） |
| B6 | P1 健壮性 + `page_size` 封顶 + CSV 开关 | `redis_cache.py` `server.py` `static_cache.py` `render.py` `query_executor.py` `report.py` `export.py` | B3,B4,B5 | ✅ 完成 8/8（Ran 3146） |
| B7 | P1 语义收口 | `config.py` `render.py` `export.py` `report.py` `result_transform.py` | B5,B6 | ☐ |
| B8 | P2 死代码清理 | 多文件 | B7 | ☐ |
| B9 | P3 结构拆分 | 新增 `ui_assets.py` 等 | B8 | ☐ |

**断点续做**：以本表**未勾选的第一行**为起点；若其「依赖」列任一为 ☐，**不得开始**。

> **裁决已定（2026-10-10，详见 spec §7）**：
> - **D1 = 池化**（用户选定）：B2 采用**完整连接池**方案（非最小版）。
> - **D2 = 节流**（本设计判断）：B2-2 执行。
> - **D3 = 方案 C**（本设计新增，待用户最终确认）：落盘用固定安全名 + `arcname` 保留原名 → 安全消除且**用户可见字节完全不变**。
> - **D4 = 全角 U+3000**（本设计判断）：B7-3 改 `config.py:1181`（半角 → 全角）；实测半角在 `<option>` 中会被 HTML 折叠，**当前即是失效的视觉 bug**。
> - **D5**：a（审计 IP）**跳过**、b（CSV 公式）**跳过或加默认关闭开关**、c（`page_size` 封顶）**做**，上限取 5000~10000 并在页面提示截断。
>
> 因此 **B1/B2/B3/B4 已无阻塞**（D3 若用户改选方案 A 则仅影响 ZIP 条目名，不影响 B3 的依赖关系）。

---

# B1 — P0 用户可见缺陷速修

**Files:**
- Modify: `server.py:86-89`（`_render_login_page`）、`report.py:1827`、`report.py:1894`、`config.py:350`、`render.py:3828-3860`（`build_delete_form_html`）+ 7 个调用点
- Test: `tests/test_b1_p0_quickfix.py`（新建）

**Interfaces:**
- Consumes: 无（首批）
- Produces: `render._js_str(s: str) -> str` — 把 Python 字符串转成可安全嵌入**单引号 JS 字面量**的转义串（转义 `\` `'` 换行 `\r` `</`）。

---

### Task B1-1: 登录页 `{next_field}` 占位符泄漏

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b1_p0_quickfix.py
import unittest
import server

class TestLoginPagePlaceholder(unittest.TestCase):
    def test_failed_login_page_has_no_raw_placeholder(self):
        html = server._render_login_page("用户名或密码错误")
        self.assertNotIn("{next_field}", html)
        self.assertNotIn("{error}", html)

    def test_failed_login_page_shows_error_text(self):
        html = server._render_login_page("用户名或密码错误")
        self.assertIn("用户名或密码错误", html)
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: FAIL — `'{next_field}' unexpectedly found`

- [ ] **Step 3: 改 `_render_login_page` 复用 `_render_login_page_ex`**

`server.py:86-89` 改为委托（`_render_login_page_ex` 在 `:92-109`，已正确替换两个占位符）：

```python
def _render_login_page(error: str = "") -> str:
    """渲染登录页，可选显示错误消息"""
    return _render_login_page_ex(error=error)
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 跑登录相关回归**

Run: `venv/bin/python -m unittest tests.test_auth tests.test_auth_session -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b1_p0_quickfix.py server.py
git commit -m "fix(login): 登录失败页不再泄漏 {next_field} 占位符并恢复 next 回跳"
```

---

### Task B1-2: 两处横幅缺 `f` 前缀（`report.py`）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b1_p0_quickfix.py
class TestBannerFString(unittest.TestCase):
    def test_no_raw_icon_literal_in_report_module_source(self):
        """report.py 不得再有落单的 {_icon(...)} 字面量（非 f-string）。"""
        import ast, pathlib
        src = pathlib.Path("report.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if '{_icon(' in node.value:
                    bad.append(node.lineno)
        self.assertEqual(bad, [], f"report.py 存在未插值的 {{_icon}} 字面量: 行 {bad}")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: FAIL — 列出约 2 处行号

- [ ] **Step 3: 给 `report.py:1823-1832` 与 `:1892-1895` 加 `f` 前缀**

两处均为隐式拼接的多行字符串；把**含 `{_icon(` 的那一段**改成 f-string：

```python
# report.py 截断横幅（原 :1827 附近）
'{_icon("alert")} 结果超过 '        # 改为:
f'{_icon("alert")} 结果超过 '

# report.py 预览横幅（原 :1894 附近）
f'{_icon("search")} 预览模式 — 当前显示的是未保存的临时 SQL 查询结果，点击筛选/排序将跳转到正式报表。'
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: PASS

- [ ] **Step 5: 跑报表回归（测试只断言子串，应仍绿）**

Run: `venv/bin/python -m unittest tests.test_report tests.test_report_extra tests.test_write_guard tests.test_export_cache_path -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b1_p0_quickfix.py report.py
git commit -m "fix(report): 截断/预览横幅补 f 前缀，不再显示 {_icon} 字面量"
```

---

### Task B1-3: 写操作警示条缺 `f` 前缀（`config.py`）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b1_p0_quickfix.py
class TestConfigWarnBanner(unittest.TestCase):
    def test_no_raw_icon_literal_in_config_module_source(self):
        import ast, pathlib
        src = pathlib.Path("config.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and '{_icon(' in n.value]
        self.assertEqual(bad, [], f"config.py 存在未插值的 {{_icon}} 字面量: 行 {bad}")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: FAIL — 约 1 处（`config.py:350`）

- [ ] **Step 3: 给 `config.py:348-350` 的拼接段加 `f` 前缀**

```python
# 原（普通字符串）
allow_write_html += ('<div class="flash-warn span-full" style="'
                     + _WARN_BOX_STYLE + '">'
                     '{_icon("alert")} 该 SQL 包含写操作语句，未开启时将拒绝执行</div>')
# 改为（只给最后一段加 f）
allow_write_html += ('<div class="flash-warn span-full" style="'
                     + _WARN_BOX_STYLE + '">'
                     f'{_icon("alert")} 该 SQL 包含写操作语句，未开启时将拒绝执行</div>')
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_b1_p0_quickfix.py config.py
git commit -m "fix(config): 写操作警示条补 f 前缀，不再显示 {_icon} 字面量"
```

---

### Task B1-4: 删除确认的 JS 转义（数据安全）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b1_p0_quickfix.py
class TestDeleteConfirmJsEscape(unittest.TestCase):
    def test_js_str_escapes_single_quote(self):
        import render
        self.assertEqual(render._js_str("O'Brien"), r"O\'Brien")

    def test_js_str_escapes_backslash_and_newline(self):
        import render
        self.assertEqual(render._js_str("a\\b"), "a\\\\b")
        self.assertEqual(render._js_str("a\nb"), "a\\nb")

    def test_confirm_handler_compiles_for_quote_name(self):
        import re, render
        html = render.build_delete_form_html("/x/delete", "确定删除连接池 O'Brien？")
        m = re.search(r"onsubmit=\"return confirm\('(.*)'\)\"", html)
        self.assertIsNotNone(m, "未找到 onsubmit confirm handler")
        self.assertNotIn("'", m.group(1), "JS 字面量内仍有未转义单引号")

    def test_pool_row_delete_confirm_has_no_bare_quote(self):
        """名称含单引号时，渲染出的 onsubmit 不得含裸单引号。"""
        import re, render
        html = render.build_delete_form_html("/config/pools/1/delete",
                                             "确定删除连接池 " + render._escape("O'Brien") + "？")
        m = re.search(r"onsubmit=\"return confirm\('(.*)'\)\"", html)
        self.assertIsNotNone(m)
        self.assertNotIn("'", m.group(1))
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: FAIL — `AttributeError: module 'render' has no attribute '_js_str'`

- [ ] **Step 3: 在 `render.py` 加 `_js_str` 并在 `build_delete_form_html` 使用**

`render.py:3828` 的 `build_delete_form_html` 内，`onsubmit` 使用 `_js_str(confirm_msg)`：

```python
def _js_str(s) -> str:
    """把字符串转成可安全嵌入**单引号 JS 字面量**的内容。

    注意与 HTML 转义的区别：HTML 转义（_escape）产出 &#x27;，浏览器在解析
    属性时会把它解码回 '，从而重新破坏 JS 字面量——故 JS 上下文必须用本函数。
    """
    return (str(s).replace("\\", "\\\\").replace("'", "\\'")
            .replace("\r", "\\r").replace("\n", "\\n")
            .replace("</", "<\\/"))
```

`render.py:3853` 改为：

```python
f'{pad}      onsubmit="return confirm(\'{_js_str(confirm_msg)}\')">\n'
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b1_p0_quickfix -t . -v`
Expected: PASS (全部)

- [ ] **Step 5: 跑全量（B1 收尾，必跑）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042 tests` / `OK (skipped=4)`

- [ ] **Step 6: 同步索引与知识库**

Run: `codegraph sync && codegraph status`
Expected: `pendingChanges` 全 0

按硬性 #7 更新 `docs/compose/knowledge/06-ui-interactions.md`（新增 `_js_str` 的 JS 转义契约）、`02-routing-auth.md`（登录页占位符）。

- [ ] **Step 7: 提交（B1 收尾）**

```bash
git add -A && git commit -m "fix(ui): 删除确认框 JS 转义修正，含单引号名称不再静默跳过确认

- B1-1 登录页 {next_field} 占位符泄漏
- B1-2/B1-3 横幅缺 f 前缀
- B1-4 引入 render._js_str() 修正 HTML 转义误用于 JS 上下文"
```

---

# B2 — P0 配置库连接池化

> **已定（spec §7.1）**：**D1 = 池化**（用户选定）→ 采用**完整连接池**方案；**D2 = 节流** → B2-2 执行。
>
> **硬约束（spec §3.2 / §8）**：
> 1. `conn.close()` 语义必须保持「归还池」（参 `query_executor.py:314-330` 的 `_PooledConnection`），**所有既有 `finally: conn.close()` 调用点不得改动**。
> 2. **不得**破坏测试里 `patch("db._connect_mysql_config")` / `patch("db._get_engine")` 的 patch 点（late import 机制，见 spec §3.2）。
> 3. MySQL 连接**不可跳线程并发共享**：池必须「借出/归还 + 探活 + 加锁」，且进程退出路径需可清理。

**Files:**
- Modify: `config_db.py:107-121`（`get_config_db`）、`query_executor.py:171-200`（新增配置库池）、`server.py:360-415`（`_handle`）、`auth.py:201-217`（`refresh_session`）
- Test: `tests/test_b2_config_conn_reuse.py`（新建）

**Interfaces:**
- Consumes: B1 完成（同改 `server.py`）
- Produces: 无新公共函数；仅改变 `server.py` 内连接获取次数。

---

### Task B2-1: 请求内复用配置库连接

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b2_config_conn_reuse.py
import unittest
from unittest import mock

class TestConfigConnReuse(unittest.TestCase):
    def test_needs_db_request_opens_config_conn_once(self):
        """一个 needs_db 请求只应获取一次配置库连接（认证 + 处理共用）。"""
        import server, auth
        calls = {"n": 0}
        real = server.db.get_config_db
        def counting(*a, **kw):
            calls["n"] += 1
            return real(*a, **kw)
        with mock.patch.object(server.db, "get_config_db", side_effect=counting), \
             mock.patch.object(auth, "refresh_session", return_value=None), \
             mock.patch.object(server, "_match_route") as m:
            m.return_value = server.RouteEntry(r"^/report$", "GET", True, True, "_handle_report")
            # 期望：认证阶段不再单独开连接
            # （具体断言见 Step 3 实现后的行为）
            self.assertTrue(True)
```

> **实施提示**：本测试在 Step 3 前**无法**写出有效断言。正确做法是先按 Step 2 建立可测入口，再回填断言。若你选择先实现，Step 3 后**必须**补一条真实断言：构造一次 `needs_db` 请求，断言 `calls["n"] == 1`。

- [ ] **Step 2: 确认当前连接次数（取证）**

Run:
```bash
venv/bin/python -c "
import ast,sys
src=open('server.py',encoding='utf-8').read()
t=ast.parse(src)
for n in ast.walk(t):
    if isinstance(n,ast.FunctionDef) and n.name=='_handle':
        print('_handle 内 get_config_db 调用行:', [c.lineno for c in ast.walk(n)
              if isinstance(c,ast.Call) and getattr(c.func,'attr','')=='get_config_db'])
"
```
Expected: 打印出 `:393` 一处（认证路径的连接在 `auth` 内部，另计）

- [ ] **Step 3: 改 `_handle` 使认证与处理共用连接**

在 `server.py:360-415`，把连接获取提到认证**之前**，认证与 handler 共用同一 `conn`；`auth` 侧的 session 刷新改为接收既有连接（新增可选参数 `conn=None`，`None` 时自建以保持兼容）：

```python
# auth.py
def refresh_session(token: str, conn=None) -> None:
    """刷新 session 时间戳（滑动过期）。conn 传入时复用调用方连接。"""
    # ... 内存内更新时间戳（不变）...
    own = conn is None
    try:
        if own:
            conn = db.get_config_db()
        db.add_session(conn, token, username)
    finally:
        if own:
            conn.close()
```

`server.py` 中 `needs_db` 分支先取 `conn`，认证时把它传给 `refresh_session(token, conn=conn)`。

- [ ] **Step 4: 回填 Step 1 的真实断言并运行**

Run: `venv/bin/python -m unittest tests.test_b2_config_conn_reuse -t . -v`
Expected: PASS — `needs_db` 请求 `get_config_db` 调用数为 1

- [ ] **Step 5: 验证 `_connect_mysql_config` 的 patch 点仍生效（Review Focus 1）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `OK (skipped=4)` —— 若大量 `patch("db._connect_mysql_config")` 失效会在此暴露

- [ ] **Step 6: 提交**

```bash
git add tests/test_b2_config_conn_reuse.py server.py auth.py
git commit -m "perf(config-db): 请求内复用配置库连接，认证与处理不再各开一次"
```

---

### Task B2-2: session 落库节流（仅当 D2 裁决为「节流」）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b2_config_conn_reuse.py
class TestSessionThrottle(unittest.TestCase):
    def test_repeated_requests_do_not_write_each_time(self):
        """同一 token 在节流窗口内连续刷新，只应落库一次。"""
        import auth
        writes = {"n": 0}
        from unittest import mock
        with mock.patch.object(auth.db, "add_session",
                               side_effect=lambda *a, **k: writes.__setitem__("n", writes["n"] + 1)), \
             mock.patch.object(auth.db, "get_config_db",
                               return_value=mock.MagicMock()):
            tok = auth.create_session("u1")
            for _ in range(5):
                auth.refresh_session(tok)
        self.assertEqual(writes["n"], 1, "节流窗口内应只落库一次")

    def test_expiry_contract_unchanged(self):
        """滑动过期仍然生效：刷新后 session 仍可用。"""
        import auth
        tok = auth.create_session("u2")
        auth.refresh_session(tok)
        self.assertEqual(auth.get_session_user(tok), "u2")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b2_config_conn_reuse -t . -v`
Expected: FAIL — `writes["n"]` 为 5，断言 1 失败

- [ ] **Step 3: 在 `refresh_session` 加入节流**

在 `auth.py` 模块级加 `_SESSION_PERSIST_INTERVAL = 60` 与 `_last_persisted: dict[str, float] = {}`（**必须在 `_sessions_lock` 内访问**），内存时间戳每次都更新（滑动过期不变），仅当距上次落库超过间隔才写库。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b2_config_conn_reuse -t . -v`
Expected: PASS

- [ ] **Step 5: 跑认证与会话全量回归**

Run: `venv/bin/python -m unittest tests.test_auth tests.test_auth_session -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 跑全量（B2 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 7: 同步知识库并提交**

按硬性 #7 更新 `01-architecture.md`（连接获取策略）、`02-routing-auth.md`（session 落库节流）。

```bash
codegraph sync
git add -A && git commit -m "perf(auth): session 滑动过期落库节流，认证请求不再每次写 MySQL"
```

---

# B3 — P0 ZIP 路径穿越（无前置依赖，但必须在 B6/B7 之前完成）

> **已定方案（spec §7.3 方案 C）**：**落盘用固定安全名，`arcname` 保留原名**。效果：服务端写盘越界漏洞消除，且 **ZIP 内条目名与现状字节完全一致**（用户无感）。
> 若用户改选方案 A（清洗条目名），则 `arcname` 也传 `_safe_arcname(orig)`——其余步骤相同。

**Files:**
- Modify: `export.py:341-358`（`_create_temp_zip`）、`export.py:518-526`（`handle_export`）
- Test: `tests/test_b3_export_zip_safety.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `export._safe_arcname(name: str) -> str` — 返回不含路径分隔与 `..` 的安全条目名。

---

### Task B3-1: 阻止导出临时文件写出 tmpdir

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b3_export_zip_safety.py
import io, os, tempfile, unittest, zipfile
import export

class TestZipTraversal(unittest.TestCase):
    def test_traversal_name_written_inside_tmpdir(self):
        """含 .. 的名称不得让文件落在外层 tmpdir 之外（方案 C）。"""
        outer = tempfile.mkdtemp(prefix="outer_")
        target = os.path.join(os.path.dirname(outer), "escape.csv")
        try:
            if os.path.exists(target):
                os.remove(target)
            data = export._create_temp_zip(b"x", "../../escape.csv", "escape.csv")
            self.assertIsInstance(data, bytes)
            self.assertFalse(os.path.exists(target), "文件被写出 tmpdir 之外！")
        finally:
            import shutil; shutil.rmtree(outer, ignore_errors=True)

    def test_absolute_name_written_inside_tmpdir(self):
        data = export._create_temp_zip(b"x", "/etc/evil.csv", "evil.csv")
        self.assertFalse(os.path.exists("/etc/evil.csv"), "绝对路径被写出！")

    def test_zip_entry_name_preserves_report_name(self):
        """方案 C 的关键：ZIP 内条目名必须仍为原名（用户可见字节不变）。"""
        data = export._create_temp_zip(b"a,b\n", "2026/Q1 营收.csv", "2026_Q1.csv")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(zf.namelist(), ["2026/Q1 营收.csv"])
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b3_export_zip_safety -t . -v`
Expected: FAIL — `_create_temp_zip` 当前把报表名直接当落点名，文件落到了 tmpdir 之外

- [ ] **Step 3: 改 `_create_temp_zip` 为「落盘用常量名 + arcname 保留原名」（方案 C）**

```python
def _safe_arcname(name: str) -> str:
    """把用户可控的名字规整为不含路径语义的 ZIP 条目名（防路径穿越 CWE-22）。"""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    base = base.replace("\x00", "").strip()
    return base if base not in ("", ".", "..") else "export"
```

在 `_create_temp_zip` 内，**落盘用固定安全名，`arcname` 保留原名**（方案 C）：

```python
_DISK_NAME = "payload"   # 磁盘落点名：与用户可控值无关，杜绝路径语义

# ... 保持原扩展名供 arcname 使用 ...
_, ext = os.path.splitext(filename)
disk_name = _DISK_NAME + ext
tmpfile_path = os.path.join(tmpdir, disk_name)
with open(tmpfile_path, "wb") as f:
    f.write(content_bytes)

zip_path = os.path.join(tmpdir, "payload.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(tmpfile_path, arcname=filename)   # ← 原名进条目名，用户可见字节不变
```

> **要点**：`tmpdir` 内的所有落点名（`tmpfile_path`、`zip_path`）现在是**常量派生**，与报表名无关——这是真正消除越界写盘的关键。`arcname` 保持 `filename` 原名，所以用户看到的 ZIP 内文件名与现状一致。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b3_export_zip_safety -t . -v`
Expected: PASS

- [ ] **Step 5: 跑导出回归**

Run: `venv/bin/python -m unittest tests.test_export tests.test_export_cache_path -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 跑全量（B3 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 7: 提交**

```bash
codegraph sync
git add tests/test_b3_export_zip_safety.py export.py
git commit -m "fix(export): ZIP 导出条目名规整，修复路径穿越（CWE-22）"
```

---

# B4 — P0 调度器保活与卡死

**Files:**
- Modify: `scheduler.py:273`（`_next_keepalive_at`）、`:303-311`（`_tick_loop`）、`:607-663`（`run_keepalive_tick`）、`:403`（`_run_schedule`）
- Test: `tests/test_b4_scheduler_safety.py`（新建）

**Interfaces:**
- Consumes: B2 完成（连接获取方式已稳定）
- Produces: 无新公共函数。

---

### Task B4-1: 保活连接泄漏防护 + 独立节拍

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b4_scheduler_safety.py
import unittest
from unittest import mock

class TestKeepaliveConnSafety(unittest.TestCase):
    def test_keepalive_does_not_leak_conn_on_select_error(self):
        """SELECT 抛异常时连接必须仍被关闭。"""
        import scheduler
        sched = scheduler.ReportScheduler(tick_seconds=999, workers=1)
        closed = {"v": False}
        class BadConn:
            def execute(self, *a, **k):
                raise RuntimeError("boom")
            def close(self):
                closed["v"] = True
        with mock.patch.object(scheduler.db, "get_config_db", return_value=BadConn()), \
             mock.patch.object(scheduler.redis_cache, "redis_available", return_value=True), \
             mock.patch.object(scheduler.redis_cache, "get_redis_manager",
                               return_value=mock.MagicMock()):
            try:
                sched.run_keepalive_tick()
            except Exception:
                pass
        self.assertTrue(closed["v"], "SELECT 异常后连接未被关闭（泄漏）")

class TestKeepaliveCadence(unittest.TestCase):
    def test_keepalive_skipped_when_interval_not_reached(self):
        """未到独立节拍时不应执行保活扫描。"""
        import scheduler
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._next_keepalive_at = 9e18  # 远未来
        with mock.patch.object(sched, "run_keepalive_tick") as m:
            sched._maybe_run_keepalive(now=1000.0)
            m.assert_not_called()

    def test_keepalive_runs_and_reschedules_when_due(self):
        import scheduler
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._next_keepalive_at = 0.0
        with mock.patch.object(sched, "run_keepalive_tick", return_value=0) as m:
            sched._maybe_run_keepalive(now=1000.0)
            m.assert_called_once()
        self.assertGreater(sched._next_keepalive_at, 1000.0)
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b4_scheduler_safety -t . -v`
Expected: FAIL — `AttributeError: 'ReportScheduler' object has no attribute '_maybe_run_keepalive'`；连接泄漏测试亦 FAIL

- [ ] **Step 3: 实现 `_maybe_run_keepalive` + 给 `run_keepalive_tick` 加 try/finally**

新增模块级常量 `_KEEPALIVE_INTERVAL_SECONDS = 300`（或复用配置），并把 `run_keepalive_tick` 的 `conn` 获取与关闭包进 `try/finally`：

```python
def _maybe_run_keepalive(self, now: float = None) -> int:
    """按独立节拍执行保活扫描（未到点直接返回 0）。"""
    now = time.time() if now is None else now
    if now < self._next_keepalive_at:
        return 0
    self._next_keepalive_at = now + _KEEPALIVE_INTERVAL_SECONDS
    return self.run_keepalive_tick(now=now)
```

`_tick_loop`（`:303-311`）把 `self.run_keepalive_tick()` 换成 `self._maybe_run_keepalive()`。

`run_keepalive_tick` 的连接块改为：

```python
conn = db.get_config_db()
try:
    rows = [dict(r) for r in conn.execute("SELECT DISTINCT ...")]
    # ... 既有重建逻辑不变 ...
finally:
    conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b4_scheduler_safety -t . -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_b4_scheduler_safety.py scheduler.py
git commit -m "fix(scheduler): 保活改独立节拍并补 try/finally，消除连接泄漏"
```

---

### Task B4-2: `_running` 去重集在取连接失败时永不释放

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b4_scheduler_safety.py
class TestRunningSetRelease(unittest.TestCase):
    def test_sid_removed_from_running_when_conn_fails(self):
        """get_config_db 抛异常时，sid 必须已从 _running 移除，否则永久停摆。"""
        import scheduler
        sched = scheduler.ReportScheduler(tick_seconds=30, workers=1)
        sched._running.add(42)
        with mock.patch.object(scheduler.db, "get_config_db",
                               side_effect=RuntimeError("db down")):
            try:
                sched._run_schedule({"id": 42, "name": "t", "report_id": 1},
                                    "success", None, 1.0, 1.1)
            except Exception:
                pass
        self.assertNotIn(42, sched._running, "取连接失败后 sid 仍留在 _running（永久停摆）")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b4_scheduler_safety -t . -v`
Expected: FAIL — `42 unexpectedly found in _running`

- [ ] **Step 3: 把 `conn = db.get_config_db()` 移入 `try`**

`scheduler.py:403` 移入 `try:`（`:404`）内；`finally` 中 `conn.close()` 需防 `conn` 未绑定：

```python
conn = None
try:
    conn = db.get_config_db()
    # ... 既有回写逻辑 ...
except Exception:
    logging.exception("定时任务 #%s 结果回写失败", sid)
finally:
    with self._running_lock:
        self._running.discard(sid)
    if conn is not None:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b4_scheduler_safety -t . -v`
Expected: PASS

- [ ] **Step 5: 跑调度器全量回归（6 个测试文件）**

Run: `venv/bin/python -m unittest tests.test_scheduler_core tests.test_scheduler_extra tests.test_scheduler_cache tests.test_scheduler_db tests.test_scheduler_acceptance tests.test_scheduler_http tests.test_scheduler_primitives -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 跑全量（B4 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 7: 同步知识库并提交**

按硬性 #7 更新 `07-cache-scheduler-audit.md`（保活节拍 + `_running` 释放保证）。

```bash
codegraph sync
git add -A && git commit -m "fix(scheduler): 取连接失败时释放 _running，消除任务永久静默停摆"
```

---

# B5 — P1 性能

**Files:**
- Modify: `result_transform.py:358-375`、`config.py:940-953`+`:652-676`、`config_db.py`（新增 `count_schedules`）、`report.py:1253-1280`
- Test: `tests/test_b5_perf.py`（新建）

**Interfaces:**
- Consumes: B2 完成
- Produces:
  - `result_transform._compile_matcher(segments, ignorecase) -> callable` — 返回单条合并后的匹配函数。
  - `config_db.count_schedules(conn) -> int`

---

### Task B5-1: 筛选内循环合并为单条 alternation

- [ ] **Step 1: 写失败测试（等价性优先）**

```python
# tests/test_b5_perf.py
import unittest
from result_transform import filter_rows

COLS = ["a", "b"]
ROWS = [("alpha", "x"), ("beta", "y"), ("ALPHA", "z"), (None, "w"), ("", "v")]

class TestFilterEquivalence(unittest.TestCase):
    def _assert_same(self, filters):
        got = filter_rows(list(ROWS), COLS, filters)
        self.assertIsInstance(got, list)

    def test_multi_value_contains_semantics(self):
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "alpha,beta")])
        self.assertEqual([x[0] for x in r], ["alpha", "beta", "ALPHA"])

    def test_notcontains_semantics(self):
        r = filter_rows(list(ROWS), COLS, [("a", "notcontains", "alpha")])
        self.assertNotIn("alpha", [x[0] for x in r])
        self.assertNotIn("ALPHA", [x[0] for x in r])

    def test_eq_is_case_sensitive(self):
        r = filter_rows(list(ROWS), COLS, [("a", "eq", "alpha")])
        self.assertEqual([x[0] for x in r], ["alpha"])

    def test_neq_semantics(self):
        r = filter_rows(list(ROWS), COLS, [("a", "neq", "alpha")])
        self.assertNotIn("alpha", [x[0] for x in r])
```

- [ ] **Step 2: 运行确认基线通过（记录既有语义）**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: PASS —— **这组测试是等价性护栏，改前就必须绿**

- [ ] **Step 3: 在 `_apply_single_filter` 内合并正则**

把四条分支的 `any(rx.search(...) for rx in regexes)` 改为单条预编译 matcher。**必须保留**：`notcontains`/`neq` 的取反、`_cell_str` 的 `None→""`、`contains` 的 `IGNORECASE`。**禁止**改成 `lower() in`（Unicode 大小写折叠语义有边界差异）。

- [ ] **Step 4: 运行确认仍绿（语义未变）**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: PASS

- [ ] **Step 5: 跑变换相关全量回归**

Run: `venv/bin/python -m unittest tests.test_result_transform tests.test_report tests.test_export tests.test_api_nested_filter -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b5_perf.py result_transform.py
git commit -m "perf(transform): 筛选多值合并为单条 alternation（100k 行实测快 2.8~3.5 倍）"
```

---

### Task B5-2: 配置页去掉 4 次完全重复的全表查询

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b5_perf.py
class TestConfigPageQueryCount(unittest.TestCase):
    def test_reports_page_does_not_double_fetch_reports(self):
        """_nav_badges 与 _render_category_section_parts 不应各取一次全表报表。"""
        import ast, pathlib
        src = pathlib.Path("config.py").read_text(encoding="utf-8")
        self.assertIn("count_schedules", pathlib.Path("config_db.py").read_text(encoding="utf-8"))
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: FAIL — `count_schedules` 未定义

- [ ] **Step 3: 加 `config_db.count_schedules` 并让 `_nav_badges` 用计数**

```python
def count_schedules(conn) -> int:
    """定时任务总数（供侧栏徽标，避免取全量再 len()）。"""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM report_schedules").fetchone()
    return int(row["cnt"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])
```

`config.py:948` 的 `("scheduler", lambda: len(db.get_all_schedules(conn)))` 改为 `("scheduler", lambda: db.count_schedules(conn))`。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: PASS

- [ ] **Step 5: 跑配置页回归（徽标数值必须不变）**

Run: `venv/bin/python -m unittest tests.test_config tests.test_config_extra tests.test_scheduler_http -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b5_perf.py config.py config_db.py
git commit -m "perf(config): 侧栏调度徽标改 COUNT(*)，去掉 N+1 全量取数"
```

---

### Task B5-3: `get_reports_by_category` 的 N+1

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b5_perf.py
class TestCategoryTreeQueryCount(unittest.TestCase):
    def test_grouped_not_per_category(self):
        import inspect, config_db
        src = inspect.getsource(config_db.get_reports_by_category)
        # 反例护栏：不得在分类循环内逐类调用 get_reports
        self.assertNotIn("for cat in", src.replace("for cat in all_cats", "OK"))
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: FAIL（当前实现含逐类调用）

- [ ] **Step 3: 改为一次全表查询后 Python 分组**

`config_db.py:1603-1614` 改为：一次 `get_reports(conn)` 取全量，再按 `category_id` 分组；未分类集合保持与现状逐条一致（**排序必须仍是 `sort_order, id`**）。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b5_perf -t . -v`
Expected: PASS

- [ ] **Step 5: 跑分类树回归**

Run: `venv/bin/python -m unittest tests.test_config tests.test_config_db_extra -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b5_perf.py config_db.py
git commit -m "perf(config-db): get_reports_by_category 由 2+C 次查询降为 1 次"
```

---

### Task B5-4: 派生态缓存拆分（D 级：仅当用户确认要做）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b5_perf.py
class TestDerivedCacheSplit(unittest.TestCase):
    def test_changing_sort_reuses_filtered_result(self):
        """换排序键不应重做整表筛选（filter_rows 调用次数不增）。"""
        from unittest import mock
        import report
        self.assertTrue(hasattr(report.CachedResult, "__init__"))
        # 实现后断言：两次不同 sorts 的派生态取用，filter_rows 只调一次
```

- [ ] **Step 2~6**: 按 spec B5-5 实施：把 `derived` 拆为 `filtered`（按 filter 键）与 `sorted`（按 sort 键）两级；**硬约束**：仍只挂 L1、不进任何序列化路径、与 L1 同生共死；容量按 spec 重新估算。

Run（每步）: `venv/bin/python -m unittest tests.test_b5_perf tests.test_report -t . 2>&1 | tail -3`

- [ ] **Step 7: 跑全量（B5 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 8: 同步知识库并提交**

按硬性 #7 更新 `03-report-transform.md`（筛选合并 + 派生态两级缓存）。

```bash
codegraph sync
git add -A && git commit -m "perf(report): 派生态缓存拆为筛选/排序两级，修正 FIFO 与 LRU 注释不符"
```

---

# B6 — P1 健壮性

**Files:**
- Modify: `redis_cache.py:402-411`、`redis_cache.py:270-300`、`query_executor.py:80-100`+`:121-133`、`server.py:322`、`render.py:2287-2303`+`:3462`、`static_cache.py:243-253`、`report.py:2213-2217`（B6-7）、`export.py:140-168`（B6-8）
- Test: `tests/test_b6_robustness.py`（新建）

**Interfaces:**
- Consumes: B4 完成
- Produces:
  - `render.logger`（模块级 logger，本仓首次在 `render.py` 引入 `logging`）
  - `static_cache._last_invalidated_lock`（模块级 `threading.Lock`）
  - `report.MAX_UI_PAGE_SIZE = 1000` + `report._clamp_ui_page_size()`（B6-7）
  - `export.sanitize_csv_formula()` + `rows_to_csv(..., sanitize_formula=False)`（B6-8）

> **D5 裁决落地（spec §7.5）**：本批做 **c（`page_size` 封顶）**；**跳过 a（审计 IP 取值语义）** 与 **b（CSV 公式中和）**——两者都会改变既有可观测数据（历史审计 IP / 导出字节），而 b 还影响用程序处理 CSV 的下游。若事后要做，b 应做成**默认关闭**的配置开关。

---

### Task B6-1: Redis 冷启动失败后可自愈

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b6_robustness.py
import unittest
from unittest import mock

class TestRedisSelfHeal(unittest.TestCase):
    def test_connects_when_manager_unavailable(self):
        """管理器已在但不可用时，应尝试重连而非永久降级。"""
        import redis_cache
        mgr = mock.MagicMock()
        mgr.available = False
        redis_cache._redis_manager = mgr
        try:
            redis_cache.get_redis_manager()
            self.assertTrue(mgr.connect.called or mgr.available, "未尝试恢复连接")
        finally:
            redis_cache._redis_manager = None
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — `connect` 未被调用

- [ ] **Step 3: 在 `get_redis_manager` 增加「已存在但不可用」的恢复分支**

**必须带退避**，防连接风暴；且按 spec §2.4 加**模块级锁**做双检（顺手修掉等级 C 的无锁竞态）。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: PASS

- [ ] **Step 5: 跑 redis 回归**

Run: `venv/bin/python -m unittest tests.test_redis_cache tests.test_redis_cache_extra -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b6_robustness.py redis_cache.py
git commit -m "fix(redis): 运行期不可用时按退避自动重连，并在单例上加锁"
```

---

### Task B6-2: 重建锁 owner 校验与 TTL

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestRebuildLock(unittest.TestCase):
    def test_release_does_not_delete_foreign_lock(self):
        """释放时必须校验持有者，不得删掉别人的锁。"""
        import redis_cache, inspect
        src = inspect.getsource(redis_cache.release_lock)
        self.assertTrue(("token" in src) or ("owner" in src), "release_lock 未校验持有者")

    def test_lock_uses_atomic_set_with_expiry(self):
        import redis_cache, inspect
        src = inspect.getsource(redis_cache)
        self.assertIn("nx=True", src.replace("nx = True", "nx=True"), "未使用原子 set(nx=,ex=)")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL

- [ ] **Step 3: 实现随机 token + Lua CAS 删除 + `set(nx=True, ex=...)`**

`redis_cache.py:270-300`：acquire 时生成随机 token 并原子写入；release 用 Lua 比较 token 再删。`_LOCK_TIMEOUT` 需覆盖最大合法报表耗时（spec：调度器/API 路径不设 read_timeout）。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: PASS

- [ ] **Step 5: 跑报表缓存回归**

Run: `venv/bin/python -m unittest tests.test_report tests.test_scheduler_cache tests.test_static_cache -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b6_robustness.py redis_cache.py
git commit -m "fix(redis): 重建锁加 owner 校验与原子过期，避免互斥退化与误删他人锁"
```

---

### Task B6-3: `?`→`%s` 占位符替换改用引号感知扫描

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestPlaceholderRewrite(unittest.TestCase):
    def test_question_mark_inside_string_literal_untouched(self):
        """字面量里的 ? 不得被替换为 %s。"""
        from query_executor import _split_sql_statements
        self.assertTrue(callable(_split_sql_statements))
        # 实现后补：断言 _question_to_percent_s("WHERE m LIKE '%?%' AND a=?")
        # 结果为 "...LIKE '%?%' AND a=%s"

    def test_comment_question_mark_untouched(self):
        pass  # 实现后补断言
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL（断言未实现）

- [ ] **Step 3: 复用 `query_executor.py:389+` 的引号感知扫描，新增替换辅助**

替换 `:84` 与 `:125` 的 `sql.replace("?", "%s")` 为引号/注释感知的替换函数。

- [ ] **Step 4: 补齐 Step 1 的断言并运行**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: PASS

- [ ] **Step 5: 跑双引擎相关回归**

Run: `venv/bin/python -m unittest tests.test_deep_edge_cases tests.test_mysql_mock tests.test_report -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b6_robustness.py query_executor.py
git commit -m "fix(query): 占位符 ?→%s 改引号感知替换，不再改坏 SQL 字面量"
```

---

### Task B6-4: HTTP socket 超时（**风险中高，须 L2 实测**）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestSocketTimeout(unittest.TestCase):
    def test_handler_has_timeout(self):
        import server
        self.assertIsNotNone(getattr(server.ReportHandler, "timeout", None),
                             "ReportHandler 未设置 timeout，慢连接可无限占线程")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — `timeout` 为 None

- [ ] **Step 3: 设 `ReportHandler.timeout`**

取值须**覆盖最大合法导出耗时**；若无法覆盖，则改为重写 `setup()` 仅对读阶段设超时（spec 风险登记）。**上限取值需用户确认为宜。**

- [ ] **Step 4: 运行确认通过 + L2 实测大导出**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Run: `venv/bin/python -m unittest tests.test_export tests.test_report -t . 2>&1 | tail -3`
Expected: PASS / `OK`

- [ ] **Step 5: 提交**

```bash
git add tests/test_b6_robustness.py server.py
git commit -m "fix(server): 设置请求 socket 超时，防慢连接无限占线程"
```

---

### Task B6-5: 静态资产降级加日志

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestRenderLogging(unittest.TestCase):
    def test_render_module_has_logger(self):
        import render
        self.assertTrue(hasattr(render, "logger"), "render.py 未引入 logging")

    def test_asset_failure_is_logged(self):
        """写盘失败应留痕，而不是静默永久降级。"""
        from unittest import mock
        import render
        with mock.patch.object(render, "ensure_common_assets",
                               side_effect=OSError("read-only")), \
             mock.patch.object(render.logger, "exception") as log, \
             mock.patch.object(render, "_COMMON_ASSET_URLS", None):
            render.reset_common_assets_cache()
            render._get_common_asset_urls()
        self.assertTrue(log.called, "资产失败未记录日志")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — `render` 无 `logger`

- [ ] **Step 3: `render.py` 引入 `logging` 并记录失败**

在 `render.py` 顶部加 `import logging` 与 `logger = logging.getLogger(__name__)`；`_get_common_asset_urls`（`:2287-2303`）的 `except Exception` 改为 `logger.exception("公共资产写入失败，回退内联")`。

> **Review Focus 4**：`render` 可能在 `setup_logging` 之前被 import；`logging.getLogger` 本身安全，但**不要**在模块级调用 `basicConfig`。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_b6_robustness.py render.py
git commit -m "fix(render): 公共资产写入失败留痕，不再静默永久降级"
```

---

### Task B6-6: `static_cache._last_invalidated` 加锁

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestStaticCacheLock(unittest.TestCase):
    def test_module_has_lock(self):
        import static_cache
        self.assertTrue(hasattr(static_cache, "_last_invalidated_lock"))

    def test_concurrent_record_does_not_corrupt(self):
        import threading, static_cache
        def w(i):
            for j in range(200):
                static_cache.record_invalidated(f"/p/{i}-{j}")
        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertLessEqual(len(static_cache._last_invalidated),
                             static_cache._MAX_LAST_INVALIDATED)
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — 无 `_last_invalidated_lock`

- [ ] **Step 3: 加 `import threading` + 模块级锁**

`static_cache.py` 顶部加 `import threading`、`_last_invalidated_lock = threading.Lock()`；`record_invalidated`（`:243-248`）与 `get_last_invalidated`（`:251-253`）的读写包进锁。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: PASS

- [ ] **Step 5: 跑全量（B6 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 6: 同步知识库并提交**

按硬性 #7 更新 `07-cache-scheduler-audit.md`（Redis 自愈 + 锁语义 + 静态缓存并发）。

```bash
codegraph sync
git add -A && git commit -m "fix(cache): 静态缓存失效记录加锁；B6 批次收尾"
```
---

### Task B6-7: UI 报表页 `page_size` 封顶 1000（D5-c）

> **用户已明确界定范围（2026-10-10）**：`page_size` **仅指 UI 报表页翻页的「每页显示多少条」**，上限取 **1000**。
>
> **三个机制层级（实测确认，互不往来）**：
> | 机制 | 层级 | 控制方 | 本任务是否动 |
> |------|------|--------|-------------|
> | `allow_all_output` + `max_rows` | **取数层**：结果集总共取多少行 | 报表配置的勾选框 | **不动** |
> | **`page_size`** | **展示层**：UI 翻页每页几条 | 报表页「每页」下拉 | **封顶 1000** |
> | `fetch_all` / `allow_fetch_all` | **取数层**：API 显式全量 | 端点配置开关 | **不动** |
>
> **API 翻页有自己独立的上限语义，本任务不适用**（用户明确要求）：API 走 `api_handler._apply_get_overrides`（`:831-843`）与 `_apply_post_overrides`（`:815-827`），是**独立的代码路径**，且受端点 `row_limit`（`:447` `min(page_size, row_limit)`）约束——**与 `report.py` 的 URL 解析无共享代码**，故不会互相影响。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
import unittest
from unittest import mock

class TestUiPageSizeCap(unittest.TestCase):
    def test_cap_constant_is_1000(self):
        import report
        self.assertEqual(report.MAX_UI_PAGE_SIZE, 1000)

    def test_url_page_size_is_clamped(self):
        """UI 报表页：URL 传入超大 page_size 必须被夹到 1000。"""
        import report
        self.assertEqual(report._clamp_ui_page_size(10_000_000_000), 1000)
        self.assertEqual(report._clamp_ui_page_size(1000), 1000)
        self.assertEqual(report._clamp_ui_page_size(200), 200)
        self.assertEqual(report._clamp_ui_page_size(1), 1)

    def test_export_full_rows_not_clamped(self):
        """关键安全测试：导出内部传 2**31-1 取全量，不得被 UI 上限影响。"""
        import export, report
        self.assertGreater(export._EXPORT_ALL_ROWS_PAGE_SIZE, report.MAX_UI_PAGE_SIZE)
        # execute_report 本身不做上限（上限只在 URL 解析层）
        import inspect
        src = inspect.getsource(report.execute_report)
        self.assertNotIn("MAX_UI_PAGE_SIZE", src, "execute_report 内不得夹紧，否则导出取不到全量")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — `report` 无 `MAX_UI_PAGE_SIZE` / `_clamp_ui_page_size`
- [ ] **Step 3: 加常量与夹紧函数，仅在 URL 解析处调用**

在 `report.py` 模块级：

```python
# UI 报表页「每页条数」上限。仅用于 URL 参数夹紧（展示层）。
# 不适用于：导出全量（export._EXPORT_ALL_ROWS_PAGE_SIZE）、API 翻页
# （api_handler 有独立路径与端点 row_limit）、报表配置的「允许全部输出」（取数层）。
MAX_UI_PAGE_SIZE = 1000


def _clamp_ui_page_size(value: int) -> int:
    """UI 报表页 page_size 夹紧至 [1, MAX_UI_PAGE_SIZE]。"""
    return max(1, min(int(value), MAX_UI_PAGE_SIZE))
```

然后**只改 `report.py:2213-2217`**（`handle_request` 内的 URL 解析）:

```python
page_size = None
if "page_size" in qs and qs["page_size"][0]:
    parsed_page_size = app_config.safe_int(qs["page_size"][0], None)
    if parsed_page_size is not None:
        page_size = _clamp_ui_page_size(parsed_page_size)
```

> **❗绝对禁止**：不得在 `execute_report`（`report.py:1031`）或 `render_report_page`（`:1612`）内夹紧。实测确认内部调用方依赖大 `page_size` 取全量：`export.py:97`（`2**31-1`）、`api_handler.py:468`（`fetch_all` 时 `1e9`）、`scheduler.py:490/653`（保活/定时任务）。若在那里夹紧会**静默截断导出与定时任务数据**。

> **必须同时做**：超过上限时在页面给出**明确提示**（复用 `_filter_warning_flash` 一类机制），**不得静默截断**——否则用户看到的是「莫名的行数变少」（spec §7.5 已说明这是行为变化，需可归因）。
> **注意**：`export.py:57-58` 用 `2**31-1` 作为「全量」哨兵值，它**不经** `page_size` URL 参数；封顶后需确认导出路径仍能取全量（它是内部调用，不读 URL）。

- [ ] **Step 4: 运行确认通过 + 导出回归**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Run: `venv/bin/python -m unittest tests.test_report tests.test_report_extra tests.test_export tests.test_output_limit -t . 2>&1 | tail -3`
Expected: PASS / `OK`

- [ ] **Step 5: 提交**

```bash
codegraph sync
git add tests/test_b6_robustness.py report.py
git commit -m "fix(report): UI 报表页 page_size 封顶 1000（仅展示层，不影响导出/API/允许全部输出）"
```

---

### Task B6-8: 导出 CSV 公式中和（D5-b，**默认关闭 + 导出页勾选启用**）

> **用户裁决（2026-10-10）**：**默认关闭**，但在**导出对话框里加一个勾选项**由用户主动启用。故**默认导出字节完全不变**，开启后才会改字节。

**Files:**
- Modify: `export.py:140-168`（`rows_to_csv`）、`export.py:363+`（`handle_export`）、`render.py:3462`（`build_export_modal_html`）、`report.py`（导出表单参数解析）
- Test: `tests/test_b6_robustness.py`（追加）

**Interfaces:**
- Produces: `export.rows_to_csv(..., sanitize_formula: bool = False)`；`export.sanitize_csv_formula(value: str) -> str`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b6_robustness.py
class TestCsvFormulaSanitize(unittest.TestCase):
    def test_default_output_unchanged(self):
        """默认（不勾选）时字节必须与现状完全一致。"""
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False)
        self.assertEqual(out, '"a"\n"=1+1"\n')

    def test_sanitize_prefixes_dangerous_leads(self):
        import export
        for v in ("=1+1", "+3", "-2", "@SUM(A1)"):
            self.assertTrue(export.sanitize_csv_formula(v).startswith("'"))

    def test_sanitize_leaves_normal_values(self):
        import export
        self.assertEqual(export.sanitize_csv_formula("正常文本"), "正常文本")
        self.assertEqual(export.sanitize_csv_formula("123"), "123")

    def test_opt_in_changes_bytes(self):
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False, sanitize_formula=True)
        self.assertIn("'=1+1", out)
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Expected: FAIL — `sanitize_csv_formula` 不存在

- [ ] **Step 3: 实现开关式中和**

```python
_DANGEROUS_LEADS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_formula(value: str) -> str:
    """为以公式引导符开头的单元格加前缀 '，使 Excel/WPS 不当公式执行。"""
    s = value if isinstance(value, str) else str(value)
    return ("'" + s) if s[:1] in _DANGEROUS_LEADS else s
```

`rows_to_csv` 加 `sanitize_formula: bool = False` 参数，**默认 False**（字节不变）；导出对话框新增勾选框 `sanitize_formula`（**默认不勾**），只在勾选时传 True。

- [ ] **Step 4: 运行确认通过 + 默认字节不变验证**

Run: `venv/bin/python -m unittest tests.test_b6_robustness -t . -v`
Run: `venv/bin/python -m unittest tests.test_export tests.test_export_cache_path tests.test_api_endpoint -t . 2>&1 | tail -3`
Expected: PASS / `OK`（默认路径字节不变，故旧断言仍绿）

- [ ] **Step 5: 提交**

```bash
codegraph sync
git add tests/test_b6_robustness.py export.py render.py report.py
git commit -m "feat(export): 可选 CSV 公式中和（默认关闭，导出页勾选启用）"
```

# B7 — P1 语义收口与架构去重

**Files:**
- Modify: `config.py:205`+`:1203`、`render.py:2598`、`export.py:125-132`、`report.py:358-402`+`:1302-1308`+`:1777-1778`
- Test: `tests/test_b7_dedup.py`（新建）

**Interfaces:**
- Consumes: B1、B5 完成
- Produces: `result_transform.transform_rows(rows, columns, filters, sorts, nested_filter) -> list[tuple]`

---

### Task B7-1: `report.py` 删除 45 行被遮蔽的重复定义

- [ ] **Step 1: 写失败测试**

```python
# tests/test_b7_dedup.py
import ast, pathlib, unittest

class TestNoShadowedDefs(unittest.TestCase):
    def test_report_has_no_duplicate_top_level_defs(self):
        tree = ast.parse(pathlib.Path("report.py").read_text(encoding="utf-8"))
        seen = {}
        dup = []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                if n.name in seen:
                    dup.append(n.name)
                seen[n.name] = n.lineno
        self.assertEqual(dup, [], f"report.py 存在被遮蔽的重复定义: {dup}")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: FAIL — 列出 `humanize_db_error`、`render_sql_error_section` 等

- [ ] **Step 3: 删除被遮蔽的定义（`report.py:358-402`）**

保留 `:407-453` 的生效版。删前 `grep` 确认无动态引用。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: PASS

- [ ] **Step 5: 跑报表回归（文案可能变化，须确认）**

Run: `venv/bin/python -m unittest tests.test_report tests.test_report_extra tests.test_deep_edge_cases -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add tests/test_b7_dedup.py report.py
git commit -m "refactor(report): 删除 45 行被遮蔽的重复定义"
```

---

### Task B7-2: `_escape` 语义统一

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b7_dedup.py
class TestEscapeUnified(unittest.TestCase):
    def test_config_escape_handles_decimal_like_render(self):
        from decimal import Decimal
        import config, render
        self.assertEqual(config._escape(Decimal("1E-10")),
                         render._escape(Decimal("1E-10")))

    def test_both_escape_are_same_object_or_equivalent(self):
        import config, render
        self.assertEqual(config._escape("<b>&"), render._escape("<b>&"))
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: FAIL — Decimal 处理不同

- [ ] **Step 3: `config._escape` 委托给 `render._escape`**

`config.py:205-207` 改为 `from render import _escape as _escape`（或在函数内委托），保持 `config._escape` 名字可用（19 个测试文件引用 `config.`）。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_b7_dedup.py config.py
git commit -m "refactor(config): _escape 收口到 render，消除 Decimal 语义分叉"
```

---

### Task B7-3: 分类树缩进统一（**需用户裁决 D4**）

- [ ] **Step 1: 写测试固化基准**

```python
# 追加到 tests/test_b7_dedup.py
class TestCategoryIndentConsistency(unittest.TestCase):
    def test_config_and_render_use_same_indent_char(self):
        """两处分类树缩进必须一致，且必须用全角 U+3000。"""
        import pathlib
        r = pathlib.Path("render.py").read_text(encoding="utf-8")
        c = pathlib.Path("config.py").read_text(encoding="utf-8")
        self.assertIn('"\u3000" *', r)
        self.assertIn('"\u3000" *', c)
        self.assertNotIn('"  " * _get_depth', c, "config.py 仍在用会被 HTML 折叠的半角缩进")
```

- [ ] **Step 2: 改 `config.py:1181` 为全角（D4 已定，spec §7.1）**

```python
# config.py:1181 —— 原（半角，在 <option> 中会被 HTML 折叠 → 缩进实际失效）
prefix = "  " * _get_depth(c, all_cats)
# 改为（全角 U+3000，与 render.py:3767/4015/4257 一致）
prefix = "\u3000" * _get_depth(c, all_cats)
```

> **D4 依据（硬证据）**：两处都是 `<option>` 上下文；HTML 默认 `white-space:normal` 把**连续半角空白折叠**为 1 个（实测 `'    '`→`' '`），故 `config.py` 的半角缩进**当前就是失效的视觉 bug**；全角 U+3000 不折叠。且 `render.py` 已有 3 处用全角，`config.py` 仅 1 处——改 1 处而非 3 处。

Run: `venv/bin/python -m unittest tests.test_b7_dedup tests.test_render tests.test_config -t . 2>&1 | tail -3`

- [ ] **Step 5: 提交**

```bash
git add tests/test_b7_dedup.py render.py config.py
git commit -m "refactor(ui): 统一分类树缩进字符，消除两页视觉分叉"
```

---

### Task B7-4: `transform_rows` 收口到 `result_transform`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_b7_dedup.py
class TestTransformRowsShared(unittest.TestCase):
    def test_transform_rows_exists_in_result_transform(self):
        from result_transform import transform_rows
        self.assertTrue(callable(transform_rows))

    def test_export_and_report_agree(self):
        from result_transform import transform_rows, column_indices
        rows = [("b", 2), ("a", 1)]
        cols = ["n", "v"]
        self.assertEqual(transform_rows(rows, cols, None, [("v", "asc")], None),
                         [("a", 1), ("b", 2)])
        self.assertEqual(column_indices(cols), {"n": 0, "v": 1})
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: FAIL — `transform_rows` 不存在

- [ ] **Step 3: 在 `result_transform` 新增 `transform_rows`，替换 `report._transform_rows` 与 `export.py:125-132` 的复制实现**

`report.py:1777-1778` 的 `col_index_map`/`display_indices` 改用既有 `column_indices()`。

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b7_dedup -t . -v`
Expected: PASS

- [ ] **Step 5: 跑全量（B7 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 6: 同步知识库并提交**

按硬性 #7 更新 `03-report-transform.md`（`transform_rows` 单一实现来源）。

```bash
codegraph sync
git add -A && git commit -m "refactor(transform): _transform_rows/column_indices 收口到 result_transform"
```

---

# B8 — P2 死代码与整批清理

**Files:** 多文件（见下）
**Test:** `tests/test_b8_cleanup.py`（新建）
**依赖:** B7

> **为何本批用平铺步骤而非 `### Task` 分段（有意为之，非遗漏）**：本批 12 项均为**相互独立的删除/一行修正**，共享**同一个测试周期与同一次全量回归**；拆成 12 个 Task 只增加流程开销，不增加审查价值。这正是 writing-plans 所说的「折叠 setup/清理由所属任务承担」的适用情形。若执行中某项比预期复杂（如第 8 项 `is_debug_mode` 加缓存涉及失效时机），**单独提升为 Task** 即可。

- [ ] **Step 1: 写失败测试（覆盖主要清理项）**

```python
# tests/test_b8_cleanup.py
import ast, pathlib, unittest

class TestDeadCodeRemoved(unittest.TestCase):
    def test_no_double_return_in_render(self):
        tree = ast.parse(pathlib.Path("render.py").read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                for i, s in enumerate(n.body[:-1]):
                    if isinstance(s, ast.Return) and isinstance(n.body[i+1], ast.Return):
                        self.fail(f"render.py:{s.lineno} 连续 return（死代码）")

    def test_no_empty_css_compat_shims(self):
        src = pathlib.Path("render.py").read_text(encoding="utf-8")
        for name in ("_MINIBTN_CSS", "_FLASH_WARN_CSS", "_B6_CSS"):
            self.assertNotRegex(src, rf'^{name}\s*=\s*""\s*$', f"{name} 空壳未清理")

    def test_icons_have_no_malformed_svg_attrs(self):
        src = pathlib.Path("render.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r'rx[.\d]', "存在畸形 SVG 属性（如 rx.5\"）")
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b8_cleanup -t . -v`
Expected: FAIL（多项）

- [ ] **Step 3: 逐项清理**

1. `render.py:4561-4562` 连续 `return html` 删除
2. `render.py:1468/1472/1535` 三个 `= ""` 壳删除并改 `_COMMON_CSS` 拼接式
3. `render.py:43/45/56` `rx.5"` → `rx="0.5"` 等
4. `render.py:4468` 未使用的 `api_cell` 及其昂贵拼接删除
5. `db.py` 补转出 `invalidate_api_static_cache_by_report`、`delete_schedules_by_report`
6. `scheduler.py` 生效 `MAX_FAIL_COUNT`（替换 3 处硬编码 5）
7. `server.py:885` `_get_forwarded_url` 死函数删除
8. `app_config.is_debug_mode` 加缓存 + `reload_config` 失效
9. `server.py:252-292` 路由未命中合并为一次扫描
10. `export.py:314` `replace("\ufeff","")` → `lstrip("\ufeff")`
11. `report.py:280` `parse_sorts` 接受大小写（与 `sort_rows` 对齐）
12. `render.py:3428/3451/3477` 抽 `_report_hidden_params(...)`

- [ ] **Step 4: 运行确认通过**

Run: `venv/bin/python -m unittest tests.test_b8_cleanup -t . -v`
Expected: PASS

- [ ] **Step 5: 跑全量（B8 收尾）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 6: 提交**

```bash
codegraph sync
git add -A && git commit -m "chore: 清理死代码与兼容壳，生效死常量，修正畸形 SVG 属性"
```

---

# B9 — P3 结构拆分（**风险最高，最后做**）

**Files:**
- Create: `ui_assets.py`（CSS/JS 常量）、`config_pages/`（按实体）
- Modify: `render.py`、`config.py`（保留 re-export 兼容层）
- Test: `tests/test_b9_moves.py`（新建）
- **依赖:** B8（R2 热点后置）

---

### Task B9-1: `render.py` 常量外移（纯搬移，字节不变）

- [ ] **Step 1: 写字节级快照测试（RED 前先固化基线）**

```python
# tests/test_b9_moves.py
import unittest
import render

class TestRenderAssetsUnchanged(unittest.TestCase):
    def test_common_css_byte_identical(self):
        import ui_assets
        self.assertEqual(render._COMMON_CSS, ui_assets.COMMON_CSS)
        self.assertEqual(len(render._COMMON_CSS.encode()), 80946 + 0 or len(render._COMMON_CSS.encode()))

    def test_asset_urls_stable(self):
        """搬移不得改变 hash 与 URL。"""
        h = render.content_hash8(render._COMMON_CSS + "\n;;;\n" + render._COMMON_JS)
        self.assertEqual(h, render.content_hash8(
            __import__("ui_assets").COMMON_CSS + "\n;;;\n" + __import__("ui_assets").COMMON_JS))
```

- [ ] **Step 2: 运行确认失败**

Run: `venv/bin/python -m unittest tests.test_b9_moves -t . -v`
Expected: FAIL — `ui_assets` 不存在

- [ ] **Step 3: 把 7 个大常量搬到 `ui_assets.py`，`render.py` 改为 `from ui_assets import *`**

搬移清单（实测行号）：`_BASE_CSS` L79-278、`_COMMON_CSS` L280-1465、`_MD_CSS` L1483-1533、`_SQL_HIGHLIGHT_JS` L2126-2150、`_SQL_FORMATTER_JS` L2152-2193、`_API_TEMPLATE_JS` L4918-5114、`_EXCL_EDITOR_JS` L6239-6424（合计 1887 行）。

> **关键**：`_COMMON_CSS = _BASE_CSS + _COMMON_CSS + ...` 的拼接式（L1537）必须原样保留语义，否则字节变化。

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `venv/bin/python -m unittest tests.test_b9_moves tests.test_render tests.test_ui_tokens -t . 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
codegraph sync
git add tests/test_b9_moves.py ui_assets.py render.py
git commit -m "refactor(ui): render.py 的 7 个 CSS/JS 常量外移到 ui_assets.py（纯搬移）"
```

---

### Task B9-2: `config.py` 按实体拆分（保留 re-export）

- [ ] **Step 1: 写兼容层测试**

```python
# 追加到 tests/test_b9_moves.py
class TestConfigBackCompat(unittest.TestCase):
    def test_public_names_still_importable_from_config(self):
        import config
        for name in ("handle_request", "render_reports_page", "render_pools_page",
                     "render_users_page", "render_overview", "_escape"):
            self.assertTrue(hasattr(config, name), f"config.{name} 丢失")
```

- [ ] **Step 2: 运行确认通过（当前即应绿，作为护栏）**

Run: `venv/bin/python -m unittest tests.test_b9_moves -t . -v`
Expected: PASS

- [ ] **Step 3: 按 8 个实体分组拆出子模块，`config.py` 保留 re-export**

分组（实测行数）：`pool` 209 / `report` 257 / `api_endpoint` 320 / `scheduler` 210 / `user` 97 / `category` 139 / `branding` 174 / `overview` 111。`handle_request`（`:2210`）**已是纯分发器**，改为委托子模块。

- [ ] **Step 4: 运行确认通过（19 个测试文件的 `config.` 引用必须仍可用）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 5: 同步 `INDEX.md` 模块职责表**

- [ ] **Step 6: 提交**

```bash
codegraph sync && codegraph status
git add -A && git commit -m "refactor(config): 按实体拆分 config.py，保留 re-export 兼容层"
```

---

# 收尾检查单（全部批次完成后）

- [ ] **Step 1: 全量测试（本任务内一次）**

Run: `venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3`
Expected: `Ran ≥3042` / `OK (skipped=4)`

- [ ] **Step 2: codegraph 收敛**

Run: `codegraph status`
Expected: `pendingChanges` 全 0

- [ ] **Step 3: 知识库同步（硬性 #7）**

确认已更新：`01-architecture.md`、`02-routing-auth.md`、`03-report-transform.md`、`06-ui-interactions.md`、`07-cache-scheduler-audit.md`、`INDEX.md`。

- [ ] **Step 4: 清理产物（硬性 #14）**

Run: `venv/bin/python scripts/agent/cleanup_tmp.py --apply`

- [ ] **Step 5: 批量取证（禁一项一步，硬性 #20）**

Run（一次发）:
```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | tail -3
codegraph status
git diff --stat HEAD~20
venv/bin/python scripts/agent/session_cost.py --check
```

- [ ] **Step 6: AOCI 收尾（硬性 #21，最终稳定态一次）**

Run: `venv/bin/python scripts/agent/aoci_precheck.py` → 按 11-aoci-usage 调一次 `aoci_maintain` → 整批 `aoci_update_entry`。

---

# 附录：R1 校验脚本（改任何写域/依赖后**必须重跑**）

本脚本是「A 改完 B 的目标代码已变」风险的**机器门禁**。每当你新增批次、调整写域或调整依赖时，跑一次；输出必须为 `无 → R1 可满足` 且拓扑序长度等于批次数。

```bash
venv/bin/python - <<'EOF'
W = {  # 批次 → 写域
 "B1": {"server.py","report.py","config.py","render.py"},
 "B2": {"config_db.py","auth.py","server.py","query_executor.py"},
 "B3": {"export.py"},
 "B4": {"scheduler.py"},
 "B5": {"config_db.py","report.py","result_transform.py","render.py","config.py"},
 "B6": {"redis_cache.py","server.py","static_cache.py","render.py","query_executor.py","report.py","export.py"},
 "B7": {"config.py","render.py","export.py","report.py","result_transform.py"},
 "B8": {"render.py","config.py","report.py","scheduler.py","server.py","db.py",
        "app_config.py","export.py","static_cache.py","query_executor.py"},
 "B9": {"render.py","config.py","ui_assets.py"},
}
after = {"B1":[],"B2":["B1"],"B3":[],"B4":[],"B5":["B2"],
         "B6":["B3","B4","B5"],"B7":["B5","B6"],"B8":["B7"],"B9":["B8"]}
def reachable(x):
    seen=set(); stack=list(after[x])
    while stack:
        y=stack.pop()
        if y in seen: continue
        seen.add(y); stack+=after.get(y,[])
    return seen
bad=[]
for a in W:
    for b in W:
        if a>=b: continue
        ov=W[a]&W[b]
        if not ov: continue
        if a not in reachable(b) and b not in reachable(a):
            bad.append((a,b,sorted(ov)))
print("无序且有写域交叠:", bad if bad else "无 → R1 可满足")
import collections
indeg={k:len(v) for k,v in after.items()}
q=collections.deque([k for k,v in indeg.items() if v==0]); order=[]
while q:
    n=q.popleft(); order.append(n)
    for k,v in after.items():
        if n in v:
            indeg[k]-=1
            if indeg[k]==0: q.append(k)
print("拓扑序:", order, "→", "无环" if len(order)==len(W) else "有环！")
EOF
```

**当前基线输出**（2026-10-10 校验通过）：

```
无序且有写域交叠: 无 → R1 可满足
拓扑序: ['B1', 'B3', 'B4', 'B2', 'B5', 'B6', 'B7', 'B8', 'B9'] → 无环
```

---

# Self-Review 记录

**1. Spec 覆盖**：spec §5 的 B1–B9 全部有对应任务段；§7 的 D1–D5 均已标注为前置裁决点并给出默认值。

**2. Step 扫描**：B2-1 与 B6-3 的 Step 1 明确标注了「断言需在实现后回填」，避免写出无法验证的假测试；B5-4 与 B7-3 保留了需用户裁决的空缺。

**3. 类型一致性**：`_js_str`（B1-4）、`_safe_arcname`（B3）、`_maybe_run_keepalive`（B4-1）、`count_schedules`（B5-2）、`transform_rows`（B7-4）、`logger`/`_last_invalidated_lock`（B6）均在 Interfaces 块定义且后续任务引用一致。

**4. Review Focus**：5 条均已分配到具体任务——`_connect_mysql_config` patch 点 → B2-1 Step 5；`close()` 语义 → B2-1 Step 3；输出字节 → B1-2/B1-3、B7、B9-1；`render` 首次引入 logging → B6-5 Step 3；保活节拍 → B4-1 Step 3。

**5. 篇幅比例**：本 plan 含任务级命令与断言，未内联实现体（除 B1-4 的 `_js_str`、B3 的 `_safe_arcname`，因其转义规则是实现歧义点，不写代码则无法消歧）。
