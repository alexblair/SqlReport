# 复盘：UI v2 落地后的 14 类缺陷 + 防复发机制

> 时间：2026-09-30 · 范围：全站视觉改版（UI v2「石墨·鸢尾」）落地后，用户实测反馈驱动的 4 轮修复
> 目的：把「用户替我发现的每一个 BUG」和「我自己犯的每一个流程错误」变成**下次一定会拦住我的机制**
> 落地物：`tests/test_ui_tokens.py`（30 用例，本轮新增 4 条门禁）、`tests/bug_hunt/gate_redproof.py`（门禁自身的 RED-GREEN 证明）、
> `knowledge/06-ui-interactions.md`（失败模式库 + 强制自检）、`knowledge/08-testing-conventions.md`（验收脚本坑）、`AGENTS.md` 硬性 #17

---

## 一、结论（一句话）

本轮所有"隐藏"BUG 都指向同一个盲区：**我把"整页加载时点一下对"当成了"功能是对的"**。
单点、单次、整页加载的验收，看不见「换页态」「组合操作」「第二次交互」这三类失效；
而它们恰好是用户日常的使用方式。所以防复发的核心不是"更仔细"，而是：
**能机械检测的做成门禁（含"门禁自己被验证过"），判断类的做成提交前清单，且验收场景按用户操作序列设计。**

---

## 二、BUG 清单（用户可见 → 根因 → 拦截）

| # | 症状（用户原话） | 根因 | 现状 | 拦截机制 |
|---|---|---|---|---|
| 1 | SQL 代码块「背景色冲突、看不清」 | 深底与深字分属两条规则，`<pre class="sql-debug code-block">` 同时命中 → 正文 1.02:1 隐形 | 底色+文字色成对声明，正文 14.88:1 | `TestContrastGate::test_code_surface_pairs_bg_and_color`（对比度程序实算） |
| 2 | 「筛选框选完还带一个连带的文本输入框」 | 快筛行与列头筛选的 DOM 契约没对齐 | `.qf-row` 快筛行补齐联动 | 结构断言 + E2E `e2e-combo.mjs` |
| 3 | 「报表管理是重灾区」（名称列挤压、表头错乱、层级丢失） | 列宽由内联 `width` 承载，清理内联样式后语义丢失；`.sql-head` 被挪用为代码工具条 | 方案 A（分组卡+导轨+行卡片）+ `table-fixed`+`colgroup` | `TestReportsPageStructure`、`TestSingleSourcePolicy` |
| 4 | 「登录后直接被一个『查询中』的层遮住了所有」 | **同一条规则内**先写 `display:none` 又留 `display:flex`，后者胜 | 基础规则只保留 `none`，`.show` 才显示 | `TestOverlayDefaultsHidden` + **新增** `TestNoDuplicateDeclarations` |
| 5 | 「排序设置、字段设置功能丢失了，弹窗也没了」 | 生产 JS 加 `.on`，CSS 只认确认稿别名 `.open/.show` | CSS 两套都认 | `TestJsToggledClassesHaveStyles`（从 JS 源码反查 CSS） |
| 6 | 导出对话框三段被排成一行 | 生产是 `head/body/foot` 三个并列兄弟，按"单个盒子"写的 CSS | `.modal{flex-direction:column}` + 分段约束 | `TestJsToggledClassesHaveStyles::test_modal_supports_sibling_sections` |
| 7 | 「排序弹窗有了但配置结果未生效」 | 字段面板只在"少选了列"时才发 `cols`；各功能各自重建 URL，组合操作时 `cols`/`nested_filter` 被静默清空 | 恒发 `cols`；URL 统一由 `buildReportUrl()` 构造 | `test_report.py` 契约用例 + E2E `e2e-combo.mjs` |
| 8 | 「按钮点了没反应」且控制台无错误 | JS 块注释里写了 `f_*/op_*`，`*/` 提前结束注释 → 整块 footer 脚本语法错误 | 改写注释 | `TestInlineJsSyntax`（node --check 真语法校验） |
| 9 | **「隐藏 ID→还原→再排序，无法排序且拖动报废」** | 报表页自己复制了一份 `innerHTML` 换页：1) 不执行 `<main>` 内联 `<script>`；2) 不重跑 `addEventListener` 初始化。内联 `onclick` 仍可用 → "按钮能点、拖拽报废" | 换页收敛为唯一 `_swapMain` + `_reinitAfterSwap()`；页面级脚本改用 `onReady` | `TestNoRefreshSwapReinit` + **新增** `TestPageInitRegistration` + E2E `swap-reinit.mjs` |
| 10 | 排序项序号从 2 开始、移动/删除错位 | `#sortList` 的「暂无排序」占位块加项时不清除 → `children` 下标整体错一位 | 占位块受 `syncSortEmptyState()` 统管，序号按 `.sort-item` 重排 | `TestNoRefreshSwapReinit::test_sort_placeholder_managed` |
| 11 | JSON 导出字符集不符合既有约定 | 导出面板允许给 JSON 选 GBK | JSON 恒 UTF-8（`export.py:443`，ZIP 内亦然） | `test_export.py` 用例断言响应头 |
| 12 | 「你修了但用户那儿还是坏的」 | 动态 HTML 无 `Cache-Control`，标签页长期跑旧内联 JS | `_send_html` 加 `no-store`（`server.py:844`） | `TestHtmlFreshness` |
| 13 | 导出格式参数可能重复提交 | 隐藏镜像 `<select>` 与单选共用 `name="format"`，靠服务端"取第一个"侥幸正确 | 镜像控件去掉 `name` | **新增** `TestFormControlNameUniqueness` |
| 14 | `ReferenceError: onReady is not defined` | `onReady` 只定义在外链 common.js（defer，晚于 body 内联脚本） | 定义移到头部内联引导脚本，common.js 里改为幂等 | **新增** `TestPageInitRegistration`（同条规则） |

> 说明：#4 与 #14 是我在修 #1–#13 的过程中**自己引入**的回归。它们同样进了门禁——回归不是耻辱，
> 没有门禁才是。

---

## 三、我自己的流程错误（元层面，最该修的）

| # | 错误 | 代价 | 纠正 |
|---|---|---|---|
| M1 | **验收只做"整页加载后点一次"** | #9 从出现到被发现跨了 3 轮反馈，用户替我做了回归测试 | AGENTS 硬性 #17：交互改动必须验「整页加载」+「操作一次后的原位换页态」 |
| M2 | **只测单点，不测组合** | 用户在"选字段→加筛选→调顺序→导出"的组合里才发现问题 | 验收场景写成用户操作序列；`e2e-combo.mjs` 固化 |
| M3 | 把「内联 `onclick` 能点」当作「交互正常」 | 掩盖了 `addEventListener` 生命周期问题 | 门禁 `TestPageInitRegistration`：init 必须能被换页重放 |
| M4 | 清理/重构表现层时**没有为每条被删声明找归属** | 内联 `width` 一删，列宽语义就没了（#3） | 表现性内联样式门禁 + 列宽契约断言 |
| M5 | 对"看起来没变"的重构不做语义对账 | `display` 重复声明、`.on/.open` 别名不同步 | 新增重复声明门禁；别名门禁从 JS 源码反查 |
| M6 | 换了实现路径后没回头看旧路径是否还有第二份 | 报表页自带换页实现（#9） | 门禁：`oldMain.innerHTML` 不得出现在页面胶水里 |
| M7 | 验收脚本自身的坑当成产品缺陷 | 陈旧 cookie 拿到登录页、`window.__t` 被 `Page.navigate` 清掉、`#f_customer` 实际是 `[name=...]`、下标被占位块污染、拖到自己身上是 no-op | 写入 `08-testing-conventions.md`（见下） |
| M8 | 大段手打 `old_string` 做补丁 | 3 次锚点失败白跑；跨函数切片险些改坏 `report.py` | 编辑三拍 + 单片段替换 + `assert count == 1` + `ast.parse` 后写 |
| M9 | 改了 `render.py`/`report.py` 但服务仍在跑内存里的旧 HTML | 验证到的是旧行为 | HTML `no-store` + 改后重启服务再验（写入 #17 说明） |
| M10 | 意识到根因后**只改了代码，没同步"下次怎么拦住"** | 同类问题换张皮再来一次 | 本文件 + 06 卷失败模式库 + P6「纠正即入库」 |

---

## 四、机制：机械门禁优先，约定只留给判断类

**判据**：这条失败模式能不能写成一段确定性代码？能 → 门禁；不能 → 清单。

### 4.1 本轮新增门禁（`tests/test_ui_tokens.py`，共 30 例）

| 门禁 | 拦住什么 | 为什么必须机械化 |
|---|---|---|
| `TestNoDuplicateDeclarations`（415） | 同一规则内重复声明同一属性（后者静默覆盖） | CSS 不报错、不波及其它规则，人工评审必漏 |
| `TestPageInitRegistration`（437） | ① 新增 `init*` 没进 `initPage()/initReportPage()`；② 无条件裸绑 `DOMContentLoaded` | 换页失效**没有报错**，只有"点了没反应"；静态可判 |
| `TestFormControlNameUniqueness`（483） | 同名控件混用类型（镜像控件带 `name`） | 服务端"取第一个"会掩盖它，只有渲染后回查才看得见 |

### 4.2 门禁自身也要被验证（`tests/bug_hunt/gate_redproof.py`）

一条从未失败过的门禁可能只是"恰好路过"。该脚本把 4 条门禁对应的历史缺陷**打回去**，
要求门禁失败（RED），还原后通过（GREEN）：

```
门禁                          RED(应失败)  GREEN(应通过)  结论
同规则重复属性                    True        False      PASS
init 未注册进 initPage            True        False      PASS
无条件裸绑 DOMContentLoaded       True        False      PASS
镜像控件带 name                   True        False      PASS
结论：4/4 条门禁通过 RED-GREEN 证明
```

第 3 项会临时改写 `report.py`：`try/finally` + sha256 比对 + 残留 `.bak` 拒绝启动，保证不留下变异代码。
**不进 discover**（文件名非 `test_*.py`），按 `08-testing-conventions.md` 手动运行。

### 4.3 判断类的清单（写进 06 卷，提交前逐条过）

1. 这次改动**碰了哪个交互**？该交互在「整页加载」和「换页态」下各验一次了吗？
2. 有没有**第二次、第三次**同类操作？（换页后拖拽、连续两次排序、先隐藏再还原）
3. 组合顺序验了吗？（字段顺序 × 筛选 × 排序 × 导出交叉）
4. 有没有打断"注册路径唯一性"？（新 init 函数 / 新 `DOMContentLoaded` / 第二份换页实现）
5. 删掉的样式/属性，**语义搬到哪儿了**？（列宽、背景+文字成对、默认隐藏）
6. 验收脚本自身可信吗？（登录态新鲜、选择器与页面一致、下标不受占位元素影响、是否在跑旧服务）

---

## 五、验收脚本自身的坑（写入 `08-testing-conventions.md`）

| 坑 | 症状 | 做法 |
|---|---|---|
| 陈旧 cookie / 未登录 | 拿到的是登录页 HTML，断言全无意义 | 每轮重新登录并断言页面上有预期元素 |
| `Page.navigate` 后 `window.*` 被清空 | 自定义测试钩子（`window.__t`）消失 | 换页后重新注入，或用 CDP `Runtime.evaluate` 每次现取 |
| 选择器想当然（`#f_customer`） | `querySelector` 返回 null → 静默跳过 | 断言元素存在再操作；用页面真实 `name`/class |
| 列表里混有占位元素 | `children` 下标整体错一位，拖动/删除打到别的元素 | 先 `querySelectorAll('.实项')` 过滤，不依赖 `children` |
| 拖到自己身上 | no-op，看不出问题 | 目标下标与源下标不同时才断言变化 |
| 自定义列默认勾选 | "取消勾选"实际是"把默认项取消"，语义反转 | 先读初始勾选状态再断言 |
| 服务跑的是旧内存 HTML | 改完代码验证到的还是旧行为 | 重启服务（改 `render.py`/`report.py`/`config.py` 后必做）+ `no-store` |

---

## 六、仍未覆盖 / 残余风险（诚实清单）

- **宽表自动布局**：连接池/用户/审计/调度页仍是 auto layout，未纳入列宽预算断言；窄屏（<1280）靠横向滚动。
- **帮助气泡的内联样式**：`filter-help-popup` / `nf-help-popup` 等仍在 JS 拼接字符串里，属表现性但未门禁（数量少、影响局部）。
- **E2E 未纳入 `unittest`**：CDP 脚本（`scripts/ui-v2/e2e/`）需手动跑，无法在 CI/全量 `discover` 中自动拦住交互回归。下一步可考虑把 `swap-reinit.mjs` 的判据降级为无头断言脚本并纳入收尾清单。
- **门禁只覆盖"结构/语法/契约"**：视觉观感（间距是否舒服、层级是否清楚）仍依赖用户确认稿与截图回验，无法机械判定。

---

## 附录：本轮复验证据（改完代码、重启服务之后跑）

| 项 | 命令 | 结果 |
|---|---|---|
| 门禁 | `venv/bin/python -m unittest tests.test_ui_tokens` | `Ran 30` **OK** |
| 门禁自证 | `venv/bin/python tests/bug_hunt/gate_redproof.py` | **4/4** RED-GREEN（RED 必失败、GREEN 必通过），exit=0 |
| L1 UI 段 | `test_render*` / `test_report*` / `test_ux*` / `tests.bug_hunt.test_static_analysis` | 374 / 190 / 59 / 5 全 **OK** |
| L2 全量 | `venv/bin/python -m unittest discover -s tests/ -t .` | `Ran 2964` **OK (skipped=4)**（65.9s） |
| 换页态 E2E | `CDP_PORT=9452 node scripts/ui-v2/e2e/swap-reinit.mjs`（重启服务后） | 隐藏→换页后拖拽 `status,id,customer`；还原→再次换页拖拽 `customer,id,status`；排序项反向拖 `status:asc,customer:desc`；导出联动 `selValue=json/charsetDisabled=true/hint=block`；嵌套筛选 1 节点；胶水函数 4 个全 `function`；**控制台异常 0** |

> E2E 复验同时纠正了两条原本会误导人的"证据"：排序项 0→1 在「插到目标之前」语义下本就是 no-op（曾读成"拖拽失效"）；
> `toggleResultIndex` 只在多结果集报表输出（单结果集页 `undefined` 不是缺陷）。两条都已写进 `08-testing-conventions.md` 易踩坑 21 与 E2E README。

