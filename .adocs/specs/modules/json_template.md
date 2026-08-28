---
module: json_template
contract_id: MOD-JSON_TEMPLATE
version: 1.0
depends_on: [app_config]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# json_template.py 模块分卷

> 本分卷由 T-007 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`json_template.py`（~300 行，10 个 def）——**API JSON 输出模板引擎**（纯标准库，零第三方依赖）。JSON 占位符替换，替换后必须是合法 JSON。支持单结果集和全结果集两种模式，支持智能去引号。

## 2. 公开 API 契约

- `is_template_enabled(template)` → bool：模板留空/空白 = 未启用。
- `render_template(template, context, keys=None, smart_quote_flags=0)` → (bool, str, str)：渲染模板，返回 (ok, output, error)；含未知占位符检测与 JSON 合法性校验。
- `validate_template(template, keys, smart_quote_flags=0)` → (bool, str)：校验模板是否可用（保存前把关）。

### 内部函数

- `_is_valid_key(name)` → bool：占位符名是否在任一模式键集内。
- `_value_to_json(value, smart_quote_flags=0)` → str：值序列化为 JSON 片段。
- `_pos_to_line_col(text, pos)` → (int, int)：字符位置 → (行, 列)。
- `_split_segments(template)` → list[tuple]：按占位符切分。
- `_render_to_output(segments, context, smart_quote_flags)`：渲染各段。
- `_output_pos_to_template_pos(segments, lengths, pos, template_len)`：输出位置 → 模板位置。

### 常量

- `_PLACEHOLDER_RE`：`\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}`。
- `SINGLE_KEYS`：单结果集模式键集（`data`/`total`/`page`/`page_size`/`total_pages`/`full`/`meta`）。
- `ALL_KEYS`：全结果集模式键集（`results`/`mode`/`page`/`page_size`/`full`/`meta`）。
- `_VALID_KEYS`：两模式键集的 frozenset 并集。
- `_SAMPLE_SINGLE_CONTEXT` / `_SAMPLE_ALL_CONTEXT`：校验/预览用内置样例上下文。

## 3. 数据流

```
模板文本 + 渲染上下文
  → is_template_enabled()（空白检查）
  → _split_segments()（正则切分）
  → 校验占位符名合法性（keys 限定或 _VALID_KEYS 宽松）
  → _render_to_output()（占位符替换为 JSON 片段）
  → json.loads()（合法性校验）
  → 返回 (ok, output, error)
```

## 4. 依赖关系

AST import 实测：`app_config`。
- `app_config`：`serialize_json`（标准 JSON 序列化）、`serialize_smart_quotes`（智能去引号）。
- 被调用方：api_handler（模板渲染）、config（模板校验/预览）。

## 5. 边界与异常

- JSON 合法性校验：渲染后 `json.loads()` 必须通过，否则返回 error。
- 未知占位符检测：占位符名不在键集内 → error。
- 错误定位：`_pos_to_line_col` 将字符位置映射为 (行, 列)，便于用户定位。
- 智能去引号：通过 `smart_quote_flags` 控制。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 json_template.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
