"""
audit_page.py — 审计日志页面处理

职责：
- 审计页 GET 浏览（自动轮转 + 分页查询 + 渲染）
- POST 清理操作（重定向回带 flash 消息）
- CSV 导出（下载响应头 + utf-8-sig 编码）

从 server.py 抽离，使 HTTP 处理器保持"路由 + 委托"薄层；
本模块只返回 (HTTP状态码, 响应体, 响应头字典)，不直接写 socket。
"""

import csv
import logging
import os
import time
import urllib.parse

import audit_db
import render
from app_config import get_audit_db_config, safe_int
from export import rows_to_csv

_FILTER_KEYS = ("type", "date_from", "date_to", "session_user", "keyword")

# CSV 导出：表头与对应取值字段（保持既有顺序与字段集不变）
_CSV_HEADER = ["时间", "类型", "操作者", "操作", "实体类型", "实体名称",
               "HTTP方法", "HTTP路径", "状态码", "IP", "耗时(ms)"]
_CSV_FIELDS = ["timestamp", "type", "session_user", "action",
               "entity_type", "entity_name", "http_method", "http_path",
               "http_status", "ip_address", "duration_ms"]


def handle_audit_request(method: str, query: str,
                         form_body: str = None) -> tuple:
    """处理审计日志页请求。

    返回 (HTTP状态码, 响应体, 响应头字典)：
    - 302 + 重定向 URL（POST 清理成功）
    - 200 + CSV bytes（导出）
    - 200 + HTML（页面浏览）
    """
    _rotate_expired()

    qs = urllib.parse.parse_qs(query, keep_blank_values=True)

    if method == "POST":
        data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
        action = data.get("action", [""])[0]
        if action == "clean":
            return _handle_clean(data)

    filters = _collect_filters(qs)
    if "export" in qs and qs["export"][0] == "csv":
        return _export_csv(filters)

    page = _qs_int(qs, "page", 1)
    page_size = max(1, _qs_int(qs, "page_size", 20))
    flash = qs.get("flash", [None])[0]

    audit_conn = audit_db.get_audit_db()
    try:
        total = audit_db.count_audit_logs(audit_conn, filters)
        rows = audit_db.query_audit_logs(audit_conn, filters, page, page_size)
    finally:
        audit_conn.close()

    db_size = 0
    try:
        db_size = os.path.getsize(audit_db.get_audit_db_path())
    except OSError:
        pass

    body = render.render_audit_page(rows, total, page, page_size, filters,
                                    message=flash or "", db_size=db_size)
    return 200, body, {}


def _rotate_expired():
    """按 retention_days 自动轮转过期审计日志（失败仅告警）。"""
    audit_config = get_audit_db_config()
    if audit_config.get("retention_days", 0) <= 0:
        return
    try:
        audit_conn = audit_db.get_audit_db()
        try:
            deleted = audit_db.rotate_audit_logs(
                audit_conn, audit_config["retention_days"])
            if deleted > 0:
                logging.info("审计日志自动清理: 删除了 %d 条过期记录", deleted)
        finally:
            audit_conn.close()
    except Exception as e:
        logging.warning("审计日志自动轮转失败: %s", e)


def _handle_clean(data: dict) -> tuple:
    """POST 清理操作：按筛选条件删除审计日志，重定向回审计页带结果消息。"""
    filters = _collect_filters(data)
    try:
        audit_conn = audit_db.get_audit_db()
        try:
            deleted = audit_db.delete_audit_logs(audit_conn, filters)
        finally:
            audit_conn.close()
        msg = f"清理成功：共删除 {deleted} 条审计日志"
    except Exception as e:
        msg = f"清理失败：{e}"
    clean_qs = urllib.parse.urlencode({k: v for k, v in filters.items() if v})
    return 302, f"/audit?{clean_qs}&flash={urllib.parse.quote(msg)}", {}


def _export_csv(filters: dict) -> tuple:
    """导出审计日志为 CSV（utf-8-sig 便于 Excel 识别）。"""
    audit_conn = audit_db.get_audit_db()
    try:
        rows = audit_db.export_audit_logs(audit_conn, filters)
    finally:
        audit_conn.close()

    # 与既有输出逐字节一致：QUOTE_ALL + CRLF 行尾 + utf-8-sig 编码（自带 BOM 字节）
    rows_out = [[r.get(key, "") for key in _CSV_FIELDS] for r in rows]
    csv_data = rows_to_csv(_CSV_HEADER, rows_out, bom=False,
                           quoting=csv.QUOTE_ALL, lineterminator="\r\n",
                           encoding="utf-8-sig")
    headers = {
        "Content-Type": "text/csv; charset=utf-8-sig",
        "Content-Disposition":
            f'attachment; filename="audit_log_{int(time.time())}.csv"',
    }
    return 200, csv_data, headers


def _collect_filters(params: dict) -> dict:
    """从查询参数/表单中收集非空筛选条件。"""
    filters = {}
    for key in _FILTER_KEYS:
        val = params.get(key, [None])[0]
        if val:
            filters[key] = val
    return filters


def _qs_int(qs: dict, key: str, default: int) -> int:
    """从 parse_qs 结果中安全取整数参数。"""
    try:
        return safe_int(qs.get(key, [default])[0], default)
    except IndexError:
        return default
