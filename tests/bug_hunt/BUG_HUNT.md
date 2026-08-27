# BUG_HUNT.md — 自动化 BUG 发现机制

## 概述

本项目定义了一套**非人工交互**的自动化 BUG 发现机制，适用于 Python 3 代码库。
整个流程由脚本驱动，无需人工检查代码，通过多层次扫描和验证自动发现 BUG，
每轮修正后回归测试确保不引入新问题。

**所有 bug_hunt 工具统一存放在 `tests/bug_hunt/` 目录下。**

---

## 第〇层：代码规范检查（静态分析）— 全自动

### 工具
- **Syntax Checker** — `py_compile` 确保每个 .py 文件无语法错误
- **Import Checker** — 检查所有 from/import 语句的模块是否存在
- **Undefined Name Checker** — AST 扫描：检测使用未定义变量/函数/类
- **Unused Import Checker** — 扫描被导入但从未使用的符号
- **Docstring Checker** — 检查模块/类/函数是否缺少 docstring

### 触发机制
- **随 `unittest discover` 自动运行** — `tests/bug_hunt/test_static_analysis.py`
- **ERROR 级别发现 → 测试失败**（阻断流程）
- **WARNING/INFO 级别发现 → 打印到 stderr**（不阻塞流程）
- 每次 `python -m unittest discover -s tests/` 都会执行

### 静态分析模块
- `tests/bug_hunt/static_analyzer.py` — 包含全部 5 个检查器类和 `run_all_checkers()` 入口
- 可通过 `from tests.bug_hunt.static_analyzer import run_all_checkers` 单独调用

---

## 第一层：单元测试验证（回归检查）

### 工具
- `python -m unittest discover -s tests/ -v` — 全部测试通过
- **FLAKY 检测** — 每个测试连续运行 3 次，确认非 Flaky

### 标准
- 所有测试必须通过，不得跳过
- 测试输出必须包含每项测试的名称和结果
- 测试耗时超过 30 秒无输出视为挂死，中断并报告

---

## 第二层：变异测试（Mutation Testing）— 手动运行

### 工具
- **`python tests/bug_hunt/bug_hunt_mutation.py`**
- 对生产代码做 8 种变异操作（布尔翻转、运算符替换、条件取反、try/except 移除等）
- 每次变异后运行所有测试，检查测试是否能捕获变异
- 未被捕获的变异 = 测试盲区 = 潜在 BUG

### 为什么不自动运行
变异测试会**修改生产代码文件**（备份后修改 → 运行测试 → 恢复），
对文件系统有写操作且耗时长，不适合作为日常自动测试的一部分。

### 变异操作
1. `True → False` / `False → True`（布尔翻转）
2. `and → or` / `or → and`（逻辑运算符替换）
3. `+ → -` / `* → /`（算术运算符替换）
4. `== → !=` / `!= → ==` / `>`→`>=` / `<`→`<=`（比较运算符替换）
5. `if cond:` → `if not cond:`（条件取反）
6. `try/except` → 移除 `except` 块（异常吞没检测）
7. `return x` → `return None`（返回值归零）
8. 删除 `@staticmethod` / `@classmethod` 装饰器

---

## 第三层：边界条件扫描（Dynamic Analysis）— 全自动

### 触发机制
- **随 `unittest discover` 自动运行** — `tests/bug_hunt/test_boundary.py`
- 直接 import 各生产模块，无需 subprocess / 临时文件

### 覆盖模块
1. **Render 边界** — `format_cell(None/Decimal/bytes)`、`render_page_header`($/None)
2. **Auth 边界** — `verify_password(None/无$)`、`parse_cookie(None/畸形)`、`get_session_user(None)`
3. **Server 路由边界** — 未知路径、空路径、子路径、畸形 Cookie
4. **SQL 边界** — `_split_sql_statements(None/空/引号不闭合)`、空查询执行
5. **Export 边界** — `_encode_content(空)`、`_no_quote_value(None/bytes)`、空文件名

### 注
分页边界、配置 CRUD 边界、排序筛选边界、Cookie 边界已在
`tests/test_deep_edge_cases.py` 中覆盖，此处不再重复。

---

## 第四层：状态机测试（State Machine）

检查每个状态流转函数：
- **Session** — 创建 → 验证 → 移除 → 再验证 → 过期
- **配置 CRUD** — 创建 → 读取 → 更新 → 再读取 → 删除 → 再读取
- **缓存** — 写入 → 命中 → 过期 → 未命中
- **登录** — 未登录 → 登录成功 → 访问受保护页面 → 登出 → 访问受保护页面

实现位置：`tests/test_state_machine.py`

---

## 第五层：集成测试（Integration）

- 对 server.py 的所有 HTTP 路由发送正确/错误请求
- 验证 HTTP 状态码、响应头、Cookie 行为
- 验证 multipart/form-data 和 application/x-www-form-urlencoded 两种请求体
- 验证 GET/POST 方法路由区分

实现位置：`tests/test_server.py`

---

## 执行流程

```
Round N:
  1. python -m unittest discover -s tests/ -v  # 自动包含:
     - 单元测试（test_*.py）
     - 静态分析  → 自动触发（ERROR→fail）
     - 边界条件  → 自动触发
     - 状态机测试 → test_state_machine.py
     - 集成测试  → test_server.py
  2. python tests/bug_hunt/bug_hunt_mutation.py  # 手动运行（破坏性）
  3. 发现 BUG → 修正 → 回归验证
  4. 如果仍有 BUG → 进入 Round N+1
  5. 无 BUG → 宣告完成
```

## 修正流程

```
发现 BUG → 记录到 bug_hunt_log.txt → git stash（可选）→ 修正 →
运行全部测试验证 → 重新扫描确认 BUG 已修复 → 更新 bug_hunt_log.txt
```

### 修正原则
1. 最小修改：只改 BUG 所在文件，不碰无关代码
2. 根因定位：先理解 BUG 原因再改，不猜测式修补
3. 测试追加：对每个 BUG 检查是否有对应测试，无则追加
4. 回归验证：所有测试通过后方可进入下一轮
5. 一轮一 BUG：每轮只处理一个 BUG，避免混淆影响
