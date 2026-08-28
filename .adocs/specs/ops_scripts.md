---
module: ops-scripts
contract_id: SPEC-OPS-SCRIPTS
version: 1
depends_on: [T-002]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28T15:30:00+08:00
---

## 1. 职责概述

SqlReport 提供三个运维脚本，覆盖安装依赖、管理 systemd 服务、Git 仓库操作三大场景。所有脚本均为 Bash，无外部依赖（除 git-tool.sh 调用 `opencode run` 生成 AI 提交信息）。

**脚本清单**：

| 文件 | 行数 | 用途 |
|------|------|------|
| `install.sh` | 63 | 依赖安装（venv + pip） |
| `manage_service.sh` | 188 | systemd 服务安装/卸载 |
| `git-tool.sh` | 1259 | Git 仓库操作（提交/推送/拉取/清理） |

## 2. 公开 API 契约

### 2.1 install.sh — 依赖安装

**用法**：`./install.sh [--no-venv]`

**行为**：
- 无参数：创建 `venv/` → 激活 → `pip install -r requirements.txt`
- `--no-venv`：跳过 venv 创建，直接 pip install

**输出**：安装完成后打印启动指引

### 2.2 manage_service.sh — systemd 服务管理

**用法**：`sudo bash manage_service.sh {install|uninstall}`

**install 子命令**：
- 前置检查（precheck）：root 权限、systemctl 可用、`server.py` 存在、`venv/` 存在、SELinux 状态
- 写入 systemd unit 文件到 `/etc/systemd/system/web-report.service`
- 配置：`Restart=always`、`RestartSec=5`、`LimitNOFILE=65536`
- 执行：`daemon-reload` → `enable` → `start` → 状态检查

**uninstall 子命令**：
- `stop` → `disable` → 删除 unit 文件 → `daemon-reload` → `reset-failed`

### 2.3 git-tool.sh — Git 仓库操作

**用法**：`./git-tool.sh [status|commit|push|pull|purge <path>]`

**五大场景**：

| 场景 | 子命令 | 功能 |
|------|--------|------|
| A | `commit` | 交互式暂存 + 提交 + 推送（支持 AI/本地/手动消息） |
| B | `push` | 仅推送未推送的本地提交 |
| C | `pull` | 拉取（3 策略：hard reset / stash+merge / cherry-pick） |
| D | `purge <path>` | 重写历史永久删除文件（filter-branch） |
| E | `status` | 仓库状态诊断 + 建议 |

**辅助函数**：
- `parse_env_credentials()`：读取 `GITHUB_TOKEN`/`GH_TOKEN` 和代理环境变量
- `setup_proxy()` / `inject_token()` / `restore_remote_url()`：网络/认证配置
- `generate_ai_summary()`：调用 `opencode run` 生成 AI 提交信息
- `generate_auto_summary()`：离线本地规则生成提交信息（文件/行统计）

**交互模式**：无参数时进入菜单驱动交互

## 3. 数据流

```
install.sh → venv/ → pip install -r requirements.txt
                         ↓
manage_service.sh → /etc/systemd/system/web-report.service → systemctl
                         ↓
git-tool.sh → git add/commit/push/pull/filter-branch
```

## 4. 依赖关系

- **install.sh** → `requirements.txt`（python3、pip）
- **manage_service.sh** → `server.py`、`venv/`、systemctl
- **git-tool.sh** → git、`opencode`（可选，AI 提交信息）

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| install.sh 无 venv 且无 --no-venv | 自动创建 venv |
| manage_service.sh 非 root | 报错退出 |
| manage_service.sh 无 systemctl | 报错退出 |
| git-tool.sh 无 .git | `require_repo()` 报错退出 |
| git-tool.sh 网络超时 | 重试或提示检查代理配置 |
| git-tool.sh purge 路径不存在 | 报错退出 |

## 6. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | install.sh 用法与参数 | last_reviewed_commit |
| CP-002 | manage_service.sh unit 文件模板 | last_reviewed_commit |
| CP-003 | git-tool.sh 五大场景命令集 | last_reviewed_commit |
| CP-004 | git-tool.sh AI 提交信息生成 | last_reviewed_commit |
