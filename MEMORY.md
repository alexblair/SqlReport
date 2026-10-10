# MEMORY — SqlReport 项目记忆

> 本文件是**跨会话记忆**，每轮开工前必读。**只放两类**：① 用户直接纠正/指示（含不可违背的禁忌）；② 不可从代码或约束推断的环境事实。
> **准入判据**：新条目默认**不进本文件**——能进 `AGENTS.md` 硬约束或 `docs/compose/knowledge/*` 分卷的，一律进那边（单一来源）。
> **淘汰判据**：已被分卷/硬约束覆盖、或已失效过期的条目**立即删**；同类条目合并；长条目只留不可推断的要点 + 指路。
> **策展时机**：本任务改过本文件或 `AGENTS.md` → 收尾**顺手删过期/重复条目**（不是顺手加内容）。
> **门禁兜底**：`tests/test_doc_budget.py` 校验本文件的体积、条数、每条归属标记与重复行；`AGENTS.md` 同样受体积与条数门禁约束。
> `AGENTS.md` 是**主入口，只留「不读就会做错」的结论**：加任何内容前必须先等量压缩或把细节移进分卷，**不许抬上限**。

## Rules（用户纠正 / 指示）

1. **证据分级铁律（用户铁律）**：程序化断言 > 数值输出 > 图像内容，UI 判断只用前两者。**`read_image` 预览会返回错位图像（与文件声明 sha 不符）→ 一次即止**，改用 CDP 取几何/计算样式；**禁止用未验证截图下 CSS 结论**（判据见 `06-ui-interactions.md`「取证成本纪律」）。
2. **改 UI 先代码层定位，浏览器取证按需（用户 2026-10-09 指示）**：Chrome/CDP 证据最硬但最慢（十秒~分钟级）；能代码层定性的不截图；需要运行时计算样式/几何/交互证据时才起浏览器，且**一次会话批量验完**，禁止"改一行截一次图"。
3. **用户要求与「最新依据」冲突时立即确认（用户 2026-10-09 指示）**：停下问一个选择题，不自我怀疑兜圈（反例：改 UI 时执着对比历史 shot 图）；裁决按「当次指示 > AGENTS.md > 最新生效 spec > 旧 spec/plan」，**历史设计图只是取证**。
4. **文档分层铁律（用户 2026-09-29 纠正）**：`AGENTS.md` 只放「每次任务都要读」的最小集（硬约束 + 入口路由 + 环境命令 + 收尾检查单）；「只在特定任务才需要」的全文进分卷。**新内容默认进分卷**，只有「不读就会做错且每次都遇到」才进 AGENTS.md。
5. **卡住即外部求援（用户 2026-09-29 流程）**：训练未覆盖且 **2 轮未解** → 停止猜测循环，产出**自包含**《咨询文档》交用户联网检索（模板 `docs/compose/consult/TEMPLATE.md`）：目标、项目背景与技术约束、现象带实测数值、逐轮尝试与效果、精确 query、答案格式与禁忌——对方无法访问本仓库。
6. **需求歧义先问，不产文档（用户指示）**：卡点是「以哪版为准」（选择/裁决）而非技术未知时，直接问一个选择题（1 次调用）比写咨询文档快且准。
7. **版本线纪律（用户指示）**：`V1` 冻结（GitHub ruleset `V1-freeze`，id 24514074）、`V2` 为默认分支承接后续提交；**禁止向 V1 推送**；切换口径唯一来源 `docs/version-switch-guide.md`。
8. **改 `render.py`/`report.py`/`config.py` 后必须重启服务再验（实测 2026-09-30）**：外链公共 CSS/JS 走内容哈希目录 + 进程级 URL 缓存（`_COMMON_ASSET_URLS`），不重启看不到变化；交付前提醒用户硬刷新。
9. **照抄确认稿前必做结构 diff（用户两次反馈才定位）**：确认稿与生产的同名 class 数量/位置可能不同——`grep -c 'class="X"'` 对比源码渲染数量，不一致先问用户或先改结构。
10. **`edit` 锚点是闭区间（实测 2026-10-09）**：`anchor_from..anchor_to` 的锚点行本身会被替换，`replace_with` 必须写回锚点行内容；大段替换不确定时整文件 `write` 一次更省。
11. **线上库操作须限定范围；用户给的「某类操作没问题」前提必须实证（用户 2026-10-10 指示）**：线上 config 库（MySQL 3307）**只允许动用户指定报表（reports=43）或自建临时报表，禁止碰其他报表**（自建临时报表用完自清）；用户前提与语句级/日志证据冲突时**以证据为准并回报差异**——本次「已知新建报表未报错」不成立：日志里 id=43 刚建（14:53:07）即单删 500（14:53:44）。

## Discovered（环境事实）

- **DSH 会话记录可直接读（复盘数据源，实测 2026-10-06）**：`~/.dsh/sessions/--<cwd 的 / 换成 ->--/session-*/session.v4.jsonl.zstd`，用 `zstd -dc` 解压（本机无 python `zstandard`）。每条 `assistant/message` 带真实 `usage`；会话标题在 `~/.dsh/storages/session_projcache/sessions/<id>.json` 的 `record.rows.title.val`；按会话统计用 `scripts/agent/session_cost.py`。
- **每步注入的提示词有两个来源（实测 2026-10-06）**：项目根 `AGENTS.md`（已入库）与全局 `/root/.dsh/AGENTS.md`（仓库外，superpowers 引导 + 全局文档裁决规矩），两者都每步重发、都计入上下文成本。
- **外部已起的 8099 实例本会话看不见也重启不了（实测 2026-10-05）**：bash 跑在 `bwrap --unshare-pid` 里，`pgrep`/`ss -ltnp` 看不到宿主 `server.py`，`./test_env.sh restart` 会以"端口被本命名空间外进程占用"拒绝。要验证改动就另起隔离实例：产物与配置都放 `run-logs/` 内，`DEBUG_CONFIG_FILE` 指向该配置，`scheduler.enable=false` 避免与宿主双跑定时任务，`redis.key_prefix`/`audit_db`/`static_cache` 也都指向该目录。
- **codegraph（本机 v1.4.0，实测 2026-10-06）**：**只索引 `.py` 与 `.js`/`.mjs`**，`.md`/`.json`/`.html`/`.css`/`.sh` 一律不索引（这些直接 grep/read）；`explore` 按代码词匹配，**纯中文问句 0 命中**（不是降级 grep 的理由）；**无守护进程、无自动同步** → 改完代码手动 `codegraph sync`；`codegraph index` 全量重建**必须在单条命令内跑完**（后台起会被沙箱杀掉、卡在 `state=indexing`，需 `codegraph unlock`）。命令表见 `09-agent-workflow.md`。
- **无头 Chrome 取证配方（实测 2026-10-09）**：命令行一次性模式 `--screenshot`/`--dump-dom` 在本容器**必挂**（`--headless=old` 是唯一稳定的一次性模式）；**不能用 `subprocess(capture_output=PIPE)`**（fork 出的子进程不关管道 → 假挂起到 timeout）；`--window-size`/`--virtual-time-budget` 与 `--screenshot` 同用也挂。稳定路线是 `--headless=new` + `--remote-debugging-port` + CDP（Node24 内置全局 `WebSocket` 即可连），但 **Chrome 必须以受管后台作业启动**、**CDP server 随 shell 退出被回收（严禁跨命令复用）**。已封装为 `scripts/ui-v2/e2e/probe_computed_style.py`（含 `--selftest`）。
- **本地 debug 栈可直接用（实测 2026-10-05）**：调试配置是工作树里的 `app_config.debug.json`（gitignore），也是 `app_config.py` 的默认路径——不设任何环境变量即生效（Redis db0/前缀 `sr_debug`、sqlite `config.debug.db`、数据池指向 `127.0.0.1:3307/sqlreport_test`）。**旧文档里的 `DEBUG_CONFIG_FILE=app_config.debug.json1` 已不存在**；只有要换配置文件时才需要设 `DEBUG_CONFIG_FILE`。
- **`run-logs/` 里的克隆副本会污染静态分析门禁（实测 2026-10-06）**：`static_analyzer.IGNORE_DIRS` 不含 `run-logs/`、`perf-logs/`，放在里面的 `git clone`/`worktree` 副本会被扫到 → 全量 discover 报 ERROR（产品代码零回归）。跑全量前确认 `run-logs/` 下无 `.py` 克隆产物，**不要为此放宽门禁**。
- **`git update-index --chmod=±x <file>` 会把工作树内容重读进索引（实测 2026-10-05）**：用它修权限位噪音时会把该文件**全部未提交改动**一并暂存 → 提交后在干净检出上自测失败。正确做法：先精确暂存（`git add -p` / `git apply --cached`），权限位改用 `git update-index --chmod=-x --cacheinfo 100644,$(git rev-parse HEAD:<path>),<path>`；改完必须用 `git worktree add --detach <dir> HEAD` 验证「干净检出 HEAD 能自绿」。
- **GitHub 操作慢时用本机代理 `http://127.0.0.1:6012`（用户指示 2026-10-05）**：直连 `git clone` 极慢；设 `https_proxy`/`http_proxy`/`all_proxy` 后 API 秒级返回。**clone 类命令一律加 `timeout` 并放后台作业**。
- **GitHub 分支改名的重定向只覆盖网页/API，不覆盖 git refspec（实测 2026-10-05）**：`main` 改名 `V1` 后 `git ls-remote origin main` 为空、老 clone 的 `origin/main` 永不更新（假「Already up to date」）。冻结旧线的可核查依据是 `GET /repos/{o}/{r}/rules/branches/<branch>` 与真实 push 被拒（`GH013`）；**`git push --dry-run` 不触发规则检查，不能当冻结证据**。
- **浅克隆切分支必须先补 refspec（实测 2026-10-05）**：`git fetch origin V1` 只写 `FETCH_HEAD`，紧接 `checkout V1` 报 `pathspec ... did not match`；正确 `git fetch --depth 1 origin V1:refs/remotes/origin/V1 && git checkout -B V1 origin/V1`（见切换指南 Q10）。浅克隆往返切换时 `status` 报 diverged 属噪音。
