# 交接：性能/健壮性/架构分批重构（B1–B4 已完成，B5–B9 待做）

> **给下一个会话的 Lead。** 本文件是唯一交接依据，读完即可续做。
> 写于 2026-10-10，因 `session_cost.py --check` 报「步数=543 ctx=555k → 必须落盘交接并换会话」。

---

## 1. 当前状态（可直接采信，已实测）

| 项 | 值 |
|---|---|
| **分支/最新提交** | `8cefb13 chore(aoci): B4 批次认知同步` |
| **全量测试** | `Ran 3083 tests, OK (skipped=4)`（约 360s） |
| **工作区** | 干净（仅 1 个收工前既存的 `AGENTS.md.backup.*` 未跟踪文件） |
| **codegraph** | `Index is up to date` |
| **AOCI** | `guide complete=true, next_action=none`（B4 时点） |
| **已完成批次** | **B1 ✅ B2 ✅ B3 ✅ B4 ✅ B5 ✅ B6 ✅ B7 ✅ B8 ✅ B9 ✅（全部 9 批次）** |
| **待做批次** | **无 —— 目标已达成** |

> **全部 9 个批次已完成**（收尾全量 `Ran 3180 tests, OK (skipped=4)`，起点 3042）。
> **B9-2 已完成**（`Ran 3180`，提交 `60fbebe`）：`config.py` 2968 → 981 行，拆出 `config_pages/`
> 7 个实体模块（共搬出 70/89 个函数）；`config.` 命名空间 **139/139 无缺失**（含 6 个 import 副产物）。
> **B9-1 已完成**（`Ran 3175`，`c6179a4`）：`render.py` 七个常量（1887 行）外移 `ui_assets.py`，字节不变。
> 后续若继续维护：`config_pages/` 子模块靠调用期 `import config` 取共享助手，**再导出块不得删**。

> **B8 已完成**（`Ran 3172`，提交 `3c1e3af`）：A 组 5 项纯删除（含 `_COMMON_CSS` 字节不变证明、
> 畸形 SVG `rx.5`、死函数 `_get_forwarded_url`）+ B 组 3 项行为修正（GBK `lstrip`、
> `is_debug_mode` 缓存、路由单次扫描）。
> **B8-6 随后补做**（`Ran 3185`，提交 `9e52ad3`）：熔断阈值改由 `config_db.MAX_FAIL_COUNT` 驱动，
> 3 处 SQL 全部参数化（原为写死的 `fail_count<5`）→ 消除「改常量不生效」的假 BUG。
> 另发现 `run_startup_scan` 与 `get_due_schedules` 是同一查询的两份实现，已合并。
> **B7 已完成 4/4**（`Ran 3167`，`d82ff73`）：删被遮蔽 48 行、`_escape` 收口、分类树全角缩进（D4）、`transform_rows` 收口。
> B6 已完成 8/8（`Ran 3146`）：`b0ebd8d` / `a3886ed` / `1680dc3` / `0937b96`。

> **B5 已完成**（`Ran 3101`）。摘要见 §3.1；B5-4（派生态拆级）按 plan 标为可选/风险中，已跳过。

### 提交历史（每个批次 = 1 个 fix 提交 + 1 个 aoci 提交）
```
8cefb13 chore(aoci): B4 批次认知同步
72666dd fix(B4): 调度器保活独立节拍 + 两处 try/finally 缺陷
51a4363 chore(aoci): B3 批次认知同步
ae24548 fix(B3): ZIP 导出路径穿越（CWE-22）
f881bd2 perf(B2): 配置库连接池化 + 请求内复用，并修复 _is_alive 探活语义错误
689b5bc fix(B1): 修复 4 类用户可见缺陷（含 1 项数据安全）
```

---

## 2. 必读依据（按顺序，**不要**重读全量 plan/spec）

1. `docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` —— **只读批次索引表**（第 43-51 行左右）+ 目标批次那一节
2. `docs/compose/spec/2026-10-10-perf-robustness-refactor-design.md` —— 只在需要机制依据时读 §3（分批策略）、§7（裁决）、§8（风险）
3. 各批次工作包：`docs/compose/reports/bN-work-brief.md`

---

## 3. 已完成批次摘要

### B1 用户可见缺陷（Ran 3052）
- 登录失败页 `{next_field}` 泄漏（`server.py`）
- `report.py`/`config.py` 三处横幅漏 `f` 前缀（页面显示 `{_icon(...)}` 文字）
- **删除/禁用确认框 JS 转义（数据安全）**：`_escape` 产出 `&#x27;` 被浏览器解码回 `'` → `confirm()` 语法错 → **确认框静默失效、表单直接提交**。修法：调用点传原文，`build_delete_form_html` 内 `_escape(_js_str(raw))`。**含第 8 处**（API 端点禁用按钮，独立拼串，原计划漏了）
- 测试：`tests/test_b1_p0_quickfix.py`（10 例）

### B2 配置库连接池化（Ran 3072）**收益最大**
- **B2-1 请求内复用**：`_handle` 把连接提到 `_authenticate()` 前存 `self._req_conn`，`auth.refresh_session(token, conn=...)` 复用。实测认证请求 **159.7ms → 75.0ms**
- **B2-2 配置库池**：新增 `_config_pool` + `_ConfigConnection(_MySQLConnection)`（仅重写 `close()` 为归还+幂等），归还前 `rollback()`。实测 **120ms → 0.86~1.31ms（92~140×）**
- **顺带修复既有重大 bug**：`_is_alive()` 写成 `bool(raw.ping(...))`，而 mysql-connector 的 `ping()` **成功返回 None** → 真实 MySQL 下**所有连接被判死**、池恒空。**既有用户查询池一直受害**。改为「ping 不抛即活」
- 测试：`tests/test_b2_config_conn_reuse.py`（20 例）；`tests/test_mysql_pool.py` 两例改为 `ping.side_effect=异常`

### B3 ZIP 路径穿越（Ran 3077）
- `_create_temp_zip` 把用户可控报表名当磁盘落点名 → `/export?zip=1` 可写到 tmpdir 外（**实测真能写出**）
- 修法（方案 C）：落盘用常量 `payload<ext>`/`payload.zip`，`arcname` 传原名 → **安全消除且 ZIP 条目名逐字节不变**
- 测试：`tests/test_b3_export_zip_safety.py`（5 例）

### B4 调度器（Ran 3083）
- **B4-1**：`_next_keepalive_at` 是死字段 → 保活每 30s 全量扫；`run_keepalive_tick` 连接**无 try/finally**。修：`_maybe_run_keepalive` + `_KEEPALIVE_INTERVAL_SECONDS=300` + try/finally 外壳（内部逻辑 AST 比对确认未改）
- **B4-2**：`_run_schedule` 的取连接在 `try:` **之外** → 抛异常时 `finally` 不执行 → `sid` 永留 `_running` → **任务永久静默停摆**。修：移入 try + `conn=None` 判空
- 测试：`tests/test_b4_scheduler_safety.py`（6 例）

### B5 性能（Ran 3101）
- **B5-1 筛选合并 alternation**（`result_transform._compile_alternation`）：原「每单元格逐个 `any(rx.search(...))`」改为单条 `(?:s1)|(?:s2)`。实测 100k 行：单值 85.2→36.9ms、三值 148.8→38.2ms（**3.9×**），结果逐元素一致。**禁止**改用 `lower() in`（Unicode 折叠语义差异）
- **B5-2 侧栏调度徽标改 `COUNT(*)`**（`config_db.count_schedules`）：原 N+1。实测 `_nav_badges` 总 SQL **8→5** 条。用 `config_db.count_schedules` 而非 `db.*`（`db.py` 是显式白名单再导出）
- **B5-3 `get_reports_by_category` 去 N+1**：一次 `get_all_reports` + Python 分组。实测 3 分类时 SQL 由 2+C 降为**常量 2**。⚠️ 必须用 `get_all_reports`——`get_reports(conn)` 的 `category_id` 默认 `None` 只查未分类报表
- **B5-4 派生态拆两级：跳过**（plan 标为可选/风险中）
- 测试：`tests/test_b5_perf.py`（18 例，含 9 个等价性护栏先行 + 200 轮随机差分）

---

## 4. 续做流程（必须照此执行，用户已明确要求）

1. **严格串行**：一次只跑一个任务，**禁止并发 subagent**（用户明确：并发 API 请求会被拦截导致无意义重试）
2. **每任务用 `subagent`（`run_in_background: false`）**，只给该任务的工作包章节
3. **每个任务独立复核**（不要采信子代理自报）：
   - 跑该任务的验收测试 + 全量核对
   - `git diff --stat` 看改动面是否符合预期
   - 必要时做**对照实验**（`git stash` 前后对比失败数）——B2-2 就是靠这个发现「72 个无关测试失败」
4. **批次收尾统一同步**（用户要求不要过频）：`codegraph sync` → 知识库 → AOCI → commit
5. **上下文保护**：工作包外置到 `docs/compose/reports/`；子代理只读工作包，禁止读全量 plan/spec

### 测试命令（**关键坑**）
`-t .` **只能跟 `discover`**：
```bash
# ✅ 正确
venv/bin/python -m unittest discover -s tests -p 'test_xxx.py' -t . 2>&1 | tail -3
# ❌ 报 unrecognized arguments: -t .
venv/bin/python -m unittest tests.test_xxx -t .
```

### AOCI 收尾三步（每批一次）
```bash
.tools/bin/aoci scope acknowledge --reviewed-by lead-agent --json   # 新增/改动测试文件后需先确认
# 然后 MCP: aoci_maintain → aoci_update_entry（整批，保留 candidate_id/code_batch_id/source_sha256）
.tools/bin/aoci verify --json && .tools/bin/aoci check --json && .tools/bin/aoci index agent guide --agent lead --json
```
- `aoci_remove_entry` 对 Volumes v1 **必须**用 `code:<path>` 形式
- **字段配额**（写条目时注意，否则返工）：`F≤160`、`R≤360`、`A≤400` 且 **≤6 项**、`S` 按档位限 token（C3-1≤50 runes / C5-7≤80 tokens / C8≤140 / C9≤200）
- 工作包 `.md` 的 E 档位常被判错配（长文件应为 M/L），属警告不阻断

---

## 5. 剩余批次（按依赖顺序）

| 批次 | 主题 | 写域 | 依赖 | 关键内容 |
|---|---|---|---|---|
| ~~B5~~ | ~~P1 性能~~ | — | — | ✅ **已完成**（Ran 3101）；写域实为 `config_db.py` `result_transform.py` `config.py`；B5-4 已跳过 |
| ~~B6~~ | ~~P1 健壮性 + page_size 封顶 + CSV 开关~~ | — | — | ✅ **已完成 8/8**（Ran 3146） |
| **B7** | P1 语义收口 | `config.py` `render.py` `export.py` `report.py` `result_transform.py` | B5 B6 | ① `_escape` 两份语义不同 ② 分类树缩进（**D4 已定：全角 U+3000**，改 `config.py:1181`）③ `transform_rows` 收口 ④ `report.py` 45 行被遮蔽重复定义 |
| **B8** | P2 死代码清理 | 多文件 | B7 | 12 项（`db.py` 漏转出、隐藏参数抄 3 遍、`MAX_FAIL_COUNT` 死常量、`is_debug_mode` 每次重读、`_ICONS` 畸形 SVG 等） |
| **B9** | P3 结构拆分 | 新增 `ui_assets.py` 等 | B8 | `render.py` 7 个大常量外移（1887 行→`ui_assets.py`）；`config.py` 按 8 实体拆分（**必须保留 re-export**，19 个测试文件引用 `config.`） |

### 已有裁决（不要重新问用户）
- **D1 = 池化**（B2 已落地）
- **D2 = session 落库节流**（B2 未做节流，只做了复用——`auth.refresh_session` 仍每次落库；若要做见 plan B2-2）
- **D3 = 方案 C**（B3 已落地）
- **D4 = 全角 U+3000**（B7 执行）
- **D5-a 跳过**（审计 IP 不改）、**D5-b 默认关 + 导出页勾选**（B6-8）、**D5-c `page_size` 封顶 1000 仅 UI 层**（B6-7）

---

## 6. 踩过的坑（避免重复）

| 坑 | 教训 |
|---|---|
| `python -m unittest tests.x -t .` | `-t .` 只能跟 `discover` |
| 工作包放 `run-logs/` | 会被 `cleanup_tmp.py` 删（B1 的 brief 就这样丢了）；改放 `docs/compose/reports/` |
| 测试文件里 `mock.patch` 写在**线程内** | 线程结束前 patch 不拆除 → `mysql.connector.connect` 全局残留 MagicMock → **之后所有用例拿到假连接（曾致 72 个无关测试失败）**。patch 必须提到线程外 |
| 测试用 `ping.return_value = False` 表达"死" | 编码了错误语义（真实驱动存活时返回 None）。应用 `ping.side_effect = 异常` |
| 凭命名推测函数签名 | B4 的 brief 把 `_run_schedule` 写成 5 参，实际 3 参（`finished/started` 是局部变量）。**写工作包前用 `inspect.signature` 实测** |
| 只信子代理自报 | B2-2 自称"新失败为 0"，实际引入 72 个失败。**必须独立对照复核** |
| 子代理在 `mock.patch` 上下文里建 session | B2-1 的测试夹具会污染计数。被 patch 的函数若自身取连接，调用要放在 patch 外 |

---

## 7. 下一步（立即可做）

**B9 无阻塞**（依赖 B8 已完成）。B9 = P3 结构拆分（plan §1707 起），**风险最高、最后做**。

✅ **`docs/compose/reports/b9-work-brief.md` 已写好**，内含 Lead 现查的全部事实：
- **7 个常量搬移清单**（`render.py` L82-6440，共 1887 行）
- **8 个常量的 sha256 + 长度基线** + **vendor `hash8 = 72429792`**（契约级护栏）
- **三处易错点**：`_COMMON_CSS` 有两次赋值（第二次是自引用拼接，B8 后右边只剩 `_BASE_CSS + _COMMON_CSS`）；
  `_COMMON_JS` **不搬**；`config.py:50/51/60` 与 `report.py:53/54/73` **从 render 导入**这些名字 → `render` 必须继续导出
✅ **B9-1 已完成**（见上方状态表）。**下一步做 B9-2：`config.py` 按实体拆分**（`b9-work-brief.md` §3 有完整指引）。

B9-2 开工前必做（brief §3 已列，此处再强调）：
1. `grep -rn 'config\.' tests/*.py | wc -l` 量清依赖面
2. 找出 `server.py` 路由表里指向 `config.handle_*` 的入口（**函数名不能变**）
3. 找出 `config.py` 内**跨实体共享**的 helper（`_escape` 已是 render 的复用导入、`_get_depth`、`_nav_badges` 等）
   → 留在 `config.py` 或放公共模块，**不要**复制到多个实体模块
4. 写「拆分前 `dir(config)` 公开符号集合」作为基线，拆分后断言**无缺失**（允许新增）

> ⚠️ **B9-2 若无法安全完成，不交付也是可接受的**——brief §3 已明确此点。
> 「结构拆分」的收益是长期可维护性，不值得用一次性大爆炸改动换回归风险。
> 若判定风险过高，请**只报告原因**，不要勉强拆分。

> 已完成批次的工作包可直接参考：`b5-work-brief.md` ~ `b8-work-brief.md`（含实测基线、必测断言、回归命令与踩坑）。

### B6 写作时必须预先核实的点（避免重复 B5 的返工）

- **B6-7 `page_size` 封顶 1000**：上限**只能在 UI 的输入解析处**夹紧，
  **绝不得**放进 `execute_report`（`report.py:1031`）或 `render_report_page`（`:1612`）——内部调用方靠大 `page_size` 取全量：
  `export.py:97`（`2**31-1`）、`api_handler.py:452`（`fetch_all` 时 `1e9`）、`scheduler.py`（保活/定时任务）。
  必须带一条断言：`execute_report` 源码里**不含** `MAX_UI_PAGE_SIZE`。
  > ⚠️ **Lead 实测发现：有 2 个 UI 入口，两个都要夹紧，否则可绕过**：
  > ① `report.py:2217`（`handle_request` 的 GET query 解析）
  > ② `report.py:2073`（`_handle_refresh_cache` 的 POST form 解析，经 `:2198` 调用）
  > 两处写法都是 `page_size = max(1, parsed_page_size)`。只夹一处＝封顶无效。
  > 另：`MAX_UI_PAGE_SIZE` **不得**用于 API 翻页（`api_handler._apply_get_overrides` 是独立路径，
  > 且受端点 `row_limit` 约束）。
- **B6-4 socket 超时**：标为中高风险，须 L2 实测大导出是否被截断。
- **B6-5 `render.py` 首次引入 `logging`**：`logging.getLogger` 安全，但**不要**模块级 `basicConfig`。
- **B6-3 `?`→`%s`**：同文件 `query_executor.py` 已有引号感知实现可复用。

### 写 brief 的通用教训（B4/B5 各踩一次）

- **凭命名推测签名会错**：写测试调用前先用 `inspect.signature` 实测（B4 把 `_run_schedule` 写成 5 参，实际 3 参）。
- **测试夹具配方先实跑**：B5 才发现 `make_config_db()` 不建表、`config_db.init_db()` 在裸 sqlite3 上报错、
  `upsert_schedule` 必须绑报表。
- **同名前缀的 DB 函数语义可能不同**：`get_reports(conn)`（默认 `None` → 只查未分类）vs
  `get_all_reports(conn)`（真全量）。改任何 N+1 前先确认用的是哪个。
- **全量套件有低概率 flaky**：B5 期间 6 次全量中有 1 次失败（重跑即绿），与改动无关；
  遇到失败先重跑 + 用 `git stash` 对照，再定位。
- **子代理的「L2 实测通过」可能只是没踩到边界**（B6-4）：子代理在 500KB/s、8MiB、30s 超时下测通过；但 Lead 把超时缩到 2s + 客户端暂停 3s，立刻暴露「读超时解除点放错位置」的真缺陷（响应只发出 2588672/4194304）。**教训：对「把 A 阶段与 B 阶段解耦」这类改动，验收要用小参数直接压迫边界，而不是只用生产参数跑一遍。**
- **测试可能编码被修掉的缺陷**（B2 的 `ping`、B6-2 的锁）：修完发现旧断言变红时，先判断「它测的是缺陷本身还是真实需求」——前者按原意改写机制断言，后者才是回归。
- **删除类工作包不能只给行区间**（B7-1）：Lead 把区间写成 `:369-435`，而 `:418`/`:433` 是**生效中**的 `_DB_ERRNO_HINTS`/`_READ_TIMEOUT_MSG_MARKERS`；子代理用 `ast.parse` 看区间顶层对象后停下报告才拦住。**要求：写「这几行属于哪个符号」+ 子代理必须 AST 复核**。
- **plan 正文的行号与示例签名会过时**（B7-2/B7-4）：plan 的 `column_indices(cols) -> dict` 与真实 `(display_cols, all_columns) -> list` 不符；`report.py:1777-1778` 实际是 `:1740-1741`。**写 brief 前一律 `grep`/`inspect.signature` 现查**。
- **收口会打断测试的 mock 靶点**（B7-4）：把三步链上提后，`tests/test_derived_cache.py` 的 `patch("report.filter_rows")` 失效 → **全量首跑 11 errors**（单跑模块是绿的）。**收口类改动必须跑全量，并同任务内把 mock 靶点迁到新位置**（硬性 #8）。
