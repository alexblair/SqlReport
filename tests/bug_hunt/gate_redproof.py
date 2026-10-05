"""gate_redproof.py — 门禁自身的变体证明（RED-GREEN）。

**为什么需要这个脚本**：一条从未失败过的门禁等于没有门禁——它可能只是"恰好路过"当前
代码，并不能在缺陷回归时拦下来。本脚本把本轮 4 条 UI 门禁各自对应的**历史缺陷打回去**
（运行时变异 / 临时改写源码），要求门禁**必须失败**（RED），还原后**必须通过**（GREEN）。

覆盖的门禁（`tests/test_ui_tokens.py`）：
  1. `TestNoDuplicateDeclarations`                ← 同一规则内 display:none 被 display:flex 覆盖
  2. `TestPageInitRegistration::...reachable...`  ← 新增 init 函数没进 initPage（换页后不重放）
  3. `TestPageInitRegistration::...replay_safe`   ← 无条件裸绑 DOMContentLoaded（换页后不执行）
  4. `TestFormControlNameUniqueness`              ← 镜像控件带 name（同名参数重复提交）

⚠️ 第 3 项会**临时改写 `report.py`**（追加一行变异、随即还原）。脚本用 try/finally +
sha256 校验保证还原；若上次运行被强杀留下 `report.py.redproof.bak`，脚本会拒绝启动，
此时请 `git checkout -- report.py` 后删除该 .bak 再跑。

手动运行（不进 discover，勿当常规回归）：
    venv/bin/python tests/bug_hunt/gate_redproof.py
"""
import hashlib
import io
import os
import shutil
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import render          # noqa: E402
import report          # noqa: E402
import tests           # noqa: E402  （导入即应用测试进程隔离）


def _sha256(path: str) -> str:
    """返回文件内容的 sha256（用于确认变异后确实还原）。"""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _run(test_name: str):
    """跑单个用例，返回 (是否失败, 失败摘要)。"""
    suite = unittest.TestLoader().loadTestsFromName(test_name)
    buf = io.StringIO()
    res = unittest.TextTestRunner(verbosity=0, stream=buf).run(suite)
    detail = ""
    for _, tb in (res.failures + res.errors):
        detail = tb.strip().splitlines()[-1][:160]
    return (not res.wasSuccessful()), detail


_CHECKS: list = []


def _check(label: str, mutate, restore, test_name: str) -> None:
    """变异 → 门禁必须失败；还原 → 门禁必须通过。任一步不符即记为 FAIL。"""
    mutate()
    red, detail = _run(test_name)
    restore()
    green, gdetail = _run(test_name)
    _CHECKS.append((label, red and not green, red, green, detail, gdetail))


def main() -> int:
    """执行全部 RED-GREEN 证明，返回进程退出码（0=全部通过）。"""
    report_py = report.__file__
    backup = report_py + ".redproof.bak"
    if os.path.exists(backup):
        print(f"[中止] 发现残留 {backup}：上次运行未正常还原。"
              f"请先 `git checkout -- report.py` 并删除该文件。")
        return 2

    # --- 1) 同规则内重复声明（历史事故：加载遮罩默认就显示） ---------------
    orig_common = render._COMMON_CSS

    def mutate_dup():
        render._COMMON_CSS = orig_common.replace(
            ".query-loading-overlay{", ".query-loading-overlay{display:flex;", 1)
        assert render._COMMON_CSS != orig_common, "变异未命中遮罩规则"

    _check("同规则重复属性", mutate_dup,
           lambda: setattr(render, "_COMMON_CSS", orig_common),
           "tests.test_ui_tokens.TestNoDuplicateDeclarations"
           ".test_no_duplicate_property_in_one_rule")

    # --- 2) 新增 init 函数但没进 initPage（换页后不重放） ------------------
    orig_js = render._COMMON_JS

    def mutate_init():
        render._COMMON_JS = orig_js.replace(
            "function initPage() {", "function initZzzGhost() {}\nfunction initPage() {", 1)
        assert render._COMMON_JS != orig_js, "变异未命中 initPage"

    _check("init 未注册进 initPage", mutate_init,
           lambda: setattr(render, "_COMMON_JS", orig_js),
           "tests.test_ui_tokens.TestPageInitRegistration"
           ".test_every_init_function_is_reachable_after_swap")

    # --- 3) 无条件裸绑 DOMContentLoaded（换页后不执行） --------------------
    before = _sha256(report_py)
    injected = ('_FOOTER_GLUE = r"""\n'
                "document.addEventListener('DOMContentLoaded', function(){ initDragHandlers(); });")

    def mutate_dcl():
        shutil.copy2(report_py, backup)
        with open(report_py, encoding="utf-8") as fh:
            src = fh.read()
        src = src.replace('_FOOTER_GLUE = r"""', injected, 1)
        with open(report_py, "w", encoding="utf-8") as fh:
            fh.write(src)

    def restore_dcl():
        shutil.move(backup, report_py)
        assert _sha256(report_py) == before, "report.py 还原后 sha256 不一致！"

    try:
        _check("无条件裸绑 DOMContentLoaded", mutate_dcl, restore_dcl,
               "tests.test_ui_tokens.TestPageInitRegistration"
               ".test_dom_content_loaded_bindings_are_replay_safe")
    finally:
        if os.path.exists(backup):        # 异常路径兜底
            shutil.move(backup, report_py)

    # --- 4) 镜像控件带 name（同名参数重复提交） ---------------------------
    import importlib
    importlib.reload(report)              # 3) 曾改写源码，重新装载以免用到缓存
    orig_modal = report.build_export_modal_html   # report.py 用 from render import 直引

    def mutate_name():
        def patched(*a, **k):
            html = orig_modal(*a, **k)
            out = html.replace('<select id="export-format-select"',
                               '<select name="format" id="export-format-select"', 1)
            assert out != html, "变异未命中隐藏 select"
            return out
        report.build_export_modal_html = patched

    _check("镜像控件带 name", mutate_name,
           lambda: setattr(report, "build_export_modal_html", orig_modal),
           "tests.test_ui_tokens.TestFormControlNameUniqueness.test_report_page_controls")

    print(f"{'门禁':26} RED(应失败)  GREEN(应通过)  结论")
    failed = 0
    for label, ok, red, green, detail, gdetail in _CHECKS:
        print(f"{label:26} {str(red):11} {str(green):14} {'PASS' if ok else 'FAIL'}")
        if detail:
            print(f"{'':26} ↳ RED 信息：{detail}")
        if gdetail:
            print(f"{'':26} ↳ GREEN 仍失败：{gdetail}")
        failed += 0 if ok else 1
    print(f"\n结论：{len(_CHECKS) - failed}/{len(_CHECKS)} 条门禁通过 RED-GREEN 证明")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
