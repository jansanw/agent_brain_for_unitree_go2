"""
robot_go2.py — Unitree Go2 Robot Control Module

Provides low-level robot control functions, state management, and tool execution.
This module is used by server.py and can also be used independently.

Usage:
    from robot_go2 import RobotController, TOOLS, run_tool
    
    controller = RobotController()
    await controller.connect(ip="192.168.8.181")
    state = controller.get_state()
    result = await run_tool("move", {"x": 1.0})

Features:
    - Video streaming via WebRTC
    - Audio streaming (input/output) via WebRTC
    - Robot state monitoring
    - Movement and trick control
"""

import asyncio
import base64
import time
import logging
from typing import Optional

logger = logging.getLogger("go2-robot")

# Suppress noisy aiortc / aioice logging
logging.getLogger("aiortc").setLevel(logging.CRITICAL)
logging.getLogger("aiortc.codecs.h264").setLevel(logging.CRITICAL)
logging.getLogger("aioice").setLevel(logging.CRITICAL)
logging.getLogger("aioice.stun").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    cv2 = None
    np = None
    _CV2 = False

try:
    from unitree_webrtc_connect.webrtc_driver import (
        UnitreeWebRTCConnection,
        WebRTCConnectionMethod,
    )
    from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD, SPORT_CMD as MCF_CMD
except ImportError:
    print("ERROR: unitree_webrtc_connect not installed.")
    raise

try:
    from aiortc import MediaStreamTrack
    from aiortc.contrib.media import MediaPlayer
    from av import AudioFrame
    _AIORTC = True
except ImportError:
    MediaStreamTrack = None
    MediaPlayer = None
    AudioFrame = None
    _AIORTC = False

# Monkey-patch library error handler
try:
    from unitree_webrtc_connect.msgs import error_handler as _eh

    def _safe(error):
        if not isinstance(error, (list, tuple)) or len(error) != 3:
            return
        try:
            ts, src, code = error
        except Exception:
            pass

    _eh.handle_error = _safe
except Exception:
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCF_TOPIC = "rt/api/sport/request"
MOVE_TICK_HZ = 25
MOVE_TICK_S = 1.0 / MOVE_TICK_HZ
OBSTACLE_STOP_M = 0.35

# Movement constants
WALK_SPEED = 0.5      # m/s
STRAFE_SPEED = 0.3    # m/s
YAW_RATE = 0.8        # rad/s

# Gait mapping
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


# ---------------------------------------------------------------------------
# Audio Stream Track (for TTS output to robot speaker)
# ---------------------------------------------------------------------------

if _AIORTC and MediaStreamTrack is not None:
    import io
    import wave
    import fractions
    from av import AudioFrame
    
    class AudioStreamTrack(MediaStreamTrack):
        """
        Audio stream track for sending audio to robot speaker.
        
        Converts audio bytes (WAV/PCM) to AudioFrame for WebRTC transmission.
        """
        
        kind = "audio"
        
        def __init__(self, sample_rate: int = 16000, channels: int = 1):
            super().__init__()
            self._sample_rate = sample_rate
            self._channels = channels
            self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
            self._timestamp = 0
            self._stopped = False
            self._frame_size = 960  # 20ms at 48kHz (WebRTC standard)
        
        async def put_audio(self, audio_bytes: bytes) -> None:
            """Add audio data to the queue."""
            await self._queue.put(audio_bytes)
        
        async def end_stream(self) -> None:
            """Signal end of stream."""
            await self._queue.put(None)
        
        def stop(self) -> None:
            """Stop the track."""
            self._stopped = True
            super().stop()
        
        async def recv(self):
            """Receive next audio frame."""
            if self._stopped:
                raise MediaStreamTrack.MediaStreamError("Track stopped")
            
            # Get audio data from queue
            audio_data = await self._queue.get()
            if audio_data is None:
                raise MediaStreamTrack.MediaStreamError("End of stream")
            
            # Convert to AudioFrame
            # WebRTC expects 48kHz stereo, but we'll use 16kHz mono
            samples = len(audio_data) // 2  # 16-bit samples
            
            # Create AudioFrame
            frame = AudioFrame.from_ndarray(
                __import__('numpy').frombuffer(audio_data, dtype=__import__('numpy').int16).reshape(1, -1),
                format='s16',
                layout='mono'
            )
            frame.pts = self._timestamp
            frame.sample_rate = self._sample_rate
            frame.time_base = fractions.Fraction(1, self._sample_rate)
            
            self._timestamp += samples
            
            return frame
else:
    AudioStreamTrack = None


# ---------------------------------------------------------------------------
# Tool Definitions (for OpenAI function calling)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "移动机器人。x为前进/后退距离(米)，y为左右平移距离(米)。正值向前/左，负值向后/右。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "前进(+) / 后退(-) 距离，单位米"},
                    "y": {"type": "number", "description": "向左(+) / 向右(-) 平移距离，单位米"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn",
            "description": "原地转向。正值为左转/逆时针，负值为右转/顺时针。",
            "parameters": {
                "type": "object",
                "properties": {"degrees": {"type": "number", "description": "转向角度，正=左转，负=右转"}},
                "required": ["degrees"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stance",
            "description": "改变机器人姿态/站姿。可选: stand_up(站起)、balance_stand(平衡站立)、sit(坐下)、stand_down(趴下)、recovery_stand(恢复站立)、stop(停止)、back_stand(后腿站立)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pose": {
                        "type": "string",
                        "enum": [
                            "stand_up",
                            "stand_down",
                            "balance_stand",
                            "recovery_stand",
                            "sit",
                            "stop",
                            "back_stand",
                        ],
                        "description": "姿态名称",
                    }
                },
                "required": ["pose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trick",
            "description": "执行特技动作/社交手势。可选: hello(招手)、stretch(伸展)、wiggle_hips(扭腰)、scrape(刨地)、wallow(打滚)、show_heart(比心)、dance1/dance2(舞蹈)、front_flip(前空翻)、back_flip(后空翻)、left_flip(左空翻)、right_flip(右空翻)、handstand(倒立)、front_jump(前跳)、front_pounce(前扑)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": [
                            "hello",
                            "stretch",
                            "wiggle_hips",
                            "scrape",
                            "wallow",
                            "show_heart",
                            "dance1",
                            "dance2",
                            "front_flip",
                            "back_flip",
                            "left_flip",
                            "right_flip",
                            "handstand",
                            "front_jump",
                            "front_pounce",
                        ],
                        "description": "动作名称",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "led",
            "description": "设置机器人机身LED灯光颜色。可选: white(白)、red(红)、yellow(黄)、blue(蓝)、green(绿)、cyan(青)、purple(紫)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {
                        "type": "string",
                        "enum": [
                            "white",
                            "red",
                            "yellow",
                            "blue",
                            "green",
                            "cyan",
                            "purple",
                        ],
                        "description": "颜色名称",
                    },
                    "duration": {"type": "integer", "description": "持续时间(秒)"},
                },
                "required": ["color"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look",
            "description": "调整机器人身体倾斜角度。roll(横滚)/pitch(俯仰)/yaw(偏航)，单位弧度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "roll": {"type": "number", "description": "横滚角(弧度)"},
                    "pitch": {"type": "number", "description": "俯仰角(弧度)"},
                    "yaw": {"type": "number", "description": "偏航角(弧度)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_speed",
            "description": "设置行走速度等级。0=慢速、1=正常、2=快速。",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "enum": [0, 1, 2],
                        "description": "速度等级: 0=慢速, 1=正常, 2=快速",
                    },
                },
                "required": ["level"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Robot Controller Class
# ---------------------------------------------------------------------------

class RobotController:
    """
    Unitree Go2 Robot Controller.
    
    Manages WebRTC connection, state subscriptions, camera stream, and audio stream.
    """
    
    def __init__(self):
        self._conn: Optional[UnitreeWebRTCConnection] = None
        self._latest_frame_jpg: Optional[bytes] = None
        self._latest_frame_ts: float = 0.0
        self._sport_state: dict = {}
        self._low_state: dict = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Audio streaming
        self._audio_buffer: list[bytes] = []
        self._audio_buffer_lock = asyncio.Lock()
        self._audio_callbacks: list = []
        self._audio_track = None
    
    @property
    def connected(self) -> bool:
        """Check if robot is connected."""
        return self._conn is not None
    
    @property
    def camera_active(self) -> bool:
        """Check if camera is active."""
        return self._latest_frame_ts > 0 and (time.time() - self._latest_frame_ts) < 30.0
    
    async def connect(
        self,
        ip: Optional[str] = None,
        serial: Optional[str] = None,
        remote: bool = False,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Connect to the Go2 robot.
        
        Returns:
            (success, message)
        """
        if self._conn is not None:
            return False, "Already connected"
        
        try:
            if remote:
                self._conn = UnitreeWebRTCConnection(
                    WebRTCConnectionMethod.Remote,
                    serialNumber=serial,
                    username=username,
                    password=password,
                )
            elif serial and not ip:
                self._conn = UnitreeWebRTCConnection(
                    WebRTCConnectionMethod.LocalSTA, serialNumber=serial
                )
            elif ip:
                self._conn = UnitreeWebRTCConnection(
                    WebRTCConnectionMethod.LocalSTA, ip=ip
                )
            else:
                self._conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
            
            await self._conn.connect()
            self._setup_state()
            await self._start_camera()
            self._main_loop = asyncio.get_event_loop()
            
            return True, "Connected successfully"
            
        except Exception as e:
            # 完全清理连接状态
            if self._conn is not None:
                try:
                    await self._conn.disconnect()
                except Exception:
                    pass
            self._conn = None
            self._sport_state = {}
            self._low_state = {}
            self._latest_frame_jpg = None
            self._latest_frame_ts = 0.0
            logger.error(f"Connection error: {e}")
            return False, f"Connection failed: {str(e)}"
    
    async def disconnect(self) -> tuple[bool, str]:
        """Disconnect from the robot."""
        if self._conn is None:
            return False, "Not connected"
        
        try:
            await self._mcf("StopMove")
            await self._mcf("BalanceStand")
            await self._conn.disconnect()
            self._conn = None
            return True, "Disconnected successfully"
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
            return False, f"Disconnect failed: {str(e)}"
    
    def get_state(self) -> dict:
        """Get current robot state summary."""
        s, l = self._sport_state, self._low_state
        return {
            "position": s.get("position", [0, 0, 0]),
            "velocity": s.get("velocity", [0, 0, 0]),
            "rpy_rad": s.get("imu_state", {}).get("rpy", [0, 0, 0]),
            "body_height": s.get("body_height", 0),
            "gait": s.get("gait_type", 0),
            "battery_pct": l.get("bms_state", {}).get("soc", 0),
            "battery_v": l.get("bms_state", {}).get("voltage", 0),
            "range_obstacle": s.get("range_obstacle", [0, 0, 0, 0]),
        }
    
    def get_camera_frame(self, quality: int = 75) -> Optional[str]:
        """Get base64 JPEG of latest camera frame."""
        if not _CV2 or self._latest_frame_jpg is None:
            return None
        if self._latest_frame_ts > 0 and (time.time() - self._latest_frame_ts) > 30.0:
            return None
        if cv2 is None or np is None:
            return None
        try:
            img = cv2.imdecode(
                np.frombuffer(self._latest_frame_jpg, np.uint8), 
                cv2.IMREAD_COLOR
            )
            if img is None:
                return None
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None
        except Exception:
            return None
    
    def get_forward_obstacle(self) -> float:
        """Get forward obstacle distance in metres."""
        r = self._sport_state.get("range_obstacle", [0, 0, 0, 0])
        if isinstance(r, list) and len(r) > 0:
            return float(r[0])
        return 0.0
    
    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------
    
    def _code(self, resp: dict | None) -> int:
        """Extract status code from response."""
        if resp is None:
            return -1
        status = resp.get("data", {}).get("header", {}).get("status", {})
        if isinstance(status, dict):
            code = status.get("code", -1)
            if isinstance(code, int):
                return code
        return -1
    
    async def _mcf(
        self, name: str, parameter: dict | None = None, timeout: float = 5.0
    ) -> dict:
        """Send MCF command."""
        payload: dict = {"api_id": MCF_CMD[name]}
        if parameter:
            payload["parameter"] = parameter
        if self._conn is None or self._conn.datachannel is None:
            return {"ok": False, "code": -1}
        try:
            resp = await asyncio.wait_for(
                self._conn.datachannel.pub_sub.publish_request_new(MCF_TOPIC, payload),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"ok": False, "code": -2}
        code = self._code(resp)
        return {"ok": code == 0, "code": code}
    
    async def _mcf_raw(
        self, api_id: int, parameter: dict | None = None, timeout: float = 5.0
    ) -> dict:
        """Send raw MCF command by API ID."""
        payload: dict = {"api_id": api_id}
        if parameter:
            payload["parameter"] = parameter
        if self._conn is None or self._conn.datachannel is None:
            return {"ok": False, "code": -1}
        try:
            resp = await asyncio.wait_for(
                self._conn.datachannel.pub_sub.publish_request_new(MCF_TOPIC, payload),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"ok": False, "code": -2}
        code = self._code(resp)
        return {"ok": code == 0, "code": code}
    
    def _setup_state(self) -> None:
        """Subscribe to robot state topics."""
        def on_sport(m):
            self._sport_state = m.get("data", {})

        def on_low(m):
            self._low_state = m.get("data", {})

        if self._conn is not None and self._conn.datachannel is not None:
            self._conn.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LF_SPORT_MOD_STATE"], on_sport
            )
            self._conn.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LOW_STATE"], on_low
            )
    
    async def _start_camera(self) -> None:
        """Start camera stream."""
        ch = getattr(self._conn, "video", None)
        if ch is None:
            return

        async def on_track(track):
            asyncio.ensure_future(self._frame_loop(track))

        ch.add_track_callback(on_track)
        await asyncio.sleep(0.5)
        ch.switchVideoChannel(True)
    
    async def _frame_loop(self, track) -> None:
        """Background task to receive and process video frames."""
        consecutive_errors = 0
        while True:
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=10.0)
                if frame is None:
                    await asyncio.sleep(0.05)
                    continue
                if not _CV2 or cv2 is None:
                    continue
                img = frame.to_ndarray(format="bgr24")
                if img is None or img.size == 0:
                    continue
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    self._latest_frame_jpg = buf.tobytes()
                    self._latest_frame_ts = time.time()
                    consecutive_errors = 0
            except asyncio.TimeoutError:
                consecutive_errors += 1
                if consecutive_errors > 5:
                    self._latest_frame_ts = 0.0
                await asyncio.sleep(0.1)
            except Exception:
                consecutive_errors += 1
                await asyncio.sleep(0.1)
    
    # -----------------------------------------------------------------------
    # Audio Streaming Methods
    # -----------------------------------------------------------------------
    
    async def start_audio(self) -> bool:
        """
        Start audio stream from robot.
        
        Returns:
            True if audio stream started successfully
        """
        if self._conn is None:
            logger.warning("Cannot start audio: not connected")
            return False
        
        audio_ch = getattr(self._conn, "audio", None)
        if audio_ch is None:
            logger.warning("Audio channel not available")
            return False
        
        try:
            # Add audio frame callback
            audio_ch.add_track_callback(self._on_audio_frame)
            
            # Enable audio channel
            audio_ch.switchAudioChannel(True)
            logger.info("Audio stream started")
            return True
        except Exception as e:
            logger.error(f"Failed to start audio: {e}")
            return False
    
    async def stop_audio(self) -> None:
        """Stop audio stream."""
        audio_ch = getattr(self._conn, "audio", None)
        if audio_ch is not None:
            try:
                audio_ch.switchAudioChannel(False)
            except Exception:
                pass
        
        async with self._audio_buffer_lock:
            self._audio_buffer.clear()
        
        self._audio_callbacks.clear()
        logger.info("Audio stream stopped")
    
    async def _on_audio_frame(self, frame) -> None:
        """
        Handle incoming audio frame from robot.
        
        Args:
            frame: Audio frame from WebRTC (usually 16kHz, 16-bit, mono)
        """
        try:
            # Convert frame to bytes
            audio_data = frame.to_ndarray()
            if audio_data is not None:
                audio_bytes = audio_data.tobytes()
                
                # Store in buffer
                async with self._audio_buffer_lock:
                    self._audio_buffer.append(audio_bytes)
                    # Keep only last 10 seconds of audio (16kHz * 2 bytes * 10s = 320KB)
                    max_buffer_size = 16000 * 2 * 10
                    while sum(len(b) for b in self._audio_buffer) > max_buffer_size:
                        self._audio_buffer.pop(0)
                
                # Notify callbacks
                for callback in self._audio_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(audio_bytes)
                        else:
                            callback(audio_bytes)
                    except Exception as e:
                        logger.error(f"Audio callback error: {e}")
                        
        except Exception as e:
            logger.error(f"Audio frame processing error: {e}")
    
    def add_audio_callback(self, callback) -> None:
        """
        Add a callback for audio frames.
        
        Args:
            callback: Function to call with audio bytes (sync or async)
        """
        self._audio_callbacks.append(callback)
    
    def remove_audio_callback(self, callback) -> None:
        """Remove an audio callback."""
        if callback in self._audio_callbacks:
            self._audio_callbacks.remove(callback)
    
    async def get_audio_buffer(self, clear: bool = True) -> bytes:
        """
        Get accumulated audio buffer.
        
        Args:
            clear: Whether to clear the buffer after reading
        
        Returns:
            Combined audio bytes from buffer
        """
        async with self._audio_buffer_lock:
            audio_data = b"".join(self._audio_buffer)
            if clear:
                self._audio_buffer.clear()
            return audio_data
    
    def get_audio_buffer_sync(self, clear: bool = True) -> bytes:
        """
        Synchronous version of get_audio_buffer.
        
        Note: This should only be called from the main event loop.
        """
        # Create new event loop if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, just return current buffer
                audio_data = b"".join(self._audio_buffer)
                if clear:
                    self._audio_buffer.clear()
                return audio_data
            return loop.run_until_complete(self.get_audio_buffer(clear))
        except RuntimeError:
            return b""
    
    async def send_audio(self, wav_bytes: bytes) -> bool:
        """
        Send audio to robot speaker via WebRTC.
        
        Args:
            wav_bytes: WAV audio data to send (16kHz, 16-bit, mono recommended)
        
        Returns:
            True if audio was sent successfully
        """
        if not _AIORTC or AudioStreamTrack is None:
            logger.warning("aiortc not available, cannot send audio")
            return False
        
        if self._conn is None:
            logger.warning("Cannot send audio: not connected")
            return False
        
        try:
            # Parse WAV and extract PCM data
            import io
            import wave
            
            with io.BytesIO(wav_bytes) as buf:
                with wave.open(buf, 'rb') as wf:
                    sample_rate = wf.getframerate()
                    channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    pcm_data = wf.readframes(wf.getnframes())
            
            # Resample to 16kHz if needed
            if sample_rate != 16000 and np is not None:
                import scipy.signal
                samples = np.frombuffer(pcm_data, dtype=np.int16)
                num_samples = int(len(samples) * 16000 / sample_rate)
                pcm_data = scipy.signal.resample(samples, num_samples).astype(np.int16).tobytes()
                sample_rate = 16000
            
            # Convert to mono if stereo
            if channels == 2 and np is not None:
                samples = np.frombuffer(pcm_data, dtype=np.int16)
                mono = samples.reshape(-1, 2).mean(axis=1).astype(np.int16)
                pcm_data = mono.tobytes()
            
            # Create audio track
            track = AudioStreamTrack(sample_rate=sample_rate, channels=1)
            
            # Add track to WebRTC connection
            if hasattr(self._conn, 'pc') and self._conn.pc is not None:
                self._conn.pc.addTrack(track)
            
            # Stream audio data
            chunk_size = 3200  # 100ms at 16kHz
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i + chunk_size]
                await track.put_audio(chunk)
            
            await track.end_stream()
            logger.info("Audio sent to robot speaker")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")
            return False
    
    async def send_audio_stream(self, audio_generator, interrupt_event: asyncio.Event = None) -> bool:
        """
        Stream audio to robot speaker in real-time.
        
        Args:
            audio_generator: Async generator yielding audio chunks (bytes)
            interrupt_event: Event to signal interruption
        
        Returns:
            True if audio was sent successfully
        """
        if not _AIORTC or AudioStreamTrack is None:
            logger.warning("aiortc not available, cannot send audio")
            return False
        
        if self._conn is None:
            logger.warning("Cannot send audio: not connected")
            return False
        
        try:
            # Create audio track
            track = AudioStreamTrack(sample_rate=16000, channels=1)
            self._audio_track = track
            
            # Add track to WebRTC connection
            if hasattr(self._conn, 'pc') and self._conn.pc is not None:
                self._conn.pc.addTrack(track)
            
            # Stream audio chunks
            async for chunk in audio_generator:
                # Check for interruption
                if interrupt_event and interrupt_event.is_set():
                    track.stop()
                    logger.info("Audio stream interrupted")
                    break
                
                # Handle WAV header if present
                if chunk.startswith(b'RIFF'):
                    # Skip WAV header (44 bytes)
                    chunk = chunk[44:] if len(chunk) > 44 else b''
                
                if chunk:
                    await track.put_audio(chunk)
            
            if not (interrupt_event and interrupt_event.is_set()):
                await track.end_stream()
            
            logger.info("Audio stream completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stream audio: {e}")
            return False
        finally:
            self._audio_track = None
    
    def stop_audio_output(self) -> None:
        """Stop current audio output."""
        if self._audio_track is not None:
            self._audio_track.stop()
            self._audio_track = None
            logger.info("Audio output stopped")
    
    @property
    def audio_active(self) -> bool:
        """Check if audio stream is active."""
        audio_ch = getattr(self._conn, "audio", None)
        return audio_ch is not None and len(self._audio_callbacks) > 0
    
    async def _velocity_loop(
        self, vx: float, vy: float, vyaw: float, duration_s: float
    ) -> bool | str:
        """Velocity control loop with obstacle detection."""
        ticks = max(1, int(duration_s * MOVE_TICK_HZ))
        ok = True
        stopped_early = False
        for _ in range(ticks):
            if vx > 0:
                dist = self.get_forward_obstacle()
                if 0 < dist < OBSTACLE_STOP_M:
                    stopped_early = True
                    break
            r = await self._mcf("Move", {"x": vx, "y": vy, "z": vyaw})
            if not r.get("ok", False):
                ok = False
            await asyncio.sleep(MOVE_TICK_S)
        await self._mcf("Move", {"x": 0, "y": 0, "z": 0})
        if stopped_early:
            return "obstacle"
        return ok


# ---------------------------------------------------------------------------
# Global controller instance
# ---------------------------------------------------------------------------

_controller = RobotController()


def get_controller() -> RobotController:
    """Get the global robot controller instance."""
    return _controller


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

async def run_tool(name: str, args: dict) -> str:
    """
    Execute a tool by name with given arguments.
    
    Args:
        name: Tool name (move, turn, stance, trick, led, look, set_speed)
        args: Tool arguments dictionary
    
    Returns:
        Result message string
    """
    c = get_controller()
    
    if name == "move":
        x = float(args.get("x", 0))
        y = float(args.get("y", 0))
        errors = []
        
        if abs(x) > 0.01:
            dur = abs(x) / WALK_SPEED
            result = await c._velocity_loop(WALK_SPEED * (1 if x > 0 else -1), 0, 0, dur)
            if result == "obstacle":
                return f"move(x={x:.2f}m) → stopped: obstacle detected within {OBSTACLE_STOP_M}m"
            if not result:
                errors.append("x")
            await asyncio.sleep(0.2)
        
        if abs(y) > 0.01:
            dur = abs(y) / STRAFE_SPEED
            ok = await c._velocity_loop(0, STRAFE_SPEED * (1 if y > 0 else -1), 0, dur)
            if not ok:
                errors.append("y")
        
        status = "ok" if not errors else f"errors on {errors}"
        return f"move(x={x:.2f}m, y={y:.2f}m) → {status}"

    elif name == "turn":
        deg = float(args.get("degrees", 0))
        rad = abs(deg) * 3.14159 / 180.0
        duration = rad / YAW_RATE
        sign = 1.0 if deg > 0 else -1.0
        ok = await c._velocity_loop(0, 0, YAW_RATE * sign, duration)
        status = "ok" if ok else "error"
        return f"turn({deg:.1f}°, {duration:.1f}s) → {status}"

    elif name == "stance":
        pose_map = {
            "stand_up": ("StandUp", None),
            "stand_down": ("StandDown", None),
            "balance_stand": ("BalanceStand", None),
            "recovery_stand": ("RecoveryStand", None),
            "sit": ("Sit", None),
            "stop": ("StopMove", None),
            "back_stand": ("BackStand", None),
        }
        pose = args.get("pose", "balance_stand")
        cmd, param = pose_map.get(pose, ("BalanceStand", None))
        r = await c._mcf(cmd, param)
        return f"{pose} → {'ok' if r['ok'] else 'error'}"

    elif name == "trick":
        trick_map = {
            "hello": lambda: c._mcf("Hello", timeout=10.0),
            "stretch": lambda: c._mcf("Stretch", timeout=10.0),
            "wiggle_hips": lambda: c._mcf_raw(1033, timeout=10.0),
            "scrape": lambda: c._mcf("Scrape", timeout=10.0),
            "wallow": lambda: c._mcf_raw(1021, timeout=10.0),
            "show_heart": lambda: c._mcf("Heart", timeout=10.0),
            "dance1": lambda: c._mcf("Dance1", timeout=15.0),
            "dance2": lambda: c._mcf("Dance2", timeout=15.0),
            "front_flip": lambda: c._mcf("FrontFlip", timeout=15.0),
            "back_flip": lambda: c._mcf("BackFlip", timeout=15.0),
            "left_flip": lambda: c._mcf("LeftFlip", timeout=15.0),
            "right_flip": lambda: c._mcf("RightFlip", timeout=15.0),
            "handstand": lambda: c._mcf("Handstand", timeout=10.0),
            "front_jump": lambda: c._mcf("FrontJump", timeout=10.0),
            "front_pounce": lambda: c._mcf("FrontPounce", timeout=10.0),
        }
        t = args.get("name", "hello")
        fn = trick_map.get(t)
        if fn is None:
            return f"unknown trick: {t}"
        r = await fn()
        return f"{t} → {'ok' if r['ok'] else 'error'}"

    elif name == "led":
        color = args.get("color", "white")
        duration = int(args.get("duration", 3))
        if c._conn is None or c._conn.datachannel is None:
            return "error: no connection"
        resp = await c._conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["VUI"],
            {"api_id": 1007, "parameter": {"color": color, "time": duration}},
        )
        ok = c._code(resp) == 0
        return f"led({color}, {duration}s) → {'ok' if ok else 'error'}"

    elif name == "look":
        roll = float(args.get("roll", 0))
        pitch = float(args.get("pitch", 0))
        yaw = float(args.get("yaw", 0))
        r = await c._mcf("Euler", {"x": roll, "y": pitch, "z": yaw})
        return f"look(roll={roll:.2f}, pitch={pitch:.2f}, yaw={yaw:.2f}) → {'ok' if r['ok'] else 'error'}"

    elif name == "set_speed":
        level = int(args.get("level", 1))
        r = await c._mcf("SpeedLevel", {"data": level})
        return f"set_speed({level}) → {'ok' if r['ok'] else 'error'}"

    else:
        return f"unknown tool: {name}"


async def set_gait(gait: str) -> tuple[bool, str]:
    """Set walking gait."""
    c = get_controller()
    cmd_name = _GAIT_MAP.get(gait)
    if cmd_name is None:
        return False, f"Unknown gait: {gait}"
    r = await c._mcf(cmd_name)
    return r["ok"], f"Gait: {gait}"


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "RobotController",
    "get_controller",
    "TOOLS",
    "run_tool",
    "set_gait",
    "_GAIT_MAP",
]