"""config.py 拆分：API 端点配置实体：表单/列表页与增删改、预览、Key 管理（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import json
import logging
import urllib.parse
import db
import config_db
import static_cache
import api_handler
import app_config
import html as html_mod
from json_template import ALL_KEYS, SINGLE_KEYS, validate_template
from render import render_page_header, render_page_footer, build_flash_html, build_api_endpoints_list_html, build_api_endpoint_form_html, build_api_endpoint_preview_help_html
from report import parse_result_names

def _estimate_result_count(sql_query: str) -> int:
    """估算 SQL 中 SELECT/WITH 语句的数量。"""
    sql = sql_query.strip()
    if not sql:
        return 1
    count = 0
    for stmt in db._split_sql_statements(sql):
        stmt = stmt.strip().upper()
        if stmt.startswith("SELECT") or stmt.startswith("WITH"):
            count += 1
    return max(count, 1)


def render_api_endpoint_form_page(conn, report_id: int,
                                   endpoint_id: int = None,
                                   flash: str = None,
                                   endpoint: dict = None,
                                   is_edit: bool = None) -> str:
    """渲染新增/编辑 API 端点表单页

    endpoint: 表单回显数据（保存失败时覆盖 DB 读取，保留用户原输入）
    is_edit: 表单模式（None 时按 endpoint_id 判定）
    """
    report = db.get_report(conn, report_id)
    if not report:
        return config.render_overview(conn, flash="错误: 报表不存在")
    if endpoint is None:
        endpoint = db.get_api_endpoint(conn, endpoint_id) if endpoint_id else None
    if endpoint_id and not endpoint:
        return config.render_overview(conn, flash="错误: API 接口不存在")

    result_names_raw = (report.get("result_names") or "").strip()
    result_names_list = parse_result_names(result_names_raw)
    result_count = len(result_names_list) if result_names_list else _estimate_result_count(report["sql_query"])

    # 编辑态查询该端点的 API Key 列表（多 key 管理区块）
    api_keys = config_db.list_api_keys(conn, endpoint_id) if endpoint_id else []

    return (render_page_header(title="SqlReport - API 接口", active_nav="api",
                                extra_css=config._CONFIG_EXTRA_CSS)
            + build_api_endpoint_form_html(report_id, report["name"],
                                            endpoint, flash,
                                            result_names_list=result_names_list,
                                            result_count=result_count,
                                            endpoint_id=endpoint_id,
                                            is_edit=is_edit,
                                            api_keys=api_keys)
            + render_page_footer())


def _template_raw_for_format(output_format: str, data: dict) -> str:
    """按输出格式取模板文本：CSV 模式不支持模板，返回空串（不校验、不落库，
    保留库中原值，切回 JSON 后模板仍可用）。"""
    return "" if output_format == "csv" else data.get("json_template", "")


def _validate_json_template(raw: str, result_mode: str,
                            smart_quote_flags: int = 0) -> str | None:
    """校验 JSON 输出模板文本；返回错误消息（None=合法或未启用）。

    键集随表单 result_mode 判定（single/all），与渲染链路保持一致。
    smart_quote_flags>0（「智能去引号」面板勾选）时替换后的 JSON 合法性
    校验恒执行（智能模式输出永远合法，升级点）。
    """
    if not raw or not raw.strip():
        return None
    keys = SINGLE_KEYS if result_mode == "single" else ALL_KEYS
    ok, err = validate_template(raw, keys, smart_quote_flags=smart_quote_flags)
    return None if ok else err


def _endpoint_from_form(data: dict, url_path: str, result_mode: str) -> dict:
    """从表单数据构造临时端点 dict（保存失败时表单回显用户原输入）。"""
    try:
        columns, filters_str, sorts_str, nested_filter_str = config._parse_rule_json(data.get("rule_json", ""))
    except ValueError:
        columns = ""
        filters_str = ""
        sorts_str = ""
        nested_filter_str = ""
    return {
        "name": data.get("name", ""),
        "description": data.get("description", "") or "",
        "url_path": url_path,
        "output_format": data.get("output_format", "json"),
        "columns": columns,
        "filters": filters_str,
        "sorts": sorts_str,
        "nested_filter": nested_filter_str,
        "row_limit": config._echo_int(data.get("row_limit"), 0),
        "api_key": data.get("api_key") or "",
        "allowed_origins": data.get("allowed_origins") or "",
        "enabled": config._echo_int(data.get("enabled"), 0),
        "allow_fetch_all": config._echo_int(data.get("allow_fetch_all"), 1),
        "static_cache": config._echo_int(data.get("static_cache"), 1),
        "smart_quote_flags": config._echo_int(data.get("smart_quote_flags"), 0),
        "result_mode": result_mode,
        "result_index": config._echo_int(data.get("result_index"), 0),
        "json_template": data.get("json_template", "") or "",
    }


def _parse_endpoint_form(data: dict) -> dict:
    """从表单数据解析 API 端点全部字段（add/edit 共用读路径）。

    产出字段含 name/url_path/output_format/columns/filters_str/sorts_str/
    row_limit/enabled/allow_fetch_all/static_cache/result_mode/
    result_index/template_raw/api_key/allowed_origins/description。
    """
    output_format = data.get("output_format", "json")
    result_mode = data.get("result_mode", "single")
    columns, filters_str, sorts_str, nested_filter_str = config._parse_rule_json(data.get("rule_json", ""))
    return {
        "name": data["name"],
        "url_path": config._normalize_api_url_path(data["url_path"]),
        "output_format": output_format,
        "columns": columns,
        "filters_str": filters_str,
        "sorts_str": sorts_str,
        "nested_filter": nested_filter_str,
        "row_limit": int(data.get("row_limit", 0) or 0),
        "enabled": int(data.get("enabled", 0) or 0),
        "allow_fetch_all": int(data.get("allow_fetch_all", 1) or 0),
        "static_cache": int(data.get("static_cache", 1) or 0),
        "smart_quote_flags": int(data.get("smart_quote_flags", 0) or 0),
        "result_mode": result_mode,
        "result_index": int(data.get("result_index", 0) or 0),
        # CSV 模式忽略模板字段（模板仅 JSON 有效）：不校验、不落库
        "template_raw": _template_raw_for_format(output_format, data),
        "api_key": data.get("api_key") or None,
        "allowed_origins": data.get("allowed_origins") or None,
        "description": data.get("description") or None,
    }


def _endpoint_unique_error(err_msg: str, url_path: str = "") -> str:
    """将 UNIQUE 约束错误转换为重复路径提示，非唯一错误原样返回。"""
    if "UNIQUE" in err_msg or "unique" in err_msg:
        return f"URL 路径 '{url_path}' 已存在"
    return err_msg


def handle_api_key_actions(conn, report_id: int, endpoint_id: int,
                           form_body: str = "",
                           session_user=None) -> tuple[int, str, dict]:
    """处理 API Key 管理动作（POST：add 生成新 Key / delete / toggle）。

    操作成功后重定向回端点编辑页并携带 flash。
    """
    edit_url = f"/config/reports/{report_id}/api_endpoints/{endpoint_id}/edit"
    endpoint = db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        flash_msg = "错误: API 接口不存在"
        return config._redirect_or_render(
            302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")
    if int(endpoint.get("report_id", 0)) != report_id:
        flash_msg = "错误: API 接口不属于该报表"
        return config._redirect_or_render(
            302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")

    data = config._parse_form_data(form_body or "")
    action = data.get("action", "")
    key_id_raw = data.get("key_id", "")
    name = (data.get("name") or "").strip()
    try:
        if action == "add":
            key_name = name or endpoint["name"]
            config_db.add_api_key(conn, endpoint_id, key_name,
                                  api_handler.generate_api_key(),
                                  session_user=session_user)
            flash_msg = f"API Key 已生成（{key_name}）"
        elif action in ("delete", "toggle"):
            # 归属校验：key 必须属于当前端点，否则拒绝（防跨端点越权操作）
            key_row = config_db.get_api_key(conn, int(key_id_raw))
            if not key_row:
                flash_msg = "错误: API Key 不存在"
            elif int(key_row.get("endpoint_id", 0)) != endpoint_id:
                flash_msg = "错误: API Key 不属于该接口"
            elif action == "delete":
                config_db.delete_api_key(conn, int(key_id_raw),
                                         session_user=session_user)
                flash_msg = "API Key 已删除"
            else:
                new_enabled = 0 if int(key_row.get("enabled", 1)) else 1
                config_db.set_api_key_enabled(conn, int(key_id_raw), new_enabled,
                                              session_user=session_user)
                flash_msg = (f"API Key {key_row['name']} "
                             f"已{'启用' if new_enabled else '禁用'}")
        else:
            flash_msg = "错误: 未知操作"
    except (ValueError, TypeError):
        flash_msg = "错误: 无效的 Key ID"
    return config._redirect_or_render(
        302, f"{edit_url}?flash={urllib.parse.quote(flash_msg)}")


def handle_api_endpoint_add(conn, report_id: int,
                             form_body: str, session_user=None) -> tuple[int, str]:
    """处理新增 API 端点表单提交"""
    data = config._parse_form_data(form_body)
    try:
        pf = _parse_endpoint_form(data)
        tpl_err = _validate_json_template(
            pf["template_raw"], pf["result_mode"],
            smart_quote_flags=pf["smart_quote_flags"])
        if tpl_err:
            return 200, render_api_endpoint_form_page(
                conn, report_id,
                endpoint=_endpoint_from_form(data, pf["url_path"], pf["result_mode"]),
                is_edit=False,
                flash=f"错误: JSON 输出模板无效: {tpl_err}")
        eid = db.add_api_endpoint(
            conn, report_id, pf["name"], pf["url_path"],
            output_format=pf["output_format"],
            columns=pf["columns"] or None,
            filters=pf["filters_str"] or None,
            sorts=pf["sorts_str"] or None,
            nested_filter=pf["nested_filter"] or None,
            row_limit=pf["row_limit"],
            allowed_origins=pf["allowed_origins"],
            result_mode=pf["result_mode"],
            result_index=pf["result_index"],
            allow_fetch_all=pf["allow_fetch_all"],
            static_cache=pf["static_cache"],
            smart_quote_flags=pf["smart_quote_flags"],
            json_template=pf["template_raw"] or None,
            description=pf["description"],
            session_user=session_user,
        )
        # 多 key 化：表单不再有 api_key 输入框。旧客户端 POST 仍带 api_key
        # 字段时（兼容路径）写入 api_keys 表（name=端点名）；否则自动生成一条。
        if pf["api_key"]:
            config_db.add_api_key(conn, eid, pf["name"], pf["api_key"],
                                  session_user=session_user)
        else:
            config_db.add_api_key(conn, eid, pf["name"],
                                  api_handler.generate_api_key(),
                                  session_user=session_user)
        if not pf["enabled"]:
            db.update_api_endpoint(conn, eid, enabled=0, session_user=session_user)
        return config._save_or_render(
            data, render_api_endpoint_form_page,
            (conn, report_id, eid), {},
            success_flash=f"API 接口 {pf['name']} 已创建 (id={eid})",
            redirect_url=f"/config/reports/{report_id}/edit")
    except Exception as e:
        err_msg = _endpoint_unique_error(str(e), data.get("url_path", ""))
        return 200, render_api_endpoint_form_page(
            conn, report_id,
            endpoint=_endpoint_from_form(data,
                                         config._normalize_api_url_path(data.get("url_path", "")),
                                         data.get("result_mode", "single")),
            is_edit=False,
            flash=f"错误: {err_msg}")


def handle_api_endpoint_edit(conn, report_id: int, endpoint_id: int,
                              form_body: str, session_user=None) -> tuple[int, str]:
    """处理编辑 API 端点表单提交"""
    data = config._parse_form_data(form_body)
    try:
        endpoint = db.get_api_endpoint(conn, endpoint_id)
        if not endpoint:
            return 302, "/config?flash=错误: API 接口不存在"
        pf = _parse_endpoint_form(data)
        tpl_err = _validate_json_template(
            pf["template_raw"], pf["result_mode"],
            smart_quote_flags=pf["smart_quote_flags"])
        if tpl_err:
            tmp = _endpoint_from_form(data, pf["url_path"], pf["result_mode"])
            tmp["id"] = endpoint_id
            return 200, render_api_endpoint_form_page(
                conn, report_id, endpoint_id, endpoint=tmp, is_edit=True,
                flash=f"错误: JSON 输出模板无效: {tpl_err}")
        update_kwargs = dict(
            name=pf["name"],
            url_path=pf["url_path"],
            output_format=pf["output_format"],
            columns=pf["columns"] or None,
            filters=pf["filters_str"] or None,
            sorts=pf["sorts_str"] or None,
            nested_filter=pf["nested_filter"] or None,
            row_limit=pf["row_limit"],
            api_key=pf["api_key"],
            allowed_origins=pf["allowed_origins"],
            enabled=pf["enabled"],
            allow_fetch_all=pf["allow_fetch_all"],
            result_mode=pf["result_mode"],
            result_index=pf["result_index"],
            static_cache=pf["static_cache"],
            smart_quote_flags=pf["smart_quote_flags"],
            description=pf["description"],
            session_user=session_user,
        )
        if pf["output_format"] != "csv":
            update_kwargs["json_template"] = pf["template_raw"] or None
        ok = db.update_api_endpoint(conn, endpoint_id, **update_kwargs)
        if ok:
            return config._save_or_render(
                data, render_api_endpoint_form_page,
                (conn, report_id, endpoint_id), {},
                success_flash=f"API 接口 {pf['name']} 已更新",
                redirect_url=f"/config/reports/{report_id}/edit")
        return 302, "/config?flash=错误: 更新失败"
    except Exception as e:
        err_msg = _endpoint_unique_error(str(e), data.get("url_path", ""))
        tmp = _endpoint_from_form(data,
                                  config._normalize_api_url_path(data.get("url_path", "")),
                                  data.get("result_mode", "single"))
        tmp["id"] = endpoint_id
        return 200, render_api_endpoint_form_page(
            conn, report_id, endpoint_id, endpoint=tmp, is_edit=True,
            flash=f"错误: {err_msg}")


def handle_api_endpoint_delete(conn, report_id: int,
                                endpoint_id: int, session_user=None) -> tuple[int, str]:
    """处理删除 API 端点"""
    endpoint = db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        return 302, "/config?flash=错误: API 接口不存在"
    if int(endpoint.get("report_id", 0)) != report_id:
        return 302, (f"/config/reports/{report_id}/edit"
                       f"?flash=错误: API 接口不属于该报表")
    db.delete_api_endpoint(conn, endpoint_id, session_user=session_user)
    return 302, (f"/config/reports/{report_id}/edit"
                   f"?flash=API 接口 {endpoint['name']} 已删除")


def handle_api_endpoint_preview(conn, report_id: int, endpoint_id: int,
                                form_body: str, session_user=None) -> tuple[int, str, dict]:
    """真实数据预览：用表单未保存值构造临时端点（不落库）执行查询。

    预览复用线上渲染链路（api_handler._execute_api_query + _format_output），
    保证预览即最终输出；行数强制限制为 _PREVIEW_MAX_ROWS 行。

    返回 (200, JSON, {"Content-Type": "application/json; charset=utf-8"})，
    JSON 形如 {"ok": true, "output": <渲染后响应文本>} 或
    {"ok": false, "error": <结构化错误消息（模板非法含行列号）>}。
    """
    json_headers = {"Content-Type": "application/json; charset=utf-8"}

    def fail(message: str) -> tuple:
        return 200, json.dumps({"ok": False, "error": message},
                               ensure_ascii=False), json_headers

    if not (form_body or "").strip():
        # 直接 GET 打开预览地址：无表单值可执行，返回可交互指引页
        return 200, build_api_endpoint_preview_help_html(
            report_id, endpoint_id), {"Content-Type": "text/html; charset=utf-8"}

    endpoint = config_db.get_api_endpoint(conn, endpoint_id)
    if not endpoint:
        return fail("API 接口不存在")
    if int(endpoint.get("report_id", 0)) != report_id:
        return fail("API 接口不属于该报表")
    if endpoint.get("output_format", "json") == "csv":
        return fail("模板仅 JSON 格式支持，CSV 格式下无法预览")

    data = config._parse_form_data(form_body or "")
    result_mode = data.get("result_mode", "single")
    template_raw = data.get("json_template", "") or ""
    smart_quote_flags = int(data.get("smart_quote_flags", 0) or 0)
    tpl_err = _validate_json_template(
        template_raw, result_mode, smart_quote_flags=smart_quote_flags)
    if tpl_err:
        return fail(tpl_err)

    # 构造临时端点：表单未保存值覆盖 DB 配置，不落库
    tmp = dict(endpoint)
    tmp["json_template"] = template_raw or None
    tmp["result_mode"] = result_mode
    tmp["result_index"] = int(data.get("result_index", 0) or 0)
    tmp["smart_quote_flags"] = smart_quote_flags
    columns, filters_str, sorts_str, nested_filter_str = config._parse_rule_json(data.get("rule_json", ""))
    tmp["columns"] = columns or None
    tmp["filters"] = filters_str or None
    tmp["sorts"] = sorts_str or None
    tmp["nested_filter"] = nested_filter_str or None
    form_row_limit = int(data.get("row_limit", 0) or 0)
    tmp["row_limit"] = min(form_row_limit, config._PREVIEW_MAX_ROWS) if form_row_limit > 0 else config._PREVIEW_MAX_ROWS

    try:
        result = api_handler._execute_api_query(conn, tmp, "GET", "", {}, {})
    except Exception as e:
        logging.warning("真实数据预览查询执行失败: %s", e)
        return fail(f"查询执行失败: {e}")

    if isinstance(result, tuple):
        status, resp_body, _ = result
        if status != 200:
            try:
                msg = json.loads(resp_body).get("error", resp_body)
            except (json.JSONDecodeError, TypeError, AttributeError):
                msg = resp_body
            return fail(f"查询执行失败: {msg}")
        # result_mode=all 成功：resp_body 已是模板渲染后的最终 JSON
        return 200, json.dumps({"ok": True, "output": resp_body},
                               ensure_ascii=False), json_headers

    status, out_body, _ = api_handler._format_output(
        result.data_rows, result.display_cols, result.total, result.page,
        result.page_size, result.total_pages, result.output_format,
        result.add_bom, result.full, template=tmp["json_template"] or "", meta=None,
        truncated=result.truncated, smart_quote_flags=result.smart_quote_flags)
    if status != 200:
        return fail("预览输出构建失败")
    return 200, json.dumps({"ok": True, "output": out_body},
                           ensure_ascii=False), json_headers


def render_api_endpoints_page(conn, flash: str = None) -> str:
    """API 接口独立列表页（T7.5 抽出为可测函数；R2-D 对齐原型 page-api）。"""
    api_endpoints = db.get_all_api_endpoints(conn)
    flash_html = build_flash_html(flash) if flash else ""
    base_url = app_config.get_server_base_url()
    # page-head：h1 + 统计 sub + 「+ 新建接口」。接口表单挂在报表下（仅有
    # /config/reports/{id}/api_endpoints/new 路由），故指向首张报表的新建接口表单；
    # 无报表时先去新建报表。
    enabled_n = sum(1 for ep in api_endpoints if int(ep.get("enabled", 1) or 0))
    sc_cfg = static_cache.get_static_cache_config()
    sc_dir = html_mod.escape(str(sc_cfg.get("dir", "static_cache")))
    reports = config_db.get_all_reports(conn)
    if reports:
        new_href = f"/config/reports/{int(reports[0]['id'])}/api_endpoints/new"
        new_title = ' title="接口表单挂在报表下，进入首张报表的新建接口表单"'
    else:
        new_href = "/config/reports/add"
        new_title = ' title="尚无报表：先新建报表，再为其创建接口"'
    body = (render_page_header(title="SqlReport - API 接口", active_nav="api",
                               extra_css=config._CONFIG_EXTRA_CSS,
                               nav_badges=config._nav_badges(conn))
            + flash_html
            + '<div class="page-head"><div>'
            + '<h1>API 接口</h1>'
            + (f'<div class="sub">API 接口管理 · 报表即服务 · 全局 '
               f'{len(api_endpoints)} 个接口（{enabled_n} 启用） · '
               f'静态缓存目录 {sc_dir}/api</div>')
            + '</div><div class="actions">'
            + f'<a class="btn btn-primary" href="{new_href}"{new_title}>+ 新建接口</a>'
            + '</div></div>'
            + build_api_endpoints_list_html(api_endpoints, show_report_name=True,
                                            base_url=base_url,
                                            key_counts=config_db.get_api_key_counts(conn))
            + render_page_footer())
    return body


def handle_api_endpoints_request(conn, method: str, path: str, query: str,
                                  form_body: str = None,
                                  session_user=None) -> tuple[int, str, dict]:
    """处理 /config/api-endpoints 请求（独立 API 端点管理页）。"""
    if method == "POST":
        data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
        action = data.get("action", [""])[0]
        endpoint_id = data.get("endpoint_id", [None])[0]
        if action == "delete" and endpoint_id:
            try:
                endpoint_id = int(endpoint_id)
                endpoint = db.get_api_endpoint(conn, endpoint_id)
                if endpoint:
                    db.delete_api_endpoint(conn, endpoint_id, session_user=session_user)
                    flash_msg = "API 接口已删除"
                else:
                    flash_msg = "错误: API 接口不存在"
            except (ValueError, TypeError):
                flash_msg = "错误: 无效的接口 ID"
            return 302, f"/config/api-endpoints?flash={urllib.parse.quote(flash_msg)}", {}
        if action == "toggle" and endpoint_id:
            try:
                endpoint_id = int(endpoint_id)
                endpoint = db.get_api_endpoint(conn, endpoint_id)
                if endpoint:
                    new_enabled = 0 if int(endpoint.get("enabled", 1)) else 1
                    db.update_api_endpoint(conn, endpoint_id, enabled=new_enabled,
                                           session_user=session_user)
                    flash_msg = f"API 接口 {endpoint['name']} 已{'启用' if new_enabled else '禁用'}"
                else:
                    flash_msg = "错误: API 接口不存在"
            except (ValueError, TypeError):
                flash_msg = "错误: 无效的接口 ID"
            return_to = data.get("return_to", [None])[0]
            if return_to and return_to.startswith("/") and not return_to.startswith("//"):
                sep = "&" if "?" in return_to else "?"
                return 302, f"{return_to}{sep}flash={urllib.parse.quote(flash_msg)}", {}
            return 302, f"/config/api-endpoints?flash={urllib.parse.quote(flash_msg)}", {}
        return 302, "/config/api-endpoints", {}

    qs = urllib.parse.parse_qs(query, keep_blank_values=True)
    flash = qs.get("flash", [None])[0]
    return 200, render_api_endpoints_page(conn, flash), {}
