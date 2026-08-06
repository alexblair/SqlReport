"""
test_file_permissions.py — 运行时文件权限管理（static_cache 目录）测试

覆盖：
- 配置解析：缺省/未启用/缺少 user/group/用户或组不存在/非 root 均降级关闭
- load_permissions 成功启用后 uid/gid/mode 解析（含默认值与非法值回退）
- apply_to 单路径 chown/chmod（按 is_dir 选择目录/文件 mode）
- apply_tree/refresh_tree 递归覆盖（含根不存在时先创建）
- static_cache.write_file 在启用时对目录树与临时文件应用权限（replace 前）
- 未启用时 write_file 行为不变（权限应用为 no-op，不抛异常）
"""

import os
import tempfile
import unittest
from unittest.mock import call, patch

import app_config
import file_permissions
import static_cache

_CACHE_DIR = tempfile.mkdtemp(prefix="test_file_perms_")

# 使用 root 用户/组（任何系统都存在），uid/gid 恒为 0
_PERM_CFG = {
    "enable": True,
    "user": "root",
    "group": "root",
    "dir_mode": "0755",
    "file_mode": "0644",
}


def _reset_state():
    """重置模块内部状态为未启用（load_permissions 会重新填充）。"""
    file_permissions._enabled = False
    file_permissions._uid = None
    file_permissions._gid = None


def _enable_for_test(uid=33, gid=33, dir_mode=0o755, file_mode=0o644):
    """直接填充启用状态（绕开 load_permissions 的 root 判定，便于单测）。"""
    _reset_state()
    file_permissions._enabled = True
    file_permissions._uid = uid
    file_permissions._gid = gid
    file_permissions._dir_mode = dir_mode
    file_permissions._file_mode = file_mode


class TestConfigParsing(unittest.TestCase):
    def test_config_default_disabled(self):
        """配置段缺失时 get_file_permissions_config 返回未启用。"""
        with patch("app_config.get_config", return_value={}):
            self.assertEqual(app_config.get_file_permissions_config(),
                             {"enable": False})

    def test_load_disabled_when_missing(self):
        """配置段缺失/未启用 → load_permissions 返回 False。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": False}):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    def test_load_disabled_missing_user_group(self):
        """启用但缺 user/group → 关闭。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True}):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_load_disabled_unknown_user(self, _m):
        """用户不存在 → 关闭并告警。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True, "user": "no_such_user_xyz",
                                 "group": "root"}):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    def test_load_disabled_not_root(self):
        """非 root 进程无法 chown 到其他用户 → 关闭（不阻塞业务）。"""
        with patch("file_permissions.os.geteuid", return_value=1000), \
                patch("app_config.get_file_permissions_config",
                      return_value=_PERM_CFG):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_load_enabled_parses_ids_and_modes(self, _m):
        """启用成功：解析出 uid/gid 与权限位。"""
        with patch("app_config.get_file_permissions_config",
                   return_value=_PERM_CFG):
            self.assertTrue(file_permissions.load_permissions())
        try:
            self.assertTrue(file_permissions.is_enabled())
            self.assertEqual(file_permissions._uid, 0)
            self.assertEqual(file_permissions._gid, 0)
            self.assertEqual(file_permissions._dir_mode, 0o755)
            self.assertEqual(file_permissions._file_mode, 0o644)
        finally:
            _reset_state()

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_mode_defaults_when_omitted(self, _m):
        """只配置 user/group 时 mode 用默认 0755/0644。"""
        cfg = {k: v for k, v in _PERM_CFG.items()
               if k not in ("dir_mode", "file_mode")}
        with patch("app_config.get_file_permissions_config", return_value=cfg):
            self.assertTrue(file_permissions.load_permissions())
        try:
            self.assertEqual(file_permissions._dir_mode, 0o755)
            self.assertEqual(file_permissions._file_mode, 0o644)
        finally:
            _reset_state()

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_invalid_mode_falls_back_default(self, _m):
        """非法 mode：字符串回退默认，整数取低 12 位。"""
        cfg = dict(_PERM_CFG, dir_mode="not-a-mode", file_mode=0o600)
        with patch("app_config.get_file_permissions_config", return_value=cfg):
            self.assertTrue(file_permissions.load_permissions())
        try:
            self.assertEqual(file_permissions._dir_mode, 0o755,
                             "非法字符串 mode 回退默认")
            self.assertEqual(file_permissions._file_mode, 0o600,
                             "整数 mode 按数值取低 12 位")
        finally:
            _reset_state()

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_numeric_user_group_accepted(self, _m):
        """数字 uid/gid 字符串同样可解析。"""
        cfg = dict(_PERM_CFG, user="0", group="0")
        with patch("app_config.get_file_permissions_config", return_value=cfg):
            self.assertTrue(file_permissions.load_permissions())
        try:
            self.assertEqual((file_permissions._uid, file_permissions._gid),
                             (0, 0))
        finally:
            _reset_state()


class TestApply(unittest.TestCase):
    def setUp(self):
        _enable_for_test()
        self._tmp = tempfile.mkdtemp(prefix="fp_apply_")

    def tearDown(self):
        _reset_state()

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown")
    def test_apply_to_file_uses_file_mode(self, m_chown, m_chmod):
        """文件用 file_mode；is_dir=None 时按路径实际类型选择。"""
        p = os.path.join(self._tmp, "a.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        file_permissions.apply_to(p)
        m_chown.assert_called_once_with(p, 33, 33)
        m_chmod.assert_called_once_with(p, 0o644)

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown")
    def test_apply_to_dir_uses_dir_mode(self, m_chown, m_chmod):
        """目录用 dir_mode。"""
        p = os.path.join(self._tmp, "sub")
        os.makedirs(p)
        file_permissions.apply_to(p)
        m_chmod.assert_called_once_with(p, 0o755)

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown")
    def test_apply_tree_recursive(self, m_chown, m_chmod):
        """apply_tree 递归覆盖全部目录与文件。"""
        sub = os.path.join(self._tmp, "api", "nested")
        os.makedirs(sub)
        files = [os.path.join(self._tmp, "a.json"),
                 os.path.join(sub, "b.json")]
        for f in files:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("{}")
        file_permissions.apply_tree(self._tmp)
        for path in (self._tmp, os.path.join(self._tmp, "api"), sub):
            self.assertIn(call(path, 33, 33), m_chown.call_args_list,
                          f"目录 {path} 应被 chown")
        for f in files:
            self.assertIn(call(f, 33, 33), m_chown.call_args_list,
                          f"文件 {f} 应被 chown")

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown")
    def test_refresh_tree_creates_missing_root(self, m_chown, m_chmod):
        """refresh_tree 在根不存在时先创建再应用权限。"""
        target = os.path.join(self._tmp, "fresh")
        file_permissions.refresh_tree(target)
        self.assertTrue(os.path.isdir(target))
        m_chown.assert_called_once_with(target, 33, 33)

    def test_disabled_apply_noop(self):
        """未启用时 apply_to/apply_tree/refresh_tree 均为 no-op。"""
        _reset_state()
        p = os.path.join(self._tmp, "x.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        file_permissions.apply_to(p)
        file_permissions.apply_tree(self._tmp)
        file_permissions.refresh_tree(self._tmp)
        self.assertTrue(os.path.isfile(p), "未启用时不应改变既有文件")


class TestWriteFileIntegration(unittest.TestCase):
    def setUp(self):
        _enable_for_test()

    def tearDown(self):
        _reset_state()

    @patch("file_permissions.apply_tree")
    @patch("file_permissions.apply_to")
    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_write_file_applies_permissions_before_replace(self, _m, m_apply_to,
                                                            m_apply_tree):
        """启用时：目录树刷新权限，临时文件在 replace 前应用文件权限。"""
        p = static_cache.resolve_file_path("api/perm")
        self.assertTrue(static_cache.write_file(p, '{"a": 1}'))
        m_apply_tree.assert_called_once_with(os.path.dirname(p))
        self.assertEqual(m_apply_to.call_count, 1)
        tmp_path = m_apply_to.call_args[0][0]
        self.assertTrue(tmp_path.endswith(".tmp"),
                        "权限应应用在临时文件上（replace 前），而非最终文件")
        self.assertEqual(m_apply_to.call_args[1], {"is_dir": False})

    @patch("file_permissions.apply_tree")
    @patch("file_permissions.apply_to")
    @patch("static_cache.get_static_cache_config",
           return_value={"enable": True, "dir": _CACHE_DIR})
    def test_write_file_disabled_still_writes(self, _m, m_apply_to, m_apply_tree):
        """未启用时写入正常，权限应用为 no-op 不抛异常。"""
        _reset_state()
        p = static_cache.resolve_file_path("api/noperm")
        self.assertTrue(static_cache.write_file(p, "{}"))
        self.assertTrue(os.path.isfile(p))
        m_apply_tree.assert_called_once_with(os.path.dirname(p))
        m_apply_to.assert_called_once()


# ---------------------------------------------------------------------------
# 缺口15：组不存在时降级关闭（load_permissions 返回 False，不阻塞启动）
# ---------------------------------------------------------------------------


class TestGroupMissingDegradation(unittest.TestCase):
    def tearDown(self):
        _reset_state()

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_load_disabled_unknown_group(self, _m):
        """组不存在 → 降级关闭并记 warning（不抛异常）。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True, "user": "root",
                                 "group": "no_such_group_xyz"}):
            with self.assertLogs("root", level="WARNING") as logs:
                self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())
        self.assertTrue(any("组" in m for m in logs.output),
                        "应记录组不存在的 warning")

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_load_disabled_unknown_numeric_gid(self, _m):
        """数字 gid 不存在 → 同样降级关闭。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True, "user": "root",
                                 "group": "299999"}):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    @patch("file_permissions.os.geteuid", return_value=0)
    def test_load_disabled_unknown_user_unknown_group(self, _m):
        """用户与组都不存在 → 关闭（uid 先判 None 短路，不报组）。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True, "user": "no_user_xyz",
                                 "group": "no_group_xyz"}):
            self.assertFalse(file_permissions.load_permissions())
        self.assertFalse(file_permissions.is_enabled())

    def test_disabled_after_load_failure_write_still_works(self):
        """load 失败后 static_cache 写入不受影响（权限关闭=原行为）。"""
        with patch("app_config.get_file_permissions_config",
                   return_value={"enable": True, "user": "root",
                                 "group": "no_such_group_xyz"}), \
                patch("static_cache.get_static_cache_config",
                      return_value={"enable": True, "dir": _CACHE_DIR}):
            self.assertFalse(file_permissions.load_permissions())
            p = static_cache.resolve_file_path("api/after_group_fail")
            self.assertTrue(static_cache.write_file(p, "{}"))
        self.assertTrue(os.path.isfile(p))


# ---------------------------------------------------------------------------
# 缺口16：权限应用失败静默降级（chown/chmod/walk/makedirs 失败不抛异常）
# ---------------------------------------------------------------------------


class TestApplyFailureDegradation(unittest.TestCase):
    def setUp(self):
        _enable_for_test()
        self._tmp = tempfile.mkdtemp(prefix="fp_fail_")

    def tearDown(self):
        _reset_state()

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown",
           side_effect=OSError("chown: Operation not permitted"))
    def test_apply_to_chown_error_no_raise(self, m_chown, m_chmod):
        """chown 失败（如权限不足）→ 记录 warning，不抛异常。"""
        p = os.path.join(self._tmp, "a.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        with self.assertLogs("root", level="WARNING") as logs:
            file_permissions.apply_to(p)   # 不应抛
        m_chown.assert_called_once_with(p, 33, 33)
        self.assertTrue(any("无法应用权限" in m for m in logs.output))

    @patch("file_permissions.os.chown")
    @patch("file_permissions.os.chmod",
           side_effect=OSError("chmod: EPERM"))
    def test_apply_to_chmod_error_no_raise(self, m_chmod, m_chown):
        """chmod 失败 → 记录 warning，不抛异常（chown 已成功也吞掉）。"""
        p = os.path.join(self._tmp, "b.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        with self.assertLogs("root", level="WARNING"):
            file_permissions.apply_to(p)
        m_chown.assert_called_once_with(p, 33, 33)

    @patch("file_permissions.os.walk",
           side_effect=OSError("walk: ENOENT"))
    def test_apply_tree_walk_error_no_raise(self, m_walk):
        """os.walk 失败 → 记录 warning，不抛异常。"""
        with self.assertLogs("root", level="WARNING") as logs:
            file_permissions.apply_tree("/no/such/dir")
        m_walk.assert_called_once_with("/no/such/dir")
        self.assertTrue(any("遍历目录失败" in m for m in logs.output))

    @patch("file_permissions.os.makedirs",
           side_effect=OSError("mkdir: EACCES"))
    def test_refresh_tree_makedirs_error_no_raise(self, m_mkdir):
        """根目录创建失败 → 记录 warning 并返回，不抛异常。"""
        with self.assertLogs("root", level="WARNING") as logs:
            file_permissions.refresh_tree("/no/such/root")
        m_mkdir.assert_called_once_with("/no/such/root")
        self.assertTrue(any("创建缓存目录失败" in m for m in logs.output))

    @patch("file_permissions.os.chmod")
    @patch("file_permissions.os.chown",
           side_effect=OSError("chown: EPERM"))
    def test_write_file_survives_apply_failure(self, m_chown, m_chmod):
        """应用失败时 static_cache.write_file 仍完成写入（降级不阻塞）。"""
        p = os.path.join(self._tmp, "c.json")
        with patch("static_cache.get_static_cache_config",
                   return_value={"enable": True, "dir": _CACHE_DIR}):
            with self.assertLogs("root", level="WARNING"):
                ok = static_cache.write_file(p, '{"ok": true}')
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(p))
        with open(p, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
