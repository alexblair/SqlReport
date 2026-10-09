# 缓存 · 定时任务 · 审计

## L1 进程缓存（`report.QueryCache`）

- 键约 `(report_id, sql_query)`；TTL ~300s  
- 存全量多结果集；内存分页/筛选在此之上  
- `force_rebuild` 跳过读；截断策略经 `_cache_matches_limit_policy`

## L2 Redis（`redis_cache`）

| 概念 | 说明 |
|------|------|
| `ReportSnapshot` + `_SNAPSHOT_VERSION=2` | JSON 快照；Decimal 标记；v1 淘汰 |
| `compute_config_version(sql, pool_id)` | 进键；改 SQL/pool 自然 miss |
| `build_snapshot_key` / `build_lock_key` | `{prefix}:snapshot:{rid}:{ver}` / lock |
| `RedisConnectionManager` | 连接 + 15s 健康检查 + SETNX 锁；单例创建有锁（双检锁），不可用时按 `_HEALTH_CHECK_INTERVAL` 退避自动重连 |
| 保活 | 剩余 TTL < ahead → `force_rebuild` **先算后换** |

配置：`redis.enable` 默认关；`key_prefix` `sr`；`default_ttl_hours`。  
`redis_available()` False → 上层**静默降级**，不当异常。
`enable=False` 时 `get_redis_manager()` **必须返回 `None`**（未启用 ≠ 连不上）；运行期不可用会按退避自愈，不需重启（B6-1）。

## L3 静态 API 缓存（`static_cache`）

见 `05-api.md`。`enable` 默认 true；`try_read` 校验版本+TTL(mtime)；`write_versioned_file` 无 meta 模板端点；`invalidate` 删稳定+全部 v*；`record_invalidated` 仅展示不参与命中（`_last_invalidated` 有界 512，读写均持 `_last_invalidated_lock` —— B6-6）。

## 定时任务（`scheduler`）

- **进程内 daemon 线程** + `ThreadPoolExecutor`；无外部调度器  
- `get_scheduler_config`：`enable` 默认 false、`tick_seconds=10`、`workers=2`  
- 生命周期：`start_scheduler_from_config` / `shutdown_scheduler` / `get_scheduler` / `trigger_manual`  
- 任务=DB 行：`upsert_schedule` + `schedule_reports`；管理页 `/config/scheduler`  
- 类型：interval / daily（`compute_next_run`）  
- **排除规则**（静默窗口）：叶子 `dow/tod/date/date_range`，`AND/OR` + **`children`**（大写 op，**≠ nested_filter 的 conditions**）  
- `evaluate_exclusions`：解析失败 → **False + warning（按不排除执行）**  
- 多报表按 `order_index`；单绑定失败不中断整包  
- 熔断：`fail_count≥5` 自动停派发；手动触发不受限且成功重置  
- misfire：启动扫描 interval 合并 / daily skip|run_once  
- 执行：`execute_report(..., force_rebuild=True)`；成功回写 Redis+L1  
- 保活 tick：剩余 TTL < ahead → rebuild + 联动 `rebuild_static_endpoint_file`；**按独立节拍 `_KEEPALIVE_INTERVAL_SECONDS=300` 跑**（曾随 tick_seconds=30 每轮全量扫，`_next_keepalive_at` 是死字段；B4-1 修）；连接必须 try/finally 包住（曾无外壳，SELECT 抛异常即泄漏）
- 审计：`log_type=scheduler`；任务级开关默认关  
- **任务永久停摆**（曾：`_run_schedule` 的取连接在 `try:` **之外**，抛异常时 `finally` 不执行 → `sid` 永留 `_running` → 每轮 `run_tick` 都 `continue` 跳过且无告警；B4-2 修，取连接移入 try + `conn=None` 判空关闭）  
- worker **自建配置库连接**  
- 页面 `refresh_cache`：主动失效 L1/Redis/该报表静态 API（与保活先算后换不同）

## 审计（`audit_db` + `audit_page`）

| API | 说明 |
|-----|------|
| `record_operation` | 业务统一入口；空 user 跳过；失败 warning |
| `insert_audit_log` | 底层插入 |
| `query/count/export_audit_logs` | 筛选分页导出 |
| `rotate/delete_audit_logs` | 轮转/条件删除 |
| `get_recent_schedule_events` | 调度最近事件 |

类型：`operation | web_access | api | scheduler`（见 02 卷）。  
keyword 共用 `parse_filter_expr`。  
路径：`app_config.audit_db.path` 默认 `audit.db`；`retention_days` 0=永久。  
页面入口：`audit_page.handle_audit_request`（每次先轮转；POST clean；GET export=csv / 分页）。

## 三层数据流

```
/report 或 /api 或 /export
  → execute_report
      force_rebuild 或 含持久写? 跳过读（写报表禁缓存短路，2026-09-25）
        ├ 门槛用 sql_has_persistent_write（精确）：会话级语句（CREATE/DROP
        │  **次关键词为 TEMPORARY** 的临时表、SET @用户变量）与 CTE 内
        │  REPLACE()/INSERT() 函数调用
        │  不算持久写 → 可放行缓存读（2026-09-30）
        └ 权限侧另用 sql_contains_write（从严）：allow_write 拦截/警示、导出与
           API 403、静态护栏**并集**（2026-10-05 追加禁静态化）
      → L1 QueryCache + 截断策略
      → L2 prefer_cache && redis_available → get_snapshot(config_version)
      → miss → 锁 → MySQL（连接期或查询期失败 → 过期快照兜底
        redis_fallback，fresh=False；兜底也失败才抛）
        → set_snapshot + L1（L1 条目不标来源：数据来自 MySQL → source=None，命中报 process）
      → L1 条目上的派生态 memo（C-3，2026-09-29）：按
        (filters, sorts, nested_filter) 缓存「已筛选已排序的全量行列表」，
        分页切片不缓存。与 L1 同生共死，不是新的一层
  → `cache_info.source` = **本次取数来源**（2026-10-05 起）：
      `mysql` 本次真查库（`snapshot_written` 标是否同时写了 L2 快照）|
      `process` 命中 L1（条目数据来自 MySQL）|
      `redis` 命中 L2 快照，或 L1 条目继承自 L2 |
      `redis_fallback` 查库失败 → 过期快照兜底（`fresh=False`）
      （徽标文案由 render.build_cache_badge_html 映射：实时查询 / 本地缓存 / 缓存快照）

scheduler tick → force_rebuild 预热 L2 + 静态 .json
```

**导出（`/export`）自 2026-09-29（C-4）起并入上述链路**——改前它自带连接直查
MySQL、完全绕过三层缓存，10 万行导出 1519.7ms；并入后 359.2ms。
详见 `03-report-transform.md`。

**派生态缓存（C-3）不属于三层中的任何一层**，它是挂在 L1 `CachedResult` 上的
请求级 memo，只在 `not skip_cache_read` 时启用（写报表与 force_rebuild 都
不复用），LRU 上限 8 组合/报表。详见 `03-report-transform.md`。

## 易踩坑

1. 三层 TTL 语义不同（秒 / 小时 / mtime+版本）  
2. 保活 vs 页面 refresh 行为不同  
3. 排除树损坏 → 按不排除跑（可能执行）  
4. 删除报表要清调度绑定（FK 不可靠）  
5. 审计失败不阻断业务——「没日志」先看 warning  

---
最后核对：explore-2/3 报告
