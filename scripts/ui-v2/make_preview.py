#!/usr/bin/env python3
"""用真实生产 HTML + UI v2 样式生成可交互预览稿（不改生产代码）。

做法：
  1. 读取 run-logs/ui-v2/raw_*.html（真实登录态抓取的生产页面）
  2. 清理内联样式（只保留 display/visibility 这类行为性声明），去掉 target=_blank
  3. 摘掉旧公共 CSS 外链，注入 app.css（v2 单一来源）
  4. 注入胶水 JS：页签/抽屉/对话框/分段控件/侧栏手柄/色调切换 在预览稿里真的可点
  5. 内部链接与表单提交统一拦截并提示（预览稿不改真实数据）

用法：venv/bin/python scripts/ui-v2/make_preview.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "run-logs", "ui-v2")
OUT = os.path.join(ROOT, "docs", "compose", "spec", "ui-v2-draft")
CSS = os.path.join(OUT, "app.css")

PAGES = [
    ("preview-login.html", "raw_login.html", "登录"),
    ("preview-center.html", "raw_report.html", "报表中心"),
    ("preview-detail.html", "raw_detail1.html", "报表详情"),
    ("preview-overview.html", "raw_config.html", "概览"),
    ("preview-reports.html", "raw_config_reports.html", "报表配置"),
    ("preview-pools.html", "raw_config_pools.html", "连接池"),
    ("preview-users.html", "raw_config_users.html", "用户"),
    ("preview-api.html", "raw_config_api-endpoints.html", "API 接口"),
    ("preview-scheduler.html", "raw_config_scheduler.html", "定时任务"),
    ("preview-audit.html", "raw_audit.html", "审计日志"),
    ("preview-report-edit.html", "raw_report-edit.html", "报表编辑"),
    ("preview-sched-new.html", "raw_sched-new.html", "新建调度"),
    ("preview-sched-edit.html", "raw_sched-edit.html", "编辑调度"),
]

# 内联样式里要剔除的「表现性」声明（视觉一律由 app.css 决定；
# 布局类声明保留，否则会丢掉生产 DOM 的排版意图）
DROP_DECL = (
    "color", "background", "border", "box-shadow", "font", "text-decoration",
    "letter-spacing", "line-height", "padding", "margin", "width", "max-width", "height",
    "min-width", "opacity", "filter", "transform", "transition", "outline",
)

_BAR_CSS = """
<style>
#pv-bar{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;display:flex;
  align-items:center;gap:2px;padding:5px 6px;background:rgba(16,18,26,.94);border:1px solid rgba(255,255,255,.09);
  border-radius:999px;box-shadow:0 12px 32px rgba(0,0,0,.34);backdrop-filter:blur(10px);
  font:500 12px/1 var(--font-sans,"PingFang SC",system-ui,sans-serif);color:#b4b7c2}
#pv-bar a,#pv-bar button{appearance:none;border:0;background:transparent;color:#b4b7c2;font:inherit;
  padding:6px 10px;border-radius:999px;cursor:pointer;text-decoration:none;white-space:nowrap}
#pv-bar a:hover,#pv-bar button:hover{background:rgba(255,255,255,.1);color:#fff}
#pv-bar a.on{background:#5d61e0;color:#fff}
#pv-bar .sep{width:1px;height:16px;background:rgba(255,255,255,.14);margin:0 4px}
#pv-bar .tag{padding:0 8px;color:#83868f;font-weight:400;white-space:nowrap}
#pv-toast{position:fixed;left:50%;bottom:70px;transform:translateX(-50%);z-index:99999;max-width:70vw;
  padding:8px 14px;background:#10121a;color:#e8eaee;border-radius:8px;font:400 12px/1.5 var(--font-sans,system-ui);
  box-shadow:0 12px 32px rgba(0,0,0,.3);opacity:0;transition:opacity .18s;pointer-events:none}
#pv-toast.show{opacity:1}
</style>
"""

_GLUE = r"""
<script>
/* —— 预览稿胶水：让真实页面里的交互在本地可演示，不改任何业务逻辑 —— */
(function(){
  var H = document.documentElement;
  var TINT_KEY = 'sqlreport_preview_tint';
  try { var t = localStorage.getItem(TINT_KEY); if (t) H.dataset.tint = t; } catch(e){}

  function toast(msg){
    var el = document.getElementById('pv-toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function(){ el.classList.remove('show'); }, 1900);
  }
  window.__pvToast = toast;

  /* ---- 侧栏三态（协议同生产：html.sb-rail / html.sb-wide） ---- */
  var handle = document.querySelector('.sb-handle');
  if (handle) {
    var clone = handle.cloneNode(true);
    handle.parentNode.replaceChild(clone, handle);
    var arrow = clone.querySelector('.sb-arrow');
    clone.addEventListener('click', function(e){ e.stopPropagation(); H.classList.toggle('sb-rail'); });
    clone.addEventListener('mousemove', function(e){
      if (!arrow) return;
      var r = clone.getBoundingClientRect();
      arrow.style.top = Math.max(16, Math.min(r.height - 52, e.clientY - r.top)) + 'px';
    });
  }

  /* ---- 页签 ---- */
  document.querySelectorAll('.tabs .tab').forEach(function(tab){
    tab.onclick = function(e){
      e.preventDefault();
      document.querySelectorAll('.tabs .tab').forEach(function(x){ x.classList.remove('active'); });
      tab.classList.add('active');
      document.querySelectorAll('.tabpanel').forEach(function(p){
        p.classList.toggle('active', p.dataset.panel === tab.dataset.tab);
      });
      window.scrollTo({top:0,behavior:'smooth'});
    };
  });

  /* ---- 抽屉 / 对话框 ---- */
  window.openPanel = function(id){ var el = document.getElementById(id); if (el) el.classList.add('open'); };
  window.closePanel = function(id){ var el = document.getElementById(id); if (el) el.classList.remove('open'); };
  document.querySelectorAll('.modal').forEach(function(m){
    m.addEventListener('click', function(e){ if (e.target === m) m.classList.remove('open'); });
  });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape') document.querySelectorAll('.modal.open,.side-panel.open').forEach(function(x){ x.classList.remove('open'); });
  });

  /* ---- 分段控件（列表/卡片视图真的互斥切换，与生产 setReportsView 语义一致） ---- */
  window.setReportsView = function(v){
    document.querySelectorAll('.view-list').forEach(function(x){ x.classList.toggle('hidden', v !== 'list'); });
    document.querySelectorAll('.view-card').forEach(function(x){ x.classList.toggle('hidden', v !== 'card'); });
    document.querySelectorAll('#rpt-view-seg button[data-view]').forEach(function(b){
      b.classList.toggle('active', b.getAttribute('data-view') === v);
    });
  };
  document.querySelectorAll('.segment').forEach(function(seg){
    seg.querySelectorAll('button').forEach(function(b){
      b.onclick = function(e){
        e.preventDefault();
        seg.querySelectorAll('button').forEach(function(x){ x.classList.remove('active'); });
        b.classList.add('active');
        if (b.dataset.view) window.setReportsView(b.dataset.view);
      };
    });
  });
  /* ---- 分类树：点父节点转动箭头 ---- */
  document.querySelectorAll('.tree .cat[data-has-kids]').forEach(function(c){
    c.addEventListener('click', function(){ c.classList.toggle('open'); });
  });

  /* ---- 快筛行：操作符 → 联动值输入框（契约与生产 render.py::toggleFilterInput 完全一致：
         nofilter/isempty/notempty → 隐藏并 disabled；其余 → 显示并启用） ---- */
  window.toggleFilterInput = function(inputName, select){
    var input = document.getElementsByName(inputName)[0];
    if (!input) return;
    var val = select.value;
    if (val === 'nofilter' || val === 'isempty' || val === 'notempty') {
      input.style.display = 'none';
      input.disabled = true;
    } else {
      input.style.display = '';
      input.disabled = false;
    }
  };
  document.querySelectorAll('.qf-row .filter-op').forEach(function(sel){
    sel.addEventListener('change', function(){ window.toggleFilterInput(sel.name.replace(/^op_/, 'f_'), sel); });
    /* 首次渲染按当前选中项同步一次（生产由 common.js 的 initPage 负责，预览稿需自己接） */
    window.toggleFilterInput(sel.name.replace(/^op_/, 'f_'), sel);
  });

  /* ---- API 行展开 ---- */
  document.querySelectorAll('.api-row .api-main').forEach(function(m){
    m.addEventListener('click', function(e){
      if (e.target.closest('a,button')) return;
      m.parentNode.classList.toggle('open');
    });
  });

  /* ---- 内部跳转与表单提交拦截（预览稿无后端） ---- */
  document.addEventListener('click', function(e){
    var a = e.target.closest('a');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#' || /^https?:/.test(href)) return;
    e.preventDefault();
    toast('预览稿：真实环境将跳转 ' + href);
  }, true);
  document.addEventListener('submit', function(e){
    e.preventDefault();
    toast('预览稿：真实环境将提交到 ' + (e.target.getAttribute('action') || '当前页'));
  }, true);

  /* ---- 保存栏在预览里固定展示 ---- */
  document.querySelectorAll('.formbar').forEach(function(b){ b.style.position = 'static'; });

  /* ---- 预览条：换页 + 换色调 ---- */
  function buildBar(){
    var bar = document.createElement('div');
    bar.id = 'pv-bar';
    bar.innerHTML = '<span class="tag">UI v2 预览</span>';
    PAGE_LIST.forEach(function(p){
      var a = document.createElement('a');
      a.href = p[0];
      a.textContent = p[2];
      if (p[0] === CURRENT) a.className = 'on';
      bar.appendChild(a);
    });
    var sep = document.createElement('span'); sep.className = 'sep'; bar.appendChild(sep);
    [['', '鸢尾'], ['steel', '石墨蓝'], ['pine', '松绿']].forEach(function(t){
      var b = document.createElement('button');
      b.textContent = t[1];
      b.onclick = function(){
        if (t[0]) H.dataset.tint = t[0]; else delete H.dataset.tint;
        try { localStorage.setItem(TINT_KEY, t[0]); } catch(e){}
        bar.querySelectorAll('button').forEach(function(x){ x.classList.remove('on'); });
        b.classList.add('on');
      };
      if ((H.dataset.tint || '') === t[0]) b.className = 'on';
      bar.appendChild(b);
    });
    document.body.appendChild(bar);
    var t = document.createElement('div'); t.id = 'pv-toast'; document.body.appendChild(t);
  }
  var PAGE_LIST = __PAGES__;
  var CURRENT = __CURRENT__;
  buildBar();
})();
</script>
"""


def clean_inline_styles(html: str) -> str:
    """内联样式只保留布局/行为性声明，其余交给 app.css（正是生产实施要做的事）。"""
    def repl(m: re.Match) -> str:
        kept = []
        for decl in m.group(1).split(";"):
            if ":" not in decl:
                continue
            prop = decl.split(":", 1)[0].strip().lower()
            if any(prop.startswith(p) for p in DROP_DECL):
                continue
            kept.append(decl.strip())
        return 'style="%s"' % ";".join(kept) if kept else ""
    return re.sub(r'style="([^"]*)"', repl, html)


def build(raw_name: str, css: str, current: str, pages_js: str) -> str | None:
    path = os.path.join(RAW, raw_name)
    if not os.path.isfile(path):
        return None
    html = open(path, encoding="utf-8").read()
    # 单一来源验证：移除页面级 <style> 补丁 + 旧公共资产外链，
    # 只用 app.css 渲染——与实施目标（render.py 单一来源）一致
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    html = re.sub(r'<link[^>]+href="/static/vendor/[^"]*"[^>]*>', "", html)
    html = re.sub(r'<script[^>]+src="/static/vendor/[^"]*"[^>]*>\s*</script>', "", html)
    html = re.sub(r'<script[^>]+src="/static/vendor/[^"]*"[^>]*/>', "", html)
    html = re.sub(r'<link[^>]+href="/favicon\.ico"[^>]*>', "", html)
    html = re.sub(r'\s+target="_blank"', "", html)
    html = clean_inline_styles(html)
    head = _BAR_CSS + "<style>\n%s\n</style>\n" % css
    html = html.replace("</head>", head + "</head>", 1)
    glue = _GLUE.replace("__PAGES__", pages_js).replace("__CURRENT__", "'%s'" % current)
    html = html.replace("</body>", glue + "</body>", 1)
    return html


def main() -> int:
    css = open(CSS, encoding="utf-8").read()
    pages_js = "[" + ",".join("['%s','%s','%s']" % p for p in PAGES) + "]"
    made = 0
    for out_name, raw_name, label in PAGES:
        html = build(raw_name, css, out_name, pages_js)
        if html is None:
            print(f"  跳过 {label}（缺少 {raw_name}）")
            continue
        with open(os.path.join(OUT, out_name), "w", encoding="utf-8") as f:
            f.write(html)
        made += 1
        print(f"  生成 {out_name}  ({len(html) // 1024} KB)")
    print(f"共 {made} 个预览稿 → {OUT}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
