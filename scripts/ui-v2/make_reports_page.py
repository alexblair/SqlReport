#!/usr/bin/env python3
"""生成「报表配置页」重设计确认稿（两个层级方案可切换）。

数据源：config.debug.db（真实演示数据：分类树 / 报表配置 / 连接池 / 接口数 / 调度绑定）
样式源：docs/compose/spec/ui-v2-draft/app.css（单一来源，第 21 节为本页新组件）
输出：docs/compose/spec/ui-v2-draft/preview-reports-v2.html

背景（用户 2026-09-30 反馈）：
  1. 名称列被压成一字一行、SQL 列表头字体/高度与其它列不一致
     → 根因：列宽原本靠内联 style="width:.."（清理内联样式时丢失）+ .sql-head 撞名
  2. 经营分析 / 区域销售 的父子层级在右侧完全没体现
     → 根因：层级原本只靠内联 margin-left + border-left 表达（同样丢失）
本稿用「方案 A 分组卡 + 层级导轨」与「方案 B 单表 + 路径列」给出两种可对比的正解。

用法：venv/bin/python scripts/ui-v2/make_reports_page.py
"""
from __future__ import annotations

import html
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "docs", "compose", "spec", "ui-v2-draft")
DB = os.path.join(ROOT, "config.debug.db")
CSS = os.path.join(OUT, "app.css")

PAGES = [
    ("preview-login.html", "登录"), ("preview-center.html", "报表中心"),
    ("preview-detail.html", "报表详情"), ("preview-overview.html", "概览"),
    ("preview-reports.html", "报表配置(旧)"), ("preview-reports-v2.html", "报表配置 v2"),
    ("preview-pools.html", "连接池"), ("preview-users.html", "用户"),
    ("preview-api.html", "API 接口"), ("preview-scheduler.html", "定时任务"),
    ("preview-audit.html", "审计日志"), ("preview-report-edit.html", "报表编辑"),
    ("preview-sched-new.html", "新建调度"), ("preview-sched-edit.html", "编辑调度"),
]


# --------------------------------------------------------------------------- 数据
def load_data() -> dict:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cats = [dict(r) for r in conn.execute(
        "select id,name,parent_id,sort_order from report_categories order by sort_order,id")]
    pools = {r["id"]: r["name"] for r in conn.execute("select id,name from connection_pools")}
    apis = {r["report_id"]: r["n"] for r in conn.execute(
        "select report_id,count(*) n from api_endpoints group by report_id")}
    scheds = {r["report_id"] for r in conn.execute(
        "select distinct report_id from schedule_reports")}
    reports = [dict(r) for r in conn.execute(
        "select id,name,sql_query,category_id,default_page_size,prefer_cache,cache_ttl_hours,"
        "pool_id,memo,allow_write,keepalive_enabled,result_names,max_rows "
        "from report_configs order by sort_order,id")]
    for r in reports:
        r["pool"] = pools.get(r["pool_id"], "—")
        r["apis"] = apis.get(r["id"], 0)
        r["sched"] = r["id"] in scheds
        r["sql"] = " ".join((r["sql_query"] or "").split())
        r["memo"] = " ".join((r["memo"] or "").split())
        r["results"] = len([x for x in (r["result_names"] or "").split(",") if x.strip()])
    return {"cats": cats, "reports": reports}


def cat_tree(data: dict) -> dict:
    """把分类组装成树，并在每个节点挂上（含子级的）报表。"""
    cats = {c["id"]: dict(c, children=[]) for c in data["cats"]}
    roots = []
    for c in cats.values():
        pid = c["parent_id"]
        (cats[pid]["children"] if pid in cats else roots).append(c)
    for r in data["reports"]:
        cid = r["category_id"]
        if cid in cats:
            cats[cid].setdefault("reports", []).append(r)
    return {"roots": roots, "by_id": cats, "uncategorized": [r for r in data["reports"] if r["category_id"] is None]}


# --------------------------------------------------------------------------- 片段
def esc(v) -> str:
    return html.escape(str(v), quote=True)


def cfg_chips(r: dict) -> str:
    chips = [f'<span class="cfg-chip">分页 <b>{r["default_page_size"]}</b></span>']
    if r["prefer_cache"]:
        ttl = r["cache_ttl_hours"]
        chips.append(f'<span class="cfg-chip ok">缓存优先 <b>{ttl}h</b></span>' if ttl
                     else '<span class="cfg-chip ok">缓存优先</span>')
    else:
        chips.append('<span class="cfg-chip">实时查询</span>')
    if r["keepalive_enabled"]:
        chips.append('<span class="cfg-chip accent">保活</span>')
    if r["allow_write"]:
        chips.append('<span class="cfg-chip warn">写护栏</span>')
    if r["results"] > 1:
        chips.append(f'<span class="cfg-chip">{r["results"]} 个结果集</span>')
    extra = len(chips) - 3
    if extra > 0:
        chips = chips[:3] + [f'<span class="cfg-chip">+{extra}</span>']
    return '<span class="cfg-chips nowrap-chips">' + "".join(chips) + "</span>"


def rpt_row(r: dict) -> str:
    api = (f'<a class="cfg-chip" href="#" title="{esc(r["name"])} 的 API 接口">接口 <b>{r["apis"]}</b></a>'
           if r["apis"] else '<span class="cfg-chip">无接口</span>')
    sched = '<span class="cfg-chip accent">定时</span>' if r["sched"] else ""
    pool = f'<span class="pool-chip" title="{esc(r["pool"])}"><span class="dot"></span><span class="txt">{esc(r["pool"])}</span></span>'
    return f"""      <div class="rpt-row" id="report-{r['id']}">
        <label class="pick"><input type="checkbox" class="report-checkbox" value="{r['id']}" onchange="updateBatch(this)"></label>
        <div class="rpt-main">
          <div class="rpt-line1">
            <a class="nm" href="#" title="{esc(r['name'])}">{esc(r['name'])}</a>
            {sched}
          </div>
          <div class="rpt-meta">{cfg_chips(r)}{pool}{api}</div>
          <div class="rpt-memo" title="{esc(r['memo'])}">{esc(r['memo'][:64])}</div>
          <div class="rpt-sql" title="{esc(r['sql'])}">{esc(r['sql'][:110])}</div>
        </div>
        <div class="rpt-ops">{ops(r['id'])}</div>
      </div>"""


def rpt_card(r: dict) -> str:
    """卡片视图形态：复用生产 .rpt-card/.rc-* DOM 词汇，与列表行同数据各渲一份。"""
    api = (f'<a class="rc-api" href="#" title="{esc(r["name"])} 的 API 接口">接口 <b>{r["apis"]}</b></a>'
           if r["apis"] else '<span class="rc-api muted">无接口</span>')
    pool = f'<span class="pool-chip" title="{esc(r["pool"])}"><span class="dot"></span><span class="txt">{esc(r["pool"])}</span></span>'
    sched = '<span class="cfg-chip accent">定时</span>' if r["sched"] else ""
    memo = f'<div class="rc-memo" title="{esc(r["memo"])}">备注：{esc(r["memo"][:56])}</div>' if r["memo"] else ""
    return f"""        <div class="rpt-card" id="report-card-{r['id']}">
          <input type="checkbox" class="report-checkbox rc-pick" value="{r['id']}" onchange="updateBatch(this)" title="勾选以批量操作">
          <div class="rc-top"><span class="rc-name"><a href="#" title="{esc(r['name'])}">{esc(r['name'])}</a></span></div>
          <div class="rc-meta">{cfg_chips(r)}{sched}{pool}</div>
          <div class="rc-sql" title="{esc(r['sql'])}">{esc(r['sql'][:64])}</div>
          {memo}
          <div class="rc-foot">{api}<span class="rc-ops">{ops(r['id'])}</span></div>
        </div>"""


def ops(rid: int) -> str:
    return (f'<button class="btn-mini" title="上移">↑</button>'
            f'<button class="btn-mini" title="下移">↓</button>'
            f'<a class="btn-mini" href="#" title="复制">⧉</a>'
            f'<a class="btn-mini" href="#" title="编辑">✎</a>'
            f'<button class="btn-mini" title="删除">✕</button>')


def cat_block(cat: dict, depth: int, demo: bool = False) -> str:
    rep = cat.get("reports", [])
    kids = cat.get("children", [])
    badge = f'<span class="badge badge-neutral">{len(rep)} 个报表</span>'
    name = f'{esc(cat["name"])}' + ('<span class="muted" style="font-size:11px">（示意第三级）</span>' if demo else '')
    cards = "".join(rpt_card(r) for r in rep)
    rows = "".join(rpt_row(r) for r in rep) or '<div class="cat-empty"><span>该分类暂无报表</span><a class="add" href="#">+ 新增报表</a></div>'
    children = ""
    if kids or demo:
        inner = "".join(cat_block(k, depth + 1) for k in kids)
        children = f'<div class="cat-children">{inner}</div>'
    return f"""    <section class="cat-block cat-depth-{depth}">
      <div class="cat-head">
        <button type="button" class="tree-toggle" onclick="toggleBlock(this)"><span class="chev">▼</span></button>
        <span class="cat-depth-dot"></span>
        <span class="cat-name">{icon_folder()}{name}</span>
        {badge}
        <span class="actions">
          <a class="btn-mini" href="#" title="新增子分类">+ 子分类</a>
          <a class="btn-mini" href="#" title="编辑分类">✎</a>
          <button class="btn-mini" title="删除分类">✕</button>
        </span>
      </div>
      <div class="cat-body">{rows}</div>
      <div class="rpt-grid cat-cards hidden">{cards}</div>
      {children}
    </section>"""


def demo_leaf(depth: int) -> str:
    return f"""      <section class="cat-block cat-depth-{depth}">
        <div class="cat-head">
          <button type="button" class="tree-toggle" onclick="toggleBlock(this)"><span class="chev">▼</span></button>
          <span class="cat-depth-dot"></span>
          <span class="cat-name">{icon_folder()}<span class="muted" style="font-size:11px">华东片区（示意第三级）</span></span>
          <span class="badge badge-neutral">0 个报表</span>
        </div>
        <div class="cat-body"><div class="cat-empty"><span>该分类暂无报表</span><a class="add" href="#">+ 新增报表</a></div></div>
      </section>"""


def icon_folder() -> str:
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">'
            '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>')


def tree_node(cat: dict, depth: int = 0) -> str:
    kids = cat.get("children", [])
    n = len(cat.get("reports", [])) + sum(count_reports(k) for k in kids)
    cls = "cat active" if depth == 0 and cat is None else "cat"
    has = ' data-has-kids="1"' if kids else ""
    return (f'<div class="cat" data-cat="{esc(cat["name"])}"{has} onclick="pickCat(this)">{icon_folder()}'
            f'<span class="nm" title="{esc(cat["name"])}">{esc(cat["name"])}</span>'
            f'<span class="cnt">{n}</span>'
            f'<span class="ops"><a class="btn-mini" href="#" title="编辑">✎</a><button class="btn-mini" title="删除">✕</button></span>'
            f'</div>'
            + (f'<div class="kids">{"".join(tree_node(k, depth + 1) for k in kids)}</div>' if kids else ""))


def count_reports(cat: dict) -> int:
    return len(cat.get("reports", [])) + sum(count_reports(k) for k in cat.get("children", []))


def path_of(cat: dict, tree: dict) -> str:
    """返回 根 › … › 自身 的路径文本。"""
    by_id = tree["by_id"]
    chain, cur = [], cat
    while cur is not None:
        chain.append(cur["name"])
        pid = cur.get("parent_id")
        cur = by_id.get(pid) if pid in by_id else None
    return " / ".join(reversed(chain))


def flat_rows(tree: dict) -> list[tuple[str, dict]]:
    """深度优先展开，得到（分类路径, 报表）列表。"""
    out: list[tuple[str, dict]] = []

    def walk(cat: dict):
        p = path_of(cat, tree)
        for r in cat.get("reports", []):
            out.append((p, r))
        for k in cat.get("children", []):
            walk(k)

    for root in tree["roots"]:
        walk(root)
    for r in tree["uncategorized"]:
        out.append(("未分类", r))
    return out


# --------------------------------------------------------------------------- 页面
def build() -> str:
    data = load_data()
    tree = cat_tree(data)
    css = open(CSS, encoding="utf-8").read()

    # 复用已有确认稿的真实侧栏，保证与其它页面完全一致
    prev = os.path.join(OUT, "preview-reports.html")
    sidebar = ""
    if os.path.isfile(prev):
        s = open(prev, encoding="utf-8").read()
        m = re.search(r'<aside class="sidebar".*?</aside>', s, re.S)
        if m:
            sidebar = m.group(0)

    cat_blocks = "".join(cat_block(c, 1) for c in tree["roots"])
    # 「未分类」不是 report_categories 里的行，必须显式渲染，否则未分类报表在方案 A 里整批消失
    if tree["uncategorized"]:
        cat_blocks += cat_block(
            {"id": None, "name": "未分类", "reports": tree["uncategorized"], "children": []}, 1)
    demo_child = demo_leaf(3)
    # 在「区域销售」块内插入第三级示意
    idx = cat_blocks.find('cat-name">' + icon_folder() + '区域销售')
    if idx > 0:
        close = cat_blocks.find("</section>", idx)
        cat_blocks = cat_blocks[:close] + f'<div class="cat-children">{demo_child}</div>' + cat_blocks[close:]

    total = len(data["reports"])
    n_cat = len(data["cats"])
    n_sched = sum(1 for r in data["reports"] if r["sched"])

    # 方案 B：单表 + 分类路径列
    b_rows = "".join(
        f"""          <tr id="breport-{r['id']}">
            <td><input type="checkbox" class="report-checkbox" value="{r['id']}" onchange="updateBatch(this)"></td>
            <td class="name-cell"><a href="#" title="{esc(r['name'])}">{esc(r['name'])}</a></td>
            <td><span class="cat-path"><span class="rt">{esc(p)}</span></span></td>
            <td>{cfg_chips(r)}</td>
            <td><span class="pool-chip" title="{esc(r['pool'])}"><span class="dot"></span><span class="txt">{esc(r['pool'])}</span></span></td>
            <td class="sql-cell" title="{esc(r['sql'])}"><code>{esc(r['sql'][:42])}</code></td>
            <td class="api-cell"><a href="#">{r['apis']} 个</a></td>
            <td class="ops-cell">{ops(r['id'])}</td>
          </tr>"""
        for p, r in flat_rows(tree))

    b_cards = "".join(
        rpt_card(r).replace('<div class="rc-top">',
                            f'<div class="rc-top"><span class="cat-path" style="margin-right:auto">'
                            f'<span class="rt">{esc(p)}</span></span>')
        for p, r in flat_rows(tree))

    tree_html = ('<div class="tree" id="rc-tree">'
                 '<div class="cat active" data-cat="全部" onclick="pickCat(this)">'
                 '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">'
                 '<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/>'
                 '<line x1="4" y1="17" x2="20" y2="17"/></svg>'
                 f'<span class="nm">全部报表</span><span class="cnt">{total}</span></div>'
                 + "".join(tree_node(c) for c in tree["roots"])
                 + '</div>')

    bar = "".join(
        f'<a href="{f}"{" class=on" if f == "preview-reports-v2.html" else ""}>{n}</a>'
        for f, n in PAGES)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>报表配置 · 重设计确认稿 — SqlReport</title>
<style>
{css}
/* —— 确认稿页脚切换条（过程素材，不进生产） —— */
#pv-bar{{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:9999;display:flex;align-items:center;
  gap:2px;padding:5px 6px;background:rgba(16,18,26,.94);border:1px solid rgba(255,255,255,.09);border-radius:999px;
  box-shadow:0 12px 32px rgba(0,0,0,.34);backdrop-filter:blur(10px);font:500 12px/1 var(--font-sans);color:#b4b7c2;max-width:94vw;overflow:auto}}
#pv-bar a{{color:#b4b7c2;text-decoration:none;padding:6px 9px;border-radius:999px;white-space:nowrap}}
#pv-bar a:hover{{background:rgba(255,255,255,.1);color:#fff}}
#pv-bar a.on{{background:#5d61e0;color:#fff}}
#pv-bar .tag{{padding:0 8px;color:#83868f}}
</style>
</head>
<body>
<div class="app">
{sidebar}
<main class="main">
<div class="container">

  <div class="page-head">
    <div>
      <div class="crumb">管理 › 报表配置</div>
      <h1>报表配置</h1>
      <div class="sub">{total} 个报表 · {n_cat} 个分类（含 1 个子分类） · {n_sched} 个绑定了定时任务</div>
    </div>
    <div class="actions">
      <div class="search-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input class="input" id="rc-search" placeholder="搜索报表名称 / 备注 / SQL…" oninput="filterRows(this.value)">
      </div>
      <div class="segment" id="scheme-seg">
        <button type="button" data-scheme="A" class="active" onclick="setScheme('A')">方案 A · 分组卡</button>
        <button type="button" data-scheme="B" onclick="setScheme('B')">方案 B · 单表</button>
      </div>
      <div class="segment" id="view-seg">
        <button type="button" data-view="list" class="active" onclick="setView('list')">列表</button>
        <button type="button" data-view="card" onclick="setView('card')">卡片</button>
      </div>
      <a class="btn btn-secondary" href="#">+ 新增分类</a>
      <a class="btn btn-primary" href="#">+ 新增报表</a>
    </div>
  </div>

  <div class="scheme-bar">
    <strong>层级方案对比</strong>
    <span id="scheme-desc">方案 A（当前）：分类卡 + 层级导轨 —— 多级时逐级缩进、竖线导轨 + 节点横线 + 字号逐级下沉，第三级用色点锚定</span>
    <span class="muted" style="margin-left:auto">切换上方分段器即可对比</span>
  </div>

  <div class="split">
    <aside class="card">
      <div class="section-title">报表分类
        <span class="actions"><a class="btn-mini" href="#">+ 新增分类</a></span>
      </div>
      {tree_html}
    </aside>

    <div>
      <!-- 方案 A -->
      <div id="scheme-A">{cat_blocks}</div>

      <!-- 方案 B -->
      <div id="scheme-B" class="hidden">
        <div class="table-wrap">
          <table class="table-fixed">
            <colgroup>
              <col class="c-check"><col class="c-name"><col class="c-path"><col class="c-cfg">
              <col class="c-pool"><col class="c-sql"><col class="c-api"><col class="c-ops">
            </colgroup>
            <thead>
              <tr>
                <th><input type="checkbox" onchange="selectAll(this)"></th>
                <th>名称</th>
                <th>分类路径</th>
                <th>配置</th>
                <th>连接池</th>
                <th>SQL 查询</th>
                <th>接口</th>
                <th style="text-align:right">操作</th>
              </tr>
            </thead>
            <tbody>
{b_rows}
            </tbody>
          </table>
        </div>
        <p class="muted" style="font-size:12px">
          方案 B 说明：全部报表一张表，用「分类路径」列表达归属（父级灰、叶级深）；跨分类排序与批量操作天然一致，
          代价是失去分组卡的视觉分区。表宽固定 8 列（原 10 列，把默认分页/缓存/TTL 合并为「配置」chips）。
        </p>
        <div class="rpt-grid cat-cards hidden" id="scheme-B-cards">
{b_cards}
        </div>
      </div>

      <div class="batch-bar batch-float hidden" id="batch-bar">
        <span>已选 <b id="batch-count">0</b> 项</span>
        <select><option>-- 移动到分类 --</option>{''.join(f'<option>{esc(c["name"])}</option>' for c in data["cats"])}</select>
        <select><option>-- 更换连接池 --</option>{''.join(f'<option>{esc(p)}</option>' for p in sorted({r["pool"] for r in data["reports"]}))}</select>
        <button class="btn btn-sm btn-secondary">应用</button>
        <button class="btn btn-sm btn-ghost" onclick="clearPicked()">取消选择</button>
      </div>
    </div>
  </div>
</div>
</main>
</div>

<div id="pv-bar"><span class="tag">UI v2 预览</span>{bar}</div>

<script>
function setScheme(v){{
  document.getElementById('scheme-A').classList.toggle('hidden', v !== 'A');
  document.getElementById('scheme-B').classList.toggle('hidden', v !== 'B');
  document.querySelectorAll('#scheme-seg button').forEach(b => b.classList.toggle('active', b.dataset.scheme === v));
  document.getElementById('scheme-desc').textContent = v === 'A'
    ? '方案 A（当前）：分类卡 + 层级导轨 —— 多级时逐级缩进、竖线导轨 + 节点横线 + 字号逐级下沉，第三级用色点锚定'
    : '方案 B（当前）：单表 + 分类路径列 —— 父级灰、叶级深；列数 10 → 8，「配置」用 chips 表达';
}}
function setView(v){{
  document.querySelectorAll('#view-seg button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  const card = v === 'card';
  document.querySelectorAll('.cat-body').forEach(el => el.classList.toggle('hidden', card));
  document.querySelectorAll('.cat-cards').forEach(el => el.classList.toggle('hidden', !card));
  const wrap = document.querySelector('#scheme-B .table-wrap');
  if (wrap) wrap.classList.toggle('hidden', card);
}}
function toggleBlock(btn){{ btn.closest('.cat-block').classList.toggle('collapsed'); }}
function pickCat(el){{
  document.querySelectorAll('#rc-tree .cat').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
}}
function updateBatch(cb){{
  /* 两形态同数据：把当前勾选值镜像到另一形态（生产 pickedReportIds() 同语义） */
  if (cb && cb.classList && cb.classList.contains('report-checkbox')) {{
    document.querySelectorAll('.report-checkbox[value="' + cb.value + '"]').forEach(x => {{ x.checked = cb.checked; }});
  }}
  const n = document.querySelectorAll('.report-checkbox:checked').length;
  document.getElementById('batch-count').textContent = n;
  document.getElementById('batch-bar').classList.toggle('hidden', n === 0);
  document.querySelectorAll('.rpt-row').forEach(row => {{
    const c = row.querySelector('.report-checkbox');
    if (c) row.classList.toggle('picked', c.checked);
  }});
  document.querySelectorAll('.rpt-card').forEach(card => {{
    const c = card.querySelector('.report-checkbox');
    if (c) card.classList.toggle('picked', c.checked);
  }});
}}
function selectAll(cb){{ document.querySelectorAll('#scheme-B .report-checkbox').forEach(c => {{ c.checked = cb.checked; }}); updateBatch(cb); }}
function clearPicked(){{
  document.querySelectorAll('.report-checkbox').forEach(c => c.checked = false);
  updateBatch({{checked:false}});
}}
function filterRows(q){{
  q = (q || '').trim().toLowerCase();
  document.querySelectorAll('.rpt-row').forEach(row => {{
    row.classList.toggle('hidden', q !== '' && !row.textContent.toLowerCase().includes(q));
  }});
  document.querySelectorAll('#scheme-B tbody tr').forEach(row => {{
    row.classList.toggle('hidden', q !== '' && !row.textContent.toLowerCase().includes(q));
  }});
  document.querySelectorAll('.cat-block').forEach(blk => {{
    const has = [...blk.querySelectorAll('.rpt-row')].some(r => !r.classList.contains('hidden'));
    blk.classList.toggle('hidden', q !== '' && !has);
  }});
}}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    html_out = build()
    dst = os.path.join(OUT, "preview-reports-v2.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"生成 {os.path.basename(dst)}  ({len(html_out)//1024} KB)")
    sys.exit(0)
