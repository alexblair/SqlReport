---
module: scheduler
contract_id: MOD-SCHEDULER
version: 2.0
depends_on: [config_db, db, redis_cache, report, api_handler, app_config, audit_db]
last_reviewed_commit: 8b76e7e
last_reviewed_at: 2026-08-28
---

# scheduler.py 模块分卷

> 本分卷由覆盖率补全阶段逆向产出，内容以主仓代码真实为准。

## 1. 职责概述

`scheduler.py`（734 行，26 个 def）——**进程内报表定时调度器**。单进程 daemon 线程 + ThreadPoolExecutor 架构（不依赖外部调度库）：tick 扫描到期任务 → 线程池执行 → 结果回写。支持缓存保活（refresh-ahead）、排除规则树（AND/OR/叶子）、misfire 处理、手动触发（绕过熔断与在途检查）。

## 2. 公开 API 契约

### 2.1 ReportScheduler 类

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(tick_seconds, workers, cache=None)` | 构造调度器，`_next_keepalive_at` 初始为 0 |
| `start()` | `-> None` | 启动 daemon tick 线程（先跑启动 misfire 扫描再进入循环） |
| `shutdown(timeout=5.0)` | `-> None` | 通知停止 + 等待在途任务收尾 |
| `run_tick(now=None)` | `-> int` | 扫描到期任务并提交线程池，返回本次派发数 |
| `run_startup_scan(now=None)` | `-> dict` | 启动时处理停机期间错过的执行（返回 `{ran, skipped}`） |
| `trigger_schedule(schedule_id, session_user=None)` | `-> bool` | 手动触发（绕过熔断与在途检查，成功后 fail_count 重置） |
| `run_keepalive_tick(now=None)` | `-> int` | 扫描临近过期的保活报表并重建，返回重建数 |

### 2.2 模块级公有函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `evaluate_exclusions(tree, dt)` | `-> bool` | 判断时刻 dt 是否命中排除规则树（应静默跳过） |
| `validate_exclusions(tree)` | `-> (bool, str\|None)` | 校验排除规则树结构合法性 |
| `get_scheduler_config()` | `-> dict` | 读取全局调度配置（enable/tick_seconds/workers） |
| `compute_next_run(...)` | `-> float\|None` | 计算下次执行时刻（epoch 秒） |
| `snapshot_remaining_ttl(snapshot, ttl_hours, now)` | `-> float\|None` | 估算快照剩余有效期（秒） |
| `start_scheduler_from_config()` | `-> ReportScheduler\|None` | 按配置创建并启动（幂等） |
| `shutdown_scheduler(timeout=5.0)` | `-> None` | 停止并清理模块级单例 |
| `get_scheduler()` | `-> ReportScheduler\|None` | 返回运行中实例 |
| `trigger_manual(schedule_id, session_user=None)` | `-> bool` | 手动触发入口；全局停用时降级为临时实例同步执行 |

### 2.3 关键常量

- `MAX_FAIL_COUNT = 5`：连续失败熔断阈值
- `DEFAULT_TICK_SECONDS = 10` / `DEFAULT_WORKERS = 2`：默认参数
- `_DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]`：排除规则星期名

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

| 依赖方 | 使用的 API | 说明 |
|--------|-----------|------|
| `config_db` | `get_due_schedules`, `get_schedule`, `mark_schedule_result`, `get_schedule_reports`, `get_report`, `get_pool`, `get_api_endpoints_by_report` | 定时任务 CRUD + 执行结果回写 |
| `db` | `get_config_db()` | 每次独立连接（非连接池） |
| `redis_cache` | `redis_available`, `get_redis_manager`, `compute_config_version`, `build_snapshot_key` | 保活快照操作 |
| `report` | `execute_report` | 执行查询 + 缓存刷新 |
| `api_handler` | `rebuild_static_endpoint_file` | 重建静态 API 端点 |
| `app_config` | `get_config()` | scheduler 配置段 |
| `audit_db` | （延迟导入） | 审计日志写入 |

## 5. 内部私有函数

| 函数 | 说明 |
|------|------|
| `_parse_hm(value)` | 把 `HH:MM` 解析为当日分钟数 |
| `_leaf_hit(node, dt)` | 求单个叶子节点命中（dow/tod/date/date_range） |
| `_eval_node(node, dt)` | 递归求值 AND/OR/叶子节点树 |
| `_validate_node(node)` | 校验单个节点结构合法性 |
| `_parse_daily_time(daily_time)` | 解析 HH:MM 为 (hour, minute)；非法返回 None |
| `_tick_loop()` | daemon 线程主循环 |
| `_mark_skipped(sched, now)` | 静默窗口命中：标记 skipped + 推进 next_run_at |
| `_run_schedule(sched, trigger, session_user)` | 线程池工作函数：执行 + 回写 + 审计 |
| `_execute_schedule(sched)` | 执行报表查询主体（多报表绑定，单绑定失败不中断整包） |
| `_rebuild_static_files(conn, rpt)` | 重建报表全部启用静态缓存的 API 端点文件 |

## 6. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| 熔断机制 | `fail_count >= 5` → tick 不再自动派发，手动触发不受限，成功后重置 |
| 去重机制 | `_running` 集合 + `_running_lock`，同一 schedule_id 同时最多一个在途 |
| 连接管理 | 每个操作独立 `db.get_config_db()`，finally 块中 `conn.close()` |
| 异常安全 | `_run_schedule` 的 finally 始终释放 `_running`，防止永久去重 |
| 排除规则 | JSON 树结构（AND/OR/叶子），非法/损坏一律按"不静默"处理 |
| 全局停用降级 | `trigger_manual` 无实例时创建临时实例同步执行后立即 shutdown |
| 保活重建失败 | 单报表异常仅记 warning，不影响其他报表与主循环（B16） |
| 静态端点重建失败 | 任一端点失败不影响其他端点，也不影响保活成功状态 |

## 7. 排除规则系统

排除规则树为 JSON，存储在 `report_schedules.exclusions` 列：

- **内部节点**：`{"op": "AND"|"OR", "children": [节点...]}`（空 children 视为假）
- **叶子节点**：
  - `dow`：`{"type": "dow", "in": ["mon","tue",...]}` — 星期命中
  - `tod`：`{"type": "tod", "from": "21:00", "to": "09:00"}` — 时间段命中（支持跨午夜）
  - `date`：`{"type": "date", "on": ["2026-01-01"]}` — 具体日期命中
  - `date_range`：`{"type": "date_range", "from": "2026-01-01", "to": "2026-01-07"}` — 日期范围命中

根 OR 多规则并行、单规则可嵌套 AND/OR。非法/损坏一律按"不静默"处理。

## 8. 保鲜核对提交点

- last_reviewed_commit: 8b76e7e
- last_reviewed_at: 2026-08-28
- 后续代码改动 scheduler.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
