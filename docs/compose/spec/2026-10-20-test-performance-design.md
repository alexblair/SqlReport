> 状态: 生效

# 全量测试性能与时机优化 设计

> 依据数据: [test-fullrun-perf-20261020.md](../reports/test-fullrun-perf-20261020.md)（2026-10-20 实测基线/根因/改后结果）
> 关联知识库: [08-testing-conventions.md](../knowledge/08-testing-conventions.md)

## 1 问题

全量自测（`python -m unittest discover -s tests/ -t .`）实测 **363s / 3221 条**。规则已把「全量次数」压到每会话 ≤2 次（`session-fce66c01`、`session-c983c002` 均为 2 次），但每次 6 分钟纯串行阻塞，且阻塞点落在收尾阶段——此时无其它事可做。

两个可优化维度：① 全量**本身**的耗时；② 全量的**使用时机**（何时跑、与什么重叠）。

## 2 实测基线（证据）

| 项 | 数值 |
|---|---|
| 全量 | `RAN=3221 failures=0 errors=0 skipped=4`，`RUN_SEC=362.6`，import 仅 0.5s |
| 单条 `test_keepalive_exception_does_not_break_loop` | **301.09s（占 83%）** |
| `test_import_overrides_pools_with_test_mysql` | 10.02s |
| `TestFaviconServing` 15 条 | 各 0.51s ≈ 7.6s |
| 静态分析（150 文件） | 7.13s，8 ERROR（已知误报）+ **6558 WARNING（全为内建名误报）** |
| 历史会话 | 每会话 2×363s ≈ 12.2 分钟串行等待 |

### 2.1 301s 根因（已验证）

`scheduler.py:39 _KEEPALIVE_INTERVAL_SECONDS = 300` → `scheduler.py:628` 未到点即返回 → 测试 `tests/test_scheduler_extra.py:443-455` 第二次触发保活须等真实 300s 节拍；夹具 `tick_seconds=0.01` 又被 `scheduler.py:270 max(1, int(tick_seconds))` 钳到 1s。

验证：脚本内把模块常量改为 0.05（不改文件）单跑该用例 → `Ran 1 test in 2.008s OK`。**即全量 363s → ≈62s，覆盖零损失。**

## 3 目标与非目标

- 目标：全量 ≤ 45s（预算红线 90s）；收尾阶段全量**阻塞时间 ≈ 0**（冻结即后台起跑，与知识库更新重叠）；既有 3221 条用例不留少一条、不改判（本次另加 8 条回归/门禁用例 → 3229 条 / 0 failure / 0 error / 4 skip / 42.53s）。
- 非目标：不改功能代码行为；不引入 CI；不引入 pytest/Node 链（硬性 #5）；不做分片并行（见 §4.4）；不减少任何一条用例。

## 4 设计

### 4.1 A 组 — 消除测试自身的病态等待（只改测试与静态分析器）

| # | 改动 | 手法 |
|---|---|---|
| A1 | 301s 用例 | 测试内 `patch.object(scheduler, "_KEEPALIVE_INTERVAL_SECONDS", 0.05)`，保留「保活异常不阻断主循环」两条断言 |
| A2 | 10s 用例 | 复用类内 `_fake_connector()` patch `preset_cases._mysql_connector`，DDL/权限路径照跑，不断真实 socket；另补 2 条建连参数断言 |
| A3 | favicon 15×0.51s | server 类级共享 + `serve_forever(poll_interval=0.01)`（服务端按请求读配置，可共享）；断言逐条不变 |
| A4 | 静态分析 builtins 误报 | `static_analyzer.py:234 set(dir(__builtins__))` 在模块上下文取到 **dict**，`dir(dict)` 不含 `int/len/str` → 6558 条「可能未定义的名称」误报。改为 `import builtins; set(dir(builtins))`，并补回归用例锁定该行为 |

A4 不只是省 7s 里的日志噪声——6558 条假 WARNING 会**淹没真 ERROR**，属「不遗漏」风险。

### 4.2 B 组 — 时机（流程 + 脚本，不改测试语义）

| # | 动作 | 落点 |
|---|---|---|
| B1 | 冻结即后台起全量，与知识库更新/diff 复查重叠 | `08-testing-conventions.md` 规则条目 |
| B2 | 前置 <10s 快速门禁（语法 + 静态分析）先跑，失败即停 | `scripts/agent/test_timing.py --quick`（含静态分析调用） |
| B3 | 全量结果指纹复用：记录 `git rev-parse HEAD` + `git diff` + 未跟踪 py 内容哈希，代码未变则直接引用上次结果 | `scripts/agent/test_timing.py` 写 `run-logs/` 下的结果 JSON（固定文件名，供复用） |

### 4.3 C 组 — 防回退

| # | 动作 |
|---|---|
| C1 | 慢用例哨兵：`scripts/agent/test_timing.py` 逐条计时，单条 >5s 打印 WARN 并落盘 |
| C2 | AST 门禁（`tests/test_no_slow_waits.py`）：`tests/` 内 `time.sleep(>1s)`、`wait/join/acquire(timeout>30s)` 即失败，同行 `slow-wait-ok:` 豁免；生产常量导致的真实节拍等待由 C1 的 >5s 运行期哨兵兜底 |
| C3 | 08 卷记录全量预算红线（≤90s）、热点清单与本设计踩坑 |

### 4.4 明确不做

**分片并行（4 进程）**：`tests/test_server.py:33 TEST_PORT = 19080`、`tests/test_health.py:19 TEST_PORT = 19081` 固定端口需独占分片；A 组做完后全量 ≈40s 且可后台跑，15s 收益不值得引入非官方入口与端口脆弱性。

## 5 判定标准（不遗漏）

1. 用例 id 集合：既有采集集不变，仅新增 8 条（`tests/bug_hunt/test_static_analysis.py` +4 误报回归、`tests/test_no_slow_waits.py` +4 等待门禁）；`RAN` 3221 → 3229 即由此而来；
2. 结果：`RAN=3229`、`skipped=4`、0 failure / 0 error，全量 **42.53s**（2026-10-20 收口实测）；
3. A 组改动自身须跑一次全量验证（硬性 #8）；
4. 每处热点修复单独给出「改前 / 改后」单条耗时证据，落 plan 执行记录。

## 6 风险与回滚

| 风险 | 缓解 |
|---|---|
| A1/A2 把「真实节拍/真实超时」测没了 | 只改测试内的时间刻度与连接方式，被 patched 的代码路径仍执行；断言逐条保留 |
| A3 共享 server 与 `_swap_db` 冲突（服务端缓存配置） | 先在改前确认服务端按请求读配置；不确定则用逐条起停 + `poll_interval=0.01` 的最小改法 |
| A4 新增回归用例误伤 | 门禁用例只断言「内建名不在报告中」，不锁具体文件列表 |

## 7 开工查证与裁决

- 最新 spec：`docs/compose/spec/2026-10-19-error-guide-design.md`（错误引导主题，与测试无关，无冲突、无需取代）。
- 08 卷既有「批次内不跑全量」「L0→L1→L2」规则**继续生效**，本设计只在其上补充「预算 + 时机 + 热点治理」，不推翻任何既有条目。
- 与硬性 #8（纯文档改动不跑测试）不冲突：A4 改静态分析器属功能代码，须跑全量。
