"""测试包

导出测试基类和工厂函数，方便各测试文件统一 import。
"""

from .test_base import (make_config_db, init_test_db, BaseConfigTest, BaseReportTest)

__all__ = [
    "make_config_db",
    "init_test_db",
    "BaseConfigTest",
    "BaseReportTest",
]
