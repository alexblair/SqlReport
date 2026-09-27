 #!/usr/bin/env bash
# install.sh — SqlReport 自动化安装脚本
#
# 用法:
#   ./install.sh              # 创建 venv 并安装依赖
#
# 说明:
#   首次运行自动创建虚拟环境并安装所有 pip 依赖。
#   如果 requirements.txt 有变更，重新运行此脚本即可同步依赖。
#
# 依赖同步规范:
#   当新增或删减 pip 依赖包时，必须同步更新:
#     1. requirements.txt  — 依赖清单
#     2. README.md          — 安装说明章节
#     3. install.sh         — 本脚本的安装命令

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================"
echo " SqlReport 依赖安装"
echo "================================"

# --- 虚拟环境管理 ---
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] 创建虚拟环境: $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/3] 虚拟环境已存在，跳过创建。"
fi

echo "[2/3] 激活虚拟环境 ..."
source "$VENV_DIR/bin/activate"

# --- 安装依赖 ---
echo "[3/3] 安装 pip 依赖 ..."
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "================================"
echo " 安装完成！"
echo "================================"
echo ""
echo "启动服务:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 server.py"
echo ""
