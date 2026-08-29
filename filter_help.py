"""filter_help.py — 筛选语法帮助内容与渲染（全系统单一来源）

所有筛选语法的用户可见文案集中在本模块，报表页与审计页共用：

- `filter_help_content()`: 结构化内容（分区标题/说明/案例表/要点），测试断言用
- `render_filter_help()`: 渲染 `?` 入口 + 弹窗（默认收起）+ 开关 JS，
  两页各调用一次即得完整片段，零复制

文案为面向非技术用户的语言，语义与 result_transform.parse_filter_expr
实现逐条一致（多值逗号 OR、`*` 通配、`\\*`/`\\,`/`\\\\` 转义、空段忽略、
等于操作符下通配仍生效、多列 AND）。
"""

_FILTER_HELP_SECTIONS = [
    {
        "title": "多值匹配（或）",
        "desc": "用英文逗号分隔多个值，命中任一个就会显示。",
        "examples": [
            ("状态是“完成”或“失败”", "完成,失败", "两种状态都显示"),
            ("只看北京、上海、广州", "北京,上海,广州", "三个城市都显示"),
            ("名字里带“张”或“李”", "张,李", "两姓用户都显示"),
        ],
    },
    {
        "title": "通配符 *",
        "desc": "星号（*）可以代替任意内容，放在前面、中间或后面都可以。",
        "examples": [
            ("姓张的所有用户", "张*", "张飞、张丽…"),
            ("名称里包含“北京”", "*北京*", "含北京两个字的数据"),
            ("以“已发货”结尾", "*已发货", "已发货、已发货并签收…"),
        ],
    },
    {
        "title": "等于操作符",
        "desc": "操作符选“等于”时仍可使用通配符；不输入通配符则按完整内容匹配。",
        "examples": [
            ("状态恰好是“完成”", "完成", "只显示状态为“完成”"),
            ("编号恰好以 AB 开头", "AB*", "AB001、AB2024…"),
        ],
    },
    {
        "title": "不包含操作符",
        "desc": "操作符选“不包含”时，排除所有含该内容的行；通配符和多个值同样可用。",
        "examples": [
            ("排除名称里含“测试”的", "测试", "不含“测试”二字的数据"),
            ("排除北京或上海", "北京,上海", "含其中任一个的都排除"),
            ("排除以“临时”开头的", "临时*", "含“临时”开头的都排除"),
        ],
    },
    {
        "title": "特殊字符转义",
        "desc": "数据本身含有 * 、英文逗号或反斜杠时，在前面加反斜杠（\\）表示按普通字符匹配。",
        "examples": [
            ("名称里含有星号", "张\\*三", "只匹配“张*三”"),
            ("名称里含有英文逗号", "A\\,B", "只匹配“A,B”"),
            ("名称里含有反斜杠", "盘\\\\符", "只匹配“盘\\符”"),
        ],
    },
]

_FILTER_HELP_NOTES = [
    "多个筛选条件之间是“且”的关系（同时满足）。",
    "多个值之间多余的空格会自动忽略。",
    "不加通配符时按“包含”模糊匹配；多个值时命中任一个即显示。",
]

# 筛选输入框 placeholder 统一提示后缀（报表页列头 + 审计页关键字共用）
FILTER_HINT_SUFFIX = "（*通配,多值）"


# ---------------------------------------------------------------------------
# 嵌套筛选表达式帮助（FR-010：面向非技术用户，通俗易懂 + 具体场景举例）
# ---------------------------------------------------------------------------

_NESTED_FILTER_EXPR_SECTIONS = [
    {
        "title": "当前时间 now()",
        "desc": "表示“此刻这一秒”，不需要填任何参数。常用于比较时间是否晚于现在（如“过期时间晚于现在”）。",
        "examples": [
            ("只看比现在晚的数据", "now()", "相当于“此刻”这一个时间点"),
            ("开始时间晚于现在", "now()", "now() 作为比较基准"),
        ],
    },
    {
        "title": "今天零点 today()",
        "desc": "表示“今天 00:00”，不需要填参数。常用于按自然日比较（如“创建日期不早于今天”）。",
        "examples": [
            ("创建日期是今天或之后", "today()", "今天 00:00 这一时刻"),
        ],
    },
    {
        "title": "往后加一段时间 date_add(基准, 数量, '单位')",
        "desc": "在基准时间上往后加。基准填 now() 或 today()；数量填数字（可为负表示往前）；"
                "单位填 'day'（天）/ 'month'（月）/ 'year'（年）。",
        "examples": [
            ("7 天之后的数据", "date_add(now(),7,'day')", "现在往后推 7 天"),
            ("3 个月前之后", "date_add(now(),-3,'month')", "支持负数表示往前推"),
        ],
    },
    {
        "title": "往前减一段时间 date_sub(基准, 数量, '单位')",
        "desc": "在基准时间上往前减，参数与 date_add 相同。",
        "examples": [
            ("30 天前的数据", "date_sub(now(),30,'day')", "现在往前推 30 天"),
            ("1 年前之前", "date_sub(today(),1,'year')", "今天往前推 1 年"),
        ],
    },
    {
        "title": "文本模糊匹配",
        "desc": "值里直接写文字即可“包含”匹配；在文字前后加 * 可当作通配符（* 代替任意内容）。",
        "examples": [
            ("姓名里含“张”", "张", "包含“张”字即命中"),
            ("姓名以“李”开头", "李*", "“李”后面接任意内容"),
            ("状态以“已发货”结尾", "*已发货", "任意内容 + “已发货”"),
        ],
    },
    {
        "title": "比较大小（数字/日期）",
        "desc": "操作符选“大于/小于/大于等于/小于等于”时，值填数字或日期（如 2026-01-01），"
                "也可填 now()/date_add(...) 等表达式做时间比较。",
        "examples": [
            ("金额大于 1000", "1000", "配合“大于”操作符"),
            ("到期日晚于 7 天后", "date_add(now(),7,'day')", "动态日期比较"),
        ],
    },
]


def nested_filter_help_content() -> dict:
    """返回嵌套筛选表达式帮助的结构化内容（单一来源，渲染与测试共用）。"""
    return {
        "sections": _NESTED_FILTER_EXPR_SECTIONS,
    }


def render_nested_filter_help_popup() -> str:
    """渲染嵌套筛选表达式帮助的“共享弹窗”（FR-009/FR-010）。

    仅返回弹窗本体（id=nf-help-popup）+ 开关函数 toggleNestedHelp(btn)；
    条件构建器中每个值输入框旁的「?」按钮调用 toggleNestedHelp 打开此同一弹窗，
    避免重复渲染多份大段 HTML。默认收起，点击页面其他区域自动关闭。
    """
    sections_html = ""
    for sec in _NESTED_FILTER_EXPR_SECTIONS:
        table_rows = ""
        for row in sec["examples"]:
            table_rows += "<tr>"
            for col_idx, val in enumerate(row):
                if col_idx == 1:
                    table_rows += (f"<td><code style=\"font-family:monospace;background:#f1f5f9;"
                                   f"padding:1px 6px;border-radius:4px;white-space:nowrap\">{val}</code></td>")
                else:
                    table_rows += f"<td>{val}</td>"
            table_rows += "</tr>"
        sections_html += (
            f'<div style="margin-top:10px">'
            f'<div style="font-weight:600;color:#334155">{sec["title"]}</div>'
            f'<div style="color:#64748b;margin:2px 0 4px">{sec["desc"]}</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<tr style="color:#94a3b8;text-align:left"><th style="padding:2px 4px;font-weight:600">想筛选</th>'
            f'<th style="padding:2px 4px;font-weight:600">填写</th>'
            f'<th style="padding:2px 4px;font-weight:600">含义</th></tr>'
            f'{table_rows}'
            f'</table>'
            f'</div>'
        )

    return f"""
<div id="nf-help-popup" style="display:none;position:absolute;z-index:999;
  width:380px;max-width:85vw;background:#fff;border:1px solid #e2e8f0;border-radius:8px;
  box-shadow:0 10px 30px rgba(0,0,0,.15);padding:14px 16px;margin-top:6px;
  text-align:left;font-size:13px;line-height:1.6">
  <div style="font-weight:700;margin-bottom:4px">表达式填写帮助（无编程基础也能用）</div>
  <div style="color:#64748b;margin-bottom:6px">值输入框可直接填文字做模糊匹配，或填下列动态表达式。</div>
  {sections_html}
  <div style="text-align:right;margin-top:8px">
    <button type="button" class="btn btn-sm btn-primary" onclick="toggleNestedHelp(this)">知道了</button>
  </div>
</div>
<style>
.nf-help-btn:hover {{ border-color:#4f46e5; color:#4f46e5; }}
</style>
<script>
function toggleNestedHelp(btn) {{
  var pop = document.getElementById('nf-help-popup');
  if (!pop) return;
  // 把弹窗挂到触发按钮所在容器，保证定位正确
  if (pop.parentNode !== btn.parentNode) btn.parentNode.appendChild(pop);
  if (pop.style.display === 'none' || !pop.style.display) {{
    pop.style.display = 'block';
  }} else {{
    pop.style.display = 'none';
  }}
}}
document.addEventListener('click', function (e) {{
  var pop = document.getElementById('nf-help-popup');
  if (pop && !e.target.closest('.nf-help-btn') && !e.target.closest('#nf-help-popup')) {{
    pop.style.display = 'none';
  }}
}});
</script>"""



def filter_help_content() -> dict:
    """返回结构化帮助内容（单一来源，渲染与测试共用）。"""
    return {
        "sections": _FILTER_HELP_SECTIONS,
        "notes": _FILTER_HELP_NOTES,
    }


def render_filter_help() -> str:
    """渲染筛选语法帮助片段：? 入口 + 弹窗（默认收起）+ 开关 JS。

    报表页筛选操作区与审计页筛选表单旁各调用一次，两页共用同一
    内容源与渲染函数。弹窗默认收起（display:none），点击 ? 展开，
    点击弹窗内“知道了”或页面其他区域收起。
    """
    sections_html = ""
    for sec in _FILTER_HELP_SECTIONS:
        table_rows = ""
        for row in sec["examples"]:
            table_rows += "<tr>"
            for col_idx, val in enumerate(row):
                if col_idx == 1:
                    table_rows += f"<td><code style=\"font-family:monospace;background:#f1f5f9;padding:1px 6px;border-radius:4px;white-space:nowrap\">{val}</code></td>"
                else:
                    table_rows += f"<td>{val}</td>"
            table_rows += "</tr>"
        sections_html += (
            f'<div style="margin-top:10px">'
            f'<div style="font-weight:600;color:#334155">{sec["title"]}</div>'
            f'<div style="color:#64748b;margin:2px 0 4px">{sec["desc"]}</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<tr style="color:#94a3b8;text-align:left"><th style="padding:2px 4px;font-weight:600">想筛选</th>'
            f'<th style="padding:2px 4px;font-weight:600">输入</th>'
            f'<th style="padding:2px 4px;font-weight:600">效果</th></tr>'
            f'{table_rows}'
            f'</table>'
            f'</div>'
        )

    notes_html = "".join(f"<li>{n}</li>" for n in _FILTER_HELP_NOTES)

    return f"""
<div class="filter-help" style="position:relative;display:inline-block">
  <button type="button" class="filter-help-btn" onclick="toggleFilterHelp(this)"
    title="筛选语法说明" style="width:24px;height:24px;border-radius:50%;border:1px solid #cbd5e1;
    background:#fff;color:#475569;font-size:13px;font-weight:700;line-height:1;
    cursor:pointer;display:inline-flex;align-items:center;justify-content:center">?</button>
  <div class="filter-help-popup" style="display:none;position:absolute;right:0;top:100%;z-index:999;
    width:360px;max-width:80vw;background:#fff;border:1px solid #e2e8f0;border-radius:8px;
    box-shadow:0 10px 30px rgba(0,0,0,.15);padding:14px 16px;margin-top:6px;
    text-align:left;font-size:13px;line-height:1.6">
    <div style="font-weight:700;margin-bottom:4px">筛选语法说明</div>
    {sections_html}
    <ul style="margin:10px 0 10px;padding-left:18px;color:#475569">{notes_html}</ul>
    <div style="text-align:right">
      <button type="button" class="btn btn-sm btn-primary" onclick="toggleFilterHelp(this)">知道了</button>
    </div>
  </div>
</div>
<style>
.filter-help-btn:hover {{ border-color:#4f46e5; color:#4f46e5; }}
.filter-help-popup td {{ padding:2px 4px; vertical-align:top; }}
.filter-help-popup th {{ border-bottom:1px solid #e2e8f0; }}
</style>
<script>
function toggleFilterHelp(btn) {{
  var pop = btn.closest('.filter-help').querySelector('.filter-help-popup');
  if (pop.style.display === 'none' || !pop.style.display) {{
    pop.style.display = 'block';
  }} else {{
    pop.style.display = 'none';
  }}
}}
document.addEventListener('click', function (e) {{
  if (!e.target.closest('.filter-help')) {{
    document.querySelectorAll('.filter-help-popup').forEach(function (p) {{ p.style.display = 'none'; }});
  }}
}});
</script>"""
