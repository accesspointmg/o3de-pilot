# O3DE Pilot GUI - AI Tab
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
AI assistant tab — first tab in the main window.

Layout (top → bottom, centred):
    ┌──────────────────────────────────────┐
    │        swirling AI animation         │
    │                                      │
    │     "Processing: <user prompt>"      │
    │            (AI response)             │
    │                                      │
    │   ┌─── prompt input ────┐ 🎤  Send  │
    └──────────────────────────────────────┘
"""

from __future__ import annotations

import json
import traceback
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QApplication, QSizePolicy,
    QTextEdit,
)

from .ai_animation import AIAnimationWidget, AIState
from .speech_utils import SPEECH_AVAILABLE


# ── Background workers ──────────────────────────────────────────────

class AIWorker(QObject):
    """Run an AI completion in a background thread."""
    finished = Signal(str)      # result text
    error = Signal(str)         # error message
    command = Signal(str)       # JSON command action from AI

    def __init__(self, provider, prompt: str, classification_prompt: str):
        super().__init__()
        self._provider = provider
        self._prompt = prompt
        self._classification_prompt = classification_prompt

    def run(self):
        try:
            response = self._provider.complete(self._classification_prompt)
            # Try to parse as JSON command
            response = response.strip()
            # Strip markdown code fences if the AI wrapped it
            if response.startswith("```"):
                response = "\n".join(response.split("\n")[1:])
                if response.endswith("```"):
                    response = response[:-3].strip()
            try:
                data = json.loads(response)
                if data.get("command") == "chat":
                    self.finished.emit(data.get("response", response))
                else:
                    self.command.emit(response)
            except (json.JSONDecodeError, KeyError):
                # Not JSON — treat as free-form answer
                self.finished.emit(response)
        except Exception as e:
            self.error.emit(str(e))


class SpeechWorker(QObject):
    """Capture speech from microphone and convert to text."""
    text_ready = Signal(str)
    error = Signal(str)
    level = Signal(float)   # 0‥1 mic amplitude
    listening = Signal()    # emitted when actually listening

    def __init__(self, timeout: int = 8, phrase_limit: int = 15):
        super().__init__()
        self._timeout = timeout
        self._phrase_limit = phrase_limit

    def run(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self.error.emit(
                "Speech recognition not available.\n"
                "Install it with:  pip install SpeechRecognition pyaudio"
            )
            return

        recogniser = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recogniser.adjust_for_ambient_noise(source, duration=0.5)
                self.listening.emit()
                audio = recogniser.listen(
                    source,
                    timeout=self._timeout,
                    phrase_time_limit=self._phrase_limit,
                )
        except sr.WaitTimeoutError:
            self.error.emit("No speech detected — timed out.")
            return
        except OSError as e:
            self.error.emit(f"Microphone error: {e}")
            return

        try:
            # Use Google's free speech-to-text API first; no key needed
            text = recogniser.recognize_google(audio)
            self.text_ready.emit(text)
        except sr.UnknownValueError:
            self.error.emit("Could not understand the audio.")
        except sr.RequestError as e:
            self.error.emit(f"Speech service error: {e}")


# ── Prompt input widget ────────────────────────────────────────────

class PromptInput(QLineEdit):
    """Single-line prompt with Enter-to-send."""
    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Ask Pilot anything, or say a command…")
        self.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 10.5pt;
            }
            QLineEdit:focus {
                border-color: #0078D4;
            }
        """)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.text().strip():
            self.submitted.emit(self.text().strip())
            self.clear()
        else:
            super().keyPressEvent(event)


# ── Chat bubble widget ─────────────────────────────────────────────

class ChatBubble(QLabel):
    """A single chat message bubble."""

    def __init__(self, text: str, is_user: bool = False, is_error: bool = False, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if is_error:
            bg = "#3D1F1F"
            border = "#D32F2F"
            color = "#FF8A80"
        elif is_user:
            bg = "#1A3A5C"
            border = "#0078D4"
            color = "#EEEEEE"
        else:
            bg = "#2D2D2D"
            border = "#444444"
            color = "#CCCCCC"

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 10pt;
            }}
        """)


# ── Main AI Tab ────────────────────────────────────────────────────

class AITab(QWidget):
    """Main AI assistant tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_provider = None
        self._worker_thread: Optional[QThread] = None
        self._speech_thread: Optional[QThread] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # AI animation
        self._animation = AIAnimationWidget()
        self._animation.setFixedHeight(120)
        layout.addWidget(self._animation, alignment=Qt.AlignHCenter)

        # Chat scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        self._chat_container = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setAlignment(Qt.AlignTop)
        self._chat_layout.setSpacing(8)
        self._scroll.setWidget(self._chat_container)
        layout.addWidget(self._scroll, stretch=1)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._prompt = PromptInput()
        self._prompt.submitted.connect(self._on_submit)
        input_row.addWidget(self._prompt, stretch=1)

        # Mic button
        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setFixedSize(40, 40)
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                border: 1px solid #444444;
                border-radius: 6px;
                font-size: 14pt;
            }
            QPushButton:hover { background-color: #3A3A3A; }
            QPushButton:pressed { background-color: #0078D4; }
            QPushButton:disabled {
                background-color: #1E1E1E;
                color: #666666;
                border-color: #333333;
            }
        """)
        self._mic_btn.clicked.connect(self._on_mic_click)

        if not SPEECH_AVAILABLE:
            self._mic_btn.setEnabled(False)
            self._mic_btn.setToolTip(
                "Speech not available. Install with:\n"
                "pip install SpeechRecognition pyaudio"
            )
        else:
            self._mic_btn.setToolTip("Click to speak")

        input_row.addWidget(self._mic_btn)

        # Send button
        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedHeight(40)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
                font-size: 10.5pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        self._send_btn.clicked.connect(lambda: self._on_submit(self._prompt.text().strip()))
        input_row.addWidget(self._send_btn)

        layout.addLayout(input_row)

    # ── Chat helpers ───────────────────────────────────────────────

    def _add_bubble(self, text: str, is_user: bool = False, is_error: bool = False):
        bubble = ChatBubble(text, is_user=is_user, is_error=is_error)
        self._chat_layout.addWidget(bubble)
        # Auto-scroll to bottom
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Submit handling ────────────────────────────────────────────

    def _on_submit(self, text: str):
        if not text:
            return
        self._prompt.clear()
        self._add_bubble(text, is_user=True)
        self._animation.set_state(AIState.PROCESSING)

        if self._ai_provider is None:
            self._add_bubble(
                "No AI provider configured. Go to Settings to set up an API key.",
                is_error=True,
            )
            self._animation.set_state(AIState.IDLE)
            return

        # Build classification prompt
        classification_prompt = (
            f"You are O3DE Pilot, an AI assistant for the O3DE game engine.\n"
            f"User said: {text}\n"
            f"Respond helpfully."
        )

        self._worker_thread = QThread()
        worker = AIWorker(self._ai_provider, text, classification_prompt)
        worker.moveToThread(self._worker_thread)

        worker.finished.connect(self._on_ai_response)
        worker.error.connect(self._on_ai_error)
        worker.command.connect(self._on_ai_command)
        self._worker_thread.started.connect(worker.run)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        # prevent GC
        self._current_worker = worker
        self._worker_thread.start()

    def _on_ai_response(self, text: str):
        self._animation.set_state(AIState.IDLE)
        self._add_bubble(text)
        self._cleanup_worker()

    def _on_ai_error(self, msg: str):
        self._animation.set_state(AIState.ERROR)
        self._add_bubble(f"Error: {msg}", is_error=True)
        self._cleanup_worker()

    def _on_ai_command(self, json_str: str):
        self._animation.set_state(AIState.IDLE)
        self._add_bubble(f"Command: {json_str}")
        self._cleanup_worker()

    def _cleanup_worker(self):
        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(2000)
        self._worker_thread = None
        self._current_worker = None

    # ── Mic / Speech handling ──────────────────────────────────────

    def _on_mic_click(self):
        if self._speech_thread and self._speech_thread.isRunning():
            return  # already listening

        self._mic_btn.setStyleSheet(
            self._mic_btn.styleSheet().replace("#2D2D2D", "#D32F2F")
        )
        self._speech_thread = QThread()
        worker = SpeechWorker()
        worker.moveToThread(self._speech_thread)

        worker.text_ready.connect(self._on_speech_text)
        worker.error.connect(self._on_speech_error)
        worker.listening.connect(lambda: self._add_bubble("🎤 Listening…"))
        self._speech_thread.started.connect(worker.run)
        self._speech_thread.finished.connect(self._speech_thread.deleteLater)
        self._current_speech_worker = worker
        self._speech_thread.start()

    def _on_speech_text(self, text: str):
        self._prompt.setText(text)
        self._reset_mic_style()
        self._cleanup_speech()

    def _on_speech_error(self, msg: str):
        self._add_bubble(f"🎤 {msg}", is_error=True)
        self._reset_mic_style()
        self._cleanup_speech()

    def _reset_mic_style(self):
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                border: 1px solid #444444;
                border-radius: 6px;
                font-size: 14pt;
            }
            QPushButton:hover { background-color: #3A3A3A; }
            QPushButton:pressed { background-color: #0078D4; }
            QPushButton:disabled {
                background-color: #1E1E1E;
                color: #666666;
                border-color: #333333;
            }
        """)

    def _cleanup_speech(self):
        if self._speech_thread and self._speech_thread.isRunning():
            self._speech_thread.quit()
            self._speech_thread.wait(2000)
        self._speech_thread = None
        self._current_speech_worker = None

    # ── Public API ─────────────────────────────────────────────────

    def set_ai_provider(self, provider):
        self._ai_provider = provider
