# 02 — export.py 私有符号清理

**What to build:** 消除 `export.py` 对 `report._format_cell` 的依赖。`_format_cell` 是一个格式化函数（将 Python 值转为显示字符串），不依赖 report 模块的上下文。将其提升为公共函数（比如放在 `render.py` 或新建 `utils.py` 中），export.py 改为导入公开名称。不修改 `_format_cell` 的行为逻辑。

**Blocked by:** 无 — 可立即开始

**Status:** ready-for-agent

- [ ] 定位 `_format_cell` 的函数定义和所有调用点
- [ ] 将其移动到公共位置（`render.py` 或 `utils.py`），改名为 `format_cell`（去掉 `_` 前缀）
- [ ] export.py 改为从新位置导入公用名
- [ ] report.py 内的调用点也改为导入公用名
- [ ] 更新相关测试（test_export.py 中的导入引用）
- [ ] 运行全量测试，确认无回归
