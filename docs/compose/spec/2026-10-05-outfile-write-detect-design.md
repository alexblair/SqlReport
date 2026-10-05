# `SELECT … INTO OUTFILE` / `DUMPFILE` 写判定缺口修复设计

> 状态: 生效
> 取代关系: 无。本设计**落实**（不是推翻）`2026-09-30-write-report-cache-gate-design.md` §5.4 的明文遗留
> ——「`SELECT … INTO OUTFILE` / `DUMPFILE` 仍被判为**读**……如需收紧应另立任务，勿在本设计里顺手夹带」。
> 本次即该「另立任务」。旧 spec 的判定规则、Redis 契约、权限文案**均不在本次改写范围**；
> 旧 spec §5.4 已加一行指针回指本设计（不复制其内容）。

## 1. 背景：护栏在，但读白名单先把它短路了

`query_executor.py` 的写判定有两条通道，分工见 `2026-09-30-write-report-cache-gate-design.md` §5
与知识库 `03-report-transform.md`（此处不复述）：

| 函数 | 定位 | 服务对象 |
|---|---|---|
| `sql_contains_write`（`query_executor.py:573`） | **从严** | `allow_write` 权限拦截、表单警示、导出/API 403、静态护栏 |
| `sql_has_persistent_write`（`query_executor.py:645`） | **精确** | 缓存读门槛、静态护栏（并集的一支） |

两者的第一道判据相同：**首关键词落在读白名单 `{SELECT, SHOW, DESCRIBE, DESC, EXPLAIN}`
（`query_executor.py:500-501`）就直接放行为「读」**——`sql_contains_write:592-593`、
`sql_has_persistent_write:679-680`。

而 `_WRITE_STATEMENT_KEYWORDS`（`query_executor.py:503-504`）与 `_WITH_WRITE_VERBS`
（`query_executor.py:605-608`）两个关键词集合里**都没有 `OUTFILE` / `DUMPFILE`**；
全仓库搜索 `OUTFILE|DUMPFILE`（排除 `venv/`）：**0 处命中**。

结论：**`SELECT … INTO OUTFILE '/path'` 与 `SELECT … INTO DUMPFILE '/path'`
被两个函数一致判为「纯读」。**

### 1.1 后果（两条，均已定位到具体调用点）

1. **权限旁路**：`allow_write=0` 的报表里放这条 SQL，`sql_contains_write` 返回 `False`
   → 不进 `allow_write` 拦截与警示 → **照常执行**。写入目标是 **MySQL 服务端磁盘上的文件**
   （`FILE` 权限允许时），不是本应用目录；但这正是护栏要挡的「未授权写」。
2. **缓存短路**：`sql_has_persistent_write` 返回 `False` → 该报表被允许走缓存读
   → 与复核 C-1（`TEMPORARY` 误判）同一失效形状：**一次真实写被执行一次后被缓存顶掉**。

### 1.2 可达性评估（为什么算缺陷而不是纯理论）

- `/report($|/)` 的路由条目只要求 **`needs_auth=True`**（`server.py:223`；字段语义见
  `RouteEntry.__slots__`，`server.py:165`）——**不要求管理员**。任何登录用户都能把这条 SQL
  写进报表。
- 边界：真正落地还需该数据源所用 MySQL 账号具备 `FILE` 权限；34 个真实报表中命中 **0**。
  故定性为「**防御缺口**」，不是「线上已中招」。

## 2. 目标与非目标

**目标**

1. `SELECT … INTO OUTFILE` / `SELECT … INTO DUMPFILE` 在**两个**判定函数里都判为写；
2. 判定只依赖**关键词流**，不引入裸文本正则，避免把字符串字面量/注释里的同名词误判；
3. 不改动既有判定对其它任何 SQL 的结论（零语义漂移）；
4. 补上机械门禁，使该形状**不可能**再被改回「读」。

**非目标**

- **不动权限文案与拦截动作**：`WRITE_DENIED_MESSAGE`、`WRITE_ALLOWED_BANNER`、导出/API 403
  逐字不变（本次只是让它们对更多输入生效）；
- **不动 Redis 快照契约**：`_SNAPSHOT_VERSION`、键构造、TTL/refresh-ahead、SETNX 锁、
  `redis_fallback` 兜底全冻结；
- **不处理 `SELECT … FOR UPDATE` / `LOCK IN SHARE MODE`**：它们是加锁读，不产生持久数据变更，
  且 `FOR UPDATE` 在报表场景无真实用例（34 报表 0 命中）——按 YAGNI 明确不做，
  理由记录于此以免后人反复提出；
- **不处理 `SELECT … INTO @变量`**：会话级，无持久副作用，现有「读」判定是**正确**的，
  本次改动必须继续把它判为读（§4.3 反向用例）；
- 不改 `sql_contains_write` 的「从严」定位（例如不去掉它对写关键词的过度判定）。

## 3. 方案取舍

| 方案 | 做法 | 评价 |
|---|---|---|
| A | 把 `OUTFILE`/`DUMPFILE` 塞进 `_WRITE_STATEMENT_KEYWORDS` 与 `_WITH_WRITE_VERBS` | **无效**：首关键词是 `SELECT` 时，读白名单在**之前**就 `continue` 掉了，集合永远轮不到；且会顺带改变 `WITH` 分支的语义 |
| **B（采纳）** | 新增「**相邻关键词对**」判定 `(INTO, OUTFILE)` / `(INTO, DUMPFILE)`，在两个函数的读白名单分支**之前**生效 | 命中真实语法；只认相邻对，`INSERT INTO outfile_table`、`SELECT 'INTO OUTFILE'`、`SELECT * FROM t INTO @a` 全部不误伤 |
| C | 在裸文本上正则搜 `INTO\s+(OUTFILE\|DUMPFILE)` | 会把字符串字面量与注释里的同名文本判成写（`SELECT 'INTO OUTFILE'`），与既有「注释/字面量不产出关键词」的设计冲突 |

**选 B 的关键理由**：现有 tokenizer（`_iter_sql_keywords_with_pos`，`query_executor.py:509`）
**已经**把字符串字面量与注释排除在关键词流之外。判定挂在关键词流上，等于免费继承这份正确性；
方案 C 则要重新回答一遍「引号/转义/块注释」的问题。

## 4. 设计

### 4.1 判定规则

> 一条语句的关键词序列中，若存在**相邻**的 `INTO` 紧跟 `OUTFILE` 或 `DUMPFILE`，
> 则该语句是**持久写**（写 MySQL 服务端文件）。

实现为一个私有谓词 + 一个常量集合，插在 `sql_contains_write` / `sql_has_persistent_write`
各自的「取关键词 → 判首关键词」之间：

```python
# `SELECT … INTO OUTFILE '/p'` / `INTO DUMPFILE '/p'` 写的是 **MySQL 服务端磁盘**。
# 首关键词是 SELECT，会被读白名单直接放行 → 权限护栏与缓存门槛都会漏判。
# 只认关键词流里**相邻**的 (INTO, OUTFILE|DUMPFILE)：字符串字面量与注释已被
# `_iter_sql_keywords_with_pos` 排除，故 `SELECT 'INTO OUTFILE'` 不会被误判。
_FILE_WRITE_TARGETS = frozenset({"OUTFILE", "DUMPFILE"})


def _has_into_file_write(keywords) -> bool:
    """关键词序列中是否存在相邻的 (INTO, OUTFILE|DUMPFILE)。"""
```

### 4.2 改动点（三处，均在 `query_executor.py`）

| # | 位置 | 改动 |
|---|---|---|
| 1 | 模块级常量区（紧邻 `_WRITE_STATEMENT_KEYWORDS`） | 新增 `_FILE_WRITE_TARGETS` 与 `_has_into_file_write()` |
| 2 | `sql_contains_write:592` 读白名单分支**之前** | 命中即 `return True`（从严通道同样必须挡住） |
| 3 | `sql_has_persistent_write:679` 读白名单分支**之前** | 命中即 `return True`（持久写 → 不得走缓存读） |

放在分支**之前**（而不是只改读白名单分支内部），同时覆盖 `WITH … SELECT … INTO OUTFILE`
——首关键词是 `WITH` 时走的是 §605 的写动词扫描分支，读白名单分支根本不会执行。

### 4.3 判定矩阵（本次必须钉死的行为）

| 输入 SQL | `contains_write` | `has_persistent_write` | 说明 |
|---|---|---|---|
| `SELECT * FROM t INTO OUTFILE '/tmp/a.csv'` | True（改前 **False**） | True（改前 **False**） | 本次修复的主形状 |
| `select id from t into outfile '/tmp/a' fields terminated by ','` | True | True | 小写 + 子句尾随 |
| `SELECT * FROM t INTO DUMPFILE '/tmp/a'` | True | True | DUMPFILE 变体 |
| `SELECT * FROM t INTO /*c*/ OUTFILE '/tmp/a'` | True | True | 注释分隔：关键词流仍相邻 |
| `WITH x AS (SELECT 1) SELECT * FROM x INTO OUTFILE '/tmp/a'` | True | True | WITH 分支 |
| `SET @x := 1; SELECT * FROM t INTO OUTFILE '/tmp/a';` | True | True | 多语句：任一条持久写即整体持久写 |
| `SELECT 'INTO OUTFILE' AS s` | False | False | 字符串字面量（不产出关键词） |
| `SELECT * FROM t INTO @a, @b` | False | False | 会话级用户变量，**必须继续判读** |
| `SELECT * FROM t INTO OUTFILE_COL` | False | False | 单个标识符 ≠ 关键词 |
| `/* INTO OUTFILE '/p' */ SELECT 1` | False | False | 块注释 |
| `INSERT INTO outfile_order (id) VALUES (1)` | True | True | 表名含 outfile：本就判写，行为不变 |

## 5. 影响面

- **调用方不需要改**：`sql_contains_write` 36 处调用、`sql_has_persistent_write` 33 处调用
  （codegraph `impact` 数据）全部只消费布尔结果，本次只让**更多**输入得到 `True`，
  即「更早拦截、更少缓存」，方向安全（`sql_has_persistent_write` 的 docstring 已声明
  「从严方向永远是安全的」）。
- **唯一可感知的行为变化**：含 `INTO OUTFILE`/`DUMPFILE` 的报表从「可缓存 + 可绕过 allow_write」
  变为「不走缓存读 + allow_write=0 时被拦」。34 个真实报表命中 0，**无现存报表受影响**。
- **回归面（必须为绿且断言零改动）**：`tests/test_sql_write_detect.py`、
  `tests/test_sql_persistent_write.py`、`tests/test_write_guard.py`、
  `tests/manual_write_gate_regression.py`。

## 6. 验证策略

1. **TDD**：先在 `tests/test_sql_persistent_write.py` 追加 `TestSqlHasPersistentWriteIntoFile`
   （矩阵 §4.3 全量，含反向用例），跑出 RED；再实现；再 GREEN。
2. **双向**：每条正向形状同时断言 `sql_contains_write` 与 `sql_has_persistent_write`，
   防止只修一条通道（历史教训：C-1 只修一侧会被复核打回）。
3. **零漂移**：上述 4 个既有测试文件**一行断言都不改**，全绿即证明未误伤。
4. **真实语料**：用 `tests/manual_write_gate_regression.py`（34 报表只读回归）复核命中数仍为 0。
5. **L0 → L1 → L2**：按 AGENTS 硬性 #8，代码不再变后 L2 分段全量只跑一次。

## 7. 风险

| 风险 | 对策 |
|---|---|
| 判定过度收紧，把纯读报表误判为写（等于永久剥夺其缓存） | §4.3 反向用例钉死：`INTO @var`、字面量、`OUTFILE_COL`、注释四类必须为 `False` |
| 只改一个函数（权限侧重、缓存侧漏，或反之） | 矩阵每条正向形状**双向断言**（§6.2） |
| 后人以为「加进关键词集合就行」而回退实现 | 门禁用例的 docstring 写明方案 A 为何无效（§3），并在知识库 03 卷补一行判定要点 |
