"""测试包

导出测试基类和工厂函数，方便各测试文件统一 import。
"""

import os

# 测试环境隔离本地调试覆盖：app_config.debug.json 属 .gitignore 的本地调试文件，
# 不应影响测试结果（如报表页 <title> 的「【开发】」前缀、端口/数据源等）。
# 仅在未显式设置 DEBUG_CONFIG_FILE 时，指向不存在路径使 _load_debug_config 返回
# None，跳过覆盖。专门的 test_debug_config_override.py 仍可用 patch.dict 显式启用。
os.environ.setdefault("DEBUG_CONFIG_FILE", "/tmp/sr-no-debug-not-exists.json")

import atexit
import shutil
import tempfile

# 找茬 M2a（批次5/6 审查）：公共资产外链化后，任何触发页头/页尾渲染的
# 测试都会经 _get_common_asset_urls() 惰性写 static/vendor/self@{hash}/，
# 污染真实仓库目录。进程级把落点重定向到临时目录（生产代码不走测试
# 进程，无影响）；需要测真实路径的场景显式传 root 或自行 patch 回来。
import render as _render
import branding  # render 已引入；用于重定向测试环境的站点标识库

_TEST_VENDOR_ROOT = tempfile.mkdtemp(prefix="sqlreport-test-vendor-")
_render.self_assets_root = lambda: _TEST_VENDOR_ROOT
atexit.register(shutil.rmtree, _TEST_VENDOR_ROOT, ignore_errors=True)

# 测试环境隔离站点标识库：branding 默认读根目录 config.db 的 site_settings
# （如本机遗留 title_prefix「【开发】」），会污染报表页 <title> 等断言。
# 重定向到临时空库，使所有测试与 CI（无遗留数据）行为一致；test_site_branding
# 等用例用 patch 覆盖本默认值，互不影响。
_TEST_BRANDING_DB = os.path.join(_TEST_VENDOR_ROOT, "site_branding.db")
branding._SITE_DB_PATH = _TEST_BRANDING_DB
branding.invalidate_site_branding_cache()

from .test_base import (make_config_db, init_test_db, BaseConfigTest, BaseReportTest)

__all__ = [
    "make_config_db",
    "init_test_db",
    "BaseConfigTest",
    "BaseReportTest",
]
