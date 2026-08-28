---
module: config-system
contract_id: SPEC-CONFIG
version: 1
depends_on: [T-002]
last_reviewed_commit: b690f8d
last_reviewed_at: 2026-08-28T15:30:00+08:00
---

## 1. 职责概述

SqlReport 的配置体系以 `app_config.json` 为核心，支持多层覆盖机制：生产主配置 → debug 覆盖 → 环境变量 → DB 覆盖。所有配置由 `app_config.py`（`load_config`）统一加载并合并，业务代码通过 `from app_config import config` 读取运行时配置。

**配置文件清单**：

| 文件 | 用途 | 优先级 |
|------|------|--------|
| `app_config.json` | 生产主配置 | 1（基础） |
| `app_config.debug.json` | 开发覆盖（可选） | 2（debug 模式） |
| 环境变量 `CONFIG_FILE` | 覆盖配置文件路径 | — |
| DB `app_configs` 表 | 运行时覆盖 `config_json` | 3（最高） |

## 2. 公开 API 契约

### 2.1 app_config.json 顶层结构

```
{
  "server":          {...},   // 服务器监听
  "log":             {...},   // 常规日志
  "error_log":       {...},   // 错误日志（可选）
  "redis":           {...},   // Redis 缓存
  "static_cache":    {...},   // API 静态缓存
  "file_permissions":{...},   // 文件权限管理
  "config_db":       [...],   // 配置数据库（数组，首个 enabled 生效）
  "audit_db":        {...},   // 审计日志存储（可选）
  "scheduler":       {...}    // 定时任务调度器
}
```

### 2.2 各段字段语义

#### server（服务器监听）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `host` | string | `"0.0.0.0"` | 监听地址 |
| `port` | integer | `1000` | 监听端口 |
| `trust_xff` | boolean | `false` | 信任 X-Forwarded-For 客户端 IP |

#### log（常规日志）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `true` | 是否启用文件日志 |
| `path` | string | `"run.log"` | 日志文件路径 |

#### error_log（错误日志，可选）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `false` | 是否启用独立错误日志 |
| `path` | string | `"error.log"` | 日志文件路径 |

#### redis（Redis 缓存）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `true` | 启用 Redis 缓存层 |
| `host` | string | `"127.0.0.1"` | Redis 主机 |
| `port` | integer | `6379` | Redis 端口 |
| `db` | integer | `6` | Redis 数据库编号 |
| `password` | string | — | 认证密码 |
| `key_prefix` | string | `"webreport_"` | 键名空间前缀 |
| `default_ttl_hours` | integer | `24` | 默认快照 TTL（小时） |
| `socket_timeout` | integer | `5` | Socket 超时（秒） |

#### static_cache（API 静态缓存）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `true` | 启用静态文件缓存 |
| `dir` | string | — | 缓存目录（相对/绝对路径） |

#### file_permissions（文件权限管理）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `true` | 启用权限管理 |
| `user` | string | `"www-data"` | 文件所有者（用户名/uid） |
| `group` | string | `"www-data"` | 文件所属组（组名/gid） |
| `dir_mode` | string | `"0755"` | 目录权限（八进制） |
| `file_mode` | string | `"0644"` | 文件权限（八进制） |

#### config_db（配置数据库数组）
数组中每个元素的结构：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | — | 启用此配置 |
| `engine` | string | — | `"mysql"` 或 `"sqlite3"` |
| `host` | string | — | MySQL 主机（engine=mysql） |
| `port` | integer | `3306` | MySQL 端口（engine=mysql） |
| `socket` | string | — | MySQL socket（engine=mysql，替代 host+port） |
| `user` | string | — | 数据库用户 |
| `password` | string | — | 数据库密码 |
| `database` | string | — | 数据库名 |
| `path` | string | — | SQLite 文件路径（engine=sqlite3） |

**选择逻辑**：遍历数组，首个 `enable=true` 的元素生效。

#### audit_db（审计日志存储，可选）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | string | `"audit.db"` | 审计数据库路径 |
| `retention_days` | integer | `90` | 日志保留天数 |

#### scheduler（定时任务调度器）
| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable` | boolean | `true` | 启用后台调度器 |
| `tick_seconds` | integer | `10` | 轮询间隔（秒） |

## 3. 数据流

```
app_config.json → load_config() → merged config dict
                                        ↑
app_config.debug.json → (debug mode)  ──┘
                                        ↑
environ["CONFIG_FILE"] → (override)   ──┘
                                        ↑
DB app_configs.config_json → (runtime) ──┘
```

## 4. 依赖关系

- **app_config.py**：统一加载入口（`load_config()`、`save_config()`）
- **config_db.py**：DB 层 config_json 存取
- **server.py**：启动时读取 config 决定监听端口、日志路径
- **所有业务模块**：通过 `from app_config import config` 读取运行时配置

## 5. 边界与异常

| 场景 | 处理方式 |
|------|----------|
| `app_config.json` 缺失 | 报错退出（无 fallback） |
| `app_config.debug.json` 缺失 | 静默跳过（非 debug 模式） |
| JSON 格式错误 | 报错退出 |
| DB config_json 格式错误 | 跳过 DB 覆盖，使用文件配置 |
| 环境变量 `CONFIG_FILE` 指向不存在文件 | 报错退出 |

## 6. 保鲜核对提交点

| 核对点 | 描述 | 提交锚定 |
|--------|------|----------|
| CP-001 | app_config.json 完整字段语义 | last_reviewed_commit |
| CP-002 | app_config.debug.json 覆盖差异 | last_reviewed_commit |
| CP-003 | load_config() 合并优先级 | last_reviewed_commit |
| CP-004 | DB config_json 覆盖机制 | last_reviewed_commit |
