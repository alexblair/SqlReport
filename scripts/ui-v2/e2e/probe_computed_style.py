#!/usr/bin/env python3
"""probe_computed_style.py — 单页 UI 取证探针（无头 Chrome 计算样式 + 滚动几何 + 截图）。

为什么需要它（2026-10-09 实测复盘）：修复「② SQL 缺滚动条」时，把一条 CSS 判断变成
浏览器实测证据，会话在**无头 Chrome 的环境漂移**上试错了约 16 步（113 步的 14%），并
制造了全会话最贵的一步。漂移源全是环境配方、与业务无关：

  - `--headless=new` 在本机 `--dump-dom` / `--screenshot` 直接挂起；只有 `--headless=old` 稳定；
  - 每次换**全新的** `--user-data-dir` 会间歇性挂起 → 复用同一个 profile，失败自动重试即热；
  - `--window-size` / `--virtual-time-budget` 与 `--screenshot` 同用实测挂起；
  - `subprocess(capture_output=PIPE)` 会因 Chrome fork 的子进程不关管道而**假挂起**（等到 timeout）→ 必须重定向到文件；
  - 页面自身 `<script>`（fetch/轮询）让 `--dump-dom` 等不到 load → 取证前剥离脚本；
  - 用非贪婪正则抽 `.card` 只会截到 `card-head` → 需按 `<div>` 配平抽取（`--focus-card`）；
  - dump 出来的 DOM 里，注入脚本源码本身含 `PROBE_JSON=` 字面量 → 必须锚定 `<pre>` 里的结果再解析。

业务页面如何渲染成 HTML 由调用方负责（最小骨架见
`docs/compose/knowledge/08-testing-conventions.md` 易踩坑 #28）。

用法（仓库根执行）：
    venv/bin/python scripts/ui-v2/e2e/probe_computed_style.py \
        --html run-logs/page.html \
        --selector 'textarea[name="sql_query"]' --selector 'textarea[name="memo"]' \
        --screenshot run-logs/page.png --out run-logs/page.probe.json
    venv/bin/python scripts/ui-v2/e2e/probe_computed_style.py --selftest

产物一律落 `run-logs/`（已 gitignore）；本脚本不删任何文件（硬性 #14）。
退出码：0 = 探针成功；1 = 重试后仍拿不到结果；2 = 参数/环境错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE = REPO / "run-logs" / "chrome-profile"
CHROME_CANDIDATES = (
    "/opt/google/chrome/chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

# 只匹配探针写进 <pre id="probe-result"> 的结果，避开注入脚本源码里的 'PROBE_JSON=' 字面量
PROBE_RESULT_RE = re.compile(r"PROBE_JSON=(\{.*?\})</pre>", re.S)

PROBE_JS_TEMPLATE = """<script>
(function(){
  var SELECTORS = %s;
  function probe(sel){
    var el = document.querySelector(sel);
    if(!el){ return {found:false, selector:sel}; }
    var cs = getComputedStyle(el);
    var o = {found:true, selector:sel, tag:el.tagName.toLowerCase(),
             cls:el.getAttribute('class')||'',
             computedOverflowX:cs.overflowX, computedOverflowY:cs.overflowY,
             display:cs.display, visibility:cs.visibility,
             clientWidth:el.clientWidth, clientHeight:el.clientHeight,
             offsetWidth:el.offsetWidth, offsetHeight:el.offsetHeight,
             scrollWidth:el.scrollWidth, scrollHeight:el.scrollHeight,
             borderBoxDelta:el.offsetWidth-el.clientWidth,
             // 滚动条槽宽 = 边框盒差 - 左右边框（textarea/input 默认有 2px 边框，
             // 直接用 offsetWidth-clientWidth 会把边框当成滚动条，2026-10-09 自检抓到）
             scrollbarGutter:el.offsetWidth-el.clientWidth
                 - parseFloat(cs.borderLeftWidth)-parseFloat(cs.borderRightWidth),
             maxScrollTop:el.scrollHeight-el.clientHeight};
    var before = el.scrollTop;
    el.scrollTop = 1000000;
    o.scrollTopAfterProgrammatic = el.scrollTop;
    el.scrollTop = before;
    return o;
  }
  var out = {url:location.href, viewport:{w:innerWidth,h:innerHeight}, probes:[]};
  for(var i=0;i<SELECTORS.length;i++){ out.probes.push(probe(SELECTORS[i])); }
  var pre = document.createElement('pre');
  pre.id = 'probe-result';
  pre.textContent = 'PROBE_JSON=' + JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


def find_chrome() -> str | None:
    """返回可用的 Chrome 可执行文件（CHROME 环境变量优先）。"""
    env = os.environ.get("CHROME")
    if env and Path(env).is_file():
        return env
    for cand in CHROME_CANDIDATES:
        if Path(cand).is_file():
            return cand
    return shutil.which("chromium") or shutil.which("google-chrome")


def strip_scripts(html: str) -> tuple[str, int]:
    """剥掉页面自身 <script>（它们发请求会让无头 Chrome 等不到 load）。"""
    return re.subn(r"<script\b.*?</script>", "", html, flags=re.S)


def parse_probe(dom: str) -> dict:
    """从 dump 出来的 DOM 里取探针 JSON（锚定 <pre>，不取脚本源码里的字面量）。"""
    m = PROBE_RESULT_RE.search(dom or "")
    if not m:
        raise ValueError("DOM 里没有探针结果（页面脚本未执行或探针被剥离）")
    return json.loads(m.group(1))


def extract_balanced_card(html: str, marker: str) -> str:
    """按 <div> 配平抽取含 marker 的 `.card`（非贪婪正则只截得到 card-head）。"""
    for m in re.finditer(r'<div class="card">', html):
        start, i, depth = m.start(), m.start(), 0
        while i < len(html):
            nxt_open = html.find("<div", i)
            nxt_close = html.find("</div>", i)
            if nxt_close == -1:
                break
            if nxt_open != -1 and nxt_open < nxt_close:
                depth += 1
                i = nxt_open + 4
            else:
                depth -= 1
                i = nxt_close + 6
                if depth == 0:
                    block = html[start:i]
                    if marker in block:
                        return block
                    break
    raise ValueError(f"未找到包含 {marker!r} 的 .card")


def build_focus_page(html: str, marker: str, width: int = 760) -> str:
    """只留公共 <style> 与目标卡片，生成便于截图/量测的聚焦页。"""
    styles = "".join(re.findall(r"<style>.*?</style>", html, re.S))
    card = extract_balanced_card(html, marker)
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">{styles}</head>'
            f'<body><div style="width:{width}px;padding:12px">{card}</div></body></html>')


def run_chrome_base(chrome: str, profile: Path) -> list[str]:
    """Chrome 公共参数（勿轻改：见 run_chrome docstring 的实测配方）。"""
    return [chrome, "--headless=old", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-first-run", f"--user-data-dir={profile}"]


def prepare_page(src_html: str, selectors: list[str], run_dir: Path, ts: str,
                 keep_scripts: bool) -> Path:
    """写出「剥脚本 + 注入探针」的工作副本，返回其路径。"""
    html, n_scripts = strip_scripts(src_html) if not keep_scripts else (src_html, 0)
    probe = PROBE_JS_TEMPLATE % json.dumps(selectors, ensure_ascii=False)
    html = html.replace("</body>", probe + "</body>", 1) if "</body>" in html else html + probe
    out = run_dir / f"probe_page_{ts}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[probe] 工作副本 -> {out}（剥离页面脚本 {n_scripts} 段）")
    return out


def run_chrome(chrome: str, url: str, profile: Path, ts: str, run_dir: Path,
               screenshot: Path | None, retries: int, timeout: int) -> str:
    """跑无头 Chrome；dump-dom 模式返回 DOM 文本，截图模式返回空串（按 retries 重试）。

    配方（都是实测踩出来的，勿轻改）：
      * `--headless=old`：new 在本机 dump-dom / screenshot 挂起；
      * 固定 `--user-data-dir` 复用同一 profile：全新 profile 间歇挂起；
      * 绝不 `capture_output=PIPE`：Chrome fork 的子进程不关管道 → 假挂起；
      * 截图时**不加** `--window-size` / `--virtual-time-budget`：同用实测挂起。
    """
    base = run_chrome_base(chrome, profile)
    wants_dom = screenshot is None
    for attempt in range(1, retries + 1):
        err_file = run_dir / f"probe_chrome_{ts}_{attempt}.log"
        if wants_dom:
            dom_file = run_dir / f"probe_dom_{ts}_{attempt}.html"
            cmd = base + ["--virtual-time-budget=3000", "--dump-dom", url]
            with open(dom_file, "wb") as out, open(err_file, "wb") as err:
                try:
                    subprocess.run(cmd, stdout=out, stderr=err, timeout=timeout)
                except subprocess.TimeoutExpired:
                    print(f"[probe] 第 {attempt}/{retries} 次 dump-dom 超时（偶发挂起，重试）")
                    continue
            dom = dom_file.read_text(encoding="utf-8", errors="replace") if dom_file.exists() else ""
            if PROBE_RESULT_RE.search(dom):
                return dom
            print(f"[probe] 第 {attempt}/{retries} 次未拿到探针结果，重试")
        else:
            cmd = base + [f"--screenshot={screenshot}", url]
            with open(err_file, "wb") as err:
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=err, timeout=timeout)
                except subprocess.TimeoutExpired:
                    print(f"[probe] 第 {attempt}/{retries} 次截图超时（偶发挂起，重试）")
                    continue
            if screenshot.exists() and screenshot.stat().st_size > 0:
                print(f"[probe] 截图 -> {screenshot}（{screenshot.stat().st_size} bytes）")
                return ""
            print(f"[probe] 第 {attempt}/{retries} 次截图未产出文件，重试")
    return ""


def selftest(run_dir: Path, chrome: str) -> int:
    """自检：最小页里 overflow:hidden / auto 两个 textarea 必须量出 gutter 0 与非 0。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    body = "\n".join(f"第 {i} 行：用来看滚动条" for i in range(1, 61))
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    textarea{{display:block;width:300px;height:120px}}
    .hid{{overflow:hidden}} .aut{{overflow:auto}}
    </style></head><body>
    <textarea class="hid">{body}</textarea>
    <textarea class="aut">{body}</textarea>
    </body></html>"""
    work = prepare_page(page, ["textarea.hid", "textarea.aut"], run_dir, ts, keep_scripts=False)
    dom = run_chrome(chrome, work.as_uri(), DEFAULT_PROFILE, ts, run_dir, None, 3, 45)
    if not dom:
        print("[selftest] FAIL：拿不到探针输出")
        return 1
    payload = parse_probe(dom)
    hid, aut = payload["probes"][0], payload["probes"][1]
    ok = (hid["computedOverflowY"] == "hidden" and hid["scrollbarGutter"] == 0
          and aut["computedOverflowY"] == "auto" and aut["scrollbarGutter"] > 0)
    print(f"[selftest] hidden: overflowY={hid['computedOverflowY']} gutter={hid['scrollbarGutter']} | "
          f"auto: overflowY={aut['computedOverflowY']} gutter={aut['scrollbarGutter']}")
    print("[selftest]", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    """命令行入口：探针 / 截图 / 自检。"""
    ap = argparse.ArgumentParser(description="无头 Chrome 单页计算样式探针（UI 取证）")
    ap.add_argument("--html", help="真实渲染页 HTML 文件")
    ap.add_argument("--selector", action="append", default=[], help="要量测的 CSS 选择器（可重复）")
    ap.add_argument("--screenshot", help="截图输出路径（与 dump-dom 分两次调用，勿加 window-size）")
    ap.add_argument("--focus-card", help="只保留含该文本的 .card（配平抽取）生成聚焦页")
    ap.add_argument("--out", help="JSON 结果落盘路径（默认同时打印到 stdout）")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE), help="Chrome profile 目录（复用同一 profile）")
    ap.add_argument("--keep-scripts", action="store_true", help="保留页面脚本（默认剥离）")
    ap.add_argument("--retries", type=int, default=3, help="超时/无输出的重试次数（默认 3）")
    ap.add_argument("--timeout", type=int, default=45, help="单次 Chrome 超时秒数（默认 45）")
    ap.add_argument("--selftest", action="store_true", help="纯本地自检（不需要业务页面）")
    args = ap.parse_args(argv)

    run_dir = REPO / "run-logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    if not chrome:
        print("[probe] 未找到 Chrome；跳过（可用 CHROME=<路径> 指定）")
        return 2 if args.selftest else 0
    if args.selftest:
        return selftest(run_dir, chrome)
    if not args.html or not Path(args.html).is_file():
        print("[probe] --html 必须是存在的文件（或使用 --selftest）")
        return 2
    if not args.selector:
        print("[probe] 至少给一个 --selector")
        return 2

    ts = time.strftime("%Y%m%d_%H%M%S")
    html = Path(args.html).read_text(encoding="utf-8")
    if args.focus_card:
        html = build_focus_page(html, args.focus_card)
        print("[probe] 已按 --focus-card 生成聚焦页（只留公共 <style> 与目标卡片）")
    work = prepare_page(html, args.selector, run_dir, ts, args.keep_scripts)
    Path(args.profile).mkdir(parents=True, exist_ok=True)

    dom = run_chrome(chrome, work.as_uri(), Path(args.profile), ts, run_dir, None,
                     args.retries, args.timeout)
    if dom:
        payload = parse_probe(dom)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"[probe] JSON -> {args.out}")
    if args.screenshot:
        run_chrome(chrome, work.as_uri(), Path(args.profile), ts, run_dir,
                   Path(args.screenshot), args.retries, args.timeout)
    return 0 if dom else 1


if __name__ == "__main__":
    sys.exit(main())
