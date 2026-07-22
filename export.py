"""
export.py — CSV / JSON 导出功能

职责：
- 根据报表配置执行完整查询（不分页）
- 将结果导出为 CSV（字段带双引号，逗号分隔）或 JSON（行对象数组）
- 设置正确的 HTTP Content-Type 和 Content-Disposition 头
- 支持导出字符集选择（GBK / UTF8）
- 支持 JSON 导出时数值不加引号（保持原始数字类型）
- 支持导出文件压缩为 ZIP 包（临时目录 -> ZIP -> 输出 -> 清理）

导出格式控制：
  /export?id=N              → CSV（默认）
  /export?id=N&format=json  → JSON

导出选项：
  charset=gbk|utf8          字符集（默认 gbk）
  json_no_quotes=1          JSON 数值不加引号
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
from decimal import Decimal
from typing import Optional, Union
import db
import report
from report import format_cell, parse_filters, _parse_sorts, _sort_rows


def export_report_to_csv(sql_query: str, pool_config: dict,
                         filters=None,
                         columns: list[str] = None,
                         result_index: int = 0,
                         sorts=None) -> str:
    """
    执行查询并将结果导出为 CSV 字符串。

    支持可选的 filters 参数（list[(col, op, val), ...]），
    在导出前按条件过滤数据行（与报表页面筛选行为一致）。
    columns: 自定义列列表（顺序 + 可见性），None 表示全部列。
    result_index: 多结果集时选择第几个结果（默认 0）。
    sorts: list[(col, dir), ...] 排序参数（与报表页面一致）。

    返回完整的 CSV 文本（含 BOM + 表头行 + 数据行），
    以 UTF-8 字符串形式返回。
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

    # 应用内存筛选（与报表页面的筛选逻辑一致）
    filtered = report._filter_rows(rows, all_columns, filters or [])
    # 应用排序（与报表页面一致）
    if sorts:
        filtered = report._sort_rows(filtered, all_columns, sorts)

    # 确定输出列（按用户自定义顺序）
    if columns is None:
        output_columns = all_columns
        display_indices = list(range(len(all_columns)))
    else:
        # 仅保留实际存在的列名，去重并保持用户指定顺序
        valid_set = set(all_columns)
        seen = set()
        output_columns = []
        for c in columns:
            if c in valid_set and c not in seen:
                output_columns.append(c)
                seen.add(c)
        # 所有列名均无效时回退到全部列
        if not output_columns:
            output_columns = all_columns
            display_indices = list(range(len(all_columns)))
        else:
            col_index_map = {name: idx for idx, name in enumerate(all_columns)}
            display_indices = [col_index_map[c] for c in output_columns]

    output = io.StringIO()
    # 写入 BOM，便于 Excel 识别编码（UTF-8 时有效，GBK 编码时由调用方处理）
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=",", quotechar='"',
                        quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(output_columns)
    for row in filtered:
        writer.writerow([row[i] for i in display_indices])

    return output.getvalue()


class _JsonNoQuoteEncoder(json.JSONEncoder):
    """
    自定义 JSON 编码器，用于 json_no_quotes 模式。

    将 Decimal 转换为数值（float / int），
    处理 date/datetime 为 ISO 字符串，
    处理 bytes 为 UTF-8 解码字符串。
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            # 与 format_cell 保持一致的数值格式化，但返回数值类型
            if obj == 0:
                return 0
            s = format(obj, "f").rstrip("0").rstrip(".")
            if s in ("", "-0"):
                return 0
            return int(s) if "." not in s else float(s)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        # date / datetime treated as string via str()
        return str(obj)


def _no_quote_value(val):
    """
    当 json_no_quotes 启用时，返回适合 JSON 序列化的值。

    保留原始数字类型（int / float / Decimal），
    字符串保持字符串，None 保持 None。
    Decimal 由 _JsonNoQuoteEncoder 处理。
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, Decimal):
        return val
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def export_report_to_json(sql_query: str, pool_config: dict,
                          report_name: str,
                          filters=None,
                          json_no_quotes: bool = False,
                          columns: list[str] = None,
                          result_index: int = 0,
                          sorts=None) -> str:
    """
    执行查询并将结果导出为 JSON 字符串。

    支持可选的 filters 参数（list[(col, op, val), ...]），
    在导出前按条件过滤数据行（与报表页面筛选行为一致）。
    columns: 自定义列列表（顺序 + 可见性），None 表示全部列。
    result_index: 多结果集时选择第几个结果（默认 0）。
    sorts: list[(col, dir), ...] 排序参数（与报表页面一致）。

    当 json_no_quotes=True 时，数值类型的字段将保持数字格式
    （不加引号），而非全部转为字符串。

    JSON 格式：
    {
      "报表名": [
        {"列A": 值, "列B": "文本"},
        ...
      ]
    }
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

    # 应用内存筛选（与报表页面的筛选逻辑一致）
    filtered = report._filter_rows(rows, all_columns, filters or [])
    # 应用排序（与报表页面一致）
    if sorts:
        filtered = report._sort_rows(filtered, all_columns, sorts)

    # 确定输出列（按用户自定义顺序）
    if columns is None:
        output_columns = all_columns
        display_indices = list(range(len(all_columns)))
    else:
        # 仅保留实际存在的列名，去重并保持用户指定顺序
        valid_set = set(all_columns)
        seen = set()
        output_columns = []
        for c in columns:
            if c in valid_set and c not in seen:
                output_columns.append(c)
                seen.add(c)
        # 所有列名均无效时回退到全部列
        if not output_columns:
            output_columns = all_columns
            display_indices = list(range(len(all_columns)))
        else:
            col_index_map = {name: idx for idx, name in enumerate(all_columns)}
            display_indices = [col_index_map[c] for c in output_columns]

    # 构建行对象数组
    rows_data = []
    for row in filtered:
        obj = {}
        for col, idx in zip(output_columns, display_indices):
            if json_no_quotes:
                # 保留原始数值类型
                obj[col] = _no_quote_value(row[idx])
            else:
                # 全部转为字符串（原有行为）
                obj[col] = format_cell(row[idx])
        rows_data.append(obj)

    # 顶层结构：以报表名（清理后）作为数据键
    safe_name = report_name.strip().replace(" ", "_").replace("-", "_")

    if json_no_quotes:
        output = json.dumps(
            {safe_name: rows_data},
            ensure_ascii=False,
            indent=2,
            cls=_JsonNoQuoteEncoder,
        )
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
      json_no_quotes — 为 1 时 JSON 数值不加引号
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

    try:
        report_id = int(qs["id"][0])
    except (ValueError, IndexError):
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

    # 解析排序参数（与报表页面共享 _parse_sorts）
    sorts = _parse_sorts(qs)

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
    result_index = 0
    if "result" in qs and qs["result"][0]:
        try:
            result_index = max(0, int(qs["result"][0]))
        except ValueError:
            pass

    # 执行导出
    try:
        if export_format == "json":
            content = export_report_to_json(
                report_config["sql_query"], pool_config,
                report_config["name"], filters, json_no_quotes,
                custom_columns, result_index, sorts=sorts)
        else:
            content = export_report_to_csv(
                report_config["sql_query"], pool_config, filters,
                custom_columns, result_index, sorts=sorts)
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

    return 200, content_bytes, headers
