"""
export.py — CSV 导出功能

职责：
- 根据报表配置执行完整查询（不分页）
- 将结果导出为 CSV（字段带双引号，逗号分隔）
- 设置正确的 HTTP Content-Type 和 Content-Disposition 头

CSV 格式规范：
- 所有字段使用双引号包裹
- 逗号作为字段分隔符
- 字段内的双引号使用 "" 转义
- UTF-8 编码，带 BOM 以便 Excel 正确识别中文
"""

import csv
import io
import urllib.parse
import db
import report
from typing import Optional


def _parse_filters(qs):
    """
    从 parse_qs 结果中解析多字段筛选参数（与 report.py 保持一致）。
    """
    filters = []
    excl = frozenset(("f_col", "f_q", "filters"))
    for key, values in qs.items():
        if not key.startswith("f_") or key in excl:
            continue
        colname = urllib.parse.unquote(key[2:])
        if values and values[0]:
            filters.append((colname, values[0]))
    if not filters:
        f_cols = qs.get("f_col", [])
        f_qs = qs.get("f_q", [])
        for c, q in zip(f_cols, f_qs):
            if q:
                filters.append((c, q))
    return filters


def export_report_to_csv(sql_query: str, pool_config: dict,
                         filters=None) -> str:
    """
    执行查询并将结果导出为 CSV 字符串。

    支持可选的 filters 参数（list[(col, q), ...]），
    在导出前按条件过滤数据行（与报表页面筛选行为一致）。

    返回完整的 CSV 文本（含 BOM + 表头行 + 数据行）。
    """
    conn = db.create_mysql_connection(pool_config)
    try:
        columns, rows = db.execute_mysql_query(conn, sql_query)
    finally:
        conn.close()

    # 应用内存筛选（与报表页面的筛选逻辑一致）
    filtered = report._filter_rows(rows, columns, filters or [])

    output = io.StringIO()
    output.write("\ufeff")

    writer = csv.writer(output, delimiter=",", quotechar='"',
                        quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(columns)
    for row in filtered:
        writer.writerow(row)

    return output.getvalue()


def handle_export(conn, query: str,
                  pool_override: Optional[dict] = None) -> tuple[str, str, dict]:
    """
    处理 CSV 导出请求。

    参数：
      conn          — SQLite 配置库连接
      query         — URL 查询字符串（含 id 参数）
      pool_override — 用于测试的 mock 连接池配置

    返回：
      (HTTP 状态码, CSV 内容/错误信息, 响应头 dict)
    """
    qs = urllib.parse.parse_qs(query, keep_blank_values=True)

    if "id" not in qs or not qs["id"][0]:
        return "400", "缺少报表 ID 参数", {}

    try:
        report_id = int(qs["id"][0])
    except (ValueError, IndexError):
        return "400", "无效的报表 ID", {}

    report = db.get_report(conn, report_id)
    if not report:
        return "404", "报表不存在", {}

    if pool_override:
        pool_config = pool_override
    else:
        pool_config = db.get_pool(conn, report["pool_id"])
        if not pool_config:
            return "404", f"报表 '{report['name']}' 关联的连接池不存在", {}

    # 解析筛选参数（从查询字符串，与报表页面一致）
    filters = _parse_filters(qs)

    try:
        csv_content = export_report_to_csv(report["sql_query"], pool_config,
                                            filters)
    except Exception as e:
        return "500", f"导出失败: {e}", {}

    # filename 按 RFC 5987 编码，兼容中文
    raw_name = f"{report['name']}.csv"
    ascii_name = f"report_{report_id}.csv"
    encoded_name = urllib.parse.quote(raw_name, safe='')
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        ),
    }
    return "200", csv_content, headers
