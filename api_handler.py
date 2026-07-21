"""
api_handler.py — API 数据接口请求处理模块

职责：
1. 处理所有 /api/ 前缀的 HTTP GET/POST/OPTIONS 请求
2. URL 路径匹配到已配置的 API 端点
3. API Key 鉴权（可选）
4. CORS 头处理
5. 按预设规则（字段/筛选/排序/条数）执行查询
6. POST 请求体支持覆盖预设规则
7. 输出 JSON 或 CSV 格式
8. 代理感知（X-Forwarded-For/Host/Proto）
9. 调用日志记录
"""

import json
import csv
import io
import time
import logging
import secrets
import urllib.parse
import traceback

import db
from report import execute_report, _parse_sorts, _parse_cols, parse_filters


def generate_api_key() -> str:
    """
    生成随机的 API Key。

    使用 secrets.token_urlsafe(32) 生成 43 字符随机字符串，
    添加 sk- 前缀，便于标识。
    """
    return "sk-" + secrets.token_urlsafe(32)
from query_executor import create_mysql_connection


def handle_api_request(path: str, method: str, headers: dict,
                       body: str, query_params: dict,
                       client_ip: str = "") -> tuple:
    """
    API 请求入口函数。

    参数:
        path: URL 路径（不含查询参数）
        method: HTTP 方法（GET/POST/OPTIONS）
        headers: 请求头字典
        body: POST 请求体字符串
        query_params: URL 查询参数字典（parse_qs 格式）
        client_ip: 客户端 IP（已考虑 X-Forwarded-For）

    返回:
        (HTTP 状态码, 响应体, 响应头字典)
    """
    start = time.time()

    # 路径匹配：从 /api/<path> 中提取 <path>
    norm_path = "/" + path.lstrip("/")
    prefix = "/api"
    if not norm_path.startswith(prefix):
        return 404, _error_response("接口不存在", "NOT_FOUND", headers), {}
    api_path = norm_path[len(prefix):] or "/"

    # 从 DB 查找匹配的端点
    conn = db.get_config_db()
    try:
        endpoint = db.get_api_endpoint_by_path(conn, norm_path)
        if endpoint is None:
            _log_api_call(norm_path, client_ip, 404, time.time() - start)
            return 404, _error_response("接口不存在或已禁用", "NOT_FOUND", headers), {}

        # CORS 预检
        if method == "OPTIONS":
            cors_headers = _build_cors_headers(endpoint, headers)
            _log_api_call(norm_path, client_ip, 204, time.time() - start)
            return 204, "", cors_headers

        # API Key 鉴权
        if endpoint.get("api_key"):
            auth_result = _validate_api_key(endpoint, headers, query_params)
            if auth_result:
                _log_api_call(norm_path, client_ip, 401, time.time() - start)
                return 401, _error_response(auth_result, "UNAUTHORIZED", headers), {}

        # 获取关联报表配置
        report_id = endpoint["report_id"]
        report = db.get_report(conn, report_id)
        if report is None:
            _log_api_call(norm_path, client_ip, 500, time.time() - start)
            return 500, _error_response("关联报表不存在", "INTERNAL_ERROR", headers), {}

        # 获取连接池配置
        pool_id = report.get("pool_id")
        if pool_id is None:
            _log_api_call(norm_path, client_ip, 500, time.time() - start)
            return 500, _error_response("报表未配置连接池", "INTERNAL_ERROR", headers), {}
        pool_config = db.get_pool(conn, pool_id)
        if pool_config is None:
            _log_api_call(norm_path, client_ip, 500, time.time() - start)
            return 500, _error_response("连接池配置不存在", "INTERNAL_ERROR", headers), {}

        # 解析规则：预设 + POST 覆盖
        filters, sorts, page, page_size, row_limit, output_format, columns, pretty = \
            _resolve_params(endpoint, method, body, query_params, headers)

        # 限制 row_limit 上限（默认页面大小作分页基准）
        actual_limit = row_limit if row_limit > 0 else 0
        ps = page_size if row_limit == 0 else min(page_size, (row_limit if actual_limit == 0 else actual_limit))
        if actual_limit > 0 and (ps * (page - 1) >= actual_limit):
            # 超出限制范围，返回空
            data_rows = []
            total = 0
            total_pages = 1
        else:
            # 执行查询（使用 report.py 的 execute_report）
            result = execute_report(
                report_id=report_id,
                sql_query=report["sql_query"],
                pool_config=pool_config,
                page=page,
                page_size=ps,
                sorts=sorts,
                filters=filters,
                refresh=False,
                active_index=0,
                report=report,
            )
            all_cols = result.columns
            all_rows = result.rows

            # 字段选择
            if columns:
                col_list = [c.strip() for c in columns.split(",") if c.strip()]
                display_cols = [c for c in col_list if c in all_cols]
                if not display_cols:
                    display_cols = list(all_cols)
            else:
                display_cols = list(all_cols)

            # 提取显示列的数据
            col_indices = [all_cols.index(c) for c in display_cols]
            data_rows = []
            for row in all_rows:
                data_rows.append({display_cols[i]: row[idx] for i, idx in enumerate(col_indices)})

            total = result.total
            total_pages = result.total_pages

        # 构建响应
        if output_format == "csv":
            status, resp_body, resp_headers = _format_csv_response(
                data_rows, display_cols, pretty
            )
        else:
            status, resp_body, resp_headers = _format_json_response(
                data_rows, total, page, ps, total_pages
            )

        # 添加 CORS 头
        cors_headers = _build_cors_headers(endpoint, headers)
        resp_headers.update(cors_headers)

        _log_api_call(norm_path, client_ip, status, time.time() - start)
        return status, resp_body, resp_headers
    finally:
        conn.close()


def _parse_post_body(body: str, headers: dict) -> dict | None:
    """解析 POST 请求体，支持 JSON 和 form-urlencoded 格式。"""
    if not body:
        return None
    content_type = (headers.get("Content-Type", "") or "").lower()
    if "application/json" in content_type:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None
    else:
        try:
            parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
            return {k: v[-1] if v else "" for k, v in parsed.items()}
        except Exception:
            return None


def _validate_api_key(endpoint: dict, headers: dict, query_params: dict) -> str | None:
    """
    校验 API Key。

    参数:
        endpoint: API 端点配置
        headers: 请求头字典
        query_params: URL 查询参数

    返回:
        None 表示通过，字符串表示错误消息。
    """
    expected_key = endpoint.get("api_key", "")
    if not expected_key:
        return None

    # 从 Authorization 头获取
    auth_header = (headers.get("Authorization", "") or "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if provided == expected_key:
            return None

    # 从查询参数获取
    qp = query_params or {}
    api_key_values = qp.get("api_key", [])
    if api_key_values and api_key_values[0] == expected_key:
        return None

    return "未提供有效的 API Key"


def _build_cors_headers(endpoint: dict, headers: dict) -> dict:
    """
    根据端点配置构建 CORS 响应头。

    允许来源规则：
    - allowed_origins 为空：不设 CORS 头
    - 包含 *：Access-Control-Allow-Origin: *
    - 否则：校验 Origin 头是否在允许列表中
    """
    allowed_raw = endpoint.get("allowed_origins", "") or ""
    if not allowed_raw.strip():
        return {}

    origins = [o.strip() for o in allowed_raw.split(",") if o.strip()]
    if "*" in origins:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        }

    origin = headers.get("Origin", "")
    if origin in origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        }

    return {}


def _resolve_params(endpoint: dict, method: str, body: str,
                    query_params: dict, headers: dict = None) -> tuple:
    """
    解析请求参数：预设规则 + POST 覆盖。

    参数:
        headers: 请求头，用于 POST body 的内容类型判断

    返回:
        (filters, sorts, page, page_size, row_limit, output_format, columns, pretty)
    """
    output_format = endpoint.get("output_format", "json")

    # 解析预设 filters
    preset_filters = []
    filters_raw = endpoint.get("filters", "") or ""
    if filters_raw:
        try:
            preset_filters = json.loads(filters_raw)
        except (json.JSONDecodeError, ValueError):
            preset_filters = []

    # 解析预设 sorts
    preset_sorts = []
    sorts_raw = endpoint.get("sorts", "") or ""
    if sorts_raw:
        try:
            preset_sorts = json.loads(sorts_raw)
        except (json.JSONDecodeError, ValueError):
            preset_sorts = []

    row_limit = int(endpoint.get("row_limit", 0) or 0)
    columns = endpoint.get("columns") or None

    page = 1
    page_size = row_limit if row_limit > 0 else 20

    if method == "POST" and body:
        post_data = _parse_post_body(body, headers or {})
        if post_data:
            if "filters" in post_data and isinstance(post_data["filters"], list):
                preset_filters = post_data["filters"]
            if "sorts" in post_data and isinstance(post_data["sorts"], list):
                preset_sorts = post_data["sorts"]
            if "page" in post_data:
                try:
                    page = int(post_data["page"])
                except (ValueError, TypeError):
                    pass
            if "page_size" in post_data:
                try:
                    page_size = int(post_data["page_size"])
                except (ValueError, TypeError):
                    pass
            if "limit" in post_data:
                try:
                    row_limit = int(post_data["limit"])
                except (ValueError, TypeError):
                    pass
            if "columns" in post_data:
                columns = post_data["columns"]
            if "format" in post_data:
                output_format = post_data["format"]
    else:
        # GET 从 URL 参数读取覆盖
        try:
            page = max(1, int(query_params.get("page", [1])[0]))
        except (ValueError, TypeError, IndexError):
            page = 1
        try:
            page_size = max(1, int(query_params.get("page_size", [page_size])[0]))
        except (ValueError, TypeError, IndexError):
            pass
        if "limit" in query_params:
            try:
                row_limit = int(query_params.get("limit", [0])[0])
            except (ValueError, TypeError):
                pass
        if "format" in query_params:
            f = query_params.get("format", [""])[0]
            if f in ("json", "csv"):
                output_format = f

    if query_params and "columns" in query_params:
        columns = query_params.get("columns", [""])[0] or columns

    pretty = False
    if query_params and "pretty" in query_params:
        pretty = True

    filters = [(f["col"], f.get("op", "contains"), f.get("val", ""))
               for f in preset_filters if "col" in f]

    sorts = [(s["col"], s.get("dir", "asc"))
             for s in preset_sorts if "col" in s]

    return filters, sorts, page, page_size, row_limit, output_format, columns, pretty


def _format_json_response(data_rows: list[dict], total: int, page: int,
                          page_size: int, total_pages: int) -> tuple:
    """
    构建 JSON 响应。

    返回:
        (HTTP 状态码, JSON 字符串, 响应头字典)
    """
    resp = {
        "data": data_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    return 200, json.dumps(resp, ensure_ascii=False, default=str), {
        "Content-Type": "application/json; charset=utf-8",
    }


def _format_csv_response(data_rows: list[dict], columns: list[str],
                         pretty: bool = False) -> tuple:
    """
    构建 CSV 响应。

    参数:
        pretty: 为 True 时添加 UTF-8 BOM

    返回:
        (HTTP 状态码, CSV 字符串, 响应头字典)
    """
    output = io.StringIO()
    if pretty:
        output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in data_rows:
        writer.writerow(row)
    csv_body = output.getvalue()

    headers = {"Content-Type": "text/csv; charset=utf-8"}
    if pretty:
        headers["Content-Type"] = "text/csv; charset=utf-8"
    return 200, csv_body, headers


def _error_response(message: str, code: str, headers: dict) -> str:
    """
    构建错误响应（按 Accept 头决定 JSON 或纯文本）。

    参数:
        message: 错误消息
        code: 错误代码
        headers: 请求头
    """
    accept = (headers.get("Accept", "") or "")
    if "application/json" in accept:
        return json.dumps({"error": message, "code": code}, ensure_ascii=False)
    return message


def _log_api_call(path: str, client_ip: str, status: int,
                  duration: float) -> None:
    """
    记录 API 调用日志。

    格式: [API] 时间 | 路径 | 客户端 IP | HTTP 状态码 | 耗时
    """
    ms = int(duration * 1000)
    logging.info("[API] %s | %s | %s | %sms", path, client_ip, status, ms)
