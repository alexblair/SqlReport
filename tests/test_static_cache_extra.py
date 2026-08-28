"""
test_static_cache_extra.py — static_cache.py 未覆盖路径补充测试

覆盖：
1. strip_json_suffix — .json 后缀剥离
2. content_has_object_meta — 非合法 JSON 返回 True
3. try_read 兜底异常 — OSError 返回 None
4. write_file replace 失败 — 临时文件清理
5. write_versioned_file 写入失败 — 返回 False
6. invalidate 路径穿越 — 返回 False
7. invalidate 文件删除异常 — OSError 返回 False
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import static_cache


class TestStripJsonSuffix(unittest.TestCase):
    """1. strip_json_suffix — 传入以 .json 结尾的路径，验证后缀剥离。"""

    def test_strip_json_suffix(self):
        self.assertEqual(static_cache.strip_json_suffix("a/b.json"), "a/b")
        self.assertEqual(static_cache.strip_json_suffix("X.JSON"), "X")
        self.assertEqual(static_cache.strip_json_suffix("no_suffix"), "no_suffix")
        self.assertEqual(static_cache.strip_json_suffix("a.json.bak"), "a.json.bak")


class TestContentHasObjectMeta(unittest.TestCase):
    """2. content_has_object_meta — 传入非合法 JSON 内容，验证解析异常返回 True。"""

    def test_invalid_json_returns_true(self):
        self.assertTrue(static_cache.content_has_object_meta("{bad json"))
        self.assertTrue(static_cache.content_has_object_meta("plain text"))
        self.assertTrue(static_cache.content_has_object_meta("{{"))


class TestTryReadException(unittest.TestCase):
    """3. try_read 兜底异常 — mock 文件操作抛出 OSError，验证返回 None。"""

    def test_read_oserror_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"meta": {"config_version": "v1"}}')
            f_path = f.name
        try:
            with patch("builtins.open", side_effect=OSError("disk error")):
                result = static_cache.try_read(f_path, "v1", ttl_hours=0)
            self.assertIsNone(result)
        finally:
            os.unlink(f_path)


class TestWriteFileReplaceFailure(unittest.TestCase):
    """4. write_file 中 replace 失败 — mock os.replace 抛出异常，验证临时文件清理。"""

    def test_replace_failure_cleans_tmp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "sub", "file.json")
            with patch("static_cache.os.replace", side_effect=OSError("replace fail")):
                result = static_cache.write_file(target, '{"ok": true}')
            self.assertFalse(result)
            # 临时文件不应残留
            files = os.listdir(os.path.join(tmpdir, "sub"))
            tmp_files = [f for f in files if f.endswith(".tmp")]
            self.assertEqual(tmp_files, [])


class TestWriteVersionedFileFailure(unittest.TestCase):
    """5. write_versioned_file 写入失败 — mock write_file 返回 False，验证返回 False。"""

    def test_write_versioned_returns_false_on_failure(self):
        with patch("static_cache.write_file", return_value=False):
            result = static_cache.write_versioned_file("/x/a.json", "v1", "{}")
        self.assertFalse(result)


class TestInvalidateTraversal(unittest.TestCase):
    """6. invalidate 路径穿越 — 传入穿越路径，验证返回 False。"""

    def test_traversal_returns_false(self):
        result = static_cache.invalidate("/../../../etc/passwd")
        self.assertFalse(result)


class TestInvalidateRemoveException(unittest.TestCase):
    """7. invalidate 文件删除异常 — mock os.remove 抛出 OSError，验证返回 False。"""

    def test_remove_oserror_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".json", dir="/tmp", delete=False) as f:
            f_path = f.name
        # 通过 resolve_file_path 映射到该文件
        url = f_path.replace(".json", "").lstrip("/")
        try:
            with patch("static_cache.resolve_file_path", return_value=f_path):
                with patch("static_cache.os.remove", side_effect=OSError("perm denied")):
                    with patch("static_cache.os.path.exists", return_value=True):
                        with patch("static_cache.glob.glob", return_value=[]):
                            result = static_cache.invalidate(f_path)
            self.assertFalse(result)
        finally:
            try:
                os.unlink(f_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
