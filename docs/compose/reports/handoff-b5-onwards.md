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
| **已完成批次** | **B1 ✅ B2 ✅ B3 ✅ B4 ✅** |
| **待做批次** | **B5 → B6 → B7 → B8 → B9** |

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
| **B5** | P1 性能 | `config_db.py` `report.py` `result_transform.py` `render.py` `config.py` | B2 ✅ | ① 筛选内循环合并 alternation（实测快 2.8~3.5×，**禁止**用 `lower() in`）② 配置页 12 次查询 → 7 ③ 侧栏徽标 N+1 ④ `get_reports_by_category` N+1 ⑤ 派生态缓存拆两级（可选项） |
| **B6** | P1 健壮性 + `page_size` 封顶 + CSV 开关 | `redis_cache.py` `server.py` `static_cache.py` `render.py` `query_executor.py` `report.py` `export.py` | B3 ✅ B4 ✅ B5 | ① Redis 冷启动自愈 ② 重建锁 owner/TTL ③ `?`→`%s` 引号感知 ④ socket 超时（**风险中高，须 L2 实测**）⑤ 资产降级加日志（render 首次引入 logging）⑥ `static_cache` 加锁 ⑦ **`page_size` 封顶 1000，仅 UI 层**（严禁加在 `execute_report`！）⑧ CSV 公式中和（默认关+导出页勾选） |
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

B5 无阻塞（依赖 B2 已完成）。建议：

1. 读 plan 的 B5 章节 + spec §5 B5
2. 写 `docs/compose/reports/b5-work-brief.md`（含：精确行号、实测基线数字、必测断言、**禁止 lower() 的警告**）
3. 按 B5-1 → B5-2 → B5-3 → B5-4 → B5-5 逐任务派子代理
4. 全量期望 `Ran ≥3090`（B4 后 3083 + B5 新增）

> **B5-1 的实测基线**（供写 brief）：100k 行 × 12 列，单条件 contains 筛选 73.2ms；改用单条 alternation 后 35.8ms（3 值场景 99.0→35.8ms）。**禁止**改成 `lower() in`（25.3→8.4ms 但 Unicode 大小写折叠语义有边界差异）。
