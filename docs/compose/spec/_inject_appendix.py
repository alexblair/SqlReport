#!/usr/bin/env python3
"""把 ui-redesign-inventory.md 转为 HTML，注入原型附录（与清单同源）。"""
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = HERE / "ui-redesign-inventory.md"
PROTO = HERE / "ui-redesign-prototype.html"


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out = []
    i = 0
    in_table = False
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|\s*$", lines[i + 1]):
            # 表头
            headers = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(h)}</th>" for h in headers) + "</tr></thead><tbody>")
            for r in rows:
                # 对齐列数
                while len(r) < len(headers):
                    r.append("")
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r[: len(headers)]) + "</tr>")
            out.append("</tbody></table>")
            continue
        if ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h2>{inline(ln[2:])}</h2>")
        elif ln.startswith("> "):
            out.append(f"<p>{inline(ln[2:])}</p>")
        elif re.match(r"^- \[x\] ", ln):
            out.append(f"<p>✅ {inline(re.sub(r'^- \\[x\\] ', '', ln))}</p>")
        elif re.match(r"^- \[ \] ", ln):
            out.append(f"<p>⬜ {inline(re.sub(r'^- \\[ \\] ', '', ln))}</p>")
        elif ln.startswith("- "):
            out.append(f"<li>{inline(ln[2:])}</li>")
        elif ln.strip() == "":
            pass
        elif ln.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append("<div class='code-block'>" + html.escape("\n".join(buf)) + "</div>")
        else:
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    # 把连续 li 包进 ul
    html_out = []
    in_ul = False
    for part in out:
        if part.startswith("<li>"):
            if not in_ul:
                html_out.append("<ul>")
                in_ul = True
            html_out.append(part)
        else:
            if in_ul:
                html_out.append("</ul>")
                in_ul = False
            html_out.append(part)
    if in_ul:
        html_out.append("</ul>")
    return "\n".join(html_out)


def main():
    md = MD.read_text(encoding="utf-8")
    # 跳过 frontmatter 式行（无），直接转换
    frag = md_to_html(md)
    proto = PROTO.read_text(encoding="utf-8")
    m = re.search(r'<div id="appendix-body">.*?</div>', proto, flags=re.S)
    if not m:
        raise SystemExit("appendix-body 容器未找到")
    proto = proto[: m.start()] + '<div id="appendix-body">' + frag + "</div>" + proto[m.end() :]
    PROTO.write_text(proto, encoding="utf-8")
    print(f"injected {len(frag)} chars into prototype appendix")


if __name__ == "__main__":
    main()
