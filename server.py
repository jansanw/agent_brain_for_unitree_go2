"""
server.py — FastAPI REST API for Unitree Go2 Robot Control

Environment:
    OPENAI_API_KEY / DASHSCOPE_API_KEY - API key for LLM
    OPENAI_BASE_URL - Default: https://dashscope.aliyuncs.com/compatible-mode/v1
    OPENAI_MODEL - Default: qwen-plus

Run:
    python server.py --ip 192.168.8.181
    uvicorn server:app --host 0.0.0.0 --port 8080
"""

import argparse
import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.robot_go2 import get_controller, TOOLS, run_tool, set_gait
from app.models import (
    init_client, get_client,
    process_chat, audio_to_text,
    OPENAI_MODEL,
)
from app.voice_assistant import VoiceAssistant, AssistantState, get_voice_assistant

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("go2-server")


class _IgnoreDataChannelMessages(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Received message on data channel" in msg:
            return False
        if "/robot/state" in msg or "/robot/camera" in msg:
            return False
        return True


logging.getLogger().addFilter(_IgnoreDataChannelMessages())
uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(_IgnoreDataChannelMessages())

for lib in ("aiortc", "aioice", "asyncio"):
    logging.getLogger(lib).setLevel(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - initialize LLM client
    try:
        init_client()
        logger.info("LLM client initialized")
    except ValueError as e:
        logger.warning(f"LLM client not initialized: {e}")

    # Auto-connect if args provided
    if hasattr(app.state, "args") and not app.state.args.no_connect:
        c = get_controller()
        args = app.state.args
        logger.info(f"Connecting to robot at {args.ip}...")
        success, message = await c.connect(
            ip=args.ip,
            serial=args.serial,
            remote=args.remote,
            username=args.username,
            password=args.password,
        )
        if success:
            logger.info("Connected to robot!")
        else:
            logger.warning(f"Auto-connect failed: {message}")

    yield

    # Shutdown
    c = get_controller()
    if c.connected:
        await c.disconnect()
        logger.info("Disconnected from robot")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    ip: Optional[str] = None
    serial: Optional[str] = None
    remote: bool = False
    username: Optional[str] = None
    password: Optional[str] = None


class MoveRequest(BaseModel):
    x: float = Field(default=0, description="Forward (+) / back (-) metres")
    y: float = Field(default=0, description="Left (+) / right (-) metres")


class TurnRequest(BaseModel):
    degrees: float = Field(..., description="Degrees to turn (positive=left/CCW)")


class StanceRequest(BaseModel):
    pose: str = Field(..., description="stand_up, stand_down, balance_stand, recovery_stand, sit, stop, back_stand")


class TrickRequest(BaseModel):
    name: str = Field(..., description="hello, stretch, wiggle_hips, dance1, front_flip, etc.")


class LedRequest(BaseModel):
    color: str = Field(..., description="white, red, yellow, blue, green, cyan, purple")
    duration: int = Field(default=3, description="Duration in seconds")


class LookRequest(BaseModel):
    roll: float = 0
    pitch: float = 0
    yaw: float = 0


class SpeedRequest(BaseModel):
    level: int = Field(..., ge=0, le=2, description="0=slow, 1=normal, 2=fast")


class GaitRequest(BaseModel):
    gait: str = Field(..., description="economic, static, trot_run, free_walk, etc.")


class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    image: bool = True


class ChatResponse(BaseModel):
    response: str
    tool_calls: list = []
    robot_state: dict = {}


class RobotState(BaseModel):
    position: list = [0.0, 0.0, 0.0]
    velocity: list = [0.0, 0.0, 0.0]
    rpy_rad: list = [0.0, 0.0, 0.0]
    body_height: float = 0.0
    gait: int = 0
    battery_pct: int = 0
    battery_v: float = 0.0
    range_obstacle: list = [0.0, 0.0, 0.0, 0.0]


class CameraResponse(BaseModel):
    image: Optional[str] = None
    timestamp: float = 0.0
    format: str = "base64_jpeg"


class StatusResponse(BaseModel):
    success: bool
    message: str
    code: int = 0


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Go2 Robot Control API",
    description="REST API for Unitree Go2 robot with OpenAI-powered chat",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages WebSocket connections for real-time data streaming."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections[:]:  # Copy to avoid modification during iteration
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Chat History
# ---------------------------------------------------------------------------

_chat_history: list[dict] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    c = get_controller()
    return {
        "status": "healthy",
        "robot_connected": c.connected,
        "camera_active": c.camera_active,
        "openai_configured": get_client() is not None,
    }


# --- Robot Connection ---

@app.post("/robot/connect", response_model=StatusResponse)
async def robot_connect(request: ConnectRequest):
    c = get_controller()
    success, message = await c.connect(
        ip=request.ip,
        serial=request.serial,
        remote=request.remote,
        username=request.username,
        password=request.password,
    )
    return StatusResponse(success=success, message=message, code=0 if success else -1)


@app.post("/robot/disconnect", response_model=StatusResponse)
async def robot_disconnect():
    c = get_controller()
    success, message = await c.disconnect()
    return StatusResponse(success=success, message=message, code=0 if success else -1)


# --- Robot State ---

@app.get("/robot/state", response_model=RobotState)
async def get_robot_state():
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    return RobotState(**c.get_state())


@app.get("/robot/camera", response_model=CameraResponse)
async def get_camera_image(quality: int = 75):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    return CameraResponse(image=c.get_camera_frame(quality), timestamp=c._latest_frame_ts)


# --- Movement ---

@app.post("/robot/move", response_model=StatusResponse)
async def robot_move(request: MoveRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("move", {"x": request.x, "y": request.y})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


@app.post("/robot/turn", response_model=StatusResponse)
async def robot_turn(request: TurnRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("turn", {"degrees": request.degrees})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


@app.post("/robot/stop", response_model=StatusResponse)
async def robot_stop():
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("stance", {"pose": "stop"})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- Stance ---

@app.post("/robot/stance", response_model=StatusResponse)
async def robot_stance(request: StanceRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("stance", {"pose": request.pose})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- Tricks ---

@app.post("/robot/trick", response_model=StatusResponse)
async def robot_trick(request: TrickRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("trick", {"name": request.name})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- LED ---

@app.post("/robot/led", response_model=StatusResponse)
async def robot_led(request: LedRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("led", {"color": request.color, "duration": request.duration})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- Look ---

@app.post("/robot/look", response_model=StatusResponse)
async def robot_look(request: LookRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("look", {"roll": request.roll, "pitch": request.pitch, "yaw": request.yaw})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- Speed ---

@app.post("/robot/speed", response_model=StatusResponse)
async def robot_speed(request: SpeedRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    result = await run_tool("set_speed", {"level": request.level})
    return StatusResponse(success="ok" in result, message=result, code=0 if "ok" in result else -1)


# --- Gait ---

@app.post("/robot/gait", response_model=StatusResponse)
async def robot_gait(request: GaitRequest):
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    success, message = await set_gait(request.gait)
    return StatusResponse(success=success, message=message, code=0 if success else -1)


# --- Chat ---

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global _chat_history
    c = get_controller()

    if not c.connected:
        raise HTTPException(503, "Robot not connected")

    if get_client() is None:
        raise HTTPException(500, "LLM client not initialized. Set OPENAI_API_KEY.")

    model = request.model or OPENAI_MODEL

    response, tool_calls, robot_state = await process_chat(
        message=request.message,
        model=model,
        include_image=request.image,
        history=_chat_history,
        get_state=c.get_state,
        get_camera_frame=c.get_camera_frame,
        tools=TOOLS,
        run_tool=run_tool,
    )

    _chat_history.append({"role": "user", "content": request.message})
    _chat_history.append({"role": "assistant", "content": response})
    if len(_chat_history) > 20:
        _chat_history = _chat_history[-20:]

    return ChatResponse(response=response, tool_calls=tool_calls, robot_state=robot_state)


@app.delete("/chat/history")
async def clear_chat_history():
    global _chat_history
    _chat_history = []
    return {"message": "Chat history cleared"}


# --- ASR (Speech Recognition) ---

@app.post("/asr")
async def recognize_audio(file: UploadFile = File(...), language: str = "zh"):
    """
    Speech recognition endpoint. Supports wav, mp3 formats.
    Returns {"text": "recognized text"}
    """
    if not file.filename:
        raise HTTPException(400, "No file provided")

    if get_client() is None:
        raise HTTPException(500, "LLM client not initialized. Set OPENAI_API_KEY.")

    content = await file.read()
    base64_str = base64.b64encode(content).decode()
    mime_type = file.content_type or "audio/wav"
    audio_data_uri = f"data:{mime_type};base64,{base64_str}"

    text = audio_to_text(audio_data_uri, language)
    logger.info(f"ASR result: {text}")
    return {"text": text}


# --- Voice Assistant ---

class VoiceStatusResponse(BaseModel):
    running: bool
    state: str
    message: str = ""


class VoiceStartRequest(BaseModel):
    model: Optional[str] = None
    silence_threshold_ms: int = 600
    min_speech_ms: int = 300
    include_image: bool = True


# Global voice assistant instance
_voice_assistant: Optional[VoiceAssistant] = None


@app.post("/voice/start", response_model=VoiceStatusResponse)
async def voice_start(request: VoiceStartRequest = VoiceStartRequest()):
    """Start voice conversation mode."""
    global _voice_assistant
    
    c = get_controller()
    if not c.connected:
        raise HTTPException(503, "Robot not connected")
    
    if get_client() is None:
        raise HTTPException(500, "LLM client not initialized. Set OPENAI_API_KEY.")
    
    if _voice_assistant is not None and _voice_assistant.is_running:
        return VoiceStatusResponse(running=True, state=_voice_assistant.state.value, message="Already running")
    
    # Create new voice assistant
    _voice_assistant = VoiceAssistant(
        model=request.model,
        silence_threshold_ms=request.silence_threshold_ms,
        min_speech_ms=request.min_speech_ms,
        include_image=request.include_image,
    )
    
    # Set up callbacks for WebSocket broadcasting
    def on_state_change(state: AssistantState):
        asyncio.create_task(ws_manager.broadcast({
            "type": "voice_state",
            "data": state.value
        }))
    
    def on_transcript(text: str):
        asyncio.create_task(ws_manager.broadcast({
            "type": "voice_transcript",
            "data": text
        }))
    
    def on_response(text: str):
        asyncio.create_task(ws_manager.broadcast({
            "type": "voice_response",
            "data": text
        }))
    
    def on_tool_call(tool: str, args: dict, result: str):
        asyncio.create_task(ws_manager.broadcast({
            "type": "voice_tool_call",
            "data": {"tool": tool, "arguments": args, "result": result}
        }))
    
    _voice_assistant.on_state_change(on_state_change)
    _voice_assistant.on_transcript(on_transcript)
    _voice_assistant.on_response(on_response)
    _voice_assistant.on_tool_call(on_tool_call)
    
    success = await _voice_assistant.start()
    if not success:
        raise HTTPException(500, "Failed to start voice assistant")
    
    return VoiceStatusResponse(running=True, state=_voice_assistant.state.value, message="Voice assistant started")


@app.post("/voice/stop", response_model=VoiceStatusResponse)
async def voice_stop():
    """Stop voice conversation mode."""
    global _voice_assistant
    
    if _voice_assistant is None or not _voice_assistant.is_running:
        return VoiceStatusResponse(running=False, state="idle", message="Not running")
    
    await _voice_assistant.stop()
    state = _voice_assistant.state.value
    _voice_assistant = None
    
    return VoiceStatusResponse(running=False, state=state, message="Voice assistant stopped")


@app.get("/voice/status", response_model=VoiceStatusResponse)
async def voice_status():
    """Get voice assistant status."""
    global _voice_assistant
    
    if _voice_assistant is None or not _voice_assistant.is_running:
        return VoiceStatusResponse(running=False, state="idle", message="Not running")
    
    return VoiceStatusResponse(running=True, state=_voice_assistant.state.value)


@app.post("/voice/interrupt", response_model=VoiceStatusResponse)
async def voice_interrupt():
    """Interrupt current TTS playback."""
    global _voice_assistant
    
    if _voice_assistant is None or not _voice_assistant.is_running:
        return VoiceStatusResponse(running=False, state="idle", message="Not running")
    
    _voice_assistant.interrupt()
    
    return VoiceStatusResponse(running=True, state=_voice_assistant.state.value, message="Interrupted")


@app.delete("/voice/history")
async def voice_clear_history():
    """Clear voice assistant chat history."""
    global _voice_assistant
    
    if _voice_assistant is not None:
        _voice_assistant.clear_history()
    
    return {"message": "Voice history cleared"}


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time robot state and camera streaming.
    
    Sends JSON messages:
    - {"type": "state", "data": {...}} - Robot state
    - {"type": "camera", "data": "base64..."} - Camera frame
    - {"type": "connected", "data": bool} - Robot connection status
    """
    await ws_manager.connect(websocket)
    c = get_controller()
    
    try:
        # Send initial connection status
        await websocket.send_json({"type": "connected", "data": c.connected})
        
        while True:
            if not c.connected:
                # Robot not connected, wait and retry
                await websocket.send_json({"type": "connected", "data": False})
                await asyncio.sleep(1)
                continue
            
            # Send robot state
            try:
                state = c.get_state()
                await websocket.send_json({"type": "state", "data": state})
            except Exception as e:
                logger.debug(f"Error getting state: {e}")
            
            # Send camera frame
            try:
                frame = c.get_camera_frame(quality=60)
                if frame:
                    await websocket.send_json({"type": "camera", "data": frame})
            except Exception as e:
                logger.debug(f"Error getting camera: {e}")
            
            await asyncio.sleep(0.4)  # ~20 FPS
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Go2 Robot Control FastAPI Server")
    parser.add_argument("--ip", default="192.168.8.181", help="Robot IP address")
    parser.add_argument("--serial", default=None, help="Robot serial number")
    parser.add_argument("--remote", action="store_true", help="Use remote connection")
    parser.add_argument("--username", default=None, help="Remote username")
    parser.add_argument("--password", default=None, help="Remote password")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--no-connect", action="store_false", help="Don't auto-connect on startup")
    return parser.parse_args()


if __name__ == "__main__":
    import uvicorn

    args = parse_args()
    app.state.args = args
    uvicorn.run(app, host=args.host, port=args.port)