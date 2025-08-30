from fastapi import FastAPI, UploadFile, File, WebSocket, Form, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
import os
from datetime import datetime
import socket
from fastapi import Request
import json
from starlette.responses import StreamingResponse
import asyncio
import aiofiles
from typing import Dict, List, Optional
import uuid
from dataclasses import dataclass, asdict
from collections import defaultdict
import secrets
import base64

# 配置FastAPI应用，优化大文件上传
app = FastAPI(
    title="局域网文件传输系统",
    description="高效的局域网文件传输和聊天系统",
    version="2.0.0"
)

# HTTP Basic 认证配置
security = HTTPBasic()

# 127.0.0.1 访问认证配置
LOCALHOST_USERNAME = "tangledupai"
LOCALHOST_PASSWORD = "123tangledup-ai"

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """验证用户名和密码"""
    correct_username = secrets.compare_digest(credentials.username, LOCALHOST_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, LOCALHOST_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def require_auth_for_localhost(request: Request):
    """检查是否需要对127.0.0.1进行身份验证"""
    client_ip = get_real_client_ip(request=request)
    return client_ip == "127.0.0.1"

def conditional_auth(request: Request):
    """条件性身份验证：只对127.0.0.1要求认证"""
    client_ip = get_real_client_ip(request=request)
    if client_ip == "127.0.0.1":
        # 获取Basic Auth header
        authorization = request.headers.get("authorization")
        if not authorization or not authorization.startswith("Basic "):
            raise HTTPException(
                status_code=401,
                detail="Authentication required for localhost access",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        # 解析认证信息
        try:
            encoded_credentials = authorization.split(" ")[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
            
            # 验证凭据
            correct_username = secrets.compare_digest(username, LOCALHOST_USERNAME)
            correct_password = secrets.compare_digest(password, LOCALHOST_PASSWORD)
            if not (correct_username and correct_password):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Basic"},
                )
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication format",
                headers={"WWW-Authenticate": "Basic"},
            )
    
    return True

with open(os.path.join(os.path.dirname(__file__), "database", "ip_list.json"), "r") as f:
    ip_list = json.load(f)

admin_ip = ip_list["admin_ip"]
ip_vs_name = ip_list["ip_vs_name"]
ip_vs_avatar = ip_list["ip_vs_avatar"]

print(f"管理员IP: {admin_ip}")







# 允许跨域请求 - 优化大文件上传配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # 添加大文件上传相关配置
    expose_headers=["Content-Length", "Content-Range"],
    max_age=3600,  # 预检请求缓存时间
)

# 创建上传文件存储目录 //// /
#UPLOAD_DIR = "/mnt/server/host_message_files"
UPLOAD_DIR = "uploads"
CHAT_HISTORY_DIR = "chat_history"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
if not os.path.exists(CHAT_HISTORY_DIR):
    os.makedirs(CHAT_HISTORY_DIR)

# 文件夹管理函数
def ensure_folder_exists(folder_path):
    """确保文件夹存在，如果不存在则创建"""
    full_path = os.path.join(UPLOAD_DIR, folder_path)
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    return full_path

def get_file_info(file_path, relative_path=""):
    """获取文件或文件夹信息"""
    is_dir = os.path.isdir(file_path)
    name = os.path.basename(file_path)
    
    if is_dir:
        return {
            "name": name,
            "type": "folder",
            "path": relative_path,
            "size": 0,
            "created": datetime.fromtimestamp(os.path.getctime(file_path)).strftime("%Y-%m-%d %H:%M:%S"),
            "uploader_username": "系统",
            "uploader_ip": "system",
            "comment": ""
        }
    else:
        # 读取文件元数据
        metadata = {}
        metadata_path = file_path + ".meta"
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except:
                pass
        
        return {
            "name": name,
            "type": "file",
            "path": relative_path,
            "size": os.path.getsize(file_path),
            "created": datetime.fromtimestamp(os.path.getctime(file_path)).strftime("%Y-%m-%d %H:%M:%S"),
            "uploader_username": metadata.get("uploader_username", "未知用户"),
            "uploader_ip": metadata.get("uploader_ip", "未知"),
            "comment": metadata.get("comment", ""),
            "original_name": metadata.get("original_name", name)
        }

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/image", StaticFiles(directory="image"), name="image")

# 用户管理
@dataclass
class User:
    username: str
    session_id: str
    ip: str
    connected_at: datetime
    last_seen: datetime

@dataclass
class ChatMessage:
    id: str
    username: str
    message: str
    message_type: str  # 'text', 'file'
    timestamp: datetime
    target_user: Optional[str] = None  # 私聊目标用户

# 内存存储
active_users: Dict[str, User] = {}  # session_id -> User
user_sessions: Dict[str, str] = {}  # username -> session_id
chat_history: List[ChatMessage] = []  # 全局聊天历史
private_chat_history: Dict[str, List[ChatMessage]] = defaultdict(list)  # 私聊历史

# 添加全局聊天历史存储
global_chat_history: List[dict] = []
private_chat_storage: Dict[str, List[dict]] = defaultdict(list)  # IP对话历史
MAX_HISTORY_MESSAGES = 200  # 增加历史消息数量

# 历史消息文件路径
GROUP_HISTORY_FILE = os.path.join(CHAT_HISTORY_DIR, "group_history.json")
PRIVATE_HISTORY_FILE = os.path.join(CHAT_HISTORY_DIR, "private_history.json")

# 启动时加载历史消息
async def load_chat_history():
    """从文件加载聊天历史"""
    global global_chat_history, private_chat_storage
    
    # 加载群聊历史
    try:
        if os.path.exists(GROUP_HISTORY_FILE):
            async with aiofiles.open(GROUP_HISTORY_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    global_chat_history = json.loads(content)
                    print(f"加载群聊历史消息: {len(global_chat_history)} 条")
    except Exception as e:
        print(f"加载群聊历史失败: {e}")
        global_chat_history = []
    
    # 加载私聊历史
    try:
        if os.path.exists(PRIVATE_HISTORY_FILE):
            async with aiofiles.open(PRIVATE_HISTORY_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    private_chat_storage = defaultdict(list, json.loads(content))
                    print(f"加载私聊历史: {len(private_chat_storage)} 个对话")
    except Exception as e:
        print(f"加载私聊历史失败: {e}")
        private_chat_storage = defaultdict(list)

async def save_group_history():
    """保存群聊历史到文件"""
    try:
        # 保留最新的消息
        messages_to_save = global_chat_history[-MAX_HISTORY_MESSAGES:] if len(global_chat_history) > MAX_HISTORY_MESSAGES else global_chat_history
        
        async with aiofiles.open(GROUP_HISTORY_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(messages_to_save, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"保存群聊历史失败: {e}")

async def save_private_history():
    """保存私聊历史到文件"""
    try:
        # 清理过老的私聊记录，保留每个对话的最新消息
        cleaned_storage = {}
        for chat_key, messages in private_chat_storage.items():
            cleaned_storage[chat_key] = messages[-MAX_HISTORY_MESSAGES:] if len(messages) > MAX_HISTORY_MESSAGES else messages
        
        async with aiofiles.open(PRIVATE_HISTORY_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(cleaned_storage, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"保存私聊历史失败: {e}")

# 优化的IP获取函数 - 保持不变
def get_real_client_ip(request: Request = None, websocket: WebSocket = None) -> str:
    """
    获取真实的客户端IP地址，支持Docker和代理环境
    优先级：X-Forwarded-For > X-Real-IP > X-Forwarded-Proto > client.host
    """
    headers = {}
    client_host = None
    
    if request:
        headers = request.headers
        client_host = request.client.host
    elif websocket:
        headers = websocket.headers
        client_host = websocket.client.host
    
    # 尝试从各种代理头获取真实IP
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For 可能包含多个IP，第一个是原始客户端IP
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip and client_ip != "unknown":
            return client_ip
    
    # 尝试从X-Real-IP获取
    real_ip = headers.get("x-real-ip")
    if real_ip and real_ip != "unknown":
        return real_ip
    
    # 尝试从X-Forwarded-Proto获取
    forwarded_proto = headers.get("x-forwarded-proto")
    if forwarded_proto:
        # 这通常只是协议，但某些代理可能包含IP信息
        pass
    
    # 如果都没有，使用客户端host，但检查是否为Docker内部IP
    if client_host:
        # Docker内部网络通常是172.x.x.x，如果检测到则尝试其他方法
        if not client_host.startswith(("172.", "127.0.0.1", "::1")):
            return client_host
    
    # 最后的备选方案
    return client_host or "unknown"

# 修改 WebSocket 连接管理，使用用户名
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # session_id -> WebSocket

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"User connected with session: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"User disconnected: {session_id}")

    async def broadcast(self, message: dict, exclude_session: str = None):
        disconnected_sessions = []
        
        for session_id, connection in self.active_connections.items():
            if session_id != exclude_session:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"Error sending message to {session_id}: {e}")
                    disconnected_sessions.append(session_id)
        
        # 清理断开的连接
        for session_id in disconnected_sessions:
            self.disconnect(session_id)

    async def send_private_message(self, message: dict, target_session: str, sender_session: str):
        try:
            # 发送给目标用户
            if target_session in self.active_connections:
                await self.active_connections[target_session].send_json(message)
            
            # 发送给发送者（如果不是同一个session）
            if sender_session != target_session and sender_session in self.active_connections:
                await self.active_connections[sender_session].send_json(message)
        except Exception as e:
            print(f"Error in send_private_message: {e}")

manager = ConnectionManager()

# 简单连接管理（用于无需登录的聊天）
simple_connections: Dict[str, dict] = {}

async def broadcast_simple_message(message: dict, exclude_id: str = None):
    """广播消息给所有简单连接"""
    disconnected_ids = []
    
    for connection_id, connection_info in simple_connections.items():
        if connection_id != exclude_id:
            try:
                await connection_info['websocket'].send_json(message)
            except Exception as e:
                print(f"Error sending message to {connection_id}: {e}")
                disconnected_ids.append(connection_id)
    
    # 清理断开的连接
    for connection_id in disconnected_ids:
        if connection_id in simple_connections:
            del simple_connections[connection_id]

async def send_chat_history(websocket: WebSocket, client_ip: str):
    """发送所有相关聊天历史给新连接的用户"""
    try:
        total_messages_sent = 0
        
        # 发送群聊历史
        if global_chat_history:
            await websocket.send_json({
                'type': 'history_start',
                'message': '正在加载群聊历史...'
            })
            
            # 按时间排序发送群聊历史
            sorted_group_messages = sorted(global_chat_history, key=lambda x: x.get('timestamp', 0))
            for message in sorted_group_messages:
                # 确保消息格式正确
                history_message = {
                    'message': message.get('message', ''),
                    'type': message.get('type', 'text'),
                    'ip': message.get('ip', 'unknown'),
                    'timestamp': message.get('timestamp', 0),
                    'is_history': True
                }
                
                await websocket.send_json(history_message)
                total_messages_sent += 1
                
                # 添加小延迟避免消息过快
                await asyncio.sleep(0.01)
        
        # 发送与该IP相关的所有私聊历史
        private_messages_sent = 0
        for chat_key, messages in private_chat_storage.items():
            # 检查这个对话是否涉及当前用户
            if client_ip in chat_key:
                if private_messages_sent == 0:
                    await websocket.send_json({
                        'type': 'history_start',
                        'message': '正在加载私聊历史...'
                    })
                
                # 按时间排序发送私聊历史
                sorted_private_messages = sorted(messages, key=lambda x: x.get('timestamp', 0))
                for message in sorted_private_messages:
                    # 确保消息格式正确
                    history_message = {
                        'message': message.get('message', ''),
                        'type': message.get('type', 'text'),
                        'ip': message.get('ip', 'unknown'),
                        'timestamp': message.get('timestamp', 0),
                        'targetIp': message.get('targetIp', ''),
                        'is_history': True
                    }
                    
                    await websocket.send_json(history_message)
                    private_messages_sent += 1
                    total_messages_sent += 1
                    
                    # 添加小延迟避免消息过快
                    await asyncio.sleep(0.01)
        
        # 发送加载完成消息
        if total_messages_sent > 0:
            await websocket.send_json({
                'type': 'history_end',
                'message': f'历史消息加载完成 (群聊: {len(global_chat_history)} 条, 私聊: {private_messages_sent} 条)'
            })
            print(f"发送历史消息给 {client_ip}: 群聊 {len(global_chat_history)} 条, 私聊 {private_messages_sent} 条")
        else:
            print(f"没有历史消息发送给 {client_ip}")
        
    except Exception as e:
        print(f"Error sending chat history: {e}")
        # 发送错误消息
        try:
            await websocket.send_json({
                'type': 'system',
                'message': '历史消息加载失败',
                'ip': 'system',
                'timestamp': datetime.now().timestamp() * 1000
            })
        except:
            pass

def add_to_global_history(message: dict):
    """添加消息到全局历史记录"""
    global global_chat_history
    
    # 只保存群聊消息到全局历史
    if not message.get('targetIp'):
        # 确保时间戳存在
        if 'timestamp' not in message:
            message['timestamp'] = datetime.now().timestamp() * 1000
            
        global_chat_history.append(message)
        
        # 异步保存到文件
        asyncio.create_task(save_group_history())

def add_to_private_history(message: dict, ip1: str, ip2: str):
    """添加消息到私聊历史记录"""
    # 创建统一的聊天键（按字典序排序确保一致性）
    chat_key = "_".join(sorted([ip1, ip2]))
    
    # 确保时间戳存在
    if 'timestamp' not in message:
        message['timestamp'] = datetime.now().timestamp() * 1000
    
    private_chat_storage[chat_key].append(message)
    
    # 异步保存到文件
    asyncio.create_task(save_private_history())

async def broadcast_private_message(message: dict, target_ip: str, sender_id: str):
    """发送私聊消息给特定IP用户"""
    disconnected_ids = []
    message_sent = False
    sender_ip = None
    
    # 获取发送者IP
    if sender_id in simple_connections:
        sender_ip = simple_connections[sender_id]['ip']
    
    for connection_id, connection_info in simple_connections.items():
        # 发送给目标IP或发送者
        if connection_info['ip'] == target_ip or connection_id == sender_id:
            try:
                await connection_info['websocket'].send_json(message)
                message_sent = True
            except Exception as e:
                print(f"Error sending private message to {connection_id}: {e}")
                disconnected_ids.append(connection_id)
    
    # 保存私聊消息到历史记录
    if sender_ip and sender_ip != target_ip:
        add_to_private_history(message, sender_ip, target_ip)
    
    # 清理断开的连接
    for connection_id in disconnected_ids:
        if connection_id in simple_connections:
            del simple_connections[connection_id]
    
    if not message_sent and sender_id in simple_connections:
        try:
            await simple_connections[sender_id]['websocket'].send_json({
                'type': 'system',
                'message': f'用户 {target_ip} 不在线，消息已保存',
                'ip': 'system',
                'timestamp': datetime.now().timestamp() * 1000
            })
        except Exception as e:
            print(f"Error sending offline message notification: {e}")

# 用户认证相关端点
@app.post("/login")
async def login(username: str = Form(...), request: Request = None):
    """用户登录"""
    if not username or not username.strip():
        raise HTTPException(status_code=400, detail="用户名不能为空")
    
    username = username.strip()
    if len(username) > 20:
        raise HTTPException(status_code=400, detail="用户名长度不能超过20个字符")
    
    # 检查用户名是否已被使用
    if username in user_sessions:
        raise HTTPException(status_code=400, detail="用户名已被使用，请选择其他用户名")
    
    # 创建新的session
    session_id = str(uuid.uuid4())
    client_ip = get_real_client_ip(request=request)
    now = datetime.now()
    
    user = User(
        username=username,
        session_id=session_id,
        ip=client_ip,
        connected_at=now,
        last_seen=now
    )
    
    active_users[session_id] = user
    user_sessions[username] = session_id
    
    return {
        "session_id": session_id,
        "username": username,
        "message": "登录成功"
    }

@app.post("/logout")
async def logout(session_id: str = Form(...)):
    """用户登出"""
    if session_id in active_users:
        user = active_users[session_id]
        username = user.username
        
        # 清理用户数据
        del active_users[session_id]
        if username in user_sessions:
            del user_sessions[username]
        
        # 断开WebSocket连接
        manager.disconnect(session_id)
        
        return {"message": "登出成功"}
    
    raise HTTPException(status_code=404, detail="会话不存在")

@app.get("/check_session")
async def check_session(session_id: str):
    """检查会话是否有效"""
    if session_id in active_users:
        user = active_users[session_id]
        return {
            "valid": True,
            "username": user.username,
            "connected_at": user.connected_at.isoformat()
        }
    return {"valid": False}

@app.get("/online_users")
async def get_online_users():
    """获取在线用户列表"""
    users = []
    for session_id, user in active_users.items():
        users.append({
            "username": user.username,
            "connected_at": user.connected_at.isoformat(),
            "last_seen": user.last_seen.isoformat()
        })
    return {"users": users}

@app.get("/chat_history")
async def get_chat_history(session_id: str, limit: int = 50):
    """获取聊天历史"""
    if session_id not in active_users:
        raise HTTPException(status_code=401, detail="无效的会话")
    
    # 返回最近的聊天记录
    recent_messages = chat_history[-limit:] if len(chat_history) > limit else chat_history
    
    return {
        "messages": [
            {
                "id": msg.id,
                "username": msg.username,
                "message": msg.message,
                "message_type": msg.message_type,
                "timestamp": msg.timestamp.isoformat(),
                "target_user": msg.target_user
            }
            for msg in recent_messages
        ]
    }

@app.get("/private_chat_history")
async def get_private_chat_history(session_id: str, target_username: str, limit: int = 50):
    """获取私聊历史"""
    if session_id not in active_users:
        raise HTTPException(status_code=401, detail="无效的会话")
    
    current_user = active_users[session_id]
    # 创建聊天对的唯一标识
    chat_pair = tuple(sorted([current_user.username, target_username]))
    chat_key = f"{chat_pair[0]}_{chat_pair[1]}"
    
    messages = private_chat_history.get(chat_key, [])
    recent_messages = messages[-limit:] if len(messages) > limit else messages
    
    return {
        "messages": [
            {
                "id": msg.id,
                "username": msg.username,
                "message": msg.message,
                "message_type": msg.message_type,
                "timestamp": msg.timestamp.isoformat(),
                "target_user": msg.target_user
            }
            for msg in recent_messages
        ]
    }

@app.get("/")
async def read_root(request: Request, auth: bool = Depends(conditional_auth)):
    """
    主页面路由 - 对127.0.0.1访问需要身份验证
    """
    # 条件认证已经在依赖项中处理
    with open("templates/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/login")
async def login_page(request: Request, auth: bool = Depends(conditional_auth)):
    """登录页面 - 对127.0.0.1访问需要身份验证"""
    with open("templates/login.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    comment: str = Form(None),
    session_id: str = Form(None),  # 改为可选参数
    relative_path: str = Form(None),  # 文件夹相对路径
    target_folder: str = Form(None),  # 目标文件夹
    custom_filename: str = Form(None),  # 自定义文件名
    request: Request = None
):
    try:
        # 获取用户信息
        if session_id and session_id in active_users:
            # 使用登录用户信息
            user = active_users[session_id]
            uploader_username = user.username
            uploader_ip = user.ip
            print(f"使用登录用户信息: {uploader_username} ({uploader_ip})")
        else:
            # 使用简化模式，直接使用IP
            uploader_ip = get_real_client_ip(request=request)
            # 优化用户名显示：如果有映射名称就直接使用，否则显示"用户_IP"
            mapped_name = ip_vs_name.get(str(uploader_ip))
            if mapped_name:
                uploader_username = mapped_name + "@" + uploader_ip
                print(f"uploader_username: {uploader_username}({uploader_ip})")
            else:
                uploader_username = f"用户ip_{uploader_ip}"
                print(f"使用IP模式: {uploader_username}")
    except Exception as e:
        print(f"获取用户信息时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")
    
    try:
        # 处理文件夹结构上传
        if relative_path:
            print(f"处理文件夹上传: {relative_path}, target_folder: {target_folder}")
            # 文件夹上传，保持目录结构
            file_dir = os.path.dirname(relative_path)
            print(f"file_dir: {file_dir}")
            
            # 文件夹上传时，relative_path 已经包含完整的文件夹结构
            # 检查是否是同名文件夹重复的情况
            if target_folder and relative_path.startswith(target_folder + "/"):
                # 用户在文件夹A内上传了同名文件夹A，这通常意味着要替换当前文件夹
                # 将文件上传到根目录，避免路径重复
                print(f"检测到同名文件夹上传，将上传到根目录")
                full_dir = os.path.join(UPLOAD_DIR, file_dir) if file_dir else UPLOAD_DIR
                relative_file_path = relative_path
            elif target_folder:
                # 正常的在文件夹内上传其他文件夹的情况
                full_dir = os.path.join(UPLOAD_DIR, target_folder, file_dir) if file_dir else os.path.join(UPLOAD_DIR, target_folder)
                relative_file_path = os.path.join(target_folder, relative_path)
            else:
                # 在根目录上传文件夹
                full_dir = os.path.join(UPLOAD_DIR, file_dir) if file_dir else UPLOAD_DIR
                relative_file_path = relative_path
            
            print(f"最终路径 - full_dir: {full_dir}, relative_file_path: {relative_file_path}")
            
            # 确保目录存在
            if not os.path.exists(full_dir):
                os.makedirs(full_dir, exist_ok=True)
                print(f"创建目录: {full_dir}")
            
            # 使用原始文件名，不添加时间戳
            # 对于文件夹上传，file.filename 可能包含完整路径，我们只需要文件名部分
            if custom_filename:
                filename = custom_filename
            else:
                filename = os.path.basename(relative_path)  # 从 relative_path 中提取文件名
            print(f"file.filename: {file.filename}")
            print(f"使用的filename: {filename}")
            file_path = os.path.join(full_dir, filename)
            print(f"计算出的 file_path: {file_path}")
        else:
            print(f"处理普通文件上传: {file.filename}")
            # 普通文件上传
            if custom_filename:
                # 使用自定义文件名
                filename = custom_filename
            else:
                # 使用时间戳前缀的原始文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{file.filename}"
            
            if target_folder:
                full_dir = os.path.join(UPLOAD_DIR, target_folder)
                if not os.path.exists(full_dir):
                    os.makedirs(full_dir, exist_ok=True)
                    print(f"创建目标目录: {full_dir}")
                file_path = os.path.join(full_dir, filename)
                relative_file_path = os.path.join(target_folder, filename)
            else:
                file_path = os.path.join(UPLOAD_DIR, filename)
                relative_file_path = filename
        
        print(f"文件将保存到: {file_path}")
    except Exception as e:
        print(f"处理文件路径时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理文件路径失败: {str(e)}")
    
    # 进一步优化大文件传输 - 局域网高速传输配置
    # 将chunk_size增加到16MB，最大化局域网传输效率
    chunk_size = 16 * 1024 * 1024  # 16MB chunks for maximum LAN performance
    total_size = 0
    
    try:
        print(f"开始写入文件到: {file_path}")
        # 验证文件路径的父目录是否存在
        file_parent_dir = os.path.dirname(file_path)
        if not os.path.exists(file_parent_dir):
            print(f"父目录不存在，创建: {file_parent_dir}")
            os.makedirs(file_parent_dir, exist_ok=True)
        
        # 高性能异步文件写入，专为局域网大文件传输优化
        async with aiofiles.open(file_path, "wb", buffering=chunk_size) as f:
            # 移除所有延迟和控制权释放，让传输尽可能快
            while chunk := await file.read(chunk_size):
                await f.write(chunk)
                total_size += len(chunk)
                # 完全移除延迟 - 局域网环境下无需限速
        print(f"文件写入成功: {file_path}, 大小: {total_size}")
    except Exception as e:
        print(f"文件写入失败: {str(e)}")
        import traceback
        traceback.print_exc()
        # 清理失败的文件
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件写入失败: {str(e)}")
    
    # 异步写入元数据
    metadata = {
        "filename": filename,
        "original_name": file.filename,
        "uploader_username": uploader_username,
        "uploader_ip": uploader_ip,
        "comment": comment,
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_size": total_size
    }
    
    metadata_path = file_path + ".meta"
    async with aiofiles.open(metadata_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(metadata, ensure_ascii=False))
    
    return {
        "filename": filename,
        "path": f"/uploads/{relative_file_path}",
        "relative_path": relative_file_path,
        "uploader_username": uploader_username,
        "comment": comment,
        "size": total_size,
        "is_folder_upload": bool(relative_path)
    }

@app.get("/files")
async def list_files(
    folder: str = "",
    sort_by: str = "name",  # name, time, uploader_ip, size
    sort_order: str = "asc",  # asc, desc
    search: str = ""
):
    """获取文件列表，支持文件夹浏览、排序和搜索"""
    try:
        # 确定当前目录
        current_dir = os.path.join(UPLOAD_DIR, folder) if folder else UPLOAD_DIR
        if not os.path.exists(current_dir):
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        files = []
        
        # 遍历当前目录
        for item_name in os.listdir(current_dir):
            # 跳过元数据文件
            if item_name.endswith('.meta') or item_name == '.folder_meta':
                continue
                
            item_path = os.path.join(current_dir, item_name)
            relative_path = os.path.join(folder, item_name) if folder else item_name
            
            # 获取文件信息
            file_info = get_file_info(item_path, relative_path)
            
            # 搜索过滤
            if search:
                search_lower = search.lower()
                # 在文件名、上传者和备注中搜索
                comment = file_info.get("comment") or ""
                if (search_lower not in file_info["name"].lower() and 
                    search_lower not in file_info["uploader_username"].lower() and
                    search_lower not in comment.lower()):
                    continue
            
            files.append(file_info)
        
        # 排序
        reverse = (sort_order == "desc")
        if sort_by == "name":
            # 文件夹排在前面，然后按名称排序
            files.sort(key=lambda x: (x["type"] != "folder", x["name"]), reverse=reverse)
        elif sort_by == "time":
            files.sort(key=lambda x: x["created"], reverse=reverse)
        elif sort_by == "uploader_ip":
            files.sort(key=lambda x: x["uploader_ip"], reverse=reverse)
        elif sort_by == "size":
            files.sort(key=lambda x: x["size"], reverse=reverse)
        
        return {
            "files": files,
            "current_folder": folder,
            "parent_folder": os.path.dirname(folder) if folder else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@app.post("/folders")
async def create_folder(
    folder_name: str = Form(...),
    parent_folder: str = Form(""),
    request: Request = None
):
    """创建新文件夹"""
    try:
        # 验证文件夹名称 - 宽松版本
        if not folder_name or not folder_name.strip():
            raise HTTPException(status_code=400, detail="文件夹名称不能为空")
        
        folder_name = folder_name.strip()
        # 自动修复文件夹名称，只禁止路径分隔符
        folder_name = folder_name.replace('/', '-').replace('\\', '-').replace('|', '_')
        
        # 只检查真正有害的字符
        if any(char in folder_name for char in ['/']):
            raise HTTPException(status_code=400, detail="文件夹名称包含不安全字符")
        
        # 构建完整路径
        if parent_folder:
            folder_path = os.path.join(parent_folder, folder_name)
        else:
            folder_path = folder_name
            
        full_path = os.path.join(UPLOAD_DIR, folder_path)
        
        # 检查是否已存在
        if os.path.exists(full_path):
            raise HTTPException(status_code=400, detail="文件夹已存在")
        
        # 创建文件夹
        os.makedirs(full_path)
        
        # 获取创建者信息
        client_ip = get_real_client_ip(request=request)
        mapped_name = ip_vs_name.get(str(client_ip))
        creator = mapped_name + "@" + client_ip if mapped_name else f"用户ip_{client_ip}"
        
        # 创建文件夹元数据
        metadata = {
            "folder_name": folder_name,
            "creator": creator,
            "creator_ip": client_ip,
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "folder"
        }
        
        metadata_path = os.path.join(full_path, ".folder_meta")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)
        
        return {
            "message": "文件夹创建成功",
            "folder_name": folder_name,
            "folder_path": folder_path,
            "creator": creator
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建文件夹失败: {str(e)}")

@app.post("/move_file")
async def move_file(
    file_name: str = Form(...),
    source_folder: str = Form(""),
    target_folder: str = Form(""),
    request: Request = None
):
    """移动文件到指定文件夹"""
    try:
        # 构建源文件路径
        if source_folder:
            source_path = os.path.join(UPLOAD_DIR, source_folder, file_name)
            source_meta_path = os.path.join(UPLOAD_DIR, source_folder, f"{file_name}.meta")
        else:
            source_path = os.path.join(UPLOAD_DIR, file_name)
            source_meta_path = os.path.join(UPLOAD_DIR, f"{file_name}.meta")
        
        if not os.path.exists(source_path):
            raise HTTPException(status_code=404, detail="源文件不存在")
        
        # 构建目标文件路径
        if target_folder:
            # 确保目标文件夹存在
            ensure_folder_exists(target_folder)
            target_path = os.path.join(UPLOAD_DIR, target_folder, file_name)
            target_meta_path = os.path.join(UPLOAD_DIR, target_folder, f"{file_name}.meta")
        else:
            target_path = os.path.join(UPLOAD_DIR, file_name)
            target_meta_path = os.path.join(UPLOAD_DIR, f"{file_name}.meta")
        
        # 检查目标位置是否已有同名文件
        if os.path.exists(target_path):
            raise HTTPException(status_code=400, detail="目标位置已存在同名文件")
        
        # 移动文件和元数据
        os.rename(source_path, target_path)
        if os.path.exists(source_meta_path):
            os.rename(source_meta_path, target_meta_path)
        
        return {
            "message": "文件移动成功",
            "file_name": file_name,
            "source_folder": source_folder,
            "target_folder": target_folder
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移动文件失败: {str(e)}")

@app.delete("/folders/{folder_path:path}")
async def delete_folder(folder_path: str, request: Request = None):
    """删除文件夹（包括其中的所有文件和子文件夹）- 仅管理员可操作"""
    try:
        # 验证管理员权限
        client_ip = get_real_client_ip(request=request)
        if client_ip != admin_ip:
            raise HTTPException(status_code=403, detail="权限不足，只有管理员才能删除文件夹")
        
        full_path = os.path.join(UPLOAD_DIR, folder_path)
        
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        if not os.path.isdir(full_path):
            raise HTTPException(status_code=400, detail="指定路径不是文件夹")
        
        # 删除文件夹及其所有内容
        import shutil
        shutil.rmtree(full_path)
        
        return {"message": "文件夹及其所有内容删除成功", "folder_path": folder_path}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文件夹失败: {str(e)}")

@app.post("/rename_file")
async def rename_file(
    old_name: str = Form(...),
    new_name: str = Form(...),
    folder_path: str = Form(""),
    request: Request = None
):
    """重命名文件"""
    try:
        # 验证新文件名 - 宽松版本
        if not new_name or not new_name.strip():
            raise HTTPException(status_code=400, detail="新文件名不能为空")
        
        new_name = new_name.strip()
        # 自动修复文件名，替换有害字符
        new_name = new_name.replace('/', '-').replace('\\', '-').replace('|', '_')
        
        # 只检查真正有害的字符
        if '/' in new_name or '\\' in new_name:
            raise HTTPException(status_code=400, detail="文件名包含不安全字符")
        
        # 构建文件路径
        if folder_path:
            old_file_path = os.path.join(UPLOAD_DIR, folder_path, old_name)
            new_file_path = os.path.join(UPLOAD_DIR, folder_path, new_name)
            old_meta_path = os.path.join(UPLOAD_DIR, folder_path, f"{old_name}.meta")
            new_meta_path = os.path.join(UPLOAD_DIR, folder_path, f"{new_name}.meta")
        else:
            old_file_path = os.path.join(UPLOAD_DIR, old_name)
            new_file_path = os.path.join(UPLOAD_DIR, new_name)
            old_meta_path = os.path.join(UPLOAD_DIR, f"{old_name}.meta")
            new_meta_path = os.path.join(UPLOAD_DIR, f"{new_name}.meta")
        
        # 检查原文件是否存在
        if not os.path.exists(old_file_path):
            raise HTTPException(status_code=404, detail="原文件不存在")
        
        # 检查新文件名是否已存在
        if os.path.exists(new_file_path):
            raise HTTPException(status_code=400, detail="新文件名已存在")
        
        # 重命名文件
        os.rename(old_file_path, new_file_path)
        
        # 重命名元数据文件（如果存在）
        if os.path.exists(old_meta_path):
            os.rename(old_meta_path, new_meta_path)
            
            # 更新元数据中的原始文件名
            try:
                with open(new_meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["original_name"] = new_name
                with open(new_meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False)
            except:
                pass  # 如果更新元数据失败，文件重命名仍然成功
        
        return {
            "message": "文件重命名成功",
            "old_name": old_name,
            "new_name": new_name,
            "folder_path": folder_path
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名文件失败: {str(e)}")

@app.post("/rename_folder")
async def rename_folder(
    old_name: str = Form(...),
    new_name: str = Form(...),
    parent_folder: str = Form(""),
    request: Request = None
):
    """重命名文件夹"""
    try:
        # 验证新文件夹名
        if not new_name or not new_name.strip():
            raise HTTPException(status_code=400, detail="新文件夹名不能为空")
        
        new_name = new_name.strip()
        # 自动修复文件夹名称，替换有害字符
        new_name = new_name.replace('/', '-').replace('\\', '-').replace('|', '_')
        
        # 只检查真正有害的字符
        if '/' in new_name or '\\' in new_name:
            raise HTTPException(status_code=400, detail="文件夹名包含不安全字符")
        
        # 构建文件夹路径
        if parent_folder:
            old_folder_path = os.path.join(UPLOAD_DIR, parent_folder, old_name)
            new_folder_path = os.path.join(UPLOAD_DIR, parent_folder, new_name)
        else:
            old_folder_path = os.path.join(UPLOAD_DIR, old_name)
            new_folder_path = os.path.join(UPLOAD_DIR, new_name)
        
        # 检查原文件夹是否存在
        if not os.path.exists(old_folder_path):
            raise HTTPException(status_code=404, detail="原文件夹不存在")
        
        if not os.path.isdir(old_folder_path):
            raise HTTPException(status_code=400, detail="指定路径不是文件夹")
        
        # 检查新文件夹名是否已存在
        if os.path.exists(new_folder_path):
            raise HTTPException(status_code=400, detail="新文件夹名已存在")
        
        # 重命名文件夹
        os.rename(old_folder_path, new_folder_path)
        
        # 更新文件夹元数据（如果存在）
        meta_file = os.path.join(new_folder_path, ".folder_meta")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["folder_name"] = new_name
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False)
            except:
                pass  # 如果更新元数据失败，文件夹重命名仍然成功
        
        return {
            "message": "文件夹重命名成功",
            "old_name": old_name,
            "new_name": new_name,
            "parent_folder": parent_folder
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名文件夹失败: {str(e)}")

# 修改 WebSocket 路由
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # 验证session
    if session_id not in active_users:
        await websocket.close(code=1008, reason="Invalid session")
        return
    
    user = active_users[session_id]
    await manager.connect(websocket, session_id)
    
    # 更新用户最后在线时间
    user.last_seen = datetime.now()
    
    print(f"User {user.username} connected via WebSocket")
    
    try:
        while True:
            data = await websocket.receive_json()
            print(f"Message from {user.username}: {data}")
            
            # 创建消息对象
            message_id = str(uuid.uuid4())
            now = datetime.now()
            
            # 根据消息类型处理
            if data.get("targetUsername"):
                # 私聊消息
                target_username = data["targetUsername"]
                
                # 检查目标用户是否在线
                target_session = user_sessions.get(target_username)
                if not target_session:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"用户 {target_username} 不在线"
                    })
                    continue
                
                # 创建私聊消息
                chat_message = ChatMessage(
                    id=message_id,
                    username=user.username,
                    message=data["message"],
                    message_type=data.get("type", "text"),
                    timestamp=now,
                    target_user=target_username
                )
                
                # 存储到私聊历史
                chat_pair = tuple(sorted([user.username, target_username]))
                chat_key = f"{chat_pair[0]}_{chat_pair[1]}"
                private_chat_history[chat_key].append(chat_message)
                
                # 发送消息
                message_data = {
                    "id": message_id,
                    "username": user.username,
                    "message": data["message"],
                    "type": data.get("type", "text"),
                    "timestamp": now.isoformat(),
                    "targetUsername": target_username,
                    "isPrivate": True
                }
                
                await manager.send_private_message(message_data, target_session, session_id)
            else:
                # 群聊消息
                chat_message = ChatMessage(
                    id=message_id,
                    username=user.username,
                    message=data["message"],
                    message_type=data.get("type", "text"),
                    timestamp=now
                )
                
                # 存储到群聊历史
                chat_history.append(chat_message)
                
                # 广播消息
                message_data = {
                    "id": message_id,
                    "username": user.username,
                    "message": data["message"],
                    "type": data.get("type", "text"),
                    "timestamp": now.isoformat(),
                    "isPrivate": False
                }
                
                await manager.broadcast(message_data, exclude_session=session_id)
            
            # 更新用户最后在线时间
            user.last_seen = now
            
    except Exception as e:
        print(f"WebSocket error for {user.username}: {e}")
    finally:
        manager.disconnect(session_id)
        print(f"User {user.username} disconnected")

@app.get("/chat")
async def chat_page(request: Request, auth: bool = Depends(conditional_auth)):
    """聊天页面 - 对127.0.0.1访问需要身份验证"""
    with open("templates/chat.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/test")
async def test_chat_page(request: Request, auth: bool = Depends(conditional_auth)):
    """测试聊天页面 - 对127.0.0.1访问需要身份验证"""
    with open("test_chat.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """强制下载文件，而不是在浏览器中显示，支持文件夹路径"""
    try:
        full_file_path = os.path.join(UPLOAD_DIR, file_path)
        
        if not os.path.exists(full_file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        if os.path.isdir(full_file_path):
            raise HTTPException(status_code=400, detail="无法下载文件夹")
        
        # 读取文件元数据获取原始文件名
        metadata_path = full_file_path + ".meta"
        original_name = os.path.basename(file_path)  # 默认使用当前文件名
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    original_name = metadata.get("original_name", original_name)
            except:
                pass  # 如果读取元数据失败，使用默认文件名
        
        return FileResponse(
            path=full_file_path,
            filename=original_name,
            media_type='application/octet-stream'  # 强制下载
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

@app.delete("/files/{file_path:path}")
async def delete_file(file_path: str, request: Request = None):
    """删除文件，支持文件夹路径 - 仅管理员可操作"""
    try:
        # 验证管理员权限
        client_ip = get_real_client_ip(request=request)
        if client_ip != admin_ip:
            raise HTTPException(status_code=403, detail="权限不足，只有管理员才能删除文件")
        
        full_file_path = os.path.join(UPLOAD_DIR, file_path)
        metadata_path = full_file_path + ".meta"
        
        if not os.path.exists(full_file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        if os.path.isdir(full_file_path):
            raise HTTPException(status_code=400, detail="请使用文件夹删除接口")
        
        if os.path.exists(full_file_path):
            os.remove(full_file_path)
        if os.path.exists(metadata_path):
            os.remove(metadata_path)
        return {"message": "文件删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        return {"message": f"删除失败: {str(e)}"}

# 添加健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# 添加获取IP的端点
@app.get("/get_ip")
async def get_client_ip(request: Request):
    """获取客户端IP地址"""
    client_ip = get_real_client_ip(request=request)
    return {"ip": client_ip}

# 添加获取管理员信息的端点
@app.get("/admin/info")
async def get_admin_info(request: Request):
    """获取管理员信息"""
    client_ip = get_real_client_ip(request=request)
    return {
        "admin_ip": admin_ip,
        "is_admin": client_ip == admin_ip,
        "client_ip": client_ip
    }

# 验证管理员权限的端点
@app.get("/admin/verify")
async def verify_admin(request: Request):
    """验证当前用户是否为管理员"""
    client_ip = get_real_client_ip(request=request)
    if client_ip != admin_ip:
        raise HTTPException(status_code=403, detail="权限不足，只有管理员才能执行此操作")
    return {
        "verified": True,
        "admin_ip": admin_ip,
        "message": "管理员权限验证成功"
    }

# 添加管理员清空历史记录的API端点
@app.post("/admin/clear_history")
async def admin_clear_history(request: Request):
    """管理员清空所有聊天历史记录"""
    client_ip = get_real_client_ip(request=request)
    
    # 验证管理员权限
    if client_ip != admin_ip:
        raise HTTPException(status_code=403, detail="权限不足，只有管理员才能执行此操作")
    
    try:
        # 清空服务器端的所有历史记录
        global global_chat_history, private_chat_storage
        global_chat_history = []
        private_chat_storage = defaultdict(list)
        
        # 删除历史文件
        files_deleted = []
        if os.path.exists(GROUP_HISTORY_FILE):
            os.remove(GROUP_HISTORY_FILE)
            files_deleted.append("群聊历史文件")
            
        if os.path.exists(PRIVATE_HISTORY_FILE):
            os.remove(PRIVATE_HISTORY_FILE)
            files_deleted.append("私聊历史文件")
        
        # 创建新的空历史文件
        await save_group_history()
        await save_private_history()
        
        print(f"管理员 {client_ip} 清空了所有聊天历史记录")
        
        # 广播管理员操作消息给所有连接的用户
        admin_message = {
            'type': 'admin_action',
            'action': 'clear_all_history',
            'admin_ip': client_ip,
            'message': f'管理员 {client_ip} 已清空所有聊天记录',
            'timestamp': datetime.now().timestamp() * 1000
        }
        
        # 异步广播消息给所有WebSocket连接
        asyncio.create_task(broadcast_simple_message(admin_message))
        
        return {
            "success": True,
            "message": "所有聊天历史记录已清空",
            "admin_ip": client_ip,
            "files_deleted": files_deleted,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"清空历史记录失败: {e}")
        return {
            "success": False,
            "message": f"清空操作失败: {str(e)}",
            "admin_ip": client_ip
        }

# 修改 WebSocket 路由，支持无session的简单聊天
@app.websocket("/ws")
async def websocket_endpoint_simple(websocket: WebSocket):
    """简化的WebSocket端点，不需要session验证"""
    await websocket.accept()
    
    # 获取客户端IP
    client_ip = get_real_client_ip(websocket=websocket)
    connection_id = str(uuid.uuid4())
    
    # 添加到连接管理器
    simple_connections[connection_id] = {
        'websocket': websocket,
        'ip': client_ip,
        'connected_at': datetime.now()
    }
    
    print(f"Simple WebSocket connection from IP: {client_ip}")
    
    # 发送欢迎消息和聊天历史
    try:
        # 获取用户显示名称
        user_display_name = ip_vs_name.get(client_ip, client_ip)
        
        # 发送欢迎消息给新用户
        welcome_message = {
            'type': 'system',
            'message': f'欢迎 {user_display_name + "(" + client_ip + ")" if user_display_name != client_ip else client_ip} 加入聊天室！',
            'ip': 'system',
            'timestamp': datetime.now().timestamp() * 1000
        }
        await websocket.send_json(welcome_message)
        
        # 向其他用户广播新用户加入消息
        join_message = {
            'type': 'system',
            'message': f'用户 {user_display_name + "(" + client_ip + ")" if user_display_name != client_ip else client_ip} 加入了聊天室',
            'ip': 'system',
            'timestamp': datetime.now().timestamp() * 1000
        }
        await broadcast_simple_message(join_message, exclude_id=connection_id)
        
        # 发送聊天历史给新用户（包括群聊和相关私聊）
        await send_chat_history(websocket, client_ip)
        
    except Exception as e:
        print(f"Error sending welcome message or history: {e}")
    
    try:
        while True:
            data = await websocket.receive_json()
            print(f"Message from {client_ip}: {data}")
            
            # 处理管理员操作
            if data.get('type') == 'admin_action' and data.get('action') == 'clear_all_history':
                print(f"收到管理员清空历史记录操作，来自IP: {client_ip}")
                
                # 验证管理员权限
                if client_ip != admin_ip:
                    await websocket.send_json({
                        'type': 'system',
                        'message': '权限不足，只有管理员才能执行此操作',
                        'ip': 'system',
                        'timestamp': datetime.now().timestamp() * 1000
                    })
                    continue
                
                # 清空服务器端的所有历史记录
                global global_chat_history, private_chat_storage
                global_chat_history = []
                private_chat_storage = defaultdict(list)
                
                # 删除历史文件
                try:
                    if os.path.exists(GROUP_HISTORY_FILE):
                        os.remove(GROUP_HISTORY_FILE)
                        print("群聊历史文件已删除")
                    if os.path.exists(PRIVATE_HISTORY_FILE):
                        os.remove(PRIVATE_HISTORY_FILE)
                        print("私聊历史文件已删除")
                except Exception as e:
                    print(f"删除历史文件失败: {e}")
                
                # 广播管理员操作消息给所有用户
                admin_message = {
                    'type': 'admin_action',
                    'action': 'clear_all_history',
                    'admin_ip': client_ip,
                    'message': f'管理员 {client_ip} 已清空所有聊天记录',
                    'timestamp': datetime.now().timestamp() * 1000
                }
                
                # 发送给所有连接的用户（包括发送者）
                await broadcast_simple_message(admin_message)
                continue
            
            # 创建消息数据，确保包含所有必要字段
            message_data = {
                'message': data.get('message', ''),
                'type': data.get('type', 'text'),
                'ip': client_ip,
                'timestamp': data.get('timestamp', datetime.now().timestamp() * 1000)
            }
            
            # 如果是文件消息，保留文件相关信息
            if data.get('type') == 'file':
                message_data['type'] = 'file'
            
            # 检查是否是私聊消息
            if data.get('targetIp'):
                message_data['targetIp'] = data['targetIp']
                # 私聊消息 - 发送给目标IP和发送者，并保存到历史
                await broadcast_private_message(message_data, data['targetIp'], connection_id)
            else:
                # 群聊消息 - 广播给所有连接并保存到历史记录
                await broadcast_simple_message(message_data, exclude_id=connection_id)
                
                # 保存到全局历史记录（只有群聊消息）
                add_to_global_history(message_data)
            
    except Exception as e:
        print(f"WebSocket error for {client_ip}: {e}")
    finally:
        # 发送离开消息给其他用户
        try:
            leave_message = {
                'type': 'system',
                'message': f'用户 {user_display_name + "(" + client_ip + ")" if user_display_name != client_ip else client_ip} 离开了聊天室',
                'ip': 'system',
                'timestamp': datetime.now().timestamp() * 1000
            }
            await broadcast_simple_message(leave_message)
        except Exception as e:
            print(f"Error sending leave message: {e}")
        
        # 清理连接
        if connection_id in simple_connections:
            del simple_connections[connection_id]
        print(f"Client {client_ip} disconnected")

# 添加应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    print("正在启动聊天服务器...")
    await load_chat_history()
    print("聊天历史加载完成")

# 添加应用关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时保存数据"""
    print("正在保存聊天历史...")
    await save_group_history()
    await save_private_history()
    print("数据保存完成")

# 添加获取IP名称映射的端点
@app.get("/get_ip_names")
async def get_ip_names():
    """获取IP名称和头像映射"""
    try:
        return {
            "ip_vs_name": ip_vs_name,
            "ip_vs_avatar": ip_vs_avatar,
            "status": "success"
        }
    except Exception as e:
        return {
            "ip_vs_name": {},
            "ip_vs_avatar": {},
            "status": "error",
            "message": str(e)
        }

# Admin登录状态管理
admin_sessions: Dict[str, dict] = {}

@app.post("/admin/login")
async def admin_login(
    username: str = Form(...),
    password: str = Form(...),
    request: Request = None
):
    """Admin账号登录"""
    try:
        # 验证admin凭据（使用与localhost认证相同的账号密码）
        correct_username = secrets.compare_digest(username, LOCALHOST_USERNAME)
        correct_password = secrets.compare_digest(password, LOCALHOST_PASSWORD)
        
        if not (correct_username and correct_password):
            raise HTTPException(
                status_code=401,
                detail="用户名或密码错误"
            )
        
        # 获取客户端IP
        client_ip = get_real_client_ip(request=request)
        
        # 生成admin session
        admin_session_id = str(uuid.uuid4())
        admin_sessions[admin_session_id] = {
            'ip': client_ip,
            'username': username,
            'login_time': datetime.now(),
            'last_activity': datetime.now()
        }
        
        print(f"Admin用户 {username} 从IP {client_ip} 登录成功")
        
        return {
            "success": True,
            "admin_session_id": admin_session_id,
            "message": "Admin登录成功",
            "admin_info": {
                "username": username,
                "ip": client_ip,
                "login_time": datetime.now().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Admin登录失败: {e}")
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")

@app.post("/admin/logout")
async def admin_logout(admin_session_id: str = Form(...)):
    """Admin账号登出"""
    try:
        if admin_session_id in admin_sessions:
            admin_info = admin_sessions[admin_session_id]
            del admin_sessions[admin_session_id]
            print(f"Admin用户 {admin_info['username']} 从IP {admin_info['ip']} 登出")
            
            return {
                "success": True,
                "message": "Admin登出成功"
            }
        else:
            raise HTTPException(status_code=404, detail="Admin会话不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登出失败: {str(e)}")

@app.get("/admin/check_session")
async def check_admin_session(admin_session_id: str, request: Request = None):
    """检查admin会话是否有效"""
    try:
        if admin_session_id not in admin_sessions:
            return {"valid": False, "message": "会话不存在"}
        
        admin_info = admin_sessions[admin_session_id]
        client_ip = get_real_client_ip(request=request)
        
        # 验证IP是否匹配（可选，增强安全性）
        if admin_info['ip'] != client_ip:
            print(f"Admin会话IP不匹配: 原IP {admin_info['ip']}, 当前IP {client_ip}")
            # 可以选择是否严格检查IP，这里暂时允许IP变化
        
        # 更新最后活动时间
        admin_sessions[admin_session_id]['last_activity'] = datetime.now()
        
        return {
            "valid": True,
            "admin_info": {
                "username": admin_info['username'],
                "ip": admin_info['ip'],
                "login_time": admin_info['login_time'].isoformat(),
                "last_activity": admin_info['last_activity'].isoformat()
            }
        }
        
    except Exception as e:
        print(f"检查admin会话失败: {e}")
        return {"valid": False, "message": "检查会话失败"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0",
        port=8888, 
        reload=True,
        access_log=True,
        # 优化大文件上传配置
        limit_max_requests=1000,        # 增加最大请求数
        limit_concurrency=100,          # 增加并发限制
        timeout_keep_alive=120,         # 保持连接时间
        timeout_graceful_shutdown=30,   # 优雅关闭超时
        # 移除文件大小限制，让系统处理大文件
        app_dir=".",
        workers=1                       # 单进程处理，避免文件锁冲突
    )