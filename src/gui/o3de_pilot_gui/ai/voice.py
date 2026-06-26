# O3DE Pilot AI - Voice Module
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Voice AI — tiered STT / TTS with local (free) and cloud (BYOK) providers.

Architecture
============
Voice is an *optional layer on top of text AI*.  Everything works without it.

STT (Speech-to-Text) providers
------------------------------
- **local** — Whisper.cpp via the ``faster-whisper`` Python binding.
  Downloads a ~150 MB model on first use.  Fully offline.
- **google_free** — Google free web STT (no key, rate-limited).
- **deepgram** — Deepgram Nova-2 streaming API (BYOK).
- **whisper_api** — OpenAI Whisper API (BYOK, uses ``ai.api_keys.openai``).

TTS (Text-to-Speech) providers
------------------------------
- **local** — OS-native synthesis: ``pyttsx3`` (SAPI / NSSpeech / espeak).
- **elevenlabs** — ElevenLabs streaming TTS (BYOK).
- **openai_tts** — OpenAI TTS API (BYOK).

Configuration keys (in ``~/.o3de/pilot/config.yaml``)::

    ai:
      voice:
        enabled: true
        stt_provider: local          # local | google_free | deepgram | whisper_api
        tts_provider: local          # local | elevenlabs | openai_tts
        stt_model: base              # whisper model size (local only)
        tts_voice: ''                # provider-specific voice ID
        auto_listen: false           # auto-listen after TTS finishes
"""

from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


# ── Data types ──────────────────────────────────────────────────────

@dataclass
class VoiceConfig:
    """Voice subsystem configuration."""

    enabled: bool = False
    stt_provider: str = "local"
    tts_provider: str = "local"
    stt_model: str = "base"
    tts_voice: str = ""
    auto_listen: bool = False

    @classmethod
    def from_config(cls) -> "VoiceConfig":
        """Load from the global o3de-pilot config."""
        try:
            from o3de_cli.core.config import get_config

            cfg = get_config()
            voice = cfg.get("ai.voice", {})
            if not isinstance(voice, dict):
                voice = {}
            return cls(
                enabled=str(voice.get("enabled", "false")).lower() == "true",
                stt_provider=voice.get("stt_provider", "local"),
                tts_provider=voice.get("tts_provider", "local"),
                stt_model=voice.get("stt_model", "base"),
                tts_voice=voice.get("tts_voice", ""),
                auto_listen=str(voice.get("auto_listen", "false")).lower() == "true",
            )
        except Exception:
            return cls()

    def save(self) -> None:
        """Persist current values to the global config."""
        from o3de_cli.core.config import get_config

        cfg = get_config()
        cfg.set("ai.voice.enabled", str(self.enabled).lower())
        cfg.set("ai.voice.stt_provider", self.stt_provider)
        cfg.set("ai.voice.tts_provider", self.tts_provider)
        cfg.set("ai.voice.stt_model", self.stt_model)
        cfg.set("ai.voice.tts_voice", self.tts_voice)
        cfg.set("ai.voice.auto_listen", str(self.auto_listen).lower())
        cfg.save()


# ── STT base class ──────────────────────────────────────────────────

class STTProvider(ABC):
    """Speech-to-text provider interface."""

    @abstractmethod
    def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        """Transcribe raw PCM-16 mono audio to text."""

    def is_available(self) -> bool:
        """Return True if this provider can be used right now."""
        return True


class TTSProvider(ABC):
    """Text-to-speech provider interface."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Synthesize *text* and return WAV audio bytes."""

    def is_available(self) -> bool:
        """Return True if this provider can be used right now."""
        return True


# ── Local STT (faster-whisper) ──────────────────────────────────────

class WhisperLocalSTT(STTProvider):
    """Offline STT using faster-whisper (CTranslate2 Whisper)."""

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size, device="cpu", compute_type="int8"
            )
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed.  Run:\n"
                "  pip install faster-whisper"
            )

    def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        self._load_model()
        # Write raw PCM to an in-memory WAV for faster-whisper
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        buf.seek(0)
        segments, _info = self._model.transcribe(buf, language="en")
        return " ".join(seg.text.strip() for seg in segments).strip()

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except ImportError:
            return False


# ── Google Free STT ─────────────────────────────────────────────────

class GoogleFreeSTT(STTProvider):
    """Google free web speech API (no key, rate-limited)."""

    def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        try:
            import speech_recognition as sr
        except ImportError:
            raise RuntimeError(
                "speech_recognition not installed.  Run:\n"
                "  pip install SpeechRecognition"
            )
        recogniser = sr.Recognizer()
        audio = sr.AudioData(audio_data, sample_rate, 2)  # 16-bit = 2 bytes
        try:
            return recogniser.recognize_google(audio)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            raise RuntimeError(f"Google STT error: {exc}") from exc

    def is_available(self) -> bool:
        try:
            import speech_recognition  # noqa: F401

            return True
        except ImportError:
            return False


# ── Deepgram STT (BYOK) ────────────────────────────────────────────

class DeepgramSTT(STTProvider):
    """Deepgram Nova-2 STT (BYOK)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        import httpx

        # Build WAV in memory
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        wav_bytes = buf.getvalue()

        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {self._api_key}",
                "Content-Type": "audio/wav",
            },
            params={"model": "nova-2", "language": "en"},
            content=wav_bytes,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        try:
            return data["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, IndexError):
            return ""

    def is_available(self) -> bool:
        return bool(self._api_key)


# ── OpenAI Whisper API STT (BYOK) ──────────────────────────────────

class WhisperAPISTT(STTProvider):
    """OpenAI Whisper API STT (BYOK)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def transcribe(self, audio_data: bytes, *, sample_rate: int = 16000) -> str:
        import httpx

        # Build WAV in memory
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        wav_bytes = buf.getvalue()

        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": "whisper-1"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("text", "")

    def is_available(self) -> bool:
        return bool(self._api_key)


# ── Local TTS (pyttsx3 / OS-native) ────────────────────────────────

class LocalTTS(TTSProvider):
    """OS-native TTS via pyttsx3 (SAPI / NSSpeech / espeak)."""

    def __init__(self, voice_id: str = "") -> None:
        self._voice_id = voice_id

    def synthesize(self, text: str) -> bytes:
        try:
            import pyttsx3
        except ImportError:
            raise RuntimeError(
                "pyttsx3 not installed.  Run:\n  pip install pyttsx3"
            )
        engine = pyttsx3.init()
        if self._voice_id:
            engine.setProperty("voice", self._voice_id)

        # pyttsx3 can save to file; we capture to a temp WAV
        import tempfile
        import os

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def is_available(self) -> bool:
        try:
            import pyttsx3  # noqa: F401

            return True
        except ImportError:
            return False


# ── ElevenLabs TTS (BYOK) ──────────────────────────────────────────

class ElevenLabsTTS(TTSProvider):
    """ElevenLabs streaming TTS (BYOK)."""

    _DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel"

    def __init__(self, api_key: str, voice_id: str = "") -> None:
        self._api_key = api_key
        self._voice_id = voice_id or self._DEFAULT_VOICE_ID

    def synthesize(self, text: str) -> bytes:
        import httpx

        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}",
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/wav",
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.content

    def is_available(self) -> bool:
        return bool(self._api_key)


# ── OpenAI TTS (BYOK) ──────────────────────────────────────────────

class OpenAITTS(TTSProvider):
    """OpenAI TTS API (BYOK)."""

    def __init__(self, api_key: str, voice: str = "alloy") -> None:
        self._api_key = api_key
        self._voice = voice

    def synthesize(self, text: str) -> bytes:
        import httpx

        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": self._voice,
                "response_format": "wav",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.content

    def is_available(self) -> bool:
        return bool(self._api_key)


# ── Audio capture ───────────────────────────────────────────────────

class AudioCapture:
    """Cross-platform microphone capture to raw PCM-16 mono.

    Uses ``pyaudio`` (PortAudio binding) which works on Windows, macOS,
    and Linux.  Falls back to ``sounddevice`` if pyaudio is unavailable.
    """

    RATE = 16000
    CHANNELS = 1
    CHUNK = 1024
    FORMAT_WIDTH = 2  # 16-bit

    def __init__(
        self,
        *,
        on_level: Callable[[float], None] | None = None,
        max_seconds: int = 30,
        silence_timeout: float = 2.0,
        silence_threshold: float = 0.01,
    ) -> None:
        self._on_level = on_level
        self._max_seconds = max_seconds
        self._silence_timeout = silence_timeout
        self._silence_threshold = silence_threshold
        self._stopped = False

    def stop(self) -> None:
        """Signal capture to stop early."""
        self._stopped = True

    def capture(self) -> bytes:
        """Record from microphone until silence or max_seconds.

        Returns raw PCM-16 mono audio bytes.
        """
        try:
            return self._capture_pyaudio()
        except ImportError:
            pass
        try:
            return self._capture_sounddevice()
        except ImportError:
            raise RuntimeError(
                "No audio capture library found.  Install one of:\n"
                "  pip install pyaudio\n"
                "  pip install sounddevice"
            )

    def _capture_pyaudio(self) -> bytes:
        import pyaudio
        import struct
        import math
        import time

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
            )
            frames: list[bytes] = []
            max_chunks = int(self.RATE / self.CHUNK * self._max_seconds)
            silence_chunks = int(self.RATE / self.CHUNK * self._silence_timeout)
            silent_count = 0

            for _ in range(max_chunks):
                if self._stopped:
                    break
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                frames.append(data)

                # Compute RMS level
                count = len(data) // 2
                shorts = struct.unpack(f"<{count}h", data)
                rms = math.sqrt(sum(s * s for s in shorts) / count) / 32768.0
                if self._on_level:
                    self._on_level(min(rms * 5, 1.0))

                if rms < self._silence_threshold:
                    silent_count += 1
                    if silent_count >= silence_chunks:
                        break
                else:
                    silent_count = 0

            stream.stop_stream()
            stream.close()
            return b"".join(frames)
        finally:
            pa.terminate()

    def _capture_sounddevice(self) -> bytes:
        import sounddevice as sd
        import numpy as np
        import time

        frames: list[bytes] = []
        max_chunks = int(self.RATE / self.CHUNK * self._max_seconds)
        silence_chunks = int(self.RATE / self.CHUNK * self._silence_timeout)
        silent_count = 0

        def callback(indata, frame_count, time_info, status):
            nonlocal silent_count
            pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            frames.append(pcm)
            rms = float(np.sqrt(np.mean(indata ** 2)))
            if self._on_level:
                self._on_level(min(rms * 5, 1.0))
            if rms < self._silence_threshold:
                silent_count += 1
            else:
                silent_count = 0

        with sd.InputStream(
            samplerate=self.RATE,
            channels=self.CHANNELS,
            blocksize=self.CHUNK,
            dtype="float32",
            callback=callback,
        ):
            start = time.monotonic()
            while not self._stopped:
                time.sleep(0.05)
                elapsed = time.monotonic() - start
                if elapsed >= self._max_seconds:
                    break
                if silent_count >= silence_chunks:
                    break

        return b"".join(frames)


# ── Audio playback ──────────────────────────────────────────────────

def play_wav(wav_bytes: bytes) -> None:
    """Play WAV audio bytes through the default output device."""
    try:
        _play_pyaudio(wav_bytes)
        return
    except ImportError:
        pass
    try:
        _play_sounddevice(wav_bytes)
        return
    except ImportError:
        pass
    # Last resort: write to temp file and use platform command
    _play_system(wav_bytes)


def _play_pyaudio(wav_bytes: bytes) -> None:
    import pyaudio

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
            )
            chunk = 1024
            data = wf.readframes(chunk)
            while data:
                stream.write(data)
                data = wf.readframes(chunk)
            stream.stop_stream()
            stream.close()
        finally:
            pa.terminate()


def _play_sounddevice(wav_bytes: bytes) -> None:
    import sounddevice as sd
    import numpy as np

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(wf.getsampwidth(), np.int16)
        audio = np.frombuffer(raw, dtype=dtype)
        if wf.getnchannels() > 1:
            audio = audio.reshape(-1, wf.getnchannels())
        sd.play(audio, wf.getframerate())
        sd.wait()


def _play_system(wav_bytes: bytes) -> None:
    import subprocess
    import sys
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(wav_bytes)
        if sys.platform == "win32":
            # Use PowerShell to play
            subprocess.run(
                ["powershell", "-c",
                 f"(New-Object System.Media.SoundPlayer '{tmp}').PlaySync()"],
                check=False,
            )
        elif sys.platform == "darwin":
            subprocess.run(["afplay", tmp], check=False)
        else:
            subprocess.run(["aplay", tmp], check=False)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── Provider factories ──────────────────────────────────────────────

STT_PROVIDERS = {
    "local": "WhisperLocalSTT",
    "google_free": "GoogleFreeSTT",
    "deepgram": "DeepgramSTT",
    "whisper_api": "WhisperAPISTT",
}

TTS_PROVIDERS = {
    "local": "LocalTTS",
    "elevenlabs": "ElevenLabsTTS",
    "openai_tts": "OpenAITTS",
}


def _get_voice_api_key(provider: str) -> str:
    """Resolve the API key for a voice provider."""
    try:
        from o3de_cli.core.config import get_config

        cfg = get_config()
        per_keys = cfg.get("ai.api_keys", {})
        if isinstance(per_keys, dict):
            # Direct voice key first
            if provider in per_keys:
                return per_keys[provider]
            # Fall back to the parent AI provider key
            parent_map = {
                "deepgram": "deepgram",
                "whisper_api": "openai",
                "elevenlabs": "elevenlabs",
                "openai_tts": "openai",
            }
            parent = parent_map.get(provider, "")
            if parent and parent in per_keys:
                return per_keys[parent]
        return cfg.get("ai.api_key", "")
    except Exception:
        return ""


def get_stt_provider(vcfg: VoiceConfig | None = None) -> STTProvider:
    """Create the configured STT provider."""
    if vcfg is None:
        vcfg = VoiceConfig.from_config()
    name = vcfg.stt_provider
    if name == "local":
        return WhisperLocalSTT(vcfg.stt_model)
    elif name == "google_free":
        return GoogleFreeSTT()
    elif name == "deepgram":
        return DeepgramSTT(_get_voice_api_key("deepgram"))
    elif name == "whisper_api":
        return WhisperAPISTT(_get_voice_api_key("whisper_api"))
    else:
        return GoogleFreeSTT()  # safe default


def get_tts_provider(vcfg: VoiceConfig | None = None) -> TTSProvider:
    """Create the configured TTS provider."""
    if vcfg is None:
        vcfg = VoiceConfig.from_config()
    name = vcfg.tts_provider
    if name == "local":
        return LocalTTS(vcfg.tts_voice)
    elif name == "elevenlabs":
        return ElevenLabsTTS(_get_voice_api_key("elevenlabs"), vcfg.tts_voice)
    elif name == "openai_tts":
        voice = vcfg.tts_voice or "alloy"
        return OpenAITTS(_get_voice_api_key("openai_tts"), voice)
    else:
        return LocalTTS()  # safe default
