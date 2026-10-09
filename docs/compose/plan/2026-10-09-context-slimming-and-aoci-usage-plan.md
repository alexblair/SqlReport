# 上下文瘦身与 AOCI 使用面 实施计划

> 状态: 已完成
> 对应 spec: ../spec/2026-10-09-context-slimming-and-aoci-usage-design.md
> 最后更新: 2026-10-09

## 任务清单

- [x] **T1 读路径脚本**：新增 `scripts/agent/aoci_precheck.py` + `tests/test_aoci_precheck.py`。验收：单测绿 + 实跑输出两段 F/S。证据：8 用例绿；实跑 `report.py`/`06 卷` 命中写报表跳缓存、隐藏页卡 mermaid 等约束。
- [x] **T2 指标**：`session_cost.py` 新增 AOCI 读/预检/maintain 三指标。验收：`--check` 一行可见。证据：本会话实测 `AOCI-读=19次(预检19)`。
- [x] **T3 门禁**：限额改 11000/13000/22000 + 新增分卷合计 ≤155000、course-state ≤8000、`硬性 #N` 断链检查；`gate_redproof.py` 补 3 条 RED 变异。验收：超限/断链时红（RED 自证）。证据：`gate_redproof` **14/14**。
- [x] **T4 AGENTS.md 重写**：21→14 条只留结论；§0 加定向读说明（采用段落而非新增表格列，成本更低）；§5 压缩；aoci 最小块重写。验收：≤11 KB。证据：**17933 → 10992 B**；`test_doc_budget` 绿。
- [x] **T5 MEMORY.md 瘦身**：只留用户纠正/指示 + 不可推断环境事实。验收：≤13 KB。证据：**25725 → 9771 B**。
- [x] **T6 分卷瘦身**：验收：逐文件达标 + 合计 ≤155 KB。证据：`06` 42105→12625、`08` 30629→11824、`09` 22737→7355、`10` 12564→6497、`11` 17995→6995、`INDEX` 12021→7984、`01` 10032→6490、`03` 12917→9966、`README` 6894→6383、`course-state` 14939→5153；**分卷合计 81897 B**；`test_doc_budget` 违规 19→0。
- [x] **T7 spec 取代两头改**：旧 spec 状态头已标「文档预算口径被修订」+ 新旧限额（部分修订而非整个取代，因 #20 其余内容继续有效）。
- [x] **T8 收尾**：验收全部达成。证据：L2 全量 `exit 0`（日志落 `run-logs/`）；`gate_redproof` 14/14；`codegraph sync` 142→146 文件；AOCI `scope acknowledge` → 3 批共 **28 条**条目整批提交 → `verify` Missing/Orphan/Stale/Unbaselined 全 0 → `check` **aligned:true, next_action:none**（余 151 条 `code_skipped` 为截图/DB 运行态告警，不阻断）→ `guide` **complete:true, stage:aligned, executable_targets=0**。

## 验证计划

- L0：`python -m unittest tests.test_doc_budget -v`、`tests.test_aoci_precheck -v`、`tests.test_temp_log_policy -v`
- L1：`python -m unittest tests.test_render tests.test_ui_tokens -v`（文档改动不应影响 UI 门禁）
- L2：`python -m unittest discover -s tests/ -t . -v`（收尾一次）
- 机械检查：`grep -rn "#N"` 断链、`wc -c` 逐文件体积、`git diff --stat`

## 执行记录

- 2026-10-09 设计阶段：AOCI 只读评估（`.aoci/ledger.jsonl` 87 事件；读 6 / 写 35；baseline 376 文件 0 漂移；151 常驻 warning）→ 用户选定力度 A + 边界提案。
- 2026-10-09 实施中（进度）：T1/T2/T3 完成（`aoci_precheck.py` + 单测、`session_cost.py` 读/预检指标、`test_doc_budget.py` 新限额与 `#N` 断链门禁 + `gate_redproof.py` 三条新 RED 变异）；T4 完成（`AGENTS.md` 17933 → **10992** B，21→14 条，退役 #4/#9/#10/#11/#13/#15/#16）；T6 部分完成（`06` 42105→12653、`08` 30629→11824、`09` 22737→≤22000 区间内、`10` 已压）；T5/T7/T8 待做。门禁违规 19 → 5。
- 踩坑入库：编辑锚点不能从 diff 上下文行推断（两次锚点错位导致重复行/丢条目），必须 `read` 目标区间后再编辑；出错后 `undo_last_edit` 可完整回滚。
- 门禁自证（`gate_redproof.py`，日志落 `run-logs/aoci-eval/` 目录）：12/14 通过；两条 FAIL 均因 GREEN 态尚未达标，扫尾后重跑应 14/14。
- T5 完成：`MEMORY.md` 25725 → **9771** B（只留用户纠正/指示 + 不可推断环境事实）。T6 已达标：`06` 12625、`08` 11824、`09` 7355、`10` 6497、`11` 6995；`INDEX/01/03/README/course-state` 由收尾子代理处理中。
- 已发现并发写入者：另有会话在改 `docs/compose/spec/2026-10-09-temp-artifact-lifecycle-design.md`、`2026-09-29-execution-layer-performance-design.md` 与 `09/10` 卷（16:20-16:22 有写入）；**最终验证与 AOCI 维护必须在无其他写入者时进行**。
- **收尾结果（已全部完成）**：① 全量测试 L2 `exit 0`；② `gate_redproof` 14/14；③ `codegraph sync` 已跑，`pendingChanges` 归零；④ AOCI 收尾链完成：`scope acknowledge`（observed_evidence_review_required → 0）→ `maintain` 三轮（11+15+2）→ 整批 `update_entry` → `verify` 全 0 → `check` aligned:true → `guide` complete:true；⑤ 历史 spec 退役号引用已修 3 处（另 2 处属并发会话在改的文件）。
- 后续补完（并发写入者关闭后）：① `10-token-budget.md` 已压回目标（删重复的收尾取证段、历史账本两行并一行、去末行核对）；② 历史 spec 退役号引用已全部修正（`temp-artifact-lifecycle-design.md` 的 #16 与 `execution-layer-performance-design.md` 的 #11 → #17）；③ 评估结论已落长期依据 `../reports/2026-10-09-aoci-effectiveness-evaluation.md`。
- **待人工裁决（会阻塞 AOCI）**：151 条 `code_skipped` 需一次受管范围变更（已加 3 条期望规则 `proj-shots-observe` / `proj-sqlite-shm-exclude` / `proj-sqlite-wal-exclude`）；机器判为需真人审批，`check` 在激活前停在 `blocked`，preview 落在 `.aoci/scope-change/` 下。
