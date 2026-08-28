# 规格（迁移聚合）

> 本文件由 migrate_askmatt.py 从历史事件 /spec 索引与 .sessions/specs/ 聚合生成，仅供 `askill show spec` 兼容。
> 原始规格见下列链接，仍为真相源。

- [完整代码审查发现的问题清单——15 项待排查项，含问题描述、影响、排查建议、可能结果](docs/代码审查待检查清单.md)
- [SqlReport 需求规格快照——含代码审查验证的架构确认、已知待优化、产品决策](docs/SPEC.md)
- [报表备注（memo）Markdown 渲染 + 编辑预览——markdown+pygments 后端渲染、白名单 sanitize、mermaid 本地静态托管按需注入、预览端点；渲染模块单一来源可复用（description 另开）](.scratch/memo-markdown/spec.md)
- [报表页与分类管理合并——废弃 /config/categories 独立页（GET 302→/config/reports），分类操作回跳统一到报表页；分类树区块整体可折叠 + localStorage 记忆；总览页分类入口改指报表页；分类表单页取消链接回报表页](.scratch/config-reports-merge/spec.md)
- 报表备注三态折叠开关 + API 接口说明 Markdown 化——折叠区三态控件（自动/展开/折叠）localStorage 按报表/端点 id 记忆；API 说明查看页复用 render_markdown 升级为独立折叠区（替换 line-clamp toggleApiDesc）；description 编辑预览端点镜像 memo-preview；mermaid 注入条件扩展；列表摘要保持纯文本
- [API 全量获取功能规格——fetch_all 参数语义、开关、响应结构、迁移、测试用例](.scratch/archive/api-fetch-all/spec.md)
- [API 静态文件缓存规格——.json 变体、全量数据+meta 节点、TTL 随报表、miss 自愈、鉴权一致、NGINX 集成](.scratch/archive/api-static-cache/spec.md)
- [API 接口说明与操作交互优化规格——description 列+报表页说明展示（截断展开）+报表页/列表快捷开关+导航入口](.scratch/archive/api-endpoint-ux/spec.md)
- [筛选匹配表达式规格——* 通配+逗号多值 OR+\ 转义统一语法，仅 contains/eq/neq；审计页 keyword 同步；帮助内容单一来源弹窗；输入框聚焦展开+触屏适配](.scratch/archive/filter-wildcard-multivalue/spec.md)
- [产品加固改造方案（Round 1）——缓存新鲜度、API Key 多 key 化、写操作护栏、全量输出开关、UI 优化、配置页拆分；迁移号 14 由 PH-02 建立](.scratch/archive/product-hardening/spec.md)
- [「值无引号」选项定义修改（原「数字无引号」）——语义重定义为所有值裸输出不带引号、名称统一、单函数序列化替代两件套、模板模式跳过合法性校验；报表导出与 API 端点同步修改](.scratch/archive/api-json-no-quotes/spec.md)
- [「JSON 智能去引号」复选面板取代「值无引号」——3 项勾选（十进制数字/科学计数/千分位去逗号）+合法化转换链+兜底回退，输出永远合法 JSON（RFC 8259）；json_no_quotes 兼容映射全开；CSV 天然不受影响；模板保留合法性校验](.scratch/archive/smart-quotes-json/spec.md)
- [定时任务组合与排除逻辑——schedule↔report 解耦为多对多（schedule_reports 关联表，按 order_index 顺序执行）；任务级排除规则树（JSON，根 OR 多规则并行、单规则可嵌套 AND/OR，支持 dow/tod/date/date_range 叶子）；任务级审计开关 audit_enabled 默认关；覆盖基础规格 report-scheduler §3.1 数据模型](.scratch/archive/scheduler-composition-exclusion/spec.md)
- [favicon 三模式可配置（默认/纯色生成/自定义上传 PNG·ICO）+ 可选环境标题前缀；site_settings kv 表双引擎存储；base64 上传链路（原生 JS FileReader，无 multipart）；magic bytes 白名单 + 256KB 上限；审计 update_site_setting；行为契约矩阵 A-F 六组 M1-M38](.scratch/archive/site-branding/spec.md)
- [notcontains-filter](.sessions/specs/notcontains-filter.md)
- [report-scheduler](.sessions/specs/report-scheduler.md)
