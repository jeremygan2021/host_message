#!/bin/bash

# ==========================================================================
# 自动部署脚本 - host_message 项目
# 功能：将本地代码打包上传到远程服务器并自动部署
# ==========================================================================

# 配置信息
REMOTE_HOST="6.6.6.86"
REMOTE_USER="ubuntu"
REMOTE_PASS="qweasdzxc1"
REMOTE_DIR="/home/ubuntu/host_message"
LOCAL_DIR="/Users/jeremygan/Desktop/TangledupAI/host_message-main"
APP_PORT=8888
ZIP_NAME="host_message_$(date +%Y%m%d_%H%M%S).zip"
TEMP_ZIP="/tmp/$ZIP_NAME"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# 检查依赖
check_dependencies() {
    log_step "检查系统依赖..."
    
    # 检查 sshpass
    if ! command -v sshpass &> /dev/null; then
        log_error "sshpass 未安装，正在安装..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install sshpass
            else
                log_error "请先安装 Homebrew，然后运行: brew install sshpass"
                exit 1
            fi
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            sudo apt-get update && sudo apt-get install -y sshpass
        else
            log_error "不支持的操作系统，请手动安装 sshpass"
            exit 1
        fi
    fi
    
    # 检查 zip
    if ! command -v zip &> /dev/null; then
        log_error "zip 命令未找到，请安装 zip 工具"
        exit 1
    fi
    
    log_info "依赖检查完成"
}

# 创建代码包
create_package() {
    log_step "创建代码包..."
    
    # 切换到项目目录
    cd "$LOCAL_DIR" || {
        log_error "无法进入项目目录: $LOCAL_DIR"
        exit 1
    }
    
    # 删除旧的临时文件
    rm -f "$TEMP_ZIP"
    
    # 创建排除文件列表
    EXCLUDE_PATTERNS=(
        "*.pyc"
        "__pycache__/*"
        ".git/*"
        ".DS_Store"
        "logs/*"
        "*.log"
        ".env"
        "venv/*"
        ".venv/*"
        "node_modules/*"
        "uploads/*"
        "chat_history/*"
        "database/*"
    )
    
    # 构建排除参数
    EXCLUDE_ARGS=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        EXCLUDE_ARGS="$EXCLUDE_ARGS -x $pattern"
    done
    
    # 创建zip包
    log_info "正在打包文件..."
    eval "zip -r \"$TEMP_ZIP\" . $EXCLUDE_ARGS"
    
    if [ $? -eq 0 ]; then
        log_info "代码包创建成功: $TEMP_ZIP"
        log_info "包大小: $(du -h "$TEMP_ZIP" | cut -f1)"
    else
        log_error "代码包创建失败"
        exit 1
    fi
}

# 测试SSH连接
test_ssh_connection() {
    log_step "测试SSH连接..."
    
    sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "echo 'SSH连接测试成功'" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        log_info "SSH连接测试成功"
    else
        log_error "SSH连接失败，请检查服务器地址、用户名和密码"
        exit 1
    fi
}

# 上传代码包
upload_package() {
    log_step "上传代码包到服务器..."
    
    # 使用scp上传文件
    sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no "$TEMP_ZIP" "$REMOTE_USER@$REMOTE_HOST:/tmp/"
    
    if [ $? -eq 0 ]; then
        log_info "代码包上传成功"
    else
        log_error "代码包上传失败"
        exit 1
    fi
}

# 远程部署
remote_deploy() {
    log_step "在远程服务器上执行部署..."
    
    # 创建远程部署脚本
    REMOTE_SCRIPT="
#!/bin/bash

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e \"\${GREEN}[远程INFO]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1\"
}

log_error() {
    echo -e \"\${RED}[远程ERROR]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1\"
}

log_warn() {
    echo -e \"\${YELLOW}[远程WARN]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1\"
}

# 检查端口占用并杀死进程
check_and_kill_port() {
    log_info \"检查端口 $APP_PORT 是否被占用...\"
    
    # 查找占用端口的进程
    PID=\$(lsof -ti:$APP_PORT 2>/dev/null)
    
    if [ ! -z \"\$PID\" ]; then
        log_warn \"发现端口 $APP_PORT 被进程 \$PID 占用，正在终止...\"
        kill -TERM \$PID
        sleep 3
        
        # 检查进程是否还存在
        if kill -0 \$PID 2>/dev/null; then
            log_warn \"进程仍然存在，强制终止...\"
            kill -KILL \$PID
            sleep 2
        fi
        
        # 再次检查
        NEW_PID=\$(lsof -ti:$APP_PORT 2>/dev/null)
        if [ ! -z \"\$NEW_PID\" ]; then
            log_error \"无法终止占用端口 $APP_PORT 的进程\"
            exit 1
        else
            log_info \"端口 $APP_PORT 已释放\"
        fi
    else
        log_info \"端口 $APP_PORT 未被占用\"
    fi
}

# 安装系统依赖
install_dependencies() {
    log_info \"检查并安装系统依赖...\"
    
    # 更新包列表
    sudo apt-get update -qq
    
    # 安装Python3和pip
    if ! command -v python3 &> /dev/null; then
        log_info \"安装 Python3...\"
        sudo apt-get install -y python3 python3-pip
    fi
    
    # 安装supervisor用于进程保活
    if ! command -v supervisorctl &> /dev/null; then
        log_info \"安装 supervisor...\"
        sudo apt-get install -y supervisor
        sudo systemctl enable supervisor
        sudo systemctl start supervisor
    fi
    
    log_info \"系统依赖检查完成\"
}

# 主要部署逻辑
main_deploy() {
    # 检查并终止端口进程
    check_and_kill_port
    
    # 安装系统依赖
    install_dependencies
    
    # 备份旧代码（如果存在）
    if [ -d \"$REMOTE_DIR\" ]; then
        log_info \"备份现有代码...\"
        sudo mv \"$REMOTE_DIR\" \"${REMOTE_DIR}_backup_\$(date +%Y%m%d_%H%M%S)\" 2>/dev/null || true
    fi
    
    # 创建部署目录
    log_info \"创建部署目录...\"
    sudo mkdir -p \"$REMOTE_DIR\"
    sudo chown \$USER:\$USER \"$REMOTE_DIR\"
    
    # 解压代码包
    log_info \"解压代码包...\"
    cd \"$REMOTE_DIR\"
    unzip -q \"/tmp/$ZIP_NAME\"
    
    if [ \$? -eq 0 ]; then
        log_info \"代码解压成功\"
    else
        log_error \"代码解压失败\"
        exit 1
    fi
    
    # 创建必要的目录
    mkdir -p logs uploads chat_history database
    
    # 安装Python依赖
    log_info \"安装Python依赖...\"
    if [ -f \"requirements.txt\" ]; then
        python3 -m pip install --upgrade pip
        python3 -m pip install -r requirements.txt
    fi
    
    # 创建supervisor配置
    log_info \"配置进程保活监控...\"
    sudo tee /etc/supervisor/conf.d/host_message.conf > /dev/null <<EOF
[program:host_message]
command=python3 main.py
directory=$REMOTE_DIR
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$REMOTE_DIR/logs/supervisor.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
environment=PATH=\"\$PATH\"
EOF
    
    # 重新加载supervisor配置
    sudo supervisorctl reread
    sudo supervisorctl update
    
    # 启动应用
    log_info \"启动应用...\"
    sudo supervisorctl start host_message
    
    # 等待应用启动
    sleep 5
    
    # 检查应用状态
    if sudo supervisorctl status host_message | grep -q \"RUNNING\"; then
        log_info \"应用启动成功！\"
        log_info \"应用状态: \$(sudo supervisorctl status host_message)\"
        
        # 检查端口监听
        if netstat -tlnp 2>/dev/null | grep -q \":$APP_PORT\"; then
            log_info \"端口 $APP_PORT 监听正常\"
            log_info \"部署完成！您可以通过 http://$REMOTE_HOST:$APP_PORT 访问应用\"
        else
            log_warn \"端口 $APP_PORT 未在监听，请检查应用日志\"
        fi
    else
        log_error \"应用启动失败，状态: \$(sudo supervisorctl status host_message)\"
        log_error \"请查看日志: $REMOTE_DIR/logs/supervisor.log\"
        exit 1
    fi
    
    # 清理临时文件
    rm -f \"/tmp/$ZIP_NAME\"
    
    log_info \"部署脚本执行完成\"
}

# 执行主要部署逻辑
main_deploy
"
    
    # 执行远程部署脚本
    sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "$REMOTE_SCRIPT"
    
    if [ $? -eq 0 ]; then
        log_info "远程部署完成"
    else
        log_error "远程部署失败"
        exit 1
    fi
}

# 清理本地临时文件
cleanup() {
    log_step "清理临时文件..."
    rm -f "$TEMP_ZIP"
    log_info "临时文件清理完成"
}

# 显示部署信息
show_deploy_info() {
    echo ""
    echo "=========================================="
    echo "           部署完成信息"
    echo "=========================================="
    echo "服务器地址: $REMOTE_HOST"
    echo "部署目录: $REMOTE_DIR"
    echo "应用端口: $APP_PORT"
    echo "访问地址: http://$REMOTE_HOST:$APP_PORT"
    echo "=========================================="
    echo ""
    echo "常用管理命令："
    echo "查看应用状态: ssh $REMOTE_USER@$REMOTE_HOST 'sudo supervisorctl status host_message'"
    echo "重启应用:     ssh $REMOTE_USER@$REMOTE_HOST 'sudo supervisorctl restart host_message'"
    echo "停止应用:     ssh $REMOTE_USER@$REMOTE_HOST 'sudo supervisorctl stop host_message'"
    echo "查看日志:     ssh $REMOTE_USER@$REMOTE_HOST 'tail -f $REMOTE_DIR/logs/supervisor.log'"
    echo "=========================================="
}

# 主函数
main() {
    echo "=========================================="
    echo "     host_message 项目自动部署脚本"
    echo "=========================================="
    echo "目标服务器: $REMOTE_HOST"
    echo "部署目录: $REMOTE_DIR"
    echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    echo ""
    
    # 执行部署步骤
    check_dependencies
    create_package
    test_ssh_connection
    upload_package
    remote_deploy
    cleanup
    show_deploy_info
    
    log_info "🎉 全部部署任务完成！"
}

# 错误处理
set -e
trap 'log_error "脚本执行过程中发生错误，退出码: $?"' ERR

# 执行主函数
main "$@"
