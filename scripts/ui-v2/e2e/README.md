# 报表页交互 E2E 脚本（CDP，需本地实例）

这些脚本用 headless Chrome + CDP 驱动**真实页面**，覆盖「点在浏览器里才暴露」的交互问题
（历史上多次踩坑：类名对不上导致点不动、遮罩盖全屏、字段顺序不发参数、JS 注释写坏整块脚本）。

前置：
```bash
# 1) 启动本地实例（仓库根，venv）
HOST=127.0.0.1 PORT=8099 venv/bin/python server.py &
# 2) 启动 headless Chrome（CDP 端口自选，需与 CDP_PORT 一致）
/opt/chrome-offline/chrome-linux64/chrome --headless=new --no-sandbox \
  --remote-debugging-port=9411 --user-data-dir=run-logs/ui-v2/.chrome-e2e about:blank &
```

运行（`CDP_PORT` 必填，与 Chrome 启动端口一致）：

| 脚本 | 覆盖 | 命令 |
|---|---|---|
| `e2e-combo.mjs` | 字段可见性 / 字段顺序 / 筛选 / 排序 / 组合叠加（cols 是否被清空） | `CDP_PORT=9411 node scripts/ui-v2/e2e/e2e-combo.mjs` |
| `e2e-export.mjs` | 导出格式 × 字符集 × ZIP × 智能去引号 × 自定义列 交叉选择 | `CDP_PORT=9411 node scripts/ui-v2/e2e/e2e-export.mjs` |
| `panel-check.mjs` | 字段设置 / 排序设置抽屉、导出对话框 能开能关（ESC） | `CDP_PORT=9411 node scripts/ui-v2/e2e/panel-check.mjs` |
| `veil-check.mjs` | 全站「有没有全屏遮挡物」（遮罩/抽屉/对话框默认必须隐藏） | `CDP_PORT=9411 node scripts/ui-v2/e2e/veil-check.mjs` |
| `sort-check2.mjs` | 排序在缓存报表与 20 万行报表上都生效、耗时 | `CDP_PORT=9411 node scripts/ui-v2/e2e/sort-check2.mjs` |
| `swap-reinit.mjs` | **无刷新换页后**拖拽/排序/导出联动/嵌套筛选是否仍可用（换页重初始化回归） | `CDP_PORT=9411 node scripts/ui-v2/e2e/swap-reinit.mjs` |
| `repro-sort-broken.mjs` | 用户复现步骤：隐藏列→应用→还原→应用→再排序 | `CDP_PORT=9411 node scripts/ui-v2/e2e/repro-sort-broken.mjs` |
| `api-row-expand-check.mjs` | `/config/api-endpoints` 展开/收起（整页+换页态+多轮+组合）、两处分类树折叠、详情页接口页签 | `CDP_PORT=9411 node scripts/ui-v2/e2e/api-row-expand-check.mjs`（可加 `BASE=http://127.0.0.1:8098`） |

注意：这些脚本默认连 `http://127.0.0.1:8099`，账号 `admin/admin123`（DEBUG 配置库默认账号）；
`api-row-expand-check.mjs` 支持 `BASE=` 覆盖（可用于另起的验证实例）。
脚本属于开发期资产，**不参与 unittest discover**（需要浏览器），但与 `tests/test_ui_tokens.py` 的
静态门禁互补：门禁管「规则/类名/令牌/对比度」，E2E 管「点下去真的有反应、结果真的变了」。

## 写/读这些脚本的坑（否则会得出假绿/假红）

1. **拖拽语义是「插到目标项之前」**：`drag(i, i+1)` 和「拖到自己身上」都是 no-op。
   要证明拖拽生效必须**反向拖**（如 `drag('#sortList', 1, 0)`）或跨项拖。
   （实测：排序项 0→1 顺序不变，曾被误读为「换页后拖拽失效」。）
2. **`children` 会被占位元素污染**：`#sortList > .sort-empty` 存在时下标整体错一位；
   统一用 `.sort-item` 之类的语义选择器。
3. **存在性判据只选「始终渲染」的东西**：`toggleResultIndex` 只在多结果集报表输出，
   单结果集页 `typeof` 是 `undefined`（不是缺陷）。`swap-reinit.mjs` 因此改用始终存在的
   页面胶水函数（`applyFieldSettings`/`applySortSettings`/`openPanel`/`navigateTo`）。
4. **`Page.navigate` 会清空 `window.*`**：自定义测试钩子要每次重新注入（`ensureTools()`）。
5. **登录态要新鲜**：陈旧 cookie 会拿到登录页 HTML，此时所有断言都无意义。
6. **改完 `render.py`/`report.py`/`config.py` 必须重启服务再跑**：页面内联 JS 由内存直出。
