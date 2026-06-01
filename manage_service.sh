#!/usr/bin/env bash
# ===========================================================================
# manage_service.sh — Web Report Tool systemd 服务安装/卸载脚本
#
# 用法:
#   sudo bash manage_service.sh install   安装并启动服务
#   sudo bash manage_service.sh uninstall 停止并移除服务
#
# 注意:
#   - 服务程序路径 = 本脚本所在目录（动态检测，换目录自动适配）
#   - 服务名: web-report
#   - 需要 root 权限（systemctl 操作）
# ===========================================================================

set -euo pipefail

SERVICE_NAME="web-report"
# 脚本所在目录（即项目根目录，动态适配目录迁移）
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
precheck() {
    if [[ $EUID -ne 0 ]]; then
        error "请使用 sudo 或以 root 用户运行"
        exit 1
    fi

    if ! command -v systemctl &>/dev/null; then
        error "未检测到 systemctl，当前系统不支持 systemd"
        exit 1
    fi

    if [[ ! -f "${PROJECT_DIR}/server.py" ]]; then
        error "未在 ${PROJECT_DIR} 中找到 server.py，请确认脚本放在项目根目录"
        exit 1
    fi

    if [[ ! -f "${PROJECT_DIR}/venv/bin/python" ]]; then
        error "未找到 Python 虚拟环境 (venv/)，请先在项目目录执行: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # 检查 SELinux/systemd 是否有权限限制（非致命，仅提示）
    if command -v getenforce &>/dev/null && [[ "$(getenforce)" == "Enforcing" ]]; then
        warn "SELinux 处于 Enforcing 模式，如果服务启动失败，请检查 SELinux 策略"
    fi
}

# ---------------------------------------------------------------------------
# 安装服务
# ---------------------------------------------------------------------------
install_service() {
    info "安装 systemd 服务: ${SERVICE_NAME}"
    info "项目目录: ${PROJECT_DIR}"

    # 写入 service 单元文件
    cat > "$SERVICE_FILE" <<SERVICEEOF
[Unit]
Description=Web Report Tool - Minimal Python 3 Web Report Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/venv/bin/python ${PROJECT_DIR}/server.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
# 限制资源
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICEEOF

    chmod 644 "$SERVICE_FILE"
    info "服务单元文件已创建: ${SERVICE_FILE}"

    # 重新加载 systemd 配置
    systemctl daemon-reload
    info "systemd 配置已重新加载"

    # 启用开机自启
    systemctl enable "${SERVICE_NAME}"
    info "开机自启已启用"

    # 启动服务
    systemctl start "${SERVICE_NAME}"
    info "服务已启动"

    # 等待片刻后检查状态
    sleep 1
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        info "服务运行正常"
        echo ""
        systemctl status "${SERVICE_NAME}" --no-pager
        echo ""
        info "安装完成！访问 http://<本机IP>:8080 进入 Web 报表工具"
        info "默认管理员: admin / admin123"
    else
        warn "服务启动可能异常，请检查日志: journalctl -u ${SERVICE_NAME}"
        systemctl status "${SERVICE_NAME}" --no-pager 2>&1 || true
    fi
}

# ---------------------------------------------------------------------------
# 卸载服务
# ---------------------------------------------------------------------------
uninstall_service() {
    info "卸载 systemd 服务: ${SERVICE_NAME}"

    # 检查服务是否存在
    if [[ ! -f "$SERVICE_FILE" ]]; then
        warn "服务 ${SERVICE_NAME} 未安装（服务文件不存在）"
        exit 0
    fi

    # 如果服务正在运行，先停止
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "检测到服务正在运行，正在停止..."
        systemctl stop "${SERVICE_NAME}"
        info "服务已停止"
    else
        info "服务当前未运行"
    fi

    # 禁用开机自启
    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        systemctl disable "${SERVICE_NAME}"
        info "开机自启已禁用"
    fi

    # 删除服务单元文件
    rm -f "$SERVICE_FILE"
    info "服务单元文件已删除: ${SERVICE_FILE}"

    # 重新加载 systemd
    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
    info "systemd 配置已重新加载"

    echo ""
    info "卸载完成！服务 ${SERVICE_NAME} 已被完全移除"
}

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
case "${1:-}" in
    install)
        precheck
        install_service
        ;;
    uninstall)
        precheck
        uninstall_service
        ;;
    *)
        echo "用法: sudo bash $0 {install|uninstall}"
        echo ""
        echo "  install   - 安装并启动 systemd 服务（同时设置开机自启）"
        echo "  uninstall - 停止并卸载 systemd 服务"
        exit 1
        ;;
esac
