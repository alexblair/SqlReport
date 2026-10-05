# 报表即 API

## 入口

```text
handle_api_request(conn, path, method, headers, body, query_params, client_ip)
  → (status, body, headers)   # api_handler.py:55
```

- 前缀 `/api`（兼容无尾斜杠历史形态）；路由正则 `^/api/`
- GET / POST / OPTIONS；**不走 Session**

## 处理顺序（勿打乱）

1. 规范化 path，`_lookup_endpoint`（`url_path=? AND enabled=1`）
2. GET 且以 `.json` 结尾且原 path 未命中 → 剥后缀重查（`static_base`）
3. 无端点 → 404 + logging
4. OPTIONS → 204 + CORS（不跑业务鉴权体）
5. `_validate_api_key` → 401
6. POST Content-Type=json 且 body 非空解析失败 → 400；**空 body 回退预设**
7. 静态分支条件全满足 → `_handle_static_request`；否则 `_run_normal_api_request`
8. `logging.info("[API] ...")`

鉴权**始终在**静态分支之前；静态分支内**再拦写护栏**（防旧文件绕过）。

## API Key 鉴权（`_validate_api_key` :684）

```
_endpoint_valid_keys:
  表内 enabled=1 列表优先
  表有记录但全禁用 → 拒绝一切
  表无记录 → 回退 endpoint.api_key 旧列；旧列也空 → 公开放行
provided = Authorization: Bearer | ?api_key=
hmac.compare_digest 逐个比
```

Key 格式：`sk-` + `token_urlsafe(32)`。

## CORS（`_build_cors_headers` :746）

- `allowed_origins` **空 → 不设任何 CORS 头**（浏览器跨域被拦，≠允许全部）
- 含 `*` → `Allow-Origin: *` + `_CORS_BASE`
- 白名单：Origin 精确命中才回显；未命中 `{}`
- `_CORS_BASE`：Methods GET,POST,OPTIONS；Headers Content-Type,Authorization；Max-Age 86400

## 查询与覆盖

| 来源 | 可覆盖 |
|------|--------|
| 端点预设 | filters/sorts/nested_filter/row_limit/columns/output_format… |
| POST body | filters/sorts/page/page_size/limit/columns/format |
| GET query | page/page_size/limit/format/columns |
| 请求 nested_filter | **优先于**预设 |

- `fetch_all`：端点 `allow_fetch_all=0` 时忽略；开启页大小 `10**9`，`full:true`
- `refresh=1`：绕过 L1/L2 直查 MySQL
- `row_limit` 兼作默认 `page_size`（>0 则用，否则 20）
- 非法预设 nested_filter 运行期视为无（不阻断）

## 输出

| 模式 | 说明 |
|------|------|
| 默认 JSON | `{data,total,page,page_size,total_pages[,truncated][,full][,meta]}` |
| CSV | `rows_to_csv` QUOTE_MINIMAL + CRLF |
| result_mode=all | JSON 数组；**CSV → 400** |
| 模板 | `json_template.render_template`；失败 warning 回退默认 |
| 智能引号 | `serialize_smart_quotes` |
| 写拒绝 | 403 `WRITE_DENIED` |

## 静态 `.json` 缓存

```
GET xxx.json
  → resolve_file_path 防穿越
  → 报表有 pool
  → allow_write=0 且写 SQL → 回退普通链路 / 拒绝静态化（权限，沿用 sql_contains_write）
  → 或 报表 SQL 含**持久写** → 同样拒绝静态化（2026-10-05 并集追加：
    静态命中不执行任何语句，会让写被整个 TTL 短路；会话级脚本报表仍允许静态化）
  → try_read(config_version, ttl)
       hit → 200 + X-Static-Cache: hit
       miss → rebuild_static_endpoint_file → 原子落盘 → miss 头
```

- `config_version` = MD5(sql|pool|端点变换|smart_quote_flags|allow_all_output|max_rows)
- 端点无 `{{meta}}` 模板 → **版本化文件名** `*.v{ver8}.json` 判定
- 权限根：`{static_cache.dir}/api`（`file_permissions` 只管这里）
- 配置变更：`config_db._invalidate_api_static_cache*`

## 日志双轨

| 符号 | 落点 |
|------|------|
| `api_handler._log_api_call` | 仅 `logging.info` |
| `server._log_api_call` | 审计库 `type=api`，`session_user=api_key:...|anonymous` |

## 管理 UI

- 报表编辑：端点表单 / Key 管理（**Key 区必须在主 form 外**）
- 独立页 `/config/api-endpoints`（R2-D：page-head+新建按钮；列表 `div.api-row` 主行+`api-more` 展开区，收全量/静态 URL 与说明）
- 报表详情「接口」页签（R2-D 组2b）：`build_api_urls_section_html` **委托** `build_api_endpoints_list_html(return_to=…, desc_full=True, wrap_section=False)`，与列表页同一实现，toggle 回跳默认 `/report?id=N`
- 存储 URL 一律 `/api/` 前缀（`_normalize_api_url_path`）

## 易踩坑

1. 无 Key 记录+旧列空 = 公开 ≠ 表有记录全禁用
2. 改端点影响字段必须失效静态缓存
3. Key 比较禁止 `==`
4. `.json` 剥离防端点 URL 本身以 `.json` 结尾误伤
5. patch 日志时分清两套 `_log_api_call`

---
最后核对：explore-1 报告 + api_handler 源码
