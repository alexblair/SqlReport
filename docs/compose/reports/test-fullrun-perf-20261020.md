# 全量测试性能基线、根因与提速结果（2026-10-20）

> 关联 spec: [2026-10-20-test-performance-design.md](../spec/2026-10-20-test-performance-design.md)
> 关联 plan: [2026-10-20-test-performance-plan.md](../plan/2026-10-20-test-performance-plan.md)
> 关联知识库: [08-testing-conventions.md](../knowledge/08-testing-conventions.md)
> 产物位置：逐条计时日志落 `run-logs/`（可被清理），**结论与数值以本文为准**。

## 1 改前基线

全量入口 `python -m unittest discover -s tests/ -t .`，2026-10-20 00:35 实测：

| 项 | 数值 |
|---|---|
| 结果 | `RAN=3221 failures=0 errors=0 skipped=4` |
| 总耗时 | `RUN_SEC=362.6`（import 仅 0.5s，即几乎全是执行） |
| 单条 `tests.test_scheduler_extra.TestTickLoopExceptions.test_keepalive_exception_does_not_break_loop` | **301.09s = 全量的 83%** |
| `tests.test_preset_cases` 11 条 | 10.1s（其中 `test_import_overrides_pools_with_test_mysql` 10.02s） |
| `tests.test_site_branding` 59 条 | 7.7s（`TestFaviconServing` 15 条各 0.51s） |
| `tests.test_api_endpoint` 99 条 | 4.7s |
| `tests.test_server` 64 条 | 4.4s |
| 静态分析（150 文件） | 7.13s；**8 ERROR（全为误报）+ 6558 WARNING（全为内建名误报）**，单次全量日志被灌到 695KB |

历史会话证据（`~/.dsh/sessions/--opdev-SqlReport--/`）：

- `session-fce66c01`：2 次全量（1 次 `Ran 3204 tests in 365.334s`）。
- `session-c983c002`：2 次全量（`366.512s`、`365.096s`）≈ **12.2 分钟纯串行等待**，全落在收尾阶段。
- 即「全量次数」已被规则压到每会话 ≤2 次，痛点是每次 6 分钟的串行阻塞 + 单条用例病态等待。

## 2 根因（逐条已验证，非推测）

### 2.1 301s：等真实 300s 保活节拍

- `scheduler.py:39 _KEEPALIVE_INTERVAL_SECONDS = 300`
- `scheduler.py:621-631 _maybe_run_keepalive`：先 `self._next_keepalive_at = now + _KEEPALIVE_INTERVAL_SECONDS`，再 `return self.run_keepalive_tick(now=now)`；`scheduler.py:628 if now < self._next_keepalive_at: return 0`
- 测试 `tests/test_scheduler_extra.py:443-455` 第二次触发保活必须等满真实 300s。
- 夹具 `ReportScheduler(tick_seconds=0.01)` 被 `scheduler.py:270 self._tick_seconds = max(1, int(tick_seconds))` 钳到 1s，所以同族用例 `test_tick_exception_does_not_break_loop` 也是 2.0s。
- 验证：脚本内把模块常量临时改 0.05 后单跑 → `Ran 1 test in 2.008s OK`。

### 2.2 10s：对 9.9.9.9 发起真实 TCP 连接

- `preset_cases.py:306 "connection_timeout": 10` 写死；`preset_cases.py:310 conn = _mysql_connector.connect(**base)` 真连 `9.9.9.9:3306` 阻塞满 10s。
- venv 内装有 mysql.connector 26.7.0，走不到 `preset_cases.py:284` 的「未安装」早退分支。

### 2.3 favicon 15×0.51s：每条例行起停 HTTPServer

- `tests/test_site_branding.py` 旧 `_get_favicon()` 每条用例起 `ThreadingHTTPServer(("127.0.0.1", 0), srv.ReportHandler)`，`serve_forever()` 默认 `poll_interval=0.5`，`finally` 里 `server.shutdown()` 必须等一轮 poll → 每条 0.503–0.508s。
- 可共享依据：`server.py:771-778 _handle_favicon` 每请求调 `branding.resolve_favicon_bytes()`，`branding.py:298-317` 实时读配置，`branding.py:291 invalidate_site_branding_cache()` 在测试 `_swap_db` 里被调 → 配置不在启动时缓存。

### 2.4 静态分析 6558 条假 WARNING

- `static_analyzer.py` 旧逻辑 `self._builtins = set(dir(__builtins__))`；本仓库模块级 `__builtins__` 实测是 **dict**，`dir(dict)` 不含 `int/len/str/print/isinstance` → 所有内建名都被报「可能未定义的名称」。
- 危害不是 7s 噪声，而是**假 WARNING 淹没真 ERROR**（属「不遗漏」风险）。

## 3 改后结果

2026-10-20 00:51 实测（同一入口、同一机器）：

| 项 | 改前 | 改后 |
|---|---|---|
| 全量结果 | `RAN=3221 / 0 fail / 0 err / 4 skip` | `RAN=3229 / 0 fail / 0 err / 4 skip` |
| 全量耗时 | 362.6s | **42.53s**（−88%） |
| 保活用例（含同族 3 条） | 301.09s + 2.00s | 0.090s |
| mysql 用例 | 10.019s | 0.010s |
| favicon 15 条 | 7.581s | 0.082s |
| 静态分析 | 7.13s / 8 ERROR / 6558 WARNING | 7.5s / **0 ERROR / 0 WARNING** / 1792 INFO |

改后最慢的单条：`tests.test_b6_robustness.TestSocketTimeout.test_write_phase_decoupled_from_read_timeout` 1.01s、`tests.test_redis_cache.TestRedisConnectionManager.test_wait_for_lock_timeout` 1.00s；第 3 位是门禁自己（扫描 150 个测试文件）0.75s，其余全部 <0.6s，**无 >5s 用例**。

`RAN` 由 3221 → 3229 的 +8 全部来自新增回归/门禁用例：`tests/bug_hunt/test_static_analysis.py` +4（误报回归）、`tests/test_no_slow_waits.py` +4（等待门禁）；既有用例一条未删、无改判。

## 4 落地物

| 落点 | 作用 |
|---|---|
| `scripts/agent/test_timing.py` | 全量逐条计时 + >5s 哨兵 + 超 90s 预算告警 + 结果指纹复用（`--quick/--report/--reuse/--force`） |
| `tests/test_no_slow_waits.py` | AST 门禁：`tests/` 内 `time.sleep(>1s)`、`wait/join/acquire(timeout>30s)` 即失败，同行 `slow-wait-ok:` 豁免 |
| `tests/bug_hunt/static_analyzer.py` | builtins/全局声明/函数内导入/相对导入/作用域收窄五处修复，误报清零 |
| `tests/bug_hunt/test_static_analysis.py` | 4 条误报回归用例（内建名、真未定义、魔法名+global、相对导入） |

## 5 未达成项与后续

- 目标曾写「全量 ≤40s」，实测 42.53s，差 2.5s：静态分析 7.5s 是必要门禁（语法/导入/未定义名），不能省；`test_api_endpoint`(4.7s)+`test_server`(4.4s) 仍按用例起停 HTTPServer。预算红线按 90s 判定，当前余量充足。
- 分片并行（4 进程）明确不做：`tests/test_server.py:33 TEST_PORT = 19080`、`tests/test_health.py:19 TEST_PORT = 19081` 固定端口需独占分片，收益 15s 不值得引入非官方入口与端口脆弱性。
