---
module: static-assets
contract_id: SPEC-STATIC-ASSETS
version: 2
depends_on: [T-002]
last_reviewed_commit: a579d19
last_reviewed_at: 2026-08-28T18:30:00+08:00
---

## 1. 职责概述

SqlReport 的静态资源目录 `static/` 存放前端 JS/CSS 库。当前结构：仅含 `vendor/` 子目录，无自定义静态资源（HTML/CSS/JS 均内联在 Python 模块中生成）。

**目录结构**：
```
static/
└── vendor/
    └── mermaid@11.16.1/   # Mermaid.js 流程图渲染库
        └── mermaid.min.js # 3.5MB，版本锁定11.16.1
```

## 2. 公开 API 契约

### 2.1 static/vendor/mermaid@11.16.1/

| 属性 | 值 |
|------|-----|
| 文件 | `mermaid.min.js` |
| 大小 | ~3.5MB |
| 版本 | 11.16.1（内容 hash 版本锁目录） |
| 来源 | CDN 下载后本地托管 |
| 用途 | 渲染 Markdown 中的 mermaid 流程图 |

**设计原则**：
- **版本锁目录**：目录名包含版本号 `@11.16.1`，升级时创建新目录，确保缓存失效
- **本地托管**：不依赖外部 CDN，离线可用，内网部署友好
- **渐进增强**：JS 加载失败时显示 `<pre class="mermaid">` 源码，不阻断页面

### 2.2 mermaid 集成架构

```
用户输入 Markdown（含 ```mermaid 块）
        ↓
markdown_render.py → _render_with_mermaid()
    ↓ 提取 mermaid 块 → 占位符
    ↓ 其他 Markdown 渲染
    ↓ 替换占位符 → <pre class="mermaid">…</pre>
        ↓
HTML 输出
        ↓
浏览器加载 /static/vendor/mermaid@11.16.1/mermaid.min.js
        ↓
mermaid.initialize({ startOnLoad: false, securityLevel: "strict" })
mermaid.run({ nodes: document.querySelectorAll('.mermaid') })
        ↓
流程图渲染到 SVG
```

### 2.3 关键配置常量

```python
# markdown_render.py
MERMAID_VENDOR_VERSION = "11.16.1"
MERMAID_JS_URL = f"/static/vendor/mermaid@{MERMAID_VENDOR_VERSION}/mermaid.min.js"
```

## 3. 数据流

```
static/vendor/mermaid@11.16.1/mermaid.min.js
        ↓
server.py → /static/vendor/mermaid@11.16.1/mermaid.min.js
        ↓
browser → 加载 mermaid.min.js
        ↓
mermaid.run() → 渲染 <pre class="mermaid"> 元素
```

## 4. 依赖关系

| 依赖方 | 依赖方式 | 说明 |
|--------|----------|------|
| `markdown_render.py` | 输出 `<pre class="mermaid">` | 渲染流程图占位符 |
| `config.py` | 备注预览页加载 mermaid | 表单预览渲染流程图 |
| `render.py` | 报表页加载 mermaid | 报表渲染流程图 |
| `report.py` | 注入 mermaid 脚本标签 | 按需加载 mermaid |
| `server.py` | 注册 `/static/` 路由 | 静态文件服务 |

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| mermaid.min.js 加载失败 | 显示 `<pre class="mermaid">` 源码，不阻断 |
| mermaid 块语法错误 | mermaid.run() 跳过该元素，控制台报错 |
| 无 mermaid 内容 | 不注入 `<script>` 标签，零请求 |
| 版本升级 | 创建新目录 `mermaid@12.x.x/`，更新 `MERMAID_VENDOR_VERSION` |

## 6. 测试覆盖

| 测试文件 | 覆盖场景 |
|----------|----------|
| `tests/test_markdown_render.py` | mermaid 块渲染、转义、多块处理、`contains_mermaid()` 判定 |
| `tests/test_config.py` | 备注预览页 mermaid 渲染 |
| `tests/test_report.py` | 报表页 mermaid 脚本注入 |
| `tests/test_server.py` | mermaid 静态文件服务、路径安全校验 |

## 7. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | static/vendor/mermaid@11.16.1/ 目录存在 | a579d19 |
| CP-002 | mermaid.min.js 文件完整性 | a579d19 |
| CP-003 | markdown_render.py mermaid 渲染逻辑 | a579d19 |
| CP-004 | 测试覆盖 mermaid 场景 | a579d19 |
