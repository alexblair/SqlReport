# MEMORY — SqlReport 项目记忆

> 本文件是**跨会话记忆**，每轮开工前必读。Rules = 硬约束（违反即返工/浪费），
> Discovered = 环境事实（别再从零摸索）。

## Rules（用户纠正 + 本轮复盘结论，全部可执行）

1. **证据分级铁律**：程序化断言 > 数值输出 > 图像内容。UI 判断只用前两者。
   `read_image` 显示内容与文件 sha256 不符 → **1 次即止**，立即改用 CDP 提取
   几何/计算样式（`shots/r3/.facts.mjs`、`.treediff.mjs`、`.verify-fix.mjs`），
   禁止第 2 次读图取证。（本轮因反复读图多耗约 6 轮往返）

2. **开工先检索，后动手**：任何任务**首次调用必须是"检索已有资产"**——
   读本文件 Discovered + `docs/compose/knowledge/08-testing-conventions.md` +
   `ls docs/compose/spec/shots/*/` 找现成脚本。本轮未检索，截图工具链从零摸索
   约 10 轮往返（chrome --screenshot 必挂 → 转 CDP → 写 WS 客户端 → 调试
   server 回收 → …）。**先花 1 次调用检索，可省约 1/3 往返。**

3. **照抄确认稿前必做结构 diff**：确认稿与生产的同名 class **数量/位置可能不同**。
   做法：`grep -c 'class="X"' 确认稿.html` vs 源码渲染数量，不一致先问用户或先改结构。
   （本轮 `.spacer`：生产每个导航组后 1 个共 4 个 vs 确认稿仅 1 个 → 改 `flex:1`
   后 4 个 spacer 各撑 283px，侧栏大段空白事故，用户两次反馈才定位）

4. **一次性脚本必须自检**：生成产物后**立即 assert 并打印关键值**。
   铁律：① 禁硬编码会变的值（vendor hash 用 `self@[0-9a-f]+` 正则匹配）；
   ② 断言必写（本轮漏写断言导致改 CSS 后重跑的是旧 HTML，测了 3 轮才发现）；
   ③ 最小用例先跑通再批量（本轮 JS 占位符/正则各错 1 次）。

5. **几何问题先算后改**：列宽/溢出/换行/圆角类问题，先写预算公式（见 Discovered
   列宽预算）**一次性改到位**，禁止"改 CSS → 重新生成 → 启浏览器 → 跑矩阵"多轮
   迭代（本轮列宽迭代 3 轮、每轮一次全链路）。

6. **编辑三拍不可省**（AGENTS #16 P3）：`old_string` 必须**逐字复制**自 Read 输出。
   本轮 3 次 Edit 锚点失败（函数签名漏 `-> str`、正则漏收尾 `">`）＝ 3 次白跑。

7. **测试时机**：只在**最终代码态**跑一次 L0+L1；中间态用 CDP 数值断言代替
   （快两个数量级且能定位问题）。代码未变禁止重跑（AGENTS #14）。

8. **UI 截图管线固定**：`docs/compose/spec/shots/r3/shot-verify.mjs`
   ——单视口截图（**禁滚动拼接**）+ 截后像素↔DOM 回验（角标对齐 + 计算样式取色，
   容差 12），FAIL 非零退出。**禁止手拍未验证图，禁止用未验证图做 CSS 结论。**

9. **卡住即外部求援**（用户 2026-09-29 新流程）：训练未覆盖 + **2 轮未解** →
   立即停止猜测循环，产出**自包含**《咨询文档》MD 交用户联网检索回填
   （模板 `docs/compose/consult/TEMPLATE.md`）。文档必须文字化：目标/项目背景与
   技术约束/现象带实测数值/逐轮尝试与效果/精确 query/严格答案格式与禁忌——
   对方 AI **无法访问本项目任何文档、代码、截图、运行环境**。

10. **需求歧义先问，不产文档**：若卡点是"以哪版为准"（选择/裁决）而非技术未知，
    直接问用户 1 个选择题（1 次调用），比写咨询文档快且准。本轮左树基准即如此处理。

11. **文档分层铁律（用户 2026-09-29 纠正）**：`AGENTS.md` 只放「**每次任务都要读**」
    的最小集——硬性约束条目 + **入口引导路由表** + 环境命令 + 收尾检查单。
    凡「只在特定类型任务才需要」的流程全文（UI 四阶段、两败必停、多代理协作、
    L2 命令表、表结构变更、模块表…）一律进 `docs/compose/knowledge/` 分卷。
    判断标准一句话：**新内容默认进分卷；只有「不读就会做错，且每次任务都会遇到」
    才进 AGENTS.md**。新增分卷须同步三处：`knowledge/INDEX.md` §8、
    `knowledge/README.md` 索引表、`AGENTS.md` §2 分卷表。
    （本次实测：AGENTS.md 395 → 141 行，内容零丢失、24 项关键条目逐条复核留存；后续随硬约束 #17–#19 增补已增至 156 行，以 `wc -l AGENTS.md` 为准。）

12. **交互类改动必须验「两种载入态 + 多轮 + 组合」**（2026-09-30 用户实测教训）：
    「整页加载后点一次」看不见三类失效：**换页态**（无刷新导航后 `innerHTML` 不执行内联
    `<script>`、不重跑 init → `addEventListener` 交互静默失效，而内联 `onclick` 仍可点）、
    **第二/三次操作**（先隐藏再还原再排序）、**组合操作**（字段顺序×筛选×排序×导出）。
    落地：AGENTS 硬性 #17、`knowledge/06-ui-interactions.md` 验收清单 + 失败模式库、
    门禁 `tests/test_ui_tokens.py::TestPageInitRegistration`、E2E `scripts/ui-v2/e2e/swap-reinit.mjs`。

13. **能机械检测的绝不写进口头约定**（累计 5 条新门禁）：同一规则内重复声明属性、
    新 init 未进 `initPage()`/裸绑 `DOMContentLoaded`、同名控件混用类型、JS 块注释 `*/`。
    且**新门禁必须自证有效**：`venv/bin/python tests/bug_hunt/gate_redproof.py`
    （把历史缺陷打回去必须失败、还原必须通过；**5/5** 才算数）。从未失败过的门禁等于没有。

14. **改 `render.py`/`report.py`/`config.py` 后必须重启服务再验**：内联 JS 由内存直出；外链公共
    CSS/JS 走 `ensure_common_assets` 的**内容哈希目录 + 进程级 URL 缓存**（`_COMMON_ASSET_URLS`），
    不重启进程 URL 不变、改了也看不到（换 hash 目录不影响旧页面）。交付前提醒硬刷新。
15. **查代码先走 codegraph，改完代码先 sync**（2026-09-30 用户硬性要求，AGENTS #18/#19）：
    `codegraph explore "<中文意图 + 代码词>"` 一次拿到源码 + 调用链 + 波及面，通常就是唯一需要的调用；
    **只有查不到才降级** `grep`/`read`，且降级前先把查询**加宽重试**（补符号名/文件名/英文技术词）。
    改完任何 `.py`/`.js`/`.mjs` **同一次任务内**跑 `codegraph sync`。完整命令表与降级白名单见
    `knowledge/09-agent-workflow.md`「代码检索纪律」。

16. **写判定第三个易漏形状：`SELECT … INTO OUTFILE` / `INTO DUMPFILE`**（2026-10-05）：
    两个判定函数的第一道判据是「首关键词落在读白名单 `{SELECT,SHOW,DESCRIBE,DESC,EXPLAIN}` 就当读」，
    而关键词集合里从来没有 `OUTFILE`/`DUMPFILE` → 写 **MySQL 服务端磁盘** 的语句被当成纯读，
    `allow_write=0` 被绕过（`/report` 只要求登录、不要求管理员）、缓存也会短路它。
    修法：判定挂在**相邻关键词对** `(INTO, OUTFILE|DUMPFILE)` 上，插在读白名单分支**之前**
    （只把 OUTFILE 加进关键词集合**无效** —— 首关键词分支先 `continue` 了）。
    反向必须继续判读：`SELECT … INTO @变量`（会话级）、`'INTO OUTFILE'` 字面量、`OUTFILE_COL` 标识符。

17. **版本线纪律（2026-10-05）**：`V1` 冻结（GitHub ruleset `V1-freeze`，id 24514074，禁 update/删除/强推）、
    `V2` 为默认分支并承接全部后续提交；开发/发版只进 V2，发版打附注 tag 后显式推送，**禁止向 V1 推送**。
    用户侧「取哪一版 / 怎么切换」的单一来源是 `docs/version-switch-guide.md`（改动须同步双 README + `01-architecture.md`）。

18. **展开/收起类交互：CSS 必须认 JS 实际切换的类，且要到「元素级」**（2026-10-06）：
    用户报「`/config/api-endpoints` 展开 收起 失效」：按钮文案会变、面板恒 `display:none`。
    根因是 ad109be（UI v2 落公共 CSS）只抄确认稿类名 `.api-row.open`，而生产 `apiToggleMore`
    切的是 `.api-more` 上的 `.on`；同一提交还删了 `.tree .kids{display:none}`＋`.kids.on`→分类树折叠同款失效。
    **类名全局存在不等于该元素可用**（`on` 在 `.side-panel` 上有效，在 `.api-more` 上是空的），
    所以门禁必须元素级：`TestRevealClassContracts` + 浏览器实测 `scripts/ui-v2/e2e/api-row-expand-check.mjs`。
19. **Token 预算三铁律（2026-10-06 会话复盘，硬性 #20）**：4 个历史会话 Σtotal **69.7M tokens**，
    其中 **98.6% 是历史重发**（cacheRead），output 仅 0.58% → **成本 ≈ 步数 × 上下文**。
    ① 单条返回 >8k 字符即超阈：一条全库 `grep`（225 命中 / 43k 字符）让该步加 16.3k tokens、
    被后面 143 步重发 ＝ **2.33M tokens（该会话 9.7%）**；先 `grep -c` 计数、`head` 截断、`read` 带 `offset/limit`。
    ② 独立调用**同步发**：会话 1 有 118/147 步只发 1 个调用；每减一步省「该步上下文 + 约 1.6 万固定开销」。
    ③ 单会话 >60 步或上下文 >120k tokens → 落盘交接（`docs/compose/reports/`，随任务提交）换新会话（长会话是二次成本）。
    ④ `write`/`edit` 会回显改动后全文（大文件一步 19.9k tokens）→ 放会话后段、一次批量改完。
    自查：`venv/bin/python scripts/agent/session_cost.py --last 1`；详见 `10-token-budget.md`。
20. **探索性命令必须限长；工具环境配方优先固化成脚本；edit 锚点是闭区间**（2026-10-09 本轮自查，实测数字）：
    ① 区间/切片命令写错 = 把一整行刷屏：`awk 'NR=792,NR=812'`（`=` 是赋值）把第 812 行打印数百次，
    叠加 `git show --stat` 的截断输出，单步 +19,128 tokens、被后面 102 步重发 ＝ **1.95M tokens（该会话 14.8%）**。
    规矩：探索/统计类命令先 `grep -c`/`wc -l` 计数再取数，区间写 `NR>=a && NR<=b`，输出必带 `head`/`sed -n` 窗口。
    ② 同一工具/环境失败 2 次就**停止换参数**，改控制变量 A/B（一次只变一个），否则整轮空转——
    本轮无头 Chrome 取证把 `headless` 模式/profile/`window-size`/PIPE 四个变量一起换，空转约 16 步（113 步的 14%）。
    配方已固化：`scripts/ui-v2/e2e/probe_computed_style.py` + 08 卷易踩坑 #28 + 10 卷追加账本。
    ③ `edit` 的 `anchor_from..anchor_to` 是**闭区间**，锚点行本身也会被替换，`replace_with` 必须把锚点行内容一起写回，
    否则整行/整函数被静默删掉（本轮犯 3 次：删 `class TestNoDuplicateDeclarations` 行、删 `run_chrome_base` 与
    `extract_balanced_card` 函数体）。大段替换不确定时，整文件 `write` 一次比重试锚点更省。

## Discovered（环境事实）

- **DSH 会话记录可直接读（复盘数据源）**：`~/.dsh/sessions/--<cwd 的 / 换 ->--/session-*/session.v4.jsonl.zstd`
  （用 `zstd -dc` 解压；本机无 python `zstandard` 模块）。每条 `assistant/message` 带真实
  `usage`（input / cacheRead / cacheWrite / output / total），`data.stream` 是流式回放产物、**不进模型上下文**。
  会话标题在 `~/.dsh/storages/session_projcache/sessions/<id>.json` 的 `record.rows.title.val`；
  `storages/usage_history.json` 只有**按天**聚合，没有按会话用量——按会话要用 `scripts/agent/session_cost.py`。
- **每步注入的提示词有两个来源**：项目根 `AGENTS.md`（2026-10-06 起入库）与**全局 `/root/.dsh/AGENTS.md`**（仓库外，superpowers 引导 + 全局文档裁决规矩）。两者都每步重发：实测某会话 `agent-instructions` 达 **25,022 字符**（两个文件叠加）。全局文件已于 2026-10-06 从 **6,206 → 4,050 字节**（−35%，只留「不加载技能就会做错」的最小集，完整技能内容改用 `skill using-superpowers` 按需加载）。
- **外部已起的 8099 实例：本会话看不见也重启不了**（bash 跑在 `bwrap --unshare-pid` 里，`pgrep`/`ss -ltnp`
  都看不到宿主的 server.py；`./test_env.sh restart` 会因“端口被本命名空间外进程占用”拒绝）。
  需要验证代码改动时：另起隔离实例（`run-logs/` 内 gitignore 目录）——
  `DEBUG_CONFIG_FILE=run-logs/probe/verify.debug.json HOST=127.0.0.1 PORT=8098 venv/bin/python -u server.py`
  （配置里 `scheduler.enable=false` 避免与宿主实例双跑定时任务，`redis.key_prefix`/`audit_db`/`static_cache` 都指向 `run-logs/probe/`）。
  浏览器验证则用 headless Chrome：`/opt/chrome-offline/chrome-linux64/chrome --headless=new --no-sandbox
  --remote-debugging-port=9411 --user-data-dir=run-logs/probe/chrome about:blank`（**必须用后台作业**跑，
  普通 `&` 会随 bwrap 退出被杀）。

- **codegraph（本机 v1.4.0）**：符号级知识图谱已建好（137 文件 / 6894 节点 / 17453 边），`codegraph status`
  可看 `pendingChanges`。**只索引 `.py`(126) + `.js`/`.mjs`(11)**——`.md`/`.json`/`.html`/`.css`/`.sh`
  一律不索引，查这些直接用 grep/read。**`explore` 按代码词（符号名/文件名/英文词）匹配，纯中文问句
  一律 0 命中**——看到 `No relevant code found` 要补代码词重试，不是降级 grep 的理由。
  **后台守护进程已死**（`.codegraph/daemon.pid` 记 pid 7216 / v1.3.1，进程早已不存在），
  **没有自动同步**——改完代码必须手动 `codegraph sync`（增量 <1s）。
  按内容哈希判定，只 `touch` 文件不会变脏；`codegraph index` 全量重建 137 文件为**秒级**，
  但**必须在单条命令内跑完**（后台起会被沙箱杀掉，索引卡在 `state=indexing`，需 `codegraph unlock`）。
- **截图**：一次性 `chrome --screenshot` 在本容器**必挂**（最小 data:URL 用例也超时）。
  可行路径 = CDP：同命令内 `nohup chrome --headless=new --remote-debugging-port=9333
  --user-data-dir=... &` → 轮询 `curl /json/version` → node 脚本（Node24 内置全局
  `WebSocket`）→ `kill`。**CDP server 随 shell 退出被回收，严禁跨命令复用。**
- **会话预览通道（read_image）会返回错位图像**（声明 sha 与显示内容不符）→
  图像内容不可作为证据（见 Rules 1）。
- `/tmp` 被环境周期清空 → 产物落仓库内目录（`docs/compose/spec/shots/r3/`）。
- 演示数据：`preset_cases.import_preset_from_file(conn)` 导入 7 报表/3 分类/2 池；
  本地 `config.db` 是空库，截图前需导入。
- **生产侧栏每组后各 1 个 `.spacer`（4 个），确认稿仅 1 个** → 账号区吸底必须用
  `.account{margin-top:auto}`，**禁改 spacer 为 flex:1**。
- **报表页列宽预算**：右栏可用宽 = 视口 − 侧栏240 − 容器padding48 − 左树260 − 间距16。
  验收线：**1280/1366/1440/1920 全部零横向溢出**（`tablesOver=[0,0,0,0]`，
  操作列右缘 < 视口宽）。列宽最终值：SQL 112 / 名称 min 60 / 备注 70 / API 56 /
  chip 96 / 单元格 padding 5px。
- **嵌套层级样式（2026-09-30 UI v2 起已改口径）**：内联 `style="margin-left:24px;border-left:3px solid #c7d2fe"` 已清理，层级改由 `.cat-children` class 承担；`tests/test_render.py` 现断言 class / `.kids`，**不再需要 `!important`**（旧条目「被 `:1742` 锁定、CSS 无法覆盖」已失效）。
- **写判定有两个函数，别再混用**（2026-10-05）：`sql_contains_write`（严格，服务权限/警示/403）
  与 `sql_has_persistent_write`（精确，只服务缓存读门槛与静态护栏）。踩过两次：
  ① 报表 35 的 9 条 `SET @…` 全带前导块注释（`/*** c ***/ SET @x := …`），在**裸文本**上
  做 `^\s*SET\s+@` 正则会全部落空 → 必须用「首关键词结束偏移 + 跳过空白/注释」定位；
  ② `WITH` 语句里的 `REPLACE(`/`INSERT(` 是 MySQL 字符串函数，扫描写动词时必须排除
  「紧跟 `(`」的关键词，否则纯读 CTE 报表（#17）会被判成写而永久跳过缓存。
- **静态护栏是并集不是替换**：`(allow_write=0 且含写) 或 含持久写` → 回退普通链路。
  只判持久写会放行 `allow_write=0` 的会话级脚本，形成权限旁路。
- **本地 debug 栈可直接用**（2026-10-05 核实订正）：调试配置就是工作树里的
  `app_config.debug.json`（被 gitignore），也是 `app_config.py:41` 的**默认**路径 ——
  不设任何环境变量即可激活（Redis db0/前缀 `sr_debug`、
  sqlite `config.debug.db`、数据池指向 `127.0.0.1:3307/sqlreport_test`）。
  **旧文档里的 `DEBUG_CONFIG_FILE=app_config.debug.json1` 已不存在**（本机实测无此文件，
  照抄会白跑一轮）；只有要换用别的配置文件时才需要设 `DEBUG_CONFIG_FILE`。
- **静态分析门禁会拦跨脚本 import**：`scripts/perf/*.py` 之间只能用点号包路径
  （`from scripts.perf.x import y`），顶层模块名（`from x import y`）会被判
  「无法导入模块」且**没有 noqa 豁免**（`tests/bug_hunt/static_analyzer.py`）。
- **`run-logs/` 里的克隆副本会污染静态分析门禁**（2026-10-06 实测）：`static_analyzer.IGNORE_DIRS` 不含 `run-logs/`、`perf-logs/`，
  放在里面的 `git clone`/`git worktree` 副本会被扫到，其 `tests/__init__.py` 的包内相对导入被判「无法导入模块 test_base」→
  全量 discover 里 `test_static_analysis.test_no_import_errors` 报 ERROR（本轮 3009 项唯一失败即此，产品代码零回归）。
  跑全量前先确认 `run-logs/` 下无 `.py` 克隆产物（或把克隆放到仓库外），**不要**为此放宽门禁。
- **`cache_info.source` 自 2026-10-05 起 = 本次取数来源**（`mysql` / `process` / `redis` /
  `redis_fallback`；`snapshot_written` 仅 `mysql` 分支有，标记本次是否同时写了 L2 快照）。
  此前「MySQL 查询成功即标 `redis`」的账本式标注已修复（`report.py` 生产者 3 处：L1 写入入参
  + 两个 `cache_info` 字典；**渲染器未动**）。**注意**：`scripts/perf/bench.py` 的 S5 正式请求
  期望是 `process`（300s 内命中 L1），不是 `redis`；只有 L1 过期后命中 L2 才是 `redis`。
- **`git update-index --chmod=±x <file>` 会把该文件的工作树内容重读进索引**（2026-10-05 踩坑，导致一次 Critical）：
  用它修正环境性的权限位噪音（本仓库工作树有 316 个文件 644→755）时，会把该文件**全部未提交改动**
  （含他人在制品）一并暂存 → 提交后在**干净检出上自测失败**（当次：`tests/test_report_extra.py` 混入 ui-v2 的
  `import render` + 两条 CSS 常量正则断言，而 ui-v2 的 `render.py` 未提交）。
  正确做法：① 先精确暂存（`git apply --cached` 命中 hunk / `git add -p`）；② 权限位用
  `git update-index --chmod=-x --cacheinfo 100644,$(git rev-parse HEAD:<path>),<path>`，
  或重建索引条目 `git hash-object -w <target> && git update-index --cacheinfo 100644,<blob>,<path>`；
  ③ **改完必须验证「干净检出 HEAD 能自绿」**：`git worktree add --detach /tmp/x HEAD` 后跑受影响模块
  —— 工作树全绿 ≠ 提交自绿（工作树可能依赖未提交的他人在制品）。
- **「已写进文档的资产未入库」= 断链，测试拦不住**（2026-10-05 踩坑）：一次提交把 `README.md` 的 8099 本地测试环境章节（`./test_env.sh start/status/stop` 与结构树条目 `├── test_env.sh`）提了，但 `test_env.sh` 本体未入库——干净检出跑满 3002 例全绿，照样是个断链提交。
  **收尾必查**：本次新增/引用的文件名（README / spec / knowledge 里出现的路径）是否都在 `git ls-files` 里；`git worktree add --detach <dir> HEAD` 后 `grep -rlF <文件名>` 扫一遍。
- **判断「过程残留 vs 有效资产」用产出者溯源，不要靠文件名**（2026-10-05）：`docs/compose/spec/shots/` 下先查「哪个脚本 `writeFileSync` 写了它」——产出脚本**已提升进 `scripts/ui-v2/e2e/`** 的才是可复现交付物；只存在于 gitignored `run-logs/` 的过程脚本产出的（`live-*`、`panel-sort-applied`、`panel-export-fixed`）= 过程图，不入库。
  另：**同目录图先 `md5sum` 去重** —— `live-audit-1440.png` 与 `live-overview-1440.png` 字节完全相同（即「审计页截成了概览页」），且画面带「查询中…」遮罩是加载中态；不逐张看图 + 不看产出者，根本发现不了。

- **GitHub 操作慢时用本机代理 `http://127.0.0.1:6012`**（2026-10-05 用户指示）：直连 `git clone` 极慢
  （`--depth 1` 几分钟拉不完），设 `https_proxy`/`http_proxy`/`all_proxy=http://127.0.0.1:6012` 后 API 1.5s 返回。
  **clone 类命令一律加 `timeout` 并放后台作业**，禁止前台长阻塞（本会话因此被用户中断两次）。
- **GitHub 分支改名的重定向只覆盖网页/API，不覆盖 git 的 refspec 匹配**（2026-10-05 实测）：`main` 改名 `V1` 后
  `git ls-remote origin main` 为空、`git clone -b main` 直接失败、老 clone 的 `origin/main` 永不更新（假「Already up to date」）。
  冻结旧线的可核查依据是 `GET /repos/{o}/{r}/rules/branches/<branch>`（返回 `update`/`deletion`/`non_fast_forward`）
  与真实 push 被拒（`GH013: Repository rule violations found`）；**`git push --dry-run` 不触发规则检查，不能当冻结证据**。
  另：改默认分支（`PATCH /repos/{o}/{r}`）与建 ruleset 都需 admin 权限（本机 PAT 具备）。
- **浅克隆（`--depth 1`）里切另一条分支必须先补 refspec**（2026-10-05 实测）：`git fetch origin V1` 只写 `FETCH_HEAD`、
  不建 `origin/V1`，紧接着 `git checkout V1` 报 `pathspec 'V1' did not match any file(s) known to git`。
  正确：`git fetch --depth 1 origin V1:refs/remotes/origin/V1 && git checkout -B V1 origin/V1`（已写进切换指南 Q10）。
  另：浅克隆里往返切换时 `git status` 会报 branch 与 `origin/*` “diverged 1 and 1”，属浅历史噪音，不影响工作树。
- **tag `v2.0.0` 在首次交付前被重指过一次**：从 `1e0ea3a` 改指到定稿提交（目的是让「V2 首个正式版」自带版本切换指南）；
  重指发生在任何用户取用之前（仓库无 Releases、无消费者），**此后不再移动**；`v1-final` 自始至终只指向 `9a975b9`。

- **AOCI 认知层已接入本项目（2026-10-08）**：MCP 九工具 + CLI `.tools/bin/aoci`（**不在 PATH**；`.tools/`、`tools/aoci/` 均 gitignore）+ 只读面板 `http://127.0.0.1:8899`；**无 hook、不会自动同步**，受管对象含 `.md`，收尾在最终稳定态调一次 `aoci_maintain`；用法全文 `docs/compose/knowledge/11-aoci-usage.md`（硬性 #21）。面板「未配置数据库」属正常：Database 卷与 Code 卷独立，且 AOCI 数据源不支持 SQLite。
- **无头 Chrome（Chrome for Testing 154）在本机的取证配方**（2026-10-09 实测，踩完才通）：`--headless=old` 是唯一稳定模式
  （`--headless=new` 跑 `--dump-dom`/`--screenshot` 直接挂起）；`--user-data-dir` 要复用同一个 profile 才稳（全新 profile 间歇挂起，重试一次即热）；
  **不能**用 `subprocess(capture_output=PIPE)`（fork 出的子进程不关管道 → 等到 timeout 的假挂起）；`--window-size`/`--virtual-time-budget`
  与 `--screenshot` 同用挂起；取证前要剥页面 `<script>`。已封装为 `scripts/ui-v2/e2e/probe_computed_style.py`（含 `--selftest`，一条命令出计算样式 JSON + 聚焦截图）。
  **补充（2026-10-09 实测）**：挂起只发生在 `--dump-dom`/`--screenshot` 这类**命令行一次性**模式；`--headless=new`
  + `--remote-debugging-port` + CDP（`Page.captureScreenshot`/`Runtime.evaluate`）稳定可用（本轮全程用它取证）；
  但 Chrome **必须以受管后台作业启动**（`nohup … &` 在单次 bash 调用结束时会被回收，症状是 CDP 端口先通后拒）。
- **隐藏页卡里的 mermaid 必须在页卡可见后再渲染**（2026-10-09 用户实测：`/report?id=42` 备注页卡两张流程图只剩空框）：
  `startOnLoad:true` 在 window load 时把 `display:none` 页卡里的 `<pre class="mermaid">` 也渲染了 —— 隐藏容器量测全 0，
  mermaid 产出 16×16 空图（viewBox `-8 -8 16 16`）并打上 `data-processed`；事后 `mermaid.run` 对已打标记的节点直接 `continue`，
  切页也不重画。修法：`report._MERMAID_INIT_JS` 锁 `startOnLoad:false` + `_FOOTER_GLUE.renderTabMermaid`（`gotoTab`/`initReportPage` 都调）；
  门禁 `TestMermaidTabRenderContract`（已在 gate_redproof 第 10/11 条），e2e `scripts/ui-v2/e2e/mermaid-tab-check.mjs`。
- **执行效率治理（2026-10-09 复盘最近 2 个会话）**：两场各 147/149 步、23.0M/23.2M tokens，单调用步 **76%/73%**——纪律早有（#20②）却等于没触发；AOCI maintain 各调 2/3 次被后轮取代。
  已落实机械拦阻：`session_cost.py` 新增 `--check` 一行体检与「批处理率」「AOCI maintain 次数」两个指标；AGENTS.md #20 增设⑤中途体检⑥收尾批量取证；
  10 卷新增第二批实测与 R2 阈值（单调用步 ≤40%）；11 卷增设 maintain 次数判据（中间态/重复调用即违规）。
  另注：会话内**整读大文件**（如 300 行工具源码）会按剩余步数反复重发，应 `read offset/limit` 分段取。
