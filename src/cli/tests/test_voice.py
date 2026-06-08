# O3DE Pilot - Voice AI Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the voice module (STT/TTS providers, audio, config, CLI)."""

import io
import json
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from click.testing import CliRunner

from o3de_pilot.ai.voice import (
    VoiceConfig,
    STTProvider,
    TTSProvider,
    WhisperLocalSTT,
    GoogleFreeSTT,
    DeepgramSTT,
    WhisperAPISTT,
    LocalTTS,
    ElevenLabsTTS,
    OpenAITTS,
    AudioCapture,
    play_wav,
    get_stt_provider,
    get_tts_provider,
    STT_PROVIDERS,
    TTS_PROVIDERS,
    _get_voice_api_key,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _make_pcm(seconds: float = 0.1, rate: int = 16000) -> bytes:
    """Generate silent PCM-16 mono audio."""
    return b"\x00\x00" * int(rate * seconds)


def _make_wav(seconds: float = 0.1, rate: int = 16000) -> bytes:
    """Generate a WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(_make_pcm(seconds, rate))
    return buf.getvalue()


# ── VoiceConfig ─────────────────────────────────────────────────────

class TestVoiceConfig:
    def test_defaults(self):
        cfg = VoiceConfig()
        assert cfg.enabled is False
        assert cfg.stt_provider == "local"
        assert cfg.tts_provider == "local"
        assert cfg.stt_model == "base"
        assert cfg.tts_voice == ""
        assert cfg.auto_listen is False

    def test_from_config_missing(self):
        """Should return defaults when config has no voice section."""
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {}
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            vcfg = VoiceConfig.from_config()
        assert vcfg.enabled is False
        assert vcfg.stt_provider == "local"

    def test_from_config_populated(self):
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {
            "enabled": "true",
            "stt_provider": "deepgram",
            "tts_provider": "elevenlabs",
            "stt_model": "small",
            "tts_voice": "rachel",
            "auto_listen": "true",
        }
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            vcfg = VoiceConfig.from_config()
        assert vcfg.enabled is True
        assert vcfg.stt_provider == "deepgram"
        assert vcfg.tts_provider == "elevenlabs"
        assert vcfg.stt_model == "small"
        assert vcfg.tts_voice == "rachel"
        assert vcfg.auto_listen is True

    def test_from_config_exception_returns_defaults(self):
        with patch("o3de_pilot.core.config.get_config", side_effect=RuntimeError):
            vcfg = VoiceConfig.from_config()
        assert vcfg.enabled is False

    def test_save(self):
        mock_cfg = MagicMock()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            vcfg = VoiceConfig(enabled=True, stt_provider="deepgram")
            vcfg.save()
        mock_cfg.set.assert_any_call("ai.voice.enabled", "true")
        mock_cfg.set.assert_any_call("ai.voice.stt_provider", "deepgram")
        mock_cfg.save.assert_called_once()


# ── STT Providers ───────────────────────────────────────────────────

class TestWhisperLocalSTT:
    def test_transcribe(self):
        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = "hello world"
        mock_model.transcribe.return_value = ([seg], MagicMock())

        stt = WhisperLocalSTT("base")
        stt._model = mock_model  # bypass lazy load
        result = stt.transcribe(_make_pcm())
        assert result == "hello world"
        mock_model.transcribe.assert_called_once()

    def test_is_available_missing(self):
        stt = WhisperLocalSTT()
        with patch.dict("sys.modules", {"faster_whisper": None}):
            # When import raises ImportError
            with patch("builtins.__import__", side_effect=ImportError):
                assert stt.is_available() is False

    def test_load_model_import_error(self):
        stt = WhisperLocalSTT()
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                with pytest.raises(RuntimeError, match="faster-whisper"):
                    stt._load_model()


class TestGoogleFreeSTT:
    def test_transcribe(self):
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "test result"
        mock_sr = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_sr.AudioData.return_value = MagicMock()

        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            stt = GoogleFreeSTT()
            result = stt.transcribe(_make_pcm())
        assert result == "test result"

    def test_transcribe_unknown_value(self):
        import importlib
        mock_sr = MagicMock()
        mock_sr.UnknownValueError = type("UnknownValueError", (Exception,), {})
        mock_sr.RequestError = type("RequestError", (Exception,), {})
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.side_effect = mock_sr.UnknownValueError()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_sr.AudioData.return_value = MagicMock()

        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            stt = GoogleFreeSTT()
            result = stt.transcribe(_make_pcm())
        assert result == ""


class TestDeepgramSTT:
    def test_transcribe(self):
        stt = DeepgramSTT("test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {
                "channels": [{"alternatives": [{"transcript": "hello deepgram"}]}]
            }
        }
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = stt.transcribe(_make_pcm())
        assert result == "hello deepgram"
        assert mock_post.call_args[1]["headers"]["Authorization"] == "Token test-key"

    def test_is_available_no_key(self):
        stt = DeepgramSTT("")
        assert stt.is_available() is False

    def test_is_available_with_key(self):
        stt = DeepgramSTT("key")
        assert stt.is_available() is True


class TestWhisperAPISTT:
    def test_transcribe(self):
        stt = WhisperAPISTT("test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"text": "whisper result"}
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = stt.transcribe(_make_pcm())
        assert result == "whisper result"
        assert "Bearer test-key" in str(mock_post.call_args)

    def test_is_available_no_key(self):
        stt = WhisperAPISTT("")
        assert stt.is_available() is False


# ── TTS Providers ───────────────────────────────────────────────────

class TestLocalTTS:
    def test_synthesize(self):
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine

        wav_data = _make_wav()

        def fake_save(text, path):
            with open(path, "wb") as f:
                f.write(wav_data)

        mock_engine.save_to_file.side_effect = fake_save

        with patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3}):
            tts = LocalTTS()
            result = tts.synthesize("hello")
        assert len(result) > 0

    def test_with_voice_id(self):
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine
        mock_engine.save_to_file.side_effect = lambda text, path: open(path, "wb").write(_make_wav())

        with patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3}):
            tts = LocalTTS("custom-voice")
            tts.synthesize("test")
        mock_engine.setProperty.assert_called_once_with("voice", "custom-voice")


class TestElevenLabsTTS:
    def test_synthesize(self):
        tts = ElevenLabsTTS("test-key", "voice123")
        mock_resp = MagicMock()
        mock_resp.content = _make_wav()
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = tts.synthesize("hello eleven")
        assert len(result) > 0
        url = mock_post.call_args[0][0]
        assert "voice123" in url
        assert mock_post.call_args[1]["headers"]["xi-api-key"] == "test-key"

    def test_default_voice(self):
        tts = ElevenLabsTTS("key")
        assert tts._voice_id == ElevenLabsTTS._DEFAULT_VOICE_ID

    def test_is_available(self):
        assert ElevenLabsTTS("key").is_available() is True
        assert ElevenLabsTTS("").is_available() is False


class TestOpenAITTS:
    def test_synthesize(self):
        tts = OpenAITTS("test-key", "nova")
        mock_resp = MagicMock()
        mock_resp.content = _make_wav()
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = tts.synthesize("hello openai")
        assert len(result) > 0
        body = mock_post.call_args[1]["json"]
        assert body["voice"] == "nova"
        assert body["model"] == "tts-1"

    def test_is_available(self):
        assert OpenAITTS("key").is_available() is True
        assert OpenAITTS("").is_available() is False


# ── Audio Capture ───────────────────────────────────────────────────

class TestAudioCapture:
    def test_capture_stops_on_flag(self):
        """Capture should respect the stop flag."""
        mock_pa = MagicMock()
        mock_stream = MagicMock()
        mock_pa.PyAudio.return_value = mock_pa
        mock_pa.open.return_value = mock_stream
        mock_pa.paInt16 = 8
        # Return one chunk of silence then stop
        silence = b"\x00\x00" * 1024
        mock_stream.read.return_value = silence

        cap = AudioCapture(max_seconds=1)
        cap._stopped = True  # stop immediately

        with patch.dict("sys.modules", {"pyaudio": mock_pa}):
            result = cap._capture_pyaudio()
        # Should have returned with minimal/no data
        assert isinstance(result, bytes)

    def test_stop_method(self):
        cap = AudioCapture()
        assert cap._stopped is False
        cap.stop()
        assert cap._stopped is True

    def test_level_callback(self):
        levels = []
        cap = AudioCapture(on_level=lambda lv: levels.append(lv), max_seconds=0.1)

        mock_pa = MagicMock()
        mock_stream = MagicMock()
        mock_pa.PyAudio.return_value = mock_pa
        mock_pa.open.return_value = mock_stream
        mock_pa.paInt16 = 8
        # One chunk of data with some amplitude
        chunk = struct.pack("<1024h", *([1000] * 1024))
        call_count = [0]

        def read_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 2:
                cap.stop()
            return chunk

        mock_stream.read.side_effect = read_side_effect

        with patch.dict("sys.modules", {"pyaudio": mock_pa}):
            cap._capture_pyaudio()
        assert len(levels) > 0


# ── Audio Playback ──────────────────────────────────────────────────

class TestPlayWav:
    def test_play_system_windows(self):
        wav = _make_wav()
        with patch("subprocess.run") as mock_run, \
             patch("sys.platform", "win32"):
            from o3de_pilot.ai.voice import _play_system
            _play_system(wav)
        mock_run.assert_called_once()
        assert "powershell" in mock_run.call_args[0][0][0].lower()

    def test_play_system_darwin(self):
        wav = _make_wav()
        with patch("subprocess.run") as mock_run, \
             patch("sys.platform", "darwin"):
            from o3de_pilot.ai.voice import _play_system
            _play_system(wav)
        assert mock_run.call_args[0][0][0] == "afplay"


# ── Provider Factories ──────────────────────────────────────────────

class TestGetSTTProvider:
    def test_local(self):
        vcfg = VoiceConfig(stt_provider="local", stt_model="tiny")
        stt = get_stt_provider(vcfg)
        assert isinstance(stt, WhisperLocalSTT)
        assert stt._model_size == "tiny"

    def test_google_free(self):
        vcfg = VoiceConfig(stt_provider="google_free")
        stt = get_stt_provider(vcfg)
        assert isinstance(stt, GoogleFreeSTT)

    def test_deepgram(self):
        with patch("o3de_pilot.ai.voice._get_voice_api_key", return_value="dk"):
            vcfg = VoiceConfig(stt_provider="deepgram")
            stt = get_stt_provider(vcfg)
        assert isinstance(stt, DeepgramSTT)
        assert stt._api_key == "dk"

    def test_whisper_api(self):
        with patch("o3de_pilot.ai.voice._get_voice_api_key", return_value="wk"):
            vcfg = VoiceConfig(stt_provider="whisper_api")
            stt = get_stt_provider(vcfg)
        assert isinstance(stt, WhisperAPISTT)
        assert stt._api_key == "wk"

    def test_unknown_falls_back(self):
        vcfg = VoiceConfig(stt_provider="unknown")
        stt = get_stt_provider(vcfg)
        assert isinstance(stt, GoogleFreeSTT)


class TestGetTTSProvider:
    def test_local(self):
        vcfg = VoiceConfig(tts_provider="local", tts_voice="v1")
        tts = get_tts_provider(vcfg)
        assert isinstance(tts, LocalTTS)
        assert tts._voice_id == "v1"

    def test_elevenlabs(self):
        with patch("o3de_pilot.ai.voice._get_voice_api_key", return_value="ek"):
            vcfg = VoiceConfig(tts_provider="elevenlabs", tts_voice="myvoice")
            tts = get_tts_provider(vcfg)
        assert isinstance(tts, ElevenLabsTTS)
        assert tts._api_key == "ek"
        assert tts._voice_id == "myvoice"

    def test_openai_tts(self):
        with patch("o3de_pilot.ai.voice._get_voice_api_key", return_value="ok"):
            vcfg = VoiceConfig(tts_provider="openai_tts", tts_voice="echo")
            tts = get_tts_provider(vcfg)
        assert isinstance(tts, OpenAITTS)
        assert tts._voice == "echo"

    def test_unknown_falls_back(self):
        vcfg = VoiceConfig(tts_provider="unknown")
        tts = get_tts_provider(vcfg)
        assert isinstance(tts, LocalTTS)


# ── API Key Resolution ──────────────────────────────────────────────

class TestGetVoiceAPIKey:
    def test_direct_key(self):
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d=None: {
            "ai.api_keys": {"deepgram": "dg-key"},
            "ai.api_key": "",
        }.get(k, d)
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            assert _get_voice_api_key("deepgram") == "dg-key"

    def test_parent_fallback(self):
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d=None: {
            "ai.api_keys": {"openai": "oai-key"},
            "ai.api_key": "",
        }.get(k, d)
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            assert _get_voice_api_key("whisper_api") == "oai-key"

    def test_global_fallback(self):
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d=None: {
            "ai.api_keys": {},
            "ai.api_key": "global-key",
        }.get(k, d)
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            assert _get_voice_api_key("deepgram") == "global-key"


# ── Provider registry constants ─────────────────────────────────────

class TestProviderRegistries:
    def test_stt_providers(self):
        assert "local" in STT_PROVIDERS
        assert "google_free" in STT_PROVIDERS
        assert "deepgram" in STT_PROVIDERS
        assert "whisper_api" in STT_PROVIDERS

    def test_tts_providers(self):
        assert "local" in TTS_PROVIDERS
        assert "elevenlabs" in TTS_PROVIDERS
        assert "openai_tts" in TTS_PROVIDERS


# ── CLI Commands ────────────────────────────────────────────────────

class TestVoiceStatusCLI:
    def test_voice_status_disabled(self):
        runner = CliRunner()
        with patch("o3de_pilot.ai.voice.VoiceConfig.from_config", return_value=VoiceConfig()):
            from o3de_pilot.commands.ai import ai
            result = runner.invoke(ai, ["voice-status"])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "Enabled" in result.output

    def test_voice_status_enabled(self):
        runner = CliRunner()
        vcfg = VoiceConfig(enabled=True, stt_provider="deepgram", tts_provider="elevenlabs")
        with patch("o3de_pilot.ai.voice.VoiceConfig.from_config", return_value=vcfg), \
             patch("o3de_pilot.ai.voice.get_stt_provider") as mock_stt, \
             patch("o3de_pilot.ai.voice.get_tts_provider") as mock_tts:
            mock_stt.return_value.is_available.return_value = True
            mock_tts.return_value.is_available.return_value = True
            from o3de_pilot.commands.ai import ai
            result = runner.invoke(ai, ["voice-status"])
        assert result.exit_code == 0
        assert "deepgram" in result.output
        assert "elevenlabs" in result.output


class TestVoiceSessionCLI:
    def test_voice_not_enabled(self):
        runner = CliRunner()
        with patch("o3de_pilot.ai.voice.VoiceConfig.from_config", return_value=VoiceConfig()):
            from o3de_pilot.commands.ai import ai
            result = runner.invoke(ai, ["voice"])
        assert result.exit_code == 0
        assert "not enabled" in result.output.lower()
