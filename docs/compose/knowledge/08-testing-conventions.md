# 测试约定 · 验证顺序 · 高频易踩坑

与根 `AGENTS.md` 硬性约束 #8–#10、#12–#14、「测试策略与推荐验证顺序」「两败必停 · 根因优先」「多子代理协作与验证纪律」对齐（R2 核对 2026-09-25 已同步）。

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

### ⚠️ `-t .` 不能省（2026-09-29 实测）

`tests/__init__.py` 承载本项目**全部**测试隔离。**不带 `-t .` 时 discover 把测试
模块当顶层模块导入**（`test_health` 而非 `tests.test_health`），包根本不被加载
（探针实测 `"tests" in sys.modules == False`），于是整套隔离全部失效：

| 入口 | `tests/__init__.py` 是否执行 |
|------|------------------------------|
| `discover -s tests/ -v` | ❌ 否 |
| `discover -s tests/ -t . -v` | ✅ 是 |
| `python -m unittest tests.test_x` | ✅ 是 |

失效的隔离项：DEBUG_CONFIG_FILE 重定向、本机 `app_config.debug.json` 泄漏、
vendor 落点重定向（会写真实 `static/vendor/self@*/`）、branding 库重定向、
**Redis 隔离**。

**其中 Redis 最严重**：主 `app_config.json` 的 `redis.enable` 为 `true`
（db 6、key_prefix `webreport_`），无隔离时**测试进程会连生产 Redis 读写真实
快照**，断言依赖进程外状态、换个执行顺序就表现不同。现已在 `tests/__init__.py`
把 Redis 一律视为「关闭」；需要 Redis 的用例自行 patch
`redis_cache.get_redis_config` 或用 `reset_redis_manager` 显式注入。

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

| 级别 | 范围 | 规则 |
|------|------|------|
| L0 | 单用例/单文件 | 改动后先跑最小范围 |
| L1 | 同大模块相邻文件 | L0 绿后再放大 |
| L2 | 分段全量 | 按大模块顺序**依次**分段跑，防单次 discover 整体超时 |
| 重复全量 | — | **禁止**：L2 已过且代码未再变，任务内不必反复全量 |

- 大模块顺序见 `AGENTS.md`「L2 大模块顺序」：静态分析 → 筛选/变换 → 配置数据 → 报表导出 → API → UI → 认证审计 → 缓存调度 → 服务杂项。
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

开发/测试中，**同一问题**（同一断言、同一报错、同一现象）连续 **2 次**未解决：

1. **立即停**：禁止第 3 次盲目修改或重试。
2. **只分析**：完整报错、最小复现、涉及模块/共享语义、是否 #9 过时测试或 #10 路径问题、知识库易踩坑是否命中。
3. **写根因假设**：一句话能解释两次失败；解释不了则继续想、仍不改码。
4. **再改一次**：有假设后做针对性修改，用 **L0** 验证；再失败视为假设被证伪，回到第 1 步。

禁止：无假设连环重试、靠全量碰运气、未理解就改断言掩盖产品 bug。

**工具层同样适用**（R2 教训）：同一工具调用**失败 2 次**禁止原样重发；**被中断的调用不计失败次数**，恢复时先 status 查上一动作是否生效、再换法（与根 AGENTS #12 工具层口径一致）。

## 多子代理协作与验证纪律（硬性 #13–#14）

R2 轮实际事故沉淀，细则见根 `AGENTS.md` 同名节：

- **派发**：同任务至多一个活跃子代理；spawn 前 Task/Actor 盘点、成功后记 actor_id；一条消息只 spawn 一次；重派前 cancel+status+mtime 三确认（**cancel 回执不作数**）；brief 只写增量、通用协议引用 AGENTS/特性文档；**每次 spawn 必含简报五件套**（必读顺序 / 先 Memory+History 检索后探索 / 上下文包 / 环境事实 / 效率预算），禁止让子代理从零摸索。
- **验证**：跑测前先查 `status`——**无活跃写入者直接跑**（免采样），有写入者才采样等待（间隔 5–10s、≤3 次，到顶→阻塞汇报）；测试输出落 `/tmp` 日志再 grep、中断后读文件不重发；**同一测试段执行上限 2 次**（首跑+收口复跑；按测试文件集合计数、**代码变更即重置**，与 #14/#15 同口径）；截图单轮矩阵、唯一文件名、禁 rm、**落盘即校验大小/md5（同页 md5 重复=重拍 1 次上限，仍无效→按 #12 找根因）**。
- **UI 截图必须过一致性回验**（R3 新增，用户纠正）：截图与 HTML 渲染不一致时，任何基于图的 CSS 判断无效。管线 = `docs/compose/spec/shots/r3/shot-verify.mjs`（CDP 单视口截图、**禁滚动拼接**；截后把 PNG 画进 canvas 按 DOM 坐标取像素，与 `getComputedStyle` 色值比对，容差 12；角标红/绿点验对齐；FAIL 非零退出）。本容器一次性 `chrome --screenshot` 必挂（最小 data: 用例也超时），只走 CDP，且 CDP server 随 shell 回收——须同命令内「启动→轮询 /json/version→执行→kill」。预览通道（read_image）错位时**禁止多轮读图取证**（#12 口径）：1 次复测失败即改用像素回验/数值断言。
- **预算（硬性 #15）**：同段测试 ≤2 次、轮询必带判据与上限、禁把重跑测试当 sleep；单页 ≤40 轮/代理 ≤120 轮 + spawn `timeout_ms`（25min 先 send 催收口、30min 硬顶）；父会话 turnCount>150 必须介入；status 巡检间隔 ≥5min、上限 6 次。（R2 实测：同一条静态分析测试每 9 秒重跑 23+ 次、代理 917 轮——无退出条件的轮询是头号浪费。）
- **中断恢复**：工具被中断先 `status` 查上一动作是否生效，禁止原样重发；阶段转换输出一次进度表。

## 测试基座

```python
from tests import BaseConfigTest, BaseReportTest, make_config_db, init_test_db
```

- 导出经 `tests/__init__.py`
- `tests/test_base.py`：**硬编码 DDL**，故意不 import `db`（防循环依赖）→ 改 schema 必须三处同步
- `tests/htmlcheck.py`：HTML 结构（form 嵌套、标签配对）
- `tests/preset_test_cases.json`：预设夹具
- `tests/integration/`：真层；无 DEBUG 配置 skip；MySQL 不通 skip

## 禁止提交的运行时/本地物

`app_config*.json`（非 example）、`config.db`、`audit.db`、`venv/`、`static_cache/`、`.codegraph/`、`docs/`、`AGENTS.md`、`.mimocode/` 等（见 `.gitignore`）

## 推荐验证顺序（改完）

1. L0 相关单测（单文件/单用例）→ 通过后 L1 模块组
2. 需要完整确认时：L2 按大模块顺序分段跑（见 AGENTS.md）；代码未再变则全量**一次即可**
3. 可选对账：`python -m unittest discover -s tests/ -v`（仍勿反复）
4. 知识库同步 + 需要时 bug_hunt 变异脚本

无 CI / 无 lint / 无 typecheck 配置。

## 跨模块一致性测试优先覆盖

- 筛选语法：`test_filter_help`、`test_result_transform`、`test_nested_filter`、`test_exclusion_engine`
- 写护栏：`test_write_guard`、`test_sql_write_detect`
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
16. **discover 忘加 `-t .`** → `tests/__init__.py` 不执行，整套测试隔离失效（含连生产 Redis）。见上文「`-t .` 不能省」
17. **测试依赖进程级全局状态而未清理**：`report._query_cache`（L1）、`query_executor` 连接池。导出改走 `execute_report`（C-4）与连接池（C-2）后，写相关测试必须在 `setUp` 清 `report._query_cache.clear()` + `query_executor.clear_pools()`，否则会读到别的用例的 mock 数据——**症状是「换个执行顺序就过不过」**
18. **characterization 测试的期望值靠推导** → 必须用**未改动的实现实测**得出。2026-09-29 实测中就抓到过推导错误（数字字符串排序我以为返回 float，实际返回原字符串，变的只是行序）

## 文档过时线索（AGENTS.md 已提醒）

- README「项目结构」可能仍写 `AGENTS.md` 存在、列出 `git-purge.sh` —— 以当前目录为准
- README 测试树不完整 —— 以 `tests/` + discover 为准
- 文档冲突 → 改文档（中英同步）

---
最后核对：`AGENTS.md`（硬性约束 #8–#10、#12–#14 + 测试策略 + 两败必停 + 多子代理协作与验证纪律）+ `tests/` 目录；2026-09-29 执行层性能优化同步（`-t .` 隔离、进程级全局清理、`scripts/perf/` 工具链、characterization 测试纪律、易踩坑 #16–#18）
