---
module: result_transform.py
contract_id: MOD-RESULT_TRANSFORM
version: 1.0
depends_on: []  # 纯函数模块，无内部依赖
last_reviewed_commit: 78895ce
last_reviewed_at: 2026-08-28
---

# result_transform.py 模块分卷

> 本分卷由 T-003 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`result_transform.py`（354 行，13 个 def）——**结果集变换模块（纯函数，无 IO）**。提供内存中的多字段筛选、多字段排序、分页计算、数值筛选合法性检测、列选择与列索引映射等纯函数能力。被 report（报表页）、api_handler（API）、export（导出）复用，是「结果集在内存中变换」的唯一事实来源。

## 2. 公开 API 契约

### 2.1 分页

- `calc_total_pages(total: int, page_size: int)` -> int：计算总页数（`ceil(total/page_size)`，page_size 非法/0 时安全回退）。

### 2.2 筛选

- `parse_filter_expr(raw)` -> list：解析筛选值表达式 → 多值段列表（多值之间 OR 语义，全系统统一语法）。
- `_split_filter_value(raw)` -> list：按裸英文逗号拆分段（`\,` 为字面逗号不拆分）。
- `_segment_regex(tokens)` -> str：段 token 列表 → 正则模式（`*` → `.*`，字面量 re.escape）。
- `_compile_segments(segments, ignorecase: bool)` -> list：多值段 → 编译后正则列表（contains 不敏感，eq/neq 敏感）。
- `_cell_str(val)` -> str：行值字符串化（None → 空串，保持 contains/eq/neq 语义）。
- `filter_rows(rows: list[tuple], columns: list[str], filters=None)` -> list：在内存中按多字段筛选（AND 逻辑）。支持操作符：
  - `contains`/`not_contains`（子串，不区分大小写，多值段 OR）
  - `eq`/`neq`（精确/不等，区分大小写）
  - `gt`/`lt`/`gte`/`lte`（数值比较，`NUMERIC_FILTER_OPS`）
  - 筛选条目形式：`[(col, op, val), ...]`；数值条件遇非数值静默跳过（由 `invalid_numeric_filters` 报告）。
- `invalid_numeric_filters(filters)` -> list：返回条件值无法转为有限数值的数值比较条目 `[(col, op, val), ...]`（供 UI 提示被忽略条件）。

### 2.3 排序

- `sort_rows(rows: list[tuple], columns: list[str], sorts=None)` -> list：在内存中按多字段排序（稳定排序）。
  - sorts 形式：`[(col, dir), ...]`，dir 为 `"asc"`/`"desc"`（或 `"1"`/`"-1"` 等兼容）。
  - 逐字段分区排序，数值列按数值比较、非数值按字符串比较。
- `_ordered_by_column(part, col_idx, reverse)` -> list：单列分区排序（`_ordered_by_column` 辅助，稳定分区）。

### 2.4 列处理

- `_try_float(val)` -> float | None：尝试将值转 float，失败或非有限值（NaN/Inf）返回 None（数值筛选基础）。
- `select_columns(all_columns: list[str], requested=None)` -> list：从 all_columns 中选择要显示的列（按请求顺序、去重、仅保留存在的列）。
- `column_indices(display_cols: list[str], all_columns: list[str])` -> list：将显示列列表映射为在 all_columns 中的索引列表（调用方保证列存在）。

## 3. 数据流

```
report.execute_report / api_handler / export
  → filter_rows(rows, columns, filters)      # 多字段 AND 筛选（contains/eq/数值比较）
  → sort_rows(filtered, columns, sorts)      # 多字段稳定排序
  → calc_total_pages(total, page_size)       # 分页计算（调用方做切片）
  → select_columns/column_indices            # 显示列选择与索引映射
  → invalid_numeric_filters(filters)         # UI 提示被静默忽略的非法数值条件
```

## 4. 依赖关系

AST import 实测：**无内部依赖**（纯函数模块，零 IO）。仅使用 Python 标准库（`re` 正则、`functools` 等）。
- 被调用方：report.py（`filter_rows`/`sort_rows`/`calc_total_pages`/`invalid_numeric_filters`/`select_columns`）、api_handler.py、export.py、config.py。

## 5. 边界与异常

- 数值筛选：`_try_float` 对 NaN/Inf 返回 None → 条件视为非法被跳过（`invalid_numeric_filters` 报告）。
- 多值段：逗号拆分支持 `\,` 字面逗号；`*` 通配 → `.*`；contains 不区分大小写、eq/neq 区分。
- 空值（None）单元格：`_cell_str` 归一化为空串，保持 contains/eq/neq 语义。
- 排序稳定性：多字段分区排序保持稳定（不破坏同序字段的原有相对顺序）。
- 列选择：请求列不存在时静默忽略，仅保留存在的列，按请求顺序去重。

## 6. 保鲜核对提交点

- last_reviewed_commit: 78895ce（T-002 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 result_transform.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
