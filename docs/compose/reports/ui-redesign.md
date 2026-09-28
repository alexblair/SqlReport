---
feature: ui-redesign
status: delivered
specs:
  - docs/compose/spec/ui-redesign.md
  - docs/compose/spec/cache-write-test-scenarios.md
plans: []
branch: main
commits: 9a975b9..812c884
---

# 全站 UI 重构与交付后质量闭环 — Final Report

## What Was Built

SqlReport 全站 UI 按已确认原型（`ui-redesign-prototype.html` / `ui-redesign-r2.html`）
完成结构级重构：统一 page-head + grid-2 双栏 + formbar 的表单页体系、卡片化的
API 列表与报表详情五页签、弹性布局（PC 宽屏利用率 42%→87.5%，移动端零溢出）、
重做的左侧分类树菜单。全部页面 HTML 仍由 `render.render_page_header` +
`build_*` 单一来源拼装，公共样式只存在于 `_BASE_CSS`/`_COMMON_CSS`。

交付后质量闭环（同轮完成）：清零 7 项 PRE-EXISTING 测试失败（缺导入/环境依赖/
时钟炸弹三条根因）、全量 2848 项回归全绿；缓存链路修复两处真实缺陷——数据源
连接建立失败不再绕过 Redis 过期快照兜底、含写 SQL 的报表禁止被缓存短路；
`htmlcheck` 结构门禁补齐报表配置页/API 列表页整页用例；产出可复跑的缓存四场景
测试资产（`tests/manual_cache_scenarios.py` + 用例文档）。

## Architecture

- **UI 单一来源**：`render.py`（`_BASE_CSS`/`_COMMON_CSS`/`_COMMON_JS` + 全部
  `build_*`）；`config.py`/`report.py` 只引用公共 class，页面级差异走
  `render_page_header(extra_css=...)`。
- **布局体系**：`.container{width:100%}` + 断点阶梯（1440/1680/1920/2400）；
  grid 一律 `minmax(0,1fr)` 防 min-content 撑爆；左菜单 `.tree/.cat` flex 行 +
  `toggleCatNode` 逐级折叠（锚点与 localStorage 保留）。
- **报表执行**：`report.execute_report`（:988 起）写护栏 →
  `skip_cache_read = force_rebuild or sql_contains_write(sql)` → L1
  `QueryCache` → L2 `redis_cache` 快照（`compute_config_version(sql,pool_id)`
  进键）→ MySQL；连接期或查询期失败 → 过期快照兜底 `cache_info.source=
  "redis_fallback"`。
- **测试结构门禁**：`tests/htmlcheck.py`（标签配对 + 防嵌套 form + SVG 自闭合
  白名单）由 `tests/test_html_structure.py` 21 例驱动，整页覆盖含报表配置页与
  API 列表页有数据态。

### Design Decisions

- **五项有理由偏差**：配置右列保留分组多表（分组信息不丢）、池表单独立页、
  用户页平权管理员文案、新建接口挂既有路由、调试磁贴用现有数据源——均以
  「确认稿与数据实义冲突时以正确语义落地」为准并入档。
- **写报表禁缓存短路**：`prefer_cache=1` 的写报表曾在热快照下短路（页面显示
  写后结果而库未动）；选择在 `execute_report` 读路径按 SQL 语义强制跳过，而非
  编辑期校验——因为存量配置无需迁移即刻生效。
- **连接期与查询期同等兜底**：`mysql.connector.connect` 连接被拒时立即抛，
  故 create 与 execute 同入内层 try，兑现 docstring 既有承诺。
- **测试夹具**：整页用例用 `make_config_db()+init_test_db()`（现行 schema），
  避开 `test_config._make_conn` 手写 DDL 的漂移（缺 `parent_id`）。

## Usage

- 服务：`source venv/bin/activate && python server.py`（配置见
  `app_config.json` / `app_config.debug.json`；`scheduler.enable` 当前为 true）。
- 全量测试：`python -m unittest discover -s tests/ -v`（或按 AGENTS L2 分段）。
- 缓存四场景复跑：启动测试 Redis（6390，见文档命令）后
  `venv/bin/python tests/manual_cache_scenarios.py`（全 PASS → exit 0）。
- API 密钥：配置页生成，`/api/<接口名>?api_key=sk-…` 或 Bearer。

## Verification

- 官方全量入口：**Ran 2848, OK (skipped=4)**（integration 设计性跳过）；
  分段 38 段 0 失败交叉一致。
- 7 项原失败修复后三段（debugcfg/preset/scheduler）全绿，MEMORY 基线清零。
- 缓存四场景 30 断言全 PASS（含修复后 3c/4b 翻转断言）；execute_report 影响
  分段 report/export/api/scheduler 677 项 OK。
- 独立评审（R2 阶段）三结论零 critical；终验 17 张截图 7 断言 PASS。
- 刚性约束审计：共享语义模块与 ROUTES 零改动、无第二套 class/内联 style、
  静态分析与 htmlcheck 门禁绿。

## Journey Log

- [lesson] 同一任务多写入者必竞态：并发子代理曾互相覆盖半成品——对策是唯一
  活跃执行者 + mtime 轮询 + 终态主会话亲测裁决（AGENTS #13–#15 由此立规）。
- [lesson] 同一问题失败 2 次必须停下找根因：htmlcheck 整页夹具连败两轮，根因
  分别是手写 DDL 漂移与漏调 `init_test_db`，盲试第三轮只会更糟。
- [dead end] 测试断言 `FAR_FUTURE=NOW+30d` 是时钟炸弹，系统日期越过即假失败
  ——固定“未来”偏移的断言应基于 `max(固定, time.time())`。
- [pivot] 场景3 初版断言 `redis_fallback` 失败，实为热快照下数据源零触碰的更
  优路径——测试预期须按真实代码路径分层（常规命中 vs 强制重建兜底）。
- [lesson] `unittest.mock` 等子模块不会因父包导入而挂载，分段 discover 首载
  即暴露；模块顶显式 `import unittest.mock` 一行根治。

## Source Materials

| File | Role | Notes |
|------|------|-------|
| `docs/compose/spec/ui-redesign.md` | 主 spec（R1+R2+反馈轮账本） | status: delivered，19 任务全勾 |
| `docs/compose/spec/cache-write-test-scenarios.md` | 缓存四场景测试设计与实测 | 转单测蓝本 |
| `docs/compose/spec/ui-redesign-prototype.html` | R1 确认原型 | 用户已确认 |
| `docs/compose/spec/ui-redesign-r2.html` | R2 确认稿（5 页签+17 截图） | 用户已确认 |
| `docs/compose/spec/ui-redesign-inventory.md` 等 | 盘点/IA/视觉规范 | 过程素材 |
| `docs/compose/knowledge/03,06,07,08-*.md` | 知识库回写 | 已随最终代码同步 |
