# Token 预算纪律（#20）实施计划

> 状态: 已完成
> 对应 spec: ../spec/2026-10-06-token-budget-design.md
> 最后更新: 2026-10-06

## 任务清单

- [x] T1 复盘取证：读 4 个会话真实 `usage`，量化成本结构（`/root/.dsh/sessions/--opdev-SqlReport--/`）
- [x] T2 工具：`scripts/agent/session_cost.py`（`--list/--last/--all/--session/--file/--selftest`）
      验收：`--selftest` 10 项断言通过；`--session 79094439` 复现报告数字
- [x] T3 知识库分卷：`docs/compose/knowledge/10-token-budget.md`（账本 + R1–R5 + 命令表 + 交接模板）
- [x] T4 硬性约束：`AGENTS.md` 新增 #20，登记 §0 路由表 / §2 分卷表 / §5 检查单第 8 条
- [x] T5 索引同步：`knowledge/README.md`（索引表 + 20 条 + 160 行）、`knowledge/INDEX.md` §8、
       `learn/sqlreport-kb/course-state.md` 第 10 章
- [x] T6 门禁：`tests/test_doc_budget.py`（AGENTS.md/MEMORY.md/分卷体积 + 路由可解析 + 无孤儿卷）
- [x] T7 门禁自证：`tests/bug_hunt/gate_redproof.py` 增 3 条内存变异（6~8），要求 RED-GREEN 全过
- [x] T8 跨会话记忆：`MEMORY.md` Rules #19 + Discovered「DSH 会话记录可直接读」
- [x] T9 证据报告：`docs/compose/reports/2026-10-06-token-efficiency-retrospective.md`

## 验证计划

```bash
venv/bin/python -m unittest tests.test_doc_budget -v          # L0 门禁 6 用例
venv/bin/python scripts/agent/session_cost.py --selftest      # 工具自测 10 断言
venv/bin/python tests/bug_hunt/gate_redproof.py               # 8/8 RED-GREEN
venv/bin/python -m unittest tests.bug_hunt.test_static_analysis -v   # 新增 .py 过静态分析
venv/bin/python -m unittest discover -s tests/ -t . -v        # L2 全量（-t . 不可省）
codegraph sync && codegraph status                            # #19 pendingChanges 全 0
```

## 执行记录

- T1：4 会话 = 440 步 / 69,666,456 tokens（cacheRead 98.56% / output 0.58%）。
  报告落 `docs/compose/reports/2026-10-06-token-efficiency-retrospective.md`。
- T2：`session_cost.py` 自测 10/10 通过。**踩坑 2 处**（已记入报告「走过的弯路」）：
  ① 用字符数当 token 代理会误把 `data.stream`（1.5M 字符回放产物）算进上下文；
  ② `data.step` 非单调，步骤编号必须按记录顺序。
- T3~T5：分卷与四处索引同步完成；`AGENTS.md` 16,720 字节（上限 18,000）。
- T6/T7：门禁 6 用例绿；`gate_redproof.py` 输出 **8/8 PASS**（新增 3 条 RED 均为 True）。
- T8/T9：完成。
- 偏差：无（未改任何生产代码 `*.py` 的业务逻辑；新增的是脚本、测试、文档）。
