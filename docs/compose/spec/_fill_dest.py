#!/usr/bin/env python3
"""回填 ui-redesign-inventory.md 的「新方案去向」列（T3 映射，一次性）。"""
from pathlib import Path

# 键：章节标题（文件中的 ## / ### 行） → {首列键: 去向}
M = {}

M["## 1. 路由级条目（server.py ROUTES，全 17 行）"] = {
    "R1": "保留（favicon 机制不变，视觉随 branding 令牌化）",
    "R2": "重构→/login（统一视觉；限流/过期/next 语义不变）",
    "R3": "保持（非 UI）",
    "R4": "保持（302→报表中心）",
    "R5": "移位→侧栏底部账户区入口（URL 不变）",
    "R6": "重构→API 接口列表页（同 URL，行卡片+展开布局）",
    "R7": "重构→报表配置页（同 URL，左树右表+浮出批量条）",
    "R8": "保留（fetch 预览协议不变，挂载编辑表单备注区）",
    "R9": "保持（重定向不变；锚点改左树选中定位并保留兼容）",
    "R10": "保留（fetch 预览协议不变，挂载端点说明区）",
    "R11": "移位→概览页设置区块（POST 不变）",
    "R12": "重构→config 子页群：概览收窄、池/用户独立列表、调度表单拆页",
    "R13": "重构→报表中心 + 报表详情（Tab 化）；refresh/preview 协议不变",
    "R14": "合并→统一导出对话框（GET 参数协议不变）",
    "R15": "保持（非页壳）",
    "R16": "重构→审计页（统一筛选条组件，参数不变）",
    "R17": "保持（机制不变）",
    "E1": "保留（连接池表单按钮，协议不变）",
    "E2": "移位→概览 DEBUG 区块（同现状，视觉统一）",
    "E3": "重构→统一错误页（令牌化+返回入口）",
}

M["### 2.1 `/login` 登录页"] = {
    "登录表单": "保留（并入统一表单组件）",
    "`next` 回跳": "保持（协议不变）",
    "错误/过期/限流状态": "保留（统一状态条组件）",
    "独立页壳": "删除（紫渐变独立壳废除，登录并入全站令牌布局）",
    "版本页脚": "改名→页脚显示产品名+版本（branding 感知）",
}

M["### 2.2 `/report`（无 id）报表选择页"] = {
    "分类树状下拉": "重构→报表中心左分类树（点击筛选右网格）；紧凑切换 select 仅留详情页头部",
    "最近查看卡片": "重构→报表中心顶部卡片横排（空则隐藏，key 不变）",
    "分类树选择器": "合并→报表中心（左树+右卡片网格，单一入口）",
}

M["### 2.3 `/report?id=` 报表详情页（核心页）"] = {
    "报表切换器": "重构→详情头部紧凑 select + 报表中心入口（整宽切换卡废除）",
    "Redis 横幅": "重构→状态横幅（仅异常出现，人话文案）",
    "flash 提示": "保留（统一 flash 组件换装）",
    "备注 memo": "重构→Tab「备注」+数据页单行摘要；三态开关删除（按报表记忆保留为折叠态）",
    "调试区": "移位→Tab「调试」",
    "当前规则区": "合并→Tab「规则」（与嵌套构建器/排序列表合一）",
    "API URL 区": "移位→Tab「接口」（复制组件统一）",
    "控制栏": "重构→数据页工具行（主操作=刷新；导出入对话框；设置入抽屉）",
    "导出内联 form": "合并→统一导出对话框（参数协议不变，选项常显）",
    "排序条": "保留→数据页排序 chips 行（组件换装）",
    "结果表格": "重构→通用数据表组件（吸附表头/列排序/快速筛选/帮助收敛保留）",
    "分页": "保留→通用分页组件（跳转防误触）",
    "字段设置面板": "重构→右侧抽屉（遮罩+ESC+焦点管理）",
    "排序设置面板": "重构→右侧抽屉（与列设置同组件族）",
    "嵌套筛选构建器": "合并→「高级筛选」抽屉（可视化构建/规则预览双视图）",
    "结果集 tab": "重构→数据页结果集分段控件（多结果集状态协议不变）",
    "缓存徽标与重建": "重构→轻量缓存状态行 + 刷新确认（术语翻译，refresh 协议不变）",
    "截断横幅": "保留→状态横幅组件（文案统一）",
    "写护栏横幅": "保留→状态横幅组件（三端同文案保持）",
    "非法筛选 flash": "保留（协议不变，组件换装）",
    "接口说明折叠": "移位→Tab「接口」端点说明卡；三态删除（默认展开）",
    "锚点行高亮": "保留（行为不变，样式令牌化）",
    "loading 遮罩": "扩展→全站提交遮罩（导出下载除外）",
}

M["### 2.4 `/report/preview` 与编辑页联动"] = {
    "未保存 SQL 预览": "保留→SQL 分区工具组按钮",
    "查看-编辑双向关联": "保留→统一操作组位置（详情头部 / 编辑底栏）",
    "memo 预览": "保留→备注区 fetch 预览",
}

M["### 2.5 `/export` 导出"] = {
    "导出触发": "合并→统一导出对话框（唯一入口；GET 协议与参数不变）",
    "格式/字符集/ZIP/智能去引号": "保留→对话框字段组（常显，废除 popover 藏匿）",
    "截断标记": "保持（非 UI）",
}

M["### 2.6 `/config` 配置门户（render_overview）"] = {
    "首部署引导": "移位→报表中心空态 + 概览空态（文案复用）",
    "连接池列表区": "移位→/config/pools 独立列表页",
    "用户列表区": "移位→/config/users 独立列表页",
    "报表管理卡": "合并→概览统计磁贴+快捷入口（大卡片留白废除）",
    "分类管理卡": "合并→概览统计磁贴（分类管理在报表配置页左树）",
    "API 接口卡": "合并→概览统计磁贴+快捷入口（内嵌清单废除）",
    "站点标识区": "保留→概览设置区块（表单组件换装）",
    "DEBUG 测试数据卡": "保留→概览 DEBUG 区块（仅 DEBUG）",
    "flash": "保留（组件换装）",
}

M["### 2.7 `/config/pools` 连接池表单"] = {
    "新增/编辑/复制表单": "保留→/config/pools 表单页（分区：连接信息）",
    "测试连接": "保留（结果统一为行内状态条）",
    "删除": "保留（统一确认弹层+破坏半径披露）",
    "上下移动": "保留→列表排序模式（组件换装）",
}

M["### 2.8 `/config/users` 用户表单"] = {
    "新增/编辑/删除": "保留→/config/users 表单页（会话约束不变）",
    "保存双按钮": "重构→sticky 底栏「保存/保存并关闭/取消」（全站表单统一）",
    "flash 防泄露": "保持（约束不变）",
}

M["### 2.9 `/config/reports` 报表列表页（render_reports_page）"] = {
    "分类树区块": "移位→页左栏常驻分类树（独立折叠区块废除）",
    "报表行操作": "重构→查看/编辑主链接 +「更多」菜单收纳复制/删除/移动",
    "徽标": "重构→文字徽标「定时」「保活」（emoji 废除）",
    "备注摘要": "保留（悬停全文）",
    "前端过滤框": "保留→页头搜索框（组件换装）",
    "批量操作": "重构→选中后底部浮出批量条（功能全保留）",
    "分类管理区块": "移位→左栏树节点操作（增删改名/排序/新增子类）",
    "锚点定位": "改名→左树选中定位（URL 锚点兼容保留）",
}

M["### 2.10 报表编辑表单（/config/reports/add|edit|copy）"] = {
    "SQL 编辑器": "保留→SQL 分区（Tab 缩进/格式化/高亮/预览按钮组保留）",
    "字段": "合并→「基础」+「SQL」分区",
    "全量输出护栏": "移位→「输出护栏」分区（逻辑不变）",
    "定时执行折叠区": "移位→「调度与保活」分区（完整管理链调度页）",
    "缓存保活折叠区": "移位→「调度与保活」分区",
    "API 端点区": "移位→「API 端点」分区（Key 区仍在主 form 外）",
    "保存": "重构→sticky 底栏三键（save/save_close 协议映射不变）",
}

M["### 2.11 `/config/api-endpoints` 与端点表单"] = {
    "全局接口列表": "重构→行卡片+展开（主 URL 优先，次要 URL 收起）",
    "端点表单": "重构→分区表单（基本信息/请求与输出/模板/预设与 Key）",
    "模板预览": "保留→模板分区实时预览",
    "接口说明": "保留→说明字段（fetch 预览保留）",
    "Key 管理": "保留→独立 Key 区块（主 form 外门禁保持）",
    "真实数据预览": "保留→基本信息区按钮",
    "静态缓存状态": "保留→请求输出区状态行（术语翻译）",
}

M["### 2.12 `/config/scheduler` 定时任务页"] = {
    "任务列表": "重构→列表主导（行卡片，信息分级）",
    "单任务操作": "保留（按钮换装；删除入「更多」）",
    "任务表单": "拆分→/config/scheduler/new 与 /{id}/edit 独立表单页",
    "排除规则编辑器": "保留→表单内组件（分组树交互统一）",
    "全局停用横幅": "保留→页顶状态横幅（人话文案）",
    "🔇 徽标": "改名→「含静默窗口」文字徽标（emoji 废除）",
}

M["### 2.13 `/audit` 审计页"] = {
    "筛选": "重构→统一筛选条组件（参数与语义不变）",
    "日期快捷": "保留→筛选条内快捷 chips",
    "分页 + 导出 CSV": "保留（导出入操作区按钮）",
    "清理": "保留（统一确认+危险分级）",
    "进页轮转": "保持（非 UI）",
}

M["## 3. 跨页面共享交互约定（新方案须保留或显式改造）"] = {
    "C1": "保持（整页刷新模式；抽屉/对话框为页内增强）",
    "C2": "保留→统一 flash 组件（剥参逻辑不变）",
    "C3": "重构→统一确认弹层（仍基于 build 组件，无框架；文案模板化）",
    "C4": "保持（checkbox 协议不变）",
    "C5": "重构→sticky 底栏三键（save/save_close 语义映射）",
    "C6": "保留（key 不变；三态记忆改为普通折叠记忆）",
    "C7": "扩展→全站提交遮罩（导出排除；统一封装自提交）",
    "C8": "重构→公共 JS 统一事件初始化（减少内联 onclick）",
    "C9": "语义保持；帮助入口重构→统一帮助抽屉（内容源 filter_help 不变）",
    "C10": "保持（URL 协议）",
    "C11": "保留（渲染链不变；样式并入令牌）",
    "C12": "保留（编辑表单 SQL 分区）",
    "C13": "重构→侧栏导航 `_NAV_GROUPS`（替代顶栏 `_NAV_ITEMS`，一处改原则不变）",
    "C14": "重构→侧栏+内容区页壳（仍单一来源；extra_css 保留）",
    "C15": "重构→设计令牌化公共 CSS（合成/ensure_common_assets 保留；hash 覆盖 CSS+JS）",
    "C16": "重构→JS 单一外链加载（废除报表页内联双轨）",
    "C17": "保留（行为不变）",
    "C18": "保留（公共 copyToClipboard）",
    "C19": "保留→通用空态组件（文案统一）",
    "C20": "保持（htmlcheck 门禁）",
    "C21": "保持",
    "C22": "重构→统一错误页（同令牌）",
    "C23": "保持",
    "C24": "保持",
    "C25": "保持",
}

M["### 4.1 CSS / JS 资产"] = {
    "`_BASE_CSS`": "合并→`_TOKENS_CSS`（reset/fadeUp 并入令牌体系）",
    "`_COMMON_CSS`": "重构→令牌化重写（合成链机制保留）",
    "`_MD_CSS`": "保留（并入 Markdown 分区样式，追加顺序约定不变）",
    "`_MINIBTN_CSS` / `_FLASH_WARN_CSS` / `_B6_CSS`": "合并→统一按钮/提示令牌组件（切片与 btn-mini 变体废除）",
    "`_COMMON_JS`": "重构→公共初始化器集合（折叠/复制/flash/过滤/最近/列记忆/loading/Tab 功能保留）",
    "`_SQL_HIGHLIGHT_JS`": "保留",
    "`_SQL_FORMATTER_JS`": "保留",
    "`ensure_common_assets`": "保持（机制不变）",
}

M["### 4.2 通用组件"] = {
    "`render_navbar` / `_NAV_ITEMS`": "重构→`render_sidebar` / `_NAV_GROUPS`（顶栏废除）",
    "`render_page_header` / `render_page_footer`": "重构→侧栏页壳（`$` 转义约定保留）",
    "`build_flash_html`": "保留（换装）",
    "`build_empty_row_html`": "保留（换装）",
    "`build_pagination_html`": "保留（换装+跳转防误触）",
    "`build_config_filter_box_html`": "保留→搜索框组件",
    "`build_delete_form_html`": "保留→统一确认弹层封装",
    "`build_move_buttons_html`": "保留→排序模式显隐",
    "`build_collapse_section_html`": "保留（分区折叠场景沿用）",
    "`build_state_span`": "保留→状态徽章（颜色+图标+文字双编码）",
    "`build_schedule_flags_badge_html`": "改名→文字徽标（定时/保活/含静默窗口）",
}

M["### 4.3 报表页组件"] = {
    "`build_sort_params` / `build_filter_params` / `build_cols_param` / `build_nested_filter_param`": "保持（URL 协议）",
    "`build_redis_banners_html`": "重构→状态横幅（仅异常出现）",
    "`build_debug_section_html`": "移位→Tab 调试",
    "`build_nested_filter_builder_html`": "合并→高级筛选抽屉",
    "`build_current_rules_section_html`": "合并→Tab 规则",
    "`build_memo_section_html`": "重构→Tab 备注+数据页摘要（三态废除）",
    "`build_result_selector_html`": "重构→结果集分段控件",
    "`build_cache_badge_html`": "重构→缓存状态行（术语翻译）",
    "`build_sort_bar_html`": "保留→排序 chips 行",
    "`build_table_header_html` / `build_table_body_html`": "重构→通用数据表组件（吸附/排序/快速筛选保留）",
    "`build_controls_bar_html`": "重构→数据页工具行 + 统一导出对话框",
    "`build_field_settings_panel_html`": "重构→列设置抽屉",
    "`build_sort_settings_panel_html`": "重构→排序抽屉（同组件族）",
    "`build_filter_form_html` / `build_clear_filters_href` / `build_filter_action_html`": "保留→快速筛选行组件（清除入工具行）",
    "`build_report_switcher_html`": "重构→详情头部紧凑 select（整卡废除）",
    "`build_api_urls_section_html`": "移位→Tab 接口",
}

M["### 4.4 配置页组件"] = {
    "`build_pool_form_html` / `build_pool_section_html`": "form 保留→分区表单；section 移位→/config/pools 列表页",
    "`build_user_form_html` / `build_user_section_html`": "form 保留→分区表单；section 移位→/config/users 列表页",
    "`build_category_opts_html` / `build_category_manage_section_html` / `build_category_section_html`": "opts 保留；manage 移位→报表配置左树；section 删除（分组表废除，右栏统一列表）",
    "`build_api_endpoints_list_html`": "重构→行卡片+展开列表",
    "`build_api_endpoint_form_html`": "重构→分区表单",
    "`build_api_endpoint_preview_help_html`": "保留→表单内帮助",
    "`build_api_key_manage_html`": "保留（主 form 外门禁保持）",
    "`render_audit_page`": "重构→统一筛选条+通用表格",
    "`build_scheduler_page_html` / `build_scheduler_task_form_html`": "page 重构→列表主导；form 拆分独立表单页",
}

M["## 5. README「功能特性」46 项 → UI 承载映射"] = {
    "连接池管理（CRUD/调序/复制）": "移位→/config/pools 独立页（视觉统一）",
    "用户管理（PBKDF2）": "移位→/config/users 独立页",
    "报表配置（SQL/池/页大小/备注/分类/复制）": "重构→编辑表单分区",
    "分类树管理（无限层级/调序）": "移位→报表配置页左栏树",
    "批量操作（删除/缓存/池/分类、全选反选）": "重构→浮出批量条（功能全保留）",
    "SQL 格式化 & 高亮预览 + 未保存预览": "保留→SQL 分区",
    "分页表格（内存分页/总页数/跳转）": "保留→通用分页组件",
    "悬浮表头": "保留→通用表格吸附表头（sticky+阴影令牌化重设计完成）",
    "多字段排序（列头+面板）": "保留→排序 chips + 排序抽屉",
    "多字段筛选（10 操作符+统一语法+帮助）": "保留→快速筛选 + 高级筛选抽屉 + 统一帮助抽屉",
    "字段设置（拖拽/显隐）": "重构→列设置抽屉",
    "CSV 导出（BOM）": "保留→统一导出对话框",
    "JSON 导出（智能去引号面板）": "保留→导出对话框选项组",
    "字符集切换（GBK/UTF-8）": "保留→导出对话框",
    "ZIP 压缩包": "保留→导出对话框",
    "多结果集 tab（独立筛选排序）": "保留→结果集分段控件（状态协议不变）",
    "报表即 API（Key/CORS/预设/模板）": "保留→端点分区表单 + Key 区块",
    "API 静态文件缓存（.json）": "UI 保留→请求输出区状态；非 UI 部分保持",
    "配置存储双引擎": "保持（非 UI）",
    "站点标识（favicon/前缀）": "保留→概览设置区块（视觉统一）",
    "三层查询缓存": "保留→缓存状态行 + 状态横幅 + 调试分区（术语翻译）",
    "报表定时执行（完整调度能力）": "重构→调度列表 + 独立表单页 + 编辑「调度与保活」分区",
    "缓存保活": "移位→编辑「调度与保活」分区 + 列表保活徽标",
    "编辑-查看双向关联": "保留→统一操作组位置",
    "健康检查端点": "保持（非 UI）",
    "API 接口独立管理页": "重构→行卡片列表（同 URL）",
    "Session 滑动过期": "保持（登录过期提示语义）",
    "导出支持排序": "保持（协议）",
    "全量输出护栏（开关/max_rows/横幅）": "保留→编辑「输出护栏」分区 + 详情状态横幅",
    "事务性 SQL 执行": "保持（非 UI）",
    "错误日志独立输出": "保持（非 UI）",
    "审计日志自动轮转": "保持（非 UI；/audit 展示不变）",
    "ThreadingHTTPServer": "保持（非 UI）",
    "全局异常兜底": "重构→统一错误页",
    "Redis 可观测性": "保持（非 UI）",
    "纯标准库": "保持（约束）",
    "预设/JSON 模板（README 独立章节）": "保留→端点模板分区 + 概览 DEBUG 卡",
    "筛选语法说明（filter_help）": "保留→统一帮助抽屉（内容源不变）",
    "审计四类 type + 筛选导出清理": "保留→审计页筛选条与操作区",
    "登录限流/过期/next": "保留→登录页（协议不变）",
}


def main():
    path = Path(__file__).resolve().parent / "ui-redesign-inventory.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    section = None
    replaced = 0
    errors = []
    for i, line in enumerate(lines):
        s = line.rstrip("\n")
        if s.startswith("## ") or s.startswith("### "):
            section = s
            continue
        if "待 T3" not in s or not s.startswith("|"):
            continue
        # 解析表格行
        raw = s[1:] if s.startswith("|") else s
        # 去掉行尾 |
        if raw.endswith("|"):
            raw = raw[:-1]
        cells = [c.strip() for c in raw.split("|")]
        if len(cells) < 3:
            errors.append(f"L{i+1}: 列不足: {s[:80]}")
            continue
        key = cells[0]
        table = M.get(section)
        if table is None:
            errors.append(f"L{i+1}: 未知章节 {section!r}")
            continue
        if key not in table:
            errors.append(f"L{i+1}: 章节 {section!r} 无键 {key!r}")
            continue
        new_val = table[key]
        if not cells[-1].startswith("待 T3") and "待 T3" not in cells[-1]:
            errors.append(f"L{i+1}: 末列不含待 T3")
            continue
        if cells[-1] != "待 T3" and "（待 T3）" not in cells[-1] and cells[-1] not in (
            "待 T3（非 UI，保持）", "待 T3（非页壳保持）", "待 T3（机制保持）",
            "待 T3（非 UI 保持）", "待 T3（语义保持，帮助入口重设计）",
            "待 T3（协议保持）", "待 T3（门禁保持）", "待 T3（保持）",
            "待 T3（非 UI 部分保持）", "待 T3（非 UI 保持）", "待 T3（约束保持）",
        ) and "列头吸附" not in cells[-1]:
            errors.append(f"L{i+1}: 未预期末列值 {cells[-1]!r}")
            # 仍继续替换
        cells[-1] = new_val
        lines[i] = "| " + " | ".join(cells) + " |\n"
        replaced += 1

    # §6 勾选去向项
    for i, line in enumerate(lines):
        if "- [ ] 「新方案去向」无空缺" in line:
            lines[i] = line.replace("- [ ] ", "- [x] ")

    path.write_text("".join(lines), encoding="utf-8")
    print(f"replaced={replaced}")
    if errors:
        print("ERRORS:")
        for e in errors:
            print(" ", e)
    else:
        print("no errors")


if __name__ == "__main__":
    main()
