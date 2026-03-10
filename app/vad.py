"""
vad.py — Voice Activity Detection for Go2 Robot

Detects speech start/end using WebRTC VAD or Silero VAD.

Usage:
    from vad import VoiceActivityDetector
    
    vad = VoiceActivityDetector()
    
    # Process audio frames
    is_speech = vad.process(audio_bytes)
    
    # Check state
    if vad.speech_started:
        print("User started speaking")
    if vad.speech_ended:
        print("User stopped speaking")
        audio = vad.get_speech_audio()
"""

import logging
import struct
import time
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger("go2-vad")

# Try to import VAD libraries
_VAD_AVAILABLE = False
try:
    import webrtcvad
    _VAD_AVAILABLE = True
    _VAD_TYPE = "webrtc"
except ImportError:
    pass

if not _VAD_AVAILABLE:
    try:
        import torch
        _VAD_AVAILABLE = True
        _VAD_TYPE = "silero"
    except ImportError:
        pass


class VADState(Enum):
    """Voice activity detection state."""
    SILENCE = "silence"
    SPEECH = "speech"
    POSSIBLE_SPEECH = "possible_speech"
    POSSIBLE_SILENCE = "possible_silence"


class VoiceActivityDetector:
    """
    Voice Activity Detector.
    
    Detects when user starts and stops speaking.
    Supports WebRTC VAD (lightweight) or Silero VAD (more accurate).
    
    Audio format: 16kHz, 16-bit, mono (default for Go2 WebRTC)
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 3,
        speech_threshold: float = 0.5,
        silence_threshold_ms: int = 500,
        min_speech_ms: int = 300,
    ):
        """
        Initialize VAD.
        
        Args:
            sample_rate: Audio sample rate (default: 16000)
            frame_duration_ms: Frame duration in ms (10, 20, or 30 for WebRTC)
            aggressiveness: WebRTC VAD aggressiveness (0-3, higher = more aggressive)
            speech_threshold: Silero VAD speech probability threshold
            silence_threshold_ms: Silence duration to consider speech ended
            min_speech_ms: Minimum speech duration to consider valid
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.aggressiveness = aggressiveness
        self.speech_threshold = speech_threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.min_speech_ms = min_speech_ms
        
        # Calculate frame size
        self.frame_size = int(sample_rate * frame_duration_ms / 1000) * 2  # 2 bytes per sample
        
        # Initialize VAD
        self._vad = None
        self._vad_type = None
        
        if _VAD_AVAILABLE:
            if _VAD_TYPE == "webrtc":
                self._vad = webrtcvad.Vad(aggressiveness)
                self._vad_type = "webrtc"
                logger.info(f"WebRTC VAD initialized (aggressiveness={aggressiveness})")
            elif _VAD_TYPE == "silero":
                # Silero VAD will be loaded on first use
                self._vad_type = "silero"
                logger.info("Silero VAD will be loaded on first use")
        else:
            logger.warning("No VAD library available. Using energy-based detection.")
            self._vad_type = "energy"
        
        # State tracking
        self._state = VADState.SILENCE
        self._speech_frames: list[bytes] = []
        self._silence_start: Optional[float] = None
        self._speech_start: Optional[float] = None
        self._last_speech_time: Optional[float] = None
        
        # Callbacks
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
    
    @property
    def state(self) -> VADState:
        """Current VAD state."""
        return self._state
    
    @property
    def is_speaking(self) -> bool:
        """Check if currently detecting speech."""
        return self._state == VADState.SPEECH
    
    @property
    def speech_started(self) -> bool:
        """Check if speech just started (transition from silence)."""
        return self._state == VADState.SPEECH and self._silence_start is None
    
    @property
    def speech_ended(self) -> bool:
        """Check if speech just ended (silence after speech)."""
        return self._state == VADState.SILENCE and len(self._speech_frames) > 0
    
    def on_speech_start(self, callback: Callable) -> None:
        """Register callback for speech start event."""
        self._on_speech_start = callback
    
    def on_speech_end(self, callback: Callable) -> None:
        """Register callback for speech end event."""
        self._on_speech_end = callback
    
    def process(self, audio_bytes: bytes) -> bool:
        """
        Process an audio frame.
        
        Args:
            audio_bytes: Audio frame bytes (16-bit PCM)
        
        Returns:
            True if speech detected in this frame
        """
        is_speech = self._detect_speech(audio_bytes)
        now = time.time()
        
        if is_speech:
            self._last_speech_time = now
            
            if self._state == VADState.SILENCE:
                # Possible speech start
                self._state = VADState.POSSIBLE_SPEECH
                self._speech_start = now
                self._speech_frames = [audio_bytes]
                
            elif self._state == VADState.POSSIBLE_SPEECH:
                # Continue accumulating
                self._speech_frames.append(audio_bytes)
                
                # Check if we have enough speech to confirm
                speech_duration = (now - self._speech_start) * 1000 if self._speech_start else 0
                if speech_duration >= self.min_speech_ms:
                    self._state = VADState.SPEECH
                    self._silence_start = None
                    if self._on_speech_start:
                        try:
                            self._on_speech_start()
                        except Exception as e:
                            logger.error(f"Speech start callback error: {e}")
                    
            elif self._state == VADState.SPEECH:
                # Continue speech
                self._speech_frames.append(audio_bytes)
                
            elif self._state == VADState.POSSIBLE_SILENCE:
                # Speech resumed
                self._state = VADState.SPEECH
                self._silence_start = None
                self._speech_frames.append(audio_bytes)
        
        else:
            # No speech in this frame
            if self._state == VADState.SPEECH:
                # Possible speech end
                self._state = VADState.POSSIBLE_SILENCE
                self._silence_start = now
                
            elif self._state == VADState.POSSIBLE_SILENCE:
                # Check if silence duration exceeded threshold
                silence_duration = (now - self._silence_start) * 1000 if self._silence_start else 0
                if silence_duration >= self.silence_threshold_ms:
                    # Speech ended
                    self._state = VADState.SILENCE
                    if self._on_speech_end:
                        try:
                            audio = self.get_speech_audio()
                            self._on_speech_end(audio)
                        except Exception as e:
                            logger.error(f"Speech end callback error: {e}")
                    self._speech_frames = []
                    self._silence_start = None
                    self._speech_start = None
                    
            elif self._state == VADState.POSSIBLE_SPEECH:
                # False alarm, not enough speech
                self._state = VADState.SILENCE
                self._speech_frames = []
                self._speech_start = None
        
        return is_speech
    
    def _detect_speech(self, audio_bytes: bytes) -> bool:
        """Detect if audio frame contains speech."""
        if len(audio_bytes) < self.frame_size:
            return False
        
        if self._vad_type == "webrtc" and self._vad:
            return self._detect_webrtc(audio_bytes)
        elif self._vad_type == "silero":
            return self._detect_silero(audio_bytes)
        else:
            return self._detect_energy(audio_bytes)
    
    def _detect_webrtc(self, audio_bytes: bytes) -> bool:
        """WebRTC VAD detection."""
        try:
            # WebRTC VAD expects specific frame sizes
            frame = audio_bytes[:self.frame_size]
            return self._vad.is_speech(frame, self.sample_rate)
        except Exception as e:
            logger.error(f"WebRTC VAD error: {e}")
            return False
    
    def _detect_silero(self, audio_bytes: bytes) -> bool:
        """Silero VAD detection (lazy load)."""
        try:
            import torch
            
            # Load model on first use
            if self._vad is None:
                self._vad, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    trusted=True
                )
            
            # Convert bytes to float tensor
            audio_int16 = struct.unpack(f"{len(audio_bytes)//2}h", audio_bytes)
            audio_float = [x / 32768.0 for x in audio_int16]
            audio_tensor = torch.tensor(audio_float)
            
            # Get speech probability
            speech_prob = self._vad(audio_tensor, self.sample_rate).item()
            return speech_prob >= self.speech_threshold
            
        except Exception as e:
            logger.error(f"Silero VAD error: {e}")
            return False
    
    def _detect_energy(self, audio_bytes: bytes) -> bool:
        """Simple energy-based speech detection (fallback)."""
        try:
            # Calculate RMS energy
            audio_int16 = struct.unpack(f"{len(audio_bytes)//2}h", audio_bytes)
            if not audio_int16:
                return False
            
            rms = (sum(x*x for x in audio_int16) / len(audio_int16)) ** 0.5
            
            # Threshold: 500 seems reasonable for 16-bit audio
            # You may need to adjust this based on your audio source
            return rms > 500
            
        except Exception as e:
            logger.error(f"Energy detection error: {e}")
            return False
    
    def get_speech_audio(self) -> bytes:
        """Get accumulated speech audio."""
        return b"".join(self._speech_frames)
    
    def reset(self) -> None:
        """Reset VAD state."""
        self._state = VADState.SILENCE
        self._speech_frames = []
        self._silence_start = None
        self._speech_start = None
        self._last_speech_time = None


class StreamingVAD:
    """
    Streaming VAD wrapper for easier integration.
    
    Provides a simple interface for processing audio streams
    with automatic speech detection.
    """
    
    def __init__(
        self,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable[[bytes], None]] = None,
        **vad_kwargs
    ):
        """
        Initialize streaming VAD.
        
        Args:
            on_speech_start: Callback for speech start
            on_speech_end: Callback for speech end (receives audio bytes)
            **vad_kwargs: Additional VAD parameters
        """
        self._vad = VoiceActivityDetector(**vad_kwargs)
        
        if on_speech_start:
            self._vad.on_speech_start(on_speech_start)
        if on_speech_end:
            self._vad.on_speech_end(on_speech_end)
    
    def process(self, audio_bytes: bytes) -> bool:
        """Process audio frame. Returns True if speech detected."""
        return self._vad.process(audio_bytes)
    
    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        return self._vad.is_speaking
    
    def reset(self) -> None:
        """Reset state."""
        self._vad.reset()


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def create_vad(
    on_speech_start: Optional[Callable] = None,
    on_speech_end: Optional[Callable[[bytes], None]] = None,
    silence_threshold_ms: int = 500,
) -> VoiceActivityDetector:
    """
    Create a VAD with common settings.
    
    Args:
        on_speech_start: Callback for speech start
        on_speech_end: Callback for speech end
        silence_threshold_ms: Silence duration to consider speech ended
    
    Returns:
        Configured VoiceActivityDetector
    """
    vad = VoiceActivityDetector(silence_threshold_ms=silence_threshold_ms)
    
    if on_speech_start:
        vad.on_speech_start(on_speech_start)
    if on_speech_end:
        vad.on_speech_end(on_speech_end)
    
    return vad


__all__ = [
    "VoiceActivityDetector",
    "StreamingVAD",
    "VADState",
    "create_vad",
]