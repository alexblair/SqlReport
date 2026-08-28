"""
test_app_config_extra.py — app_config.py 未覆盖路径的单元测试

覆盖路径：
1. _load_debug_config: 文件存在但内容损坏的 except 分支
2. _load_config: 配置文件不存在 / JSON 损坏的默认配置回退
3. get_server_config: port 非法值回退到默认端口
4. ensure_api_prefix: 空路径抛 ValueError
5. strip_api_prefix: /apiFoo 路径剥离
6. serialize_json: 传入自定义 cls
7. _smart_scalar: 嵌套 Decimal 序列化
8. _smart_decimal_text: Decimal("-0") 归一化为 "0"
9. get_active_db_config: 全禁用返回默认 SQLite
10. get_log_config: log 配置段解析
11. get_test_mysql_config: test_mysql 配置段
"""

import json
import os
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

import app_config


class TestLoadDebugConfigCorrupted(unittest.TestCase):
    """1. _load_debug_config: 文件存在但内容损坏的 except 分支"""

    def test_corrupted_debug_config_returns_none(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json content")
            tmp_path = f.name
        try:
            with mock.patch.dict(os.environ, {"DEBUG_CONFIG_FILE": tmp_path}):
                result = app_config._load_debug_config()
                self.assertIsNone(result)
        finally:
            os.unlink(tmp_path)


class TestLoadConfigMissingCorrupted(unittest.TestCase):
    """2. _load_config: 配置文件不存在 / JSON 损坏的默认配置回退"""

    def test_missing_config_file_returns_default(self):
        with mock.patch.dict(os.environ, {"CONFIG_FILE": "/nonexistent/path/config.json"}):
            result = app_config._load_config()
            self.assertEqual(result["config_db"][0]["engine"], "sqlite3")
            self.assertEqual(result["config_db"][0]["path"], "config.db")

    def test_corrupted_config_file_returns_default(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            tmp_path = f.name
        try:
            with mock.patch.dict(os.environ, {"CONFIG_FILE": tmp_path}):
                result = app_config._load_config()
                self.assertEqual(result["config_db"][0]["engine"], "sqlite3")
        finally:
            os.unlink(tmp_path)


class TestGetServerConfigInvalidPort(unittest.TestCase):
    """3. get_server_config: port 非法值回退到默认端口"""

    def test_invalid_port_falls_back_to_default(self):
        with mock.patch.object(app_config, 'get_config', return_value={"server": {"port": "abc"}}):
            host, port = app_config.get_server_config()
            self.assertEqual(port, 8080)

    def test_none_port_falls_back_to_default(self):
        with mock.patch.object(app_config, 'get_config', return_value={"server": {"port": None}}):
            host, port = app_config.get_server_config()
            self.assertEqual(port, 8080)


class TestEnsureApiPrefixEmpty(unittest.TestCase):
    """4. ensure_api_prefix: 空路径抛 ValueError"""

    def test_empty_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            app_config.ensure_api_prefix("")

    def test_whitespace_only_raises_value_error(self):
        with self.assertRaises(ValueError):
            app_config.ensure_api_prefix("   ")


class TestStripApiPrefixFoo(unittest.TestCase):
    """5. strip_api_prefix: /apiFoo 路径剥离"""

    def test_api_foo_path_strips_prefix(self):
        result = app_config.strip_api_prefix("/apiFoo")
        self.assertEqual(result, "Foo")


class TestSerializeJsonCustomCls(unittest.TestCase):
    """6. serialize_json: 传入自定义 cls"""

    def test_custom_cls_not_inject_default_str(self):
        class CustomEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, Decimal):
                    return str(obj)
                return super().default(obj)

        data = {"value": Decimal("3.14")}
        result = app_config.serialize_json(data, cls=CustomEncoder)
        parsed = json.loads(result)
        self.assertEqual(parsed["value"], "3.14")


class TestSmartScalarNestedDecimal(unittest.TestCase):
    """7. _smart_scalar: 嵌套 Decimal 序列化"""

    def test_nested_decimal_in_list(self):
        data = {"items": [Decimal("1.5"), Decimal("2.5")]}
        result = app_config.serialize_smart_quotes(data, flags=app_config.SMART_FLAG_DECIMAL)
        self.assertIn("1.5", result)
        self.assertIn("2.5", result)

    def test_nested_decimal_in_dict(self):
        data = {"nested": {"value": Decimal("9.99")}}
        result = app_config.serialize_smart_quotes(data, flags=app_config.SMART_FLAG_DECIMAL)
        self.assertIn("9.99", result)


class TestSmartDecimalTextNegativeZero(unittest.TestCase):
    """8. _smart_decimal_text: Decimal("-0") 归一化为 '0'"""

    def test_negative_zero_becomes_zero(self):
        result = app_config._smart_decimal_text(Decimal("-0"))
        self.assertEqual(result, "0")

    def test_negative_zero_decimal_becomes_zero(self):
        result = app_config._smart_decimal_text(Decimal("-0.0"))
        self.assertEqual(result, "0")


class TestGetActiveDbConfigAllDisabled(unittest.TestCase):
    """9. get_active_db_config: 全禁用返回默认 SQLite"""

    def test_all_disabled_returns_default_sqlite(self):
        config = {
            "config_db": [
                {"enable": False, "engine": "mysql", "host": "localhost"},
                {"enable": False, "engine": "sqlite3", "path": "other.db"}
            ]
        }
        with mock.patch.object(app_config, 'get_config', return_value=config):
            result = app_config.get_active_db_config()
            self.assertEqual(result["engine"], "sqlite3")
            self.assertEqual(result["path"], "config.db")


class TestGetLogConfig(unittest.TestCase):
    """10. get_log_config: log 配置段解析"""

    def test_log_config_enabled(self):
        config = {"log": {"enable": True, "path": "app.log"}}
        with mock.patch.object(app_config, 'get_config', return_value=config):
            enabled, path = app_config.get_log_config()
            self.assertTrue(enabled)
            self.assertEqual(path, "app.log")

    def test_log_config_disabled(self):
        config = {"log": {"enable": False, "path": "app.log"}}
        with mock.patch.object(app_config, 'get_config', return_value=config):
            enabled, path = app_config.get_log_config()
            self.assertFalse(enabled)

    def test_log_config_missing(self):
        with mock.patch.object(app_config, 'get_config', return_value={}):
            enabled, path = app_config.get_log_config()
            self.assertFalse(enabled)
            self.assertEqual(path, "run.log")


class TestGetTestMysqlConfig(unittest.TestCase):
    """11. get_test_mysql_config: test_mysql 配置段"""

    def test_test_mysql_enabled(self):
        config = {
            "test_mysql": {
                "enable": True,
                "host": "127.0.0.1",
                "port": 3306,
                "user": "test"
            }
        }
        with mock.patch.object(app_config, 'get_config', return_value=config):
            result = app_config.get_test_mysql_config()
            self.assertEqual(result["host"], "127.0.0.1")

    def test_test_mysql_disabled(self):
        config = {"test_mysql": {"enable": False, "host": "127.0.0.1"}}
        with mock.patch.object(app_config, 'get_config', return_value=config):
            result = app_config.get_test_mysql_config()
            self.assertEqual(result, {})

    def test_test_mysql_missing_host(self):
        config = {"test_mysql": {"enable": True}}
        with mock.patch.object(app_config, 'get_config', return_value=config):
            result = app_config.get_test_mysql_config()
            self.assertEqual(result, {})

    def test_test_mysql_missing(self):
        with mock.patch.object(app_config, 'get_config', return_value={}):
            result = app_config.get_test_mysql_config()
            self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
