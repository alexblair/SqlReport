---
module: scheduler
contract_id: MOD-SCHEDULER
version: 1.0
depends_on: [config_db, db, redis_cache, report, api_handler, app_config, audit_db]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# scheduler.py 模块分卷

> 本分卷由 T-005 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`scheduler.py`（734 行，26 个 def）——**进程内报表定时调度器**。单进程 daemon 线程 + ThreadPoolExecutor 架构（不依赖外部调度库）：tick 扫描到期任务 → 线程池执行 → 结果回写。支持缓存保活（refresh-ahead）、排除规则树（AND/OR/叶子）、misfire 处理、手动触发（绕过熔断与在途检查）。

## 2. 公开 API 契约

### 2.1 ReportScheduler 类

- `__init__(tick_seconds=DEFAULT_TICK_SECONDS, workers=DEFAULT_WORKERS, cache=None)`：构造调度器。
- `start()` → None：启动 daemon tick 线程（先跑启动 misfire 扫描再进入循环）。
- `shutdown(timeout=5.0)` → None：通知停止 + 等待在途任务收尾。
- `run_tick(now=None)` → int：扫描到期任务并提交线程池，返回本次派发数。
- `run_startup_scan(now=None)` → dict：启动时处理停机期间错过的执行（返回 `{ran, skipped}`）。
- `trigger_schedule(schedule_id, session_user=None)` → bool：手动触发（绕过熔断与在途检查，成功后 fail_count 重置）。
- `run_keepalive_tick(now=None)` → int：扫描临近过期的保活报表并重建，返回重建数。

### 2.2 模块级公有函数

- `evaluate_exclusions(tree, dt)` → bool：判断时刻 dt 是否命中排除规则树（应静默跳过）。
- `validate_exclusions(tree)` → (bool, str|None)：校验排除规则树结构合法性。
- `get_scheduler_config()` → dict：读取全局调度配置（enable/tick_seconds/workers）。
- `compute_next_run(schedule_type, interval_minutes, daily_time, now, last_run_at=None)` → float|None：计算下次执行时刻（epoch 秒）。
- `snapshot_remaining_ttl(snapshot, ttl_hours, now)` → float|None：估算快照剩余有效期（秒）。
- `start_scheduler_from_config()` → ReportScheduler|None：按配置创建并启动（幂等）。
- `shutdown_scheduler(timeout=5.0)` → None：停止并清理模块级单例。
- `get_scheduler()` → ReportScheduler|None：返回运行中实例。
- `trigger_manual(schedule_id, session_user=None)` → bool：手动触发入口（B6/B21）；全局停用时降级为临时实例同步执行。

### 2.3 关键常量

- `MAX_FAIL_COUNT = 5`：连续失败熔断阈值。
- `DEFAULT_TICK_SECONDS = 10` / `DEFAULT_WORKERS = 2`：默认参数。

## 3. 数据流

```
启动: server.main → start_scheduler_from_config()
  → get_scheduler_config()（enable=false → 不启动）
  → ReportScheduler.start() → daemon thread → _tick_loop()
     ├─ [一次性] run_startup_scan() → 补跑停机期间错过
     └─ [循环] 每 tick_seconds: run_tick() + run_keepalive_tick()

tick 扫描: run_tick(now)
  → db.get_config_db() → config_db.get_due_schedules(conn, now)
  → 遍历到期任务: _running 去重 → evaluate_exclusions() 命中 → _mark_skipped()
                → 未命中 → _executor.submit(_run_schedule)

单任务执行: _run_schedule(sched, trigger, session_user)
  → _execute_schedule(sched)
     → config_db.get_schedule_reports() → 按 order_index 遍历绑定报表
     → report_mod.execute_report(id, sql, pool, force_rebuild=True)
  → config_db.mark_schedule_result()（回写 status/error/next_run_at/last_run_at/last_duration_ms）
  → audit_enabled → 写 scheduler 审计日志

缓存保活: run_keepalive_tick(now)
  → SQL 查询 keepalive_enabled=1 且 prefer_cache=1 的报表
  → 快照剩余 TTL < ahead_seconds → execute_report(force_rebuild=True) 重建
  → _rebuild_static_files() 重建关联静态 API 端点文件（B15）

手动触发: trigger_manual(schedule_id, session_user)
  → 有实例 → inst.trigger_schedule()
  → 无实例（全局停用）→ 临时 ReportScheduler(workers=1) → trigger_schedule() → shutdown()
```

## 4. 依赖关系

AST import 实测：`config_db, db, redis_cache, report, api_handler, app_config`（+ 延迟导入 `audit_db`）。
- `config_db`：`get_due_schedules`/`get_schedule`/`mark_schedule_result`/`get_schedule_reports`/`get_report`/`get_pool`/`get_api_endpoints_by_report`。
- `db`：`get_config_db()`（每次独立连接）。
- `redis_cache`：`redis_available`/`get_redis_manager`/`compute_config_version`/`build_snapshot_key`（快照操作）。
- `report`（别名 `report_mod`）：`execute_report`（执行查询 + 缓存刷新）。
- `api_handler`：`rebuild_static_endpoint_file`（重建静态 API 端点）。
- `app_config`：`get_config`（scheduler 配置段）。
- `audit_db`（延迟导入）：审计日志写入。

## 5. 边界与异常

- 熔断机制：`fail_count >= 5` → tick 不再自动派发，手动触发不受限，成功后重置。
- 去重机制：`_running` 集合 + `_running_lock`，同一 schedule_id 同时最多一个在途。
- 连接管理：每个操作独立 `db.get_config_db()`，finally 块中 `conn.close()`。
- 异常安全：`_run_schedule` 的 finally 始终释放 `_running`，防止永久去重。
- 排除规则：JSON 树结构（AND/OR/叶子），非法/损坏一律按"不静默"处理。
- 全局停用降级：`trigger_manual` 无实例时创建临时实例同步执行后立即 shutdown。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 scheduler.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
