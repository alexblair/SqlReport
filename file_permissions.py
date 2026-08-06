"""
file_permissions.py — 运行时文件权限管理（仅 static_cache 缓存目录）

背景：程序以 root 运行，static_cache 的 .json 缓存文件经 tempfile.mkstemp
创建（0600 root:root），NGINX 直出（adr-0005）时以非 root 用户运行的
worker 无法读取。本模块在配置中指定缓存文件/目录的属主（用户、组）与
权限位，程序启动时刷新缓存目录树，此后新增文件按配置权限建立。

配置段（app_config.json）:
    "file_permissions": {
        "enable": true,
        "user": "nginx",
        "group": "nginx",
        "dir_mode": "0755",
        "file_mode": "0644"
    }

语义:
  - user/group: 以名称指定属主/属组，启动时解析为 uid/gid（兼容数字字符串）
  - dir_mode/file_mode: 可选，八进制字符串（JSON 无八进制字面量），
    缺省 "0755"/"0644"。仅配置 user/group 时文件若保持 mkstemp 的 0600，
    NGINX 仍无法读取，故默认权限位必须放开读权限
  - 整个段缺失或 enable=false → 功能关闭，行为与未引入本功能时完全一致
  - 程序非 root 或用户/组不存在 → 降级关闭并记 warning（chown 需要 root，
    无法 chown 的部署保持默认创建行为），绝不阻塞业务启动/写入

本模块不新增任何第三方依赖（仅标准库 pwd/grp）。
"""

import grp
import logging
import os
import pwd

# ---------------------------------------------------------------------------
# 内部状态（load_permissions() 一次性填充）
# ---------------------------------------------------------------------------

_uid: int | None = None
_gid: int | None = None
_dir_mode: int = 0o755
_file_mode: int = 0o644
_enabled: bool = False


# ---------------------------------------------------------------------------
# 配置解析
# ---------------------------------------------------------------------------


def _resolve_uid(user: str) -> int | None:
    """把用户名/数字 uid 解析为 uid；不存在返回 None。"""
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        pass
    if user.isdigit():
        try:
            return pwd.getpwuid(int(user)).pw_uid
        except KeyError:
            pass
    logging.warning("file_permissions: 用户 %s 不存在，权限功能关闭", user)
    return None


def _resolve_gid(group: str) -> int | None:
    """把组名/数字 gid 解析为 gid；不存在返回 None。"""
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        pass
    if group.isdigit():
        try:
            return grp.getgrgid(int(group)).gr_gid
        except KeyError:
            pass
    logging.warning("file_permissions: 组 %s 不存在，权限功能关闭", group)
    return None


def _parse_mode(value, default: int) -> int:
    """解析权限位：接受八进制字符串（如 "0644"）或整数；非法时用默认值。"""
    if value is None:
        return default
    try:
        if isinstance(value, int):
            return value & 0o7777
        return int(str(value), 8) & 0o7777
    except (ValueError, TypeError):
        logging.warning("file_permissions: 非法 mode %r，使用默认 %s",
                        value, oct(default))
        return default


def load_permissions() -> bool:
    """从 app_config 加载并解析权限配置，返回是否启用。

    配置缺失/未启用、user/group 缺失、用户或组不存在、程序非 root 时
    降级关闭并记 warning，返回 False。仅成功启用后 apply_* 才生效。
    """
    global _uid, _gid, _dir_mode, _file_mode, _enabled
    _enabled = False
    from app_config import get_file_permissions_config
    cfg = get_file_permissions_config()
    if not cfg.get("enable", False):
        return False
    user = cfg.get("user")
    group = cfg.get("group")
    if not user or not group:
        logging.warning("file_permissions 已启用但缺少 user/group，权限功能关闭")
        return False
    uid = _resolve_uid(str(user))
    gid = _resolve_gid(str(group))
    if uid is None or gid is None:
        return False
    if os.geteuid() != 0:
        logging.warning("file_permissions 需要 root 权限才能 chown（当前 euid=%s），权限功能关闭",
                        os.geteuid())
        return False
    _uid, _gid = uid, gid
    _dir_mode = _parse_mode(cfg.get("dir_mode"), 0o755)
    _file_mode = _parse_mode(cfg.get("file_mode"), 0o644)
    _enabled = True
    logging.info("file_permissions 已启用: %s:%s 目录%s 文件%s",
                 user, group, oct(_dir_mode), oct(_file_mode))
    return True


def is_enabled() -> bool:
    """当前权限管理是否已启用。"""
    return _enabled


# ---------------------------------------------------------------------------
# 权限应用
# ---------------------------------------------------------------------------


def apply_to(path: str, is_dir: bool | None = None) -> None:
    """对单个路径应用配置的属主与权限位。

    is_dir=None 时按路径实际类型选择 mode；失败静默降级（warning），
    绝不向调用方抛异常。
    """
    if not _enabled:
        return
    try:
        if is_dir is None:
            mode = _dir_mode if os.path.isdir(path) else _file_mode
        else:
            mode = _dir_mode if is_dir else _file_mode
        os.chown(path, _uid, _gid)
        os.chmod(path, mode)
    except OSError as e:
        logging.warning("file_permissions: 无法应用权限到 %s: %s", path, e)


def apply_tree(root: str) -> None:
    """递归应用权限到 root 下全部目录与文件（root 需已存在）。

    供写入路径使用：新增子目录/文件后刷新所属目录树，确保新增节点
    以配置权限建立。
    """
    if not _enabled:
        return
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            apply_to(dirpath, is_dir=True)
            for name in filenames:
                apply_to(os.path.join(dirpath, name), is_dir=False)
    except OSError as e:
        logging.warning("file_permissions: 遍历目录失败 %s: %s", root, e)


def refresh_tree(root: str) -> None:
    """递归刷新目录树权限；root 不存在时先创建（启动时调用）。

    程序启动时对 static_cache 根目录整树刷新，覆盖历史遗留的
    root:root 0600 文件（root 权限下可修改属主）。
    """
    if not _enabled:
        return
    if not os.path.exists(root):
        try:
            os.makedirs(root)
        except OSError as e:
            logging.warning("file_permissions: 创建缓存目录失败 %s: %s", root, e)
            return
    apply_tree(root)
