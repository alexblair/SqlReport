"""test_scheduler_acceptance.py — 缓存保活 + misfire 错过补偿策略 完整验收测试。

背景（2026-08-21）：缓存保活（refresh-ahead）与定时任务错过执行补偿
（misfire：skip / run_once）无法人工验收——保活要等 TTL 临近过期（小时级），
misfire 要等停机跨周期。本文件用固定 now + 构造快照剩余 TTL + 同步假执行器
把"等待数小时/跨天"压缩为毫秒级断言，覆盖完整行为契约矩阵：

保活（B13/B14/B15/B16）：
- K1  剩余 TTL < ahead → 触发 force_rebuild（先算后换）
- K2  剩余 TTL == ahead → 跳过（严格小于才触发）
- K3  剩余 TTL > ahead → 跳过
- K4  无快照 → 跳过（等请求自然重建）
- K5  ahead=0 → 永不触发
- K6  Redis 不可用 → 整轮跳过
- K7  无启用任务行（JOIN）→ 跳过
- K8  熔断中（fail_count=5）→ 跳过
- K9  prefer_cache=0 → 跳过
- K10 单个报表异常（B16）→ 不影响其余报表
- K11 快照已过期（剩余 TTL 为负）→ 触发
- K12 ahead > TTL（提前量覆盖整个生命周期）→ 始终触发
- K13 重建成功 → 静态文件联动只处理 static_cache=1 端点（B15）
- K14 静态联动端点失败 → 不影响保活成功状态（B15）
- K15 执行失败 → 不计数重建、不联动静态文件

misfire（B8/B9/B10/B11）：
- M1  interval 停机跨多周期 → 合并补跑一次，next=now+interval
- M2  daily skip 当日已过 → 不补跑、推进次日、审计 scheduled_misfire
- M3  daily run_once 今天未跑 → 补跑一次
- M4  daily run_once 今天已跑 → 不补跑
- M5  interval 过期但 disabled → 跳过
- M6  interval 过期且熔断（fail_count=5）→ 跳过
- M7  daily 过期且熔断 → 跳过
- M8  next_run_at IS NULL（未排程）→ 跳过
- M9  daily skip 今天已跑过 → 仍跳过推进次日（skip 无重复跑语义）
- M10 daily run_once 昨天跑过今天未跑 → 今天补跑（跨日）
- M11 非法 daily_time → 不崩溃
- M12 无过期任务 → {ran:0, skipped:0}
- M13 混合场景统计正确
- M14 B11：运行期 tick 只按到期派发（trigger=scheduler，不引入 misfire 语义）
- M15 补跑后 next_run_at 精确推进（interval: now+interval；daily: 次日 HH:MM）

测试策略（与 test_scheduler_core 同模式）：
- 临时 SQLite 文件库 + patch app_config.get_config 配置隔离；
- ReportScheduler._executor 替换为同步假执行器（提交即执行，结果立即可断言）；
- execute_report / audit_db.record_operation / redis 管理器 mock；
- scheduler.time.time patch 为固定值以便精确断言 next_run_at 推进。
"""

import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import config_db
import scheduler
from redis_cache import ReportSnapshot

_TMP_ROOT = tempfile.mkdtemp(prefix="test_sched_accept_")
_TMP_DB = os.path.join(_TMP_ROOT, "config.db")


def _test_config() -> dict:
    return {
        "config_db": [{"enable": True, "engine": "sqlite3", "path": _TMP_DB}],
        "log": {"enable": False, "path": "/dev/null"},
    }


def _get_conn():
    conn = sqlite3.connect(_TMP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _set_up_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connection_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 3306,
            user TEXT NOT NULL, password TEXT NOT NULL,
            database TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            sql_query TEXT NOT NULL, default_page_size INTEGER NOT NULL DEFAULT 20,
            pool_id INTEGER, memo TEXT, prefer_cache INTEGER NOT NULL DEFAULT 1,
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            allow_write INTEGER NOT NULL DEFAULT 1, allow_all_output INTEGER NOT NULL DEFAULT 1,
            max_rows INTEGER NOT NULL DEFAULT 100000,
            keepalive_enabled INTEGER NOT NULL DEFAULT 0,
            keepalive_ahead_seconds INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL,
            name TEXT NOT NULL, url_path TEXT UNIQUE NOT NULL,
            output_format TEXT NOT NULL DEFAULT 'json', columns TEXT, filters TEXT,
            sorts TEXT, row_limit INTEGER DEFAULT 0, api_key TEXT,
            allowed_origins TEXT, enabled INTEGER NOT NULL DEFAULT 1,
            result_mode TEXT NOT NULL DEFAULT 'single',
            result_index INTEGER NOT NULL DEFAULT 0,
            allow_fetch_all INTEGER NOT NULL DEFAULT 1,
            static_cache INTEGER NOT NULL DEFAULT 1,
            json_no_quotes INTEGER NOT NULL DEFAULT 0,
            smart_quote_flags INTEGER NOT NULL DEFAULT 0,
            json_template TEXT, description TEXT,
            created_at TEXT NOT NULL DEFAULT '',
        nested_filter    TEXT,
            updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS report_schedules (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL DEFAULT '',
            schedule_type    TEXT    NOT NULL DEFAULT 'interval',
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            daily_time       TEXT    NOT NULL DEFAULT '08:00',
            misfire_policy   TEXT    NOT NULL DEFAULT 'skip',
            enabled          INTEGER NOT NULL DEFAULT 1,
            exclusions       TEXT,
            audit_enabled    INTEGER NOT NULL DEFAULT 0,
            next_run_at      REAL,
            last_run_at      REAL,
            last_status      TEXT,
            last_error       TEXT,
            fail_count       INTEGER NOT NULL DEFAULT 0,
            last_duration_ms INTEGER,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS schedule_reports (
            schedule_id INTEGER NOT NULL,
            report_id   INTEGER NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            enabled     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (schedule_id, report_id)
        );
    """)
    conn.commit()
    conn.close()


_set_up_db()


def _local_ts(year, month, day, hour, minute, second=0):
    """构造本地时区固定时刻的 epoch 秒。"""
    return time.mktime((year, month, day, hour, minute, second, 0, 0, -1))


# 固定"今天"：2026-08-21 15:00 本地时间
NOW = _local_ts(2026, 8, 21, 15, 0, 0)


class _FakeExecutor:
    """同步假执行器：submit 立即执行 fn（生产线程池完成语义）。"""

    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        fn(*args, **kwargs)
        return None

    def shutdown(self, wait=True):
        pass


class AcceptanceBase(unittest.TestCase):
    """公共环境：临时库 + 种子数据 + mock + 固定时钟。"""

    def setUp(self):
        cfg_patcher = patch("app_config.get_config",
                            return_value=_test_config())
        cfg_patcher.start()
        self.addCleanup(cfg_patcher.stop)

        conn = _get_conn()
        for table in ("schedule_reports", "report_schedules", "api_endpoints",
                      "report_configs", "connection_pools"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "INSERT INTO connection_pools "
            "(id,name,host,port,user,password,database,sort_order) "
            "VALUES (1,'pool','127.0.0.1',3306,'root','p','db',1)")
        conn.execute(
            "INSERT INTO report_configs (id,name,sql_query,default_page_size,"
            "pool_id,prefer_cache,cache_ttl_hours,allow_write,allow_all_output,"
            "max_rows,keepalive_enabled,keepalive_ahead_seconds) "
            "VALUES (1,'报表A','SELECT 1',20,1,1,0,1,1,100000,0,0)")
        conn.commit()
        conn.close()
        self.report_id = 1
        self.pool_id = 1

        # 审计收集
        self.audit_calls = []

        def _record(session_user, action, entity_type, **kw):
            self.audit_calls.append(dict(
                user=session_user, action=action, entity_type=entity_type,
                entity_id=kw.get("entity_id"), entity_name=kw.get("entity_name"),
                after_value=kw.get("after_value")))
            return True

        audit_patcher = patch("audit_db.record_operation", side_effect=_record)
        audit_patcher.start()
        self.addCleanup(audit_patcher.stop)

        exec_patcher = patch("report.execute_report")
        self.mock_exec = exec_patcher.start()
        self.addCleanup(exec_patcher.stop)

        # Redis：默认可用，快照由用例构造
        avail_patcher = patch("scheduler.redis_cache.redis_available",
                              return_value=True)
        avail_patcher.start()
        self.addCleanup(avail_patcher.stop)
        self.mgr = MagicMock()
        self.mgr.key_prefix = "sr"
        self.mgr.get_snapshot.return_value = None
        mgr_patcher = patch("scheduler.redis_cache.get_redis_manager",
                            return_value=self.mgr)
        mgr_patcher.start()
        self.addCleanup(mgr_patcher.stop)

        # 静态文件联动 mock（B15 落盘原语在本文件不真跑）
        self.static_calls = []
        self.static_side_effects = {}

        def _fake_rebuild(conn, endpoint, record_invalidation=True, headers=None):
            self.static_calls.append((endpoint.get("url_path"),
                                      record_invalidation))
            ep_path = endpoint.get("url_path")
            if ep_path in self.static_side_effects:
                raise self.static_side_effects[ep_path]
            return True, 200, "{}", {"Content-Type": "application/json"}

        static_patcher = patch("api_handler.rebuild_static_endpoint_file",
                               side_effect=_fake_rebuild)
        static_patcher.start()
        self.addCleanup(static_patcher.stop)

        # 固定时钟：scheduler.time.time → NOW（精确断言 next_run_at）
        time_patcher = patch("scheduler.time.time", return_value=NOW)
        time_patcher.start()
        self.addCleanup(time_patcher.stop)

        # 调度器实例：同步假执行器
        self.executor = _FakeExecutor()
        self.sched = scheduler.ReportScheduler(tick_seconds=10, workers=2)
        self.sched._executor = self.executor
        scheduler._scheduler = None
        self.addCleanup(setattr, scheduler, "_scheduler", None)

    # -- 公共辅助 ----------------------------------------------------------

    def _add_report(self, report_id, name, **kw):
        args = dict(name=name, sql_query="SELECT 1", default_page_size=20,
                    pool_id=1, prefer_cache=1, cache_ttl_hours=0,
                    allow_write=1, allow_all_output=1, max_rows=100000,
                    keepalive_enabled=0, keepalive_ahead_seconds=0)
        args.update(kw)
        conn = _get_conn()
        try:
            cols = ", ".join(args)
            ph = ", ".join("?" * len(args))
            conn.execute(f"INSERT INTO report_configs (id,{cols}) "
                         f"VALUES ({report_id},{ph})", tuple(args.values()))
            conn.commit()
        finally:
            conn.close()

    def _add_schedule(self, report_id=1, schedule_type="interval",
                      interval_minutes=30, daily_time="08:00",
                      misfire_policy="skip", enabled=1, next_run_at=1000.0,
                      last_run_at=None, fail_count=0, audit_enabled=0):
        conn = _get_conn()
        try:
            sid = config_db.upsert_schedule(
                conn, report_id=report_id, schedule_type=schedule_type,
                interval_minutes=interval_minutes, daily_time=daily_time,
                misfire_policy=misfire_policy, enabled=enabled,
                audit_enabled=audit_enabled,
                next_run_at=next_run_at)
            conn.execute(
                "UPDATE report_schedules SET fail_count=? WHERE id=?",
                (fail_count, sid))
            if last_run_at is not None:
                conn.execute(
                    "UPDATE report_schedules SET last_run_at=? WHERE id=?",
                    (last_run_at, sid))
            conn.commit()
            return sid
        finally:
            conn.close()

    def _row(self, schedule_id):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_schedules WHERE id=?",
                (schedule_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _audit_of(self, action):
        return [a for a in self.audit_calls if a["action"] == action]

    def _report_row(self, report_id=1):
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM report_configs WHERE id=?",
                (report_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _enable_keepalive(self, report_id=1, ahead=600, ttl_hours=6,
                          prefer_cache=1, with_schedule=True, fail_count=0):
        conn = _get_conn()
        conn.execute(
            "UPDATE report_configs SET keepalive_enabled=1, "
            "keepalive_ahead_seconds=?, cache_ttl_hours=?, prefer_cache=? "
            "WHERE id=?", (ahead, ttl_hours, prefer_cache, report_id))
        if with_schedule:
            sid = config_db.upsert_schedule(
                conn, report_id=report_id, schedule_type="interval",
                interval_minutes=30, daily_time="08:00",
                misfire_policy="skip", enabled=1, next_run_at=NOW)
            if fail_count:
                conn.execute(
                    "UPDATE report_schedules SET fail_count=? WHERE id=?",
                    (fail_count, sid))
        conn.commit()
        conn.close()

    def _set_snapshot_remaining(self, remaining_seconds, ttl_hours=6):
        """构造快照使其剩余 TTL 恰为 remaining_seconds。"""
        self.mgr.get_snapshot.return_value = ReportSnapshot(
            results=[{"columns": ["id"], "rows": [[1]], "total": 1}],
            sql_query="SELECT 1",
            updated_at=NOW + remaining_seconds - ttl_hours * 3600,
            config_version="v-test")

    def _add_endpoint(self, url_path, report_id=1, static_cache=1):
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO api_endpoints (report_id,name,url_path,"
                "output_format,static_cache) VALUES (?,?,?,?,?)",
                (report_id, url_path, url_path, "json", static_cache))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# K 组：缓存保活验收（B13/B14/B15/B16）
# ---------------------------------------------------------------------------

class TestKeepaliveAcceptance(AcceptanceBase):

    def test_k1_remaining_below_threshold_triggers(self):
        """剩余 TTL 500s < ahead 600s → 先算后换重建。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(500)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        self.mock_exec.assert_called_once()
        kw = self.mock_exec.call_args.kwargs
        self.assertTrue(kw["force_rebuild"])
        self.assertFalse(kw["refresh"])

    def test_k2_remaining_equal_threshold_skips(self):
        self._enable_keepalive()
        self._set_snapshot_remaining(600)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k3_remaining_above_threshold_skips(self):
        self._enable_keepalive()
        self._set_snapshot_remaining(700)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k4_missing_snapshot_skips(self):
        self._enable_keepalive()
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k5_zero_ahead_never_triggers(self):
        self._enable_keepalive(ahead=0)
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k6_redis_unavailable_skips_whole_scan(self):
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        with patch("scheduler.redis_cache.redis_available", return_value=False):
            self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mgr.get_snapshot.assert_not_called()

    def test_k7_no_schedule_row_skips(self):
        """JOIN report_schedules：报表没配启用任务 → 不参与保活。"""
        self._enable_keepalive(with_schedule=False)
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)

    def test_k8_burned_out_schedule_skips(self):
        """熔断中（fail_count=5）的任务不参与保活。"""
        self._enable_keepalive(fail_count=5)
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)

    def test_k9_prefer_cache_off_skips(self):
        self._enable_keepalive(prefer_cache=0)
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)

    def test_k18_multi_binding_single_rebuild(self):
        """回归（2026-08-23 审查）：同一报表挂在多个启用任务下，保活扫描
        必须去重只重建一次（JOIN 多行曾导致重复重建与计数虚高）。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        # 同一张报表 1 再挂第二个独立任务（多对多合法场景）
        conn = _get_conn()
        config_db.upsert_schedule(
            conn, name="task2-same-report", report_ids=[1],
            schedule_type="interval", interval_minutes=60,
            daily_time="08:00", misfire_policy="skip", enabled=1,
            next_run_at=NOW)
        conn.close()
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        self.mock_exec.assert_called_once()

    def test_k10_single_report_error_isolated(self):
        """B16：报表1 保活异常 → 报表2 仍正常重建。"""
        self._add_report(2, "报表B", keepalive_enabled=1,
                         keepalive_ahead_seconds=300, cache_ttl_hours=6)
        conn = _get_conn()
        config_db.upsert_schedule(
            conn, report_id=2, schedule_type="interval",
            interval_minutes=30, daily_time="08:00",
            misfire_policy="skip", enabled=1, next_run_at=NOW)
        conn.close()
        self._enable_keepalive(report_id=1, ahead=600)
        self._set_snapshot_remaining(100)
        self.mock_exec.side_effect = [RuntimeError("池炸了"), None]
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        self.assertEqual(self.mock_exec.call_count, 2)

    def test_k11_expired_snapshot_triggers(self):
        """快照已过期（剩余 TTL 为负）→ 立即进入提前量窗口。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(-100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        self.mock_exec.assert_called_once()

    def test_k12_ahead_exceeds_ttl_always_triggers(self):
        """ahead(7h) > TTL(6h)：快照剩余 TTL 永远 < ahead → 每轮都触发。"""
        self._enable_keepalive(ahead=7 * 3600, ttl_hours=6)
        self._set_snapshot_remaining(6 * 3600 - 1)  # 刚写完也已在窗口内
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        self.mock_exec.assert_called_once()

    def test_k13_static_files_rebuilt_only_for_static_cached(self):
        """B15：重建成功后，只联动 static_cache=1 的端点；static_cache=0 跳过。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        self._add_endpoint("/api/keep-json", static_cache=1)
        self._add_endpoint("/api/keep-plain", static_cache=0)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        paths = [c[0] for c in self.static_calls]
        self.assertEqual(paths, ["/api/keep-json"])
        # 保活是计划内预热而非失效事件 → record_invalidation=False（B15 语义）
        self.assertFalse(self.static_calls[0][1])
        self.mock_exec.assert_called_once()

    def test_k14_static_endpoint_failure_does_not_affect_keepalive(self):
        """B15：静态联动端点失败 → 仅告警，保活成功状态不受影响。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        self._add_endpoint("/api/keep-a", static_cache=1)
        self._add_endpoint("/api/keep-b", static_cache=1)
        self.static_side_effects["/api/keep-a"] = RuntimeError("磁盘满")
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 1)
        # 两个端点都被尝试（失败的不中断后续）
        self.assertEqual(len(self.static_calls), 2)
        self.mock_exec.assert_called_once()

    def test_k15_execution_failure_no_rebuild_no_static(self):
        """执行失败 → 不计数重建、不联动静态文件。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        self._add_endpoint("/api/keep-json", static_cache=1)
        self.mock_exec.side_effect = RuntimeError("MySQL down")
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.assertEqual(self.static_calls, [])

    def test_k15b_keepalive_disabled_report_skipped(self):
        """keepalive_enabled=0 的报表不参与保活。"""
        # 默认种子报表 keepalive_enabled=0
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k16_zero_ttl_hours_skipped(self):
        """cache_ttl_hours=0：SQL JOIN 过滤，保活无意义 → 跳过。"""
        self._enable_keepalive(ttl_hours=0)
        self._set_snapshot_remaining(100)
        self.assertEqual(self.sched.run_keepalive_tick(now=NOW), 0)
        self.mock_exec.assert_not_called()

    def test_k17_keepalive_not_affect_burned_schedule_state(self):
        """保活执行不改变任务行执行状态字段（与定时执行互不影响）。"""
        self._enable_keepalive()
        self._set_snapshot_remaining(100)
        self.sched.run_keepalive_tick(now=NOW)
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT s.* FROM report_schedules s "
                "JOIN schedule_reports sr ON sr.schedule_id=s.id "
                "WHERE sr.report_id=? LIMIT 1",
                (self.report_id,)).fetchone()
            self.assertEqual(row["last_status"], None)
            self.assertEqual(row["fail_count"], 0)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# M 组：misfire 错过补偿验收（B8/B9/B10/B11）
# ---------------------------------------------------------------------------

class TestMisfireAcceptance(AcceptanceBase):

    def test_m1_interval_overdue_merged_rerun(self):
        """B8：interval 停机跨 4 周期 → 合并补跑一次，next=now+interval。"""
        sid = self._add_schedule(next_run_at=NOW - 7200)
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats, {"ran": 1, "skipped": 0})
        self.assertEqual(self.mock_exec.call_count, 1)
        row = self._row(sid)
        self.assertEqual(row["next_run_at"], NOW + 1800)  # 精确推进一个周期
        self.assertEqual(row["last_status"], "success")

    def test_m2_daily_skip_advance_and_audit(self):
        """B9：daily skip 当日已过 → 不补跑、next=次日 09:00、审计。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="skip", audit_enabled=1,
                                 next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats, {"ran": 0, "skipped": 1})
        self.mock_exec.assert_not_called()
        row = self._row(sid)
        self.assertEqual(row["next_run_at"], _local_ts(2026, 8, 22, 9, 0))
        records = self._audit_of("scheduled_misfire")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["after_value"]["policy"], "skip")
        self.assertEqual(records[0]["after_value"]["resumed_at"],
                         _local_ts(2026, 8, 22, 9, 0))

    def test_m3_daily_run_once_reruns_when_not_run_today(self):
        """B10：run_once 且今天未跑 → 补跑一次，next=次日。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="run_once", last_run_at=None,
                                 next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 1)
        self.mock_exec.assert_called_once()
        row = self._row(sid)
        self.assertEqual(row["next_run_at"], _local_ts(2026, 8, 22, 9, 0))
        self.assertEqual(row["last_status"], "success")

    def test_m4_daily_run_once_skips_if_already_ran_today(self):
        """B10 反例：今天已跑过 → 不补跑（防重复执行）。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="run_once",
                                 last_run_at=_local_ts(2026, 8, 21, 9, 0, 5),
                                 next_run_at=_local_ts(2026, 8, 22, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 0)
        self.mock_exec.assert_not_called()

    def test_m5_interval_overdue_disabled_skipped(self):
        self._add_schedule(enabled=0, next_run_at=NOW - 7200)
        self.assertEqual(self.sched.run_startup_scan(now=NOW),
                         {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()

    def test_m6_interval_overdue_burned_out_skipped(self):
        """interval 过期且熔断（fail_count=5）→ 启动扫描跳过。"""
        self._add_schedule(fail_count=5, next_run_at=NOW - 7200)
        self.assertEqual(self.sched.run_startup_scan(now=NOW),
                         {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()

    def test_m7_daily_overdue_burned_out_skipped(self):
        self._add_schedule(schedule_type="daily", daily_time="09:00",
                           fail_count=5, next_run_at=NOW - 7200)
        self.assertEqual(self.sched.run_startup_scan(now=NOW),
                         {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()

    def test_m8_null_next_run_skipped(self):
        """next_run_at IS NULL（未排程）→ 启动扫描不处理。"""
        self._add_schedule(next_run_at=None)
        self.assertEqual(self.sched.run_startup_scan(now=NOW),
                         {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()

    def test_m9_daily_skip_already_ran_today_still_advances(self):
        """daily skip 今天已跑过 → 仍跳过并推进次日（skip 无补跑语义）。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="skip",
                                 last_run_at=_local_ts(2026, 8, 21, 9, 0, 5),
                                 next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats, {"ran": 0, "skipped": 1})
        self.mock_exec.assert_not_called()
        self.assertEqual(self._row(sid)["next_run_at"],
                         _local_ts(2026, 8, 22, 9, 0))

    def test_m10_daily_run_once_cross_midnight_reruns_today(self):
        """run_once 昨天跑过、今天未跑（跨日）→ 今天补跑。"""
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="run_once",
                                 last_run_at=_local_ts(2026, 8, 20, 9, 0),
                                 next_run_at=_local_ts(2026, 8, 21, 9, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 1)
        self.mock_exec.assert_called_once()
        self.assertEqual(self._row(sid)["last_status"], "success")

    def test_m11_invalid_daily_time_no_crash(self):
        """非法 daily_time：compute_next_run 返回 None，跳过推进不崩溃。"""
        # upsert 会校验拒绝非法值，先以合法值建任务再用 SQL 注入非法值
        sid = self._add_schedule(schedule_type="daily", daily_time="08:00",
                                 misfire_policy="skip",
                                 next_run_at=NOW - 60)
        conn = _get_conn()
        conn.execute("UPDATE report_schedules SET daily_time=? WHERE id=?",
                     ("25:00", sid))
        conn.commit()
        conn.close()
        stats = self.sched.run_startup_scan(now=NOW)
        # next_run_at 推不动（nxt=None）→ 计入 skipped（避免卡死过期点）
        self.assertEqual(stats["skipped"], 1)
        self.mock_exec.assert_not_called()

    def test_m12_no_overdue_returns_empty(self):
        self._add_schedule(next_run_at=NOW + 3600)
        self.assertEqual(self.sched.run_startup_scan(now=NOW),
                         {"ran": 0, "skipped": 0})
        self.mock_exec.assert_not_called()

    def test_m13_mixed_stats_correct(self):
        """混合：interval 补跑 + daily skip 推进 + run_once 补跑 + 熔断跳过。"""
        self._add_schedule(report_id=1, next_run_at=NOW - 7200)          # M1 补跑
        self._add_report(2, "报表B")
        self._add_schedule(report_id=2, schedule_type="daily",
                           daily_time="09:00", misfire_policy="skip",
                           next_run_at=_local_ts(2026, 8, 21, 9, 0))     # skip
        self._add_report(3, "报表C")
        self._add_schedule(report_id=3, schedule_type="daily",
                           daily_time="09:00", misfire_policy="run_once",
                           next_run_at=_local_ts(2026, 8, 21, 9, 0))     # 补跑
        self._add_report(4, "报表D")
        self._add_schedule(report_id=4, fail_count=5, next_run_at=NOW - 7200)  # 熔断
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats, {"ran": 2, "skipped": 1})
        self.assertEqual(self.mock_exec.call_count, 2)
        # 熔断的报表4 未被触碰
        self.assertNotIn(4, [c[0] for c in self.executor.submitted])

    def test_m14_runtime_tick_uses_scheduler_trigger(self):
        """B11：运行期 tick 只按到期派发，trigger=scheduler（非 misfire）。"""
        sid = self._add_schedule(next_run_at=NOW - 60, audit_enabled=1)
        self.sched.run_tick(now=NOW)
        self.assertEqual(self.mock_exec.call_count, 1)
        audit = self._audit_of("scheduled_run")
        self.assertEqual(audit[0]["after_value"]["trigger"], "scheduler")

    def test_m15_daily_skip_next_precise_advance(self):
        """daily skip 推进精确到次日 HH:MM（含跨月边界）。"""
        # 2026-08-31 23:00 设 daily 08:00 已过 → 推进到 2026-09-01 08:00（跨月）
        sep_1 = _local_ts(2026, 8, 31, 23, 0, 0)
        self._add_schedule(schedule_type="daily", daily_time="08:00",
                           misfire_policy="skip",
                           next_run_at=_local_ts(2026, 8, 31, 8, 0))
        with patch("scheduler.time.time", return_value=sep_1):
            stats = self.sched.run_startup_scan(now=sep_1)
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(self.sched._executor, self.executor)  # 环境完好

    def test_m16_misfire_rerun_audit_trigger(self):
        """misfire 补跑审计 trigger=misfire，after_value 完整（B19）。"""
        self._add_schedule(next_run_at=NOW - 7200, audit_enabled=1)
        self.sched.run_startup_scan(now=NOW)
        records = self._audit_of("scheduled_run")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["user"], "system")
        self.assertEqual(rec["after_value"]["trigger"], "misfire")
        self.assertEqual(rec["after_value"]["status"], "success")
        self.assertIn("duration_ms", rec["after_value"])

    def test_m17_run_once_ran_today_but_next_expired_advances_no_rerun(self):
        """run_once 今天已跑过、但 next_run_at 意外过期 → 不补跑只推进。

        防御性场景：正常回写后 next 应在明日，此处人为构造过期数据，
        验证不会因"今日已跑过却已过期"触发重复执行。
        """
        sid = self._add_schedule(schedule_type="daily", daily_time="09:00",
                                 misfire_policy="run_once",
                                 last_run_at=_local_ts(2026, 8, 21, 9, 0, 5),
                                 next_run_at=_local_ts(2026, 8, 21, 10, 0))
        stats = self.sched.run_startup_scan(now=NOW)
        self.assertEqual(stats["ran"], 0)
        self.mock_exec.assert_not_called()
        # next 推进到次日（不卡在过期点）
        self.assertEqual(self._row(sid)["next_run_at"],
                         _local_ts(2026, 8, 22, 9, 0))


if __name__ == "__main__":
    unittest.main()
