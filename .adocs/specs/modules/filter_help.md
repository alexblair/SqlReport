---
module: filter_help
contract_id: MOD-FILTER_HELP
version: 1.0
depends_on: []
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# filter_help.py 模块分卷

> 本分卷由 T-007 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`filter_help.py`（~150 行，2 个 def）——**筛选语法帮助**。全系统单一来源：结构化帮助内容（5 个分区 + 3 条补充说明）+ 渲染为 HTML 片段（`?` 入口 + 弹窗 + 开关 JS）。被报表页和审计页共用。

## 2. 公开 API 契约

- `filter_help_content()` → dict：返回结构化帮助内容（sections + notes），测试断言用。
- `render_filter_help()` → str：渲染完整 HTML 片段（`?` 入口 + 弹窗 + 开关 JS）。

### 常量

- `_FILTER_HELP_SECTIONS`：5 个帮助分区（多值匹配/通配符/等于/不包含/转义），含标题/说明/案例表。
- `_FILTER_HELP_NOTES`：3 条补充说明（AND 关系/空格忽略/默认模糊匹配）。
- `FILTER_HINT_SUFFIX`：统一 placeholder 提示后缀 `"（*通配,多值）"`。

## 3. 数据流

```
调用方（报表页/审计页）→ render_filter_help()
  → 遍历 _FILTER_HELP_SECTIONS 生成分区 HTML
  → 遍历 _FILTER_HELP_NOTES 生成补充说明
  → 返回 HTML 片段直接嵌入页面
```

## 4. 依赖关系

AST import 实测：**无项目模块依赖**（纯标准库 + 内联 HTML/JS）。
- 被调用方：render（build_controls_bar_html 等嵌入帮助片段）。

## 5. 边界与异常

- 纯 UI 生成：无 IO/DB 操作，无异常路径。
- 唯一公共常量 `FILTER_HINT_SUFFIX` 被 render 和 config 引用。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 filter_help.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
