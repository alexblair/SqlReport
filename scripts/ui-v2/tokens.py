#!/usr/bin/env python3
"""Graphite & Iris 设计令牌生成器（UI v2）。

在 OKLCH 感知均匀色彩空间中定义色板 → 转 sRGB hex → 计算 WCAG 对比度，
输出可直接粘贴进 CSS 的令牌块与对比度报告。

用法：
    python scripts/ui-v2/tokens.py            # 打印令牌 + 对比度报告
    python scripts/ui-v2/tokens.py --css      # 只打印 CSS 令牌块
    python scripts/ui-v2/tokens.py --check    # 对比度断言（不达标非零退出）
"""
from __future__ import annotations

import math
import sys

# ---------------------------------------------------------------------------
# 色彩转换：OKLCH → sRGB
# ---------------------------------------------------------------------------


def oklch_to_linear(L: float, C: float, H: float) -> tuple[float, float, float]:
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _gamma(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055


def oklch_hex(L: float, C: float, H: float) -> str:
    r, g, b = oklch_to_linear(L, C, H)
    return "#%02x%02x%02x" % tuple(round(_gamma(v) * 255) for v in (r, g, b))


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [p / 12.92 if p <= 0.04045 else ((p + 0.055) / 1.055) ** 2.4 for p in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------------------
# 色板（OKLCH 定义）
# ---------------------------------------------------------------------------

# 中性：冷石墨（hue 265，极低彩度）——界面骨架
NEUTRAL = {
    "n0": (0.995, 0.000, 265),
    "n25": (0.985, 0.003, 265),
    "n50": (0.975, 0.004, 265),
    "n100": (0.958, 0.005, 265),
    "n150": (0.936, 0.006, 265),
    "n200": (0.905, 0.007, 265),
    "n300": (0.820, 0.010, 265),
    "n400": (0.700, 0.014, 265),
    "n500": (0.548, 0.019, 265),
    "n600": (0.470, 0.022, 265),
    "n700": (0.360, 0.022, 265),
    "n800": (0.265, 0.020, 265),
    "n900": (0.195, 0.018, 265),
    "n950": (0.150, 0.016, 268),
    # 侧栏专用（更深更紫一点，与内容区拉开层次）
    "sbg": (0.185, 0.017, 272),
    "sbg2": (0.235, 0.017, 272),
}

# 主色：鸢尾（iris，hue 277）——唯一强调色
IRIS = {
    "a50": (0.975, 0.014, 277),
    "a100": (0.945, 0.032, 277),
    "a200": (0.895, 0.062, 277),
    "a300": (0.805, 0.105, 277),
    "a400": (0.680, 0.160, 277),
    "a500": (0.560, 0.190, 277),
    "a600": (0.500, 0.190, 277),
    "a700": (0.430, 0.170, 277),
}

# 语义色：与主色同族调和（低彩度软底 + 高对比实色）
SEMANTIC = {
    "ok500": (0.560, 0.130, 158),
    "ok700": (0.440, 0.110, 158),
    "ok50": (0.965, 0.025, 158),
    "warn500": (0.700, 0.150, 72),
    "warn700": (0.560, 0.130, 62),
    "warn50": (0.972, 0.030, 80),
    "dan500": (0.560, 0.200, 25),
    "dan700": (0.470, 0.180, 25),
    "dan50": (0.968, 0.022, 25),
    "info500": (0.580, 0.160, 250),
    "info700": (0.480, 0.150, 250),
    "info50": (0.968, 0.022, 250),
}

PALETTE: dict[str, str] = {}
for _name, (_l, _c, _h) in {**NEUTRAL, **IRIS, **SEMANTIC}.items():
    PALETTE[_name] = oklch_hex(_l, _c, _h)

# ---------------------------------------------------------------------------
# 语义映射（CSS 变量名 → 色板键）
# ---------------------------------------------------------------------------

TOKENS: list[tuple[str, str, str]] = [
    # (CSS 变量, 色板键, 用途)
    ("--bg-app", "n50", "应用底"),
    ("--bg-surface", "n0", "卡片/表格面"),
    ("--bg-raised", "n25", "次级面"),
    ("--bg-subtle", "n100", "表头/内嵌面板"),
    ("--bg-hover", "n100", "行/项 hover"),
    ("--bg-active", "n150", "按下/选中底"),
    ("--line", "n200", "常规分隔线"),
    ("--line-soft", "n150", "弱分隔线"),
    ("--line-strong", "n300", "输入框描边"),
    ("--ink-1", "n900", "主文字"),
    ("--ink-2", "n600", "次文字"),
    ("--ink-3", "n500", "辅助文字"),
    ("--ink-4", "n400", "占位/禁用"),
    ("--accent", "a500", "主色"),
    ("--accent-hover", "a600", "主色 hover"),
    ("--accent-press", "a700", "主色 active"),
    ("--accent-ink", "a700", "主色文字（浅底上）"),
    ("--accent-soft", "a50", "主色浅底"),
    ("--accent-soft-2", "a100", "主色浅底（深一档）"),
    ("--accent-line", "a200", "主色描边"),
    ("--ok", "ok500", "成功"),
    ("--ok-ink", "ok700", "成功文字"),
    ("--ok-soft", "ok50", "成功浅底"),
    ("--warn", "warn500", "警示"),
    ("--warn-ink", "warn700", "警示文字"),
    ("--warn-soft", "warn50", "警示浅底"),
    ("--danger", "dan500", "危险"),
    ("--danger-ink", "dan700", "危险文字"),
    ("--danger-soft", "dan50", "危险浅底"),
    ("--info", "info500", "信息"),
    ("--info-ink", "info700", "信息文字"),
    ("--info-soft", "info50", "信息浅底"),
    ("--sidebar-bg", "sbg", "侧栏底"),
    ("--sidebar-bg-2", "sbg2", "侧栏次级面"),
]

# 代码面（深色）——旧 token 色为浅底设计，压在深底上曾低至 1.02:1（正文隐形）
CODE_TOKENS = {
    "--code-bg": "#0f131b",
    "--code-ink": "#e2e6ef",
    "--code-dim": "#9fa5b0",
    "--code-op": "#c8ccd6",
    "--code-kw": "#a9a5ff",
    "--code-fn": "#7ac8f5",
    "--code-str": "#88d9a5",
    "--code-num": "#eebe7c",
    "--code-comment": "#9298a5",
    # 已被替换的旧值：保留在此仅用于回归对比（不得再出现在 CSS 中）
    "--old-kw": "#7c3aed",
    "--old-fn": "#2563eb",
    "--old-ink": "#11151d",
}
CODE_CHECKS = [
    ("代码正文", "--code-ink", 4.5),
    ("代码次级", "--code-dim", 4.5),
    ("代码运算符", "--code-op", 4.5),
    ("关键字", "--code-kw", 4.5),
    ("函数", "--code-fn", 4.5),
    ("字符串", "--code-str", 4.5),
    ("数字", "--code-num", 4.5),
    ("注释", "--code-comment", 4.5),
]

# 对比度验收线（WCAG：正文 ≥4.5，大字/图形 ≥3.0）
CHECKS: list[tuple[str, str, str, float]] = [
    ("ink-1", "--ink-1", "--bg-surface", 4.5),
    ("ink-1 on app", "--ink-1", "--bg-app", 4.5),
    ("ink-2", "--ink-2", "--bg-surface", 4.5),
    ("ink-3", "--ink-3", "--bg-surface", 4.5),
    ("accent 文字", "--accent-ink", "--bg-surface", 4.5),
    ("accent 文字于软底", "--accent-ink", "--accent-soft", 4.5),
    ("白字于主色钮", "n0", "--accent", 4.5),
    ("ok 文字", "--ok-ink", "--bg-surface", 4.5),
    ("warn 文字", "--warn-ink", "--bg-surface", 4.5),
    ("danger 文字", "--danger-ink", "--bg-surface", 4.5),
    ("info 文字", "--info-ink", "--bg-surface", 4.5),
    ("侧栏常规字", "--sidebar-ink", "--sidebar-bg", 4.5),
    ("侧栏分组标题", "--sidebar-ink-dim", "--sidebar-bg", 3.0),
]


def build_sidebar_tokens() -> str:
    """侧栏专用令牌（依赖上面算出的基色）。"""
    return (
        "  --sidebar-ink:#%s; --sidebar-ink-dim:#%s; --sidebar-ink-active:#ffffff;\n"
        "  --sidebar-hover:rgba(255,255,255,.055); --sidebar-active:rgba(255,255,255,.09);\n"
        "  --sidebar-line:rgba(255,255,255,.075);\n"
        % (
            oklch_hex(0.780, 0.016, 272).lstrip("#"),
            oklch_hex(0.620, 0.014, 272).lstrip("#"),
        )
    )


def render_css() -> str:
    lines = [":root{"]
    lines.append("  /* 中性（冷石墨） */")
    for var, key, use in TOKENS[:17]:
        lines.append(f"  {var}:{PALETTE[key]}; /* {use} */")
    lines.append("  /* 主色（鸢尾） */")
    for var, key, use in TOKENS[17:30]:
        lines.append(f"  {var}:{PALETTE[key]}; /* {use} */")
    lines.append("  /* 语义 */")
    for var, key, use in TOKENS[30:]:
        lines.append(f"  {var}:{PALETTE[key]}; /* {use} */")
    lines.append(build_sidebar_tokens().rstrip("\n"))
    lines.append("}")
    return "\n".join(lines)


VAR_TO_KEY = {var: key for var, key, _ in TOKENS}
VAR_TO_KEY.update({
    "n0": "n0",
    "--sidebar-ink": oklch_hex(0.780, 0.016, 272),
    "--sidebar-ink-dim": oklch_hex(0.620, 0.014, 272),
})


def resolve(name: str) -> str:
    """令牌名或色板键 → hex。"""
    if name.startswith("#"):
        return name
    val = VAR_TO_KEY.get(name)
    if val is None:
        return PALETTE[name]
    return val if val.startswith("#") else PALETTE[val]


def report() -> int:
    print("色板：")
    for k, v in PALETTE.items():
        print(f"  {k:8} {v}")
    print("\n对比度：")
    fails = 0
    for label, fg, bg, need in CHECKS:
        fg_hex, bg_hex = resolve(fg), resolve(bg)
        r = contrast(fg_hex, bg_hex)
        mark = "PASS" if r >= need else "FAIL"
        if r < need:
            fails += 1
        print(f"  [{mark}] {label:22} {fg_hex} / {bg_hex} = {r:.2f}:1  (需 {need})")
    print("\n代码面对比度（底色 %s）：" % CODE_TOKENS["--code-bg"])
    for label, key, need in CODE_CHECKS:
        r = contrast(CODE_TOKENS[key], CODE_TOKENS["--code-bg"])
        mark = "PASS" if r >= need else "FAIL"
        if r < need:
            fails += 1
        print(f"  [{mark}] {label:22} {CODE_TOKENS[key]} = {r:.2f}:1  (需 {need})")
    for label, key in (("旧关键字(反例)", "--old-kw"), ("旧函数(反例)", "--old-fn"), ("旧正文(反例)", "--old-ink")):
        print(f"  [REF ] {label:22} {CODE_TOKENS[key]} = {contrast(CODE_TOKENS[key], CODE_TOKENS['--code-bg']):.2f}:1  ← 已废弃")
    return fails

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--css" in args:
        print(render_css())
    elif "--check" in args:
        sys.exit(1 if report() else 0)
    else:
        report()
        print("\n" + render_css())
