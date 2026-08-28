---
module: redis_cache
contract_id: MOD-REDIS_CACHE
version: 1.0
depends_on: [app_config]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28
---

# redis_cache.py 模块分卷

> 本分卷由 T-005 逆向产出，内容以主仓还原后代码真实为准（FR-010）。

## 1. 职责概述

`redis_cache.py`（432 行，33 个 def）——**Redis 缓存层**。提供 Redis 连接管理（懒初始化单例）、后台健康检查守护线程、报表快照读写（JSON 序列化，Decimal 保真往返）、快照分布式锁（SETNX）、旧格式快照自动淘汰。Redis 不可用时降级为"缓存失效"透明穿透，不阻断业务。

## 2. 公开 API 契约

### 2.1 数据类

- `class ReportSnapshot(results, sql_query, updated_at, config_version, truncated=False)`：快照实体（`__slots__` 优化）。`to_json()` → JSON 字符串；`@classmethod from_json(data)` → ReportSnapshot（兼容旧格式缺省 truncated=False）。

### 2.2 全局单例管理

- `get_redis_manager()` → Optional[RedisConnectionManager]：获取全局 Redis 连接管理器（懒初始化）。
- `redis_available()` → bool：Redis 是否可用。
- `reset_redis_manager(config=None)`：重置全局实例（测试用）。

### 2.3 Key 构建

- `compute_config_version(sql_query, pool_id)` → str：报表配置版本号（MD5 of sql + pool_id）。
- `build_snapshot_key(prefix, report_id, config_version)` → str：快照 Redis key。
- `build_lock_key(prefix, report_id, config_version)` → str：重建锁 Redis key。

### 2.4 RedisConnectionManager

- `__init__(config)`：保存配置，创建锁和状态变量。
- `key_prefix`（property）：Redis 键前缀（默认 `"sr"`）。
- `available`（property）：连接是否健康。
- `client`（property）：底层 Redis 客户端。
- `connect()` → bool：建立连接 + ping 检测。
- `start_health_check()`：启动后台健康检查守护线程（15s 轮询）。
- `stop_health_check()`：停止健康检查。
- `acquire_lock(lock_key, timeout=30)` → bool：获取分布式锁（SETNX + EX）。
- `release_lock(lock_key)`：释放锁。
- `wait_for_lock(lock_key, max_wait=60)` → bool：轮询等待锁释放。
- `get_snapshot(key)` → Optional[ReportSnapshot]：读取快照（旧格式自动淘汰）。
- `set_snapshot(key, snapshot, ttl_hours=0)`：写入快照（ttl_hours=0 永不过期）。
- `delete_snapshot(key)`：删除快照。
- `scan_snapshots(prefix, report_id)` → list[str]：SCAN 匹配某报表全部快照 key。
- `set_expiration(key, ttl_hours)`：设置过期（0=PERSIST）。
- `close()`：停止健康检查 + 关闭连接。

### 2.5 序列化工具（内部共享）

- `_snapshot_default(obj)`：JSON default 钩子（Decimal 标记包装）。
- `_snapshot_hook(obj)`：JSON object_hook 钩子（还原 Decimal 标记）。
- `_snapshot_to_json(snapshot)` → str：Decimal 保真序列化。
- `_snapshot_is_stale(data)` → bool：旧格式判定（无 snapshot_version → v1 淘汰）。
- `_snapshot_from_json(data)` → dict：解析快照 JSON（还原 Decimal 标记）。
- `_md5_hex(content)` → str：MD5 十六进制摘要（供版本计算）。

## 3. 数据流

```
调用方（scheduler/report）→ get_redis_manager()（懒初始化）
  → RedisConnectionManager.connect()（首次 ping 检测）
  → 后台 health_check_thread 每 15s ping

快照读取: get_snapshot(key) → Redis GET → _snapshot_from_json → ReportSnapshot（v2）
                              ↓ 旧格式（v1 无 snapshot_version）
                             delete_snapshot + 返回 None

快照写入: set_snapshot(key, snapshot) → _snapshot_to_json → Redis SET

分布式锁: acquire_lock → SETNX + EX（30s 过期）/ release_lock → DEL / wait_for_lock → 轮询

Redis 不可用时: connect() 返回 False → available=False → get_snapshot 返回 None → 业务透明穿透
```

## 4. 依赖关系

AST import 实测：`app_config`（延迟导入 `get_redis_config`）。
- `app_config`：获取 Redis 配置段（host/port/password/key_prefix/db/ssl）。
- 运行时可选依赖：`redis`（`import redis` 在 `_create_client` 中按需导入，未安装抛 `RuntimeError`）。
- 被调用方：scheduler（快照读写 + 分布式锁）、report（缓存命中/回写）、server（连接管理）。

## 5. 边界与异常

- Redis 不可用透明降级：connect() 返回 False，get_snapshot 返回 None，业务按"缓存失效"处理。
- 旧格式淘汰：`_snapshot_is_stale` 检测 v1 快照（无 snapshot_version）→ 自动删除。
- Decimal 保真：JSON 序列化用 `__sr_decimal__` 标记包装，反序列化还原。
- 锁超时：`_LOCK_TIMEOUT=30s` 自动释放，`_LOCK_MAX_WAIT=60s` 等待上限。
- 健康检查：后台守护线程 15s 间隔 ping，失败标记 available=False。

## 6. 保鲜核对提交点

- last_reviewed_commit: b690f8d（T-004 后主仓 HEAD）
- last_reviewed_at: 2026-08-28
- 后续代码改动 redis_cache.py 时，须同步更新本分卷并更新 last_reviewed_commit/at（FR-005）。
