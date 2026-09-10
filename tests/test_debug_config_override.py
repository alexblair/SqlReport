"""
test_debug_config_override.py — DEBUG 配置覆盖层单元测试（快层，无需真实库）

验证 app_config.debug.json 覆盖语义：
- 无 debug 文件：返回值与现有一致（不触发覆盖）
- 有 debug 文件：dict 深层合并，list/标量整体覆盖，未覆盖段继承
- reload_config() 同样生效
- is_debug_mode() 反映激活状态

用临时文件隔离，不污染仓库内真实配置。
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import app_config

# 其他测试（如 test_api_endpoint）在模块导入期会污染 os.environ 的
# CONFIG_FILE / CONFIG_DB；本模块 setUp 统一清除，确保 _load_config 读取
# 仓库真实 app_config.json，避免环境残留干扰断言。


class TestDebugOverride(unittest.TestCase):
    """DEBUG 配置覆盖行为测试（文件驱动，patch 临时路径）。"""

    def setUp(self):
        for k in ("CONFIG_FILE", "CONFIG_DB", "DEBUG_CONFIG_FILE"):
            os.environ.pop(k, None)
        app_config._config = None

    def _write_debug(self, payload: dict) -> str:
        fd, path = tempfile.mkstemp(prefix="sr-debug-", suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def _no_debug_env(self):
        """返回 patch.dict：清空 CONFIG 相关键，并把 DEBUG_CONFIG_FILE 指向
        不存在的路径，确保即使仓库根存在 app_config.debug.json 也不被读到。
        """
        return patch.dict(os.environ, {
            "DEBUG_CONFIG_FILE": "/tmp/sr-no-debug-not-exists.json",
        }, clear=False)

    def test_no_debug_file_behavior_unchanged(self):
        """无 debug 文件：配置与现有逻辑一致。"""
        with self._no_debug_env():
            app_config._config = None
            cfg = app_config.get_config()
            self.assertFalse(app_config.is_debug_mode())
            self.assertIn("config_db", cfg)
            # 无 debug 文件时 server 段不注入
            self.assertEqual(cfg["config_db"][0]["enable"], True)

    def test_debug_overrides_nested_dict(self):
        """debug 文件存在：server 端口覆盖，未覆盖键继承。"""
        debug_path = self._write_debug({"server": {"port": 9999}})
        with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": debug_path}):
            app_config._config = None
            cfg = app_config.get_config()
            self.assertTrue(app_config.is_debug_mode())
            self.assertEqual(cfg["server"]["port"], 9999)
            # 未覆盖的 host 继承基础配置
            self.assertEqual(cfg["server"]["host"], "0.0.0.0")

    def test_debug_overrides_config_db_list(self):
        """debug 文件整体替换 config_db 列表。"""
        debug_path = self._write_debug({
            "config_db": [
                {"enable": True, "engine": "sqlite3", "path": "test.db"}
            ]
        })
        with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": debug_path}):
            app_config._config = None
            cfg = app_config.get_config()
            self.assertEqual(cfg["config_db"], [
                {"enable": True, "engine": "sqlite3", "path": "test.db"}
            ])

    def test_debug_missing_file_not_active(self):
        """DEBUG_CONFIG_FILE 指向不存在文件：不激活、行为不变。"""
        with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": "/tmp/no-such-debug.json"}):
            app_config._config = None
            cfg = app_config.get_config()
            self.assertFalse(app_config.is_debug_mode())
            self.assertEqual(cfg["server"]["port"], 1000)

    def test_reload_config_applies_debug(self):
        """reload_config() 在 debug 文件写入后重新加载覆盖。"""
        # 初始无 debug（隔离仓库根可能存在的 debug 文件）
        with self._no_debug_env():
            app_config._config = None
            base = app_config.get_config()
            self.assertEqual(base["server"]["port"], 1000)
        # 出现 debug 文件 → reload 生效
        debug_path = self._write_debug({"server": {"port": 7777}})
        with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": debug_path}):
            cfg = app_config.reload_config()
            self.assertEqual(cfg["server"]["port"], 7777)
            self.assertTrue(app_config.is_debug_mode())
        # 清理
        app_config._config = None

    def test_deep_merge_dict_chain(self):
        """深层 dict 合并：多层嵌套也覆盖到最深层。"""
        debug_path = self._write_debug({
            "redis": {"password": "override_pw", "db": 8}
        })
        with patch.dict(os.environ, {"DEBUG_CONFIG_FILE": debug_path}):
            app_config._config = None
            cfg = app_config.get_config()
            self.assertEqual(cfg["redis"]["password"], "override_pw")
            self.assertEqual(cfg["redis"]["db"], 8)
            # 未覆盖的 redis 键继承
            self.assertEqual(cfg["redis"]["default_ttl_hours"], 24)


if __name__ == "__main__":
    unittest.main()
