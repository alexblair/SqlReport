---
module: readme-reconciliation
contract_id: SPEC-README-RECON
version: 1
depends_on: [T-002]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28T15:30:00+08:00
---

## 1. 职责概述

本分卷记录 README.md 与代码/目录树的真相核对结果。README 中存在多处与代码实际不符的描述，需在知识库中记录失真项并标注还原后修正。

**核对基准**：主仓还原后的真实代码（commit `218718d` 基线 + 后续开发）。

## 2. 公开 API 契约

### 2.1 README 概况

README.md 共 681 行，包含：项目简介、技术栈、功能表（30+ 特性）、快速启动、配置文档、API 模板、项目结构、测试、环境变量、License。

### 2.2 已核对章节

| 章节 | 核对结果 | 备注 |
|------|----------|------|
| 项目简介 | ✅ 一致 | "SQL in. Reports & APIs out." |
| 技术栈 | ✅ 一致 | Python 3.11+ stdlib，无框架 |
| 功能表 | ⚠️ 部分失真 | 见 §2.3 |
| 快速启动 | ✅ 一致 | clone → install → venv → server.py |
| 配置文档 | ✅ 一致 | app_config.json 全字段覆盖 |
| API 模板 | ✅ 一致 | {{placeholders}} 系统 |
| 项目结构 | ⚠️ 失真 | 见 §2.4 |
| 测试 | ⚠️ 失真 | 见 §2.5 |
| 环境变量 | ✅ 一致 | CONFIG_FILE/CONFIG_DB/HOST/PORT |

### 2.3 失真项：功能表

README 功能表列出 30+ 特性，经代码核对：

| 功能 | README 描述 | 代码实际 | 失真类型 |
|------|-------------|----------|----------|
| git-purge.sh | 独立脚本 | 已合并入 git-tool.sh 的 purge 子命令 | 脚本名过时 |

### 2.4 失真项：项目结构

README 项目结构章节列出文件清单，经核对：

| 项目 | README 描述 | 代码实际 | 失真类型 |
|------|-------------|----------|----------|
| tests/ | 未列出 | 实际存在 60+ 测试文件 + 3 子目录 | 目录遗漏 |
| git-purge.sh | 单独列出 | 已合并入 git-tool.sh | 脚本名过时 |
| .adocs/ | 未列出 | 知识库目录（.gitignore 排除） | 非公开，不需列出 |

### 2.5 失真项：测试

README 测试章节：

| 项目 | README 描述 | 代码实际 | 失真类型 |
|------|-------------|----------|----------|
| 测试发现命令 | `python -m unittest discover -s tests/ -v` | ✅ 正确 | — |
| tests/ 目录 | 未明确列出内容 | 实际含 60+ 测试文件 + bug_hunt/integration/regression 子目录 | 内容遗漏 |

## 3. 数据流

```
README.md → 人工核对 → 本分卷（失真项记录）
                    ↓
          知识库修正（不改 README）
```

## 4. 依赖关系

- **README.md**：核对基准源
- **所有 .py 模块**：代码真实依据
- **tests/ 目录**：测试结构真实依据

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| README 失真但不影响使用 | 记录但不修改 README |
| README 与代码严重不一致 | 在知识库中标注，建议人工修正 |

## 6. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | 功能表失真项（git-purge.sh） | last_reviewed_commit |
| CP-002 | 项目结构失真项（tests/ 遗漏） | last_reviewed_commit |
| CP-003 | 测试章节失真项（内容遗漏） | last_reviewed_commit |
