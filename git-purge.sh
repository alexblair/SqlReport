#!/usr/bin/env bash
# ============================================================================
# git-purge.sh — 从 Git 仓库彻底删除文件/目录（历史+跟踪+.gitignore）
#
# 功能：
#   1. 将指定路径加入 .gitignore
#   2. 取消跟踪（git rm --cached）
#   3. 从全部提交历史中彻底抹除（git filter-branch --index-filter）
#   4. 清理残留引用并回收磁盘空间
#   5. 可选：强制推送到远程覆盖历史（支持 Token + 代理）
#
# 用法：
#   ./git-purge.sh <路径> [--push] [--token <TOKEN>] [--proxy <PROXY>]
#
#   认证（优先级：--token > GITHUB_TOKEN > GH_TOKEN）：
#     --token <TOKEN>       GitHub Personal Access Token
#     GITHUB_TOKEN         环境变量
#     GH_TOKEN             环境变量
#
#   代理（优先级：--proxy > ALL_PROXY > HTTPS_PROXY > HTTP_PROXY）：
#     --proxy <URL>        HTTP 代理地址，如 http://127.0.0.1:6012
#     ALL_PROXY            环境变量（全大写或全小写）
#     HTTPS_PROXY          环境变量
#     HTTP_PROXY           环境变量
#
# 示例：
#   ./git-purge.sh config.db
#   ./git-purge.sh secrets/ --push --token ghp_xxxxxx --proxy http://127.0.0.1:6012
#   GITHUB_TOKEN=ghp_xxxxxx ALL_PROXY=http://127.0.0.1:6012 ./git-purge.sh .env --push
#   ./git-purge.sh '*.log' --push
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
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# 解析参数
# ---------------------------------------------------------------------------
TARGET=""
DO_PUSH=0
TOKEN=""
PROXY=""

# 先从环境变量读取 token
if [ -n "${GITHUB_TOKEN:-}" ]; then
    TOKEN="$GITHUB_TOKEN"
elif [ -n "${GH_TOKEN:-}" ]; then
    TOKEN="$GH_TOKEN"
fi

# 从环境变量读取代理（优先级：ALL_PROXY > HTTPS_PROXY > HTTP_PROXY）
if [ -n "${ALL_PROXY:-}" ]; then
    PROXY="$ALL_PROXY"
elif [ -n "${all_proxy:-}" ]; then
    PROXY="$all_proxy"
elif [ -n "${HTTPS_PROXY:-}" ]; then
    PROXY="$HTTPS_PROXY"
elif [ -n "${https_proxy:-}" ]; then
    PROXY="$https_proxy"
elif [ -n "${HTTP_PROXY:-}" ]; then
    PROXY="$HTTP_PROXY"
elif [ -n "${http_proxy:-}" ]; then
    PROXY="$http_proxy"
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --push)
            DO_PUSH=1
            shift
            ;;
        --token)
            if [ $# -lt 2 ]; then
                err "--token 需要参数"
                exit 1
            fi
            TOKEN="$2"
            shift 2
            ;;
        --proxy)
            if [ $# -lt 2 ]; then
                err "--proxy 需要参数"
                exit 1
            fi
            PROXY="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 <路径> [--push] [--token <TOKEN>] [--proxy <URL>]"
            echo ""
            echo "认证环境变量: GITHUB_TOKEN, GH_TOKEN"
            echo "代理环境变量: ALL_PROXY, HTTPS_PROXY, HTTP_PROXY"
            exit 0
            ;;
        -*)
            err "未知选项: $1"
            exit 1
            ;;
        *)
            if [ -n "$TARGET" ]; then
                err "只能指定一个路径"
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    err "请指定要删除的文件或目录路径"
    echo "用法: $0 <路径> [--push] [--token <TOKEN>] [--proxy <URL>]"
    exit 1
fi

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    err "当前目录不是一个 Git 仓库"
    exit 1
fi

if ! git diff --quiet HEAD 2>/dev/null; then
    warn "工作区有未提交的修改，建议先 commit 或 stash"
    read -rp "是否继续？(y/N) " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        info "已取消"
        exit 0
    fi
fi

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

if [ ! -f .gitignore ]; then
    touch .gitignore
    ok "创建 .gitignore"
fi

if ! grep -Fxq "$TARGET" .gitignore 2>/dev/null; then
    echo "$TARGET" >> .gitignore
    ok "已追加到 .gitignore"
else
    info "已在 .gitignore 中，跳过"
fi

# ---------------------------------------------------------------------------
# Step 2: 取消跟踪
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
# Step 4: 从全部历史中抹除
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

git for-each-ref --format='delete %(refname)' refs/original | \
    git update-ref --stdin 2>/dev/null || true

git reflog expire --expire=now --all
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

# ---------------------------------------------------------------------------
# 可选：强制推送到远程
# ---------------------------------------------------------------------------
_push_remote() {
    local REMOTES
    _SET_PROXY=0  # 全局作用域，供 _restore_git_proxy 读取

    REMOTES=$(git remote)
    if [ -z "$REMOTES" ]; then
        warn "未配置远程仓库，跳过推送"
        _restore_git_proxy
        return
    fi

    echo ""
    warn "即将强制推送到以下远程仓库："
    git remote -v
    echo ""
    read -rp "确认强制推送？(y/N) " CONFIRM_PUSH
    if [[ ! "$CONFIRM_PUSH" =~ ^[Yy]$ ]]; then
        info "跳过推送"
        _restore_git_proxy
        return
    fi

    # ---- 代理配置 ----
    if [ -n "$PROXY" ]; then
        # 保存现有 git proxy 配置
        OLD_HTTP_PROXY=$(git config --global --get http.proxy 2>/dev/null || true)
        OLD_HTTPS_PROXY=$(git config --global --get https.proxy 2>/dev/null || true)
        # 设置代理
        git config --global http.proxy "$PROXY"
        git config --global https.proxy "$PROXY"
        _SET_PROXY=1
        ok "已设置 Git 代理: $PROXY"
    fi

    # ---- Token 注入 ----
    _SET_TOKEN=0
    if [ -n "$TOKEN" ]; then
        info "检测到 GitHub Token，正在注入认证信息..."
        # 保存原始 remote URL
        ORIG_REMOTE_URLS=$(git remote -v | awk '{print $2}' | sort -u)
        _SET_TOKEN=1

        for REMOTE in $REMOTES; do
            REMOTE_URL=$(git remote get-url "$REMOTE")
            if echo "$REMOTE_URL" | grep -q "^https://"; then
                if echo "$REMOTE_URL" | grep -q "@"; then
                    warn "remote '$REMOTE' 的 URL 已包含凭据，使用现有凭据"
                else
                    REMOTE_URL_AUTH=$(echo "$REMOTE_URL" | sed "s|https://|https://x-access-token:${TOKEN}@|")
                    git remote set-url "$REMOTE" "$REMOTE_URL_AUTH"
                    ok "已为 remote '$REMOTE' 注入 Token"
                fi
            fi
        done
    fi

    echo ""
    info "正在强制推送（覆盖远程历史）..."

    git push --force --all origin 2>&1 || {
        err "推送失败，请检查网络/代理/Token 权限"
        _restore_remote_urls
        _restore_git_proxy
        exit 1
    }
    git push --force --tags origin 2>&1 || true

    ok "推送完成"

    # 恢复原始配置
    _restore_remote_urls
    _restore_git_proxy
}

_restore_git_proxy() {
    if [ "${_SET_PROXY:-0}" -eq 1 ]; then
        if [ -n "${OLD_HTTP_PROXY:-}" ]; then
            git config --global http.proxy "$OLD_HTTP_PROXY"
        else
            git config --global --unset http.proxy 2>/dev/null || true
        fi
        if [ -n "${OLD_HTTPS_PROXY:-}" ]; then
            git config --global https.proxy "$OLD_HTTPS_PROXY"
        else
            git config --global --unset https.proxy 2>/dev/null || true
        fi
        ok "已恢复 Git 代理配置"
    fi
}

_restore_remote_urls() {
    if [ -n "${ORIG_REMOTE_URLS:-}" ]; then
        echo "$ORIG_REMOTE_URLS" | while read -r URL; do
            # 从 URL 中提取不带凭据的原始 URL
            CLEAN_URL=$(echo "$URL" | sed "s|https://.*@|https://|")
            # 找到哪个 remote 用的是这个带 token 的 URL
            for R in $(git remote); do
                CUR_URL=$(git remote get-url "$R" 2>/dev/null || true)
                if [ "$CUR_URL" = "$URL" ]; then
                    git remote set-url "$R" "$CLEAN_URL"
                    ok "已清除 remote '$R' 中的 Token"
                fi
            done
        done
    fi
}

if [ "$DO_PUSH" -eq 1 ]; then
    _push_remote
else
    info "如需推送覆盖远程历史，请执行："
    echo ""
    echo "    ./git-purge.sh '$TARGET' --push [--token <TOKEN>] [--proxy <URL>]"
    echo "    # 或使用环境变量:"
    echo "    GITHUB_TOKEN=ghp_xxxxxx ALL_PROXY=http://127.0.0.1:6012 \\"
    echo "      git push --force --all origin"
    echo ""
fi

echo ""
info "提示：其他协作者需要执行 git rebase 或重新 clone 以同步"
