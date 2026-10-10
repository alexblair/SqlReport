"""config.py 按实体拆分出的子包（B9-2）。

设计要点（纯搬移，逻辑零改动）：

* 各子模块是 `config.py` 中对应实体簇函数的**唯一新家**，函数体逐字搬移。
* 跨实体共享的助手与模块级常量**仍留在 `config.py`**；子模块通过
  `import config` 在**调用期**按属性访问（`config.<helper>`），因此
  `config.py` 末尾的再导出块必须保留。
* `config.py` 末尾以 `from config_pages.<x> import (...)` 再导出全部搬出的符号，
  使 `config.<name>`（`server.py` 路由分发与 `tests/` 517 处引用）完全兼容。

下面这行 `import config` 是**导入顺序保险**：`config.py` 末尾会反向导入本包，
若调用方先 `import config_pages.<x>`（而不是先 `import config`），子模块顶部的
`import config` 会触发 `config.py` 执行，而它反过来 `from config_pages.<x> import ...`
时该子模块尚在初始化中 → ImportError。先在包初始化时把 `config` 拉起来即可让
任意导入顺序都成立。
"""

import config  # noqa: F401  # 导入顺序保险，见模块 docstring
