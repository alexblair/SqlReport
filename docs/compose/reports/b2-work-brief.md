> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# B2 工作包（P0 配置库连接池化）— 高风险批次

> 本文件是 **B2 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/spec/2026-10-10-perf-robustness-refactor-design.md` §5 B2、`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B2
> 生成：2026-10-10 · 开工基线：`Ran 3052 tests, OK (skipped=4)`（B1 后）
> **本文件放在 `docs/compose/reports/` 而非 `run-logs/`**：`run-logs/` 会被 `cleanup_tmp.py` 删除。

---

## 0. 硬约束（每个任务都适用）

1. 仓库根 `/opdev/SqlReport`，**必须** `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
   写成 `python -m unittest tests.test_x -t .` 会报 `unrecognized arguments: -t .`。
3. **只改本任务 `Files` 列出的文件**。
4. **不改变可观测行为**，除任务明确要改的。
5. 用户可感知文字一律**简体中文**（硬性 #2）。
6. **禁止**新依赖、禁 Django/Flask/React/Node（硬性 #5）。
7. **不要**跑 `codegraph sync`、**不要**动 `aoci*`、**不要** `git add`/`commit` —— Lead 批次验收后统一做。
8. **中断恢复**：只做一件事，做完立即自报；被中断不要重做。
9. 追加测试用 `edit`/`>>`，不要重写整个测试文件。

## 0.1 本批为什么是「高风险」

`docs/compose/spec/...design.md` §8 风险登记把本批列为**唯一高风险项**：
**MySQL 连接不可跨线程并发共享**。`ThreadingHTTPServer` 每请求一线程，池必须
「借出 / 归还 + 探活 + 加锁」，否则会出现跨线程串包（两个请求共用一个连接、
事务互相污染），这类 bug 在生产表现为「偶发数据错乱」，极难复现。

## 0.2 三条不可违反的契约

### 契约 1：`conn.close()` 的语义是「归还池」，不是「真关闭」
既有池化实现 `query_executor.py:314-330` 的 `_PooledConnection` 就是这么做的——
把归还藏进 `close()`，于是 `report.execute_report` 的 `finally: conn.close()`
**一行都不用改**。

> **本批要求**：`config_db.get_config_db()` 返回的连接，`close()` 也必须语义为「归还」。
> **`config_db.py`/`server.py`/`auth.py` 里既有所有 `finally: conn.close()` 调用点一律不得改动。**

### 契约 2：不得破坏测试的打桩点（late import 机制）
生产代码靠 **late import** 让测试能 patch。实测被 patch 的位置：
- `patch("db._get_engine")` —— 大量测试用它返回 `"sqlite3"` 走 SQLite 路径
- `patch("db._connect_mysql_config")` —— `tests/test_mysql_mock.py:612/636`
- `patch("db._connect_sqlite")` —— `tests/test_mysql_mock.py:624`

`config_db.get_config_db()` 现在长这样（**必须保持调用路径**）：
```python
def get_config_db():
    import db as _db
    engine = _db._get_engine()
    if engine == "mysql":
        return _db._connect_mysql_config()
    return _db._connect_sqlite()
```
> ⚠️ 引擎字面量是 **`"sqlite3"`**（不是 `"sqlite"`），默认值也是它（`config_db.py:77`）。
> 判断用 `== "mysql"` else SQLite，**不要**改成正向判断 `== "sqlite3"`。

### 契约 3：不得把 late import 提为模块级
`config_db.py ↔ db.py ↔ query_executor.py` 是本仓**唯一的真循环依赖**（spec §3.2），
靠 13 处函数内 late import 容忍。**提为模块级会直接打断 9 个模块的 import。**

---

## 1. 背景（一次性，避免重复调研）

**实测数据**（本机真实 MySQL `127.0.0.1:3307`）：
```
db.get_config_db() 连接 + SELECT 1
  5 次: [119.2, 82.2, 77.8, 70.6, 91.0] ms  中位 82.2 ms
db.get_audit_db() 连接 + COUNT  → 中位 0.6 ms（本地 SQLite，便宜）
auth.refresh_session()          → 中位 77.8 ms（内部一次 config DB 连接 + REPLACE INTO）
```

**现状**：配置库是 MySQL，但 `_connect_mysql_config()`（`query_executor.py:171-200`）
**每次调用都 `mysql.connector.connect()`**，完全绕开同文件已有的有界池
（`:238-241` `_POOL_MAX_SIZE=8` + `_pools` + `_pools_lock`）。

**后果**：每个配置库请求付一次 TCP + MySQL 认证握手。认证态页面因为
`refresh_session` 还要再来一次，合计 ~161ms 纯连接开销。

---

## 2. Task B2-1：请求内复用配置库连接

**目标**：让**同一个 HTTP 请求**内，认证阶段与 handler 阶段**共用同一个 `conn`**，
而不是各开一次。（这是最小、最先做的一步；B2-2 再做跨请求池化。）

**现状链路**（`server.py:_handle`）：
- `:393` `if route.needs_db: conn = db.get_config_db()` → 传给 handler
- `:435` `auth.refresh_session(token)` → 内部 `auth.py:211` **又** `db.get_config_db()`

**Files**
- Modify: `auth.py`（`refresh_session`，约 :201-217）
- Modify: `server.py`（`_handle` 内 `needs_db` 分支与 `refresh_session` 调用点）
- Test: 新建 `tests/test_b2_config_conn_reuse.py`

**Step 1 — 写测试**

```python
import unittest
from unittest import mock


class TestConfigConnReuse(unittest.TestCase):
    def test_refresh_session_accepts_external_conn(self):
        """refresh_session 接受外部连接时，不得自己再开一条。"""
        import auth
        opened = {"n": 0}

        def counting():
            opened["n"] += 1
            return mock.MagicMock()

        with mock.patch.object(auth.db, "get_config_db", side_effect=counting), \
             mock.patch.object(auth.db, "add_session") as add:
            tok = auth.create_session("u1")
            conn = mock.MagicMock()
            auth.refresh_session(tok, conn=conn)
        self.assertEqual(opened["n"], 0, "传了 conn 仍自开连接")
        self.assertTrue(add.called, "未落库")

    def test_refresh_session_without_conn_still_opens_one(self):
        """不传 conn 时保持旧行为（向后兼容）。"""
        import auth
        opened = {"n": 0}

        def counting():
            opened["n"] += 1
            return mock.MagicMock()

        with mock.patch.object(auth.db, "get_config_db", side_effect=counting), \
             mock.patch.object(auth.db, "add_session"):
            tok = auth.create_session("u2")
            auth.refresh_session(tok)
        self.assertEqual(opened["n"], 1)
```

**Step 2 — 跑确认失败**
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b2_config_conn_reuse.py' -t . 2>&1 | tail -3
```
Expected: FAIL —— `refresh_session() got an unexpected keyword argument 'conn'`

**Step 3 — 改 `auth.refresh_session`**（新增 `conn=None`，`None` 时自建，保持兼容）

```python
def refresh_session(token: str, conn=None) -> None:
    """刷新 session 时间戳（滑动过期）。

    conn 传入时复用调用方连接（避免同请求内重复建连）；None 时自建并负责关闭。
    """
    with _sessions_lock:
        entry = _sessions.get(token)
        if entry is None:
            return
        username, _ = entry
        now = time.time()
        _sessions[token] = (username, now)
    own = conn is None
    try:
        if own:
            conn = db.get_config_db()
        db.add_session(conn, token, username)   # REPLACE INTO 更新时间和用户名
    except Exception as e:
        logging.warning("Session 刷新失败: %s", e)
    finally:
        if own and conn is not None:
            conn.close()
```
> ⚠️ 保持既有 `except`/`logging.warning` 行为不变（原来就是吞掉并 warning）。
> ⚠️ `own and conn is not None`：防 `get_config_db()` 自身抛异常时 `conn` 未绑定。

**Step 4 — 跑确认通过**；**Step 5 — 回归**
```bash
venv/bin/python -m unittest discover -s tests -p 'test_auth*.py' -t . 2>&1 | tail -3
```

**Step 6 — `server.py` 改为传连接**（Lead 已预先分析过控制流，按下述定案做）

**已核实的控制流**（`server.py:_handle`，行号实测）：
```
_match_route(...)                        # :382
if route.needs_auth and not self._authenticate():   # :393  ← 内含 refresh_session
    return
if route.needs_db:                       # :395
    conn = db.get_config_db()            # :396
    ...handler(..., conn)... finally: conn.close()
else:
    ...handler(..., None)...
```
且 `_authenticate()` 在 `:435` 调 `auth.refresh_session(token)`。

**定案：把取连接提前到 `_authenticate()` 之前，存进 `self._req_conn`，两处共用。**
理由：
1. 验证发现 `needs_auth=True, needs_db=False` 的路由**确实存在且不能拿连接**：
   `/`（:195）、`/logout`（:196）、两个 preview（:200/:201）、`/audit`（:208）。
   所以 `refresh_session` 的 `conn=None` 自开兼容分支**必须保留**（已写在 Step 3）。
2. 对 `needs_db=True` 的路由，取连接提前**不改变任何行为**（仍然是同一条连接传给 handler，
   仍是同一个 `finally: conn.close()`），只是把它借给认证段复用。

具体改法（**只改这几行，不要动其他结构**）：
```python
# _handle 内，_match_route 之后、needs_auth 判断之前：
self._req_conn = db.get_config_db() if route.needs_db else None
if route.needs_auth and not self._authenticate():
    # 认证失败会 send_redirect 并 return —— 必须先把连接还回去，否则泄漏
    if self._req_conn is not None:
        self._req_conn.close()
        self._req_conn = None
    return
```
然后把原 `:396` 改为复用：
```python
if route.needs_db:
    conn = self._req_conn
    try:
        ...
    finally:
        conn.close()
```
`_authenticate()` 的 `:435` 改为：
```python
_auth_conn = getattr(self, "_req_conn", None)
auth.refresh_session(token, conn=_auth_conn)
```
（`_auth_conn` 为 `None` 时 `refresh_session` 自建——即上述 5 条 auth-only 路由的旧行为。）

并在 `_handle` 开头（`self._session_token = None` 附近）加 `self._req_conn = None` 复位，
防同一条 keep-alive 连接的下一个请求读到上个请求的残留。

> ⚠️ **认证失败分支的连接归还不能漏**：`_authenticate()` 返回 False 时会直接把用户
> 重定向到登录页并 `return`，此时那个已借出的连接若不 `close()` 就泄漏了。
> 这是本任务**唯一新增的泄漏面**，务必按上面代码处理。
> ⚠️ 若你发现实际控制流与上述不符（行号/结构有差异），**停下报告**，不要自行大改。

**Step 7 — 回归 + 提交前自检**
```bash
venv/bin/python -m unittest discover -s tests -p 'test_server*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_mysql_mock.py' -t . 2>&1 | tail -3
```

**完成后报告**（严格六行内）
1. 改动文件与行号
2. 新测试结果（精确 `Ran N tests, OK`）
3. `test_auth*.py` / `test_server*.py` / `test_mysql_mock.py` 回归结果
4. `server.py` 采用的是「直接传 conn」还是「self._req_conn」，为什么
5. 是否动了既有 `finally: conn.close()` 调用点（**必须是没动**）
6. 是否把任何 late import 提为模块级（**必须是没有**）

---

## 3. Task B2-2：配置库 MySQL 连接池化

> **仅在 B2-1 验收通过后开始。**
> **B2-1 实测收益（Lead 已验证）**：生产 MySQL 下，认证请求 159.7ms → **75.0ms**（中位，省掉一次完整建连）。B2-2 要在此基础上再把剩下那次也省掉。

**目标**：`_connect_mysql_config()` 走**有界池**（参照用户查询池 `query_executor.py:238-335`），
把每次 71–82ms 的 MySQL 建连降到接近 0（**跨请求**复用，不只是请求内）。

### 3.1 关键设计：包装层次（Lead 已核实，照此实现）

本仓 MySQL 有**两层包装**，别搞混：
```
mysql.connector 原生连接（raw，真正可池化的东西）
  └─ _MySQLConnection(raw)      ← query_executor.py:110，做 ?→%s 占位符转换
         └─ _PooledConnection(raw)  ← query_executor.py:314，做“归还池”语义
```
实测：`_connect_mysql_config()` 返回的是 **`_MySQLConnection`**（`:200` `return _MySQLConnection(raw)`），
且它自己的 `close()`（`:146-147`）是**真关闭** `self._conn.close()`。

**推荐实现（改动最小、不改上层语义）**：
1. 新开一个**配置库专属池**（不要与用户查询池混用：二者配置来源不同——
   一个来自 `app_config` 固定值，一个来自 `pool_config` 参数，混用会让键语义变模糊）
2. 池里存 **raw** 连接；`_connect_mysql_config()` 从池取 raw，取不到再建，
   然后返回 `_MySQLConnection(raw)`
3. 让返回的 `_MySQLConnection` 的 `close()` 变成“归还池”而非真关——
   **两种做法任选，优先第一种**：
   - **(a) 推荐**：新增一个 `_ConfigConnection(_MySQLConnection)`，只重写 `close()` 为归还+幂等，
     并在归还时探活（死连接真关）。上层拿到的仍是 `_MySQLConnection` 子类，接口不变。
   - (b) 在 `_connect_mysql_config` 里自己管理一个 `_released` 标志（比较绕，不推荐）。
4. **池满时真关闭**（防撑爆 MySQL `max_connections`）
5. 新池必须在 `clear_pools()`（`:306-312`）里一并清空，否则测试间连接泄漏

> ⚠️ **不要**直接把 `_connect_mysql_config` 改成返回 `_PooledConnection`：那会改变
> 上层拿到的类型（`_PooledConnection` 不提供 `executescript`、`_MySQLCursor` 兼容等），
> `config_db.py` 大量 CRUD 依赖 `_MySQLConnection` 的接口。

> ⚠️ **IDLE/事务残留**：归还前建议 `rollback()` 未提交的隐式事务，
> 否则下一个借出者会继承上一个的未提交事务（跨请求串包）。
> 这一条是**本任务最容易被忽略的坑**，请实现并加测试。

**Files**
- Modify: `query_executor.py`（新增专属池或复用机制）
- Test: 追加到 `tests/test_b2_config_conn_reuse.py`

**必须照抄的既有池设计要点**
| 要点 | 出处 |
|---|---|
| `_POOL_MAX_SIZE = 8`（模块常量，非配置项） | `:238` |
| `_pools: dict[tuple, list]` + `_pools_lock = threading.Lock()` | `:241-242` |
| **池键必须含所有影响连接语义的维度** | `:246-256`（`read_timeout` 在键里，注释解释为何） |
| `_is_alive()` 探活，异常一律按死处理 | `:259-265` |
| `_return_to_pool()` 满则真关闭（防泄漏撑爆） | `:276-288` |
| `_take_from_pool()` 空/全死返回 None → 调用方降级直连 | `:291-303` |
| `_PooledConnection.close()` = 归还 + 幂等 | `:314-330` |
| `clear_pools()` 测试清理入口 | `:306-312` |

**验收**
- 测试断言：连续 N 次 `get_config_db()` + `close()` 后，底层 `mysql.connector.connect`
  调用次数 **== 1**（复用生效）
- 测试断言：池满（> 8）后不泄漏（多出的被真关闭）
- 测试断言：`_is_alive` 为 False 的连接不会被复用
- **测试清理**：`BaseReportTest.setUp` 已统一 `clear_pools()`；若连接池是**新的**
  模块级池，必须在 `query_executor.clear_pools()` 里一并清理，否则跨用例泄漏

**风险与禁止**
- ❌ 不得让两个线程拿到同一条连接（借出必须从池里 pop 掉）
- ❌ 不得改 `_connect_mysql_config` 的**签名与 patch 点**（`tests/test_mysql_mock.py` 依赖它）
- ❌ 不得改动既有 `finally: conn.close()` 调用点
- ✅ `init_db` 迁移期若需独占连接，须保持既有行为

**完成后报告**：与 B2-1 同格式 + 「底层 connect 调用次数」实测数字。

---

## 4. B2 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3054` / `OK (skipped=4)`（3052 + B2 新增用例）。

然后 Lead 统一做：`codegraph sync` → 知识库更新（`01-architecture.md` 连接获取策略、
`07-cache-scheduler-audit.md` 若涉及池）→ 一次 AOCI maintain+update → git commit。

## 5. L2 实测要求（Lead 执行）

B2 的收益必须**实测复现**，不能只信单测：
```bash
venv/bin/python - <<'EOF'
import sys, time; sys.path.insert(0,'.')
import db
ts=[]
for _ in range(5):
    t=time.perf_counter()
    c=db.get_config_db(); c.execute("SELECT 1"); c.close()
    ts.append((time.perf_counter()-t)*1000)
print("get_config_db ms:", [round(x,1) for x in ts])
EOF
```
**期望**：改动后中位从 **~82ms** 降到 **< 5ms**（首次建连仍是 ~82ms，之后复用）。
若没有下降，说明池没生效，**不要提交**，回来查原因。
