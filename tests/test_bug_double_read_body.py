"""
test_bug_double_read_body.py — 验证 POST 保存后页面卡住的问题

根因：_handle_config/_handle_report 中 _read_body() 被调用两次
（第一次读取表单数据，第二次在 _log_web_access 中又调用一次），
导致 self.rfile.read() 在已消耗的流上阻塞。

回归测试：POST 请求应在合理时间内返回（不 hang）。
"""

import unittest
import threading
import time
import urllib.request
import urllib.error
import http.server
import os
import tempfile
from http.cookiejar import CookieJar

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="test_bug_")
_tmp_db.close()
os.environ["CONFIG_DB"] = _tmp_db.name

import db
import auth
import server as srv

TEST_PORT = 19082
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"
TIMEOUT = 5


def _set_up_db():
    conn = db.get_config_db()
    db.init_db(conn)
    if not db.get_user(conn, "admin"):
        pw_hash = auth.hash_password("admin123")
        db.add_user(conn, "admin", pw_hash)
    conn.close()


_server_ref = None


def _start_server():
    global _server_ref
    _server_ref = http.server.HTTPServer((srv.HOST, TEST_PORT), srv.ReportHandler)
    _server_ref.serve_forever()


class TestDoubleReadBodyBug(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _set_up_db()
        cls._thread = threading.Thread(target=_start_server, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        if _server_ref:
            _server_ref.shutdown()
        db_path = _tmp_db.name
        if os.path.exists(db_path):
            os.remove(db_path)

    def _login(self):
        cj = CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj)
        )
        data = urllib.parse.urlencode({
            "username": "admin", "password": "admin123"
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/login", data=data, method="POST"
        )
        opener.open(req)
        return opener

    def _assert_no_hang(self, resp_or_exc):
        """确认请求未 hang（在 TIMEOUT 内返回）"""
        # 如果走到这里，说明请求在 TIMEOUT 内返回了，没 hang
        pass

    def test_config_pool_add_does_not_hang(self):
        """POST /config/pools/add 不应 hang"""
        opener = self._login()
        form_data = urllib.parse.urlencode({
            "name": "test_pool",
            "host": "127.0.0.1",
            "port": "3306",
            "user": "test",
            "password": "test",
            "database": "test",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/config/pools/add",
            data=form_data, method="POST",
        )
        start = time.time()
        try:
            opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            pass  # 即使是 HTTP 错误，只要不 hang 就说明修复有效
        except Exception as e:
            self.fail(f"请求异常（需检查是否为 hang 导致）: {e}")
        elapsed = time.time() - start
        self.assertLess(elapsed, TIMEOUT,
                        f"请求耗时 {elapsed:.2f}s，疑似因二次 _read_body 卡住")

    def test_report_preview_does_not_hang(self):
        """POST /report/preview 不应 hang"""
        opener = self._login()
        form_data = urllib.parse.urlencode({
            "id": "1", "sql_query": "SELECT 1",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/report/preview",
            data=form_data, method="POST",
        )
        start = time.time()
        try:
            opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            pass
        except Exception as e:
            self.fail(f"请求异常: {e}")
        elapsed = time.time() - start
        self.assertLess(elapsed, TIMEOUT,
                        f"请求耗时 {elapsed:.2f}s，疑似因二次 _read_body 卡住")

    def test_config_user_add_does_not_hang(self):
        """POST /config/users/add 不应 hang"""
        opener = self._login()
        form_data = urllib.parse.urlencode({
            "username": "newuser", "password": "pass123",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/config/users/add",
            data=form_data, method="POST",
        )
        start = time.time()
        try:
            opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            pass
        except Exception as e:
            self.fail(f"请求异常: {e}")
        elapsed = time.time() - start
        self.assertLess(elapsed, TIMEOUT,
                        f"请求耗时 {elapsed:.2f}s，疑似因二次 _read_body 卡住")


if __name__ == "__main__":
    unittest.main()
