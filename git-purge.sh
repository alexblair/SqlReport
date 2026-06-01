#!/usr/bin/env bash
# ============================================================================
# git-purge.sh — 从 Git 仓库彻底删除文件/目录（历史+跟踪+.gitignore）
#
# 功能：
#   1. 将指定路径加入 .gitignore
#   2. 取消跟踪（git rm --cached）
#   3. 从全部提交历史中彻底抹除（git filter-branch --index-filter）
#   4. 清理残留引用并回收磁盘空间
#   5. 可选：强制推送到远程覆盖历史
#
# 用法：
#   ./git-purge.sh <文件或目录路径> [--push]
#
# 示例：
#   ./git-purge.sh config.db
#   ./git-purge.sh secrets/       --push
#   ./git-purge.sh *.log
#
# 注意：
#   - 必须在 Git 仓库根目录执行
#   - --push 会强制覆盖远程所有分支历史，谨慎使用！
#   - 操作不可逆，建议先备份仓库
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# 检查参数
# ---------------------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "用法: $0 <文件或目录路径> [--push]"
    echo ""
    echo "示例:"
    echo "  $0 config.db"
    echo "  $0 secrets/ --push"
    echo "  $0 '*.log'"
    exit 1
fi

TARGET="$1"
PUSH="${2:-}"

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
# 1. 是否在 git 仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    err "当前目录不是一个 Git 仓库"
    exit 1
fi

# 2. 工作区是否干净（避免意外丢失未提交修改）
if ! git diff --quiet HEAD 2>/dev/null; then
    warn "工作区有未提交的修改，建议先 commit 或 stash"
    read -rp "是否继续？(y/N) " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        info "已取消"
        exit 0
    fi
fi

# 3. 目标路径是否存在（仅警告）
if [ ! -e "$TARGET" ] && ! git ls-files --error-unmatch "$TARGET" > /dev/null 2>&1; then
    warn "路径 '$TARGET' 既不在磁盘上也不在 Git 跟踪中，将继续尝试从历史中清理"
fi

# ---------------------------------------------------------------------------
# 确认
# ---------------------------------------------------------------------------
echo ""
warn "╔══════════════════════════════════════════════════════════════╗"
warn "║  此操作将 永久删除 '$TARGET' 的 全部历史记录！    ║"
warn "║  提交历史将被重写，所有协作者需要重新 clone。              ║"
warn "╚══════════════════════════════════════════════════════════════╝"
echo ""
read -rp "确定要执行？(y/N) " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    info "已取消"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1: 加入 .gitignore
# ---------------------------------------------------------------------------
echo ""
info "Step 1/5 — 将 '$TARGET' 加入 .gitignore"

# 如果 .gitignore 不存在则创建
if [ ! -f .gitignore ]; then
    touch .gitignore
    ok "创建 .gitignore"
fi

# 如果尚未包含该条目则追加
if ! grep -Fxq "$TARGET" .gitignore 2>/dev/null; then
    echo "$TARGET" >> .gitignore
    ok "已追加到 .gitignore"
else
    info "已在 .gitignore 中，跳过"
fi

# ---------------------------------------------------------------------------
# Step 2: 取消跟踪（如果正在跟踪）
# ---------------------------------------------------------------------------
echo ""
info "Step 2/5 — 取消跟踪 '$TARGET'"

if git ls-files --error-unmatch "$TARGET" > /dev/null 2>&1; then
    git rm --cached -r "$TARGET" 2>/dev/null || true
    ok "已取消跟踪"
else
    info "未在跟踪中，跳过"
fi

# ---------------------------------------------------------------------------
# Step 3: 提交 .gitignore 变更
# ---------------------------------------------------------------------------
echo ""
info "Step 3/5 — 提交 .gitignore 变更"

if git diff --cached --quiet; then
    info "无变更需要提交，跳过"
else
    git add .gitignore
    git commit -m "把 $TARGET 加入 .gitignore 并取消跟踪"
    ok "已提交"
fi

# ---------------------------------------------------------------------------
# Step 4: 从全部历史中抹除（filter-branch）
# ---------------------------------------------------------------------------
echo ""
info "Step 4/5 — 从全部提交历史中抹除 '$TARGET'"
info "此步骤可能需要较长时间，取决于历史长度..."

export FILTER_BRANCH_SQUELCH_WARNING=1

git filter-branch --force --index-filter \
    "git rm --cached --ignore-unmatch -r \"$TARGET\"" \
    --prune-empty -- --all

ok "历史重写完成"

# ---------------------------------------------------------------------------
# Step 5: 清理残留引用和对象
# ---------------------------------------------------------------------------
echo ""
info "Step 5/5 — 清理残留引用和回收磁盘空间"

# 删除备份引用
git for-each-ref --format='delete %(refname)' refs/original | \
    git update-ref --stdin 2>/dev/null || true

# 过期 reflog
git reflog expire --expire=now --all

# 垃圾回收（彻底删除悬空对象）
git gc --prune=now --aggressive 2>/dev/null || git gc --prune=now

ok "清理完成"

# ---------------------------------------------------------------------------
# 完成
# ---------------------------------------------------------------------------
echo ""
ok "╔══════════════════════════════════════════════════════════════╗"
ok "║   '$TARGET' 已从仓库中彻底删除！              ║"
ok "╚══════════════════════════════════════════════════════════════╝"
echo ""
info "当前仓库状态："
git log --oneline -3

echo ""
echo "────────────────────────────────────────────────────────"

# ---------------------------------------------------------------------------
# 可选：强制推送到远程
# ---------------------------------------------------------------------------
if [ "$PUSH" = "--push" ]; then
    # 检查是否有远程仓库
    REMOTE=$(git remote)
    if [ -z "$REMOTE" ]; then
        warn "未配置远程仓库，跳过推送"
    else
        echo ""
        warn "即将强制推送到以下远程仓库："
        git remote -v
        echo ""
        read -rp "确认强制推送？(y/N) " CONFIRM_PUSH
        if [[ "$CONFIRM_PUSH" =~ ^[Yy]$ ]]; then
            echo ""
            info "正在强制推送（覆盖远程历史）..."
            git push --force --all origin
            git push --force --tags origin
            ok "推送完成"
        else
            info "跳过推送"
        fi
    fi
else
    echo ""
    info "未指定 --push，跳过远程推送"
    info "如需推送请执行："
    echo "    git push --force --all origin"
    echo "    git push --force --tags origin"
fi

echo ""
info "提示：其他协作者需要执行 git rebase 或重新 clone 以同步"
