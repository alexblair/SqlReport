---
type: module
id: MOD-RESULT_TRANSFORM
module: result_transform.py
tags:
- transform
- filter
- nested-filter
version: '1.1'
last_reviewed_commit: d455c81116eb2c1e114dcf045e010043ff9acf83
last_reviewed_at: 2026-08-29
---

# result_transform.py 模块节点

> **依赖**：无外部依赖（纯函数，无 IO）。被 `report.py`、`export.py`、`api_handler.py` 三处调用方共用。

## 职责概述

`result_transform.py` —— **结果集内存变换模块**：对取回的结果集（rows + columns）执行筛选、排序、列选择、列索引映射。T-001 在既有 `filter_rows` 基础上新增嵌套筛选（and/or 递归条件树）与 value 表达式语法，全部为纯函数、无 IO，并复用既有操作符语义。

## 公开 API 契约

### 2.1 既有筛选入口

**`filter_rows(rows, columns, filters=None) -> list[tuple]`**
- 内存中按多字段 AND 筛选；`filters = list[(col, op, q), ...]`。
- 操作符：`contains`/`notcontains`/`eq`/`neq`/`gt`/`lt`/`gte`/`lte`/`isempty`/`notempty`。
- 单一条件匹配逻辑已抽取至 `_apply_single_filter`，供嵌套筛选复用（语义一致）。

### 2.2 T-001 新增 API

**`filter_rows_nested(rows, columns, nested_filter) -> list[tuple]`**
- 按嵌套筛选条件树求值，返回**新列表（不修改入参，不污染缓存，FR-006）**。
- `nested_filter` 结构：`{"op": "and"|"or", "conditions": [节点, ...]}`；节点可为分组（op+conditions）或叶节点 `{"col", "op", "value"}`。
- 空 dict / None / 空 conditions → 视为 no-op，返回原全部行。
- 递归深度不限（FR-001）；OR 语义对原始候选行分别求值后取并集（按对象身份去重）。

**`resolve_expression(value) -> str`**
- 解析 value 字段表达式语法 → 字面量；**不区分大小写（统一转小写，FR-002）**。
- 支持：`now()`/`today()`、`yesterday()`/`tomorrow()`、`date_add(base, n, unit)`、`date_sub(base, n, unit)`、`date('YYYY-MM-DD')`。
- base 可为 `now()`/`today()`/`yesterday()`/`tomorrow()` 或 `'YYYY-MM-DD'`；unit ∈ `day`/`week`/`month`/`year`（可带 s）。
- 非表达式 / 无法识别 → 原样返回（不报错）。

**`validate_nested_filter(nested_filter, available_columns=None) -> {"valid": bool, "errors": [...]}`**
- 结构化校验（FR-012）；`errors` 每项 `{"path", "message", "suggestion"}`——指明问题条件位置、原因，并基于实际输入给出修正建议（假设用户无编程基础）。
- `available_columns` 可选列名白名单；提供时检测非法列名并给出可用列名建议。

### 2.3 内部函数（契约要点）

- `_apply_single_filter(result, columns, col, op, q)`：单一条件匹配（复用既有语义，新增 ISO 日期比较）。
- `_parse_numeric_or_date(s)`：值 → `(num, date)`；数值/日期统一比较入口。
- `_eval_node(rows, columns, node)`：递归求值单个条件节点。
- `_NESTED_LEAF_OPS`：嵌套筛选叶节点支持的操作符集合（同 filter_rows）。

## 与既有模块交接点

- `report.py` / `export.py` / `api_handler.py`：T-002/T-003 将嵌套筛选解析后合并进现有 `filters` 列表，统一经 `filter_rows` 或 `filter_rows_nested` 应用（FR-005/FR-007）。
- `filter_rows` 既有的「未知列静默跳过」「数值不可比静默跳过」行为在 `filter_rows_nested` 叶节点保持一致。

## 约束与边界

- **FORCE-FR-014**：全部新增函数位于 `result_transform.py`，未新建模块文件。
- **FORCE-FR-006**：`filter_rows_nested` 为纯函数，不修改入参、不触碰缓存。
- **FORCE-FR-002**：表达式语法统一 `.lower()` 后解析，大小写混用等价。
- 日期比较：`gt`/`lt`/`gte`/`lte` 当条件值与单元格值均为 ISO 日期时按日期比较，否则退回数值比较；类型不可比时静默跳过该行（与既有数值跳过语义一致）。
- 已知测试债（非 T-001 引入）：`tests/bug_hunt/test_static_analysis.py::test_no_import_errors` 与 `tests/test_ux_b6_polish.py::Test27a_ReportPageTitle` 在基线 54c7541 即失败，与本次变更无关。

## 测试资产

- `tests/test_nested_filter.py`：21 个单元测试覆盖表达式解析、递归求值、不污染缓存、中文、结构化校验。
- 回归脚本（`tests/regression/T-001/`）：由 P3 测试阶段机械落盘。
