# Go2 Agentic Robotics Control

通过自然语言控制 Unitree Go2 机器狗的智能代理系统。

## 功能特性

- 🤖 **自然语言控制** - 通过对话方式控制机器狗
- 📹 **实时视频流** - WebRTC 摄像头画面实时传输
- 🎤 **语音识别 (ASR)** - 支持语音指令输入
- 🔊 **语音合成 (TTS)** - 机器狗语音反馈
- 🗣️ **语音对话** - 全双工语音对话，支持打断
- 🌐 **REST API** - OpenAI 兼容的 HTTP 接口
- 🔌 **WebSocket** - 实时状态推送
- 📚 **技能系统** - Markdown 定义的技能模块

## 快速开始

### 环境要求

- Python 3.10+
- Unitree Go2 机器狗

### 安装

```bash
# 克隆仓库
git clone https://github.com/jansanw/agent_brain_for_unitree_go2.git
cd agent_brain_for_unitree_go2

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置

复制环境变量示例文件并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# LLM API 配置
OPENAI_API_KEY=your_api_key_here
# 或使用阿里云 DashScope
DASHSCOPE_API_KEY=your_dashscope_key

# API 地址 (可选，默认使用 DashScope)
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 模型配置
OPENAI_MODEL=qwen-plus
ASR_MODEL=qwen3-asr-flash
TTS_MODEL=qwen3-tts-flash
```

### 启动服务器

```bash
# 连接机器狗 (通过 IP)
python server.py --ip 192.168.8.181

# 或使用序列号
python server.py --serial B42D2000XXXXXXXX

# 使用 uvicorn 启动
uvicorn server:app --host 0.0.0.0 --port 8080
```

### 连接模式

| 模式 | 说明 | 命令示例 |
|------|------|----------|
| **LocalAP** | 连接机器狗热点 | `python server.py` |
| **LocalSTA (IP)** | 通过 IP 局域网连接 | `python server.py --ip 192.168.8.181` |
| **LocalSTA (序列号)** | 通过序列号自动发现 | `python server.py --serial B42D2000XXX` |
| **Remote** | 云端远程连接 | `python server.py --remote --serial XXX --username email --password pwd` |

## API 文档

### REST API

#### 机器人控制

```bash
# 连接机器人
curl -X POST http://localhost:8080/robot/connect \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.8.181"}'

# 获取状态
curl http://localhost:8080/robot/state

# 移动
curl -X POST http://localhost:8080/robot/move \
  -H "Content-Type: application/json" \
  -d '{"x": 1.0, "y": 0}'

# 转向
curl -X POST http://localhost:8080/robot/turn \
  -H "Content-Type: application/json" \
  -d '{"degrees": 90}'

# 姿态控制
curl -X POST http://localhost:8080/robot/stance \
  -H "Content-Type: application/json" \
  -d '{"pose": "stand_up"}'

# 特技动作
curl -X POST http://localhost:8080/robot/trick \
  -H "Content-Type: application/json" \
  -d '{"name": "hello"}'
```

#### 对话接口

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "向前走两米然后转个圈"}'
```

#### 语音识别

```bash
curl -X POST http://localhost:8080/asr \
  -F "file=@audio.wav"
```

#### 语音对话

```bash
# 启动语音对话
curl -X POST http://localhost:8080/voice/start

# 停止语音对话
curl -X POST http://localhost:8080/voice/stop

# 获取语音对话状态
curl http://localhost:8080/voice/status

# 打断当前 TTS 播放
curl -X POST http://localhost:8080/voice/interrupt
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  switch (msg.type) {
    case 'connected':
      console.log('Robot connected:', msg.data);
      break;
    case 'state':
      console.log('Robot state:', msg.data);
      break;
    case 'camera':
      // Base64 JPEG image
      document.getElementById('camera').src = 
        'data:image/jpeg;base64,' + msg.data;
      break;
  }
};
```

### 可用姿态

| 姿态 | 说明 |
|------|------|
| `stand_up` | 站起 |
| `stand_down` | 趴下 |
| `balance_stand` | 平衡站立 |
| `recovery_stand` | 恢复站立 (摔倒后) |
| `sit` | 坐下 |
| `stop` | 停止 |
| `back_stand` | 后腿站立 |

### 可用特技

| 特技 | 说明 |
|------|------|
| `hello` | 招手 |
| `stretch` | 伸展 |
| `wiggle_hips` | 扭腰 |
| `scrape` | 刨地 |
| `wallow` | 打滚 |
| `show_heart` | 比心 |
| `dance1` / `dance2` | 舞蹈 |
| `front_flip` / `back_flip` | 前/后空翻 |
| `left_flip` / `right_flip` | 左/右空翻 |
| `handstand` | 倒立 |
| `front_jump` | 前跳 |
| `front_pounce` | 前扑 |

## 项目结构

```
agent_brain_for_unitree_go2/
├── server.py              # FastAPI 服务器
├── app/
│   ├── models.py          # LLM 集成
│   ├── robot_go2.py       # 机器人控制 + 音频输入输出
│   ├── voice_assistant.py # 语音对话管理
│   ├── prompts.md         # 系统提示词
│   └── vad.py             # 语音活动检测
├── skills/                # 技能定义
│   ├── base.py            # 技能加载器
│   ├── movement.md        # 移动技能
│   ├── perception.md      # 感知技能
│   ├── social.md          # 社交技能
│   ├── stance.md          # 姿态技能
│   └── trick.md           # 特技技能
├── static/
│   └── index.html         # Web UI
├── docs/
│   ├── DEVELOPMENT_INDEX.md
│   └── UnitreeWebRTCConnection.md
└── requirements.txt
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | - | OpenAI API 密钥 |
| `DASHSCOPE_API_KEY` | - | 阿里云 DashScope 密钥 |
| `OPENAI_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | API 地址 |
| `OPENAI_MODEL` | `glm-5` | 默认模型 |
| `ASR_MODEL` | `qwen3-asr-flash` | 语音识别模型 |
| `TTS_MODEL` | `qwen3-tts-flash` | 语音合成模型 |
| `TTS_VOICE` | `Cherry` | 语音音色 |

## 技能系统

技能是 Markdown 文件定义的操作指南，位于 `skills/` 目录：

```markdown
---
name: movement
description: 机器人移动控制
---

# Movement Skill

## Overview
控制机器人移动...

## Instructions
详细指令...
```

使用方式：

```python
from skills.base import get_skill_loader

loader = get_skill_loader()
skill = loader.get("movement")
print(skill.content)
```

## 开发文档

详细的开发文档请参考 [DEVELOPMENT_INDEX.md](docs/DEVELOPMENT_INDEX.md)。

## 相关链接

- [Unitree Go2 官网](https://www.unitree.com/go2)
- [unitree_webrtc_connect](https://github.com/jrcichra/unitree_webrtc_connect) - WebRTC 通信库
- [FastAPI 文档](https://fastapi.tiangolo.com/)

## 许可证

MIT License