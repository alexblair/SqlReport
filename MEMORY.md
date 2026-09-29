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

## Discovered（环境事实）

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
  border-left:3px solid #c7d2fe"` 被 `tests/test_render.py:1742` 锁定，CSS 无法覆盖。
