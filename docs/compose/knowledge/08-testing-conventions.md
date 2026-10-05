# 测试约定 · 验证顺序 · 高频易踩坑

与根 `AGENTS.md` 硬性约束 #8–#14 对齐（2026-09-29 起：**「测试策略与推荐验证顺序」「两败必停」「多子代理协作与验证纪律」的全文在本卷与 `09-agent-workflow.md`**，AGENTS.md 只留条目与指路）。

## 跑测试（官方入口）

```bash
source venv/bin/activate   # 若已 install
python -m unittest discover -s tests/ -t . -v     # 官方全量入口（对账用，勿反复跑）
python -m unittest tests.test_filter_help -v      # 最小范围
python -m unittest tests.test_auth.TestSession.test_sliding_expiry_keeps_session_alive -v
```

- **以 `unittest` 为准**；`requirements.txt` 有 `pytest` 但环境未必装，勿默认 pytest
- discover 含 `tests/bug_hunt/test_static_analysis.py`（ERROR 会失败）
- 手动破坏性变异（勿当常规）：`python tests/bug_hunt/bug_hunt_mutation.py`

### ⚠️ `-t .` 不能省（2026-09-29 实测 + 已加金丝雀）

**隔离的单一来源是 `tests/_bootstrap.py`**（由 `tests/__init__.py` 调用
`_bootstrap.apply()`），包含四项：DEBUG_CONFIG_FILE 重定向、vendor 落点重定向、
branding 库重定向、**Redis 强制关闭**。

**不带 `-t .` 时 discover 把测试模块当顶层模块导入**（`test_health` 而非
`tests.test_health`），包根本不被加载（探针实测 `"tests" in sys.modules == False`），
上述隔离**全部失效**：

| 入口 | 隔离是否生效 |
|------|--------------|
| `discover -s tests/ -v` | ❌ 否 |
| `discover -s tests/ -t . -v` | ✅ 是 |
| `python -m unittest tests.test_x` | ✅ 是 |

失效的后果：连**生产 Redis** 读写真实快照（最严重）、写真实
`static/vendor/self@*/`、读本机 `config.db` 的站点标识、被本机
`app_config.debug.json` 覆盖。

#### 金丝雀：`tests/test_test_isolation.py`

只改命令不够——**任何人漏一次 `-t .` 就会静默回到危险状态**，且要很久以后才被
unrelated 的测试失败发现。所以隔离是否生效本身是一条会自己报警的测试：

| 用例 | 检查 |
|------|------|
| `test_imported_as_package_module` | **核心判据**：本模块须以 `tests.xxx` 形式导入，否则失败并打印修复命令 |
| `test_bootstrap_applied` | `_bootstrap.apply()` 已执行 |
| `test_redis_is_not_reachable` | `redis_available()` 为假、`get_redis_config().enable` 为假、无全局管理器 |
| `test_debug_config_redirected` | `DEBUG_CONFIG_FILE` 指向隔离路径 |
| `test_vendor_root_is_temp` / `test_branding_db_is_temp` | 落点在临时目录 |

**判据为什么用「本模块的导入风格」而不是「隔离当前是否生效」**：后者会被自我
掩盖——金丝雀若 import 了 `tests`，`tests/__init__.py` 就替它装上隔离，于是
「隔离生效」恒为真、金丝雀形同虚设（第一版就是这么写错的：漏 `-t .` 时它反而
全绿）。`__name__` 在模块导入时确定，无法被后续导入掩盖。

需要 Redis 的用例自行 patch `redis_cache.get_redis_config` 或用
`reset_redis_manager` 显式注入（显式注入即显式选择连哪个 Redis）；实测
`test_redis_cache*` 全部 patch `RedisConnectionManager._create_client`，从不连
真实服务。

## 性能测量工具链（`scripts/perf/`，2026-09-29）

一次性脚本，**故意不放 `tests/`**——它们会建表、灌数、改真实 MySQL 与真实配置库，
绝不能被 `discover` 触及或被维护者误当测试跑。

| 脚本 | 作用 |
|------|------|
| `check_conn.py` | MySQL/Redis 连通性预检，失败时打印「缺哪个配置键」并非零退出 |
| `seed_perf_data.py` | 造性能数据（`perf_text` 10 万行含 DECIMAL/混排/NULL 等） |
| `init_debug_env.py` | 初始化空的 `config.debug.db`，建数据源、4 张性能报表、基准账号、API 端点 |
| `bench.py` | 12 场景端到端 HTTP 压测，输出 JSON；**并断言 `cache_info.source` 分布** |
| `verify_transform_equivalence.py` | 以 `git <基线commit>` 的实现为参考，真实数据上逐行比对 transform 语义 |

约定：
- **产物落 `perf-logs/`（已 gitignore），不要用 `/tmp`** —— 本环境 `/tmp` 会被
  周期清空，且 `nohup` 后台进程活不过单次 bash 调用；起服务+压测必须在同一条命令内
- 凭据从 `perf-logs/bench-credentials.txt` 读（`init_debug_env.py` 自动生成）
- 端到端测量噪声约 **±6%**，小于 ~10% 的差异不可解读；判断 transform 类收益要用
  隔离 A/B（同进程、多次重复、同一数据），不要用端到端数字

## 范围递进与全量纪律（硬性）

摘要（完整规则与 L2 分段命令表见本卷「测试策略与推荐验证顺序」）：

| 级别 | 范围 | 规则 |
|------|------|------|
| L0 | 单用例/单文件 | 改动后先跑最小范围 |
| L1 | 同大模块相邻文件 | L0 绿后再放大 |
| L2 | 分段全量 | 按大模块顺序**依次**分段跑，防单次 discover 整体超时 |
| 重复全量 | — | **禁止**：L2 已过且代码未再变，任务内不必反复全量 |

- 某段失败只修该段，不整库重来、不跳级用全量掩盖 L0/L1 失败。

## 测试/脚本对齐最新需求（硬性 #9）

- 需求变更的**同一次任务**内改写受影响断言、夹具、脚本；禁止保留旧逻辑测试反复假失败。
- 旧测试与新需求冲突时：以**当前需求**为准改测试，不迁就过时断言。

## 禁止硬编码项目主目录（硬性 #10）

- 测试代码、程序代码、文档**不得**写死本仓库主目录绝对路径（主目录可随时变更）。
- 正确做法：「仓库根（`server.py` 所在目录）」相对表述，或 `pathlib.Path(__file__).resolve()` 推导。
- 例外：`AGENTS.md` 硬性约束 #1 生产副本路径是禁止触碰的外部路径，不属于本条。
- 勿依赖真实 `static/vendor/self@*` 绝对路径或本机 debug 配置。

## 两败必停 · 根因优先（硬性 #12）

适用：开发改码、跑测试、联调、UI 验证等——凡「同一个问题」（同一失败断言、同一报错栈、同一可复现现象）连续 **2 次**尝试未解决。

### 触发后必须立即

1. **停**：不再改代码、不再换参数重试、不再第 3 次「也许这样能过」。
2. **想**：只分析原因，不写补丁。至少回答：
   - 完整报错/失败断言是什么？第一次与第二次失败是否同一根因？
   - 复现步骤是否稳定？最小复现是什么？
   - 涉及哪些模块与共享语义（先查 `INDEX.md`、对应分卷、`codegraph`）？
   - 是需求理解错、测试过时（#9）、路径写死（#10）、还是实现真 bug？
   - 知识库/「高频易踩坑」是否已有同类案例？
3. **判**：形成一句话根因假设，以及「改哪里、为何能消错」的依据；假设不能解释现象则回到第 2 步，**仍不改码**。
4. **再动手**：根因清楚后才允许下一步修改；改完用 **L0 最小范围**验证，绿了再放大。

### 禁止

- 同一问题第 3 次及以后仍无根因假设的盲试（连环改、连环重跑全量、瞎改无关文件）。
- 用「跑全量碰运气」代替定位；用改测试断言掩盖未理解的产品行为（除非根因确证为过时测试且属 #9）。
- 对话/汇报里只写「再试一次」而不写根因分析。

### 何时可以再次尝试

仅当：已写出根因假设 → 该假设对应**一次有针对性的**修改 → L0 验证。验证若再失败，视为**新问题或假设被证伪**，回到「停/想」，不得原样重试。

**工具层口径**（R2 教训）：同一工具调用**失败 2 次**禁止原样重发；**被中断的调用不计入失败次数**，恢复时先 status 查上一动作是否生效、再换法。

**实战样例（2026-09-29 性能优化）**：连续两次「导出用例失败」时，若继续改断言就是在瞎试。停手后的三问直接定位到真因——「失败是否随执行方式变化」（是 → 顺序/状态问题）、「失败用例是否与最近改动同链路」（是 → 回归）、「mock 的返回是否真的被消费」（否 → 根本没走到被改的代码）。第三问顺带查出了「测试进程在连生产 Redis」这个与性能任务无关、但更严重的隐患。

## 多子代理协作与验证纪律（硬性 #13–#14）

> **完整细则见 [09-agent-workflow.md](09-agent-workflow.md)**（派发纪律 / 简报五件套 / 预算与监控 / 汇报节奏 / 执行效率 P1–P7）。本节只留测试与截图相关的部分。

- **派发**：同任务至多一个活跃子代理；spawn 前 Task/Actor 盘点、成功后记 actor_id；一条消息只 spawn 一次；重派前 cancel+status+mtime 三确认（**cancel 回执不作数**）；brief 只写增量、通用协议引用 09 卷；**每次 spawn 必含简报五件套**（必读顺序 / 先 Memory+History 检索后探索 / 上下文包 / 环境事实 / 效率预算），禁止让子代理从零摸索。
- **验证**：跑测前先查 `status`——**无活跃写入者直接跑**（免采样），有写入者才采样等待（间隔 5–10s、≤3 次，到顶→阻塞汇报）；测试输出落**仓库内 gitignore 目录**（`run-logs/`）再 grep、中断后读文件不重发；**同一测试段执行上限 2 次**（首跑+收口复跑；按测试文件集合计数、**代码变更即重置**）；截图单轮矩阵、唯一文件名、禁 rm、**落盘即校验大小/md5（同页 md5 重复=重拍 1 次上限，仍无效→按 #12 找根因）**。
- **UI 截图必须过一致性回验**（R3 新增，用户纠正）：截图与 HTML 渲染不一致时，任何基于图的 CSS 判断无效。管线 = `docs/compose/spec/shots/r3/shot-verify.mjs`（CDP 单视口截图、**禁滚动拼接**；截后把 PNG 画进 canvas 按 DOM 坐标取像素，与 `getComputedStyle` 色值比对，容差 12；角标红/绿点验对齐；FAIL 非零退出）。本容器一次性 `chrome --screenshot` 必挂（最小 data: 用例也超时），只走 CDP，且 CDP server 随 shell 回收——须同命令内「启动→轮询 /json/version→执行→kill」。预览通道（read_image）错位时**禁止多轮读图取证**（#12 口径）：1 次复测失败即改用像素回验/数值断言。
- **预算（硬性 #15）**：同段测试 ≤2 次、轮询必带判据与上限、禁把重跑测试当 sleep；单页 ≤40 轮/代理 ≤120 轮 + spawn `timeout_ms`（25min 先 send 催收口、30min 硬顶）；父会话 turnCount>150 必须介入；status 巡检间隔 ≥5min、上限 6 次。（R2 实测：同一条静态分析测试每 9 秒重跑 23+ 次、代理 917 轮——无退出条件的轮询是头号浪费。）
- **中断恢复**：工具被中断先 `status` 查上一动作是否生效，禁止原样重发；阶段转换输出一次进度表。

## 测试基座

```python
from tests import BaseConfigTest, BaseReportTest, make_config_db, init_test_db
```

- 导出经 `tests/__init__.py`（它调用 `tests/_bootstrap.py` 做进程隔离，见上文 `-t .` 节）
- `tests/test_base.py`：**硬编码 DDL**，故意不 import `db`（防循环依赖）→ 改 schema 必须三处同步
- `tests/htmlcheck.py`：HTML 结构（form 嵌套、标签配对）
- `tests/preset_test_cases.json`：预设夹具
- `tests/integration/`：真层；无 DEBUG 配置 skip；MySQL 不通 skip
- `tests/bug_hunt/`：**bug_hunt 工具一律放这里**（见该目录 `BUG_HUNT.md`），不散落到 tests 根
- 渲染相关改动**建议用 `htmlcheck` 而非仅 `assertIn` 字符串**，避免 form 嵌套类回归

### 加测的优先级（怎么写）

- **优先给共享行为加测**：筛选语法、写护栏、导出截断、API 鉴权、HTML 结构——改一处会波及三端的东西，最值得钉死。具体文件清单见下方「跨模块一致性测试优先覆盖」。
- **characterization 测试的期望值必须来自未改动实现的实测**，不能靠推导（2026-09-29 实测中推导错误两次）。改这类"不许变"的行为时：先写测试→先确认绿→再改代码→确认仍绿。
- 测试必须能**独立于执行顺序**通过，否则是隐藏的进程级全局污染（见易踩坑 #18）。

## 禁止提交的运行时/本地物

`app_config*.json`（非 example）、`config.db`、`audit.db`、`venv/`、`static_cache/`、`run-logs/`、`perf-logs/`、`.codegraph/`、`AGENTS.md`、`.mimocode/` 等（见 `.gitignore`）。
**`docs/` 与 `MEMORY.md` 已入库**，勿误当忽略物（`git check-ignore <path>` 可实测）。

## 测试策略与推荐验证顺序（硬性 #8）

改动落地后（无强制 lint/typecheck），按下列**范围递进**执行，禁止一上来就盲目全量、也禁止代码未变时反复全量。

### 1. 范围递进

| 级别 | 范围 | 何时用 |
|------|------|--------|
| L0 最小 | 单用例 / 单文件 | 改动刚落地；先证明「点」是绿的 |
| L1 模块组 | 与改动同一大模块的相邻测试文件 | L0 通过后立即放大 |
| L2 分段全量 | 按下方大模块顺序**依次**跑完全部 | 任务收尾、或跨模块改动需要一次完整确认 |
| L3 重复全量 | — | **禁止**：L2 已通过且其后代码无变化时，不必再跑 L2 |

- 每级通过后再进入下一级；某级失败只修该级，不跳级用全量掩盖。
- **完整测试通过一次即可**：同一任务内若源码/测试均未再变更，后续勿反复 `discover` 全量。
- **分段防超时**：L2 不要用单次长时间 `discover -t . -v` 一把梭；按大模块顺序分段执行，单段超时/失败时只重跑该段。
- **取数模板（硬性 #16②）**：上表全部命令实际执行时统一 `python -m unittest … > run-logs/<段>-<时间戳>.log 2>&1; grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )' <该 log>`——落盘与取数同一动作，中断可续查、禁止只靠管道结果留在对话里。

### 2. L2 大模块顺序（依次执行，避免整体超时）

均在已激活的 `venv` 中、以仓库根为工作目录（**`-t .` 不可省**，理由见上文）：

```bash
# ① 静态分析（全量 discover 也会跑；分段时先跑，尽快暴露 ERROR）
python -m unittest tests.bug_hunt.test_static_analysis -v

# ② 筛选 / 变换 / 输出护栏
python -m unittest tests.test_filter_help tests.test_result_transform \
  tests.test_nested_filter tests.test_exclusion_engine \
  tests.test_max_rows tests.test_output_limit \
  tests.test_write_guard tests.test_sql_write_detect \
  tests.test_sql_persistent_write tests.test_derived_cache -v

# ③ 配置 / 数据层 / 迁移
python -m unittest discover -s tests/ -t . -p 'test_config*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_db.py' -v
python -m unittest discover -s tests/ -t . -p 'test_mysql*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_deletion_safety.py' -v
python -m unittest discover -s tests/ -t . -p 'test_app_config*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_debug_config*.py' -v

# ④ 报表页 / 导出 / 预设 / JSON 模板
python -m unittest discover -s tests/ -t . -p 'test_report*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_export*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_preset*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_json_template.py' -v

# ⑤ API
python -m unittest discover -s tests/ -t . -p 'test_api*.py' -v

# ⑥ UI / render / HTML / 品牌
python -m unittest discover -s tests/ -t . -p 'test_render*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_html*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_markdown*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_*branding*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_ux*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_feedback*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_smart_quotes*.py' -v

# ⑦ 认证 / 审计 / 健康检查
python -m unittest discover -s tests/ -t . -p 'test_auth*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_audit*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_api_key*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_health.py' -v
python -m unittest discover -s tests/ -t . -p 'test_trust*.py' -v

# ⑧ 缓存 / 调度
python -m unittest discover -s tests/ -t . -p 'test_redis_cache*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_static_cache*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_query_cache.py' -v
python -m unittest discover -s tests/ -t . -p 'test_cache_ui.py' -v
python -m unittest discover -s tests/ -t . -p 'test_scheduler*.py' -v

# ⑨ 服务入口与杂项收尾
python -m unittest discover -s tests/ -t . -p 'test_server.py' -v
python -m unittest discover -s tests/ -t . -p 'test_state*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_deep*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_bug_*.py' -v
python -m unittest discover -s tests/ -t . -p 'test_file_permissions.py' -v
python -m unittest discover -s tests/ -t . -p 'test_sql_formatter.py' -v
python -m unittest discover -s tests/ -t . -p 'test_*.py' -v   # 可选兜底：仅当需要与 discover 对账时
```

说明：

- 顺序固定为 ①→⑨；后段依赖前段语义时不要倒序「先跑大的」。
- 上表用 `discover -p` / 显式模块名分段；**单段失败先修该段再继续**，不要整库重来。
- 仅当需要与官方全量入口对账、或跨多段改完收口时，最后可跑一次：
  `python -m unittest discover -s tests/ -t . -v`（仍受「代码未变不重复全量」约束）。
- 参考规模（2026-09-29 实测）：全量 2934 项约 62s；分段累计 2900+ 项。

### 3. 收尾检查单

1. L0（及必要时 L1）绿 → 需要时 L2 分段全量绿（本任务内一次即可）
2. **知识库同步**：确认 `docs/compose/knowledge/` 受影响分卷与 `learn/sqlreport-kb/course-state.md` 已随本次变更更新
3. 需要时再手动跑 bug_hunt 变异脚本
4. **spec 查证**：确认本次任务已按 spec/plan 约定查过生效 spec

无 CI / 无 lint / 无 typecheck 配置。

## 跨模块一致性测试优先覆盖

- 筛选语法：`test_filter_help`、`test_result_transform`、`test_nested_filter`、`test_exclusion_engine`
- 写护栏：`test_write_guard`、`test_sql_write_detect`、`test_sql_persistent_write`（判定分工矩阵）、`test_derived_cache`
- 写判定/缓存门槛回归（手工，不进 discover）：`tests/manual_write_gate_regression.py`（只读跑配置库全部报表比对新旧判定）、`scripts/perf/bench_session_script.py`（本地夹具 A/B + 三端一致性）
- 导出/截断：`test_export`、`test_max_rows`、`test_output_limit`
- API：`test_api_*`
- HTML：`test_html_structure` + `htmlcheck`
- 迁移：`test_config_db_migrations`
- 删除安全：`test_deletion_safety`
- 调度：`test_scheduler_*`
- 缓存：`test_redis_cache*`、`test_static_cache*`、`test_query_cache`

## 高频易踩坑清单（Top）

1. **只改 SQLite 忘 MySQL 迁移**（或忘 `test_base` DDL）
2. **在 export/api 重写筛选语义** 而非 `result_transform`
3. **新 UI 另起 CSS/JS** 未进 `render` 单一来源
4. **ROUTES 插入顺序** 被 `/config($|/)` 等吞掉
5. **flash 未 URL 编码** 导致 Location 非 ASCII
6. **嵌套 form** 通过 assertIn 却挂 htmlcheck
7. **改 README 只改中或英**（镜像对须同次提交）
8. **依赖变更未同步** requirements + 双 README + install.sh
9. **测试依赖真实 vendor 路径或 debug 配置**
10. **生产路径** `/alexblair/windir/www/SqlReport/` 被误读误改（禁止）
11. **子代理写 `/tmp` 后再读被 `external_directory=ask` 拦**——子代理截图落 /tmp 后应在当轮直接报告数值/文件名，读图与复核由主会话执行
11. **未先最小范围就全量** / 代码未变反复全量 / 单次 discover 整体超时
12. **旧测试逻辑未随需求改写**，假失败干扰修正
13. **测试/代码/文档硬编码本仓库主目录绝对路径**
14. **同一问题失败 ≥2 次仍盲目重试**，不先找根因（硬性 #12）
15. **本机 `app_config.json` 配了 `config_db.engine=mysql` 时，未 patch 引擎的 SQLite 用例会在 `init_db` 走 MySQL 分支**报 `sqlite3.OperationalError: near "="`——`init_db` 内部经 `db._get_engine()` 读配置；单测须按 `test_base` 惯例 `patch("db._get_engine", return_value="sqlite3")`（已修：`test_config_db_migrations/TestInitDbFullMigration`、`test_preset_cases/make_db`）；新增直调 `init_db` 的测试同样要隔离
16. **discover 忘加 `-t .`** → `tests/__init__.py` 不执行，整套测试隔离失效（含连生产 Redis）。有金丝雀 `test_test_isolation` 会失败并给出修复命令。见上文
17. **金丝雀被自己掩盖** → 断言「隔离是否生效」的测试**不能 import `tests`**（import 了就等于自己装上隔离，断言恒为真）。用「本模块的导入风格」（`__name__` 是否以 `tests.` 开头）这类**导入期确定**的判据
18. **测试依赖进程级全局状态而未清理**：`report._query_cache`（L1）、`query_executor` 连接池。导出改走 `execute_report`（C-4）与连接池（C-2）后，写相关测试必须在 `setUp` 清 `report._query_cache.clear()` + `query_executor.clear_pools()`，否则会读到别的用例的 mock 数据——**症状是「换个执行顺序就过不过」**
19. **characterization 测试的期望值靠推导** → 必须用**未改动的实现实测**得出。2026-09-29 实测中就抓到过推导错误（数字字符串排序我以为返回 float，实际返回原字符串，变的只是行序）
20. **UI 验收只做「整页加载后点一次」**（2026-09-30 复盘头号教训）：无刷新换页（`_swapMain`）后 `innerHTML` 不执行内联 `<script>`、不重跑初始化——靠 `addEventListener` 绑定的交互全部静默失效，而内联 `onclick` 仍可用（表现为“按钮能点、拖拽报废”）。
    → 交互类改动必须验**两种载入态**（整页 + 换页后）+ **第二次/第三次操作** + **组合顺序**；静态门禁 `TestPageInitRegistration`（新 init 必须进 `initPage()`，页面脚本用 `onReady`），E2E `scripts/ui-v2/e2e/swap-reinit.mjs`。
21. **CDP 验收脚本自身的坑**（都是“测了个假绿/假红”）：陈旧 cookie 拿到登录页；`Page.navigate` 清空 `window.*` 自定义钩子；选择器想当然（`#f_customer` 实际是 `[name="f_customer"]`）；`children` 下标被占位元素（如 `#sortList > .sort-empty`）污染；拖拽语义是「**插到目标项之前**」，故 `drag(i, i+1)` 与「拖到自己身上」都是 no-op，要验必须反向拖或跨项拖（实测：排序项 0→1 顺序不变曾被误读为“换页后拖拽失效”）；拿**条件渲染**的函数当存在性判据（`toggleResultIndex` 只在多结果集报表输出，单结果集页 `typeof` 为 `undefined`）；自定义列默认勾选使“取消勾选”语义反转。
22. **改了 `render.py`/`report.py`/`config.py` 但服务没重启** → 页面内联 JS 从内存直出，验到的是旧行为。配合 HTML `Cache-Control: no-store`（`server.py:_send_html`），否则用户标签页也会跑旧脚本。
23. **新增门禁不等效于门禁有效**：从未失败过的门禁可能只是恰好路过当前代码。新门禁必须做 RED-GREEN 证明（把历史缺陷打回去→必须失败；还原→必须通过）：`venv/bin/python tests/bug_hunt/gate_redproof.py`（会临时改写 `report.py` 并校验 sha256 还原；不进 discover，勿当常规回归）。

## 文档过时线索（AGENTS.md 已提醒）

- README「项目结构」可能仍写 `AGENTS.md` 存在、列出 `git-purge.sh` —— 以当前目录为准
- README 测试树不完整 —— 以 `tests/` + discover 为准
- 文档冲突 → 改文档（中英同步）

---
最后核对：`tests/` 目录 + `AGENTS.md` 硬性约束 #8–#17；**2026-09-30 UI v2 复盘同步**（易踩坑 #20–#23：换页态验收、CDP 脚本自身的坑、改代码后重启服务、门禁需 RED-GREEN 自证；新工具 `tests/bug_hunt/gate_redproof.py`；交互验收清单见 `knowledge/06-ui-interactions.md` 硬性 #17）；2026-09-29 执行层性能优化同步（`-t .` 隔离与金丝雀、进程级全局清理、`scripts/perf/` 工具链、characterization 测试纪律、易踩坑 #16–#19）；2026-09-29 AGENTS.md 瘦身重构（本卷接收「测试策略与推荐验证顺序」全文 + 「两败必停」全文；多子代理细则移交 `09-agent-workflow.md`）
