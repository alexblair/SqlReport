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

import db
from report import execute_report

_CORS_BASE = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
}


def generate_api_key() -> str:
    """生成随机的 API Key（sk- 前缀 + 43 字符随机字符串）。"""
    return "sk-" + secrets.token_urlsafe(32)


def handle_api_request(conn, path: str, method: str, headers: dict,
                       body: str, query_params: dict,
                       client_ip: str = "") -> tuple:
    """
    API 请求入口函数。

    参数:
        conn: 配置数据库连接
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

    norm_path = _normalise_path(path)
    if not norm_path.startswith("/api"):
        return 404, _error_response("接口不存在", "NOT_FOUND", headers), {}

    endpoint = _lookup_endpoint(conn, norm_path)
    if endpoint is None:
        _log_api_call(norm_path, client_ip, 404, time.time() - start)
        return 404, _error_response("接口不存在或已禁用", "NOT_FOUND", headers), {}

    if method == "OPTIONS":
        cors_headers = _build_cors_headers(endpoint, headers)
        _log_api_call(norm_path, client_ip, 204, time.time() - start)
        return 204, "", cors_headers

    auth_error = _validate_api_key(endpoint, headers, query_params)
    if auth_error:
        _log_api_call(norm_path, client_ip, 401, time.time() - start)
        return 401, _error_response(auth_error, "UNAUTHORIZED", headers), {}

    result = _execute_api_query(conn, endpoint, method, body, query_params, headers)
    if isinstance(result[0], int):
        _log_api_call(norm_path, client_ip, result[0], time.time() - start)
        return result

    data_rows, display_cols, total, page, ps, total_pages, output_format, add_bom = result

    cors_headers = _build_cors_headers(endpoint, headers)
    status, resp_body, resp_headers = _format_output(
        data_rows, display_cols, total, page, ps, total_pages, output_format, add_bom
    )
    resp_headers.update(cors_headers)

    _log_api_call(norm_path, client_ip, status, time.time() - start)
    return status, resp_body, resp_headers


def _normalise_path(path: str) -> str:
    """规范化请求路径，确保以 / 开头。"""
    return "/" + path.lstrip("/")


def _lookup_endpoint(conn, norm_path: str) -> dict | None:
    """从数据库查找匹配的 API 端点。"""
    return db.get_api_endpoint_by_path(conn, norm_path)


def _execute_api_query(conn, endpoint: dict, method: str, body: str,
                       query_params: dict, headers: dict) -> tuple:
    """
    执行 API 查询：加载报表/连接池 + 解析参数 + 执行 SQL。

    返回 (data_rows, display_cols, total, page, ps, total_pages, output_format, pretty)
    或在出错时返回 (HTTP状态码, 错误响应体, 响应头字典)。
    """
    report_id = endpoint["report_id"]
    report = db.get_report(conn, report_id)
    if report is None:
        return 500, _error_response("关联报表不存在", "INTERNAL_ERROR", headers), {}

    pool_id = report.get("pool_id")
    if pool_id is None:
        return 500, _error_response("报表未配置连接池", "INTERNAL_ERROR", headers), {}
    pool_config = db.get_pool(conn, pool_id)
    if pool_config is None:
        return 500, _error_response("连接池配置不存在", "INTERNAL_ERROR", headers), {}

    filters, sorts, page, page_size, row_limit, output_format, columns, add_bom = \
        _resolve_params(endpoint, method, body, query_params, headers)

    ps = page_size if row_limit == 0 else min(page_size, row_limit)
    if row_limit > 0 and ps * (page - 1) >= row_limit:
        return [], [], 0, page, ps, 1, output_format, add_bom

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
    display_cols = _resolve_display_cols(all_cols, columns)
    col_indices = [all_cols.index(c) for c in display_cols]
    data_rows = [{display_cols[i]: row[idx] for i, idx in enumerate(col_indices)} for row in all_rows]

    return data_rows, display_cols, result.total, page, ps, result.total_pages, output_format, add_bom


def _resolve_display_cols(all_cols: list, columns: str | None) -> list:
    """根据 columns 参数解析显示列列表。"""
    if not columns:
        return list(all_cols)
    col_list = [c.strip() for c in columns.split(",") if c.strip()]
    display = [c for c in col_list if c in all_cols]
    return display if display else list(all_cols)


def _format_output(data_rows, display_cols, total, page, ps,
                   total_pages, output_format, add_bom) -> tuple:
    """根据 output_format 构建最终响应。"""
    if output_format == "csv":
        return _format_csv_response(data_rows, display_cols, add_bom)
    return _format_json_response(data_rows, total, page, ps, total_pages)


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
        return {**_CORS_BASE, "Access-Control-Allow-Origin": "*"}

    origin = headers.get("Origin", "")
    if origin in origins:
        return {**_CORS_BASE, "Access-Control-Allow-Origin": origin}

    return {}


def _parse_json_field(raw: str) -> list:
    """尝试解析 JSON 字符串为列表，失败返回空列表。"""
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _parse_preset_rules(endpoint: dict) -> tuple:
    """
    从端点配置解析预设规则。

    返回:
        (preset_filters, preset_sorts, row_limit, columns, output_format)
    """
    filters_raw = endpoint.get("filters", "") or ""
    sorts_raw = endpoint.get("sorts", "") or ""
    return (
        _parse_json_field(filters_raw),
        _parse_json_field(sorts_raw),
        int(endpoint.get("row_limit", 0) or 0),
        endpoint.get("columns") or None,
        endpoint.get("output_format", "json"),
    )


def _apply_post_overrides(post_data: dict,
                          preset_filters: list, preset_sorts: list,
                          page: int, page_size: int,
                          row_limit: int, columns: str | None,
                          output_format: str) -> tuple:
    """应用 POST 请求体中的覆盖参数。"""
    if isinstance(post_data.get("filters"), list):
        preset_filters = post_data["filters"]
    if isinstance(post_data.get("sorts"), list):
        preset_sorts = post_data["sorts"]
    page = _safe_int(post_data.get("page"), page)
    page_size = _safe_int(post_data.get("page_size"), page_size)
    row_limit = _safe_int(post_data.get("limit"), row_limit)
    columns = post_data.get("columns", columns)
    output_format = post_data.get("format", output_format)
    return preset_filters, preset_sorts, page, page_size, row_limit, columns, output_format


def _apply_get_overrides(query_params: dict,
                         page: int, page_size: int,
                         row_limit: int, columns: str | None,
                         output_format: str) -> tuple:
    """应用 GET URL 参数中的覆盖参数。"""
    page = max(1, _safe_int(query_params.get("page", [page])[0], page))
    qs_page_size = query_params.get("page_size", [page_size])[0]
    page_size = max(1, _safe_int(qs_page_size, page_size))
    row_limit = _safe_int(query_params.get("limit", [row_limit])[0], row_limit)
    fmt = query_params.get("format", [""])[0]
    if fmt in ("json", "csv"):
        output_format = fmt
    columns = query_params.get("columns", [columns])[0] or columns
    return page, page_size, row_limit, columns, output_format


def _safe_int(val, default: int) -> int:
    """安全转换为 int，失败返回默认值。"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _resolve_params(endpoint: dict, method: str, body: str,
                    query_params: dict, headers: dict = None) -> tuple:
    """
    解析请求参数：预设规则 + POST/GET 覆盖。

    返回:
        (filters, sorts, page, page_size, row_limit, output_format, columns, add_bom)
    """
    preset_filters, preset_sorts, row_limit, columns, output_format = \
        _parse_preset_rules(endpoint)

    page = 1
    page_size = row_limit if row_limit > 0 else 20

    if method == "POST" and body:
        post_data = _parse_post_body(body, headers or {})
        if post_data:
            preset_filters, preset_sorts, page, page_size, row_limit, columns, output_format = \
                _apply_post_overrides(post_data, preset_filters, preset_sorts,
                                       page, page_size, row_limit, columns, output_format)
    elif query_params:
        page, page_size, row_limit, columns, output_format = \
            _apply_get_overrides(query_params, page, page_size, row_limit, columns, output_format)

    add_bom = bool(query_params and "pretty" in query_params)

    filters = [(f["col"], f.get("op", "contains"), f.get("val", ""))
               for f in preset_filters if "col" in f]
    sorts = [(s["col"], s.get("dir", "asc"))
             for s in preset_sorts if "col" in s]

    return filters, sorts, page, page_size, row_limit, output_format, columns, add_bom


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
                         add_bom: bool = False) -> tuple:
    """
    构建 CSV 响应。

    参数:
        add_bom: 为 True 时添加 UTF-8 BOM

    返回:
        (HTTP 状态码, CSV 字符串, 响应头字典)
    """
    output = io.StringIO()
    if add_bom:
        output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in data_rows:
        writer.writerow(row)
    csv_body = output.getvalue()
    return 200, csv_body, {"Content-Type": "text/csv; charset=utf-8"}


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
