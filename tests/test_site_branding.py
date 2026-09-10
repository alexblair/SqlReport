"""test_site_branding.py — 站点标识（spec site-branding）行为契约矩阵测试

矩阵来源：.scratch/site-branding/spec.md「行为契约矩阵」A-F 六组（M1-M38）。
断言期望值一律引用矩阵格子，禁止从实现反推。
"""

import base64
import http.client
import http.server
import json
import sqlite3
import threading
import unittest
import urllib.parse
from unittest.mock import patch

import branding
import render
import server as srv
import config

from tests.test_base import BaseConfigTest

_PNG_1PX = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode("ascii")
_ICO_BYTES = branding.DEFAULT_FAVICON_BYTES
_ICO_B64 = base64.b64encode(_ICO_BYTES).decode("ascii")
_DATAURL = "data:image/png;base64," + _PNG_1PX


class _SettingsDB:
    """实例本地站点标识库工厂（临时文件，路径注入 branding._SITE_DB_PATH）。"""

    def __init__(self, **initial):
        import os
        import tempfile
        fd, self.path = tempfile.mkstemp(suffix=".db", prefix="branding-cfg-")
        os.close(fd)
        if initial:
            branding.write_site_settings(initial, path=self.path)

    def dispose(self):
        import os
        try:
            os.unlink(self.path)
        except OSError:
            pass


class BrandingSettingsMixin:
    """把站点标识存储指到临时文件（实例本地库与配置库引擎无关）。"""

    def setUp(self):
        super().setUp()
        self._sdb = _SettingsDB()
        self.settings_patcher = patch.object(
            branding, "_SITE_DB_PATH", self._sdb.path)
        self.settings_patcher.start()
        branding.invalidate_site_branding_cache()

    def tearDown(self):
        self.settings_patcher.stop()
        self._sdb.dispose()
        branding.invalidate_site_branding_cache()
        super().tearDown()

    def _swap_db(self, **kv):
        """替换本地库内容并失效缓存（模拟保存后的读取环境）。"""
        old = self._sdb
        self._sdb = _SettingsDB(**kv)
        self.settings_patcher.stop()
        self.settings_patcher = patch.object(
            branding, "_SITE_DB_PATH", self._sdb.path)
        self.settings_patcher.start()
        branding.invalidate_site_branding_cache()
        old.dispose()


class TestColorNormalize(unittest.TestCase):
    """颜色规范化（矩阵 A 组 M4-M7 的纯函数层）。"""

    def test_m4_valid_3digit_hex(self):
        self.assertEqual(branding.normalize_color("#0f0"), (0, 255, 0))

    def test_valid_6digit_hex(self):
        self.assertEqual(branding.normalize_color("#FF0000"), (255, 0, 0))

    def test_m5_non_hex_rejected(self):
        self.assertIsNone(branding.normalize_color("#GG0000"))

    def test_m6_empty_rejected(self):
        self.assertIsNone(branding.normalize_color(""))

    def test_m7_no_hash_rejected(self):
        self.assertIsNone(branding.normalize_color("ff0000"))

    def test_wrong_length_rejected(self):
        self.assertIsNone(branding.normalize_color("#12345"))

    def test_non_string_rejected(self):
        self.assertIsNone(branding.normalize_color(None))


class TestUploadPipeline(unittest.TestCase):
    """上传校验落盘管线（矩阵 B 组 M14-M22）。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="branding-test-")
        self.root_patcher = patch(
            "branding.custom_favicon_root", return_value=self.tmp)
        self.root_patcher.start()

    def tearDown(self):
        self.root_patcher.stop()
        super().tearDown()

    def test_m14_valid_png_saved(self):
        branding.save_custom_favicon(_PNG_1PX)
        data = branding.load_custom_favicon()
        self.assertTrue(data.startswith(branding.PNG_MAGIC))

    def test_m15_valid_ico_saved(self):
        branding.save_custom_favicon(_ICO_B64)
        data = branding.load_custom_favicon()
        self.assertEqual(data[:4], branding.ICO_MAGIC)

    def test_m16_dataurl_prefix_stripped(self):
        branding.save_custom_favicon(_DATAURL)
        data = branding.load_custom_favicon()
        self.assertTrue(data.startswith(branding.PNG_MAGIC))

    def test_m17_text_forgery_rejected_old_file_intact(self):
        branding.save_custom_favicon(_PNG_1PX)
        with self.assertRaises(branding.BrandingError) as ctx:
            branding.save_custom_favicon(
                base64.b64encode(b"hello not an image").decode())
        self.assertIn("格式", str(ctx.exception))
        self.assertTrue(branding.load_custom_favicon().startswith(
            branding.PNG_MAGIC))

    def test_m18_whitelist_outside_rejected(self):
        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 10).decode()
        with self.assertRaises(branding.BrandingError):
            branding.save_custom_favicon(jpeg)

    def test_m19_empty_rejected(self):
        for bad in ("", "   "):
            with self.assertRaises(branding.BrandingError) as ctx:
                branding.save_custom_favicon(bad)
            self.assertIn("未选择文件", str(ctx.exception))

    def test_m20_oversize_rejected(self):
        big_png = branding.PNG_MAGIC + b"\x00" * (branding.MAX_IMAGE_BYTES + 1)
        with self.assertRaises(branding.BrandingError) as ctx:
            branding.save_custom_favicon(base64.b64encode(big_png).decode())
        self.assertIn("256 KB", str(ctx.exception))

    def test_m21_invalid_base64_rejected(self):
        with self.assertRaises(branding.BrandingError) as ctx:
            branding.save_custom_favicon("!!!!not-base64!!!!")
        self.assertIn("base64", str(ctx.exception))

    def test_m22_replace_atomic_no_corrupt_state(self):
        branding.save_custom_favicon(_PNG_1PX)
        old = branding.load_custom_favicon()
        branding.save_custom_favicon(_ICO_B64)
        new = branding.load_custom_favicon()
        self.assertNotEqual(old, new)
        self.assertEqual(new[:4], branding.ICO_MAGIC)

    def test_load_missing_returns_none(self):
        self.assertIsNone(branding.load_custom_favicon())


class TestFaviconServing(BrandingSettingsMixin, BaseConfigTest):
    """favicon 三模式分派与 HTTP 响应（矩阵 A 组 M1-M13）。"""

    def _set_settings(self, **kv):
        self._swap_db(**kv)

    def _get_favicon(self):
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), srv.ReportHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", "/favicon.ico")
            resp = c.getresponse()
            body = resp.read()
            headers = dict(resp.getheaders())
            status = resp.status
            c.close()
            return status, body, headers
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_m1_fresh_install_returns_builtin(self):
        status, body, _ = self._get_favicon()
        self.assertEqual(status, 200)
        self.assertEqual(body, srv._FAVICON_BYTES)
        self.assertEqual(body[:4], b"\x00\x00\x01\x00")

    def test_m2_default_ignores_residual_values(self):
        self._set_settings(favicon_mode="default",
                           favicon_color="#FF0000",
                           title_prefix="[X] ")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m3_color_mode_generates_colored_ico(self):
        self._set_settings(favicon_mode="color", favicon_color="#FF0000")
        _, body, _ = self._get_favicon()
        self.assertNotEqual(body, srv._FAVICON_BYTES)
        self.assertEqual(body[:4], b"\x00\x00\x01\x00")
        # GS-1 语义：图标主色确为 #FF0000（解包 PNG 像素验证）
        import struct as _struct
        import zlib as _zlib
        png = body[22:]  # ICONDIR(6) + ICONDIRENTRY(16)
        assert png[:8] == branding.PNG_MAGIC
        off = 8
        red_pixels = 0
        dark_pixels = 0
        total = 0
        while off < len(png):
            dlen, typ = _struct.unpack(">I4s", png[off:off + 8])
            data = png[off + 8:off + 8 + dlen]
            if typ == b"IDAT":
                raw = _zlib.decompress(data)
                stride = 1 + 16 * 4  # 每 PNG 行：1 filter byte + 16 像素 RGBA
                for y in range(16):
                    row = raw[y * stride + 1:(y + 1) * stride]
                    for px in range(0, len(row), 4):
                        r, g, b = row[px], row[px + 1], row[px + 2]
                        total += 1
                        if r > 200 and g < 80 and b < 80:
                            red_pixels += 1
                        elif 100 < r < 200 and g < 80 and b < 80:
                            dark_pixels += 1
            off += 12 + dlen
        self.assertEqual(total, 256)
        # 双色设计（GS-1）：内芯纯红 + 外圈暗红，全部像素红通道占优
        self.assertEqual(red_pixels, 144)
        self.assertEqual(dark_pixels, 112)

    def test_m4_http_serves_3digit_color_ico(self):
        self._set_settings(favicon_mode="color", favicon_color="#0f0")
        status, body, _ = self._get_favicon()
        self.assertEqual(status, 200)
        self.assertNotEqual(body, srv._FAVICON_BYTES)

    def test_m9_custom_serves_uploaded_ico(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="branding-srv-")
        with patch("branding.custom_favicon_root", return_value=tmp):
            branding.save_custom_favicon(_ICO_B64)
            self._set_settings(favicon_mode="custom")
            _, body, _ = self._get_favicon()
            with open(f"{tmp}/favicon.img", "rb") as f:
                self.assertEqual(body, f.read())

    def test_m11_deleted_file_falls_back_to_builtin(self):
        import os
        import tempfile
        tmp = tempfile.mkdtemp(prefix="branding-srv-")
        with patch("branding.custom_favicon_root", return_value=tmp):
            branding.save_custom_favicon(_PNG_1PX)
            self._set_settings(favicon_mode="custom")
            os.unlink(f"{tmp}/favicon.img")
            _, body, _ = self._get_favicon()
            self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m24_unauthenticated_post_redirects_to_login(self):
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), srv.ReportHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            body = urllib.parse.urlencode({
                "favicon_mode": "color", "favicon_color": "#FF0000",
                "title_prefix": "", "favicon_data": ""})
            c.request("POST", "/config/site-branding", body=body,
                      headers={"Content-Type":
                               "application/x-www-form-urlencoded"})
            resp = c.getresponse()
            resp.read()
            self.assertEqual(resp.status, 302)
            self.assertIn("/login", resp.getheader("Location") or "")
            c.close()
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_m5_invalid_color_falls_back(self):
        self._set_settings(favicon_mode="color", favicon_color="#GG0000")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m6_empty_color_falls_back(self):
        self._set_settings(favicon_mode="color", favicon_color="")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m7_no_hash_color_falls_back(self):
        self._set_settings(favicon_mode="color", favicon_color="ff0000")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m8_custom_serves_uploaded_png(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="branding-srv-")
        with patch("branding.custom_favicon_root", return_value=tmp):
            branding.save_custom_favicon(_PNG_1PX)
            self._set_settings(favicon_mode="custom")
            _, body, _ = self._get_favicon()
            self.assertTrue(body.startswith(branding.PNG_MAGIC))

    def test_m10_custom_without_file_falls_back(self):
        self._set_settings(favicon_mode="custom")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m12_illegal_mode_falls_back(self):
        self._set_settings(favicon_mode="hacker")
        _, body, _ = self._get_favicon()
        self.assertEqual(body, srv._FAVICON_BYTES)

    def test_m13_cache_control_no_cache(self):
        """修订 M13：no-cache 协商缓存——保存后刷新立即生效（用户反馈回归）。"""
        _, _, headers = self._get_favicon()
        self.assertEqual(headers.get("Cache-Control"), "no-cache")

    def test_content_type_is_icon(self):
        _, _, headers = self._get_favicon()
        self.assertEqual(headers.get("Content-Type"), "image/x-icon")


class TestPageHeaderInjection(BrandingSettingsMixin, BaseConfigTest):
    """页面头注入（矩阵 C 组 M25-M28）。"""

    def _header_title(self):
        html = render.render_page_header(title="Web 报表工具 - 配置",
                                         active_nav="config")
        start = html.index("<title>") + len("<title>")
        end = html.index("</title>")
        return html[start:end], html

    def test_m25_empty_prefix_keeps_title(self):
        title, html = self._header_title()
        self.assertEqual(title, "Web 报表工具 - 配置")
        self.assertNotIn("[DEV]", html)

    def test_m26_prefix_prepended_all_pages(self):
        self._swap_db(title_prefix="[DEV] ")
        title, html = self._header_title()
        self.assertEqual(title, "[DEV] Web 报表工具 - 配置")
        self.assertIn('<link rel="icon" href="/favicon.ico">', html)

    def test_m27_html_in_prefix_escaped(self):
        self._swap_db(title_prefix="<script>alert(1)</script>")
        title, html = self._header_title()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", title)

    def test_m28_full_length_prefix_kept(self):
        self._swap_db(title_prefix="P" * 20)
        title, _ = self._header_title()
        self.assertTrue(title.startswith("P" * 20))


class TestSaveEndpoint(BrandingSettingsMixin, BaseConfigTest):
    """站点标识保存端点整单行为（矩阵 B/D/F 组）。"""

    def setUp(self):
        super().setUp()
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="branding-save-")
        self.root_patcher = patch(
            "branding.custom_favicon_root", return_value=self.tmp)
        self.root_patcher.start()
        self.audit_calls = []
        self.audit_patcher = patch(
            "config_db._write_audit_log",
            side_effect=lambda *a, **kw: self.audit_calls.append((a, kw)))
        self.audit_patcher.start()

    def tearDown(self):
        self.audit_patcher.stop()
        self.root_patcher.stop()
        super().tearDown()

    def _save(self, mode="color", color="#FF0000", prefix="[DEV] ",
              data="", form=None):
        body = form or urllib.parse.urlencode({
            "favicon_mode": mode, "favicon_color": color,
            "title_prefix": prefix, "favicon_data": data})
        return config.handle_site_branding_save(body,
                                                session_user="admin")

    def _settings_now(self):
        return branding.read_site_settings()

    def test_m30_full_valid_submit_persists_three_keys(self):
        code, location, _ = self._save()
        self.assertEqual(code, 302)
        self.assertIn("flash=", location)
        settings = self._settings_now()
        self.assertEqual(settings.get("favicon_mode"), "color")
        self.assertEqual(settings.get("favicon_color"), "#FF0000")
        self.assertEqual(settings.get("title_prefix"), "[DEV] ")

    def test_m31_switch_to_default_prefix_still_effective(self):
        self._save()
        code, _, _ = self._save(mode="default", color="whatever",
                                prefix="[PROD] ")
        self.assertEqual(code, 302)
        settings = self._settings_now()
        self.assertEqual(settings.get("favicon_mode"), "default")
        self.assertEqual(settings.get("title_prefix"), "[PROD] ")

    def test_m32_custom_without_image_allowed_but_hinted(self):
        code, location, _ = self._save(mode="custom", data="")
        self.assertEqual(code, 302)
        self.assertIn("尚未上传", urllib.parse.unquote(location))
        self.assertEqual(self._settings_now().get("favicon_mode"), "custom")

    def test_m33_switch_away_from_custom_keeps_file(self):
        with patch.object(branding, "custom_favicon_path",
                          return_value=f"{self.tmp}/favicon.img"):
            branding.save_custom_favicon(_PNG_1PX)
            self._save(mode="custom", data=_DATAURL)
            self._save(mode="color")
            with open(f"{self.tmp}/favicon.img", "rb") as f:
                self.assertTrue(f.read().startswith(branding.PNG_MAGIC))

    def test_m34_invalid_color_rejects_whole_form(self):
        self._save()  # 先写入合法值
        code, location, _ = self._save(color="#GGG")
        self.assertEqual(code, 302)
        self.assertIn("%E9%94%99%E8%AF%AF", location)  # "错误:"
        settings = self._settings_now()
        self.assertEqual(settings.get("favicon_color"), "#FF0000")

    def test_m29_overlong_prefix_rejected(self):
        code, location, _ = self._save(prefix="X" * 21)
        self.assertEqual(code, 302)
        self.assertIn("20", urllib.parse.unquote(location))
        self.assertNotIn("title_prefix", self._settings_now())

    def test_unknown_mode_rejected(self):
        code, location, _ = self._save(mode="hacker")
        self.assertEqual(code, 302)
        self.assertNotIn("favicon_mode", self._settings_now())

    def test_upload_failure_keeps_config_unchanged(self):
        self._save()
        code, _, _ = self._save(
            mode="custom",
            data=base64.b64encode(b"broken image").decode())
        self.assertEqual(code, 302)
        settings = self._settings_now()
        self.assertEqual(settings.get("favicon_mode"), "color")

    def test_m37_audit_written_with_snapshots(self):
        self._save()  # 先建立 before 状态
        self.audit_calls.clear()
        self._save(color="#00FF00")
        self.assertEqual(len(self.audit_calls), 1)
        args, kwargs = self.audit_calls[0]
        self.assertEqual(args[0], "admin")
        self.assertEqual(args[1], "update_site_setting")
        self.assertEqual(args[2], "site_setting")
        after = json.loads(kwargs["after_value"])
        self.assertEqual(after["favicon_color"], "#00FF00")
        before = json.loads(kwargs["before_value"])
        self.assertEqual(before["favicon_color"], "#FF0000")

    def test_m38_failed_post_writes_no_audit(self):
        self.audit_calls.clear()
        self._save(color="#bad!")
        self.assertEqual(len(self.audit_calls), 0)


class TestSiteSettingsStore(unittest.TestCase):
    """E 组：实例本地库存取（M35/M36，2026-08-24 存储重构后语义）。

    存储定位变更：站点标识是"每部署的身份"，必须与共享配置库解耦——
    M36 由"MySQL upsert 分支"改为"不触碰全局配置引擎连接"。
    """

    def setUp(self):
        self._sdb = _SettingsDB()
        self.patcher = patch.object(branding, "_SITE_DB_PATH", self._sdb.path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self._sdb.dispose()

    def test_m35_upsert_roundtrip(self):
        branding.write_site_settings({
            "favicon_mode": "color", "favicon_color": "#0f0",
            "title_prefix": "[T] "})
        rows = sqlite3.connect(self._sdb.path).execute(
            "SELECT COUNT(*) FROM site_settings").fetchone()[0]
        values = branding.read_site_settings()
        self.assertEqual(rows, 3)
        self.assertEqual(values["favicon_mode"], "color")

    def test_m35b_repeated_set_no_duplicate_rows(self):
        branding.write_site_settings({"favicon_mode": "color"})
        branding.write_site_settings({"favicon_mode": "custom"})
        conn = sqlite3.connect(self._sdb.path)
        count, value = conn.execute(
            "SELECT COUNT(*), MAX(value) FROM site_settings "
            "WHERE key='favicon_mode'").fetchone()
        conn.close()
        self.assertEqual(count, 1)
        self.assertEqual(value, "custom")

    def test_unknown_keys_ignored(self):
        branding.write_site_settings({"evil_key": "x"})
        count = sqlite3.connect(self._sdb.path).execute(
            "SELECT COUNT(*) FROM site_settings").fetchone()[0]
        self.assertEqual(count, 0)

    def test_m36_decoupled_from_config_engine(self):
        """站点标识读写绝不触碰全局配置引擎连接（多部署共用配置库时
        配置互不串扰的根本保证）。"""
        with patch("db.get_config_db",
                   side_effect=AssertionError("禁止触碰全局配置库")):
            branding.write_site_settings({"favicon_mode": "color"})
            self.assertEqual(
                branding.read_site_settings().get("favicon_mode"), "color")

    def test_fresh_file_self_bootstrap(self):
        """空临时目录下首次写入自举建表（新部署零初始化依赖）。"""
        import os
        import tempfile
        fd, fresh = tempfile.mkstemp(suffix=".db", prefix="branding-fresh-")
        os.close(fd)
        os.unlink(fresh)
        try:
            branding.write_site_settings({"title_prefix": "[N] "}, path=fresh)
            got = branding.read_site_settings(path=fresh)
            self.assertEqual(got["title_prefix"], "[N] ")
        finally:
            os.unlink(fresh)

    def test_read_failure_falls_back_to_empty(self):
        """读取异常回退空配置（渲染层永不因存储故障而 500）。"""
        with patch.object(branding, "_site_conn",
                          side_effect=sqlite3.OperationalError("boom")):
            self.assertEqual(branding.read_site_settings(), {})


class TestSaveBrandSignal(BrandingSettingsMixin, BaseConfigTest):
    """保存成功信号 saved_brand=1（T80）：仅纯色保存生效才带标记。"""

    def setUp(self):
        super().setUp()
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="branding-sig-")
        self.root_patcher = patch(
            "branding.custom_favicon_root", return_value=self.tmp)
        self.root_patcher.start()

    def tearDown(self):
        self.root_patcher.stop()
        super().tearDown()

    def _save(self, **kw):
        body = urllib.parse.urlencode(dict(
            favicon_mode=kw.get("mode", "color"),
            favicon_color=kw.get("color", "#FF0000"),
            title_prefix=kw.get("prefix", ""),
            favicon_data=kw.get("data", "")))
        return config.handle_site_branding_save(body, session_user="admin")

    def test_color_save_carries_saved_brand(self):
        code, location, _ = self._save(mode="color")
        self.assertEqual(code, 302)
        self.assertIn("saved_brand=1", location)

    def test_default_save_no_saved_brand(self):
        code, location, _ = self._save(mode="default", color="whatever")
        self.assertEqual(code, 302)
        self.assertNotIn("saved_brand", location)

    def test_custom_save_no_saved_brand(self):
        code, location, _ = self._save(mode="custom", data="")
        self.assertEqual(code, 302)
        self.assertNotIn("saved_brand", location)


class TestColorPickerRender(BrandingSettingsMixin, unittest.TestCase):
    """颜色取色器与最近色面板渲染接线（T77/T78/T79）。"""

    def _render(self, mode, color):
        self._swap_db(favicon_mode=mode, favicon_color=color)
        return config._render_branding_section()

    def test_color_picker_and_recent_panel_wired(self):
        html = self._render("color", "#FF0000")
        self.assertIn('type="color"', html)
        self.assertIn('id="recent-colors"', html)
        self.assertIn('id="favcolor-text"', html)
        self.assertIn("addRecentColor", html)
        self.assertIn("renderRecentColors", html)

    def test_picker_value_normalizes_3digit(self):
        html = self._render("color", "#0f0")
        self.assertIn('id="favcolor" value="#00FF00"', html)

    def test_picker_value_invalid_color_falls_to_brand_default(self):
        html = self._render("color", "#GGG")
        self.assertIn('id="favcolor" value="#4F46E5"', html)

    def test_color_row_hidden_unless_color_mode(self):
        html = self._render("default", "")
        self.assertIn('id="row-color" style="display:none"', html)


if __name__ == "__main__":
    unittest.main()
