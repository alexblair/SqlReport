# 03 — server.py 路由表重构

**What to build:** 将 `server.py` 中 `handle_request` 的巨型 if-elif 链（约 285 行）替换为显式路由表 `{path_pattern: handler_function}`。每个路由独立注册，取消当前单函数内的路径判断逻辑。不改变 HTTP 请求处理行为。

**Blocked by:** 无 — 可立即开始

**Status:** ready-for-agent

- [ ] 定义路由表数据结构（`dict[str, Callable]` 或 `list[tuple[str, Callable]]`）
- [ ] 提取每个 if-elif 分支为独立的 handler 函数
- [ ] 用 `do_GET` / `do_POST` 方法分发表取代当前的 `handle_request` 单入口
- [ ] 确保路径参数（如 `/report/123`）通过路由匹配提取
- [ ] 更新 test_server.py（测试用例结构可能需要对应调整）
- [ ] 运行全量测试，确认无回归
