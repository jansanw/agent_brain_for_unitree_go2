# UnitreeWebRTCConnection 开发 Agent Skill

## 概述

`UnitreeWebRTCConnection` 是一个用于与 Unitree Go2 机器狗建立 WebRTC 连接的 Python 库。它提供了完整的 API 来控制机器狗的运动、获取状态数据、接收视频/音频流、控制 LED 灯等功能。

---

## 连接方式

### 1. LocalAP 模式（本地AP直连）
通过机器狗的热点直接连接（IP: 192.168.12.1）

```python
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod

conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
await conn.connect()
```

### 2. LocalSTA 模式（局域网连接）
通过局域网连接，需要提供 IP 地址或序列号

```python
# 使用 IP 地址
conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip="192.168.8.181")

# 使用序列号（会自动扫描局域网）
conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, serialNumber="B42D2000XXXXXXXX")
```

### 3. Remote 模式（远程连接）
通过云端服务器远程连接，需要账号密码和序列号

```python
conn = UnitreeWebRTCConnection(
    WebRTCConnectionMethod.Remote, 
    serialNumber="B42D2000XXXXXXXX", 
    username="email@gmail.com", 
    password="your_password"
)
await conn.connect()
```

---

## 核心 API

### UnitreeWebRTCConnection 类

#### 初始化参数
| 参数 | 类型 | 说明 |
|------|------|------|
| `connectionMethod` | WebRTCConnectionMethod | 连接方式 (LocalAP/LocalSTA/Remote) |
| `serialNumber` | str | 机器狗序列号（可选） |
| `ip` | str | 机器狗IP地址（可选） |
| `username` | str | 远程连接用户名（可选） |
| `password` | str | 远程连接密码（可选） |

#### 主要方法
| 方法 | 说明 |
|------|------|
| `async connect()` | 建立 WebRTC 连接 |
| `async disconnect()` | 断开连接 |
| `async reconnect()` | 重新连接 |

#### 子模块
| 属性 | 类型 | 说明 |
|------|------|------|
| `datachannel` | WebRTCDataChannel | 数据通道模块 |
| `audio` | WebRTCAudioChannel | 音频通道模块 |
| `video` | WebRTCVideoChannel | 视频通道模块 |
| `pc` | RTCPeerConnection | aiortc 原生连接对象 |

---

### WebRTCDataChannel 类

#### 发布/订阅方法

```python
# 订阅主题
conn.datachannel.pub_sub.subscribe(topic, callback)

# 取消订阅
conn.datachannel.pub_sub.unsubscribe(topic)

# 发布消息（带回调）
response = await conn.datachannel.pub_sub.publish(topic, data, msg_type)

# 发布消息（无回调）
conn.datachannel.pub_sub.publish_without_callback(topic, data, msg_type)

# 发送请求并等待响应
response = await conn.datachannel.pub_sub.publish_request_new(topic, options)
```

#### publish_request_new 参数结构
```python
options = {
    "api_id": 1001,           # 必需：API ID
    "parameter": {"key": "value"},  # 可选：参数对象
    "id": 12345,              # 可选：请求ID
    "priority": 1             # 可选：优先级
}
response = await conn.datachannel.pub_sub.publish_request_new(RTC_TOPIC["SPORT_MOD"], options)
```

#### 通道控制
```python
# 开启/关闭视频通道
conn.datachannel.switchVideoChannel(True/False)

# 开启/关闭音频通道
conn.datachannel.switchAudioChannel(True/False)

# 设置雷达解码器类型
conn.datachannel.set_decoder(decoder_type='libvoxel')  # 或 'native'

# 禁用流量节省模式（用于雷达数据）
await conn.datachannel.disableTrafficSaving(True)
```

---

### WebRTCAudioChannel 类

```python
# 开启音频通道
conn.audio.switchAudioChannel(True)

# 添加音频帧回调
async def audio_callback(frame):
    # 处理音频帧
    audio_data = frame.to_ndarray()
    # ...

conn.audio.add_track_callback(audio_callback)
```

---

### WebRTCVideoChannel 类

```python
# 开启视频通道
conn.video.switchVideoChannel(True)

# 添加视频帧回调
async def video_callback(track):
    while True:
        frame = await track.recv()
        img = frame.to_ndarray(format="bgr24")
        # 处理视频帧...

conn.video.add_track_callback(video_callback)
```

---

## 常量参考

### RTC_TOPIC - 数据通道主题

```python
from unitree_webrtc_connect.constants import RTC_TOPIC

RTC_TOPIC = {
    # 状态数据
    "LOW_STATE": "rt/lf/lowstate",                    # 低层状态
    "MULTIPLE_STATE": "rt/multiplestate",              # 多重状态
    "SPORT_MOD_STATE": "rt/sportmodestate",            # 运动模式状态
    "LF_SPORT_MOD_STATE": "rt/lf/sportmodestate",      # 低层运动模式状态
    
    # 控制
    "SPORT_MOD": "rt/api/sport/request",               # 运动控制
    "LOW_CMD": "rt/lowcmd",                             # 低层命令
    "WIRELESS_CONTROLLER": "rt/wirelesscontroller",    # 无线控制器
    
    # 视频/音频
    "FRONT_PHOTO_REQ": "rt/api/videohub/request",       # 前置摄像头请求
    "AUDIO_HUB_REQ": "rt/api/audiohub/request",         # 音频中心请求
    "AUDIO_HUB_PLAY_STATE": "rt/audiohub/player/state", # 音频播放状态
    
    # 雷达
    "ULIDAR_SWITCH": "rt/utlidar/switch",              # 雷达开关
    "ULIDAR": "rt/utlidar/voxel_map",                   # 雷达数据
    "ULIDAR_ARRAY": "rt/utlidar/voxel_map_compressed", # 压缩雷达数据
    "ULIDAR_STATE": "rt/utlidar/lidar_state",           # 雷达状态
    "ROBOTODOM": "rt/utlidar/robot_pose",              # 机器人位姿
    
    # VUI (LED和音量)
    "VUI": "rt/api/vui/request",                        # VUI控制
    
    # UWB
    "UWB_REQ": "rt/api/uwbswitch/request",             # UWB请求
    "UWB_STATE": "rt/uwbstate",                        # UWB状态
    
    # 其他
    "BASH_REQ": "rt/api/bashrunner/request",           # Bash命令
    "SELF_TEST": "rt/selftest",                         # 自检
    "SERVICE_STATE": "rt/servicestate",                # 服务状态
    "OBSTACLES_AVOID": "rt/api/obstacles_avoid/request", # 避障
    "MOTION_SWITCHER": "rt/api/motion_switcher/request", # 运动模式切换
    # ... 更多主题
}
```

### SPORT_CMD - 运动命令

```python
from unitree_webrtc_connect.constants import SPORT_CMD

SPORT_CMD = {
    # 基础控制
    "Damp": 1001,              # 阻尼模式
    "BalanceStand": 1002,      # 平衡站立
    "StopMove": 1003,          # 停止移动
    "StandUp": 1004,           # 站起
    "StandDown": 1005,         # 趴下
    "RecoveryStand": 1006,     # 恢复站立
    
    # 姿态控制
    "Euler": 1007,             # 欧拉角控制
    "BodyHeight": 1013,        # 身体高度
    "FootRaiseHeight": 1014,   # 抬脚高度
    "SpeedLevel": 1015,        # 速度等级
    "SwitchGait": 1011,        # 切换步态
    
    # 移动
    "Move": 1008,              # 移动 (x, y, z 参数)
    "Sit": 1009,               # 坐下
    "RiseSit": 1010,           # 起身
    
    # 特技动作
    "Hello": 1016,             # 招手
    "Stretch": 1017,           # 伸展
    "Wallow": 1021,            # 打滚
    "Dance1": 1022,            # 舞蹈1
    "Dance2": 1023,            # 舞蹈2
    "Scrape": 1029,            # 刨地
    "FrontFlip": 1030,         # 前空翻
    "BackFlip": 1044,           # 后空翻
    "LeftFlip": 1042,          # 左空翻
    "RightFlip": 1043,         # 右空翻
    "FrontJump": 1031,         # 前跳
    "FrontPounce": 1032,       # 前扑
    "WiggleHips": 1033,        # 扭腰
    "FingerHeart": 1036,       # 比心
    "Bound": 1304,             # 跳跃
    "MoonWalk": 1305,          # 太空步
    "Handstand": 1301,         # 倒立
    "StandOut": 1039,          # 站出（AI模式）
    
    # 状态查询
    "GetBodyHeight": 1024,     # 获取身体高度
    "GetFootRaiseHeight": 1025, # 获取抬脚高度
    "GetSpeedLevel": 1026,     # 获取速度等级
    "GetState": 1034,          # 获取状态
    
    # 其他
    "Trigger": 1012,           # 触发器
    "TrajectoryFollow": 1018,  # 轨迹跟随
    "ContinuousGait": 1019,    # 连续步态
    "Content": 1020,           # 内容
    "SwitchJoystick": 1027,   # 切换摇杆
    "Pose": 1028,              # 姿态
    "EconomicGait": 1035,     # 经济步态
    # ...
}
```

### AUDIO_API - 音频命令

```python
from unitree_webrtc_connect.constants import AUDIO_API

AUDIO_API = {
    # 播放器控制
    "GET_AUDIO_LIST": 1001,           # 获取音频列表
    "SELECT_START_PLAY": 1002,        # 选择并开始播放
    "PAUSE": 1003,                    # 暂停
    "UNSUSPEND": 1004,                # 继续播放
    "SELECT_PREV_START_PLAY": 1005,   # 上一首
    "SELECT_NEXT_START_PLAY": 1006,   # 下一首
    "SET_PLAY_MODE": 1007,            # 设置播放模式
    "SELECT_RENAME": 1008,            # 重命名
    "SELECT_DELETE": 1009,            # 删除
    "GET_PLAY_MODE": 1010,            # 获取播放模式
    
    # 上传
    "UPLOAD_AUDIO_FILE": 2001,        # 上传音频文件
    
    # 内部语料
    "PLAY_START_OBSTACLE_AVOIDANCE": 3001,  # 开始避障
    "PLAY_EXIT_OBSTACLE_AVOIDANCE": 3002,   # 退出避障
    "PLAY_START_COMPANION_MODE": 3003,      # 开始伴随模式
    "PLAY_EXIT_COMPANION_MODE": 3004,       # 退出伴随模式
    
    # 扩音器
    "ENTER_MEGAPHONE": 4001,          # 进入扩音模式
    "EXIT_MEGAPHONE": 4002,           # 退出扩音模式
    "UPLOAD_MEGAPHONE": 4003,         # 上传扩音内容
}
```

### VUI_COLOR - LED颜色

```python
from unitree_webrtc_connect.constants import VUI_COLOR

VUI_COLOR = {
    'WHITE': 'white',
    'RED': 'red',
    'YELLOW': 'yellow',
    'BLUE': 'blue',
    'GREEN': 'green',
    'CYAN': 'cyan',
    'PURPLE': 'purple'
}
```

---

## 使用示例

### 完整连接示例

```python
import asyncio
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod

async def main():
    # 创建连接
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip="192.168.8.181")
    
    try:
        # 连接
        await conn.connect()
        
        # 在这里执行你的操作...
        
    finally:
        # 断开连接
        await conn.disconnect()

asyncio.run(main())
```

### 运动控制示例

```python
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

# 获取当前运动模式
response = await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["MOTION_SWITCHER"], 
    {"api_id": 1001}
)
current_mode = json.loads(response['data']['data'])['name']

# 切换到正常模式
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["MOTION_SWITCHER"], 
    {"api_id": 1002, "parameter": {"name": "normal"}}
)

# 执行招手动作
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["SPORT_MOD"], 
    {"api_id": SPORT_CMD["Hello"]}
)

# 移动（参数：x前进速度, y侧移速度, z旋转速度）
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["SPORT_MOD"], 
    {"api_id": SPORT_CMD["Move"], "parameter": {"x": 0.5, "y": 0, "z": 0}}
)

# 切换到AI模式
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["MOTION_SWITCHER"], 
    {"api_id": 1002, "parameter": {"name": "ai"}}
)

# AI模式下的特殊动作
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["SPORT_MOD"], 
    {"api_id": SPORT_CMD["StandOut"], "parameter": {"data": True}}
)
```

### 订阅状态数据示例

```python
# 订阅低层状态
def lowstate_callback(message):
    data = message['data']
    imu = data['imu_state']['rpy']
    motors = data['motor_state']
    battery = data['bms_state']
    print(f"IMU RPY: {imu}")
    print(f"Battery SOC: {battery['soc']}%")

conn.datachannel.pub_sub.subscribe(RTC_TOPIC['LOW_STATE'], lowstate_callback)

# 订阅运动模式状态
def sportmode_callback(message):
    data = message['data']
    print(f"Mode: {data['mode']}, Position: {data['position']}")

conn.datachannel.pub_sub.subscribe(RTC_TOPIC['LF_SPORT_MOD_STATE'], sportmode_callback)

# 保持运行以接收数据
await asyncio.sleep(3600)
```

### 视频流示例

```python
import cv2
import numpy as np

async def recv_camera_stream(track):
    while True:
        frame = await track.recv()
        img = frame.to_ndarray(format="bgr24")
        cv2.imshow('Video', img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# 开启视频通道
conn.video.switchVideoChannel(True)

# 添加回调
conn.video.add_track_callback(recv_camera_stream)
```

### 音频接收示例

```python
import wave
import numpy as np

# 开启音频通道
conn.audio.switchAudioChannel(True)

async def save_audio(frame):
    audio_data = np.frombuffer(frame.to_ndarray(), dtype=np.int16)
    # 保存到文件...

conn.audio.add_track_callback(save_audio)
```

### 音频播放示例（MP3/网络电台）

```python
from aiortc.contrib.media import MediaPlayer

# 播放本地MP3文件
player = MediaPlayer("path/to/file.mp3")
conn.pc.addTrack(player.audio)

# 播放网络电台
player = MediaPlayer("https://stream-url.mp3")
conn.pc.addTrack(player.audio)
```

### LED灯和音量控制（VUI）

```python
# 获取当前亮度
response = await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["VUI"], 
    {"api_id": 1006}
)
brightness = json.loads(response['data']['data'])['brightness']

# 设置亮度 (0-10)
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["VUI"], 
    {"api_id": 1005, "parameter": {"brightness": 5}}
)

# 设置LED颜色和闪烁
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["VUI"], 
    {
        "api_id": 1007,
        "parameter": {
            "color": VUI_COLOR.PURPLE,
            "time": 5,           # 持续时间（秒）
            "flash_cycle": 1000  # 闪烁周期（毫秒）
        }
    }
)

# 获取音量
response = await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["VUI"], 
    {"api_id": 1004}
)

# 设置音量 (0-10)
await conn.datachannel.pub_sub.publish_request_new(
    RTC_TOPIC["VUI"], 
    {"api_id": 1003, "parameter": {"volume": 5}}
)
```

### 雷达数据示例

```python
# 禁用流量节省模式
await conn.datachannel.disableTrafficSaving(True)

# 设置解码器
conn.datachannel.set_decoder(decoder_type='libvoxel')

# 开启雷达
conn.datachannel.pub_sub.publish_without_callback(RTC_TOPIC["ULIDAR_SWITCH"], "on")

# 订阅雷达数据
def lidar_callback(message):
    point_cloud = message["data"]
    print(f"Received {len(point_cloud)} points")

conn.datachannel.pub_sub.subscribe(RTC_TOPIC["ULIDAR_ARRAY"], lidar_callback)
```

---

## 最佳实践

### 1. 连接管理
- 始终使用 `try/finally` 或 `async with` 模式确保正确断开连接
- 远程连接需要确保网络稳定

### 2. 错误处理
```python
try:
    response = await conn.datachannel.pub_sub.publish_request_new(topic, options)
    if response['data']['header']['status']['code'] == 0:
        # 成功
        data = json.loads(response['data']['data'])
    else:
        # 处理错误
        print(f"Error: {response['data']['header']['status']['code']}")
except Exception as e:
    logging.error(f"Request failed: {e}")
```

### 3. 异步编程
- 所有 WebRTC 操作都是异步的，需要在 async 函数中使用 `await`
- 使用 `asyncio.run()` 启动主异步函数

### 4. 运动模式切换
- Go2 有多种运动模式：`normal`、`ai` 等
- 某些特技动作只能在 `ai` 模式下执行
- 切换模式后需要等待几秒让机器狗稳定

### 5. 数据订阅
- 订阅后保持程序运行以接收数据
- 使用回调函数处理接收到的数据
- 数据格式为字典，包含 `type`、`topic`、`data` 字段

---

## 常见问题

### Q: 连接被拒绝？
A: 检查是否已关闭手机APP，Go2 同时只能有一个 WebRTC 客户端连接。

### Q: 数据通道未打开？
A: 确保在操作前调用 `await conn.connect()` 并等待连接成功。

### Q: 远程连接失败？
A: 确保 Unitree 账号密码正确，序列号正确，且机器狗已绑定到账号。

### Q: 视频无画面？
A: 确保调用了 `conn.video.switchVideoChannel(True)` 开启视频通道。

### Q: 音频无声音？
A: 确保调用了 `conn.audio.switchAudioChannel(True)` 开启音频通道。

---

## 版本信息

- 库: `unitree_webrtc_connect`
- 支持机器人: Unitree Go2
- 依赖: `aiortc`, `aioice`