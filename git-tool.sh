#!/usr/bin/env bash
# ============================================================================
# git-tool.sh — Git 一体化交互工具（合并自 git-commit.sh / git-pull.sh / git-purge.sh）
#
# 功能：
#   一个脚本覆盖日常 Git 全部操作场景：
#     场景 A（提交）   ：有未提交变更 → 提交并推送到 GitHub
#     场景 B（推送）   ：有本地提交未推送 → 仅推送
#     场景 C（拉取）   ：生产/测试服务器同步远端更新（3 种处理方式）
#     场景 D（清理）   ：彻底删除文件（含历史 + .gitignore + 可选强推）
#
# 用法（交互引导模式）：
#   ./git-tool.sh
#     自动诊断仓库状态 → 给出操作建议 → 菜单选择 → 分步引导执行
#
# 用法（命令行直通模式）：
#   ./git-tool.sh status                # 查看仓库状态概览
#   ./git-tool.sh commit                # 提交并推送（交互：暂存→备注→确认）
#   ./git-tool.sh push                  # 仅推送未推送的本地提交
#   ./git-tool.sh pull                  # 拉取远端更新（3 场景选择）
#   ./git-tool.sh purge <路径>          # 彻底删除文件/目录（含全部历史）
#
# 通用选项（所有子命令可用）：
#   --remote <名称>   远程仓库名称（默认 origin）
#   --branch <分支>   目标分支（默认当前分支的 upstream）
#   --token <TOKEN>   GitHub Personal Access Token（私有仓库；优先级 > 环境变量）
#   --proxy <URL>     HTTP 代理地址，如 http://127.0.0.1:6012
#
# 认证（优先级：--token > GITHUB_TOKEN > GH_TOKEN）
# 代理（优先级：--proxy > ALL_PROXY > HTTPS_PROXY > HTTP_PROXY）
#
# 示例：
#   ./git-tool.sh
#   ./git-tool.sh commit
#   ./git-tool.sh push
#   ./git-tool.sh pull --proxy http://127.0.0.1:6012
#   ./git-tool.sh purge config.db --push
#   GITHUB_TOKEN=ghp_xxx ALL_PROXY=http://127.0.0.1:6012 ./git-tool.sh pull
#
# 注意：
#   - 必须在 Git 仓库根目录执行
#   - 交互模式每个确认都有默认值与危险提示，回车即选推荐项
#   - pull 场景 1/3 与 purge --push 会丢弃/重写内容，务必看清警告
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 基础工具
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

separator() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 确认（默认 N，y 才通过）
confirm_yn() {
    local prompt="$1" ans
    read -rp "$prompt (y/N) " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

# 确认（默认 Y，n 取消）
confirm_default() {
    local prompt="$1" ans
    read -rp "$prompt (Y/n) " ans
    [[ ! "$ans" =~ ^[Nn]$ ]]
}

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
REMOTE="" BRANCH="" TOKEN="" PROXY="" UPSTREAM="" COMMIT_MSG="" TARGET="" ACTION=""
BEHIND=0 AHEAD=0 DIRTY=0 UNTRACKED=0 UNPUSHED=0
INJECTED=0 ORIG_REMOTE_URL=""

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
parse_env_credentials() {
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        TOKEN="$GITHUB_TOKEN"
    elif [ -n "${GH_TOKEN:-}" ]; then
        TOKEN="$GH_TOKEN"
    fi
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
}

parse_args() {
    parse_env_credentials
    while [ $# -gt 0 ]; do
        case "$1" in
            --remote)
                [ $# -lt 2 ] && { err "--remote 需要参数"; exit 1; }
                REMOTE="$2"; shift 2 ;;
            --branch)
                [ $# -lt 2 ] && { err "--branch 需要参数"; exit 1; }
                BRANCH="$2"; shift 2 ;;
            --token)
                [ $# -lt 2 ] && { err "--token 需要参数"; exit 1; }
                TOKEN="$2"; shift 2 ;;
            --proxy)
                [ $# -lt 2 ] && { err "--proxy 需要参数"; exit 1; }
                PROXY="$2"; shift 2 ;;
            --help|-h)
                usage; exit 0 ;;
            -*)
                err "未知选项: $1"; exit 1 ;;
            *)
                if [ -z "$ACTION" ]; then
                    ACTION="$1"; shift
                else
                    [ -n "$TARGET" ] && { err "只能指定一个路径: $TARGET / $1"; exit 1; }
                    TARGET="$1"; shift
                fi
                ;;
        esac
    done
}

usage() {
    echo "用法: $0 [子命令] [选项]"
    echo ""
    echo "子命令（省略则进入交互引导模式，自动诊断并推荐操作）："
    echo "  status        查看仓库状态概览"
    echo "  commit        提交并推送（交互：暂存→备注→确认）"
    echo "  push          仅推送未推送的本地提交"
    echo "  pull          拉取远端更新（3 场景选择）"
    echo "  purge <路径>  彻底删除文件/目录（含全部历史，可选 --push 强推覆盖远程）"
    echo ""
    echo "选项："
    echo "  --remote <名称>  远程仓库名称（默认 origin）"
    echo "  --branch <分支>  目标分支（默认当前分支 upstream）"
    echo "  --token <TOKEN>  GitHub Personal Access Token"
    echo "  --proxy <URL>    HTTP 代理地址"
    echo ""
    echo "认证环境变量: GITHUB_TOKEN, GH_TOKEN"
    echo "代理环境变量: ALL_PROXY, HTTPS_PROXY, HTTP_PROXY"
}

require_repo() {
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        err "当前目录不是 Git 仓库"
        exit 1
    fi
}

resolve_upstream() {
    [ -z "$REMOTE" ] && REMOTE="origin"
    if ! git remote get-url "$REMOTE" > /dev/null 2>&1; then
        err "远程仓库 '$REMOTE' 不存在"
        exit 1
    fi
    if [ -n "$BRANCH" ]; then
        UPSTREAM="$REMOTE/$BRANCH"
    else
        UPSTREAM=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || true)
        if [ -z "$UPSTREAM" ]; then
            UPSTREAM="$REMOTE/$(git rev-parse --abbrev-ref HEAD)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 网络与认证（token 注入 / 代理，操作后恢复）
# ---------------------------------------------------------------------------
setup_proxy() {
    if [ -n "$PROXY" ]; then
        export all_proxy="$PROXY" ALL_PROXY="$PROXY"
        export https_proxy="$PROXY" HTTPS_PROXY="$PROXY"
        export http_proxy="$PROXY" HTTP_PROXY="$PROXY"
        ok "已设置代理: $PROXY"
    fi
}

inject_token() {
    INJECTED=0
    ORIG_REMOTE_URL=""
    if [ -n "$TOKEN" ]; then
        local url
        url=$(git remote get-url "$REMOTE")
        if echo "$url" | grep -q "^https://" && ! echo "$url" | grep -q "@"; then
            ORIG_REMOTE_URL="$url"
            git remote set-url "$REMOTE" "$(echo "$url" | sed "s|https://|https://x-access-token:${TOKEN}@|")"
            INJECTED=1
            info "检测到 GitHub Token，正在注入认证信息..."
        fi
    fi
}

restore_remote_url() {
    if [ "$INJECTED" -eq 1 ]; then
        git remote set-url "$REMOTE" "$ORIG_REMOTE_URL"
        ok "已清除 remote '$REMOTE' 中的 Token"
        INJECTED=0
    fi
}

# ---------------------------------------------------------------------------
# 状态诊断与展示
# ---------------------------------------------------------------------------
analyze() {
    BEHIND=0 AHEAD=0 DIRTY=0 UNTRACKED=0 UNPUSHED=0
    BEHIND=$(git rev-list --count "HEAD..$UPSTREAM" 2>/dev/null || echo "0")
    AHEAD=$(git rev-list --count "$UPSTREAM..HEAD" 2>/dev/null || echo "0")
    DIRTY=$(git status --short | grep -c . || true)
    UNTRACKED=$(git status --short | grep -c '^??' || true)
    UNPUSHED=$AHEAD
}

show_status() {
    separator
    info "当前分支状态"
    separator
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "（无分支）")
    echo -e "  分支: ${YELLOW}${branch}${NC}   目标: $UPSTREAM"

    if ! git rev-parse --abbrev-ref "@{upstream}" > /dev/null 2>&1; then
        warn "  当前分支没有远程跟踪分支（首次推送请用: git push -u $REMOTE $branch）"
    fi

    if [ "$BEHIND" -gt 0 ]; then
        warn "  落后远程 ${BEHIND} 个提交（建议运行: git-tool.sh pull）"
    fi
    if [ "$AHEAD" -gt 0 ]; then
        info "  领先远程 ${AHEAD} 个提交（未推送）"
    fi
    if [ "$BEHIND" -eq 0 ] && [ "$AHEAD" -eq 0 ]; then
        info "  与远程已同步"
    fi

    echo ""
    info "未暂存变更（已修改但未 git add）:"
    separator
    git status --short 2>/dev/null || true

    echo ""
    info "详细变更统计:"
    separator
    git diff --stat 2>/dev/null || true

    if [ "$UNTRACKED" -gt 0 ]; then
        echo ""
        warn "发现 ${UNTRACKED} 个未跟踪文件（可用 'git add <文件>' 添加）"
        git status --short | grep '^??' | sed 's/^/    /'
    fi
}

# 生成建议（供交互引导展示）
suggest() {
    echo ""
    separator
    echo -e "${YELLOW}状态诊断与建议${NC}"
    separator
    echo "  分支: $(git rev-parse --abbrev-ref HEAD)  目标: $UPSTREAM"
    [ "$BEHIND" -gt 0 ]  && echo "  · 落后远程 ${BEHIND} 个提交"
    [ "$AHEAD" -gt 0 ]   && echo "  · 领先远程 ${AHEAD} 个提交（未推送）"
    [ "$DIRTY" -gt 0 ]   && echo "  · ${DIRTY} 个未提交变更（其中 ${UNTRACKED} 个未跟踪）"
    [ "$BEHIND" -eq 0 ] && [ "$AHEAD" -eq 0 ] && [ "$DIRTY" -eq 0 ] && echo "  · 工作区与远程完全同步"

    echo ""
    if [ "$BEHIND" -gt 0 ] && [ "$DIRTY" -gt 0 ] && [ "$AHEAD" -gt 0 ]; then
        echo "  🎯 建议 1: 先「提交并推送」完成本地工作，再「拉取更新」同步远端（可能需处理分叉）"
        echo "  🎯 建议 2: 只同步远端 → 「拉取更新」，选场景 2 可保留本地修改"
    elif [ "$BEHIND" -gt 0 ] && [ "$DIRTY" -gt 0 ]; then
        echo "  🎯 建议: 「拉取更新」并选场景 2（保留本地修改；远端更新将并入本地）"
    elif [ "$BEHIND" -gt 0 ] && [ "$AHEAD" -gt 0 ]; then
        echo "  ⚠️  本地与远端已分叉（各 ${BEHIND}/${AHEAD} 个提交）"
        echo "  🎯 建议: 「拉取更新」选场景 2 合并；若有冲突倾向请先备份重要文件"
    elif [ "$BEHIND" -gt 0 ]; then
        echo "  🎯 建议: 「拉取更新」选场景 1（本地无改动，直接同步到远端最新版）"
    elif [ "$DIRTY" -gt 0 ]; then
        echo "  🎯 建议: 「提交并推送」把本次变更发布（回车默认即此项）"
    elif [ "$AHEAD" -gt 0 ]; then
        echo "  🎯 建议: 「仅推送」把 ${AHEAD} 个本地提交同步到 GitHub"
    else
        echo "  🎯 无待处理内容；可用「查看完整状态」确认，或退出"
    fi
}

# ============================================================================
# 场景 A：提交并推送（原 git-commit.sh）
# ============================================================================

stage_files() {
    separator
    info "如何暂存文件？(y=暂存所有已跟踪变更 / i=逐个选择文件添加 / n=跳过)"
    info "提示: 未跟踪的新文件（??）不会被自动暂存，需用 i 逐个添加，或先手动 git add"
    read -r -p "  选择 [Y/i/n]: " choice
    case "$choice" in
        [Nn]*)
            info "跳过自动暂存，你可以手动 git add 后重新运行"
            exit 0
            ;;
        [Ii]*)
            info "进入交互式暂存模式（输入文件路径，空行结束）:"
            echo ""
            while true; do
                read -r -p "  添加文件（留空结束）: " filepath
                [ -z "$filepath" ] && break
                if git add "$filepath" 2>/dev/null; then
                    ok "已暂存: $filepath"
                else
                    err "添加失败: $filepath"
                fi
            done
            ;;
        *)
            git add -u
            ok "已暂存所有已跟踪文件的变更"
            ;;
    esac

    local staged_count
    staged_count=$(git diff --cached --stat 2>/dev/null | tail -1 | grep -oP '\d+ file' | grep -oP '\d+' || echo "0")
    if [ "$staged_count" = "0" ]; then
        warn "暂存区为空，没有需要提交的内容"
        exit 0
    fi

    echo ""
    info "当前暂存区内容:"
    separator
    git diff --cached --stat 2>/dev/null || true
}

generate_auto_summary() {
    local status_lines total mods adds dels renames untracked
    local title detail body parts

    status_lines=$(git status --short 2>/dev/null || true)
    if [ -z "$status_lines" ]; then
        return 1
    fi

    total=$(printf '%s\n' "$status_lines" | grep -c . || true)
    mods=$(printf '%s\n' "$status_lines" | awk '{c=substr($1,1,1); if (c=="M") n++} END {print n+0}')
    adds=$(printf '%s\n' "$status_lines" | awk '{c=substr($1,1,1); if (c=="A") n++} END {print n+0}')
    dels=$(printf '%s\n' "$status_lines" | awk '{c=substr($1,1,1); if (c=="D") n++} END {print n+0}')
    renames=$(printf '%s\n' "$status_lines" | awk '{c=substr($1,1,1); if (c=="R") n++} END {print n+0}')
    untracked=$(printf '%s\n' "$status_lines" | awk '{c=substr($1,1,1); if (c=="?") n++} END {print n+0}')

    parts=()
    [ "$mods" -gt 0 ] && parts+=("${mods} 修改")
    [ "$adds" -gt 0 ] && parts+=("${adds} 新增")
    [ "$dels" -gt 0 ] && parts+=("${dels} 删除")
    [ "$renames" -gt 0 ] && parts+=("${renames} 重命名")
    detail=$(IFS=' / '; echo "${parts[*]}")
    title="更新 ${total} 个文件（${detail}）"
    [ "$untracked" -gt 0 ] && title="${title}；${untracked} 个未跟踪"

    body=$(printf '%s\n' "$status_lines")

    printf '%s\n\n%s\n' "$title" "$body"
}

input_message_manual() {
    local msg=""
    local lines=()
    local empty_count=0

    separator
    info "请输入提交备注"
    info "提示: 首行作为标题，空行后写详细描述（输入空行结束）"
    separator

    while IFS= read -r -p "  > " line; do
        if [ -z "$line" ]; then
            empty_count=$((empty_count + 1))
            [ "$empty_count" -ge 1 ] && break
            lines+=("")
        else
            empty_count=0
            lines+=("$line")
        fi
    done

    msg=$(printf "%s\n" "${lines[@]}")

    if [ -z "$msg" ]; then
        err "备注不能为空！"
        exit 1
    fi

    COMMIT_MSG="$msg"
}

input_message() {
    local auto_summary

    separator
    info "正在自动生成未提交变更摘要..."
    if auto_summary=$(generate_auto_summary); then
        separator
        info "已生成变更摘要（可作提交备注）："
        echo "$auto_summary" | sed 's/^/  /'
        echo ""
        warn "使用此摘要作为提交备注？(y=使用 / n=手动输入 / q=取消)"
        read -r -p "  选择 [Y/n/q]: " use_auto
        case "$use_auto" in
            [Qq]*)
                info "已取消"
                exit 0
                ;;
            [Nn]*)
                input_message_manual
                ;;
            *)
                COMMIT_MSG="$auto_summary"
                ;;
        esac
    else
        warn "工作区无已暂存变更，请手动输入备注"
        input_message_manual
    fi
}

cmd_commit() {
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     场景 A：提交并推送                        ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    show_status
    stage_files
    input_message
    confirm_and_commit
}

confirm_and_commit() {
    separator
    echo -e "${YELLOW}提交确认${NC}"
    separator
    echo ""
    echo "  分支: $(git rev-parse --abbrev-ref HEAD)"
    echo ""
    echo "  备注:"
    echo "$COMMIT_MSG" | sed 's/^/    /'
    echo ""
    echo "  变更文件:"
    git diff --cached --stat | sed 's/^/    /'
    echo ""
    separator

    warn "是否提交并推送到 GitHub？"
    read -r -p "  选择 [y/N]: " confirm

    case "$confirm" in
        [Yy]*)
            info "正在提交..."
            if git commit -m "$COMMIT_MSG"; then
                ok "提交成功"
            else
                err "提交失败"
                exit 1
            fi

            echo ""
            push_flow
            ;;
        [Ee]*)
            info "请重新输入备注"
            input_message
            confirm_and_commit
            ;;
        *)
            warn "已取消"
            exit 0
            ;;
    esac
}

# ============================================================================
# 场景 B：仅推送本地提交（原 git-commit.sh push_only）
# ============================================================================

push_flow() {
    info "正在推送到 GitHub..."
    setup_proxy
    inject_token
    if git push; then
        restore_remote_url
        ok "推送成功 ✅"
        separator
        echo ""
        echo "  最新提交:"
        git log --oneline -3 | sed 's/^/    /'
        echo ""
        separator
    else
        restore_remote_url
        err "推送失败，请检查网络或权限"
        exit 1
    fi
}

cmd_push() {
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     场景 B：仅推送本地提交                     ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    show_status
    if [ "$AHEAD" -eq 0 ]; then
        warn "没有未推送的本地提交（与远程已同步）"
        exit 0
    fi

    separator
    info "未推送的本地提交："
    separator
    git log "@{upstream}"..HEAD --oneline 2>/dev/null | sed 's/^/  /'
    echo ""

    if ! confirm_yn "是否推送到 GitHub？"; then
        info "已取消"
        exit 0
    fi

    push_flow
}

# ============================================================================
# 场景 C：拉取远端更新（原 git-pull.sh）
# ============================================================================

_discard_confirm() {
    local desc="$1" ans

    warn "$desc"
    if [ "$DIRTY" -gt 0 ]; then
        warn "将丢弃 $DIRTY 个已跟踪文件的本地改动"
    fi
    if [ "$AHEAD" -gt 0 ]; then
        warn "将丢弃 $AHEAD 个本地未推送提交（reflog 中可恢复）"
    fi
    if [ "$UNTRACKED" -gt 0 ]; then
        warn "发现 $UNTRACKED 个未跟踪文件（默认保留，不会删除）："
        git status --short | grep '^??' | sed 's/^/    /'
    fi
    echo ""
    if ! confirm_yn "确认继续？"; then
        info "已取消"
        return 1
    fi
    return 0
}

_clean_untracked_prompt() {
    if [ "$UNTRACKED" -gt 0 ]; then
        if confirm_yn "是否同时删除 $UNTRACKED 个未跟踪文件？"; then
            git clean -fd
            ok "已清理未跟踪文件"
        fi
    fi
}

scene_1() {
    if ! _discard_confirm "场景 1：将把本地重置为 $UPSTREAM 最新版本"; then
        return
    fi

    git reset --hard "$UPSTREAM"
    ok "已重置到 $UPSTREAM（$(git log -1 --oneline "$UPSTREAM")）"

    _clean_untracked_prompt
}

scene_2() {
    local dirty stash_done=0 conflicts stash_err f

    warn "场景 2：拉取最新版本并保留本地更改，冲突时以本地版本为准"
    dirty=$(git status --short | grep -c . || true)

    if [ "$dirty" -gt 0 ]; then
        info "正在备份本地未提交更改..."
        if git stash push -u -m "git-tool.sh 自动备份 $(date +%F_%H%M%S)"; then
            stash_done=1
            ok "已备份到 stash: $(git stash list | head -1 | cut -d: -f1)"
        else
            err "备份失败，中止场景 2"
            return
        fi
    fi

    info "正在合并 $UPSTREAM 到当前分支..."
    if git merge --no-edit -X ours "$UPSTREAM"; then
        ok "合并完成"
    else
        err "合并失败（存在无法自动处理的冲突），请手动解决后恢复 stash"
        [ "$stash_done" -eq 1 ] && info "恢复命令: git stash pop"
        return
    fi

    if [ "$stash_done" -eq 1 ]; then
        info "正在恢复本地未提交更改..."
        stash_err=$(mktemp)
        if git stash pop 2>"$stash_err"; then
            ok "本地未提交更改已恢复"
            rm -f "$stash_err"
        else
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

cmd_pull() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     场景 C：拉取远端更新（3 场景）             ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    require_repo
    resolve_upstream
    info "当前分支: $(git rev-parse --abbrev-ref HEAD)  目标: $UPSTREAM"
    info "正在从 '$REMOTE' 拉取最新信息..."

    setup_proxy
    inject_token
    if ! FETCH_OUT=$(git fetch "$REMOTE" 2>&1); then
        err "拉取失败，请检查网络/代理/Token 权限："
        echo "$FETCH_OUT" | sed 's/^/    /'
        restore_remote_url
        exit 1
    fi
    [ -n "$FETCH_OUT" ] && echo "$FETCH_OUT" | sed 's/^/  /'
    restore_remote_url
    ok "拉取完成"

    analyze

    echo ""
    if [ "$BEHIND" -gt 0 ]; then
        info "$UPSTREAM 领先本地 $BEHIND 个提交"
    else
        info "$UPSTREAM 与本地已同步（无新提交）"
    fi
    [ "$AHEAD" -gt 0 ] && warn "本地领先 $UPSTREAM $AHEAD 个提交（未推送）"
    [ "$DIRTY" -gt 0 ] && warn "本地有 $DIRTY 个未提交变更"

    # 场景建议
    echo ""
    if [ "$BEHIND" -eq 0 ]; then
        info "没有远端更新，无需拉取"
        if [ "$AHEAD" -gt 0 ]; then
            info "本地有 ${AHEAD} 个未推送提交，可运行: git-tool.sh push"
        fi
        exit 0
    elif [ "$DIRTY" -eq 0 ] && [ "$AHEAD" -eq 0 ]; then
        warn "推荐选择: 1（本地无改动，直接同步到远端最新版）"
    elif [ "$DIRTY" -gt 0 ]; then
        warn "推荐选择: 2（保留本地修改，冲突时留本地版本）"
    fi

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
    case "$SCENE" in
        1) scene_1 ;;
        2) scene_2 ;;
        3) scene_3 ;;
    esac

    echo ""
    separator
    info "当前仓库状态："
    git log --oneline -3
    echo ""
    git status --short | sed 's/^/  /' || true
    separator
    echo ""
}

# ============================================================================
# 场景 D：彻底删除文件（原 git-purge.sh）
# ============================================================================

cmd_purge() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     场景 D：彻底删除文件（含历史）             ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    require_repo

    # 交互模式下引导输入路径
    if [ -z "$TARGET" ]; then
        read -rp "请输入要彻底删除的文件/目录路径（留空取消）: " TARGET
        [ -z "$TARGET" ] && { info "已取消"; exit 0; }
    fi

    if ! git diff --quiet HEAD 2>/dev/null; then
        warn "工作区有未提交的修改，建议先 commit 或 stash"
        if ! confirm_yn "是否继续？"; then
            info "已取消"
            exit 0
        fi
    fi

    if [ ! -e "$TARGET" ] && ! git ls-files --error-unmatch "$TARGET" > /dev/null 2>&1; then
        warn "路径 '$TARGET' 既不在磁盘上也不在 Git 跟踪中，将继续尝试从历史中清理"
    fi

    echo ""
    warn "╔══════════════════════════════════════════════════════════════╗"
    warn "║  此操作将 永久删除 '$TARGET' 的 全部历史记录！    ║"
    warn "║  提交历史将被重写，所有协作者需要重新 clone。              ║"
    warn "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    if ! confirm_yn "确定要执行？"; then
        info "已取消"
        exit 0
    fi

    # Step 1: 加入 .gitignore
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

    # Step 2: 取消跟踪
    echo ""
    info "Step 2/5 — 取消跟踪 '$TARGET'"
    if git ls-files --error-unmatch "$TARGET" > /dev/null 2>&1; then
        git rm --cached -r "$TARGET" 2>/dev/null || true
        ok "已取消跟踪"
    else
        info "未在跟踪中，跳过"
    fi

    # Step 3: 提交 .gitignore 变更
    echo ""
    info "Step 3/5 — 提交 .gitignore 变更"
    if git diff --cached --quiet; then
        info "无变更需要提交，跳过"
    else
        git add .gitignore
        LOCAL_SUMMARY=$(git status --short 2>/dev/null | grep -v '\.gitignore$' || true)
        if [ -n "$LOCAL_SUMMARY" ]; then
            git commit -m "把 $TARGET 加入 .gitignore 并取消跟踪

本地未提交变更摘要：
$LOCAL_SUMMARY"
        else
            git commit -m "把 $TARGET 加入 .gitignore 并取消跟踪"
        fi
        ok "已提交"
    fi

    # Step 4: 从全部历史中抹除
    echo ""
    info "Step 4/5 — 从全部提交历史中抹除 '$TARGET'"
    info "此步骤可能需要较长时间，取决于历史长度..."

    STASHED=0
    if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git status --short 2>/dev/null)" ]; then
        warn "工作区有未提交变更，filter-branch 需要干净工作区，自动暂存..."
        if git stash push -u -m "git-tool.sh 自动备份 $(date +%F_%H%M%S)"; then
            STASHED=1
            ok "已暂存未提交变更: $(git stash list | head -1 | cut -d: -f1)"
        else
            err "自动暂存失败，请手动 git stash 后重试"
            exit 1
        fi
    fi

    export FILTER_BRANCH_SQUELCH_WARNING=1

    REFS_TO_REWRITE=$(git for-each-ref --format='%(refname)' | grep -Ev '^refs/stash$|^refs/original/' || true)
    if [ -z "$REFS_TO_REWRITE" ]; then
        err "没有可重写的引用"
        exit 1
    fi

    git filter-branch --force --index-filter \
        "git rm --cached --ignore-unmatch -r \"$TARGET\"" \
        --prune-empty -- $REFS_TO_REWRITE

    ok "历史重写完成"

    # Step 5: 清理残留引用和对象
    echo ""
    info "Step 5/5 — 清理残留引用和回收磁盘空间"

    git for-each-ref --format='delete %(refname)' refs/original | \
        git update-ref --stdin 2>/dev/null || true

    git reflog expire --expire=now --all
    git gc --prune=now --aggressive 2>/dev/null || git gc --prune=now

    ok "清理完成"

    if [ "$STASHED" -eq 1 ]; then
        echo ""
        info "恢复暂存的未提交变更..."
        if git stash pop; then
            ok "已恢复未提交变更"
        else
            warn "恢复失败（可能有冲突），请手动执行: git stash pop"
        fi
    fi

    echo ""
    ok "╔══════════════════════════════════════════════════════════════╗"
    ok "║   '$TARGET' 已从仓库中彻底删除！              ║"
    ok "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    git log --oneline -3
    echo ""

    # 可选：强制推送到远程
    purge_push_remote
}

purge_push_remote() {
    local REMOTES confirm

    REMOTES=$(git remote)
    if [ -z "$REMOTES" ]; then
        warn "未配置远程仓库，跳过推送"
        return
    fi

    echo ""
    warn "即将强制推送到以下远程仓库（覆盖全部历史）："
    git remote -v
    echo ""
    if ! confirm_yn "确认强制推送？"; then
        info "跳过推送"
        echo ""
        info "如需稍后推送覆盖远程历史: git push --force --all $REMOTE"
        return
    fi

    setup_proxy
    inject_token

    info "正在强制推送（覆盖远程历史）..."
    if git push --force --all "$REMOTE" 2>&1; then
        ok "推送完成"
        git push --force --tags "$REMOTE" 2>/dev/null || true
    else
        err "推送失败，请检查网络/代理/Token 权限"
    fi
    restore_remote_url

    info "提示：其他协作者需要执行 git rebase 或重新 clone 以同步"
}

# ============================================================================
# 交互引导模式（无子命令时）
# ============================================================================

interactive_main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║      Git 一体化交互工具（git-tool）          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    require_repo
    resolve_upstream
    analyze
    suggest

    echo ""
    echo "请选择操作："
    if [ "$DIRTY" -gt 0 ]; then
        echo "  [1] 提交并推送（${DIRTY} 个未提交变更）${YELLOW}← 推荐${NC}"
    else
        echo "  [1] 提交并推送（当前无未提交变更）"
    fi
    if [ "$AHEAD" -gt 0 ]; then
        echo "  [2] 仅推送本地提交（${AHEAD} 个）${YELLOW}← 推荐${NC}"
    else
        echo "  [2] 仅推送本地提交（无未推送提交）"
    fi
    if [ "$BEHIND" -gt 0 ]; then
        echo "  [3] 拉取远端更新（领先本地 ${BEHIND} 个提交）${YELLOW}← 推荐${NC}"
    else
        echo "  [3] 拉取远端更新（已同步）"
    fi
    echo "  [4] 彻底删除文件（历史清理，慎用）"
    echo "  [5] 查看完整仓库状态"
    echo "  [0] 退出"
    echo ""
    read -rp "  选择 [0-5]（回车默认 ${DEFAULT_CHOICE}）: " choice

    case "${choice:-$DEFAULT_CHOICE}" in
        1) cmd_commit ;;
        2) cmd_push ;;
        3) cmd_pull ;;
        4) cmd_purge ;;
        5) show_status ;;
        0|"") info "已退出"; exit 0 ;;
        *) err "无效选择: $choice"; exit 1 ;;
    esac
}

# ============================================================================
# 入口
# ============================================================================

main() {
    parse_args "$@"

    case "$ACTION" in
        "")
            # 交互引导：根据状态计算默认推荐
            require_repo
            resolve_upstream
            analyze
            DEFAULT_CHOICE=0
            if [ "$DIRTY" -gt 0 ]; then
                DEFAULT_CHOICE=1
            elif [ "$AHEAD" -gt 0 ]; then
                DEFAULT_CHOICE=2
            elif [ "$BEHIND" -gt 0 ]; then
                DEFAULT_CHOICE=3
            fi
            interactive_main
            ;;
        status)
            require_repo
            resolve_upstream
            analyze
            show_status
            ;;
        commit)
            require_repo
            resolve_upstream
            analyze
            cmd_commit
            ;;
        push)
            require_repo
            resolve_upstream
            analyze
            cmd_push
            ;;
        pull)
            cmd_pull
            ;;
        purge)
            cmd_purge
            ;;
        *)
            err "未知子命令: $ACTION"
            usage
            exit 1
            ;;
    esac
}

main "$@"