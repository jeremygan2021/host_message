#!/bin/bash

# 定义常量
PORT=8888
LOG_FILE="logs/$(date +%Y%m%d_%H%M%S)_message.log"
PID_FILE="logs/app.pid"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"

# 切换到脚本目录
cd "$SCRIPT_DIR" || {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] 错误: 无法进入目录 $SCRIPT_DIR" | tee -a "$LOG_FILE"
    exit 1
}

# 日志输出函数
log_info() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [ERROR] $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [WARN] $1" | tee -a "$LOG_FILE"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -i :$port >/dev/null 2>&1
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln | grep ":$port " >/dev/null 2>&1
    elif command -v ss >/dev/null 2>&1; then
        ss -tuln | grep ":$port " >/dev/null 2>&1
    else
        log_error "无法找到检查端口的命令 (lsof, netstat, ss)"
        return 1
    fi
}

# 健康检查函数
health_check() {
    local url="http://localhost:$PORT"
    local timeout=5
    
    if command -v curl >/dev/null 2>&1; then
        curl -s --connect-timeout $timeout --max-time $timeout "$url" >/dev/null 2>&1
    elif command -v wget >/dev/null 2>&1; then
        wget -q --timeout=$timeout --tries=1 -O /dev/null "$url" >/dev/null 2>&1
    else
        log_warn "无法找到HTTP检查工具 (curl, wget)，跳过健康检查"
        return 0
    fi
}

# 停止现有进程
stop_existing_process() {
    log_info "停止现有进程..."
    
    # 从PID文件停止
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "正在停止进程 PID: $pid"
            kill "$pid"
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                log_warn "进程仍在运行，强制终止"
                kill -9 "$pid"
            fi
            rm -f "$PID_FILE"
        else
            log_info "PID文件中的进程已不存在，清理PID文件"
            rm -f "$PID_FILE"
        fi
    fi
    
    # 通过端口查找并停止进程
    if check_port $PORT; then
        log_info "发现端口 $PORT 仍被占用，查找并停止相关进程"
        if command -v lsof >/dev/null 2>&1; then
            local pids=$(lsof -ti :$PORT)
            if [ -n "$pids" ]; then
                echo "$pids" | xargs kill -15 2>/dev/null || true
                sleep 2
                # 如果进程仍在运行，强制杀死
                local remaining_pids=$(lsof -ti :$PORT 2>/dev/null)
                if [ -n "$remaining_pids" ]; then
                    echo "$remaining_pids" | xargs kill -9 2>/dev/null || true
                fi
            fi
        fi
    fi
}

# 启动应用
start_app() {
    log_info "开始启动应用..."
    
    # 后台运行Python程序
    nohup python main.py >> "$LOG_FILE" 2>&1 &
    local app_pid=$!
    
    # 保存PID
    echo $app_pid > "$PID_FILE"
    log_info "应用已启动，PID: $app_pid"
    
    # 等待应用启动
    local max_wait=30
    local wait_time=0
    
    while [ $wait_time -lt $max_wait ]; do
        if check_port $PORT; then
            log_info "端口 $PORT 已开始监听"
            break
        fi
        sleep 1
        wait_time=$((wait_time + 1))
    done
    
    if [ $wait_time -ge $max_wait ]; then
        log_error "应用启动超时，端口 $PORT 未开始监听"
        return 1
    fi
    
    # 健康检查
    sleep 2
    if health_check; then
        log_info "应用健康检查通过"
        return 0
    else
        log_warn "应用健康检查失败，但端口已监听"
        return 0
    fi
}

# 主逻辑
main() {
    log_info "开始检查应用状态..."
    
    # 检查端口是否被占用
    if check_port $PORT; then
        log_info "检测到端口 $PORT 已被占用"
        
        # 进行健康检查
        if health_check; then
            log_info "应用正常运行，端口 $PORT 可正常访问，跳过重启"
            exit 0
        else
            log_warn "端口 $PORT 被占用但健康检查失败，准备重启应用"
            stop_existing_process
        fi
    else
        log_info "端口 $PORT 未被占用，准备启动应用"
    fi
    
    # 启动应用
    if start_app; then
        log_info "应用启动成功"
    else
        log_error "应用启动失败"
        exit 1
    fi
}

# 执行主函数
main
