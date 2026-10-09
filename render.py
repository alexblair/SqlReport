"""
render.py — HTML 渲染模板层

职责：
提供基于 string.Template 的公共 HTML 渲染函数，统一页面头/尾/导航栏/
CSS/JS 资源。避免 report.py 和 config.py 各自维护一套 HTML 模板。

设计原则：
- 使用 string.Template（Python 标准库），零外部依赖
- 模板为 Python 字符串常量，无外部模板文件
- 渲染函数接收纯数据 dict，返回 HTML 字符串
- 页面特定的 CSS/JS 通过参数传入，不包含在公共模板中
"""

import string
import html as html_mod
import urllib.parse
import time
import json
import hashlib
import os
import threading
from decimal import Decimal
import app_config
import branding
import redis_cache
import static_cache
from filter_help import (render_filter_help, FILTER_HINT_SUFFIX,
                       render_nested_filter_help_popup, nested_filter_help_content)
import markdown_render

# ---------------------------------------------------------------------------
# SVG 图标辅助（替代 emoji 字符，符合设计规范 icon 集合）
# ---------------------------------------------------------------------------

_ICONS = {
    "alert": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1v5M8 11.5v.5"/><circle cx="8" cy="8" r="7"/></svg>',
    "search": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="5"/><line x1="10" y1="10" x2="14" y2="14"/></svg>',
    "file": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 3h7l5 5v7a1 1 0 01-1 1H3a1 1 0 01-1-1V4a1 1 0 011-1z"/><polyline points="7,3 7,8 12,8"/></svg>',
    "settings": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.3 3.3l1.4 1.4M11.3 11.3l1.4 1.4M3.3 12.7l1.4-1.4M11.3 4.7l1.4-1.4"/></svg>',
    "list": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="2" y1="4" x2="14" y2="4"/><line x1="2" y1="8" x2="14" y2="8"/><line x1="2" y1="12" x2="14" y2="12"/></svg>',
    "folder": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M1.5 3a1 1 0 011-1h4l2 2h5a1 1 0 011 1v7a1 1 0 01-1 1h-11a1 1 0 01-1-1V4a1 1 0 011-1z"/></svg>',
    "chart": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="10" width="3" height="4" rx.5"/><rect x="6.5" y="6" width="3" height="8" rx.5"/><rect x="11" y="2" width="3" height="12" rx.5"/></svg>',
    "key": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M14.5 1.5l-3 3M3 9V6a3 3 0 013-3h3"/><circle cx="8.5" cy="8.5" r="2.5"/></svg>',
    "calendar": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="11" rx1.5"/><line x1="2" y1="7" x2="14" y2="7"/><line x1="5" y1="1.5" x2="5" y2="4"/><line x1="11" y1="1.5" x2="11" y2="4"/></svg>',
    "refresh": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="2,8 4.5,5.5 7,8"/><path d="M11 2.5A5.5 5.5 0 0114 7h-2a3.5 3.5 0 00-3.5-3.5"/></svg>',
    "check": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3.5,8.5 6.5,11.5 12.5,4"/></svg>',
    "x": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>',
    "info": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="7"/><path d="M8 7v4M8 10.5v.5"/></svg>',
    "edit": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3L4 14H1V11z"/></svg>',
    "plus": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>',
    "chevron-down": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="4,6 8,10 12,6"/></svg>',
    "chevron-right": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="6,4 10,8 6,12"/></svg>',
    "chevron-up": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="4,10 8,6 12,10"/></svg>',
    "chevron-left": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="10,4 6,8 10,12"/></svg>',
    "copy": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="5" y="5" width="9" height="9" rx1"/><path d="M11 11V3a2 2 0 00-2-2H3"/></svg>',
    "trash": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="2,4 14,4"/><path d="M4 4l1 10h6l1-10"/><path d="M6 7v5M10 7v5"/></svg>',
    "download": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 2v8M4 10l4 4 4-4"/><path d="M2 12v2h12v-2"/></svg>',
    "database": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><ellipse cx="8" cy="5" rx="7" ry="3"/><path d="M1 5v6c0 1.66 3.13 3 7 3s7-1.34 7-3V5"/><path d="M1 11v2c0 1.66 3.13 3 7 3s7-1.34 7-3v-2"/></svg>',
    "users": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="5" cy="5" r="2.5"/><circle cx="11" cy="5" r="2.5"/><path d="M1 14a5 5 0 0110 0"/><circle cx="11" cy="8" r="2"/></svg>',
    "eye": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></svg>',
    "play": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polygon points="4,1 14,8 4,15"/></svg>',
    "link": '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5 3h4a3 3 0 013 3v2"/><path d="M11 13h-4a3 3 0 01-3-3V8"/></svg>',
}

def _icon(name: str) -> str:
    """返回设计规范内联的 SVG 图标 HTML。name 不在集合中时返回空串。"""
    return _ICONS.get(name, "")

# 侧边栏折叠图标（保持原有语义）
_CHEVRON_DOWN = _icon("chevron-down")
_CHEVRON_RIGHT = _icon("chevron-right")

# ---------------------------------------------------------------------------
# 公共 CSS（全站单一来源：report.py + config.py + audit + 登录页共享）
# ---------------------------------------------------------------------------

# 基础片段（reset + body 字体栈 + fadeUp 关键帧），供登录页等独立页面复用
_BASE_CSS = """
/* ============================================================================
   SqlReport UI v2 · 石墨·鸢尾（Graphite & Iris）
   全站单一视觉来源：令牌 → 基座 → 组件 → 页面 → 兼容层。
   设计基线：4px 间距栅格 / 一套字阶 / 一套圆角 / 一套阴影 / 单一强调色。
   禁止在页面级另写样式或散写 hex（除本文件令牌区）。
   ========================================================================= */

/* ---------------------------------------------------------------- 1. 令牌 */
:root{
  /* 中性（冷石墨） */
  --n0:#ffffff;
  --bg-app:#f4f6f9;        /* 页面底 */
  --bg-surface:#ffffff;    /* 卡片/表格面 */
  --bg-subtle:#f7f8fa;     /* 表头/内嵌 */
  --bg-sunken:#f1f3f7;     /* 下沉块（快筛行/代码内嵌） */
  --bg-hover:#f5f7fa;
  --bg-active:#eceff4;
  --line:#dde0e4;          /* 常规分隔线 */
  --line-soft:#e8eaee;     /* 弱分隔线 */
  --line-strong:#c1c4cb;   /* 输入框描边 */
  --ink-1:#11151d;         /* 主文字 17.9:1 */
  --ink-2:#555b68;         /* 次文字 6.7:1 */
  --ink-3:#6c717c;         /* 辅助  4.8:1 */
  --ink-4:#9a9ea7;         /* 占位/禁用 */

  /* 主色（鸢尾） */
  --accent:#5d61e0;
  --accent-hover:#4e4ecc;
  --accent-press:#3e3caa;
  --accent-ink:#3e3caa;    /* 浅底上的主色文字 8.5:1 */
  --accent-soft:#f4f6ff;
  --accent-soft-2:#e7ebff;
  --accent-line:#d1d9ff;

  /* 语义 */
  --ok:#048b56;      --ok-ink:#00643a;      --ok-soft:#e6f9ed;      --ok-line:#b8e8cd;
  --warn:#d78c00;    --warn-ink:#9a5700;    --warn-soft:#fff4e0;    --warn-line:#f5ddb0;
  --danger:#d02b31;  --danger-ink:#a9131f;  --danger-soft:#ffefed;  --danger-line:#f8cdc9;
  --info:#0d7dd4;    --info-ink:#005fad;    --info-soft:#eaf6ff;    --info-line:#bfe1f8;

  /* 代码面（深色）：底色与文字色成对声明，禁止分开写（曾因此出现 1.02:1 隐形文字） */
  --code-bg:#0f131b;      /* 代码面底 */
  --code-bg-2:#191d26;    /* 代码面次级（工具条） */
  --code-border:#292e37;
  --code-ink:#e2e6ef;     /* 正文 14.9:1 */
  --code-dim:#9fa5b0;     /* 次级 7.5:1 */
  --code-op:#c8ccd6;      /* 运算符/标点 11.6:1 */
  --code-kw:#a9a5ff;      /* 关键字 8.4:1 */
  --code-fn:#7ac8f5;      /* 函数 10.1:1 */
  --code-str:#88d9a5;     /* 字符串 11.1:1 */
  --code-num:#eebe7c;     /* 数字 10.9:1 */
  --code-comment:#9298a5; /* 注释 6.4:1 */

  /* 侧栏 */
  --sidebar-bg:#10121a;
  --sidebar-bg-2:#1b1e26;
  --sidebar-w:248px;
  --sidebar-rail:60px;
  --sidebar-ink:#b4b7c2;
  --sidebar-ink-dim:#83868f;
  --sidebar-ink-active:#ffffff;
  --sidebar-hover:rgba(255,255,255,.055);
  --sidebar-active:rgba(255,255,255,.09);
  --sidebar-line:rgba(255,255,255,.075);

  /* 字阶（px/行高）——中文优先，正文 14/1.6 */
  --font-sans:"Inter","SF Pro Text",-apple-system,BlinkMacSystemFont,"Segoe UI Variable Text","Segoe UI",
              "PingFang SC","HarmonyOS Sans SC","MiSans","Source Han Sans SC","Noto Sans CJK SC","Microsoft YaHei",
              system-ui,sans-serif;
  --font-mono:"JetBrains Mono","SFMono-Regular",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
  --fs-11:11px;  --lh-11:16px;
  --fs-12:12px;  --lh-12:18px;
  --fs-13:13px;  --lh-13:20px;
  --fs-14:14px;  --lh-14:22px;
  --fs-16:16px;  --lh-16:24px;
  --fs-18:18px;  --lh-18:26px;
  --fs-22:22px;  --lh-22:30px;
  --fs-28:28px;  --lh-28:36px;

  /* 间距（4px 栅格） */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px; --sp-10:40px;

  /* 圆角 / 阴影 / 动效 */
  --r-xs:4px; --r-sm:6px; --r-md:10px; --r-lg:14px; --r-full:999px;
  --sh-1:0 1px 2px rgba(17,21,29,.05);
  --sh-2:0 2px 4px rgba(17,21,29,.04), 0 8px 20px -6px rgba(17,21,29,.12);
  --sh-3:0 4px 8px rgba(17,21,29,.05), 0 24px 56px -16px rgba(17,21,29,.26);
  --t-fast:120ms; --t-med:180ms;
  --ease:cubic-bezier(.2,.8,.2,1);
}

/* ------------------------------------------------------------ 2. 基座 */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  font-family:var(--font-sans);font-size:var(--fs-14);line-height:var(--lh-14);
  color:var(--ink-1);background:var(--bg-app);min-height:100vh;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
  font-feature-settings:"cv11" 1,"ss01" 1;
}
a{color:var(--accent-ink);text-decoration:none}
a:hover{text-decoration:none;color:var(--accent-hover)}
h1,h2,h3,h4{font-weight:600;line-height:1.3;color:var(--ink-1)}
h1{font-size:var(--fs-22);line-height:var(--lh-22);letter-spacing:-.01em}
h2{font-size:var(--fs-14);letter-spacing:0}
h3{font-size:var(--fs-13)}
code,kbd,samp,pre,.mono{font-family:var(--font-mono);font-variant-ligatures:none}
/* 兜底：未声明尺寸的内联 SVG 一律按 16px 图标处理。
   生产里不少图标只写了 viewBox（旧 CSS 靠上下文 class 兜底），缺此规则会渲染成 300×150 巨图。 */
svg:not([width]){width:16px;height:16px;flex:0 0 auto}
::selection{background:var(--accent-soft-2);color:var(--accent-press)}
:focus-visible{outline:2px solid var(--accent);outline-offset:1px;border-radius:var(--r-xs)}
::placeholder{color:var(--ink-4);opacity:1}
*{scrollbar-width:thin;scrollbar-color:#c6cbd4 transparent}
*::-webkit-scrollbar{width:10px;height:10px}
*::-webkit-scrollbar-thumb{background:#ced3db;border:3px solid transparent;background-clip:content-box;border-radius:99px}
*::-webkit-scrollbar-thumb:hover{background:#aeb5c0;border:3px solid transparent;background-clip:content-box}
*::-webkit-scrollbar-track{background:transparent}
.muted{color:var(--ink-3)}
.sub,.meta{color:var(--ink-3);font-size:var(--fs-12);line-height:var(--lh-12)}
.grow{flex:1 1 auto}

/* ---------------------------------------------------------- 15. 登录页 */
body:has(.login-box){
  display:grid;grid-template-columns:minmax(0,1.02fr) minmax(0,1fr);min-height:100vh;
  background:var(--bg-surface);align-items:stretch;justify-items:stretch;
}
body:has(.login-box)::before{
  content:"";grid-column:1;align-self:stretch;min-height:100vh;
  background:
    radial-gradient(120% 90% at 12% 8%, rgba(122,126,240,.34), transparent 55%),
    radial-gradient(90% 70% at 90% 96%, rgba(63,63,176,.42), transparent 60%),
    linear-gradient(160deg,#14161f 0%,#0e1017 60%,#0b0d13 100%);
}
.login-box{
  grid-column:2;display:flex;flex-direction:column;justify-content:center;align-items:stretch;
  width:100%;max-width:400px;margin:0 auto;padding:var(--sp-10) var(--sp-6);
}
.login-box h1{
  display:flex;align-items:center;gap:10px;font-size:var(--fs-28);line-height:var(--lh-28);
  font-weight:600;letter-spacing:-.02em;margin-bottom:6px;
}
.login-box h1 .logo{
  width:32px;height:32px;border-radius:9px;display:grid;place-items:center;flex:0 0 32px;
  font-size:12px;font-weight:700;color:#fff;
  background:linear-gradient(150deg,#7b7ff0,#5050d8 55%,#3f3fb0);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.28),0 2px 6px rgba(62,60,170,.35);
}
.login-subtitle{font-size:var(--fs-14);color:var(--ink-3);margin-bottom:var(--sp-8)}
.login-box form{display:flex;flex-direction:column;gap:6px}
.login-box form label{font-size:var(--fs-12);font-weight:500;color:var(--ink-2);margin-top:var(--sp-2)}
.login-box form input{height:38px;font-size:var(--fs-14)}
.login-box form button[type=submit]{
  height:38px;margin-top:var(--sp-4);border:0;border-radius:var(--r-sm);cursor:pointer;
  background:var(--accent);color:#fff;font-size:var(--fs-14);font-weight:600;letter-spacing:.01em;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 1px 2px rgba(62,60,170,.28);
  transition:background var(--t-fast) var(--ease);
}
.login-box form button[type=submit]:hover{background:var(--accent-hover)}
.login-footer{margin-top:var(--sp-6);font-size:var(--fs-12);color:var(--ink-4)}
@media (max-width:860px){
  body:has(.login-box){grid-template-columns:1fr}
  body:has(.login-box)::before{display:none}
  .login-box{grid-column:1;max-width:400px}
}

/* —— 会话过期 / 表单内联错误 / 横幅 —— */
.notice{
  padding:10px 14px;margin-bottom:var(--sp-3);border-radius:var(--r-sm);
  background:var(--warn-soft);border:1px solid var(--warn-line);color:var(--warn-ink);font-size:var(--fs-13);
}
.error{
  padding:10px 14px;margin-bottom:var(--sp-3);border-radius:var(--r-sm);
  background:var(--danger-soft);border:1px solid var(--danger-line);color:var(--danger-ink);font-size:var(--fs-13);
}
.banner{
  display:flex;gap:var(--sp-3);align-items:flex-start;padding:12px 14px;margin-bottom:var(--sp-3);
  border-radius:var(--r-sm);font-size:var(--fs-13);line-height:1.6;
  background:var(--info-soft);border:1px solid var(--info-line);color:var(--info-ink);
}
.banner-info{background:var(--info-soft);border-color:var(--info-line);color:var(--info-ink)}
.banner strong{font-weight:600}
.banner a{color:inherit;text-decoration:underline;text-underline-offset:2px}
.flash-close{margin-left:auto;cursor:pointer;opacity:.55;font-size:var(--fs-14);line-height:1;padding:0 2px}
.flash-close:hover{opacity:1}

/* —— 错误页（原 server.py 内联样式） —— */
.err-box{
  min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:var(--sp-2);text-align:center;padding:var(--sp-6);
}
.err-code{font-size:60px;line-height:1;font-weight:600;letter-spacing:-.03em;color:var(--accent-ink)}
.err-title{font-size:var(--fs-16);color:var(--ink-2)}
.err-back{
  display:inline-flex;align-items:center;height:34px;padding:0 16px;margin-top:var(--sp-3);
  background:var(--accent);color:#fff;border-radius:var(--r-sm);font-size:var(--fs-13);font-weight:500;
}
.err-back:hover{background:var(--accent-hover);color:#fff}
"""

_COMMON_CSS = """
/* ------------------------------------------------------------ 3. 页壳 */
.app{display:flex;min-height:100vh}
.sidebar{
  width:var(--sidebar-w);flex:0 0 var(--sidebar-w);background:var(--sidebar-bg);
  color:var(--sidebar-ink);position:fixed;inset:0 auto 0 0;display:flex;flex-direction:column;
  z-index:40;border-right:1px solid rgba(0,0,0,.4);
}
.main{margin-left:var(--sidebar-w);flex:1;min-width:0;display:flex;flex-direction:column}
.container{width:100%;max-width:1560px;margin:0 auto;padding:0 28px var(--sp-10)}

/* 侧栏品牌 */
.sidebar .brand{
  display:flex;align-items:center;gap:10px;padding:18px 18px 16px;color:#fff;
  font-weight:600;font-size:var(--fs-14);letter-spacing:-.005em;text-decoration:none;
  border-bottom:1px solid var(--sidebar-line);margin-bottom:10px;
}
.sidebar .brand:hover{text-decoration:none;color:#fff}
.sidebar .brand .logo{
  width:26px;height:26px;border-radius:7px;display:grid;place-items:center;flex:0 0 26px;
  font-size:11px;font-weight:700;letter-spacing:.02em;color:#fff;
  background:linear-gradient(150deg,#7b7ff0,#5050d8 55%,#3f3fb0);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.28), 0 1px 2px rgba(0,0,0,.4);
}
.sidebar .brand .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* 分组与导航 */
.nav-group{
  padding:14px 20px 6px;font-size:10px;line-height:14px;color:var(--sidebar-ink-dim);
  font-weight:600;letter-spacing:.1em;text-transform:uppercase;
}
.nav-item{
  display:flex;align-items:center;gap:10px;margin:1px 10px;padding:7px 10px;
  border-radius:var(--r-sm);color:var(--sidebar-ink);font-size:var(--fs-13);line-height:18px;
  text-decoration:none;border:0;background:transparent;width:calc(100% - 20px);text-align:left;
  position:relative;cursor:pointer;transition:background var(--t-fast) var(--ease),color var(--t-fast) var(--ease);
}
.nav-item:hover{background:var(--sidebar-hover);color:#fff;text-decoration:none}
.nav-item.nav-active{background:var(--sidebar-active);color:var(--sidebar-ink-active);font-weight:600}
.nav-item.nav-active::before{
  content:"";position:absolute;left:-10px;top:6px;bottom:6px;width:2px;border-radius:0 2px 2px 0;background:#8b8ff5;
}
.nav-item svg{width:16px;height:16px;flex:0 0 16px;opacity:.85;stroke-width:1.6}
.nav-item:hover svg,.nav-item.nav-active svg{opacity:1}
.nav-item a{color:inherit;text-decoration:none}
.nav-badge{
  margin-left:auto;font-size:10px;line-height:16px;min-width:18px;text-align:center;
  background:rgba(255,255,255,.08);color:var(--sidebar-ink);padding:0 6px;border-radius:var(--r-full);
  font-weight:600;font-variant-numeric:tabular-nums;
}
.nav-item.nav-active .nav-badge{background:rgba(255,255,255,.16);color:#fff}
.sidebar .spacer{flex:0 0 1.5em;min-height:24px}
.account{
  border-top:1px solid var(--sidebar-line);padding:12px 14px;display:flex;align-items:center;
  gap:9px;font-size:var(--fs-12);margin-top:auto;
}
.account .avatar{
  width:26px;height:26px;border-radius:var(--r-full);background:var(--sidebar-bg-2);display:grid;
  place-items:center;color:#dfe1e8;font-size:11px;font-weight:600;flex:0 0 26px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.06);
}
.account .who{color:#dfe1e8;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.account .out{margin-left:auto;color:var(--sidebar-ink-dim);font-size:var(--fs-12);text-decoration:none;padding:4px 6px;border-radius:var(--r-xs)}
.account .out:hover{color:#fff;background:var(--sidebar-hover)}
.account .out-icon{display:none}

/* 折叠手柄（三态协议不变） */
.sb-handle{
  position:absolute;top:0;bottom:0;right:0;width:12px;padding:0;border:0;background:transparent;
  cursor:pointer;z-index:5;font:inherit;transition:background var(--t-fast) linear;
}
.sb-handle:hover{background:rgba(255,255,255,.07)}
.sb-handle:focus-visible{outline:none;box-shadow:inset 0 0 0 2px var(--accent)}
.sb-arrow{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:grid;place-items:center;pointer-events:none;transition:top .08s linear}
.sb-arrow svg{width:11px;height:18px;color:var(--sidebar-ink-dim);transition:transform var(--t-med) var(--ease);transform:rotate(180deg)}
.sb-handle:hover .sb-arrow svg{color:#fff}
html.sb-rail .sb-arrow svg{transform:none}

/* 三态：默认 / sb-wide = 248px；sb-rail = 60px 图标条 */
html.sb-rail .sidebar{width:var(--sidebar-rail);flex-basis:var(--sidebar-rail)}
html.sb-rail .main{margin-left:var(--sidebar-rail)}
html.sb-rail .sidebar .brand{justify-content:center;padding:18px 8px 16px;margin-bottom:10px}
html.sb-rail .sidebar .brand .name,
html.sb-rail .sidebar .nav-group,
html.sb-rail .sidebar .nav-item span,
html.sb-rail .sidebar .nav-badge,
html.sb-rail .sidebar .who,
html.sb-rail .sidebar .account .out{display:none}
html.sb-rail .sidebar .nav-item{justify-content:center;margin:2px 8px;padding:8px}
html.sb-rail .sidebar .nav-item.nav-active::before{left:-8px}
html.sb-rail .account{flex-direction:column;justify-content:center;align-items:center;gap:6px;padding:10px 8px}
html.sb-rail .account .avatar{width:26px;height:26px;font-size:10px}
html.sb-rail .account .out-icon{
  display:grid;place-items:center;width:26px;height:26px;border-radius:var(--r-xs);
  color:var(--sidebar-ink-dim);text-decoration:none;flex:0 0 26px;
}
html.sb-rail .account .out-icon:hover{background:var(--sidebar-hover);color:#fff}
html.sb-rail .account .out-icon svg{width:15px;height:15px}

@media (max-width:1024px){
  html:not(.sb-wide) .sidebar{width:var(--sidebar-rail);flex-basis:var(--sidebar-rail)}
  html:not(.sb-wide) .main{margin-left:var(--sidebar-rail)}
  html:not(.sb-wide) .sidebar .brand{justify-content:center;padding:18px 8px 16px}
  html:not(.sb-wide) .sidebar .brand .name,
  html:not(.sb-wide) .sidebar .nav-group,
  html:not(.sb-wide) .sidebar .nav-item span,
  html:not(.sb-wide) .sidebar .nav-badge,
  html:not(.sb-wide) .sidebar .who,
  html:not(.sb-wide) .sidebar .account .out{display:none}
  html:not(.sb-wide) .sidebar .nav-item{justify-content:center;margin:2px 8px;padding:8px}
  html:not(.sb-wide) .account{flex-direction:column;justify-content:center;align-items:center;gap:6px;padding:10px 8px}
  html:not(.sb-wide) .account .avatar{width:26px;height:26px;font-size:10px}
  html:not(.sb-wide) .account .out-icon{display:grid;place-items:center;width:26px;height:26px;border-radius:var(--r-xs);color:var(--sidebar-ink-dim);flex:0 0 26px}
  html:not(.sb-wide) .account .out-icon svg{width:15px;height:15px}
  html:not(.sb-wide) .sb-arrow svg{transform:none}
  html.sb-wide .sidebar{width:var(--sidebar-w);flex-basis:var(--sidebar-w);box-shadow:var(--sh-3);z-index:60}
  html.sb-wide .main{margin-left:var(--sidebar-rail)}
}
@media (pointer:coarse){.sb-handle{width:26px}}

/* ------------------------------------------------- 4. 页头（粘性） */
.page-head{
  position:sticky;top:0;z-index:30;display:flex;align-items:flex-end;gap:var(--sp-4);
  flex-wrap:wrap;padding:18px 0 14px;margin:0 0 var(--sp-5);
  background:color-mix(in srgb,var(--bg-app) 88%,transparent);
  -webkit-backdrop-filter:saturate(1.6) blur(10px);backdrop-filter:saturate(1.6) blur(10px);
  border-bottom:1px solid var(--line);
}
.page-head > div:first-child{min-width:0;flex:1 1 auto}
.page-head h1{display:flex;align-items:center;gap:var(--sp-3);font-size:var(--fs-22);line-height:var(--lh-22);font-weight:600;letter-spacing:-.015em;flex-wrap:wrap}
.page-head .sub{margin-top:5px;font-size:var(--fs-12);color:var(--ink-3);display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.page-head .actions{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.crumb{font-size:var(--fs-12);color:var(--ink-3);margin-bottom:6px;display:flex;align-items:center;gap:6px}
.crumb a{color:var(--ink-3)}
.crumb a:hover{color:var(--accent-ink)}
.summary-line{display:flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-12);color:var(--ink-3)}

/* ------------------------------------------------- 5. 卡片 / 区块 */
.card{
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);
  margin-bottom:var(--sp-4);overflow:hidden;
}
.card > .card-head{
  display:flex;align-items:center;gap:var(--sp-2);padding:12px var(--sp-4);
  border-bottom:1px solid var(--line-soft);background:var(--bg-surface);
}
.card > .card-head h2,.card-head h2{font-size:var(--fs-14);font-weight:600;letter-spacing:-.005em}
.card .card-head .actions{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2)}
.card > :not(.card-head){padding:var(--sp-4)}
.card > .card-head ~ *{padding:var(--sp-4)}
.card > table,.card > .table-wrap,.card > form > .table-wrap{padding:0}
.card > .table-wrap{border:0;border-radius:0;margin:0}
.card > form{padding:var(--sp-4)}
.card > .formbar{margin:0;border-radius:0;border-left:0;border-right:0;border-bottom:0;box-shadow:none}
.card-head .form-section,.form-section{font-size:var(--fs-13);font-weight:600;color:var(--ink-1);display:flex;align-items:center;gap:var(--sp-2)}
.section{margin-bottom:var(--sp-4)}
.section-title{
  display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap;
  font-size:var(--fs-14);font-weight:600;color:var(--ink-1);padding:12px var(--sp-4);
  border-bottom:1px solid var(--line-soft);
}
.section-title .actions{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2)}
.section-title .ico svg{display:block;width:15px;height:15px}
.tree .cat > svg{width:15px;height:15px;flex:0 0 15px;color:var(--ink-4)}
.tree .cat.active > svg{color:var(--accent)}
.tree .cat > svg[data-chevron]{transition:transform var(--t-fast) var(--ease)}
.tree .cat.open > svg[data-chevron]{transform:rotate(90deg)}
.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--sp-4);align-items:stretch}
.grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-3)}
.grid-stat{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--sp-3)}
.split{display:grid;grid-template-columns:264px minmax(0,1fr);gap:var(--sp-4);align-items:start}
.span-full{grid-column:1 / -1}
aside.card{position:sticky;top:78px}

/* 统计磁贴 */
.stat-tile{
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);
  padding:var(--sp-4);display:flex;flex-direction:column;gap:2px;min-width:0;
}
.stat-tile .num{font-size:var(--fs-28);line-height:var(--lh-28);font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat-tile .lbl{font-size:var(--fs-12);color:var(--ink-3)}
.stat-tile a{font-size:var(--fs-12);margin-top:auto;padding-top:6px;display:inline-flex;align-items:center;gap:4px}

/* ------------------------------------------------------------ 6. 按钮 */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:30px;padding:0 11px;border-radius:var(--r-sm);border:1px solid transparent;
  background:transparent;color:var(--ink-1);font:inherit;font-size:var(--fs-13);font-weight:500;
  line-height:1;cursor:pointer;white-space:nowrap;text-decoration:none;
  transition:background var(--t-fast) var(--ease),border-color var(--t-fast) var(--ease),
             color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease);
}
.btn:hover{text-decoration:none}
.btn:active{transform:translateY(.5px)}
.btn svg{width:15px;height:15px;flex:0 0 15px;opacity:.9}
.btn-primary{
  background:var(--accent);border-color:var(--accent);color:#fff;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 1px 2px rgba(62,60,170,.24);
}
.btn-primary:hover{background:var(--accent-hover);border-color:var(--accent-hover);color:#fff}
.btn-primary:active{background:var(--accent-press);border-color:var(--accent-press)}
.btn-secondary,.btn-outline{
  background:var(--bg-surface);border-color:var(--line-strong);color:var(--ink-1);
}
.btn-secondary:hover,.btn-outline:hover{background:var(--bg-hover);border-color:#a9aeb8;color:var(--ink-1)}
.btn-ghost{background:transparent;color:var(--ink-2)}
.btn-ghost:hover{background:var(--bg-active);color:var(--ink-1)}
.btn-danger{background:var(--bg-surface);border-color:var(--danger-line);color:var(--danger-ink);box-shadow:var(--sh-1)}
.btn-danger:hover{background:var(--danger-soft);border-color:#eda9a3;color:var(--danger-ink)}
.btn-danger-solid{background:var(--danger);border-color:var(--danger);color:#fff}
.btn-danger-solid:hover{background:#b81f26;border-color:#b81f26;color:#fff}
.btn-success{background:var(--ok);border-color:var(--ok);color:#fff}
.btn-info{background:var(--info);border-color:var(--info);color:#fff}
.btn-sm{height:26px;padding:0 9px;font-size:var(--fs-12);gap:5px}
.btn-sm svg{width:13px;height:13px;flex-basis:13px}
.btn-icon{width:30px;padding:0;justify-content:center}
.btn-icon.btn-sm{width:26px}
.btn:disabled,.btn[disabled],.btn-mini-disabled{opacity:.45;cursor:not-allowed;box-shadow:none}
.btn:disabled:hover,.btn[disabled]:hover{background:var(--bg-surface)}
/* 行内迷你按钮（表格操作列）：无边框低噪音，hover 才浮出底色 */
.btn-mini,.btn-mini-solid,.btn-mini-primary{
  display:inline-flex;align-items:center;justify-content:center;gap:4px;height:24px;padding:0 7px;
  border-radius:var(--r-xs);border:1px solid transparent;background:transparent;
  color:var(--ink-2);font-size:var(--fs-12);font-weight:500;line-height:1;cursor:pointer;
  text-decoration:none;transition:all var(--t-fast) var(--ease);
}
.btn-mini:hover{background:var(--bg-active);color:var(--ink-1)}
.btn-mini-solid{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-mini-solid:hover{background:var(--accent-hover);border-color:var(--accent-hover);color:#fff}
.btn-mini-primary{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent-ink)}
.btn-mini-primary:hover{background:var(--accent-soft-2);color:var(--accent-press)}
.btn-refresh{background:var(--bg-surface);border:1px solid var(--line-strong);color:var(--ink-2);height:26px;padding:0 9px;border-radius:var(--r-sm);font-size:var(--fs-12);cursor:pointer}
.btn-refresh:hover{background:var(--bg-hover);color:var(--ink-1)}

/* ------------------------------------------------------------ 7. 表单 */
input[type=text],input[type=password],input[type=number],input[type=search],input[type=email],input[type=url],
input[type=date],input[type=datetime-local],input[type=time],input[type=month],input[type=tel],
input:not([type]),select,textarea{
  font:inherit;font-size:var(--fs-13);color:var(--ink-1);background:var(--bg-surface);
  border:1px solid var(--line-strong);border-radius:var(--r-sm);height:32px;padding:0 10px;width:100%;
  transition:border-color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease),background var(--t-fast) var(--ease);
}
input:hover:not(:disabled),select:hover:not(:disabled),textarea:hover:not(:disabled){border-color:#a9aeb8}
input:focus,select:focus,textarea:focus{
  outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft-2);background:var(--bg-surface);
}
input:disabled,select:disabled,textarea:disabled{background:var(--bg-subtle);color:var(--ink-4);cursor:not-allowed}
select{
  appearance:none;-webkit-appearance:none;padding-right:26px;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%236c717c' stroke-width='1.4' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
}
select[multiple]{height:auto;padding:4px;background-image:none}
textarea{height:auto;min-height:88px;padding:8px 10px;line-height:var(--lh-13);resize:vertical}
input[type=checkbox],input[type=radio]{
  appearance:none;-webkit-appearance:none;width:15px;height:15px;flex:0 0 15px;border:1px solid var(--line-strong);
  border-radius:var(--r-xs);background:var(--bg-surface);cursor:pointer;position:relative;padding:0;
  transition:all var(--t-fast) var(--ease);
}
input[type=checkbox]:hover,input[type=radio]:hover{border-color:var(--accent)}
input[type=checkbox]:checked,input[type=radio]:checked{background:var(--accent);border-color:var(--accent)}
input[type=checkbox]:checked::after{
  content:"";position:absolute;left:4px;top:1px;width:5px;height:9px;
  border:solid #fff;border-width:0 1.8px 1.8px 0;transform:rotate(42deg);
}
input[type=radio]{border-radius:var(--r-full)}
input[type=radio]:checked::after{content:"";position:absolute;inset:4px;border-radius:var(--r-full);background:#fff}
input[type=checkbox]:focus-visible,input[type=radio]:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
label{font-size:var(--fs-13);color:var(--ink-2)}
.config-form > .field-row,form.config-form > *{margin-bottom:0}
.config-form{display:flex;flex-direction:column;gap:var(--sp-4)}
.config-form label{display:block;font-size:var(--fs-12);font-weight:500;color:var(--ink-2);margin-bottom:5px}
.config-form .field-hint,.field-hint{font-size:var(--fs-12);color:var(--ink-3);margin-top:5px;line-height:var(--lh-12)}
.check-group{display:flex;flex-wrap:wrap;gap:var(--sp-3)}
.check-inline,.check{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-13);color:var(--ink-1);cursor:pointer}
.check-inline input,.check input{margin:0}
.field-item{
  display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line);
  border-radius:var(--r-sm);background:var(--bg-surface);cursor:grab;user-select:none;
  transition:border-color var(--t-fast) var(--ease),background var(--t-fast) var(--ease);
}
.field-item:hover{border-color:var(--accent-line);background:var(--accent-soft)}
.drag-handle{color:var(--ink-4);font-size:var(--fs-14);cursor:grab;flex-shrink:0;line-height:1}
.drag-handle:hover{color:var(--ink-2)}
.field-up,.field-down{
  width:22px;height:22px;flex:0 0 22px;display:inline-grid;place-items:center;border-radius:var(--r-xs);
  border:1px solid var(--line);background:var(--bg-surface);color:var(--ink-3);cursor:pointer;font-size:10px;line-height:1;padding:0;
}
.field-up:hover,.field-down:hover{background:var(--bg-hover);color:var(--ink-1);border-color:var(--line-strong)}
/* 保存栏 */
.formbar{
  display:flex;align-items:center;gap:var(--sp-3);padding:12px var(--sp-4);background:var(--bg-surface);
  border:1px solid var(--line);border-radius:var(--r-md);position:sticky;bottom:12px;z-index:20;
  box-shadow:0 -1px 0 var(--line-soft),var(--sh-2);
}
.formbar .cancel{color:var(--ink-3);font-size:var(--fs-13);display:inline-flex;align-items:center;gap:5px}
.formbar .cancel:hover{color:var(--ink-1)}
.formbar .right{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2)}
.form-actions{display:flex;align-items:center;gap:var(--sp-2);padding-top:var(--sp-2)}
.form-actions .right,.form-actions .grow{margin-left:auto}

/* ------------------------------------------------------------ 8. 表格 */
.table-wrap{
  width:100%;overflow-x:auto;overflow-y:auto;max-height:calc(100vh - 130px);  /* 表内滚动 + 粘性表头（批次6 契约） */
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);margin-bottom:var(--sp-4);
}
.card .table-wrap,.card > .table-wrap{border:0;border-radius:0;margin-bottom:0}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--fs-13)}
table th{
  position:sticky;top:0;z-index:10;text-align:left;font-weight:600;font-size:var(--fs-12);
  line-height:18px;letter-spacing:0;text-transform:none;color:var(--ink-2);
  background:color-mix(in srgb,var(--bg-subtle) 92%,transparent);
  -webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);
  height:38px;vertical-align:middle;padding:0 12px;
  border-bottom:1px solid var(--line);white-space:nowrap;
}
table td{padding:9px 12px;border-bottom:1px solid var(--line-soft);color:var(--ink-1);vertical-align:middle}
table tbody tr:last-child td{border-bottom:0}
table tbody tr{transition:background var(--t-fast) var(--ease)}
table tbody tr:hover{background:var(--bg-hover)}
table tbody tr:has(input[type=checkbox]:checked){background:var(--accent-soft)}
table tr[id^=report-].anchor-hit,table tr.anchor-hit{background:var(--accent-soft);box-shadow:inset 3px 0 0 var(--accent)}
td.num,th.num,.num-cell{text-align:right;font-variant-numeric:tabular-nums}
td.ops-cell{text-align:right;white-space:nowrap}
td.ops-cell .btn-mini{margin-left:4px}
td.ops-cell .btn-mini:first-child{margin-left:0}
.name-cell strong{font-weight:600}
.name-cell a{font-weight:500}
.memo-cell{color:var(--ink-3);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.memo-cell:hover{color:var(--ink-2)}
.sql-cell,.rc-sql{font-family:var(--font-mono);font-size:var(--fs-12);color:var(--ink-2);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cfg-group{background:var(--bg-subtle);box-shadow:inset 1px 0 0 var(--line);font-weight:600;color:var(--ink-2);text-align:center}
td.cfg-group{text-align:center;font-variant-numeric:tabular-nums;color:var(--ink-2)}
.qf-row td{background:var(--bg-subtle);padding:5px 8px;border-bottom:1px solid var(--line-soft)}
.qf-row .filter-input,.qf-row select,.qf-row input{
  height:26px;font-size:var(--fs-12);padding:0 7px;border-color:var(--line-soft);background:var(--bg-surface);
}
.qf-row input:hover,.qf-row select:hover{border-color:var(--line-strong)}
.qf-row input:focus,.qf-row select:focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft-2)}
.qf-row .filter-input{min-width:72px}
.sort-links{display:inline-flex;align-items:center;gap:0}
.sort-link{color:var(--ink-1);font-weight:600;text-decoration:none;display:inline-flex;align-items:center;gap:2px}
.sort-link:hover{color:var(--accent-ink)}
.sort-arrow{color:var(--accent);font-size:9px;line-height:1;text-decoration:none}
.sort-num{
  display:inline-grid;place-items:center;min-width:15px;height:15px;padding:0 3px;margin-left:4px;
  background:var(--accent);color:#fff;border-radius:var(--r-full);font-size:10px;font-weight:600;
}
th[data-sort],th .th-sort{cursor:pointer}
.table-empty,.empty{
  padding:var(--sp-10) var(--sp-4);text-align:center;color:var(--ink-3);font-size:var(--fs-13);
  background:var(--bg-surface);
}
.empty .empty-title{font-size:var(--fs-14);font-weight:600;color:var(--ink-1);margin-bottom:4px}

/* 列宽体系：生产原本靠内联 style="width:.."，清理内联样式后列宽失控
   （名称列曾被压成「一」字一行）。改为 colgroup + table-layout:fixed 显式声明。 */
.table-fixed{table-layout:fixed}
.table-fixed > thead > tr > th,.table-fixed > tbody > tr > td{
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.table-fixed col.c-check{width:36px}
.table-fixed col.c-name{width:216px}
.table-fixed col.c-sql{width:180px}
.table-fixed col.c-cfg{width:76px}
.table-fixed col.c-pool{width:112px}
.table-fixed col.c-memo{width:160px}
.table-fixed col.c-path{width:176px}
.table-fixed col.c-api{width:96px}
.table-fixed col.c-ops{width:116px}
/* 无 colgroup 兜底：名称列保底宽度，宁可横向滚动也不竖排 */
th:first-child + th{min-width:156px}
.name-cell{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.name-cell strong{font-weight:600}
.name-cell a{font-weight:500}
/* ------------------------------------------------- 9. 工具行/筛选/分页 */
.toolbar{
  display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap;
  padding:10px 0;border-bottom:1px solid var(--line-soft);margin-bottom:0;
}
.toolbar > form{display:inline-flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-12);color:var(--ink-2)}
.toolbar select{width:auto;height:28px;font-size:var(--fs-12);padding:0 24px 0 8px}
/* 工具行按钮降噪：静止无底无框，hover 才浮出 */
.toolbar .btn-secondary,.toolbar .btn-outline,.toolbar .btn-ghost{
  background:transparent;border-color:transparent;color:var(--ink-2);
}
.toolbar .btn-secondary:hover,.toolbar .btn-outline:hover{
  background:var(--bg-active);border-color:var(--line);color:var(--ink-1);
}
.toolbar label{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-12);color:var(--ink-3)}
.filterbar,.audit-filters{
  display:flex;align-items:flex-end;gap:var(--sp-3);flex-wrap:wrap;
  padding:12px var(--sp-4);background:var(--bg-surface);border:1px solid var(--line);
  border-radius:var(--r-md);margin-bottom:var(--sp-4);
}
.filterbar form{display:flex;align-items:flex-end;gap:var(--sp-3);flex-wrap:wrap;width:100%}
.filterbar label{display:flex;flex-direction:column;gap:5px;font-size:var(--fs-12);font-weight:500;color:var(--ink-2)}
.filterbar input,.filterbar select{height:30px;min-width:130px;width:auto}
.filterbar input[type=text]{min-width:200px}
.filter-row{display:flex;gap:4px;align-items:center}
.filter-input{min-width:80px}
.filter-btns{display:inline-flex;gap:var(--sp-2);margin-left:auto}
.filter-help{position:relative;display:inline-block}
.filter-help-btn,.nf-help-btn{
  width:24px;height:24px;border-radius:var(--r-full);border:1px solid var(--line-strong);
  background:var(--bg-surface);color:var(--ink-3);font-size:var(--fs-12);font-weight:600;line-height:1;
  cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0;
}
.filter-help-btn:hover,.nf-help-btn:hover{background:var(--bg-hover);color:var(--ink-1);border-color:var(--line-strong)}
.filter-help-popup{
  position:absolute;top:calc(100% + 6px);right:0;z-index:60;width:340px;padding:var(--sp-3);
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);
  box-shadow:var(--sh-3);font-size:var(--fs-12);line-height:var(--lh-12);color:var(--ink-2);
}
.filter-help-popup h4{font-size:var(--fs-12);margin-bottom:6px;color:var(--ink-1)}
.filter-help-popup table{font-size:var(--fs-12)}
.pagination{
  display:flex;align-items:center;gap:4px;flex-wrap:wrap;justify-content:center;
  padding:var(--sp-4) 0;font-size:var(--fs-12);color:var(--ink-3);
}
.pagination .page-btn,.pagination .active,.pagination .disabled,.pagination .nav-arrow{
  display:inline-grid;place-items:center;min-width:28px;height:28px;padding:0 8px;border-radius:var(--r-sm);
  border:1px solid var(--line);background:var(--bg-surface);color:var(--ink-2);text-decoration:none;font-size:var(--fs-12);
  transition:all var(--t-fast) var(--ease);
}
.pagination .page-btn:hover{background:var(--bg-hover);border-color:var(--line-strong);color:var(--ink-1)}
.pagination .active{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.pagination .disabled{color:var(--ink-4);background:var(--bg-subtle);border-color:var(--line-soft);cursor:default}
.pagination .nav-arrow{font-size:14px;line-height:1}
.pagination .jump-box{display:inline-flex;align-items:center;gap:5px;margin-left:var(--sp-2);color:var(--ink-3)}
.pagination .jump-box input{width:52px;height:28px;text-align:center;font-size:var(--fs-12)}

/* ----------------------------------------------------------------- 10. 页签 */
.tabs{
  display:flex;align-items:center;gap:2px;position:relative;
  border-bottom:1px solid var(--line);margin-bottom:var(--sp-4);
}
.tab{
  appearance:none;border:0;background:transparent;font:inherit;font-size:var(--fs-13);font-weight:500;
  color:var(--ink-3);padding:9px 12px;cursor:pointer;position:relative;border-radius:var(--r-sm) var(--r-sm) 0 0;
  display:inline-flex;align-items:center;gap:6px;transition:color var(--t-fast) var(--ease);
}
.tab:hover{color:var(--ink-1);background:var(--bg-hover)}
.tab::after{
  content:"";position:absolute;left:8px;right:8px;bottom:-1px;height:2px;border-radius:2px 2px 0 0;
  background:var(--accent);transform:scaleX(0);transform-origin:center;transition:transform var(--t-med) var(--ease);
}
.tab.active{color:var(--ink-1);font-weight:600}
.tab.active::after{transform:scaleX(1)}
.tab .badge{margin-left:0}
.tabpanel{display:none}
.tabpanel.active{display:block;animation:panelIn var(--t-med) var(--ease)}
@keyframes panelIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
/* 分段控件 */
.segment{
  display:inline-flex;align-items:center;padding:2px;gap:2px;background:var(--bg-sunken);
  border:1px solid var(--line);border-radius:var(--r-sm);
}
.segment button{
  appearance:none;border:0;background:transparent;font:inherit;font-size:var(--fs-12);font-weight:500;
  color:var(--ink-2);padding:4px 10px;border-radius:var(--r-xs);cursor:pointer;line-height:18px;
  transition:all var(--t-fast) var(--ease);
}
.segment button:hover{color:var(--ink-1)}
.segment button.active{background:var(--bg-surface);color:var(--ink-1);font-weight:600;box-shadow:var(--sh-1)}
.result-selector{margin-left:auto}

/* --------------------------------------------- 11. 抽屉 / 对话框 / 提示条 */
.side-panel{
  display:none;position:fixed;top:0;right:0;bottom:0;width:400px;max-width:92vw;z-index:80;
  background:var(--bg-surface);box-shadow:var(--sh-3);flex-direction:column;
  border-left:1px solid var(--line);animation:panelIn var(--t-med) var(--ease);
}
.side-panel.on,.side-panel.open{display:flex}   /* 生产 JS 加 .on；.open 为确认稿别名 */
.side-panel .panel-head{
  display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-4);border-bottom:1px solid var(--line-soft);
  flex:0 0 auto;
}
.side-panel .panel-head h3{font-size:var(--fs-14);font-weight:600;flex:1}
.side-panel > :not(.panel-head){padding:var(--sp-4);overflow-y:auto}
.side-panel > div[id^=fieldList],.side-panel .panel-body{overflow-y:auto}
.modal{
  display:none;position:fixed;inset:0;z-index:90;padding:var(--sp-4);
  background:rgba(17,21,29,.45);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);
}
.modal.on,.modal.open{display:flex}   /* 同上 */
/* 对话框两种形态都要支持：
   ① 生产形态：.modal 内是 head/body/foot 三个并列兄弟（无包装），需纵向堆叠成一张卡；
   ② 确认稿形态：.modal 内是单个 .modal-box 包装。 */
.modal{flex-direction:column;align-items:center;justify-content:center}
.modal > .modal-head,.modal > .modal-body,.modal > .modal-foot{
  width:100%;max-width:520px;background:var(--bg-surface);margin:0;
  animation:modalIn var(--t-med) var(--ease);
}
.modal > .modal-head{border-radius:var(--r-lg) var(--r-lg) 0 0;border-bottom:1px solid var(--line-soft)}
.modal > .modal-body{overflow:auto;max-height:62vh}
.modal > .modal-foot{border-radius:0 0 var(--r-lg) var(--r-lg)}
.modal > .modal-head:last-child{border-radius:var(--r-lg)}
.modal > .modal-body:last-child{border-radius:0 0 var(--r-lg) var(--r-lg)}
.modal .modal-box{
  background:var(--bg-surface);border-radius:var(--r-lg);box-shadow:var(--sh-3);
  width:100%;max-width:520px;max-height:88vh;overflow:auto;animation:modalIn var(--t-med) var(--ease);
}
@keyframes modalIn{from{opacity:0;transform:translateY(8px) scale(.985)}to{opacity:1;transform:none}}
.modal-head{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-4);border-bottom:1px solid var(--line-soft)}
.modal-head h3{font-size:var(--fs-16);font-weight:600}
.modal-body{padding:var(--sp-4)}
.modal-foot,.modal .modal-foot{
  display:flex;align-items:center;justify-content:flex-end;gap:var(--sp-2);
  padding:var(--sp-3) var(--sp-4);border-top:1px solid var(--line-soft);background:var(--bg-subtle);
}
/* 提示条 */
.flash{
  display:flex;align-items:flex-start;gap:var(--sp-2);padding:10px var(--sp-3);border-radius:var(--r-sm);
  font-size:var(--fs-13);line-height:var(--lh-13);margin-bottom:var(--sp-3);
  background:var(--bg-subtle);border:1px solid var(--line);color:var(--ink-1);
  border-left:3px solid var(--ink-4);
}
.flash::before{content:"";flex:0 0 auto;width:14px;height:14px;margin-top:3px;border-radius:var(--r-full);background:currentColor;opacity:.18}
.flash-info{background:var(--info-soft);border-color:var(--info-line);border-left-color:var(--info);color:var(--info-ink)}
.flash-success,.flash-ok{background:var(--ok-soft);border-color:var(--ok-line);border-left-color:var(--ok);color:var(--ok-ink)}
.flash-warn{background:var(--warn-soft);border-color:var(--warn-line);border-left-color:var(--warn);color:var(--warn-ink)}
.flash-error,.flash-danger{background:var(--danger-soft);border-color:var(--danger-line);border-left-color:var(--danger);color:var(--danger-ink)}
.flash-warn a,.flash-info a{color:inherit;text-decoration:underline;text-underline-offset:2px}
.memo-bar{
  display:flex;align-items:center;gap:var(--sp-3);padding:9px var(--sp-3);margin-bottom:var(--sp-3);
  background:var(--bg-surface);border:1px solid var(--line);border-left:3px solid var(--accent-line);
  border-radius:var(--r-sm);font-size:var(--fs-13);color:var(--ink-2);
}
.memo-bar .txt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink-3);font-size:var(--fs-12)}
.memo-bar strong{font-size:var(--fs-12);color:var(--ink-2);font-weight:600}

/* --------------------------------------------------- 12. 徽标 / 状态点 */
.badge{
  display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:var(--r-full);
  font-size:var(--fs-11);font-weight:600;line-height:1;background:var(--bg-subtle);color:var(--ink-2);
  border:1px solid var(--line);white-space:nowrap;vertical-align:middle;
}
.badge-ok{background:var(--ok-soft);color:var(--ok-ink);border-color:var(--ok-line)}
.badge-warn{background:var(--warn-soft);color:var(--warn-ink);border-color:var(--warn-line)}
.badge-danger{background:var(--danger-soft);color:var(--danger-ink);border-color:var(--danger-line)}
.badge-info{background:var(--info-soft);color:var(--info-ink);border-color:var(--info-line)}
.badge-neutral,.badge-pool{background:var(--bg-subtle);color:var(--ink-2);border-color:var(--line)}
.badge-accent{background:var(--accent-soft);color:var(--accent-ink);border-color:var(--accent-line)}
.cache-badge{
  display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 9px;border-radius:var(--r-full);
  font-size:var(--fs-11);font-weight:500;background:var(--bg-subtle);color:var(--ink-2);border:1px solid var(--line);
}
.cache-badge::before{content:"";width:6px;height:6px;border-radius:var(--r-full);background:var(--ink-4)}
.cache-badge.fresh,.cache-badge.hit{background:var(--ok-soft);color:var(--ok-ink);border-color:var(--ok-line)}
.cache-badge.fresh::before,.cache-badge.hit::before{background:var(--ok)}
.cache-badge.stale,.cache-badge.warn{background:var(--warn-soft);color:var(--warn-ink);border-color:var(--warn-line)}
.cache-badge.stale::before,.cache-badge.warn::before{background:var(--warn)}
.cache-badge.miss,.cache-badge.off{background:var(--bg-subtle);color:var(--ink-3)}
.cache-badge.miss::before,.cache-badge.off::before{background:var(--ink-4)}
.dot{width:6px;height:6px;border-radius:var(--r-full);background:var(--ok);display:inline-block;flex:0 0 6px}
.dot.off,.dot.danger{background:var(--danger)}
.dot.warn{background:var(--warn)}
.pool-chip{
  display:inline-flex;align-items:center;gap:5px;max-width:140px;height:22px;padding:0 8px;
  background:var(--bg-subtle);border:1px solid var(--line);border-radius:var(--r-full);
  font-size:var(--fs-11);color:var(--ink-2);font-weight:500;
}
.pool-chip .txt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.path-chip{
  display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:var(--r-xs);
  background:var(--bg-subtle);border:1px solid var(--line);color:var(--ink-2);
  font-family:var(--font-mono);font-size:var(--fs-11);
}
/* 审计类型徽标 */
.audit-type{
  display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:var(--r-xs);
  font-size:var(--fs-11);font-weight:600;white-space:nowrap;background:var(--bg-subtle);color:var(--ink-2);border:1px solid var(--line);
}
.audit-type-login{background:var(--accent-soft);color:var(--accent-ink);border-color:var(--accent-line)}
.audit-type-write{background:var(--warn-soft);color:var(--warn-ink);border-color:var(--warn-line)}
.audit-type-error{background:var(--danger-soft);color:var(--danger-ink);border-color:var(--danger-line)}
.audit-type-page_view,.audit-type-api_access{background:var(--info-soft);color:var(--info-ink);border-color:var(--info-line)}

/* ------------------------------- 13. 树 / API 行 / 报表卡片 / 列表卡 */
.tree{display:flex;flex-direction:column;gap:1px;font-size:var(--fs-13)}
.tree .cat{
  display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:var(--r-sm);cursor:pointer;
  color:var(--ink-2);transition:background var(--t-fast) var(--ease),color var(--t-fast) var(--ease);
}
.tree .cat:hover{background:var(--bg-hover);color:var(--ink-1)}
.tree .cat.active{background:var(--accent-soft);color:var(--accent-ink);font-weight:600}
.tree .cat .ico{width:15px;height:15px;flex:0 0 15px;color:var(--ink-4)}
.tree .cat.active .ico{color:var(--accent)}
.tree .cat .cnt{margin-left:auto;font-size:var(--fs-11);font-weight:600;color:var(--ink-3);font-variant-numeric:tabular-nums}
.tree .cat .ops{display:none;align-items:center;gap:2px;margin-left:4px}
.tree .cat:hover .ops{display:inline-flex}
.tree .cat.active .cnt{color:var(--accent-ink)}
.tree .cat.active .ops{display:inline-flex}
.tree .kids{display:none;margin-left:14px;padding-left:10px;border-left:1px solid var(--line-soft)}   /* 折叠态=默认；toggleCatNode 切 .on 展开 */
.tree .kids.on{display:block}
aside.card .section-title{border-bottom:1px solid var(--line-soft)}
.tree-toggle{
  display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-13);font-weight:600;
  color:var(--ink-1);background:transparent;border:0;cursor:pointer;padding:4px 0;
}
.tree-toggle:hover{color:var(--accent-ink)}

/* API 行卡片 */
.api-row{
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);
  margin-bottom:var(--sp-2);overflow:hidden;transition:border-color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease);
}
.api-row:hover{border-color:var(--accent-line);box-shadow:var(--sh-1)}
.api-main{
  display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-3) var(--sp-4);cursor:pointer;flex-wrap:wrap;
}
.api-main .name{font-size:var(--fs-14);font-weight:600;color:var(--ink-1)}
.api-main .name:hover{color:var(--accent-ink)}
.api-main .muted{font-size:var(--fs-12);color:var(--ink-3)}
.api-main .actions,.api-main .ops{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2)}
.api-more{display:none;padding:var(--sp-3) var(--sp-4) var(--sp-4);border-top:1px solid var(--line-soft);background:var(--bg-subtle)}
.api-row.open .api-more,.api-more.on{display:block}   /* 生产 JS 加 .on；.open 为确认稿别名 */
.api-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:var(--sp-2) var(--sp-4);margin-bottom:var(--sp-3)}
.api-meta > *{font-size:var(--fs-12);color:var(--ink-2)}
.api-desc{font-size:var(--fs-13);color:var(--ink-2);line-height:1.7;margin-bottom:var(--sp-3)}
.api-url-code,.api-url-code code{
  display:block;font-family:var(--font-mono);font-size:var(--fs-12);color:var(--ink-2);
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-xs);
  padding:6px 8px;margin-bottom:6px;overflow-x:auto;white-space:nowrap;
}
.api-more-btn{margin-left:auto}
.api-help{font-size:var(--fs-12);color:var(--ink-3)}

/* 报表卡片 / 双视图 */
.rpt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--sp-3)}
.rpt-card,.report-card{
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);padding:var(--sp-4);
  display:flex;flex-direction:column;gap:6px;transition:border-color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease),transform var(--t-fast) var(--ease);
}
.rpt-card:hover,.report-card:hover{border-color:var(--accent-line);box-shadow:var(--sh-2);transform:translateY(-1px)}
.rpt-card .name,.report-card .name{font-size:var(--fs-14);font-weight:600}
.rpt-card .muted,.report-card .muted{font-size:var(--fs-12);color:var(--ink-3);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--sp-3)}
.view-card{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--sp-3)}
.view-card > .section,.view-card > div{background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);padding:var(--sp-4)}
.view-list{}
/* 排除规则行 */
.rule-row,.rule-group{display:flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-13);padding:6px 0}
.nf-group-head{font-size:var(--fs-12);font-weight:600;color:var(--ink-2);padding:6px 0}
.schedule-row{display:flex;align-items:center;gap:var(--sp-2);padding:6px 0;font-size:var(--fs-13)}
.excl-fields{display:flex;flex-wrap:wrap;gap:var(--sp-2)}
.sched-reports-wrap{max-height:340px;overflow:auto;border:1px solid var(--line);border-radius:var(--r-sm)}
.rc-meta{display:flex;align-items:center;gap:var(--sp-3);font-size:var(--fs-12);color:var(--ink-3);flex-wrap:wrap}
.bind-col{font-weight:600;color:var(--ink-2);font-size:var(--fs-12)}
.bind-cell{font-size:var(--fs-12);color:var(--ink-2)}
.config-filter-box{
  display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-4);
}
.config-filter-input{
  height:34px;font-size:var(--fs-13);background:var(--bg-surface);border:1px solid var(--line-strong);
  border-radius:var(--r-sm);max-width:420px;
}

/* ------------------------------------------- 14. 代码面 / SQL 高亮 / Markdown */
/* 单一实现：底色 + 文字色必须成对出现。历史事故：<pre class="sql-debug code-block">
   同时命中「深底」与「深字」两条规则 → 正文 1.02:1 完全看不见。 */
pre,.code-block,.code-view,.sql-debug,.sql-preview,.sql-editor code{
  background:var(--code-bg);color:var(--code-ink);
  border:1px solid var(--code-border);border-radius:var(--r-sm);
  padding:12px 14px;margin:0;
  font-family:var(--font-mono);font-size:12.5px;line-height:1.75;
  overflow:auto;tab-size:2;white-space:pre-wrap;word-break:break-word;
}
pre b,pre strong{color:var(--code-kw);font-weight:600}
.sql-debug,.sql-preview{padding:12px 0}
.sql-debug pre,.sql-preview pre{
  background:transparent;border:0;border-radius:0;padding:0 14px;color:var(--code-ink);
}
/* 代码面工具条（语言标签 / 复制） */
.code-head{
  display:flex;align-items:center;gap:var(--sp-2);padding:7px 12px;
  background:var(--code-bg-2);border-bottom:1px solid var(--code-border);
  border-radius:var(--r-sm) var(--r-sm) 0 0;
  font-size:var(--fs-11);font-weight:600;letter-spacing:.04em;
  color:var(--code-dim);text-transform:uppercase;
}
.code-head .actions{margin-left:auto;display:flex;gap:6px;text-transform:none;letter-spacing:0}
.code-head .btn-ghost{color:var(--code-dim);height:22px;font-size:var(--fs-11)}
.code-head .btn-ghost:hover{background:rgba(255,255,255,.08);color:#fff}
.code-head + pre,.code-head + .code-view{border:0;border-radius:0 0 var(--r-sm) var(--r-sm)}
/* SQL 词法着色（同底色实测对比度 ≥6.4:1） */
.sql-hl-keyword{color:var(--code-kw);font-weight:600}
.sql-hl-string{color:var(--code-str)}
.sql-hl-number{color:var(--code-num)}
.sql-hl-comment{color:var(--code-comment);font-style:italic}
.sql-hl-function{color:var(--code-fn);font-weight:500}
/* 行内代码：浅色，与代码面明确区分 */
:not(pre) > code,.md-body code,td code,p code,li code{
  background:#eef0f4;border:1px solid var(--line-soft);border-radius:var(--r-xs);
  padding:1px 5px;color:var(--ink-1);font-size:12.5px;
}
/* SQL 编辑器（可编辑，保持浅色表单语境） */
/* .sql-editor 是「容器/编辑框」共用的外观类：只给边框与底色，**永不得设 overflow**。
   生产把该类直接挂在 <textarea class="sql-textarea sql-editor"> 上（config.py 报表编辑页
   ② SQL），写 overflow:hidden 会把编辑框自己的滚动条一起裁掉——2026-10-09 用户实测反馈
   「② SQL 缺少文本滚动条」（无头 Chrome：overflowY=hidden、scrollbarGutter=0、
   60 行 SQL 被裁在 clientHeight 318 / scrollHeight 1284）。滚动契约由 .sql-textarea 声明。 */
.sql-editor{border:1px solid var(--line-strong);border-radius:var(--r-sm);background:var(--bg-surface)}
.sql-toolbar{
  display:flex;align-items:center;gap:var(--sp-2);padding:7px 10px;
  border-bottom:1px solid var(--line-soft);background:var(--bg-subtle);
}
.sql-textarea{
  width:100%;border:0;border-radius:0;font-family:var(--font-mono);font-size:12.5px;line-height:1.75;
  padding:var(--sp-3) 14px;min-height:220px;background:var(--bg-surface);color:var(--ink-1);resize:vertical;
  overflow:auto;   /* 编辑框自身的滚动契约：长 SQL/备注必须出现滚动条，不靠 UA 默认 */
}
.sql-textarea:focus{box-shadow:none;border:0;outline:2px solid var(--accent);outline-offset:-2px}
/* Markdown 正文 */
.md-body{font-size:var(--fs-14);line-height:1.75;color:var(--ink-1);max-width:78ch}
.md-body h1{font-size:var(--fs-18);margin:0 0 var(--sp-3);padding-bottom:6px;border-bottom:1px solid var(--line-soft)}
.md-body h2{font-size:var(--fs-16);margin:var(--sp-4) 0 var(--sp-2)}
.md-body h3{font-size:var(--fs-14);margin:var(--sp-3) 0 var(--sp-2)}
.md-body p{margin:0 0 var(--sp-3)}
.md-body ul,.md-body ol{margin:0 0 var(--sp-3) var(--sp-4)}
.md-body li{margin-bottom:4px}
.md-body pre code{background:transparent;border:0;padding:0;color:inherit}
.md-body blockquote{border-left:3px solid var(--accent-line);padding-left:var(--sp-3);color:var(--ink-2);margin:0 0 var(--sp-3)}
.md-body table{margin-bottom:var(--sp-3)}
.md-body img{max-width:100%;border-radius:var(--r-sm)}
/* 快筛单元格：紧实的「操作符 + 值」成组控件（选择非“不筛选”时值输入框出现） */
.qf-row .filter-row{display:flex;gap:4px;align-items:center;min-width:0}
.qf-row .filter-op{
  width:auto;min-width:74px;max-width:96px;flex:0 0 auto;height:26px;
  font-size:var(--fs-12);padding:0 22px 0 8px;
}
.qf-row .filter-input{flex:1 1 auto;min-width:64px;max-width:150px;height:26px;font-size:var(--fs-12)}
.qf-row .filter-input:focus{max-width:220px}   /* 聚焦时临时放宽，失焦收回，避免把列撑开 */
.qf-row input[disabled]{background:var(--bg-subtle)}

/* --------------------------------------------------- 16. 页面级细节 */
/* 概览 */
.grid-stat + .card,.grid-stat + .grid-2{margin-top:var(--sp-4)}
/* 报表详情工具行 */
.tabpanel[data-panel=data] .toolbar{border-bottom:0}
.tabpanel[data-panel=data] > .toolbar + .filterbar{margin-top:var(--sp-3)}
/* 表格里的表单（快筛） */
.qf-row form{display:contents}
/* 排序列头 */
th > .sort-links + .filter-row{margin-top:4px}
/* 审计筛选快捷 */
.audit-filters input[type=date]{min-width:150px}

/* ------------------------------------------------------------ 17. 工具类 */
.text-right{text-align:right}
.nowrap{white-space:nowrap}
.tnum{font-variant-numeric:tabular-nums}
.mt-0{margin-top:0}
.mb-0{margin-bottom:0}

/* ------------------------------------------------- 18. 收尾 / 动效降级 */
@media (max-width:1280px){
  .grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:1024px){
  .split{grid-template-columns:minmax(0,1fr)}
  .grid-2{grid-template-columns:minmax(0,1fr)}
  .grid-3{grid-template-columns:minmax(0,1fr)}
  aside.card{position:static}
  .container{padding-left:var(--sp-4);padding-right:var(--sp-4)}
}
@media (max-width:640px){
  .container{padding:12px}
  .grid-stat{grid-template-columns:minmax(0,1fr)}
  .page-head{align-items:flex-start}
  .page-head .actions{width:100%}
  .filterbar input[type=text]{min-width:100%}
  .filterbar label{width:100%}
  .filterbar input,.filterbar select{width:100%}
  .formbar{flex-wrap:wrap}
  .formbar .right{width:100%;justify-content:flex-end}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}
}

/* ------------------------------------- 20. 页面级组件补全（原散在内联样式里） */
/* 通用工具 */
.hidden{display:none!important}
/* 报表中心：搜索框 */
.search-box{position:relative;display:flex;align-items:center;flex:0 1 320px;min-width:180px}
.search-box svg{position:absolute;left:10px;width:15px;height:15px;color:var(--ink-4);pointer-events:none}
.search-box input,.search-box .input{padding-left:32px;height:32px}
/* 报表卡片（报表中心） */
.report-card{position:relative}
.report-card .t{font-size:var(--fs-14);font-weight:600;color:var(--ink-1);line-height:var(--lh-13)}
.report-card .meta{font-size:var(--fs-12);color:var(--ink-3)}
.report-card .desc{font-size:var(--fs-12);color:var(--ink-3);line-height:1.6;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.report-card .tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:auto;padding-top:var(--sp-2)}
/* 报表配置卡片视图 */
.rpt-card{position:relative;gap:8px}
.rpt-card .rc-pick{position:absolute;top:12px;right:12px}
.rpt-card .rc-top{display:flex;align-items:center;gap:var(--sp-2);padding-right:24px}
.rpt-card .rc-name{font-size:var(--fs-14);font-weight:600;line-height:var(--lh-13)}
.rpt-card .rc-name a{color:var(--ink-1)}
.rpt-card .rc-name a:hover{color:var(--accent-ink)}
.rpt-card .rc-sql{margin:2px 0;color:var(--ink-3)}
.rpt-card .rc-memo{font-size:var(--fs-12);color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rpt-card .rc-foot{display:flex;align-items:center;gap:var(--sp-2);margin-top:auto;padding-top:var(--sp-2);border-top:1px solid var(--line-soft)}
.rpt-card .rc-ops{display:inline-flex;align-items:center;gap:4px;margin-left:auto}
.rpt-card .rc-ops form{display:inline}
.rpt-card .rc-api{font-size:var(--fs-12);color:var(--ink-3)}
.rpt-card .rc-api:hover{color:var(--accent-ink)}
/* 批量操作浮条 */
.batch-bar{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap;font-size:var(--fs-13);color:var(--ink-2)}
.batch-float{
  position:sticky;bottom:14px;z-index:35;margin:var(--sp-3) 0 0;padding:10px 14px;
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);
  box-shadow:var(--sh-2);
}
.batch-float select,.batch-float input{width:auto;height:28px;font-size:var(--fs-12);min-width:150px}
/* 日期快捷 */
.date-shortcuts{display:inline-flex;align-items:center;gap:6px}
/* 页头内联报表切换器 */
.select.compact-switch{
  width:auto;height:28px;font-size:var(--fs-13);font-weight:500;color:var(--ink-2);
  border-color:var(--line);background-color:var(--bg-surface);min-width:130px;
}
/* 导出对话框字段集 / 备注预览 */
fieldset.fs{border:1px solid var(--line);border-radius:var(--r-sm);padding:var(--sp-3) var(--sp-4);margin:0 0 var(--sp-3)}
fieldset.fs legend{font-size:var(--fs-12);font-weight:600;color:var(--ink-2);padding:0 6px}
.memo-preview{margin-top:var(--sp-2);padding:var(--sp-3);background:var(--bg-subtle);border:1px solid var(--line-soft);border-radius:var(--r-sm);min-height:56px}
/* 嵌套筛选构建器 */
.nf-builder{font-size:var(--fs-13);color:var(--ink-2);display:flex;flex-direction:column;gap:var(--sp-2)}
.nf-builder > div:first-child{font-size:var(--fs-12);color:var(--ink-3)}
/* 可折叠调试块 */
.debug-info{border-top:1px solid var(--line-soft);padding-top:var(--sp-2);margin-top:var(--sp-2)}
.debug-toggle{
  appearance:none;border:0;background:transparent;font:inherit;font-size:var(--fs-13);font-weight:600;
  color:var(--ink-2);cursor:pointer;padding:6px 0;display:inline-flex;align-items:center;gap:6px;
}
.debug-toggle:hover{color:var(--accent-ink)}
.debug-content{padding:var(--sp-2) 0 var(--sp-3)}
/* 抽屉遮罩 */
.backdrop{position:fixed;inset:0;z-index:70;background:rgba(17,21,29,.42);display:none}
.backdrop.on,.backdrop.show{display:block}   /* 生产 JS 加 .on */
/* 调度表单绑定表 */
.sched-reports{width:100%;font-size:var(--fs-12)}
.sched-reports th{font-size:var(--fs-11)}
/* 审计类型补充 */
.audit-type-web_access{background:var(--info-soft);color:var(--info-ink);border-color:var(--info-line)}
.audit-type-operation{background:var(--accent-soft);color:var(--accent-ink);border-color:var(--accent-line)}
.audit-type-login_fail,.audit-type-security{background:var(--danger-soft);color:var(--danger-ink);border-color:var(--danger-line)}
/* 生产遗留笔误 class */
.btn-smbtn-sm{height:26px;padding:0 9px;font-size:var(--fs-12)}
/* 概览快捷入口：3 列网格、44px 行高，末行单个时整行铺满（消除末行缺口） */
.card > .grid-3 > .btn{height:44px;font-size:var(--fs-13);justify-content:center}
.card > .grid-3 > .btn:last-child:nth-child(3n+1){grid-column:1 / -1}
/* 统计磁贴：6 磁贴排成 2×3（避免末行 ragged） */
.grid-stat{grid-template-columns:repeat(3,minmax(0,1fr))}
/* 可排序表头：默认次级色，hover/当前列才用主文字色 */
.sort-link{color:var(--ink-2)}
.sort-link:hover{color:var(--ink-1)}
/* 分页器内所有按钮统一 28px */
.pagination .btn{height:28px;padding:0 10px;font-size:var(--fs-12)}

/* --------------------------------------------- 19. 色调变体（同一套结构） */
/* 石墨蓝：更中性、更“工具” */
html[data-tint=steel]{
  --accent:#3f6ad8; --accent-hover:#355cc0; --accent-press:#2b4c9e;
  --accent-ink:#2b4c9e; --accent-soft:#f2f6ff; --accent-soft-2:#e2eaff; --accent-line:#c9d8f8;
}
html[data-tint=steel] .sidebar .brand .logo{background:linear-gradient(150deg,#6ea0f0,#3f6ad8 55%,#2b4c9e)}
/* 松绿：更冷静、偏“运维” */
html[data-tint=pine]{
  --accent:#0f8a6a; --accent-hover:#0c7358; --accent-press:#0a5c46;
  --accent-ink:#075c45; --accent-soft:#f0fbf6; --accent-soft-2:#dcf5ea; --accent-line:#b6e6d5;
}
html[data-tint=pine] .sidebar .brand .logo{background:linear-gradient(150deg,#3fbf9a,#0f8a6a 55%,#0a5c46)}

/* 树节点名 / API 单元格 / 调度表单微调 */
.tree .cat .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.api-cell a{font-size:var(--fs-12);color:var(--ink-2);display:inline-flex;align-items:center;gap:4px}
.api-cell a:hover{color:var(--accent-ink)}
.sched-form{display:flex;flex-direction:column;gap:var(--sp-4)}

/* ============ 21. 报表配置页重设计：分组卡 + 多级层级 + 行卡片 ============ */
/* 分组卡（一级分类） */
.cat-block{background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-md);margin-bottom:var(--sp-3);overflow:hidden}
.cat-block > .cat-head{
  display:flex;align-items:center;gap:var(--sp-2);padding:10px 14px;
  background:var(--bg-subtle);border-bottom:1px solid var(--line-soft);
}
.cat-block > .cat-head .cat-name{display:inline-flex;align-items:center;gap:7px;font-size:var(--fs-13);font-weight:600;color:var(--ink-1)}
.cat-block > .cat-head .cat-name svg{color:var(--ink-4)}
.cat-block > .cat-head .actions{margin-left:auto;display:flex;align-items:center;gap:2px;opacity:0;transition:opacity var(--t-fast) var(--ease)}
.cat-block:hover > .cat-head .actions,.cat-block:focus-within > .cat-head .actions{opacity:1}
.cat-block .cat-head .tree-toggle{font-size:var(--fs-13);font-weight:600;padding:2px 0}
.cat-block .cat-head .tree-toggle .chev{transition:transform var(--t-fast) var(--ease);display:inline-flex}
.cat-block.collapsed .cat-head .tree-toggle .chev{transform:rotate(-90deg)}
.cat-block.collapsed > .cat-body,.cat-block.collapsed > .cat-children{display:none}

/* 层级导轨：父子关系靠「竖线 + 节点横线 + 逐级缩进 + 字号下沉」表达，不靠表格缩进 */
.cat-children{position:relative;margin-left:22px;padding:10px 0 10px 20px;border-left:1px solid var(--line)}
.cat-children > .cat-block{position:relative;margin-bottom:var(--sp-2);box-shadow:none}
.cat-children > .cat-block::before{
  content:"";position:absolute;left:-20px;top:17px;width:11px;height:1px;background:var(--line);
}
.cat-children > .cat-block > .cat-head{background:var(--bg-surface);border-bottom:1px solid var(--line-soft)}
.cat-children > .cat-block > .cat-head .cat-name{color:var(--ink-2);font-weight:600}
.cat-children > .cat-block > .cat-head .cat-name svg{color:var(--ink-4)}
.cat-block .cat-children .cat-children{margin-left:18px;padding-left:18px;border-left-color:var(--line)}
.cat-block .cat-children .cat-children > .cat-block > .cat-head .cat-name{font-size:var(--fs-12);color:var(--ink-2)}
/* 层级深度色带：三级及以上用主色系小圆点做锚点，避免无限缩进 */
.cat-depth-dot{width:6px;height:6px;border-radius:var(--r-full);flex:0 0 6px;background:var(--line-strong)}
.cat-depth-1 > .cat-head .cat-depth-dot{background:var(--accent)}
.cat-depth-2 > .cat-head .cat-depth-dot{background:var(--accent-line)}
.cat-depth-3 > .cat-head .cat-depth-dot{background:var(--line-strong)}

/* 报表行卡片（替代 10 列挤压表格） */
.rpt-body{display:flex;flex-direction:column}
.rpt-row{
  display:flex;align-items:center;gap:12px;padding:11px 14px;
  border-bottom:1px solid var(--line-soft);transition:background var(--t-fast) var(--ease);
}
.rpt-row:last-child{border-bottom:0}
.rpt-row:hover{background:var(--bg-hover)}
.rpt-row.picked{background:var(--accent-soft)}
.rpt-row .pick{display:flex;align-items:center;flex:0 0 auto}
.rpt-main{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:4px}
.rpt-line1{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap}
.rpt-line1 .nm{font-size:var(--fs-14);font-weight:600;color:var(--ink-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.rpt-line1 .nm:hover{color:var(--accent-ink)}
.rpt-meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px;font-size:var(--fs-12);color:var(--ink-3);min-width:0}
.rpt-memo{font-size:var(--fs-12);color:var(--ink-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.rpt-sql{
  font-family:var(--font-mono);font-size:var(--fs-12);color:var(--ink-3);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;
}
.rpt-ops{
  flex:0 0 auto;display:flex;align-items:center;gap:2px;
  opacity:0;transition:opacity var(--t-fast) var(--ease);
}
.rpt-row:hover .rpt-ops,.rpt-row:focus-within .rpt-ops,.rpt-row.picked .rpt-ops{opacity:1}
/* 配置 chips：把「默认分页 / 缓存 / TTL」三列并成一列，消除挤压 */
.cfg-chips{display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0}
.cfg-chip{
  display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;
  border-radius:var(--r-xs);background:var(--bg-subtle);border:1px solid var(--line);
  font-size:var(--fs-11);color:var(--ink-2);white-space:nowrap;
}
.cfg-chip b{font-weight:600;color:var(--ink-1);font-variant-numeric:tabular-nums}
.cfg-chip.ok{background:var(--ok-soft);border-color:var(--ok-line);color:var(--ok-ink)}
.cfg-chip.ok b{color:var(--ok-ink)}
.cfg-chip.warn{background:var(--warn-soft);border-color:var(--warn-line);color:var(--warn-ink)}
.cfg-chip.warn b{color:var(--warn-ink)}
.cfg-chip.accent{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent-ink)}
.cfg-chip.accent b{color:var(--accent-ink)}
.cfg-chip .dot{width:5px;height:5px;flex:0 0 5px}
/* 分类路径（方案 B：单表 + 路径列） */
.cat-path{display:inline-flex;align-items:center;gap:4px;font-size:var(--fs-12);color:var(--ink-3);white-space:nowrap}
.cat-path .sep{color:var(--ink-4)}
.cat-path .leaf{color:var(--ink-2);font-weight:500}
.cat-path .rt{color:var(--accent-ink);font-weight:500}
/* 方案切换条 */
.scheme-bar{
  display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;
  padding:10px 14px;margin-bottom:var(--sp-4);
  background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:var(--r-md);
  font-size:var(--fs-12);color:var(--accent-ink);
}
.scheme-bar strong{font-weight:600}
.scheme-bar .segment{background:var(--bg-surface);border-color:var(--accent-line)}
.scheme-bar .segment button.active{background:var(--accent);color:#fff}
/* 空分组提示 */
.cat-empty{padding:14px;font-size:var(--fs-12);color:var(--ink-3);border-top:1px dashed var(--line);display:flex;align-items:center;gap:8px;justify-content:space-between}
.cat-empty .add{color:var(--accent-ink);font-weight:500}
@media (max-width:1400px){.split{grid-template-columns:220px minmax(0,1fr)}}

.nowrap-chips{flex-wrap:nowrap;overflow:hidden}

/* —— 报表配置页 v2：卡片视图（与列表视图同数据各渲一份，.view-list/.view-card 语义与生产一致） —— */
.cat-cards{padding:12px 14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:12px}
.cat-cards .rpt-card{padding:12px 14px;border-radius:var(--r-sm);gap:6px;min-width:0}
.cat-cards .rpt-card .rc-top{padding-right:22px}
.cat-cards .rpt-card .rc-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cat-cards .rpt-card .rc-sql{
  font-family:var(--font-mono);font-size:12px;color:var(--ink-3);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.cat-cards .rpt-card .rc-memo{
  font-size:var(--fs-12);color:var(--ink-3);min-height:36px;   /* 固定两行高度，卡片底边对齐 */
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}
.cat-cards .rpt-card .rc-meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.cat-cards .rpt-card .rc-foot{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px;border-top:1px solid var(--line-soft)}
.cat-cards .rpt-card .rc-ops{margin-left:auto;display:inline-flex;gap:2px;opacity:0;transition:opacity var(--t-fast) var(--ease)}
.cat-cards .rpt-card:hover .rc-ops,.cat-cards .rpt-card.picked .rc-ops{opacity:1}
.rpt-card.picked{border-color:var(--accent-line);background:var(--accent-soft)}

/* —— JS 运行时切换的动态类（必须存在，否则交互无视觉反馈） —— */
@keyframes rowHighlightFade{from{background:var(--accent-soft-2)}to{background:transparent}}
.row-highlight{animation:rowHighlightFade 2s ease forwards}
.flash.fading-out{opacity:0;transition:opacity .5s ease}
.btn-group{display:inline-flex;gap:8px;flex-wrap:wrap}
.btn-link{background:none;border:none;color:var(--accent-ink);height:auto;padding:0;font-weight:500}
.btn-link:hover{text-decoration:underline;text-underline-offset:2px}
.btn[disabled],.btn.disabled{opacity:.5;pointer-events:none}
.btn.loading{position:relative;color:transparent}
.btn.loading::after{
  content:"";position:absolute;width:14px;height:14px;border:2px solid rgba(255,255,255,.4);
  border-top-color:#fff;border-radius:var(--r-full);animation:querySpin .7s linear infinite;
}
.pagination .page-span,
.pagination a:not(.page-btn):not(.nav-arrow){
  display:inline-grid;place-items:center;min-width:28px;height:28px;padding:0 8px;border-radius:var(--r-sm);
  border:1px solid var(--line);background:var(--bg-surface);color:var(--ink-2);font-size:var(--fs-12);
}
.pagination a:not(.page-btn):not(.nav-arrow):hover{background:var(--bg-hover);border-color:var(--line-strong);color:var(--ink-1)}

/* ============ 22. 生产组件补全（原由页面级 CSS / 小分片提供，迁入单一来源） ============ */
/* —— 迷你按钮变体（原 _MINIBTN_CSS） —— */
.btn-mini-outline,.btn-mini-outline-light,.btn-mini-outline-key{
  background:var(--bg-surface);border:1px solid var(--line-strong);color:var(--ink-2);
}
.btn-mini-outline:hover,.btn-mini-outline-light:hover,.btn-mini-outline-key:hover{
  background:var(--bg-hover);border-color:#a9aeb8;color:var(--ink-1);
}
.btn-mini-outline-accent{background:var(--accent-soft);border:1px solid var(--accent-line);color:var(--accent-ink)}
.btn-mini-outline-accent:hover{background:var(--accent-soft-2);color:var(--accent-press)}
.btn-mini-success{background:var(--ok);border-color:var(--ok);color:#fff}
.btn-mini-success:hover{background:#037048;border-color:#037048;color:#fff}
.btn-mini-s{height:22px;padding:0 6px;font-size:var(--fs-11)}
.btn-mini-m{height:26px;padding:0 9px;font-size:var(--fs-12)}

/* —— 报表页工具条 .controls（原 report._CSS） —— */
.controls{
  display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;
  padding:12px var(--sp-4);background:var(--bg-subtle);border:1px solid var(--line);
  border-radius:var(--r-md);margin-bottom:var(--sp-4);
}
.controls label{display:inline-flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-13);font-weight:500;color:var(--ink-2)}
.controls select{width:auto;height:30px;font-size:var(--fs-13)}
.controls .stat{margin-left:auto;font-size:var(--fs-12);color:var(--ink-3)}

/* —— 排序条 / 排序项 —— */
.sort-bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:8px 0;font-size:var(--fs-12);color:var(--ink-2)}
.sort-tag{
  display:inline-flex;align-items:center;gap:3px;padding:2px 8px;
  background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:var(--r-xs);
  color:var(--accent-ink);font-size:var(--fs-12);
}
.sort-prio{
  display:inline-grid;place-items:center;min-width:15px;height:15px;padding:0 3px;
  background:var(--accent);color:#fff;border-radius:var(--r-full);font-size:10px;font-weight:600;
}
.sort-item{
  display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line);
  border-radius:var(--r-sm);background:var(--bg-surface);cursor:grab;user-select:none;
}
.sort-item:hover{border-color:var(--accent-line);background:var(--accent-soft)}
.sort-up,.sort-down,.sort-remove{
  width:22px;height:22px;flex:0 0 22px;display:inline-grid;place-items:center;padding:0;
  border:1px solid var(--line);border-radius:var(--r-xs);background:var(--bg-surface);
  color:var(--ink-3);font-size:10px;line-height:1;cursor:pointer;
}
.sort-up:hover,.sort-down:hover{background:var(--bg-hover);color:var(--ink-1);border-color:var(--line-strong)}
.sort-remove{color:var(--ink-3);font-size:11px}
.sort-remove:hover{background:var(--danger-soft);border-color:var(--danger-line);color:var(--danger-ink)}
.sort-up:disabled,.sort-down:disabled{opacity:.4;cursor:not-allowed}
.clear-filter{display:inline-block;margin-left:8px;font-size:var(--fs-12);color:var(--ink-3)}
.clear-filter:hover{color:var(--danger-ink)}

/* —— 嵌套筛选构建器（nf-*） —— */
.nf-leaf,.nf-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:6px 0}
.nf-col,.nf-op{width:auto;min-width:104px;height:28px;font-size:var(--fs-12)}
.nf-op{min-width:88px}
.nf-val{flex:1 1 160px;max-width:240px;height:28px;font-size:var(--fs-12)}
.nf-val:disabled{background:var(--bg-subtle)}
.nf-example{font-size:var(--fs-11);color:var(--ink-4)}
.nf-rm{
  width:22px;height:22px;display:inline-grid;place-items:center;padding:0;border:1px solid var(--line);
  border-radius:var(--r-xs);background:var(--bg-surface);color:var(--ink-3);cursor:pointer;font-size:11px;
}
.nf-rm:hover{background:var(--danger-soft);border-color:var(--danger-line);color:var(--danger-ink)}
.nf-andor{width:auto;min-width:96px;height:28px;font-size:var(--fs-12);font-weight:600}
.nf-children{margin-left:14px;padding-left:12px;border-left:1px solid var(--line);display:flex;flex-direction:column;gap:2px}
.nf-empty{padding:var(--sp-4);text-align:center;font-size:var(--fs-12);color:var(--ink-3)}

/* —— 调度排除规则编辑器（excl-*） —— */
.excl-node{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:6px 0}
.excl-children{margin-left:14px;padding-left:12px;border-left:1px solid var(--line);display:flex;flex-direction:column;gap:2px}
.excl-type,.excl-op,.excl-dow{width:auto;height:28px;font-size:var(--fs-12)}
.excl-type{min-width:132px}
.excl-dow{min-width:88px}
.excl-from,.excl-to{width:auto;height:28px;font-size:var(--fs-12);padding:0 8px}
.excl-on{font-size:var(--fs-12);color:var(--ink-3)}

/* —— 报表切换卡 / 报表列表（report._CSS .report-select/.report-list） —— */
.report-select label{display:block;margin-bottom:6px;font-size:var(--fs-13);font-weight:500;color:var(--ink-2)}
.report-select select{width:100%;height:34px;font-size:var(--fs-13)}
.report-list{list-style:none;padding:0;margin-top:4px}
.report-list li{padding:7px 0;border-bottom:1px solid var(--line-soft)}
.report-list li:last-child{border-bottom:0}
.report-list a{display:flex;align-items:center;gap:8px;font-size:var(--fs-13);font-weight:500}
.report-list a::before{content:"→";color:var(--ink-4);font-weight:400}

/* —— 配置表单（原 config._CONFIG_EXTRA_CSS 的双栏网格） —— */
form.config-form{max-width:1200px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
  grid-auto-flow:dense;column-gap:32px;row-gap:16px;align-items:start}
form.config-form.sched-form{max-width:1560px}
form.config-form .span-full{grid-column:1 / -1}
.config-form label{display:block;margin-top:0;font-weight:600;font-size:var(--fs-13);color:var(--ink-2)}
.config-form .field-hint{display:block;margin-top:4px;font-weight:400;color:var(--ink-3);font-size:var(--fs-12)}
.config-form .check-inline{display:inline-flex;align-items:center;gap:6px;font-weight:400;margin:4px 18px 4px 0;cursor:pointer}
.config-form textarea{font-family:var(--font-mono);font-size:var(--fs-12);min-height:100px;resize:vertical}
.config-form .form-actions{margin-top:var(--sp-4);display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap}
.config-form .form-actions .cancel{color:var(--ink-3);font-size:var(--fs-13);font-weight:500}
.config-form .form-actions .cancel:hover{color:var(--ink-1)}
.config-form .form-actions .test-result{font-size:var(--fs-13);font-weight:500;align-self:center}
.config-form .form-actions .test-result.ok{color:var(--ok-ink)}
.config-form .form-actions .test-result.err{color:var(--danger-ink)}
.sched-reports-wrap{max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg-surface)}
table.sched-reports{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--fs-12)}
table.sched-reports thead th{position:sticky;top:0;background:var(--bg-subtle);text-align:left;padding:8px 12px;
  border-bottom:1px solid var(--line);color:var(--ink-2);font-weight:600;height:auto}
table.sched-reports tbody td{padding:7px 12px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
table.sched-reports tbody tr:last-child td{border-bottom:0}
table.sched-reports .bind-col{width:56px;text-align:center}
/* SQL 预览 / 备注预览显隐（原 .show 契约） */
.sql-preview.show,.memo-preview.show{display:block}
.sql-preview:not(.show),.memo-preview:not(.show){display:none}

/* —— 加载遮罩 / 空态（原 _COMMON_CSS query-loading-overlay） —— */
.query-loading-overlay{
  display:none;                       /* 默认隐藏；JS 加 .show 才显示 */
  position:fixed;inset:0;z-index:200;flex-direction:column;align-items:center;justify-content:center;
  gap:var(--sp-3);background:rgba(17,21,29,.34);-webkit-backdrop-filter:blur(1.5px);backdrop-filter:blur(1.5px);
  color:var(--ink-1);font-size:var(--fs-13);font-weight:500;
}
.query-loading-overlay.show{display:flex}
.query-loading-overlay .spinner{
  width:34px;height:34px;border:3px solid rgba(255,255,255,.55);border-top-color:var(--accent);
  border-radius:var(--r-full);animation:querySpin .8s linear infinite;
}
@keyframes querySpin{to{transform:rotate(360deg)}}
.empty-state{color:var(--ink-3);font-size:var(--fs-13);padding:var(--sp-6) var(--sp-3);text-align:center}
.empty-state .icon{font-size:26px;line-height:1;opacity:.45;margin-bottom:8px}
.empty-state-row td{background:var(--bg-surface)}

/* —— 最近查看（报表中心） —— */
.recent-reports{margin-bottom:var(--sp-4)}
.recent-title{font-size:var(--fs-12);font-weight:600;color:var(--ink-3);margin-bottom:8px}
.recent-cards{display:flex;gap:8px;flex-wrap:wrap}
.recent-card{
  display:inline-flex;align-items:center;max-width:240px;height:28px;padding:0 12px;
  background:var(--bg-surface);border:1px solid var(--line);border-radius:var(--r-full);
  color:var(--accent-ink);font-size:var(--fs-13);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.recent-card:hover{border-color:var(--accent-line);background:var(--accent-soft);color:var(--accent-press)}

/* —— 杂项钩子 —— */
.sql-head{white-space:nowrap}
.report-checkbox{vertical-align:middle;margin:0}
.mermaid{
  background:var(--bg-subtle);border:1px solid var(--line);border-radius:var(--r-sm);
  padding:12px;font-family:var(--font-mono);font-size:var(--fs-12);overflow:auto;color:var(--ink-2);
}
.result-mode-section{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.on{color:var(--ok-ink)}
.gone{color:var(--ink-3);text-decoration:line-through}
.act{color:var(--accent-ink);font-weight:500}

/* 规则 JSON 只读框（原内联深色样式 → 类） */
.code-textarea{
  width:100%;min-height:80px;margin:0;padding:12px;resize:vertical;
  background:var(--code-bg);color:var(--code-ink);border:1px solid var(--code-border);
  border-radius:var(--r-sm);font-family:var(--font-mono);font-size:12.5px;line-height:1.6;
}
.code-textarea:focus{outline:2px solid var(--accent);outline-offset:-2px}

/* 触屏：聚焦时把快筛输入框放大到固定宽度（JS 加 .filter-input-touch） */
.filter-input-touch{
  width:min(320px,80vw) !important;min-width:min(320px,80vw);
  box-shadow:0 8px 24px -6px rgba(17,21,29,.28);
  border-color:var(--accent) !important;background:var(--bg-surface);
}
"""

# 迷你按钮公共样式（config 页与 report 页共享；类拆分与内联现状视觉等价）
_MINIBTN_CSS = ""  # 迷你按钮变体已并入 _COMMON_CSS 第 22 节（保留变量名兼容既有引用）

# 黄色警示条公共样式（色值统一为较新的 #fefce8 系；!important 覆盖
# report 页 .controls .cache-badge 等既有类，保证与内联时代视觉一致）
_FLASH_WARN_CSS = ""  # flash-warn 已并入 _COMMON_CSS（保留变量名兼容既有引用）

# 黄色警示框内联样式（flash-warn 块级组件：表单警示、结果集名称警示共用，防样式漂移）
_WARN_BOX_STYLE = "margin:8px 0;padding:8px 12px;border-radius:6px;border:1px solid #fde68a;font-size:13px"

# Markdown 渲染内容排版（报表页 memo 折叠区 / 编辑预览面板 #memo-preview 共用）。
# 全局 reset（_BASE_CSS 的 `*, *::before, *::after { margin:0; padding:0 }`）清掉了
# 浏览器默认的 ul/ol 缩进，必须显式补回，否则嵌套列表左侧挤在一起。
# 消费页必须把本样式追加在各自 extra_css 的【末尾】（报表页 _CSS、配置页
# _CONFIG_EXTRA_CSS 之后），保证与既有 .debug-info / .memo-preview 规则特异性
# 相同时后注入胜出；代码高亮色系见 markdown_render.codehilite_css()（monokai 深色）。
_MD_CSS = """
.md-body { font-size: 14px; line-height: 1.7; color: #1e293b; overflow-wrap: break-word; }
.md-body > :first-child { margin-top: 0; }
.md-body > :last-child { margin-bottom: 0; }
.md-body p { margin: 8px 0; }
.md-body h1, .md-body h2, .md-body h3, .md-body h4 {
  color: #0f172a; font-weight: 700; line-height: 1.35; margin: 20px 0 10px;
}
.md-body h1 { font-size: 21px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }
.md-body h2 { font-size: 18px; padding-bottom: 6px; border-bottom: 1px solid #eef2f7; }
.md-body h3 { font-size: 16px; }
.md-body h4 { font-size: 14px; color: #334155; }
.md-body ul, .md-body ol { margin: 6px 0; padding-left: 1.6em; }
.md-body ul ul, .md-body ol ol, .md-body ul ol, .md-body ol ul { margin: 2px 0; }
.md-body li { margin: 3px 0; }
.md-body li::marker { color: #94a3b8; }
.md-body blockquote {
  margin: 10px 0; padding: 8px 14px; background: #f8fafc;
  border-left: 3px solid #818cf8; border-radius: 0 6px 6px 0; color: #475569;
}
.md-body blockquote p { margin: 4px 0; }
.md-body code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  background: #eef2f7; padding: 2px 6px; border-radius: 4px;
  font-size: 0.9em; color: #be185d;
}
.md-body pre {
  background: #0f172a; color: #e2e8f0; padding: 12px 14px; border-radius: 8px;
  overflow-x: auto; font-size: 13px; line-height: 1.6; margin: 10px 0;
}
.md-body pre code { background: none; padding: 0; color: inherit; font-size: 13px; }
.md-body .highlight {
  background: #0f172a; color: #e2e8f0; border-radius: 8px;
  overflow-x: auto; margin: 10px 0;
}
.md-body .highlight pre { background: none; padding: 12px 14px; margin: 0; }
.md-body .highlight code { background: none; padding: 0; color: inherit; }
.md-body pre.mermaid {
  background: #fff; border: 1px solid #e2e8f0; color: #334155;
  text-align: center; padding: 12px;
}
.md-body a { color: #4f46e5; text-decoration: none; border-bottom: 1px solid rgba(79,70,229,0.3); transition: border-color 0.15s; }
.md-body a:hover { border-bottom-color: #4f46e5; }
.md-body hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }
.md-body img { max-width: 100%; height: auto; border-radius: 8px; }
.md-body table { margin: 10px 0; font-size: 13px; border-collapse: collapse; width: auto; max-width: 100%; }
.md-body th, .md-body td { border: 1px solid #e2e8f0; padding: 6px 12px; }
.md-body th { background: #f8fafc; }
.md-body tbody tr:hover { background: #f8fafc; }
.md-body del { color: #64748b; }
"""

_B6_CSS = ""  # 检索过滤框/最近查看卡片已并入 _COMMON_CSS 第 22 节（保留变量名兼容既有引用）

_COMMON_CSS = _BASE_CSS + _COMMON_CSS + _MINIBTN_CSS + _FLASH_WARN_CSS + _B6_CSS

# ---------------------------------------------------------------------------
# 公共 JavaScript（交互式 UI 组件）
# ---------------------------------------------------------------------------

# 全量获取 URL 查询串（JS 字符串与 Python f-string 统一引用）
FETCH_ALL_QUERY = "?fetch_all=true"

_COMMON_JS = r"""
function toggleSection(btn, label) {
  var content = btn.nextElementSibling;
  var hidden = content.classList.toggle("hidden");
  btn.textContent = hidden ? "\u25b6 " + label : "\u25bc " + label;
}
function toggleCatTree(btn) {
  var content = document.getElementById("cat-tree-content");
  if (!content) return;
  var collapsed = content.classList.toggle("hidden");
  btn.textContent = (collapsed ? "\u25b6 " : "\u25bc ") + "报表分类";
  try { localStorage.setItem("cat_tree_collapsed", collapsed ? "1" : "0"); } catch (e) {}
}
function toggleCatNode(ev, row) {
  if (ev && ev.target && ev.target.closest && ev.target.closest(".ops, form, a, button")) return;
  var id = row.getAttribute("data-kids");
  if (!id) return;
  var kids = document.getElementById(id);
  if (kids) kids.classList.toggle("on");
}
function apiToggleMore(btn) {
  var row = btn && btn.closest && btn.closest(".api-row");
  if (!row) return;
  var more = row.querySelector(".api-more");
  if (!more) return;
  var on = more.classList.toggle("on");
  btn.textContent = on ? "收起 ▴" : "展开 ▾";
}
function apiMainClick(ev, main) {
  if (!ev || !ev.target || !ev.target.closest) return;
  if (ev.target.closest("a, button, form, input, label")) return;
  var btn = main.querySelector(".api-more-btn");
  if (btn) apiToggleMore(btn);
}
function initCatTree() {
  var content = document.getElementById("cat-tree-content");
  var btn = document.getElementById("cat-tree-toggle");
  if (!content || !btn) return;
  var collapsed = "0";
  try { collapsed = localStorage.getItem("cat_tree_collapsed") || "0"; } catch (e) {}
  var isCollapsed = collapsed === "1";
  if (isCollapsed) content.classList.add("hidden");
  btn.textContent = (isCollapsed ? "\u25b6 " : "\u25bc ") + "报表分类";
}
function selectAllInSection(el) {
  /* v2：分组容器由 .section 改为 .section.cat-block（兼容两种写法） */
  var section = el.closest('.cat-block, .section');
  if (!section) return;
  var c = section.querySelectorAll('.report-checkbox');
  for (var i = 0; i < c.length; i++) {
    c[i].checked = el.checked;
  }
  updateBatchCount();
}
function toggleCatBlock(btn) {
  var b = btn.closest('.cat-block');
  if (b) b.classList.toggle('collapsed');
}
function submitBatchPost(actionUrl, ids, extraFields) {
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = actionUrl;
  ids.forEach(function(id) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'report_ids'; inp.value = id;
    form.appendChild(inp);
  });
  extraFields.forEach(function(f) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = f.name; inp.value = f.value;
    form.appendChild(inp);
  });
  document.body.appendChild(form);
  form.submit();
  return false;
}
function buildApiUrl(path, kind) {
  var origin = window.location.origin;
  if (kind === 'full') {
    return origin + path + '""" + FETCH_ALL_QUERY + r"""';
  } else if (kind === 'static') {
    return origin + path + '.json';
  }
  return origin + path;
}
function toggleFilterInput(inputName, select) {
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
}
function copyRulesJson() {
  copyToClipboard('current-rules-json');
}
function copyToClipboard(elementId) {
  var el = document.getElementById(elementId);
  if (!el) return;
  var text = el.value || el.textContent || el.innerText;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      var btn = el.nextElementSibling;
      if (btn && btn.tagName === 'BUTTON') {
        var originalText = btn.textContent;
        btn.textContent = '已复制';
        btn.style.color = '#059669';
        setTimeout(function() {
          btn.textContent = originalText;
          btn.style.color = '';
        }, 2000);
      }
    }).catch(function() {
      fallbackCopyText(text, el);
    });
  } else {
    fallbackCopyText(text, el);
  }
}
function fallbackCopyText(text, el) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    var btn = el.nextElementSibling;
    if (btn && btn.tagName === 'BUTTON') {
      var originalText = btn.textContent;
      btn.textContent = '已复制';
      btn.style.color = '#059669';
      setTimeout(function() {
        btn.textContent = originalText;
        btn.style.color = '';
      }, 2000);
    }
  } catch (err) {
    console.error('复制失败:', err);
  }
  document.body.removeChild(ta);
}
function initApiUrls() {
  var els = document.querySelectorAll('.api-url-code');
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var path = el.getAttribute('data-path') || '';
    var kind = el.getAttribute('data-kind') || 'base';
    el.textContent = buildApiUrl(path, kind);
  }
}
/* 页面级初始化只允许一条注册路径：initPage()（见下）。
   历史写法 initApiUrls/initCatTree 各自再绑一次 DOMContentLoaded → 首次加载二者
   都会执行两遍（幂等所以没炸），而无刷新换页后这第二条路径不会重放，容易误以为
   「已注册 = 换页后也会跑」。已删除（复盘门禁：TestPageInitRegistration）。 */
function showFlashWarn(msg) {
  /* 行内警告提示条（spec ux-optimization 批次6#27e）：替代阻塞式弹窗。
     复用 .flash-warn 样式，5 秒后自动隐藏；容器缺失时降级 console.warn。 */
  var box = document.getElementById('js-flash-warn');
  if (!box) {
    box = document.createElement('div');
    box.id = 'js-flash-warn';
    box.className = 'flash-warn';
    box.setAttribute('role', 'alert');
    var container = document.querySelector('.container');
    if (!container) { console.warn(msg); return; }
    container.insertBefore(box, container.firstChild);
  }
  box.textContent = msg;
  box.style.display = '';
  clearTimeout(showFlashWarn._timer);
  showFlashWarn._timer = setTimeout(function() { box.style.display = 'none'; }, 5000);
}
function initConfigFilter() {
  /* 合并页检索过滤框（spec ux-optimization 批次6#21）：纯前端 tr 文本
     contains 匹配显隐；空查询恢复全部。表头行（含 th）不过滤，避免表头
     被误藏破坏表格结构；分类树区块非 tr 不参与。
     确认稿 r3：卡片视图（.rpt-card）同规则参与过滤，两视图一致。 */
  var input = document.getElementById('config-filter-input');
  if (!input) return;
  input.addEventListener('input', function() {
    var q = input.value.trim().toLowerCase();
    var rows = document.querySelectorAll('.section tr');
    for (var i = 0; i < rows.length; i++) {
      var tr = rows[i];
      if (tr.querySelector('th')) continue;
      if (!q) { tr.style.display = ''; continue; }
      var text = (tr.innerText || tr.textContent || '').toLowerCase();
      tr.style.display = text.indexOf(q) >= 0 ? '' : 'none';
    }
    var cards = document.querySelectorAll('.section .rpt-card');
    for (var j = 0; j < cards.length; j++) {
      var card = cards[j];
      if (!q) { card.style.display = ''; continue; }
      var ctext = (card.innerText || card.textContent || '').toLowerCase();
      card.style.display = ctext.indexOf(q) >= 0 ? '' : 'none';
    }
  });
}
function saveRecentVisit(reportId, reportName) {
  /* 最近查看记录（spec ux-optimization 批次6#22）：localStorage 去重保序，
     最多保留 8 条；存储异常静默（隐私模式等场景不阻断页面）。 */
  try {
    var list = JSON.parse(localStorage.getItem('sqlreport_recent') || '[]');
    if (!Array.isArray(list)) list = [];
    list = list.filter(function(it) { return it && it.id !== reportId; });
    list.unshift({id: reportId, name: String(reportName || ''), ts: Date.now()});
    localStorage.setItem('sqlreport_recent', JSON.stringify(list.slice(0, 8)));
  } catch (e) {}
}
function initRecentReports() {
  /* 总览页「最近查看」快捷卡片（批次6#22）：无记录不插入任何内容。 */
  var mount = document.getElementById('recent-reports-mount');
  if (!mount) return;
  var list;
  try { list = JSON.parse(localStorage.getItem('sqlreport_recent') || '[]'); } catch (e) { list = []; }
  if (!Array.isArray(list)) return;
  var cards = '';
  list.forEach(function(it) {
    if (!it || !it.id) return;
    var name = String(it.name || ('#' + it.id))
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    cards += '<a class="recent-card" href="/report?id=' + encodeURIComponent(it.id)
           + '" title="' + name + '">' + name + '</a>';
  });
  if (!cards) return;
  mount.innerHTML = '<div class="recent-reports"><div class="recent-title">'
                  + '\ud83d\udd52 \u6700\u8fd1\u67e5\u770b</div><div class="recent-cards">'
                  + cards + '</div></div>';
}
function applyStoredCols(reportId) {
  /* 列设置 localStorage 记忆（spec ux-optimization 批次6#25）：
     URL 显式 cols 参数优先——存在即写入记忆并直接返回（分享语义不被覆盖）；
     URL 无 cols 且有记忆时以记忆值前端隐藏 th/td（服务端仍渲染全列）。 */
  var params = new URLSearchParams(window.location.search);
  var colsParam = params.get('cols');
  var key = 'sqlreport_cols_' + reportId;
  if (colsParam) {
    try { localStorage.setItem(key, colsParam); } catch (e) {}
    return;
  }
  var stored = null;
  try { stored = localStorage.getItem(key); } catch (e) {}
  if (!stored) return;
  var visible = {};
  stored.split(',').forEach(function(c) { visible[c] = true; });
  /* 找茬 M1：过期记忆自愈——记忆列名与页面现有 data-col 无任何交集时
     （SQL 列结构已变更），清除记忆并放弃应用，避免全列被隐死局。 */
  var wraps = document.querySelectorAll('.table-wrap');
  if (!wraps.length) return;
  var anyOverlap = false;
  Array.prototype.forEach.call(wraps, function(wrap) {
    Array.prototype.forEach.call(
      wrap.querySelectorAll('thead tr [data-col]'), function(th) {
        if (th.getAttribute('data-col') in visible) anyOverlap = true;
      });
  });
  if (!anyOverlap) {
    try { localStorage.removeItem(key); } catch (e) {}
    return;
  }
  /* 找茬 L5：多结果集（result_mode=all）下逐表应用，不再只作用首表。 */
  Array.prototype.forEach.call(wraps, function(wrap) {
    applyStoredColsToTable(wrap, visible);
  });
}
function applyStoredColsToTable(wrap, visible) {
  var headRows = wrap.querySelectorAll('thead tr');
  if (!headRows.length) return;
  var hideIdx = [];
  Array.prototype.forEach.call(headRows[0].children, function(th, i) {
    var col = th.getAttribute('data-col');
    if (col !== null && !(col in visible)) { th.style.display = 'none'; hideIdx.push(i); }
  });
  if (!hideIdx.length) return;
  /* ui-redesign R2-D：表头改为「排序行 + qf-row 快筛行」两行，隐藏列需同步 */
  Array.prototype.forEach.call(headRows, function(row, ri) {
    if (ri === 0) return;
    hideIdx.forEach(function(i) {
      var cell = row.children[i];
      if (cell) cell.style.display = 'none';
    });
  });
  var bodyRows = wrap.querySelectorAll('tbody tr');
  Array.prototype.forEach.call(bodyRows, function(tr) {
    if (tr.children.length === 1 && tr.children[0].colSpan) return;
    hideIdx.forEach(function(i) {
      var td = tr.children[i];
      if (td) td.style.display = 'none';
    });
  });
}
function initSqlEditorTabIndent() {
  /* SQL 编辑器 Tab 缩进（spec ux-optimization 批次6#23）：仅对带
     data-tab-indent 标记的 sql-editor 生效；Tab 拦截后经 setRangeText
     插入两空格（execCommand 已废弃，不使用）。 */
  var tas = document.querySelectorAll('textarea.sql-editor[data-tab-indent="1"]');
  Array.prototype.forEach.call(tas, function(ta) {
    ta.addEventListener('keydown', function(e) {
      if (e.key !== 'Tab') return;
      e.preventDefault();
      ta.setRangeText('  ', ta.selectionStart, ta.selectionEnd, 'end');
    });
  });
}
function sbIsRail() {
  /* 当前视觉状态：状态类 + 视口联合判定（防小屏状态错位） */
  var el = document.documentElement;
  if (el.classList.contains('sb-rail')) return true;
  if (el.classList.contains('sb-wide')) return false;
  return !!(window.matchMedia && window.matchMedia('(max-width:1024px)').matches);
}
function sbStoreWrite(v) {
  /* 收缩状态记忆（浏览器本地）；写失败不阻断切换，向 UI 明示 */
  try { localStorage.setItem('sqlreport_sidebar_collapsed', v); return null; }
  catch (e) {
    var name = (e && e.name) || String(e);
    console.warn('侧栏收缩状态无法写入 localStorage：', name);
    showFlashWarn('侧栏收缩状态写入失败（' + name + '）：本页切换仍有效，刷新后不保留。');
    return null;
  }
}
function initSidebarHandle() {
  /* 全高手柄：侧栏最右边整条竖边任意高度可点；箭头随指针高度移动。
     data-sb-bound 保证 initPage 重复调用时幂等（无刷新换页复用）。 */
  var handle = document.querySelector('.sb-handle');
  if (!handle || handle.getAttribute('data-sb-bound')) return;
  handle.setAttribute('data-sb-bound', '1');
  var arrow = handle.querySelector('.sb-arrow');
  handle.addEventListener('click', function (ev) {
    ev.preventDefault();
    var el = document.documentElement;
    if (sbIsRail()) {
      el.classList.remove('sb-rail');
      el.classList.add('sb-wide');
      sbStoreWrite('0');
    } else {
      el.classList.remove('sb-wide');
      el.classList.add('sb-rail');
      sbStoreWrite('1');
    }
    handle.title = sbIsRail() ? '展开侧栏' : '收起侧栏';
  });
  handle.addEventListener('mousemove', function (ev) {
    if (!arrow) return;
    var rect = handle.getBoundingClientRect();
    var y = Math.max(12, Math.min(rect.height - 12, ev.clientY - rect.top));
    /* 确认稿 r3 区一：rail 态箭头不进入账号区——纵向范围钳制在账号区之上，
       避免箭头与头像/退出图标挤团（账号区在侧栏底部） */
    if (sbIsRail()) {
      var account = document.querySelector('.sidebar .account');
      if (account) {
        var accTop = account.getBoundingClientRect().top - rect.top;
        y = Math.min(y, Math.max(12, accTop - 14));
      }
    }
    arrow.style.top = y + 'px';
  });
  handle.addEventListener('mouseleave', function () {
    if (arrow) arrow.style.top = '50%';
  });
  handle.title = sbIsRail() ? '展开侧栏' : '收起侧栏';
  /* 读失败（引导脚本记下）向 UI 明示一次，不静默降级 */
  if (window.__sbStorageErr) {
    showFlashWarn('侧栏收缩状态记忆不可用（' + window.__sbStorageErr
      + '）：切换仅本页有效，刷新后回默认态。');
    window.__sbStorageErr = null;
  }
}
function initPage() {
  /* 页面初始化（DOMContentLoaded 与无刷新换页后共用；需幂等） */
  initApiUrls();
  initSidebarHandle();
  initCatTree();
  initFlashMessages();
  initAnchorRowHighlight();
  initQueryLoadingOverlay();
  initConfigFilter();
  initRecentReports();
  initSqlEditorTabIndent();
}
document.addEventListener('DOMContentLoaded', initPage);
function applyRulesJson() {
  var ta = document.getElementById('current-rules-json');
  if (!ta) return;
  var text = ta.value.trim();
  if (!text) { showFlashWarn('请输入规则 JSON'); return; }
  var rules;
  try { rules = JSON.parse(text); } catch (e) {
    showFlashWarn('JSON 格式错误: ' + e.message); return;
  }
  var params = new URLSearchParams(window.location.search);
  var keysToRemove = [];
    params.forEach(function(_, k) {
      if (k.startsWith('f_') || k.startsWith('op_') || k.startsWith('s_')
          || k === 'sort' || k === 'dir' || k === 'cols' || k === 'page'
          || k === 'nested_filter') {
        keysToRemove.push(k);
      }
    });
  keysToRemove.forEach(function(k) { params.delete(k); });
  if (rules.filters && rules.filters.length) {
    rules.filters.forEach(function(f) {
      params.set('f_' + f.col, f.val || '');
      if (f.op && f.op !== 'contains') params.set('op_' + f.col, f.op);
    });
  }
  if (rules.sorts && rules.sorts.length) {
    rules.sorts.forEach(function(s) {
      params.append('sort', s.col);
      params.append('dir', s.dir || 'asc');
    });
  }
  if (rules.columns) params.set('cols', rules.columns);
  if (rules.nested_filter && typeof rules.nested_filter === 'object'
      && Object.keys(rules.nested_filter).length) {
    params.set('nested_filter', encodeURIComponent(JSON.stringify(rules.nested_filter)));
  }
   params.set('page', '1');
   navigateTo('?' + params.toString());
 }
 /* ---- 批次5#14：flash 自动消失 + × 关闭 + 剥 flash 参数 ---- */
function initFlashMessages() {
  var params = new URLSearchParams(window.location.search);
  if (params.has('flash')) {
    params.delete('flash');
    var qs = params.toString();
    window.history.replaceState(null, '',
      window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
  }
  var flashes = document.querySelectorAll('.flash');
  for (var i = 0; i < flashes.length; i++) {
    (function(f) {
      var closeBtn = f.querySelector('.flash-close');
      if (closeBtn) closeBtn.addEventListener('click', function() { f.remove(); });
      if (f.getAttribute('data-autohide') === '1') {
        setTimeout(function() {
          f.classList.add('fading-out');
          setTimeout(function() { f.remove(); }, 600);
        }, 6000);
      }
    })(flashes[i]);
  }
}
/* ---- 批次5#16：锚点目标行高亮（#report-N / #pool-N / #user-N）---- */
function initAnchorRowHighlight() {
  var id = window.location.hash.substring(1);
  if (!/^(report|pool|user)-\d+$/.test(id)) return;
  var row = document.getElementById(id);
  if (row) row.classList.add('row-highlight');
  /* 确认稿 r3：卡片视图下行锚点（#report-N）对应卡片副本一并高亮 */
  var card = document.getElementById('report-card-' + id.replace(/^report-/, ''));
  if (card) card.classList.add('row-highlight');
}
/* ---- 批次5#18：慢查询 loading 遮罩 ----
   仅在触发查询的 form submit 与「重建缓存」按钮 click 时显示；
   不用 beforeunload（会误伤导出下载），导出表单同样排除。 */
 function initQueryLoadingOverlay() {
  var overlay = document.getElementById('query-loading-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'query-loading-overlay';
    overlay.className = 'query-loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div><div>查询中…请稍候</div>';
    document.body.appendChild(overlay);
  }
  var showOverlay = function() { overlay.classList.add('show'); };
  var forms = document.querySelectorAll('form');
  for (var i = 0; i < forms.length; i++) {
    if (forms[i].hasAttribute('data-ov-bound')) continue;
    var action = forms[i].getAttribute('action') || '';
    if (action.indexOf('/export') !== -1) continue;
    /* 仅同页提交与报表查询端点（精确匹配，防止 /config/reports/* 批量操作误伤） */
    if (action === '' || action === '/report' || action.indexOf('/report?') === 0) {
      forms[i].setAttribute('data-ov-bound', '1');
      forms[i].addEventListener('submit', showOverlay);
    }
  }
  var refreshBtns = document.querySelectorAll('.btn-refresh[type="submit"]');
  for (var j = 0; j < refreshBtns.length; j++) {
    if (refreshBtns[j].hasAttribute('data-ov-bound')) continue;
    refreshBtns[j].setAttribute('data-ov-bound', '1');
    refreshBtns[j].addEventListener('click', showOverlay);
  }
}
/* ---- 批次5#20：跳页钳制 + 回车原生提交 ---- */
 function goPage(evt, baseUrl, current, totalPages) {
  evt.preventDefault();
  var input = document.getElementById('jump_page');
  var p = parseInt(input.value, 10);
  if (isNaN(p)) p = current;
  if (p < 1) p = 1;
  if (p > totalPages) p = totalPages;
  input.value = p;
  navigateTo(baseUrl + '&page=' + p);
  return false;
}
 /* ---- 无刷新导航：history.pushState + fetch 替换 <main> 内容 ---- */
 function _swapMain(html, url, replace) {
   var parser = new DOMParser();
   var doc = parser.parseFromString(html, 'text/html');
   var newMain = doc.querySelector('main.main');
   var oldMain = document.querySelector('main.main');
   if (newMain && oldMain) { oldMain.innerHTML = newMain.innerHTML; }
   var newTitle = doc.querySelector('title');
   if (newTitle) document.title = newTitle.textContent;
   if (url) {
     if (replace) { history.replaceState(null, '', url); }
     else { history.pushState(null, '', url); }
   }
   _reinitAfterSwap();
 }
 /* 无刷新换页后的统一重初始化（供所有 navigateTo/_swapMain 调用，幂等）：
    ① innerHTML 赋值的 <script> 不会执行 → 逐块重建以重新执行（<main> 内的
       导出对话框联动、嵌套筛选、结果集切换等都靠这个）；
    ② initPage() 重新绑定公共行为（表单提交遮罩、侧栏、折叠、最近查看…）；
    ③ initReportPage()（报表页专有）重新绑定字段/排序列表的拖拽。 */
 /* 「就绪即执行」：内联脚本首次解析时 readyState==='loading' → 绑 DOMContentLoaded；
   无刷新换页后被重建重放时 readyState==='complete' → 立即执行。
   历史缺陷：页面级脚本只绑 DOMContentLoaded，换页重放后永远不执行（嵌套筛选/导出联动/结果集切换失效）。 */
 if (typeof window.onReady !== 'function') {
   window.onReady = function(fn) {
     if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', fn); }
     else { fn(); }
   };
 }
 function _reinitAfterSwap() {
   var main = document.querySelector('main.main');
   if (main) {
     var scripts = main.querySelectorAll('script');
     for (var i = 0; i < scripts.length; i++) {
       var old = scripts[i];
       if (!old.src && !old.textContent.trim()) continue;
       var fresh = document.createElement('script');
       if (old.src) { fresh.src = old.src; } else { fresh.textContent = old.textContent; }
       old.parentNode.replaceChild(fresh, old);
     }
   }
   if (typeof initPage === 'function') { initPage(); }
   if (typeof initReportPage === 'function') { initReportPage(); }
 }
 window._reinitAfterSwap = _reinitAfterSwap;
 function navigateTo(url, replace) {
   fetch(url)
     .then(function(r) { return r.text(); })
     .then(function(html) { _swapMain(html, url, replace); })
     .catch(function() { window.location.href = url; });
 }
 window.addEventListener('popstate', function() {
   fetch(window.location.href)
     .then(function(r) { return r.text(); })
     .then(function(html) { _swapMain(html, null, false); })
     .catch(function() {});
 });
 /* ---- 上移/下移箭头无刷新（/config/{section}/{id}/move-up|move-down）：
        fetch POST 跟随 302 后原位换 <main>，保持滚动位置（不跳顶）。
        服务端无 JS 时仍走原生提交兜底。 ---- */
 document.addEventListener('submit', function(e) {
   var form = e.target;
   if (!form || form.tagName !== 'FORM') return;
   var action = form.getAttribute('action') || '';
   if (!/\/move-(up|down)$/.test(action)) return;
   e.preventDefault();
   fetch(action, { method: 'POST', body: new FormData(form) })
     .then(function(r) {
       return r.text().then(function(html) { _swapMain(html, r.url, false); });
     })
     .catch(function() { form.submit(); });
 });
 """

# ---------------------------------------------------------------------------
# SQL 格式化与高亮 JS（config.py 与 report.py 共享）
# ---------------------------------------------------------------------------

_SQL_HIGHLIGHT_JS = r"""
function h(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function highlight(txt) {
  var s = txt.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
  var kw = 'SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN|EXISTS|AS|ON|JOIN|INNER|OUTER|LEFT|RIGHT|CROSS|FULL|NATURAL|USING|GROUP|BY|HAVING|ORDER|ASC|DESC|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|DROP|ALTER|ADD|COLUMN|INDEX|UNIQUE|PRIMARY|KEY|FOREIGN|REFERENCES|CASCADE|DEFAULT|DISTINCT|COUNT|SUM|AVG|MIN|MAX|CASE|WHEN|THEN|ELSE|END|UNION|ALL|EXCEPT|INTERSECT|WITH|RECURSIVE|REPLACE|TRUNCATE|EXPLAIN|DESCRIBE|SHOW|USE|DATABASE|IF|EXISTS|GRANT|REVOKE';
  var re = new RegExp(
    "('(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\")|" +
    "(--[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/)|" +
    "\\b(\\d+(?:\\.\\d+)?)\\b|" +
    "\\b(" + kw + ")\\b|" +
    "\\b(\\w+)(?=\\s*\\()",
    "gi"
  );
  return s.replace(re, function(m, str, cmt, num, kw, fn) {
    if (str) return '<span class="sql-hl-string">' + str + '</span>';
    if (cmt) return '<span class="sql-hl-comment">' + cmt + '</span>';
    if (num) return '<span class="sql-hl-number">' + num + '</span>';
    if (kw) return '<span class="sql-hl-keyword">' + kw + '</span>';
    if (fn)  return '<span class="sql-hl-function">' + fn + '</span>';
    return m;
  });
}
"""

_SQL_FORMATTER_JS = r"""
function fmt(t) {
  if (!t || !t.trim()) return t;
  var s = t.replace(/\s*;\s*$/,""), toks = [], lines = [], indent = 0, clauseCount = 0;
  s = s.replace(/(--[^\n]*|\/\*[\s\S]*?\*\/|'(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.|"")*"|`(?:[^`\\]|\\.|``)*`)/g,
    function(m) { toks.push(m); return "\u0001" + (toks.length - 1) + "\u0001"; });
  var parts = s.split(/\b(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|CROSS\s+JOIN|FULL\s+JOIN|NATURAL\s+JOIN|INSERT\s+INTO|DELETE\s+FROM|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE|GROUP\s+BY|ORDER\s+BY|UNION\s+ALL|SELECT|FROM|WHERE|JOIN|ON|AND|OR|GROUP|BY|HAVING|ORDER|LIMIT|OFFSET|UNION|VALUES|SET|CASE|WHEN|THEN|ELSE|END|INTO)\b/i);
  for (var i = 0; i < (parts ? parts.length : 0); i++) {
    var p = parts[i];
    if (!p || !p.trim()) continue;
    var w = p.trim(), u = w.toUpperCase();
    function pad() {
      if (indent === 0) return "";
      if (indent === 1) return "  ";
      return Array(indent + 1).join("  ");
    }
    if (u === "SELECT") { indent = indent === 0 ? 1 : (clauseCount > 0 && indent++); lines.push(pad() + "SELECT"); indent = 2; clauseCount++; }
    else if (u === "FROM" || u === "INNER JOIN" || u === "LEFT JOIN" || u === "RIGHT JOIN" || u === "CROSS JOIN" || u === "FULL JOIN" || u === "NATURAL JOIN" || u === "JOIN") { indent = Math.max(1, indent - 1); lines.push(pad() + w); indent = 2; }
    else if (u === "ON") { lines.push(pad() + w); indent = 2; }
    else if (u === "WHERE") { indent = Math.max(1, indent - 1); lines.push(pad() + "WHERE"); indent = 2; }
    else if (u === "AND" || u === "OR") { lines.push(pad() + w); indent = 2; }
    else if (u === "GROUP BY" || u === "GROUP") { indent = Math.max(1, indent - 1); lines.push(pad() + "GROUP BY"); indent = 2; }
    else if (u === "HAVING") { indent = Math.max(1, indent - 1); lines.push(pad() + "HAVING"); indent = 2; }
    else if (u === "ORDER BY" || u === "ORDER") { indent = Math.max(1, indent - 1); lines.push(pad() + "ORDER BY"); indent = 2; }
    else if (u === "LIMIT") { indent = Math.max(1, indent - 1); lines.push(pad() + "LIMIT"); indent = 1; }
    else if (u === "OFFSET") { lines.push(pad() + "OFFSET"); indent = 1; }
    else if (u === "UNION" || u === "UNION ALL") { indent = 0; lines.push(""); lines.push(w); }
    else if (u === "VALUES") { lines.push(pad() + "VALUES"); indent = 2; }
    else if (u === "SET") { lines.push(pad() + "SET"); indent = 2; }
    else if (u === "DELETE FROM" || u === "INSERT INTO" || u === "CREATE TABLE" || u === "DROP TABLE" || u === "ALTER TABLE") { indent = 0; lines.push(w); indent = 2; }
    else if (u === "CASE") { lines.push(pad() + "CASE"); indent++; }
    else if (u === "WHEN") { lines.push(pad() + "WHEN"); indent = 2; }
    else if (u === "THEN" || u === "ELSE") { lines.push(pad() + w); }
    else if (u === "END") { indent = Math.max(1, indent - 1); lines.push(pad() + "END"); }
    else if (u === "INTO") { lines.push(pad() + "INTO"); indent = 1; }
    else { lines.push(pad() + w); }
  }
  return lines.map(function(l) {
    return l.replace(/\u0001(\d+)\u0001/g, function(m, n) { return toks[+n]; });
  }).join("\n") + ";";
}
"""

# ---------------------------------------------------------------------------
# 公共模板
# ---------------------------------------------------------------------------

# 侧栏收缩记忆引导：在 CSS 应用前读 localStorage 设状态类，避免闪烁。
# 存储被禁（预览沙箱等）不阻断渲染——降级默认态并记错误名，交 initPage
# 以既有 flash-warn 向 UI 明示（确认稿承诺：读写异常不再静默吞掉）。
_SIDEBAR_BOOTSTRAP_JS = (
    '<script>(function(){try{var v=localStorage.getItem("sqlreport_sidebar_collapsed");'
    'if(v==="1")document.documentElement.classList.add("sb-rail");'
    'else if(v==="0")document.documentElement.classList.add("sb-wide");'
    '}catch(e){window.__sbStorageErr=(e&&e.name)||"StorageError";}})();'
    # onReady 必须在页面内联脚本之前可用：外链 common.js 是 defer，晚于 body 内联脚本执行。
    # 首次解析（readyState==="loading"）→ 绑 DOMContentLoaded；
    # 无刷新换页后脚本被重建重放（readyState==="complete"）→ 立即执行。
    'window.onReady=function(fn){'
    'if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",fn);}'
    'else{fn();}};</script>'
)

_PAGE_HEADER_TEMPLATE = string.Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
$sidebar_bootstrap
$favicon_link
<title>$title</title>
$common_css_assets
<style>${extra_css}</style>
</head>
<body>
<div class="app">
$sidebar
<main class="main">
<div class="container">
""")

# ---------------------------------------------------------------------------
# 公共 CSS/JS 外链化（spec ux-optimization 批次6#28）
#
# 复用既有 /static/vendor/<name>@<version>/ 版本锁 + immutable 管线：
# 首次调用（server.py 启动序列预热，或渲染兜底惰性触发）把 _COMMON_CSS /
# _COMMON_JS 按内容 sha256 前 8 位写入 static/vendor/self@{hash8}/ 目录，
# 页头输出 <link>、页尾输出 <script defer> 外链引用；浏览器侧 immutable
# 缓存跨页复用。内容变化 → hash 变化 → 新目录自动生成，旧目录留存无害。
# 写入失败（只读盘等）→ 回退内联 <style>/<script>，功能不降级。
# ---------------------------------------------------------------------------

_SELF_VENDOR_DIR = os.path.join("static", "vendor")
_COMMON_ASSET_LOCK = threading.Lock()
# 进程级缓存：(css_url, js_url)；空串元素表示内联回退模式。None=未初始化。
_COMMON_ASSET_URLS = None


def self_assets_root() -> str:
    """返回 self 资产落点根目录（static/vendor 绝对路径）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        *_SELF_VENDOR_DIR.split(os.sep))


def content_hash8(content: str) -> str:
    """内容 hash 前 8 位（sha256 hex），作为版本锁目录名。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


def ensure_common_assets(root: str = None) -> tuple[str, str] | None:
    """把公共 CSS/JS 写入 {root}/self@{hash8}/ 并返回 (css_url, js_url)。

    幂等：同内容重复调用覆盖写同样字节；内容升级生成新目录。
    hash 覆盖 CSS+JS（ui-redesign C16：只改 JS 也会换 URL，避免 immutable 不刷新）。
    root 参数供测试注入临时目录；默认写仓库 static/vendor/。
    任一环节失败返回 None（调用方回退内联）。
    """
    try:
        base = root or self_assets_root()
        hash8 = content_hash8(_COMMON_CSS + "\n;;;\n" + _COMMON_JS)
        target_dir = os.path.join(base, f"self@{hash8}")
        os.makedirs(target_dir, exist_ok=True)
        for fname, payload in (("common.css", _COMMON_CSS),
                               ("common.js", _COMMON_JS)):
            path = os.path.join(target_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(payload)
            if not os.path.isfile(path):
                return None
        return (f"/static/vendor/self@{hash8}/common.css",
                f"/static/vendor/self@{hash8}/common.js")
    except OSError:
        return None


def _get_common_asset_urls() -> tuple[str, str]:
    """取公共资产 URL（带进程级缓存）；不可用时返回 ("", "") 表示内联。

    找茬 M2a：测试环境下写入仓库真实目录会污染工作区——测试通过
    patch self_assets_root 指向临时目录隔离（见 tests/test_render.py）。
    """
    global _COMMON_ASSET_URLS
    if _COMMON_ASSET_URLS is None:
        with _COMMON_ASSET_LOCK:
            if _COMMON_ASSET_URLS is None:
                urls = None
                try:
                    urls = ensure_common_assets()
                except Exception:
                    urls = None
                _COMMON_ASSET_URLS = urls or ("", "")
    return _COMMON_ASSET_URLS


def reset_common_assets_cache() -> None:
    """重置进程级资产缓存（测试隔离用）。"""
    global _COMMON_ASSET_URLS
    with _COMMON_ASSET_LOCK:
        _COMMON_ASSET_URLS = None

def _render_common_footer() -> str:
    """生成页尾公共脚本段：闭合 container/main/app + 外链公共 JS（失败内联回退）。"""
    _, js_url = _get_common_asset_urls()
    if js_url:
        return ('</div>\n</main>\n</div>\n'
                f'<script src="{js_url}" defer></script>\n</body>\n</html>')
    return ('</div>\n</main>\n</div>\n'
            '<script>' + _COMMON_JS + '</script>\n</body>\n</html>')

# ---------------------------------------------------------------------------
# 导航栏链接定义
# ---------------------------------------------------------------------------

# 侧栏导航（单一来源；ui-redesign T7.1，替代旧顶栏 _NAV_ITEMS）
# 条目：(active_key, href, 标签, 可选内联 SVG path)
_NAV_GROUPS = [
    ("分析", [
        ("report", "/report", "报表中心",
         '<path d="M4 19V5m0 14h16M8 15v-4m4 4V7m4 8v-6"/>'),
    ]),
    ("管理", [
        ("config", "/config", "概览",
         '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
         '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
        ("config-reports", "/config/reports", "报表配置",
         '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>'),
        ("config-pools", "/config/pools", "连接池",
         '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>'),
        ("config-users", "/config/users", "用户",
         '<circle cx="9" cy="8" r="3.5"/><path d="M3 19c.5-3 2.8-4.5 6-4.5S14.5 16 15 19"/>'),
    ]),
    ("服务", [
        ("api", "/config/api-endpoints", "API 接口",
         '<path d="M10 13a5 5 0 0 0 7.1 0l2.4-2.4a5 5 0 0 0-7.1-7.1L11 4.9M14 11a5 5 0 0 0-7.1 0L4.5 13.4a5 5 0 0 0 7.1 7.1L13 19.1"/>'),
        ("scheduler", "/config/scheduler", "定时任务",
         '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>'),
    ]),
    ("治理", [
        ("audit", "/audit", "审计日志",
         '<path d="M9 4h6l1 2h3a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h3l1-2z"/><path d="M8 11h8M8 15h5"/>'),
    ]),
]


def _nav_is_active(key: str, active: str) -> bool:
    """侧栏高亮：精确匹配 + config-reports 前缀（表单/列表同项）。"""
    if not active:
        return False
    if key == active:
        return True
    if key == "config-reports" and active.startswith("config-reports"):
        return True
    return False


# 请求级当前登录用户名：server 认证成功后注入、每请求入口复位。
# ThreadingHTTPServer 每请求一线程，threading.local 天然隔离无串号。
_request_ctx = threading.local()


def set_request_user(user) -> None:
    """设置当前请求的登录用户名（None=无会话/公开页）。"""
    _request_ctx.user = user


def get_request_user():
    """读取当前请求登录用户名；未设置时返回 None。"""
    return getattr(_request_ctx, "user", None)


def _build_sidebar_html(active: str = "", nav_badges: dict = None,
                        current_user: str = None) -> str:
    """构建侧栏 HTML（含分组导航与账户区）。active 为 None/空时不高亮。

    current_user 未显式传入时回退读取请求级上下文（server 认证后经
    set_request_user 注入；每请求一线程的 threading.local 隔离）。
    """
    active = active or ""
    nav_badges = nav_badges or {}
    if current_user is None:
        current_user = get_request_user()
    parts = ['<aside class="sidebar" aria-label="主导航">',
             '  <a class="brand" href="/report"><span class="logo">SR</span>'
             '<span class="name">SqlReport</span></a>']
    for group_title, items in _NAV_GROUPS:
        parts.append(f'  <div class="nav-group">{html_mod.escape(group_title)}</div>')
        for key, href, label, icon in items:
            cls = ' class="nav-item nav-active"' if _nav_is_active(key, active) else ' class="nav-item"'
            svg = (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   f'stroke-width="1.5">{icon}</svg>') if icon else ""
            badge = ""
            if key in nav_badges and nav_badges[key] is not None:
                badge = f'<span class="nav-badge">{html_mod.escape(str(nav_badges[key]))}</span>'
            parts.append(f'  <a{cls} href="{href}" '
                         f'title="{html_mod.escape(label)}">'
                         f'{svg}<span>{html_mod.escape(label)}</span>{badge}</a>')
        parts.append('  <div class="spacer"></div>')
    parts.append('  <div class="account">')
    if current_user:
        initial = html_mod.escape(current_user[:1].upper() or "?")
        parts.append(f'    <span class="avatar">{initial}</span>'
                     f'<span class="who">{html_mod.escape(current_user)}</span>')
    parts.append('    <a class="out" href="/logout">退出</a>')
    parts.append('    <a class="out-icon" href="/logout" title="退出'
                 + (f'（{html_mod.escape(current_user)}）' if current_user else '')
                 + '" aria-label="退出">'
                 '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
                 'stroke-linecap="round" stroke-linejoin="round">'
                 '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>'
                 '<polyline points="16,17 21,12 16,7"/>'
                 '<line x1="21" y1="12" x2="9" y2="12"/></svg></a>')
    parts.append('  </div>')
    # 全高竖边手柄：整条右边任意高度可点，箭头随指针移动（确认稿 v2）
    parts.append('  <button class="sb-handle" type="button" title="收起侧栏" '
                 'aria-label="收起或展开侧栏"><span class="sb-arrow">'
                 '<svg viewBox="0 0 12 18" fill="none" stroke="currentColor" stroke-width="1.8" '
                 'stroke-linecap="round" stroke-linejoin="round">'
                 '<polyline points="4,3 9,9 4,15"/></svg></span></button>')
    parts.append('</aside>')
    return "\n".join(parts)


def render_sidebar(active: str = "", nav_badges: dict = None,
                   current_user: str = None) -> str:
    """渲染侧栏导航（公开入口）。"""
    return _build_sidebar_html(active, nav_badges=nav_badges,
                               current_user=current_user)


# ---------------------------------------------------------------------------
# 公开渲染函数
# ---------------------------------------------------------------------------


def _get_branding_prefix() -> str:
    """站点标识标题前缀（已 HTML 转义）；页面头模板全部注入点共用。"""
    site = branding.get_site_branding()
    return _escape(site["prefix"]) if site["prefix"] else ""


def render_navbar(active: str = "") -> str:
    """
    渲染导航（兼容名 → 侧栏）。

    Args:
        active: 当前活动页标识，为空时无高亮。

    Returns:
        侧栏 HTML 字符串。
    """
    return _build_sidebar_html(active)


def render_page_header(title: str = "SqlReport",
                       active_nav: str = "",
                       extra_css: str = "",
                       nav_badges: dict = None,
                       current_user: str = None) -> str:
    """
    渲染页面头部（<head> + 侧栏页壳 + container 开头）。

    ui-redesign T7.1：顶栏改为固定侧栏；公共 CSS 优先外链
    （/static/vendor/self@{hash}/common.css，hash 覆盖 CSS+JS），失败回退内联。
    extra_css 为页面特有样式，始终内联。

    Args:
        title: 页面标题（显示在浏览器标签页）。
        active_nav: 当前活动页标识，传给侧栏用于高亮。
        extra_css: 页面特定的额外 CSS 内容，追加在公共 CSS 之后。
        nav_badges: 可选 {active_key: 数字}，侧栏徽标。
        current_user: 可选当前用户名（侧栏账户区展示）。

    Returns:
        从 DOCTYPE 到 <div class="container"> 的完整头部 HTML。
    """
    sidebar_html = _build_sidebar_html(active_nav, nav_badges=nav_badges,
                                       current_user=current_user)
    css_url, _ = _get_common_asset_urls()
    if css_url:
        common_css_assets = f'<link rel="stylesheet" href="{css_url}">'
    else:
        common_css_assets = f"<style>{_COMMON_CSS}</style>"
    # site-branding：favicon link 单点注入 + 环境标题前缀（HTML 转义，
    # 前缀与 favicon 模式正交——default 模式下前缀仍生效，矩阵 M31）
    prefix = _get_branding_prefix()
    full_title = f"{prefix}{title}" if prefix else title
    return _PAGE_HEADER_TEMPLATE.substitute(
        title=full_title.replace("$", "$$"),
        sidebar_bootstrap=_SIDEBAR_BOOTSTRAP_JS,
        favicon_link='<link rel="icon" href="/favicon.ico">',
        common_css_assets=common_css_assets,
        extra_css=extra_css.replace("$", "$$"),
        sidebar=sidebar_html,
    )


def render_page_footer(extra_js: str = "") -> str:
    """
    渲染页面尾部（container/main/app 闭合 + 脚本 + </body></html>）。

    公共 JS 优先外链（<script defer>），资产写入失败时回退内联。
    extra_js：页面级胶水脚本，以 defer 追加在公共 JS 之后（保持依赖顺序）。
    """
    base = _render_common_footer()
    if not extra_js:
        return base
    # 在 </body> 前插入页面级脚本
    marker = "</body>\n</html>"
    injected = f"<script defer>{extra_js}</script>\n{marker}"
    return base.replace(marker, injected, 1)


def build_config_filter_box_html() -> str:
    """构建合并页顶部检索过滤框（spec ux-optimization 批次6#21）。

    纯前端过滤：输入事件由公共 JS initConfigFilter 监听，对页面内各
    配置区块的数据行（tr，跳过表头行）做文本 contains 显隐匹配；
    空查询恢复全部显隐。服务端零状态。
    """
    return (
        '<div class="config-filter-box" id="config-filter-box">'
        '<input type="text" id="config-filter-input" class="config-filter-input"'
        ' data-filter-scope="merge-tr" autocomplete="off"'
        ' placeholder="\U0001f50d 输入关键字过滤当前页配置项（连接池 / 用户 / 报表 / 分类），清空恢复全部">'
        '</div>'
    )


# ===================================================================
# 筛选操作符定义（从 report.py 移入）
# ===================================================================

FILTER_OPS = [
    ("nofilter", "不筛选", "不筛选"),
    ("contains", "包含", "包含"),
    ("notcontains", "不包含", "不包含"),
    ("eq",       "等于",   "="),
    ("neq",      "不等于", "≠"),
    ("gt",       "大于",   ">"),
    ("lt",       "小于",   "<"),
    ("gte",      "大于等于", "≥"),
    ("lte",      "小于等于", "≤"),
    ("isempty",  "为空",   "为空"),
    ("notempty", "非空",   "非空"),
]
_OP_MAP: dict[str, tuple[str, str]] = {
    code: (label, short) for code, label, short in FILTER_OPS
}
DEFAULT_OP = "contains"


# ===================================================================
# 单元格格式化与 HTML 转义（从 report.py 移入）
# ===================================================================


def format_cell(val) -> str:
    """
    格式化表格单元格值。

    - Decimal：避免科学计数法（如 0E-10 → 0）
    - float：如果 str() 产生科学计数法，重新格式化为全小数形式
    - None：返回空字符串
    - 其余：str() 原样输出
    """
    if val is None:
        return ""
    if isinstance(val, Decimal):
        if val == 0:
            return "0"
        s = format(val, "f")
    elif isinstance(val, float):
        s = str(val)
        # float 的 str() 可能产生科学计数法（如 1e-10），重新格式化为全小数
        if "e" in s or "E" in s:
            s = f"{val:.15f}"
    else:
        return str(val)
    # 去除尾部多余的 0 和小数点
    if "." in s:
        s = s.rstrip("0").rstrip(".")
        if s == "-0" or s == "":
            s = "0"
    return s


def _escape(val) -> str:
    """HTML 转义（自动格式化数值避免科学计数法）"""
    return html_mod.escape(format_cell(val))


def build_flash_html(flash: str, is_error: bool = None) -> str:
    """构建 flash 提示条 HTML。

    默认自动判定错误样式：以"错误"开头，或冒号前缀段含"失败"
    （批次3#13 单点判定——此前仅识别"错误"前缀，「xx 失败」类文案
    会误用成功样式）。is_error 传入时显式指定。

    批次5#14（spec ux-optimization）：data-autohide 标记供公共 JS 判定
    自动淡出（错误提示不自动消失，需人工关闭）；× 关闭按钮点击移除
    整条提示；URL 中的 flash 参数由前端 history.replaceState 剥除，
    防刷新重现/复制分享陈旧提示。
    """
    if is_error is None:
        prefix = flash.split(":", 1)[0]
        is_error = flash.startswith("错误") or "失败" in prefix
    css_cls = " flash-error" if is_error else " flash-success"
    autohide = ' data-autohide="0"' if is_error else ' data-autohide="1"'
    return (f'<div class="flash{css_cls}"{autohide}>{_escape(flash)}'
            f'<span class="flash-close" title="关闭">×</span></div>')


def build_empty_row_html(colspan, text: str, with_icon: bool = False,
                          icon: str = "file") -> str:
    """构建表格空状态提示行 HTML。

    with_icon=True 时输出带图标面板变体（colspan 固定 999，图标默认 file，
         批次5#19 筛选空态可传 search）。
    其余为纯文字版 `<tr><td colspan="N" class="empty-state">text</td></tr>`。
    """
    icon_html = _icon(icon)
    if with_icon:
        return ('<tr class="empty-state-row">'
                '<td colspan="999"><div class="empty-state">'
                f'<div class="icon">{icon_html}</div>' + text + '</div></td></tr>')
    return f'<tr><td colspan="{colspan}" class="empty-state">{text}</td></tr>'


# ===================================================================
# URL 参数工具（从 report.py 移入）
# ===================================================================


def build_sort_params(sorts):
    """将 sorts 列表编码为 URL 查询字符串（sort=col&dir=asc 重复）。"""
    parts = []
    for col, dir_ in sorts:
        parts.append(f"sort={urllib.parse.quote(col, safe='')}&dir={urllib.parse.quote(dir_, safe='')}")
    return "&".join(parts)


def build_filter_params(filters, skip_col=None):
    """
    将 filters 列表编码为 URL 查询字符串（f_{col}=value & op_{col}=op）。

    若指定 skip_col，则跳过该列的 filter 项（用于生成某列自己的排序链接时）。
    filters: list[(col, op, val), ...]
    """
    parts = []
    for col, op, val in filters:
        if op == "nofilter":
            continue
        if skip_col is not None and col == skip_col:
            continue
        fk = "f_" + urllib.parse.quote(col, safe='')
        parts.append(f"{fk}={urllib.parse.quote(val, safe='')}")
        if op != DEFAULT_OP:
            ok = "op_" + urllib.parse.quote(col, safe='')
            parts.append(f"{ok}={urllib.parse.quote(op, safe='')}")
    return "&".join(parts)


def filter_hidden_inputs(filters) -> str:
    """生成筛选参数的隐藏 input 标签（含操作符）"""
    parts = []
    for col, op, val in filters:
        if op == "nofilter":
            continue
        fk = urllib.parse.quote(col, safe='')
        parts.append(f'<input type="hidden" name="f_{fk}" value="{_escape(val)}">')
        if op != DEFAULT_OP:
            ok = urllib.parse.quote(col, safe='')
            parts.append(f'<input type="hidden" name="op_{ok}" value="{_escape(op)}">')
    return "".join(parts)


def build_cols_param(display_columns: list[str], all_columns: list[str]) -> str:
    """
    构建 cols URL 查询参数字符串。
    仅在用户自定义了列顺序或隐藏了列时生成参数，否则返回空字符串。
    """
    if display_columns == list(all_columns):
        return ""
    return "cols=" + urllib.parse.quote(",".join(display_columns), safe='')


def build_nested_filter_param(nf) -> str:
    """将嵌套筛选条件树编码为 URL 查询字符串片段（不含前导 &；空时返回空串）。"""
    if not nf:
        return ""
    return "nested_filter=" + urllib.parse.quote(json.dumps(nf, ensure_ascii=False), safe='')


# ===================================================================
# HTML 渲染函数（从 report.py 移入）
# ===================================================================


def build_pagination_html(report_id: int, current: int, total_pages: int,
                          page_size: int, total_rows: int,
                          sorts=None, filters=None, cols_param: str = '',
                          result_param: str = '',
                          page_url_base: str = None,
                          nested_filter=None,
                          always: bool = False) -> str:
    """构建分页 HTML，携带多字段排序/筛选/自定义列/多结果参数。

    当提供 page_url_base 时，直接以此为基 URL（须已含 &amp; 转义），
    忽略 report_id/page_size/sorts/filters/cols/result 参数。
    always=True（R2-D 报表详情页）：单页/空结果也渲染分页条（‹ 1 › + 跳转），
    与原型 page-detail「表格下方恒显分页条」一致；默认 False 保持其它调用方
    单页不输出的现状。
    """
    sorts = sorts or []
    filters = filters or []
    if total_pages <= 1 and not always:
        return ""
    if always:
        # 单页恒显：页数与当前页归一到 [1, max(total_pages,1)]，跳转仍受钳制
        total_pages = max(int(total_pages or 0), 1)
        current = min(max(int(current or 1), 1), total_pages)

    if page_url_base is not None:
        base_url = page_url_base
    else:
        # 基础 URL（使用 &amp; 确保 HTML 中 & 被正确转义）
        base_url = f"/report?id={report_id}&amp;page_size={page_size}"
        if sorts:
            base_url += "&amp;" + build_sort_params(sorts)
        if filters:
            base_url += "&amp;" + build_filter_params(filters)
        if cols_param:
            base_url += "&amp;" + cols_param
        if result_param:
            base_url += "&amp;" + result_param
            base_url += "&amp;" + cols_param
        if nested_filter:
            base_url += "&amp;" + build_nested_filter_param(nested_filter)

    parts = []

    if current > 1:
        parts.append(f'<a href="{base_url}&amp;page={current - 1}" class="nav-arrow">‹</a>')
    else:
        parts.append('<span class="disabled">‹</span>')

    pages_to_show = set()
    pages_to_show.add(1)
    pages_to_show.add(total_pages)
    for i in range(max(1, current - 3), min(total_pages, current + 3) + 1):
        pages_to_show.add(i)

    sorted_pages = sorted(pages_to_show)
    prev = 0
    for p in sorted_pages:
        if p - prev > 1:
            parts.append('<span class="disabled">…</span>')
        if p == current:
            parts.append(f'<span class="active">{p}</span>')
        else:
            parts.append(f'<a href="{base_url}&amp;page={p}" class="page-btn">{p}</a>')
        prev = p

    if current < total_pages:
        parts.append(f'<a href="{base_url}&amp;page={current + 1}" class="nav-arrow">›</a>')
    else:
        parts.append('<span class="disabled">›</span>')

    # 批次5#20：包一层 form 支持回车原生提交；goPage 内做 parseInt 钳制
    # （NaN 回落当前页，越界收敛到 [1, total_pages]）
    jump = (
        f'<form class="jump-box" onsubmit="return goPage(event, '
        f"'{base_url}', {current}, {total_pages})\">"
        f'跳转到: '
        f'<input type="number" id="jump_page" min="1" max="{total_pages}" '
        f'value="{current}"> '
        f'<button type="submit" class="btn btn-primary btn-sm">GO</button>'
        f'</form>'
    )

    return f'<div class="pagination">{" ".join(parts)}{jump}</div>'


def build_redis_banners_html(cache_info) -> str:
    """构建 Redis 降级/兜底提示横幅。"""
    if not cache_info:
        return ""
    src = cache_info.get("source", "")
    banners = []

    if src == "redis":
        ts = cache_info.get("timestamp")
        if ts:
            dt_str = app_config.format_local_time(ts, with_tz=False)
            banners.append(
                f'<div class="flash flash-info">'
                f'数据来自缓存快照（{_escape(dt_str)}）</div>'
            )
    elif src == "mysql":
        if not redis_cache.redis_available():
            banners.append(
                '<div class="flash flash-info">'
                '缓存服务暂不可用，已直连数据库查询（不影响使用）'
                '</div>'
            )

    return "".join(banners)


def build_debug_section_html(pool_config, actual_sql, active_index,
                              num_results, result_names, filters, sorts) -> str:
    """构建调试页签内容（R2-D：普通卡片 + grid-3 统计磁贴 + SQL 代码块）。

    按已确认原型 page-detail「调试」页签：不再用 debug-info 折叠块。
    连接池/结果/筛选/排序的可读信息行保留在磁贴下方（原文案），SQL 以
    code-block 代码块展示（保留 .sql-debug 类，页面 JS 语法高亮照常生效）。
    """
    sorts = sorts or []
    filters = filters or []
    tiles = []
    info_lines = []
    if pool_config:
        pname = pool_config.get("name", "?")
        phost = pool_config.get("host", "?")
        pport = pool_config.get("port", "?")
        puser = pool_config.get("user", "?")
        pdb = pool_config.get("database", "?")
        tiles.append(
            f'<div class="stat-tile"><div class="num">{_escape(str(pname))}</div>'
            f'<div class="lbl">连接池 {_escape(str(phost))}:{pport}</div></div>')
        tiles.append(
            f'<div class="stat-tile"><div class="num">{_escape(str(pdb))}</div>'
            f'<div class="lbl">数据库（用户 {_escape(str(puser))}）</div></div>')
        info_lines.append(f'连接池: {_escape(str(pname))} ({_escape(str(phost))}:{pport})'
                          f' | 用户: {_escape(str(puser))} | 数据库: {_escape(str(pdb))}')
    if num_results > 1:
        tiles.append(
            f'<div class="stat-tile"><div class="num">{active_index + 1}/{num_results}</div>'
            f'<div class="lbl">结果视图（{_escape(str(result_names[active_index]))}）</div></div>')
        info_lines.append(f'结果: {active_index + 1}/{num_results} ({result_names[active_index]})')
    tiles.append(
        f'<div class="stat-tile"><div class="num">{len(filters)} 条筛选 · {len(sorts)} 条排序</div>'
        f'<div class="lbl">当前条件</div></div>')
    if filters:
        filter_desc = " AND ".join(f'{_escape(c)} {_escape(_OP_MAP.get(o, [o, o])[1])} "{_escape(v)}"' for c, o, v in filters)
        info_lines.append(f'筛选: {filter_desc}')
    if sorts:
        sort_desc = ", ".join(f'{_escape(c)} {"↑" if d == "asc" else "↓"}' for c, d in sorts)
        info_lines.append(f'排序: {sort_desc}')
    grid_html = (f'<div class="grid-3">{"".join(tiles)}</div>'
                 if tiles else "")
    info_html = (f'<div class="muted">'
                 f'{"<br>".join(info_lines)}</div>' if info_lines else "")
    return (f'<div class="card">'
            f'<div class="card-head"><h2>执行信息（Debug）</h2></div>'
            f'{grid_html}{info_html}'
            f'<h3>实际执行 SQL</h3>'
            f'<pre class="sql-debug code-block" style="word-break:break-all">'
            f'{_escape(actual_sql)}</pre>'
            f'</div>')


# 嵌套筛选叶节点运算符 → 中文标签（与 result_transform._NESTED_LEAF_OPS 对齐）
_NF_OP_LABELS = [
    ("contains", "包含"),
    ("notcontains", "不包含"),
    ("eq", "等于"),
    ("neq", "不等于"),
    ("gt", "大于"),
    ("lt", "小于"),
    ("gte", "大于等于"),
    ("lte", "小于等于"),
    ("isempty", "为空"),
    ("notempty", "不为空"),
]


def build_nested_filter_builder_html(all_columns: list[str], nested_filter=None) -> str:
    """构建嵌套筛选条件构建器 UI（FR-003/FR-008/FR-009/FR-010/FR-016，禁止新建模块）。

    vanilla JS 实现（FR-008），不引入任何第三方依赖：
    - 可视化编辑 AND/OR 条件树，支持无限嵌套（FR-001 递归结构的前端呈现）；
    - 字段下拉来自报表列配置（含中文列名，FR-016）；
    - 操作符下拉（10 种，与后端 _NESTED_LEAF_OPS 对齐）；
    - 值输入框支持静态文本与表达式（now()/today()/date_add/date_sub）；
    - 表达式模板面板（FR-003）：now()/today() 点击即插入；date_add/date_sub 弹出输入表单后插入；
    - 每个值输入框旁内嵌悬浮提示与示例（FR-009），完整帮助来自 filter_help 模块（FR-010）；
    - UI 与 JSON 双向同步：树编辑实时写回 JSON 文本框；亦支持「从 JSON 载入」回写树；
    - 「应用嵌套筛选」把 JSON 写入筛选表单 ff 的 hidden input 并提交（与现有筛选并存，FR-005）。
    """
    all_columns = all_columns or []
    init_state = nested_filter if nested_filter else {"op": "and", "conditions": []}
    cols_json = json.dumps(all_columns, ensure_ascii=False)
    op_list_json = json.dumps(_NF_OP_LABELS, ensure_ascii=False)
    init_json = json.dumps(init_state, ensure_ascii=False)

    # JS 主逻辑（普通字符串，花括号为字面量；动态数据用 + 拼接注入）
    js = (
        "var NF_COLS = " + cols_json + ";\n"
        "var NF_OPLIST = " + op_list_json + ";\n"
        "var nfState = " + init_json + ";\n"
        "var nfActiveVal = null;\n"
        "var nfDateKind = 'add';\n"
        "function escAttr(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/\"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "function escHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "function nfGetNode(path){if(path==='')return nfState;var node=nfState;var ps=path.split('.');for(var i=0;i<ps.length;i++){node=node.conditions[parseInt(ps[i],10)];}return node;}\n"
        "function nfLeafHtml(c,path){"
        "var colOpts='<option value=\"\">— 选择列 —</option>';"
        "NF_COLS.forEach(function(col){colOpts+='<option value=\"'+escAttr(col)+'\"'+(c.col===col?' selected':'')+'>'+escHtml(col)+'</option>';});"
        "var opOpts='';NF_OPLIST.forEach(function(o){opOpts+='<option value=\"'+o[0]+'\"'+(c.op===o[0]?' selected':'')+'>'+o[1]+'</option>';});"
        "var emptyOp=(c.op==='isempty'||c.op==='notempty');"
        "var h='<div class=\"nf-leaf\" data-path=\"'+path+'\">';"
        "h+='<select class=\"nf-col\" onchange=\"nfSetCol(this)\">'+colOpts+'</select>';"
        "h+='<select class=\"nf-op\" onchange=\"nfSetOp(this)\">'+opOpts+'</select>';"
        "h+='<input class=\"nf-val\" type=\"text\" value=\"'+escAttr(c.value||'')+'\" placeholder=\"值，可填 张* 或 now()\" '+(emptyOp?'disabled':'')+' oninput=\"nfSetVal(this)\" onfocus=\"nfActiveVal=this\">';"
        "h+='<span class=\"nf-example\">例：张* 或 now()</span>';"
        "h+='<button type=\"button\" class=\"nf-help-btn\" onclick=\"toggleNestedHelp(this)\" title=\"表达式帮助\">?</button>';"
        "h+='<button type=\"button\" class=\"nf-rm\" onclick=\"nfRemoveNode(this)\" title=\"删除条件\">✕</button>';"
        "h+='</div>';return h;}\n"
        "function nfNodeHtml(node,isRoot,path){"
        "var h='<div class=\"nf-group\" data-path=\"'+path+'\">';"
        "h+='<div class=\"nf-group-head\">';"
        "h+='<select class=\"nf-andor\" onchange=\"nfSetAndOr(this)\">'+"
        "'<option value=\"and\"'+(node.op==='and'?' selected':'')+'>且 (AND)</option>'+"
        "'<option value=\"or\"'+(node.op==='or'?' selected':'')+'>或 (OR)</option>'+'</select>';"
        "h+='<button type=\"button\" onclick=\"nfAddCond(this)\">+ 条件</button>';"
        "h+='<button type=\"button\" onclick=\"nfAddGroup(this)\">+ 分组</button>';"
        "if(!isRoot)h+='<button type=\"button\" onclick=\"nfRemoveNode(this)\">删除组</button>';"
        "h+='</div><div class=\"nf-children\">';"
        "node.conditions.forEach(function(ch,i){var cp=path===''?String(i):path+'.'+i;"
        "if(ch.op==='and'||ch.op==='or'){h+=nfNodeHtml(ch,false,cp);}else{h+=nfLeafHtml(ch,cp);}});"
        "h+='</div></div>';return h;}\n"
        "function nfRender(){var root=document.getElementById('nf-tree');if(root)root.innerHTML=nfNodeHtml(nfState,true,'');nfSyncJson();}\n"
        "function nfSyncJson(){var ta=document.getElementById('nf-json');if(ta)ta.value=JSON.stringify(nfState,null,2);nfValidate();}\n"
        "function nfSetAndOr(sel){var n=nfGetNode(sel.closest('[data-path]').dataset.path);n.op=sel.value;nfSyncJson();}\n"
        "function nfSetCol(sel){var n=nfGetNode(sel.closest('[data-path]').dataset.path);n.col=sel.value;nfSyncJson();}\n"
        "function nfSetOp(sel){var n=nfGetNode(sel.closest('[data-path]').dataset.path);n.op=sel.value;"
        "if(n.op==='isempty'||n.op==='notempty'){n.value='';nfRender();}else{nfSyncJson();}}\n"
        "function nfSetVal(inp){var n=nfGetNode(inp.closest('[data-path]').dataset.path);n.value=inp.value;nfSyncJson();}\n"
        "function nfAddCond(btn){var n=nfGetNode(btn.closest('[data-path]').dataset.path);n.conditions.push({col:'',op:'contains',value:''});nfRender();}\n"
        "function nfAddGroup(btn){var n=nfGetNode(btn.closest('[data-path]').dataset.path);n.conditions.push({op:'and',conditions:[]});nfRender();}\n"
        "function nfRemoveNode(btn){var el=btn.closest('[data-path]');var path=el.dataset.path;if(path==='')return;"
        "var idx=parseInt(path.slice(path.lastIndexOf('.')+1),10);"
        "var parent=nfGetNode(path.indexOf('.')>=0?path.slice(0,path.lastIndexOf('.')):'');"
        "parent.conditions.splice(idx,1);nfRender();}\n"
        "function nfValidate(){var msg=document.getElementById('nf-msg');var errs=[];"
        "function walk(node){if(node.op==='and'||node.op==='or'){if(!node.conditions||!node.conditions.length)errs.push('存在空分组，请补充条件');node.conditions.forEach(walk);}"
        "else{if(!node.col)errs.push('存在未选择列的条件');if(node.op!=='isempty'&&node.op!=='notempty'&&!String(node.value).trim())errs.push('存在未填值的条件');}}"
        "walk(nfState);if(msg)msg.textContent=errs.join('；');return errs.length?errs.join('；'):null;}\n"
        "function applyNestedFilter(){var err=nfValidate();if(err){alert('请先修正：'+err);return;}"
        "var ff=document.getElementById('ff');if(!ff){alert('筛选表单不存在');return;}"
        "var inp=ff.querySelector('input[name=\"nested_filter\"]');if(!inp){inp=document.createElement('input');inp.type='hidden';inp.name='nested_filter';ff.appendChild(inp);}"
        "inp.value=JSON.stringify(nfState);ff.submit();}\n"
        "function clearNestedFilter(){var ff=document.getElementById('ff');if(!ff)return;"
        "var inp=ff.querySelector('input[name=\"nested_filter\"]');if(!inp){inp=document.createElement('input');inp.type='hidden';inp.name='nested_filter';ff.appendChild(inp);}"
        "inp.value='';ff.submit();}\n"
        "function nfLoadFromJson(){var ta=document.getElementById('nf-json');try{var obj=JSON.parse(ta.value);"
        "if(!obj||typeof obj!=='object'||(obj.op!=='and'&&obj.op!=='or'))throw new Error('顶层需为 op:and/or');"
        "nfState=obj;nfRender();}catch(e){alert('JSON 解析失败：'+e.message);}}\n"
        "function insertExpr(text){if(!nfActiveVal){alert('请先点击要填入的值输入框');return;}"
        "var el=nfActiveVal;var s=el.selectionStart,e=el.selectionEnd;var v=el.value;"
        "el.value=v.slice(0,s)+text+v.slice(e);el.focus();el.selectionStart=el.selectionEnd=s+text.length;"
        "var n=nfGetNode(el.closest('[data-path]').dataset.path);n.value=el.value;nfSyncJson();}\n"
        "function nfToggleDateForm(kind){nfDateKind=kind;document.getElementById('nf-date-form').style.display='inline-block';}\n"
        "function nfInsertDate(){var n=document.getElementById('nf-date-n').value;var u=document.getElementById('nf-date-u').value;"
        "var text=(nfDateKind==='add'?'date_add':'date_sub')+'(now(),'+n+',\\''+u+'\\')';insertExpr(text);"
        "document.getElementById('nf-date-form').style.display='none';}\n"
        "onReady(nfRender);\n"
    )

    help_popup = render_nested_filter_help_popup()

    return (
        '<div class="nf-builder" style="margin-bottom:10px;border:1px solid #e2e8f0;'
        'border-radius:8px;padding:12px;background:#f8fafc">'
        '<div>嵌套筛选条件构建器（AND/OR 组合，支持无限嵌套）</div>'
        '<div id="nf-tree"></div>'
        '<div style="display:flex;gap:6px;flex-wrap:wrap">'
        '<button type="button" class="btn btn-sm btn-primary" onclick="applyNestedFilter()">应用嵌套筛选</button>'
        '<button type="button" class="btn btn-sm" onclick="clearNestedFilter()">清除嵌套筛选</button>'
        '<button type="button" class="btn btn-sm" onclick="nfLoadFromJson()">从 JSON 载入</button>'
        '</div>'
        '<div id="nf-expr-panel">'
        '<span>表达式模板：</span>'
        '<button type="button" class="btn btn-sm" onclick="insertExpr(\'now()\')">now()</button>'
        '<button type="button" class="btn btn-sm" onclick="insertExpr(\'today()\')">today()</button>'
        '<button type="button" class="btn btn-sm" onclick="nfToggleDateForm(\'add\')">date_add…</button>'
        '<button type="button" class="btn btn-sm" onclick="nfToggleDateForm(\'sub\')">date_sub…</button>'
        '<span id="nf-date-form" style="display:none">数量'
        '<input id="nf-date-n" type="number" value="7">'
        '单位<select id="nf-date-u"><option value="day">天</option>'
        '<option value="month">月</option><option value="year">年</option></select>'
        '<button type="button" class="btn btn-sm btn-primary" onclick="nfInsertDate()">确定</button></span>'
        '</div>'
        '<div>'
        '<textarea id="nf-json" style="width:100%;min-height:72px;font-family:monospace;font-size:12px;'
        'border:1px solid #cbd5e1;border-radius:6px;padding:8px" spellcheck="false"></textarea>'
        '<div id="nf-msg" style="min-height:16px"></div>'
        '</div>'
        + help_popup +
        '<style>'
        '.nf-group{margin:6px 0;padding:8px;border:1px dashed #cbd5e1;border-radius:6px;background:#fff}'
        '.nf-group-head{display:flex;gap:6px;align-items:center;margin-bottom:6px}'
        '.nf-children{margin-left:14px}'
        '.nf-leaf{display:flex;gap:6px;align-items:center;margin:4px 0;flex-wrap:wrap}'
        '.nf-leaf select,.nf-group-head select{padding:3px 6px;border:1px solid #cbd5e1;border-radius:4px;font-size:12px}'
        '.nf-leaf input.nf-val{padding:3px 6px;border:1px solid #cbd5e1;border-radius:4px;font-size:12px;flex:1;min-width:140px}'
        '.nf-example{font-size:11px;color:#94a3b8;white-space:nowrap}'
        '.nf-help-btn{width:22px;height:22px;border-radius:50%;border:1px solid #cbd5e1;background:#fff;'
        'color:#475569;font-weight:700;cursor:pointer}'
        '.nf-rm{border:none;background:transparent;color:#b91c1c;cursor:pointer;font-size:13px}'
        '</style>'
        '<script>' + js + '</script>'
        '</div>'
    )


def build_current_rules_section_html(filters, sorts, display_columns: list[str],
                                      all_columns: list[str],
                                      nested_filter=None) -> str:
    """
    构建「规则」页签内容（R2-D：左右分栏双卡，原型 page-detail）。
    左卡=嵌套条件构建器；右卡=当前报表筛选/排序/字段规则为 JSON 格式，提供
    复制/应用按钮，方便用户将规则粘贴到 API 接口配置表单。
    """
    sorts = sorts or []
    filters = filters or []

    # 构建 JSON 规则对象
    rules = {}
    if filters:
        rules["filters"] = [
            {"col": c, "op": o, "val": v}
            for c, o, v in filters
        ]
    if sorts:
        rules["sorts"] = [
            {"col": c, "dir": d}
            for c, d in sorts
        ]
    if display_columns and display_columns != all_columns:
        rules["columns"] = ",".join(display_columns)
    else:
        rules["columns"] = ""
    # 嵌套筛选（FR-005 与 filters/sorts 并列）：并入同一份规则 JSON，
    # 使「当前规则」成为可整体复制、粘贴到 API 配置的唯一完整来源
    if nested_filter:
        rules["nested_filter"] = nested_filter

    rules_json = json.dumps(rules, indent=2, ensure_ascii=False)

    # 可读摘要
    summary_parts = []
    if filters:
        filter_summary = " AND ".join(
            f'{_escape(c)} {_escape(_OP_MAP.get(o, [o, o])[1])} "{_escape(v)}"'
            for c, o, v in filters
        )
        summary_parts.append(f'筛选: {filter_summary}')
    if sorts:
        sort_summary = ", ".join(
            f'{_escape(c)} {"↑" if d == "asc" else "↓"}'
            for c, d in sorts
        )
        summary_parts.append(f'排序: {sort_summary}')
    if display_columns and display_columns != all_columns:
        summary_parts.append(f'字段: {", ".join(_escape(c) for c in display_columns)}')
    if not summary_parts:
        summary_parts.append("无自定义规则（显示全部字段和数据）")

    content = (
        '<div>'
        + '<br>'.join(summary_parts) +
        '</div>'
        '<div style="position:relative">'
        '<textarea id="current-rules-json" class="code-textarea" spellcheck="false">'
        f'{_escape(rules_json)}</textarea>'
        '</div>'
        '<div>'
        '提示: 以上 JSON 同时包含筛选/排序/字段/嵌套筛选，粘贴到 API 接口配置的「规则 JSON」即可完整复用当前报表规则。'
        '</div>'
    )
    builder_html = build_nested_filter_builder_html(all_columns, nested_filter)
    # R2-D（原型 page-detail「规则」页签）：grid-2 左右双卡（任务书/知识库
    # 06 卷确认结构；原型为 340px split，此处按任务书用 grid-2 等宽双卡）——
    # 左=嵌套条件构建器（筛选/排除规则），右=当前规则 JSON（复制/应用）。
    left_card = ('<div class="card">'
                 '<div class="card-head"><h2>嵌套条件</h2></div>'
                 + builder_html + '</div>')
    right_card = ('<div class="card">'
                  '<div class="card-head"><h2>当前规则</h2>'
                  '<div class="actions">'
                  '<button type="button" onclick="copyRulesJson()" '
                  'class="btn btn-outline btn-sm">复制 JSON</button>'
                  '<button type="button" onclick="applyRulesJson()" '
                  'class="btn btn-secondary btn-sm">从 JSON 应用</button>'
                  '</div></div>' + content + '</div>')
    return f'<div class="grid-2">{left_card}{right_card}</div>'


def build_memo_section_html(memo_raw: str, report_id: int = None) -> str:
    """构建「备注」页签内容（R2-D：普通卡片，非折叠块）。

    备注内容为 Markdown 源文本：经 render_markdown() 渲染为已消毒的 HTML
    （含 ```mermaid 时产出 <pre class="mermaid">，由前端按需渲染）。
    按已确认原型 page-detail：页签内直接展示卡片（card + card-head + md-body），
    不再使用 debug-info 折叠块；无备注时显示占位文案。
    report_id 仅保留签名兼容（三态折叠记忆已废除，不再使用）。
    """
    memo_html = markdown_render.render_markdown(memo_raw)
    # 内容外包 .md-body 排版容器（消费页 extra_css 末尾的 _MD_CSS 提供样式）
    body = f'<div class="md-body">{memo_html}</div>' if memo_html else '<div class="muted">暂无备注</div>'
    return ('<div class="card">'
            '<div class="card-head"><h2>备注（Markdown）</h2></div>'
            + body + '</div>')


def build_result_selector_html(report_id, qs_page_size, result_names,
                                active_index, sql_override, swi,
                                filters=None, sorts=None) -> str:
    """构建多结果集切换 segment（R2-D：原型 page-detail 工具行内的结果集分段控件）。

    协议不变：容器携带 data-report-id / data-active-index / data-swi /
    data-page-size / data-sql-override，点击按钮走 switchResult 切换 result=N。
    filters/sorts: 当前结果视图已应用的筛选/排序（用于状态角标，None 视为无）。
    """
    num_results = len(result_names)
    if num_results <= 1:
        return ""
    seg_btns = "".join(
        f'<button type="button" class="{"active" if i == active_index else ""}"'
        f' data-index="{i}" onclick="switchResult(this)">'
        f'{_escape(result_names[i])}</button>'
        for i in range(num_results)
    )
    # PH-11 视图状态角标：复用 sort-tag 样式，当前视图已应用筛选/排序时展示
    badge_parts = []
    if filters:
        badge_parts.append(
            f'<span class="sort-tag" style="display:inline-flex;align-items:center;gap:3px;'
            f'background:#eef2ff;color:#4f46e5;border-radius:4px;padding:2px 8px;'
            f'font-size:12px;border:1px solid #c7d2fe">已筛选 ×{len(filters)}</span>')
    if sorts:
        badge_parts.append(
            f'<span class="sort-tag" style="display:inline-flex;align-items:center;gap:3px;'
            f'background:#eef2ff;color:#4f46e5;border-radius:4px;padding:2px 8px;'
            f'font-size:12px;border:1px solid #c7d2fe">已排序 ×{len(sorts)}</span>')
    badges_html = "".join(badge_parts)
    return (
        f'<div class="result-selector" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"'
        f' data-report-id="{report_id}" data-active-index="{active_index}"'
        f' data-swi="{_escape(swi)}" data-page-size="{qs_page_size}"'
        f' data-sql-override="{_escape(sql_override or "")}">'
        f'<span>结果视图:</span>'
        f'<div class="segment" aria-label="结果集">{seg_btns}</div>'
        f'{badges_html}'
        f'<span>每个结果视图独立维护筛选/排序/分页状态</span>'
        f'</div>'
    )


def build_cache_badge_html(cache_info, prefer_cache: bool = False,
                           cache_ttl_hours: int = 0) -> str:
    """构建缓存状态标签 HTML。

    当 prefer_cache=True 且 cache_ttl_hours>0 时，额外显示 TTL 信息；
    快照模式（redis/redis_fallback/process）带时间戳时计算过期时刻
    （ts + ttl*3600），已过期显示警示样式 + 「已过期（下次请求自动刷新）」；
    TTL=0（永不过期）保持现状。
    """
    parts = []
    expired = False
    if prefer_cache:
        parts.append("已启用缓存")
        if cache_ttl_hours > 0:
            parts.append(f"缓存 {cache_ttl_hours} 小时")
    extra = (" · " + " · ".join(parts)) if parts else ""
    if cache_info:
        src = cache_info.get("source", "")
        ts = cache_info.get("timestamp")
        if (src in ("redis", "redis_fallback", "process")
                and prefer_cache and cache_ttl_hours > 0 and ts
                and ts + cache_ttl_hours * 3600 < time.time()):
            expired = True
            extra += " · 已过期，下次访问自动刷新"
        if src == "redis":
            age = int(time.time() - ts) if ts else 0
            css = "flash-warn" if expired else "fresh"
            return (f'<span class="cache-badge {css}">'
                    f'缓存快照 ({age}s 前{extra})'
                    '</span>')
        elif src == "redis_fallback":
            age = int(time.time() - ts) if ts else 0
            return ('<span class="cache-badge flash-warn">'
                    f'缓存快照（{age}s 前{extra}，数据库不可用）'
                    '</span>')
        elif src == "process":
            age = int(time.time() - ts) if ts else 0
            css = "flash-warn" if expired else "fresh"
            return (f'<span class="cache-badge {css}">'
                    f'本地缓存 ({age}s 前刷新{extra})'
                    '</span>')
        else:
            badge = '实时查询'
            if extra:
                badge += f' ({extra[3:]})'
            return f'<span class="cache-badge">{badge}</span>'
    else:
        badge = '未缓存'
        if extra:
            badge += f' ({extra[3:]})'
        return f'<span class="cache-badge">{badge}</span>'


def build_sort_bar_html(report_id, page_size, sorts, filters,
                         cols_param, result_param, nested_filter=None) -> str:
    """构建排序栏（显示当前排序列及其优先级）HTML。"""
    sorts = sorts or []
    filters = filters or []
    sort_bar_parts = []
    if sorts:
        sort_bar_parts.append('<div class="sort-bar">')
        sort_bar_parts.append('<span>排序:</span>')
        for idx, (sc, sd) in enumerate(sorts, 1):
            label = f'{_escape(sc)} {"↑" if sd == "asc" else "↓"}'
            prio = chr(0x2460 + idx - 1) if idx <= 20 else f"#{idx}"
            rm_sorts = [(c, d) for c, d in sorts if c != sc]
            rm_href = f"/report?id={report_id}&amp;page_size={page_size}"
            if rm_sorts:
                rm_href += "&amp;" + build_sort_params(rm_sorts)
            if filters:
                rm_href += "&amp;" + build_filter_params(filters)
            if cols_param:
                rm_href += "&amp;" + cols_param
            if result_param:
                rm_href += "&amp;" + result_param
            if nested_filter:
                rm_href += "&amp;" + build_nested_filter_param(nested_filter)
            sort_bar_parts.append(
                f'<span class="sort-tag">'
                f'<span class="sort-prio">{prio}</span> {label}'
                f'<a href="{rm_href}" class="sort-link" title="移除排序">✕</a>'
                f'</span>'
            )
        sort_bar_parts.append('</div>')
    return "".join(sort_bar_parts)


def build_table_header_html(columns, display_columns, sorts, filters,
                             report_id, page_size, cols_param, result_param,
                             nested_filter=None) -> str:
    """构建表头 HTML（排序行 + 独立快筛行）。

    R2-D（原型 page-detail 数据页签）：第 1 行 <tr> 只放列名与排序双箭头；
    第 2 行 <tr class="qf-row"> 放筛选操作符下拉框 + 筛选输入框（表头下独立
    快筛行）。筛选协议（f_/op_ 参数名、form="ff" 关联、操作符集合）不变。
    """
    sorts = sorts or []
    filters = filters or []
    filter_form_id = "ff"
    thead_parts = ["<tr>"]
    qf_parts = ['<tr class="qf-row">']
    for col in display_columns:
        current_dir = None
        sort_priority = 0
        for idx, (c, d) in enumerate(sorts, 1):
            if c == col:
                current_dir = d
                sort_priority = idx
                break

        asc_sorts = list(sorts)
        found_asc = False
        for i, (c, d) in enumerate(asc_sorts):
            if c == col:
                asc_sorts[i] = (col, "asc")
                found_asc = True
                break
        if not found_asc:
            asc_sorts.append((col, "asc"))
        asc_href = f"/report?id={report_id}&amp;page_size={page_size}"
        asc_href += "&amp;" + build_sort_params(asc_sorts)
        if filters:
            asc_href += "&amp;" + build_filter_params(filters)
        if cols_param:
            asc_href += "&amp;" + cols_param
        if result_param:
            asc_href += "&amp;" + result_param
        if nested_filter:
            asc_href += "&amp;" + build_nested_filter_param(nested_filter)
        asc_cls = "sort-arrow active" if current_dir == "asc" else "sort-arrow"

        desc_sorts = list(sorts)
        found_desc = False
        for i, (c, d) in enumerate(desc_sorts):
            if c == col:
                desc_sorts[i] = (col, "desc")
                found_desc = True
                break
        if not found_desc:
            desc_sorts.append((col, "desc"))
        desc_href = f"/report?id={report_id}&amp;page_size={page_size}"
        desc_href += "&amp;" + build_sort_params(desc_sorts)
        if filters:
            desc_href += "&amp;" + build_filter_params(filters)
        if cols_param:
            desc_href += "&amp;" + cols_param
        if result_param:
            desc_href += "&amp;" + result_param
        if nested_filter:
            desc_href += "&amp;" + build_nested_filter_param(nested_filter)
        desc_cls = "sort-arrow active" if current_dir == "desc" else "sort-arrow"

        priority_badge = ""
        if sort_priority > 0:
            prio_char = chr(0x2460 + sort_priority - 1) if sort_priority <= 20 else f"#{sort_priority}"
            priority_badge = f'<span class="sort-prio">{prio_char}</span>'

        cur_fval = ""
        cur_op = "nofilter"
        for item in filters:
            c, op, val = item
            if c == col:
                cur_fval = val
                cur_op = op
                break

        filter_input_name = "f_" + urllib.parse.quote(col, safe='')
        filter_op_name = "op_" + urllib.parse.quote(col, safe='')

        op_options = ""
        for code, label, short in FILTER_OPS:
            sel = ' selected' if code == cur_op else ''
            op_options += f'<option value="{code}"{sel}>{_escape(label)}</option>'

        input_hidden = cur_op in ("nofilter", "isempty", "notempty")
        input_style = "display:none" if input_hidden else ""
        input_disabled = "disabled" if input_hidden else ""

        # 批次6#25：data-col 供前端列设置 localStorage 记忆定位列（排序行/快筛行
        # 同步隐藏 + 同索引 td 隐藏；R2-D：快筛移至表头下独立 qf-row）
        thead_parts.append(f"""<th data-col="{_escape(col)}">
  <div class="sort-links" style="display:inline-flex;align-items:center;gap:0">
    <a href="{asc_href}" class="sort-link" title="升序">{_escape(col)}</a>
    <a href="{asc_href}" class="sort-link" title="升序"><span class="{asc_cls}">▲</span></a>
    <a href="{desc_href}" class="sort-link" title="降序"><span class="{desc_cls}">▼</span></a>
    {priority_badge}
  </div>
</th>""")
        qf_parts.append(f"""<td data-col="{_escape(col)}">
  <div class="filter-row" style="display:flex;gap:2px;align-items:center">
    <select class="filter-op" form="{filter_form_id}" name="{filter_op_name}"
      style="flex-shrink:0;cursor:pointer"
      onchange="toggleFilterInput('{filter_input_name}', this)">{op_options}</select>
    <input type="text" class="filter-input" form="{filter_form_id}"
      name="{filter_input_name}" placeholder="筛选 {_escape(col)}{FILTER_HINT_SUFFIX}"
      value="{_escape(cur_fval)}" title="{_escape(cur_fval)}"
      style="{input_style}" {input_disabled}>
  </div>
</td>""")
    thead_parts.append("</tr>")
    qf_parts.append("</tr>")
    return "".join(thead_parts) + "".join(qf_parts)


def build_table_body_html(rows, display_indices, filters=None,
                          clear_filters_href: str = None) -> str:
    """构建表格数据行 HTML。

    批次5#19（spec ux-optimization）：空结果按是否有筛选区分文案——
    filters 非空显示「{_icon("search")} 没有符合筛选条件的行」+ 服务端构造好的
    「清除筛选」链接（当前路径去掉 f_*/op_* 参数）；否则保持「暂无数据」。
    """
    tbody = ""
    if not rows:
        if filters:
            link = ""
            if clear_filters_href:
                link = (f' <a href="{clear_filters_href}"'
                        f' class="clear-filter">清除筛选</a>')
            tbody = build_empty_row_html(
                999, "没有符合筛选条件的行" + link,
                with_icon=True, icon=_icon("search"))
        else:
            tbody = build_empty_row_html(999, "暂无数据", with_icon=True)
    else:
        for row in rows:
            cells = "".join(f"<td>{_escape(row[i])}</td>" for i in display_indices)
            tbody += "<tr>" + cells + "</tr>"
    return tbody


def build_controls_bar_html(report_id, page_size, sorts, filters,
                             cols_param, display_columns, active_index,
                             cache_badge, total_rows, total_pages,
                             result_param='', page=1, nested_filter=None,
                             result_html='') -> str:
    """构建数据页工具行（分页行数、页大小、结果集 segment、刷新、设置抽屉、高级筛选、缓存状态）。

    ui-redesign T7.4：导出选项迁至统一导出对话框（build_export_modal_html），
    字段/排序设置改为右侧抽屉；页大小/重建缓存协议与隐藏字段保持不变。
    result_html（R2-D）：多结果集 segment（build_result_selector_html 输出），
    非空时插在页大小表单之后、grow 之前（原型 page-detail 工具行内）。
    """
    sorts = sorts or []
    filters = filters or []
    cols_hidden = f'<input type="hidden" name="cols" value="{_escape(",".join(display_columns))}">' if cols_param else ""
    nf_hidden = (f'<input type="hidden" name="nested_filter" value="'
                 f'{_escape(urllib.parse.quote(json.dumps(nested_filter, ensure_ascii=False), safe=""))}">'
                 ) if nested_filter else ""
    return f"""
<div class="toolbar">
  <span class="meta">共 {total_rows} 行，{total_pages} 页</span>
  <form method="get" action="/report" style="display:inline-flex;align-items:center;gap:8px">
    <input type="hidden" name="id" value="{report_id}">
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    {nf_hidden}
     <label>每页
       <select name="page_size" onchange="navigateTo(this.closest('form').action+'?'+new URLSearchParams(new FormData(this.closest('form'))).toString())">
         {''.join(f'<option value="{s}"{" selected" if page_size == s else ""}>{s}</option>'
                  for s in [10, 20, 50, 100, 200])}
       </select>
     </label>
    <noscript><button type="submit" class="btn btn-primary btn-sm">刷新</button></noscript>
  </form>
  {f'<span class="sep"></span>{result_html}' if result_html else ''}
  <div class="grow"></div>
  <button type="button" class="btn btn-sm btn-secondary" onclick="openPanel('fieldSettingsPanel')">{_icon("settings")} 字段设置</button>
  <button type="button" class="btn btn-sm btn-secondary" onclick="openPanel('sortSettingsPanel')">{_icon("list")} 排序设置</button>
  <button type="button" class="btn btn-sm btn-secondary" onclick="gotoTab('rules')">高级筛选</button>
  <span class="sep"></span>
   <form method="post" action="/report" style="display:inline-flex;align-items:center">
    <input type="hidden" name="action" value="refresh_cache">
    <input type="hidden" name="id" value="{report_id}">
    <input type="hidden" name="page" value="{page}">
    <input type="hidden" name="page_size" value="{page_size}">
    {"".join(f'<input type="hidden" name="sort" value="{_escape(c)}"><input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)}
    {filter_hidden_inputs(filters) if filters else ''}
    {cols_hidden}
    {nf_hidden}
    {f'<input type="hidden" name="result" value="{active_index}">' if result_param else ''}
    <button type="submit" class="btn btn-sm btn-refresh">⟳ 重建缓存</button>
   </form>
  {cache_badge}
</div>"""


def build_export_modal_html(report_id, sorts, filters, cols_param,
                            display_columns, active_index,
                            result_param='', nested_filter=None) -> str:
    """统一导出对话框（GET /export，协议与原内联表单一致）。

    选项常显：格式 / 字符集 / 智能去引号 / 压缩包 / 应用自定义字段（T7.4）。
    """
    sorts = sorts or []
    filters = filters or []
    cols_hidden = (f'<input type="hidden" name="cols" '
                   f'value="{_escape(",".join(display_columns))}">') if cols_param else ""
    nf_hidden = (f'<input type="hidden" name="nested_filter" value="'
                 f'{_escape(urllib.parse.quote(json.dumps(nested_filter, ensure_ascii=False), safe=""))}">'
                 ) if nested_filter else ""
    hiddens = (
        f'<input type="hidden" name="id" value="{report_id}">'
        + (f'<input type="hidden" name="result" value="{active_index}">' if result_param else "")
        + "".join(f'<input type="hidden" name="sort" value="{_escape(c)}">'
                  f'<input type="hidden" name="dir" value="{_escape(d)}">' for c, d in sorts)
        + (filter_hidden_inputs(filters) if filters else "")
        + cols_hidden + nf_hidden
    )
    return f"""
<div class="modal" id="modal-export" role="dialog" aria-modal="true" aria-label="导出">
  <div class="modal-head"><h3>导出</h3></div>
  <div class="modal-body">
    <p>导出当前筛选、排序与列设置的完整结果集（不分页）。</p>
    <form method="get" action="/export" id="export-modal-form">
      {hiddens}
      <fieldset class="fs">
        <legend>格式</legend>
        <div class="check-group">
          <label class="check"><input type="radio" name="format" value="csv" checked id="export-format-csv"> CSV（UTF-8 BOM）</label>
          <label class="check"><input type="radio" name="format" value="json" id="export-format-json"> JSON</label>
          <label class="check"><input type="checkbox" name="zip" value="1"> 打包为 ZIP</label>
        </div>
        <select id="export-format-select" style="display:none" aria-hidden="true">
          <option value="csv">CSV</option><option value="json">JSON</option>
        </select>
      </fieldset>
      <fieldset class="fs">
        <legend>字符集</legend>
        <div class="check-group">
          <label class="check"><input type="radio" name="charset" value="gbk" checked> GBK（Excel 中文版推荐）</label>
          <label class="check"><input type="radio" name="charset" value="utf8"> UTF-8（通用 / 程序处理）</label>
        </div>
        <div class="field-hint" id="export-charset-json-hint" style="display:none">
          JSON 固定 UTF-8（RFC 8259，与 API 响应一致），此选项对 JSON 不生效。
        </div>
      </fieldset>
      <fieldset class="fs">
        <legend>智能去引号（仅 JSON）</legend>
        <div id="export-smart-panel">
          <input type="hidden" name="smart_quotes" id="export-smart-quotes-input" value="0">
          <div class="check-group">
            <label class="check"><input type="checkbox" class="smart-quote-cb" value="1"> 十进制数字（含正负号）</label>
            <label class="check"><input type="checkbox" class="smart-quote-cb" value="2"> 科学计数法</label>
            <label class="check"><input type="checkbox" class="smart-quote-cb" value="4"> 千分位数字</label>
          </div>
          <div>
            原生 int/float 恒裸输出；输出永远合法 JSON（RFC 8259）。
            <span id="export-smart-csv-hint" style="display:none">（仅 JSON 格式支持）</span>
          </div>
        </div>
      </fieldset>
      <fieldset class="fs">
        <legend>列范围</legend>
        <label class="check"><input type="checkbox" name="use_custom_cols" value="1" {"checked" if cols_param else ""}> 应用自定义字段</label>
      </fieldset>
    </form>
  </div>
  <div class="modal-foot">
    <button type="button" class="btn btn-secondary" onclick="closePanel('modal-export')">取消</button>
    <button type="submit" form="export-modal-form" class="btn btn-primary">导出</button>
  </div>
</div>
<script>
(function () {{
  function syncRadio() {{
    var sel = document.getElementById('export-format-select');
    if (!sel) return;
    sel.value = (document.getElementById('export-format-json')||{{}}).checked ? 'json' : 'csv';
    if (typeof updateExportSmartState === 'function') updateExportSmartState();
    if (typeof updateExportCharsetState === 'function') updateExportCharsetState();
  }}
  var rj = document.getElementById('export-format-json');
  var rc = document.getElementById('export-format-csv');
  if (rj) rj.addEventListener('change', syncRadio);
  if (rc) rc.addEventListener('change', syncRadio);
  function updateExportSmartFlags() {{
    var input = document.getElementById('export-smart-quotes-input');
    if (!input) return;
    var flags = 0;
    var cbs = document.querySelectorAll('#export-smart-panel .smart-quote-cb');
    cbs.forEach(function(cb) {{
      if (cb.checked) flags |= parseInt(cb.value, 10) || 0;
    }});
    input.value = flags;
  }}
  function updateExportCharsetState() {{
    var sel = document.getElementById('export-format-select');
    if (!sel) return;
    var isJson = sel.value === 'json';
    var radios = document.querySelectorAll('input[name="charset"]');
    radios.forEach(function(r) {{
      r.disabled = isJson;
      if (isJson) r.checked = (r.value === 'utf8');
    }});
    var hint = document.getElementById('export-charset-json-hint');
    if (hint) hint.style.display = isJson ? 'block' : 'none';
  }}
  function updateExportSmartState() {{
    var sel = document.getElementById('export-format-select');
    if (!sel) return;
    var isCsv = sel.value === 'csv';
    var cbs = document.querySelectorAll('#export-smart-panel .smart-quote-cb');
    cbs.forEach(function(cb) {{
      cb.disabled = isCsv;
      if (isCsv) cb.checked = false;
    }});
    if (isCsv) updateExportSmartFlags();
    var hint = document.getElementById('export-smart-csv-hint');
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
  }}
  window.updateExportSmartFlags = updateExportSmartFlags;
  window.updateExportSmartState = updateExportSmartState;
  document.querySelectorAll('#export-smart-panel .smart-quote-cb').forEach(function(cb) {{
    cb.addEventListener('change', updateExportSmartFlags);
  }});
  window.updateExportCharsetState = updateExportCharsetState;
  onReady(function() {{
    updateExportSmartState();
    updateExportCharsetState();
  }});
}})();
</script>"""


def build_field_settings_panel_html(all_columns, display_columns) -> str:
    """构建字段设置面板 HTML。"""
    field_settings_items = []
    for idx, col in enumerate(all_columns):
        checked = "checked" if col in display_columns else ""
        pos = display_columns.index(col) if col in display_columns else -1
        up_disabled = "disabled" if pos <= 0 else ""
        down_disabled = "disabled" if pos >= len(display_columns) - 1 or pos < 0 else ""
        bg_color = '#f8fafc' if col in display_columns else '#fff'
        field_settings_items.append(
            f'<label class="field-item" draggable="true" style="display:flex;align-items:center;gap:8px">'
            f'<span class="drag-handle" style="cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
            f'<input type="checkbox" name="col_visible" value="{_escape(col)}" {checked} '
            f'onchange="toggleFieldItem(this)" onclick="event.stopPropagation()">'
            f'<span style="flex:1">{_escape(col)}</span>'
            f'<input type="hidden" name="col_order" value="{_escape(col)}">'
            f'<button type="button" class="field-up" {up_disabled} onclick="moveField(this,-1)">▲</button>'
            f'<button type="button" class="field-down" {down_disabled} onclick="moveField(this,1)">▼</button>'
            f'</label>'
        )
    field_settings_html = (
        '<div id="fieldSettingsPanel" class="side-panel" role="dialog" '
        'aria-modal="true" aria-label="字段设置">'
        '<div class="panel-head"><h3>字段设置</h3>'
        '<button type="button" class="btn btn-sm btn-ghost" '
        'onclick="closePanel(\'fieldSettingsPanel\')">收起</button></div>'
        '<div id="fieldList" style="display:grid;'
        'grid-template-columns:1fr;gap:6px;max-height:60vh;overflow-y:auto">'
        + "".join(field_settings_items) +
        '</div>'
        '<div style="display:flex;gap:8px">'
        '<button type="button" onclick="selectAllFields(true)" class="btn btn-outline btn-sm">全选</button>'
        '<button type="button" onclick="selectAllFields(false)" class="btn btn-outline btn-sm">全不选</button>'
        '<button type="button" onclick="applyFieldSettings()" class="btn btn-primary btn-sm">应用</button>'
        '</div>'
        '</div>'
    )
    return field_settings_html


def build_sort_settings_panel_html(sorts, all_columns) -> str:
    """构建排序管理面板 HTML。"""
    sorts = sorts or []
    sort_settings_items = []
    for idx, (sc, sd) in enumerate(sorts):
        up_disabled = "disabled" if idx == 0 else ""
        down_disabled = "disabled" if idx == len(sorts) - 1 else ""
        icon = "↑" if sd == "asc" else "↓"
        sort_settings_items.append(
            f'<div class="sort-item" draggable="true" style="display:flex;align-items:center;gap:8px">'
            f'<span class="drag-handle" style="cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
            f'<span class="sort-num">{idx + 1}</span>'
            f'<span style="flex:1">{_escape(sc)} {icon}</span>'
            f'<input type="hidden" name="sort_col" value="{_escape(sc)}">'
            f'<input type="hidden" name="sort_dir" value="{_escape(sd)}">'
            f'<button type="button" class="sort-up" {up_disabled} onclick="moveSortItem(this,-1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▲</button>'
            f'<button type="button" class="sort-down" {down_disabled} onclick="moveSortItem(this,1)" '
            f'style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;'
            f'cursor:pointer;background:#fff;color:#475569">▼</button>'
            f'<button type="button" onclick="removeSortItem(this)" '
            f'style="padding:2px 6px;font-size:11px;border:none;border-radius:4px;'
            f'cursor:pointer;background:transparent;color:#dc2626">✕</button>'
            f'</div>'
        )
    col_options = "".join(f'<option value="{_escape(c)}">{_escape(c)}</option>' for c in all_columns)
    sort_settings_html = (
        '<div id="sortSettingsPanel" class="side-panel" role="dialog" '
        'aria-modal="true" aria-label="排序设置">'
        '<div class="panel-head"><h3>排序设置</h3>'
        '<button type="button" class="btn btn-sm btn-ghost" '
        'onclick="closePanel(\'sortSettingsPanel\')">收起</button></div>'
        '<div id="sortList" style="display:flex;flex-direction:column;gap:6px;'
        'max-height:40vh;overflow-y:auto;margin-bottom:8px">'
        + ("".join(sort_settings_items)
           if sort_settings_items else
           '<div class="sort-empty" style="text-align:center">暂无排序</div>') +
        '</div>'
        '<div style="display:flex;gap:8px;align-items:center;padding:8px;'
        'background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:8px">'
        '<select id="newSortCol" style="flex:1">'
        '<option value="">-- 添加排序字段 --</option>' + col_options + '</select>'
        '<select id="newSortDir">'
        '<option value="asc">↑ 升序</option><option value="desc">↓ 降序</option></select>'
        '<button type="button" onclick="addSortItem()" class="btn btn-primary btn-sm">添加</button>'
        '</div>'
        '<div style="display:flex;gap:8px;align-items:center">'
        '<button type="button" onclick="applySortSettings()" class="btn btn-primary btn-sm">应用</button>'
        '</div>'
        '</div>'
    )
    return sort_settings_html


def build_filter_form_html(form_id: str, form_hidden_str: str) -> str:
    """构建隐藏筛选表单 HTML。"""
    return f'<form id="{form_id}" method="get" action="/report" style="display:none">\n  {form_hidden_str}\n</form>'


def build_clear_filters_href(report_id, page_size, sorts, cols_param,
                             result_param, nested_filter=None) -> str:
    """构造「清除筛选」目标 URL：当前路径去掉 f_*/op_* 参数后的形态。

    批次5#19（spec ux-optimization）：筛选空态与筛选操作条共用，
    服务端单点构造，避免两处拼 URL 漂移。
    """
    sorts = sorts or []
    href = f"/report?id={report_id}&amp;page_size={page_size}"
    if sorts:
        href += "&amp;" + build_sort_params(sorts)
    if cols_param:
        href += "&amp;" + cols_param
    if result_param:
        href += "&amp;" + result_param
    if nested_filter:
        href += "&amp;" + build_nested_filter_param(nested_filter)
    return href


def build_filter_action_html(report_id, page_size, sorts, cols_param,
                            result_param, filters, nested_filter=None) -> tuple:
    """构建筛选操作按钮和清除筛选提示 HTML。"""
    sorts = sorts or []
    filters = filters or []
    clear_href = build_clear_filters_href(
        report_id, page_size, sorts, cols_param, result_param,
        nested_filter=nested_filter)

    filter_action_html = (f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
                         f'<button type="submit" form="ff" class="btn btn-primary btn-sm">筛选</button>'
                         f'<a href="{clear_href}" class="btn btn-outline btn-sm">清除筛选</a>'
                         + render_filter_help() +
                         f'</div>')

    clear_html = ""
    if filters:
        filter_items = []
        for c, o, v in filters:
            op_label = _OP_MAP.get(o, (o, o))[1]
            if o in ("isempty", "notempty"):
                filter_items.append(f'{_escape(c)} ({op_label})')
            else:
                filter_items.append(f'{_escape(c)} {op_label} "{_escape(v)}"')
        filter_summary = "、".join(filter_items)
        clear_html = (f'<div>'
                      f'筛选: {filter_summary} '
                      f'<a href="{clear_href}" class="clear-filter">✕ 全部清除</a></div>')

    return filter_action_html, clear_html


def build_report_switcher_html(reports_data, all_cats, cat_tree,
                                current_id=None) -> str:
    """构建报表切换下拉框 HTML（按分类层级树状呈现，纯 HTML 渲染，无 DB 调用）。"""
    cat_reports: dict[int, list] = {}
    uncategorized: list = []
    for r in reports_data:
        cid = r.get("category_id")
        if cid is not None:
            cat_reports.setdefault(cid, []).append(r)
        else:
            uncategorized.append(r)

    def _render_tree_switcher(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            if rpts or node.get("children", []):
                label = f"{indent}{node['name']}"
                html += f'<optgroup label="{_escape(label)}">'
                for r in rpts:
                    sel = ' selected' if r["id"] == current_id else ''
                    html += f'<option value="{r["id"]}"{sel}>{_escape(r["name"])}</option>'
                if node.get("children", []):
                    html += _render_tree_switcher(node["children"], depth + 1)
                html += "</optgroup>"
            else:
                html += f'<option value="" disabled>{indent}({_escape(node["name"])} - 无报表)</option>'
                if node.get("children", []):
                    html += _render_tree_switcher(node["children"], depth + 1)
        return html

    options = _render_tree_switcher(cat_tree)
    for r in uncategorized:
        sel = ' selected' if r["id"] == current_id else ''
        options += f'<option value="{r["id"]}"{sel}>(未分类) {_escape(r["name"])}</option>'

    return f"""<div class="card">
  <div class="report-select">
    <form method="get" action="/report">
      <label style="display:block">切换报表:</label>
       <select name="id" onchange="navigateTo(this.closest('form').action+'?'+new URLSearchParams(new FormData(this.closest('form'))).toString())">
         <option value="">-- 选择报表 --</option>
         {options}
       </select>
     </form>
   </div>
 </div>"""


# ===================================================================
# 配置页渲染函数（从 config.py 移入）
# ===================================================================


def _link_btn(url: str, label: str, cls: str = "btn btn-outline btn-sm",
              title: str = "") -> str:
    """生成链接按钮（title 可选：图标化按钮的无障碍提示）"""
    title_attr = f' title="{_escape(title)}"' if title else ""
    return f'<a href="{_escape(url)}" class="{cls}"{title_attr}>{_escape(label)}</a>'


def _report_delete_confirm(report: dict,
                           api_endpoints_map: dict = None) -> str:
    """报表删除确认文案（spec ux-optimization 批次2#5）。

    有关联 API 端点时披露一并删除的数量（级联在 db.delete_report 内完成）。
    """
    ep_count = len((api_endpoints_map or {}).get(report.get("id"), []))
    if ep_count > 0:
        return (f"确定删除报表 {_escape(report.get('name'))}？"
                f"其下 {ep_count} 个 API 接口将一并删除")
    return f"确定删除报表 {_escape(report.get('name'))}？"


def build_delete_form_html(action_url: str, confirm_msg: str,
                           extra_hidden: str = "",
                           button_cls: str = "",
                           indent: int = 4,
                           label: str = "删除",
                           btn_title: str = "") -> str:
    """构建删除确认表单 HTML（POST + confirm 确认 + 可选隐藏域）。

    参数:
        action_url: 表单提交地址
        confirm_msg: confirm() 提示文案（不含引号包裹）
        extra_hidden: 额外隐藏域 HTML，多行时按按钮行缩进统一缩进
        button_cls: 追加到按钮的额外 class（如迷你按钮尺寸 .btn-mini-s）
        indent: 表单开标签源码缩进空格数（与调用处对齐，保持输出逐字符一致）
        label: 按钮可见文本（默认「删除」；左树图标化时传 ✕）
        btn_title: 按钮 title 提示（空则不输出 title 属性；图标化时传无障碍文案）
    """
    pad = " " * indent
    btn_pad = " " * (indent + 2)
    hidden_html = ""
    if extra_hidden:
        hidden_html = "\n".join(f"{btn_pad}{ln}" for ln in extra_hidden.split("\n")) + "\n"
    title_attr = f' title="{_escape(btn_title)}"' if btn_title else ""
    return (
        f'{pad}<form method="post" action="{action_url}" style="display:inline"\n'
        f'{pad}      onsubmit="return confirm(\'{confirm_msg}\')">\n'
        f'{btn_pad}{hidden_html}'
        f'<button type="submit" class="btn btn-danger btn-sm{button_cls}"{title_attr}>{_escape(label)}</button>\n'
        f'{pad}</form>'
    )


def build_move_buttons_html(item_id: int, section: str, index: int, total: int) -> str:
    """
    生成上下移动按钮的 HTML。

    统一处理连接池/报表/分类列表中的上移/下移按钮。
    在三个地方使用：连接池列表、分类列表中的分类项、分类列表中的报表行。

    Args:
        item_id: 被移动项的数据库 ID。
        section: 配置段名称（pools / reports / categories），对应 URL 路径。
        index: 当前项在列表中的序号（从 0 开始）。
        total: 列表总项数。

    Returns:
        移动按钮的 HTML 字符串（空字符串表示无需显示按钮）。
    """
    if total <= 1:
        return ""
    html = ""
    if index > 0:
        html += (f'<form method="post" action="/config/{section}/{item_id}/move-up" style="display:inline">'
                 f'<button type="submit" class="btn btn-outline btn-sm" title="上移">↑</button></form> ')
    if index < total - 1:
        html += (f'<form method="post" action="/config/{section}/{item_id}/move-down" style="display:inline">'
                 f'<button type="submit" class="btn btn-outline btn-sm" title="下移">↓</button></form> ')
    return html


def build_pool_form_html(pool: dict = None, copy_mode: bool = False, is_edit: bool = None,
                         prefill_copy_suffix: bool = True) -> str:
    """渲染连接池编辑/新增/复制表单（纯数据 → HTML，无 DB 调用）

    is_edit: 显式指定编辑模式（None 时按 pool 是否非空 + copy_mode 判定）
    prefill_copy_suffix: 复制模式是否自动追加「 (副本)」后缀（保存失败回显时关闭）
    """
    if is_edit is None:
        is_edit = pool is not None and not copy_mode
    is_copy = pool is not None and copy_mode
    if is_edit:
        action_url = f"/config/pools/{pool['id']}/edit"
        title = "编辑连接池"
    elif is_copy:
        action_url = f"/config/pools/{pool['id']}/copy"
        title = "复制连接池"
    else:
        action_url = "/config/pools/add"
        title = "新增连接池"

    name = _escape(pool["name"] if pool else "")
    host = _escape(pool["host"] if pool else "")
    port = str(pool["port"]) if pool else "3306"
    user = _escape(pool["user"] if pool else "")
    # 批次3#12（spec ux-optimization）：编辑态不回显已存密码——
    # value 恒为空 + 非必填，留空提交时沿用库中旧密码（handle_pool_edit 语义）。
    password = ""
    database = _escape(pool["database"] if pool else "")
    pw_required = "" if is_edit else "required"
    pw_hint = (' <span>'
               '留空则沿用当前密码</span>') if is_edit else ""

    if is_copy:
        if prefill_copy_suffix:
            # 复制时自动加后缀，允许用户改名
            name = _escape(pool["name"] + " (副本)")
        # 复制模式同样不回显密码：留空则需重新输入

    form_html = f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form">
  <input type="hidden" name="pool_id" value="{_escape(pool['id']) if pool and pool.get('id') else ''}">
  <label>名称: <input type="text" name="name" value="{name}" required></label>
  <label>主机地址: <input type="text" name="host" value="{host}" placeholder="例如 127.0.0.1" required></label>
  <label>端口: <input type="number" name="port" value="{port}" required></label>
  <label>用户名: <input type="text" name="user" value="{user}" required></label>
  <label>密码: <input type="password" name="password" value="" {pw_required}>{pw_hint}</label>
  <label>数据库: <input type="text" name="database" value="{database}" required></label>
  <div class="form-actions span-full">
    <button type="submit" class="btn btn-primary">保存</button>
    <button type="button" class="btn btn-outline" data-test-conn
            formnovalidate title="用当前表单填写的连接信息试连数据库（不保存）"
            onclick="testPoolConnection(this.form)">测试连接</button>
    <span id="pool-test-result" class="test-result"></span>
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
</div>"""
    # 「测试连接」脚本独立于 f-string：内含 JS 大括号，不能进入 f-string 字面量，
    # 否则会被当作格式占位符解析而语法报错。脚本仅绑定 data-test-conn 按钮，
    # 经 fetch 提交且返回 JSON，不刷新页面、保留表单已填内容。
    test_script = """
<script>
function testPoolConnection(form) {
  var btn = form.querySelector('button[data-test-conn]');
  var result = document.getElementById('pool-test-result');
  if (!form || !btn) return;
  btn.disabled = true;
  var old = btn.textContent;
  btn.textContent = '测试中...';
  if (result) { result.textContent = ''; result.className = 'test-result'; }
  var fd = new URLSearchParams(new FormData(form));
  fd.set('test_ajax', '1');
  fetch('/config/pools/test', { method: 'POST', body: fd })
    .then(function(r) {
      return r.json().catch(function() {
        return { ok: false, flash: '响应解析失败（HTTP ' + r.status + '）' };
      });
    })
    .then(function(data) {
      if (result) {
        var msg = (data && data.flash) || '未知错误';
        result.textContent = msg;
        result.className = 'test-result ' + ((data && data.ok) ? 'ok' : 'err');
      }
    })
    .catch(function(e) {
      if (result) { result.textContent = '请求失败: ' + e; result.className = 'test-result err'; }
    })
    .finally(function() {
      btn.disabled = false;
      btn.textContent = old;
    });
}
</script>"""
    return form_html + test_script


def build_user_form_html(user: dict = None, is_edit: bool = None) -> str:
    """渲染用户编辑/新增表单（纯数据 → HTML，无 DB 调用）

    is_edit: 显式指定编辑模式（None 时按 user 是否非空判定）
    """
    if is_edit is None:
        is_edit = user is not None
    action_url = f"/config/users/{user['id']}/edit" if is_edit else "/config/users/add"
    title = "编辑用户" if is_edit else "新增用户"
    username = _escape(user["username"] if is_edit else "")
    pw_required = "" if is_edit else "required"
    pw_hint = ' <span>留空则不修改密码</span>' if is_edit else ""
    return f"""<div class="card">
<h2>{title}</h2>
<form method="post" action="{action_url}" class="config-form">
  <label>用户名: <input type="text" name="username" value="{username}" required></label>
  <label>密码: <input type="password" name="password" value="" {pw_required}>{pw_hint}</label>
  <div class="form-actions span-full">
    <button type="submit" class="btn btn-primary">保存</button>
    <a href="/config" class="cancel">取消</a>
  </div>
</form>
</div>"""


def build_category_opts_html(nodes, depth, cur_cat_id):
    """递归生成分类选项 HTML（树形缩进）（纯数据 → HTML，无 DB 调用）"""
    html = ""
    for node in nodes:
        indent = "　" * depth
        sel = ' selected' if cur_cat_id != "" and str(node["id"]) == str(cur_cat_id) else ''
        html += f'<option value="{node["id"]}"{sel}>{indent}{_escape(node["name"])}</option>'
        if node["children"]:
            html += build_category_opts_html(node["children"], depth + 1, cur_cat_id)
    return html


def _get_cat_depth(cat: dict, all_cats: list[dict]) -> int:
    """计算分类的层级深度（用于缩进显示）。"""
    depth = 0
    seen = set()
    pid = cat.get("parent_id")
    while pid is not None:
        if pid in seen:
            break
        seen.add(pid)
        depth += 1
        parent = next((c for c in all_cats if c["id"] == pid), None)
        if parent:
            pid = parent.get("parent_id")
        else:
            break
    return depth


def build_pool_section_html(pools: list, report_counts: dict = None,
                            pool_reports: dict = None) -> str:
    """渲染连接池配置列表（含复制、排序）（纯数据 → HTML，无 DB 调用）

    report_counts: {pool_id: 关联报表数}（spec ux-optimization 批次2#6）；
    提供时删除确认弹窗披露断连破坏半径。
    pool_reports: {pool_id: [{id, name}, ...]}（R2 P9 关联报表列）；
    提供时渲染第 6 列报表名链接，缺省显示计数或「—」。
    """
    rows = ""
    pool_count = len(pools)
    for i, p in enumerate(pools):
        move_btns = build_move_buttons_html(p["id"], "pools", i, pool_count)
        ref_count = (report_counts or {}).get(p["id"], 0)
        if ref_count > 0:
            pool_confirm = (f"确定删除连接池 {_escape(p['name'])}？"
                            f"其下 {ref_count} 个报表将失去数据库连接"
                            f"（报表保留但无法执行）")
        else:
            pool_confirm = f"确定删除连接池 {_escape(p['name'])}？"
        linked = (pool_reports or {}).get(p["id"]) or []
        if linked:
            linked_cell = "、".join(
                f'<a href="/report?id={int(r["id"])}" target="_blank" '
                f'rel="noopener">'
                f'{_escape(r["name"])}</a>'
                for r in linked)
        elif ref_count > 0:
            linked_cell = f"{ref_count} 个"
        else:
            linked_cell = '<span>—</span>'
        rows += f"""<tr id="pool-{p['id']}">
  <td><strong>{_escape(p['name'])}</strong></td>
  <td><span class="badge badge-pool">{_escape(p['host'])}:{p['port']}</span></td>
  <td>{_escape(p['user'])}</td>
  <td>{_escape(p['database'])}</td>
  <td>{linked_cell}</td>
  <td class="ops-cell">
    {move_btns}
    {_link_btn(f"/config/pools/{p['id']}/edit", "编辑")}
    {_link_btn(f"/config/pools/{p['id']}/copy", "复制")}
    {build_delete_form_html(f"/config/pools/{p['id']}/delete", pool_confirm)}
  </td>
</tr>"""
    return f"""<div class="section" id="sec-pools">
<div class="section-title">
  <span>📦 连接池配置</span>
  <span class="actions">{_link_btn("/config/pools/add", "新增连接池", "btn btn-primary btn-sm")}</span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th>名称</th><th>地址</th><th>用户</th><th>数据库</th><th>关联报表</th><th>操作</th>
</tr></thead><tbody>
{rows or build_empty_row_html(6, "暂无连接池配置")}
</tbody></table>
</div>
</div>"""


def build_user_section_html(users: list, current_username: str = None) -> str:
    """渲染用户配置列表（纯数据 → HTML，无 DB 调用）

    current_username: 当前登录用户名（spec ux-optimization 批次2#7）；
    其所在行不渲染删除按钮——删除自己会立即失效自己的会话，
    服务端同样兜底拒绝（config.handle_user_delete）。

    R2 P10：三列对齐原型 page-users（用户名｜角色说明｜操作）。
    users 表无 role 字段（仅 id/username/password_hash），全部登录用户
    权限相同，角色说明列按此实际语义渲染，不虚构只读角色。
    """
    rows = ""
    for u in users:
        is_current = bool(current_username) and u["username"] == current_username
        if is_current:
            delete_btn = '<span title="不能删除当前登录账号">—</span>'
        else:
            delete_btn = build_delete_form_html(
                f"/config/users/{u['id']}/delete",
                f"确定删除用户 {_escape(u['username'])}？"
                f"其全部登录会话将立即失效")
        name_cell = f"<strong>{_escape(u['username'])}</strong>"
        if is_current:
            name_cell += ' <span class="badge badge-info">当前登录</span>'
        role_cell = "管理员 · 全部配置与报表可管理"
        if is_current:
            role_cell += "；禁止删除当前登录用户"
        rows += f"""<tr id="user-{u['id']}">
  <td>{name_cell}</td>
  <td class="muted">{role_cell}</td>
  <td class="ops-cell">
    {_link_btn(f"/config/users/{u['id']}/edit", "编辑")}
    {delete_btn}
  </td>
</tr>"""
    return f"""<div class="section" id="sec-users">
<div class="section-title">
  <span>👤 用户配置</span>
  <span class="actions">{_link_btn("/config/users/add", "新增用户", "btn btn-primary btn-sm")}</span>
</div>
<div class="table-wrap">
<table><thead><tr>
  <th>用户名</th><th>角色说明</th><th>操作</th>
</tr></thead><tbody>
{rows or build_empty_row_html(3, "暂无用户")}
</tbody></table>
</div>
<p class="muted">
约定保持：改用户名/密码后强制下线该用户全部会话；flash 不回显明文密码。</p>
</div>"""


def build_category_manage_section_html(all_cats, cat_tree,
                                       show_report_add: bool = True,
                                       report_counts: dict = None,
                                       total_reports: int = None) -> str:
    """渲染分类管理区块（分类树 + 排序 + CRUD，纯数据 → HTML，无 DB 调用）

    ui-redesign R2-A：左树按已确认原型改为 flex 行——图标 + 名称 + 报表数角标 +
    ghost 操作（✎↑↓✕，悬停提亮）；子分类包 .kids 容器逐级缩进，行点击折叠/展开
    （toggleCatNode）；不再使用 ├─ 文本引导线。
    config-reports-merge：区块整体可折叠
    （localStorage 记忆折叠状态，标题栏按钮折叠时仍可见）。
    确认稿 r3：树顶渲染「全部报表 N」静态高亮首行（total_reports=全量报表数，
    None 时不渲染，向后兼容）；左树头部收敛为「折叠标题 + 仅新增分类」单行形态
    （新增报表入口保留在页头与未分类区，show_report_add 参数保留仅作签名兼容）。
    """
    counts = report_counts or {}

    def _render_cat_item(cat, has_children):
        siblings = [c for c in all_cats if c.get("parent_id") == cat.get("parent_id")]
        idx = next((i for i, c in enumerate(siblings) if c["id"] == cat["id"]), -1)
        n = len(siblings)
        move_btns = build_move_buttons_html(cat["id"], "categories", idx, n)
        count = counts.get(cat["id"])
        count_html = f'<span class="cnt">{count}</span>' if count else ""
        kids_attr = (f' data-kids="cat-kids-{cat["id"]}"'
                     f' onclick="toggleCatNode(event,this)"' if has_children else "")
        name = _escape(cat["name"])
        edit_btn = _link_btn(f"/config/categories/{cat['id']}/edit", "✎",
                             "btn btn-ghost btn-sm btn-icon", title="编辑")
        del_btn = build_delete_form_html(
            f"/config/categories/{cat['id']}/delete",
            f"确定删除分类 {name}？分类下的报表和子分类将变为未分类。",
            indent=2, label="✕", btn_title="删除")
        return f"""<div class="cat"{kids_attr}>
  <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
  <span class="nm" title="{name}">{name}</span>
  <span class="ops">
    {move_btns}{edit_btn}{del_btn}
  </span>
  {count_html}
</div>"""

    def _render_tree(nodes):
        html = ""
        for node in nodes:
            children = node.get("children") or []
            html += _render_cat_item(node, bool(children))
            if children:
                html += (f'<div class="kids on" id="cat-kids-{node["id"]}">'
                         f'{_render_tree(children)}</div>')
        return html

    cat_list_html = _render_tree(cat_tree)

    if not cat_list_html:
        cat_list_html = '<div>暂无分类</div>'

    report_add_btn = (_link_btn("/config/reports/add", "新增报表", "btn btn-ghost btn-sm")
                      if show_report_add else "")
    # 确认稿 r3：树顶「全部报表 N」静态高亮首行（列表 SVG 图标，沿用 R2-A 图标体系）
    all_row = ""
    if total_reports is not None:
        all_row = ('<div class="cat active" aria-current="true">'
                   '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   'stroke-width="1.5" aria-hidden="true">'
                   '<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/>'
                   '<line x1="4" y1="17" x2="20" y2="17"/></svg>'
                   f'<span class="nm">全部报表</span><span class="cnt">{total_reports}</span></div>')
    return f"""<div class="section" id="sec-categories">
<div class="section-title">
  <button type="button" id="cat-tree-toggle" class="btn btn-ghost btn-sm tree-toggle"
          onclick="toggleCatTree(this)">▼ 报表分类</button>
  <span class="actions">
    {_link_btn("/config/categories/add", "新增分类", "btn btn-ghost btn-sm")}
  </span>
</div>
<div id="cat-tree-content">
<div class="tree" role="tree">
  {all_row}
  {cat_list_html}
</div>
</div>
</div>"""


def build_category_section_html(cat_reports, unclassified_reports, all_cats,
                                 all_reports, pools, cat_tree,
                                 api_endpoints_map: dict[int, list[dict]] = None,
                                 schedules_map: dict[int, dict] = None,
                                 split_parts: bool = False):
    """渲染报表分类配置段（分类管理 + 各分类下的报表列表，纯数据 → HTML，无 DB 调用）

    参数:
        api_endpoints_map: { report_id: [api_endpoint_dict, ...] }，可选。
        schedules_map: { report_id: schedule_dict }，可选；提供时在报表名
                       后渲染 {_icon("calendar")} 定时徽标（保活徽标取报表行 keepalive 列）。
    """
    pools_map: dict = {p["id"]: p for p in pools}

    # 批量操作：连接池选择 + 分类选择
    pool_opts = '<option value="">-- 请选择 --</option>'
    for p in pools:
        pool_opts += f'<option value="{p["id"]}">{_escape(p["name"])}</option>'
    cat_opts = '<option value="">-- 请选择分类 --</option>'
    for c in all_cats:
        prefix = "　" * _get_cat_depth(c, all_cats)
        cat_opts += f'<option value="{c["id"]}">{prefix}{_escape(c["name"])}</option>'
    cat_opts += '<option value="-1">无分类</option>'
    # 批次5#17（spec ux-optimization）：批量操作条从「未分类区块内联」改为
    # 页面级单实例 sticky 底部浮动条——跨分类勾选后操作条可达；初始隐藏，
    # 由 updateBatchCount 按选中数切换显隐；端点 action 保持不变。
    batch_bar = f"""
<div class="batch-bar batch-float" id="batch-bar" style="display:none;position:sticky;bottom:0;align-items:center;gap:12px;flex-wrap:wrap;z-index:50">
  <span>
    已选 <span id="batch_count">0</span> 项
  </span>
  <select id="batch_pool_id">
    {pool_opts}
  </select>
  <button type="button" class="btn btn-primary btn-sm"
    onclick="batchUpdatePool()">批量修改连接池</button>
  <select id="batch_cat_id">
    {cat_opts}
  </select>
   <button type="button" class="btn btn-success btn-sm"
    onclick="batchSetCategory()">批量设置分类</button>
   <select id="batch_cache_switch">
     <option value="">不改变</option>
     <option value="1">启用缓存</option>
     <option value="0">关闭缓存</option>
   </select>
   <input type="checkbox" id="batch_modify_ttl" onchange="toggleTtlInput()">
   <label for="batch_modify_ttl">修改TTL</label>
   <input type="number" id="batch_cache_ttl" value="0" min="0" step="1"
     disabled>
   <span>小时（0=永久）</span>
   <button type="button" class="btn btn-info btn-sm"
     onclick="batchUpdateCache()">批量更新缓存配置</button>
   <button type="button" class="btn btn-danger btn-sm"
     onclick="batchDeleteReports()">批量删除报表</button>
</div>
<script>
/* 确认稿 r3：列表/卡片双形态共享勾选——按 value 去重收集 id */
function pickedReportIds() {{
  var boxes = document.querySelectorAll('.report-checkbox:checked');
  var seen = {{}}, ids = [];
  for (var i = 0; i < boxes.length; i++) {{
    var v = boxes[i].value;
    if (!seen[v]) {{ seen[v] = 1; ids.push(v); }}
  }}
  return ids;
}}
function batchUpdatePool() {{
  var ids = pickedReportIds();
  if (ids.length === 0) {{ showFlashWarn('请至少选择一项'); return; }}
  var poolId = document.getElementById('batch_pool_id').value;
  if (!poolId) {{ showFlashWarn('请选择目标连接池'); return; }}
  submitBatchPost('/config/reports/batch-pool', ids, [{{name: 'pool_id', value: poolId}}]);
}}
function batchSetCategory() {{
  var ids = pickedReportIds();
  if (ids.length === 0) {{ showFlashWarn('请至少选择一项'); return; }}
  var catId = document.getElementById('batch_cat_id').value;
  if (!catId) {{ showFlashWarn('请选择目标分类'); return; }}
  submitBatchPost('/config/reports/batch-set-category', ids, [{{name: 'category_id', value: catId === '-1' ? '' : catId}}]);
}}
function toggleTtlInput() {{
  var cb = document.getElementById('batch_modify_ttl');
  var inp = document.getElementById('batch_cache_ttl');
  inp.disabled = !cb.checked;
  inp.style.opacity = cb.checked ? '1' : '0.5';
}}
function batchUpdateCache() {{
  var ids = pickedReportIds();
  if (ids.length === 0) {{ showFlashWarn('请至少选择一项'); return; }}
  var cacheSwitch = document.getElementById('batch_cache_switch').value;
  var modifyTtl = document.getElementById('batch_modify_ttl').checked;
  if (cacheSwitch === '' && !modifyTtl) {{
    showFlashWarn('请选择缓存开关或勾选修改TTL');
    return;
  }}
  if (!confirm(`确定批量更新 ${{ids.length}} 个报表的缓存配置？`)) return;
  var extra = [{{name: 'cache_switch', value: cacheSwitch}}];
  if (modifyTtl) {{
    extra.push({{name: 'modify_ttl', value: '1'}});
    extra.push({{name: 'cache_ttl_hours', value: document.getElementById('batch_cache_ttl').value}});
  }}
  submitBatchPost('/config/reports/batch-cache', ids, extra);
}}
function batchDeleteReports() {{
  var ids = pickedReportIds();
  if (ids.length === 0) {{ showFlashWarn('请至少选择一项'); return; }}
  if (!confirm(`确定批量删除 ${{ids.length}} 个报表？该操作不可撤销`)) return;
  submitBatchPost('/config/reports/batch-delete', ids, []);
}}
function updateBatchCount() {{
  /* 双形态同一报表各有一份勾选框：只把可见形态当选择源，
     再把选择镜像到全部副本，保证切换视图后勾选不丢、计数不翻倍 */
  var boxes = document.querySelectorAll('.report-checkbox');
  var sel = window.__rptSel = window.__rptSel || {{}};
  var i, b;
  for (i = 0; i < boxes.length; i++) {{
    b = boxes[i];
    if (b.offsetParent === null) continue;
    if (b.checked) sel[b.value] = 1; else delete sel[b.value];
  }}
  var n = 0;
  for (var k in sel) {{ if (Object.prototype.hasOwnProperty.call(sel, k)) n++; }}
  for (i = 0; i < boxes.length; i++) {{
    boxes[i].checked = !!sel[boxes[i].value];
  }}
  document.getElementById('batch_count').textContent = n;
  var bar = document.getElementById('batch-bar');
  if (bar) bar.style.display = n > 0 ? 'flex' : 'none';
}}
/* 确认稿 r3：「列表/卡片」全局开关——作用于全部层级分组（.view-list/.view-card），
   默认列表、localStorage 记忆；层级仅靠分组头缩进与左侧层级线表达 */
function setReportsView(v, save) {{
  var lists = document.querySelectorAll('.view-list');
  var cards = document.querySelectorAll('.view-card');
  var i;
  for (i = 0; i < lists.length; i++) lists[i].classList.toggle('hidden', v !== 'list');
  for (i = 0; i < cards.length; i++) cards[i].classList.toggle('hidden', v !== 'card');
  var btns = document.querySelectorAll('#rpt-view-seg button[data-view]');
  for (i = 0; i < btns.length; i++) {{
    btns[i].classList.toggle('active', btns[i].getAttribute('data-view') === v);
  }}
  if (save) {{
    try {{ localStorage.setItem('sqlreport_reports_view', v); }} catch (e) {{}}
  }}
  updateBatchCount();
}}
(function () {{
  var v = null;
  try {{ v = localStorage.getItem('sqlreport_reports_view'); }} catch (e) {{}}
  setReportsView(v === 'card' ? 'card' : 'list', false);
}})();
</script>"""

    def _render_report_rows(report_list, in_category=False):
        """渲染报表列表行 + 卡片（确认稿 r3：一次数据准备，输出两形态）

        返回 (rows_html, cards_html)——rows 给 .view-list 表格、cards 给
        .view-card 卡片网格；两形态同受页头「列表/卡片」全局开关控制。
        """
        rows = ""
        cards = ""
        total = len(report_list)
        for idx, r in enumerate(report_list):
            rpt_id = r["id"]
            pool_name = ""
            pool_id = r["pool_id"]
            if pool_id is not None:
                pool = pools_map.get(pool_id)
                if pool:
                    pool_name = pool["name"]
            # 确认稿 r3 反馈②：连接池由圆角胶囊 badge 改单行 chip（6px 圆角 +
            # 状态点 + 截断 + title 全名），长池名不再包成圆饼
            if pool_name:
                pool_cell = (f'<span class="pool-chip" title="{_escape(pool_name)}">'
                             f'<span class="dot"></span><span class="txt">{_escape(pool_name)}</span></span>')
            else:
                pool_cell = ('<span class="pool-chip gone" title="连接池已删除">'
                             '<span class="dot"></span><span class="txt">连接池已删除</span></span>')
            move_btns = build_move_buttons_html(rpt_id, "reports", idx, total)
            memo_raw = r.get("memo") or ""
            if memo_raw:
                memo_display = _escape(memo_raw[:15])
                if len(memo_raw) > 15:
                    memo_display += "..."
                # 批次6#27h：截断展示补 title 全文，悬浮可读完整备注
                memo_title_attr = f' title="{_escape(memo_raw)}"'
                memo_plain = memo_display
            else:
                memo_display = '<span>—</span>'
                memo_title_attr = ""
                memo_plain = "—"

            prefer_cache = int(r.get("prefer_cache", 1))
            prefer_cache_display = (
                build_state_span("是")
                if prefer_cache
                else build_state_span("否", "muted", bold=False)
            )
            cache_ttl_hours = int(r.get("cache_ttl_hours", 0))
            cache_ttl_display = f'{cache_ttl_hours}h' if cache_ttl_hours else '<span>—</span>'
            # 卡片徽标用纯文本（避免 0 TTL 时嵌入 span）
            if not prefer_cache:
                card_cache_badge = '<span class="badge badge-neutral">不缓存</span>'
            elif cache_ttl_hours:
                card_cache_badge = f'<span class="badge badge-ok">缓存 {cache_ttl_hours}h</span>'
            else:
                card_cache_badge = '<span class="badge badge-ok">缓存 永久</span>'

            # API 接口列
            eps = (api_endpoints_map or {}).get(rpt_id, [])
            if eps:
                total_cnt = len(eps)
                enabled_cnt = sum(1 for ep in eps if int(ep.get("enabled", 1)))
                disabled_cnt = total_cnt - enabled_cnt
                parts = []
                if enabled_cnt:
                    parts.append(f'{enabled_cnt}启用')
                if disabled_cnt:
                    parts.append(f'{disabled_cnt}禁用')
                summary = f'{total_cnt} 个接口 ({" / ".join(parts)})' if parts else f'{total_cnt} 个接口'
                tooltip_lines = []
                for ep in eps:
                    ep_name = ep.get("name", "")
                    ep_path = ep.get("url_path", "")
                    ep_format = ep.get("output_format", "json")
                    ep_enabled = int(ep.get("enabled", 1))
                    ep_status = "启用" if ep_enabled else "禁用"
                    ep_key = "有 Key" if ep.get("api_key") else "无 Key"
                    tooltip_lines.append(f"  [{ep_status}] {ep_name} ({ep_path}) - {ep_format}, {ep_key}")
                tooltip = "\\n".join(tooltip_lines)
                api_cell = f'<a href="/config/reports/{rpt_id}/edit#api-endpoints" title="{_escape(tooltip)}">🔌 {summary}</a>'
                api_plain = f'🔌 {summary}'
            else:
                api_cell = '<span>—</span>'
                api_plain = "—"

            # 确认稿 r3 反馈①：SQL 摘要窄列单行截断，完整 SQL 悬浮 title 预览
            sql_full = _escape(r["sql_query"])
            sql_short = _escape(r["sql_query"][:80]) + ("..." if len(r["sql_query"]) > 80 else "")
            # 操作列图标化（确认稿 r3）：✎ 编辑 / ⧉ 复制 / 🗑 删除，title 无障碍提示
            ops_html = (f"""{move_btns}
    {_link_btn(f"/config/reports/{rpt_id}/edit", "✎", "btn btn-outline btn-sm btn-icon", title="编辑")}
    {_link_btn(f"/config/reports/{rpt_id}/copy", "⧉", "btn btn-outline btn-sm btn-icon", title="复制")}
    {build_delete_form_html(f"/config/reports/{rpt_id}/delete", _report_delete_confirm(r, api_endpoints_map), button_cls=" btn-icon", label="🗑", btn_title="删除报表")}""")
            sched_badge = build_schedule_flags_badge_html(
                (schedules_map or {}).get(rpt_id, {}).get('enabled'), r.get('keepalive_enabled'))

            # UI v2 方案 A：10 列表格 → 行卡片（名称 / 状态 chip / 配置 chips / 连接池 / 接口 / 备注 / SQL）
            # 原 10 列在 1440 视口右栏（856px）内必然挤压（名称列曾被压成一字一行）
            rows += f"""<div class="rpt-row" id="report-{rpt_id}">
  <label class="pick"><input type="checkbox" class="report-checkbox" value="{rpt_id}" onchange="updateBatchCount()"></label>
  <div class="rpt-main">
    <div class="rpt-line1">
      <a class="nm" href="/report?id={rpt_id}" target="_blank" rel="noopener">{_escape(r['name'])}</a>{sched_badge}
    </div>
    <div class="rpt-meta">
      <span class="cfg-chip">分页 <b>{r['default_page_size']}</b></span>
      <span class="cfg-chip{' ok' if prefer_cache else ''}">{'缓存 ' + (str(cache_ttl_hours) + 'h' if cache_ttl_hours else '永久') if prefer_cache else '不缓存'}</span>
      {pool_cell}
      <span class="cfg-chip">{api_plain}</span>
    </div>
    <div class="rpt-memo"{memo_title_attr}>{memo_display}</div>
    <div class="rpt-sql" title="{sql_full}">{sql_short}</div>
  </div>
  <div class="rpt-ops">{ops_html}</div>
</div>"""

            cards += f"""<div class="rpt-card" id="report-card-{rpt_id}">
  <input type="checkbox" class="report-checkbox rc-pick" value="{rpt_id}" onchange="updateBatchCount()" title="勾选以批量操作">
  <div class="rc-top"><span class="rc-name"><a href="/report?id={rpt_id}" target="_blank" rel="noopener">{_escape(r['name'])}</a>{sched_badge}</span></div>
  <div class="rc-sql" title="{sql_full}">{sql_short}</div>
  <div class="rc-meta">{pool_cell}
    {card_cache_badge}
    <span class="badge badge-info">分页 {r['default_page_size']}</span>
  </div>
  <div class="rc-memo"{memo_title_attr}>备注：{memo_plain}</div>
  <div class="rc-foot">
    <span class="rc-ops">{ops_html}</span>
    <a class="rc-api" href="/config/reports/{rpt_id}/edit#api-endpoints" title="{_escape(r['name'])} 的 API 接口">{api_plain}</a>
  </div>
</div>"""
        return rows, cards

    cat_areas = build_category_manage_section_html(
        all_cats, cat_tree, show_report_add=True,
        report_counts={e["id"]: len(e.get("reports") or []) for e in cat_reports},
        total_reports=len(all_reports or []))

    report_lookup: dict[int, list] = {entry["id"]: entry.get("reports", []) for entry in cat_reports}
    tab_html = ""

    def _render_report_sections(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            reports = report_lookup.get(node["id"], [])
            has_children = bool(node["children"])
            if not reports and not has_children:
                continue
            inner = ""
            if reports:
                rows, cards = _render_report_rows(reports, in_category=True)
                # UI v2 方案 A：列表=行卡片（.view-list）、卡片=网格（.view-card），同受页头开关控制
                inner += f"""<div class="cat-body view-list">
{rows}
</div>
<div class="rpt-grid cat-cards view-card hidden">
{cards}
</div>"""
            if has_children:
                # 层级导轨：子级容器负责缩进 + 竖线 + 节点横线，不再用内联 margin/border
                inner += f'<div class="cat-children">{_render_report_sections(node["children"], depth + 1)}</div>'
            icon = _icon("folder") if has_children else _icon("chart")
            html += f"""<section class="section cat-block cat-depth-{min(depth + 1, 3)}">
  <div class="cat-head">
    <button type="button" class="tree-toggle" onclick="toggleCatBlock(this)" title="折叠/展开"><span class="chev">▼</span></button>
    <span class="cat-depth-dot"></span>
    <span class="cat-name"><span class="ico">{icon}</span>{_escape(node['name'])}</span>
    <span class="badge badge-neutral">{len(reports)} 个报表</span>
    <label class="pick-all" title="全选本分类"><input type="checkbox" onchange="selectAllInSection(this)"></label>
    <span class="actions">{_link_btn(f"/config/categories/{node['id']}/edit", "编辑分类", "btn-mini") if depth == 0 else ""}</span>
  </div>
{inner}
</section>"""
        return html
        return html

    tab_html = _render_report_sections(cat_tree)
    uncat_rows, uncat_cards = _render_report_rows(unclassified_reports)
    # 批次5#17：未分类区块不再内联批量操作条（页面级单实例移至列表容器之后）
    uncat_section = f"""<section class="section cat-block cat-depth-1">
  <div class="cat-head">
    <button type="button" class="tree-toggle" onclick="toggleCatBlock(this)" title="折叠/展开"><span class="chev">▼</span></button>
    <span class="cat-depth-dot"></span>
    <span class="cat-name"><span class="ico">{_icon("list")}</span>未分类报表</span>
    <span class="badge badge-neutral">{len(unclassified_reports)} 个报表</span>
    <label class="pick-all" title="全选本分类"><input type="checkbox" onchange="selectAllInSection(this)"></label>
    <span class="actions">{_link_btn("/config/reports/add", "新增报表", "btn-mini")}</span>
  </div>
<div class="cat-body view-list">
{uncat_rows or '<div class="cat-empty"><span>暂无未分类报表</span><a class="add" href="/config/reports/add">+ 新增报表</a></div>'}
</div>
<div class="rpt-grid cat-cards view-card hidden">
{uncat_cards or '<div class="empty-state">暂无未分类报表</div>'}
</div>
</section>"""

    # 批次5#17：浮动操作条渲染一次，置于全部列表区块之后（footer 之前）
    if split_parts:
        # ui-redesign T7.6：左树（分类管理）/ 右表（分组报表+批量条）拆分
        return cat_areas, tab_html + uncat_section + batch_bar
    return cat_areas + tab_html + uncat_section + batch_bar


# ===================================================================
# API 端点管理渲染函数
# ===================================================================


def build_api_endpoints_list_html(api_endpoints: list[dict],
                                   report_id: int = None,
                                   show_report_name: bool = False,
                                   base_url: str = "",
                                   key_counts: dict = None,
                                   return_to: str = None,
                                   desc_full: bool = False,
                                   wrap_section: bool = True) -> str:
    """
    渲染 API 接口列表区块（R2-D：api-main 主行 + api-more 展开区行卡片）。

    参数:
        api_endpoints: API 端点列表
        report_id: 关联报表 ID（为 None 时表示独立管理页，不带区块标题/新增按钮，
                   标题与新建入口由页面 page-head 承担）
        show_report_name: 是否显示关联报表名称列（独立管理页使用）
        base_url: 服务器基础 URL（如 http://localhost:8080），仅作服务端兜底
                  渲染值；页面加载后 JS 用 window.location.origin 覆盖
                  （与 API 配置后台/报表查看页一致，显示用户实际访问的地址）
        key_counts: {endpoint_id: key 数量} 映射（多 key 化后列表显示数量徽标；
                    None 时回退旧 api_key 列掩码+复制逻辑）
        return_to: toggle 后回跳地址（详情页签传 /report?id=N）；
                   None 时按 report_id / 独立管理页推导
        desc_full: 展开区说明用 Markdown 全文折叠区（详情页签，原型 md-body），
                   False=截断摘要 + title 全文（列表页）
        wrap_section: False=不包 .section 外壳与信息分级 help（详情页签由自己的
                      card 提供标题）；True=区块外壳（页面/报表编辑页列表用）
    """
    _sc_cfg = static_cache.get_static_cache_config()
    _sc_enabled = _sc_cfg.get("enable", True)
    rows = ""
    for ep in api_endpoints:
        ep_id = ep["id"]
        ep_name_raw = ep.get("name", "")
        ep_name = _escape(ep_name_raw)
        ep_path_raw = ep.get("url_path", "")
        ep_path = _escape(ep_path_raw)
        ep_format = _escape(ep.get("output_format", "json"))
        enabled = int(ep.get("enabled", 1))
        enabled_badge = ('<span class="badge badge-ok">启用</span>' if enabled
                         else '<span class="badge badge-warn">禁用</span>')
        ep_result_mode = ep.get("result_mode", "single")
        ep_result_index = int(ep.get("result_index", 0))
        if ep_result_mode == "all":
            mode_display = '<span>全部</span>'
        else:
            mode_display = f'<span>结果 {ep_result_index}</span>'
        allow_fetch_all = int(ep.get("allow_fetch_all", 1))
        fetch_all_display = (build_state_span("允许")
                             if allow_fetch_all else
                             build_state_span("禁止", "warn"))
        static_cache_on = int(ep.get("static_cache", 1))
        static_cache_display = (build_state_span("开")
                                if static_cache_on else
                                build_state_span("关", "muted"))
        # 主行名称：点击进入该接口的配置页（新开窗）
        ep_edit_url = _api_endpoint_url(ep['report_id'], ep_id)
        name_html = (f'<a class="name" href="{ep_edit_url}" target="_blank" rel="noopener" '
                     f'title="打开接口配置">'
                     f'{ep_name}</a>')
        # 主行关联报表（独立管理页）
        report_html = ""
        if show_report_name:
            rname = _escape(ep.get("report_name", ""))
            rpt_id = int(ep.get("report_id", 0) or 0)
            if rpt_id:
                report_html = (f'<span class="muted">报表：'
                               f'<a href="/report?id={rpt_id}" '
                               f'target="_blank" rel="noopener" '
                               f'title="打开报表查看页" '
                               f'>'
                               f'{rname}</a></span>')
            else:
                report_html = (f'<span class="muted">'
                               f'报表：{rname}</span>')
        # 展开区：三种调用地址（完整/全量/静态），置灰能力未开启的行
        full_disabled = not allow_fetch_all
        full_hint = "未开启「允许全量获取」，请在接口配置中开启" if full_disabled else ""
        if static_cache_on:
            static_disabled = not _sc_enabled
            static_hint = ("全局静态缓存已关闭（app_config.json 的 static_cache.enable）"
                           if static_disabled else "")
        else:
            static_disabled = True
            static_hint = "未开启「静态缓存」，请在接口配置中开启"
        base_api_url, full_url, static_url = _api_url_variants(base_url, ep_path_raw)
        url_html = (_build_api_url_row(f"api-url-{ep_id}", "完整 URL:",
                                       ep_path_raw, "base", base_api_url)
                    + _build_api_url_row(f"api-full-{ep_id}", "全量 URL:",
                                         ep_path_raw, "full", full_url,
                                         disabled=full_disabled,
                                         disabled_hint=full_hint,
                                         edit_url=ep_edit_url)
                    + _build_api_url_row(f"api-static-{ep_id}", "静态 URL:",
                                         ep_path_raw, "static", static_url,
                                         disabled=static_disabled,
                                         disabled_hint=static_hint,
                                         edit_url=ep_edit_url))
        # 主行 Key 徽标：多 key 化后显示数量（详情在端点配置页「API Key 管理」区块）；
        # key_counts 未提供时回退旧 api_key 掩码 + 复制完整值
        api_key_raw = ep.get("api_key") or ""
        api_key_display = _mask_api_key(api_key_raw) if api_key_raw else "—"
        if key_counts is not None:
            ep_key_count = key_counts.get(ep_id, 0)
            if ep_key_count:
                key_html = (f'<code>'
                            f'{ep_key_count} 个 Key</code>')
            else:
                key_html = '<code>—</code>'
        elif api_key_raw:
            key_html = (f'<code>{api_key_display}</code> '
                        f'<code id="api-key-raw-{ep_id}" style="display:none">'
                        f'{_escape(api_key_raw)}</code>'
                        f'<button type="button" onclick="copyToClipboard(\'api-key-raw-{ep_id}\')" '
                        f'title="复制完整 API Key" '
                        f'class="btn-mini btn-mini-outline-key">复制</button>')
        else:
            key_html = '<code>—</code>'
        # 快捷启用/禁用：POST 到独立管理页 toggle 端点，回跳来源页（禁用需确认）
        toggle_label = "禁用" if enabled else "启用"
        if return_to:
            toggle_return_to = return_to
        elif report_id is not None:
            toggle_return_to = f"/config/reports/{report_id}/edit"
        else:
            toggle_return_to = "/config/api-endpoints"
        toggle_confirm = (" onsubmit=\"return confirm('确定禁用 API 接口 "
                          f"{_escape(ep_name_raw)}？')\"") if enabled else ""
        toggle_btn = f"""<form method="post" action="/config/api-endpoints" style="display:inline"{toggle_confirm}>
      <input type="hidden" name="action" value="toggle">
      <input type="hidden" name="endpoint_id" value="{ep_id}">
      <input type="hidden" name="return_to" value="{toggle_return_to}">
      <button type="submit" class="btn btn-outline btn-sm">{toggle_label}</button>
    </form>"""
        if report_id is not None:
            ops_html = f"""<div class="ops">
    {toggle_btn}
    {_link_btn(ep_edit_url, "编辑")}
    {build_delete_form_html(_api_endpoint_url(report_id, ep_id, "delete"),
                            f"确定删除 API 接口 {_escape(ep_name_raw)}？")}
    <button type="button" class="btn btn-outline btn-sm api-more-btn" onclick="apiToggleMore(this)">展开 ▾</button>
  </div>"""
        else:
            ops_html = f"""<div class="ops">
    {toggle_btn}
    {_link_btn(ep_edit_url, "编辑")}
    {build_delete_form_html("/config/api-endpoints",
                            f"确定删除 API 接口 {_escape(ep_name_raw)}？",
                            extra_hidden='<input type="hidden" name="action" value="delete">\n'
                                         '<input type="hidden" name="endpoint_id" value="' + str(ep_id) + '">')}
    <button type="button" class="btn btn-outline btn-sm api-more-btn" onclick="apiToggleMore(this)">展开 ▾</button>
  </div>"""
        # 说明放展开区：列表=全文（不再截断到 title；title 仅作主行悬停兜底）；
        # 详情页签 desc_full=True=Markdown 全文折叠区（原型 md-body）
        if desc_full:
            desc_full_html = _build_api_description_html(ep)
            desc_block = (f'<div class="api-desc">{desc_full_html}</div>'
                          if desc_full_html else "")
        else:
            desc_raw_full = (ep.get("description") or "").strip()
            if desc_raw_full:
                desc_block = (f'<div class="api-desc" title="{_escape(desc_raw_full)}">'
                              f'<span class="lbl">说明</span>'
                              f'{_escape(desc_raw_full)}</div>')
            else:
                desc_block = '<div class="api-desc"><span class="lbl">说明</span>—</div>'
        rows += f"""<div class="api-row" id="api-row-{ep_id}">
  <div class="api-main" onclick="apiMainClick(event, this)">
    {name_html}
    <span class="path-chip">{ep_path}</span>
    {report_html}
    {enabled_badge}
    <span class="badge badge-neutral">{ep_format}</span>
    {key_html}
    {ops_html}
  </div>
  <div class="api-more" id="api-more-{ep_id}">
    <div class="api-meta">
      <span>输出模式：{mode_display}</span>
      <span>全量获取：{fetch_all_display}</span>
      <span>静态缓存：{static_cache_display}</span>
    </div>
    {desc_block}
    {url_html}
  </div>
</div>"""
    # 独立管理页由 page-head 承担标题与新建按钮，区块内不再重复标题
    title_actions = (_link_btn(f"/config/reports/{report_id}/api_endpoints/new", "新增 API 接口", "btn btn-primary btn-sm")
                     if report_id is not None else "")
    section_title = (f"""<div class="section-title">
  <span>🔌 API 接口</span>
  <span class="actions">{title_actions}</span>
</div>""" if report_id is not None else "")
    _sc_state = "开启" if _sc_enabled else "关闭"
    _sc_dir = _sc_cfg.get("dir", "static_cache")
    _sc_hint = (f'<div>'
                f'静态文件缓存: 全局 {_sc_state} | 存储目录: <code>{_escape(str(_sc_dir))}</code>'
                f'（通过 app_config.json 的 static_cache 段配置）</div>')
    list_html = rows or '<div class="empty-state">暂无 API 接口配置</div>'
    if not wrap_section:
        # 详情页签：由调用方 card 提供标题，只输出静态缓存提示 + 卡片行
        return f"{_sc_hint}\n{list_html}"
    help_html = ('<p class="api-help">信息分级：主行只保留「名称/路径/状态/主操作」；'
                 '全量与静态 URL、说明收进展开区（解决旧 11 列过载行）。</p>')
    return f"""<div class="section" id="api-endpoints">
{section_title}
{_sc_hint}
{list_html}
{help_html}
</div>"""


def _mask_api_key(key: str) -> str:
    """
    对 API Key 进行掩码显示。

    保留前4个字符和后4个字符，中间用 *** 替代。
    短密钥则全部显示后4位以 *** 开头。
    """
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***" + key[-2:]
    return key[:4] + "***" + key[-4:]


# 接口说明截断阈值（字符数）：
# - 列表页摘要版（表格单元格窄，单行 ellipsis）：40 字符 + title 悬停全文
_DESC_SUMMARY_TRUNCATE_LEN = 40


def _build_desc_summary_html(desc_raw: str,
                             max_chars: int = _DESC_SUMMARY_TRUNCATE_LEN) -> str | None:
    """构建接口说明的截断摘要 HTML（title 保留全文，悬停可见）。

    纯展示：超出 max_chars 字符截断为摘要（省略号），title 属性保留全文；
    空说明返回 None（调用方决定占位符）。
    """
    desc = (desc_raw or "").strip()
    if not desc:
        return None
    title = _escape(desc)
    summary = desc if len(desc) <= max_chars else desc[:max_chars] + "…"
    return (f'<span title="{title}" '
            f'style="display:inline-block;max-width:220px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom;'
            f'color:#64748b">{_escape(summary)}</span>')


def _build_result_mode_ui(result_count: int, result_names_list: list,
                          current_mode: str, current_index: int) -> str:
    """生成结果集输出模式的 UI 区块 HTML。"""
    if result_count <= 1:
        return ""
    has_names = bool(result_names_list)
    names = result_names_list if has_names else [f"结果{i+1}" for i in range(result_count)]
    assert len(names) == result_count, "result_names_list 长度与 result_count 不一致"

    # 名称列表展示
    name_items = "".join(
        f'<li>{"①" if i == 0 else "②" if i == 1 else "③" if i == 2 else f"<span style=\"font-family:monospace\">{i+1}.</span>"} {_escape(n)}</li>'
        for i, n in enumerate(names)
    )

    # 下拉框选项
    select_opts = "".join(
        f'<option value="{i}"{" selected" if current_mode == "single" and current_index == i else ""}>{_escape(names[i])}</option>'
        for i in range(result_count)
    )

    single_checked = ' checked' if current_mode == 'single' else ''
    all_checked = ' checked' if current_mode == 'all' else ''
    select_disabled = ' disabled' if current_mode == 'all' else ''

    warning_html = ""
    if not has_names:
        warning_html = (f'<div class="flash-warn" style="{_WARN_BOX_STYLE}">'
                        f'<span>{_icon("alert")} 该报表的 SQL 包含 {result_count} 段 SELECT，但未配置结果集名称</span>'
                        f'<span>请在报表编辑页的「结果名称」字段中设置，便于识别。暂用默认名称：{" / ".join(names)}</span>'
                        f'</div>')

    return f'''<div class="result-mode-section span-full">
  <div>结果集输出模式</div>
  <div>
    该报表的 SQL 包含 <strong>{result_count}</strong> 段 SELECT，返回 <strong>{result_count}</strong> 个结果集
  </div>
  <ul style="list-style:none">{name_items}</ul>
  {warning_html}
  <div>
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="radio" name="result_mode" value="all"{all_checked} onchange="toggleResultIndex()">
      <span>输出全部结果集</span>
      <span>— 每个结果集独立分页，API 返回 JSON 数组</span>
    </label>
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="radio" name="result_mode" value="single"{single_checked} onchange="toggleResultIndex()">
      <span>输出单个结果集：</span>
      <select name="result_index"{select_disabled}>
        {select_opts}
      </select>
    </label>
  </div>
  <div>
    结果集名称在报表编辑页的「结果名称」中配置
  </div>
  <script>
  function toggleResultIndex() {{
    var radios = document.getElementsByName('result_mode');
    var select = document.getElementsByName('result_index')[0];
    for (var i = 0; i < radios.length; i++) {{
      if (radios[i].checked && radios[i].value === 'all') {{
        select.disabled = true;
      }} else {{
        select.disabled = false;
      }}
    }}
  }}
  onReady(toggleResultIndex);
  </script>
</div>'''


_API_TEMPLATE_JS = r'''
<script>
  var TPL_DEFAULTS = {
    single: '{\n  "data": {{data}},\n  "total": {{total}},\n  "page": {{page}},\n  "page_size": {{page_size}},\n  "total_pages": {{total_pages}}\n}',
    all: '{\n  "results": {{results}},\n  "mode": {{mode}},\n  "page": {{page}},\n  "page_size": {{page_size}}\n}'
  };
  var TPL_KEYS = {
    single: ['data', 'total', 'page', 'page_size', 'total_pages', 'full', 'meta'],
    all: ['results', 'mode', 'page', 'page_size', 'full', 'meta']
  };
  var TPL_META_SAMPLE = {
    "generated_at": "2026-08-05 10:00:00 +0800",
    "expires_at": null,
    "last_invalidated_at": null,
    "config_version": "ab12cd34"
  };
  var TPL_SAMPLE = {
    single: {
      data: [{"客户ID": 1, "客户名称": "张三"}, {"客户ID": 2, "客户名称": "李四"}],
      total: 42, page: 1, page_size: 20, total_pages: 3, full: true,
      meta: TPL_META_SAMPLE
    },
    all: {
      results: [{
        "name": "结果1",
        "data": [{"客户ID": 1, "客户名称": "张三"}, {"客户ID": 2, "客户名称": "李四"}],
        "total": 42, "page": 1, "page_size": 42, "total_pages": 1
      }],
      mode: "all", page: 1, page_size: 42, full: true,
      meta: TPL_META_SAMPLE
    }
  };
  function currentTemplateMode() {
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) return radios[i].value;
    }
    return 'single';
  }
  function lineColOf(text, pos) {
    var line = 1, col = 1;
    for (var i = 0; i < pos && i < text.length; i++) {
      if (text.charAt(i) === '\n') { line++; col = 1; } else { col++; }
    }
    return { line: line, col: col };
  }
  function jsonErrorLoc(msg, replaced) {
    var m = msg.match(/line (\d+) column (\d+)/);
    if (m) return { line: +m[1], col: +m[2] };
    m = msg.match(/position (\d+)/);
    if (m) return lineColOf(replaced, +m[1]);
    return null;
  }
  function renderTemplatePreview() {
    var ta = document.getElementById('json-template-input');
    var pre = document.getElementById('template-preview');
    var err = document.getElementById('template-preview-error');
    if (!ta || !pre || !err) return;
    var mode = currentTemplateMode();
    var tpl = ta.value;
    pre.textContent = '';
    err.textContent = '';
    if (!tpl.trim()) {
      pre.textContent = '（留空 = 默认输出）';
      return;
    }
    var re = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;
    var keys = TPL_KEYS[mode];
    var m;
    while ((m = re.exec(tpl)) !== null) {
      if (keys.indexOf(m[1]) === -1) {
        var loc = lineColOf(tpl, m.index);
        err.textContent = '未知占位符 {{' + m[1] + '}} 位于第 ' + loc.line + ' 行第 ' + loc.col + ' 列；可用占位符: ' + keys.join(', ');
        return;
      }
    }
    var sqCbs = document.querySelectorAll('.smart-quote-cb');
    var smartMode = sqCbs.length > 0 && Array.prototype.some.call(sqCbs, function(cb) {
      return cb.checked;
    });
    var replaced = tpl.replace(re, function(mm, key) {
      var v = TPL_SAMPLE[mode][key];
      if (v === undefined) return 'null';
      return JSON.stringify(v);
    });
    if (smartMode) {
      // 智能去引号：判定逻辑单一来源在后端（复用约定），占位预览不做第二套实现
      pre.textContent = replaced + '\n（智能去引号模式：字符串值按勾选形态去引号，以真实数据预览为准）';
      return;
    }
    try {
      var parsed = JSON.parse(replaced);
      pre.textContent = JSON.stringify(parsed, null, 2);
    } catch (e) {
      var loc = jsonErrorLoc(e.message, replaced);
      if (loc) {
        err.textContent = 'JSON 格式非法（第 ' + loc.line + ' 行第 ' + loc.col + ' 列附近）: ' + e.message;
      } else {
        err.textContent = 'JSON 格式非法: ' + e.message;
      }
    }
  }
  function resetTemplateToDefault() {
    var ta = document.getElementById('json-template-input');
    if (!ta) return;
    ta.value = TPL_DEFAULTS[currentTemplateMode()];
    renderTemplatePreview();
  }
  function previewWithRealData() {
    var btn = document.getElementById('preview-live-btn');
    if (!btn) return;
    var pre = document.getElementById('template-preview');
    var err = document.getElementById('template-preview-error');
    var urlPath = btn.getAttribute('data-url');
    if (!urlPath || !pre || !err) return;
    btn.disabled = true;
    btn.textContent = '预览中...';
    var fd = new URLSearchParams();
    var ta = document.getElementById('json-template-input');
    fd.append('json_template', ta ? ta.value : '');
    var ruleTa = document.getElementsByName('rule_json')[0];
    fd.append('rule_json', ruleTa ? ruleTa.value : '');
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) fd.append('result_mode', radios[i].value);
    }
    var idxSel = document.getElementsByName('result_index')[0];
    fd.append('result_index', idxSel ? idxSel.value : '0');
    var rlInput = document.getElementsByName('row_limit')[0];
    fd.append('row_limit', rlInput ? rlInput.value : '0');
    var sqHidden = document.getElementById('smart-quote-flags-input');
    fd.append('smart_quote_flags', sqHidden ? sqHidden.value : '0');
    fetch(urlPath, {method: 'POST', body: fd})
      .then(function(r) {
        return r.json().catch(function() {
          return {ok: false, error: '响应解析失败（HTTP ' + r.status + '）'};
        });
      })
      .then(function(data) {
        if (data && data.ok) {
          try {
            pre.textContent = JSON.stringify(JSON.parse(data.output), null, 2);
          } catch (e) {
            pre.textContent = data.output;
          }
          err.textContent = '';
        } else {
          pre.textContent = '';
          err.textContent = '真实数据预览失败: ' + ((data && data.error) || '未知错误');
        }
      })
      .catch(function(e) {
        err.textContent = '真实数据预览失败: ' + e;
      })
      .then(function() {
        btn.disabled = false;
        btn.textContent = '用真实数据预览';
      });
  }
  function updateTemplateMode() {
    var mode = currentTemplateMode();
    var badgesSingle = document.getElementById('tpl-badges-single');
    var badgesAll = document.getElementById('tpl-badges-all');
    var defSingle = document.getElementById('tpl-default-single');
    var defAll = document.getElementById('tpl-default-all');
    if (badgesSingle) badgesSingle.style.display = mode === 'single' ? 'block' : 'none';
    if (badgesAll) badgesAll.style.display = mode === 'all' ? 'block' : 'none';
    if (defSingle) defSingle.style.display = mode === 'single' ? 'block' : 'none';
    if (defAll) defAll.style.display = mode === 'all' ? 'block' : 'none';
    renderTemplatePreview();
  }
  function updateTemplateState() {
    var fmtSel = document.querySelector('select[name="output_format"]');
    var isCsv = fmtSel && fmtSel.value === 'csv';
    var ta = document.getElementById('json-template-input');
    var btn = document.getElementById('template-reset-btn');
    var liveBtn = document.getElementById('preview-live-btn');
    var hint = document.getElementById('template-csv-hint');
    var section = document.getElementById('template-section');
    if (ta) ta.disabled = isCsv;
    if (btn) btn.disabled = isCsv;
    if (liveBtn) liveBtn.disabled = isCsv;
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
    if (section) section.style.opacity = isCsv ? '0.55' : '1';
  }
  onReady(function() {
    var radios = document.getElementsByName('result_mode');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', updateTemplateMode);
    }
    var fmtSel = document.querySelector('select[name="output_format"]');
    if (fmtSel) fmtSel.addEventListener('change', updateTemplateState);
    updateTemplateMode();
    updateTemplateState();
  });
</script>
'''


def build_api_endpoint_preview_help_html(report_id: int, endpoint_id: int) -> str:
    """渲染真实数据预览指引页（预览地址被直接 GET 打开时）。

    预览需要携带表单未保存值（json_template/rule_json/result_mode/
    result_index/row_limit），直接打开地址无法执行，给出返回编辑页的指引。
    """
    back_url = _api_endpoint_url(report_id, endpoint_id)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>真实数据预览</title></head>"
        "<body style='font-family:sans-serif;background:#f8fafc;margin:0;"
        "padding:60px 20px;color:#0f172a'>"
        "<div style='max-width:560px;margin:0 auto;background:#fff;"
        "border:1px solid #e2e8f0;border-radius:12px;padding:32px'>"
        "<h2 style='margin-top:0'>真实数据预览</h2>"
        "<p>预览需要携带当前编辑表单中的模板与规则参数，请通过"
        "「用真实数据预览」按钮发起，或点击下方按钮返回编辑页填写。"
        "</p><a href='" + back_url + "' style='display:inline-block;margin-top:12px;"
        "padding:8px 20px;background:#6366f1;color:#fff;border-radius:8px;"
        "text-decoration:none'>返回编辑页</a>"
        "<div style='margin-top:24px;font-size:12px;color:#64748b'>"
        "POST 请求需携带参数：json_template、rule_json、result_mode、"
        "result_index、row_limit（均与编辑表单一致）。</div>"
        "</div></body></html>"
    )


def build_api_endpoint_form_html(report_id: int, report_name: str,
                                 endpoint: dict = None,
                                 flash: str = None,
                                 result_names_list: list = None,
                                 result_count: int = 1,
                                 endpoint_id: int = None,
                                 is_edit: bool = None,
                                 api_keys: list = None) -> str:
    """
    渲染 API 端点编辑/新增表单。

    参数:
        report_id: 关联报表 ID
        report_name: 关联报表名称（显示用）
        endpoint: 现有端点配置（None 表示新增；保存失败回显时传表单临时数据）
        flash: 错误消息
        result_names_list: 结果集名称列表（按行分割）
        result_count: 结果集估算数量
        endpoint_id: 端点 ID（决定 action_url）
        is_edit: 表单模式（None 时按 endpoint 是否为 None 判定）
    """
    if is_edit is None:
        is_edit = endpoint is not None
    if is_edit:
        ep_id = endpoint_id or (endpoint or {}).get("id")
        action_url = _api_endpoint_url(report_id, ep_id)
        title = "编辑 API 接口"
    else:
        action_url = f"/config/reports/{report_id}/api_endpoints/new"
        title = "新增 API 接口"

    flash_html = build_flash_html(flash) if flash else ""

    name = _escape(endpoint["name"]) if endpoint else ""
    description = _escape((endpoint or {}).get("description") or "")
    url_path = endpoint["url_path"] if endpoint else ""
    # 从完整 URL 路径中剥离 /api/ 前缀，仅保留用户输入的后段
    url_path_short = app_config.strip_api_prefix(url_path)
    url_path_short = _escape(url_path_short)
    output_format = (endpoint or {}).get("output_format", "json")
    row_limit = str((endpoint or {}).get("row_limit", 0) or 0)
    allowed_origins = _escape((endpoint or {}).get("allowed_origins") or "")
    enabled_checked = ' checked' if (endpoint is None or int(endpoint.get("enabled", 1))) else ''
    allow_fetch_all_checked = (' checked' if (endpoint is None or int(endpoint.get("allow_fetch_all", 1))) else '')
    static_cache_checked = (' checked' if (endpoint is None or int(endpoint.get("static_cache", 1))) else '')
    # 智能去引号面板默认全不勾（= 标准 JSON，零破坏）；「数字（原生类型）」恒裸
    # 不占位，仅说明文案；存量 json_no_quotes=1 由迁移映射为面板全开（0b111）
    smart_flags = int((endpoint or {}).get("smart_quote_flags", 0) or 0)
    sq_decimal_checked = ' checked' if (smart_flags & 1) else ''
    sq_scientific_checked = ' checked' if (smart_flags & 2) else ''
    sq_thousand_checked = ' checked' if (smart_flags & 4) else ''

    # 结果集输出模式
    result_mode = (endpoint or {}).get("result_mode", "single")
    result_index = int((endpoint or {}).get("result_index", 0))

    # 从三个 DB 字段拼合规则 JSON（含 nested_filter 嵌套筛选规则）
    if endpoint:
        rules = {}
        cols_val = endpoint.get("columns") or ""
        filters_raw_db = endpoint.get("filters") or ""
        sorts_raw_db = endpoint.get("sorts") or ""
        nested_raw_db = endpoint.get("nested_filter") or ""
        if cols_val:
            rules["columns"] = cols_val
        if filters_raw_db:
            try:
                rules["filters"] = json.loads(filters_raw_db)
            except (json.JSONDecodeError, TypeError):
                rules["filters"] = filters_raw_db
        if sorts_raw_db:
            try:
                rules["sorts"] = json.loads(sorts_raw_db)
            except (json.JSONDecodeError, TypeError):
                rules["sorts"] = sorts_raw_db
        if nested_raw_db:
            try:
                rules["nested_filter"] = json.loads(nested_raw_db)
            except (json.JSONDecodeError, TypeError):
                rules["nested_filter"] = nested_raw_db
        rule_json = json.dumps(rules, indent=2, ensure_ascii=False) if rules else ""
    else:
        rule_json = ""

    format_opts = "".join(
        f'<option value="{v}"{" selected" if output_format == v else ""}>{v.upper()}</option>'
        for v in ("json", "csv")
    )
    template_val = _escape((endpoint or {}).get("json_template") or "")

    # 真实数据预览：仅编辑态可用（新增端点无 endpoint_id、无关联已存配置）
    if endpoint_id is not None:
        live_preview_html = (
            '<div>'
            f'<button type="button" id="preview-live-btn" data-url="{_api_endpoint_url(report_id, endpoint_id, "preview")}" '
            'onclick="previewWithRealData()" '
            'style="cursor:pointer">用真实数据预览</button>'
            '<span>以当前表单未保存的模板/规则执行真实查询（最多 3 行数据），结果展示在下方预览区</span>'
            '</div>'
        )
    else:
        live_preview_html = ""

    # API Key 管理：编辑态渲染管理区块（独立表单，放在主表单之外
    # 避免 HTML 嵌套 form——嵌套 form 会提前闭合主表单导致保存按钮失效）；
    # 新增态表单内显示"保存后自动生成"提示
    if is_edit and endpoint_id:
        api_key_block_html = ""
        key_manage_extra = build_api_key_manage_html(
            api_keys or [], report_id, endpoint_id)
    else:
        api_key_block_html = (
            '<div class="flash-warn span-full" style="margin-bottom:16px;padding:10px 14px;'
            'border-radius:8px;border:1px solid #fde68a;font-size:13px">'
            '<strong>' + _icon("key") + ' API Key：</strong>保存后将自动生成 API Key（名称=接口名称），'
            '可在编辑页「API Key 管理」区块查看、复制与禁用。</div>'
        )
        key_manage_extra = ""

    # 页面头动作（spec page-api-edit）：编辑态给「真实数据预览」，
    # 复用④卡片内的 preview-live-btn（previewWithRealData 按 id 取地址，document 级）
    page_head_actions = (
        '<button type="button" class="btn btn-secondary" '
        'onclick="previewWithRealData()">真实数据预览</button>'
        if is_edit and endpoint_id else "")
    return f"""{flash_html}
<form method="post" action="{action_url}" class="config-form">
  <div class="page-head span-full">
    <div>
      <div class="crumb"><a href="/config/api-endpoints">API 接口</a> › {'编辑' if is_edit else '新增'}</div>
      <h1>{title}</h1>
      <div class="sub">关联报表：{_escape(report_name)}（ID: {report_id}）</div>
    </div>
    <div class="actions">{page_head_actions}</div>
  </div>
  <div class="grid-2 span-full">
  <div>
  <div class="card">
  <div class="card-head"><div class="form-section">① 基本信息</div></div>
  <label>接口名称: <input type="text" name="name" value="{name}" required
    placeholder="例如: 客户数据 API"></label>

  <label class="span-full">接口说明（可选，仅页面展示，不进入 API 输出）:
    <textarea name="description" class="sql-textarea" placeholder="描述该接口的用途、当前状态、使用注意事项，支持 Markdown（标题/列表/代码块/```mermaid 流程图）…" rows="4" style="min-height:80px">{description}</textarea>
    <div class="memo-preview md-body" id="description-preview"></div>
    <div class="sql-toolbar">
      <button type="button" class="btn btn-outline btn-sm" onclick="toggleDescPreview(this)">预览接口说明</button>
    </div>
  </label>

  </div>
  <div class="card">
  <div class="card-head"><div class="form-section">② 调用地址</div></div>
  <label class="span-full">URL 路径:
    <div style="display:flex;align-items:center;gap:0">
      <span style="white-space:nowrap">/api/</span>
      <input type="text" name="url_path" value="{url_path_short}" required
        id="url-path-input"
        placeholder="customers"
        style="flex:1"
        oninput="updateFullUrl()">
    </div>
  </label>
  <div class="span-full" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span>完整 URL:</span>
    <code id="full-url-text" style="flex:1;word-break:break-all"></code>
    <button type="button" onclick="copyToClipboard('full-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>
  <div id="fetch-all-url-row" class="span-full" style="margin-top:6px;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:13px;color:#475569;display:{'flex' if allow_fetch_all_checked else 'none'};align-items:center;gap:8px;flex-wrap:wrap">
    <span>全量 URL:</span>
    <code id="fetch-all-url-text" style="flex:1;word-break:break-all"></code>
    <button type="button" onclick="copyToClipboard('fetch-all-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>
  <script>
  function updateFullUrl() {{
    var input = document.getElementById('url-path-input');
    var display = document.getElementById('full-url-text');
    var path = input.value || '';
    display.textContent = buildApiUrl('/api/' + path, 'base');
    updateFetchAllUrl();
    updateStaticUrl();
  }}
  function updateFetchAllUrl() {{
    var input = document.getElementById('url-path-input');
    var row = document.getElementById('fetch-all-url-row');
    var checkbox = document.querySelector('input[type="checkbox"][name="allow_fetch_all"]');
    if (!input || !row) return;
    var show = !checkbox || checkbox.checked;
    row.style.display = show ? 'flex' : 'none';
    if (show) {{
      var text = document.getElementById('fetch-all-url-text');
      var path = input.value || '';
      text.textContent = buildApiUrl('/api/' + path, 'full');
    }}
  }}
  function updateStaticUrl() {{
    var input = document.getElementById('url-path-input');
    var row = document.getElementById('static-url-row');
    var checkbox = document.getElementById('static-cache-checkbox');
    if (!input || !row) return;
    var show = checkbox && checkbox.checked && !checkbox.disabled;
    row.style.display = show ? 'flex' : 'none';
    if (show) {{
      var text = document.getElementById('static-url-text');
      var path = input.value || '';
      text.textContent = buildApiUrl('/api/' + path, 'static');
    }}
  }}
  function updateSmartFlags() {{
    var cbs = document.querySelectorAll('.smart-quote-cb');
    var hidden = document.getElementById('smart-quote-flags-input');
    if (!hidden) return;
    var flags = 0;
    cbs.forEach(function(cb) {{
      if (cb.checked) flags |= parseInt(cb.value, 10) || 0;
    }});
    hidden.value = flags;
  }}
  function updateStaticCacheState() {{
    var fmtSel = document.querySelector('select[name="output_format"]');
    if (!fmtSel) return;
    var isCsv = fmtSel.value === 'csv';
    var cb = document.getElementById('static-cache-checkbox');
    var hint = document.getElementById('static-cache-csv-hint');
    if (cb) {{
      cb.disabled = isCsv;
      if (isCsv) cb.checked = false;
    }}
    if (hint) hint.style.display = isCsv ? 'inline' : 'none';
    var hintNoQuotes = document.getElementById('json-no-quotes-csv-hint');
    var sqCbs = document.querySelectorAll('.smart-quote-cb');
    if (sqCbs.length) {{
      sqCbs.forEach(function(cb) {{
        cb.disabled = isCsv;
        if (isCsv) cb.checked = false;
      }});
      if (isCsv) updateSmartFlags();
    }}
    if (hintNoQuotes) hintNoQuotes.style.display = isCsv ? 'inline' : 'none';
    updateStaticUrl();
  }}
  onReady(function() {{
    updateFullUrl();
    updateFetchAllUrl();
    updateStaticCacheState();
  }});
  var _descPreviewSeq = 0;
  function renderDescPreviewMermaid() {{
    var nodes = document.querySelectorAll('#description-preview .mermaid');
    if (!nodes.length) return;
    if (window.mermaid) {{
      mermaid.run({{ nodes: nodes }});
      return;
    }}
    var s = document.createElement('script');
    s.src = '{markdown_render.MERMAID_JS_URL}';
    s.onload = function() {{
      mermaid.initialize({{ startOnLoad: false, securityLevel: 'strict' }});
      mermaid.run({{ nodes: nodes }});
    }};
    document.head.appendChild(s);
  }}
  function refreshDescPreview(btn) {{
    var prev = document.getElementById('description-preview');
    var ta = document.querySelector('textarea[name="description"]');
    if (!prev || !ta) return;
    var seq = ++_descPreviewSeq;
    var body = new URLSearchParams();
    body.append('description', ta.value);
    fetch('/config/api-endpoints/description-preview', {{ method: 'POST', body: body }})
      .then(function(r) {{ return r.text(); }})
      .then(function(html) {{
        if (seq !== _descPreviewSeq) return;
        prev.innerHTML = html;
        renderDescPreviewMermaid();
        if (btn && btn.textContent === '预览中...') btn.textContent = '隐藏预览';
      }})
      .catch(function() {{
        if (seq !== _descPreviewSeq) return;
        prev.textContent = '预览失败，请稍后重试';
        if (btn && btn.textContent === '预览中...') btn.textContent = '隐藏预览';
      }});
  }}
  function scheduleDescPreview() {{
    var prev = document.getElementById('description-preview');
    if (!prev || !prev.classList.contains('show')) return;
    if (window._descPreviewTimer) clearTimeout(window._descPreviewTimer);
    window._descPreviewTimer = setTimeout(function() {{ refreshDescPreview(); }}, 300);
  }}
  function toggleDescPreview(btn) {{
    var prev = document.getElementById('description-preview');
    var ta = document.querySelector('textarea[name="description"]');
    if (!prev || !ta) return;
    var show = !prev.classList.contains('show');
    if (!show) {{
      prev.classList.remove('show');
      btn.textContent = '预览接口说明';
      return;
    }}
    prev.classList.add('show');
    btn.textContent = '预览中...';
    refreshDescPreview(btn);
  }}
  var _descTa = document.querySelector('textarea[name="description"]');
  if (_descTa) _descTa.addEventListener('input', scheduleDescPreview);
  </script>
  </div>
  </div>
  <div>
  <div class="card">
  <div class="card-head"><div class="form-section">③ 请求与输出</div></div>
  <label>输出格式:
    <select name="output_format" onchange="updateStaticCacheState();updateTemplateState()">{format_opts}</select>
  </label>

  <label class="span-full" style="display:flex;align-items:center;gap:8px">
    <input type="hidden" name="static_cache" value="0">
    <input type="checkbox" name="static_cache" value="1"{static_cache_checked} id="static-cache-checkbox"
      onchange="updateStaticUrl()">
    <span>静态文件缓存（.json 变体）</span>
    <span id="static-cache-csv-hint" style="display:none">仅 JSON 格式支持</span>
  </label>
  <div class="span-full">
    开启后，调用方在端点 URL 后追加 <code>.json</code> 即可访问静态化输出（全量数据 + meta 节点），
    命中时零查询零计算；缓存失效自动回退并重建。TTL 与报表缓存配置（cache_ttl_hours）一致。
  </div>
  <div id="static-url-row" class="span-full" style="margin-top:6px;padding:8px 12px;background:#f1f5f9;border-radius:6px;font-size:13px;color:#475569;display:{'flex' if static_cache_checked else 'none'};align-items:center;gap:8px;flex-wrap:wrap">
    <span>静态 URL:</span>
    <code id="static-url-text" style="flex:1;word-break:break-all"></code>
    <button type="button" onclick="copyToClipboard('static-url-text')" class="btn-mini btn-mini-outline">复制</button>
  </div>

  <label class="span-full" style="display:flex;align-items:center;gap:8px">
    <span>智能去引号</span>
    <span id="json-no-quotes-csv-hint" style="display:none">仅 JSON 格式支持</span>
  </label>
  <div class="span-full">
    <input type="hidden" name="smart_quote_flags" id="smart-quote-flags-input" value="{smart_flags}">
    勾选以下形态时，JSON 输出中对应字符串值<strong>去掉引号</strong>（未勾选形态保持带引号）：
    <label style="display:flex;align-items:center;gap:6px">
      <input type="checkbox" class="smart-quote-cb" value="1"{sq_decimal_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      十进制数字（含正负号），如 <code>-1.5</code>；前导零数值化（<code>007</code> → <code>7</code>）
    </label>
    <label style="display:flex;align-items:center;gap:6px">
      <input type="checkbox" class="smart-quote-cb" value="2"{sq_scientific_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      科学计数法，如 <code>1e5</code>（符合 JSON 数字语法，原样输出）
    </label>
    <label style="display:flex;align-items:center;gap:6px">
      <input type="checkbox" class="smart-quote-cb" value="4"{sq_thousand_checked}
        onchange="updateSmartFlags();renderTemplatePreview()">
      千分位数字，如 <code>1,000</code>（输出去逗号数值化：<code>1,000</code> → <code>1000</code>）
    </label>
    <div>
      开启任一形态时，输出<strong>永远合法 JSON</strong>（RFC 8259）：原生 int/float 始终输出为数字，
      无需勾选；Decimal 数值列在勾选「十进制数字」或「科学计数法」时输出为数字，未勾选时带引号；
      含非数字内容的文本（如日期、空串、<code>true</code>/<code>false</code>）永远带引号。
      模板占位预览在勾选时以真实数据预览为准。
    </div>
  </div>

  {_build_result_mode_ui(result_count, result_names_list, result_mode, result_index)}

  <div class="flash-warn span-full">
    <strong>{_icon("info")} 快捷获取规则：</strong>在报表页面使用筛选/排序/字段选择功能调整数据后，
    切到「<strong>规则</strong>」页签，在「<strong>当前规则</strong>」卡片点击「<strong>复制 JSON</strong>」按钮即可获取 JSON 格式的配置，
    直接粘贴到下方的 JSON 文本框中。
    <div>
      查看报表 → <a href="/report?id={report_id}" target="_blank">/report?id={report_id}</a>
    </div>
  </div>

  <label class="span-full">规则 JSON（筛选/排序/字段选择，留空=无二次加工）:
    <textarea name="rule_json" class="sql-textarea"
      placeholder='{{"filters":[{{"col":"status","op":"eq","val":"active"}}],"sorts":[{{"col":"created_at","dir":"desc"}}],"columns":"id,name,email"}}'
      rows="5" style="min-height:100px">{_escape(rule_json)}</textarea></label>

  <label>最大行数（0=不限制）:
    <input type="number" name="row_limit" value="{row_limit}" min="0" step="1"></label>

  <label class="span-full" style="display:flex;align-items:center;gap:8px">
    <input type="hidden" name="allow_fetch_all" value="0">
    <input type="checkbox" name="allow_fetch_all" value="1"{allow_fetch_all_checked} onchange="updateFetchAllUrl()">
    <span>允许全量获取（fetch_all 参数）</span>
  </label>
  <div class="span-full">
    <strong>使用示例：</strong>开启后，调用方在请求中携带 <code>fetch_all</code> 参数即可一次获取全部数据（不做翻页）：
    <div>
      GET&nbsp;&nbsp; /api/&lt;路径&gt;?fetch_all=true<br>
      POST&nbsp; body: {{"fetch_all": true}}
    </div>
    <div>值仅接受 true / 1 / yes；关闭后即使传递该参数，也按翻页逻辑返回</div>
  </div>

  {api_key_block_html}

  <label class="span-full">CORS 允许来源（逗号分隔，留空=不设 CORS）:
    <input type="text" name="allowed_origins" value="{allowed_origins}"
      placeholder="例如: https://example.com,http://localhost:3000"></label>

  <label class="span-full" style="display:flex;align-items:center;gap:8px">
    <input type="hidden" name="enabled" value="0">
    <input type="checkbox" name="enabled" value="1"{enabled_checked}>
    <span>启用</span>
  </label>

  </div>
  <div class="card">
  <div class="card-head"><div class="form-section">④ JSON 模板</div></div>
  <div id="template-section" class="span-full">
    <div>JSON 输出模板（可选）</div>
    <label style="display:block">
      <textarea name="json_template" id="json-template-input" rows="8"
        style="min-height:150px;box-sizing:border-box"
        placeholder='{{"data": {{{{data}}}}, "total": {{{{total}}}}, "page": {{{{page}}}}, "page_size": {{{{page_size}}}}, "total_pages": {{{{total_pages}}}}}}'
        oninput="renderTemplatePreview()">{template_val}</textarea>
    </label>
    <div>
      留空 = 默认输出。自定义模板以默认 JSON 为起点，用 <code>{{{{占位符}}}}</code> 引用数据，
      值将按实际数据替换（缺键输出 null）。<span id="template-csv-hint" style="display:none">模板仅 JSON 格式支持，CSV 格式下已禁用。</span>
    </div>

    <div>
      <span>可用占位符（随「结果集输出模式」切换）：</span>
      <div id="tpl-badges-single">
        <span style="display:inline-block">{{{{data}}}}</span>数据数组
        <span style="display:inline-block">{{{{total}}}}</span>总行数
        <span style="display:inline-block">{{{{page}}}}</span>页码
        <span style="display:inline-block">{{{{page_size}}}}</span>每页条数
        <span style="display:inline-block">{{{{total_pages}}}}</span>总页数
        <span style="display:inline-block">{{{{full}}}}</span>全量标记（fetch_all 时 true）
        <span style="display:inline-block">{{{{meta}}}}</span>静态缓存 meta（.json 变体）
      </div>
      <div id="tpl-badges-all" style="display:none">
        <span style="display:inline-block">{{{{results}}}}</span>结果集数组
        <span style="display:inline-block">{{{{mode}}}}</span>模式（固定 "all"）
        <span style="display:inline-block">{{{{page}}}}</span>页码
        <span style="display:inline-block">{{{{page_size}}}}</span>每页条数
        <span style="display:inline-block">{{{{full}}}}</span>全量标记（fetch_all 时 true）
        <span style="display:inline-block">{{{{meta}}}}</span>静态缓存 meta（.json 变体）
      </div>
    </div>

    <details open>
      <summary style="cursor:pointer">默认 JSON 起点（把默认结构改一改就是模板）</summary>
      <div id="tpl-default-single">
        <pre style="overflow:auto">{{
  "data": {{{{data}}}},              // 数据数组
  "total": {{{{total}}}},            // 总行数
  "page": {{{{page}}}},              // 页码
  "page_size": {{{{page_size}}}},    // 每页条数
  "total_pages": {{{{total_pages}}}} // 总页数
}}</pre>
        <div>注：原生默认输出在 fetch_all 时含 <code>"full": {{{{full}}}}</code>，.json 静态变体含 <code>"meta": {{{{meta}}}}</code>；如需这些字段，在模板中手动加对应键</div>
      </div>
      <div id="tpl-default-all" style="display:none">
        <pre style="overflow:auto">{{
  "results": {{{{results}}}},   // 结果集数组（每项含 name/data/total/page/page_size/total_pages）
  "mode": {{{{mode}}}},         // 固定 "all"
  "page": {{{{page}}}},         // 页码
  "page_size": {{{{page_size}}}} // 每页条数
}}</pre>
        <div>注：fetch_all 时原生输出含 <code>"full": {{{{full}}}}</code>，.json 静态变体含 <code>"meta": {{{{meta}}}}</code></div>
      </div>
    </details>

    <div>
      <button type="button" id="template-reset-btn" onclick="resetTemplateToDefault()"
        style="cursor:pointer">还原为默认 JSON 格式</button>
      <span>还原结果为当前模式的默认模板文本（不含 full/meta，可手动添加）</span>
    </div>
    {live_preview_html}

    <div>实时预览（样例数据）：</div>
    <pre id="template-preview" style="overflow:auto;max-height:280px"></pre>
    <div id="template-preview-error"></div>
  </div>

  </div>
  </div>
  </div>

  {_API_TEMPLATE_JS}

  <div class="form-actions span-full formbar">
    <button type="submit" name="action" value="save" class="btn btn-primary">保存</button>
    <button type="submit" name="action" value="save_close" class="btn btn-outline">保存并关闭</button>
    <a href="/config/reports/{report_id}/edit" class="cancel">关闭</a>
  </div>
</form>
{key_manage_extra}"""


# ===================================================================
# API Key 管理区块（多 key 化 PH-03）
# ===================================================================


def build_api_key_manage_html(keys: list, report_id: int, endpoint_id: int) -> str:
    """构建「API Key 管理」区块 HTML。

    独立于主表单渲染（操作 POST 到
    /config/reports/{report_id}/api_endpoints/{endpoint_id}/api_keys），
    避免 HTML 嵌套 form。每行：名称 + 掩码 + 复制 + 启用/禁用 + 删除；
    底部提供「生成新 Key」（名称留空=端点名）。
    """
    action_url = _api_endpoint_url(report_id, endpoint_id, "api_keys")
    rows = ""
    for k in keys:
        kid = k["id"]
        kname = _escape(k.get("name") or "未命名")
        kraw = k.get("api_key") or ""
        kdisp = _mask_api_key(kraw) if kraw else "—"
        enabled = int(k.get("enabled", 1))
        state = (build_state_span("启用")
                 if enabled else build_state_span("禁用", "warn"))
        toggle_label = "禁用" if enabled else "启用"
        toggle_confirm = (
            " onsubmit=\"return confirm('确定禁用该 API Key？禁用后调用方立即失效。')\""
            if enabled else "")
        toggle_form = (
            f'<form method="post" action="{action_url}" style="display:inline"{toggle_confirm}>'
            f'<input type="hidden" name="action" value="toggle">'
            f'<input type="hidden" name="key_id" value="{kid}">'
            f'<button type="submit" class="btn-mini btn-mini-m">{toggle_label}</button>'
            f'</form>')
        del_form = (
            f'<form method="post" action="{action_url}" style="display:inline" '
            f'onsubmit="return confirm(\'确定删除该 API Key？删除后调用方立即失效。\')">'
            f'<input type="hidden" name="action" value="delete">'
            f'<input type="hidden" name="key_id" value="{kid}">'
            f'<button type="submit" class="btn-mini btn-mini-m" '
            f'>删除</button>'
            f'</form>')
        rows += (
            f'<div style="display:flex;align-items:center;gap:10px;padding:7px 0;'
            f'border-bottom:1px dashed #e2e8f0">'
            f'<span>'
            f'{kname}</span>'
            f'<code>{kdisp}</code>'
            f'<code id="api-key-raw-{kid}" style="display:none">{_escape(kraw)}</code>'
            f'<button type="button" onclick="copyToClipboard(\'api-key-raw-{kid}\')" '
            f'title="复制完整 API Key" class="btn-mini btn-mini-outline-key">复制</button>'
            f'{state}{toggle_form}{del_form}'
            f'</div>')
    if not rows:
        rows = (
            '<div>'
            '暂无 API Key——接口为公开访问（无需鉴权）。生成 Key 后立即生效。</div>')
    return (
        f'<div style="margin:16px 0;padding:14px;background:#f8fafc;border-radius:8px;'
        f'border:1px solid #e2e8f0">'
        f'<div>'
        f'{_icon("key")} API Key 管理</div>'
        f'<div>'
        f'每个调用方可分配独立 Key（名称仅作管理标识）；Key 明文可查看（内控要求），'
        f'通过 Authorization: Bearer &lt;key&gt; 或 ?api_key=xxx 调用。'
        f'禁用/删除后立即失效。</div>'
        f'{rows}'
        f'<form method="post" action="{action_url}" '
        f'style="display:flex;align-items:center;gap:8px">'
        f'<input type="text" name="name" placeholder="Key 名称（留空=接口名称）" '
        f'style="flex:1;min-width:160px;padding:6px 10px;border:1px solid #cbd5e1;'
        f'border-radius:6px;font-size:13px">'
        f'<input type="hidden" name="action" value="add">'
        f'<button type="submit" class="btn-mini btn-mini-solid btn-mini-primary">'
        f'生成新 Key</button>'
        f'</form>'
        f'</div>')


# ===================================================================
# 审计日志页
# ===================================================================


def render_audit_page(
    rows: list[dict],
    total: int,
    page: int,
    page_size: int,
    filters: dict,
    message: str = "",
    db_size: int = 0,
) -> str:
    """渲染审计日志页面（筛选栏 + 表格 + 分页 + CSV 导出 + 清理）。"""
    now = time.time()
    total_pages = max(1, (total + page_size - 1) // page_size)
    selected_type = filters.get("type", "")
    type_options = {"": "全部类型", "operation": "操作日志", "web_access": "页面访问",
                    "api": "API 调用", "scheduler": "定时任务"}
    type_html = ""
    for val, label in type_options.items():
        sel = ' selected' if val == selected_type else ''
        type_html += f'<option value="{val}"{sel}>{label}</option>'
    range_presets = {"today": "今天", "yesterday": "昨天", "last7": "近7天", "last30": "近30天"}
    range_btns = ""
    for rkey, rlabel in range_presets.items():
        range_btns += f'<button type="button" class="btn btn-sm btn-outline" onclick="setAuditDateRange(\'{rkey}\')">{rlabel}</button>'
    date_from = filters.get("date_from", "")
    date_to = filters.get("date_to", "")
    session_user_val = filters.get("session_user", "")
    keyword_val = filters.get("keyword", "")

    table_header = """<thead><tr>
      <th>时间</th>
      <th>类型</th>
      <th>操作者</th>
      <th>操作</th>
      <th>实体类型</th>
      <th>详情</th>
    </tr></thead>"""

    type_labels = {"operation": "操作", "web_access": "页面", "api": "API",
                   "scheduler": "定时"}
    rows_html = ""
    for r in rows:
        rtype = r.get("type", "")
        type_label = type_labels.get(rtype, rtype)
        ts = r.get("timestamp", "")
        user = html_mod.escape(r.get("session_user") or "")
        action = html_mod.escape(r.get("action") or "")
        entity_type = html_mod.escape(r.get("entity_type") or "")
        entity_name = html_mod.escape(r.get("entity_name") or "")
        http_method = html_mod.escape(r.get("http_method") or "")
        http_path = html_mod.escape(r.get("http_path") or "")
        http_status = r.get("http_status") or ""
        duration = r.get("duration_ms") or ""
        ip = html_mod.escape(r.get("ip_address") or "")
        before_val = r.get("before_value") or ""
        after_val = r.get("after_value") or ""
        request_body = r.get("request_body") or ""

        detail_parts = []
        if rtype == "operation":
            if entity_name:
                detail_parts.append(f"名称: {entity_name}")
            if before_val:
                detail_parts.append(f"改前: {html_mod.escape(str(before_val)[:80])}")
            if after_val:
                detail_parts.append(f"改后: {html_mod.escape(str(after_val)[:80])}")
        elif rtype == "scheduler":
            # 定时任务执行：展示 after_value 中的 trigger/status/duration/error
            try:
                av = json.loads(after_val) if isinstance(after_val, str) else (after_val or {})
            except (ValueError, TypeError):
                av = {}
            if isinstance(av, dict):
                if entity_name:
                    detail_parts.append(f"报表: {entity_name}")
                trigger_map = {"scheduler": "定时", "manual": "手动", "misfire": "补跑"}
                trig = av.get("trigger")
                if trig:
                    detail_parts.append(f"触发: {trigger_map.get(trig, trig)}")
                st = av.get("status")
                if st:
                    detail_parts.append(f"结果: {'成功' if st == 'success' else '失败'}")
                if av.get("duration_ms") is not None:
                    detail_parts.append(f"耗时: {av['duration_ms']}ms")
                err = av.get("error")
                if err:
                    detail_parts.append(f"错误: {html_mod.escape(str(err)[:100])}")
                if av.get("policy") == "skip" and "missed_at" in av:
                    detail_parts.append("跳过（推进到下次计划）")
        elif rtype in ("web_access", "api"):
            detail_parts.append(f"{http_method} {http_path}")
            if http_status:
                detail_parts.append(f"状态: {http_status}")
            if duration:
                detail_parts.append(f"耗时: {duration}ms")
            if ip:
                detail_parts.append(f"IP: {ip}")
            if request_body:
                detail_parts.append(f"请求: {html_mod.escape(str(request_body)[:200])}")
        detail_html = " | ".join(detail_parts) if detail_parts else "-"

        rows_html += f"""<tr>
      <td style="white-space:nowrap">{html_mod.escape(ts)}</td>
      <td><span class="audit-type audit-type-{rtype}">{type_label}</span></td>
      <td>{user}</td>
      <td>{action}</td>
      <td>{entity_type}</td>
      <td style="overflow:hidden;text-overflow:ellipsis">{detail_html}</td>
    </tr>"""
    if not rows_html:
        rows_html = build_empty_row_html(6, "暂无匹配的审计日志")

    qs = urllib.parse.urlencode({k: v for k, v in filters.items() if v})
    qs_amp = qs.replace("&", "&amp;") if qs else ""
    page_url_base = f"/audit?{qs_amp}"
    pagination = build_pagination_html(
        report_id=0,
        current=page,
        total_pages=total_pages,
        page_size=page_size,
        total_rows=total,
        page_url_base=page_url_base,
    )

    export_qs = urllib.parse.urlencode({**{k: v for k, v in filters.items() if v}, "export": "csv"})

    extra_css = """
    .audit-filters { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }
    .audit-filters label { font-size:13px; color:#475569; display:flex; flex-direction:column; gap:2px; }
    .audit-filters input, .audit-filters select { padding:6px 10px; border:1px solid #e2e8f0; border-radius:6px; font-size:14px; }
    .audit-filters input:focus, .audit-filters select:focus { outline:none; border-color:#4f46e5; box-shadow:0 0 0 3px rgba(79,70,229,0.1); }
    .audit-filters .filter-btns { display:flex; gap:8px; align-items:flex-end; }
    .audit-type { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; }
    .audit-type-operation { background:#ede9fe; color:#5b21b6; }
    .audit-type-web_access { background:#dbeafe; color:#1e40af; }
    .audit-type-api { background:#d1fae5; color:#065f46; }
    .audit-type-scheduler { background:#fef3c7; color:#92400e; }
    .date-shortcuts { display:flex; gap:4px; align-items:flex-end; }
    .audit-actions { display:flex; gap:10px; margin-bottom:16px; }
    .audit-info { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; font-size:14px; color:#64748b; }
    """

    extra_js = r"""
    function setAuditDateRange(range) {
      var now = new Date();
      function fmt(d) { return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'); }
      var dateFrom, dateTo, y;
      switch(range) {
        case 'today':
          dateFrom=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
        case 'yesterday':
          y=new Date(now);y.setDate(y.getDate()-1);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),23,59)); break;
        case 'last7':
          y=new Date(now);y.setDate(y.getDate()-6);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
        case 'last30':
          y=new Date(now);y.setDate(y.getDate()-29);
          dateFrom=fmt(new Date(y.getFullYear(),y.getMonth(),y.getDate(),0,0));
          dateTo=fmt(new Date(now.getFullYear(),now.getMonth(),now.getDate(),23,59)); break;
      }
      document.querySelector('input[name="date_from"]').value=dateFrom;
      document.querySelector('input[name="date_to"]').value=dateTo;
    }
    function confirmClean() {
      if(!confirm('确定要删除当前筛选条件下的所有审计日志吗？此操作不可恢复。')) return;
      var form=document.querySelector('.audit-filters form');
      var input=document.createElement('input');
      input.type='hidden';input.name='action';input.value='clean';
      form.appendChild(input);
      form.method='post';
      form.submit();
    }
    """

    sidebar_html = _build_sidebar_html("audit")
    # 批次6#28：公共 CSS 走外链管线，审计页特有样式并入 extra_css 段
    audit_css_url, _ = _get_common_asset_urls()
    if audit_css_url:
        audit_common_assets = f'<link rel="stylesheet" href="{audit_css_url}">'
    else:
        audit_common_assets = f"<style>{_COMMON_CSS}</style>"
    html = _PAGE_HEADER_TEMPLATE.substitute(
        title=_get_branding_prefix() + "SqlReport - 审计日志",
        sidebar_bootstrap=_SIDEBAR_BOOTSTRAP_JS,
        favicon_link='<link rel="icon" href="/favicon.ico">',
        common_css_assets=audit_common_assets,
        extra_css=extra_css.replace("$", "$$"),
        sidebar=sidebar_html,
    )

    if message:
        html += build_flash_html(message, is_error="成功" not in message)

    size_info = ""
    if db_size > 0:
        for unit in ("B", "KB", "MB", "GB"):
            if db_size < 1024:
                size_info = f"{db_size:.1f} {unit}"
                break
            db_size /= 1024
        size_info = f'<span>数据库大小: {size_info}</span>'

    html += f"""
<div class="page-head">
  <div>
    <h1>审计日志</h1>
    <div class="sub">共 {total} 条记录，第 {page}/{total_pages} 页{size_info}</div>
  </div>
  <div class="actions">
    <a href="/audit?{export_qs}" class="btn btn-secondary">导出 CSV</a>
    <button type="button" class="btn btn-danger" onclick="confirmClean()">清理过期</button>
  </div>
</div>
<div class="audit-filters filterbar">
  <form method="get" action="/audit" style="display:contents">
    <label>类型: <select name="type">{type_html}</select></label>
    <label>操作者: <input type="text" name="session_user" value="{html_mod.escape(session_user_val)}" placeholder="操作者"></label>
    <label>关键字: <input type="text" name="keyword" value="{html_mod.escape(keyword_val)}" placeholder="关键字{FILTER_HINT_SUFFIX}"></label>
    <div class="date-shortcuts">{range_btns}</div>
    <label>从: <input type="datetime-local" name="date_from" value="{html_mod.escape(date_from)}"></label>
    <label>到: <input type="datetime-local" name="date_to" value="{html_mod.escape(date_to)}"></label>
    <div class="filter-btns">
      <button type="submit" class="btn btn-sm btn-primary">筛选</button>
      {render_filter_help()}
    </div>
  </form>
</div>
<div class="table-wrap">
  <table>{table_header}<tbody>{rows_html}</tbody></table>
</div>
{pagination}
<script>{extra_js}</script>"""

    html += _render_common_footer()
    return html


# ===================================================================


def build_api_urls_section_html(api_endpoints: list[dict], base_url: str,
                                return_to: str = None) -> str:
    """
    渲染报表详情「接口」页签内容（R2-D：委托 build_api_endpoints_list_html
    输出 api-row 卡片行，与列表页同一实现，禁止第二套体系）。

    参数:
        api_endpoints: API 端点列表
        base_url: 服务器基础 URL（如 http://localhost:8080）
        return_to: toggle 后回跳地址；None 时按首个端点所属报表回跳 /report?id=N
    """
    if not api_endpoints:
        return ""
    if return_to is None:
        first_rid = int(api_endpoints[0].get("report_id") or 0)
        if first_rid:
            return_to = f"/report?id={first_rid}"
    return build_api_endpoints_list_html(api_endpoints, base_url=base_url,
                                          return_to=return_to, desc_full=True,
                                          wrap_section=False)


def build_collapse_section_html(title: str, content: str,
                                default_hidden: bool = True,
                                extra_style: str = "",
                                button_text: str = None,
                                multiline: bool = False,
                                mem_key: str = None) -> str:
    """构建折叠区骨架 HTML（debug-info 样式）。

    标题按钮: class="debug-toggle" onclick="toggleSection(this, '标题')"。
    按钮初始文案为 "▶ 标题"（备注等特殊形态经 button_text 覆盖）。
    multiline=True 时外层按多行排版输出（折叠区内容本身多行的场景），
    内容行的缩进由调用方在 content 中自带，保证与现状逐字符一致。

    mem_key 参数保留仅为兼容调用方（T7.11 三态废除：不再输出
    data-mem-key/data-default-hidden 与「自动/展开/折叠」控件；折叠态
    由 default_hidden 决定，普通 toggleSection 切换）。
    """
    style_attr = f' style="{extra_style}"' if extra_style else ""
    hidden_cls = " hidden" if default_hidden else ""
    btn_text = button_text if button_text is not None else f"▶ {title}"
    mem_attrs = ""
    mem_ctl = ""
    if multiline:
        return (f'<div class="debug-info"{mem_attrs}{style_attr}>\n'
                f'<button class="debug-toggle" onclick="toggleSection(this, \'{title}\')" type="button">{btn_text}</button>\n'
                f'<div class="debug-content{hidden_cls}">\n'
                f'{content}\n'
                f'</div>\n'
                f'{mem_ctl}\n'
                f'</div>')
    return (f'<div class="debug-info"{mem_attrs}{style_attr}>'
            f'<button class="debug-toggle" onclick="toggleSection(this, \'{title}\')" type="button">{btn_text}</button>'
            f'<div class="debug-content{hidden_cls}">{content}</div>'
            f'{mem_ctl}'
            '</div>')


def _build_api_url_row(code_id: str, label: str, url_path: str,
                       kind: str, url_value: str,
                       disabled: bool = False,
                       disabled_hint: str = "",
                       edit_url: str = "") -> str:
    """构建一行 API URL 展示（标签 + code + 复制按钮，样式与 Debug 信息模块一致）。

    disabled=True 时行置灰：地址保留可见（用户能知道该能力存在但未启用）、
    复制按钮禁用、title 悬浮提示原因，并提供「去开启」链接（新窗口打开接口配置页）。
    """
    code_style = ('font-size:12px;color:#64748b;text-decoration:line-through;'
                  if disabled else
                  'font-size:12px;background:#f1f5f9;padding:2px 6px;'
                  'border-radius:4px;color:#4f46e5')
    if disabled:
        copy_btn = ('<button type="button" disabled '
                    'class="btn-mini btn-mini-disabled">复制</button>')
        fix_link = (f'<a href="{_escape(edit_url)}" target="_blank" rel="noopener" '
                    f'title="在接口配置中开启该能力" '
                    f'style="white-space:nowrap">去开启 ↗</a>'
                    if edit_url else "")
    else:
        copy_btn = (f'<button onclick="copyToClipboard(\'{code_id}\')" '
                    f'class="btn-mini btn-mini-solid btn-mini-primary">复制</button>')
        fix_link = ""
    return (f'<div style="margin:2px 0;opacity:{"0.55" if disabled else "1"}">'
            f'<span>{label}</span> '
            f'<code id="{code_id}" class="api-url-code" data-path="{_escape(url_path)}" '
            f'data-kind="{kind}" style="{code_style}" '
            f'title="{_escape(disabled_hint) if disabled else ""}">{_escape(url_value)}</code> '
            f'{copy_btn} {fix_link}'
            f'</div>')



def build_state_span(text: str, state: str = "ok", bold: bool = True) -> str:
    """构建状态文字徽章 span HTML。

    state: ok=绿 #059669 / warn=红 #dc2626 / muted=灰 #64748b（批次6#27d 对比度加深）。
    bold=False 时省略 font-weight（个别场景原样式无加粗，保持现状）。
    """
    colors = {"ok": "#059669", "warn": "#dc2626", "muted": "#64748b"}
    color = colors.get(state, "#059669")
    weight = ";font-weight:600" if bold else ""
    return f'<span style="color:{color}{weight}">{text}</span>'


def _api_endpoint_url(report_id, ep_id, action: str = "edit") -> str:
    """拼装 API 端点配置页 URL（/config/reports/{report_id}/api_endpoints/{ep_id}/{action}）。"""
    return f"/config/reports/{report_id}/api_endpoints/{ep_id}/{action}"


# ---------------------------------------------------------------------------
# 报表定时任务（scheduler T4：管理页 + 列表徽标）
# ---------------------------------------------------------------------------

_SCHED_MISFIRE_LABELS = {"skip": "跳过", "run_once": "补跑一次"}


def build_schedule_flags_badge_html(sched_flag, keepalive_flag) -> str:
    """报表列表名称后的功能徽标：{_icon("calendar")}=已配定时、{_icon("refresh")}=已开保活（纯文本符号）。

    两项均未启用时返回空串（不渲染单元格内容变化，仅追加徽标）。
    """
    parts = ""
    if int(sched_flag or 0) == 1:
        parts += f'<span title="已配置定时执行">{_icon("calendar")}</span>'
    if int(keepalive_flag or 0) == 1:
        parts += f'<span title="已开启缓存保活">{_icon("refresh")}</span>'
    if parts:
        parts = f' <span>{parts}</span>'
    return parts


def _format_schedule_plan(sched: dict) -> str:
    """任务计划描述文本（类型列 + 计划列共用数据源）。"""
    stype = sched.get("schedule_type")
    if stype == "daily":
        return f'每天 {sched.get("daily_time") or ""}'
    minutes = int(sched.get("interval_minutes") or 0)
    return f"每 {minutes} 分钟"


def build_report_schedule_summary_html(report_id, scheds: list) -> str:
    """报表编辑页「④ 调度与保活」卡内的关联定时任务只读摘要（spec page-report-edit）。

    scheds 为该报表已关联的任务（复用 db.get_all_schedules 的 report_ids 过滤，
    不新建第二套查询语义）。无关联任务时输出静态提示；两种情况都给出真实的
    「新建调度」入口 /config/scheduler/new?report_id=N（新建页按该参数预选报表）。
    """
    if not report_id:
        return ""
    new_url = f"/config/scheduler/new?report_id={report_id}"
    if scheds:
        rows = ""
        for s in scheds:
            on = int(s.get("enabled", 1) or 0) == 1
            state = "启用" if on else "停用"
            badge = "badge-ok" if on else "badge-neutral"
            sid = int(s.get("id") or 0)
            rows += (
                '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;'
                'font-size:13px;padding:7px 0;border-bottom:1px dashed var(--line)">'
                f'<a href="/config/scheduler/{sid}/edit" style="font-weight:600;'
                f'color:var(--brand);text-decoration:none">'
                f'{_escape(s.get("name") or "未命名任务")}</a>'
                f'<span class="badge {badge}">{state}</span>'
                f'<span class="muted">{_escape(_format_schedule_plan(s))}</span>'
                '</div>')
        body = (rows + '<p>'
                '命中排除规则（静默窗口）时该次执行跳过；多任务可同时绑定本报表。</p>')
    else:
        body = ('<p>'
                '本报表尚未关联定时任务；新建后可按间隔或每天定时批量刷新本报表缓存。</p>')
    return (f'<div style="margin:0 0 12px;padding:10px 12px;background:var(--bg-subtle);'
            f'border:1px dashed var(--line-strong);border-radius:var(--r-sm)">{body}'
            f'<div>'
            f'<a class="btn btn-outline btn-sm" href="{new_url}">+ 新建调度</a></div></div>')


def _format_schedule_last_result(sched: dict) -> str:
    """上次结果单元格：状态 + 耗时（含失败摘要 title 提示）。"""
    status = sched.get("last_status")
    duration = sched.get("last_duration_ms")
    dur_text = f" ({duration}ms)" if duration is not None else ""
    if status == "success":
        return f'<span title="上次执行成功">{_icon("check")} 成功{_escape(dur_text)}</span>'
    if status == "fail":
        err = (sched.get("last_error") or "").replace('"', "&quot;")
        summary = _escape((sched.get("last_error") or "")[:60])
        return (f'<span style="cursor:help" '
                f'title="{err}">{_icon("x")} 失败{dur_text}：{summary}</span>')
    if status == "skipped":
        return f'<span title="排除规则命中（静默窗口），本次未执行">{_icon("x")} 静默跳过</span>'
    return '<span>— 未执行</span>'


def build_scheduler_page_html(schedules: list, scheduler_enabled: bool) -> str:
    """构建 /config/scheduler 任务管理页主体（纯数据 → HTML，无 DB 调用）。

    表格列对齐原型 page-scheduler（7 列）：任务名 / 关联报表 / 计划 /
    下次执行 / 上次结果 / 状态 / 操作。全局停用时顶部显示横幅（B17，
    页面仍可查看）。执行历史不在此页重复渲染，到审计日志查询。
    """
    banner = ""
    if not scheduler_enabled:
        banner = ('<div class="flash-warn" style="padding:10px 14px;'
                  'border-radius:8px;margin-bottom:12px">'
                  '⛔ 定时调度全局已停用（app_config.json → scheduler.enable=false），'
                  '以下配置仅展示，不会自动执行</div>')
    rows = ""
    for s in schedules:
        sid = s["id"]
        task_name = _escape(s.get("name") or f"#{sid}")
        report_names = s.get("report_names") or []
        reports_cell = (", ".join(_escape(r) for r in report_names)
                        if report_names else
                        '<span>无关联报表</span>')
        badges = ""
        if s.get("exclusions"):
            badges += f' <span title="已配置执行排除（静默窗口）">{_icon("x")}</span>'
        if int(s.get("audit_enabled", 0) or 0):
            badges += f' <span title="执行审计已开启">{_icon("edit")}</span>'
        enabled = int(s.get("enabled", 1))
        fail_count = int(s.get("fail_count", 0))
        status_cell = (build_state_span("启用")
                       if enabled else
                       build_state_span("停用", "muted"))
        if fail_count >= 5 and enabled:
            status_cell += ' <span title="连续失败达上限，自动派发已熔断；手动成功后恢复">🔥熔断</span>'
        next_at = s.get("next_run_at")
        next_cell = (time.strftime("%Y-%m-%d %H:%M", time.localtime(next_at))
                     if next_at else
                     '<span>—</span>')
        misfire_label = _SCHED_MISFIRE_LABELS.get(
            s.get("misfire_policy"), s.get("misfire_policy") or "")
        toggle_label = "停用" if enabled else "启用"
        toggle_cls = "btn-outline" if enabled else "btn-success"
        rows += f"""<tr>
  <td><a href="/config/scheduler/{sid}/edit">{task_name}</a>{badges}</td>
  <td>{reports_cell}</td>
  <td>{_escape(_format_schedule_plan(s))}<span>错过{_escape(misfire_label)}</span></td>
  <td>{next_cell}</td>
  <td>{_format_schedule_last_result(s)}</td>
  <td style="white-space:nowrap">{status_cell}</td>
  <td class="ops-cell" style="white-space:nowrap">
    <form method="post" action="/config/scheduler/run/{sid}" style="display:inline" onsubmit="this.querySelector('button').disabled=true">
      <button type="submit" class="btn btn-primary btn-sm">立即执行</button>
    </form>
    <form method="post" action="/config/scheduler/toggle/{sid}" style="display:inline">
      <button type="submit" class="btn {toggle_cls} btn-sm">{toggle_label}</button>
    </form>
    {build_delete_form_html(f"/config/scheduler/delete/{sid}", f"确定删除任务「{_escape(s.get('name') or sid)}」？", button_cls="btn-sm")}
  </td>
</tr>"""
    if not schedules:
        rows = ('<tr><td colspan="7" class="empty-state">'
                '暂无定时任务 — 点击右上角「新建任务」创建</td></tr>')
    return (banner
            + f'<div class="section"><div class="section-title"><span>{_icon("calendar")} 报表定时任务</span>'
              '<span class="actions">'
              + _link_btn("/config/reports", "前往报表编辑页",
                          "btn btn-outline btn-sm")
              + '</span></div>'
            + '<div class="table-wrap"><table><thead><tr>'
              '<th>任务名</th><th>关联报表</th><th>计划</th>'
              '<th>下次执行</th>'
              '<th>上次结果</th>'
              '<th>状态</th><th>操作</th>'
              '</tr></thead><tbody>' + rows + '</tbody></table></div>'
            '<p class="muted">'
            '徽标语义：成功/失败/熔断/静默窗口均为「颜色+文字」双编码；'
            '任务级审计默认关，开启后显示「' + _icon("edit") + '」徽标。'
            '执行历史不在本页重复展示，请到审计日志查询。</p></div>')


_EXCL_EDITOR_JS = """
(function(){
  var DOWS = ["mon","tue","wed","thu","fri","sat","sun"];
  var DOW_LABELS = {mon:"一",tue:"二",wed:"三",thu:"四",fri:"五",sat:"六",sun:"日"};

  function el(html){var t=document.createElement("template");
    t.innerHTML=html.trim();return t.content.firstChild;}
  function rulesBox(){return document.getElementById("excl-rules");}
  function hiddenBox(){return document.getElementById("excl-json");}
  function sourceBox(){return document.getElementById("excl-source");}

  function leafFields(type,data){
    data=data||{};
    var w="padding:4px 6px;border:1px solid #cbd5e1;border-radius:6px";
    if(type==="dow"){
      var h="",set=data.in||[];
      for(var i=0;i<DOWS.length;i++){var d=DOWS[i];
        var ck=set.indexOf(d)>=0?" checked":"";
        h+='<label>'
          +'<input type="checkbox" class="excl-dow" value="'+d+'"'+ck+">"
          +DOW_LABELS[d]+"</label>";}
      return '<span>'+h+'</span>';
    }
    if(type==="tod")
      return '<span>从 <input type="time" class="excl-from" value="'
        +(data.from||"21:00")+'" style="'+w+'"> 到 <input type="time" '
        +'class="excl-to" value="'+(data.to||"09:00")+'" style="'+w
        +'">（含边界，可跨午夜）</span>';
    if(type==="date")
      return '<span>日期（逗号分隔 YYYY-MM-DD）<input type="text" '
        +'class="excl-on" value="'+(data.on||[]).join(",")+'" style="'
        +w+';width:220px"></span>';
    return '<span>自 <input type="date" class="excl-from" value="'
      +(data.from||"")+'" style="'+w+'"> 至 <input type="date" '
      +'class="excl-to" value="'+(data.to||"")+'" style="'+w
      +'">（闭区间）</span>';
  }

  function nodeHtml(kind,type){
    var head;
    if(kind==="group"){
      head='<select class="excl-op" style="padding:3px 5px;border:1px solid '
        +'#cbd5e1;border-radius:6px"><option value="OR">任一命中（OR）</option>'
        +'<option value="AND">全部满足（AND）</option></select>';
    }else{
      head='<select class="excl-type" onchange="exclRebuild(this)">'
        +'<option value="dow">星期（dow）</option>'
        +'<option value="tod">每日时段（tod）</option>'
        +'<option value="date">指定日期（date）</option>'
        +'<option value="date_range">日期区间（date_range）</option>'
        +'</select><span class="excl-fields"></span>';
    }
    var del=' onclick="exclDel(this)"';
    return '<div class="excl-node" data-kind="'+kind+'"'
      +(type?' data-type="'+type+'"':'')
      +' style="border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;'
      +'margin:6px 0;background:#fff"><div class="rule-row" style="display:flex;gap:8px;'
      +'align-items:center;flex-wrap:wrap;margin-bottom:0">'+head
      +'<button type="button" class="btn btn-outline btn-sm"'+del+'>删除</button></div>'
      +'<div class="excl-children"></div></div>';
  }

  function addChild(containerId,kind,json){
    var box=document.getElementById(containerId)||rulesBox();
    var isRoot=box===rulesBox();
    var type=isRoot||kind==="group"?null:(json?json.type:"dow");
    var div=el(nodeHtml(kind,type));
    if(kind==="leaf"){
      div.querySelector(".excl-type").value=type;
      div.querySelector(".excl-fields").innerHTML=
        leafFields(type,json);
    }else{
      var op=json&&json.op?json.op:(isRoot?"OR":"AND");
      if(isRoot)op="OR"; // 根固定 OR：多规则并行语义（规格 §4.5）
      div.querySelector(".excl-op").value=op;
      var kids=(json&&json.children)||[];
      for(var i=0;i<kids.length;i++)
        addChildInner(div.querySelector(".excl-children"),kids[i]);
    }
    box.appendChild(div);return div;
  }
  function addChildInner(container,json){
    var kind=json&&json.op?"group":"leaf";
    var div=el(nodeHtml(kind,kind==="leaf"?json.type:null));
    if(kind==="group"){
      div.querySelector(".excl-op").value=json.op;
      var kids=json.children||[];
      for(var i=0;i<kids.length;i++)
        addChildInner(div.querySelector(".excl-children"),kids[i]);
    }else{
      div.setAttribute("data-type",json.type);
      div.querySelector(".excl-type").value=json.type;
      div.querySelector(".excl-fields").innerHTML=leafFields(json.type,json);
    }
    container.appendChild(div);return div;
  }

  window.exclAddRule=function(){addChild("","leaf",{type:"dow"});};
  window.exclAddGroup=function(){addChild("","group",{op:"AND",children:[]});};
  window.exclAddChild=function(btn){
    addChildInner(btn.closest(".excl-node").querySelector(".excl-children"),
                  {type:"dow"});
  };
  window.exclAddSubgroup=function(btn){
    addChildInner(btn.closest(".excl-node").querySelector(".excl-children"),
                  {op:"AND",children:[]});
  };
  window.exclDel=function(btn){btn.closest(".excl-node").remove();};
  window.exclRebuild=function(sel){
    var node=sel.closest(".excl-node");
    node.setAttribute("data-type",sel.value);
    node.querySelector(".excl-fields").innerHTML=leafFields(sel.value,null);
  };

  function serializeNode(div){
    if(div.getAttribute("data-kind")==="group"){
      var op=div.querySelector(":scope > div > .excl-op").value,kids=[];
      div.querySelectorAll(":scope > .excl-children > .excl-node")
        .forEach(function(c){kids.push(serializeNode(c));});
      return {op:op,children:kids};
    }
    var type=div.getAttribute("data-type"),n={type:type};
    if(type==="dow"){var arr=[];
      div.querySelectorAll(".excl-dow:checked").forEach(function(c){arr.push(c.value);});
      n.in=arr;}
    else if(type==="tod"||type==="date_range"){
      n.from=div.querySelector(".excl-from").value;
      n.to=div.querySelector(".excl-to").value;}
    else{n.on=div.querySelector(".excl-on").value.split(",")
      .map(function(s){return s.trim();}).filter(Boolean);}
    return n;
  }
  function serializeAll(){
    var kids=[];
    rulesBox().querySelectorAll(":scope > .excl-node")
      .forEach(function(c){kids.push(serializeNode(c));});
    if(!kids.length)return "";
    return JSON.stringify({op:"OR",children:kids});
  }

  function showMsg(text){
    var m=document.getElementById("excl-msg");
    m.textContent=text;m.style.display=text?"block":"none";
  }

  window.exclToggleSource=function(){
    var src=sourceBox();
    if(src.style.display==="none"){
      try{src.value=serializeAll()||hiddenBox().value||"";}catch(e){}
      src.style.display="block";showMsg("");
    }else{
      var raw=src.value.trim();
      if(raw){
        try{
          var tree=JSON.parse(raw);
          if(!tree||typeof tree!=="object")throw new Error("根必须是对象");
          rulesBox().innerHTML="";
          var kids=tree.op==="OR"&&tree.children?tree.children:[tree];
          for(var i=0;i<kids.length;i++)addChildInner(rulesBox(),kids[i]);
        }catch(e){showMsg("JSON 无效："+e.message+"，已保留源码模式");return;}
      }
      src.style.display="none";showMsg("");
    }
  };

  function init(){
    var form=hiddenBox().closest("form");
    form.addEventListener("submit",function(){
      if(sourceBox().style.display!=="none")
        hiddenBox().value=sourceBox().value.trim();
      else
        hiddenBox().value=serializeAll();
    });
    var raw=(hiddenBox().value||"").trim();
    if(!raw)return;
    try{
      var tree=JSON.parse(raw);
      var kids=tree.op==="OR"&&tree.children?tree.children:[tree];
      for(var i=0;i<kids.length;i++)addChildInner(rulesBox(),kids[i]);
    }catch(e){showMsg("既有排除规则不是合法 JSON，请点「源码」查看修正");}
  }
  if(document.readyState==="loading")
    document.addEventListener("DOMContentLoaded",init);
  else init();
})();
"""


def build_scheduler_task_form_html(prefill: dict | None,
                                   reports: list) -> str:
    """构建「新建/编辑定时任务」表单（spec §7.2/§7.3，多报表组合）。

    prefill 为现有任务 dict（含 report_ids）时预填并带 edit_id 隐藏域；
    reports 为全部报表列表（id/name），用于关联报表多选框。排除规则为
    前端内联 JS 树编辑器（增删规则/叶子类型/嵌套组，产出 JSON 写入隐藏
    域 name="exclusions"；另提供源码模式直接改 JSON），后端仍以
    validate_exclusions 校验兜底。
    """
    pf = prefill or {}
    edit_id = pf.get("id")
    name = pf.get("name") or ""
    stype = pf.get("schedule_type") or "interval"
    interval = pf.get("interval_minutes") if pf.get("interval_minutes") \
        is not None else 60
    daily = pf.get("daily_time") or "08:00"
    policy = pf.get("misfire_policy") or "skip"
    enabled_checked = "checked" if int(pf.get("enabled", 1) or 0) else ""
    audit_checked = "checked" if int(pf.get("audit_enabled", 0) or 0) else ""
    selected = set(pf.get("report_ids") or [])
    binding_map = {int(k): int(v)
                   for k, v in (pf.get("binding_enabled") or {}).items()}
    exclusions = pf.get("exclusions") or ""
    type_opts = "".join(
        f'<option value="{t}"{" selected" if t == stype else ""}>'
        f'{"每日" if t == "daily" else "间隔"}</option>'
        for t in ("interval", "daily"))
    policy_opts = "".join(
        f'<option value="{p}"{" selected" if p == policy else ""}>'
        f'{_SCHED_MISFIRE_LABELS.get(p, p)}</option>'
        for p in ("skip", "run_once"))
    # 关联报表：绑定 | 报表 | 参与执行 三列表格（未绑定行不渲染 bind_enabled 输入，根治误勾选）
    _rows = []
    for r in reports:
        rid = r["id"]
        bound = rid in selected
        if bound:
            pchecked = "checked" if binding_map.get(rid, 1) else ""
            bind_cell = (f'<label class="check-inline">'
                         f'<input type="checkbox" name="bind_enabled_{rid}" '
                         f'value="1" {pchecked}> 参与执行</label>')
        else:
            bind_cell = '<span class="muted">—</span>'
        _rows.append(
            f'<tr>'
            f'<td class="bind-col"><input type="checkbox" name="report_ids" '
            f'value="{rid}"{" checked" if bound else ""} '
            f'onchange="syncBindRow(this)"></td>'
            f'<td>{_escape(r.get("name") or rid)} (#{rid})</td>'
            f'<td class="bind-cell" data-rid="{rid}">{bind_cell}</td>'
            f'</tr>')
    report_rows_html = "".join(_rows)
    edit_hidden = (f'<input type="hidden" name="edit_id" value="{edit_id}">'
                   if edit_id else "")
    excl_editor = f'''
    <p>任一规则命中则本次不执行；解析失败按「不排除」处理（后端 validate_exclusions 兜底）。与报表嵌套筛选结构不同，勿混用。</p>
    <div id="excl-rules" class="rule-group"></div>
    <textarea id="excl-source" rows="5" style="display:none"></textarea>
    <div id="excl-msg" style="display:none"></div>
    <input type="hidden" name="exclusions" id="excl-json" value="{_escape(exclusions)}">'''
    interval_disp = "" if stype == "interval" else ' style="display:none"'
    daily_disp = "" if stype == "daily" else ' style="display:none"'
    # spec page-scheduler-new：grid-2（左「计划」卡｜右「关联报表」卡）→
    # 独立「排除规则」卡（仍在主 form 内）→ formbar。按钮协议与 POST 字段不变。
    return f'''<form method="post" action="/config/scheduler/save" class="config-form sched-form">
  {edit_hidden}
  <div class="grid-2 span-full">
    <div class="card">
      <div class="card-head"><h2>计划</h2></div>
      <label>任务名<input type="text" name="name" value="{_escape(name)}" required></label>
      <label>调度类型<select name="schedule_type" onchange="syncSchedType()">{type_opts}</select></label>
      <div class="schedule-row span-full" id="row-interval"{interval_disp}><label>间隔（分钟）<input type="number" name="interval_minutes" value="{int(interval)}" min="1"></label></div>
      <div class="schedule-row span-full" id="row-daily"{daily_disp}><label>每日时刻<input type="time" name="daily_time" value="{_escape(daily)}"></label></div>
      <label>错过策略<select name="misfire_policy">{policy_opts}</select></label>
      <div>
        <label class="check-inline"><input type="checkbox" name="schedule_enabled" {enabled_checked}> 启用</label>
        <label class="check-inline"><input type="checkbox" name="audit_enabled" {audit_checked}> 记录执行审计</label>
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h2>关联报表（按序执行）</h2></div>
      <label>关联报表<span class="field-hint">勾选=绑定该报表；「参与执行」未勾选的报表在任务中停用（S10）</span></label>
      <div class="sched-reports-wrap">
        <table class="sched-reports">
          <thead><tr><th>绑定</th><th>报表</th><th>参与执行</th></tr></thead>
          <tbody>{report_rows_html}</tbody>
        </table>
      </div>
    </div>
  </div>
  <div class="card span-full">
    <div class="card-head"><h2>排除规则（静默窗口）</h2>
      <div class="actions">
        <button type="button" class="btn btn-outline btn-sm" onclick="exclAddRule()">+ 添加规则</button>
        <button type="button" class="btn btn-outline btn-sm" onclick="exclAddGroup()">+ 规则组</button>
        <button type="button" class="btn btn-outline btn-sm" onclick="exclToggleSource()">源码</button>
      </div>
    </div>
    {excl_editor}
  </div>
  <div class="formbar span-full">
    <a href="/config/scheduler" class="cancel">← 取消</a>
    <div class="right"><button type="submit" class="btn btn-primary">保存任务</button></div>
  </div>
</form>
<script>{_EXCL_EDITOR_JS}
function syncSchedType() {{
  var sel = document.querySelector('form.sched-form select[name=schedule_type]');
  if (!sel) return;
  var t = sel.value;
  document.getElementById('row-interval').style.display = (t === 'interval') ? '' : 'none';
  document.getElementById('row-daily').style.display = (t === 'daily') ? '' : 'none';
}}
function syncBindRow(cb) {{
  var cell = cb.parentNode.parentNode.querySelector('.bind-cell');
  if (cb.checked) {{
    cell.innerHTML = '<label class="check-inline"><input type="checkbox" name="bind_enabled_' + cb.value + '" value="1" checked> 参与执行</label>';
  }} else {{
    cell.innerHTML = '<span class="muted">—</span>';
  }}
}}
syncSchedType();
</script>'''


def _api_url_variants(base_url: str, url_path: str) -> tuple[str, str, str]:
    """计算 API 地址三变体（完整/全量/静态），与内联拼接输出逐字符一致。"""
    return (f"{base_url}{url_path}",
            f"{base_url}{url_path}{FETCH_ALL_QUERY}",
            f"{base_url}{url_path}{static_cache.JSON_SUFFIX}")



def _build_api_description_html(ep: dict) -> str:
    """构建接口说明折叠区 HTML（api-desc-markdown T3）。

    说明为纯展示 Markdown 源文本：经 render_markdown() 渲染为已消毒的 HTML
    （含 ```mermaid 时产出 <pre class="mermaid">，由前端按需渲染），外包
    .md-body 排版容器，再构建「接口说明」折叠区（默认展开，三态记忆键
    api_desc_fold_{endpoint_id}）。空说明返回空串（不渲染任何块）。
    """
    desc_raw = (ep.get("description") or "").strip()
    if not desc_raw:
        return ""
    desc_html = markdown_render.render_markdown(desc_raw)
    desc_html = f'<div class="md-body">{desc_html}</div>' if desc_html else ""
    return build_collapse_section_html(
        "接口说明", desc_html, default_hidden=False,
        button_text="▼ 接口说明", mem_key=f"api_desc_fold_{ep['id']}")


