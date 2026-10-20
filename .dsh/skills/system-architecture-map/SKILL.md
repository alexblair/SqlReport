---
name: system-architecture-map
description: 更新 SqlReport 系统架构图单页（docs/compose/reports/<日期>-system-architecture-map.html）时使用——含页面/组件/dataflow/共用-私有配色标识。凡涉及代码或功能调整、全部任务完成且通过验收后自动触发；用户在任何时间说「更新架构图 / 刷新架构图 / 架构图过时了」也触发。当天多次触发只更新当天那一个文件。
---

# 系统架构图 · 增量更新

**核心原则**：架构图是**代码的派生物**，不是独立创作。
更新 = 拿新代码事实与图里内嵌的旧事实做差 → 只改被差出的章节。
**禁止从 0 重画，禁止凭记忆填数字。**

## 三条铁律（违反即返工）

1. **不改代码**。本技能只读代码、只写 `docs/compose/reports/` 下的 HTML。发现代码缺陷 → 单独报告，不顺手修。
2. **一天一个文件**。文件名 `<YYYY-MM-DD>-system-architecture-map.html`（`date +%F` 取当天）。同日再触发 → **就地更新它**，绝不新建 `-2` / `-v2` / `-new`。同日该目录下只允许存在一个匹配 `[0-9]{4}-[0-9]{2}-[0-9]{2}-system-architecture-map.html` 且日期为今天的文件。
3. **数字必须可复现**。写进图的每个计数（路由数 / 行数 / 调用点 / 表数）必须能由 §2 的命令复算出来；写不出命令的条目，改成定性描述或删掉。

## §1 触发条件（何时必须做）

| 触发源 | 判据 | 动作 |
|---|---|---|
| **自动**（收尾） | 本次任务改了 `.py` / `config_pages/*` / `ui_assets.py` / 路由 / 新增页面，且测试通过、用户已验收 | 收尾阶段执行本技能，与知识库同步并列 |
| **手工** | 用户说「更新 / 刷新 / 重画架构图」「架构图过时了」 | 立刻执行，不看是否有代码改动（可能只是要换日期快照） |
| **不触发** | 纯文档 / 纯注释 / 纯测试改动 | 跳过，不做无意义的日期翻新 |

自动触发的固化位置：`AGENTS.md` §5 收尾检查单 + §0 路由表，以及
`docs/compose/knowledge/09-agent-workflow.md`「架构图更新纪律」。三处任一处被删都会漏触发，改规则时同步。

## §2 借力取证（四档，从低到高，够用就停）

**禁止**：直接把全仓库重读一遍。上一版 HTML 就是上一次的取证结果，先复用它。

### A 档 · 拿上一版当骨架（≈30 秒）

```bash
TODAY=$(date +%F)
DIR=docs/compose/reports
ls -1 "$DIR"/*-system-architecture-map.html        # 看有几个、哪个最新

SAME="$DIR/$TODAY-system-architecture-map.html"    # 今天的
BASE=$(ls -1 "$DIR"/*-system-architecture-map.html | sort | tail -1)   # 最新一版

if [ ! -f "$SAME" ]; then cp "$BASE" "$SAME"; fi   # 无今日文件 → 以最新版为骨架派生
```

派生后**必须**改两处日期：顶部 `<span class="ver">代码快照 YYYY-MM-DD</span>` 与 `<footer>` 里的快照日期。
**除这两处外别的一律先不动**——等 B 档差出问题再改。

### B 档 · 事实差比对（≈1 分钟，主要工作量在这里）

```bash
venv/bin/python scripts/agent/arch_facts.py --prev "$SAME"
```

- 输出 `NO_CHANGE` → **停**。只交付日期翻新（或若当天已有文件且仅是用户重复触发，直接回报「代码事实无变化，图纸无改动」）。
- 输出 `CHANGED N 项` → 按 §3 映射表定位到具体章节，只改这些章节。
- 报 `E_NO_FACTS` → 说明该 HTML 还没有内嵌事实块（首版遗留），先 `--embed "$SAME"` 补一次，再 `--prev`。

`arch_facts.py` 提取的事实：`routes`（按端点去重，含 auth/db）、`modules`（行数 + imports + imported_by）、
`shared_components`（`render.py` 公开函数被 ≥2 个模块直接调用的站点数）、`tables` / `audit_tables`、
`ui_consts`（CSS/JS 常量名 + JS 函数名）、`vendor`（第三方前端库版本目录）。

### C 档 · 知识库交叉校验（只在 B 档报警时查，禁止整卷通读）

| 想知道 | 查 |
|---|---|
| 模块职责怎么写、页面路由归属 | `docs/compose/knowledge/INDEX.md` §1 模块职责表、§2 路由总表 |
| 页面清单与页内组件 | `docs/compose/knowledge/06-ui-interactions.md` |
| 缓存分层 / 调度 / 审计 type | `docs/compose/knowledge/07-cache-scheduler-audit.md` |
| 筛选排序导出 API 的共用语义 | `docs/compose/knowledge/03-report-transform.md`、`05-api.md` |
| 为什么这么设计（决策依据） | `docs/compose/spec/` 最新生效 spec（先看状态头） |

知识库与代码冲突 → **以代码为准**，并把差异回写知识库（硬性 #7）。

### D 档 · 精确调用链（只在需要判断「共用还是私有」时用）

```bash
codegraph explore "render_page_header 调用点"
```

`arch_facts.py` 的共用判定是「`render.py` 公开函数 + 被 ≥2 个非 render 模块匹配到调用」。
边界情况（动态调用、字符串拼接、别名导入）用 codegraph 复核，别拿正则结果当定论。

## §3 事实变更 → 章节映射（改哪里）

| B 档报的变更 | 要改的章节 | 具体动作 |
|---|---|---|
| `routes` 增 / 删 / 属性变 | ① L1 路由盒、② 对应页卡头部路由章与 `auth`/`db` 徽标、`hero` KPI「N HTTP 路由」「N 页面与端点」、`footer` 范围行 | 页卡是 `<article class="page" id="p-xxx">`，路由章 `<span class="route">`，API 用 `class="route api"`，免鉴权用 `class="route none"` |
| `modules` 行数 / 依赖变 | ⑥ 模块依赖表、KPI「~Nk Python 行」 | 表格 `<tr><td><code>模块</code></td><td>行数</td><td>依赖</td><td>被依赖</td><td>职责</td></tr>` |
| `shared_components` 增 / 减 / 调用点数变 | ③ 共用组件矩阵（按调用点数降序）、② 各页卡里对应 chip 的 `shared`↔`private` 升降级、KPI「N 共用构件」 | 降级到 1 处 = 从共用矩阵删行，并把页卡 chip 改 `chip private` |
| `tables` / `audit_tables` 变 | ① L5 数据层、② 配置域页卡、KPI「N 数据表」 | 配置库与 `audit.db` 是**两个故障域**，别合并 |
| `ui_consts` / `vendor` 变 | ⑤ 前端资产与初始化链、② 页卡里的 `chip css`（第三方库）/ `chip js` | 新增第三方库要写清 `名字@版本` |
| **新增页面**（`config_pages/` 新文件 + 新路由） | ② 新增一张 `<article class="page">` 卡（结构照抄最相近的同类卡）、③ 若产生新共用构件则加行、④ 若引入新链路则新增 `F<n>` 且补序号 | 页卡必须含：路由章 / `auth`·`db` 徽标 / 页内分组（共用·私有·dataflow） |
| **删除页面** | 删对应 `<article>` 卡、清理 ③④ 里的孤儿引用、重算 KPI | 删完 grep 一遍旧路由串确认无残留 |

改完 **务必**同步 `footer` 的「范围：N 路由 · N 页面/端点 · N 共用构件 · N 条 dataflow」四项计数。

## §4 视觉规范（不许破的不变量）

用户已三次因「颜色单独表意 / 图例与实际不一致」打回。以下是不变量，新增内容必须照办：

1. **颜色 + 文字前缀双通道**。每个 chip 必带分类 class，`::before` 自动加前缀：
   `.chip.shared`→`共用`（绿 `--shared`）、`.chip.private`→`私有`（橙 `--private`）、
   `.chip.js`→`JS`（紫）、`.chip.css`→`资产`（品红）、`.chip.infra`→`服务`（蓝）。
   **禁止裸 `<span class="chip">`**，禁止只靠颜色区分。
2. **`guard` 是叠加后缀，不是分类**。写法 `<span class="chip private guard" title="含安全护栏：…">`，
   渲染出「⚠ 护栏」并保留底色分类。用于写操作 / 全量输出 / 注入防护等风险点。
3. **组标题三段式**：`<h5><i class="dot" style="background:var(--X)"></i>前缀 · 作用域<span class="gcount">N</span></h5>`
   —— 色点对应分组色、右侧件数必须准确。
4. **一组只放一类构件**。CSS / JS / 服务端 HTML 混在一个「共用组件」组 = 用户看不懂差异（已发生过）。
5. **dataflow 组标题**固定写 `dataflow · 数据流向（非构件，N 步）`，防止被误读成构件分类。
6. **每章开头自带 `.legend` + `.lg-title`**，且图例里的样例 chip 必须与正文真实用法一致
   （图例是承诺，正文是兑现）。
7. **数字类徽标要有读法说明**：`.route`（靛蓝=普通页 / 青绿 `.api`=API Key / 灰 `.none`=免鉴权）、
   `.flag.on`/`.flag.no`、`.gcount`、`.cnt.hi`/`.cnt`——新增一种视觉元素就必须在图例里加一行。

## §5 校验（改完必跑，一次批量）

```bash
F="docs/compose/reports/$(date +%F)-system-architecture-map.html"
grep -o 'class="chip[^"]*"' "$F" | sort | uniq -c          # 分类分布；裸 chip 必须为 0
grep -c 'class="grp"' "$F"                                  # 组数
venv/bin/python - "$F" <<'EOF'                              # 结构合法性
import sys
from html.parser import HTMLParser
VOID={'meta','link','br','img','hr','input','source','col','area','base','embed','track','wbr'}
class P(HTMLParser):
    def __init__(s): super().__init__(); s.st=[]; s.err=[]
    def handle_starttag(s,t,a):
        if t not in VOID: s.st.append(t)
    def handle_endtag(s,t):
        if t in VOID: return
        if s.st and s.st[-1]==t: s.st.pop()
        elif t in s.st:
            while s.st and s.st[-1]!=t: s.err.append(('unclosed',s.st.pop()))
            if s.st: s.st.pop()
        else: s.err.append(('stray',t))
p=P(); p.feed(open(sys.argv[1],encoding='utf-8').read())
print('error' if p.err or p.st else 'OK', p.err[:5], p.st[:5])
EOF
```

硬门禁（任一不满足 = 重做）：

- HTMLParser `OK`，零 unclosed / 零 stray。
- 裸 `class="chip"` 计数为 0；无 `hot` 类残留（已废弃的旧标记）。
- 每个 `<div class="grp">` 的 `<h5>` 都带 `dot` + `gcount`；`gcount` 数字与实际 chip 数一致。
- 组标题全部是「前缀 · 作用域」形态。
- 文件仍为**单文件**：无 `<link rel=stylesheet>`、无 `<script src=…>` 外链。

> 本机通常无 chromium，**不要**尝试截图自检（`which chromium` 无输出即确认）；上面这套结构化校验就是验收依据。

## §6 收尾（三步，缺一不算完）

```bash
F="docs/compose/reports/$(date +%F)-system-architecture-map.html"
venv/bin/python scripts/agent/arch_facts.py --embed "$F"      # 把本次事实写回图里，下次才能 --prev
ls -1 docs/compose/reports/*-system-architecture-map.html      # 确认今天只有一个同名日期文件
git diff --stat -- docs/compose/reports/                        # 报告改了哪些章节
```

1. `--embed` 必做——否则下次 `--prev` 只能对上上一次的快照，差分会把已改过的项重复报出来。
2. 向用户报告：**触发的证据**（B 档差出的具体条目）、改了哪几章、结构校验结果（`OK` / chip 分布）。
3. 用 `present` 交付 HTML。纯文档产物，按硬性 #8 **不跑任何测试**。

## §7 常见坑（都踩过）

- **正则改 HTML 必须带 assert 命中数**，改完立刻跑 §5 的 parser 复验。历史上一次批量注入把 40 处写成了 `<span9</span>` 这种残缺标签，parser 才抓出来。
- **同日建第二个文件**是最常见的违规；动手前先 `ls -1 "$DIR"/*-system-architecture-map.html`。
- **只改日期不改内容**看着无害，但会让 `--prev` 失去参照（图里事实块撒谎）。要么 `--embed` 同步，要么别改日期。
- **把「共用」理解成「render.py 里定义的」是错的**：判定标准是**被 ≥2 个非 render 模块调用**；只被一个页面用的仍是私有。
- 上一版 HTML 的 `arch-facts` 块是 `type="application/json"` 的 `<script>`，**不参与渲染**，但改图时不要手动编辑它——永远走 `--embed`。
