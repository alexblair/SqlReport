> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# B6 工作包（P1 健壮性 + `page_size` 封顶 + CSV 开关）

> 本文件是 **B6 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B6、spec §5 B6 + §7.4.1
> 开工基线：`Ran 3101 tests, OK (skipped=4)`（B5 后）· 期望收尾 `Ran ≥3110`
> 事实来源：本文件所有行号由**只读侦察**（grep + AST 双重复核）得出，**可直接采信**。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. 只改本任务 `Files` 列出的文件。
4. 不改变可观测行为，除任务明确要改的（B6-7/B6-8 是**显式**的行为变化，已由用户裁决）。
5. 用户可感知文字一律简体中文（硬性 #2）。
6. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
7. 中断恢复：只做一件事；被中断不要重做。追加测试用 `edit`，不要重写整个测试文件。
8. 测试文件若需 DB 夹具：`init_test_db(conn)` + 按需内联 DDL；`make_config_db()` **不建表**。

---

## 1. Task B6-1：Redis 冷启动失败后无法自愈（**最严重**）

**Files**: `redis_cache.py`（`get_redis_manager` :402-412、`connect` :225 附近、`_health_check_loop` :239-251）
**Test**: 新建 `tests/test_b6_robustness.py`

### 已核实的缺陷
```python
399: _redis_manager: Optional[RedisConnectionManager] = None
402: def get_redis_manager():
405:     if _redis_manager is None:            # ← 只在「从未初始化」时进入
406:         config = get_redis_config()
407:         if config.get("enable", False):
408:             _redis_manager = RedisConnectionManager(config)
409:             _redis_manager.connect()      # 内部空 except → _available=False
410:             if _redis_manager.available:
411:                 _redis_manager.start_health_check()   # ← 只有初次成功才会启动
412:     return _redis_manager
```
**后果**：初次 `connect()` 失败后 `_redis_manager` 已非 None 且 `_available=False` →
后续调用**永不重进** `is None` 分支、永不重连、健康线程**从未启动** →
**Redis 在 Web 启动后恢复也不会被用上，必须重启进程**。

另：全文件 `threading.Lock()` 仅 **1** 处（`:181`，实例锁），且 `self._lock` 除定义外**无使用**。
**单例创建处（405-411）无锁**——并发首访可能创建多个 manager。

### 关键语义（不可破坏）
- `_redis_manager is None` 是「从未初始化」的唯一判据；`enable=False` 时**必须保持 None**
  （语义：Redis 未启用 ≠ 连接失败）——**不要**把 `enable=False` 也变成非 None。
- `redis_available()`（:415-418）= `mgr is not None and mgr.available`；
  「未启用」与「连不上」都返回 False，调用方靠这一条统一降级。
- `reset_redis_manager()`（:428）是**测试用**唯一另一处 `connect()` 调用点。

### Step 1 — 写测试
```python
# tests/test_b6_robustness.py
import threading
import unittest
from unittest import mock

import redis_cache


class TestRedisSelfHeal(unittest.TestCase):
    """B6-1：运行期不可用时必须能重连，而不是永久降级到重启。"""

    def setUp(self):
        redis_cache.reset_redis_manager()

    def tearDown(self):
        redis_cache.reset_redis_manager()

    def test_reconnects_when_existing_manager_unavailable(self):
        mgr = mock.MagicMock()
        mgr.available = False
        redis_cache._redis_manager = mgr
        try:
            with mock.patch.object(redis_cache, "get_redis_config",
                                   return_value={"enable": True}), \
                 mock.patch.object(redis_cache, "RedisConnectionManager",
                                   return_value=mgr) as cls:
                redis_cache.get_redis_manager()
            # 必须尝试过恢复（重连 或 start_health_check）
            self.assertTrue(cls.called or mgr.connect.called,
                            "管理器已存在但不可用时未尝试恢复连接")
        finally:
            redis_cache._redis_manager = None

    def test_disabled_redis_keeps_none(self):
        """enable=False 必须保持 _redis_manager is None（语义：未启用 ≠ 连不上）。"""
        redis_cache._redis_manager = None
        with mock.patch.object(redis_cache, "get_redis_config",
                               return_value={"enable": False}):
            self.assertIsNone(redis_cache.get_redis_manager())

    def test_singleton_creation_is_thread_safe(self):
        """并发首访不得创建多个 manager（当前无锁）。"""
        created = []
        bar = threading.Barrier(8)

        def fake_cls(cfg):
            m = mock.MagicMock()
            m.available = False
            created.append(m)
            return m

        def worker():
            bar.wait(timeout=10)
            redis_cache.get_redis_manager()

        redis_cache._redis_manager = None
        with mock.patch.object(redis_cache, "get_redis_config",
                               return_value={"enable": True}), \
             mock.patch.object(redis_cache, "RedisConnectionManager",
                               side_effect=fake_cls):
            ts = [threading.Thread(target=worker) for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=10)
        self.assertEqual(len(created), 1,
                         f"并发首访创建了 {len(created)} 个 manager（应为 1）")
        redis_cache._redis_manager = None
```

### Step 2 — 实现
- 加**模块级锁**（如 `_redis_manager_lock = threading.Lock()`），把 405-411 的
  check-then-act 改成双检锁。
- 增加**「已存在但不可用」的恢复分支**：带**退避**（记录上次尝试时间，间隔 ≥
  `_HEALTH_CHECK_INTERVAL` 一类常量，防连接风暴）。
- 恢复成功时启动健康检查。
- **保持** `enable=False → None` 与 `redis_available()` 的既有语义不变。

### Step 3 — 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_redis*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
```

### 报告（四行）
1. 改动行号 2. 新测试 + 两个回归（精确 `Ran N tests, OK`）
3. 恢复分支的退避策略 4. `enable=False` 语义是否仍为 `None`（必须：是）

---

## 2. Task B6-2：重建锁无持有者校验 + 非原子 + TTL 偏短

**Files**: `redis_cache.py`（常量 :90-93、`acquire_lock` :270-282、`release_lock` :284-291、`wait_for_lock` :293-300）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实的缺陷
```python
 90: _LOCK_TIMEOUT = 30          # TTL 30s
276:             ok = self._client.setnx(lock_key, "1")
277:             if ok:
278:                 self._client.expire(lock_key, timeout)   # ← setnx 与 expire 两次往返，非原子
289:             self._client.delete(lock_key)                # ← release 无持有者校验
```
锁值恒为 `"1"`，`release_lock(lock_key)` 直接 `delete` → **会删掉别人的锁**。
`wait_for_lock`（:293-300）以 1 秒轮询、`_LOCK_MAX_WAIT=60`，内层用默认 **30 秒** TTL。
而 `query_executor` 明确允许调度器/API 路径**不限超时**，即 >30s 的慢报表是设计预期 →
锁过期后他人获锁重建，原持有者结束时删掉**别人的锁**，互斥退化为重复全量查询。

### 关键语义（不可破坏）
- `lock_held` 语义 = **本进程实际持有锁**；只有它为 True 才 release
  （`report.py:1228-1232` 的 `finally` 里 `if _mgr and lock_key and lock_held`）。
- `wait_for_lock` **超时返回 False 时不得 release**（`report.py:1230` 注释明写）。
- `skip_cache_read` 路径（`report.py:1143`）**完全不碰锁**。
- 调用方：`report.py:1144` `acquire_lock`、`:1147` `wait_for_lock`、`:1232` `release_lock`。

### Step 1 — 写测试
```python
class TestRebuildLock(unittest.TestCase):
    """B6-2：锁必须有持有者校验与原子过期，不得误删他人锁。"""

    def _mgr(self):
        cfg = {"enable": True, "key_prefix": "sr_test"}
        return redis_cache.RedisConnectionManager(cfg)

    def test_release_does_not_delete_foreign_lock(self):
        mgr = self._mgr()
        store = {}

        class Fake:
            def set(self, k, v, nx=False, ex=None):     # 期望实现用原子 set
                if nx and k in store:
                    return None
                store[k] = v
                return True
            def get(self, k):
                return store.get(k)
            def delete(self, k):
                store.pop(k, None)
                return 1
            def setnx(self, k, v):
                if k in store:
                    return False
                store[k] = v
                return True
            def expire(self, k, t):
                return True

        mgr._client = Fake()
        self.assertTrue(mgr.acquire_lock("lock:x"))
        # 模拟锁过期后被他人获取：直接换掉值
        store["lock:x"] = "someone-else"
        mgr.release_lock("lock:x")
        self.assertIn("lock:x", store, "release 删掉了别人的锁！")

    def test_release_own_lock_removes_it(self):
        mgr = self._mgr()
        store = {}
        class Fake:
            def set(self, k, v, nx=False, ex=None):
                if nx and k in store: return None
                store[k] = v; return True
            def get(self, k): return store.get(k)
            def delete(self, k): store.pop(k, None); return 1
            def setnx(self, k, v):
                if k in store: return False
                store[k] = v; return True
            def expire(self, k, t): return True
        mgr._client = Fake()
        self.assertTrue(mgr.acquire_lock("lock:y"))
        mgr.release_lock("lock:y")
        self.assertNotIn("lock:y", store)
```
> 若实现的内部结构不同，**按实际接口调整 Fake**，但两条断言必须保留：
> 「他人锁不被删」与「自己的锁被删」。

### Step 2 — 实现
- `acquire_lock` 用**随机 token** 作锁值，并用 `set(lock_key, token, nx=True, ex=timeout)` **原子**写入。
- `release_lock` **校验 token 后才删**（Lua CAS 或 `get` 比对 + `delete`；
  如用 get/delete 两步，须在注释里说明「非严格原子，但已消除误删他人锁的主风险」）。
- `_LOCK_TIMEOUT` 需覆盖最大合法报表耗时（**取值是语义决策**，请在报告里说明你选的值与理由）。

### Step 3 — 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_redis*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
```
> ⚠️ `release_lock` 签名从 `(lock_key)` 改成带 token 会波及 `report.py:1232` 与测试。
> **可以在类内保存「本实例持有的 token 映射」**，从而不改 `report.py` 的调用形态——优先这个方案。

---

## 3. Task B6-3：`?`→`%s` 改引号感知替换

**Files**: `query_executor.py`（`_MySQLCursor.execute` :80-88 与 `_MySQLConnection.execute` :121-129）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实的缺陷
```python
 84:         mysql_sql = sql.replace("?", "%s") if params is not None else sql
125:         mysql_sql = sql.replace("?", "%s") if params is not None else sql
```
**仅这 2 处**，均为**全串逐字符替换，不跳过字符串字面量与注释**。
`WHERE memo LIKE '%?%'` 或注释里的 `?` 会被误替换 → 参数个数不匹配 / MySQL 语法错
（同一 SQL 在 SQLite 正常、MySQL 报错，双引擎分叉且难定位）。

### 已有可复用能力
`_split_sql_statements(sql)`（`query_executor.py:529` 定义，:532-545 docstring）**已有引号/注释感知扫描**：
跳过 `'...'` / `"..."` / `` `...` ``、行注释 `-- ` `# `、块注释 `/* */`，处理 `''`/反斜杠转义。

> ⚠️ **但它是「按 `;` 切分语句」的函数，会重组/丢弃空白**——**不要**直接把它的返回值当 SQL 用。
> 正确做法：**参照它的扫描逻辑**（或抽出一个「逐字符遍历、识别引号/注释区间」的小助手），
> 只把**区间之外**的 `?` 换成 `%s`，其余字符**原样保留**。

### 关键语义
- `params is not None` 是替换的唯一触发条件（`params=None` 时**原样传递**）。
- 注意 `params` 为空元组时 `params is not None` 仍为 True（既有行为，不要改）。

### Step 1 — 写测试（必须先 RED）
至少覆盖：
- `"WHERE m LIKE '%?%' AND a=?"` → 结果 `"...LIKE '%?%' AND a=%s"`
- 双引号内 `?` 不动；反引号内 `?` 不动
- `-- 注释含 ?` 行注释内不动；`/* ? */` 块注释内不动
- 多个占位符全部替换；无 `params` 时**完全不替换**
- `?` 在字符串字面量里且该字面量含转义引号（`'it''s ?'`）时不动

### Step 2 — 实现（新增小助手，改那 2 处调用）
### Step 3 — 回归（**重点**：这是全仓 CRUD 的兼容层注入点）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_mysql_mock.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_deep_edge_cases.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_db*.py' -t . 2>&1 | tail -3
```

---

## 4. Task B6-4：HTTP socket 超时（**风险中高，须 L2 实测**）

**Files**: `server.py`（`ReportHandler` :321-；服务构造 :1012/:1014/:1025）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实现状
- `class ReportHandler(http.server.BaseHTTPRequestHandler)` 定义于 `:321`，
  类体内**无 `timeout` 类属性**、**无 `setup()` 重写**（全文件唯一 `setup` 是 `:910 setup_logging()`）。
- `server.py` 全文**无** `import socket`、无 `daemon_threads`、无 `setdefaulttimeout`。
- 服务构造：`:1014` `http.server.ThreadingHTTPServer((HOST, PORT), ReportHandler)`；`:1025` 端口冲突重试处同样构造。

### 风险
`timeout` 作用于**整个请求 socket（含响应写）** → 大导出/全量 API 在慢链路上可能被**截断**。
**必须先 L2 实测**：起服务 → 触发一个大导出 → 确认未被截断，再定值。

### Step 1 — 写测试
```python
class TestSocketTimeout(unittest.TestCase):
    def test_handler_has_timeout(self):
        import server
        self.assertIsNotNone(getattr(server.ReportHandler, "timeout", None),
                             "ReportHandler 未设 timeout，慢连接可无限占线程")
```
### Step 2 — 实现
取值须**覆盖最大合法导出耗时**。若无法兼顾，改为重写 `setup()` **只对读阶段设超时**。
**在报告里明确给出你选的秒数与依据。**
### Step 3 — L2 实测（必做）
起服务跑一个真实大导出，确认响应完整（可用 `/export?id=N` + `curl` 或既有 e2e 脚本）。
### Step 4 — 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_server*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_export*.py' -t . 2>&1 | tail -3
```

---

## 5. Task B6-5：静态资产失败静默降级 + `render.py` 无 logging

**Files**: `render.py`（新增 `import logging` 与 logger；`_get_common_asset_urls` :2287-2303）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实现状
```python
2287: def _get_common_asset_urls() -> tuple[str, str]:
2294:     global _COMMON_ASSET_URLS
2296:     if _COMMON_ASSET_URLS is None:            # 双检锁（_COMMON_ASSET_LOCK @2245）
2297:         with _COMMON_ASSET_LOCK:
2300:                 except Exception:             # ← 裸捕获，无日志
2301:                     urls = None
2302:                 _COMMON_ASSET_URLS = urls or ("", "")   # ← 失败被永久缓存，无重试
```
- **`render.py` 全文未 import logging**（import 段 :15-30，`grep -c logging render.py` = **0**）。
- 失败后果：`("", "")` 是「内联回退」哨兵 → 每页内联 **`_COMMON_CSS` 79531 字符 + `_COMMON_JS` 21397 字符 ≈ 100KB**。
- 内联点：CSS → `:2489-2493`（页面头）、`:5913-5917`（审计页）；JS → `_render_common_footer()` :2312-2319。
- `_COMMON_ASSET_URLS is None` 才是「未初始化」；`("", "")` 是**约定哨兵**。

### Step 1 — 写测试
```python
class TestRenderLogging(unittest.TestCase):
    def test_render_module_has_logger(self):
        import render
        self.assertTrue(hasattr(render, "logger"), "render.py 未引入 logging")

    def test_asset_failure_is_logged(self):
        from unittest import mock
        import render
        render.reset_common_assets_cache()
        with mock.patch.object(render, "ensure_common_assets",
                               side_effect=OSError("read-only")), \
             mock.patch.object(render.logger, "exception") as log, \
             mock.patch.object(render, "_COMMON_ASSET_URLS", None):
            render.reset_common_assets_cache()
            render._get_common_asset_urls()
        self.assertTrue(log.called, "资产失败未留痕")
        render.reset_common_assets_cache()
```
### Step 2 — 实现
`render.py` 顶部加 `import logging` 与 `logger = logging.getLogger(__name__)`；
`:2300` 的 `except Exception` 改为 `logger.exception("公共资产写入失败，回退内联")`。
> ⚠️ **不要**在模块级调 `logging.basicConfig`（`setup_logging` 之前 `render` 就可能被 import）。
> ⚠️ `("", "")` 哨兵语义与**返回值形状**不得改（3 处调用点依赖）。

### Step 3 — 回归（UI 静态断言面）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_render*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_ui_tokens.py' -t . 2>&1 | tail -3
```

---

## 6. Task B6-6：`static_cache._last_invalidated` 加锁（**优先级最低**）

**Files**: `static_cache.py`（:37-38、`record_invalidated` :243-248、`get_last_invalidated` :251-253）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实现状
```python
 37: _MAX_LAST_INVALIDATED = 512
 38: _last_invalidated: OrderedDict[str, float] = OrderedDict()
243: def record_invalidated(url_path: str) -> None:
245:     _last_invalidated[url_path] = time.time()
246:     _last_invalidated.move_to_end(url_path)
247:     if len(_last_invalidated) > _MAX_LAST_INVALIDATED:
248:         _last_invalidated.popitem(last=False)
```
- `static_cache.py` **未 import threading**（import 段 :23-32 无 threading）。
- **重要**：该表**仅用于 `meta.last_invalidated_at` 展示，不参与命中判定** → 数据竞争影响面**很小**（可能丢一条展示记录）。
- 生产调用点各 1 个：写 `api_handler.py:301`、读 `api_handler.py:302`。

> ⚠️ 多个测试**直接操作内部结构**并断言 `len()`/`assertIn`：
> `tests/test_static_cache.py:552/555`、`tests/test_scheduler_primitives.py:218/260/264` 等。
> **不得改数据结构**（保持 `OrderedDict`），只加锁。

### Step 1 — 写测试
```python
class TestStaticCacheLock(unittest.TestCase):
    def test_module_has_lock(self):
        import static_cache
        self.assertTrue(hasattr(static_cache, "_last_invalidated_lock"))

    def test_concurrent_record_keeps_bound(self):
        import threading, static_cache
        def w(i):
            for j in range(200):
                static_cache.record_invalidated(f"/p/{i}-{j}")
        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertLessEqual(len(static_cache._last_invalidated),
                             static_cache._MAX_LAST_INVALIDATED)
```
### Step 2 — 实现
`import threading` + `_last_invalidated_lock = threading.Lock()`；
`record_invalidated` 的读改写三步与 `get_last_invalidated` 的读都进锁。
**保持 `OrderedDict` 与 `_MAX_LAST_INVALIDATED` 不变。**

---

## 7. Task B6-7：UI `page_size` 封顶 1000 ⚠️ **两个入口都要改**

**Files**: `report.py`（**两处**解析点 + 新增常量与夹紧函数）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实的全部出现点
| 位置 | 函数 | 写法 |
|---|---|---|
| `report.py:2213-2217` | `handle_request`（GET query） | `page_size = max(1, parsed_page_size)` ← **入口①** |
| `report.py:2071-2073` | `_handle_refresh_cache`（POST form，经 `:2198` 调用） | `page_size = max(1, parsed_page_size)` ← **入口②** |
| `report.py:1031` | `execute_report` | `page_size = max(page_size if page_size is not None else 20, 1)` ← **禁止在此夹紧** |
| `report.py:1612-1613` | `render_report_page` | `if page_size is None or page_size < 1: page_size = report["default_page_size"]` ← **禁止在此夹紧** |
- 全仓**无** `MAX_UI_PAGE_SIZE` / `MAX_PAGE` 常量（需新增）。
- **内部大 `page_size` 消费者（禁止影响）**：`export.py:97`（`_EXPORT_ALL_ROWS_PAGE_SIZE = 2**31-1`）、
  `api_handler.py:452`（`_FETCH_ALL_PAGE_SIZE = 10**9`）、`scheduler.py`（保活/定时任务）。
- UI 下拉值域：`render.py:3447-3448` **硬编码 `[10, 20, 50, 100, 200]`**（无「全部」档）。
- API 翻页是**独立路径**（`api_handler._apply_get_overrides`）+ 受端点 `row_limit` 约束 → **不适用**本上限。

### 用户裁决（不要重新问）
`page_size` **仅指 UI 报表页翻页的「每页显示多少条」**，上限 **1000**；
**不适用于** API 翻页上限；**不动**报表配置的「允许全部输出」与 API `fetch_all`。

### Step 1 — 写测试
```python
class TestUiPageSizeCap(unittest.TestCase):
    def test_cap_constant_is_1000(self):
        import report
        self.assertEqual(report.MAX_UI_PAGE_SIZE, 1000)

    def test_clamp_helper(self):
        import report
        self.assertEqual(report._clamp_ui_page_size(10_000_000_000), 1000)
        self.assertEqual(report._clamp_ui_page_size(1000), 1000)
        self.assertEqual(report._clamp_ui_page_size(200), 200)
        self.assertEqual(report._clamp_ui_page_size(1), 1)
        self.assertEqual(report._clamp_ui_page_size(0), 1)

    def test_both_ui_entry_points_are_clamped(self):
        """⚠️ 两个入口都要夹：只改一处等于没封顶。"""
        import inspect, report
        for fn_name in ("handle_request", "_handle_refresh_cache"):
            src = inspect.getsource(getattr(report, fn_name))
            self.assertIn("_clamp_ui_page_size", src,
                          f"{fn_name} 未夹紧 page_size（可绕过封顶）")

    def test_execute_report_not_clamped(self):
        """关键安全断言：内部调用方靠大 page_size 取全量，绝不能在此夹。"""
        import inspect, report
        self.assertNotIn("MAX_UI_PAGE_SIZE", inspect.getsource(report.execute_report))
```

### Step 2 — 实现
```python
# report.py 模块级
MAX_UI_PAGE_SIZE = 1000
# 仅用于 UI 输入夹紧；不适用于导出全量、API 翻页、报表配置的「允许全部输出」

def _clamp_ui_page_size(value: int) -> int:
    return max(1, min(int(value), MAX_UI_PAGE_SIZE))
```
把**两个入口**的 `page_size = max(1, parsed_page_size)` 改为
`page_size = _clamp_ui_page_size(parsed_page_size)`。

> ⚠️ 超上限时**建议在页面给出提示**（复用 `_filter_warning_flash` 一类机制）而非静默截断——
> 若实现成本高，至少在报告里说明当前是静默夹紧。

### Step 3 — 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_export*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_output_limit.py' -t . 2>&1 | tail -3
```

---

## 8. Task B6-8：导出 CSV 公式中和（**默认关闭 + 导出页勾选**）

**Files**: `export.py`（`rows_to_csv` :140-161、`handle_export` :370-372/参数解析）、
`render.py`（`build_export_modal_html` :3475，字段区 :3507-3542）
**Test**: 追加到 `tests/test_b6_robustness.py`

### 已核实的现状
```python
140: def rows_to_csv(header, rows, *, bom=True, quoting=csv.QUOTE_ALL,
141:                 encoding="utf-8", lineterminator="\n"):
160:     writer = csv.writer(output, delimiter=",", quotechar='"',
161:                         quoting=quoting, lineterminator=lineterminator)
```
- 默认 `QUOTE_ALL`；**无任何公式中和**。
- 生产调用点：`export.py:208-209`（`export_report_to_csv`）。
- 该函数是**导出 / API / 审计页三处共用**（docstring :143）——注意影响面。
- 导出对话框：`render.py:3475` `build_export_modal_html(...)`，
  现有字段（:3507-3542）：`format`(csv/json radio)、`zip`(checkbox)、`charset`(gbk 默认/utf8 radio)、
  `smart_quotes`(隐藏+3 checkbox)、`use_custom_cols`(checkbox)。
- 参数解析：`handle_export` 内 `:391` `parse_qs`；`format` :437-440、`charset` :442-445、
  `json_no_quotes` :453-455、`zip` :457-459、`smart_quotes` :491-500（**仅 JSON 分支**）。

### 用户裁决（不要重新问）
**默认关闭**；在**导出对话框加一个勾选项**由用户主动启用 → **默认输出字节完全不变**。

### Step 1 — 写测试
```python
class TestCsvFormulaSanitize(unittest.TestCase):
    def test_default_output_byte_identical(self):
        """默认（不勾选）时字节必须与现状完全一致。"""
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False)
        self.assertEqual(out, '"a"\n"=1+1"\n')

    def test_sanitize_prefixes_dangerous_leads(self):
        import export
        for v in ("=1+1", "+3", "-2", "@SUM(A1)"):
            self.assertTrue(export.sanitize_csv_formula(v).startswith("'"),
                            f"{v!r} 未被中和")

    def test_sanitize_leaves_normal_values(self):
        import export
        self.assertEqual(export.sanitize_csv_formula("正常文本"), "正常文本")
        self.assertEqual(export.sanitize_csv_formula("123"), "123")

    def test_opt_in_changes_bytes(self):
        import export
        out = export.rows_to_csv(["a"], [("=1+1",)], bom=False, sanitize_formula=True)
        self.assertIn("'=1+1", out)
```

### Step 2 — 实现
```python
_DANGEROUS_LEADS = ("=", "+", "-", "@", "\t", "\r")

def sanitize_csv_formula(value) -> str:
    """为以公式引导符开头的单元格加前缀 '，使 Excel/WPS 不当公式执行。"""
    s = value if isinstance(value, str) else str(value)
    return ("'" + s) if s[:1] in _DANGEROUS_LEADS else s
```
`rows_to_csv` 加 **`sanitize_formula: bool = False`**（默认 False → 字节不变）；
导出对话框新增 checkbox（**默认不勾**），`handle_export` 解析该参数并传入。
> ⚠️ 截断注释行在 `export.py:210-212` 于 `rows_to_csv` **返回后**追加——
> 中和若做在 writer 层要避免影响该行（它在函数外，天然不受影响）。

### Step 3 — 回归（默认路径字节不变，旧断言应仍绿）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b6_robustness.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_export*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_api*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_audit*.py' -t . 2>&1 | tail -3
```

---

## 9. B6 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3110` / `OK (skipped=4)`（3101 + B6 新增）。

> **注意**：全量套件有**低概率 flaky**（B5 期间 6 次中 1 次失败，重跑即绿）。
> 遇到失败先**重跑**；仍失败再用 `git stash` 对照定位，不要直接判定为 B6 引入。

### 顺序建议
B6-5（最小、独立）→ B6-6（最小）→ B6-7（用户裁决项，两个入口）→ B6-3（兼容层，回归面大）
→ B6-8（开关式）→ B6-1（最重要）→ B6-2（锁语义，需判断）→ B6-4（风险最高，须 L2）
