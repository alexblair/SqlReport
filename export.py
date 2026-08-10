"""
export.py — CSV / JSON 导出功能

职责：
- 根据报表配置执行完整查询（不分页）
- 将结果导出为 CSV（字段带双引号，逗号分隔）或 JSON（行对象数组）
- 设置正确的 HTTP Content-Type 和 Content-Disposition 头
- 支持导出字符集选择（GBK / UTF8）
- 支持 JSON 值无引号模式（所有值输出不带引号，含字符串）
- 支持导出文件压缩为 ZIP 包（临时目录 -> ZIP -> 输出 -> 清理）

导出格式控制：
  /export?id=N              → CSV（默认）
  /export?id=N&format=json  → JSON

导出选项：
  charset=gbk|utf8          字符集（默认 gbk）
  json_no_quotes=1          JSON 值无引号（所有值不加引号）
  zip=1                     输出为 ZIP 压缩包

CSV 格式规范：
- 所有字段使用双引号包裹
- 逗号作为字段分隔符
- 字段内的双引号使用 "" 转义

JSON 格式规范：
- 顶层结构：{"报表名": [{"列名": 值}, ...]}
- 使用 json.dumps(ensure_ascii=False, indent=2) 序列化
- 字段值中的引号自动转义
"""

import csv
import io
import json
import os
import shutil
import tempfile
import urllib.parse
import zipfile
from typing import Optional, Union
import db
import app_config
from render import format_cell
from report import parse_filters, parse_sorts, parse_result_index, WRITE_DENIED_MESSAGE
from query_executor import sql_contains_write
from result_transform import filter_rows, sort_rows, select_columns, column_indices


def _load_and_transform(sql_query: str, pool_config: dict,
                        filters=None,
                        columns: list[str] = None,
                        result_index: int = 0,
                        sorts=None,
                        max_rows: int = None) -> tuple:
    """
    执行查询并应用内存变换，返回导出所需的数据。

    两导出函数（CSV / JSON）共用的头部流程：
    连接 → 查询 → 多结果集越界回退 → 截断至 max_rows → 内存筛选 → 排序 →
    输出列确定（自定义列回退全部列）→ 列索引映射。

    返回 (output_columns, display_indices, rows, truncated)：
      output_columns — 最终输出列名列表（按用户自定义顺序）
      display_indices — output_columns 在 all_columns 中的索引列表
      rows — 已筛选/排序的行数据列表
      truncated — 查询结果是否发生过 max_rows 截断（False 表示未截断）
    """
    conn = db.create_mysql_connection(pool_config)
    try:
        results = db.execute_mysql_query(conn, sql_query)
        if result_index >= len(results):
            result_index = 0
        all_columns = results[result_index]["columns"]
        rows = results[result_index]["rows"]
    finally:
        conn.close()

    # PH-07 全量输出护栏：与报表页面/API 一致，原始行截断后再筛选/排序
    truncated = False
    if max_rows is not None and max_rows > 0 and len(rows) > max_rows:
        rows = rows[:max_rows]
        truncated = True

    # 应用内存筛选（与报表页面的筛选逻辑一致）
    filtered = filter_rows(rows, all_columns, filters or [])
    # 应用排序（与报表页面一致）
    if sorts:
        filtered = sort_rows(filtered, all_columns, sorts)

    # 确定输出列（按用户自定义顺序，无效列名回退全部列）
    output_columns = select_columns(all_columns, columns)
    display_indices = column_indices(output_columns, all_columns)
    return output_columns, display_indices, filtered, truncated


def rows_to_csv(header, rows, *, bom=True, quoting=csv.QUOTE_ALL,
                encoding="utf-8", lineterminator="\n"):
    """
    将表头与行数据序列化为 CSV 文本（导出 / API / 审计页三处共用的统一实现）。

    header: 表头列名列表。
    rows: 每行数据列表（按 header 顺序取值）。

    参数:
        bom: 为 True 时输出开头写入 \\ufeff BOM 字符（UTF-8 场景便于 Excel 识别）。
        quoting: csv 引号策略（默认 QUOTE_ALL 全字段加双引号）。
        encoding: "utf-8" 返回 str；"utf-8-sig" 返回 utf-8-sig 编码的 bytes
                  （自带 BOM 字节，等价于调用方自行 .encode("utf-8-sig")）。
        lineterminator: 行结束符（默认 "\\n"；需要 CRLF 时传 "\\r\\n"）。

    返回 str（encoding="utf-8"）或 bytes（encoding="utf-8-sig" 时）。
    """
    output = io.StringIO()
    if bom:
        output.write("\ufeff")
    writer = csv.writer(output, delimiter=",", quotechar='"',
                        quoting=quoting, lineterminator=lineterminator)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    content = output.getvalue()
    if encoding == "utf-8-sig":
        return content.encode("utf-8-sig")
    return content


def export_report_to_csv(sql_query: str, pool_config: dict,
                         filters=None,
                         columns: list[str] = None,
                         result_index: int = 0,
                         sorts=None,
                         max_rows: int = None,
                         _truncated_out: list = None) -> str:
    """
    执行查询并将结果导出为 CSV 字符串。

    支持可选的 filters 参数（list[(col, op, val), ...]），
    在导出前按条件过滤数据行（与报表页面筛选行为一致）。
    columns: 自定义列列表（顺序 + 可见性），None 表示全部列。
    result_index: 多结果集时选择第几个结果（默认 0）。
    sorts: list[(col, dir), ...] 排序参数（与报表页面一致）。
    max_rows: 全量输出截断上限（None=不截断；>0 时原始行超过即截断，PH-07）。
    _truncated_out: 内部回传通道（list）；发生过截断时写入 [True]（供响应头标记）。

    返回完整的 CSV 文本（含 BOM + 表头行 + 数据行），
    以 UTF-8 字符串形式返回。
    """
    output_columns, display_indices, filtered, truncated = _load_and_transform(
        sql_query, pool_config, filters, columns, result_index, sorts,
        max_rows=max_rows)
    if truncated and _truncated_out is not None:
        _truncated_out.append(True)

    # 序列化为 CSV（QUOTE_ALL 全字段加双引号 + BOM + "\n" 行尾，与既有输出一致）
    rows_out = [[row[i] for i in display_indices] for row in filtered]
    return rows_to_csv(output_columns, rows_out, bom=True,
                       quoting=csv.QUOTE_ALL, lineterminator="\n")


def export_report_to_json(sql_query: str, pool_config: dict,
                          report_name: str,
                          filters=None,
                          json_no_quotes: bool = False,
                          columns: list[str] = None,
                          result_index: int = 0,
                          sorts=None,
                          max_rows: int = None,
                          _truncated_out: list = None) -> str:
    """
    执行查询并将结果导出为 JSON 字符串。

    支持可选的 filters 参数（list[(col, op, val), ...]），
    在导出前按条件过滤数据行（与报表页面筛选行为一致）。
    columns: 自定义列列表（顺序 + 可见性），None 表示全部列。
    result_index: 多结果集时选择第几个结果（默认 0）。
    sorts: list[(col, dir), ...] 排序参数（与报表页面一致）。
    max_rows: 全量输出截断上限（None=不截断；>0 时原始行超过即截断，PH-07）。
    _truncated_out: 内部回传通道（list）；发生过截断时写入 [True]（供响应头标记）。

    当 json_no_quotes=True 时，输出的值一律不带引号（含字符串，如 "123" 输出
    为 123、文本输出为裸文本），结构保留 JSON 语法（键带引号）；输出不保证是
    合法 JSON。与 API 端点「值无引号」选项共用 app_config.serialize_no_quote
    单一实现。关闭时全部值转为字符串。

    JSON 格式：
    {
      "报表名": [
        {"列A": 值, "列B": "文本"},
        ...
      ]
    }
    """
    output_columns, display_indices, filtered, truncated = _load_and_transform(
        sql_query, pool_config, filters, columns, result_index, sorts,
        max_rows=max_rows)
    if truncated and _truncated_out is not None:
        _truncated_out.append(True)

    # 构建行对象数组
    rows_data = []
    for row in filtered:
        obj = {}
        for col, idx in zip(output_columns, display_indices):
            if json_no_quotes:
                # 值无引号模式：保留原始值，序列化时统一裸输出
                obj[col] = row[idx]
            else:
                # 全部转为字符串（原有行为）
                obj[col] = format_cell(row[idx])
        rows_data.append(obj)

    # 顶层结构：以报表名（清理后）作为数据键
    safe_name = report_name.strip().replace(" ", "_").replace("-", "_")

    if json_no_quotes:
        output = app_config.serialize_no_quote(
            {safe_name: rows_data}, indent=2)
    else:
        output = json.dumps(
            {safe_name: rows_data},
            ensure_ascii=False,
            indent=2,
        )
    return output


def _encode_content(content: str, charset: str) -> bytes:
    """
    将字符串内容编码为指定字符集的字节。

    charset 支持 'gbk' 和 'utf8'。
    GBK 编码时移除 BOM 字符（\ufeff），因为 GBK 不支持该字符。
    编码失败时使用 replace 策略。
    """
    if charset == "utf8":
        return content.encode("utf-8")
    # GBK 编码：先移除 BOM 字符（CSV 导出时写入的 \ufeff 不可编码为 GBK）
    clean = content.replace("\ufeff", "")
    return clean.encode("gbk", errors="replace")


def _build_export_filename(report_name: str, report_id: int,
                           export_format: str, is_zip: bool) -> tuple[str, str, str]:
    """
    构建导出文件名。

    返回 (raw_name, ascii_name, encoded_name) 三元组，
    用于 Content-Disposition 头。
    """
    ext = ".zip" if is_zip else f".{export_format}"
    raw_name = f"{report_name}{ext}"
    ascii_name = f"report_{report_id}{ext}"
    encoded_name = urllib.parse.quote(raw_name, safe='')
    return raw_name, ascii_name, encoded_name


def _create_temp_zip(content_bytes: bytes, filename: str,
                     zip_filename: str) -> bytes:
    """
    将字节内容写入临时文件，创建 ZIP 压缩包，返回 ZIP 字节。

    函数结束后清理临时目录和临时文件。
    """
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="report_export_")
        # 写入原始内容到临时文件
        tmpfile_path = os.path.join(tmpdir, filename)
        with open(tmpfile_path, "wb") as f:
            f.write(content_bytes)

        # 创建 ZIP 文件
        zip_path = os.path.join(tmpdir, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmpfile_path, arcname=filename)

        # 读取 ZIP 内容
        with open(zip_path, "rb") as f:
            zip_data = f.read()
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return zip_data


def handle_export(conn, query: str,
                  pool_override: Optional[dict] = None
                  ) -> tuple[int, Union[str, bytes], dict]:
    """
    处理导出请求。

    解析以下查询参数：
      id             — 报表 ID（必需）
      format         — csv 或 json（默认 csv）
      charset        — gbk 或 utf8（默认 utf8）
      json_no_quotes — 为 1 时 JSON 值不带引号（所有值裸输出）
      zip            — 为 1 时输出 ZIP 压缩包
      f_COL          — 筛选值（多字段）
      op_COL         — 筛选操作符（缺省为 contains）

    返回：
      (HTTP 状态码, 内容/错误信息, 响应头 dict)
      当返回 ZIP 时，内容为 bytes 类型。
    """
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)

    if "id" not in qs or not qs["id"][0]:
        return 400, "缺少报表 ID 参数", {}

    report_id = app_config.safe_int(qs["id"][0], None)
    if report_id is None:
        return 400, "无效的报表 ID", {}

    report_config = db.get_report(conn, report_id)
    if not report_config:
        return 404, "报表不存在", {}

    if pool_override:
        pool_config = pool_override
    else:
        pool_config = db.get_pool(conn, report_config["pool_id"])
        if not pool_config:
            return 404, f"报表 '{report_config['name']}' 关联的连接池不存在", {}

    # 解析筛选参数（从查询字符串，与报表页面一致）
    filters = parse_filters(qs)

    # 解析排序参数（与报表页面共享 parse_sorts）
    sorts = parse_sorts(qs)

    # 解析自定义列参数
    custom_columns = None
    use_custom_cols = qs.get("use_custom_cols", [None])[0] == "1"
    cols_raw = qs.get("cols", [])
    if use_custom_cols and cols_raw and cols_raw[0]:
        custom_columns = [urllib.parse.unquote(c) for c in cols_raw[0].split(",")]

    # 解析导出选项
    export_format = "csv"
    fmt_vals = qs.get("format", [])
    if fmt_vals and fmt_vals[0].lower() == "json":
        export_format = "json"

    charset = "gbk"
    charset_vals = qs.get("charset", [])
    if charset_vals and charset_vals[0].lower() in ("utf8", "utf-8"):
        charset = "utf8"

    json_no_quotes = False
    if qs.get("json_no_quotes", [None])[0] == "1":
        json_no_quotes = True

    is_zip = False
    if qs.get("zip", [None])[0] == "1":
        is_zip = True

    # 多结果集索引
    result_index = parse_result_index(qs)

    # PH-05 写护栏：导出走独立连接路径，同样按规则拦截
    # （allow_write=0 且报表 SQL 含写语句 → 拒绝导出，与页面/API 一致）
    if not int(report_config.get("allow_write", 1) or 0) \
            and sql_contains_write(report_config["sql_query"]):
        return 403, WRITE_DENIED_MESSAGE, {}

    # PH-07 全量输出护栏：allow_all_output=0 且 max_rows>0 → 截断至 max_rows
    # （与报表页面 execute_report 语义一致；存量报表缺字段按存量语义不截断）
    export_limit = None
    if not int(report_config.get("allow_all_output", 1) or 0):
        m = int(report_config.get("max_rows") or 0)
        if m > 0:
            export_limit = m
    truncated_sink = []

    # 执行导出
    try:
        if export_format == "json":
            content = export_report_to_json(
                report_config["sql_query"], pool_config,
                report_config["name"], filters, json_no_quotes,
                custom_columns, result_index, sorts=sorts,
                max_rows=export_limit, _truncated_out=truncated_sink)
        else:
            content = export_report_to_csv(
                report_config["sql_query"], pool_config, filters,
                custom_columns, result_index, sorts=sorts,
                max_rows=export_limit, _truncated_out=truncated_sink)
    except Exception as e:
        return 500, f"导出失败: {e}", {}

    # 构建 Content-Disposition 文件名
    raw_name, ascii_name, encoded_name = _build_export_filename(
        report_config["name"], report_id, export_format, is_zip)

    if is_zip:
        # 编码内容为字节，打包为 ZIP
        content_bytes = _encode_content(content, charset)
        # 压缩包内文件使用原始扩展名（.csv 或 .json），而非 .zip
        inner_filename = f"{report_config['name']}.{export_format}"
        zip_data = _create_temp_zip(content_bytes, inner_filename, raw_name)

        headers = {
            "Content-Type": "application/zip",
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
        }
        if truncated_sink:
            headers["X-Export-Truncated"] = "true"
        return 200, zip_data, headers

    # 非 ZIP 模式：根据字符集编码内容
    content_bytes = _encode_content(content, charset)

    if export_format == "json":
        content_type = "application/json"
    else:
        content_type = "text/csv"

    charset_label = "utf-8" if charset == "utf8" else "gbk"
    headers = {
        "Content-Type": f"{content_type}; charset={charset_label}",
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        ),
    }
    if truncated_sink:
        headers["X-Export-Truncated"] = "true"

    return 200, content_bytes, headers
