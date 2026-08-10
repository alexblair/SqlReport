#!/bin/bash
# ============================================================================
# git-commit.sh — 交互式 Git 提交脚本
# 功能：显示状态 → 选择暂存文件 → 输入备注 → 确认后提交并推送
#
# 使用场景：
#   日常开发机使用。写完代码、修改/新增/删除文件后，运行本脚本：
#   自动生成变更摘要作提交备注 → 确认后提交并推送到 GitHub。
#   适合不想记 git 命令、懒得手写提交备注的开发者。
#
#   何时用：每次开发迭代完成，有未提交变更需要上传时。
#   何时不用：本脚本只做"提交+推送"，不做拉取、不解决冲突。
#   先拉取远端更新请用 git-pull.sh；彻底删除文件（含历史）请用 git-purge.sh。
#
# 注意：
#   - 必须在 Git 仓库根目录执行
#   - 默认只暂存已跟踪文件的变更（git add -u），未跟踪文件需手动 git add
# ============================================================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# 辅助函数
# ============================================================================

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

# 打印分隔线
separator() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# 步骤 1：显示仓库状态
# ============================================================================

show_status() {
    separator
    info "当前分支状态"
    separator

    # 当前分支信息
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "（无分支）")
    echo "  分支: ${YELLOW}${branch}${NC}"

    # 远程同步状态
    local ahead_behind
    ahead_behind=$(git rev-list --count --left-right "@{upstream}"...HEAD 2>/dev/null || echo "0 0")
    local behind="${ahead_behind%% *}"
    local ahead="${ahead_behind##* }"
    if [ "$behind" -gt 0 ] 2>/dev/null; then
        warn "  落后远程 ${behind} 个提交，请先 git pull"
    fi
    if [ "$ahead" -gt 0 ] 2>/dev/null; then
        info "  领先远程 ${ahead} 个提交（未推送）"
    fi

    echo ""
    info "未暂存变更（已修改但未 git add）:"
    separator

    # git status 短格式
    git status --short 2>/dev/null || true

    echo ""
    info "详细变更统计:"
    separator

    git diff --stat 2>/dev/null || true

    local has_untracked
    has_untracked=$(git status --short | grep -c '^??' 2>/dev/null || true)
    if [ "$has_untracked" -gt 0 ]; then
        echo ""
        warn "发现 ${has_untracked} 个未跟踪文件（可用 'git add <文件>' 添加）"
    fi
}

# ============================================================================
# 步骤 2：交互式暂存文件
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
            # 交互式暂存
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
            # 默认暂存所有已跟踪文件 + 删除
            git add -u
            ok "已暂存所有已跟踪文件的变更"
            ;;
    esac

    # 检查是否有已暂存内容
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

# ============================================================================
# 步骤 3：输入提交备注
# ============================================================================

# 自动生成未提交变更摘要（基于 git status --short）
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

# 手动输入提交备注
input_message_manual() {
    local msg=""

    separator
    info "请输入提交备注"
    info "提示: 首行作为标题，空行后写详细描述（输入 EOF 或 空行两次结束）"
    separator

    # 收集多行输入
    local lines=()
    local empty_count=0

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

    # 移除末尾多余空行
    while [ ${#lines[@]} -gt 0 ] && [ -z "${lines[-1]}" ]; do
        unset 'lines[-1]'
    done

    # 合并为字符串
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

# ============================================================================
# 步骤 4：确认并提交
# ============================================================================

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

    warn "是否提交并推送到 GitHub？(y/n)"
    read -r -p "  选择 [y/N]: " confirm

    case "$confirm" in
        [Yy]*)
            info "正在提交..."
            # 提交
            if git commit -m "$COMMIT_MSG"; then
                ok "提交成功"
            else
                err "提交失败"
                exit 1
            fi

            echo ""
            info "正在推送到 GitHub..."
            if git push; then
                ok "推送成功 ✅"
                separator
                echo ""
                git log --oneline -3
                echo ""
                separator
            else
                err "推送失败，请检查网络或权限"
                exit 1
            fi
            ;;
        [Ee]*)
            # 重新编辑备注
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
# 入口
# ============================================================================

main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║      Git 交互式提交工具                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    # 检查是否在 git 仓库中
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        err "当前目录不是 Git 仓库"
        exit 1
    fi

    # 检查是否有未提交变更
    if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null && [ -z "$(git status --short 2>/dev/null)" ]; then
        warn "工作区干净，没有需要提交的变更"
        exit 0
    fi

    show_status
    stage_files
    input_message
    confirm_and_commit
}

main "$@"
