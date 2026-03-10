"""
voice_assistant.py — Voice Conversation Manager for Go2 Robot

Integrates VAD, ASR, LLM, and TTS for natural voice conversation with the robot.

Features:
    - Voice Activity Detection (VAD) for speech start/end
    - Automatic Speech Recognition (ASR) via DashScope
    - LLM-powered conversation with tool calling
    - Text-to-Speech (TTS) for robot responses
    - Interruption support (stop TTS when user speaks)

Usage:
    from voice_assistant import VoiceAssistant
    
    assistant = VoiceAssistant()
    await assistant.start()
    # ... conversation happens ...
    await assistant.stop()
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Callable, AsyncGenerator

from app.vad import VoiceActivityDetector, VADState
from app.models import (
    audio_to_text,
    process_chat,
    text_to_speech,
    get_client,
    OPENAI_MODEL,
)
from app.robot_go2 import get_controller, TOOLS, run_tool

logger = logging.getLogger("go2-voice")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------

class AssistantState(Enum):
    """Voice assistant state."""
    IDLE = "idle"           # Not active
    LISTENING = "listening" # Waiting for user speech
    PROCESSING = "processing"  # ASR + LLM processing
    SPEAKING = "speaking"   # TTS playing


# ---------------------------------------------------------------------------
# Voice Assistant
# ---------------------------------------------------------------------------

class VoiceAssistant:
    """
    Voice conversation manager for Go2 robot.
    
    Manages the complete voice interaction loop:
    1. Listen for user speech (VAD)
    2. Transcribe speech (ASR)
    3. Process with LLM and execute tools
    4. Speak response (TTS)
    5. Support interruption during TTS
    """
    
    def __init__(
        self,
        model: str = None,
        silence_threshold_ms: int = 600,
        min_speech_ms: int = 300,
        include_image: bool = True,
    ):
        """
        Initialize voice assistant.
        
        Args:
            model: LLM model to use
            silence_threshold_ms: Silence duration to consider speech ended
            min_speech_ms: Minimum speech duration to process
            include_image: Whether to include camera frame in LLM context
        """
        self._model = model or OPENAI_MODEL
        self._include_image = include_image
        
        # State
        self._state = AssistantState.IDLE
        self._running = False
        self._tasks: list[asyncio.Task] = []
        
        # VAD
        self._vad = VoiceActivityDetector(
            sample_rate=SAMPLE_RATE,
            silence_threshold_ms=silence_threshold_ms,
            min_speech_ms=min_speech_ms,
        )
        
        # Audio buffer for current utterance
        self._audio_buffer: list[bytes] = []
        self._audio_buffer_lock = asyncio.Lock()
        
        # Interruption
        self._interrupt_event = asyncio.Event()
        
        # TTS audio queue
        self._tts_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        
        # Callbacks
        self._on_state_change: Optional[Callable[[AssistantState], None]] = None
        self._on_transcript: Optional[Callable[[str], None]] = None
        self._on_response: Optional[Callable[[str], None]] = None
        self._on_tool_call: Optional[Callable[[str, dict, str], None]] = None
        
        # Chat history
        self._chat_history: list[dict] = []
        
        # Controller reference
        self._controller = get_controller()
    
    @property
    def state(self) -> AssistantState:
        """Current assistant state."""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """Check if assistant is running."""
        return self._running
    
    # -----------------------------------------------------------------------
    # Callback Registration
    # -----------------------------------------------------------------------
    
    def on_state_change(self, callback: Callable[[AssistantState], None]) -> None:
        """Register callback for state changes."""
        self._on_state_change = callback
    
    def on_transcript(self, callback: Callable[[str], None]) -> None:
        """Register callback for ASR transcript."""
        self._on_transcript = callback
    
    def on_response(self, callback: Callable[[str], None]) -> None:
        """Register callback for LLM response."""
        self._on_response = callback
    
    def on_tool_call(self, callback: Callable[[str, dict, str], None]) -> None:
        """Register callback for tool calls (name, args, result)."""
        self._on_tool_call = callback
    
    # -----------------------------------------------------------------------
    # State Management
    # -----------------------------------------------------------------------
    
    async def _set_state(self, state: AssistantState) -> None:
        """Set state and notify callback."""
        if self._state != state:
            old_state = self._state
            self._state = state
            logger.info(f"State: {old_state.value} → {state.value}")
            if self._on_state_change:
                try:
                    self._on_state_change(state)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
    
    # -----------------------------------------------------------------------
    # Start / Stop
    # -----------------------------------------------------------------------
    
    async def start(self) -> bool:
        """
        Start voice assistant.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Voice assistant already running")
            return False
        
        if not self._controller.connected:
            logger.error("Robot not connected")
            return False
        
        if get_client() is None:
            logger.error("LLM client not initialized")
            return False
        
        self._running = True
        self._interrupt_event.clear()
        
        # Start audio stream from robot
        success = await self._controller.start_audio()
        if not success:
            logger.error("Failed to start audio stream")
            self._running = False
            return False
        
        # Register audio callback
        self._controller.add_audio_callback(self._on_audio_frame)
        
        # Setup VAD callbacks
        self._vad.on_speech_start(self._on_speech_start)
        self._vad.on_speech_end(self._on_speech_end)
        
        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._audio_processing_loop()),
            asyncio.create_task(self._tts_playback_loop()),
        ]
        
        await self._set_state(AssistantState.LISTENING)
        logger.info("Voice assistant started")
        return True
    
    async def stop(self) -> None:
        """Stop voice assistant."""
        if not self._running:
            return
        
        self._running = False
        self._interrupt_event.set()
        
        # Stop audio stream
        await self._controller.stop_audio()
        self._controller.remove_audio_callback(self._on_audio_frame)
        
        # Cancel tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        # Clear queues
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        await self._set_state(AssistantState.IDLE)
        logger.info("Voice assistant stopped")
    
    def interrupt(self) -> None:
        """Interrupt current TTS playback."""
        if self._state == AssistantState.SPEAKING:
            logger.info("Interrupting TTS")
            self._interrupt_event.set()
    
    # -----------------------------------------------------------------------
    # Audio Processing
    # -----------------------------------------------------------------------
    
    def _on_audio_frame(self, audio_bytes: bytes) -> None:
        """Handle incoming audio frame from robot."""
        if not self._running:
            return
        
        # Process through VAD
        self._vad.process(audio_bytes)
        
        # If speaking (VAD detected speech), buffer audio
        if self._vad.is_speaking:
            self._audio_buffer.append(audio_bytes)
    
    def _on_speech_start(self) -> None:
        """VAD callback: speech started."""
        logger.debug("Speech started")
        
        # If currently speaking, interrupt
        if self._state == AssistantState.SPEAKING:
            self.interrupt()
        
        # Clear audio buffer for new utterance
        self._audio_buffer.clear()
    
    def _on_speech_end(self, audio: bytes) -> None:
        """VAD callback: speech ended."""
        logger.debug(f"Speech ended: {len(audio)} bytes")
        
        # This is called by VAD when speech ends
        # The audio is already accumulated in _audio_buffer
        # We'll process it in the main loop
    
    async def _audio_processing_loop(self) -> None:
        """Main loop for processing speech."""
        last_speech_time = 0.0
        
        while self._running:
            try:
                # Check if VAD detected speech end
                if self._vad.speech_ended and self._state == AssistantState.LISTENING:
                    # Get the speech audio
                    async with self._audio_buffer_lock:
                        audio_data = b"".join(self._audio_buffer)
                        self._audio_buffer.clear()
                    
                    if len(audio_data) > 0:
                        # Process the speech
                        await self._process_speech(audio_data)
                    last_speech_time = time.time()
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.01)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Audio processing error: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_speech(self, audio_bytes: bytes) -> None:
        """
        Process speech audio: ASR → LLM → TTS.
        
        Args:
            audio_bytes: Speech audio (16kHz, 16-bit, mono)
        """
        await self._set_state(AssistantState.PROCESSING)
        
        try:
            # 1. ASR: Speech to text
            logger.info("Running ASR...")
            import base64
            audio_b64 = base64.b64encode(audio_bytes).decode()
            audio_data_uri = f"data:audio/wav;base64,{audio_b64}"
            
            try:
                transcript = audio_to_text(audio_data_uri, language="zh")
            except Exception as e:
                logger.error(f"ASR error: {e}")
                transcript = ""
            
            if not transcript:
                logger.warning("ASR returned empty transcript")
                await self._set_state(AssistantState.LISTENING)
                return
            
            logger.info(f"Transcript: {transcript}")
            if self._on_transcript:
                self._on_transcript(transcript)
            
            # 2. LLM: Process with context
            logger.info("Processing with LLM...")
            response, tool_calls, robot_state = await process_chat(
                message=transcript,
                model=self._model,
                include_image=self._include_image,
                history=self._chat_history,
                get_state=self._controller.get_state,
                get_camera_frame=self._controller.get_camera_frame,
                tools=TOOLS,
                run_tool=run_tool,
            )
            
            # Update chat history
            self._chat_history.append({"role": "user", "content": transcript})
            self._chat_history.append({"role": "assistant", "content": response})
            if len(self._chat_history) > 20:
                self._chat_history = self._chat_history[-20:]
            
            # Notify callbacks
            if self._on_response:
                self._on_response(response)
            
            for tc in tool_calls:
                if self._on_tool_call:
                    self._on_tool_call(tc["tool"], tc["arguments"], tc["result"])
            
            # 3. TTS: Speak the response
            if response:
                await self._speak(response)
            
            # Return to listening
            await self._set_state(AssistantState.LISTENING)
            
        except Exception as e:
            logger.error(f"Speech processing error: {e}")
            await self._set_state(AssistantState.LISTENING)
    
    # -----------------------------------------------------------------------
    # TTS Playback
    # -----------------------------------------------------------------------
    
    async def _speak(self, text: str) -> None:
        """
        Speak text using TTS.
        
        Supports interruption via _interrupt_event.
        
        Args:
            text: Text to speak
        """
        await self._set_state(AssistantState.SPEAKING)
        self._interrupt_event.clear()
        
        try:
            logger.info(f"Speaking: {text[:50]}...")
            
            # Generate TTS audio chunks
            audio_chunks = []
            try:
                for chunk in text_to_speech(text, stream=True):
                    if self._interrupt_event.is_set():
                        logger.info("TTS interrupted")
                        break
                    audio_chunks.append(chunk)
                    await self._tts_queue.put(chunk)
            except Exception as e:
                logger.error(f"TTS error: {e}")
            
            # Signal end of TTS
            await self._tts_queue.put(None)
            
            # Wait for playback to complete (if not interrupted)
            if not self._interrupt_event.is_set():
                # Wait for queue to be consumed
                while not self._tts_queue.empty() and not self._interrupt_event.is_set():
                    await asyncio.sleep(0.05)
            
        except asyncio.CancelledError:
            logger.info("TTS cancelled")
        except Exception as e:
            logger.error(f"Speak error: {e}")
    
    async def _tts_playback_loop(self) -> None:
        """Background loop for playing TTS audio to robot speaker."""
        while self._running:
            try:
                # Collect audio chunks for streaming
                chunks = []
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            self._tts_queue.get(),
                            timeout=0.1
                        )
                        if chunk is None:
                            break
                        chunks.append(chunk)
                    except asyncio.TimeoutError:
                        if chunks:
                            break
                        continue
                
                if not chunks:
                    continue
                
                # Check for interruption before sending
                if self._interrupt_event.is_set():
                    # Clear remaining queue
                    while not self._tts_queue.empty():
                        try:
                            self._tts_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    continue
                
                # Create async generator for audio chunks
                async def audio_generator():
                    for chunk in chunks:
                        if self._interrupt_event.is_set():
                            break
                        yield chunk
                
                # Stream audio to robot speaker
                try:
                    await self._controller.send_audio_stream(
                        audio_generator(),
                        interrupt_event=self._interrupt_event
                    )
                except Exception as e:
                    logger.error(f"Failed to send audio to robot: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTS playback error: {e}")
    
    # -----------------------------------------------------------------------
    # Utility Methods
    # -----------------------------------------------------------------------
    
    def clear_history(self) -> None:
        """Clear chat history."""
        self._chat_history.clear()
    
    async def speak_text(self, text: str) -> None:
        """
        Speak text directly (without LLM processing).
        
        Args:
            text: Text to speak
        """
        if not self._running:
            return
        await self._speak(text)


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_assistant: Optional[VoiceAssistant] = None


def get_voice_assistant() -> VoiceAssistant:
    """Get or create the global voice assistant instance."""
    global _assistant
    if _assistant is None:
        _assistant = VoiceAssistant()
    return _assistant


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "VoiceAssistant",
    "AssistantState",
    "get_voice_assistant",
]