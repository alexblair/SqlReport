# 缓存徽标「取数来源」标注修正设计

> 状态: 生效
> 取代关系: 无。本设计**不改变任何缓存行为**（键、TTL、锁、兜底、命中判定全部冻结），
> 只修正 `cache_info.source` 的**生产者语义**，使实现符合 2026-09-29 执行层性能设计 §6.1 第 2 条的既有措辞
> （「冷请求 → `mysql`，二次请求 → `redis`」）。该 spec 的 §10 历史实测表不在本次改写范围。

## 1. 背景：一次真实的误诊

2026-09-30 排查「报表 35 每次翻页卡 1 秒」时，页面的缓存徽标显示 **`redis` 且时间新鲜**，
但实测每翻一页都在生产库上真跑那 31 条语句。徽标与事实相反，导致排查初期把方向定在
「Redis 到底有没有被读」，多花了一轮往返。

本次修复（`1f971fc`）解决了「写报表被永久剥夺缓存读」的根因，但**徽标会说谎这件事本身仍然存在**。

## 2. 缺陷的精确定义

**渲染器是无辜的；说谎的是「生产者」。**

`render.build_cache_badge_html`（`render.py:3182-3196`）的 `else` 分支对
`source == "mysql"` 已经渲染成「**实时查询**」——语义正确。问题在于 MySQL 分支
**不把 `source` 报成 `mysql`**：

| # | 位置 | 现状 | 后果 |
|---|---|---|---|
| 1 | `report.py:1197-1203`（MySQL 查询成功**且写入了快照**） | `{"source": "redis", "timestamp": _snap_ts, "fresh": True}` | 徽标显示「**缓存快照 (0s 前 · 已启用缓存 · 缓存 N 小时)**」；`build_redis_banners_html`（`render.py:2792-2802`）还会显示横幅「数据来自缓存快照（时间）」——**而这一行的数据其实刚从 MySQL 取回** |
| 2 | `report.py:1187-1190`（写 L1 条目时） | `source="redis" if _redis_written else None` | L1 条目被标成 `redis`；此后 **300s 内每次 L1 命中**都走 `report.py:1085-1090` 的 `cached.source == "redis"` 分支，徽标继续显示「缓存快照」。**「L1 本地缓存」与「L2 Redis 快照」的区分同时丢失** |
| 3 | 由此派生 | `source == "mysql"` 只在「未启用 Redis / 预览 / 无快照」时出现 | 用户在**最需要判断**的场景（prefer_cache=1 的冷请求）恰恰看不到「实时查询」 |

**同一根因的另一种表现**：`cache_info.source` 这个字段名表达的是「本次取数来源」，
但实现把它当成了「本次是否写了快照」的账本。

## 3. 目标与非目标

**目标**
1. 徽标/横幅能**一眼**回答「这一页的数据是刚查库拿的，还是从缓存拿的」；
2. 保留并**区分** `process`（L1 本地缓存）与 `redis`（L2 快照）；
3. 改动最小化：**优先只改生产者，不动渲染器**。

**非目标**
- 不改缓存行为：快照格式、键构造、TTL/refresh-ahead、SETNX 锁、`redis_fallback` 兜底全部冻结；
- 不改 `fresh` 语义（仍表示「数据是否新鲜」，兜底时为 `False`）；
- 不改 API/导出的输出契约（`cache_info` 不进入 API JSON 与快照序列化，已核实）；
- 不处理另两条遗留（`SELECT … INTO OUTFILE` 判定缺口、静态端点 403），它们各自另立。

## 4. 方案取舍

| 方案 | 做法 | 评价 |
|---|---|---|
| A | 保留 `source` 原样，**新增** `data_from` 字段，徽标改读 `data_from` | 零破坏，但留下两个含义重叠的字段，后人仍会误读 `source`；且要改渲染器 |
| **B（采纳）** | **只修生产者**：让 `source` 真正表示「本次取数来源」 | 渲染器**一行不改**（`mysql` 分支已渲染「实时查询」）；字段名与语义归一；代价是 `source` 取值在冷路径上变化，需更新少量断言（§6） |
| C | 只改渲染器（例如按 `snapshot_written` 判断文案） | 治标：`source` 继续骗人，任何其它读取方（`scripts/perf/*`）仍被误导 |

**选 B 的关键理由**：2026-09-29 spec §6.1 第 2 条**本来就写着**「冷请求 → `mysql`，二次请求 → `redis`」。
本设计是把实现修回既有契约，而不是改契约。

## 5. 设计

### 5.1 `cache_info` 的取值表（改后）

| 场景 | `source` | 其它字段 | 徽标文案 |
|---|---|---|---|
| MySQL 查询成功**且写入快照** | **`mysql`**（原为 `redis`） | `timestamp=_snap_ts`、`fresh=True`、`snapshot_written=True` | **实时查询**（· 已启用缓存 · 缓存 N 小时） |
| MySQL 查询成功、未写快照 | `mysql` | `snapshot_written=False` | 实时查询 |
| 命中 L2 Redis 快照 | `redis` | `timestamp=snapshot.updated_at`、`fresh=True` | 缓存快照 (Ns 前 …) |
| 命中 L1，且该条目数据来自 L2 | `redis` | `timestamp=source_timestamp or cached.timestamp`、`cached_at` | 缓存快照 (Ns 前 …) |
| **命中 L1，且该条目数据来自 MySQL** | **`process`**（原为 `redis`） | `timestamp=cached.timestamp` | **本地缓存 (Ns 前刷新)** |
| MySQL 失败 → 过期快照兜底 | `redis_fallback` | `timestamp`、`fresh=False` | 缓存快照（Ns 前…，数据库不可用） |

### 5.2 改动点（预计 2 处，均在 `report.py`）

1. `report.py:1197-1203`：`{"source": "redis", ...}` → `{"source": "mysql", "timestamp": _snap_ts, "fresh": True, "snapshot_written": True}`；
   并将紧随的 `else` 分支补上 `snapshot_written: False`（形状统一，便于读取方不再靠「有没有这个键」判断）。
2. `report.py:1187-1190`：L1 写入的 `source` 改为**按本次数据真实来源**取：
   该分支的数据来自 MySQL → `source=None`（L1 命中即报 `process`）。
   L2 命中分支（`report.py:1099-1103`）**保持不变**（它确实来自 Redis）。

`render.py` **不改**。`fresh`、`timestamp` 的既有读取方（徽标 TTL 过期计算、横幅）**行为不变**。

## 6. 影响面（必须同批更新的断言与文档）

已核实会被本设计改变行为、需同步更新的位置：

| 文件 | 位置 | 现状断言 | 改后 |
|---|---|---|---|
| `tests/test_report_extra.py` | `:328`、`:331-332` | **L2 命中用例**（`test_redis_snapshot_hit_skips_mysql`）：`source == "redis"`、`cached.source == "redis"`、`source_timestamp == 123.0` | **无需改动**（§8 的 L2→L1 继承链必须保持 `redis`）；真正需要改的是 `tests/test_cache_ui.py:305/312`（`refresh=True` 冷路径写 L1 条目：`source` 改 `mysql` + `snapshot_written`，L1 条目 `cached.source` 改 `None`） |
| `tests/test_report_extra.py` | `:328`、`:379`、`:447` | `source == "redis"`（grep 已确认；**是否均为冷路径待逐条核对**） | 逐条判断：冷路径 → `mysql`（`snapshot_written is True`），L2 命中则不变 |
| `tests/test_query_cache.py` | `:226`、`:262`、`:333` | `source == "redis"` | 逐条核对是「冷路径」还是「L2 命中」：前者改 `mysql`，后者不变 |
| `tests/test_scheduler_primitives.py` | `:90`、`:95` | `force_rebuild` 后 `source == "redis"` | 保活重建的数据来自 MySQL → `mysql`（`redis_fallback` 用例不变） |
| `tests/manual_cache_scenarios.py` | `:225`、`:235` | 手工脚本断言 `redis` | 同批核对（场景 2 是 L2 命中，应保持 `redis`） |
| `scripts/perf/bench.py` | `:18-19` 的期望说明 + S5 断言 | 「S5 预热与正式都必须是 `redis`」 | 改为「S5 预热 `mysql`（并写入快照）→ 正式 `process`」（正式请求 300s 内命中 L1）；`_BADGE_PATTERNS` 无需改（`mysql`↔「实时查询」、`process`↔「本地缓存」已映射） |
| `docs/compose/spec/2026-09-29-…design.md` | §6.1 第 2 条附近 | 已是「冷请求 → mysql」 | **只补注**指向本 spec（说明 S5 曾经实测为「全部 redis」是旧实现的账本式标注），**不改其历史实测数据** |

`tests/test_render.py`、`tests/test_render_extra.py`、`tests/test_cache_ui.py` 中的多数引用是
**手工构造 `cache_info` 字典**喂给渲染器，不经过生产者 → 预期**不需要改**（实施时逐条核对确认）。
`docs/compose/knowledge/07-cache-scheduler-audit.md`（三层数据流）与 `03-report-transform.md`
的 `cache_info` 说明需同步一句「`source` = 本次取数来源」。

### 6.1 实施期订正记录（2026-10-05，逐条核对得出）

1. **原 §6 首行 `:331-332` 是误判**：该两行属 `test_redis_snapshot_hit_skips_mysql`（L2 命中），按 §8「L2→L1 继承链不得断裂」必须保持 `redis`，**不改**（已在 §6 表格首行订正）。
2. **S5 正式请求应为 `process` 而非 `redis`**：`bench.py` 的 S5 预热 1 次后紧接 20 次请求，`QueryCache` 默认 `ttl=300` → 20 次全命中 L1 进程缓存，新语义下报 `process`；现状「全部 `redis`」正是旧账本式标注造成的假象（与 S1 现状「正式全 `process`」同构）。
3. **本 spec 漏列的影响点（实施时补）**：`tests/test_cache_ui.py:305/312`（`refresh=True` 冷路径写 L1）、`scripts/perf/verify_redis_fallback.py:80`（① 冷路径 → `mysql`）、`tests/manual_cache_scenarios.py:261/321`（场景 3 前置冷查 / 4a 冷启动写 → `mysql`）。
4. **已核实无需改动的读取方**：`scripts/perf/bench_session_script.py:143`（已容错 `src in ("process","redis")`）、`tests/test_report_perf.py:149`（L2 命中）、`tests/test_derived_cache.py:247`（已容错）、`tests/test_cache_ui.py:156`（手工构造 L1 条目）、`tests/test_render*.py`（手工构造 `cache_info`）。
5. 实施后的取值表与 §5.1 完全一致；`report.py` 生产者改动局限于 `execute_report` 的 MySQL 成功分支（L1 写入入参 + 两个 `cache_info` 字典）。

## 7. 验证策略

### 7.1 单测（新增，TDD）
`tests/test_cache_source_label.py`（已定：**新建独立文件**，共 9 个用例 = 6 生产者 + 3 徽标文案）：

- 冷路径（prefer_cache=1、Redis 可用、mock 数据源）→ `source == "mysql"` 且 `snapshot_written is True`；
- 紧接着的第二次请求（L1 命中）→ `source == "process"`（**回归点：不得再是 `redis`**）；
- 清 L1 只留 L2 → 命中 → `source == "redis"`；
- 数据源故障 + 快照存在 → `source == "redis_fallback"` 且 `fresh is False`；
- 未启用 Redis（`prefer_cache=0`）→ `source == "mysql"` 且 `snapshot_written is False`；
- **渲染断言**：对 `source="mysql"` 的 `cache_info`，徽标文案为「实时查询」且**不含**「缓存快照」；
  对 `source="process"` 为「本地缓存」——把「徽标不得说谎」直接钉成断言。

### 7.2 既有守卫
`tests/test_query_cache.py`、`tests/test_report_extra.py`、`tests/test_cache_ui.py`、
`tests/test_render*.py`、`tests/test_scheduler*.py`、`tests/test_redis_cache*.py` 全绿；
**改动过的断言必须在 spec 记录「为什么必须改」**（§6 已列），其余一律不得改动。

### 7.3 生产验收（沿用本次已证明有效的手法）
1. 重启 8099（清空 L1）→ 打开一个 `prefer_cache=1` 报表的**冷加载**：
   徽标应显示「**实时查询**」，**不得**再显示「缓存快照」；快照 `updated_at` 应为该时刻；
2. 在 300s 内再翻一页（L1 命中）：徽标应显示「**本地缓存**」；
3. 静置 >300s 后再翻一页（L1 过期、L2 命中）：徽标应显示「**缓存快照**」；
4. 三态可用截图或页面 HTML 取证（`bench.py:_BADGE_PATTERNS` 已有从 HTML 解析文案的实现，可直接复用）。

## 8. 风险与退出条件

| 风险 | 退出条件 |
|---|---|
| `source` 取值变化破坏外部读取方（仅仓库内 `scripts/perf/*` 与测试） | 全仓 `grep -rn cache_info` 逐一核对；出现仓库外消费者则改回方案 A（加字段不动 `source`） |
| 改 L1 条目的 `source` 影响 L1 命中标签 | L1 命中必须报 `process`；若 L2→L1 的继承链被破坏（应报 `redis` 的报成 `process`），整段回退 |
| 有人依赖“冷请求也显示缓存快照”这一旧表现 | 属本次要修的缺陷本身；若用户明确要保留，则退回方案 A |
| 误改渲染器语义 | **渲染器不改**；一旦发现需要改 `render.py`，回到本 spec 重审方案 |

## 9. 范围

- **在范围内**：`report.py`（`cache_info` 生产者 2 处）、受影响测试与其断言、`scripts/perf/bench.py`
  的期望、`docs/compose/knowledge/03`+`07`、`docs/compose/spec/2026-09-29-…design.md` 补注。
- **不在范围内**：任何缓存行为（键/TTL/锁/兜底/命中判定）、`render.py`、API/导出输出契约、
  minor ①（`INTO OUTFILE`）与 minor ③（静态端点 403）。

---

最后更新：2026-10-05
