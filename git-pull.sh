#!/usr/bin/env bash
# ============================================================================
# git-pull.sh — 生产环境从 GitHub 拉取更新（交互式 3 场景）
#
# 使用场景：
#   生产/测试服务器使用。GitHub 上有新版本时，运行本脚本把代码更新到服务器。
#   先展示与远端差距（领先/落后/本地未提交变更），再由用户选择处理方式。
#
#   三个场景怎么选：
#     场景 1：服务器上没有任何本地修改，直接同步到 GitHub 最新版（最常用）。
#     场景 2：服务器上改过文件（如临时改配置）且不想丢失，
#             拉取新版本时保留本地修改；同一文件 GitHub 也改了就留本地版本。
#     场景 3：GitHub 一次推了多个提交，只想更新到其中某一个（如回退到旧版），
#             列出每个提交让用户选。
#
#   何时不用：
#     - 本地开发完要上传代码 → 用 git-commit.sh
#     - 要彻底删除仓库里的文件（含历史）→ 用 git-purge.sh
#
# 场景：
#   1. 放弃本地所有改动，以 GitHub 最新版本为准，拉取覆盖本地
#   2. 先拉取 GitHub 最新版本，保留本地更改的文件；
#      冲突时（GitHub 也改了、本地也改了）留本地的版本
#   3. 列出 GitHub 上的每个更新，通过提交 ID 选择任意一个覆盖本地
#      （处理逻辑同场景 1，区别：场景 1 只认 GitHub 最新版本）
#
# 用法：
#   ./git-pull.sh [--remote <名称>] [--branch <分支>] [--token <TOKEN>] [--proxy <PROXY>]
#
#   --remote <名称>    远程仓库名称（默认 origin）
#   --branch <分支>    目标分支（默认当前分支的 upstream）
#   --token <TOKEN>    GitHub Personal Access Token（私有仓库拉取）
#   --proxy <URL>      HTTP 代理地址，如 http://127.0.0.1:6012
#
# 认证（优先级：--token > GITHUB_TOKEN > GH_TOKEN）：
#   GITHUB_TOKEN / GH_TOKEN  环境变量
#
# 代理（优先级：--proxy > ALL_PROXY > HTTPS_PROXY > HTTP_PROXY）：
#   ALL_PROXY / HTTPS_PROXY / HTTP_PROXY  环境变量
#
# 示例：
#   ./git-pull.sh
#   ./git-pull.sh --branch main
#   ./git-pull.sh --proxy http://127.0.0.1:6012
#   GITHUB_TOKEN=ghp_xxxxxx ALL_PROXY=http://127.0.0.1:6012 ./git-pull.sh
#
# 注意：
#   - 必须在 Git 仓库根目录执行
#   - 场景 1/3 会丢弃本地未提交改动与未推送提交（reflog 可恢复）
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
REMOTE=""
BRANCH=""
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
        --remote)
            if [ $# -lt 2 ]; then
                err "--remote 需要参数"
                exit 1
            fi
            REMOTE="$2"
            shift 2
            ;;
        --branch)
            if [ $# -lt 2 ]; then
                err "--branch 需要参数"
                exit 1
            fi
            BRANCH="$2"
            shift 2
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
            echo "用法: $0 [--remote <名称>] [--branch <分支>] [--token <TOKEN>] [--proxy <URL>]"
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
            err "未知参数: $1（本脚本无位置参数）"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    err "当前目录不是一个 Git 仓库"
    exit 1
fi

if [ -z "$REMOTE" ]; then
    REMOTE="origin"
fi
if ! git remote get-url "$REMOTE" > /dev/null 2>&1; then
    err "远程仓库 '$REMOTE' 不存在"
    exit 1
fi

# 目标 upstream：--branch > 当前分支 upstream > remote/当前分支
if [ -n "$BRANCH" ]; then
    UPSTREAM="$REMOTE/$BRANCH"
else
    UPSTREAM=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || true)
    if [ -z "$UPSTREAM" ]; then
        LOCAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        UPSTREAM="$REMOTE/$LOCAL_BRANCH"
    fi
fi

# 代理（仅当前进程生效，无需恢复）
if [ -n "$PROXY" ]; then
    export all_proxy="$PROXY" ALL_PROXY="$PROXY"
    export https_proxy="$PROXY" HTTPS_PROXY="$PROXY"
    export http_proxy="$PROXY" HTTP_PROXY="$PROXY"
    ok "已设置代理: $PROXY"
fi

# ---------------------------------------------------------------------------
# Token 注入（临时修改 remote URL，完成后恢复）
# ---------------------------------------------------------------------------
ORIG_REMOTE_URL=""
INJECTED=0

_inject_token() {
    if [ -n "$TOKEN" ]; then
        REMOTE_URL=$(git remote get-url "$REMOTE")
        if echo "$REMOTE_URL" | grep -q "^https://" && ! echo "$REMOTE_URL" | grep -q "@"; then
            ORIG_REMOTE_URL="$REMOTE_URL"
            git remote set-url "$REMOTE" "$(echo "$REMOTE_URL" | sed "s|https://|https://x-access-token:${TOKEN}@|")"
            INJECTED=1
            info "检测到 GitHub Token，正在注入认证信息..."
        fi
    fi
}

_restore_remote_url() {
    if [ "$INJECTED" -eq 1 ]; then
        git remote set-url "$REMOTE" "$ORIG_REMOTE_URL"
        ok "已清除 remote '$REMOTE' 中的 Token"
    fi
}

# ---------------------------------------------------------------------------
# 拉取远端更新
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Git 生产环境拉取工具（3 场景）             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
info "当前分支: $(git rev-parse --abbrev-ref HEAD)  目标: $UPSTREAM"
info "正在从 '$REMOTE' 拉取最新信息..."

_inject_token
if ! FETCH_OUT=$(git fetch "$REMOTE" 2>&1); then
    err "拉取失败，请检查网络/代理/Token 权限："
    echo "$FETCH_OUT" | sed 's/^/    /'
    _restore_remote_url
    exit 1
fi
[ -n "$FETCH_OUT" ] && echo "$FETCH_OUT" | sed 's/^/  /'
_restore_remote_url
ok "拉取完成"

# ---------------------------------------------------------------------------
# 状态概览
# ---------------------------------------------------------------------------
BEHIND=$(git rev-list --count "HEAD..$UPSTREAM" 2>/dev/null || echo "0")
AHEAD=$(git rev-list --count "$UPSTREAM..HEAD" 2>/dev/null || echo "0")
DIRTY=$(git status --short | grep -c . || true)

echo ""
if [ "$BEHIND" -gt 0 ]; then
    info "$UPSTREAM 领先本地 $BEHIND 个提交"
else
    info "$UPSTREAM 与本地已同步（无新提交）"
fi
[ "$AHEAD" -gt 0 ] && warn "本地领先 $UPSTREAM $AHEAD 个提交（未推送）"
[ "$DIRTY" -gt 0 ] && warn "本地有 $DIRTY 个未提交变更"

# ---------------------------------------------------------------------------
# 场景菜单
# ---------------------------------------------------------------------------
echo ""
echo "请选择拉取场景："
echo "  1) 放弃本地所有改动，以 GitHub 最新版本为准，拉取覆盖本地"
echo "  2) 先拉取 GitHub 最新版本，保留本地更改的文件；冲突时留本地的版本"
echo "  3) 列出 GitHub 上的每个更新，选择任意一个提交覆盖本地"
echo "  0) 退出"
echo ""
read -rp "  选择 [1/2/3/0]: " SCENE
case "$SCENE" in
    1|2|3) ;;
    0|"")
        info "已退出"
        exit 0
        ;;
    *)
        err "无效选择: $SCENE"
        exit 1
        ;;
esac

echo ""

# ---------------------------------------------------------------------------
# 丢弃提示与确认（场景 1/3 共用）
# ---------------------------------------------------------------------------
_discard_confirm() {
    local desc="$1"
    local dirty ahead untracked ans

    dirty=$(git status --short | grep -c . || true)
    ahead=$(git rev-list --count "$UPSTREAM..HEAD" 2>/dev/null || echo "0")
    untracked=$(git status --short | grep -c '^??' || true)

    warn "$desc"
    if [ "$dirty" -gt 0 ]; then
        warn "将丢弃 $dirty 个已跟踪文件的本地改动"
    fi
    if [ "$ahead" -gt 0 ]; then
        warn "将丢弃 $ahead 个本地未推送提交（reflog 中可恢复）"
    fi
    if [ "$untracked" -gt 0 ]; then
        warn "发现 $untracked 个未跟踪文件（默认保留，不会删除）："
        git status --short | grep '^??' | sed 's/^/    /'
    fi
    echo ""
    read -rp "确认继续？(y/N) " ans
    if [[ ! "$ans" =~ ^[Yy]$ ]]; then
        info "已取消"
        return 1
    fi
    return 0
}

# 未跟踪文件清理询问（场景 1/3 共用）
_clean_untracked_prompt() {
    local untracked ans
    untracked=$(git status --short | grep -c '^??' || true)
    if [ "$untracked" -gt 0 ]; then
        read -rp "是否同时删除 $untracked 个未跟踪文件？(y/N) " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            git clean -fd
            ok "已清理未跟踪文件"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 场景 1：以 GitHub 最新版本为准，覆盖本地
# ---------------------------------------------------------------------------
scene_1() {
    if ! _discard_confirm "场景 1：将把本地重置为 $UPSTREAM 最新版本"; then
        return
    fi

    git reset --hard "$UPSTREAM"
    ok "已重置到 $UPSTREAM（$(git log -1 --oneline "$UPSTREAM")）"

    _clean_untracked_prompt
}

# ---------------------------------------------------------------------------
# 场景 2：保留本地更改，冲突时以本地版本为准
# ---------------------------------------------------------------------------
scene_2() {
    local dirty stash_done conflicts f stash_err

    warn "场景 2：拉取最新版本并保留本地更改，冲突时以本地版本为准"
    dirty=$(git status --short | grep -c . || true)
    stash_done=0

    # 1. 备份本地未提交更改
    if [ "$dirty" -gt 0 ]; then
        info "正在备份本地未提交更改..."
        if git stash push -u -m "git-pull.sh 自动备份 $(date +%F_%H%M%S)"; then
            stash_done=1
            ok "已备份到 stash: $(git stash list | head -1 | cut -d: -f1)"
        else
            err "备份失败，中止场景 2"
            return
        fi
    fi

    # 2. 合并远端（保留本地已推送/未推送提交；文本冲突自动取本地版本）
    info "正在合并 $UPSTREAM 到当前分支..."
    if git merge --no-edit -X ours "$UPSTREAM"; then
        ok "合并完成"
    else
        err "合并失败（存在无法自动处理的冲突），请手动解决后恢复 stash"
        [ "$stash_done" -eq 1 ] && info "恢复命令: git stash pop"
        return
    fi

    # 3. 恢复本地未提交更改
    if [ "$stash_done" -eq 1 ]; then
        info "正在恢复本地未提交更改..."
        stash_err=$(mktemp)
        if git stash pop 2>"$stash_err"; then
            ok "本地未提交更改已恢复"
            rm -f "$stash_err"
        else
            # 处理恢复冲突：theirs = 本地之前的修改，留本地版本
            conflicts=$(git diff --name-only --diff-filter=U 2>/dev/null || true)
            if [ -n "$conflicts" ]; then
                warn "检测到 $(printf '%s\n' "$conflicts" | grep -c . || true) 个文件冲突，按\"留本地版本\"处理..."
                while IFS= read -r f; do
                    git checkout --theirs -- "$f" 2>/dev/null || true
                done <<< "$conflicts"
                git add -u 2>/dev/null || git add --all
                if git diff --name-only --diff-filter=U | grep -q .; then
                    err "仍有未解决冲突，请手动处理（stash 已保留: git stash list）"
                else
                    git stash drop
                    ok "冲突已按本地版本解决，stash 备份已清除"
                fi
            else
                err "恢复未提交更改失败（可能是未跟踪文件与远端同名冲突），stash 备份已保留："
                sed 's/^/    /' "$stash_err"
                info "手动处理: git stash pop，解决冲突后 git stash drop"
            fi
            rm -f "$stash_err"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 场景 3：列出 GitHub 更新，选择任意提交覆盖本地
# ---------------------------------------------------------------------------
scene_3() {
    local commits count choice target i line

    commits=$(git log --oneline "HEAD..$UPSTREAM" 2>/dev/null || true)
    count=$(printf '%s\n' "$commits" | grep -c . || true)
    if [ "$count" -eq 0 ]; then
        warn "$UPSTREAM 没有新提交，本地已是最新"
        return
    fi

    echo "GitHub 远端新增提交（共 $count 个，从新到旧）："
    i=0
    while IFS= read -r line; do
        i=$((i + 1))
        printf '  [%2d] %s\n' "$i" "$line"
    done <<< "$commits"
    echo ""

    read -rp "输入编号或提交 ID（留空取消）: " choice
    if [ -z "$choice" ]; then
        info "已取消"
        return
    fi

    if [[ "$choice" =~ ^[0-9]+$ ]]; then
        target=$(printf '%s\n' "$commits" | sed -n "${choice}p" | awk '{print $1}')
        if [ -z "$target" ]; then
            err "编号超出范围（1-$count）"
            return
        fi
    else
        if ! git rev-parse --verify --quiet "$choice^{commit}" > /dev/null 2>&1; then
            err "提交不存在: $choice"
            return
        fi
        target="$choice"
    fi

    echo ""
    info "选中提交: $(git log -1 --oneline "$target")"

    if ! _discard_confirm "场景 3：将把本地重置为选中提交（$target）"; then
        return
    fi

    git reset --hard "$target"
    ok "已重置到 $target（$(git log -1 --oneline "$target")）"

    _clean_untracked_prompt
}

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
case "$SCENE" in
    1) scene_1 ;;
    2) scene_2 ;;
    3) scene_3 ;;
esac

echo ""
separator="──────────────────────────────────────────────────────────"
echo -e "${CYAN}${separator}${NC}"
info "当前仓库状态："
git log --oneline -3
echo ""
git status --short | sed 's/^/  /' || true
echo -e "${CYAN}${separator}${NC}"
echo ""
