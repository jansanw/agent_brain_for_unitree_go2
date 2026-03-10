# Go2 Agentic Robotics Control - 开发索引

> 最后更新: 2026-03-10 (添加语音对话功能)

---

## 📖 目录

1. [项目概述](#项目概述)
2. [目录结构](#目录结构)
3. [技术架构](#技术架构)
4. [核心模块详解](#核心模块详解)
   - [server.py](#serverpy---fastapi-rest-api)
   - [app/robot_go2.py](#approbot_go2py---机器人控制模块)
   - [app/models.py](#appmodelspy---llm-集成模块)
   - [app/voice_assistant.py](#appvoice_assistantpy---语音对话模块)
   - [skills/base.py](#skillsbasepy---技能加载器)
5. [API 参考](#api-参考)
6. [工具函数](#工具函数)
7. [状态管理](#状态管理)
8. [连接模式](#连接模式)
9. [技能系统](#技能系统)
10. [开发指南](#开发指南)
11. [故障排除](#故障排除)

---

## 项目概述

### 目的

通过自然语言控制 Unitree Go2 机器狗，提供 REST API 和 WebSocket 接口。

### 技术栈

```
Python 3.10+
├── WebRTC 通信: unitree_webrtc_connect (aiortc)
├── HTTP 服务器: uvicorn + FastAPI
├── 图像处理: opencv-python-headless, numpy, pillow
├── LLM 集成: openai API (支持 DashScope/阿里云)
└── 技能系统: Markdown 文件定义
```

### 核心依赖

```text
uvicorn, fastapi, starlette    # 异步 HTTP 服务器
opencv-python-headless          # 图像处理 (无 GUI)
numpy                           # 数值计算
pillow                          # 图像格式转换
unitree_webrtc_connect          # Go2 WebRTC 通信
openai                          # LLM API 客户端
langchain-core, langchain-openai # LangChain 集成
python-dotenv                   # 环境变量管理
websockets                      # WebSocket 支持
edge-tts                        # 文字转语音
```

---

## 目录结构

```
agent_brain_for_unitree_go2/
├── server.py              # FastAPI REST API 服务器
├── app/
│   ├── __init__.py
│   ├── models.py          # LLM 集成 (Chat/ASR/TTS)
│   ├── robot_go2.py       # 机器人控制模块 (核心逻辑)
│   ├── voice_assistant.py # 语音对话管理 (全双工)
│   ├── prompts.md         # 系统提示词定义
│   └── vad.py             # 语音活动检测
├── skills/
│   ├── __init__.py
│   ├── base.py            # SkillLoader 基类
│   ├── movement.md        # 移动技能定义
│   ├── perception.md      # 感知技能定义
│   ├── social.md          # 社交技能定义
│   ├── stance.md          # 姿态技能定义
│   └── trick.md           # 特技技能定义
├── static/
│   └── index.html         # Web UI 界面
├── docs/
│   ├── DEVELOPMENT_INDEX.md   # 本开发索引
│   └── UnitreeWebRTCConnection.md  # WebRTC API 文档
├── .env                   # 环境变量配置
├── .env.example           # 环境变量示例
├── .gitignore
├── README.md              # 项目说明
└── requirements.txt       # Python 依赖
```

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户界面层                            │
├─────────────────────────────────────────────────────────────┤
│   Web UI (static/index.html)                                │
│   - 摄像头实时画面                                           │
│   - 机器人状态显示                                           │
│   - 自然语言对话界面                                         │
├─────────────────────────────────────────────────────────────┤
│                      API 接口层                              │
├─────────────────────────────────────────────────────────────┤
│   REST API (server.py)                                      │
│   - POST /chat          自然语言对话                         │
│   - POST /robot/*       机器人控制                           │
│   - POST /asr           语音识别                             │
│   - WebSocket /ws       实时状态推送                         │
├─────────────────────────────────────────────────────────────┤
│                      业务逻辑层                              │
├─────────────────────────────────────────────────────────────┤
│   app/robot_go2.py - 机器人控制                              │
│   - RobotController 类                                      │
│   - 工具调度 (run_tool)                                      │
│   - 状态管理 (_sport_state, _low_state)                     │
│   - 视频帧处理 (_frame_loop)                                 │
│   - 移动控制 (_velocity_loop)                                │
│                                                             │
│   app/models.py - LLM 集成                                   │
│   - process_chat() 对话处理                                  │
│   - audio_to_text() 语音识别                                 │
│   - text_to_speech() 语音合成                                │
│                                                             │
│   skills/base.py - 技能系统                                  │
│   - SkillLoader 从 Markdown 加载技能                         │
│   - Skill 数据类                                            │
├─────────────────────────────────────────────────────────────┤
│                      通信层                                  │
├─────────────────────────────────────────────────────────────┤
│  unitree_webrtc_connect                                    │
│  - UnitreeWebRTCConnection                                 │
│  - DataChannel (pub_sub)                                   │
│  - VideoChannel / AudioChannel                             │
├─────────────────────────────────────────────────────────────┤
│                    Unitree Go2 机器狗                        │
│  - WebRTC 服务端                                            │
│  - 摄像头 / 麦克风 / LiDAR                                  │
│  - 运动控制器                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心模块详解

### server.py - FastAPI REST API

**文件位置**: `./server.py`  
**代码行数**: ~350 行  
**职责**: FastAPI REST API 服务器，OpenAI 兼容接口

#### 主要组件

##### 1. Pydantic 模型

```python
class ConnectRequest(BaseModel):
    ip: Optional[str] = None
    serial: Optional[str] = None
    remote: bool = False
    username: Optional[str] = None
    password: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    image: bool = True

class RobotState(BaseModel):
    position: list = [0.0, 0.0, 0.0]
    velocity: list = [0.0, 0.0, 0.0]
    rpy_rad: list = [0.0, 0.0, 0.0]
    body_height: float = 0.0
    gait: int = 0
    battery_pct: int = 0
    battery_v: float = 0.0
    range_obstacle: list = [0.0, 0.0, 0.0, 0.0]
```

##### 2. WebSocket 连接管理器

```python
class ConnectionManager:
    """管理 WebSocket 连接，实时推送机器人状态"""
    
    async def connect(websocket: WebSocket)
    def disconnect(websocket: WebSocket)
    async def broadcast(message: dict)
```

##### 3. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web UI 首页 |
| `/health` | GET | 健康检查 |
| `/robot/connect` | POST | 连接机器人 |
| `/robot/disconnect` | POST | 断开连接 |
| `/robot/state` | GET | 获取机器人状态 |
| `/robot/camera` | GET | 获取摄像头图像 |
| `/robot/move` | POST | 移动控制 |
| `/robot/turn` | POST | 转向控制 |
| `/robot/stop` | POST | 停止 |
| `/robot/stance` | POST | 姿态控制 |
| `/robot/trick` | POST | 特技动作 |
| `/robot/led` | POST | LED 控制 |
| `/robot/look` | POST | 视角调整 |
| `/robot/speed` | POST | 速度设置 |
| `/robot/gait` | POST | 步态设置 |
| `/chat` | POST | 自然语言对话 |
| `/chat/history` | DELETE | 清空对话历史 |
| `/asr` | POST | 语音识别 |
| `/ws` | WebSocket | 实时状态流 |

##### 4. 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--ip` | 192.168.8.181 | 机器狗 IP 地址 |
| `--serial` | - | 机器狗序列号 |
| `--remote` | False | 远程连接模式 |
| `--username` | - | Unitree 账号 (远程) |
| `--password` | - | Unitree 密码 (远程) |
| `--host` | 0.0.0.0 | HTTP 监听地址 |
| `--port` | 8080 | HTTP 监听端口 |
| `--no-connect` | False | 启动时不自动连接 |

##### 5. 使用示例

```bash
# 启动服务器
python server.py --ip 192.168.8.181

# 使用 uvicorn 启动
uvicorn server:app --host 0.0.0.0 --port 8080

# 连接机器人
curl -X POST http://localhost:8080/robot/connect \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.8.181"}'

# 发送对话
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "让机器狗站起来"}'
```

---

### app/robot_go2.py - 机器人控制模块

**文件位置**: `./app/robot_go2.py`  
**代码行数**: ~400 行  
**职责**: 低层机器人控制、状态管理、工具执行

#### 主要组件

##### 1. RobotController 类

```python
class RobotController:
    """Unitree Go2 机器人控制器"""
    
    # 属性
    @property
    def connected(self) -> bool      # 是否已连接
    @property
    def camera_active(self) -> bool  # 摄像头是否活跃
    
    # 方法
    async def connect(...)           # 建立连接
    async def disconnect()           # 断开连接
    def get_state() -> dict          # 获取状态摘要
    def get_camera_frame(quality)    # 获取摄像头帧 (base64)
    def get_forward_obstacle()       # 获取前方障碍物距离
```

##### 2. 工具定义 (TOOLS)

```python
TOOLS = [
    {"type": "function", "function": {"name": "move", ...}},      # 移动
    {"type": "function", "function": {"name": "turn", ...}},      # 转向
    {"type": "function", "function": {"name": "stance", ...}},    # 姿态
    {"type": "function", "function": {"name": "trick", ...}},     # 特技
    {"type": "function", "function": {"name": "led", ...}},       # LED
    {"type": "function", "function": {"name": "look", ...}},      # 视角
    {"type": "function", "function": {"name": "set_speed", ...}}, # 速度
]
```

##### 3. 核心函数

| 函数 | 说明 |
|------|------|
| `get_controller()` | 获取全局控制器实例 |
| `run_tool(name, args)` | 执行工具调用 |
| `set_gait(gait)` | 设置步态 |
| `_mcf(name, parameter, timeout)` | 发送 MCF 命令 |
| `_velocity_loop(vx, vy, vyaw, duration)` | 速度控制循环 |

##### 4. 运动常量

```python
MOVE_TICK_HZ = 25           # 命令发送频率 (Hz)
OBSTACLE_STOP_M = 0.35      # 障碍物停止距离 (米)
WALK_SPEED = 0.5            # 行走速度 (米/秒)
STRAFE_SPEED = 0.3          # 侧移速度 (米/秒)
YAW_RATE = 0.8              # 转向速度 (弧度/秒)
```

##### 5. 步态映射

```python
_GAIT_MAP = {
    "economic": "EconomicGait",
    "static": "StaticWalk",
    "trot_run": "TrotRun",
    "free_walk": "FreeWalk",
    "free_bound": "FreeBound",
    "free_jump": "FreeJump",
    "free_avoid": "FreeAvoid",
    "classic": "ClassicWalk",
    "cross_step": "CrossStep",
    "continuous": "ContinuousGait",
}
```

---

### app/models.py - LLM 集成模块

**文件位置**: `./app/models.py`  
**代码行数**: ~250 行  
**职责**: LLM API 集成、对话处理、ASR/TTS

#### 主要组件

##### 1. 配置常量

```python
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
OPENAI_MODEL = "glm-5"           # 默认模型
ASR_MODEL = "qwen3-asr-flash"    # 语音识别模型
TTS_MODEL = "qwen3-tts-flash"    # 语音合成模型
TTS_VOICE = "Cherry"             # 默认语音
```

##### 2. 客户端管理

```python
def init_client(api_key: str = None) -> OpenAI
def get_client() -> Optional[OpenAI]
```

##### 3. 对话处理

```python
async def process_chat(
    message: str,                    # 用户消息
    model: str = None,               # 模型名称
    include_image: bool = True,      # 是否包含图像
    history: list = None,            # 对话历史
    get_state: Callable = None,      # 获取机器人状态
    get_camera_frame: Callable = None, # 获取摄像头帧
    tools: list = None,              # 可用工具
    run_tool: Callable = None,       # 工具执行函数
    max_iterations: int = 10,        # 最大迭代次数
) -> tuple[str, list, dict]          # (响应, 工具调用, 机器人状态)
```

##### 4. 语音识别 (ASR)

```python
def audio_to_text(
    audio_base64_data_uri: str,  # 音频数据 (data URI)
    language: str = "zh"         # 语言代码
) -> str                         # 转写文本
```

##### 5. 语音合成 (TTS)

```python
def text_to_speech(
    text: str,
    voice: str = None,
    language_type: str = "Chinese",
    stream: bool = True
) -> Generator[bytes, None, None]  # WAV 音频流

def text_to_speech_sync(text: str, ...) -> bytes  # 完整音频

def play_audio(text: str, ...)  # 直接播放
```

##### 6. 系统提示词

从 `app/prompts.md` 加载，包含：
- **Chat System Prompt**: 机器人控制指令
- **ASR Context**: 语音识别热词

---

### app/voice_assistant.py - 语音对话模块

**文件位置**: `./app/voice_assistant.py`  
**代码行数**: ~200 行  
**职责**: 全双工语音对话管理，支持打断

#### 主要组件

##### 1. VoiceAssistant 类

```python
class VoiceAssistant:
    """语音对话管理器，支持全双工对话和打断"""
    
    # 属性
    @property
    def running(self) -> bool        # 是否正在运行
    @property
    def speaking(self) -> bool       # 是否正在播放 TTS
    
    # 方法
    async def start()                # 启动语音对话
    async def stop()                 # 停止语音对话
    async def interrupt()            # 打断当前 TTS 播放
    def get_status() -> dict         # 获取状态
```

##### 2. 核心功能

| 功能 | 说明 |
|------|------|
| VAD 检测 | 语音活动检测，自动检测用户说话 |
| 全双工对话 | 听和说同时进行 |
| 打断支持 | 用户说话时自动打断 TTS |
| 状态管理 | running, speaking 状态追踪 |

##### 3. 对话流程

```
启动 → VAD监听 → 检测语音 → ASR转文字 → LLM处理 → TTS播放
           ↑                                        ↓
           └────────── 打断 ← 用户说话 ←────────────┘
```

##### 4. 全局函数

```python
def get_voice_assistant() -> VoiceAssistant  # 获取全局实例
```

---

### skills/base.py - 技能加载器

**文件位置**: `./skills/base.py`  
**代码行数**: ~150 行  
**职责**: 从 Markdown 文件加载技能定义

#### 主要组件

##### 1. 数据类

```python
@dataclass
class SkillResult:
    success: bool
    message: str
    data: Optional[dict] = None
    audio_response: Optional[str] = None

@dataclass
class Skill:
    name: str           # 技能标识
    description: str    # 简短描述
    content: str        # 完整 Markdown 内容
    path: Path = None   # 源文件路径
    
    def to_tool_schema() -> dict  # 转换为 OpenAI 工具模式
```

##### 2. SkillLoader 类

```python
class SkillLoader:
    """从 Markdown 文件加载技能定义"""
    
    def __init__(self, skills_dir: str = "skills")
    def load_all() -> dict[str, Skill]     # 加载所有技能
    def get(name: str) -> Optional[Skill]  # 获取单个技能
    def list_skills() -> list[Skill]       # 列出所有技能
    def get_skills_description() -> str    # 获取技能描述 (用于系统提示词)
```

##### 3. Markdown 文件格式

```markdown
---
name: skill-name
description: Short description for LLM
---

# Skill Title

## Overview
...

## Instructions
...
```

##### 4. 全局函数

```python
def get_skill_loader(skills_dir: str = "skills") -> SkillLoader
def get_skill(name: str) -> Optional[Skill]
```

---

## API 参考

### REST API 端点

#### 机器人连接

| 端点 | 方法 | 说明 |
|------|------|------|
| `/robot/connect` | POST | 连接机器人 |
| `/robot/disconnect` | POST | 断开连接 |

**请求示例**:
```json
{
  "ip": "192.168.8.181",
  "serial": null,
  "remote": false,
  "username": null,
  "password": null
}
```

#### 机器人状态

| 端点 | 方法 | 说明 |
|------|------|------|
| `/robot/state` | GET | 获取机器人状态 |
| `/robot/camera` | GET | 获取摄像头图像 (base64) |

**状态响应**:
```json
{
  "position": [0.0, 0.0, 0.0],
  "velocity": [0.0, 0.0, 0.0],
  "rpy_rad": [0.0, 0.0, 0.0],
  "body_height": 0.0,
  "gait": 0,
  "battery_pct": 85,
  "battery_v": 28.5,
  "range_obstacle": [0.5, 0.0, 0.0, 0.0]
}
```

#### 运动控制

| 端点 | 方法 | 说明 |
|------|------|------|
| `/robot/move` | POST | 移动 (x: 前后, y: 左右) |
| `/robot/turn` | POST | 转向 (degrees) |
| `/robot/stop` | POST | 停止 |
| `/robot/speed` | POST | 设置速度等级 (0-2) |
| `/robot/gait` | POST | 设置步态 |

#### 姿态与特技

| 端点 | 方法 | 说明 |
|------|------|------|
| `/robot/stance` | POST | 姿态控制 |
| `/robot/trick` | POST | 特技动作 |

**姿态选项**: `stand_up`, `stand_down`, `balance_stand`, `recovery_stand`, `sit`, `stop`, `back_stand`

**特技选项**: `hello`, `stretch`, `wiggle_hips`, `scrape`, `wallow`, `show_heart`, `dance1`, `dance2`, `front_flip`, `back_flip`, `left_flip`, `right_flip`, `handstand`, `front_jump`, `front_pounce`

#### LED 控制

| 端点 | 方法 | 说明 |
|------|------|------|
| `/robot/led` | POST | LED 颜色控制 |

**颜色选项**: `white`, `red`, `yellow`, `blue`, `green`, `cyan`, `purple`

#### 对话

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 自然语言对话 |
| `/chat/history` | DELETE | 清空对话历史 |

**对话请求**:
```json
{
  "message": "向前走两米",
  "model": "qwen-plus",
  "image": true
}
```

**对话响应**:
```json
{
  "response": "好的，我向前走了两米...",
  "tool_calls": [{"tool": "move", "arguments": {"x": 2.0}, "result": "ok"}],
  "robot_state": {...}
}
```

#### 语音识别

| 端点 | 方法 | 说明 |
|------|------|------|
| `/asr` | POST | 上传音频文件进行识别 |

**请求**: `multipart/form-data` with audio file

**响应**:
```json
{
  "text": "向前走两米"
}
```

#### 语音对话

| 端点 | 方法 | 说明 |
|------|------|------|
| `/voice/start` | POST | 启动语音对话 |
| `/voice/stop` | POST | 停止语音对话 |
| `/voice/status` | GET | 获取语音对话状态 |
| `/voice/interrupt` | POST | 打断当前 TTS 播放 |

**启动语音对话**:
```json
// POST /voice/start
// 响应:
{
  "success": true,
  "message": "语音对话已启动"
}
```

**获取状态**:
```json
// GET /voice/status
// 响应:
{
  "running": true,
  "speaking": false
}
```

### WebSocket API

**端点**: `/ws`

**消息格式**:
```json
// 连接状态
{"type": "connected", "data": true}

// 机器人状态
{"type": "state", "data": {...}}

// 摄像头帧
{"type": "camera", "data": "base64..."}
```

---

## 工具函数

### app/robot_go2.py

```python
async def run_tool(name: str, args: dict) -> str:
    """
    执行工具调用
    
    Args:
        name: 工具名称 (move, turn, stance, trick, led, look, set_speed)
        args: 工具参数
    
    Returns:
        结果消息
    """

async def set_gait(gait: str) -> tuple[bool, str]:
    """
    设置步态
    
    Args:
        gait: 步态名称 (economic, static, trot_run, etc.)
    
    Returns:
        (成功, 消息)
    """
```

### app/models.py

```python
async def process_chat(...) -> tuple[str, list, dict]:
    """
    处理对话消息，支持工具调用
    
    Returns:
        (响应文本, 工具调用列表, 机器人状态)
    """

def audio_to_text(audio_base64_data_uri: str, language: str = "zh") -> str:
    """
    语音转文字
    
    Returns:
        转写文本
    """

def text_to_speech(text: str, ...) -> Generator[bytes, None, None]:
    """
    文字转语音
    
    Yields:
        WAV 音频数据块
    """
```

---

## 状态管理

### 全局状态变量

| 变量 | 类型 | 更新方式 | 用途 |
|------|------|----------|------|
| `_conn` | UnitreeWebRTCConnection | 连接时设置 | WebRTC 连接实例 |
| `_sport_state` | dict | 订阅回调 | 运动状态缓存 |
| `_low_state` | dict | 订阅回调 | 低层状态缓存 |
| `_latest_frame_jpg` | bytes | 视频循环 | 最新摄像头帧 |
| `_latest_frame_ts` | float | 视频循环 | 帧时间戳 |

### 状态订阅

```python
def _setup_state(self) -> None:
    """订阅机器人状态主题"""
    conn.datachannel.pub_sub.subscribe(
        RTC_TOPIC["LF_SPORT_MOD_STATE"], on_sport
    )
    conn.datachannel.pub_sub.subscribe(
        RTC_TOPIC["LOW_STATE"], on_low
    )
```

### 状态数据结构

```python
# _sport_state
{
    "position": [x, y, z],           # 位置 (米)
    "velocity": [vx, vy, vz],        # 速度 (米/秒)
    "imu_state": {"rpy": [r, p, y]}, # 姿态 (弧度)
    "body_height": 0.0,              # 身体高度
    "gait_type": 0,                  # 步态类型
    "range_obstacle": [f, l, r, b],  # 障碍物距离 (米)
}

# _low_state
{
    "motor_state": [...],            # 电机状态 (20个)
    "imu_state": {"rpy": [...]},     # IMU 姿态
    "bms_state": {                   # 电池状态
        "soc": 85,                   # 电量百分比
        "voltage": 28.5              # 电压
    },
    "foot_force": [...],             # 足端力传感器
}
```

---

## 连接模式

### LocalAP 模式

```python
# 连接机器狗热点 (默认 IP: 192.168.12.1)
conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
await conn.connect()
```

### LocalSTA 模式

```python
# 通过 IP 连接
conn = UnitreeWebRTCConnection(
    WebRTCConnectionMethod.LocalSTA, 
    ip="192.168.8.181"
)

# 通过序列号连接 (自动扫描)
conn = UnitreeWebRTCConnection(
    WebRTCConnectionMethod.LocalSTA, 
    serialNumber="B42D2000XXXXXXXX"
)
```

### Remote 模式

```python
# 通过云端远程连接
conn = UnitreeWebRTCConnection(
    WebRTCConnectionMethod.Remote,
    serialNumber="B42D2000XXXXXXXX",
    username="email@gmail.com",
    password="your_password"
)
await conn.connect()
```

### 命令行示例

```bash
# LocalAP 模式
python server.py

# LocalSTA 模式 (IP)
python server.py --ip 192.168.8.181

# LocalSTA 模式 (序列号)
python server.py --serial B42D2000XXXXXXXX

# Remote 模式
python server.py --remote \
    --serial B42D2000XXXXXXXX \
    --username email@gmail.com \
    --password your_password
```

---

## 技能系统

### 技能文件

| 文件 | 技能名 | 描述 |
|------|--------|------|
| `skills/movement.md` | movement | 移动控制 |
| `skills/perception.md` | perception | 感知能力 |
| `skills/social.md` | social | 社交动作 |
| `skills/stance.md` | stance | 姿态控制 |
| `skills/trick.md` | trick | 特技动作 |

### 使用方式

```python
from skills.base import get_skill_loader, get_skill

# 加载所有技能
loader = get_skill_loader()
skills = loader.list_skills()

# 获取单个技能
skill = get_skill("movement")
print(skill.description)
print(skill.content)

# 获取技能描述 (用于 LLM 系统提示词)
desc = loader.get_skills_description()
```

---

## 开发指南

### 添加新工具

1. **在 `app/robot_go2.py` 的 `TOOLS` 列表中定义**:

```python
{
    "type": "function",
    "function": {
        "name": "new_action",
        "description": "执行新动作",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数1"}
            },
            "required": ["param1"]
        }
    }
}
```

2. **在 `run_tool()` 函数中添加处理**:

```python
elif name == "new_action":
    param1 = args.get("param1")
    r = await c._mcf("NewAction", {"data": param1})
    return f"new_action → {'ok' if r['ok'] else 'error'}"
```

### 添加新技能

1. **创建 Markdown 文件** `skills/new_skill.md`:

```markdown
---
name: new_skill
description: 技能简短描述
---

# New Skill

## Overview
技能概述

## Instructions
详细指令...
```

2. **技能会自动被 SkillLoader 加载**

### 添加新的 API 端点

在 `server.py` 中添加:

```python
@app.post("/robot/new_endpoint", response_model=StatusResponse)
async def new_endpoint(request: NewRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("new_action", {...})
    return StatusResponse(success="ok" in result, message=result)
```

### 调试方法

1. **启用详细日志**:
```python
logging.basicConfig(level=logging.DEBUG)
```

2. **检查连接状态**:
```bash
curl http://localhost:8080/health
```

3. **测试工具调用**:
```python
result = await run_tool("stance", {"pose": "stand_up"})
print(result)
```

---

## 故障排除

### 连接问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接被拒绝 | 手机 APP 占用连接 | 关闭手机 APP |
| LocalSTA 找不到 | IP 错误或不在同一网络 | 检查 IP，确认在同一局域网 |
| Remote 连接失败 | 账号/密码/序列号错误 | 验证凭据，确认机器狗已绑定 |

### 运动问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 空翻失败 | 固件 1.1.7+ MCF 模式 | 直接调用 trick，不要切换模式 |
| 机器狗不动 | 未站起或阻尼模式 | 先执行 stance(stand_up) |
| 突然停止 | LiDAR 检测到障碍物 | 检查前方障碍物距离 |

### 视频/摄像头问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 无画面 | 视频通道未开启 | 检查连接是否正常建立 |
| 画面模糊 | JPEG 质量太低 | 调高 quality 参数 (1-100) |

### LLM 问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API 连接失败 | API Key 未设置 | 设置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY |
| 模型不存在 | 模型名称错误 | 检查 OPENAI_MODEL 环境变量 |

### 错误码参考

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| 0 | 成功 | - |
| 7004 | MCF 模式已激活 | 忽略，命令正常执行 |
| -1 | 未知错误 | 检查连接和参数 |
| -2 | 超时 | 重试或检查网络 |

---

## 相关文档

- [README.md](../README.md) - 项目说明
- [UnitreeWebRTCConnection.md](./UnitreeWebRTCConnection.md) - WebRTC API 详细文档
- [unitree_webrtc_connect](https://github.com/jrcichra/unitree_webrtc_connect) - WebRTC 库

---

*本开发索引由 Claude 自动生成并更新*