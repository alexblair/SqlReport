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
from unittest.mock import patch

import server as srv


TEST_PORT = 19081
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def _start_server():
    srv.PORT = TEST_PORT
    server = http.server.ThreadingHTTPServer((srv.HOST, srv.PORT), srv.ReportHandler)
    srv._server_ref = server
    server.serve_forever()


def _stop_server():
    if hasattr(srv, "_server_ref") and srv._server_ref is not None:
        srv._server_ref.shutdown()
        srv._server_ref.server_close()
        srv._server_ref = None


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


class TestSetupLoggingErrorLog(unittest.TestCase):
    """缺口17：setup_logging 的 error_log 分支（错误日志文件配置生效）"""

    def _restore_root_logger(self, root, original_handlers, original_level):
        """恢复根 logger 的 handler 集合与级别（避免污染其它测试的日志断言）。"""
        root.handlers[:] = original_handlers
        root.setLevel(original_level)

    def test_error_log_branch_attaches_warning_handler(self):
        """error_log.enable=True → setup_logging 为根 logger 附加指向错误文件的 WARNING handler"""
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        f = tempfile.NamedTemporaryFile(suffix=".log", delete=False, mode="w")
        error_path = f.name
        f.close()
        try:
            with patch("server.get_error_log_config",
                       return_value={"enable": True, "path": error_path}), \
                 patch("server.get_log_config", return_value=(False, "unused.log")):
                srv.setup_logging()

            matching = [h for h in root.handlers
                        if getattr(h, "baseFilename", None) == error_path]
            self.assertTrue(matching, "error_log 配置生效：根 logger 应挂载指向错误文件的 handler")
            self.assertEqual(matching[0].level, logging.WARNING)
            # formatter 带 asctime/levelname（与产品 setup_logging 的格式一致）
            fmt = matching[0].formatter
            self.assertIsNotNone(fmt)
            self.assertIn("%(asctime)s", fmt._fmt)
            self.assertIn("%(levelname)s", fmt._fmt)

            # 真实写入验证：ERROR 记录落到错误文件
            logging.error("error_log 分支测试消息")
            matching[0].flush()
            with open(error_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("error_log 分支测试消息", content)
            self.assertIn("ERROR", content)
        finally:
            self._restore_root_logger(root, original_handlers, original_level)
            os.unlink(error_path)

    def test_error_log_disabled_adds_no_handler(self):
        """error_log.enable=False → setup_logging 不附加错误文件 handler（仅基本配置）"""
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            with patch("server.get_error_log_config",
                       return_value={"enable": False, "path": "error.log"}), \
                 patch("server.get_log_config", return_value=(False, "unused.log")):
                srv.setup_logging()
            matching = [h for h in root.handlers
                        if getattr(h, "baseFilename", None) == "error.log"]
            self.assertEqual(matching, [], "error_log 未启用时不应附加错误文件 handler")
        finally:
            self._restore_root_logger(root, original_handlers, original_level)
