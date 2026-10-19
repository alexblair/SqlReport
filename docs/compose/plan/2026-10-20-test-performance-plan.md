# 全量测试性能与时机优化 实施计划

> 状态: 已完成
> 对应 spec: ../spec/2026-10-20-test-performance-design.md
> 最后更新: 2026-10-20

## 任务清单

- [x] T1 A1：修 301s 用例（`tests/test_scheduler_extra.py` `TestTickLoopExceptions.test_keepalive_exception_does_not_break_loop`；验收：单跑 ≤3s 且 OK；命令：`./venv/bin/python -m unittest tests.test_scheduler_extra -v`）
- [x] T2 A4：`tests/bug_hunt/static_analyzer.py` 用 `import builtins` 取内建名；新增回归用例锁定「`int/len/str` 不被报为未定义」；验收：`static_analyzer` WARNING 计数从 6558 降到 ≤200 且 errors 不增加（实际：errors 8→0、warnings 6558→0）
- [x] T3 A2：修 10s mysql 用例（`tests/test_preset_cases.py:206`；验收：单条 ≤0.5s，断言不变）
- [x] T4 A3：favicon 提速（`tests/test_site_branding.py:176`；实际 15 条，验收：15 条合计 ≤1.5s，断言不变）
- [x] T5 B2/B3/C1：新增 `scripts/agent/test_timing.py`（`--quick` 快速门禁 / 逐条计时与 >5s WARN / 全量指纹复用）
- [x] T6 C2：新增 AST 门禁用例，禁止 tests 内真实秒级 `time.sleep` 与超长 join/wait 超时（`tests/test_no_slow_waits.py`，含同行 `slow-wait-ok:` 豁免与合成样本自证）
- [x] T7 B1/C3：更新 `docs/compose/knowledge/08-testing-conventions.md`（冻结即后台跑全量、预算 ≤90s、热点清单、指纹复用）
- [x] T8 全量验证：`./venv/bin/python scripts/agent/test_timing.py`（实际 `RAN=3229` / 0 failure / 0 error / 4 skip，总耗时 43s 级）
- [x] T9 收尾：`codegraph sync`（pendingChanges 归零）、`scripts/agent/cleanup_tmp.py --apply`、知识库与 plan 状态回填

## 验证计划

- L0（逐点）：每个热点单跑对应模块/用例，记录改前/改后单条耗时。
- L1（分段）：`tests.test_scheduler_extra`、`tests.test_preset_cases`、`tests.test_site_branding`、`tests/bug_hunt` 四段分别跑绿。
- L2（全量一次）：改完后跑一次全量，记录 `Ran N / OK / 耗时`，与基线 `RAN=3221 / 0 failure / 0 error / 4 skip / 363s` 对比。
- 用例集不遗漏：既有用例一条不减；`RAN` 由 3221 → 3229 全部来自新增门禁用例（`tests/bug_hunt/test_static_analysis.py` +4、`tests/test_no_slow_waits.py` +4）。

## 执行记录

- 2026-10-20：spec/plan 落盘；基线数据见 [reports/test-fullrun-perf-20261020.md](../reports/test-fullrun-perf-20261020.md)。
- 2026-10-20 T1：`tests.test_scheduler_extra.TestTickLoopExceptions` 由 301.09s+2.00s → `Ran 3 tests in 0.090s OK`（测试内 patch `_KEEPALIVE_INTERVAL_SECONDS=0.05` + 直接置 `_tick_seconds=0.01` 绕过 `scheduler.py:270` 的钳位）。
- 2026-10-20 T3：`test_import_overrides_pools_with_test_mysql` 10.019s → 0.010s；patch `preset_cases._mysql_connector`，原 6 条断言全留，另补 2 条建连参数断言（10.02s 真凶是 `preset_cases.py:306 connection_timeout: 10` 对 9.9.9.9 真连）。
- 2026-10-20 T4：`TestFaviconServing` 15 条 7.581s → 0.082s；类级共享 server + `poll_interval=0.01`（旧写法每条 `shutdown()` 等一轮 0.5s poll）；`self.assert*` 23→23；两模块合计 `Ran 70 tests in 0.199s OK`。
- 2026-10-20 T2：`run_all_checkers()` errors 8→0、warnings 6558→0、infos 1792，耗时约 7.5s；回归用例 `tests/bug_hunt/test_static_analysis.py` 5→9 条，`Ran 9 tests in 7.977s OK`。真阳性自检：临时文件里的 `undefined_thing` 仍被报 WARNING。
- 2026-10-20 T5：`scripts/agent/test_timing.py` 落地（`--quick/--report/--reuse/--force`）。
- 2026-10-20 T6：`tests/test_no_slow_waits.py` 4 条，`Ran 4 tests in 0.785s OK`；首次实跑发现既有 8 处 30s/10s 超时都在 `join/wait` 上（是安全网上限，会提前返回），故划线改为「sleep>1s / timeout>30s」，避免误杀正常并发用例。
- 2026-10-20 T8：首轮全量 `RAN=3225 failures=1`，失败项是 `tests.test_temp_log_policy` 抓到本任务 spec/plan 引用了具体临时产物文件名（`run-logs/timing-*.log`、`.last-full-run.json`）→ 改为引用 `docs/compose/reports/test-fullrun-perf-20261020.md` 后复跑。**该门禁两次都只报这一处文档问题，非测试逻辑缺陷。**
- 2026-10-20 T8 收口：`RAN=3229 failures=0 errors=0 skipped=4`，`SEC=43.20s`（预算 90s）；最慢单条 1.01s（`tests.test_redis_cache.TestRedisConnectionManager.test_wait_for_lock_timeout`），无 >5s 用例。
- 2026-10-20 T9：`codegraph sync` / `cleanup_tmp.py --apply` / 知识库（08 卷新增「全量的时机、预算与慢用例治理」小节，并订正第 9 条易踩坑：`IGNORE_DIRS` 实际已含 `run-logs`/`perf-logs`）已同步。
