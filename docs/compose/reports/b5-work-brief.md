# B5 工作包（P1 性能：筛选合并 / 配置页 N+1 / 派生态）

> 本文件是 **B5 批次子代理的唯一依据**。**不要**重新盘点、**不要**读全量 plan/spec。
> 上游依据：`docs/compose/plan/2026-10-10-perf-robustness-refactor-plan.md` # B5
> 开工基线：`Ran 3083 tests, OK (skipped=4)`（B4 后）
> 放在 `docs/compose/reports/`（`run-logs/` 会被 `cleanup_tmp.py` 删除）。

---

## 0. 硬约束

1. 仓库根 `/opdev/SqlReport`，必须 `venv/bin/python`（硬性 #6）。
2. **测试命令必须用 `discover` 形式**（`-t .` 只能跟 `discover`）：
   ```bash
   venv/bin/python -m unittest discover -s tests -p '<glob>' -t . 2>&1 | tail -3
   ```
3. 只改本任务 `Files` 列出的文件。
4. **行为必须完全不变**（本批是纯性能优化，个别项除外——会在任务里注明）。
5. 用户可感知文字一律简体中文（硬性 #2）。
6. **不要** `git add`/`commit`；**不要** `codegraph sync`；**不要**动 `aoci*`。
7. 中断恢复：只做一件事；被中断不要重做。追加测试用 `edit`/`>>`，不要重写整个文件。

---

## 1. Task B5-1：筛选内循环合并为单条 alternation ⭐ 本批最重要

**Files**
- Modify: `result_transform.py`（`_compile_segments` :158-161 与 `_apply_single_filter` :348-375）
- Test: 新建 `tests/test_b5_perf.py`

### 问题
`_apply_single_filter`（`:358-375`）四个分支都写成：
```python
[r for r in result if any(rx.search(_cell_str(r[col_idx])) for rx in regexes)]
```
即**每个单元格**都新建一个 generator 并**逐个**正则调用。多值筛选（`a,b,c`）时退化为 M 次正则。

### 实测基线（Lead 已复现，100k 行）
| 场景 | 旧 | 新（alternation） | 加速 |
|---|---|---|---|
| `contains` 单值 | 86.2ms | 33.9ms | **2.54×** |
| `contains` 三值 | 149.4ms | 41.6ms | **3.59×** |
| `eq` 单值（fullmatch） | 75.7ms | 29.7ms | **2.55×** |

结果集**逐元素一致**（已实测）。

**为什么等价**：`_segment_regex`（`:147-155`）只产出 `re.escape(字面量)` 与 `.*`，**结构上不可能含裸 `|`**（我实测过 `a|b`→`a\|b`、`a.b`→`a\.b` 等 10 个样本均无裸 `|`）。故 `(?:s1)|(?:s2)` 与「逐个 any」严格等价。

> ⚠️ **禁止**改成 `str.lower() in`：虽然实测 25.3→8.4ms 更快，但 Unicode 大小写折叠语义与 `re.IGNORECASE` 有边界差异，会改变可观察行为。

### Step 1 — 写测试（等价性护栏优先，**改之前就必须绿**）

```python
# tests/test_b5_perf.py
import unittest

from result_transform import filter_rows

COLS = ["a", "b"]
ROWS = [("alpha", "x"), ("beta", "y"), ("ALPHA", "z"), (None, "w"), ("", "v"),
        ("a|b", "p"), ("a.b", "q"), ("x", "r")]


class TestFilterEquivalence(unittest.TestCase):
    """B5-1：合并为 alternation 后语义必须与旧实现完全一致。"""

    def test_multi_value_contains_is_case_insensitive(self):
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "alpha,beta")])
        self.assertEqual([x[0] for x in r], ["alpha", "beta", "ALPHA"])

    def test_contains_hits_regex_metachars_literally(self):
        """`|` `.` 等必须是字面量，不得被当正则元字符。"""
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "a|b")])
        self.assertEqual([x[0] for x in r], ["a|b"])
        r2 = filter_rows(list(ROWS), COLS, [("a", "contains", "a.b")])
        self.assertEqual([x[0] for x in r2], ["a.b"])

    def test_notcontains_inverts(self):
        r = filter_rows(list(ROWS), COLS, [("a", "notcontains", "alpha")])
        got = [x[0] for x in r]
        self.assertNotIn("alpha", got)
        self.assertNotIn("ALPHA", got)

    def test_eq_is_case_sensitive(self):
        r = filter_rows(list(ROWS), COLS, [("a", "eq", "alpha")])
        self.assertEqual([x[0] for x in r], ["alpha"])

    def test_neq_inverts(self):
        r = filter_rows(list(ROWS), COLS, [("a", "neq", "alpha")])
        self.assertNotIn("alpha", [x[0] for x in r])
        self.assertIn("ALPHA", [x[0] for x in r])   # neq 大小写敏感

    def test_wildcard_still_works(self):
        r = filter_rows(list(ROWS), COLS, [("a", "contains", "al*ha")])
        self.assertEqual(sorted(x[0] for x in r), ["ALPHA", "alpha"])

    def test_empty_segments_ignored(self):
        """全空值（如 " , "）→ 条件忽略，返回原列表。"""
        r = filter_rows(list(ROWS), COLS, [("a", "contains", " , ")])
        self.assertEqual(len(r), len(ROWS))

    def test_unknown_column_ignored(self):
        r = filter_rows(list(ROWS), COLS, [("nope", "contains", "x")])
        self.assertEqual(len(r), len(ROWS))

    def test_none_matches_empty_string_semantics(self):
        """None → ""（既有语义），故 contains "" 会命中 None 行。"""
        r = filter_rows(list(ROWS), COLS, [("a", "isempty", "")])
        self.assertIn(None, [x[0] for x in r])
```

### Step 2 — 跑确认基线通过（改之前就必须绿）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b5_perf.py' -t . 2>&1 | tail -3
```
Expected: **PASS** —— 这是**等价性护栏**，先证明它抓住既有语义。

### Step 3 — 实现合并

**① 在 `_compile_segments` 旁新增**（放在 `:161` 之后，**不要改 `_compile_segments` 本身**，它还有其他调用方语义）：
```python
def _compile_alternation(segments: list[list[tuple]], ignorecase: bool):
    """把多值段合并为**单条** alternation 正则，返回其 search/fullmatch 方法。

    为什么合并：每单元格逐个 `any(rx.search(...))` 会为每个值付一次正则调用 +
    generator 开销；合并后只付一次。实测 100k 行 × 12 列：单值 2.54×、三值 3.59×。

    ⚠️ 等价性前提：`_segment_regex` 只产出 `re.escape(字面量)` 与 `.*`，结构上
    不含裸 `|`，故 `(?:s1)|(?:s2)` 与「逐个 any」结果严格一致（不要改用
    `lower() in`——Unicode 折叠语义有差异）。
    """
    flags = re.IGNORECASE if ignorecase else 0
    pattern = "|".join("(?:%s)" % _segment_regex(seg) for seg in segments)
    rx = re.compile(pattern, flags)
    return rx.search, rx.fullmatch
```

**② 改 `_apply_single_filter` 的四个分支**：
```python
    if op in ("contains", "notcontains", "eq", "neq"):
        segments = parse_filter_expr(q)
        if not segments:
            return result
        search, fullmatch = _compile_alternation(
            segments, ignorecase=(op in ("contains", "notcontains")))
        if op == "contains":
            return [r for r in result if search(_cell_str(r[col_idx]))]
        if op == "notcontains":
            return [r for r in result if not search(_cell_str(r[col_idx]))]
        if op == "eq":
            return [r for r in result if fullmatch(_cell_str(r[col_idx]))]
        # neq
        return [r for r in result if not fullmatch(_cell_str(r[col_idx]))]
```
> 其余分支（`gt/lt/gte/lte/isempty/notempty/...`）**一行都不要动**。

### Step 4 — 跑确认仍绿（语义未变）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b5_perf.py' -t . 2>&1 | tail -3
```

### Step 5 — 回归（变换语义被多方复用，必须全跑）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_result_transform*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_report*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_export*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_api*.py' -t . 2>&1 | tail -3
```

### Step 6 — 实测加速（必做，证明预期收益达成）
```bash
venv/bin/python - <<'EOF'
import sys, time; sys.path.insert(0,'.')
from result_transform import filter_rows
ROWS=[(f"name{i}", i%7) for i in range(100_000)]
for q in ["name1", "name1,name2,name3"]:
    t=time.perf_counter(); r=filter_rows(list(ROWS), ["a","b"], [("a","contains",q)])
    print(f"  q={q!r:22} {(time.perf_counter()-t)*1000:7.1f}ms  命中 {len(r)}  预期 <45ms")
EOF
```

### Step 7 — 报告（六行内）
1. 改动文件与行号
2. 新测试结果（精确 `Ran N tests, OK`）
3. 四个回归模块结果
4. `contains` 单值/三值 实测 ms
5. 是否改了 `_compile_segments`（**必须：没改**）
6. 是否用了 `lower() in`（**必须：没有**）

---

## 2. Task B5-2：配置页去掉重复全表查询

**Files**
- Modify: `config.py`（`_nav_badges` :940-954）
- Modify: `config_db.py`（新增 `count_schedules`）
- Test: 追加到 `tests/test_b5_perf.py`

### 问题
`_nav_badges` 的 `("scheduler", lambda: len(db.get_all_schedules(conn)))` 调用的
`get_all_schedules`（`config_db.py:2394-2411`）是 **1 条 SELECT + 每任务一条**
`get_schedule_reports`（含 LEFT JOIN）——即 **N+1**，而这里**只需要数量**。

其余 4 个徽标（reports/pools/users/api）是单查询，但 `get_all_reports` 会
`SELECT *` 取出全部大字段（含 `sql_query`/`memo`）只为 `len()`。

### Step 1 — 写测试（Lead 已核实可用的夹具写法）

**测试夹具配方（Lead 已实跑验证可用）** —— 注意：`make_config_db()` **不建表**，
而 `config_db.init_db()` 在**裸 sqlite3 连接**上会报 `near "=": syntax error`
（它面向包装连接）。正确做法是 `init_test_db` + 内联 DDL：

```python
import re
from tests import init_test_db          # 建 6 张基础表（含 report_configs）
from tests.test_base import make_config_db

# report_schedules / schedule_reports 的 DDL 在 tests/test_scheduler_db.py:18
# 项目惯例是「内联建表 DDL，有意重复，避免循环导入」——直接复用那段字符串：
_SCHED_DDL = re.search(
    r'SQL_CREATE_REPORT_SCHEDULES = """(.*?)"""',
    open("tests/test_scheduler_db.py", encoding="utf-8").read(), re.S).group(1)
```

```python
    def setUp(self):
        self.conn = make_config_db()
        init_test_db(self.conn)                 # 基础 6 表
        self.conn.executescript(_SCHED_DDL)     # 补 report_schedules / schedule_reports
        self.conn.execute(
            "INSERT INTO report_configs (name, sql_query) VALUES ('r1','SELECT 1')")
        self.conn.commit()
        self._rid = self.conn.execute(
            "SELECT id FROM report_configs LIMIT 1").fetchone()["id"]

    def tearDown(self):
        self.conn.close()

    def _add_schedule(self, name):
        # ⚠️ upsert_schedule 要求至少绑定一张报表（config_db.py:2285），
        # 空 report_ids 会抛 ValueError —— 不要传 report_ids=[]
        import config_db
        return config_db.upsert_schedule(
            self.conn, name=name, report_ids=[self._rid],
            schedule_type="interval", interval_minutes=60)
```
> **实跑验证结果**：建两条任务后 `COUNT(*)=2`、`len(get_all_schedules)=2`，一致。

```python
    def test_count_schedules_exists(self):
        import config_db
        self.assertTrue(hasattr(config_db, "count_schedules"))

    def test_count_matches_len_of_get_all(self):
        import config_db
        self.assertEqual(config_db.count_schedules(self.conn), 0)
        self._add_schedule("任务甲")
        self._add_schedule("任务乙")
        self.assertEqual(config_db.count_schedules(self.conn), 2)
        # 与全量取数一致（防止数错）
        self.assertEqual(config_db.count_schedules(self.conn),
                         len(config_db.get_all_schedules(self.conn)))

    def test_count_does_not_need_report_binding(self):
        """徽标只要数量：不得因任务无绑定报表而少计。"""
        import config_db
        self._add_schedule("无绑定任务")
        self.assertEqual(config_db.count_schedules(self.conn), 1)
```
> 夹具细节已核实：`make_config_db()`（`tests/test_base.py:124`）**不建表**，须配 `init_test_db`；
> `upsert_schedule`（`config_db.py:2258`）**必须至少绑定一张报表**（`:2285` 会抛 `ValueError`）；
> `name` 重名也会抛 `ValueError`（故两个用例用不同名）。

### Step 2 — 实现
```python
def count_schedules(conn) -> int:
    """定时任务总数（供侧栏徽标，避免取全量 + 每任务一条 JOIN 查询）。"""
    row = conn.execute("SELECT COUNT(*) FROM report_schedules").fetchone()
    if row is None:
        return 0
    # _MySQLRow / sqlite3.Row / tuple 三种形态都要能取到第 1 列
    try:
        return int(row[0])
    except (TypeError, IndexError, KeyError):
        return int(row["cnt"])
```
> ⚠️ **取列时要兼容三种 row 形态**：SQLite `sqlite3.Row`（支持 `row[0]`）、
> `_MySQLRow`、以及测试里的假连接。**不要**假定 `row["cnt"]` 一定可用
> （纯 `COUNT(*)` 无别名时列名因引擎而异）。**建议直接写
> `SELECT COUNT(*) AS cnt` 然后用 `row["cnt"]`，并保留 `row[0]` 回退。**

`config.py:948` 改为：
```python
        ("scheduler", lambda: db.count_schedules(conn)),
```

### Step 3 — 跑测试 + 回归
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b5_perf.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_scheduler*.py' -t . 2>&1 | tail -3
```
> ⚠️ **不得改 `get_all_schedules` 本身**：它有 5 个调用方
> （`config.py:607/668/2025`、`report.py:1376`、`tests/test_scheduler_db.py`）都**需要**
> `report_ids`/`report_names`，不是只要数量。

### Step 4 — 报告（四行内）
1. 改动文件与行号
2. 新测试 + 三个回归结果（各精确 `Ran N tests, OK`）
3. 是否改了 `get_all_schedules`（**必须：没改**）
4. `count_schedules` 的 row 取值兼容策略

---

## 3. Task B5-3：`get_reports_by_category` 的 N+1

**Files**
- Modify: `config_db.py`（`get_reports_by_category` :1603-1614）
- Test: 追加到 `tests/test_b5_perf.py`

### 问题
```python
for cat in categories:
    cat["reports"] = get_reports(conn, category_id=cat["id"])   # ← 每分类一次全表扫
```
2+C 次查询，每次扫 `report_configs` 全表；且 `category_id` **无索引**。

### 修法（一次全表查询 + Python 分组）
```python
def get_reports_by_category(conn):
    """返回所有分类及其下的报表列表（仅直接归属）+ 未分类报表。

    B5-3：改为一次全表查询后在 Python 分组（原为每分类一次查询，2+C 次）。
    ⚠️ 排序必须保持 `sort_order, id`（get_reports 的既有 ORDER BY），
    分组后各组内的相对顺序必须与逐分类查询时逐个一致。
    """
    categories = get_all_categories(conn)
    # ⚠️ 必须用 get_all_reports（真全量，ORDER BY sort_order, id）。
    # 不得用 get_reports(conn)——它的 category_id 默认值是 None，
    # 走的是 `WHERE category_id IS NULL`，只返回**未分类**报表！（Lead 已实测）
    all_reports = get_all_reports(conn)
    by_cat: dict = {}
    unassigned: list = []
    for r in all_reports:
        cid = r.get("category_id")
        if cid is None:
            unassigned.append(r)
        else:
            by_cat.setdefault(cid, []).append(r)
    result = []
    for cat in categories:
        cat["reports"] = by_cat.get(cat["id"], [])
        result.append(cat)
    return result, unassigned
```
> **必须核实两点**：① `category_id` 为 `None` 的判定（是否可能是 `""` 或 `0`）；
> ② 未分类报表的过滤条件与 `get_reports(conn, category_id=None)` 完全一致。

### 回归（分类树是重点）
```bash
venv/bin/python -m unittest discover -s tests -p 'test_b5_perf.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_config*.py' -t . 2>&1 | tail -3
venv/bin/python -m unittest discover -s tests -p 'test_db*.py' -t . 2>&1 | tail -3
```

### 报告（四行内）
1. 改动文件与行号
2. 新测试 + 三个回归结果
3. `category_id` 的 None 判定依据（怎么核实的）
4. 各组内顺序是否与改动前逐个一致（怎么验证的）

---

## 4. Task B5-4（可选）：派生态缓存拆两级

> **仅在 B5-1～B5-3 全部验收通过后，且 Lead 明确指示时**才做（本项风险较高，可能被跳过）。

**Files**: `report.py`（`execute_report` :1253-1280、`CachedResult` :90-120）
**测试**: 追加到 `tests/test_b5_perf.py`

**要点**：`derived` 现在把 `(filters, sorts, nested_filter)` 合成**一个键**，
换排序键就要重做整表筛选；且淘汰是 FIFO（`pop(next(iter(...))`）而注释写 LRU。
拆成「filtered（按 filter 键）」+「sorted（按 sort 键）」两级。

**硬约束**：派生态必须**仍只挂 L1**、不进任何序列化路径、与 L1 同生共死。

---

## 5. B5 整批收尾（**Lead 执行，子代理不跑**）

```bash
venv/bin/python -m unittest discover -s tests/ -t . 2>&1 | grep -E '^(Ran|OK|FAILED)'
```
期望 `Ran ≥3092` / `OK (skipped=4)`。
