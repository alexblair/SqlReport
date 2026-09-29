"""
tests/test_test_isolation.py — 测试隔离金丝雀

为什么需要这个文件：
    `tests/_bootstrap.py` 的隔离**只在 `tests` 包被导入时执行**。而
    `python -m unittest discover -s tests/`（漏掉 `-t .`）会把测试模块当
    顶层模块导入（`test_health` 而非 `tests.test_health`），包根本不被
    加载——整套隔离（DEBUG_CONFIG_FILE / vendor 落点 / branding 库 / Redis）
    全部静默失效。2026-09-29 实测该状态下测试进程会连**生产 Redis**
    （主 app_config.json 的 redis.enable=true，db 6、key_prefix webreport_），
    读写真实快照，断言依赖进程外状态。

    只靠「文档里写清楚要用 `-t .`」是不够的——任何人漏一次就静默回到危险
    状态，且要很久以后才被 unrelated 的测试失败发现。本文件把这件事变成
    一条**会自己报警的断言**。

判据为什么用「本模块的导入风格」而不是「隔离当前是否生效」：
    后者会被自我掩盖——本文件若 import 了 `tests`，`tests/__init__.py` 就替
    我们装上隔离，于是「隔离生效」恒为真，金丝雀形同虚设（第一版就是这么
    写错的，漏 `-t .` 时它反而全绿）。`__name__` 在模块导入时确定，是顶层
    模块（`test_test_isolation`）还是包模块（`tests.test_test_isolation`）
    直接反映了 discover 的入口写法，无法被后续导入掩盖。

它测的不是业务逻辑，而是**测试环境自身的健康度**，所以模块顶层刻意不
`import tests`。
"""

import importlib
import unittest

# 模块导入时确定：能否证明本次运行走了会加载 tests/__init__.py 的入口。
_IMPORTED_AS_PACKAGE_MODULE = __name__.startswith("tests.")


class TestIsolationEntryIsCorrect(unittest.TestCase):
    """入口检查：discover 必须带 `-t .`，否则隔离根本不会执行。"""

    def test_imported_as_package_module(self):
        """✅ 核心判据：必须以 `tests.xxx` 形式被导入。

        失败即表示用了 `discover -s tests/`（漏 `-t .`）。
        """
        if not _IMPORTED_AS_PACKAGE_MODULE:
            self.fail(
                f"测试入口不对：本文件被当作顶层模块 `{__name__}` 导入，"
                f"说明用了 `discover -s tests/`（漏了 `-t .`）。\n"
                f"  后果：tests/__init__.py 不会被执行，测试进程隔离全部失效——\n"
                f"        会连生产 Redis（主 app_config.json 的 redis.enable=true，\n"
                f"        db 6、key_prefix webreport_）读写真实快照，\n"
                f"        并写真实 static/vendor/self@*/ 目录、读本机 config.db。\n"
                f"  修复：`python -m unittest discover -s tests/ -v`\n"
                f"     → `python -m unittest discover -s tests/ -t . -v`"
            )


class TestIsolationIsActive(unittest.TestCase):
    """隔离是否真的生效——上面入口对了，这里逐项核对实际效果。"""

    def test_bootstrap_applied(self):
        """✅ 隔离逻辑已执行。"""
        # 用 importlib 而非 `import _bootstrap`：两种入口下模块名不同
        # （`-t .` 时是 `tests._bootstrap`，漏 `-t .` 时是顶层 `_bootstrap`），
        # 而裸 import 会被 tests/bug_hunt 的静态分析判为「无法导入的模块」。


        last_error = None
        for name in ("tests._bootstrap", "_bootstrap"):
            try:
                bootstrap = importlib.import_module(name)
                break
            except ImportError as e:
                last_error = e
        else:
            self.fail(f"无法导入 tests/_bootstrap：{last_error}")

        self.assertTrue(bootstrap.is_applied(),
                        "tests/_bootstrap.apply() 未执行")

    def test_redis_is_not_reachable(self):
        """✅ 最关键的一条：测试进程绝不能连生产 Redis。"""
        import app_config
        import redis_cache

        self.assertFalse(
            redis_cache.redis_available(),
            "redis_available() 为真：测试进程会连 Redis。主 app_config.json "
            "的 redis.enable=true 指向生产 Redis（db 6、key_prefix webreport_）。")
        self.assertFalse(
            app_config.get_redis_config().get("enable", False),
            "app_config.get_redis_config() 仍返回 enable=True，生产 Redis 未隔离。")
        self.assertIsNone(redis_cache.get_redis_manager(),
                          "redis_cache 已持有全局管理器实例")

    def test_debug_config_redirected(self):
        """✅ 本机 app_config.debug.json 不得影响测试。

        断言的是 **bootstrap 当时写入的值**（`_bootstrap.DETAILS`），不是实时
        `os.environ`：别的用例（如 test_debug_config_override）会用 patch.dict
        临时改这个环境变量，那是那些用例自己的事，不构成「隔离失效」。
        直接读实时 env 会让本用例在全量跑里误报——这正是「金丝雀必须零误报」
        的代价：第一版就是这么栽的。
        """


        bootstrap = importlib.import_module("tests._bootstrap")
        self.assertTrue(
            bootstrap.DETAILS["debug_config_file"].endswith(
                "sr-no-debug-not-exists.json"),
            f"bootstrap 未把 DEBUG_CONFIG_FILE 指向隔离路径，"
            f"当前={bootstrap.DETAILS['debug_config_file']!r}")

    def test_vendor_root_is_temp(self):
        """✅ 不得写真实 static/vendor/self@*/。"""
        import render

        root = str(render.self_assets_root())
        self.assertIn("sqlreport-test-vendor-", root,
                      f"vendor 落点未重定向到临时目录，当前={root}")

    def test_branding_db_is_temp(self):
        """✅ 不得读仓库根 config.db 的 site_settings。"""
        import branding

        path = str(branding._SITE_DB_PATH)
        self.assertIn("sqlreport-test-vendor-", path,
                      f"站点标识库未重定向，当前={path}")


if __name__ == "__main__":
    unittest.main()
