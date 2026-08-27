## 背景与目标

本项目为 SqlReport，一个 Python 纯标准库加少量 pip 依赖、零框架、无构建步骤的 SQL 报表 Web 工具。入口 server.py，默认监听 0.0.0.0:8080。本次任务不开发新功能、不修复 BUG（F-001），唯一目标是通过详细阅读代码，逆向沉淀本项目的完整知识库，使此后的开发、测试任务具有完善的起点。

知识库交付物必须符合 flow 插件的文档读取规范（活的文档），能被 flow 流程直接读取（F-002）。已确认结论：交付形态等于 flow 可读活文档（SPEC 九章节加附录A contract-json 机器契约，写入 .adocs/specs/，R1-A）；覆盖范围等于全量穷尽（R2-A）；组织等于总纲主 SPEC 加模块分卷加模块级元数据加 specs/index.json 机器索引（R3-A、R4-A）；保鲜等于提交点锚定加代码改动同步约束加保鲜核对机制（R5-A）；插件增强等于本轮内双交付（R6-A）；保鲜核对落地等于流程内嵌加按需手动（flow_docs_check，R7-A）；可见性等于 .adocs/ 纳入 .gitignore 排除公开、README 不加导读（R8-B、R9-A）；历史文档素材等于 copy 目录只读、按其格式改写进知识库（R10、R11）。

本次与历史逻辑的关系：/opdev/SqlReport copy/ 存在成体系的历史知识文档（docs/SPEC.md 规格快照、vocabulary.md 符号词典、9 加 4 份 ADR、MAP.yaml、LESSONS.yaml 教训库、.scratch/ 探针等），经代码级确认与主仓 23 个 .py 源码 md5 全一致、同源可信（F-010、F-011），作为高可信采信骨架，逐条与代码真相核对、剔除过时演进标注后，按 flow 活文档格式改写进当前项目知识库（F-013、F-014）。

### 系统架构总览

（本小节为 T-002 补充的系统架构总览，内容以主仓还原后的代码真实为准——FR-010。）

**技术形态**：Python 纯标准库 `http.server` 实现的零框架 SQL 报表 Web 工具，无构建步骤、无异步框架；默认监听 `0.0.0.0:8080`。依赖面仅 `requirements.txt` 所列少量 pip 包（MySQL 驱动、redis 客户端等，均按需惰性加载）。

**请求分发链路（入口 server.py，1110 行，53 个处理器）**：
1. `ReportHandler(BaseHTTPRequestHandler)` 接收 GET/POST/HEAD/OPTIONS/PUT/DELETE/PATCH；
2. `_handle()` 解析 path 与 method，先做白名单静态服务（`/static/vendor/` 前缀，仅服务 vendor 根内文件，MIME 白名单），再查 `ROUTES` 路由表（顺序优先、首次匹配即生效）；
3. 命中 `RouteEntry(pattern, method, needs_auth, needs_db, handler)` 后：`needs_auth` 为真则 `_authenticate()`（cookie 会话校验 + 滑动过期刷新）；`needs_db` 为真则 `db.get_config_db()` 取共享连接；
4. `getattr(self, route.handler)(method, path, query, conn)` 委托给对应处理器；异常收口：`BodyReadError`→400、其余→500（详情只进日志不进响应体）；
5. 各页面处理器再将请求委托给模块层：`config.handle_request` / `report.handle_request` / `export_mod.handle_export` / `api_handler.handle_api_request` / `audit_page` 等。

**路由表（ROUTES 摘要）**：`/favicon.ico`、`/login`(GET/POST)、`/health`、`/`(首页重定向 /report)、`/logout`、`/config/api-endpoints`(GET/POST)、`/config/reports`、`/config/reports/memo-preview`(POST)、`/config/api-endpoints/description-preview`(POST)、`/config/categories`(重定向兼容)、`/config/site-branding`(POST)、`/config/*`、`/report/*`、`/export/*`、`/api/*`(API Key 鉴权，无需会话)、`/audit/*`。

**23 个源码模块职责（逐文件 docstring 提取）**：
- server.py — HTTP 服务器入口（路由分发、会话、请求日志）
- report.py — 报表页面处理（报表渲染与执行编排）
- api_handler.py — API 数据接口请求处理模块
- config.py — 配置页面处理
- config_db.py — 配置数据库 CRUD 操作（config.db/MySQL 双引擎）
- app_config.py — 应用配置文件管理（app_config.json）
- auth.py — 简易 Cookie 认证（会话 + 登录限流）
- audit_db.py — 审计数据库模块（独立 SQLite audit.db）
- audit_page.py — 审计日志页面处理
- export.py — CSV/JSON 导出功能
- query_executor.py — MySQL 查询执行器
- result_transform.py — 结果集变换模块（纯函数，无 IO）
- redis_cache.py — Redis 缓存层
- scheduler.py — 进程内报表定时调度器（report_schedules）
- branding.py — 站点标识（favicon 三模式 + 标题前缀单一实现来源）
- render.py — HTML 渲染模板层
- db.py — 数据库层（兼容适配层，从 config_db 转发导出）
- static_cache.py — API 静态文件缓存（.json 变体）
- preset_cases.py — 预设测试用例（数据夹具）一键导入
- markdown_render.py — Markdown 渲染单一来源（URL 协议白名单）
- json_template.py — API JSON 输出模板引擎（纯标准库）
- filter_help.py — 筛选语法帮助内容与渲染（全系统单一来源）
- file_permissions.py — 运行时文件权限管理（static_cache 缓存落点）

**模块依赖与调用链（AST import 实测）**：
- 顶层编排：server.py → report / config / api_handler / export / audit_page / audit_db / auth / branding / render / scheduler / static_cache / app_config / db / file_permissions；
- 页面/接口层：report、config、api_handler、export、audit_page → render（HTML 模板）、branding（站点标识）、markdown_render（Markdown）、json_template（API JSON 模板）；
- 业务/数据层：report、api_handler、config、export → query_executor（SQL 执行）、redis_cache（缓存）、result_transform（结果变换）、config_db（配置 CRUD）、static_cache（静态缓存）；
- 数据访问层：db.py（兼容适配）→ config_db.py → audit_db.py / query_executor；auth → audit_db / db；
- 支撑：scheduler（独立调度线程）→ api_handler / redis_cache / report / config_db / db；file_permissions 供 static_cache 缓存落点；filter_help 供 render；app_config 被绝大多数模块引用（配置单一来源）；
- 无内部依赖的叶模块：app_config、result_transform、branding、preset_cases、markdown_render、filter_help（纯函数/配置/工具层）。

**两套运行时数据源**：config.db（SQLite，可切换 MySQL；存连接池/报表/分类/API端点/定时任务/用户等配置数据）与 audit.db（独立 SQLite 审计库）。另：redis_cache 可选 Redis 缓存、static_cache 文件缓存（受 file_permissions 保护）。

### 模块分卷目录与统一元数据规范

（本小节为 T-003~T-008 的统一模板——FR-003/FR-004。）

**目录结构（.adocs/specs/ 下）**：
- `SPEC_v1.md` — 主 SPEC（本文件，flow 各阶段读取入口）；
- `modules/<module>.md` — 模块分卷，逐模块一份（T-003~T-007 产出 19 份：report、api_handler、query_executor、result_transform、config_db、config、app_config、auth、redis_cache、audit_db、audit_page、scheduler、server、render、branding、export、db、markdown_render、preset_cases、static_cache、filter_help、json_template、file_permissions 中除主 SPEC 已内联者外的全部源码模块，按 T-003~T-007 划分）；
- `config_system.md` / `db_schemas.md` / `ops_scripts.md` / `static_assets.md` / `readme_reconciliation.md` — 非模块类分卷（T-008 产出）；
- `index.json` — 机器索引（T-009 产出）。

**每份分卷统一元数据头（YAML front-matter，机器可读）**：
```markdown
---
module: <文件名，如 report.py>
contract_id: MOD-<模块大写下划线，如 MOD-REPORT>
version: 1.0
depends_on: [<import 依赖模块名列表>]
last_reviewed_commit: <git 提交哈希>
last_reviewed_at: <YYYY-MM-DD>
---
```

**每份分卷正文结构**（按此顺序，逐函数逐类）：
1. 职责概述（与主 SPEC 架构总览对应）；
2. 公开 API 契约：逐函数/逐类记录签名（参数/返回值/异常）、行为语义、调用方；
3. 数据流：模块内关键流程（含调用的下游模块）；
4. 依赖关系：import 矩阵 + 用途说明；
5. 边界与异常：错误形态（错误码/类型）、空值/边界处理；
6. 保鲜核对提交点：记录 last_reviewed_commit/at，供 flow_docs_check 核对。

**contract_id 命名规范**：`MOD-<模块名全大写，点转下划线>`（如 `MOD-REPORT`、`MOD-CONFIG_DB`、`MOD-API_HANDLER`）。

### README 与代码真相核对方法（FR-010）

（本小节为 T-002 补充的真相核对方法，内容以代码真实为准。）

**原则**：知识库内容一律以代码真实为准；README 宣称与代码/目录树不一致处，以代码为准并在 `readme_reconciliation.md`（T-008）逐条记录。

**已发现失真项（核对基线）**：
- README.md 与 README-CN.md 第 610 行宣称 `git-purge.sh`，实际仓库为 `git-tool.sh`（一体化 commit/push/pull/purge 脚本）——README 失真，知识库以 git-tool.sh 为准；
- README 宣称 `tests/` 目录——主仓代码还原后 tests/ 实际存在（68 个 .py 测试文件），该项已还原成立，不列入失真。

**核对流程**：每份分卷产出时（T-003~T-008）逐函数对照源码核验；历史文档（copy）采信时逐条与代码 md5/行为核对、剔除过时演进标注（如「AppContext—已清理」「错误处理已统一」等阶段性标注）；新增事实须带 source 与确认状态。

## 核心决策记录

- 决策：知识库以 flow 可读活文档形态交付，写入 .adocs/ 治理资产，采用 SPEC 九章节骨架加附录A contract-json 机器契约。decided_by: user（R1-A，F-001、F-002）
- 决策：知识库全量穷尽覆盖，包括全部源码模块（20 多个 .py）逐函数逐类 API 契约、配置体系（app_config.json）、config.db 与 audit.db schema、部署运维脚本（install.sh、manage_service.sh、git-tool.sh）、静态资源，并与 README 做真相核对，不留死角。decided_by: user（R2-A，F-003）
- 决策：知识库以总纲主 SPEC 加模块分卷附录两层组织，主 SPEC 为 flow 各阶段读取入口；每份模块分卷带统一结构化元数据（模块名、契约ID、依赖、版本），并维护 specs/index.json 机器索引，使 flow 能按需定位读取单个模块。decided_by: user（R3-A、R4-A，F-004、F-005）
- 决策：知识库建立持续保鲜机制，每份文档带最后核对提交点（git 提交哈希或日期）；在 AGENTS 与 CONTEXT 固化代码改动须同步更新知识库的流程约束；提供核对指引供 flow 定期校验文档与代码真相一致、及时发现脱节。decided_by: user（R5-A，F-006）
- 决策：插件能力增强作为显式需求（FR-006、FR-007）写入知识库契约，并在本流程 P2 开发阶段直接对 .opencode/plugins/ar-flow.mjs 增量增强（specgen 支持模块分卷解析与 specs/index.json 索引、新增按需读取与保鲜核对能力），P3 配套测试；交付等于知识库加插件能力同步就绪。decided_by: user（R6-A，F-007）
- 决策：保鲜核对的定期落地为流程内嵌加按需手动形态，插件新增 flow_docs_check 类核对工具，在 P2 开发完成、P4 交付前由流程强制调用，并支持随时手动调用；不设常驻后台调度（当前 opencode 插件环境无独立后台定时器能力）。decided_by: user（R7-A，F-008）
- 决策：README 不加知识库导读章节（本项目将发布 GitHub 开源，README 必须公开，开发约束与产品需求不希望公开）。decided_by: user（R8-B）
- 决策：.adocs/（知识库主 SPEC、模块分卷、index.json、访谈记录、flow 状态）纳入 .gitignore 排除公开，延续项目既有知识文档本地使用不提交、主仓保持可安全推送 GitHub 的约定。decided_by: user（R9-A，F-010）
- 决策：历史文档素材利用策略，/opdev/SqlReport copy/ 下所有文件必须只读、不得直接地址引用，须按其格式改写到当前项目知识库 .adocs/specs/。decided_by: user（R10、R11 自由文本，F-013、F-014）
- 决策：知识库内容以代码真实为准，README 宣称与代码或目录树不一致处（如宣称存在 tests/ 实际不存在、git-purge.sh 实为 git-tool.sh）以代码真实为准；历史文档采信须逐条与代码真相核对、剔除过时演进标注。decided_by: ai（D-005、D-024，佐证 R2-A、F-003）

## 既有代码关联（涟漪发现）

- D-001：flow 的 SPEC 读取规范等于九章节骨架（背景与目标、核心决策记录、既有代码关联、被拒绝方案、待定事项、不可违背规则、变更历史、术语表、附录A）加附录A contract-json 机器契约围栏，机器抽取为 CONTRACT_v1.json。source: doc:.adocs/prompts/v1/phase0_specgen.txt（confirmed: true）
- D-002：CONTEXT.md 已含领域词汇表（连接池、报表、分类、结果集、缓存快照、审计日志、会话、API端点、全量获取、预览、导出、多语句SQL 共 12 词条）、4 条已确认设计约束、预设测试用例能力说明。source: doc:CONTEXT.md（confirmed: true）
- D-003：项目为 Python 纯标准库加少量 pip 依赖、零框架、无构建步骤的 SQL 报表 Web 工具；入口 server.py，核心模块包括 report.py（报表渲染）、api_handler.py（API）、config_db.py（运行时配置库）、export.py（导出）、auth.py（鉴权）、audit_db.py（审计）、redis_cache.py（缓存）、scheduler.py（定时任务）、branding、render、config、query_executor、static_cache、preset_cases 等。source: code:/opdev/SqlReport 目录结构（confirmed: true）
- D-004：.adocs/specs、contracts、tasks、test 目录当前为空，无历史 SPEC 或契约沉淀，本次为全新建库流程。source: code:.adocs/ 目录勘察（confirmed: true）
- D-005：仓库无 lint、typecheck、formatter、CI、测试套件配置（AGENTS.md 明示）；且 README 声称存在 tests/ 目录但实际目录树中不存在，知识库须以代码真实为准而非 README 宣称（AGENTS.md 已知陷阱）。source: doc:AGENTS.md（confirmed: true）
- D-006：运行时数据源有两套库，config.db（SQLite 或 MySQL 双引擎，存连接池、报表、分类、API端点、定时任务）与 audit.db（独立 SQLite 审计库），知识库需逆向其表结构与字段语义。source: code:config_db.py、audit_db.py、AGENTS.md（confirmed: true）
- D-007：flow specgen 阶段产出为单份原生 Markdown SPEC（含二级标题章节与 contract-json 围栏），机器抽取为 CONTRACT_v1.json；P1 拆分、P2 开发、P3 测试、P4 交付均以这份 SPEC 为消费入口。source: doc:.adocs/prompts/v1/phase0_specgen.txt 及 phase1_split.txt 等（confirmed: true）
- D-008：.adocs/ 下已有 CONTEXT.md（含 12 领域术语词汇表）与 .adocs/specs/ 空目录，可承接知识库主 SPEC 与模块分卷。source: code:.adocs/ 目录勘察（confirmed: true）
- D-009：flow 当前 contract-json 机制是整份 SPEC 机器抽取（CONTRACT_v1.json），尚无模块级按需定位先例，模块分卷加索引是本次为满足主动按需读取新增的设计。source: doc:.adocs/prompts/v1/phase0_specgen.txt（confirmed: true）
- D-010：.adocs/ 下 specs/ 目录为空可放知识库主 SPEC、分卷、索引；tasks/ 与 flow/ 由引擎管理，不宜手动写入。source: code:.adocs/ 目录勘察（confirmed: true）
- D-011：AGENTS.md 已有 README 双语镜像须同一次提交同步改动的先例约束，可复用该模式固化代码改动须同步知识库的流程。source: doc:AGENTS.md（confirmed: true）
- D-012：仓库 git 集成工具为 git-tool.sh（一体化 commit、push、pull、purge），可承载知识库提交点核对信息。source: code:git-tool.sh（confirmed: true）
- D-013：flow 插件 specgen 的 persistSpecgen 仅写单份 SPEC_v1.md（layout.specs）加 CONTRACT_v1.json（layout.contracts），无模块分卷或模块索引支持。source: code:.opencode/plugins/ar-flow.mjs persistSpecgen（confirmed: true）
- D-014：flow 插件消费端 buildCodeContextDigest 仅列出 specs 目录下 .md 文件名（历史 SPEC 摘要），无模块级按需读取机制。source: code:.opencode/plugins/ar-flow.mjs buildCodeContextDigest（confirmed: true）
- D-015：flow 插件全文无任何文档与代码真相核对、保鲜、脱节检测相关逻辑，该能力确属缺失。source: code:.opencode/plugins/ar-flow.mjs 全文检索（confirmed: true）
- D-016：.opencode/plugins/ar-flow.mjs 为 687KB 单文件打包产物（zod 等依赖 inline），.opencode/ 下无独立 src 源码目录，增强需直接编辑打包文件。source: code:.opencode/ 目录勘察（confirmed: true）
- D-017：ar-flow.mjs 仅注册 flow_init、status、next、submit、answer、reset、freeze、regression、dispatch 等工具，无任何保鲜、核对、定时调度工具或逻辑；新增核对工具需在插件工具注册表扩充。source: code:.opencode/plugins/ar-flow.mjs 工具注册表勘察（confirmed: true）
- D-018：README.md（英文）与 README-CN.md（中文）为双语镜像，AGENTS.md 约定两者须在同一次提交中同步改动，不得只改其一。source: doc:AGENTS.md（confirmed: true）
- D-020：.gitignore 已排除 .opencode（插件源码）、docs/、SPEC.md、CONTEXT.md、.lcm/ 等，注释明示知识文档本地使用不提交、主仓保持可安全推送 GitHub，项目已有开源安全基线；R6 选的插件增强改动位于 .opencode/，天然不随 GitHub 公开。source: code:.gitignore（confirmed: true）
- D-021：.gitignore 未排除 .adocs/；当前 .adocs/ 未被 git 跟踪仅因尚未 add 或 commit，一旦纳入版本控制将随主仓公开，存在泄露缺口，需补入 .gitignore。source: code:.gitignore 加 git ls-files（confirmed: true）
- D-022：app_config.json（含凭据）、config.db、audit.db 均被 .gitignore 排除，凭据与运行库不进版本库。source: code:.gitignore（confirmed: true）

## 被拒绝方案

- （R1 拒 B）以项目内独立可读文档交付（如 docs/KNOWLEDGE_BASE.md），不必强制 flow 格式，被拒：用户要求必须符合 flow 插件读取规范、活文档。（R1-A）
- （R2 拒 B）核心链路优先，非核心模块仅关联说明，被拒：用户要求细致、毫无遗漏、完整知识库。（R2-A）
- （R3 拒 B）单份总纲式 SPEC 浓缩全部模块，被拒：全量穷尽下会臃肿难维护，违背活的文档诉求。（R3-A）
- （R4 拒 B）不另设索引，仅整份 SPEC 读取，被拒：不满足 flow 主动按需读取。（R4-A）
- （R5 拒 B）一次性交付即止、靠人工自觉维护，被拒：不满足绝不能是死文档。（R5-A）
- （R6 拒 B）知识库先行、插件增强后置为单独任务，被拒：用户要求避免文档就绪插件不知情。（R6-A）
- （R7 拒 B）插件内置独立后台定时任务定期自动核对，被拒：当前 opencode 插件环境无独立后台调度能力，不可兑现。（R7-A）
- （R8 拒 A）README 新增知识库导读章节，被拒：本项目将发布 GitHub 开源，README 必须公开，开发约束与产品需求不希望公开。（R8-B）
- （R9 拒 B）.adocs/ 选择性入库公开、剥离敏感内容，被拒：需逐份审查、成本高且仍有泄露风险，与 R8-B 逻辑一致。（R9-A）
- （R10 拒 B）历史文档仅背景参考、完全从代码重新逆向，被拒：用户原话方便知识库体系恢复工作，恢复意味捡回而非丢弃；且代码级确认历史文档与当前代码同源可信。（R10-A）

## 待定事项

- 无挂起项（pending_explanations 为空）。历史文档素材利用策略（PE-001）已由用户 round-11 自由文本明确（copy 只读加改写进知识库）。
- 提示：D-001（flow SPEC 读取规范）、D-023（旧版 MAP.yaml 机制废弃、新机制为 .adocs/specs/ flow 活文档）等 needs_confirmation=true 项已在后续轮次（R1、R3、R4、R6、R9、R10、R11）经用户确认采纳，纳入本 SPEC。

## 不可违背规则

- 知识库交付物必须符合 flow 插件的文档读取规范（活的文档），能被 flow 流程直接读取。FR-001
- 知识库全量穷尽覆盖全部源码模块逐函数逐类 API 契约、配置体系、数据库 schema、部署脚本、静态资源，并核对 README 与代码真相。FR-002
- 知识库以总纲主 SPEC 加模块分卷附录两层组织，主 SPEC 为 flow 各阶段读取入口。FR-003
- 知识库建立模块级结构化元数据加机器索引 specs/index.json，使 flow 能按需定位读取单个模块。FR-004
- 知识库建立持续保鲜机制（提交点锚定、代码改动同步约束、核对指引），防止代码演进后文档腐化成死文档。FR-005
- 本轮内同步增强 flow 插件（specgen 支持模块分卷解析与 specs/index.json 索引、新增按需读取能力）并配套测试。FR-006
- 插件新增 flow_docs_check 保鲜核对工具（比对代码 git 改动与文档最后核对提交点、报告脱节模块），P2 开发完成、P4 交付前强制调用并支持随时手动调用。FR-007
- .adocs/ 纳入 .gitignore 排除公开、不随 GitHub 主仓推送；README 保持现状不加知识库导读。FR-008
- /opdev/SqlReport copy/ 下所有文件必须只读、不得直接地址引用，须按其格式改写到当前项目知识库 .adocs/specs/。FR-009
- 知识库内容以代码真实为准（README 失真处以代码为准），历史文档采信须逐条与代码真相核对、剔除过时演进标注。FR-010

## 变更历史

- 初始创建：本次为全新建库流程（D-004），P0 六维访谈（R1 至 R9）加两轮自由文本补充（R10、R11）确认后生成本主 SPEC。
- T-002 增补：在「背景与目标」内补充三个子节——系统架构总览（入口 server.py 路由分发链路、23 模块职责、AST import 依赖矩阵、两套数据源）、模块分卷目录与统一元数据规范（front-matter + 六段正文结构 + contract_id 命名，作为 T-003~T-008 统一模板）、README 与代码真相核对方法（git-purge.sh→git-tool.sh 失真项等）。满足 FR-001/FR-003/FR-010。

## 术语表

- 知识库（KnowledgeBase）：本项目逆向沉淀的完整知识库，存放于 .adocs/specs/，以 flow 可读活文档形态交付。
- 活文档：能被 flow 各阶段主动按需读取而非仅人工可读的治理资产文档，需含机器可读结构（contract-json、模块元数据、索引）。别名：活的文档、flow 可读文档。
- 模块分卷：知识库中按模块拆分、随主 SPEC 配套的子文档，每份带结构化元数据（模块名、契约ID、依赖、版本），供 flow 按需定位读取。别名：分卷、模块子文档。
- 保鲜核对：flow 定期校验知识库文档与代码真相一致的能力，发现文档与代码脱节时及时报告。别名：定期校验、脱节检测、文档与代码真相核对。
- 历史知识资产：/opdev/SqlReport copy 目录下未入库的旧版知识文档体系（docs/SPEC.md、vocabulary.md、adr、MAP.yaml、LESSONS.yaml、.scratch 探针等），与当前代码同源（md5 一致），作为知识库恢复的只读改写素材。别名：历史文档、旧知识库、copy 文档、MAP.yaml 机制。
- 连接池：数据源连接池配置，运行期存于 config.db 或 MySQL。
- 报表：SQL 报表定义与渲染对象。
- 分类：报表或数据源分类组织。
- 结果集：SQL 查询返回的结果数据集合。
- 缓存快照：结果集在缓存（Redis 或内存）中的快照。
- 审计日志：用户操作审计记录，存于独立 SQLite audit.db。
- 会话：登录会话管理。
- API 端点：HTTP API 路由端点。
- 全量获取：获取全量数据的接口语义。
- 预览：报表结果预览。
- 导出：结果集导出功能。
- 多语句 SQL：单次提交包含多条 SQL 语句。
- 主 SPEC：flow 九章节骨架加附录A contract-json 的总纲文档，为 flow 各阶段读取入口。
- specs/index.json：机器索引，列出全部模块文档位置与契约 ID，供 flow 按需定位读取。
- flow 插件：.opencode/plugins/ar-flow.mjs，本轮内增强：模块分卷解析、index 索引、按需读取、保鲜核对。
- flow_docs_check：插件新增保鲜核对工具，比对代码 git 改动与文档最后核对提交点，报告脱节模块。

## 附录A：机器契约（本节由脚本机械抽取为 CONTRACT_v1.json）
```contract-json
{
  "FR": [
    {"id":"FR-001","desc":"知识库以 flow 可读活文档形态交付：采用 SPEC 九章节骨架加附录A contract-json 机器契约，写入 .adocs/specs/，确保后续 P1-P4 阶段可直接读取复用","priority":"must"},
    {"id":"FR-002","desc":"知识库全量穷尽覆盖：全部源码模块（20 多个 .py）逐函数逐类 API 契约、配置体系（app_config.json）、config.db 与 audit.db schema、部署运维脚本（install.sh、manage_service.sh、git-tool.sh）、静态资源，并与 README 做真相核对","priority":"must"},
    {"id":"FR-003","desc":"知识库以总纲主 SPEC 加模块分卷两层组织：主 SPEC 承载全局（背景、架构、术语表、契约索引）作为 flow 各阶段读取入口；模块分卷按模块拆分（职责、逐函数逐类 API 契约、数据流、依赖关系）作为主 SPEC 附录被引用","priority":"must"},
    {"id":"FR-004","desc":"知识库建立模块级结构化元数据加机器索引 specs/index.json（列出全部模块文档位置与契约 ID），使 flow 能按需定位读取单个模块而非整份读取","priority":"must"},
    {"id":"FR-005","desc":"知识库建立持续保鲜机制：每份文档带最后核对提交点（git 提交哈希或日期）；在 AGENTS 与 CONTEXT 固化代码改动须同步更新知识库流程约束；提供核对指引供 flow 定期校验文档与代码真相一致","priority":"must"},
    {"id":"FR-006","desc":"本轮内同步增强 flow 插件（.opencode/plugins/ar-flow.mjs）：specgen 支持模块分卷解析与 specs/index.json 索引、新增按需读取能力，并配套测试","priority":"must"},
    {"id":"FR-007","desc":"插件新增 flow_docs_check 保鲜核对工具：比对代码 git 改动与各文档最后核对提交点、报告脱节模块；在 P2 开发完成、P4 交付前由流程强制调用，并支持随时手动调用","priority":"must"},
    {"id":"FR-008","desc":".adocs/ 纳入 .gitignore 排除公开，不随 GitHub 主仓推送；README 保持现状不加知识库导读章节","priority":"must"},
    {"id":"FR-009","desc":"历史文档素材 /opdev/SqlReport copy/ 下所有文件保持只读、不得直接地址引用，须按其格式改写到当前项目知识库 .adocs/specs/","priority":"must"},
    {"id":"FR-010","desc":"知识库内容以代码真实为准：README 宣称与代码或目录树不一致处（如 tests/ 目录不存在、git-purge.sh 实为 git-tool.sh）以代码为准；历史文档采信须逐条与代码真相核对、剔除过时演进标注","priority":"must"}
  ],
  "force_rules": [
    {"fr_id":"FR-001","rule":"知识库文档必须为 flow 可读活文档：SPEC 九章节骨架加附录A contract-json 机器契约"},
    {"fr_id":"FR-005","rule":"代码改动须同步更新知识库（保鲜约束，提交点锚定）"},
    {"fr_id":"FR-008","rule":".adocs/ 不随 GitHub 公开（.gitignore 排除）；README 不加知识库导读"},
    {"fr_id":"FR-009","rule":"/opdev/SqlReport copy/ 只读，不得修改；不得直接地址引用其文件"},
    {"fr_id":"FR-010","rule":"每个 FR-ID 与事实在 SPEC 或 CONTRACT 有且仅有一处权威记载"}
  ],
  "business_entities": {
    "知识库": {"fields":["name","desc"],"required":["name"]},
    "主 SPEC": {"fields":["name","desc"],"required":["name"]},
    "模块分卷": {"fields":["name","desc"],"required":["name"]},
    "specs/index.json": {"fields":["name","desc"],"required":["name"]},
    "flow 插件": {"fields":["name","desc"],"required":["name"]},
    "flow_docs_check": {"fields":["name","desc"],"required":["name"]},
    "历史知识资产": {"fields":["name","desc"],"required":["name"]}
  },
  "relations": [
    {"subject":"主 SPEC","predicate":"包含并索引","object":"模块分卷"},
    {"subject":"specs/index.json","predicate":"索引","object":"模块分卷"},
    {"subject":"flow 插件","predicate":"按需读取","object":"主 SPEC 与模块分卷"},
    {"subject":"flow_docs_check","predicate":"核对","object":"知识库与代码真相"},
    {"subject":"知识库","predicate":"被 .gitignore 排除，不随","object":"GitHub 公开"},
    {"subject":"历史知识资产","predicate":"以只读方式采信，改写为","object":"知识库模块分卷"}
  ]
}
```