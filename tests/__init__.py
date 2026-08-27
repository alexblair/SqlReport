"""测试包

导出测试基类和工厂函数，方便各测试文件统一 import。
"""

import atexit
import shutil
import tempfile

# 找茬 M2a（批次5/6 审查）：公共资产外链化后，任何触发页头/页尾渲染的
# 测试都会经 _get_common_asset_urls() 惰性写 static/vendor/self@{hash}/，
# 污染真实仓库目录。进程级把落点重定向到临时目录（生产代码不走测试
# 进程，无影响）；需要测真实路径的场景显式传 root 或自行 patch 回来。
import render as _render

_TEST_VENDOR_ROOT = tempfile.mkdtemp(prefix="sqlreport-test-vendor-")
_render.self_assets_root = lambda: _TEST_VENDOR_ROOT
atexit.register(shutil.rmtree, _TEST_VENDOR_ROOT, ignore_errors=True)

from .test_base import (make_config_db, init_test_db, BaseConfigTest, BaseReportTest)

__all__ = [
    "make_config_db",
    "init_test_db",
    "BaseConfigTest",
    "BaseReportTest",
]
