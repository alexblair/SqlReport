"""
test_branding_e2e.py — 站点标识功能端到端可用性测试（真实 HTTP 全链路）

背景教训：单测/mock 层全部通过 ≠ 功能可用——site-branding 首版路由未接线
（POST /config/site-branding 无注册项），mock 测试全绿但真实保存必然失败，
由用户实测发现。本文件补齐「起真服务器 + urllib 真请求」的可用性回归：
登录 → 配置页表单在 → POST 保存 → favicon/标题立即生效 → 非法输入整单拒绝。
"""

import unittest
import threading
import time
import urllib.request
import urllib.parse
import http.server
import os
import tempfile
from http.cookiejar import CookieJar
from unittest.mock import patch

# 临时数据库 / 图片目录（仅预创建对象；environ 与 branding 目录改写
# 收敛在 setUpClass/tearDownClass 内完成并恢复原值——模块级永久改写
# 会串扰 discover 同进程的后续测试模块）
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="test_branding_e2e_")
_tmp_db.close()
_tmp_dir = tempfile.TemporaryDirectory(prefix="test_branding_e2e_imgs_")

import db
import auth
import branding
import server as srv


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁用自动重定向，便于断言 302 的 Location"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _login_opener(base_url: str):
    """返回已登录 admin 的 opener（不自动跟随重定向）"""
    cj = CookieJar()
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{base_url}/login", data=data, method="POST")
    try:
        opener.open(req)
    except urllib.error.HTTPError:
        pass
    return opener


class TestBrandingEndToEnd(unittest.TestCase):
    """站点标识：真实服务器 + 真实 HTTP 请求的可用性回归"""

    @classmethod
    def setUpClass(cls):
        # 强制 SQLite（app_config.json 可能启用 MySQL 配置库，
        # e2e 必须隔离到临时库，绝不触碰真实引擎）
        cls._engine_patch = patch.object(db, "_get_engine", return_value="sqlite3")
        cls._engine_patch.start()
        # 环境变量与图标落盘目录：类生命周期内生效，结束恢复原值
        cls._old_env = os.environ.get("CONFIG_DB")
        os.environ["CONFIG_DB"] = _tmp_db.name
        cls._old_branding_dir = branding._BRANDING_DIR
        branding._BRANDING_DIR = os.path.join(_tmp_dir.name, "branding")
        # 站点标识实例本地库同样指到临时文件（默认 config.db 是仓库
        # 工作目录的真实文件，绝不触碰）
        cls._old_site_db = branding._SITE_DB_PATH
        branding._SITE_DB_PATH = os.path.join(_tmp_dir.name, "config.db")
        conn = db.get_config_db()
        db.init_db(conn)
        if not db.get_user(conn, "admin"):
            db.add_user(conn, "admin", auth.hash_password("admin123"))
        conn.close()
        branding.invalidate_site_branding_cache()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.ReportHandler)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls._thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        branding.invalidate_site_branding_cache()
        cls._engine_patch.stop()
        if cls._old_env is None:
            os.environ.pop("CONFIG_DB", None)
        else:
            os.environ["CONFIG_DB"] = cls._old_env
        branding._BRANDING_DIR = cls._old_branding_dir
        branding._SITE_DB_PATH = cls._old_site_db
        os.unlink(_tmp_db.name)
        _tmp_dir.cleanup()

    def setUp(self):
        self.opener = _login_opener(self.base)

    def _post_form(self, fields: dict, url="/config/site-branding"):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(f"{self.base}{url}", data=data, method="POST")
        try:
            resp = self.opener.open(req, timeout=10)
            return resp.status, resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.headers

    def _get(self, path):
        """带登录态 GET（favicon 公开页同样适用）"""
        try:
            resp = self.opener.open(f"{self.base}{path}", timeout=10)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    # ------------------------------------------------------------------
    # 可用性链路 1：配置页表单存在且 action 指向已注册路由
    # ------------------------------------------------------------------

    def test_config_page_has_branding_form(self):
        _, body, _ = self._get("/config")
        html = body.decode("utf-8")
        self.assertIn("站点标识", html)
        self.assertIn('action="/config/site-branding"', html)

    # ------------------------------------------------------------------
    # 可用性链路 2：color 模式保存后刷新立即生效（favicon 字节 + 标题前缀）
    # ------------------------------------------------------------------

    def test_save_color_mode_immediate_effect(self):
        status, headers = self._post_form({
            "favicon_mode": "color",
            "favicon_color": "#FF0000",
            "title_prefix": "[DEV] ",
        })
        self.assertEqual(status, 302)
        self.assertTrue(headers.get("Location", "").startswith("/config?flash="))

        # favicon 立即变红（无 5 分钟缓存窗口）
        _, fav, hdrs = self._get("/favicon.ico")
        self.assertEqual(fav, branding.build_color_favicon("#FF0000"))
        self.assertEqual(hdrs.get("Cache-Control"), "no-cache")

        # 标题前缀立即出现在任意页面 <title>
        _, page, _ = self._get("/config")
        self.assertIn("<title>[DEV] ", page.decode("utf-8"))

    # ------------------------------------------------------------------
    # 可用性链路 3：custom 模式 base64 上传后按原字节服务
    # ------------------------------------------------------------------

    def test_save_custom_upload_served_verbatim(self):
        png = branding.build_color_favicon("#00AA00")
        data_url = "data:image/png;base64," + __import__("base64").b64encode(png).decode()
        status, _ = self._post_form({
            "favicon_mode": "custom",
            "favicon_data": data_url,
            "title_prefix": "",
        })
        self.assertEqual(status, 302)
        _, fav, _ = self._get("/favicon.ico")
        self.assertEqual(fav, png)

    # ------------------------------------------------------------------
    # 可用性链路 4：非法输入整单拒绝，配置不被破坏（M34）
    # ------------------------------------------------------------------

    def test_invalid_color_rejected_no_partial_save(self):
        # 前置：先写入一份合法 color 配置（用例自建状态，不依赖执行顺序）
        status, _ = self._post_form({
            "favicon_mode": "color", "favicon_color": "#0000FF",
            "title_prefix": ""})
        self.assertEqual(status, 302)
        # 非法提交：颜色不合法
        status, headers = self._post_form({
            "favicon_mode": "color",
            "favicon_color": "red",
            "title_prefix": "",
        })
        self.assertEqual(status, 302)
        self.assertIn("flash=%E9%94%99%E8%AF%AF", headers.get("Location", ""))
        # 整单校验（M34）：先前合法配置保持不变，favicon 不回退默认
        _, fav, _ = self._get("/favicon.ico")
        self.assertEqual(fav, branding.build_color_favicon("#0000FF"))

    # ------------------------------------------------------------------
    # 可用性链路 5：未认证 POST 被认证中间件拦截
    # ------------------------------------------------------------------

    def test_unauthenticated_post_redirects_to_login(self):
        data = urllib.parse.urlencode({"favicon_mode": "default"}).encode()
        req = urllib.request.Request(f"{self.base}/config/site-branding",
                                     data=data, method="POST")
        try:
            urllib.request.build_opener(_NoRedirect).open(req)
            self.fail("预期重定向到登录页")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertTrue(e.headers.get("Location", "").startswith("/login"))


if __name__ == "__main__":
    unittest.main()
