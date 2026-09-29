"""测试包

两件事：
1. 应用测试进程隔离（见 `_bootstrap`，那里的注释解释了每一项为什么必须隔离）
2. 导出测试基类和工厂函数，方便各测试文件统一 import
"""

from . import _bootstrap as _bootstrap

# 隔离必须在本包被导入的第一时间生效——各测试模块 `from tests import ...`
# 时就会执行到这里。
_bootstrap.apply()

from .test_base import (make_config_db, init_test_db, BaseConfigTest, BaseReportTest)

__all__ = [
    "make_config_db",
    "init_test_db",
    "BaseConfigTest",
    "BaseReportTest",
]
