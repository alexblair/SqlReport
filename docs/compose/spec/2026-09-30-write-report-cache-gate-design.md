# 写报表缓存读门槛收窄设计

> 状态: 生效
> 取代关系: 无。本设计只**收窄** `cache-write-test-scenarios.md`「场景 4b 写护栏」的**适用范围**，
> 其结论与断言保持不变（真写仍每次真实跑库、仍被 allow_write 拦截）；
> 2026-09-29 执行层性能设计的 C-3 规则不变，本设计只是让更多报表能走进该规则。

## 1. 背景：一个真实生产现象

现象（2026-09-30，8099 环境跑的是 `app_config.json` 即生产配置）：报表 35
《咸渔台向集团三权看板上报：项目使用覆盖率（百分比）》**每次翻页约 1 秒**。

诊断结论（全程只读取证，**未执行任何报表的 SQL**）：

| 环节 | 事实 | 取证方式 |
|---|---|---|
| 报表 35 SQL | 6,806 字符 / 31 条语句：7 条 `CREATE TEMPORARY TABLE` + 7 条 `DROP TEMPORARY TABLE` + 9 条 `SET @用户变量` + 8 条 `SELECT` | 只读读配置库 `report_configs` |
| 持久副作用 | **零**。31/31 条语句逐条判定为「读」或「可证明的会话级」；无 `GLOBAL`/`PERSIST`、无 DML、DDL 全部带 `TEMPORARY` | 逐语句分类（§5 规则的只读试算） |
| 判定结果 | `sql_contains_write()` → **True**（`DROP`/`CREATE`/`SET` 均在写关键词集，`query_executor.py:503`） | 只读取 SQL 后本地计算 |
| 直接后果 | `skip_cache_read` 对**每次请求**恒为 True → L1 / L2 / C-3 三条读路径全部关闭 | `report.py:1020`、`:1075`、`:1092`、`:1229` |
| 但写路径未关闭 | 每次请求仍把 1.80 MB 结果序列化并 `SETEX` 覆盖 Redis 快照 | `report.py:1181` |
| 实证 | 快照键 `webreport_:snapshot:35:10a268ec…` **存在**、1,887,247 B、TTL 86,355 s；由 TTL 反推其写入时刻恰为 `run.log` 中一次**普通** `GET /report?id=35`（11:16:51，非「重建缓存」）；Redis `maxmemory=0`、`evicted_keys=0`，排除逐出 | 只读 Redis `SCAN/STRLEN/TTL/INFO` + `run.log` |
| 代价量级 | 31 条语句顺序执行，实测到该 RDS 的 TCP RTT 中位 **10.8 ms** → 仅往返 **≥335 ms**；8 次 `CREATE TEMPORARY TABLE … SELECT` 的服务端执行为主项；返回数据仅 8 结果集 / 4,675 行 → Python transform 为个位毫秒 | 实测 RTT + 只读统计快照 |
| 附带代价 | 每次翻页 `json.dumps` 1.80 MB ≈ 12.1 ms + 一次 1.8 MB `SETEX` + 1.8 MB Python 对象写入**永不读**的 L1 | 实测真实快照 |

**未测项（诚实声明）**：服务端执行时间与往返时间的拆分无法在「不执行该脚本」的前提下测得——
执行它等于在生产 RDS 上跑 8 次 `CREATE TEMPORARY TABLE`，用户已明令禁止。精确拆分需要一份非生产副本。

一句话根因：**报表 35 是一个纯会话级脚本，却被写护栏永久剥夺了缓存读取。**

连线到既有结论：`../knowledge/07-cache-scheduler-audit.md` 的「写报表禁缓存短路（2026-09-25）」
是**有意**的安全设计，但当时没有评估「临时表脚本」这一类报表的代价。

## 2. 问题本质：一个布尔值承担两个职责

`sql_contains_write()` 同时服务两个语义不同的决策：

| 用途 | 调用点 | 需要的语义 |
|---|---|---|
| **权限 / 警示**（allow_write 契约） | `report.py:1025`、`report.py:1788`、`export.py:460`、`api_handler.py:211`、`api_handler.py:285`、`config.py:593` | **从严**：任何可能持久化的写都必须拦或警示 |
| **缓存读门槛**（跳过读会不会让真实的写不执行） | `report.py:1020` | **可从宽**：只关心「跳过读是否会导致待执行的写被短路」 |

两者的敏感度不同：报表 35 需要 `allow_write=1` 才能运行（可以保留，甚至是必要的显式确认），
但**不应该**因此永久失去缓存。现状把两者绑死，「从严」的那一票否决了缓存。

## 3. 横向审计：所有缓存消费者链路核查

用户要求确认「Redis 生效期间，API / 报表页各类二次操作（排序、翻页、搜索、筛选、自定义规则）的原始数据
都来自 Redis」这一前提在各链路是否成立。核查结论如下。

### 3.1 消费者清单

「自定义规则」= 报表页的筛选 / 排序 / 列规则面板（`render.build_current_rules_section_html`），
其数据加工与翻页、排序、搜索共用同一条 transform 链。

| # | 消费者 | 入口 | 取数是否走 `execute_report` | 是否受本次门槛影响 |
|---|---|---|---|---|
| 1 | 报表页（翻页 / 排序 / 筛选 / 搜索 / 列规则） | `report.py:1607` | ✅ | ✅ **受影响**（#17 / #19 / #35 被永久跳过） |
| 2 | 报表页「重建缓存」 | `report.py:2050`（`refresh=True`） | ✅ | ➖ 不受影响（本就要求真实重跑并刷新各层） |
| 3 | API（`/api/v1` 与 `/api/*`） | `api_handler.py:454` | ✅ | ✅ **受影响**（同一函数，同病） |
| 4 | 静态 `.json`（L3 文件） | `api_handler._handle_static_request` → miss 时 `rebuild_static_endpoint_file` | ✅（仅 miss 时） | ⚠️ **另有独立缺陷**，见 §3.3 |
| 5 | 导出 CSV / JSON | `export.py:95`（C-4 起） | ✅ | ✅ **受影响**（同一函数，同病） |
| 6 | 调度器定时任务 / 保活 | `scheduler.py:488`、`scheduler.py:651`（`force_rebuild=True`） | ✅ | ➖ 不受影响（设计即强制重建） |
| 7 | 审计页 | `audit_page`（读 `audit.db`） | ❌ | ➖ 与 Redis 缓存无关 |

**结论一（好消息）**：1 / 3 / 5 三个消费者**共用 `execute_report` 这一个实现来源**（AGENTS 硬性 #3），
因此存量缺陷是**同一处根因、同一处修复**——不存在需要各改一遍的重复实现。

**结论二**：除共用的门槛缺陷外，横向审计又发现 **2 处独立缺陷**（§3.2、§3.3），均属同一症状族
（「缓存该用的没用 / 不该用的用了」），故一并纳入本设计范围。

### 3.2 新发现 1：`WITH` 语句里的**函数名**导致纯读报表被误判为写（报表 17）

`sql_contains_write` 唯一会扫描「整条语句全部关键词」的分支是 `WITH`（`query_executor.py:585`）。
报表 17《处置商管理一览表》是**单条 `WITH … SELECT` 纯读语句**，却被判为写。根因：

```
… LENGTH(REPLACE(t.ancestors, ',', '')) …     ← REPLACE 是 MySQL 字符串函数
```

`REPLACE` 同时是写关键词（`REPLACE INTO`）又是常用字符串函数，于是 `WITH` 分支命中，
**报表 17 因此永久跳过全部缓存**——与报表 35 症状相同、根因完全不同。
同族的还有 `INSERT()` 字符串函数（`INSERT(str,pos,len,newstr)`）。

判定修法（纳入 §5）：扫描写动词时**排除函数调用**——写动词后面跟的是 `INTO` / 表名 / `TABLE`，
绝不会紧跟 `(`。因此「关键词紧跟 `(`」即函数调用，不构成语句动词。

### 3.3 新发现 2：静态 `.json` 命中时**完全不执行**，写护栏在 L3 上失效

`_handle_static_request` 的命中分支直接 `return 200, content, …`，**不调用 `execute_report`**；
其写护栏条件是 `allow_write=0 AND sql_contains_write`（`api_handler.py:210`）。
于是对 **`allow_write=1` 的写报表**，静态文件的整个 TTL 窗口内**一次都不会真实执行写**——
这正是 2026-09-25 场景 4b 要禁止的「热缓存短路写执行」，只是发生在 L3 而不是 Redis/L1。

**当前是潜伏缺陷，不是活跃事故**：唯一挂了静态端点的写判定报表是 #35
（`/api/fish/project/usagecoverage/for3rights`），而它的「写」全是会话级，短路无害。
一旦有人给 #37 这类**真持久写**报表（`TRUNCATE` + `INSERT IGNORE t_project_pm_mapping_order`）建静态端点，
就会变成「接口报成功、表其实没重建」。

修法与 §5 的新函数天然一致，但**必须是「并集」而不是替换**：保留原有权限判定，只**追加**持久写判定——
会话级报表（#35）**保留**静态缓存的快速度，真持久写报表（#37 类）**禁止**静态化、回退普通 API 链路；
而 `allow_write=0` 的报表（含「只建临时表」的脚本）**仍然**回退并 403，权限语义零变更。

⚠️ **权限旁路警告**：若把条件**替换**成只判 `sql_has_persistent_write`，则
`allow_write=0` + 会话级脚本会因新判定为 False 而直接静态化，**绕过 allow_write 拦截**——
这是一条权限旁路，**禁止**（正确写法见 §4 代码，断言见 §9.4 第 3 条）。

### 3.4 已核实**无问题**的环节（避免过度怀疑）

| 环节 | 核查结论 | 依据 |
|---|---|---|
| 各消费者是否传「精确一致」的 SQL（`is_preview` 依赖它） | ✅ 全部精确：报表页取 `report["sql_query"]`（仅 `/report/preview` 用 `sql_override`）；API 取 `report["sql_query"]`；导出取 `report_config["sql_query"]` | `report.py:1605`、`api_handler.py:455`、`export.py:497,506` |
| 导出是否真的复用缓存（C-4） | ✅ 成立，非 `report_id=None` 的直连旧路径 | `export.py:94-107` |
| 二次操作（排序 / 筛选 / 翻页 / 搜索 / 列规则）是否吃 Redis 原始数据 | ✅ 成立：L1/L2 存**全量未筛选未排序**行，transform 在其上现算 | `../knowledge/03-report-transform.md` |
| SQL 里带前导块注释是否影响关键词识别 | ✅ 不受影响（`_iter_sql_keywords` 跳过注释与字符串/反引号） | `query_executor.py:509` |

### 3.5 配置层观察（非缺陷，需确认意图）

1. **`cache_ttl_hours=0` 的含义是「永不过期」，不是「不缓存」**（表单文案 `config.py:454` 与
   `static_cache.try_read` 文档一致）。当前 **#20 / #24 / #26 / #38** 四个报表为此值：
   其 Redis 快照永不自动过期，且调度保活查询要求 `cache_ttl_hours>0`，因此也不会被预热刷新。
   如非有意（#20「字典快查表」看起来是有意的），请改 TTL。
2. **派生态 LRU 是「每报表 8 个组合」且被报表页 / API / 导出共用**：端点组合多的报表，
   API 的组合可能把报表页的组合顶掉（只影响冷启动耗时，不影响正确性）。当前无需处理，记录备查。

## 4. 方案取舍

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A | 直接收窄 `sql_contains_write` 本身 | 一处改动，缓存与权限同步 | **同时放松权限护栏**；必须改 `tests/test_sql_write_detect.py` 已锁断言（`SET @x = 1` 由 True→False）；波及 6 个调用方与全部 PH-05 测试 | ❌ 否决 |
| **B** | **新增 `sql_has_persistent_write()`，只用于缓存读门槛 + 静态护栏** | `sql_contains_write` 逐字不变 → 权限 / 警示 / 静态度**零语义变更**，现有断言**零改动**；误判后果被限制在「缓存」一层，不会新增任何未授权写 | 需维护两个判定函数（用共享助手消重） | ✅ **采纳** |
| C | 不改判定，只在写报表上关掉无效的 L2/L1 回填 | 省掉每请求 1.8 MB 序列化 | 不解决 1 秒；且会失去 MySQL 故障兜底（`report.py:1155` 的 `redis_fallback` 不受 `skip_cache_read` 约束，正依赖该快照） | ⚠️ 本设计不采纳，另议 |

方案 B 的改动点只有两处：

```python
# report.py:1020 —— 缓存读门槛
skip_cache_read = bool(force_rebuild) or sql_has_persistent_write(sql_query)

# api_handler.py:210 —— 静态护栏（保留原权限判定，仅追加持久写判定；并集，不是替换）
_sql = report.get("sql_query") or ""
if (not int(report.get("allow_write", 1) or 0) and sql_contains_write(_sql)) \
        or sql_has_persistent_write(_sql):
    return _run_normal_api_request(...)   # 真持久写 / 未授权写：都禁止静态化，回退走统一 403
```

## 5. `sql_has_persistent_write` 判定规则

**唯一铁律：只有能静态证明「无持久副作用」时才排除该语句；一切未知、无法解析、动态构造的语句一律按持久写处理。**

### 5.1 逐语句判定

对每条语句（用 `_split_sql_statements` 切分），取其首关键词 `first` 与关键词集合 `kws`：

| 条件 | 判定 |
|---|---|
| `first` ∈ {SELECT, SHOW, DESCRIBE, DESC, EXPLAIN} | 会话级（读），继续下一条 |
| `first` ∈ {CREATE, DROP} 且**次关键词**（修饰词位置）为 `TEMPORARY` | 会话级，继续下一条。⚠️ **不得用「`TEMPORARY` ∈ `kws`」**：`temporary` 是合法表名/列名，集合式判定会把 `DROP TABLE temporary`、`CREATE TABLE t (temporary INT)` 判成会话级，真实 DDL 因而被缓存读短路（复核 C-1 实证：3 次翻页只执行 1 次） |
| `first` == `SET`，且为**单 `@`** 用户变量（`@@` 系统变量、`SET GLOBAL/PERSIST/SESSION/NAMES` 一律不算） | 会话级。实现口径：从**首关键词的结束偏移**向后跳过空白与注释再取字符（不是对裸文本做正则）——实测等价且更强（额外覆盖 `SET /* c */ @x`），见 §12 第 4 条 |
| `first` == `WITH` | 扫描写动词（见 §5.2）；无命中则视为读，继续下一条 |
| 其余 | **持久写** |

⚠️ **实现陷阱 1（SET 形状判定）**：不能对**裸文本**做正则。报表 35 的 9 条
`SET @…` 全部带前导块注释（`/*** 入驻数计算 ***/`），裸文本正则 `^\s*SET\s+@`
会全部落空、把它们判成持久写、使整个修复失效。**已采用口径**：首关键词取自
`_iter_sql_keywords_with_pos`（已跳过注释与字符串），再从该关键词的**结束偏移**
用 `_skip_ws_and_comments` 跳过空白/注释后取字符——与「剥离注释后做正则」等价，
且额外覆盖 `SET /* c */ @x = 1`。

⚠️ **实现陷阱 2（复核 C-1 的教训，已修）**：`TEMPORARY` 必须判在
**修饰词位置**（`CREATE`/`DROP` 的次关键词），不能是「关键词集合里出现过」。
集合式判定把 `DROP TABLE temporary;` 判成会话级，真实 DDL 因此被缓存读短路——
正落在 §5.4 明令禁止的方向。已用
`test_temporary_named_identifiers_are_persistent` 与反向的
`test_temporary_modifier_still_session_level` 双向钉死。

### 5.2 `WITH` 语句的写动词扫描（修正 §3.2 的误判）

在 `WITH` 语句中，需要扫描的写动词集合为
{INSERT, UPDATE, DELETE, REPLACE, CREATE, DROP, ALTER, TRUNCATE, CALL, GRANT, REVOKE}（**不含 `SET`**，
`SET` 在 WITH 内只可能出现在表达式中，不是语句动词）。

- **命中条件**：出现上述关键词，且其**后面紧跟的不是 `(`**（紧跟 `(` 即函数调用，如 `REPLACE(` / `INSERT(`）
- **不命中**：`SET`；任何紧跟 `(` 的函数名
- **从严**：无法判定位置关系、或扫描失败 → 按持久写

依据：真正的写语句是 `REPLACE INTO …` / `INSERT INTO …`，动词后面跟 `INTO`，绝不会跟 `(`。

### 5.3 必须判为持久写（保持既有从严）

- `CREATE` / `ALTER` / `DROP TABLE`（不带 `TEMPORARY`）
- 任何 `INSERT` / `UPDATE` / `DELETE` / `REPLACE` / `TRUNCATE` / `CALL` / `GRANT` / `REVOKE`
- `SET GLOBAL` / `SET PERSIST` / `SET @@global.*` / `SET @@persist.*`
- `SET SESSION …`、`SET NAMES …`、`SET <系统变量>`（含 `SET autocommit=0`）——会改变会话 / 事务语义，从严
- `PREPARE` / 其余首关键词不在读白名单者
- 任何拼装、无法切分、无法取到关键词的语句

**明确不做的事（YAGNI）**：不追踪「本脚本内建的临时表名」。
`CREATE TEMPORARY TABLE t` 之后的 `INSERT INTO t` / `DROP TABLE t` 一律按持久写处理
（即该类报表继续跳过缓存＝维持现状，无正确性风险）。当前 34 个真实报表无一需要此豁免（§6），
若将来出现，再单独评估。

### 5.4 诚实边界（静态不可判定）

- 存储过程内部的副作用不可见 → `CALL` 从严（已覆盖）
- 动态 SQL → `PREPARE` / `EXECUTE` 首关键词不在白名单 → 从严（已覆盖）
- 判定是**保守近似**：允许存在「实际只动临时表却被判为持久写」的漏网（维持现状，无正确性风险）；
  **不允许**出现反方向的误放行
- 既有缺口（**非本设计引入，也不由本设计修复**）：`SELECT … INTO OUTFILE` / `INTO DUMPFILE` 首关键词是 `SELECT`，
  在 `sql_contains_write` 中一直被当作「读」。如需收紧应另立任务，勿在本设计里顺手夹带
- 订正（2026-10-05）：该缺口**已另立并落地**——见 `2026-10-05-outfile-write-detect-design.md`
  （两个判定函数均判写 + 机械门禁；判定规则见该设计 §4.1）。

## 6. 规则对全部真实报表的验证结果（只读试算）

用 §5 规则对生产配置库里**全部 34 个报表**做只读试算（临时脚本，未改产品代码）。
2026-10-05 由 `tests/manual_write_gate_regression.py` 复跑确认（34 个报表，`RESULT: PASS`）：

| 结果 | 报表 |
|---|---|
| ✅ 净解封（恢复缓存读） | **#17**（`REPLACE(` 误判）、**#19**（临时表脚本）、**#35**（临时表脚本 + `SET @`） |
| ➖ 保持拦截（**必须**，正确保留） | **#37**（`UPDATE` + `TRUNCATE` + `INSERT IGNORE t_project_pm_mapping_order`，真持久写） |
| ➖ 其余 30 个 | 判定前后一致，无变化 |
| ❌ 反向误判（读报表被判为写） | **0 个** |

这一格「反向误判 0」是本设计最重要的安全证据：**没有任何一个当前可缓存的报表会因本次改动被锁掉缓存。**

## 7. 行为变化清单

| 项 | 前 | 后 |
|---|---|---|
| #17 / #19 / #35 的读路径 | 每请求全部跳过（L1 / L2 / C-3） | 恢复：首次 `mysql` → 后续 `redis` / `process` |
| 三者的 API / 导出链路 | 同上（同一函数） | 同上（一次修复三处生效） |
| #37 及一切真持久写报表 | 跳过读 | **不变**（必须保持） |
| 静态 `.json`（`allow_write=1` 的写报表） | 命中即返回文件，写不执行 | 真持久写报表不再静态化、回退普通链路；会话级报表（#35）**保留**静态缓存 |
| 翻页耗时（#35 类） | ≈ 脚本全量执行（本案 ~1 s） | TTL 内「数十毫秒内」量级——#35 仅 4,675 行、transform 为个位毫秒，**实际值以 §9.3 夹具实测为准** |
| Redis 快照写入频次 | 每请求一次（1.8 MB） | 每次 miss / TTL 过期一次 |
| Redis 快照用途 | 仅 MySQL 故障兜底 | 正常读路径 + 故障兜底 |
| **不变（硬约束）** | — | `allow_write` 拦截与警示文案、导出 403、API 403、快照格式 `_SNAPSHOT_VERSION=2`、键构造、TTL 与 refresh-ahead 保活、SETNX 锁、`cache_info.source` 全部取值、C-3 的 LRU 上限与「`derived` 不进序列化」 |

⚠️ **唯一用户可见语义变化（2026-09-30 用户已确认接受）**：#17 / #19 / #35 的 `cache_ttl_hours`
分别为 6 / 6 / 24 小时。改造后用户看到的表数据陈旧度从「每次请求实时」变为「最多一个 TTL」。
配置项 `prefer_cache=1` / `cache_ttl_hours` 是用户自己声明的意图，现状被写护栏静默推翻；
本设计让配置重新生效。**用户决策：三个报表的 `cache_ttl_hours` 原值一律保持不变**（#17 / #19 为 6 小时、#35 为 24 小时），不调短 TTL。

## 8. 方案范围

- **在范围内**：
  1. `query_executor.py` —— 新增 `sql_has_persistent_write()`（含 §5.2 的 WITH 修正）；
     `sql_contains_write` **一行不改**
  2. `report.py:1020` —— 缓存读门槛换用新函数
  3. `api_handler.py:210` —— 静态护栏**追加**持久写判定（并集，保留原权限判定；预防性修复，当前无实际受影响端点）
- **不在范围内**：SQL 下推（2026-09-29 spec §3.1 已否决）、transform 内部实现、渲染与前端、
  Redis 快照契约、生产数据与生产环境、§3.5 的配置值调整（需用户自行在配置页操作）

## 9. 验证策略

### 9.1 判定矩阵单测（新增）
`tests/test_sql_persistent_write.py`：

- 正例（会话级）：`CREATE TEMPORARY TABLE t …`、`DROP TEMPORARY TABLE IF EXISTS t`、`SET @x=1`、
  `SET @x := (SELECT COUNT(*) FROM t)`、**带前导块注释的 `/* c */ SET @x=1`**
- 正例（读）：纯 `WITH … SELECT`、**`WITH x AS (SELECT REPLACE(a,',','') FROM t) SELECT * FROM x`**（§3.2 回归）、
  `SELECT INSERT('abc',1,1,'x')`
- 反例（必须仍为持久写）：`CREATE TABLE t`、`DROP TABLE t`、**`DROP TABLE temporary`**、
  **`CREATE TABLE temporary (id INT)`**、**`CREATE TABLE t (temporary INT)`**（复核 C-1：temporary 作标识符）、
  `SET GLOBAL`、`SET PERSIST`、
  `SET @@sql_mode=''`、`SET @@session.sql_mode=''`、`SET SESSION`、`SET NAMES`、`SET autocommit=0`、
  `UPDATE t SET…`、`WITH x AS (…) DELETE FROM t`、`CALL p()`、注释 / 字符串内关键词不误判
- **真实报表回归**：从配置库导出 #17 / #19 / #35 的 SQL 作夹具，断言
  `sql_has_persistent_write == False` 且 `sql_contains_write == True`；#37 断言两者皆 `True`

### 9.2 既有守卫（必须全绿，且**断言不得改动**）
`tests/test_sql_write_detect.py`、`tests/test_write_guard.py`、`tests/test_derived_cache.py`、
`tests/test_query_cache.py`、`tests/test_redis_cache*.py`、`tests/test_report*.py`、`tests/test_export*.py`、
`tests/test_api*.py`。

若其中任一断言需要改动，即说明方案 B 的边界没守住——应停止并回退。

### 9.3 端到端（**禁止在生产 8099 上做对照**）
复用 `scripts/perf/`：在本地 `sqlreport_test`（3307）造等价夹具——一个「临时表脚本 + 多结果集 + 排序/筛选」
报表，用 `bench.py` 取「同一脚本、同一数据、改前 vs 改后」的 P50 / P95，并断言 `cache_info.source`
序列（首次 `mysql` → 后续 `redis` / `process`）。

翻页是本次验收主场景；同时断言分页切片结果与改前**逐行一致**（防止派生态复用引入行序变化）。
另需三端一致性用例：同一报表在 **报表页 / API / 导出** 三条链路上取到的 `cache_info.source` 一致。

### 9.4 静态护栏用例（§3.3）
断言三条：
1. 会话级报表（`allow_write=1`）的静态端点仍命中文件（`X-Static-Cache: hit`）；
2. 真持久写报表（#37 类夹具）的静态端点不再静态化，改走 `execute_report` 链路且写真实执行；
3. **权限红线**：`allow_write=0` + 会话级脚本报表，静态端点仍须 403
   （不得因新判定为 False 而被静态化放行）。
4. **既有用例前置构造的调整（2026-10-05 实施中发现）**：`test_static_cache_hit_cannot_bypass_guard`
   原用 `DELETE FROM t` + `allow_write=1` 先生成静态文件；真持久写被禁静态化后该前置状态**不可达**。
   已改为用「会话级脚本」构造（`sql_contains_write` 对它仍为 True）——**三条断言一字未改**，
   `allow_write=0` 的拦截语义照旧被验到。

### 9.5 门禁自证
新增判定函数若配静态门禁，须按 AGENTS 硬性 #13 用 `tests/bug_hunt/gate_redproof.py` 做 RED-GREEN 自证。

### 9.6 Redis 契约守卫（对齐 2026-09-29 spec §6.1）
优化前后同一 SQL 的快照 JSON **逐字节一致**；`redis_fallback` 真实验证沿用
`scripts/perf/verify_redis_fallback.py`。

## 10. 知识库同步义务

| 变更 | 至少更新 |
|---|---|
| 缓存读门槛与新判定函数的分工 | `../knowledge/07-cache-scheduler-audit.md`（三层数据流中「SQL 含写?」改写为「含持久写?」，并写清静态护栏的新条件） |
| `report.py` 写护栏与派生态门禁 | `../knowledge/03-report-transform.md`（写护栏与缓存门槛的区分、C-3 启用条件） |
| 静态缓存写护栏条件变更 | `../knowledge/05-api.md` |
| 三条实现陷阱（前导注释、`REPLACE(` 函数名、**`TEMPORARY` 修饰词位置**） | `MEMORY.md` 的 Discovered（下次会话直接可用） |
| 旧场景文档的事实性补注 | `cache-write-test-scenarios.md` §行为说明第 1 条的公式补注指向本 spec（**只补注，不改其已实测结论**） |
| 新增测试入口 | `../knowledge/08-testing-conventions.md` |
| 掌握状态 | `learn/sqlreport-kb/course-state.md` |

## 11. 风险与退出条件

| 风险 | 退出条件 |
|---|---|
| 误判为会话级 → 真实的写被缓存短路（场景 4b 复现） | 任一语句无法静态证明即判持久写；一旦出现真写被短路，整段回退 |
| `WITH` 函数调用豁免被滥用成放行通道（如某函数名后真的接写语句） | 豁免仅限「关键词紧跟 `(`」；出现任何反例即整段回退 |
| 静态护栏改动引出 API 回退行为变化 | 会话级报表的静态命中行为**必须**逐字不变；真持久写报表仅从「命中文件」变为「走完整链路」 |
| 陈旧度语义变化（最长一个 TTL）事后被认为不可接受 | 已确认接受（见 §12 第 1 条）；若反悔，改相应报表 TTL 或回退整段 |
| 实施者顺手收窄权限侧 | 只允许新增函数 + 替换 §8 列出的两处调用；`sql_contains_write` 的任何改动都视为越界，回退 |

## 12. 已决策记录（2026-09-30）

1. **陈旧度**：**保留 `cache_ttl_hours` 原值不变**（#35 为 24 小时，用户决策，尊重现有配置原意）。
   代价明确：表数据最多陈旧一个 TTL，换来翻页由「脚本全量执行」降为「缓存命中」。
2. **权限侧**：**不动**。`sql_contains_write` 逐字不变，只替换 §8 的两处调用——
   于是 allow_write 拦截、页面警示条、导出 403、API 403 全部零语义变更，现有断言零改动（§9.2）。
3. **横向链路缺陷一并纳入**：用户 2026-09-30 要求「API / 报表各类二次操作链路有故障就一起写进方案」，
   故 §3.2（`WITH` 函数名误判）与 §3.3（静态命中短路写）纳入同一修复。
4. **独立复核发现 C-1 并已修复（2026-10-05）**：`TEMPORARY` 原按「关键词集合里出现过」判定，
   导致 `DROP TABLE temporary;` 等真持久写反例被判成会话级、真实 DDL 被缓存读短路
   （复核者实证：3 次翻页请求只执行 1 次）。已收紧为**次关键词（修饰词位置）**判定，
   并补双向用例。**当前 34 个真实报表上两种口径判定完全一致（爆炸半径为 0）**，
   但按 §11「真写被短路即整段回退」的红线必须修。
   同日复核另提 I-1/I-2/I-3（回归脚本补「安全方向」独立交叉复算、静态护栏两类新用例、
   `rebuild_static_endpoint_file` 的 403 正向断言）——均已落地。

---

最后更新：2026-09-30
