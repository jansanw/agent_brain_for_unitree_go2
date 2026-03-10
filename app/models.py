"""
models.py — LLM Model Integration for Go2 Robot Control

Provides unified interface for:
- Chat processing with tool calling
- Speech recognition (ASR)
- Text-to-speech (TTS)

Environment:
    OPENAI_API_KEY / DASHSCOPE_API_KEY - API key for LLM
    OPENAI_BASE_URL - Default: https://dashscope.aliyuncs.com/compatible-mode/v1
    OPENAI_MODEL - Default: qwen-plus
    ASR_MODEL - Default: qwen3-asr-flash
    TTS_MODEL - Default: qwen3-tts-flash
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Callable, Generator

from dotenv import load_dotenv
from openai import OpenAI
import base64
import dashscope

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger("go2-models")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENAI_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "glm-5")
ASR_MODEL = os.environ.get("ASR_MODEL", "qwen3-asr-flash")
TTS_MODEL = os.environ.get("TTS_MODEL", "qwen3-tts-flash")
TTS_VOICE = os.environ.get("TTS_VOICE", "Cherry")

# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

def _load_prompt(name: str) -> str:
    """Load system prompt from SYSTEM_PROMPT.md file."""
    prompt_file = Path(__file__).parent / "prompts.md"
    if not prompt_file.exists():
        logger.warning(f"prompts.md not found, using default prompts")
        return _DEFAULT_PROMPTS.get(name, "")
    
    content = prompt_file.read_text(encoding="utf-8")
    
    # Extract prompt between ``` blocks after the header
    lines = content.split("\n")
    in_section = False
    in_code_block = False
    prompt_lines = []
    
    for line in lines:
        if f"## {name}" in line:
            in_section = True
            continue
        if in_section:
            if line.startswith("```"):
                if in_code_block:
                    break
                in_code_block = True
                continue
            if in_code_block:
                prompt_lines.append(line)
    
    return "\n".join(prompt_lines).strip()


_DEFAULT_PROMPTS = {
    "Chat System Prompt": """You are controlling a Unitree Go2 robot dog via tool calls.
Execute natural language instructions decisively and efficiently.

RULES:
- Issue ONE tool call at a time. After each call, you receive a fresh camera frame.
- move(x, y) — x=forward/back metres, y=left/right strafe.
- turn(degrees) — positive=left/CCW, negative=right/CW.
- Good increments: turn(45-90°) to scan, move(x=0.5-1.5) for walking.
- If robot looks fallen (rpy > 0.5 rad), use stance(recovery_stand).
- Describe what you see after each step. Stop when task is done.""",
    
    "ASR Context": """你是语音助手，将语音转写成文字。专注于转写，不要添加无关内容。
机器人控制热词：站起、趴下、坐下、平衡、恢复、停止、前进、后退、左转、右转、招手、
伸展、扭腰、打滚、比心、跳舞、空翻、倒立、前跳、灯光、速度、慢速、快速、经济步态、小跑。""",
}

# Load prompts
SYSTEM_PROMPT = _load_prompt("Chat System Prompt") or _DEFAULT_PROMPTS["Chat System Prompt"]
ASR_CONTEXT = _load_prompt("ASR Context") or _DEFAULT_PROMPTS["ASR Context"]


# ---------------------------------------------------------------------------
# Client Management
# ---------------------------------------------------------------------------

_client: Optional[OpenAI] = None


def init_client(api_key: Optional[str] = None) -> OpenAI:
    """Initialize OpenAI client with API key."""
    global _client
    
    key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise ValueError("No API key provided. Set OPENAI_API_KEY or DASHSCOPE_API_KEY.")
    
    _client = OpenAI(api_key=key, base_url=OPENAI_BASE_URL)
    logger.info(f"OpenAI client initialized: {OPENAI_BASE_URL}")
    return _client


def get_client() -> Optional[OpenAI]:
    """Get the current OpenAI client, initializing if needed."""
    global _client
    
    if _client is None:
        try:
            init_client()
        except ValueError:
            return None
    
    return _client


# ---------------------------------------------------------------------------
# Chat Processing
# ---------------------------------------------------------------------------

async def process_chat(
    message: str,
    model: Optional[str] = None,
    include_image: bool = True,
    history: Optional[list[dict]] = None,
    get_state: Optional[Callable] = None,
    get_camera_frame: Optional[Callable] = None,
    tools: Optional[list] = None,
    run_tool: Optional[Callable] = None,
    max_iterations: int = 10,
) -> tuple[str, list, dict]:
    """
    Process a chat message with tool calling support.
    
    Args:
        message: User message
        model: Model to use (default: OPENAI_MODEL)
        include_image: Whether to include camera frame
        history: Chat history
        get_state: Function to get robot state
        get_camera_frame: Function to get camera frame (base64)
        tools: Available tools for LLM
        run_tool: Async function to run a tool
        max_iterations: Maximum tool calling iterations
    
    Returns:
        Tuple of (response_text, tool_calls, robot_state)
    """
    client = get_client()
    if client is None:
        raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")
    
    model = model or OPENAI_MODEL
    history = history or []
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    
    # Build user content with robot state
    state = get_state() if get_state else {}
    user_content = [{"type": "text", "text": f"{message}\n\n[Robot state: {json.dumps(state)}]"}]
    
    # Add camera frame if available
    if include_image and get_camera_frame:
        frame_b64 = get_camera_frame()
        if frame_b64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}", "detail": "low"}
            })
            user_content[0]["text"] += "\n[Camera frame attached]"
        else:
            user_content[0]["text"] += "\n[No camera available]"
    
    messages.append({"role": "user", "content": user_content})
    
    all_tool_calls = []
    
    for iteration in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else "none",
                max_tokens=1000,
                extra_body={"enable_thinking": False},
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API error: {e}") from e
        
        msg = response.choices[0].message
        messages.append(msg)
        
        # No tool calls, return response
        if not msg.tool_calls:
            final_state = get_state() if get_state else {}
            return msg.content or "", all_tool_calls, final_state
        
        # Process tool calls
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            logger.info(f"Tool: {fn_name}({fn_args})")
            
            if run_tool:
                result = await run_tool(fn_name, fn_args)
            else:
                result = "No tool runner available"
            
            logger.info(f"Result: {result}")
            all_tool_calls.append({"tool": fn_name, "arguments": fn_args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        
        # Add fresh observation after tool calls
        fresh_state = get_state() if get_state else {}
        fresh_frame = get_camera_frame() if get_camera_frame else None
        obs = [{"type": "text", "text": f"[After action — Robot state: {json.dumps(fresh_state)}]"}]
        if fresh_frame:
            obs.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{fresh_frame}", "detail": "low"}})
        messages.append({"role": "user", "content": obs})
    
    final_state = get_state() if get_state else {}
    return "Max iterations reached", all_tool_calls, final_state


# ---------------------------------------------------------------------------
# Speech Recognition (ASR)
# ---------------------------------------------------------------------------

def audio_to_text(audio_base64_data_uri: str, language: str = "zh") -> str:
    """
    Convert audio to text using ASR API.
    
    Args:
        audio_base64_data_uri: Audio data as base64 data URI (data:audio/wav;base64,...)
        language: Language code (default: zh)
    
    Returns:
        Transcribed text
    """
    client = get_client()
    if client is None:
        raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")
    
    completion = client.chat.completions.create(
        model=ASR_MODEL,
        messages=[
            {"role": "system", "content": [{"text": ASR_CONTEXT}]},
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": audio_base64_data_uri}}]},
        ],
        stream=False,
        extra_body={
            "asr_options": {
                "language": language,
                "enable_itn": False
            }
        }
    )
    
    return completion.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Text-to-Speech (TTS)
# ---------------------------------------------------------------------------

def text_to_speech(
    text: str,
    voice: Optional[str] = None,
    language_type: str = "Chinese",
    stream: bool = True,
) -> Generator[bytes, None, None]:
    """
    Convert text to speech using TTS API.
    
    Args:
        text: Text to convert
        voice: Voice name (default: TTS_VOICE / Cherry)
        language_type: Language type (Chinese, English, etc.)
        stream: Whether to stream audio chunks
    
    Yields:
        Audio data chunks (WAV bytes)
    """
    
    client = get_client()
    if client is None:
        raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")
    
    voice = voice or TTS_VOICE
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    
    response = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=TTS_MODEL,
        text=text,
        voice=voice,
        language_type=language_type,
        stream=stream
    )
    
    for chunk in response:
        if chunk.output is not None:
            audio = chunk.output.audio
            if audio.data is not None:
                wav_bytes = base64.b64decode(audio.data)
                yield wav_bytes


def text_to_speech_sync(text: str, voice: Optional[str] = None, language_type: str = "Chinese") -> bytes:
    """
    Convert text to speech and return complete audio data.
    
    Args:
        text: Text to convert
        voice: Voice name (default: TTS_VOICE / Cherry)
        language_type: Language type
    
    Returns:
        Complete WAV audio bytes
    """
    audio_chunks = list(text_to_speech(text, voice, language_type, stream=True))
    return b"".join(audio_chunks)


def play_audio(text: str, voice: Optional[str] = None, language_type: str = "Chinese"):
    """
    Convert text to speech and play through speakers.
    
    Requires pyaudio to be installed.
    
    Args:
        text: Text to speak
        voice: Voice name
        language_type: Language type
    """
    import pyaudio
    
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=24000,
        output=True
    )
    
    try:
        for wav_bytes in text_to_speech(text, voice, language_type):
            import numpy as np
            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
            stream.write(audio_np.tobytes())
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()