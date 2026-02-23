# O3DE Pilot GUI - AI Tab
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
AI assistant tab \u2014 first tab in the main window.

Layout (top \u2192 bottom, centred):
    \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
    \u2502        swirling AI animation         \u2502
    \u2502                                      \u2502
    \u2502     \u201cProcessing: <user prompt>\u201d      \u2502
    \u2502            (AI response)             \u2502
    \u2502                                      \u2502
    \u2502   \u250c\u2500\u2500\u2500 prompt input \u2500\u2500\u2500\u2500\u2510 \ud83c\udfa4  Send  \u2502
    \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
"""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox,
)

from .ai_animation import AIAnimationWidget, AIState
from .speech_support import SPEECH_AVAILABLE, SPEECH_MISSING_TOOLTIP


# \u2500\u2500 Background workers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

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
                # Not JSON \u2014 treat as free-form answer
                self.finished.emit(response)
        except Exception as e:
            self.error.emit(str(e))


class SpeechWorker(QObject):
    """Capture speech from microphone and convert to text."""
    text_ready = Signal(str)
    error = Signal(str)
    level = Signal(float)   # 0\u20261 mic amplitude
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
            self.error.emit("No speech detected \u2014 timed out.")
            return
        except OSError as e:
            self.error.emit(f"Microphone error: {e}")
            return

        try:
            # Use Google\u2019s free speech-to-text API first; no key needed
            text = recogniser.recognize_google(audio)
            self.text_ready.emit(text)
        except sr.UnknownValueError:
            self.error.emit("Could not understand the audio.")
        except sr.RequestError as e:
            self.error.emit(f"Speech service error: {e}")


# \u2500\u2500 Prompt input widget \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class PromptInput(QLineEdit):
    """Single-line prompt with Enter-to-send."""
    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Ask Pilot anything, or say a command\u2026")
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
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
        else:
            super().keyPressEvent(event)


# \u2500\u2500 AI Tab \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class AITab(QWidget):
    """Main AI assistant tab."""

    # Emitted when a command should be executed
    execute_command = Signal(str, dict)  # command, args

    def __init__(self, parent=None):
        super().__init__(parent)
        self._speech_available = SPEECH_AVAILABLE
        self._speech_thread: Optional[QThread] = None
        self._speech_worker: Optional[SpeechWorker] = None
        self._ai_thread: Optional[QThread] = None
        self._ai_worker: Optional[AIWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # AI animation
        self._animation = AIAnimationWidget()
        self._animation.setMinimumHeight(160)
        layout.addWidget(self._animation, stretch=2)

        # Status / response area
        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #AAAAAA; font-size: 10pt;")
        layout.addWidget(self._status_label)

        self._response_area = QTextEdit()
        self._response_area.setReadOnly(True)
        self._response_area.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #DDDDDD;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 8px;
                font-size: 10pt;
            }
        """)
        self._response_area.setVisible(False)
        layout.addWidget(self._response_area, stretch=3)

        # Prompt bar
        prompt_layout = QHBoxLayout()
        prompt_layout.setSpacing(8)

        self._prompt_input = PromptInput()
        self._prompt_input.submitted.connect(self._on_submit)
        prompt_layout.addWidget(self._prompt_input, stretch=1)

        # Microphone button
        self._mic_btn = QPushButton("\ud83c\udfa4")
        self._mic_btn.setFixedSize(40, 40)
        self._mic_btn.setToolTip("Voice input")
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                border: 1px solid #444444;
                border-radius: 6px;
                font-size: 14pt;
            }
            QPushButton:hover { background-color: #3D3D3D; }
            QPushButton:pressed { background-color: #0078D4; }
            QPushButton:disabled {
                background-color: #1E1E1E;
                color: #666666;
                border-color: #333333;
            }
        """)

        if not self._speech_available:
            self._mic_btn.setEnabled(False)
            self._mic_btn.setToolTip(SPEECH_MISSING_TOOLTIP)
        else:
            self._mic_btn.clicked.connect(self._on_mic_clicked)

        prompt_layout.addWidget(self._mic_btn)

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
        self._send_btn.clicked.connect(self._on_send_clicked)
        prompt_layout.addWidget(self._send_btn)

        layout.addLayout(prompt_layout)

    # \u2500\u2500 Slots \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _on_submit(self, text: str):
        """Handle prompt submission (Enter key)."""
        self._send_prompt(text)

    def _on_send_clicked(self):
        """Handle Send button click."""
        text = self._prompt_input.text().strip()
        if text:
            self._prompt_input.clear()
            self._send_prompt(text)

    def _send_prompt(self, text: str):
        """Send prompt to AI provider."""
        self._status_label.setText(f"Processing: {text}")
        self._response_area.setVisible(False)
        self._animation.set_state(AIState.THINKING)

        # Try local pattern match first
        try:
            from ..ai.command_router import match_command
            action = match_command(text)
            if action:
                self._animation.set_state(AIState.IDLE)
                self._status_label.setText("")
                # Emit command for execution
                self.execute_command.emit(action.command, action.args)
                self._on_ai_finished(f"Running command: {action.command}")
                return
        except ImportError:
            pass  # Command router not available, fall through to AI

        # Send to AI provider
        try:
            from ..ai.provider import get_ai_provider
            from ..ai.command_router import get_ai_classification_prompt
            provider = get_ai_provider()
            classification_prompt = get_ai_classification_prompt(text)
        except Exception as e:
            self._on_ai_error(str(e))
            return

        # Start AI worker in background thread
        self._ai_thread = QThread()
        self._ai_worker = AIWorker(provider, text, classification_prompt)
        self._ai_worker.moveToThread(self._ai_thread)

        # Wire signals
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.command.connect(self._on_ai_command)
        self._ai_worker.error.connect(self._on_ai_error)

        # Quit thread when worker emits any result
        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.command.connect(self._ai_thread.quit)
        self._ai_worker.error.connect(self._ai_thread.quit)

        # Clean up after thread finishes
        self._ai_thread.finished.connect(self._cleanup_ai_worker)

        self._ai_thread.start()

    def _cleanup_ai_worker(self):
        """Clean up worker and thread after AI completes."""
        if self._ai_worker:
            self._ai_worker.deleteLater()
            self._ai_worker = None
        if self._ai_thread:
            self._ai_thread.deleteLater()
            self._ai_thread = None

    def _on_ai_command(self, action_json: str):
        """Handle AI command response."""
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        try:
            data = json.loads(action_json)
            command = data.get("command", "")
            args = data.get("args", {})
            self.execute_command.emit(command, args)
            self._response_area.setPlainText(f"Executing: {command}\n{json.dumps(args, indent=2)}")
            self._response_area.setVisible(True)
        except Exception as e:
            self._on_ai_error(f"Failed to parse command: {e}")

    def _on_ai_finished(self, result: str):
        """Handle AI completion result."""
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._response_area.setPlainText(result)
        self._response_area.setVisible(True)

    def _on_ai_error(self, message: str):
        """Handle AI completion error."""
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._response_area.setPlainText(f"Error: {message}")
        self._response_area.setVisible(True)

    # \u2500\u2500 Speech \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _on_mic_clicked(self):
        """Start speech recognition in a background thread."""
        if self._speech_thread is not None and self._speech_thread.isRunning():
            return  # already listening

        self._mic_btn.setEnabled(False)
        self._mic_btn.setText("\u2026")
        self._status_label.setText("Listening\u2026")
        self._animation.set_state(AIState.LISTENING)

        self._speech_thread = QThread()
        self._speech_worker = SpeechWorker()
        self._speech_worker.moveToThread(self._speech_thread)

        # Wire signals
        self._speech_thread.started.connect(self._speech_worker.run)
        self._speech_worker.text_ready.connect(self._on_speech_text)
        self._speech_worker.error.connect(self._on_speech_error)
        self._speech_worker.listening.connect(self._on_speech_listening)
        self._speech_worker.level.connect(self._animation.set_mic_level)

        # Clean up thread when worker finishes
        self._speech_worker.text_ready.connect(self._speech_thread.quit)
        self._speech_worker.error.connect(self._speech_thread.quit)
        self._speech_thread.finished.connect(self._on_speech_thread_finished)
        self._speech_thread.finished.connect(self._speech_thread.deleteLater)
        self._speech_thread.finished.connect(self._speech_worker.deleteLater)

        self._speech_thread.start()

    def _on_speech_listening(self):
        """Called when the recogniser is actually listening."""
        self._status_label.setText("Listening\u2026 speak now")

    def _on_speech_text(self, text: str):
        """Populate prompt input with recognised speech."""
        self._prompt_input.setText(text)
        self._prompt_input.setFocus()
        self._status_label.setText("")
        self._animation.set_state(AIState.IDLE)

    def _on_speech_error(self, message: str):
        """Show speech error in a message box."""
        self._status_label.setText("")
        self._animation.set_state(AIState.IDLE)
        QMessageBox.warning(self, "Speech Recognition", message)

    def _on_speech_thread_finished(self):
        """Reset mic button after speech thread completes."""
        self._mic_btn.setEnabled(True)
        self._mic_btn.setText("\ud83c\udfa4")
        self._speech_worker = None
        self._speech_thread = None
