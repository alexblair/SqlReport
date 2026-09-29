"""
tests/_bootstrap.py — 测试进程隔离（单一来源）

为什么单独成文件：
    `tests/__init__.py` 里的隔离**只在包被导入时才执行**。而
    `python -m unittest discover -s tests/` 会把测试模块当顶层模块导入
    （`test_health` 而非 `tests.test_health`），包根本不被加载，整套隔离
    全部失效——2026-09-29 实测 `"tests" in sys.modules == False`。
    把隔离抽成可显式调用的模块，让 `tests/__init__.py` 与金丝雀测试
    （`tests/test_test_isolation.py`）引用同一份逻辑，不再两处维护。

隔离项（全部是「测试进程不得影响/依赖仓库外部状态」）：
    1. DEBUG_CONFIG_FILE → 不存在的路径（本机 app_config.debug.json 不泄漏）
    2. vendor 资产落点 → 临时目录（不写真实 static/vendor/self@*/）
    3. 站点标识库 → 临时空库（本机 config.db 遗留 title_prefix 不泄漏）
    4. **Redis → 强制关闭**（详见下方说明）

关于 Redis（最重要的一条）：
    主 `app_config.json` 的 `redis.enable` 为 **true**（db 6、
    key_prefix `webreport_`），即生产 Redis。测试进程若连上去，会读写
    真实快照，使断言依赖进程外状态——换个执行顺序表现就不同，报告
    「是生产数据的问题」还可能误判为产品 bug。导出改走
    `report.execute_report`（2026-09-29 C-4）后立刻暴露：report_id=1 的
    生产快照让 40+ 个导出用例读到了完全不相关的数据。

    需要 Redis 的用例自行 patch `redis_cache.get_redis_config` 或用
    `reset_redis_manager` 显式注入（显式注入即显式选择连哪个 Redis）。
    实测 `test_redis_cache*` 全部 patch `RedisConnectionManager._create_client`，
    从不连真实服务，故不受影响。
"""

import os
import atexit
import shutil
import tempfile

#: 隔离是否已应用（金丝雀测试读它）
_APPLIED = False

#: 隔离详情，供金丝雀测试与失败信息使用
DETAILS: dict = {}

#: 不存在的 DEBUG 配置路径——指向它使 app_config._load_debug_config 返回 None
NO_DEBUG_CONFIG_PATH = "/tmp/sr-no-debug-not-exists.json"

#: 测试进程内一律使用的 Redis 配置（enable=False）
DISABLED_REDIS_CONFIG = {
    "enable": False, "key_prefix": "sr_test",
    "default_ttl_hours": 0, "socket_timeout": 1,
}


def is_applied() -> bool:
    """本模块的隔离是否已在本进程生效。"""
    return _APPLIED


def apply() -> None:
    """应用全部测试隔离。幂等：重复调用无副作用。"""
    global _APPLIED
    if _APPLIED:
        return

    # ---- 1. 隔离本地调试覆盖 ----
    # app_config.debug.json 属 .gitignore 的本地调试文件，不应影响测试结果
    # （如报表页 <title> 的「【开发】」前缀、端口/数据源等）。仅在未显式设置时
    # 指向不存在路径使覆盖被跳过；test_debug_config_override.py 仍可用
    # patch.dict 显式启用。
    if not os.environ.get("DEBUG_CONFIG_FILE"):
        os.environ["DEBUG_CONFIG_FILE"] = NO_DEBUG_CONFIG_PATH
    DETAILS["debug_config_file"] = os.environ["DEBUG_CONFIG_FILE"]

    import render
    import branding

    # ---- 2. vendor 资产落点重定向 ----
    # 公共资产外链化后，任何触发页头/页尾渲染的测试都会经
    # _get_common_asset_urls() 惰性写 static/vendor/self@{hash}/，污染真实仓库
    # 目录。生产代码不走测试进程，无影响。
    vendor_root = tempfile.mkdtemp(prefix="sqlreport-test-vendor-")
    render.self_assets_root = lambda: vendor_root
    atexit.register(shutil.rmtree, vendor_root, ignore_errors=True)
    DETAILS["vendor_root"] = vendor_root

    # ---- 3. 站点标识库重定向 ----
    # branding 默认读根目录 config.db 的 site_settings（如本机遗留
    # title_prefix「【开发】」），会污染报表页 <title> 等断言。重定向到临时空库，
    # 使所有测试与 CI（无遗留数据）行为一致；test_site_branding 等用例用
    # patch 覆盖本默认值，互不影响。
    branding_db = os.path.join(vendor_root, "site_branding.db")
    branding._SITE_DB_PATH = branding_db
    branding.invalidate_site_branding_cache()
    DETAILS["branding_db"] = branding_db

    # ---- 4. Redis 强制关闭 ----
    # app_config.get_redis_config 与 redis_cache.get_redis_config 都打：
    # 后者在 import 时把函数对象绑到了模块全局，只补一处会漏。
    import app_config
    import redis_cache

    def _disabled_redis_config():
        return dict(DISABLED_REDIS_CONFIG)

    app_config.get_redis_config = _disabled_redis_config
    redis_cache.get_redis_config = _disabled_redis_config
    redis_cache._redis_manager = None
    DETAILS["redis_disabled"] = True

    _APPLIED = True
