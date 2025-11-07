# FastAPI 文件共享和聊天应用

这是一个基于FastAPI的文件共享和实时聊天应用，支持Docker部署并解决了Docker环境下IP获取错误的问题。

## ✨ 主要功能

- 📁 文件上传和下载
- 💬 实时聊天（WebSocket）
- 👥 显示在线用户
- 🔍 真实IP地址获取（支持Docker/代理环境）
- ❤️ 健康检查
- 🗑️ 文件删除功能

## 🚀 快速开始

### 方式1：Docker Compose（推荐）

```bash
# 使用nginx反向代理（推荐，支持真实IP）
docker-compose up -d

# 访问应用
open http://localhost

# 查看日志
docker-compose logs -f
```

### 方式2：仅FastAPI服务

```bash
# 构建并运行
docker-compose up -d web

# 访问应用  
open http://localhost:1000
```

### 方式3：本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 开发模式启动
./start.sh dev

# 或直接启动
python main.py
```

## 🔧 IP获取优化

### 问题说明
在Docker环境中，传统的 `request.client.host` 会返回Docker内部网络IP（如172.x.x.x），而不是真实的客户端IP。

### 解决方案
本项目实现了智能IP获取机制：

1. **优先级顺序**：
   - `X-Forwarded-For` 头部
   - `X-Real-IP` 头部  
   - `client.host`（排除Docker内部IP）

2. **支持的代理场景**：
   - Nginx反向代理
   - Docker网络
   - Cloudflare等CDN
   - 各种负载均衡器

### 配置示例

#### Nginx配置
```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

#### Docker启动参数
```bash
uvicorn main:app --proxy-headers --forwarded-allow-ips "*"
```

## 📁 项目结构

```
├── main.py                 # 主应用文件
├── templates/              # HTML模板
│   ├── index.html         # 文件上传页面
│   └── chat.html          # 聊天页面
├── uploads/               # 文件存储目录
├── Dockerfile             # Docker构建文件
├── docker-compose.yml     # Docker编排文件
├── nginx.conf             # Nginx配置
├── requirements.txt       # Python依赖
├── start.sh              # 启动脚本
└── README.md             # 说明文档
```

## 🔗 API端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 主页（文件上传） |
| `/chat` | GET | 聊天页面 |
| `/upload` | POST | 上传文件 |
| `/files` | GET | 获取文件列表 |
| `/files/{filename}` | DELETE | 删除文件 |
| `/get_ip` | GET | 获取客户端IP |
| `/ws` | WebSocket | 聊天WebSocket |
| `/health` | GET | 健康检查 |
| `/online_users` | GET | 获取在线用户 |

## 🐳 Docker部署细节

### 环境变量
```bash
FORWARDED_ALLOW_IPS=*      # 允许所有IP转发
PROXY_HEADERS=1            # 启用代理头部
```

### 端口映射
- `1000` - FastAPI应用端口
- `80` - Nginx反向代理端口（可选）

### 数据持久化
```yaml
volumes:
  - ./uploads:/app/uploads  # 文件存储持久化
```

## 🛠️ 开发说明

### 本地开发
```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
./start.sh dev

# 或者
python main.py
```

### 调试IP获取
```python
# 查看请求头
print(request.headers)

# 测试IP获取函数
ip = get_real_client_ip(request=request)
print(f"Client IP: {ip}")
```

## 🚨 常见问题

### Q: Docker中IP显示为172.x.x.x？
A: 使用nginx反向代理或确保启动时包含 `--proxy-headers` 参数。

### Q: WebSocket连接失败？  
A: 检查防火墙设置和代理配置。

### Q: 文件上传失败？
A: 检查uploads目录权限和磁盘空间。

### Q: 健康检查失败？
A: 确保应用正常启动并且端口未被占用。

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交Issue和Pull Request！ 