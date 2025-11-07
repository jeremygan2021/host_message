#!/bin/bash

# 部署前检查脚本
echo "=========================================="
echo "         部署前环境检查"
echo "=========================================="

# 检查本地环境
echo "1. 检查本地环境..."
echo "   - 当前目录: $(pwd)"
echo "   - 主文件存在: $(test -f main.py && echo "✅ main.py存在" || echo "❌ main.py不存在")"
echo "   - 依赖文件存在: $(test -f requirements.txt && echo "✅ requirements.txt存在" || echo "❌ requirements.txt不存在")"
echo "   - zip命令: $(command -v zip >/dev/null && echo "✅ 已安装" || echo "❌ 未安装")"

# 检查sshpass
if command -v sshpass >/dev/null; then
    echo "   - sshpass: ✅ 已安装"
else
    echo "   - sshpass: ❌ 未安装"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "     安装命令: brew install sshpass"
    else
        echo "     安装命令: sudo apt-get install sshpass"
    fi
fi

echo ""
echo "2. 检查目标服务器连接..."
REMOTE_HOST="6.6.6.86"
REMOTE_USER="ubuntu"
REMOTE_PASS="qweasdzxc1"

if command -v sshpass >/dev/null; then
    echo "   - 测试SSH连接..."
    if sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$REMOTE_USER@$REMOTE_HOST" "echo 'SSH连接正常'" 2>/dev/null; then
        echo "   - SSH连接: ✅ 正常"
        
        # 检查服务器系统信息
        echo "   - 服务器信息:"
        sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "
            echo '     操作系统: '$(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')
            echo '     Python版本: '$(python3 --version 2>/dev/null || echo '未安装')
            echo '     磁盘空间: '$(df -h / | tail -1 | awk '{print \$4}' || echo '未知') 可用
        " 2>/dev/null
    else
        echo "   - SSH连接: ❌ 失败"
        echo "     请检查服务器地址、用户名和密码"
    fi
else
    echo "   - SSH连接: ⚠️ 跳过 (sshpass未安装)"
fi

echo ""
echo "3. 检查项目文件..."
echo "   - 项目大小: $(du -sh . 2>/dev/null | cut -f1 || echo "未知")"
echo "   - 关键文件检查:"
echo "     * main.py: $(test -f main.py && echo "✅ 存在" || echo "❌ 缺失")"
echo "     * requirements.txt: $(test -f requirements.txt && echo "✅ 存在" || echo "❌ 缺失")"
echo "     * database/ip_list.json: $(test -f database/ip_list.json && echo "✅ 存在" || echo "❌ 缺失")"

if [ -f "requirements.txt" ]; then
    echo "   - Python依赖包:"
    while IFS= read -r line; do
        if [[ ! $line =~ ^[[:space:]]*# ]] && [[ ! -z $line ]]; then
            echo "     * $line"
        fi
    done < requirements.txt
fi

echo ""
echo "=========================================="
echo "检查完成！如果所有项目都显示 ✅，您可以运行:"
echo "./deploy.sh"
echo "=========================================="
