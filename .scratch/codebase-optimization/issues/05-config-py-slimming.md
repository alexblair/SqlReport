# 05 — config.py 瘦身 + 内联 import 消除

**What to build:** 以 01 建立的 AppContext 和 render.py 为基础，重构 config.py。核心目标：拆分 `handle_request` 的巨型 if-elif 链（1374行）和 `_render_category_section`（315行），HTML 渲染移至 render.py，消除所有 `from auth import ...` 和 `from redis_cache import ...` 等内联 import 改为通过 AppContext 注入。

**Blocked by:** 01 — AppContext + render.py 基础模块

**Status:** ready-for-agent

- [ ] config.py 各 handler 函数改为接收 `ctx: AppContext` 参数
- [ ] 拆分 `_render_category_section` 多个嵌套函数为独立函数，HTML 移至 render.py
- [ ] 消除所有内联 import（auth、redis_cache 等）→ 改为 ctx.* 访问
- [ ] 更新 test_config.py 的 mock 策略以适配 AppContext 注入
- [ ] 每一步修改后运行全量测试，确认无回归
