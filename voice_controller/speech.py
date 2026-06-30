"""Audio capture, voice activity detection, and speech recognition.

Provides a ContinuousListener that orchestrates microphone capture, VAD,
Whisper transcription, and delivers recognized text via a callback.
"""

import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample a 1-D numpy array from *orig_sr* to *target_sr* via linear
    interpolation.  Fast enough for short speech segments (< 10 s)."""
    if orig_sr == target_sr:
        return audio
    duration = len(audio) / orig_sr
    n_out = max(1, round(duration * target_sr))
    x_in = np.arange(len(audio), dtype=np.float64)
    x_out = np.linspace(0, len(audio) - 1, n_out, dtype=np.float64)
    return np.interp(x_out, x_in, audio).astype(np.float32)


# ---------------------------------------------------------------------------
# AudioCapture
# ---------------------------------------------------------------------------

class AudioCapture:
    """Stream audio from the microphone using sounddevice.

    Parameters
    ----------
    sample_rate:
        Desired output sample rate (e.g. 16000).  If the hardware does not
        support this rate the stream is opened at the device's native rate and
        resampled automatically.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[int] = None,
        block_size: int = 512,
    ) -> None:
        self._output_rate = sample_rate
        self._device = device
        self._block_size = block_size
        self._native_rate: int = sample_rate  # may change after start()
        self._stream = None
        self._buffer: deque[np.ndarray] = deque()
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        """Open and start the audio input stream."""
        import sounddevice as sd

        if self._device is None:
            try:
                self._device = sd.default.device[0]
            except Exception:
                pass

        # Validate device
        try:
            device_info = sd.query_devices(self._device, kind="input")
        except (sd.PortAudioError, ValueError) as e:
            devices = sd.query_devices()
            input_devices = [
                f"  [{d['index']}] {d['name']} (max {int(d['max_input_channels'])} ch)"
                for d in devices
                if d["max_input_channels"] > 0
            ]
            if input_devices:
                msg = (
                    f"Cannot open input device {self._device}: {e}\n\n"
                    f"Available input devices:\n"
                    + "\n".join(input_devices)
                )
            else:
                msg = (
                    f"No microphone found.\n"
                    f"Audio device error: {e}"
                )
            raise AudioError(msg) from e

        # Prefer the requested rate; fall back to the device's native rate
        native_rate = int(device_info["default_samplerate"])
        # Scale block_size so that after resampling we get ~512 samples
        # (32 ms at 16 kHz), which is what Silero VAD expects.
        capture_block = max(64, round(self._block_size * native_rate / self._output_rate))

        try:
            self._stream = sd.InputStream(
                device=self._device,
                samplerate=self._output_rate,
                channels=1,
                dtype="float32",
                blocksize=capture_block,
                callback=self._audio_callback,
            )
            self._native_rate = self._output_rate
        except sd.PortAudioError:
            log.info(
                "Device does not support %d Hz, using native %d Hz (resampling).",
                self._output_rate,
                native_rate,
            )
            self._stream = sd.InputStream(
                device=self._device,
                samplerate=native_rate,
                channels=1,
                dtype="float32",
                blocksize=capture_block,
                callback=self._audio_callback,
            )
            self._native_rate = native_rate

        self._stream.start()
        self._running = True
        log.info(
            "Microphone: %s (capture %d Hz → output %d Hz)",
            device_info["name"],
            self._native_rate,
            self._output_rate,
        )

    def stop(self) -> None:
        """Stop and close the audio stream."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: int,
    ) -> None:
        """Called by sounddevice for each audio block."""
        if status:
            log.warning("Audio stream status: %s", status)
        with self._lock:
            self._buffer.append(indata.copy().flatten())

    def read(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Read the next available audio chunk resampled to the output rate."""
        with self._lock:
            if self._buffer:
                chunk = self._buffer.popleft()
                if self._native_rate != self._output_rate:
                    chunk = _resample(chunk, self._native_rate, self._output_rate)
                return chunk
        return None

    @property
    def sample_rate(self) -> int:
        return self._output_rate


# ---------------------------------------------------------------------------
# VoiceActivityDetector
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    """Voice Activity Detection using Silero VAD."""

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000) -> None:
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._model = None

    def load(self) -> None:
        """Load the Silero VAD model."""
        from silero_vad import load_silero_vad

        self._model = load_silero_vad(onnx=False)

    def is_speech(self, audio: np.ndarray) -> bool:
        """Return True if the audio chunk contains speech."""
        if self._model is None:
            raise RuntimeError("VAD model not loaded. Call load() first.")

        import torch

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.flatten()

        tensor = torch.from_numpy(audio)
        prob = self._model(tensor, self._sample_rate)
        return prob.item() >= self._threshold


# ---------------------------------------------------------------------------
# SpeechRecognizer
# ---------------------------------------------------------------------------

class SpeechRecognizer:
    """Speech-to-text using faster-whisper."""

    def __init__(self, model_size: str = "tiny", language: str = "en") -> None:
        self._model_size = model_size
        self._language = language
        self._whisper = None

    def load(self) -> None:
        """Load the Whisper model (downloads on first run)."""
        from faster_whisper import WhisperModel

        log.info("Loading Whisper model '%s' (this may take a moment)...",
                 self._model_size)
        try:
            self._whisper = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )
        except Exception as e:
            raise RecognitionError(
                f"Failed to load Whisper model '{self._model_size}': {e}"
            ) from e

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe a numpy audio array and return the text."""
        if self._whisper is None:
            raise RuntimeError("Whisper model not loaded. Call load() first.")

        if audio.size == 0:
            return ""

        # faster-whisper expects float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        try:
            segments, _info = self._whisper.transcribe(
                audio,
                language=self._language,
                beam_size=5,
                vad_filter=False,  # We use our own VAD
            )
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            return " ".join(texts)
        except Exception as e:
            log.warning("Whisper transcription error: %s", e, exc_info=True)
            return ""


# ---------------------------------------------------------------------------
# ContinuousListener
# ---------------------------------------------------------------------------

class ContinuousListener:
    """Continuously listen, detect speech segments, transcribe, and callback."""

    def __init__(
        self,
        audio_capture: AudioCapture,
        vad: VoiceActivityDetector,
        recognizer: SpeechRecognizer,
        silence_chunks: int = 15,
    ) -> None:
        """
        Parameters
        ----------
        silence_chunks:
            Number of consecutive silent chunks (32ms each) before a speech
            segment is considered complete.  15 chunks ≈ 480ms of silence.
        """
        self._capture = audio_capture
        self._vad = vad
        self._recognizer = recognizer
        self._silence_chunks = silence_chunks
        self._running = False
        self._callback: Optional[Callable[[str], None]] = None

    def start(self, callback: Callable[[str], None]) -> None:
        """Begin continuous listening. Blocks until stop() is called."""
        self._callback = callback
        self._running = True

        speech_buffer: list[np.ndarray] = []
        silent_count = 0
        in_speech = False

        self._capture.start()

        try:
            while self._running:
                chunk = self._capture.read(timeout=0.05)
                if chunk is None:
                    time.sleep(0.01)
                    continue

                # Silero VAD works best with exactly 512 samples at 16kHz
                # If the chunk is a different size, pad or slice
                if chunk.size < 512:
                    chunk = np.pad(chunk, (0, 512 - chunk.size))
                elif chunk.size > 512:
                    chunk = chunk[:512]

                is_speech = self._vad.is_speech(chunk)

                if is_speech:
                    speech_buffer.append(chunk.copy())
                    silent_count = 0
                    if not in_speech:
                        in_speech = True
                        log.debug("Speech started")
                elif in_speech:
                    # Transition from speech to silence
                    speech_buffer.append(chunk.copy())
                    silent_count += 1

                    if silent_count >= self._silence_chunks:
                        # Speech segment complete
                        audio = np.concatenate(speech_buffer)
                        speech_buffer.clear()
                        silent_count = 0
                        in_speech = False

                        if audio.size > 0:
                            self._process_audio(audio)

        except AudioError:
            raise
        except Exception as e:
            log.error("Listener error: %s", e, exc_info=True)
            raise
        finally:
            self._capture.stop()

    def stop(self) -> None:
        """Signal the listener to stop."""
        self._running = False

    def _process_audio(self, audio: np.ndarray) -> None:
        """Transcribe audio and invoke the callback with the result."""
        text = self._recognizer.transcribe(
            audio,
            self._capture.sample_rate,
        )
        if text and self._callback and self._running:
            try:
                self._callback(text)
            except Exception:
                log.exception("Callback error")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AudioError(Exception):
    """Raised when audio capture fails."""


class RecognitionError(Exception):
    """Raised when speech recognition fails."""
