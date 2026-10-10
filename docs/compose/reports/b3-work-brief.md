> ⚠️ **AOCI 已卸载（2026-10-10）**：本文中的 `aoci*` 路径、命令与「硬性 #21」均已失效，仅作历史记录保留；代码分析请走 `codegraph`（硬性 #18）。

# B3 工作包（P0 ZIP 导出路径穿越）

> 本文件是 **B3 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/spec/2026-10-10-perf-robustness-refactor-design.md` §7.3（方案 C）
> 开工基线：`Ran 3072 tests, OK (skipped=4)`（B2 后）
> 放在 `docs/compose/reports/` 而非 `run-logs/`（后者会被 `cleanup_tmp.py` 删除）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. **只改 `export.py`**，测试新建 `tests/test_b3_export_zip_safety.py`。
4. 不改变可观测行为 —— **本任务的要点正是「安全修好 + 用户可见字节不变」**。
5. 用户可感知文字一律简体中文（硬性 #2）。
6. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`（Lead 批次验收后统一做）。
7. 中断恢复：只做这一件事；被中断不要重做。

---

## 1. 缺陷（已实测复现）

`export.py:333-358` 的 `_create_temp_zip(content_bytes, filename, zip_filename)`：
**磁盘落点名与 ZIP 条目名共用同一个 `filename`**，而该值来自报表名：

```python
# export.py:522-523（调用点）
inner_filename = f"{report_config['name']}.{export_format}"
zip_data = _create_temp_zip(content_bytes, inner_filename, raw_name)
```

```python
# export.py:344-352（缺陷处）
tmpfile_path = os.path.join(tmpdir, filename)   # ← 报表名直接当落点名
with open(tmpfile_path, "wb") as f:
    f.write(content_bytes)
zip_path = os.path.join(tmpdir, zip_filename)
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(tmpfile_path, arcname=filename)
```

**实测**（`os.path.join` 语义）：
```
filename='../../escape.csv' → /tmp/report_export_xxx/../../escape.csv   越界 True
filename='/tmp/evil.csv'    → /tmp/evil.csv                            越界 True
filename='normal.csv'       → /tmp/report_export_xxx/normal.csv        越界 False
```

报表名由用户在配置页填写（`config.py` → `config_db.update_report`），**零校验**。
报表名含 `/`、`..` 或以 `/` 开头时，`/export?id=N&zip=1` 会把导出内容写到 `tmpdir` 之外。

---

## 2. 修法：方案 C（已定，用户已认可）

**关键洞察**：ZIP 格式里「磁盘上叫什么」与「压缩包里叫什么」**本来就是两件事**。
把磁盘落点固定为**与报表名无关的常量**，`arcname` 仍传原名即可。

### Step 1 — 写测试

```python
# tests/test_b3_export_zip_safety.py
import io
import os
import tempfile
import unittest
import zipfile

import export


class TestZipTraversal(unittest.TestCase):
    """ZIP 导出不得让服务端把文件写出临时目录（CWE-22）。"""

    def test_traversal_name_not_written_outside_tmpdir(self):
        """报表名含 ../ 时，文件不得落到 tmpdir 之外。"""
        outer = tempfile.mkdtemp(prefix="outer_")
        target = os.path.join(os.path.dirname(outer), "escape.csv")
        try:
            if os.path.exists(target):
                os.remove(target)
            data = export._create_temp_zip(b"x", "../../escape.csv", "escape.csv")
            self.assertIsInstance(data, bytes)
            self.assertFalse(os.path.exists(target), "文件被写出 tmpdir 之外！")
        finally:
            import shutil
            shutil.rmtree(outer, ignore_errors=True)

    def test_absolute_name_not_written(self):
        """报表名为绝对路径时，不得写到该绝对路径。"""
        probe = os.path.join(tempfile.gettempdir(), "sr_b3_probe.csv")
        if os.path.exists(probe):
            os.remove(probe)
        export._create_temp_zip(b"x", probe, "probe.csv")
        self.assertFalse(os.path.exists(probe), "绝对路径被写出！")

    def test_zip_entry_name_preserves_report_name(self):
        """✅ 方案 C 的核心：ZIP 内条目名必须仍为原名（用户可见字节不变）。"""
        for name in ["销售报表.csv", "2026/Q1 营收.csv", "O'Brien.csv"]:
            data = export._create_temp_zip(b"a,b\n1,2\n", name, "x.zip")
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                self.assertEqual(zf.namelist(), [name],
                                 f"条目名被改变了：期望 {name!r}")

    def test_normal_name_still_works(self):
        """普通名字的导出内容必须正确（不能只测安全、把功能测坏）。"""
        payload = "a,b\n1,2\n".encode("utf-8")
        data = export._create_temp_zip(payload, "销售报表.csv", "销售报表.csv")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(zf.namelist(), ["销售报表.csv"])
            self.assertEqual(zf.read("销售报表.csv"), payload)

    def test_extension_kept_on_inner_entry(self):
        """json 导出时条目名仍是 .json（不是被写死成 .csv）。"""
        data = export._create_temp_zip(b"{}", "报表.json", "x.zip")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(zf.namelist(), ["报表.json"])
```

### Step 2 — 跑确认失败
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b3_export_zip_safety.py' -t . 2>&1 | tail -5
```
Expected: 至少 `test_traversal_name_not_written_outside_tmpdir` / `test_absolute_name_not_written` 失败
（`test_zip_entry_name_preserves_report_name` 现在会**通过**——它同时是"不回归"护栏）。

> ⚠️ 若两个安全测试**直接写入失败**（例如沙箱只读导致 `open()` 抛异常而不是静默写错），
> 这仍算 RED（说明确实试图写到 tmpdir 外）。请在报告里说明实际现象。

### Step 3 — 改 `_create_temp_zip`

**磁盘落点全部改为常量派生**（与报表名无关），**`arcname` 保留原名**：

```python
def _create_temp_zip(content_bytes: bytes, filename: str,
                     zip_filename: str) -> bytes:
    """将字节内容写入临时文件，创建 ZIP 压缩包，返回 ZIP 字节。

    ⚠️ 安全要点（B3，CWE-22）：`filename` 来自用户填写的报表名，**不可**直接
    用作磁盘落点名——含 `../` 或绝对路径时会写到 tmpdir 之外。故：
      - 磁盘落点用固定常量名（`payload<ext>` / `payload.zip`），与报表名无关；
      - `arcname` 仍传原名，因此**用户看到的 ZIP 内文件名与改动前完全一致**。
    """
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="report_export_")
        # 落盘名与用户可控值解耦：只借用扩展名，其余一律常量
        _, ext = os.path.splitext(filename)
        disk_name = "payload" + ext
        tmpfile_path = os.path.join(tmpdir, disk_name)
        with open(tmpfile_path, "wb") as f:
            f.write(content_bytes)

        # zip 文件自身也用固定名
        zip_path = os.path.join(tmpdir, "payload.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmpfile_path, arcname=filename)   # ← 原名进条目名

        with open(zip_path, "rb") as f:
            zip_data = f.read()
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return zip_data
```

> `zip_filename` 参数保留（调用方仍传 `raw_name`），但**不再用于磁盘落点**——
> 避免改签名（可能影响其他调用方/mock）。若 lint 报未使用参数，可保留原样不动。

### Step 4 — 跑确认通过
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b3_export_zip_safety.py' -t . 2>&1 | tail -3
```

### Step 5 — 回归（导出相关）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_export*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
```

---

## 3. 完成后报告（六行内）

1. 改动文件与行号
2. 新测试结果（精确 `Ran N tests, OK`）；并说明 RED 阶段的实际现象
3. `test_export*.py` 结果（精确 `Ran N tests, OK`）
4. `test_report*.py` 结果
5. `test_zip_entry_name_preserves_report_name` 是否 PASS（这是"字节不变"的证据）
6. 是否改了 `_create_temp_zip` 的**签名**（**必须：没改**，参数列表保持 3 个）

若发现 brief 与实际代码不符，**停下报告差异**。

---

## 4. B3 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3077` / `OK (skipped=4)`（3072 + B3 新增用例）。
