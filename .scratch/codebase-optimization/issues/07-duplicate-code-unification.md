# 07 — 重复代码统一

**What to build:** 统一三组重复代码：(1) 排序按钮（上移/下移/置顶/置底）在 config.py 中有 4 份实现，提取为可复用组件；(2) 分类树渲染（递归 `<ul><li>`）在 report.py 和 config.py 各实现一次，提取为公共树组件；(3) SQL 格式化/高亮在 report.py（SQL debug）和 config.py（SQL 编辑框）各实现一次，统一为 shared 函数。所有统一后的组件放入 render.py 或新增的公共模块。

**Blocked by:** 04 — report.py 瘦身, 05 — config.py 瘦身（需要两个模块先完成迁移，因为重复代码分布在两者中）

**Status:** ready-for-agent

- [ ] 识别并提取排序按钮 4 份实现为 1 个公共函数
- [ ] 识别并提取分类树 2 份实现为 1 个公共组件
- [ ] 识别并提取 SQL 高亮 2 份实现为 1 个公共函数
- [ ] 所有调用点切换为公共组件
- [ ] 运行全量测试，确认无回归
