#!/usr/bin/env bash
# ===========================================================================
# test_env.sh — 本地测试环境（默认 8099 端口）启动 / 停止控制脚本
#
# 用法:
#   ./test_env.sh start     后台启动（默认 0.0.0.0:8099，允许任意地址访问）
#   ./test_env.sh stop      优雅停止（SIGINT → SIGTERM → SIGKILL 逐级兜底）
#   ./test_env.sh restart   重启
#   ./test_env.sh status    查看运行状态 / 监听地址 / 健康检查
#   ./test_env.sh log       跟踪最新一次启动的控制台日志（Ctrl+C 退出跟踪）
#   ./test_env.sh fg        前台运行（排障用，Ctrl+C 停止）
#   ./test_env.sh help      显示本帮助
#
# 环境变量（可选）:
#   TEST_PORT=8099     监听端口（默认 8099）
#   TEST_HOST=0.0.0.0  监听地址（默认 0.0.0.0，即允许任意来源地址访问）
#   TEST_BASE_CONFIG=1 不叠加 app_config.debug.json（改用 app_config.json 主配置）
#   TEST_WAIT=60       启动等待就绪的最长秒数（默认 60）
#
# 说明:
#   - 一律使用仓库根 venv/bin/python（禁止系统 Python，见 AGENTS.md 硬性约束 #6）
#   - 不设置 CONFIG_FILE → 仓库根存在 app_config.debug.json 时自动深合并覆盖，
#     即测试环境使用 config.debug.db / audit.debug.db / run.debug.log，
#     与生产配置（app_config.json → config.db / audit.db）互不干扰
#   - HOST / PORT 环境变量在 app_config.get_server_config() 中优先级最高，
#     因此无需改任何配置文件即可改端口/地址
#   - PID 文件与控制台日志落在已被 .gitignore 的 run-logs/ 目录
# ===========================================================================

set -euo pipefail

# --- 路径与参数（不硬编码项目目录，一律由脚本自身位置推导） ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TEST_PORT="${TEST_PORT:-8099}"
TEST_HOST="${TEST_HOST:-0.0.0.0}"
TEST_WAIT="${TEST_WAIT:-60}"
RUN_DIR="${SCRIPT_DIR}/run-logs"
PID_FILE="${RUN_DIR}/test-env-${TEST_PORT}.pid"
LOG_FILE="${RUN_DIR}/test-env-${TEST_PORT}-$(date +%Y%m%d-%H%M%S).log"
PY="${SCRIPT_DIR}/venv/bin/python"

# --- 颜色输出 ---
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR ]${NC} $*" >&2; }

usage() {
    sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

# 读取 PID 文件中的 PID（无则输出空）
read_pid() {
    [[ -f "$PID_FILE" ]] || return 0
    local pid
    pid="$(tr -dc '0-9' < "$PID_FILE" 2>/dev/null || true)"
    [[ -n "$pid" ]] && echo "$pid"
}

# 进程是否存活
alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

# 进程身份判定，输出以下之一：
#   none    PID 为空（PID 文件无有效内容）
#   dead    进程不存在（过期 PID 文件）
#   ours    确认是本项目的 server.py（cmdline 含 server.py 且 cwd 为项目根）
#   foreign 确认不是本项目的 server.py
#   unknown /proc 不可读（如容器 PID 命名空间），无法判定
verify_process() {
    local pid="${1:-}"
    [[ -n "$pid" ]] || { echo "none"; return 0; }
    kill -0 "$pid" 2>/dev/null || { echo "dead"; return 0; }
    if [[ ! -r "/proc/${pid}/cmdline" ]]; then
        echo "unknown"
        return 0
    fi
    local cmdline cwd
    cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
    if ! grep -q 'server\.py' <<< "$cmdline"; then
        echo "foreign"
        return 0
    fi
    cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
    if [[ -n "$cwd" && "$cwd" != "$SCRIPT_DIR" ]]; then
        echo "foreign"
        return 0
    fi
    echo "ours"
}

# 是否可以对该 PID 执行停止操作（ours / unknown 可停，foreign 不可）
can_stop() {
    local v
    v="$(verify_process "$1")"
    [[ "$v" == "ours" || "$v" == "unknown" ]]
}

# 占用 TCP 监听端口的 PID 列表（多行）
port_pids() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnpH "sport = :${TEST_PORT}" 2>/dev/null \
            | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true
    elif command -v lsof >/dev/null 2>&1; then
        lsof -t -iTCP:"${TEST_PORT}" -sTCP:LISTEN 2>/dev/null | sort -u || true
    fi
}

# 端口是否可连接
port_open() {
    (exec 3<>"/dev/tcp/127.0.0.1/${TEST_PORT}") >/dev/null 2>&1
}

# 健康检查：GET /login（公开路由，返回 200 即视为就绪）
http_code() {
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:${TEST_PORT}/login" 2>/dev/null || true)"
    [[ "$code" =~ ^[0-9]{3}$ ]] || code="000"
    printf '%s' "$code"
}

# 应用自身日志路径（app_config 解析结果，用于提示用户）
app_log_path() {
    "$PY" -c 'import app_config; print(app_config.get_log_config()[1])' 2>/dev/null | tail -n 1
}

# 列出可访问地址
access_urls() {
    local ips=() ip
    if command -v hostname >/dev/null 2>&1; then
        read -r -a ips <<< "$(hostname -I 2>/dev/null || true)"
    fi
    echo "  本机:   http://127.0.0.1:${TEST_PORT}"
    for ip in ${ips[@]+"${ips[@]}"}; do
        echo "  局域网: http://${ip}:${TEST_PORT}"
    done
}

firewall_hint() {
    if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
        warn "检测到 firewalld 运行中，外部访问不通时放行端口："
        echo "        firewall-cmd --permanent --add-port=${TEST_PORT}/tcp && firewall-cmd --reload"
    fi
}

precheck() {
    if [[ ! -f "${SCRIPT_DIR}/server.py" ]]; then
        err "未在 ${SCRIPT_DIR} 找到 server.py，请把本脚本放在项目根目录"
        exit 1
    fi
    if [[ ! -x "$PY" ]]; then
        err "未找到虚拟环境解释器 ${PY}"
        err "请先执行: ./install.sh"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------
do_start() {
    precheck
    mkdir -p "$RUN_DIR"

    local pid v
    pid="$(read_pid || true)"
    v="$(verify_process "$pid")"
    if [[ "$v" == "ours" ]]; then
        info "测试环境已在运行（PID ${pid}）"
        show_status
        return 0
    fi
    if [[ "$v" == "unknown" ]]; then
        warn "PID ${pid} 存活但无法校验身份（/proc 不可读），为安全起见不重复启动"
        show_status
        return 0
    fi
    if [[ "$v" == "foreign" ]]; then
        warn "PID 文件记录的是其它进程（PID ${pid}），已忽略并重新登记"
    fi
    # 过期/无效 PID 文件：截断（不删除），避免子进程写 PID 前被误读为“旧 PID 已死”
    : > "$PID_FILE"

    # 端口预检：若被本项目的残留 server.py 占用，先清掉再启动
    local pids p
    pids="$(port_pids)"
    if [[ -n "$pids" ]]; then
        local foreign=0
        for p in $pids; do
            if can_stop "$p"; then
                warn "清理残留进程占用端口 ${TEST_PORT}（PID ${p}）"
                kill -INT "$p" 2>/dev/null || true
                sleep 1
                kill -0 "$p" 2>/dev/null && kill -KILL "$p" 2>/dev/null || true
            else
                foreign=1
            fi
        done
        if [[ "$foreign" -eq 1 ]] || port_open; then
            err "端口 ${TEST_PORT} 已被其它进程占用，请先处理："
            err "  查占用:  ss -ltnp 'sport = :${TEST_PORT}'"
            err "  清理:    fuser -k ${TEST_PORT}/tcp"
            return 1
        fi
    fi

    # 端口已被占用但查不到占用进程（容器/PID 命名空间隔离时常见）：直接报错，
    # 避免拉起后才因绑定失败退出，浪费一轮等待
    if [[ -z "$pids" ]] && port_open; then
        err "端口 ${TEST_PORT} 已被其它服务占用（占用进程不在本命名空间内，无法自动处理）"
        err "  查占用:  ss -ltnp 'sport = :${TEST_PORT}'"
        err "  换端口:  TEST_PORT=其它端口 ./test_env.sh start"
        return 1
    fi

    # 启动（setsid 独立会话，避免调用方 shell 退出时被连带回收）
    info "启动测试环境: ${TEST_HOST}:${TEST_PORT}（DEBUG 配置叠加：$([[ "${TEST_BASE_CONFIG:-0}" == 1 ]] && echo '否（已指定基础配置）' || echo '是')）"
    if [[ "${TEST_BASE_CONFIG:-0}" == "1" ]]; then
        export CONFIG_FILE="app_config.json"
    else
        unset CONFIG_FILE || true
    fi

    HOST="$TEST_HOST" PORT="$TEST_PORT" setsid bash -c \
        'echo $$ > "$1"; cd "$2"; exec "$3" -u server.py' \
        _ "$PID_FILE" "$SCRIPT_DIR" "$PY" >>"$LOG_FILE" 2>&1 </dev/null &

    # 等待子进程写入 PID（最多 5s）；仍未落盘则退回后台作业 PID
    local i=0
    while (( i < 50 )); do
        pid="$(read_pid || true)"
        [[ -n "$pid" ]] && break
        sleep 0.1
        i=$((i + 1))
    done
    if [[ -z "$pid" ]]; then
        pid=$!
        warn "PID 文件未落盘，回退使用后台作业 PID ${pid}"
    fi

    # 等待就绪
    local waited=0 code=""
    info "等待服务就绪（最长 ${TEST_WAIT}s）..."
    while (( waited < TEST_WAIT )); do
        if ! alive "$pid"; then
            err "进程已退出，启动失败。日志尾部："
            tail -n 20 "$LOG_FILE" >&2 || true
            return 1
        fi
        code="$(http_code)"
        [[ "$code" == "200" ]] && break
        sleep 1
        waited=$((waited + 1))
        if (( waited % 5 == 0 )); then
            echo "        ... ${waited}s"
        fi
    done

    if [[ "$code" != "200" ]]; then
        err "等待超时（${TEST_WAIT}s），最后一次健康检查返回 '${code}'。日志尾部："
        tail -n 20 "$LOG_FILE" >&2 || true
        err "进程仍在运行，可用 './test_env.sh log' 查看完整日志，或 './test_env.sh stop' 停止"
        return 1
    fi

    ok "测试环境已启动（PID ${pid}，监听 ${TEST_HOST}:${TEST_PORT}，健康检查 /login = 200）"
    echo ""
    echo "访问地址（${TEST_HOST} 绑定，允许任意来源地址访问）:"
    access_urls
    echo ""
    echo "  控制台日志: ${LOG_FILE}"
    local applog
    applog="$(app_log_path || true)"
    if [[ -n "$applog" ]]; then
        echo "  应用日志:   ${SCRIPT_DIR}/${applog}"
    fi
    echo "  停止服务:   ./test_env.sh stop"
    firewall_hint
}

# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------
kill_pid() {
    local pid="$1"
    # 逐级兜底：SIGINT 走 server.py 的优雅关闭分支（停调度器 + 关 socket），
    # 其失败再退 SIGTERM，最后 SIGKILL。
    local sig
    for sig in INT TERM KILL; do
        kill -"$sig" "$pid" 2>/dev/null || true
        local i=0
        while (( i < 10 )); do
            kill -0 "$pid" 2>/dev/null || return 0
            sleep 0.5
            i=$((i + 1))
        done
        if [[ "$sig" == "KILL" ]]; then
            break
        fi
    done
    kill -0 "$pid" 2>/dev/null && return 1
    return 0
}

do_stop() {
    local pid stopped=0 v
    pid="$(read_pid || true)"
    v="$(verify_process "$pid")"

    if [[ "$v" != "none" && "$v" != "dead" ]] && can_stop "$pid"; then
        info "停止测试环境（PID ${pid}）..."
        if kill_pid "$pid"; then
            ok "已停止（PID ${pid}）"
        else
            err "PID ${pid} 未响应信号，请手动处理：kill -9 ${pid}"
            return 1
        fi
        stopped=1
    elif [[ "$v" == "foreign" ]]; then
        warn "PID 文件中的进程（${pid}）不是本项目 server.py，跳过（防误杀）"
    fi

    # 清理：PID 文件丢失/过期但端口仍被本项目 server.py 占用的情况
    local pids p
    pids="$(port_pids)"
    for p in $pids; do
        if can_stop "$p"; then
            warn "清理未登记的残留进程（PID ${p}）"
            kill_pid "$p" || true
            stopped=1
        fi
    done

    if [[ "$stopped" -eq 0 ]]; then
        info "测试环境未在运行"
    fi

    # PID 文件只截断不删除（run-logs/ 内不留孤儿文件）
    : > "$PID_FILE"

    if port_open; then
        warn "端口 ${TEST_PORT} 仍处于监听状态，残留占用进程："
        ss -ltnp "sport = :${TEST_PORT}" 2>/dev/null >&2 || true
        return 1
    fi
    ok "端口 ${TEST_PORT} 已释放"
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
show_status() {
    local pid code v
    pid="$(read_pid || true)"
    v="$(verify_process "$pid")"
    echo "== 测试环境状态 =="
    echo "  监听地址: ${TEST_HOST}:${TEST_PORT}   （0.0.0.0 = 允许任意来源地址访问）"
    echo "  配置文件: ${SCRIPT_DIR}/app_config.json$([[ -f "${SCRIPT_DIR}/app_config.debug.json" ]] && echo ' + app_config.debug.json（DEBUG 叠加）')"
    echo "  PID 文件: ${PID_FILE}"

    if [[ "$v" == "ours" || "$v" == "unknown" ]]; then
        local start_time elapsed
        start_time="$(stat -c %Y "/proc/${pid}" 2>/dev/null || echo 0)"
        if [[ "$start_time" -gt 0 ]]; then
            elapsed=$(( $(date +%s) - start_time ))
            ok "进程: 运行中（PID ${pid}，已运行 $((elapsed / 3600))h$(((elapsed % 3600) / 60))m$((elapsed % 60))s）"
        else
            ok "进程: 运行中（PID ${pid}）"
        fi
    else
        if [[ "$v" == "dead" || "$v" == "foreign" ]]; then
            warn "进程: 未运行（PID 文件残留 ${pid}，已失效）"
        else
            warn "进程: 未运行"
        fi
    fi

    if port_open; then
        ok "端口: ${TEST_PORT} 正在监听"
        ss -ltnp "sport = :${TEST_PORT}" 2>/dev/null | sed 's/^/        /' || true
    else
        warn "端口: ${TEST_PORT} 未监听"
    fi

    code="$(http_code)"
    if [[ "$code" == "200" ]]; then
        ok "健康检查: /login = 200"
    else
        warn "健康检查: /login = ${code}（000 = 未连通）"
    fi

    echo ""
    echo "访问地址:"
    access_urls
}

# ---------------------------------------------------------------------------
# log / fg
# ---------------------------------------------------------------------------
do_log() {
    mkdir -p "$RUN_DIR"
    local latest
    latest="$(ls -t "${RUN_DIR}"/test-env-"${TEST_PORT}"-*.log 2>/dev/null | head -n 1 || true)"
    if [[ -z "$latest" ]]; then
        info "暂无控制台日志（尚未启动过）"
        return 0
    fi
    info "跟踪日志: ${latest}（Ctrl+C 退出跟踪，服务不受影响）"
    tail -n 200 -f "$latest"
}

do_fg() {
    precheck
    info "前台运行 ${TEST_HOST}:${TEST_PORT}（Ctrl+C 停止）"
    if [[ "${TEST_BASE_CONFIG:-0}" == "1" ]]; then
        export CONFIG_FILE="app_config.json"
    else
        unset CONFIG_FILE || true
    fi
    HOST="$TEST_HOST" PORT="$TEST_PORT" exec "$PY" server.py
}

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
cmd="${1:-help}"
case "$cmd" in
    start)          do_start ;;
    stop)           do_stop ;;
    restart)        do_stop || true; echo ""; do_start ;;
    status|st)      show_status ;;
    log)            do_log ;;
    fg|foreground)  do_fg ;;
    help|-h|--help) usage ;;
    *)
        err "未知命令: ${cmd}"
        echo ""
        usage
        exit 1
        ;;
esac
