"""
test_health.py — 健康检查端点与错误日志测试
"""

import json
import logging
import os
import tempfile
import threading
import time
import unittest
import urllib.request
import http.server

import server as srv


TEST_PORT = 19081
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def _start_server():
    srv.PORT = TEST_PORT
    server = http.server.ThreadingHTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
    srv._server_ref = server
    server.serve_forever()


def _stop_server():
    if hasattr(srv, "_server_ref"):
        srv._server_ref.shutdown()


class TestHealthEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._thread = threading.Thread(target=_start_server, daemon=True)
        cls._thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        _stop_server()

    def test_health_returns_ok(self):
        resp = urllib.request.urlopen(f"{BASE_URL}/health")
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["uptime"], int)
        self.assertGreaterEqual(data["uptime"], 0)

    def test_health_content_type(self):
        resp = urllib.request.urlopen(f"{BASE_URL}/health")
        self.assertIn("application/json", resp.headers.get("Content-Type", ""))

    def test_health_no_auth(self):
        resp = urllib.request.urlopen(f"{BASE_URL}/health")
        self.assertEqual(resp.status, 200)

    def test_route_registered(self):
        route = srv._match_route("GET", "/health")
        self.assertIsNotNone(route)
        self.assertFalse(route.needs_auth)
        self.assertFalse(route.needs_db)


class TestErrorLogConfig(unittest.TestCase):
    def test_get_error_log_config_defaults(self):
        from app_config import reload_config, get_error_log_config
        reload_config()
        cfg = get_error_log_config()
        self.assertIn("enable", cfg)
        self.assertIn("path", cfg)

    def test_get_error_log_config_path_default(self):
        from app_config import reload_config, get_error_log_config
        reload_config()
        cfg = get_error_log_config()
        self.assertEqual(cfg["path"], "error.log")

    def test_error_log_written(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False, mode="w") as f:
            log_path = f.name
        try:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setLevel(logging.WARNING)
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logging.getLogger().addHandler(handler)

            logging.error("测试错误消息")
            handler.flush()
            handler.close()

            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("测试错误消息", content)
        finally:
            os.unlink(log_path)
            logging.getLogger().removeHandler(handler)
