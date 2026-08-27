"""scheduler.py — 进程内报表定时调度器（迁移 16 / report_schedules）。

职责（规格 .scratch/report-scheduler/spec.md）：
- 定时执行：interval（每 N 分钟）/ daily（每日 HH:MM 本地时区）自动
  执行报表查询，预热缓存或驱动写操作副作用；
- 缓存保活（refresh-ahead）：对启用保活的报表，Redis 快照临近过期时
  以 force_rebuild「先算后换」提前重建，消除过期后首个请求的空窗；
- misfire 处理：启动扫描按任务策略补跑或跳过。

架构约束：
- 单进程 daemon 线程 + ThreadPoolExecutor，不引入外部调度依赖；
- 每个工作线程自建配置库连接（db.get_config_db() 每次独立连接）；
- 同一任务同时最多一个在途执行（内存 running 集合去重）；
- 连续失败 fail_count≥5 自动熔断，手动触发成功后重置。
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import config_db
import db
import redis_cache
import report as report_mod
import api_handler

# 连续失败熔断阈值（B5）：达到后 tick 不再自动派发，手动触发不受限
MAX_FAIL_COUNT = 5


# ---------------------------------------------------------------------------
# 排除规则树求值（规格 scheduler-composition-exclusion）
# ---------------------------------------------------------------------------
# 任务级"静默窗口"：命中排除规则的执行时刻不触发报表执行。规则树为 JSON：
#   - 内部节点：{"op": "AND"|"OR", "children": [节点...]}（空 children 视为假）
#   - 叶子：dow / tod / date / date_range（见规格 §4.5）
# 根 OR 多规则并行、单规则可嵌套 AND/OR。非法/损坏一律按"不静默"处理，
# 保证不会意外吞掉执行，并打 warning 便于排查。
# ---------------------------------------------------------------------------

_DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hm(value: str) -> int:
    """把 'HH:MM' 解析为当日分钟数。"""
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _leaf_hit(node: dict, dt: datetime) -> bool:
    """求单个叶子节点的命中（不处理 AND/OR 内部节点）。"""
    ntype = node.get("type")
    if ntype == "dow":
        allowed = node.get("in")
        if not isinstance(allowed, list) or not allowed:
            # E26 缺字段：非法树一律 warning + 不静默（spec §4.5），
            # 否则配置笔误会被静默吞掉、用户以为规则生效
            logging.warning("排除规则 dow 节点缺 in 列表，按不静默处理")
            return False
        return _DOW_NAMES[dt.weekday()] in set(allowed)
    if ntype == "tod":
        f = _parse_hm(node["from"])
        t = _parse_hm(node["to"])
        cur = dt.hour * 60 + dt.minute
        if f <= t:
            return f <= cur <= t
        # 跨午夜（如 21:00–09:00）：满足任一侧即命中
        return cur >= f or cur <= t
    if ntype == "date":
        on = node.get("on")
        if not isinstance(on, list) or not on:
            logging.warning("排除规则 date 节点缺 on 列表，按不静默处理")
            return False
        return dt.date().isoformat() in set(on)
    if ntype == "date_range":
        d = dt.date()
        lo = datetime.strptime(node["from"], "%Y-%m-%d").date()
        hi = datetime.strptime(node["to"], "%Y-%m-%d").date()
        return lo <= d <= hi
    # 未知叶子类型 → 不静默（E26：需 warning 便于发现配置笔误）
    logging.warning("排除规则含未知叶子类型 %r，按不静默处理", ntype)
    return False


def _eval_node(node, dt: datetime) -> bool:
    if not isinstance(node, dict):
        return False
    op = node.get("op")
    if op in ("AND", "OR"):
        children = node.get("children") or []
        if not children:
            return False
        if op == "AND":
            return all(_eval_node(c, dt) for c in children)
        return any(_eval_node(c, dt) for c in children)
    return _leaf_hit(node, dt)


def evaluate_exclusions(tree, dt: datetime) -> bool:
    """判断时刻 dt 是否命中任务的排除规则（应静默跳过）。

    接受 dict 树或 JSON 字符串（库里以 TEXT 存储）。None / 空串 / 非对象 /
    JSON 损坏 / 求值异常一律返回 False（不静默），并打 warning。
    """
    if tree is None:
        return False
    if isinstance(tree, str):
        tree = tree.strip()
        if not tree:
            return False
        try:
            tree = json.loads(tree)
        except Exception:
            logging.warning("排除规则 JSON 解析失败，按不静默处理")
            return False
    if not isinstance(tree, dict):
        return False
    try:
        return _eval_node(tree, dt)
    except Exception:
        logging.warning("排除规则求值异常，按不静默处理")
        return False


def validate_exclusions(tree) -> tuple:
    """校验排除规则树结构是否合法，返回 (ok: bool, error: str|None)。

    用于 UI 保存前的后端校验：结构非法时拒绝保存并回显错误，绝不静默吞掉。
    接受 dict 或 JSON 字符串。
    """
    if tree is None or (isinstance(tree, str) and not tree.strip()):
        return True, None  # 空 = 无排除，合法
    if isinstance(tree, str):
        try:
            tree = json.loads(tree)
        except Exception as e:
            return False, f"JSON 解析失败: {e}"
    if not isinstance(tree, dict):
        return False, "排除规则根节点必须是对象"
    ok, err = _validate_node(tree)
    return ok, err


def _validate_node(node) -> tuple:
    if not isinstance(node, dict):
        return False, "节点必须是对象"
    op = node.get("op")
    if op in ("AND", "OR"):
        children = node.get("children")
        if not isinstance(children, list) or not children:
            return False, f"{op} 节点必须包含非空 children 列表"
        for c in children:
            ok, err = _validate_node(c)
            if not ok:
                return ok, err
        return True, None
    ntype = node.get("type")
    if ntype == "dow":
        if not isinstance(node.get("in"), list) or not node["in"]:
            return False, "dow 节点需要非空 in 列表"
        bad = [x for x in node["in"] if x not in _DOW_NAMES]
        if bad:
            return False, f"dow 含非法星期: {bad}"
        return True, None
    if ntype == "tod":
        try:
            _parse_hm(node["from"]); _parse_hm(node["to"])
        except Exception:
            return False, "tod 节点 from/to 须为 HH:MM"
        return True, None
    if ntype == "date":
        if not isinstance(node.get("on"), list) or not node["on"]:
            return False, "date 节点需要非空 on 列表"
        return True, None
    if ntype == "date_range":
        try:
            datetime.strptime(node["from"], "%Y-%m-%d")
            datetime.strptime(node["to"], "%Y-%m-%d")
        except Exception:
            return False, "date_range 节点 from/to 须为 YYYY-MM-DD"
        return True, None
    return False, f"未知节点类型: {ntype!r}"


# 默认调度参数（可被 app_config.json 的 scheduler 节覆盖）
# tick 默认 10s：降低 daily 定时执行相对设定时刻的最大相位延迟（30s→10s，
# 2026-08-21 用户确认，见 SPEC §2）
DEFAULT_TICK_SECONDS = 10
DEFAULT_WORKERS = 2


def get_scheduler_config() -> dict:
    """读取全局调度配置（enable/tick_seconds/workers），带默认值兜底。"""
    from app_config import get_config
    cfg = get_config().get("scheduler", {}) or {}
    return {
        # 缺失键默认停用（B17 规格）；显式 true 才启动
        "enable": bool(cfg.get("enable", False)),
        "tick_seconds": max(1, int(cfg.get("tick_seconds",
                                           DEFAULT_TICK_SECONDS))),
        "workers": max(1, int(cfg.get("workers", DEFAULT_WORKERS))),
    }


def _parse_daily_time(daily_time: str):
    """解析 HH:MM 为 (hour, minute)；非法返回 None。"""
    parts = str(daily_time).split(":")
    if (len(parts) != 2 or not all(p.isdigit() for p in parts)):
        return None
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def compute_next_run(schedule_type: str, interval_minutes: int,
                     daily_time: str, now: float,
                     last_run_at=None) -> float | None:
    """计算下次执行时刻（epoch 秒）；无法排程返回 None。

    - interval：max(now, last_run_at) + interval*60 —— 以最近一次实际执行
      （或当前时刻）为基准顺延一个周期，避免重启后周期漂移叠加补跑；
    - daily：今日 HH:MM 未过则今日，否则次日；本地时区秒级对齐。
    """
    if schedule_type == "interval":
        base = max(now, last_run_at) if last_run_at else now
        return base + max(1, int(interval_minutes)) * 60
    if schedule_type == "daily":
        hm = _parse_daily_time(daily_time)
        if hm is None:
            return None
        lt = time.localtime(now)
        day_start = now - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec)
        target = day_start + hm[0] * 3600 + hm[1] * 60
        if target <= now:
            target += 86400
        return target
    return None


def snapshot_remaining_ttl(snapshot, ttl_hours: int, now: float) -> float | None:
    """估算 Redis 快照剩余有效期（秒）；无快照/永不过期返回 None。

    数据驱动判定（不依赖 Redis TTL 命令）：快照写入时以 setex(ttl_hours)
    落盘，预计过期时刻 = updated_at + ttl_hours*3600。
    """
    if snapshot is None or ttl_hours <= 0:
        return None
    expires_at = float(snapshot.updated_at) + ttl_hours * 3600
    return expires_at - now


class ReportScheduler:
    """报表定时调度器：tick 扫描到期任务 → 线程池执行 → 结果回写。"""

    def __init__(self, tick_seconds: int = DEFAULT_TICK_SECONDS,
                 workers: int = DEFAULT_WORKERS,
                 cache=None):
        self._tick_seconds = max(1, int(tick_seconds))
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(workers)),
            thread_name_prefix="report-sched")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # 在途任务集合（schedule_id）：同一任务同时最多一个执行（B7）
        self._running: set[int] = set()
        self._running_lock = threading.Lock()
        # 保活独立节拍：与定时 tick 共用线程循环，按各自间隔推进
        self._next_keepalive_at = 0.0
        self._cache = cache  # None → execute_report 使用全局进程缓存

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动 daemon tick 线程（先跑启动 misfire 扫描再进入循环）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._tick_loop, name="report-scheduler", daemon=True)
        self._thread.start()
        logging.info("报表调度器已启动 (tick=%ss)", self._tick_seconds)

    def shutdown(self, timeout: float = 5.0) -> None:
        """通知停止并等待在途任务收尾（KeyboardInterrupt 关闭链路调用）。"""
        self._stop_event.set()
        self._executor.shutdown(wait=True)
        if self._thread:
            self._thread.join(timeout=timeout)

    def _tick_loop(self) -> None:
        # 启动扫描：处理停机期间错过的执行（B8/B9/B10），失败不阻断主循环
        try:
            self.run_startup_scan()
        except Exception:
            logging.exception("调度器启动 misfire 扫描失败")
        while not self._stop_event.wait(self._tick_seconds):
            try:
                self.run_tick()
            except Exception:
                logging.exception("调度器 tick 异常")
            try:
                self.run_keepalive_tick()
            except Exception:
                logging.exception("调度器保活 tick 异常")

    # ------------------------------------------------------------------
    # 到期扫描与执行
    # ------------------------------------------------------------------

    def run_tick(self, now: float = None) -> int:
        """扫描到期任务并提交线程池；返回本次派发数。

        在途任务跳过（B7 去重）；派发即从到期集合移出（running 集合
        在提交前占位，防止下个 tick 重复派发同一任务）。
        """
        now = time.time() if now is None else now
        conn = db.get_config_db()
        try:
            due = config_db.get_due_schedules(conn, now)
        finally:
            conn.close()
        dispatched = 0
        for sched in due:
            sid = sched["id"]
            with self._running_lock:
                if sid in self._running:
                    continue
                self._running.add(sid)
            # 静默窗口命中（S1/S3）：自动触发不执行，标记 skipped 并推进
            if evaluate_exclusions(sched.get("exclusions"),
                                   datetime.fromtimestamp(now)):
                try:
                    self._mark_skipped(sched, now)
                finally:
                    # 无论 _mark_skipped 是否抛异常都必须释放 _running，
                    # 否则任务被永久去重、静默窗口过后也再不会派发（B7 语义）。
                    with self._running_lock:
                        self._running.discard(sid)
                continue
            self._executor.submit(self._run_schedule, sched, "scheduler")
            dispatched += 1
        return dispatched

    def _mark_skipped(self, sched: dict, now: float) -> None:
        """静默窗口命中：标记 skipped、推进 next_run_at（不执行报表），
        仅在 audit_enabled 时写 scheduler 审计（S5/S6）。"""
        sid = sched["id"]
        next_run_at = compute_next_run(
            sched["schedule_type"], sched["interval_minutes"],
            sched["daily_time"], now,
            last_run_at=sched.get("last_run_at") or None)
        conn = db.get_config_db()
        try:
            config_db.mark_schedule_result(
                conn, sid, "skipped", next_run_at=next_run_at,
                last_run_at=now)
        finally:
            conn.close()
        if int(sched.get("audit_enabled", 0) or 0):
            try:
                config_db._write_audit_log(
                    "system", "scheduled_skip", "schedule", sid,
                    f"task#{sched.get('name')}",
                    after_value={"trigger": "skip", "status": "skipped",
                                 "next_run_at": next_run_at},
                    log_type="scheduler")
            except Exception:
                logging.warning("定时任务 #%s 跳过审计写入失败", sid)

    def _run_schedule(self, sched: dict, trigger: str,
                      session_user=None) -> None:
        """执行单个任务并回写结果（线程池工作线程内运行）。

        trigger ∈ {scheduler, misfire, manual}；审计 user：
        scheduler/misfire 记 system，manual 记操作者 session_user。
        """
        sid = sched["id"]
        audit_user = session_user if trigger == "manual" else "system"
        status, error = "success", None
        started = time.time()
        next_run_at = None
        try:
            err = self._execute_schedule(sched)
            if err:
                # 多报表聚合（用户确认 2026-08-24）：单绑定失败不中断整包，
                # 已完成绑定正常落库；任一绑定失败 → 整体记 fail。
                status, error = "fail", err
        except Exception as e:
            status = "fail"
            error = f"{type(e).__name__}: {e}"
            logging.warning("定时任务 #%s (task=%s) 执行失败: %s",
                            sid, sched.get("name"), error)
        finished = time.time()
        duration_ms = int((finished - started) * 1000)

        conn = db.get_config_db()
        try:
            cur = config_db.get_schedule(conn, sid)
            if cur is not None:
                next_run_at = compute_next_run(
                    cur["schedule_type"], cur["interval_minutes"],
                    cur["daily_time"], finished,
                    last_run_at=cur["last_run_at"] or None)
            config_db.mark_schedule_result(
                conn, sid, status, error=error,
                next_run_at=next_run_at, last_run_at=finished,
                last_duration_ms=duration_ms)
        except Exception:
            logging.exception("定时任务 #%s 结果回写失败", sid)
        finally:
            with self._running_lock:
                self._running.discard(sid)
            conn.close()

        # B19：自动执行审计（成功与失败均记，供追溯）。
        # log_type=scheduler：审计日志单开"定时任务"类型（2026-08-22 需求），
        # 与用户操作（operation）分栏，可独立筛选/导出。
        # audit_enabled=0（默认）时不写任何 scheduler 审计（S5/S6）。
        if int(sched.get("audit_enabled", 0) or 0):
            try:
                # 附带本次执行的报表清单（T3：最近执行记录增强）。
                # report_total=绑定总数；report_executed=实际参与执行（启用绑定）数；
                # report_names=参与执行的报表名列表；向后兼容旧记录（缺键降级）。
                rep_conn = db.get_config_db()
                try:
                    bound = config_db.get_schedule_reports(rep_conn, sid)
                finally:
                    rep_conn.close()
                report_total = len(bound)
                enabled = [r for r in bound
                           if int(r.get("enabled", 1) or 0) == 1]
                report_executed = len(enabled)
                report_names = [r.get("report_name") or r.get("report_id")
                                for r in enabled]
                config_db._write_audit_log(
                    audit_user, "scheduled_run", "schedule", sid,
                    f"task#{sched.get('name')}",
                    after_value={"trigger": trigger, "status": status,
                                 "duration_ms": duration_ms,
                                 "error": error,
                                 "report_total": report_total,
                                 "report_executed": report_executed,
                                 "report_names": report_names},
                    log_type="scheduler")
            except Exception:
                logging.warning("定时任务 #%s 审计写入失败", sid)

    def _execute_schedule(self, sched: dict) -> Optional[str]:
        """执行报表查询主体（B12 写护栏由 execute_report 内 PH-05 生效）。

        任务可绑定多张报表：按 order_index 顺序依次执行各启用绑定（T4）。
        单绑定执行失败（pool 缺失 / SQL 报错）**不中断整包**——记录错误后
        继续执行剩余绑定，已完成的绑定正常落库（force_rebuild 写回缓存）。
        全部成功返回 None；任一绑定失败返回首个失败摘要（聚合）。
        """
        conn = db.get_config_db()
        errors: list[str] = []
        try:
            reports = config_db.get_schedule_reports(conn, sched["id"])
            if not reports:
                logging.warning("定时任务 #%s 无绑定报表，跳过执行", sched["id"])
                return None
            for binding in reports:
                # 绑定级启停：禁用的绑定跳过（S10）
                if not int(binding.get("enabled", 1) or 0):
                    continue
                rpt = config_db.get_report(conn, binding["report_id"])
                if rpt is None:
                    logging.warning("定时任务 #%s 报表 #%s 不存在，跳过",
                                    sched["id"], binding["report_id"])
                    continue
                pool_id = rpt.get("pool_id")
                pool = config_db.get_pool(conn, pool_id) if pool_id else None
                if pool is None:
                    errors.append(f"报表 #{rpt['id']} 未绑定有效连接池")
                    logging.warning("定时任务 #%s 报表 #%s 未绑定连接池，跳过",
                                    sched["id"], rpt["id"])
                    continue
                try:
                    # report=dict 全量传入 → allow_write=0 时写 SQL 被 PH-05 拦截
                    report_mod.execute_report(
                        rpt["id"], rpt["sql_query"], pool,
                        page=1, page_size=rpt.get("default_page_size") or 20,
                        refresh=False, force_rebuild=True, report=rpt,
                        cache=self._cache)
                except Exception as e:
                    errors.append(f"报表 #{rpt['id']}: {type(e).__name__}: {e}")
                    logging.warning("定时任务 #%s 报表 #%s 执行失败: %s",
                                    sched["id"], rpt["id"], e)
        finally:
            conn.close()
        return "; ".join(errors)[:500] if errors else None

    # ------------------------------------------------------------------
    # 手动触发（B6/B21）
    # ------------------------------------------------------------------

    def trigger_schedule(self, schedule_id: int,
                         session_user=None) -> bool:
        """手动触发任务：绕过熔断与在途检查（同步执行）。

        成功经 mark_schedule_result 重置 fail_count（B6）。
        任务不存在返回 False。
        """
        conn = db.get_config_db()
        try:
            sched = config_db.get_schedule(conn, schedule_id)
        finally:
            conn.close()
        if sched is None:
            return False
        self._run_schedule(sched, "manual", session_user=session_user)
        return True

    # ------------------------------------------------------------------
    # 启动 misfire 扫描（B8/B9/B10）
    # ------------------------------------------------------------------

    def run_startup_scan(self, now: float = None) -> dict:
        """启动时处理停机期间错过的执行；返回 {ran, skipped} 统计。

        - interval 过期（B8）：合并补跑一次，next 推进至 now+interval，
          不按周期连补多次；
        - daily skip（B9）：不补跑，next 推进至未来最近一日 HH:MM，
          审计 scheduled_misfire；
        - daily run_once（B10）：当日时刻已过且今天未跑过则补跑一次；
        - 运行期短暂阻塞不在此处理（B11，tick 只看 next_run_at）。
        """
        now = time.time() if now is None else now
        stats = {"ran": 0, "skipped": 0}
        conn = db.get_config_db()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM report_schedules WHERE enabled=1 AND "
                "fail_count<5 AND next_run_at IS NOT NULL AND next_run_at<=?",
                (now,)).fetchall()]
            for sched in rows:
                stype = sched["schedule_type"]
                # S7：错过时刻命中排除 → 视为正确跳过（推进 next_run_at，不补跑）。
                # 以"错过时刻"（next_run_at）求值而非当前扫描时刻：静默窗口
                # 回答的是"那个计划执行时刻是否应被排除"，停机跨窗口重启时
                # 用 now 判定会错误补跑本已被用户排除的执行。
                if evaluate_exclusions(
                        sched.get("exclusions"),
                        datetime.fromtimestamp(sched["next_run_at"])):
                    self._mark_skipped(sched, now)
                    stats["skipped"] += 1
                    continue
                if stype == "interval":
                    # B8：合并补跑一次
                    with self._running_lock:
                        self._running.add(sched["id"])
                    self._executor.submit(self._run_schedule, sched, "misfire")
                    stats["ran"] += 1
                elif stype == "daily":
                    ran_today = bool(sched["last_run_at"]) and time.strftime(
                        "%Y-%m-%d", time.localtime(sched["last_run_at"])) \
                        == time.strftime("%Y-%m-%d", time.localtime(now))
                    should_rerun = (sched["misfire_policy"] == "run_once"
                                    and not ran_today)
                    nxt = compute_next_run(stype, sched["interval_minutes"],
                                           sched["daily_time"], now,
                                           last_run_at=sched["last_run_at"])
                    if should_rerun:
                        sched = dict(sched, next_run_at=nxt)
                        with self._running_lock:
                            self._running.add(sched["id"])
                        self._executor.submit(self._run_schedule, sched,
                                              "misfire")
                        stats["ran"] += 1
                    else:
                        # B9：跳过但推进 next_run_at（否则永远卡在过期时刻）
                        if sched["misfire_policy"] == "skip":
                            if int(sched.get("audit_enabled", 0) or 0):
                                config_db._write_audit_log(
                                    "system", "scheduled_misfire", "schedule",
                                    sched["id"], f"task#{sched['name']}",
                                    after_value={"policy": "skip",
                                                 "missed_at": sched["next_run_at"],
                                                 "resumed_at": nxt},
                                    log_type="scheduler")
                        conn.execute(
                            "UPDATE report_schedules SET next_run_at=?, "
                            "updated_at=? WHERE id=?",
                            (nxt, time.strftime("%Y-%m-%d %H:%M:%S"),
                             sched["id"]))
                        conn.commit()
                        stats["skipped"] += 1
        finally:
            conn.close()
        if stats["ran"] or stats["skipped"]:
            logging.info("调度器启动扫描完成: 补跑=%s 跳过=%s",
                         stats["ran"], stats["skipped"])
        return stats

    # ------------------------------------------------------------------
    # 缓存保活（refresh-ahead，B13-B16）
    # ------------------------------------------------------------------

    def run_keepalive_tick(self, now: float = None) -> int:
        """扫描临近过期的保活报表并以先算后换重建；返回重建数。

        判定条件（全部满足才处理）：keepalive_enabled=1、prefer_cache=1、
        cache_ttl_hours>0、Redis 可用、快照剩余 TTL < ahead_seconds。
        任一报表异常仅记 warning，不影响其他报表与主循环（B16）。
        """
        now = time.time() if now is None else now
        if not redis_cache.redis_available():
            return 0
        mgr = redis_cache.get_redis_manager()
        if mgr is None:
            return 0

        rebuilt = 0
        conn = db.get_config_db()
        # DISTINCT：同一报表可挂多个任务（多对多），不去重会重复重建
        rows = [dict(r) for r in conn.execute(
            "SELECT DISTINCT rc.* FROM report_configs rc "
            "JOIN schedule_reports sr ON sr.report_id=rc.id "
            "JOIN report_schedules rs ON rs.id=sr.schedule_id "
            "WHERE rs.enabled=1 AND rs.fail_count<5 AND rc.keepalive_enabled=1 AND "
            "rc.prefer_cache=1 AND rc.cache_ttl_hours>0").fetchall()]

        for rpt in rows:
            rid = rpt["id"]
            try:
                ahead = int(rpt.get("keepalive_ahead_seconds", 0) or 0)
                if ahead <= 0:
                    continue
                ttl_hours = int(rpt.get("cache_ttl_hours", 0) or 0)
                version = redis_cache.compute_config_version(
                    rpt["sql_query"], rpt.get("pool_id"))
                key = redis_cache.build_snapshot_key(mgr.key_prefix, rid,
                                                     version)
                snap = mgr.get_snapshot(key)
                remaining = snapshot_remaining_ttl(snap, ttl_hours, now)
                if remaining is None or remaining >= ahead:
                    continue  # 无快照（等请求自然重建）或仍新鲜
                # 先算后换：force_rebuild 不删旧快照，新数据原子覆盖（B14）
                pool_id = rpt.get("pool_id")
                pool = config_db.get_pool(conn, pool_id) if pool_id else None
                if pool is None:
                    raise RuntimeError(f"报表 #{rid} 连接池不可用")
                report_mod.execute_report(
                    rid, rpt["sql_query"], pool, page=1,
                    page_size=rpt.get("default_page_size") or 20,
                    refresh=False, report=rpt, cache=self._cache,
                    force_rebuild=True)
                rebuilt += 1
                # 静态文件联动：该报表全部静态端点重算落盘（B15），
                # 任一端点失败不影响其他端点，也不影响保活成功状态
                self._rebuild_static_files(conn, rpt)
            except Exception as e:
                logging.warning("保活重建失败 report=%s: %s", rid, e)
        conn.close()
        return rebuilt

    @staticmethod
    def _rebuild_static_files(conn, rpt: dict) -> None:
        """重建报表全部启用静态缓存的 API 端点文件（B15）。"""
        endpoints = config_db.get_api_endpoints_by_report(conn, rpt["id"])
        for ep in endpoints:
            if not int(ep.get("static_cache", 1) or 0):
                continue
            try:
                written, status, _body, _hdr = \
                    api_handler.rebuild_static_endpoint_file(
                        conn, ep, record_invalidation=False)
                if not written or status != 200:
                    logging.warning("保活静态联动未落盘 endpoint=%s status=%s",
                                    ep.get("url_path"), status)
            except Exception as e:
                logging.warning("保活静态联动失败 endpoint=%s: %s",
                                ep.get("url_path"), e)


# ---------------------------------------------------------------------------
# 模块级单例（server.main 启动 / 关闭链路使用）
# ---------------------------------------------------------------------------

_scheduler: ReportScheduler | None = None


def start_scheduler_from_config() -> ReportScheduler | None:
    """按全局配置创建并启动调度器；enable=false 时不启动（B17）。

    已在运行时直接返回现有实例（幂等，防重复启动多个线程池）。
    """
    global _scheduler
    cfg = get_scheduler_config()
    if not cfg["enable"]:
        logging.info("报表调度器全局已停用 (scheduler.enable=false)")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = ReportScheduler(cfg["tick_seconds"], cfg["workers"])
    _scheduler.start()
    return _scheduler


def shutdown_scheduler(timeout: float = 5.0) -> None:
    """停止并清理模块级调度器实例（进程退出链路调用）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(timeout=timeout)
        _scheduler = None


def get_scheduler() -> ReportScheduler | None:
    """返回运行中的调度器实例（未启动返回 None，供手动触发降级判断）。"""
    return _scheduler


def trigger_manual(schedule_id: int, session_user=None) -> bool:
    """手动触发入口（B6/B21）：复用运行中的调度器实例；
    全局停用/未启动时降级为一次性临时实例同步执行。

    任务不存在返回 False；不校验熔断与 enabled（人工确认语义）。
    """
    inst = _scheduler
    if inst is None:
        inst = ReportScheduler(workers=1)
        try:
            return inst.trigger_schedule(schedule_id, session_user=session_user)
        finally:
            inst.shutdown(timeout=0)
    return inst.trigger_schedule(schedule_id, session_user=session_user)
