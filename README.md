<div align="center">

# 🐬 SqlReport

### SQL in. Reports & APIs out. — Zero dependencies, one command.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-brightgreen)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-1%20(pip)-blueviolet)](requirements.txt)
[![Framework](https://img.shields.io/badge/framework-none-important)](https://docs.python.org/3/library/http.server.html)
[![MySQL](https://img.shields.io/badge/MySQL-5.7%20%2F%208.0-orange)](https://www.mysql.com/)

Pure Python 3 stdlib · No framework · No build step · Single-process deploy

```
git clone https://github.com/alexblair/SqlReport.git && cd SqlReport
./install.sh && source venv/bin/activate
python server.py
```

**In 60 seconds: open a browser, log in, write one SQL — your teammates get a web report they can filter, sort and export; third-party systems get an HTTP API.**

[Features](#-features) · [Quick Start](#-quick-start) · [中文文档](./README-CN.md) · [English](./README.md)

</div>

---

## 💡 Why another tool?

> You just want a **page for your business folks to look at data**, and an **endpoint for third-party systems to fetch data**.
> You don't want to deploy a "BI stack" that needs Postgres + Redis + Celery + a headless browser,
> you don't want to carry weekly ops overhead just for a couple of charts, and you definitely don't want to build a full web application.

**SqlReport does exactly one thing: it turns your SQL into web reports and HTTP APIs.**
It is built for people who write SQL — developers, ops engineers, data engineers, and SQL-literate analysts.

- 🚀 **Absurdly light to deploy**: 1 pip package, `python server.py` and it runs. No Docker, no JVM, no Node, no build step
- 📡 **Report-as-API**: one SQL is both a web report and an authenticated, CORS-enabled HTTP API endpoint any system can call
- ⚡ **High concurrency without burning resources**: 3-layer cache (process / Redis / DB) + API static file cache — append `.json` to an endpoint URL and serve a pre-computed static file, NGINX-ready
- 🔒 **Compliance out of the box**: full audit log, PBKDF2 password hashing, sliding-expiry sessions, transactional SQL execution, MIT license — no AGPL baggage

### Where we fit / Positioning vs. mainstream open-source BI

| | **SqlReport** | Metabase | Apache Superset | Redash |
|---|---|---|---|---|
| Target user | **People who write SQL** | Non-technical business users | Data teams | SQL analysts |
| Deployment | 1 Python file + 1 pip package | JVM app + metadata DB | Web + Postgres + Redis + Celery + headless browser | Web + Postgres + Redis + workers |
| Time to first report | **Minutes** (just one SQL) | Minutes | Hours (semantic layer first) | Minutes |
| Report-as-API | ✅ Native (API Key + CORS + templates) | Needs extra dev | Needs extra dev | Needs extra dev |
| API static cache / NGINX direct serve | ✅ Native (`.json` variant) | ❌ | ❌ | ❌ |
| Query cache layers | ✅ Process + Redis + DB fallback | In-process | Redis | Redis |
| Charts & visualizations | ❌ Table-first (deliberate choice) | ✅ 25+ chart types | ✅ 40+ chart types | Basic charts |
| Audit log | ✅ Built-in | Paid tier | Needs setup | Partial |
| License | **MIT** | AGPL (often banned by legal depts) | Apache 2.0 | BSD-2 (stalled) |
| Maintenance | Actively developed | Active | Active | Mostly stalled |

> **Why no charts?** Over 80% of internal reporting needs are "look at data, filter, sort, export" — tables + filtering + sorting + export already cover that.
> Rather than shipping a mediocre chart library and going head-to-head with Superset, we polish the table experience to the extreme and keep API the differentiator that nobody else has.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Connection Pool Mgmt** | Visual CRUD for MySQL connection pools with reorder and copy |
| **User Management** | Multi-user support with salted PBKDF2-SHA-256 password hashing |
| **Report Configuration** | Custom SQL, bind pool, page size, memo, category; with copy support |
| **Category Tree** | Unlimited depth categories, tree-indented display, reorder/add/rename/delete |
| **Batch Operations** | Batch delete reports, batch update cache/pool/category, select all/deselect per category |
| **SQL Formatter & Preview** | One-click SQL formatting, toggle syntax-highlighted preview, live-preview unsaved SQL |
| **Paginated Tables** | In-memory pagination with total pages and page jump |
| **Sticky Table Header** | Column header stays fixed at the top of the table container while scrolling long result sets, so column names remain visible |
| **Multi-column Sorting** | Click column headers, multi-column combo sort with management panel |
| **Multi-field Filtering** | 10 operators (contains/not-contains/eq/neq/gt/lt/gte/lte/is-empty/not-empty); values support `*` wildcard, comma multi-value (OR), `\` escaping — one shared syntax across report/export/API/audit pages |
| **Column Settings** | Drag-and-drop column reorder, show/hide fields |
| **CSV Export** | Full dataset export with UTF-8 BOM for Excel compatibility |
| **JSON Export** | JSON format export with optional smart no-quotes panel (decimal numbers / scientific notation / thousands-separated numbers) — output always stays valid JSON |
| **Charset Selection** | GBK or UTF-8 encoding for exports |
| **ZIP Compression** | Package export results as ZIP archive |
| **Multi Result Sets** | One multi-statement SQL returns several result sets, each in its own tab with independent filter/sort state |
| **Report-as-API** | Publish any report as an HTTP API: API Key auth, CORS, JSON/CSV output, preset rules, request override, custom JSON templates |
| **API Static File Cache** | Append `.json` to endpoint URL for static full output (zero query/compute), auto rebuild on miss, NGINX serve-ready |
| **Dual Config Engine** | SQLite or MySQL for config storage, switchable via `app_config.json` |
| **Site Branding** | Configurable favicon (built-in / solid-color generated / custom PNG·ICO upload ≤256KB) plus optional tab-title environment prefix (e.g. `[DEV] `) to tell deployments apart at a glance; stored in an instance-local SQLite file so multiple deployments sharing one config database stay independent; changes go live on the next page refresh after saving |
| **3-Layer Query Cache** | L1 process memory (300s TTL) → L2 Redis snapshot (versioned keys + distributed lock) → L3 DB direct (Redis fallback) |
| **Scheduled Reports** | Standalone scheduled tasks bound to one or many reports (ordered execution), exclusion windows (silent windows with `dow`/`tod`/`date`/`date_range` rules, nested AND/OR, multiple rules OR-ed together), configurable misfire policy (skip / run-once per day), per-task audit switch (off by default), 5-consecutive-failure circuit breaker, manual trigger & management page `/config/scheduler`, full audit trail |
| **Cache Keepalive** | For cache-enabled reports, proactively rebuilds the Redis snapshot when its remaining TTL drops below the configured lead time, so the first request never pays the rebuild cost (requires report-level caching and an available Redis) |
| **Report-Editor Link** | Jump from report view to editor, preview unsaved SQL in real time |
| **Health Check** | `GET /health` returns JSON status (status + uptime), no auth required |
| **API Endpoint Indep. Mgmt** | Standalone page `/config/api-endpoints` with global list & linked report |
| **Session Sliding Expiry** | 24h TTL, refreshed on each request, persisted via SQLite across restarts |
| **Export with Sorting** | CSV/JSON exports apply current sort state (consistent with report view) |
| **Output Limit Guard** | Per-report "allow all output" switch (new reports default off, existing default on); when off, results beyond `max_rows` (default 100,000) are truncated consistently across report page / export / API, with a page banner and `truncated` / `X-Export-Truncated` markers |
| **Transactional SQL** | Multi-statement execution wrapped in BEGIN/COMMIT/ROLLBACK, full rollback on failure |
| **Error Log Output** | Configurable separate log file for WARNING+ level messages |
| **Audit Log Rotation** | Configurable retention days, auto-cleanup on startup and page visits |
| **ThreadingHTTPServer** | Multi-threaded HTTP server for better concurrency |
| **Global Error Handler** | Uncaught exceptions render a 500 error page instead of crashing |
| **Redis Observability** | All silent exceptions (`except: pass`) upgraded to structured logging |
| **Pure Stdlib** | Python stdlib plus a minimal set of required pip packages (see below) |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- MySQL 5.7+ / 8.0+

### Installation

```bash
# Clone the repo
git clone https://github.com/alexblair/SqlReport.git
cd SqlReport

# One-click setup (venv + deps)
./install.sh

# Activate venv, then start the server
source venv/bin/activate
python server.py
```

The `install.sh` script creates a virtual environment and installs all dependencies from `requirements.txt` automatically. Manual installation works too:

```bash
python3 -m venv venv
source venv/bin/activate

# Install external dependencies
pip install -r requirements.txt
# Or manually: pip install mysql-connector-python redis markdown pygments
#   - mysql-connector-python: MySQL query connector (required)
#   - redis: Redis snapshot cache (optional, set "enable": true in app_config.json)
#   - markdown: Markdown → HTML rendering (required, for report memo and other Markdown content)
#   - pygments: Syntax highlighting for code blocks (required, powers the codehilite extension)
```

The server listens at `http://0.0.0.0:8080` by default (overridable via the `HOST` / `PORT` env vars or the `server` section of the config file).

The API static file cache directory `static_cache/` is created automatically on first cache write (no manual setup); in production, consider including it in your backup/cleanup strategy. Its location can be changed via `static_cache.dir` in `app_config.json` (relative path or **external absolute path**, see the "API Static File Cache" section below).

### First Login

Open your browser and navigate to `http://localhost:8080`, then log in with the default admin account:

| Username | Password |
|----------|----------|
| `admin`  | `admin123` |

> ⚠️ **Please change the password immediately after first login!**

After login, go to the `/config` portal page and use the entry cards to configure connection pools, users, reports, and categories.

---

## 🔧 Configuration File

The application uses `app_config.json` (or the `CONFIG_FILE` env var) to select the config database engine.

The `config_db` field supports a **list of configurations**, toggled via the `enable` flag. The legacy single-dict format is still supported.

### Full Example

`static_cache.dir` accepts a relative path or an external absolute path (e.g. `/var/cache/sqlreport_static`); the directory is created automatically on first write.

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "trust_xff": false
    },
    "static_cache": {
        "enable": true,
        "dir": "static_cache"
    },
    "config_db": [
        {
            "enable": true,
            "engine": "mysql",
            "host": "127.0.0.1",
            "port": 3306,
            "user": "root",
            "password": "your_password",
            "database": "sqlreport_config"
        },
        {
            "enable": false,
            "engine": "sqlite3",
            "path": "config.db"
        }
    ]
}
```

`server.trust_xff` (default `false`): the client IP in audit logs is taken from the socket peer address by default; set it to `true` only when deployed behind a trusted reverse proxy (e.g. Nginx that overwrites `X-Forwarded-For`) to trust the first IP in that header, preventing client IP spoofing.

In MySQL mode, an optional `socket` key specifies a Unix socket path (mutually exclusive with `host`/`port`):

```json
{
    "enable": true,
    "engine": "mysql",
    "socket": "/var/run/mysqld/mysqld.sock",
    "user": "root",
    "password": "your_password",
    "database": "sqlreport_config"
}
```

### Log Configuration

```json
{
    "log": {
        "enable": false,
        "path": "run.log"
    },
    "error_log": {
        "enable": false,
        "path": "error.log"
    }
}
```

- `log.enable` — `true` enables regular file logging, `false` disables (default)
- `log.path` — log file path, defaults to `run.log` (project root)
- `error_log.enable` — `true` enables a separate error log file (WARNING and above), `false` disables (default)
- `error_log.path` — error log file path, defaults to `error.log`
- Logs include startup info, request records and error messages

### Audit Log Configuration

```json
{
    "audit_db": {
        "path": "audit.db",
        "retention_days": 90
    }
}
```

- `path` — audit database file path, defaults to `audit.db`
- `retention_days` — retention days (0 = keep forever); expired records are cleaned up on startup and on every audit page visit

### Scheduler Configuration

```json
{
    "scheduler": {
        "enable": false
    }
}
```

- `scheduler.enable` — `true` starts the background report scheduler with the web server; `false` (default) keeps it off. When disabled, existing schedule configs are kept but never auto-executed, and the `/config/scheduler` page shows a banner
- Tasks are managed on `/config/scheduler`: each task has a name and binds one or more reports (`schedule_reports`, executed sequentially by `order_index`; a binding can be disabled individually). One report may appear in multiple tasks
- Exclusion windows ("silent windows") define when a task must NOT run: rules are stored as a JSON tree (`exclusions`) supporting leaf types `dow` / `tod` (midnight-crossing aware) / `date` / `date_range`, nested `AND`/`OR` groups, multiple rules OR-ed together. A hit skips execution, marks the task `skipped` and advances `next_run_at`; invalid trees never silence (fail-open). Manual trigger ignores exclusions
- Per-task audit switch (`audit_enabled`, off by default): when off no `scheduler`-type audit records are written; when on, runs / skips / misfires are logged as `scheduled_run` / `scheduled_skip` / `scheduled_misfire`
- Schedule behavior is configured per report on the report edit form ("⏰ Scheduled execution" section): interval minutes or daily time, misfire policy, on/off switch
- On startup the scheduler scans overdue tasks once: if the missed moment falls inside an exclusion window it counts as a correct skip (advance only, no catch-up); otherwise `interval` tasks merge into a single catch-up run and `daily` tasks follow their misfire policy (`skip` advances to the next day and logs a `scheduled_misfire` audit record, `run_once` re-runs at most once that day)
- A schedule is suspended automatically after 5 consecutive failures (circuit breaker); a manual trigger from `/config/scheduler` bypasses it, and a successful run restores auto dispatch
- Cache keepalive ("♻ Cache keepalive" section) requires the report to have Redis caching enabled; when a snapshot's remaining TTL falls below the lead seconds, the scheduler rebuilds it in the background

> ⚠️ `app_config.json` contains credentials and is in `.gitignore` — do not commit.

---

## 📄 API JSON Output Template

API endpoints support a custom JSON output structure: an admin maintains a JSON template on the endpoint config page, with `{{placeholders}}` referencing data values. **Leaving it empty = default output** (`{"data": ..., "total": N, ...}`).

### Usage

Start from the default JSON and change key names/positions. For example, output only the data array and total count:

```json
{
  "count": {{total}},
  "items": {{data}}
}
```

Rendered result:

```json
{"count": 42, "items": [{"id": 1, "name": "张三"}, ...]}
```

### Placeholders

The placeholder key set follows the **result set output mode**:

- **single (one result set)**: `{{data}}` data array, `{{total}}` row count, `{{page}}` page number, `{{page_size}}` page size, `{{total_pages}}` total pages, `{{full}}` full marker, `{{meta}}` static cache meta
- **all (all result sets)**: `{{results}}` result set array (each item has name/data/total/page/page_size/total_pages), `{{mode}}` mode (fixed "all"), `{{page}}`, `{{page_size}}`, `{{full}}`, `{{meta}}`

Rules:

- **Fields absent from the template are not output**; the default output includes `"full": true` only on `fetch_all` — add `{{full}}` manually in a template if needed
- A missing key within the set outputs `null` (e.g. `{{meta}}` is null when there is no meta on the normal path); **placeholders outside the key set are rejected on save** (the page reports the line/column)
- **Templates are not supported for CSV** (form disabled); if template rendering fails at runtime, it falls back to the default output without breaking the endpoint
- Static cache integration: template text changes are included in the config_version calculation, invalidating and rebuilding the `.json` static variant; the `meta` node is emitted when the template contains `{{meta}}`, and omitted otherwise

### Live Preview

On the endpoint edit page (for already-saved endpoints), the "Live preview with real data" button executes a real query using the **unsaved** template and rules (filter/sort/column selection) from the current form (at most 3 rows, not persisted, no impact on the live endpoint) and shows the rendered result in the preview area; an invalid template shows a structured error with line/column position, a failed query shows a structured error message. New (unsaved) endpoints do not have this button.

### Smart no-quotes

The API endpoint form offers a **smart no-quotes** checkbox panel (all off by default, sharing the same implementation as the identically named option of report JSON export). It replaces the old "value no-quotes" toggle (removed): quotes are stripped only from string values that match the checked shapes, instead of from **every** value:

| Shape | Examples |
|---|---|
| Decimal number (with optional sign) | `9.999`, `-1.5`, `007` → `7`, `+5` → `5` |
| Scientific notation | `1e5`, `1E+5`, `1e-3`, `007e5` → `7e5` |
| Thousands-separated number | `1,000` → `1000`, `-1,234.50` → `-1234.50` |

Values matching a checked shape are unquoted and normalized (commas / leading `+` / leading zeros removed — text-level operations that never go through float/int, no precision loss), then validated against the RFC 8259 number grammar; forms that fail validation after normalization fall back to quoted strings. **The output is always valid JSON (RFC 8259).** Native int/float always render as numbers regardless of the panel; Decimal columns (MySQL DECIMAL) render as bare numbers whenever any shape is checked (flags>0), and stay quoted when none is checked; values containing non-numeric text (dates, empty strings, `true`/`false`/`null`, …) always stay quoted. It applies to both the default output structure and custom JSON templates (which keep validating the rendered JSON when the panel is on — opposite to the old mode, which skipped validation); CSV output is unaffected; the static cache `.json` variant is automatically invalidated and rebuilt when the flags change (included in the config_version calculation). Legacy `json_no_quotes=1` URL parameter still maps to the full panel for compatibility; the legacy database column is converted once by migration 15 (=1 → full panel, 0b111) and reset to 0 — it no longer drives runtime behavior, the panel is the single control for quotes; the panel shows three checkboxes (decimal / scientific / thousands) stored as the `smart_quote_flags` bitmap.

The API endpoint form also offers a **description preview**: the "Interface Description" textarea supports Markdown (headings/lists/tables/code blocks/```mermaid diagrams) with a **Preview** button that renders it live via `POST /config/api-endpoints/description-preview` (mirrors the report memo preview, render-only, no DB writes); the same single `render_markdown` pipeline drives both the editor preview and the report-page display.

---

## 📄 API Static File Cache

For high-concurrency, high-traffic scenarios, **static output** is provided: append `.json` to an API endpoint URL to access the endpoint's static cache file — on hit, the file bytes are returned directly with zero queries, zero computation, zero Redis access.

### How it works

- **Content**: full dataset (fetch_all semantics, `page:1`, `page_size:total`, `total_pages:1`, `full:true`) + top-level `meta` node, compatible with the original API output structure (only an extra `meta` key)
- **Hit conditions**: file exists + config version (SQL/connection pool MD5) matches + not expired
- **Self-healing on miss**: if the file is missing, expired, or deleted by a third party, the full API pipeline (Redis → MySQL) runs automatically and rebuilds the file — the caller never notices
- **Auth**: identical to the normal API — an endpoint with an empty `api_key` is public; otherwise the key is required (`Authorization: Bearer` header or `?api_key=` param), missing/wrong keys return 401
- **Response header**: `X-Static-Cache: hit|miss` tells whether the request hit the cache; `Content-Type: application/json; charset=utf-8`
- **GET only**: POST requests, CSV-format endpoints and non-200 responses never participate

### Usage

```bash
# Static cache path (first miss → falls back to compute and rebuilds; subsequent requests hit directly)
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers.json"
# Normal API (no static cache) stays the same
curl -H "Authorization: Bearer sk-XXXX" "https://your-host/api/customers"
```

Normal API requests support `refresh=1` (strict value check: `true`/`1`/`yes`, case-insensitive) to **bypass the L1/L2 cache, re-query MySQL and write the result back** into the cache — useful when callers must always get the latest data; combinable with `fetch_all`. The static `.json` variant **ignores `refresh`** and keeps serving the cached file while valid.

Example response body:

```json
{
  "data": [...],
  "total": 1000,
  "page": 1,
  "page_size": 1000,
  "total_pages": 1,
  "full": true,
  "meta": {
    "generated_at": "2026-08-04 18:30:22 +0800",
    "expires_at": "2026-08-05 18:30:22 +0800",
    "last_invalidated_at": null,
    "config_version": "a1b2c3d4e5f6..."
  }
}
```

`meta` fields (times are server-local, second precision):

| Field | Description |
|---|---|
| `generated_at` | File generation time |
| `expires_at` | Expiry = generation time + report `cache_ttl_hours`; `null` when `cache_ttl_hours=0` (permanent) |
| `last_invalidated_at` | The moment this cache path was last judged invalid: recorded on rebuild due to version mismatch/expiry; carried over on rebuild due to missing file (first run/third-party deletion); `null` when no record |
| `config_version` | Internal field: config version MD5 (SQL + connection pool + endpoint columns/filters/sorts/row limit/JSON template), used for hit determination; any change invalidates and rebuilds automatically |

### Configuration

```json
"static_cache": {
    "enable": true,
    "dir": "static_cache"
}
```

- `enable`: global switch, default `true`
- `dir`: static file storage directory, accepts a **relative path or external absolute path** (default `static_cache`). Resolution goes through `os.path.realpath()`; absolute paths like `/var/cache/sqlreport_static` are used as-is, relative paths like `../external_cache` resolve against the process working directory. Either way the directory is **auto-created** on first cache write (`os.makedirs(exist_ok=True)`). On write failure (e.g. permission denied, disk full) the system only logs `logging.warning` and falls back to the normal API path — regular requests are unaffected.
- **No independent TTL**: expiry follows the linked report's `cache_ttl_hours` exactly (0 = never expires, only manual cleanup/config changes invalidate)
- Endpoint-level switch: the "Static file cache (.json variant)" checkbox on the API endpoint form (enabled by default) can disable it per endpoint
- **Invalidation linkage**: "Rebuild cache" on the report page and "Disable cache" in batch cache config delete the corresponding static files (deletion = invalidation; the next `.json` request lazily rebuilds)

### Cache File Permissions

When the program runs as root, `.json` cache files are created with `0600 root:root` by default (`tempfile.mkstemp`), which non-root processes like NGINX cannot read when serving them directly (see next section). Use the `file_permissions` config section to specify the owner and permission bits of the cache directory/files; on startup the whole cache directory tree is refreshed once, and all new files are created with the configured permissions:

```json
"file_permissions": {
    "enable": true,
    "user": "nginx",
    "group": "nginx",
    "dir_mode": "0755",
    "file_mode": "0644"
}
```

- `enable`: off by default; when off or the whole section is missing, behavior is identical to before this feature existed
- `user` / `group`: owner/group of the cache directory and files (name or numeric uid/gid), resolved at startup
- `dir_mode` / `file_mode`: optional, octal strings (JSON has no octal literals); default `0755` / `0644`. Directories need `x` (NGINX must traverse), files need `r` (NGINX must read)
- With only `user`/`group` configured, modes fall back to `0755`/`0644` (otherwise NGINX still cannot read `0600` files)
- When the program is not root, or the user/group does not exist, the feature degrades to disabled with a `logging.warning` — startup and writes are not blocked
- Permissions apply only to the static_cache directory tree, not to `config.db`/`audit.db`/log files

### NGINX Integration

Three NGINX integration modes, chosen by endpoint auth policy:

**Scenario 1: public endpoint (empty api_key) static direct-serve + miss falls back to the app (recommended)**

```nginx
# static_cache.dir set to /opt/sqlreport/static_cache (must match app_config.json)
location ~ ^/api/(?<api_file>.+)\.json$ {
    root /opt/sqlreport;
    # /api/customers.json → /opt/sqlreport/static_cache/api/customers.json
    try_files /static_cache/api/$api_file.json @api_upstream;

    default_type application/json;
    add_header X-Static-Cache hit always;
    add_header Cache-Control "public, max-age=300" always;
}

location @api_upstream {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**Scenario 2: endpoints with api_key → everything goes to the app (auth and static reads both handled in-app)**

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**Scenario 3: rewrite direct-serve variant (no fallback, 404 when the file does not exist)**

```nginx
location ~ ^/api/(?<api_file>.+)\.json$ {
    rewrite ^/api/(.+)\.json$ /static_cache/$1.json break;
    root /opt/sqlreport;
    default_type application/json;
    add_header X-Static-Cache hit always;
}
```

**Full domain-prefix mapping example**: `https://a.com/fishapi/` → `http://127.0.0.1:8101/api/` (the backend system requires API paths to start with `/api/`), keeping full API Key auth and cache consistency (no independent cache at the NGINX layer):

```nginx
# /etc/nginx/conf.d/a.com-fishapi.conf
server {
    listen 80;
    server_name a.com;

    location /fishapi/ {
        # Strip the /fishapi/ prefix, replace with the /api/ prefix the system requires
        # rewrite does not touch the query string, ?api_key=xxx passes through as-is
        rewrite ^/fishapi/(.*)$ /api/$1 break;

        proxy_pass http://127.0.0.1:8101;
        proxy_http_version 1.1;

        # Keep the client domain in Host (used by backend audit logs)
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout  60s;
        proxy_send_timeout  60s;
        client_max_body_size 10m;
    }
}
```

Verify:

```bash
nginx -t && systemctl reload nginx
curl -H "Authorization: Bearer sk-XXXX" "https://a.com/fishapi/customers"
curl -i -H "Authorization: Bearer sk-XXXX" "https://a.com/fishapi/customers.json"   # check X-Static-Cache
```

**NGINX integration notes**:

1. **Auth boundary**: the static direct-serve in scenarios 1/3 bypasses app auth — **only for public endpoints with an empty api_key**; endpoints with a key must use scenario 2, otherwise the data is effectively public
2. **TTL is guaranteed by the app**: NGINX direct-serve does not check expiry, stale files keep being served; to expire at the NGINX layer too, use the `expires` directive or a deploy task that cleans up by `meta.expires_at`
3. **Security**: the regex location restricts `.json` suffixes; `try_files` returns 404 for `..`; disable script execution in that directory
4. Adjust the backend port to your deployment (the default `python server.py` listen port is the `server` section of `app_config.json`)

---

## 🖥️ Pages

### Config page `/config`

Config overview portal, entry cards leading to each management page:

- **Pools** — add/edit/delete/copy MySQL connection configs, reorder up/down
- **Users** — add/edit/delete system users
- **Reports** — standalone page `/config/reports`: configure SQL queries, bound pool, default page size, category, memo
- **Categories** — merged into `/config/reports` (top collapsible category tree): unlimited-depth tree management, reorder/add/rename/delete; old address `/config/categories` redirects to `/config/reports`
- **API endpoints** — standalone page `/config/api-endpoints`, global API endpoint list with linked report names
- **Schedules** — standalone page `/config/scheduler`: all report schedules with task name, bound reports, next run time, last result (with duration), failure counter, audit badge and circuit-breaker marker; per-task manual trigger / enable / delete; 🔇 marks tasks with exclusion rules; a banner shows when the scheduler is globally disabled

Report edit form highlights:
- SQL editor with format button and syntax-highlighted preview toggle
- Memo field for documenting report purpose
- Output limit guard: per-report "allow all output" switch plus truncation cap (`max_rows`, default 100,000, only effective when the switch is off); enabling the switch asks for confirmation
- "⏰ Scheduled execution" section: enable auto execution, interval minutes or daily HH:MM, misfire policy (skip / run-once); saving syncs the schedule row (unchanged params keep the existing rhythm). Full task management — multi-report binding, exclusion rules editor, audit switch — lives on `/config/scheduler`
- "♻ Cache keepalive" section: rebuild the Redis snapshot proactively before TTL expiry (requires Redis caching); lead seconds configurable, `0` disables
- Report list badges: ⏰ = schedule configured & enabled, ♻ = cache keepalive on
- [View] button: opens the report page in a new window
- [Preview] button: live-previews the query result using the current form SQL (unsaved), handy for checking SQL correctness
- [Save] returns to the list page on success

Report list page highlights:
- Tree display with indentation for hierarchy
- Collapsible category tree section (fold state remembered via localStorage)
- Up/down move buttons per report row
- Category-level select all/deselect, batch delete
- Reports can be moved across categories (target category dropdown)
- Memo truncated to 15 chars for preview

### Report page `/report`

- Category tree dropdown to select a report
- Auto-runs the SQL and caches the result (with cache timestamp and rebuild button)
- Paginated browsing (10/20/50/100/200 rows per page)
- Multi-column sorting — click column headers ▲▼ arrows, combo sort with a management panel (drag/add/remove)
- Multi-field filtering — per-column operators (contains/not-contains/eq/neq/gt/lt/gte/lte/is-empty/not-empty), multiple columns at once; filter values support a **unified match expression**: `*` wildcard (any position/repetition), comma multi-value (OR between segments), `\` escaping (`\*`/`\,`/`\\` match literally, for data containing those characters); only contains/not-contains/eq/neq participate in parsing, multiple column conditions combine with AND; the report page, export, API presets and audit-page keyword share the same syntax (help popup `?` for examples); in the audit page keyword, `%`/`_` match literally
- Column settings panel — drag to reorder columns, check to show/hide, select all/none
- Memo display — collapsible report memo (Markdown-rendered) with a **tri-state fold toggle** (Auto/Expand/Collapse): Auto keeps the default behavior (non-empty expanded, empty collapsed), Expand/Collapse force the state; the choice is remembered per report in localStorage
- API description blocks — each endpoint's interface description renders as its own "Interface Description" fold section (Markdown-rendered, default expanded) with the same tri-state toggle remembered per endpoint id; list/table summaries keep plain-text truncation (40 chars + full text on hover)
- [Edit] button: opens the report's config edit page in a new window
- Force-refresh cache (re-query the database); the cache badge shows the snapshot age, TTL, and an **"expired (auto-refresh on next request)"** warning when the snapshot has passed its TTL (`cache_ttl_hours=0` = never expires)
- Truncation notice — when the output limit guard cuts results to `max_rows`, a banner shows the cap and how to enable full output in the edit page

### Export `/export`

- Full dataset export (no pagination, keeps current filters and sorting)
- **CSV** and **JSON** formats
- UTF-8 BOM encoding (CSV) for correct Chinese text in Excel
- Charset selectable: GBK / UTF-8
- JSON smart no-quotes panel (decimal / scientific / thousands; URL param `smart_quotes=<comma list, e.g. 1,4>`; legacy `json_no_quotes=1` maps to the full panel — output always stays valid JSON)
- ZIP archive download
- Applies custom column settings (export only selected columns, in the chosen order)
- Applies the output limit guard: when full output is disabled and results exceed `max_rows`, the export is truncated with header `X-Export-Truncated: true` plus an in-file marker (a trailing `# ...` note line for CSV; a top-level `_meta: {"truncated": true, "max_rows": N}` object for JSON)

---

## 🏗️ Project Structure

```
SqlReport/
├── server.py              # HTTP server entry, route dispatch (ThreadingHTTPServer)
├── config.py              # Config page CRUD (pools/users/reports/categories/API endpoints)
├── report.py              # Report page, pagination, sorting, filtering
├── result_transform.py    # Result set transforms (filter/sort/column select, shared by page/export/API)
├── export.py              # CSV/JSON/ZIP export (with sorting)
├── auth.py                # User auth, Session management (sliding expiry + SQLite persistence)
├── db.py                  # Config storage (SQLite/MySQL dual engine) + query connection mgmt
├── app_config.py          # App config file loader
├── app_config.json        # App config file (contains credentials, not committed)
├── app_config.example.json# Config file template
├── config_db.py           # Config database engine selection
├── query_executor.py      # MySQL query executor (transaction support, ?→%s placeholder conversion)
├── render.py              # HTML templates (string.Template constants)
├── audit_db.py            # Audit log database (with auto rotation)
├── audit_page.py          # Audit log page (browse/cleanup/CSV export)
├── redis_cache.py         # Redis snapshot cache layer
├── api_handler.py         # API endpoint handler (endpoint queries + static cache + named result structure)
├── file_permissions.py    # Runtime file permission management (static_cache owner/perms)
├── tests/                 # Unit tests
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_base.py
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_export.py
│   ├── test_health.py
│   ├── test_mysql_mock.py
│   ├── test_mysql_transactional.py
│   ├── test_redis_cache.py
│   ├── test_report.py
│   ├── test_server.py
│   ├── test_file_permissions.py
│   └── test_state_machine.py
├── config.db              # SQLite config database (auto-created, not committed)
├── install.sh             # Automated dependency installer (venv + pip install)
├── requirements.txt       # pip dependency list
├── manage_service.sh      # Systemd service management script
├── git-purge.sh           # Git history rewrite tool (clean history/change author/proxy support)
└── AGENTS.md              # AI development agent guide
```

---

## 🧪 Running Tests

```bash
source venv/bin/activate
python -m unittest discover -s tests/ -v
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_FILE` | `app_config.json` | App config file path |
| `CONFIG_DB` | `config.db` | SQLite database file path (`path` in the config file takes precedence) |
| `HOST` | `0.0.0.0` | HTTP listen address |
| `PORT` | `8080` | HTTP listen port |

---

## 📜 Tech Stack

| Layer | Technology |
|-------|------------|
| Web server | `http.server.ThreadingHTTPServer` (Python stdlib) |
| Config storage | SQLite (Python stdlib `sqlite3`) or MySQL (`mysql-connector-python`), switched via `app_config.json` |
| Data queries | MySQL via `mysql-connector-python` |
| Markdown rendering | `markdown` + `pygments` (report memo Markdown, code highlighting) |
| Auth | Cookie + PBKDF2-SHA-256 salted hash + sliding expiry (Python stdlib `hashlib`, `secrets`, `hmac`, `time`) |
| Frontend | Pure HTML + inline CSS (no JS framework) |
| Tests | `unittest` (Python stdlib) |

---

## 🤝 Contributing

Issues and PRs are welcome!

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📐 Development Standards

- **Dependency sync rule**: when adding or removing pip dependencies, all three files below must be updated together:
  1. `requirements.txt` — dependency list
  2. `README.md` / `README-CN.md` — installation sections
  3. `install.sh` — `pip install` command (if changed)

- **README bilingual sync rule**: `README.md` (English) and `README-CN.md` (Chinese) are maintained in parallel as a mirror pair — any change to one must be applied to the other with an equivalent translation in the same commit. Feature additions, fixes, and config changes must never touch only one of the two.

---

## 📄 License

MIT License © 2024 [alexblair](https://github.com/alexblair)

---

<div align="center">
  <sub>Built with ❤️ using only Python standard library</sub>
</div>
