# 测试约定 · 验证顺序 · 高频易踩坑

与根 `AGENTS.md` 硬性约束 #8 / #12 / #14 / #17 对齐。本卷是**测试与验证纪律的全文所在**：官方入口与 `-t .` 隔离、范围递进与全量纪律、两败必停（硬性 #12）、测试基座与加测优先级、性能测量工具链、高频易踩坑。子代理派发与效率预算不在本卷，见 [09-agent-workflow.md](09-agent-workflow.md)。

## 跑测试（官方入口）

```bash
source venv/bin/activate   # 若已 install
python -m unittest discover -s tests/ -t . -v     # 官方全量入口（-t . 不可省；勿反复跑）
python -m unittest tests.test_filter_help -v      # 最小范围
python -m unittest tests.test_auth.TestSession.test_sliding_expiry_keeps_session_alive -v
```

- **以 `unittest` 为准**；`requirements.txt` 虽列 `pytest` 但环境未必装，勿默认 pytest。无 CI / 无 lint / 无 typecheck。
- discover 含 `tests/bug_hunt/test_static_analysis.py`（ERROR 会使测试失败）。
- 手动破坏性变异（勿当常规）：`python tests/bug_hunt/bug_hunt_mutation.py`。

### `-t .` 不能省（隔离的单一开关）

- 隔离唯一来源是 `tests/_bootstrap.py`（由 `tests/__init__.py` 调用 `_bootstrap.apply()`）：DEBUG_CONFIG 重定向、vendor 落点重定向、branding 库重定向、**Redis 强制关闭**。
- 不带 `-t .` 时 discover 把测试模块当顶层模块导入（`test_health` 而非 `tests.test_health`），`tests` 包根本不加载，上述隔离**全部失效**：连**生产 Redis** 读写真实快照（最严重）、写真实 `static/vendor/self@*/`、读本机 `config.db` 站点标识、被本机 `app_config.debug.json` 覆盖。
- 生效：`discover -s tests/ -t . -v` ✅、`python -m unittest tests.test_x` ✅；`discover -s tests/ -v`（无 `-t .`）❌。
- 金丝雀门禁 **`tests/test_test_isolation.py`**：漏一次 `-t .` 会静默回到危险状态，故「隔离是否生效」本身是一条会自己报警的测试；核心判据用本模块的**导入风格**（`__name__` 须以 `tests.` 开头，导入期确定），而不是「隔离当前是否生效」——后者会被金丝雀自己 import `tests` 而恒真掩盖。
- 需要 Redis 的用例自行 patch（如 `RedisConnectionManager._create_client`、`redis_cache.get_redis_config`）。

## 范围递进与全量纪律（硬性 #8）

| 级别 | 范围 | 规则 |
|------|------|------|
| L0 | 单用例 / 单文件 | 改动刚落地先跑，先证明「点」是绿的 |
| L1 | 同大模块相邻文件 | L0 绿后立即放大 |
| L2 | 分段或全量 | 任务收尾 / 跨模块改动时做一次完整确认 |
| L3 | 重复全量 | **禁止**：代码未再变时不得反复 `discover` |

- **代码未再变时，完整测试通过一次即可**；某级失败只修该级，不跳级用全量掩盖 L0/L1 失败。
- 确需分段（防单次整体超时）时按模块前缀依次 `-p` 跑，例：`test_config*.py`、`test_report*.py`、`test_api*.py`、`test_auth*.py`、`test_redis_cache*.py`；先跑 `tests.bug_hunt.test_static_analysis` 尽早暴露 ERROR。
- 易漏项（不被 `test_*.py` 通配覆盖）：`tests.test_base`、`tests.test_test_isolation`、`tests/bug_hunt/test_boundary.py`。
- **故意不进 discover**：`tests/integration/`（真层，需 DEBUG 配置 / MySQL，否则 skip）、`tests/manual_*.py`（`manual_` 前缀不被收集，须显式运行）。
- **同一测试段执行上限 2 次**（首跑 + 收口复跑，代码变更即重置，硬性 #14）；输出统一落 `run-logs/<段>-<时间戳>.log` 再 `grep -E '^(OK|FAILED|Ran |ERROR: |FAIL: )'`，落盘与取数同一动作，禁止只把管道结果留在对话里。

- **批次内不跑全量（2026-10-10 实测）**：9 批重构会话里 `unittest` bash 调用 186 次，其中全量 `discover -s tests` **159 次**，返回 220,647 字符（≈55k tokens 一次性注入，并被后续每步重发）。规则收敛为：**子任务/单文件改动只跑定向**（`-m unittest tests.test_x -v` 或 `-s tests/test_x.py`），**全量 `discover` 每批只在收尾跑 1 次**；同批已有绿全量日志时，后续子任务直接引用日志、不重跑（硬性 #14 的「同段 ≤2 次」不豁免批次内的重复全量）。

## 需求变更同任务改写测试（硬性 #8）

- 需求变更的**同一次任务**内改写受影响断言、夹具、脚本；禁止保留旧逻辑制造假失败。
- 旧测试与新需求冲突时，以**当前需求**为准改测试，不迁就过时断言。

## 禁止硬编码项目主目录

- 测试代码、程序代码、文档**不得**写死本仓库主目录绝对路径（主目录随时可变）。
- 正确做法：「仓库根（`server.py` 所在目录）」相对表述，或 `pathlib.Path(__file__).resolve()` 推导；勿依赖真实 `static/vendor/self@*` 绝对路径或本机 debug 配置。

## 两败必停 · 根因优先（硬性 #12）

适用：改码、跑测试、联调、UI 验证——凡「同一个问题」（同一失败断言 / 同一报错栈 / 同一可复现现象）连续 **2 次**尝试未解决即触发。工具层同样：同一工具调用**失败 2 次**禁止原样重发；被中断的调用不计失败次数，恢复时先查上一动作是否生效。

1. **停**：不再改码、不再换参数重试、不再第 3 次「也许这样能过」。
2. **想**（只分析，不写补丁）：完整报错/失败断言是什么、两次是否同一根因？复现是否稳定、最小复现是什么？涉及哪些模块与共享语义（查 `INDEX.md` / 对应分卷 / codegraph）？是需求理解错、测试过时（硬性 #8）、路径写死，还是实现真 bug？易踩坑清单是否已有同类？
3. **判**：写出一句话根因假设 + 「改哪里、为何能消错」的依据；假设解释不了现象就回到第 2 步，**仍不改码**。
4. **再动手**：仅允许**一次有针对性的**修改 + **L0 最小范围**验证；再失败即视为新问题或假设被证伪，回到第 1 步。

禁止：无根因假设的第 3 次及以后盲试（连环改、连环重跑全量、瞎改无关文件）；用「跑全量碰运气」代替定位；用改断言掩盖未理解的产品行为（除非根因确证为过时测试，属硬性 #8）。

## 测试基座与加测优先级

- 基类与夹具从 `tests/__init__.py` 导入（`BaseConfigTest` / `BaseReportTest` / `make_config_db` / `init_test_db`）；进程隔离由 `tests/_bootstrap.py` 提供，真层见 `tests/integration/base.py`（无 DEBUG 配置 / MySQL 不通则 skip）。
- `tests/test_base.py` **硬编码 DDL**、故意不 import `db`（防循环依赖）→ 改 schema 必须多处同步；HTML 结构用 `tests/htmlcheck.py` 而非仅 `assertIn` 字符串；`tests/bug_hunt/` 只放 bug_hunt 工具（见其 `BUG_HUNT.md`，勿散落到 tests 根）。
- 加测优先钉**共享行为**：筛选语法、写护栏、导出截断、API 鉴权、HTML 结构——改一处会波及三端（具体文件见 `INDEX.md` 共享语义表）。
- **characterization 测试的期望值必须来自未改动实现的实测**，不能靠推导；改这类「不许变」的行为按「先写测试 → 确认绿 → 改代码 → 确认仍绿」。
- 测试必须能**独立于执行顺序**通过，否则是隐藏的进程级全局污染（见易踩坑）。

## 性能测量工具链（`scripts/perf/`）

一次性脚本，**故意不放 `tests/`**：它们会建表、灌数、改真实 MySQL 与真实配置库，绝不能被 discover 触及。产物落 `perf-logs/`（已 gitignore，勿用 `/tmp`），凭据读 `perf-logs/bench-credentials.txt`。

- `check_conn.py` 连通性预检（缺哪个配置键并非零退出）；`seed_perf_data.py` 造性能数据（`perf_text` 10 万行，含 DECIMAL / 混排 / NULL）；`init_debug_env.py` 初始化 `config.debug.db`（数据源、4 张性能报表、基准账号、API 端点）。
- `bench.py` 12 场景端到端 HTTP 压测（输出 JSON，并断言 `cache_info.source` 分布）；`seed_session_script_report.py` + `bench_session_script.py` 会话级脚本的缓存门槛 A/B 与三端一致性（启动即校验数据源为本地）。
- `verify_transform_equivalence.py` 以 `git <基线 commit>` 实现为参考、真实数据上逐行比对 transform 语义；`verify_redis_fallback.py` 真跑「数据源不可用 → 过期快照兜底」。
- 端到端测量噪声约 **±6%**，小于 ~10% 的差异不可解读；判断 transform 类收益要用**隔离 A/B**（同进程、多次重复、同一数据），不要端到端数字。
## 取证手段选择（先代码，后浏览器；硬性 #17）

- **默认代码层定位**：`codegraph`/`grep`/读源码/静态门禁能定性的，不启动浏览器（Chrome 启动 + 字体/双 rAF 等待 + 像素回验，单次数十秒到分钟级）。
- **只有需要运行时证据才起 Chrome**：计算样式/几何/布局、DOM 事件层交互（换页初始化、拖拽、渲染时机）、代码层无法判定的视觉现象、修复后的最终视觉确认。
- **一次会话批量验完**，禁止「改一行 → 截一次图」；能做成门禁的优先做成门禁（毫秒级且可回归）。
- 判据表与工具见 [06-ui-interactions.md](06-ui-interactions.md)「取证成本纪律」。

## 禁止提交的运行时/本地物

`app_config*.json`（非 example）、`config.db`、`audit.db`、`venv/`、`static_cache/`、`run-logs/`、`perf-logs/`、`.codegraph/`、`.mimocode/` 等（见 `.gitignore`）。**`docs/` 与 `MEMORY.md` 已入库**，勿误当忽略物（`git check-ignore <path>` 可实测）。

## 高频易踩坑清单（Top）

1. **discover 忘加 `-t .`** → `tests/__init__.py` 不执行，整套测试隔离失效（含连生产 Redis）；金丝雀 `tests/test_test_isolation.py` 会失败并给出修复命令（见上文）。
2. **本机 `app_config.json` 配了 `config_db.engine=mysql` 时，未 patch 引擎的 SQLite 用例会在 `init_db` 走 MySQL 分支**报 `sqlite3.OperationalError: near "="`（`init_db` 内部经 `db._get_engine()` 读配置）→ 按 `tests/test_base.py` 惯例 `patch("db._get_engine", return_value="sqlite3")`；新增直调 `init_db` 的测试同样要隔离。
3. **测试依赖进程级全局状态而未清理**：`report._query_cache`、`query_executor` 连接池 → 相关用例在 `setUp` 里清 `report._query_cache.clear()` + `query_executor.clear_pools()`，否则会读到别的用例的 mock 数据——**症状是「换个执行顺序就过不过」**。
4. **characterization 测试的期望值靠推导** → 必须用**未改动的实现实测**得出（2026-09-29 实测中就抓到过推导错误两次）。
5. **UI 验收只做「整页加载后点一次」**：无刷新换页后 `innerHTML` 不执行内联 `<script>`、不重跑初始化，靠 `addEventListener` 绑定的交互静默失效（表现为「按钮能点、拖拽报废」）→ 交互改动必须验**两种载入态**（整页 + 换页后）+ 第二/三次操作 + 组合顺序（硬性 #17）。
6. **CDP/E2E 验收脚本自身的坑**（都是「测了个假绿/假红」）：陈旧 cookie 拿到登录页；`Page.navigate` 清空 `window.*` 自定义钩子；选择器想当然（`#f_customer` 实际是 `[name="f_customer"]`）；拖拽语义是「**插到目标项之前**」，故 `drag(i, i+1)` 与拖到自己都是 no-op；把**条件渲染**的函数当存在性判据。
7. **改了 `render.py` / `report.py` / `config.py` 但服务没重启** → 页面内联 JS 从内存直出，验到的是旧行为（HTML 带 `Cache-Control: no-store`，用户标签页方不跑旧脚本）。
8. **断言公共 CSS 别对着报表页 `body` 断言**：公共样式走外链 `/static/vendor/self@<hash>/common.css`，**不内联**，故「产物里必须出现某条 CSS 规则」在正常环境**必红**；应断言公共样式单一来源 `render._COMMON_CSS`，并另加一条「页面确实携带公共样式」。
9. **`run-logs/` 里的克隆副本污染静态分析门禁**：`tests/bug_hunt/static_analyzer.py` 只跳过 `IGNORE_DIRS`（`venv`/`.codegraph`/`__pycache__`/`.git`/`.opencode`/`.tmp`），**不跳过 `run-logs/`、`perf-logs/`** → 留在其中的 `git clone`/`worktree` 被判「无法导入模块 test_base」，全量 discover 因此 ERROR。跑全量前确认 `run-logs/` 下无 `.py` 克隆产物（或把克隆放到仓库外），**不要**为此放宽门禁。
10. **新增门禁 ≠ 门禁有效**：从未失败过的门禁可能只是恰好路过当前代码，新门禁必须做 RED-GREEN 自证（`venv/bin/python tests/bug_hunt/gate_redproof.py`，不进 discover）；门禁读「可能缺失的文件」须用 `_maybe_read()` 式容错并在文件存在时才断言，同时另加结构断言防止读盘入口空转通过。

## 文档过时线索

历史过时项（README 结构树、测试清单等）见 `README.md`「过时线索」；一切以当前目录、可执行代码与 `tests/` 为准，冲突时改文档（中英同步）。
