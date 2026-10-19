# 执行失败错误引导（三段式 + 【编辑】入口）设计

> 状态: 生效
> 取代关系: 无。本设计只扩展**页面渲染层**的报错呈现，不改 `sql_contains_write` / `sql_has_persistent_write` 判定规则（后者的 WITH 函数名修法见 `2026-09-30-write-report-cache-gate-design.md` §5.2，2026-10-19 已同步落到 `sql_contains_write`）。
> 确认稿: `2026-10-19-error-guide-edit-entry-confirm.html`（版式 A2，用户 2026-10-19 确认）

## 1. 触发场景与问题

报表 17《处置商管理一览表》是纯读 `WITH … SELECT`，因 `LENGTH(REPLACE(t.ancestors, ',', ''))`
被 `sql_contains_write` 误判为写（根因与修法见 `../reports/2026-10-19-report17-write-misjudge-and-error-guide.md` §1）。
用户在编辑页取消「允许执行写操作」后执行报表，页面只显示：

```
查询执行失败：该报表包含写操作语句且未开启『允许执行写操作』，请到编辑页开启
查看原始错误信息 ▸
```

两个问题：

1. 判定误报（已在 `query_executor.py` 修复，非本文档范围）。
2. **报错只说「去编辑页」，不给入口**——用户当前就在报表页，必须自己记住 `id=17`，
   再从左侧配置菜单逐层点到该报表。这是「抛错误」而不是「引导」。

## 2. 用户要求（2026-10-19 原话）

> 「所有执行失败都出现按钮，文案上加入引导：『当前问题可能是 XXXX 引起的，您可以尝试进入
> 【编辑】报表，寻找解决方案』，这里的【编辑】点击后，新开窗进入该报表的编辑功能。同时，
> XXXX 引起的，这个部分的文案，你需要对错误的可能方向和修复方式设定一些文案提示字典，
> 不仅仅是本次的错误，这个字典需要不断的完善和在后期你做功能开发时同步更新，你要时刻理解
> 『用户是不懂你的程序的，你需要给他最精准的解决方案，引导他解决问题，而不是仅仅抛出错误。』」

约束：① 覆盖**所有**执行失败，不止写拦截；② 引导文案入**字典**，可持续扩充；
③ 【编辑】新窗口打开；④ 版式经确认稿确认后才实施（硬性 #17），已确认 A2。

## 3. 结构与契约

### 3.1 错误块三段式（`report.render_sql_error_section`）

```html
<div class="flash flash-error">
  <div class="grow">
    <div class="flash-title">查询执行失败：<发生了什么></div>
    <div class="flash-hint"><strong>可能原因</strong>：<什么情况导致的></div>
    <div class="flash-hint"><strong>如何解决</strong>：<具体下一步> + 统一收尾句（含【编辑】链接）</div>
    <details class="flash-details"><summary>查看原始错误信息</summary><pre>原始错误</pre></details>
  </div>
  <div class="flash-actions"><a class="btn btn-outline btn-sm" target="_blank" rel="noopener">编辑报表</a></div>
</div>
```

- **统一收尾句**（只在 `fix` 之后追加一次，不在每个词条里重复）：
  「需要修正这条报表时，点击【编辑】打开该报表的编辑页（新窗口），改完保存后回到本页重新执行即可。」
- `report_id > 0` 才出现入口；**预览（report_id=0）不出**——那时报表尚未保存，编辑页无处可去。
- 入口出现时共 **2 个**同 URL 链接（正文【编辑】+ 右侧按钮），测试锁死数量。

### 3.2 文案字典 `report._ERROR_GUIDES`

- 结构：`{title, cause, fix}`；数字键（错误码）**不自带 message**，主文案运行时取
  `_DB_ERRNO_HINTS` —— 单一来源，防两处文案漂移。
- 键：`write_denied`、`pool_missing`、`1064`、`1146`、`1054`、`1142`、`1044`、`1045`、
  `2003`、`2005`、`1205`、`1969`、`unknown`。
- `write_denied["message"]` 直接引用 `WRITE_DENIED_MESSAGE` 常量；
  `unknown["message"] = None`，运行时兜底用 `friendly`。
- **扩充规则**：新增可识别的失败类型（新错误码 / 新业务拦截）时，同一次任务内加一条词条；
  没有词条就走 `unknown`（通用建议：核对 SQL 与连接池、把原始错误发给管理员）。

### 3.3 选择优先级 `report.error_guide`

显式 `guide_key` > `PermissionError` → `write_denied` > `_error_errno()` 命中的数字词条 > `unknown`。

`_error_errno(e, raw)`：先看异常对象 `errno` 属性，再用 `\((\d{4})\)` / `^(\d{4})\s` 从原始文本提取；
与原 `humanize_db_error` 内联逻辑同源，抽出后两处共用。

### 3.4 出口清单

| 出口 | 处理 |
|------|------|
| `report.py` 主查询错误 `except` | `render_sql_error_section(friendly, raw, report_id=report_id, error=e)` |
| `report.py` 连接池缺失分支 | `guide_key="pool_missing"` + 报表名/`pool_id` 进 raw |
| `/report/preview`（有 id） | 与主出口同一路径，自动带上编辑入口 |
| `/report/preview`（无 id） | 无入口（`report_id=0`） |
| `api_handler` 403 / `export` 403 | **不变**：JSON / 纯文本只回 `WRITE_DENIED_MESSAGE` 常量，不得塞 HTML |
| 连接池测试 `config_pages/pools.py` | 复用 `humanize_db_error`，签名与「短句人话」形态保持不变 |

### 3.5 文案与样式

- `WRITE_DENIED_MESSAGE` 去掉尾巴 →「该报表包含写操作语句且未开启『允许执行写操作』」
  （按钮就在旁边，再说「请到编辑页开启」是重复）。
- 样式只加到 `ui_assets.COMMON_CSS` 的 `.flash-*` 组，**禁止页面级补丁**：
  `.flash-title` / `.flash-hint` / `.flash-hint strong` / `.flash .grow` / `.flash-actions` /
  `.flash-error a:not(.btn)` / `.flash-error .flash-hint a` / `.flash-details` /
  `.flash-details summary` / `.flash-details pre`。
- **对比度**：`--ink-3`(#6c717c) 在 `--danger-soft`(#ffefed) 上只有 4.39:1 **不达标**，
  正文与 summary 一律用 `--ink-2`(#555b68, 6.11:1)。

## 4. 验证

- `tests/test_error_guide.py`：字典结构、数字键与 `_DB_ERRNO_HINTS` 对齐、选择优先级、
  三段式版式、两个编辑链接、预览无入口、HTML 转义、标签平衡，以及写拦截 / 连接池缺失 /
  有 id 预览三条**页面级**断言。
- 既有门禁需同步：`tests/test_b7_dedup.py`（错误块仍含人话与原始文本）、
  `tests/test_trust_baseline.py`（1064 含「语法」+ `<details`）、`tests/test_b9_moves.py`
  （`_COMMON_CSS` 字节/hash 与 vendor hash8）。改 `COMMON_CSS` 后必须重启服务再验（进程级 URL 缓存）。
- 浏览器取证：无头 Chrome 计算样式断言 `.flash-actions .btn` 在三态都存在、预览态不存在。

## 5. 明确不做

- 不做「错误码 → 一键自动修复」按钮（写操作是否有意，只有报表作者能判断）。
- 不在 API / 导出通道返回 HTML 或链接（消费方是程序，不是人）。
- 不为每个错误码发明独立版式；差异只在字典文案。
