# 根因报告：删报表 1093（批量删失败）/ 单删 500

> 时间：2026-10-10 · 范围：`config_db.delete_schedules_by_report`（单删与批量删的共同路径）
> 现象（线上）：批量删 flash「批量删除报表失败: 1093 (HY000): You can't specify target table
> 'report_schedules' for update in FROM clause」；单删页面 500。
> 结论：**一条自引用子查询 DELETE 在 MySQL 解析期必被拒**——与数据、权限、报表新旧无关。

## 一、根因（单一）

`config_db.py` 的 `delete_schedules_by_report()`（孤儿任务清理）发的是自引用子查询：

```sql
DELETE FROM report_schedules WHERE id IN (
  SELECT s.id FROM report_schedules s
  LEFT JOIN schedule_reports sr ON sr.schedule_id=s.id
  WHERE sr.schedule_id IS NULL)
```

MySQL 8.0 禁止 `DELETE`/`UPDATE` 的目标表出现在子查询 `FROM` 中（错误 1093），**在解析阶段就拒绝，
与表里有多少行、删哪张报表、账号权限都无关**；SQLite 允许自引用 → SQLite 单测全绿。

两条删除路径都会命中它：

| 入口 | 调用链 | 表现 |
|---|---|---|
| 单删 `config_pages/reports.py:619` | `delete_report` → `config_db.py:1466` → `delete_schedules_by_report` | **无 try/except → 未捕获异常 → 500** |
| 批量删 `config.py:592` | `batch_delete_reports` → `config_db.py:2201` → 同上 | 有 try/except → flash 展示 1093 |

## 二、证据

1. **语句级**：MySQL 8.0.46 直连线上 config 库（`127.0.0.1:3307/sqlreport_config`）对该语句 `EXPLAIN`
   → `ERROR 1093 (HY000)`。EXPLAIN 不访问数据，证明是**语句本身**被拒。
2. **线上日志** `run.log`：`14:53:22 POST /config/reports/batch-delete` → flash 1093；
   `14:53:44 POST /config/reports/43/delete` → `500`，traceback 落 `config_db.py:2560`
   （`conn.execute` 处），即 `delete_schedules_by_report`。
3. **「新建报表不受影响」不成立**：日志显示 `14:53:07` 刚创建 `report 111 (id=43)`，
   紧接着对这张**刚建的**报表批量删 + 单删**双双失败**；全日志无一条「已删除」成功记录。
4. **与孤儿数据无关**：线上 `report_schedules` 仅 1 行（id=2，绑定 report 37）、`schedule_reports`
   仅 1 行；新建报表（零绑定）同样报错。
5. **同类自查**：全仓生产 `.py` 静态扫描 → 无其他自引用 `DELETE`/`UPDATE`。

## 三、修复（单一改动）

`config_db.py:delete_schedules_by_report()` 用**派生表包装**隔离目标表（SQLite/MySQL 等价）：

```sql
DELETE FROM report_schedules WHERE id IN (
  SELECT id FROM (
    SELECT s.id AS id FROM report_schedules s
    LEFT JOIN schedule_reports sr ON sr.schedule_id=s.id
    WHERE sr.schedule_id IS NULL) AS _orphan_schedules)
```

未改动调用方、事务边界与异常处理——根因不在这三处；同时未夹带"顺手"重构。

## 四、验证（证据）

| 项 | 证据 | 结果 |
|---|---|---|
| RED→GREEN | `tests.test_mysql_mock.TestScheduleMySQLDialect.test_delete_report_orphan_cleanup_not_self_referencing` | FAIL → ok |
| 真实 MySQL E2E | 一次性脚本（产物落 `run-logs/`，收尾清理）：无绑定单删 / 带任务单删（孤儿任务清理）/ 批量删 | 4/4 PASS |
| HTTP 层症状 | 调用 `config.handle_batch_delete` / `handle_report_delete` | 批量「已删除 2 个报表」；单删 302 |
| 回归基线同步 | `tests/test_mysql_mock.py::TestMySQLReportCRUD.test_delete_report` 原先把**错误 SQL 原文**钉住 | 已同步为新 SQL |
| 全量回归 | `venv/bin/python -m unittest discover -s tests/ -t . -v` | Ran 3186 / OK |

E2E 场景明细（engine=mysql，一次性脚本，复现步骤见 §五）：

1. 新建报表（无绑定）单删 → `True`，`report_configs` 行已删；
2. 新建报表绑定唯一任务 → 单删后**残留绑定 0、残留孤儿任务 0**（1093 修复的核心路径）；
3. 批量删 2 张（其一有任务）→ 返回 2，残留报表 0、孤儿任务 0；
4. `reports=43` 事务内试删 → 语句执行成功（无 1093）→ **回滚，reports=43 原样保留**。

## 五、复现方法

```bash
mysql -h127.0.0.1 -P3307 -usqlreport_config -p sqlreport_config -e \
  "EXPLAIN DELETE FROM report_schedules WHERE id IN (SELECT s.id FROM report_schedules s \
   LEFT JOIN schedule_reports sr ON sr.schedule_id=s.id WHERE sr.schedule_id IS NULL)"
# → ERROR 1093 (HY000)
```

```python
# 端到端级联（只动自建临时报表；脚本产物落 run-logs/，收尾按硬性 #14 清理）
import db
conn = db.get_config_db()
rid = db.add_report(conn, "临时验证报表", "SELECT 1 AS x", 20, None)
print(db.delete_report(conn, rid))        # 修复前：抛 1093；修复后：True（行已删）
# 批量删同理：db.batch_delete_reports(conn, [rid_a, rid_b])
# HTTP 文案同理：config.handle_batch_delete(conn, "report_ids=..&report_ids=..")
```


## 六、教训

- **「SQLite 绿」不等于「双引擎安全」**：`tests/test_mysql_mock.py` 用 MagicMock 断言 SQL 文本，
  原 `test_delete_report` 把这条**错误 SQL 原文**钉进回归基线——**测试编码了缺陷本身**。
  修 SQL 必须同任务改该断言（已改），并把「不得自引用」写成独立守卫用例。
- 用户给的前提（「新建报表未报错」）与日志/语句级证据冲突时，**以证据为准并回报差异**，
  不按错误前提缩小排查范围。
- MySQL 的 1093 是**解析期**错误：`EXPLAIN` 即可无副作用复现，不必真的删数据。
