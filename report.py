"""
report.py — 报表页面处理

职责：
- 报表选择（根据配置显示下拉列表）
- 缓存原始 SQL 查询结果，避免重复查询数据库
- 在缓存结果上执行**多字段**内存排序、**多字段**模糊筛选、分页
- 完整分页控制（显示总页数、跳转任意页）

URL 路由：
  GET /report                       → 报表选择页
  GET /report?id=N                  → 展示第 N 个报表的第一页
  GET /report?id=N&page=P           → 第 P 页
  GET /report?id=N&sort=COL&dir=asc → 按 COL 单列排序
  GET /report?id=N&sort=C1&dir=asc&sort=C2&dir=desc → 多列排序
  GET /report?id=N&f_name=alice     → name 列模糊筛选
  GET /report?id=N&f_name=alice&f_age=30 → 多字段同时筛选
  POST /report（action=refresh_cache） → 重建缓存后 302 回跳（破坏性操作 POST 化）
  POST /report/preview              → 预览模式：不保存配置，临时以 POST 表单中的 SQL 查看

兼容旧格式：
  GET /report?id=N&f_col=name&f_q=alice →（自动转为 f_name=alice）
"""

import logging
import re
import urllib.parse
import time
import threading
import json
import db
from typing import Optional
import redis_cache
import static_cache
import app_config
import config_db
from result_transform import (filter_rows, sort_rows, select_columns,
                              calc_total_pages, invalid_numeric_filters,
                              NUMERIC_FILTER_OPS, filter_rows_nested)
from query_executor import sql_contains_write

# PH-05 写操作护栏：拦截与警示共用文案（页面 flash / API 结构化错误 / 导出拒绝一致）
WRITE_DENIED_MESSAGE = "该报表包含写操作语句且未开启『允许执行写操作』，请到编辑页开启"
WRITE_ALLOWED_BANNER = "本报表包含写操作语句，执行会修改数据库数据"
# 报表页顶部警示条共享样式（预览模式警示条与写操作警示条共用，防样式漂移）
_BANNER_STYLE = "padding:6px 12px;border-radius:6px;margin-bottom:10px;font-size:13px;font-weight:600"

# 从 render.py 导入常量和渲染函数（移走了纯 HTML 生成逻辑）
from render import (
    _COMMON_JS,
    _SQL_HIGHLIGHT_JS,
    _SQL_FORMATTER_JS,
    render_page_header,
    _OP_MAP, DEFAULT_OP, _escape, format_cell,
    build_filter_params as _build_filter_params,
    build_cols_param as _build_cols_param,
    build_pagination_html as _build_pagination,
    build_redis_banners_html as _build_redis_banners,
    build_debug_section_html, build_memo_section_html,
    build_current_rules_section_html,
    build_result_selector_html, build_cache_badge_html,
    build_sort_bar_html, build_table_header_html, build_table_body_html,
    build_controls_bar_html, build_field_settings_panel_html,
    build_sort_settings_panel_html, build_filter_form_html,
    build_filter_action_html, build_clear_filters_href,
    build_report_switcher_html,
    build_api_urls_section_html, build_flash_html,
    _MD_CSS,
)
import markdown_render

# ===================================================================
# 缓存（FILTER_OPS / _OP_MAP / DEFAULT_OP 已移至 render.py）
# ===================================================================


class CachedResult:
    """单次报表查询的缓存结果，保存原始 SQL 返回的全量数据（支持多结果集）。"""

    __slots__ = ("results", "sql_query", "timestamp", "source",
                 "source_timestamp", "truncated")

    def __init__(self, results: list[dict], sql_query: str,
                 source: str = None, source_timestamp: float = None,
                 truncated: bool = False):
        """
        results: [{"columns": [...], "rows": [...]}, ...]
        source: 数据原始来源（redis / mysql），F5 刷新后保留源头信息
        source_timestamp: 原始来源的时间戳（Redis 快照的 updated_at）
        truncated: 写入时是否发生过 max_rows 截断（PH-06 全量输出护栏）
        """
        self.results = results
        self.sql_query = sql_query
        self.timestamp = time.time()
        self.source = source
        self.source_timestamp = source_timestamp
        self.truncated = truncated


class QueryCache:
    """
    报表查询结果缓存。

    将原始 SQL 查询结果（全量行）保存在内存中，后续的排序/筛选/分页
    均在缓存数据上操作，避免对 MySQL 数据库产生重复压力。

    线程安全：ThreadingHTTPServer 下多个请求可能并发读写同一缓存项，
    所有操作均在锁内进行（get 的过期逐出与 SQL 变更逐出非原子，
    无锁时并发逐出同一项会抛 KeyError）。
    """

    def __init__(self, ttl: int = 300):
        """ttl: 缓存有效期（秒），默认 5 分钟"""
        self._cache: dict[int, CachedResult] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, report_id: int,
            sql_query: str = None) -> CachedResult | None:
        with self._lock:
            cached = self._cache.get(report_id)
            if cached is None:
                return None
            if time.time() - cached.timestamp > self._ttl:
                del self._cache[report_id]
                return None
            if sql_query is not None and cached.sql_query != sql_query:
                del self._cache[report_id]
                return None
            return cached

    def set(self, report_id: int, results: list[dict],
            sql_query: str, source: str = None,
            source_timestamp: float = None,
            truncated: bool = False) -> None:
        with self._lock:
            self._cache[report_id] = CachedResult(results, sql_query, source,
                                                   source_timestamp,
                                                   truncated)

    def invalidate(self, report_id: int) -> None:
        with self._lock:
            self._cache.pop(report_id, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


# 全局缓存实例
_query_cache = QueryCache()


# ===================================================================
# URL 参数工具（URL 工具函数已移至 render.py，通过别名保持 API 兼容）
# ===================================================================


def parse_filters(qs):
    """
    从 parse_qs 结果中解析多字段筛选参数。

    新格式（推荐）：
      f_{col}=value    筛选值
      op_{col}=op      操作符（缺省为 contains）
      例：f_age=100&op_age=gt   → age > 100
          f_name=alice           → name 包含 alice

    旧格式（兼容）：
      f_col=name&f_q=alice（仅单字段有效）

    返回 list[(col, op, val), ...]
    """
    # 第一步：收集筛选值 f_{col}=val
    f_values: dict[str, str] = {}
    excl = frozenset(("f_col", "f_q", "filters"))
    for key, values in qs.items():
        if not key.startswith("f_") or key in excl:
            continue
        colname = urllib.parse.unquote(key[2:])
        if values and values[0]:
            f_values[colname] = values[0]

    # 第二步：收集操作符 op_{col}=op
    op_values: dict[str, str] = {}
    for key, values in qs.items():
        if not key.startswith("op_") or key in ("op_col", "op_q"):
            continue
        colname = urllib.parse.unquote(key[3:])
        if values and values[0] in _OP_MAP:
            op_values[colname] = values[0]

    # 旧格式兼容
    if not f_values:
        f_cols = qs.get("f_col", [])
        f_qs = qs.get("f_q", [])
        for c, q in zip(f_cols, f_qs):
            if q:
                f_values[c] = q

    filters = []
    for col, val in f_values.items():
        op = op_values.get(col, DEFAULT_OP)
        filters.append((col, op, val))
    # 单独的操作符也需要输出（如 isempty/notempty 可能无值）
    for col, op in op_values.items():
        if col not in f_values and op != "nofilter":
            filters.append((col, op, ""))
    filters = [(c, o, v) for c, o, v in filters if o != "nofilter"]
    return filters


_parse_filters = parse_filters  # 向后兼容别名


def parse_sorts(qs):
    """
    从 parse_qs 结果中解析多字段排序参数。

    格式：sort=col1&dir=asc&sort=col2&dir=desc  (repeated)
    返回 list[(col, dir), ...] 按原始优先级从低到高排列。
    同一列名重复时，保留第一个出现的位置优先级，使用最后一个方向。
    """
    sorts = [(c, d) for c, d in
             zip(qs.get("sort", []), qs.get("dir", []))
             if d in ("asc", "desc")]
    # 去重：保留第一出现的位置，使用最后一出现的方向
    result: list[tuple[str, str]] = []
    for c, d in sorts:
        found = False
        for i, (xc, xd) in enumerate(result):
            if xc == c:
                result[i] = (c, d)
                found = True
                break
        if not found:
            result.append((c, d))
    return result


_parse_sorts = parse_sorts  # 向后兼容别名


def _parse_cols(qs, all_columns: list[str]) -> list[str]:
    """
    从 parse_qs 结果中解析自定义列顺序参数。

    格式：cols=col1,col2,col3
    返回实际要显示的列名列表（按用户指定顺序）。
    仅保留 all_columns 中存在的列名，忽略无效列名。
    若未传 cols 参数或为空，返回 all_columns（默认显示全部）。
    """
    cols_raw = qs.get("cols", [])
    if not cols_raw or not cols_raw[0]:
        return list(all_columns)
    requested = [urllib.parse.unquote(c) for c in cols_raw[0].split(",")]
    return select_columns(all_columns, requested)


def _qs_val(qs: dict, key: str, default: str = None) -> Optional[str]:
    """从 parse_qs 结果中安全取第一个值"""
    vals = qs.get(key, [])
    return vals[0] if vals else default


def parse_result_index(qs: dict, key: str = "result", default: int = 0) -> int:
    """从 parse_qs 结果中安全解析结果集索引，非法值回退 default。"""
    if key in qs and qs[key][0]:
        try:
            return max(0, int(qs[key][0]))
        except ValueError:
            return default
    return default


def parse_result_names(raw: str, count: int = None) -> list[str]:
    """解析结果集名称文本（每行一个，剔除空行）。

    count 给定时补齐/截断到该数量，缺名自动补"结果{i+1}"（i 从 0 起）。
    """
    names = [n.strip() for n in raw.split("\n") if n.strip()]
    if count is None:
        return names
    return [names[i] if i < len(names) else f"结果{i + 1}" for i in range(count)]


# ===================================================================
# HTML 模板（CSS）
# ===================================================================
# 公共 CSS（reset/body/navbar/container/card/btn/table/flash/empty-state/
# sql-hl/pagination/jump-box 等）统一来自 render._COMMON_CSS，
# 此处仅保留报表页特有类，经 render_page_header(extra_css=...) 追加。

_CSS = """
  th .sort-link {
    color: #475569; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;
    transition: color 0.15s; cursor: pointer;
  }
  th .sort-link:hover { color: #4f46e5; }
  th .sort-arrow { font-size: 12px; color: #94a3b8; }
  th .sort-arrow.active { color: #4f46e5; }
  th .filter-input {
    display: block; width: 100%; margin-top: 6px; padding: 4px 8px;
    border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px;
    font-weight: 400; text-transform: none; letter-spacing: 0;
    outline: none; transition: border-color 0.2s; background: #fff;
    box-sizing: border-box;
  }
  th .filter-input:focus { border-color: #4f46e5; box-shadow: 0 0 0 2px rgba(79,70,229,0.12); }
  th .filter-input::placeholder { color: #cbd5e1; }
  /* 05 工单：表头列保守 min-width 保证筛选输入框可用；聚焦展开为固定宽度（桌面） */
  th { min-width: 100px; }
  th .filter-input:focus { width: 220px; }
  .debug-info {
    background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;
    margin-bottom: 16px; font-size: 13px; color: #64748b;
    word-break: break-all; line-height: 1.6;
  }
  .debug-info code {
    background: #e9ecef; padding: 2px 6px; border-radius: 4px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px; color: #334155;
  }
  .debug-info pre {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px; color: #334155;
  }
  .debug-toggle {
    display:inline-flex; align-items:center; gap:4px; font-size:12px;
    color:#94a3b8; cursor:pointer; background:none; border:1px solid #e2e8f0;
    border-radius:6px; padding:4px 10px; margin-bottom:8px; transition:color 0.15s;
  }
  .debug-toggle:hover { color:#475569; background:#f1f5f9; }
  .debug-content { padding: 0 16px 12px; }
  .debug-content.hidden { display: none; }
  .debug-info[data-mem-key] { position: relative; }
  .mem-toggle {
    position: absolute; top: 6px; right: 12px;
    display: inline-flex; align-items: center; gap: 4px;
  }
  .mem-mode {
    border: 1px solid #e2e8f0; background: #fff; color: #94a3b8;
    border-radius: 4px; padding: 1px 6px; cursor: pointer; font-size: 12px;
    line-height: 1.6;
  }
  .mem-mode:hover { color: #475569; border-color: #cbd5e1; }
  .mem-mode.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }
  .controls {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 14px 16px; background: #f8fafc; border-radius: 8px; margin-bottom: 16px;
    border: 1px solid #e2e8f0;
  }
  .controls label { font-size: 14px; color: #475569; font-weight: 500; display: inline-flex; align-items: center; gap: 8px; }
  .controls select {
    padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
    font-size: 14px; color: #1e293b; background: #fff; outline: none;
    cursor: pointer; transition: border-color 0.2s;
  }
  .controls select:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.12); }
  .controls .stat { font-size: 14px; color: #64748b; margin-left: auto; }
  .controls .cache-badge {
    font-size: 12px; color: #64748b; background: #e9ecef; padding: 2px 10px;
    border-radius: 99px; white-space: nowrap;
  }
  .controls .cache-badge.fresh { background: #dcfce7; color: #166534; }
  .btn-refresh {
    display:inline-flex; align-items:center; gap:4px; padding:6px 14px;
    font-size:13px; font-weight:600; border-radius:6px; cursor:pointer;
    background:#f0f0f0; color:#475569; border:1px solid #cbd5e1;
    text-decoration:none; transition:background 0.2s, color 0.2s;
  }
  .btn-refresh:hover { background:#e2e8f0; color:#1e293b; }
  .report-select label { font-size: 15px; color: #334155; font-weight: 500; display: block; margin-bottom: 8px; }
  .report-select select {
    width: 100%; padding: 10px 14px; border: 2px solid #e2e8f0; border-radius: 8px;
    font-size: 15px; color: #1e293b; outline: none; cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s; background: #fff;
    appearance: auto;
  }
  .report-select select:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.15); }
  .report-list { list-style: none; padding: 0; margin-top: 4px; }
  .report-list li { padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
  .report-list li:last-child { border-bottom: none; }
  .report-list a {
    color: #4f46e5; text-decoration: none; font-weight: 500; font-size: 15px;
    transition: color 0.15s; display: flex; align-items: center; gap: 8px;
  }
  .report-list a:hover { color: #4338ca; }
  .report-list a::before { content: "→"; color: #94a3b8; font-weight: 400; }
  .clear-filter {
    display: inline-block; margin-left: 8px; font-size: 12px; color: #94a3b8;
    text-decoration: none; cursor: pointer;
  }
  .clear-filter:hover { color: #dc2626; }
"""

# _PAGE_HEADER 已删除：页面头部（<head>/导航栏/公共 CSS）统一由
# render.render_page_header 生成，见 _render_page_header()。

# 常见 MySQL 错误码 → 业务用户可读提示（spec ux-optimization 批次3#10）。
# 命中映射时页面展示人话 + 折叠原始错误供技术排查；未命中保留原文。
_DB_ERROR_HINTS = {
    1064: "SQL 语法有误，请检查报表的 SQL 语句",
    1146: "查询的数据表不存在，可能已被删除或改名",
    1054: "查询的字段不存在，可能已被删除或改名",
    1142: "数据库账号缺少执行该操作的权限，请联系管理员",
    1044: "数据库账号缺少访问该库的权限，请联系管理员",
    2003: "无法连接数据库服务器，请稍后重试或联系管理员检查连接池配置",
    2005: "数据库主机名无法解析，请检查连接池配置",
    1045: "数据库账号或密码被拒绝，请检查连接池配置",
    1205: "数据库锁等待超时，可能有其他任务占用，请稍后重试",
    1049: "数据库不存在，请检查连接池配置",
}


def humanize_db_error(e) -> tuple[str, str]:
    """把数据库异常翻译为业务用户可读文案（批次3#10）。

    返回 (friendly, raw)：friendly 为人话主文案；raw 保留原始错误文本，
    由 render_sql_error_section 折叠展示。errno 提取双通道：优先取
    mysql.connector.Error 的 errno 属性，否则从消息 "(NNNN)" 模式正则匹配
    （兼容测试 mock 与第三方包装异常）。未命中映射时 friendly 即原文。
    """
    msg = str(e)
    errno = getattr(e, "errno", None)
    if not isinstance(errno, int):
        m = re.search(r"\((\d{4})\)", msg)
        errno = int(m.group(1)) if m else None
    hint = _DB_ERROR_HINTS.get(errno) if errno else None
    return (hint or msg, msg)


def render_sql_error_section(friendly: str, raw: str) -> str:
    """渲染 SQL 执行错误区块：人话主文案 + <details> 折叠原始错误。

    原始错误默认折叠——业务用户只需看懂出了什么问题；
    需要排查的技术人员可展开复制完整信息反馈给管理员。
    """
    from html import escape as _h  # 局部引用避免与模块级 _escape 混淆
    return (
        f'<div class="flash flash-error">查询失败：{_h(friendly)}'
        f'<details style="margin-top:6px"><summary style="cursor:pointer;'
        f'color:#94a3b8;font-size:13px">查看原始错误信息</summary>'
        f'<pre style="white-space:pre-wrap;word-break:break-all;'
        f'font-size:12px;color:#7f1d1d;margin:6px 0 0">{_h(raw)}</pre>'
        f'</details></div>')


# 常见 MySQL 错误码 → 用户可读文案（spec ux-optimization 批次3#10）。
# 数值 errno 优先取异常属性，其次从消息文本 "(HY000)" 形式代码正则提取。
_DB_ERRNO_HINTS = {
    1064: "SQL 语法有误：请检查报表 SQL（该错误通常需要管理员修正）",
    1146: "查询的数据表不存在：表可能已被删除或改名",
    1054: "查询的字段不存在：列可能已被删除或改名",
    1142: "数据库权限不足：当前账号无权访问该表",
    1044: "数据库权限不足：当前账号无权访问该库",
    1045: "数据库账号或密码被拒绝：请检查连接池配置",
    2003: "无法连接数据库：目标库暂时不可用，请稍后重试或联系管理员",
    2005: "数据库地址无法识别：请检查连接池主机配置",
    1205: "数据库锁等待超时：可能有其他任务占用该表，请稍后重试",
    # 批次5#18（spec ux-optimization）：read_timeout 触发的查询超时
    1969: "查询超时：数据量过大或数据库繁忙，请缩小筛选范围后重试",
}

# 消息文本命中即视为读取超时（部分驱动/包装异常不携带 errno 1969）
_READ_TIMEOUT_MSG_MARKERS = ("Read timed out",)


def humanize_db_error(e: Exception) -> tuple[str, str]:
    """把数据库异常翻译为用户可读文案。

    返回 (friendly, raw)：friendly 为人话主文案；raw 为原始错误文本，
    供页面折叠展示与技术排查。未识别的异常原样返回（不制造虚假解释）。
    批次5#18：errno 1969 或消息含 "Read timed out" 时映射为查询超时人话。
    """
    raw = str(e)
    errno = getattr(e, "errno", None)
    if not isinstance(errno, int):
        m = re.search(r"\((\d{4})\)", raw) or re.match(r"^(\d{4})\s", raw)
        errno = int(m.group(1)) if m else None
    hint = _DB_ERRNO_HINTS.get(errno)
    if not hint and any(marker in raw for marker in _READ_TIMEOUT_MSG_MARKERS):
        hint = _DB_ERRNO_HINTS[1969]
    if not hint:
        return raw, raw
    return hint, raw


def render_sql_error_section(friendly: str, raw: str) -> str:
    """渲染报表执行错误区块：人话主文案 + <details> 折叠原始错误。"""
    return (f'<div class="flash flash-error">查询执行失败：'
            f'{_escape(friendly)}'
            f'<details style="margin-top:6px"><summary style="cursor:pointer;'
            f'color:#64748b;font-size:12px">查看原始错误信息</summary>'
            f'<pre style="white-space:pre-wrap;font-size:12px;color:#7f1d1d;'
            f'margin:6px 0 0">{_escape(raw)}</pre></details></div>')


def _render_page_header(title: str = None) -> str:
    """报表页头部：公共 CSS（render._COMMON_CSS）+ 报表页特有 CSS + 代码高亮 CSS + Markdown 排版 CSS + 导航高亮。

    批次6#27a：title 可选传入（如报表名），默认保持站点标题。
    """
    return render_page_header(title=title or "Web 报表工具", active_nav="report",
                              extra_css=_CSS + markdown_render.codehilite_css() + _MD_CSS)


def _js_string(s: str) -> str:
    r"""把 Python 字符串安全内嵌进 <script> 的 JS 字符串字面量。

    json.dumps 保证引号/控制字符转义；再对 HTML 敏感字符做 unicode 转义
    （如 \u003c 形式），防止 </script>、<!-- 等序列提前闭合脚本上下文。
    """
    out = json.dumps(str(s), ensure_ascii=False)
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                    ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        out = out.replace(ch, esc)
    return out


_FOOTER = r"""</div>
<script>
function toggleFieldItem(checkbox) {
  var label = checkbox.closest('.field-item');
  if (label) {
    label.style.background = checkbox.checked ? '#f8fafc' : '#fff';
  }
}
function moveField(btn, dir) {
  var item = btn.closest('.field-item');
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  var idx = items.indexOf(item);
  var target = idx + dir;
  if (target < 0 || target >= items.length) return;
  if (dir === -1) {
    list.insertBefore(item, items[target]);
  } else {
    list.insertBefore(item, items[target].nextSibling);
  }
  updateMoveButtons();
}
function updateMoveButtons() {
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  items.forEach(function(item, i) {
    var up = item.querySelector('.field-up');
    var down = item.querySelector('.field-down');
    if (up) up.disabled = (i === 0);
    if (down) down.disabled = (i === items.length - 1);
  });
}
function selectAllFields(checked) {
  var list = document.getElementById('fieldList');
  var checkboxes = list.querySelectorAll('input[type="checkbox"]');
  checkboxes.forEach(function(cb) {
    cb.checked = checked;
    toggleFieldItem(cb);
  });
}
function applyFieldSettings() {
  var list = document.getElementById('fieldList');
  var items = Array.from(list.children);
  var cols = [];
  items.forEach(function(item) {
    var cb = item.querySelector('input[type="checkbox"]');
    if (cb && cb.checked) {
      var colInput = item.querySelector('input[name="col_order"]');
      if (colInput) cols.push(colInput.value);
    }
  });
  var reportId = new URLSearchParams(window.location.search).get('id');
  var pageSize = new URLSearchParams(window.location.search).get('page_size') || '';
  var resultIdx = new URLSearchParams(window.location.search).get('result') || '';
  var sorts = [];
  var filters = [];
  var params = new URLSearchParams(window.location.search);
  params.forEach(function(val, key) {
    if (key === 'sort') sorts.push(val);
    if (key === 'dir') sorts.push(val);
    if (key.startsWith('f_')) filters.push({key: key, val: val});
    if (key.startsWith('op_')) filters.push({key: key, val: val});
  });
  var url = '/report?id=' + reportId;
  if (pageSize) url += '&page_size=' + pageSize;
  if (resultIdx) url += '&result=' + encodeURIComponent(resultIdx);
  for (var i = 0; i < sorts.length; i += 2) {
    url += '&sort=' + encodeURIComponent(sorts[i]) + '&dir=' + encodeURIComponent(sorts[i+1]);
  }
  filters.forEach(function(f) {
    url += '&' + f.key + '=' + encodeURIComponent(f.val);
  });
  if (cols.length > 0 && cols.length < items.length) {
    url += '&cols=' + encodeURIComponent(cols.join(','));
  }
  window.location.href = url;
}
var _dragSrcEl = null;
function initDragHandlers() {
  var list = document.getElementById('fieldList');
  if (!list) return;
  list.addEventListener('dragstart', function(e) {
    var item = e.target.closest('.field-item');
    if (!item) return;
    _dragSrcEl = item;
    item.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
  });
  list.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    var item = e.target.closest('.field-item');
    if (!item || item === _dragSrcEl) return;
    var rect = item.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;
    if (e.clientY < midY) {
      list.insertBefore(_dragSrcEl, item);
    } else {
      list.insertBefore(_dragSrcEl, item.nextSibling);
    }
  });
  list.addEventListener('dragend', function(e) {
    if (_dragSrcEl) {
      _dragSrcEl.style.opacity = '';
      _dragSrcEl = null;
    }
    updateMoveButtons();
  });
}
document.addEventListener('DOMContentLoaded', function() {
  initDragHandlers();
  initSortDragHandlers();
});

function initSortDragHandlers() {
  var list = document.getElementById('sortList');
  if (!list) return;
  list.addEventListener('dragstart', function(e) {
    var item = e.target.closest('.sort-item');
    if (!item) return;
    _dragSrcEl = item;
    item.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
  });
  list.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    var item = e.target.closest('.sort-item');
    if (!item || item === _dragSrcEl) return;
    var rect = item.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;
    if (e.clientY < midY) {
      list.insertBefore(_dragSrcEl, item);
    } else {
      list.insertBefore(_dragSrcEl, item.nextSibling);
    }
  });
  list.addEventListener('dragend', function(e) {
    if (_dragSrcEl) {
      _dragSrcEl.style.opacity = '';
      _dragSrcEl = null;
    }
    updateSortMoveButtons();
  });
}

// ---- 排序管理面板 ----
function moveSortItem(btn, dir) {
  var item = btn.closest('.sort-item');
  var list = document.getElementById('sortList');
  if (!list || !item) return;
  var items = Array.from(list.children);
  var idx = items.indexOf(item);
  var target = idx + dir;
  if (target < 0 || target >= items.length) return;
  list.insertBefore(item, dir === -1 ? items[target] : items[target].nextSibling);
  updateSortMoveButtons();
}
function updateSortMoveButtons() {
  var list = document.getElementById('sortList');
  if (!list) return;
  var items = Array.from(list.children);
  items.forEach(function(item, i) {
    var up = item.querySelector('.sort-up');
    var down = item.querySelector('.sort-down');
    var num = item.querySelector('.sort-num');
    if (up) up.disabled = (i === 0);
    if (down) down.disabled = (i === items.length - 1);
    if (num) num.textContent = i + 1;
  });
}
function removeSortItem(btn) {
  var item = btn.closest('.sort-item');
  if (item) item.parentNode.removeChild(item);
  updateSortMoveButtons();
}
function addSortItem() {
  var col = document.getElementById('newSortCol').value;
  var dir = document.getElementById('newSortDir').value;
  if (!col) return;
  var list = document.getElementById('sortList');
  var existing = Array.from(list.querySelectorAll('input[name="sort_col"]')).some(function(inp) {
    return inp.value === col;
  });
  if (existing) return;
  var div = document.createElement('div');
  div.className = 'sort-item';
  div.draggable = true;
  div.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;background:#f8fafc;cursor:grab;user-select:none';
  var icon = dir === 'asc' ? '↑' : '↓';
  div.innerHTML = '<span class="drag-handle" style="color:#94a3b8;font-size:14px;cursor:grab;flex-shrink:0" title="拖拽排序">⠿</span>'
    + '<span class="sort-num" style="font-weight:700;font-size:11px;color:#4f46e5;min-width:20px">' + (list.children.length + 1) + '</span>'
    + '<span style="flex:1;font-size:13px;color:#1e293b">' + col + ' ' + icon + '</span>'
    + '<input type="hidden" name="sort_col" value="' + col + '">'
    + '<input type="hidden" name="sort_dir" value="' + dir + '">'
    + '<button type="button" class="sort-up" onclick="moveSortItem(this,-1)" style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff;color:#475569">▲</button>'
    + '<button type="button" class="sort-down" onclick="moveSortItem(this,1)" style="padding:2px 6px;font-size:11px;border:1px solid #e2e8f0;border-radius:4px;cursor:pointer;background:#fff;color:#475569">▼</button>'
    + '<button type="button" onclick="removeSortItem(this)" style="padding:2px 6px;font-size:11px;border:none;border-radius:4px;cursor:pointer;background:transparent;color:#dc2626">✕</button>';
  list.appendChild(div);
  updateSortMoveButtons();
  document.getElementById('newSortCol').value = '';
}
function applySortSettings() {
  var list = document.getElementById('sortList');
  var items = Array.from(list.children);
  var sorts = [];
  items.forEach(function(item) {
    var colInput = item.querySelector('input[name="sort_col"]');
    if (!colInput) return;
    sorts.push({col: colInput.value, dir: item.querySelector('input[name="sort_dir"]').value});
  });
  var reportId = new URLSearchParams(window.location.search).get('id');
  var pageSize = new URLSearchParams(window.location.search).get('page_size') || '';
  var resultIdx = new URLSearchParams(window.location.search).get('result') || '';
  var cols = new URLSearchParams(window.location.search).get('cols') || '';
  var url = '/report?id=' + reportId;
  if (pageSize) url += '&page_size=' + pageSize;
  if (resultIdx) url += '&result=' + encodeURIComponent(resultIdx);
  sorts.forEach(function(s) {
    url += '&sort=' + encodeURIComponent(s.col) + '&dir=' + encodeURIComponent(s.dir);
  });
  var params = new URLSearchParams(window.location.search);
  params.forEach(function(val, key) {
    if (key.startsWith('f_') || key.startsWith('op_')) {
      url += '&' + key + '=' + encodeURIComponent(val);
    }
  });
  if (cols) url += '&cols=' + encodeURIComponent(cols);
  window.location.href = url;
}
function switchResult(sel) {
  var rid = sel.dataset.reportId;
  var currIdx = parseInt(sel.dataset.activeIndex);
  var targetIdx = parseInt(sel.value);
  var swi = sel.dataset.swi;
  var ps = sel.dataset.pageSize;
  var so = sel.dataset.sqlOverride;
  if (targetIdx === currIdx) return;
  var key = 'rstate_' + rid;
  sessionStorage.setItem(key + '_' + currIdx, window.location.href);
  var saved = sessionStorage.getItem(key + '_' + targetIdx);
  if (saved) {
    window.location.href = saved;
  } else {
    var base = '/' + swi + '?id=' + rid + '&page_size=' + ps;
    if (so) base += '&sql_query=' + encodeURIComponent(so);
    base += '&result=' + targetIdx;
    window.location.href = base;
  }
}
function formatDebugSQL() {
  var pres = document.querySelectorAll('.sql-debug');
  pres.forEach(function(pre) {
    var raw = pre.textContent;
    if (!raw || !raw.trim()) return;
    var formatted = fmt(raw);
    pre.innerHTML = highlight(h(formatted));
  });
}
document.addEventListener('DOMContentLoaded', formatDebugSQL);
""" + _SQL_HIGHLIGHT_JS + _SQL_FORMATTER_JS + _COMMON_JS + r"""
var filterTouchInit = (function () {
  var coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  if (!coarse) return;
  var vv = window.visualViewport;
  function expand(el) {
    var rect = el.getBoundingClientRect();
    var offset = vv ? (vv.offsetTop || 0) : 0;
    el.classList.add('filter-input-touch');
    el.dataset.filterVvTop = String(rect.top);
    el.dataset.filterVvOffset = String(offset);
    el.style.position = 'fixed';
    el.style.left = Math.max(0, Math.min(rect.left, (vv ? vv.width : window.innerWidth) - 320)) + 'px';
    el.style.top = (rect.top + offset) + 'px';
    el.style.width = 'min(320px, 80vw)';
    el.style.zIndex = '1000';
  }
  function collapse(el) {
    el.classList.remove('filter-input-touch');
    delete el.dataset.filterVvTop;
    delete el.dataset.filterVvOffset;
    el.style.position = '';
    el.style.left = '';
    el.style.top = '';
    el.style.width = '';
    el.style.zIndex = '';
  }
  function recalc() {
    var offset = vv ? (vv.offsetTop || 0) : 0;
    document.querySelectorAll('.filter-input.filter-input-touch').forEach(function (el) {
      var dy = offset - (parseFloat(el.dataset.filterVvOffset) || 0);
      el.style.top = ((parseFloat(el.dataset.filterVvTop) || 0) + dy) + 'px';
    });
  }
  document.addEventListener('focusin', function (e) {
    if (e.target.classList && e.target.classList.contains('filter-input')) expand(e.target);
  });
  document.addEventListener('focusout', function (e) {
    if (e.target.classList && e.target.classList.contains('filter-input')) collapse(e.target);
  });
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.filter-input.filter-input-touch').forEach(function (el) {
      if (e.target !== el) collapse(el);
    });
  });
  if (vv) vv.addEventListener('resize', recalc);
})();
</script>
</body></html>"""


# ===================================================================
# 查询执行与分页（带缓存）
# ===================================================================


class ReportResult:
    """封装报表查询结果（支持多结果集）"""

    __slots__ = ("results", "active_index", "page", "page_size", "cache_info",
                 "truncated")

    def __init__(self, results=None, active_index: int = 0,
                 page: int = 1, page_size: int = 20, **kwargs):
        """
        新式调用：results=[{"columns":..., "rows":..., "total":N}, ...], active_index
        旧式兼容：results=columns(list[str]), active_index=rows(list[tuple]), total=total

        当第一个参数是 str 列表时自动识别为旧式调用。
        """
        total = kwargs.pop("total", None)
        columns_kw = kwargs.pop("columns", None)
        rows_kw = kwargs.pop("rows", None)
        self.cache_info = kwargs.pop("cache_info", None)
        self.truncated = kwargs.pop("truncated", None)
        if kwargs:
            raise TypeError(f"不支持的参数: {kwargs}")

        if columns_kw is not None or rows_kw is not None:
            # 旧式兼容：columns=..., rows=... 关键字参数
            cols = columns_kw or []
            rws = rows_kw or []
            self.results = [{
                "columns": cols,
                "rows": rws,
                "total": total if total is not None else len(rws)
            }]
            self.active_index = 0
        elif results is not None and results and isinstance(results[0], str):
            # 旧式兼容：results 其实是 columns，active_index 其实是 rows
            cols = results
            rws = active_index if isinstance(active_index, (list, tuple)) else []
            self.results = [{
                "columns": cols,
                "rows": rws,
                "total": total if total is not None else len(rws)
            }]
            self.active_index = 0
        else:
            # 新式：results 是 [{"columns":..., "rows":..., "total":...}, ...]
            self.results = results if results is not None else [{"columns": [], "rows": [], "total": 0}]
            self.active_index = active_index
        self.page = page
        self.page_size = page_size

    @property
    def columns(self) -> list[str]:
        """当前激活结果的列名"""
        if not self.results:
            return []
        return self.results[self.active_index]["columns"]

    @property
    def rows(self) -> list[tuple]:
        """当前激活结果的行数据"""
        if not self.results:
            return []
        return self.results[self.active_index]["rows"]

    @property
    def total(self) -> int:
        """当前激活结果的总行数"""
        if not self.results:
            return 0
        return self.results[self.active_index]["total"]

    @property
    def total_pages(self) -> int:
        """当前激活结果的总页数"""
        return calc_total_pages(self.total, self.page_size)


def execute_report(report_id: int, sql_query: str, pool_config: dict,
                   page: int = 1, page_size: int = 20,
                   sorts=None, filters=None,
                   refresh: bool = False,
                   active_index: int = 0,
                   report: Optional[dict] = None,
                   conn=None,
                   cache: "QueryCache" = None,
                   force_rebuild: bool = False,
                   read_timeout: Optional[int] = None,
                   nested_filter=None) -> ReportResult:
    """
    执行报表查询（优先使用缓存），支持多字段排序/筛选/分页。

    read_timeout: MySQL 读取超时秒数，仅 Web 交互路径传 30（批次5#18）；
    调度器/API 默认 None 不限制（找茬 H1：超长报表定时任务不受 30s 截断）。

    集成 Redis 缓存层：
    - 若报表启用了 prefer_cache 且 Redis 可用，优先读取 Redis 快照
    - 缓存重建时使用分布式锁避免重复查询
    - Redis 不可用时降级到 MySQL
    - MySQL 失败时兜底读取过期 Redis 快照

    sorts:   list[(col, dir), ...]  或 None
    filters: list[(col, op, val), ...]  或 None
    active_index: 当前渲染的结果索引
    report: 报表配置 dict（必须包含 prefer_cache/cache_ttl_hours，由调用方传入）
    cache: 进程内缓存会话（QueryCache 实例）。None 时使用模块级全局缓存；
           测试可注入独立实例避免跨用例污染。
    force_rebuild: 缓存保活专用（调度器 refresh-ahead）。True 时跳过进程内
           缓存与 Redis 快照的全部读取路径，直接查询 MySQL 并将新快照原子
           写回各层缓存。与 refresh 的「先删后查」不同，本模式「先算后换」：
           不预先删除旧快照，查询成功后新快照覆盖旧值，全程旧数据可持续
           服务（零空窗）；MySQL 失败时仍走过期快照兜底，不破坏现有缓存。
           供定时任务/保活链路调用，用户请求路径不应传入。
    """
    if cache is None:
        cache = _query_cache
    page = max(page if page is not None else 1, 1)
    page_size = max(page_size if page_size is not None else 20, 1)

    # 保活强制重建：跳过全部缓存读取（进程缓存 + Redis 快照 + 锁等待），
    # 直接进入 MySQL 查询分支；写路径（进程缓存/快照回填）保持生效。
    skip_cache_read = bool(force_rebuild)

    # PH-05 写操作护栏：实际 SQL 含写语句且报表未开启 allow_write → 拒绝执行。
    # 拦截置于缓存读取之前，防止已缓存结果绕过拦截；裸调用（report=None，测试等）
    # 不拦截，保持历史契约。
    if report is not None \
            and not int(report.get("allow_write", 1) or 0) \
            and sql_contains_write(sql_query):
        raise PermissionError(WRITE_DENIED_MESSAGE)

    # PH-06 全量输出护栏：allow_all_output=0 且 max_rows>0 时结果集截断至 max_rows。
    # 裸调用（report=None）或存量报表缺字段 → 按存量语义（allow_all_output=1）不截断。
    max_rows_cfg = int(report.get("max_rows", 0) or 0) if report else 0
    limit_rows = bool(report is not None
                      and not int(report.get("allow_all_output", 1) or 0)
                      and max_rows_cfg > 0)
    truncated_flag = None  # 本次执行是否发生截断（缓存条目/快照记录的基准值）

    prefer_cache = bool(report.get("prefer_cache", 0)) if report else False
    # 预览模式（SQL 来自表单而非数据库）时不写入 Redis
    is_preview = report is not None and sql_query != report.get("sql_query", "")
    cache_ttl_hours = int(report.get("cache_ttl_hours", 0)) if report else 0
    redis_avail = redis_cache.redis_available() if prefer_cache else False
    cache_info = None  # 缓存状态信息

    # 计算配置版本（仅当 Redis 可用时）
    config_version = None
    snapshot_key = None
    lock_key = None
    redis_prefix = ""
    if redis_avail and report:
        mgr = redis_cache.get_redis_manager()
        redis_prefix = mgr.key_prefix if mgr else "sr"
        pool_id = report.get("pool_id")
        config_version = redis_cache.compute_config_version(sql_query, pool_id)
        snapshot_key = redis_cache.build_snapshot_key(redis_prefix, report_id, config_version)
        lock_key = redis_cache.build_lock_key(redis_prefix, report_id, config_version)

    # 强制刷新：清除各层缓存
    if refresh:
        cache.invalidate(report_id)
        if redis_avail and snapshot_key:
            mgr = redis_cache.get_redis_manager()
            if mgr:
                mgr.delete_snapshot(snapshot_key)
        # 静态文件缓存联动：删除该报表全部 API 端点的静态文件（惰性重建）
        if conn is not None:
            try:
                config_db.invalidate_api_static_cache_by_report(conn, report_id)
            except Exception as e:
                logging.warning("static_cache refresh 联动失败: %s", e)

    # ---- 尝试从进程内缓存获取 ----
    cached = None if skip_cache_read else cache.get(report_id, sql_query)
    if cached is not None and _cache_matches_limit_policy(
            bool(getattr(cached, "truncated", False)), limit_rows):
        all_results = cached.results
        truncated_flag = bool(getattr(cached, "truncated", False))
        # 如果进程缓存源自 Redis，保留原始来源信息以供 UI 展示
        if cached.source == "redis":
            cache_info = {
                "source": "redis",
                "timestamp": cached.source_timestamp or cached.timestamp,
                "cached_at": cached.timestamp,
            }
        else:
            cache_info = {"source": "process", "timestamp": cached.timestamp}
    else:
        # ---- 尝试从 Redis 快照获取 ----
        redis_hit = False
        if redis_avail and snapshot_key and not skip_cache_read:
            mgr = redis_cache.get_redis_manager()
            if mgr:
                snapshot = mgr.get_snapshot(snapshot_key)
                if snapshot is not None and _cache_matches_limit_policy(
                        bool(getattr(snapshot, "truncated", False)), limit_rows):
                    all_results = snapshot.results
                    truncated_flag = bool(getattr(snapshot, "truncated", False))
                    cache.set(report_id, all_results, sql_query,
                                     source="redis",
                                     source_timestamp=snapshot.updated_at,
                                     truncated=truncated_flag)
                    redis_hit = True
                    cache_info = {
                        "source": "redis",
                        "timestamp": snapshot.updated_at,
                        "fresh": True,
                    }

        if not redis_hit:
            # ---- 检查是否需要走 Redis 重建锁 ----
            # force_rebuild（保活）：_mgr 仍需初始化供成功后写快照，但不取
            # 重建锁、不等他人锁结果——直接查询 MySQL，新快照原子覆盖旧值
            #（先算后换）；与用户请求触发的锁重建并发时最多重复一次查询，
            # 无正确性影响。
            lock_held = False  # 本进程是否实际持有 Redis 重建锁
            _mgr = redis_cache.get_redis_manager() if (redis_avail and snapshot_key and lock_key) else None
            if _mgr and not skip_cache_read:
                lock_held = _mgr.acquire_lock(lock_key)
                if not lock_held:
                    # 锁已被占用 → 等待锁释放后重新读取 Redis
                    lock_held = _mgr.wait_for_lock(lock_key)
                    if lock_held:
                        # 获取到锁后先检查 Redis 是否已有数据（可能已被其他进程写入）
                        _snap = _mgr.get_snapshot(snapshot_key)
                        if _snap is not None and _cache_matches_limit_policy(
                                bool(getattr(_snap, "truncated", False)), limit_rows):
                            all_results = _snap.results
                            truncated_flag = bool(getattr(_snap, "truncated", False))
                            cache.set(report_id, all_results, sql_query,
                                             source="redis",
                                             source_timestamp=_snap.updated_at,
                                             truncated=truncated_flag)
                            redis_hit = True
                            cache_info = {
                                "source": "redis",
                                "timestamp": _snap.updated_at,
                                "fresh": True,
                            }

            try:
                if not redis_hit:
                    # ---- MySQL 查询 ----
                    clean_sql = sql_query.rstrip("; \t\n\r")
                    conn = db.create_mysql_connection(
                        pool_config, read_timeout=read_timeout)
                    try:
                        all_results = db.execute_mysql_query(conn, clean_sql, transactional=True)
                    except Exception as e:
                        # MySQL 失败 → 兜底读：尝试读取过期 Redis 快照
                        if _mgr and snapshot_key:
                            _snap = _mgr.get_snapshot(snapshot_key)
                            if _snap is not None and _cache_matches_limit_policy(
                                    bool(getattr(_snap, "truncated", False)), limit_rows):
                                all_results = _snap.results
                                truncated_flag = bool(getattr(_snap, "truncated", False))
                                cache_info = {
                                    "source": "redis_fallback",
                                    "timestamp": _snap.updated_at,
                                    "fresh": False,
                                }
                        if cache_info is None:
                            raise
                    finally:
                        conn.close()

                    if cache_info is None:
                        # MySQL 查询成功 → 截断至 max_rows 后写入各层缓存
                        # （缓存即截断快照，省内存；truncated 标记随缓存条目/快照存储）
                        _cut = False
                        if limit_rows:
                            _cut, _ = _apply_max_rows(all_results, max_rows_cfg)
                            if _cut:
                                truncated_flag = True
                        _snap_ts = time.time()
                        _redis_written = False
                        if _mgr and prefer_cache and not is_preview:
                            _snap = redis_cache.ReportSnapshot(
                                results=all_results,
                                sql_query=sql_query,
                                updated_at=_snap_ts,
                                config_version=config_version or "",
                                truncated=_cut,
                            )
                            _mgr.set_snapshot(snapshot_key, _snap, ttl_hours=cache_ttl_hours)
                            _redis_written = True
                        cache.set(report_id, all_results, sql_query,
                                         source="redis" if _redis_written else None,
                                         source_timestamp=_snap_ts if _redis_written else None,
                                         truncated=_cut)
                        if _redis_written:
                            cache_info = {
                                "source": "redis",
                                "timestamp": _snap_ts,
                                "fresh": True,
                            }
                        else:
                            cache_info = {"source": "mysql"}
            finally:
                # 仅当本进程实际持有锁时才释放，覆盖成功/兜底/抛异常/锁等待命中快照全部路径；
                # wait_for_lock 超时未获锁（lock_held=False）时不误删他人持有的锁。
                if _mgr and lock_key and lock_held:
                    _mgr.release_lock(lock_key)

    # 越界 result 索引安全回退：clamp 到 0..len(all_results)-1（保留 -1 哨兵语义）
    if all_results:
        if active_index != -1:
            active_index = min(max(active_index, 0), len(all_results) - 1)
    elif active_index != -1:
        active_index = 0

    # PH-06 统一兜底：陈旧全量数据（缓存/快照在全量配置下写入，或写缓存前未
    # 截断的历史数据）按当前配置截断。非就地模式不污染缓存条目/快照。
    if limit_rows:
        _cut, all_results = _apply_max_rows(all_results, max_rows_cfg, inplace=False)
        if _cut:
            truncated_flag = True

    # 对每个结果集独立执行筛选、排序、分页
    report_results = []
    for i, res in enumerate(all_results):
        columns = res["columns"]
        all_rows = res["rows"]

        filtered = filter_rows(all_rows, columns, filters or [])
        if nested_filter:
            # 嵌套筛选（FR-005 与既有 filters 并存；FR-006 纯函数不污染缓存）
            filtered = filter_rows_nested(filtered, columns, nested_filter)
        sorted_rows = sort_rows(filtered, columns, sorts or [])

        total = len(sorted_rows)
        if active_index == -1 or i == active_index:
            offset = (page - 1) * page_size
            page_rows = sorted_rows[offset:offset + page_size]
        else:
            page_rows = sorted_rows

        report_results.append({
            "columns": columns,
            "rows": page_rows if (active_index == -1 or i == active_index) else sorted_rows,
            "total": total,
        })

    return ReportResult(report_results, active_index, page, page_size,
                        cache_info=cache_info, truncated=truncated_flag)


def _cache_matches_limit_policy(truncated: bool, limit_rows: bool) -> bool:
    """缓存条目/快照的 truncated 标记是否与当前截断策略一致。

    当前策略截断（limit_rows=True）→ 数据要么已截断（truncated=True）要么
    未截断（读取兜底 _apply_max_rows 会再截断）→ 均可用。
    当前策略不截断（limit_rows=False）→ 缓存若已截断（truncated=True）则
    缺行，视为不可用走重建。防止编辑报表开启「允许全部输出」后，SQL 未变
    导致进程缓存/Redis 快照 key 不变、TTL 内持续命中截断旧数据（PH-07）。
    """
    return limit_rows or not truncated


def _apply_max_rows(all_results: list[dict], max_rows: int,
                    inplace: bool = True) -> tuple[bool, list[dict]]:
    """对每个结果集独立截断至 max_rows 行。

    PH-06 全量输出护栏：allow_all_output=0 时结果集超过 max_rows 即截断。
    inplace=True 时就地修改结果集（供写缓存前截断，截断快照入缓存）；
    inplace=False 时返回新列表（供读取兜底，不污染缓存条目/快照）。
    返回 (是否发生过截断, 处理后的结果集列表)。
    """
    truncated = False
    if inplace:
        for res in all_results:
            rows = res.get("rows") or []
            if len(rows) > max_rows:
                res["rows"] = rows[:max_rows]
                truncated = True
        return truncated, all_results
    new_results = []
    for res in all_results:
        rows = res.get("rows") or []
        if len(rows) > max_rows:
            new_res = dict(res)
            new_res["rows"] = rows[:max_rows]
            new_results.append(new_res)
            truncated = True
        else:
            new_results.append(res)
    return truncated, new_results


# ===================================================================
# 页面渲染
# ===================================================================


def render_report_selector(conn) -> str:
    """渲染报表选择页面（按分类层级树状呈现）"""
    reports = db.get_all_reports(conn)
    # 按分类分组
    cat_reports: dict[int, list] = {}
    uncategorized: list = []
    for r in reports:
        cid = r.get("category_id")
        if cid is not None:
            cat_reports.setdefault(cid, []).append(r)
        else:
            uncategorized.append(r)

    all_cats = db.get_all_categories(conn)
    cat_tree = db.get_category_tree(conn)

    def _cat_depth(cat_id: int) -> int:
        d = 0
        seen = set()
        c = next((x for x in all_cats if x["id"] == cat_id), None)
        while c and c.get("parent_id") is not None:
            if c["parent_id"] in seen:
                break
            seen.add(c["parent_id"])
            d += 1
            c = next((x for x in all_cats if x["id"] == c["parent_id"]), None)
        return d

    # ── 下拉框选项（按分类树层级） ──
    def _render_tree_options(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            # 如果分类有报表或是父分类，显示为 optgroup
            if rpts or node["children"]:
                label = f"{indent}{node['name']}"
                html += f'<optgroup label="{_escape(label)}">'
                for r in rpts:
                    html += f'<option value="{r["id"]}">{_escape(r["name"])}</option>'
                if node["children"]:
                    html += _render_tree_options(node["children"], depth + 1)
                html += "</optgroup>"
            else:
                # 空分类（无报表无子分类）只显示占位行
                html += f'<option value="" disabled style="color:#94a3b8;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</option>'
                if node["children"]:
                    html += _render_tree_options(node["children"], depth + 1)
        return html

    options = _render_tree_options(cat_tree)

    # 未分类报表
    for r in uncategorized:
        options += f'<option value="{r["id"]}">(未分类) {_escape(r["name"])}</option>'

    # ── 列表视图（按分类树层级） ──
    def _render_tree_list(nodes: list[dict], depth: int = 0) -> str:
        html = ""
        for node in nodes:
            indent = "　" * depth
            cid = node["id"]
            rpts = cat_reports.get(cid, [])
            if rpts or node["children"]:
                html += f'<li class="cat-header" style="list-style:none;font-weight:600;color:#4f46e5;padding:6px 0 2px {8 + depth * 20}px;font-size:14px">{indent}📁 {_escape(node["name"])}</li>'
                for r in rpts:
                    html += f'<li style="padding:4px 0 4px {28 + depth * 20}px"><a href="/report?id={r["id"]}">{_escape(r["name"])}</a></li>'
                if node["children"]:
                    html += _render_tree_list(node["children"], depth + 1)
            else:
                html += f'<li style="list-style:none;padding:4px 0 2px {8 + depth * 20}px;color:#94a3b8;font-size:13px;font-style:italic">{indent}({_escape(node["name"])} - 无报表)</li>'
                if node["children"]:
                    html += _render_tree_list(node["children"], depth + 1)
        return html

    report_list = _render_tree_list(cat_tree)
    for r in uncategorized:
        report_list += f'<li style="padding:4px 0"><a href="/report?id={r["id"]}">(未分类) {_escape(r["name"])}</a></li>'

    # PH-09 空状态引导：无任何报表时整个列表卡片替换为三步指引
    list_card = ('<div class="card">'
                 '<h3>可用报表列表</h3>'
                 f'<ul class="report-list" style="padding-left:0">{report_list}</ul>'
                 '</div>')
    if not reports:
        list_card = ('<div class="card" style="border:1px dashed #c7d2fe;'
                     'background:#f5f7ff;padding:16px 20px;margin-top:12px">'
                     '<h3 style="margin:0 0 8px">🚀 开始使用</h3>'
                     '<p style="margin:0 0 12px;color:#475569;font-size:14px">'
                     '三步开始：① 添加连接池 → ② 创建报表 → ③ 发布 API 接口</p>'
                     '<a href="/config" class="btn btn-primary btn-sm">前往配置管理</a>'
                     '</div>')

    # 批次6#22：最近查看快捷卡片挂载点——服务端不感知 localStorage，
    # 公共 JS initRecentReports 在 DOMContentLoaded 时读取并渲染；
    # 无记录时保持空白，页面结构不受影响。
    body = _render_page_header() + """
<div id="recent-reports-mount"></div>
<div class="card">
  <h2>选择报表</h2>
  <div class="report-select">
    <form method="get" action="/report">
      <label>请选择要查看的报表：</label>
      <select name="id" onchange="this.form.submit()" style="width:100%">
        <option value="">-- 请选择 --</option>
""" + options + """
      </select>
      <noscript><button type="submit" class="btn btn-primary btn-sm" style="margin-top:10px">查看</button></noscript>
    </form>
  </div>
</div>
""" + list_card + """
""" + _FOOTER
    return body


def render_report_page(conn, report_id: int, page: int = 1,
                       page_size: Optional[int] = None,
                       pool_override: Optional[dict] = None,
                       sorts=None, filters=None,
                       refresh: bool = False,
                       cols_raw: str = None,
                       sql_override: str = None,
                       active_index: int = 0,
                       result_names_override: str = None,
                       flash: str = None,
                       report_override: dict = None) -> str:
    """
    渲染报表数据展示页，支持多字段排序/筛选/自定义列/多结果集。
    cols_raw: 原始 cols 参数字符串（如 "id,name,age"），由 execute_report 结果中的列名解析。
               为 None 表示全部显示。
    sql_override: 预览模式时替代 report["sql_query"] 的临时 SQL，不保存到数据库。
    active_index: 当前激活的结果集索引。
    flash: 操作结果提示（如 API 快捷开关回跳），None=不显示。
    report_override: 预览报表配置 dict（新建表单预览等无库中报表的场景），
                     提供后不再按 report_id 从库中读取。
    """
    if report_override is not None:
        report = report_override
    else:
        report = db.get_report(conn, report_id)
    if not report:
        return _render_page_header() + '<div class="flash flash-error">错误: 报表不存在</div>' + _FOOTER

    if page_size is None or page_size < 1:
        page_size = report["default_page_size"]

    if pool_override:
        pool_config = pool_override
    else:
        pool_id = report["pool_id"]
        if pool_id is None:
            return (_render_page_header() +
                    f'<div class="flash flash-error">该报表 "{_escape(report["name"])}" 关联的连接池已被删除。'
                    f' 请前往 <a href="/config" style="color:#4f46e5;font-weight:600">配置管理</a> 重新指定连接池。</div>' +
                    _FOOTER)
        pool_config = db.get_pool(conn, pool_id)
        if not pool_config:
            return (_render_page_header() +
                    f'<div class="flash flash-error">错误: 报表 "{_escape(report["name"])}" 关联的连接池不存在</div>' +
                    _FOOTER)

    actual_sql = sql_override or report["sql_query"]
    try:
        result = execute_report(report_id, actual_sql, pool_config,
                                page, page_size, sorts or [], filters or [], refresh,
                                active_index, report, conn,
                                read_timeout=30)
    except Exception as e:
        logging.error("报表 %d 查询执行失败: %s", report_id, e, exc_info=True)
        pool_name = pool_config.get("name", "?")
        pool_host = pool_config.get("host", "?")
        pool_port = pool_config.get("port", "?")
        pool_user = pool_config.get("user", "?")
        friendly, raw = humanize_db_error(e)
        return (_render_page_header() +
                render_sql_error_section(friendly, raw) +
                f'<div class="flash flash-error">连接池: {_escape(str(pool_name))}'
                f' ({_escape(str(pool_host))}:{pool_port}, 用户: {_escape(str(pool_user))})'
                f'</div>' + _FOOTER)

    # 越界/空结果集安全：以执行结果为准对 active_index 做上界 clamp（保留 -1 哨兵），
    # 防止调用方构造越界 ReportResult 时 result.columns 等属性抛 IndexError 导致 500。
    if result.results:
        if result.active_index != -1:
            result.active_index = min(max(result.active_index, 0), len(result.results) - 1)
    elif result.active_index != -1:
        result.active_index = 0
    active_index = result.active_index

    # 从原始 cols 字符串解析自定义列（利用 execute_report 已获取的列名）
    all_cols = result.columns
    if cols_raw:
        display_columns = _parse_cols({"cols": [cols_raw]}, all_cols)
    else:
        display_columns = None

    return _build_report_html(conn, report, result, pool_config,
                              sorts or [], filters or [], refresh,
                              display_columns, sql_override, active_index,
                              result_names_override=result_names_override,
                              flash=flash)


# ===================================================================
# HTML 构建（核心）
# ===================================================================


def _build_report_html(conn, report: dict, result: ReportResult,
                       pool_config: dict = None,
                       sorts=None, filters=None,
                       refresh: bool = False,
                       display_columns: list[str] = None,
                       sql_override: str = None,
                       active_index: int = 0,
                       result_names_override: str = None,
                       flash: str = None) -> str:
    """
    构建完整的报表 HTML，支持多结果集下拉切换。
    sorts/filters 均为列表。
    display_columns: 用户自定义的显示列列表（顺序 + 可见性），None 表示全部显示。
    sql_override: 预览模式时替代 report["sql_query"] 的临时 SQL。
    active_index: 当前激活的结果集索引。
    flash: 操作结果提示（如 API 快捷开关回跳），None=不显示。
    """
    sorts = sorts or []
    filters = filters or []
    report_id = report["id"]
    actual_sql = sql_override or report["sql_query"]
    qs_page_size = result.page_size
    all_columns = list(result.columns)
    if display_columns is None:
        display_columns = all_columns
    cols_param = _build_cols_param(display_columns, all_columns)

    # ---- 多结果集 ----
    num_results = len(result.results)
    # 解析 result_names（每行一个名称，JSON 格式字符串），补齐/截断到实际结果数
    result_names_raw = result_names_override if result_names_override else (report.get("result_names", "") or "")
    result_names = parse_result_names(result_names_raw, num_results)
    swi = ("report" if not sql_override else "report/preview")
    result_selector_html = build_result_selector_html(
        report_id, qs_page_size, result_names, active_index, sql_override, swi,
        filters=filters, sorts=sorts)

    # ---- Debug 信息、当前规则、备注均委托给 render.py 渲染 ----
    debug_html = build_debug_section_html(
        pool_config, actual_sql, active_index, num_results, result_names, filters, sorts)
    current_rules_html = build_current_rules_section_html(
        filters, sorts, display_columns, all_columns)
    memo_html = build_memo_section_html(report.get("memo") or "", report_id)

    # ---- API URL 区域 ----
    try:
        api_endpoints = db.get_api_endpoints_by_report(conn, report_id)
        # base_url 仅作服务端兜底值（无 JS 时可用）；页面加载后 JS 用
        # window.location.origin 覆盖（与 API 配置后台一致，显示用户实际访问的地址）
        base_url = app_config.get_server_base_url()
        api_urls_html = build_api_urls_section_html(api_endpoints, base_url)
    except Exception:
        api_urls_html = ""
        api_endpoints = []

    # 备注或任一 API 接口说明含 ```mermaid 块时按需注入 mermaid 渲染脚本
    # （api-desc-markdown T5；渐进增强：JS 加载失败时页面显示 <pre class="mermaid">
    # 转义源码，不空白；无 mermaid 内容时零请求）
    mermaid_sources = [report.get("memo") or ""]
    mermaid_sources += [ep.get("description") or "" for ep in api_endpoints]
    mermaid_scripts = ""
    if any(markdown_render.contains_mermaid(s) for s in mermaid_sources):
        mermaid_scripts = (
            f'<script src="{markdown_render.MERMAID_JS_URL}"></script>\n'
            '<script>if (window.mermaid) { '
            'mermaid.initialize({ startOnLoad: true, securityLevel: "strict" }); '
            '}</script>\n')

    # ---- 结果参数（多结果集时附加到 URL） ----
    result_param = f"result={active_index}" if num_results > 1 else ""

    # ---- 构建表单隐藏字段（排序、列等状态通过隐藏 input 保留） ----
    filter_form_id = "ff"
    form_hidden = [f'<input type="hidden" name="id" value="{report_id}">',
                   f'<input type="hidden" name="page_size" value="{qs_page_size}">']
    if result_param:
        form_hidden.append(f'<input type="hidden" name="result" value="{active_index}">')
    for col, dir_ in sorts:
        form_hidden.append(f'<input type="hidden" name="sort" value="{_escape(col)}">')
        form_hidden.append(f'<input type="hidden" name="dir" value="{_escape(dir_)}">')
    if cols_param:
        form_hidden.append(f'<input type="hidden" name="cols" value="{_escape(",".join(display_columns))}">')
    form_hidden_str = "\n    ".join(form_hidden)

    # ---- 排序栏、表头、数据行、缓存标记、控制栏、面板均由 render.py 渲染 ----
    sort_bar_html = build_sort_bar_html(
        report_id, qs_page_size, sorts, filters, cols_param, result_param)
    thead_str = build_table_header_html(
        all_columns, display_columns, sorts, filters, report_id, qs_page_size, cols_param, result_param)

    col_index_map = {name: idx for idx, name in enumerate(all_columns)}
    display_indices = [col_index_map[c] for c in display_columns]
    # 批次5#19：空态区分——有筛选时显示「没有符合筛选条件的行」+ 清除筛选链接
    clear_filters_href = build_clear_filters_href(
        report_id, qs_page_size, sorts, cols_param, result_param)
    tbody = build_table_body_html(result.rows, display_indices,
                                  filters=filters or None,
                                  clear_filters_href=clear_filters_href)

    pagination = _build_pagination(report_id, result.page, result.total_pages,
                                   result.page_size, result.total, sorts, filters, cols_param, result_param if num_results > 1 else "")

    cache_badge = build_cache_badge_html(result.cache_info,
        prefer_cache=bool(report.get("prefer_cache")),
        cache_ttl_hours=int(report.get("cache_ttl_hours") or 0))

    controls = build_controls_bar_html(
        report_id, qs_page_size, sorts, filters, cols_param, display_columns,
        active_index, cache_badge, result.total, result.total_pages,
        result_param=result_param, page=result.page)

    filter_action_html, clear_html = build_filter_action_html(
        report_id, qs_page_size, sorts, cols_param, result_param, filters)

    field_settings_html = build_field_settings_panel_html(all_columns, display_columns)
    sort_settings_html = build_sort_settings_panel_html(sorts, all_columns)
    filter_form_html = build_filter_form_html(filter_form_id, form_hidden_str)

    # ---- 组装最终 HTML ----
    flash_html = build_flash_html(flash) if flash else ""
    # PH-05 写操作警示条：allow_write=1 且实际 SQL 含写语句 → 页面顶部显著警示
    # （allow_write=0 时执行已被 execute_report 拦截，不会到达渲染）
    write_banner = ''
    if int(report.get("allow_write", 1) or 0) and sql_contains_write(actual_sql):
        write_banner = ('<div class="flash-warn" style="'
                        + _BANNER_STYLE + '">'
                        f'⚠️ {WRITE_ALLOWED_BANNER}'
                        '</div>')
    # PH-07 截断提示条：本次执行发生 max_rows 截断时，页面顶部提示
    # （编辑页「允许全部输出」可关闭截断；提示中的 N 取当前配置的 max_rows）
    trunc_banner = ''
    if result.truncated:
        trunc_banner = ('<div class="flash-warn" style="'
                        + _BANNER_STYLE + '">'
                        '⚠️ 结果超过 '
                        + str(int(report.get("max_rows") or 100000))
                        + ' 行，已截断显示前 '
                        + str(int(report.get("max_rows") or 100000))
                        + ' 行；如需全量输出请在编辑页开启「允许全部输出」'
                        '</div>')
    # 无库中报表的预览（新建表单预览，report_id=0）不显示编辑入口
    edit_btn = ''
    if report_id > 0:
        edit_btn = (f'<div style="margin-bottom:10px">'
                    f'<a href="/config/reports/{report_id}/edit" class="btn btn-outline btn-sm" target="_blank" rel="noopener">编辑</a>'
                    f'</div>')

    # ---- 批次6 页内脚本（spec ux-optimization）----
    # #25 列设置记忆：页面加载时按 URL cols 参数写 / 按 localStorage 读应用。
    # #22 最近查看：正式查看（非预览）成功渲染后写 sqlreport_recent；
    # 预览模式不记录（临时 SQL 不算「查看该报表」）。报表名经 _js_string
    # 安全内嵌，防 </script> 提前闭合。report_id 为 0（无库报表预览）时不注入。
    b6_scripts = ""
    if report_id > 0:
        recent_call = (f"    saveRecentVisit({int(report_id)}, "
                       f"{_js_string(report['name'])});\n"
                       if not sql_override else "")
        b6_scripts = (
            "<script>\n"
            "document.addEventListener('DOMContentLoaded', function() {\n"
            f"    applyStoredCols({int(report_id)});\n"
            f"{recent_call}"
            "});\n"
            "</script>\n")

    body = (_render_page_header(
                title=f'{_escape(report["name"])} - Web 报表工具') +
            _build_report_switcher(conn, report_id) +
            f'<div class="card">'
            f'<h2>{_escape(report["name"])}</h2>' +
            ('<div class="preview-badge flash-warn" style="'
             + _BANNER_STYLE + '">'
             '🔍 预览模式 — 当前显示的是未保存的临时 SQL 查询结果，点击筛选/排序将跳转到正式报表。'
             '</div>' if sql_override else '') +
            write_banner +
            trunc_banner +
            edit_btn +
            flash_html +
            memo_html +
            api_urls_html +
            debug_html +
            current_rules_html +
            result_selector_html +
            _build_redis_banners(result.cache_info) +
            controls +
            field_settings_html +
            sort_settings_html +
            sort_bar_html +
            filter_action_html +
            clear_html +
            filter_form_html +
            '<div class="table-wrap"><table>' + thead_str + tbody + '</table></div>' +
            pagination +
            '</div>' +
            mermaid_scripts +
            b6_scripts +
            _FOOTER)
    return body


def _build_report_switcher(conn, current_id: int = None) -> str:
    """构建报表切换下拉框（按分类层级树状呈现）"""
    reports = db.get_all_reports(conn)
    all_cats = db.get_all_categories(conn)
    cat_tree = db.get_category_tree(conn)
    return build_report_switcher_html(reports, all_cats, cat_tree, current_id)


# ===================================================================
# 入口（_build_pagination 已移至 render.py，通过别名保持 API 兼容）
# ===================================================================


def _handle_refresh_cache(conn, form_data: dict) -> tuple[int, str, dict]:
    """处理「重建缓存」POST：强制刷新缓存后 302 回跳报表页。

    回跳保留当前视图全部状态参数（page/page_size/sort/dir/filters/cols/result），
    并附带 flash 提示（复用 config 表单 POST + 回跳模式）：预填成功 →
    「缓存已重建」；报表/连接池缺失或执行异常 → 错误提示（不以成功文案
    掩盖失败，spec ux-optimization 批次1#2）。
    预填失败不影响回跳（错误在回跳后的页面展示）。
    """
    try:
        report_id = int(_qs_val(form_data, "id", "") or "")
    except (ValueError, TypeError):
        return 302, "/report", {}
    if report_id <= 0:
        return 302, "/report", {}
    report = db.get_report(conn, report_id)
    # flash 默认成功；预填未执行（报表/连接池缺失）或执行异常时改为错误提示，
    # 避免「假绿色横幅」（spec ux-optimization 批次1#2）
    refresh_ok = bool(report)
    if report:
        pool_id = report.get("pool_id")
        pool_config = db.get_pool(conn, pool_id) if pool_id else None
        if not pool_config:
            refresh_ok = False
        else:
            page = max(1, app_config.safe_int(_qs_val(form_data, "page"), 1))
            page_size = None
            parsed_page_size = app_config.safe_int(_qs_val(form_data, "page_size"), None)
            if parsed_page_size is not None:
                page_size = max(1, parsed_page_size)
            sorts = parse_sorts(form_data)
            filters = _parse_filters(form_data)
            active_index = parse_result_index(form_data)
            try:
                execute_report(report_id, report["sql_query"], pool_config,
                               page, page_size, sorts, filters, True,
                               active_index, report, conn,
                               read_timeout=30)
            except Exception as e:
                logging.warning("refresh_cache 预填失败: %s", e)
                refresh_ok = False
    # 回跳：保留视图状态参数 + flash（parse_qs → urlencode 往返保持编码一致；
    # urlencode 自动百分号编码中文，规避 latin-1 响应头限制）
    flash_msg = ("缓存已重建" if refresh_ok
                 else "错误: 缓存重建失败，数据未刷新，请稍后重试或检查数据库连接")
    keep = {"id": [str(report_id)], "flash": [flash_msg]}
    for key, vals in form_data.items():
        if key in ("page", "page_size", "sort", "dir", "cols", "result"):
            keep[key] = vals
        elif key.startswith("f_") or key.startswith("op_"):
            keep[key] = vals
    return 302, "/report?" + urllib.parse.urlencode(keep, doseq=True), {}


_OP_SYMBOLS = {"gt": ">", "lt": "<", "gte": "≥", "lte": "≤"}


def _filter_warning_flash(filters, existing_flash: str = "") -> str:
    """检测非法数值筛选并生成提示 flash（spec ux-optimization 批次1#3）。

    filter_rows 对 gt/lt/gte/lte 遇非数值条件静默跳过，用户看到的是
    「被悄悄忽略」的结果；本函数把被忽略的条件显式回传给页面。
    仅 Web 报表页调用；API / 导出路径行为不变。
    """
    bad = invalid_numeric_filters(filters)
    if not bad:
        return existing_flash
    items = "；".join(
        f"{col} {_OP_SYMBOLS.get(op, op)} {val}"
        for col, op, val in bad)
    warn = f"错误: 筛选条件 {items} 的值不是有效数字，已忽略对应条件"
    if existing_flash:
        return f"{warn}；{existing_flash}"
    return warn


def handle_request(conn, method: str, path: str, query: str,
                   form_body: str = None,
                   pool_override: Optional[dict] = None) -> tuple[int, str, dict]:
    """
    报表页面请求入口。
    解析多字段排序/刷新缓存等参数。
    支持 POST 预览模式（/report/preview），不保存配置，临时查看。
    """
    # 预览模式：不保存配置，临时以表单中的 SQL 在新窗口中查看。
    # 支持无 id（新建/复制表单预览）：POST sql_query + pool_id 构造临时报表配置，
    # allow_write 取表单值（checkbox+hidden 提交顺序为 0,1，取最后一个，与
    # parse_form_urlencoded 的重复键语义一致）。
    if path == "/report/preview" and method == "POST":
        form_data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)

        def _last(key, default=None):
            return (form_data.get(key) or [default])[-1]

        sql_override = _last("sql_query", "") or ""
        preview_result = parse_result_index(form_data)
        preview_names = _last("result_names")
        try:
            preview_id = int(_last("id", "") or "")
        except (ValueError, TypeError):
            preview_id = None
        if preview_id is not None and preview_id > 0:
            # 有 id 预览：报表配置取自库中；若表单提交了 allow_write（编辑表单
            # 开关 + hidden 保底），以表单值为准——表单开关状态与预览执行联动
            report_cfg = db.get_report(conn, preview_id)
            if report_cfg is not None and "allow_write" in form_data:
                report_cfg = dict(report_cfg)
                report_cfg["allow_write"] = int(_last("allow_write", "0") or "0")
            return 200, render_report_page(conn, preview_id, sql_override=sql_override,
                                             report_override=report_cfg,
                                             active_index=preview_result,
                                             result_names_override=preview_names or None), {}
        # 无 id：新建预览（缺少 pool_id 或 SQL 时回退报表选择页，兼容历史行为）
        pool_id_raw = _last("pool_id", "") or ""
        if not pool_id_raw or not sql_override:
            return 200, render_report_selector(conn), {}
        try:
            pool_id = int(pool_id_raw)
        except (ValueError, TypeError):
            return 200, render_report_selector(conn), {}
        preview_report = {
            "id": 0,
            "name": "新建报表预览",
            "pool_id": pool_id,
            "sql_query": sql_override,
            "default_page_size": app_config.safe_int(_last("default_page_size", "20"), 20),
            "category_id": None,
            "memo": None,
            "result_names": preview_names or "",
            "prefer_cache": 0,
            "cache_ttl_hours": 0,
            "allow_write": int(_last("allow_write", "0") or "0"),
        }
        return 200, render_report_page(conn, 0, sql_override=sql_override,
                                         report_override=preview_report,
                                         active_index=preview_result,
                                         result_names_override=preview_names or None), {}

    qs = urllib.parse.parse_qs(query, keep_blank_values=True)

    # PH-08 破坏性操作 POST 化：「重建缓存」经 POST 表单触发，GET 不再产生副作用
    if method == "POST" and path == "/report":
        form_data = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
        if _qs_val(form_data, "action") == "refresh_cache":
            return _handle_refresh_cache(conn, form_data)

    if "id" not in qs or not qs["id"][0]:
        return 200, render_report_selector(conn), {}


    try:
        report_id = int(qs["id"][0])
    except (ValueError, IndexError):
        return 200, render_report_selector(conn), {}

    page = 1
    if "page" in qs and qs["page"][0]:
        page = max(1, app_config.safe_int(qs["page"][0], 1))

    page_size = None
    if "page_size" in qs and qs["page_size"][0]:
        parsed_page_size = app_config.safe_int(qs["page_size"][0], None)
        if parsed_page_size is not None:
            page_size = max(1, parsed_page_size)

    # 多字段排序
    sorts = parse_sorts(qs)
    # 多字段筛选
    filters = _parse_filters(qs)

    # 自定义列顺序/可见性（原始参数字符串，推迟到 render_report_page 中解析）
    cols_raw = _qs_val(qs, "cols")

    # 多结果集索引
    active_index = parse_result_index(qs)

    html = render_report_page(conn, report_id, page, page_size, pool_override,
                              sorts, filters, False, cols_raw,
                              active_index=active_index, flash=_filter_warning_flash(
                                  filters, _qs_val(qs, "flash")))
    return 200, html, {}
