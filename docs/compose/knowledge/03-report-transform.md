# 报表页 · 结果变换 · 导出 · 护栏

## 报表执行核心：`report.execute_report`（report.py:949）

输入：`report_id, sql, pool, page, page_size, sorts, filters, refresh, active_index, cache, force_rebuild, read_timeout, nested_filter`

输出：`ReportResult`（多结果集 `results=[{columns,rows,total}]` + `active_index/page/page_size/cache_info/truncated`）

流程要点：

1. **写护栏在读缓存之前**（约 :997）：`allow_write` 缺省按 0（新建表单）/ 存量缺字段按 1 历史契约；`report is None` 裸调用**不拦**；护栏通过后**含写 SQL 仍令 `skip_cache_read`**（2026-09-25）——热快照不得短路写执行，每次真实跑库，缓存回填照常
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
/export?id=N[&format=json][&charset=utf8|gbk][&zip=1]
        [&smart_quotes=1,2,4][&json_no_quotes=1]
        [&f_*/op_*/sort/nested_filter/cols/result=...]
```

| 项 | 行为 |
|----|------|
| 默认格式 | CSV |
| 默认字符集 | **gbk**（非 utf8）；GBK 剥 BOM |
| 变换顺序 | 查询 → 选结果集 → **先 max_rows 截断** → 筛选 → 排序 → 列 |
| 写护栏 | 403 `WRITE_DENIED_MESSAGE`（独立连接，不经 execute_report） |
| 截断载体 | 头 `X-Export-Truncated`；CSV 尾注释；JSON `_meta.truncated`（报表名恰为 `_meta` 时跳过 JSON 标记） |
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

## 易踩坑

1. **禁止**在 export/api 重写匹配语义
2. `humanize_db_error` / `render_sql_error_section` 在 report.py **定义两次**，后者覆盖前者
3. 截断在筛选**之前**——筛后 N 行 ≠ 导出 N 行
4. 改筛选语法三件套：`parse_filter_expr` + `filter_help` + `test_filter_help`
5. 三端写护栏同文案同条件

---
最后核对：explore-1/3 报告 + 源码交叉
