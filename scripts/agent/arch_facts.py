#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""架构图取证器 —— 一次命令产出架构图所需的结构化事实（JSON）。

用途：`docs/compose/reports/<日期>-system-architecture-map.html` 的更新输入。
产出六类事实：路由表 / 模块行数与依赖 / 共用构件调用点 / 配置表 / 前端资产 / 体积。

用法：
    python3 scripts/agent/arch_facts.py                    # 打印当前代码事实
    python3 scripts/agent/arch_facts.py --prev <html>      # 与上一版 HTML 内嵌事实比对
    python3 scripts/agent/arch_facts.py --embed <html>     # 把当前事实写回 HTML 的 arch-facts 块

`ponytail:` 只做正则级提取，不做 AST。要精确调用链用 `codegraph explore`。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES_DIR = "config_pages"
FACT_ID = "arch-facts"


def _read(rel):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _py_files():
    files = [f for f in sorted(os.listdir(ROOT)) if f.endswith(".py")]
    sub = os.path.join(ROOT, PAGES_DIR)
    if os.path.isdir(sub):
        files += [f"{PAGES_DIR}/{f}" for f in sorted(os.listdir(sub)) if f.endswith(".py")]
    return files


ROUTE_RE = re.compile(
    r'RouteEntry\(\s*r?["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,'
    r"\s*(True|False)\s*,\s*(True|False)\s*,\s*[\"']([^\"']+)[\"']"
)
IMPORT_RE = re.compile(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", re.M)
TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)")
DEF_RE = re.compile(r"^def (\w+)\(", re.M)
JSFN_RE = re.compile(r"^function (\w+)\(", re.M)


def facts():
    routes, seen = [], set()
    for m in ROUTE_RE.finditer(_read("server.py")):
        pattern, method, auth, db, handler = m.groups()
        key = (pattern, method)
        if key in seen:            # /login、/config/api-endpoints 各占两行，按端点去重
            continue
        seen.add(key)
        routes.append({
            "pattern": pattern, "method": method, "handler": handler,
            "auth": auth == "True", "db": db == "True",
        })

    modules, importers = {}, {}
    for rel in _py_files():
        src = _read(rel)
        mod = rel[:-3].replace("/", ".")
        deps = sorted({
            (a or b).split(".")[0].strip()
            for a, b in IMPORT_RE.findall(src)
            if (a or b).strip()
        } - {"__future__"})
        modules[mod] = {
            "lines": src.count("\n") + (1 if src and not src.endswith("\n") else 0),
            "imports": deps,
        }
        for d in deps:
            importers.setdefault(d, []).append(mod)
    for mod, info in modules.items():
        info["imported_by"] = sorted(importers.get(mod, []))

    # 共用构件：render.py 的公开构件被其它模块直接调用的次数
    corpus = {rel: _read(rel) for rel in _py_files()}
    shared = []
    for fn in sorted(set(DEF_RE.findall(_read("render.py")))):
        if fn.startswith("_"):
            continue
        sites = [
            rel for rel, src in corpus.items()
            if rel != "render.py" and re.search(rf"\b{fn}\(", src)
        ]
        if len(sites) >= 2:
            shared.append({"fn": fn, "sites": sorted(sites), "count": len(sites)})
    shared.sort(key=lambda x: (-x["count"], x["fn"]))

    tables = sorted(set(TABLE_RE.findall(_read("config_db.py"))))
    audit_tables = sorted(set(TABLE_RE.findall(_read("audit_db.py"))))

    assets_src = _read("ui_assets.py")
    css_consts = sorted(set(re.findall(r"^([A-Z][A-Z0-9_]*CSS[A-Z0-9_]*)\s*=", assets_src, re.M)))
    js_consts = sorted(set(re.findall(r"^([A-Z][A-Z0-9_]*JS[A-Z0-9_]*)\s*=", assets_src, re.M)))
    js_funcs = []
    for src, names in ((assets_src, js_consts), (_read("render.py"), ["_COMMON_JS"])):
        for name in names:
            # 字面量可能带 r / b 前缀（r""" ... """）
            block = re.search(rf'^{name}\s*=\s*[rb]?("""|\'\'\')(.*?)\1', src, re.S | re.M)
            if block:
                js_funcs += JSFN_RE.findall(block.group(2))

    vendor = []
    vdir = os.path.join(ROOT, "static", "vendor")
    if os.path.isdir(vdir):
        vendor = sorted(os.listdir(vdir))

    return {
        "root": ROOT,
        "routes": routes,
        "modules": modules,
        "shared_components": shared,
        "tables": tables,
        "audit_tables": audit_tables,
        "ui_consts": {"css": css_consts, "js": js_consts, "js_functions": sorted(set(js_funcs))},
        "vendor": vendor,
    }


def _prev_facts(path):
    src = _read_abs(path)
    m = re.search(rf'<script[^>]+id="{FACT_ID}"[^>]*>(.*?)</script>', src, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def _read_abs(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def diff(prev, cur):
    """只比对会影响架构图章节的事实；返回人类可读的变更行（空 = 无需更新）。"""
    out = []
    old = {f"{r['method']} {r['pattern']}": r for r in prev.get("routes", [])}
    new = {f"{r['method']} {r['pattern']}": r for r in cur["routes"]}
    for k in sorted(set(new) - set(old)):
        out.append(f"路由新增 {k} → {new[k]['handler']}")
    for k in sorted(set(old) - set(new)):
        out.append(f"路由删除 {k}")
    for k in sorted(set(old) & set(new)):
        if old[k] != new[k]:
            out.append(f"路由属性变更 {k}: {old[k]} → {new[k]}")

    pm, cm = prev.get("modules", {}), cur["modules"]
    for k in sorted(set(cm) - set(pm)):
        out.append(f"模块新增 {k} ({cm[k]['lines']} 行)")
    for k in sorted(set(pm) - set(cm)):
        out.append(f"模块删除 {k}")
    for k in sorted(set(pm) & set(cm)):
        if pm[k]["lines"] != cm[k]["lines"]:
            out.append(f"行数 {k}: {pm[k]['lines']} → {cm[k]['lines']}")
        if pm[k].get("imports") != cm[k]["imports"]:
            out.append(f"依赖变更 {k}: {pm[k].get('imports')} → {cm[k]['imports']}")

    ps = {s["fn"]: s["count"] for s in prev.get("shared_components", [])}
    cs = {s["fn"]: s["count"] for s in cur["shared_components"]}
    for k in sorted(set(cs) - set(ps)):
        out.append(f"共用构件新增 {k} ({cs[k]} 处)")
    for k in sorted(set(ps) - set(cs)):
        out.append(f"共用构件降级/删除 {k} (原 {ps[k]} 处)")
    for k in sorted(set(ps) & set(cs)):
        if ps[k] != cs[k]:
            out.append(f"共用构件调用点 {k}: {ps[k]} → {cs[k]} 处")

    for key in ("tables", "audit_tables", "vendor"):
        a, b = set(prev.get(key) or []), set(cur[key])
        for k in sorted(b - a):
            out.append(f"{key} 新增 {k}")
        for k in sorted(a - b):
            out.append(f"{key} 减少 {k}")
    for key in ("css", "js", "js_functions"):
        a = set((prev.get("ui_consts") or {}).get(key) or [])
        b = set(cur["ui_consts"][key])
        for k in sorted(b - a):
            out.append(f"前端资产 {key} 新增 {k}")
        for k in sorted(a - b):
            out.append(f"前端资产 {key} 减少 {k}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="架构图取证器")
    ap.add_argument("--prev", help="上一版 HTML，比对后只打印变更")
    ap.add_argument("--embed", help="把当前事实写回该 HTML 的 arch-facts 块（就地替换）")
    args = ap.parse_args(argv)

    cur = facts()

    if args.embed:
        path = args.embed
        src = _read_abs(path)
        if not src:
            print(f"E_NOFILE {path}", file=sys.stderr)
            return 2
        block = (
            f'<script type="application/json" id="{FACT_ID}">\n'
            + json.dumps(cur, ensure_ascii=False, indent=0)
            + "\n</script>"
        )
        pat = re.compile(rf'<script[^>]+id="{FACT_ID}"[^>]*>.*?</script>', re.S)
        if pat.search(src):
            src = pat.sub(lambda _m: block, src, count=1)
        else:                                     # 插在 </body> 前，不参与渲染
            src = src.replace("</body>", block + "\n</body>", 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        print(f"OK embedded -> {path}")
        return 0

    if args.prev:
        prev = _prev_facts(args.prev)
        if prev is None:
            print(f"E_NO_FACTS {args.prev} 里没有 id=\"{FACT_ID}\" 块，先 --embed 一次", file=sys.stderr)
            return 3
        changes = diff(prev, cur)
        if not changes:
            print("NO_CHANGE 代码事实与上一版一致：无需更新架构图（同日重复触发到此即可）")
        else:
            print(f"CHANGED {len(changes)} 项")
            for line in changes:
                print(" -", line)
        return 0

    print(json.dumps(cur, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
