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
    （本次实测：AGENTS.md 395 → 141 行，内容零丢失、24 项关键条目逐条复核留存。）

12. **交互类改动必须验「两种载入态 + 多轮 + 组合」**（2026-09-30 用户实测教训）：
    「整页加载后点一次」看不见三类失效：**换页态**（无刷新导航后 `innerHTML` 不执行内联
    `<script>`、不重跑 init → `addEventListener` 交互静默失效，而内联 `onclick` 仍可点）、
    **第二/三次操作**（先隐藏再还原再排序）、**组合操作**（字段顺序×筛选×排序×导出）。
    落地：AGENTS 硬性 #17、`knowledge/06-ui-interactions.md` 验收清单 + 失败模式库、
    门禁 `tests/test_ui_tokens.py::TestPageInitRegistration`、E2E `scripts/ui-v2/e2e/swap-reinit.mjs`。

13. **能机械检测的绝不写进口头约定**（本轮 4 条新门禁）：同一规则内重复声明属性、
    新 init 未进 `initPage()`/裸绑 `DOMContentLoaded`、同名控件混用类型、JS 块注释 `*/`。
    且**新门禁必须自证有效**：`venv/bin/python tests/bug_hunt/gate_redproof.py`
    （把历史缺陷打回去必须失败、还原必须通过；4/4 才算数）。从未失败过的门禁等于没有。

14. **改 `render.py`/`report.py`/`config.py` 后必须重启服务再验**，否则验的是内存里的旧 HTML；
    交付给用户前提醒硬刷新（HTML 已 `no-store`，但用户标签页可能已在跑旧脚本）。
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

## Discovered（环境事实）

- **codegraph（本机 v1.4.0）**：符号级知识图谱已建好（146 文件 / 6870 节点 / 17278 边），`codegraph status`
  可看 `pendingChanges`。**只索引 `.py`(121) + `.js`/`.mjs`(25)**——`.md`/`.json`/`.html`/`.css`/`.sh`
  一律不索引，查这些直接用 grep/read。**`explore` 按代码词（符号名/文件名/英文词）匹配，纯中文问句
  一律 0 命中**——看到 `No relevant code found` 要补代码词重试，不是降级 grep 的理由。
  **后台守护进程已死**（`.codegraph/daemon.pid` 记 pid 7216 / v1.3.1，进程早已不存在），
  **没有自动同步**——改完代码必须手动 `codegraph sync`（增量 <1s）。
  按内容哈希判定，只 `touch` 文件不会变脏；`codegraph index` 全量 146 文件仅 **3.1s**，
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
- **嵌套层级容器样式须 `!important`**：模板 inline `style="margin-left:24px;
  border-left:3px solid #c7d2fe" 被 `tests/test_render.py:1742` 锁定，CSS 无法覆盖。
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

