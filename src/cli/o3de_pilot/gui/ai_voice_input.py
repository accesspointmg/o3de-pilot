# O3DE Pilot GUI - Voice Input Worker
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Voice-to-text pipeline using the ``speech_recognition`` library.

``speech_recognition`` is a lightweight wrapper that can use several
backends (Google Web Speech API – free default, Whisper, Sphinx, etc.).
It falls back gracefully when optional heavy dependencies are absent.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class VoiceInputWorker(QThread):
    """Record from the default microphone and emit transcribed text.

    Signals:
        transcriptionReady(str) – the recognised text.
        errorOccurred(str)      – human-readable error description.
        recordingStarted()      – microphone capture has begun.
        recordingStopped()      – microphone capture has ended.
    """

    transcriptionReady = Signal(str)
    errorOccurred = Signal(str)
    recordingStarted = Signal()
    recordingStopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag = False

    # -- public API --------------------------------------------------------

    def request_stop(self):
        """Ask the worker to stop after the current phrase."""
        self._stop_flag = True

    # -- QThread -----------------------------------------------------------

    def run(self):  # noqa: D401 – Qt override
        try:
            import speech_recognition as sr  # type: ignore[import-untyped]
        except ImportError:
            self.errorOccurred.emit(
                "speech_recognition is not installed.\n"
                "Install it with: pip install SpeechRecognition"
            )
            return

        recogniser = sr.Recognizer()

        try:
            mic = sr.Microphone()
        except (OSError, AttributeError) as exc:
            self.errorOccurred.emit(f"Microphone not available: {exc}")
            return

        try:
            with mic as source:
                recogniser.adjust_for_ambient_noise(source, duration=0.5)
                self.recordingStarted.emit()

                if self._stop_flag:
                    self.recordingStopped.emit()
                    return

                # Listen for a single phrase (up to 15 s).
                try:
                    audio = recogniser.listen(source, timeout=15, phrase_time_limit=30)
                except sr.WaitTimeoutError:
                    self.recordingStopped.emit()
                    self.errorOccurred.emit("No speech detected within the timeout.")
                    return

            self.recordingStopped.emit()

            if self._stop_flag:
                return

            # --- transcription --------------------------------------------
            # Try Whisper first (local, needs openai-whisper installed),
            # then fall back to the free Google Web Speech API.
            text: str | None = None

            try:
                text = recogniser.recognize_whisper(audio, language="english")  # type: ignore[attr-defined]
            except (AttributeError, sr.UnknownValueError, sr.RequestError):
                pass  # whisper unavailable or failed
            except Exception:  # noqa: BLE001
                pass

            if text is None:
                try:
                    text = recogniser.recognize_google(audio)
                except sr.UnknownValueError:
                    self.errorOccurred.emit("Could not understand the audio.")
                    return
                except sr.RequestError as exc:
                    self.errorOccurred.emit(f"Speech service error: {exc}")
                    return

            if text:
                self.transcriptionReady.emit(text)
            else:
                self.errorOccurred.emit("No speech recognised.")

        except Exception as exc:  # noqa: BLE001
            self.recordingStopped.emit()
            self.errorOccurred.emit(f"Voice input error: {exc}")
