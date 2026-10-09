# -*- coding: utf-8 -*-
"""B3：ZIP 导出路径穿越（CWE-22）安全测试。

报表名由用户在配置页自由填写、零校验，且 `_create_temp_zip` 曾把它直接当作
磁盘落点名；含 `../` 或绝对路径时会写到临时目录之外。本组用例锁定：
  - 安全：文件不得落到 tmpdir 之外；
  - 不回归：ZIP 内条目名必须仍是报表原名（用户可见字节不变）。
"""
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


if __name__ == "__main__":
    unittest.main()
