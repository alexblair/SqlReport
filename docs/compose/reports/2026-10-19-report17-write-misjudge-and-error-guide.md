# 报表 17 写操作误判 + 执行失败错误引导（2026-10-19）

> 关联：用户报告（报表 17 实际 SQL 无写操作，取消「允许执行写操作」后仍报「包含写操作语句」）
> 依据：`docs/compose/spec/2026-09-30-write-report-cache-gate-design.md` §3.2/§5.2、`docs/compose/spec/2026-10-19-error-guide-edit-entry-confirm.html`（用户确认稿 v2）

## 一、问题 1：为什么这条纯读 SQL 被判成写操作

### 判定链（改前）

`report.execute_report` 在缓存读之前调用 `sql_contains_write(sql_query)`（`query_executor.py`），
首关键词为 `WITH` 时走单独分支：

```python
if first == "WITH":
    if any(kw in _WRITE_STATEMENT_KEYWORDS for kw in keywords[1:]):
        return True
```

**两个缺陷叠加**：

1. 扫的是**全部关键词**，没有「函数调用」排除；
2. 写集 `_WRITE_STATEMENT_KEYWORDS` 含 `REPLACE`，而 `REPLACE` 同时是 MySQL 字符串函数。

报表 17「处置商管理一览表」的 SQL（6686 字符、单条 WITH 语句）在偏移 4533 处写了
`LENGTH(REPLACE(t.ancestors, ',', ''))` —— 纯字符串函数，被当成 `REPLACE INTO` 语句命中 → `True`。

### 为什么是「新增行为可见、老报表才炸」

`sql_has_persistent_write`（缓存门槛用）早在 2026-09-30 就修好了同款问题（`_WITH_WRITE_VERBS`
+ `_skip_ws_and_comments` 后紧跟 `(` 即函数调用），所以两个函数对报表 17 给出**互相矛盾**的结论：

| 函数 | 改前报表 17 | 用途 |
|------|------------|------|
| `sql_has_persistent_write` | `False`（正确） | 缓存读写门槛 |
| `sql_contains_write` | `True`（误判） | `allow_write` 权限拦截 / 徽标 / 警示条 |

用户在编辑页把「允许执行写操作」取消后，拦截分支 `report.py:1015` 直接抛
`PermissionError(WRITE_DENIED_MESSAGE)`，页面即报「查询执行失败：该报表包含写操作语句…」。

### 全库审计

遍历生产库 `report_configs` 全部报表，只有 **#17 一处**是误判（来源 `REPLACE`）；
#19/#35/#42 两函数结论不一致但属真实会话级写（`CREATE/DROP TEMPORARY`、`SET @变量`），非误判。

### 修法（已落盘）

新增共用助手 `_with_statement_has_write(statement, keywords)`（`query_executor.py`），
两个判定函数都改为调用它，规则与 spec §5.2 完全一致：

- 只认写动词集 `_WITH_WRITE_VERBS`（**不含 `SET`**）；
- 动词后 `_skip_ws_and_comments` 取下一有效字符，**是 `(` 即函数调用，不判写**。

`sql_contains_write` 同时改用 `_iter_sql_keywords_with_pos`（带结束偏移），与
`sql_has_persistent_write` 同一个词法器 —— 消除「两个词法器、两套规则」的漂移源头。

验证：报表 17 生产 SQL → 两函数均 `False`；反向回归 `WITH ... DELETE/UPDATE/INSERT/REPLACE INTO`
仍为 `True`；`SELECT REPLACE(...)/INSERT(...)` 为 `False`。

### 教训

**同一语义有第二个实现时，第二个实现必然漂移。** 判定规则必须收口到一个助手函数；
`tests/test_sql_persistent_write.py` 里那条「旧判定的误报在此固定下来」的断言本身就是错误——
它把 bug 固化成契约，本次已改为 `assertFalse`。

## 二、问题 2：报错只抛错、不给下一位动作

### 改前

`render_sql_error_section(friendly, raw)` 只输出一行
`查询执行失败：…` + 折叠的原始错误，**没有任何编辑入口**（虽然文案里写着「请到编辑页开启」，
但页面就在报表页，用户要去左侧配置菜单自己找）。

### 用户需求（原话）

> 「用户是不懂你的程序的，你需要给他最精准的解决方案，引导他解决问题，而不是仅仅抛出错误。」

并明确要求：**所有执行失败都出现按钮**；文案引导为「当前问题可能是 XXXX 引起的，您可以尝试进入【编辑】报表，
寻找解决方案」；XXXX 部分要建**可不断完善的文案提示字典**，后期做功能开发时同步更新；【编辑】新开窗口。

### 实现（已落盘，用户已确认版式 A2）

1. `report._ERROR_GUIDES`：12 条词条（`write_denied` / `pool_missing` / 1064 / 1146 / 1054 / 1142 /
   1044 / 1045 / 2003 / 2005 / 1205 / 1969 / `unknown`），结构 `{title, cause, fix}`；
   数字键**不自带 message**，主文案运行时取 `_DB_ERRNO_HINTS`，防两处文案漂移。
2. `report.error_guide(friendly, raw, error, guide_key)`：选择优先级
   显式 `guide_key` > `PermissionError`→`write_denied` > 错误码词条 > `unknown`。
3. `report.render_sql_error_section(friendly, raw, report_id=0, error=None, guide_key="")`：
   三段式 `查询执行失败：<发生了什么>` / `可能原因：<…>` / `如何解决：<…>` + 统一收尾句
   （正文【编辑】链接） + 右侧「编辑报表」按钮（`target="_blank" rel="noopener"`） + `<details>` 折叠原始错误。
   `report_id<=0`（预览）不出口，避免假入口。
4. 两个真实出口都接上：主错误出口 `report.py:1614`、连接池缺失 `report.py:1594`。
5. `WRITE_DENIED_MESSAGE` 去掉冗余尾巴 → 「该报表包含写操作语句且未开启『允许执行写操作』」（按钮就在旁边）。
6. 样式入 `ui_assets.COMMON_CSS`（`.flash-title/.flash-hint/.flash-actions/.flash-details` 等 10 条）；
   `--ink-3` 在 danger-soft 上只有 4.39:1 不达标，故正文与 summary 一律用 `--ink-2`（6.11:1）。
7. API / 导出仍是 JSON / 纯文本，只回常量文案，引导只在页面渲染层（不能塞 HTML）。

### 契约保护

`tests/test_error_guide.py`（17 用例）：字典结构、数字键与 `_DB_ERRNO_HINTS` 对齐、
选择优先级、三段式版式、有 id 才出现两个编辑链接、预览无入口、HTML 转义、标签平衡、
以及三条页面级断言（写拦截页、连接池缺失页、有 id 预览 1064 页都带编辑链接）。

## 三、验证证据

- 全量：`venv/bin/python -m unittest discover -s tests/ -t .` → **Ran 3221 tests, OK (skipped=4)**，366s。
- 定向：`tests.test_error_guide` 17/17、`test_write_guard + test_trust_baseline + test_b7_dedup +
  test_b9_moves + test_ui_tokens + test_report + test_report_extra + test_html_structure` → 389 OK。
- 生产库实测：报表 17「处置商管理一览表」`allow_write=0`、SQL 6686 字符 →
  `sql_contains_write=False` / `sql_has_persistent_write=False`。
- 浏览器计算样式（无头 Chrome，`run-logs/eg-*.png`）：写拦截 / 连接池缺失 / 1064 三态都渲染出
  `.flash-actions .btn`（84×24，`display:flex`），预览态 `found:false`（无按钮，符合预期）。
