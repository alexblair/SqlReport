# 01 — AppContext + render.py 基础模块

**What to build:** 新建 `context.py` 和 `render.py` 两个模块，作为后续所有重构的公共基础。`context.py` 包含一个纯数据容器 `AppContext`（无生命周期，仅有字段），持有配置DB连接、Redis管理器、查询缓存、会话等共享依赖。`render.py` 使用 `string.Template` 实现公共 HTML 模板（页面头/尾/导航栏/CSS/JS），供报表页和配置页渲染调用。不修改任何现有代码，全量测试保持不变。

**Blocked by:** 无 — 可立即开始

**Status:** ready-for-agent

- [ ] 新建 `context.py`：`@dataclass` 定义 `AppContext`，包含 `config_db`、`redis_manager`、`query_cache`、`sessions` 四个字段
- [ ] 新建 `render.py`：使用 `string.Template` 定义公共 HTML 布局模板（页面头/尾/导航栏/公共CSS+JS）
- [ ] render.py 导出至少 3 个模板函数：`render_page_header`、`render_page_footer`、`render_navbar`
- [ ] 各函数接收纯数据 dict，返回渲染后的 HTML 字符串
- [ ] 为 `context.py` 编写测试：验证 AppContext 字段正确初始化，支持 field-by-field 设置
- [ ] 为 `render.py` 编写测试：验证每个模板函数在正常/空输入下返回正确 HTML 结构字符串
- [ ] 运行全量测试，确认无回归
