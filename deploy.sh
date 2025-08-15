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
    
    # 创建远程部署脚本
    REMOTE_SCRIPT=$(cat <<EOF
#!/bin/bash

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "\${GREEN}[远程INFO]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1"
}

log_error() {
    echo -e "\${RED}[远程ERROR]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1"
}

log_warn() {
    echo -e "\${YELLOW}[远程WARN]\${NC} \$(date '+%Y-%m-%d %H:%M:%S') - \$1"
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

# 检查环境是否已安装
check_environment() {
    log_info \"检查服务器环境...\"
    
    # 检查Python3
    if ! python3 --version &> /dev/null; then
        log_info \"Python3 未安装，需要安装...\"
        return 1
    fi
    
    # 检查是否存在虚拟环境
    if [ -d \"/home/ubuntu/host_message_venv\" ]; then
        log_info \"发现已存在的虚拟环境\"
        return 0
    fi
    
    # 检查supervisor
    if ! command -v supervisorctl &> /dev/null; then
        log_info \"Supervisor 未安装，需要安装...\"
        return 1
    fi
    
    log_info \"基础环境检查通过，但需要创建虚拟环境\"
    return 2
}

# 安装系统依赖
install_dependencies() {
    log_info \"安装系统依赖...\"
    
    # 更新包列表
    sudo apt-get update -qq
    
    # 安装Python3、pip和相关开发工具
    log_info \"安装 Python3 和相关工具...\"
    sudo apt-get install -y python3 python3-pip python3-venv python3-dev build-essential python3-full
    
    # 安装supervisor用于进程保活
    if ! command -v supervisorctl &> /dev/null; then
        log_info \"安装 supervisor...\"
        sudo apt-get install -y supervisor
        sudo systemctl enable supervisor
        sudo systemctl start supervisor
    fi
    
    # 安装其他必要工具
    sudo apt-get install -y curl wget unzip lsof net-tools
    
    log_info \"系统依赖安装完成\"
}

# 创建和管理虚拟环境
setup_virtual_environment() {
    local venv_path=\"/home/ubuntu/host_message_venv\"
    
    log_info \"设置Python虚拟环境...\"
    
    # 如果虚拟环境已存在，询问是否重新创建
    if [ -d \"\$venv_path\" ]; then
        log_info \"虚拟环境已存在，删除旧环境并重新创建...\"
        rm -rf \"\$venv_path\"
    fi
    
    # 创建虚拟环境
    log_info \"创建新的虚拟环境...\"
    python3 -m venv \"\$venv_path\"
    
    if [ \$? -eq 0 ]; then
        log_info \"虚拟环境创建成功: \$venv_path\"
    else
        log_error \"虚拟环境创建失败\"
        exit 1
    fi
    
    # 激活虚拟环境并升级pip
    log_info \"激活虚拟环境并升级pip...\"
    source \"\$venv_path/bin/activate\"
    pip install --upgrade pip setuptools wheel
    
    log_info \"虚拟环境设置完成\"
}

# 主要部署逻辑
main_deploy() {
    # 检查并终止端口进程
    check_and_kill_port
    
    # 检查环境状态
    check_environment
    env_status=\$?
    
    case \$env_status in
        0)
            log_info "环境已完整安装，跳过依赖安装"
            ;;
        1)
            log_info "需要安装基础环境"
            install_dependencies
            setup_virtual_environment
            ;;
        2)
            log_info "基础环境已安装，只需创建虚拟环境"
            setup_virtual_environment
            ;;
    esac
    
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
    
    # 激活虚拟环境并安装Python依赖
    log_info \"激活虚拟环境并安装Python依赖...\"
    source \"/home/ubuntu/host_message_venv/bin/activate\"
    
    if [ -f \"requirements.txt\" ]; then
        log_info \"发现 requirements.txt，安装依赖包...\"
        pip install -r requirements.txt
        if [ \$? -eq 0 ]; then
            log_info \"Python依赖安装成功\"
        else
            log_error \"Python依赖安装失败\"
            # 尝试单独安装每个包
            log_info \"尝试单独安装依赖包...\"
            while IFS= read -r package; do
                if [[ ! \$package =~ ^[[:space:]]*# ]] && [[ ! -z \$package ]]; then
                    log_info \"安装: \$package\"
                    pip install \$package || log_warn \"安装 \$package 失败\"
                fi
            done < requirements.txt
        fi
    else
        log_warn \"未找到 requirements.txt 文件\"
    fi
    
    # 验证关键依赖
    log_info \"验证Python依赖...\"
    python -c \"import fastapi, uvicorn; print('关键依赖验证成功')\" || {
        log_error \"关键依赖验证失败，手动安装...\"
        pip install fastapi uvicorn
    }
    
    # 检查main.py文件
    if [ ! -f \"main.py\" ]; then
        log_error \"main.py 文件不存在！\"
        exit 1
    fi
    
    # 测试Python应用是否可以启动
    log_info \"测试Python应用...\"
    source \"/home/ubuntu/host_message_venv/bin/activate\"
    timeout 10 python -c \"
import sys
sys.path.insert(0, '.')
try:
    import main
    print('应用模块导入成功')
except Exception as e:
    print(f'应用模块导入失败: {e}')
    sys.exit(1)
\" || log_warn \"应用模块测试失败，但继续部署...\""
    
    # 创建启动脚本
    log_info \"创建应用启动脚本...\"
    cat > start_app.sh <<SCRIPT_EOF
#!/bin/bash
set -e

# 进入应用目录
cd \"$REMOTE_DIR\"

# 激活虚拟环境
source \"/home/ubuntu/host_message_venv/bin/activate\"

# 设置环境变量
export PYTHONPATH=\"$REMOTE_DIR:\\\$PYTHONPATH\"

# 记录启动信息
echo \"[\$(date)] 应用启动开始...\"
echo \"当前目录: \$(pwd)\"
echo \"Python版本: \$(python --version)\"
echo \"虚拟环境: \$VIRTUAL_ENV\"

# 检查必要文件
if [ ! -f \"main.py\" ]; then
    echo \"错误: main.py 文件不存在\"
    exit 1
fi

# 启动应用
echo \"[\$(date)] 启动Python应用...\"
python main.py
SCRIPT_EOF
    chmod +x start_app.sh
    
    # 创建调试脚本
    log_info \"创建调试脚本...\"
    cat > debug_app.sh <<DEBUG_EOF
#!/bin/bash
cd \"$REMOTE_DIR\"
echo \"=== 调试信息 ===\"
echo \"当前目录: \$(pwd)\"

# 激活虚拟环境
source \"/home/ubuntu/host_message_venv/bin/activate\" 2>/dev/null || echo \"虚拟环境激活失败\"

echo \"Python版本: \$(python --version 2>/dev/null || python3 --version)\"
echo \"pip版本: \$(pip --version 2>/dev/null || echo '无pip')\"
echo \"虚拟环境: \$VIRTUAL_ENV\"
echo \"文件列表:\"
ls -la
echo \"=== 尝试导入测试 ===\"
python -c \"
import sys
print('Python路径:', sys.path)
try:
    import fastapi
    print('fastapi版本:', fastapi.__version__)
except ImportError as e:
    print('fastapi导入失败:', e)
try:
    import uvicorn
    print('uvicorn版本:', uvicorn.__version__)
except ImportError as e:
    print('uvicorn导入失败:', e)
\" 2>/dev/null || python3 -c \"
import sys
print('Python路径:', sys.path)
try:
    import fastapi
    print('fastapi版本:', fastapi.__version__)
except ImportError as e:
    print('fastapi导入失败:', e)
try:
    import uvicorn
    print('uvicorn版本:', uvicorn.__version__)
except ImportError as e:
    print('uvicorn导入失败:', e)
\"
echo \"=== 检查端口占用 ===\"
netstat -tlnp | grep 8888 || echo '端口8888未被占用'
echo \"=== 尝试启动应用（5秒后停止） ===\"
timeout 5 python main.py 2>/dev/null || timeout 5 python3 main.py || echo '应用启动测试完成'
DEBUG_EOF
    chmod +x debug_app.sh
    
    # 创建supervisor配置
    log_info \"配置进程保活监控...\"
    sudo tee /etc/supervisor/conf.d/host_message.conf > /dev/null <<EOF
[program:host_message]
command=$REMOTE_DIR/start_app.sh
directory=$REMOTE_DIR
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$REMOTE_DIR/logs/supervisor.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
environment=PATH=\"/home/ubuntu/host_message_venv/bin:/usr/local/bin:/usr/bin:/bin\",PYTHONPATH=\"$REMOTE_DIR\"
startsecs=10
startretries=3
EOF
    
    # 停止可能存在的旧进程
    sudo supervisorctl stop host_message 2>/dev/null || true
    
    # 重新加载supervisor配置
    sudo supervisorctl reread
    sudo supervisorctl update
    
    # 启动应用
    log_info \"启动应用...\"
    sudo supervisorctl start host_message
    
    # 等待应用启动并检查状态
    log_info \"等待应用启动...\"
    for i in {1..30}; do
        sleep 2
        STATUS=\$(sudo supervisorctl status host_message 2>/dev/null || echo "ERROR")
        log_info \"第 \$i 次检查: \$STATUS\"
        
        if echo \"\$STATUS\" | grep -q \"RUNNING\"; then
            log_info \"应用启动成功！\"
            break
        elif echo \"\$STATUS\" | grep -q \"FATAL\\|BACKOFF\"; then
            log_error \"应用启动失败: \$STATUS\"
            log_error \"查看详细日志:\"
            tail -20 \"$REMOTE_DIR/logs/supervisor.log\" 2>/dev/null || echo \"无法读取日志文件\"
            
            # 运行调试脚本
            log_info \"运行调试脚本获取详细信息:\"
            cd \"$REMOTE_DIR\"
            ./debug_app.sh 2>&1 || true
            
            # 检查supervisor错误日志
            log_info \"检查supervisor错误日志:\"
            sudo tail -20 /var/log/supervisor/supervisord.log 2>/dev/null || echo \"无法读取supervisor日志\"
            
            exit 1
        fi
        
        if [ \$i -eq 30 ]; then
            log_error \"应用启动超时\"
            log_error \"最终状态: \$STATUS\"
            exit 1
        fi
    done
    
    # 检查端口监听
    log_info \"检查端口监听状态...\"
    for i in {1..10}; do
        if netstat -tlnp 2>/dev/null | grep -q \":$APP_PORT\" || ss -tlnp 2>/dev/null | grep -q \":$APP_PORT\"; then
            log_info \"端口 $APP_PORT 监听正常\"
            log_info \"部署完成！您可以通过 http://$REMOTE_HOST:$APP_PORT 访问应用\"
            break
        else
            log_warn \"等待端口 $APP_PORT 开始监听... (\$i/10)\"
            sleep 2
        fi
        
        if [ \$i -eq 10 ]; then
            log_warn \"端口 $APP_PORT 未在监听，请检查应用日志\"
            log_info \"当前监听的端口:\"
            netstat -tlnp 2>/dev/null | grep LISTEN || ss -tlnp 2>/dev/null | grep LISTEN || echo \"无法获取监听端口信息\"
        fi
    done
    
    # 清理临时文件
    rm -f \"/tmp/$ZIP_NAME\"
    
    log_info \"部署脚本执行完成\"
}

# 执行主要部署逻辑
main_deploy
EOF
)
    
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
