# 报表页 · 结果变换 · 导出 · 护栏

## 报表执行核心：`report.execute_report`（report.py:949）

输入：`report_id, sql, pool, page, page_size, sorts, filters, refresh, active_index, cache, force_rebuild, read_timeout, nested_filter`

输出：`ReportResult`（多结果集 `results=[{columns,rows,total}]` + `active_index/page/page_size/cache_info/truncated`）

流程要点：

1. **写护栏在读缓存之前**（约 :997）：`allow_write` 缺省按 0（新建表单）/ 存量缺字段按 1 历史契约；`report is None` 裸调用**不拦**；护栏通过后**含持久写 SQL 仍令 `skip_cache_read`**（2026-09-25，2026-09-30 收窄）——热快照不得短路写执行，每次真实跑库，缓存回填照常。
   **判定分两个函数**（2026-09-30，`docs/compose/spec/2026-09-30-write-report-cache-gate-design.md`）：`sql_contains_write`（从严，服务权限与警示）与 `sql_has_persistent_write`（精确，只服务缓存门槛与静态护栏）。会话级语句（`CREATE`/`DROP TEMPORARY TABLE`、`SET @用户变量`）与 CTE 里的 `REPLACE()`/`INSERT()` 字符串函数调用**不再**跳过缓存读。
2. 优先 Redis 快照（`prefer_cache`）→ 否则查 MySQL → 写回快照（分布式锁）；预览 SQL 与配置不一致**不写 Redis**
3. L1 `QueryCache` 进程缓存全量行，键约 `(report_id, sql_query)`
4. 全量输出护栏：`allow_all_output=0` 且 `max_rows>0` → 截断并 `truncated`；`_cache_matches_limit_policy` 拒绝「已截断但当前要全量」的旧缓存
5. 内存：`filter_rows` → `filter_rows_nested` → `sort_rows` → `select_columns` → 分页

Web 路径 `read_timeout=30`；调度器/API 默认不设（防长查询被截）。  
`force_rebuild=True` 仅调度保活「先算后换」，用户路径勿传。

### 关键入口（report.py）

| 函数 | 行 | 作用 |
|------|----|------|
| `handle_request` | :1775 | HTTP 总入口：预览 / refresh_cache / GET → `render_report_page` |
| `parse_filters` | :160 | `f_{col}`+`op_{col}`；旧 `f_col`+`f_q`；`nofilter` 丢弃 |
| `parse_sorts` | :250 | `sort`/`dir` 可重复；同列保留先出现位置、后出现方向 |
| `parse_nested_filter` | :217 | URL JSON → `validate_nested_filter`；失败 `ValueError` |
| `parse_result_index` | :300 | `result=N`；非法回退 0；`-1` 全量哨兵 |
| `render_report_page` | :1383 | 取配置 → `execute_report(read_timeout=30)` → HTML |
| `_handle_refresh_cache` | :1699 | POST 重建后 302，保留 page/sort/cols/result |
| `_filter_warning_flash` | :1756 | 非法数值筛选提示（**仅 Web 页**） |

### URL 参数

```
GET /report[?id=&page=&page_size=&sort=&dir=&f_=&op_=&cols=&result=&nested_filter=&flash=]
POST /report  action=refresh_cache
POST /report/preview   sql_query / id / pool_id / allow_write（hidden+checkbox 取最后值）
```

嵌套示例（须 URL 编码）：  
`{"op":"and","conditions":[{"col":"姓名","op":"contains","value":"张"}]}`

三端错误差异：nested 非法 → 页面 flash 后继续；导出 400；API 400 结构化。

## 筛选语法（全系统统一）

实现：`result_transform.parse_filter_expr`（:57）  
文案：`filter_help.py`（报表页 + 审计页 + 条件构建器）

- 操作符：`contains/notcontains`（**不敏感**）、`eq/neq`（**敏感**、fullmatch、通配仍可用）、`gt/lt/gte/lte`（数值或 ISO 日期，不可比**静默跳过**）、`isempty/notempty`
- 值表达式：`*` → `.*`；英文逗号 **OR**（有裸逗号才 strip+丢空段；**无逗号不 strip**）；`\*` `\,` `\\` 转义（逗号前连续 `\` 奇数=字面逗号）
- 多列之间 **AND**；未知列/操作符静默跳过
- 空多值（`" , "`）→ 条件忽略
- `invalid_numeric_filters` → 仅报表页 flash
- 嵌套：`filter_rows_nested` + `validate_nested_filter`；`resolve_expression`：`now()/today()/yesterday()/tomorrow()/date_add/date_sub`（`now()` 实际返回**今天日期**串）
- `filter_help` 与实现必须对齐（`tests/test_filter_help.py` 钉死）

## 导出（`export.handle_export` :319）

```
/export?id=N[&format=json][&charset=utf8|gbk][&zip=1]（**JSON 固定 UTF-8**：RFC 8259，与 `/api/*` 响应统一；选 JSON 时导出面板的字符集会被置为 UTF-8 并禁用）
        [&smart_quotes=1,2,4][&json_no_quotes=1]
        [&f_*/op_*/sort/nested_filter/cols/result=...]
```

| 项 | 行为 |
|----|------|
| 默认格式 | CSV |
| 默认字符集 | **gbk**（非 utf8）；GBK 剥 BOM（仅 CSV；**JSON 恒 UTF-8**，面板传其它字符集也会被忽略——`export.handle_export` 在解析后强制 `charset="utf8"`，ZIP 内 `.json` 同样是 UTF-8）|
| 变换顺序 | 查询 → 选结果集 → **先 max_rows 截断** → 筛选 → 排序 → 列 |
| **数据来源** | 走 `report.execute_report`（**复用 L1 进程缓存 / L2 Redis 快照**，2026-09-29 C-4 起）。改前自带连接直查 MySQL、完全绕过三层缓存，实测 10 万行导出 1519.7ms → 复用缓存后 359.2ms。`report_id=None` 时保留旧的直连分支 |
| 写护栏 | 403 `WRITE_DENIED_MESSAGE`（在调用 execute_report **之前**判定，不依赖其 `PermissionError`） |
| 截断载体 | 头 `X-Export-Truncated`；CSV 尾注释；JSON `_meta.truncated`（报表名恰为 `_meta` 时跳过 JSON 标记）。截断标记取自 `ReportResult.truncated` |
| ZIP | tempfile → ZIP_DEFLATED → 读回；内 `{报表名}.csv\|json` |
| smart_quotes | 1 十进制、2 科学计数法、4 千分位；`json_no_quotes=1` ≡ 全开 |

导出 CSV：**QUOTE_ALL + BOM + `\n`**；API CSV：**QUOTE_MINIMAL + CRLF + 仅 pretty BOM**（勿混用）。

共用序列化：`export.rows_to_csv`（导出 / API / 审计）。

## 写操作护栏（PH-05）

```text
report.allow_write 与 sql_contains_write(sql)
  → execute_report: PermissionError（缓存读之前）
  → export: 403
  → api: PermissionError → 403 WRITE_DENIED；静态 .json 生成/hit 再拦一次
  → 允许时页面 WRITE_ALLOWED_BANNER
文案: report.WRITE_DENIED_MESSAGE / WRITE_ALLOWED_BANNER（:44-45）
```

`sql_contains_write`（query_executor:408）：首词 SELECT/SHOW/DESC/EXPLAIN=读；WITH 扫写集；其余=写；`SET` 也算写；未知首词从严当写。

## 多结果集

`active_index` / `result` 切换 tab；`result_mode=all` 在 API 下 JSON 数组，**CSV 不支持 → 400**。

## 预设 / 模板 / Markdown

- `preset_cases`：DEBUG 导入夹具；upsert 不删多余行
- `json_template`：`{{data}}` 单结果 / `{{results}}` 全结果键集不同；校验须传 `keys`
- `markdown_render.render_markdown`：消毒 HTML 单一来源；mermaid 预提取；memo/描述共用

## 调度排除 ≠ 嵌套筛选

`scheduler.exclusions`：`op` 大写 `AND/OR` + `children`；评估失败按**不排除**执行。  
与 `nested_filter`（`and/or` + `conditions`）结构不同，勿混用。

## transform 实现的性能要点（2026-09-29 C-1/C-3 实测）

| 位置 | 要点 |
|------|------|
| `_parse_numeric_or_date` | 快速路径 `isinstance(s, (int, float, Decimal))`。**`Decimal` 必须在内**——MySQL `DECIMAL` 列返回 `decimal.Decimal`，漏了会让每个金额单元格走 `str().strip()` + 日期正则 + `float()` 三连。快速路径内**保留 `isfinite` 检查**（`Decimal('Infinity')`/`('NaN')` 仍按不可比较处理，既有语义不得被绕过）。`bool` 在 `isinstance` 之前单独判掉 |
| `_try_float` | `int`/`float` 走快速路径，避免文本列每格构造一次 `ValueError` 再捕获。**`bool` 不特判**（既有 `float(True)==1.0`） |
| `sort_rows` / `_ordered_by_column` | 每个排序键**一趟**遍历完成 None/数值/文本三分区。稳定排序与「从低优先级到高优先级」的调用约定不变 |
| `filter_rows` | **保持链式多趟，不要单趟化**。实测把 M 个条件编译成行判定函数一趟应用，10 万行反而**慢 41%~72%**（每格多一层闭包调用；且 M 个条件链式过滤时中间列表逐级缩小，总访问量本就不高） |
| 排序分区语义 | 数值（含数值字符串）恒在文本之前（不随方向翻转）；`None` 恒最后（不受升降序影响）；稳定排序。**这些由 `tests/test_result_transform_perf.py` 逐行钉死** |

改这几处时：**先跑 characterization 测试确认绿，再改，改完必须仍绿**。
它们的错误模式是静默换行序——不报错，只变用户看到的顺序。

## 派生态缓存（C-3，`report.CachedResult.derived`）

- L1/L2 缓存的是**全量未筛选未排序**数据，故每次请求都要重跑 filter+sort。
  `CachedResult.derived` 缓存「已筛选已排序的全量行列表」，键为
  `(filters, sorts, nested_filter)` 规范化元组 + 结果集下标。
- **挂在 `CachedResult` 上而非独立全局缓存** → 零失效逻辑：L1 每次 `set`
  新建对象，旧对象连同派生态一起回收；L1 TTL 过期/逐出，派生态随之消失。
  派生态绝不会比 L1 活得久，严格保持「进程内看不到别的进程经 scheduler
  刷新 Redis 快照」这一既有语义。
- **分页切片不缓存**，每次现算（`O(page_size)`）。翻页只有 page 变 →
  命中率高，这正是设计针对的访问模式。
- **仅在 `not skip_cache_read` 时启用**：真持久写报表每轮数据都变、force_rebuild
  是「先算后换」，两者复用派生态都会返回旧行序。（`skip_cache_read` 自 2026-09-30 起
  由 `sql_has_persistent_write` 决定：会话级脚本与 CTE+函数名报表**恢复**复用派生态。）
- LRU 上限 `_DERIVED_CACHE_MAX = 8` 组合/报表。`derived` 绝不进序列化路径。
- 10 万行实测（重复同筛选/排序）：排序 76.1→16.1ms，筛选 95.3→15.5ms。
  **首次**访问仍是 O(N)，与基线同量级。

## 统一筛选 / 排序 / 输出语义（三处调用方一致，禁止单边修改）

- **值匹配表达式**：`result_transform.parse_filter_expr`（`*` 通配、英文逗号「或」、`\` 转义）；操作符集合以代码为准，帮助文案在 `filter_help.py`（筛选语法三件套：改语法必须同改 `parse_filter_expr` + `filter_help` + `test_filter_help`）。
- **嵌套筛选**：URL 参数 `nested_filter`（JSON），`validate_nested_filter` 校验。
- **全量输出护栏**：`max_rows`、截断标记在报表页 / 导出 / API 必须行为一致。
- **审计页关键字**共用同一套匹配语义（`audit_page` / `audit_db`），改语义要全链路对齐测试。
- **分页/排序/筛选 URL 解析**在 `report.py`：`parse_filters`（`f_{col}` + `op_{col}`）、`parse_sorts`（`sort` + `dir`）、`parse_nested_filter`、`parse_result_index`、`parse_result_names`。
- **改任一处前先看本卷的「transform 实现的性能要点」与「派生态缓存」两节**——C-1/C-3 已在这些函数上做过有测试锁定的优化，不可凭直觉重写。

## 易踩坑

1. **禁止**在 export/api 重写匹配语义
2. `humanize_db_error` / `render_sql_error_section` 在 report.py **定义两次**，后者覆盖前者
3. 截断在筛选**之前**——筛后 N 行 ≠ 导出 N 行
4. 改筛选语法三件套：`parse_filter_expr` + `filter_help` + `test_filter_help`
5. 三端写护栏同文案同条件
6. 导出改走 `execute_report` 后会**读写进程级 L1 缓存**——写导出相关测试时
   必须清 `report._query_cache`，否则读到别的用例的 mock 数据
7. 导出必须传 `report_config` 给 `execute_report`，否则**全量输出护栏失效**
   （`limit_rows` 依赖 `report` 参数非 None）

---
最后核对：2026-09-29 执行层性能优化（C-1/C-3/C-4）+ 源码交叉
