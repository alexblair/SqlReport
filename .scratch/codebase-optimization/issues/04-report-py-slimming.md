# 04 — report.py 瘦身 + 测试更新

**What to build:** 以 01 建立的 AppContext 和 render.py 为基础，重构 report.py。核心目标：将 `_build_report_html`（520行）按功能切分为表头渲染、分页栏、排序面板、字段选择器、数据表格体、调试面板等独立函数/类，并将 HTML 生成部分移至 render.py。`_build_sql_debug_html`（215行）同样迁移。业务逻辑函数接收 `ctx: AppContext` 参数替代模块级全局变量。逐步迁移，改一个函数测一次。

**Blocked by:** 01 — AppContext + render.py 基础模块

**Status:** ready-for-agent

- [ ] report.py 入口函数改为接收 `ctx: AppContext` 参数
- [ ] 拆分 `_build_report_html` 为 5+ 个专注小函数
- [ ] 将 HTML 生成逻辑迁移到 render.py 模板函数中
- [ ] 迁移 `_build_sql_debug_html` 到 render.py
- [ ] 消除 report.py 中对模块级全局变量的直接引用（改为 ctx.*）
- [ ] 更新 test_report.py 的 mock 策略以适配 AppContext 注入
- [ ] 每一步修改后运行全量测试，确认无回归
