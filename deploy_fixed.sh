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
    
    # 上传远程部署脚本
    sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no "remote_deploy_script.sh" "$REMOTE_USER@$REMOTE_HOST:/tmp/"
    
    # 执行远程部署脚本
    sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "chmod +x /tmp/remote_deploy_script.sh && /tmp/remote_deploy_script.sh '$ZIP_NAME'"
    
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
    echo "调试应用:     ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && ./debug_app.sh'"
    echo "=========================================="

    # 最后验证部署
    log_info "正在验证部署结果..."
    sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "
        echo '=== 最终验证 ==='
        sudo supervisorctl status host_message
        echo '=== 端口检查 ==='
        netstat -tlnp | grep 8888 || ss -tlnp | grep 8888 || echo '端口8888未监听'
        echo '=== 进程检查 ==='
        ps aux | grep 'python3 main.py' | grep -v grep || echo '未找到Python进程'
    " || log_warn "最终验证失败，请手动检查"
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
