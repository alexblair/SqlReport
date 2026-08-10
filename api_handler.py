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
import os
import time
import logging
import secrets
import hmac

import db
import app_config
import auth
from report import execute_report, parse_result_names, WRITE_DENIED_MESSAGE
from query_executor import sql_contains_write
import static_cache
from json_template import is_template_enabled, render_template
from result_transform import select_columns, column_indices, calc_total_pages
from redis_cache import _md5_hex
from export import rows_to_csv

_CORS_BASE = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
}

# fetch_all 全量获取时的内部页大小：足够大以避免内存分页切片，实际行数以 total 为准
_FETCH_ALL_PAGE_SIZE = 10 ** 9

# fetch_all 参数合法值（大小写不敏感），复用公共真值常量
_FETCH_ALL_VALUES = app_config.TRUTHY_VALUES


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

    静态缓存（.json 变体）：
    - 仅 GET 且路径以 .json 结尾（大小写不敏感）时解析静态目标
    - 原路径未命中端点时剥离 .json 后缀再查（防端点 URL 本身以 .json 结尾被误伤）
    - 端点存在且 output_format=json 且全局启用时才进入静态分支，否则回退普通链路
    - 鉴权在静态分支之前统一执行，与普通请求完全一致
    """
    start = time.time()

    norm_path = _normalise_path(path)
    # 校验 /api 前缀（兼容无斜杠的 "/api" 形态，保持历史行为）
    if not (norm_path == app_config.API_PREFIX[:-1]
            or norm_path.startswith(app_config.API_PREFIX)):
        body, err_headers = _error_response("接口不存在", "NOT_FOUND", headers)
        return 404, body, err_headers

    # 静态缓存目标解析（仅 GET 触发）：原路径未命中且以 .json 结尾时，
    # 剥离后缀再查一次（防端点 URL 本身以 .json 结尾被误伤）
    endpoint = _lookup_endpoint(conn, norm_path)
    static_base = None
    if endpoint is None and method == "GET":
        static_base = _static_base_path(norm_path)
        if static_base is not None:
            endpoint = _lookup_endpoint(conn, static_base)
            if endpoint is not None:
                norm_path = static_base

    if endpoint is None:
        _log_api_call(norm_path, client_ip, 404, time.time() - start)
        body, err_headers = _error_response("接口不存在或已禁用", "NOT_FOUND", headers)
        return 404, body, err_headers

    if method == "OPTIONS":
        cors_headers = _build_cors_headers(endpoint, headers)
        _log_api_call(norm_path, client_ip, 204, time.time() - start)
        return 204, "", cors_headers

    auth_error = _validate_api_key(conn, endpoint, headers, query_params)
    if auth_error:
        _log_api_call(norm_path, client_ip, 401, time.time() - start)
        body, err_headers = _error_response(auth_error, "UNAUTHORIZED", headers)
        return 401, body, err_headers

    # 非法 JSON 请求体：Content-Type=application/json 且解析失败 → 400 拒绝
    # （解析失败与"未传 body"区分：空 body 回退预设，不视为解析失败）
    if method == "POST" and _is_invalid_json_body(body, headers):
        body, err_headers = _error_response("请求体 JSON 解析失败", "INVALID_JSON", headers)
        return 400, body, err_headers

    # 静态缓存分支：鉴权之后、执行查询之前
    # 仅 JSON 格式端点 + 端点开关开启 + 全局开关启用时进入，否则回退普通 API 链路
    if static_base is not None \
            and endpoint.get("output_format", "json") == "json" \
            and int(endpoint.get("static_cache", 1)) == 1 \
            and static_cache.get_static_cache_config().get("enable", True):
        status, resp_body, resp_headers = _handle_static_request(
            conn, endpoint, static_base, method, body, query_params, headers)
        _log_api_call(norm_path, client_ip, status, time.time() - start)
        return status, resp_body, resp_headers

    result = _run_normal_api_request(conn, endpoint, method, body, query_params, headers)
    _log_api_call(norm_path, client_ip, result[0], time.time() - start)
    return result


def _normalise_path(path: str) -> str:
    """规范化请求路径，确保以 / 开头。"""
    return "/" + path.lstrip("/")


def _endpoint_template(endpoint: dict) -> str:
    """返回端点的 JSON 输出模板（未配置时为空串）。"""
    return endpoint.get("json_template") or ""


def _lookup_endpoint(conn, norm_path: str) -> dict | None:
    """从数据库查找匹配的 API 端点。"""
    return db.get_api_endpoint_by_path(conn, norm_path)


def _static_base_path(norm_path: str) -> str | None:
    """路径以 .json 结尾（大小写不敏感）时返回剥离后缀的路径，否则返回 None。"""
    if not norm_path.lower().endswith(static_cache.JSON_SUFFIX):
        return None
    return static_cache.strip_json_suffix(norm_path)


def _rows_to_dicts(rows, display_cols, col_indices) -> list:
    """将行元组列表按列索引映射为 [{列名: 值}] 字典列表。

    值保持原始类型（含 Decimal）：「智能去引号」在序列化阶段统一处理
    （serialize_smart_quotes），本函数不在此处做任何转换。
    """
    return [{display_cols[i]: row[idx] for i, idx in enumerate(col_indices)}
            for row in rows]


def _run_normal_api_request(conn, endpoint: dict, method: str, body: str,
                            query_params: dict, headers: dict) -> tuple:
    """执行普通 API 链路（查询 + 格式化 + CORS），静态分支回退共用。"""
    template = _endpoint_template(endpoint)
    result = _execute_api_query(conn, endpoint, method, body, query_params, headers)
    if isinstance(result, tuple):
        return result
    status, resp_body, resp_headers = _format_output(
        result.data_rows, result.display_cols, result.total,
        result.page, result.page_size, result.total_pages,
        result.output_format, result.add_bom, result.full, template=template,
        truncated=result.truncated,
        smart_quote_flags=result.smart_quote_flags)
    resp_headers.update(_build_cors_headers(endpoint, headers))
    return status, resp_body, resp_headers


def _handle_static_request(conn, endpoint: dict, base_path: str,
                           method: str, body: str, query_params: dict,
                           headers: dict) -> tuple:
    """
    处理静态缓存请求（.json 变体，已通过鉴权，端点 output_format=json 且全局启用）。

    命中：直接返回文件内容，X-Static-Cache: hit。
    miss：以全量语义执行完整计算链路（Redis 快照 → 锁 → MySQL 兜底），
          200 成功后把"全量 + meta"输出原子写入文件；非 200 不落盘。
    文件 IO / 配置异常静默降级：回退普通 API 链路。
    """
    url_key = base_path.lstrip("/")
    file_path = static_cache.resolve_file_path(url_key)
    if file_path is None:
        # 路径穿越（..）被拒：回退普通 API 链路
        logging.warning("static_cache 路径穿越被拒绝: %s", base_path)
        return _run_normal_api_request(conn, endpoint, method, body, query_params, headers)

    report = db.get_report(conn, endpoint["report_id"])
    if report is None or report.get("pool_id") is None:
        return _run_normal_api_request(conn, endpoint, method, body, query_params, headers)

    # PH-05 写护栏：allow_write=0 且 SQL 含写 → 回退普通链路（execute_report 统一 403），
    # 防止历史静态缓存文件绕过护栏直出（普通 API 与 .json 变体行为必须一致）
    if not int(report.get("allow_write", 1) or 0) \
            and sql_contains_write(report.get("sql_query") or ""):
        return _run_normal_api_request(conn, endpoint, method, body, query_params, headers)

    ttl_hours = int(report.get("cache_ttl_hours", 0) or 0)
    config_version = _compute_static_config_version(endpoint, report)

    content = static_cache.try_read(file_path, config_version, ttl_hours)
    if content is not None:
        resp_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Static-Cache": "hit",
        }
        resp_headers.update(_build_cors_headers(endpoint, headers))
        return 200, content, resp_headers

    return _execute_static_miss(
        conn, endpoint, url_key, file_path, ttl_hours, config_version, headers)


def _compute_static_config_version(endpoint: dict, report: dict) -> str:
    """计算静态缓存配置版本（MD5 of sql + pool_id + 端点变换配置 + 截断策略）。

    静态文件内容是"SQL 结果 + 端点变换规则（字段/筛选/排序/条数/结果集选择/模板）"
    的产物，任一变化都会改变文件内容，必须纳入版本计算；否则编辑端点配置后
    旧文件在 TTL 内持续命中（缓存陈旧）。
    PH-07：allow_all_output/max_rows 决定结果是否截断，同样影响文件内容
    （截断是文件生成时固化的事实），纳入版本计算保证开关切换后自动失效重建。
    """
    parts = [report["sql_query"], str(report.get("pool_id") or "")]
    for key in ("columns", "filters", "sorts", "row_limit", "json_template",
                "result_mode", "result_index"):
        value = endpoint.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    # 「智能去引号」有效位：旧列 json_no_quotes=1（迁移 15 前存量，极端防御）
    # 等价面板全开（0b111），与 smart_quote_flags 取大值后纳入版本计算——
    # 两者任一变化都会改变文件内容，必须参与版本判定（防 TTL 内陈旧命中）。
    flags = int(endpoint.get("smart_quote_flags", 0) or 0)
    if int(endpoint.get("json_no_quotes", 0) or 0):
        flags = max(flags, 7)
    parts.append(f"smart_quote_flags={flags}")
    parts.append(f"allow_all_output={int(report.get('allow_all_output', 1) or 0)}")
    parts.append(f"max_rows={int(report.get('max_rows') or 0)}")
    return _md5_hex("|".join(parts))


def _execute_static_miss(conn, endpoint: dict, url_key: str, file_path: str,
                         ttl_hours: int, config_version: str,
                         headers: dict) -> tuple:
    """miss 链路：失效记录 → 全量计算 → 200 成功原子落盘（非 200 不落盘）。

    last_invalidated_at 语义（该缓存路径"上次被判定失效"的时刻）：
    - 文件存在但版本不匹配/过期 → 本次即一次失效事件，记录本次时刻
    - 文件缺失（首次/第三方删除）→ 本次没有文件被判定失效，沿用历史记录（无则 null）
    """
    if os.path.exists(file_path):
        static_cache.record_invalidated(url_key)
    last_invalidated = static_cache.get_last_invalidated(url_key)
    template = _endpoint_template(endpoint)
    # smart_quote_flags 的旧列兼容归一化在 _execute_api_query 内完成
    # （json_no_quotes=1 极端防御等价面板全开）
    meta = _build_static_meta(ttl_hours, url_key, config_version, last_invalidated)
    result = _execute_api_query(conn, endpoint, "GET", "", {}, headers,
                                force_full=True, meta=meta)
    if isinstance(result, tuple):
        if result[0] != 200:
            # 非 200 不落盘
            status, resp_body, resp_headers = result[0], result[1], dict(result[2])
        else:
            # result_mode=all 成功：直接返回 (200, JSON 串, 响应头)
            status, resp_body, resp_headers = 200, result[1], dict(result[2])
    else:
        status, resp_body, resp_headers = _format_output(
            result.data_rows, result.display_cols, result.total,
            result.page, result.page_size, result.total_pages,
            result.output_format, result.add_bom, result.full,
            template=template, meta=meta, truncated=result.truncated,
            smart_quote_flags=result.smart_quote_flags)

    if status == 200:
        # 默认结构与模板：meta 均已在序列化前注入（模板内嵌 {{meta}}，
        # 默认结构由 _format_json_response / all 分支在构造 resp 时注入；
        # 模板不含 {{meta}} 占位符则自然不带 meta）
        file_content = resp_body
        # 写入方式选择：内容可解析且含对象 meta → 稳定文件 + 内容判定；
        # 否则（模板无 meta）→ 版本化文件双写（版本嵌入文件名，try_read
        # 靠版本路径判定，不依赖内容解析）
        has_object_meta = static_cache.content_has_object_meta(file_content)
        if has_object_meta:
            written = static_cache.write_file(file_path, file_content)
        else:
            written = static_cache.write_versioned_file(
                file_path, config_version[:8], file_content)
        if written:
            resp_body = file_content

    resp_headers = dict(resp_headers)
    resp_headers["X-Static-Cache"] = "miss"
    resp_headers.update(_build_cors_headers(endpoint, headers))
    return status, resp_body, resp_headers


def _build_static_meta(ttl_hours: int, url_key: str, config_version: str,
                       last_invalidated: float | None) -> dict:
    """构建静态文件 meta 节点（服务器本地时区，秒级精度）。

    last_invalidated_at 为该缓存路径"上次被判定失效"的时刻：
    - 本次重建因文件失效（版本不匹配/过期）触发 → 本次失效时刻
    - 本次重建因文件缺失（首次/第三方删除）触发 → 历史记录；无记录时为 null
    """
    now = time.time()
    return {
        "generated_at": _format_local_time(now),
        "expires_at": _format_local_time(now + ttl_hours * 3600) if ttl_hours > 0 else None,
        "last_invalidated_at": _format_local_time(last_invalidated) if last_invalidated else None,
        "config_version": config_version,
    }


def _format_local_time(ts: float) -> str:
    """格式化为服务器本地时区时间（秒级精度），如 2026-08-04 18:30:22 +0800。"""
    return app_config.format_local_time(ts)


def _get_result_name(report, result_index: int, result_obj) -> str:
    """获取结果集的显示名称，优先使用 result_names，否则自动命名。"""
    result_names_raw = (report.get("result_names") or "").strip()
    if result_names_raw:
        names = parse_result_names(result_names_raw)
        if result_index < len(names):
            return names[result_index]
    cols = result_obj.results[result_index]["columns"]
    preview = ", ".join(cols[:3])
    suffix = "..." if len(cols) > 3 else ""
    return f"结果{result_index + 1} ({preview}{suffix})"


def _execute_api_query(conn, endpoint: dict, method: str, body: str,
                       query_params: dict, headers: dict,
                       force_full: bool = False, meta: dict | None = None) -> tuple:
    """
    执行 API 查询：加载报表/连接池 + 解析参数 + 执行 SQL。

    force_full: 强制全量语义（静态缓存文件的固有语义，与 allow_fetch_all 开关
                及请求参数无关），无视分页与行数限制。
    meta: 静态缓存链路的 meta 节点（模板启用时进入模板上下文；普通链路为 None）。

    成功路径（单结果集模式）返回 ApiQueryResult 具名结构；
    错误或 result_mode=all 成功时返回 (HTTP状态码, 响应体, 响应头字典)。
    """
    report_id = endpoint["report_id"]
    report = db.get_report(conn, report_id)
    if report is None:
        body, err_headers = _error_response("关联报表不存在", "INTERNAL_ERROR", headers)
        return 500, body, err_headers

    pool_id = report.get("pool_id")
    if pool_id is None:
        body, err_headers = _error_response("报表未配置连接池", "INTERNAL_ERROR", headers)
        return 500, body, err_headers
    pool_config = db.get_pool(conn, pool_id)
    if pool_config is None:
        body, err_headers = _error_response("连接池配置不存在", "INTERNAL_ERROR", headers)
        return 500, body, err_headers

    filters, sorts, page, page_size, row_limit, output_format, columns, add_bom, fetch_all = \
        _resolve_params(endpoint, method, body, query_params, headers)

    # 端点「智能去引号」位图：1=十进制数字（含正负号）、2=科学计数法、
    # 4=千分位数字，默认 0 = 标准 JSON（与报表导出共用
    # app_config.serialize_smart_quotes 单一实现）。
    # 旧列 json_no_quotes 兼容：存量数据转换已由迁移 15 承载（=1 → 面板全开
    # 0b111）；此分支为极端防御——未迁移/直接落库数据 json_no_quotes=1 时
    # 等价面板全开（取大值），保证既有端点与调用方不失效。
    smart_quote_flags = int(endpoint.get("smart_quote_flags", 0) or 0)
    if int(endpoint.get("json_no_quotes", 0) or 0):
        smart_quote_flags = max(smart_quote_flags, 7)

    # API 强制刷新：refresh=1（严格值校验）→ 绕过 L1/L2 缓存直查 MySQL 并回写缓存
    refresh = _resolve_flag(query_params, method, body, headers, "refresh")

    ps = page_size if row_limit == 0 else min(page_size, row_limit)
    if fetch_all or force_full:
        # 全量获取：无视分页与行数限制（静态缓存的全量是文件固有语义，与 allow_fetch_all 开关无关）
        fetch_all = True
        page = 1
        ps = _FETCH_ALL_PAGE_SIZE
    elif row_limit > 0 and ps * (page - 1) >= row_limit:
        return ApiQueryResult(
            [], [], 0, page, ps, 1, output_format, add_bom, False,
            smart_quote_flags=smart_quote_flags)

    result_mode = endpoint.get("result_mode", "single")
    result_index = int(endpoint.get("result_index", 0))
    active_index = -1 if result_mode == "all" else result_index

    try:
        result = execute_report(
            report_id=report_id,
            sql_query=report["sql_query"],
            pool_config=pool_config,
            page=page,
            page_size=ps,
            sorts=sorts,
            filters=filters,
            refresh=refresh,
            active_index=active_index,
            report=report,
        )
    except PermissionError as e:
        # PH-05 写护栏：写语句报表未开启 allow_write → 403 结构化错误
        body, err_headers = _error_response(str(e), "WRITE_DENIED", headers)
        return 403, body, err_headers

    # 全部输出模式
    if result_mode == "all":
        if output_format == "csv":
            return 400, json.dumps({
                "error": "CSV 格式不支持全部结果集输出，请使用 JSON 格式或改为单结果集模式",
                "code": "CSV_NOT_SUPPORTED",
            }, ensure_ascii=False), {"Content-Type": "application/json; charset=utf-8"}

        results_list = []
        total_all_rows = 0
        for i, res in enumerate(result.results):
            disp_cols = select_columns(res["columns"], columns)
            col_indices_local = column_indices(disp_cols, res["columns"])
            data_rows = _rows_to_dicts(res["rows"], disp_cols, col_indices_local)
            total = res["total"]
            total_all_rows += total
            total_pages = calc_total_pages(total, ps)
            item = {
                "name": _get_result_name(report, i, result),
                "data": data_rows,
                "total": total,
                "page": page,
                "page_size": total if fetch_all else ps,
                "total_pages": total_pages,
            }
            if fetch_all:
                item["full"] = True
            results_list.append(item)

        template = _endpoint_template(endpoint)
        if is_template_enabled(template):
            context = _build_all_context(
                results_list, page,
                total_all_rows if fetch_all else ps, fetch_all, meta)
            rendered = _apply_json_template(
                template, context, smart_quote_flags=smart_quote_flags)
            if rendered is not None:
                return 200, rendered, {"Content-Type": "application/json; charset=utf-8"}

        resp_body = _serialize_api_payload({
            "results": results_list,
            "mode": "all",
            "page": page,
            "page_size": total_all_rows if fetch_all else ps,
        } | ({"full": True} if fetch_all else {})
          | ({"truncated": True} if result.truncated else {})
          | ({"meta": meta} if meta is not None else {}),
            smart_quote_flags=smart_quote_flags)
        return 200, resp_body, {"Content-Type": "application/json; charset=utf-8"}

    # 单结果集模式 — 校验索引
    if result_index >= len(result.results):
        body, err_headers = _error_response(
            f"结果集索引 {result_index} 超出范围，该查询仅返回 {len(result.results)} 个结果集",
            "INVALID_RESULT_INDEX", headers
        )
        return 400, body, err_headers

    all_cols = result.columns
    all_rows = result.rows
    display_cols = select_columns(all_cols, columns)
    col_indices = column_indices(display_cols, all_cols)
    data_rows = _rows_to_dicts(all_rows, display_cols, col_indices)

    display_ps = result.total if fetch_all else ps
    return ApiQueryResult(
        data_rows, display_cols, result.total, page, display_ps,
        result.total_pages, output_format, add_bom, fetch_all,
        truncated=bool(result.truncated),
        smart_quote_flags=smart_quote_flags)


class ApiQueryResult:
    """API 查询结果的具名结构（单结果集成功路径，替代 9 字段位置元组）。

    错误路径与 result_mode=all 的成功路径仍返回 (状态码, 响应体, 响应头) 元组，
    调用方通过 isinstance(result, tuple) 区分。
    """

    __slots__ = ("data_rows", "display_cols", "total", "page", "page_size",
                 "total_pages", "output_format", "add_bom", "full",
                 "truncated", "smart_quote_flags")

    def __init__(self, data_rows, display_cols, total, page, page_size,
                 total_pages, output_format, add_bom, full,
                 truncated: bool = False, smart_quote_flags: int = 0):
        self.data_rows = data_rows
        self.display_cols = display_cols
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = total_pages
        self.output_format = output_format
        self.add_bom = add_bom
        self.full = full
        self.truncated = truncated
        self.smart_quote_flags = smart_quote_flags


def _format_output(data_rows, display_cols, total, page, ps,
                   total_pages, output_format, add_bom, full: bool,
                   template: str = "", meta: dict | None = None,
                   truncated: bool = False,
                   smart_quote_flags: int = 0) -> tuple:
    """根据 output_format 构建最终响应（JSON 支持自定义输出模板）。"""
    if output_format == "csv":
        return _format_csv_response(data_rows, display_cols, add_bom)
    return _format_json_response(data_rows, total, page, ps, total_pages, full,
                                 template=template, meta=meta,
                                 truncated=truncated,
                                 smart_quote_flags=smart_quote_flags)


def _build_single_context(data_rows, total, page, ps, total_pages, full,
                          meta: dict | None) -> dict:
    """构建单结果集模式的模板上下文（模板键集 SINGLE_KEYS）。"""
    return {
        "data": data_rows,
        "total": total,
        "page": page,
        "page_size": ps,
        "total_pages": total_pages,
        "full": full,
        "meta": meta,
    }


def _build_all_context(results_list, page, ps, full,
                       meta: dict | None) -> dict:
    """构建全部输出模式的模板上下文（模板键集 ALL_KEYS，mode 恒为 "all"）。"""
    return {
        "results": results_list,
        "mode": "all",
        "page": page,
        "page_size": ps,
        "full": full,
        "meta": meta,
    }


def _apply_json_template(template: str, context: dict,
                         smart_quote_flags: int = 0) -> str | None:
    """渲染 JSON 输出模板；失败时记录警告并返回 None（调用方回退默认结构）。

    smart_quote_flags>0（智能模式）时渲染结果合法性校验恒执行（输出永远
    合法 JSON）。
    """
    ok, output, error = render_template(
        template, context, smart_quote_flags=smart_quote_flags)
    if not ok:
        logging.warning("API JSON 输出模板渲染失败，回退默认结构: %s", error)
        return None
    return output


def _serialize_api_payload(obj: dict, smart_quote_flags: int = 0) -> str:
    """序列化 API JSON 响应体。

    smart_quote_flags>0（「智能去引号」位图：1=十进制数字、2=科学计数法、
    4=千分位数字）时字符串值按勾选形态判定裸输出（app_config.
    serialize_smart_quotes，与报表导出共用单一实现，输出永远合法 JSON）；
    未勾选形态的值保持带引号，原生数字恒按标准 JSON。
    均关闭（flags=0）时沿用全项目序列化约定（ensure_ascii=False、default=str）。
    """
    if smart_quote_flags > 0:
        return app_config.serialize_smart_quotes(obj, smart_quote_flags)
    return app_config.serialize_json(obj)


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
            return app_config.parse_form_urlencoded(body)
        except Exception:
            return None


def _is_invalid_json_body(body: str, headers: dict) -> bool:
    """Content-Type=application/json 且 body 非空但 JSON 解析失败 → 非法。

    空 body（无请求体）不视为解析失败，回退端点预设规则。
    """
    if not body:
        return False
    content_type = (headers.get("Content-Type", "") or "").lower()
    if "application/json" not in content_type:
        return False
    try:
        json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return True
    return False


def _validate_api_key(conn, endpoint: dict, headers: dict, query_params: dict) -> str | None:
    """
    校验 API Key。

    优先按 endpoint_id 查 api_keys 表（enabled=1 且 key 匹配，常数时间比对）；
    api_keys 表无记录（旧库未迁移）时回退 endpoint.api_key 兼容旧数据。
    端点无任何 key 配置（表空 + 旧列空）→ 公开，直接通过。
    表内有记录但全部禁用 → 拒绝一切请求。

    参数:
        conn: 配置数据库连接
        endpoint: API 端点配置
        headers: 请求头字典
        query_params: URL 查询参数

    返回:
        None 表示通过，字符串表示错误消息。
    """
    keys, has_records = _endpoint_valid_keys(conn, endpoint)
    if not keys and not has_records:
        return None

    # 从 Authorization 头获取，未带则从查询参数获取
    auth_header = (headers.get("Authorization", "") or "")
    provided = auth.extract_bearer_token(auth_header)
    if provided is None:
        qp = query_params or {}
        api_key_values = qp.get("api_key", [])
        provided = api_key_values[0] if api_key_values else None
    if provided is None:
        return "未提供有效的 API Key"

    for expected in keys:
        if hmac.compare_digest(provided, expected):
            return None
    return "未提供有效的 API Key"


def _endpoint_valid_keys(conn, endpoint: dict) -> tuple[list[str], bool]:
    """返回 (有效 key 列表, 表内是否有记录)。

    表内 enabled=1 的记录优先；表内无记录（旧库未迁移）时回退
    endpoint.api_key 旧列；表内有记录但全部禁用 → (空列表, True)，
    调用方据此拒绝一切请求（区别于"公开端点"）。
    """
    rows = conn.execute(
        "SELECT api_key FROM api_keys WHERE endpoint_id=? AND enabled=1",
        (endpoint["id"],),
    ).fetchall()
    keys = [r[0] for r in rows if r[0]]
    if keys:
        return keys, True
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM api_keys WHERE endpoint_id=?",
        (endpoint["id"],),
    ).fetchone()
    if row and row[0] > 0:
        return [], True
    old = endpoint.get("api_key", "") or ""
    return ([old] if old else []), False


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
    return app_config.safe_int(val, default)


def _filter_val_str(val) -> str:
    """筛选值归一化为字符串（None → 空串，数字/布尔等 → str）。

    filter_rows 入口另有 str 防御（result_transform.parse_filter_expr），
    此处归一化保证下游 filters 元组的 val 恒为 str（契约一致性）。
    """
    if val is None:
        return ""
    return str(val)


def _resolve_flag(query_params: dict, method: str, body: str,
                  headers: dict = None, name: str = "fetch_all") -> bool:
    """
    解析布尔型请求参数（fetch_all/refresh 共用）。

    GET 从 query string 提取，POST 从请求体（JSON/form-urlencoded）提取。
    严格值校验：true/1/yes（大小写不敏感），其他值视为未传递。
    """
    raw = None
    if method == "POST" and body:
        post_data = _parse_post_body(body, headers or {})
        if post_data:
            raw = post_data.get(name)
    elif query_params:
        qp = query_params.get(name, [""])
        raw = qp[0] if qp else ""
    if raw is None:
        return False
    return str(raw).strip().lower() in _FETCH_ALL_VALUES


def _resolve_fetch_all(endpoint: dict, method: str, body: str,
                       query_params: dict, headers: dict = None) -> bool:
    """
    解析 fetch_all 全量获取参数。

    端点配置 allow_fetch_all 关闭时参数被忽略，返回 False。
    """
    if not int(endpoint.get("allow_fetch_all", 1) or 0):
        return False
    return _resolve_flag(query_params, method, body, headers, "fetch_all")


def _resolve_params(endpoint: dict, method: str, body: str,
                    query_params: dict, headers: dict = None) -> tuple:
    """
    解析请求参数：预设规则 + POST/GET 覆盖。

    返回:
        (filters, sorts, page, page_size, row_limit, output_format, columns, add_bom, fetch_all)
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
    fetch_all = _resolve_fetch_all(endpoint, method, body, query_params, headers)

    filters = [(f["col"], f.get("op", "contains"), _filter_val_str(f.get("val")))
               for f in preset_filters if "col" in f]
    sorts = [(s["col"], s.get("dir", "asc"))
             for s in preset_sorts if "col" in s]

    return filters, sorts, page, page_size, row_limit, output_format, columns, add_bom, fetch_all


def _format_json_response(data_rows: list[dict], total: int, page: int,
                          page_size: int, total_pages: int,
                          full: bool = False, template: str = "",
                          meta: dict | None = None,
                          truncated: bool = False,
                          smart_quote_flags: int = 0) -> tuple:
    """
    构建 JSON 响应。

    truncated: 本次查询结果是否发生 max_rows 截断（True 时响应体附加
               "truncated": true，缺省 False 不出现，不破坏现有响应契约）。
    smart_quote_flags: 端点「智能去引号」位图（1=十进制数字、2=科学计数法、
                       4=千分位数字），>0 时字符串值按勾选形态判定裸输出，
                       默认 0 = 标准 JSON。

    返回:
        (HTTP 状态码, JSON 字符串, 响应头字典)
    """
    if is_template_enabled(template):
        context = _build_single_context(
            data_rows, total, page, page_size, total_pages, full, meta)
        rendered = _apply_json_template(
            template, context, smart_quote_flags=smart_quote_flags)
        if rendered is not None:
            return 200, rendered, {
                "Content-Type": "application/json; charset=utf-8",
            }

    resp = {
        "data": data_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    if truncated:
        resp["truncated"] = True
    if full:
        resp["full"] = True
    if meta is not None:
        resp["meta"] = meta
    return 200, _serialize_api_payload(
        resp, smart_quote_flags=smart_quote_flags), {
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
    # DictWriter 语义（QUOTE_MINIMAL + CRLF 行尾 + BOM 可选）经 rows_to_csv
    # 参数化保持逐字节一致：按 header 顺序取值，忽略行内多余键（extrasaction='ignore'）
    rows_out = [[row.get(c, "") for c in columns] for row in data_rows]
    csv_body = rows_to_csv(columns, rows_out, bom=add_bom,
                           quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    return 200, csv_body, {"Content-Type": "text/csv; charset=utf-8"}


def _error_response(message: str, code: str, headers: dict) -> tuple:
    """
    构建错误响应（按 Accept 头决定 JSON 或纯文本）。

    返回 (响应体字符串, 响应头字典)；响应头携带与 body 一致的 Content-Type：
    - Accept 含 application/json → application/json; charset=utf-8
    - 否则 → text/plain; charset=utf-8

    参数:
        message: 错误消息
        code: 错误代码
        headers: 请求头
    """
    accept = (headers.get("Accept", "") or "")
    if "application/json" in accept:
        body = json.dumps({"error": message, "code": code}, ensure_ascii=False)
        return body, {"Content-Type": "application/json; charset=utf-8"}
    return message, {"Content-Type": "text/plain; charset=utf-8"}


def _log_api_call(path: str, client_ip: str, status: int,
                  duration: float) -> None:
    """
    记录 API 调用日志。

    格式: [API] 时间 | 路径 | 客户端 IP | HTTP 状态码 | 耗时
    """
    ms = int(duration * 1000)
    logging.info("[API] %s | %s | %s | %sms", path, client_ip, status, ms)
