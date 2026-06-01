# AGENTS.md — Web Report Tool (Python 3)

## Project Identity

**Purpose**: Minimal Python 3 web report tool. Configure connection pools, MySQL queries, and users via a config page; select and view reports with paginated tables and CSV export.

**Stack**: Python 3 standard library only — no web framework, no ORM, no extra dependencies unless proven necessary. Use `http.server`, `sqlite3`/`mysql-connector`, `csv`, etc.

**Repo skeleton**: `opencode.json` + `.opencode/` (OpenAgents Control tooling). Project code goes at repo root alongside these.

---

## Hard Constraints

These override any generic best-practice advice:

| # | Rule | Why |
|---|------|-----|
| 1 | **External network access** → always use proxy `http://127.0.0.1:6012`. Never remove it, never skip it. | Geo-blocked resources. |
| 2 | **Zero unnecessary dependencies**. Prefer Python stdlib. Only add a package when the stdlib genuinely cannot do the job. | Keep it lean. |
| 3 | **Full inline comments/docstrings** on every function, class, and non-trivial block. Every file must have a header comment explaining its purpose. | Agents find their way without scanning the whole project. |
| 4 | **Bug fixes**: find root cause first, then fix. Never modify unrelated code. Document the root cause in comments. | Avoid regressions. |
| 5 | **Every feature point must have tests**. All tests must pass locally before delivery. | Enforced quality gate. |
| 6 | **VENV 环境隔离** — 必须使用 `python -m venv` 创建虚拟环境。依赖安装、运行、测试全部在 venv 内进行。`venv/` 不提交。 | 依赖隔离，避免污染系统 Python。 |
| 7 | **全简体中文** — 所有沟通、代码注释、文档说明必须使用简体中文。禁止混合英文或繁体中文。 | 项目要求统一中文语境。 |
| 8 | **测试必须实时输出结果** — 运行 `python -m unittest` 时必须加 `-v` 参数，并展示全部输出。禁止在测试运行时不展示输出而造成"卡断中"的假象。如果测试运行时间超过 30 秒无输出，应中止并检查卡住原因。 | 避免误以为测试挂死。 |

---

## Architecture & Conventions

### Project Layout (expected)

```
repo-root/
├── server.py              # Entry point (HTTP server)
├── config_page.py         # Config page handler
├── report_page.py         # Report page handler
├── db.py                  # MySQL connection pool management
├── query.py               # Query execution & pagination
├── export.py              # CSV export
├── auth.py                # Simple user auth
├── templates/             # HTML templates (inline or separate)
├── tests/
│   ├── test_config.py
│   ├── test_report.py
│   ├── test_export.py
│   └── test_auth.py
├── AGENTS.md
├── opencode.json
└── .opencode/             # OpenCode tooling — do not edit manually
```

### Coding style
- **Functions < 50 lines**, single responsibility.
- Pure functions where possible; isolate I/O (DB, filesystem, network).
- Dependency injection for testability — pass DB pool/connections explicitly, never import globals.
- Early returns, no deep nesting.
- Module docstring at the top of every `.py` file.
- Python 3.11+ (match f-strings, `datetime` improvements available).

### Config page features
- Connection pool CRUD (add/delete/modify pools).
- User CRUD (add/delete/modify users).
- Report config CRUD (MySQL query, default page size, which pool to use).

### Report page features
- Report selector (tabs or dropdown).
- Table display with configurable page size (default from config, user can override).
- Full pagination: show total pages, jump to any page.
- CSV export (quoted fields, comma-separated).

---

## Development Workflow

### Environment setup

```bash
# 必须在 venv 内操作，禁止使用系统 Python
python3 -m venv venv && source venv/bin/activate
pip install mysql-connector-python  # 唯一的外部依赖
```

所有命令（安装、运行、测试）都在激活 venv 后执行。`venv/` 目录不提交到 git。

### Workflow steps

1. **Plan** — Propose approach, get approval.
2. **Implement** — Write code + inline docs + tests in the same pass.
3. **Validate** — Run full test suite inside venv.
4. **Fix** — If tests fail, find root cause, fix, re-run all tests. Never partial fix.
5. **Deliver** — All tests green.

### Test commands

```bash
source venv/bin/activate && python -m pytest tests/ -v           # if using pytest
source venv/bin/activate && python -m unittest discover -s tests/ # if using unittest (prefer stdlib)
```

Prefer `unittest` (stdlib) to avoid adding pytest as a dependency unless needed.

### Run server for development

```bash
source venv/bin/activate && python server.py
```

首次启动会自动创建默认管理员账户：
- 用户名: `admin`
- 密码: `admin123`
- 请尽快登录 `/config` 修改密码。

### 首次用户创建（第二种方式）

如果不想用默认账户，启动前手动创建：

```bash
source venv/bin/activate
python -c "import db, auth; c=db.get_config_db(); db.init_db(c); \
  db.add_user(c, 'admin', auth.hash_password('你的密码')); c.close()"
```

---

## Context System

This project uses OpenAgents Control. Before writing code, load relevant standards:

- **Code quality**: `.opencode/context/core/standards/code-quality.md`
- **Testing**: `.opencode/context/core/standards/test-coverage.md`
- **Documentation**: `.opencode/context/core/standards/documentation.md`

These reference JS examples but the principles (modular design, pure functions, AAA pattern, DI) apply to Python directly.

---

## Gotchas

- `.opencode/` is OpenCode tooling, not project code. Do not modify it unless explicitly asked.
- `opencode.json` is minimal (model config only). Do not delete or restructure it.
- There is no `__init__.py` at repo root yet — the project is greenfield.
- No existing `.gitignore` — one may be created at project start. Never commit `__pycache__/`, `.env`, or `.tmp/`.
- **VENV always**: never run `pip install`, `python server.py`, or `python -m unittest` outside the venv. Use `source venv/bin/activate` first.

### 运行方式

```bash
source venv/bin/activate
python -m unittest discover -s tests/ -v    # 详细输出
python -m unittest discover -s tests/       # 简洁输出
```

