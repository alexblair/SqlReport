# 缓存四场景测试用例（Redis / 数据源失效 / 写SQL+缓存更新）

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> 现状事实以 [知识库 INDEX](../knowledge/INDEX.md) 为准（本文件是 2026-09-25 的过程稿）。

> 状态：已实测通过（2026-09-25，四场景全 PASS）
> 可执行脚本：`tests/manual_cache_scenarios.py`（manual 前缀，不进 unittest discover）
> 用途：本轮策划验证 + 后续转正式单元测试的蓝本

## 环境与手法

| 要素 | 方案 |
|------|------|
| 测试 Redis | 独立实例 `redis-server --port 6390`（不触碰被 requirepass 保护的 6379）；`app_config.debug.json` 未改 |
| MySQL 替身 | 报表执行层仅支持 MySQL（`report.execute_report → db.create_mysql_connection`）。脚本把 `db.create_mysql_connection` 打补丁为 **本地 sqlite3 连接包装**（`_SqliteMysqlShim`，接口兼容 `execute_mysql_query` 所需 begin/cursor/commit/rollback/close），写 SQL 落在临时库文件，零 MySQL 风险 |
| 场景3数据源 | **debug 配置的 sqlite3**（`app_config.debug.json → config.debug.db`）只读副本；「失效」= 真实文件级故障（移走文件 / 目录占位），不注入代码异常 |
| Redis 切换 | `redis_cache.reset_redis_manager(config)`（现成测试钩子）；连接期失败=端口 6391 无人监听 |
| 隔离 | 每场景独立 `report.QueryCache`（L1 可注入）；快照 key 由 `compute_config_version(sql,pool_id)` 推导，场景间用不同 report_id |

## 场景与断言（实测结果）

### 场景1 Redis 失效时的查询 —— PASS(5)

前置：`reset_redis_manager(port=6391)` → `redis_available=False`。

| # | 步骤 | 断言 | 实测 |
|---|------|------|------|
| 1.1 | 执行查询（prefer_cache=1） | 成功返回 3 行 | rows=3 |
| 1.2 | 同上 | `cache_info.source == "mysql"`（直查数据源降级标签） | `{'source':'mysql'}` |
| 1.3 | 同上 | 数据源真实访问 1 次 | hits=1 |
| 1.4 | 二次请求（同一 L1） | `source == "process"`（L1 兜底链正常） | process |

### 场景2 Redis 有效时的查询 —— PASS(6)

前置：`reset_redis_manager(port=6390)`，删除该 rid 快照冷启动。

| # | 步骤 | 断言 | 实测 |
|---|------|------|------|
| 2.1 | 首次查询 | `source=redis, fresh=True`；数据源执行 1 次 | ✓ |
| 2.2 | 查 Redis | 快照已落盘 3 行 | ✓ |
| 2.3 | 新 L1 + 数据源封死（factory 即抛）再查 | 纯命中 L2、未触数据源、行数一致 | hits=0 未触 |

### 场景3 Redis 有效 + debug sqlite3 失效 → 正常读取 Redis —— PASS(10)+INFO(1)

前置：复制 `config.debug.db` → 临时副本；冷查 `SELECT id,name FROM report_configs`（7 行）建立热快照；移走副本文件。

| # | 步骤 | 断言 | 实测 |
|---|------|------|------|
| 3.0 | 前置 | 冷查 `source=redis`；副本可查 7 行；文件已移走 | ✓ |
| 3a | 常规请求 | 纯命中 Redis、**数据源零访问**（失效无感）、行数一致 | hits=0 |
| 3b | `force_rebuild=True`（保活语义） | 真实查询失败 → `source=redis_fallback, fresh=False`，兜底 7 行 | ✓ hits=1 |
| 3c | 连接建立期失败（同名目录占位） | **已修复**：与查询期失败同等走 `redis_fallback` 兜底 | 修复后 PASS(3) |

### 场景4 写 SQL + allow_write + Redis 缓存更新 —— PASS(9)

数据：临时 sqlite `orders` 表（id=1 pending）。写 SQL：
`UPDATE orders SET status='done' WHERE id=1; SELECT id, customer, status FROM orders WHERE id=1`
报表：`allow_write=1, prefer_cache=1`。

| # | 步骤 | 断言 | 实测 |
|---|------|------|------|
| 4a | 冷启动执行 | UPDATE 真实落库(done)；`source=redis`；**快照含写后新值**；本次返回写后结果 | snapshot_row=[1,'Alice','done'] |
| 4b | 人为还原 pending 后二次请求（热快照在） | **护栏生效**：写仍真实执行落库(done)、数据源执行 1 次、返回写后结果 | 修复后 PASS(3) |
| 4c | `refresh=True`（页面「刷新缓存」语义） | 写重新执行(done)；快照再次更新 | ✓ |
| 4d | `allow_write=0` 同写 SQL | `PermissionError` 文案与 `WRITE_DENIED_MESSAGE` 一致；库不被改动 | ✓ |

## 行为说明与已知缺口（转单测时须固化）

1. **4b 写报表护栏（2026-09-25 已加）**：`execute_report` 原来在 `prefer_cache=1`
   且快照热时被缓存短路、写 SQL 不再执行（页面显示 done 而库仍 pending）。
   修复：`skip_cache_read = force_rebuild or sql_contains_write(sql_query)`——
   含写语句的执行每次真实跑库，缓存回填路径保持生效；纯 SELECT 报表行为不变。
   转单测建议名：`test_warm_snapshot_cannot_short_circuit_write`。
   **2026-09-30 补注**：上述公式已**收窄**为 `skip_cache_read = force_rebuild or
   sql_has_persistent_write(sql_query)`——会话级语句（临时表、`SET @用户变量`）
   不再跳过缓存读。本场景（真 `UPDATE`）的结论与断言**不变**。
   详见 `2026-09-30-write-report-cache-gate-design.md`。
2. **3c 缺口（2026-09-25 已修复）**：`report.py execute_report` 内层 try 原仅包
   `execute_mysql_query`，`create_mysql_connection` 在其外；实测
   `mysql.connector.connect` 连接被拒时**立即抛** InterfaceError → 最常见
   「MySQL 宕机」不走文档承诺的过期快照兜底（docstring :1009）。修复：create
   移入内层 try、`conn=None` + finally 条件关闭；连接期与查询期失败现同等兜底
   （脚本 3c 断言已翻转并 PASS）。转单测时 3c 用例按期望兜底断言（勿再 xfail）。
3. **场景1 的 `source="mysql"` 标签**：任何直查数据源路径都标 mysql，即使底层
   实为 sqlite 替身——标签语义=「直查」非引擎名，单测勿断言引擎。

## 转正式单元测试建议

- 落点（2026-10-05 订正）：本「转正式单测」建议**未落地**；四场景实现仍在 `tests/manual_cache_scenarios.py`
  （`manual_` 前缀不被 `unittest discover` 收集，需显式运行；脚本 docstring 自述为「正式单测的蓝本」）。
  原写的 `tests/test_cache_write_scenarios.py` 不存在。
- skip 守卫（对齐 `tests/integration` 模式）：测试 Redis 6390 不可达 →
  `raise unittest.SkipTest("测试 Redis 未启动")`；`config.debug.db` 不存在 → skip。
- fixture：复制 debug 库与 orders 库到 `tempfile.mkdtemp`（进程内不删，取证友好）；
  `setUp` 打补丁 `db.create_mysql_connection`、`tearDown` 还原；
  每用例独立 `QueryCache` 与 `reset_redis_manager`。
- 用例映射：场景1→`test_s1_redis_down_degrades_to_source`；场景2→
  `test_s2_redis_hit_and_write_back`；场景3a/b→`test_s3_source_down_serves_redis*`；
  3c→`test_s3_connect_failure_fallback`（期望兜底，已修复）；
  场景4→`test_s4a_write_updates_snapshot` / `test_s4b_warm_snapshot_cannot_short_circuit_write` /
  `test_s4c_refresh_reruns_write` / `test_s4d_guard_denies_write`。

## 复跑

```bash
# 1) 测试 Redis（一次性）
redis-server --port 6390 --bind 127.0.0.1 --daemonize yes \
  --dir /tmp/sr-cache-redis --dbfilename dump.rdb
# 2) 执行
venv/bin/python tests/manual_cache_scenarios.py   # 全 PASS → exit 0
```

取证目录：脚本运行时打印的 `/tmp/sr-cache-sc-*`（只建不删）。
