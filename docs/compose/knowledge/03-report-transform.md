# 报表页 · 结果变换 · 导出 · 护栏

> 函数签名、行号、调用链一律以源码与 `codegraph` 为准（硬性 #18）；本卷只留**三端共用语义、判定规则与约定**。

## 报表执行核心 `report.execute_report`

输入 `report_id/sql/pool/page/page_size/sorts/filters/refresh/active_index/cache/force_rebuild/read_timeout/nested_filter`，输出 `ReportResult`（多结果集 `results=[{columns,rows,total}]` + `active_index/page/page_size/cache_info/truncated`）；签名见 `report.py`。

`cache_info.source` 表示**本次取数来源**（`mysql` / `process` / `redis` / `redis_fallback`），不是「是否写了缓存」的账本；`snapshot_written`（仅 `mysql` 分支）标记本次是否同时写了 L2 快照。

流程要点：

1. **写护栏在读缓存之前**：`allow_write` 缺省按 0（新建表单）/ 存量缺字段按历史契约当 1；`report is None` 裸调用**不拦**；护栏通过后**含持久写 SQL 仍令 `skip_cache_read`**——热快照不得短路写执行，每次真实跑库，缓存回填照常。
2. **写判定分两个函数**：`sql_contains_write`（从严，服务权限与警示）与 `sql_has_persistent_write`（精确，只服务缓存门槛与静态护栏）。会话级语句（`CREATE`/`DROP TEMPORARY TABLE`、`SET @用户变量`）与 CTE 里的 `REPLACE()`/`INSERT()` 字符串函数调用**不再**跳过缓存读。
3. **读白名单不豁免写文件**：`SELECT … INTO OUTFILE` / `INTO DUMPFILE` 写的是 **MySQL 服务端磁盘**，首关键词虽是 SELECT 也必须判写；判定挂在**相邻关键词对** `(INTO, OUTFILE|DUMPFILE)` 上并插在读白名单分支**之前**（关键词集合用 `codegraph node sql_contains_write` 核对）。
4. 优先 Redis 快照（`prefer_cache`）→ 否则查 MySQL → 写回快照（分布式锁）；预览 SQL 与配置不一致**不写 Redis**。
5. L1 `QueryCache` 进程缓存全量行。**全量输出护栏**：`allow_all_output=0` 且 `max_rows>0` → 截断并置 `truncated`；`_cache_matches_limit_policy` 拒绝「已截断但当前要全量」的旧缓存。
6. 内存顺序：`filter_rows` → `filter_rows_nested` → `sort_rows` → `select_columns` → 分页。

Web 路径 `read_timeout=30`；调度器/API 默认不设（防长查询被截）。`force_rebuild=True` 仅调度保活「先算后换」，用户路径勿传。

### URL 参数

```text
GET /report[?id=&page=&page_size=&sort=&dir=&f_=&op_=&cols=&result=&nested_filter=&flash=]
（`page_size` **仅 UI 分页**，上限 `MAX_UI_PAGE_SIZE=1000`，必须在 handle_request 与 refresh_cache **两个入口**都夹紧；**不适用** API 翻页与导出全量 —— B6-7）
POST /report  action=refresh_cache
POST /report/preview   sql_query / id / pool_id / allow_write（hidden+checkbox 取最后值）
```

嵌套示例（须 URL 编码）：`{"op":"and","conditions":[{"col":"姓名","op":"contains","value":"张"}]}`

三端错误差异：nested 非法 → 页面 flash 后继续；导出 400；API 400 结构化。

## 筛选语法（全系统统一）

实现 `result_transform.parse_filter_expr`，文案 `filter_help.py`（报表页 + 审计页 + 条件构建器），两者必须对齐（`tests/test_filter_help.py` 钉死）。

- 操作符：`contains/notcontains`（**不敏感**）、`eq/neq`（**敏感**、fullmatch、通配仍可用）、`gt/lt/gte/lte`（数值或 ISO 日期，不可比**静默跳过**）、`isempty/notempty`。
- 值表达式：`*` → `.*`；英文逗号 **OR**（有裸逗号才 strip+丢空段，**无逗号不 strip**）；`\*` `\,` `\\` 转义（逗号前连续 `\` 奇数=字面逗号）。
- 多列之间 **AND**；未知列/操作符静默跳过；空多值（`" , "`）→ 条件忽略。
- `invalid_numeric_filters` → 仅报表页 flash。
- 嵌套：`filter_rows_nested` + `validate_nested_filter`；`resolve_expression` 支持 `now()/today()/yesterday()/tomorrow()/date_add/date_sub`（`now()` 实际返回**今天日期**串）。

## 导出（`export.handle_export`）

```text
/export?id=N[&format=json][&charset=utf8|gbk][&zip=1]
        [&smart_quotes=1,2,4][&json_no_quotes=1]
        [&f_*/op_*/sort/nested_filter/cols/result=...]
```

| 项 | 行为 |
|----|------|
| 默认 | CSV + **gbk** 字符集；GBK 剥 BOM（仅 CSV）。**JSON 恒 UTF-8**（RFC 8259，与 `/api/*` 一致）：解析后强制 `charset="utf8"`，ZIP 内 `.json` 同样是 UTF-8，面板选别的字符集会被忽略 |
| 变换顺序 | 查询 → 选结果集 → **先 max_rows 截断** → 筛选 → 排序 → 列 |
| **数据来源** | 走 `report.execute_report`（**复用 L1 进程缓存 / L2 Redis 快照**）；`report_id=None` 时保留旧的直连分支 |
| 写护栏 | 403 `WRITE_DENIED_MESSAGE`（在调用 `execute_report` **之前**判定，不依赖其 `PermissionError`） |
| 截断载体 | 头 `X-Export-Truncated`；CSV 尾注释；JSON `_meta.truncated`（报表名恰为 `_meta` 时跳过 JSON 标记），取自 `ReportResult.truncated` |
| ZIP | tempfile → ZIP_DEFLATED → 读回；内 `{报表名}.csv\|json` |
| ZIP 落盘安全 | **磁盘落点名必须与报表名解耦**（用常量 `payload<ext>` / `payload.zip`），`arcname` 才传原名——报表名用户可控，直接当落点名会让 `/export?zip=1` 写到 tmpdir 之外（CWE-22，2026-10-10 B3 修）。门禁 `tests/test_b3_export_zip_safety.py` |
| smart_quotes | 1 十进制、2 科学计数法、4 千分位；`json_no_quotes=1` ≡ 全开 |

- 导出 CSV：**QUOTE_ALL + BOM + `\n`**；API CSV：**QUOTE_MINIMAL + CRLF + 仅 pretty BOM**（勿混用）。
- 共用序列化：`export.rows_to_csv`（导出 / API / 审计）。

## 写操作护栏（PH-05）

```text
report.allow_write 与 sql_contains_write(sql)
  → execute_report: PermissionError（缓存读之前）
  → export: 403
  → api: PermissionError → 403 WRITE_DENIED
  → 静态 .json 生成/hit 再拦一次（并集：权限判定 + 持久写判定，不是替换）
  → 允许时页面 WRITE_ALLOWED_BANNER
文案: report.WRITE_DENIED_MESSAGE / WRITE_ALLOWED_BANNER
```

`sql_contains_write`：首词 SELECT/SHOW/DESC/EXPLAIN=读（**例外 `INTO OUTFILE`/`INTO DUMPFILE` 判写**）；WITH 扫写集；其余（含 `SET`、未知首词）从严当写。

## 多结果集

`active_index` / `result` 切换 tab；`result_mode=all` 在 API 下为 JSON 数组，**CSV 不支持 → 400**。

## 预设 / 模板 / Markdown

- `preset_cases`：DEBUG 导入夹具；upsert 不删多余行。
- `json_template`：`{{data}}` 单结果 / `{{results}}` 全结果键集不同；校验须传 `keys`。
- `markdown_render.render_markdown`：消毒 HTML 单一来源；mermaid 预提取；memo/描述共用。报表页 mermaid 须「页卡可见」时才渲染（隐藏容器里渲染会退化成空图并打 `data-processed`），失败模式见 `06-ui-interactions.md`。

## 调度排除 ≠ 嵌套筛选

`scheduler.exclusions`：`op` 大写 `AND/OR` + `children`；评估失败按**不排除**执行。与 `nested_filter`（`and/or` + `conditions`）结构不同，勿混用。

## transform 实现要点（有测试锁定）

- `_parse_numeric_or_date` 快速路径**必须含 `Decimal`**（MySQL `DECIMAL` 列返回 `decimal.Decimal`），并保留 `isfinite` 检查；`bool` 单独先判掉。
- `_try_float` 走 `int`/`float` 快速路径；**`bool` 不特判**（既有 `float(True)==1.0`）。
- `sort_rows` / `_ordered_by_column`：每个排序键**一趟**完成 None/数值/文本三分区；稳定排序与「从低优先级到高优先级」调用约定不变。
- `filter_rows`：**保持链式多趟，不要单趟化**（实测单趟化更慢）。
- **多值筛选必须合并为单条 alternation**（`_compile_alternation`，B5-1）：原「每单元格逐个 `any(rx.search(...))`」的 generator+多次正则开销大；合并后实测单值 2.5×、三值 3.7×（100k 行），结果严格等价。等价前提：`_segment_regex` 只产 `re.escape` 字面量与 `.*`，结构上**不含裸 `|`**。**禁止**改用 `str.lower() in`（Unicode 折叠语义与 `re.IGNORECASE` 有边界差异）。
- 排序分区语义：数值（含数值字符串）恒在文本之前（不随方向翻转）；`None` 恒最后；稳定排序——由 `tests/test_result_transform_perf.py` 钉死。

改这几处时先跑 characterization 测试确认绿，改完必须仍绿；错误模式是**静默换行序**。

## 派生态缓存（C-3，`report.CachedResult.derived`）

- L1/L2 缓存的是**全量未筛选未排序**数据，故每次请求都要重跑 filter+sort；`derived` 缓存「已筛选已排序的全量行」，键为 `(filters, sorts, nested_filter)` 规范化元组 + 结果集下标。
- **挂在 `CachedResult` 上而非独立全局缓存** → 零失效逻辑：L1 每次 `set` 新建对象，旧对象连同派生态一起回收；派生态绝不会比 L1 活得久。
- **分页切片不缓存**，每次现算（`O(page_size)`）；翻页只有 page 变 → 命中率高。
- **仅在 `not skip_cache_read` 时启用**：真持久写报表每轮数据都变、`force_rebuild` 是「先算后换」，复用派生态都会返回旧行序（`skip_cache_read` 由 `sql_has_persistent_write` 决定，会话级脚本与 CTE+函数名报表**恢复**复用）。
- LRU 上限 `_DERIVED_CACHE_MAX` 组合/报表；`derived` 绝不进序列化路径。

## 统一筛选 / 排序 / 输出语义（三处调用方一致，禁止单边修改）

- **值匹配表达式**：`result_transform.parse_filter_expr`（`*` 通配、英文逗号「或」、`\` 转义）；**筛选语法三件套**：改语法必须同改 `parse_filter_expr` + `filter_help` + `test_filter_help`。
- **嵌套筛选**：URL 参数 `nested_filter`（JSON），`validate_nested_filter` 校验。
- **全量输出护栏**：`max_rows` 与截断标记在报表页 / 导出 / API 必须行为一致。
- **审计页关键字**共用同一套匹配语义（`audit_page` / `audit_db`），改语义要全链路对齐测试。
- **分页/排序/筛选 URL 解析**在 `report.py`（`parse_filters` / `parse_sorts` / `parse_nested_filter` / `parse_result_index` / `parse_result_names`）。
- 改任一处前先看本卷「transform 实现要点」与「派生态缓存」两节——这些函数上有测试锁定的优化，不可凭直觉重写。

## 易踩坑

1. **禁止**在 export/api 重写匹配语义。
2. `humanize_db_error` / `render_sql_error_section` 在 `report.py` **定义两次**，后者覆盖前者。
3. 截断在筛选**之前**——筛后 N 行 ≠ 导出 N 行。
4. 三端写护栏同文案同条件；导出必须传 `report_config` 给 `execute_report`，否则**全量输出护栏失效**。
5. 导出改走 `execute_report` 后会读写进程级 L1 缓存——写导出测试必须清 `report._query_cache`，否则读到别的用例的 mock 数据。
