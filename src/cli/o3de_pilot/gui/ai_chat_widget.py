# O3DE Pilot GUI - AI Chat Widget
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Standalone AI chat / assistant widget.

Contains:
* a scrollable response area,
* a single-line prompt input,
* a microphone toggle button (voice → text),
* a send button.

Can be embedded in a dock, tab, or dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QSizePolicy,
)

from .ai_provider import AiProvider, StubAiProvider
from .ai_voice_input import VoiceInputWorker


class AiChatWidget(QWidget):
    """Reusable AI chat panel with voice input support."""

    promptSent = Signal(str)  # emitted when a prompt is dispatched

    # -- Colours & style constants -----------------------------------------
    _IDLE_MIC_STYLE = (
        "QPushButton { background-color: #444444; color: #CCCCCC;"
        " border: 1px solid #555555; border-radius: 4px;"
        " padding: 4px 10px; font-size: 14px; }"
        "QPushButton:hover { background-color: #555555; }"
    )
    _RECORDING_MIC_STYLE = (
        "QPushButton { background-color: #CC3333; color: #FFFFFF;"
        " border: 1px solid #FF4444; border-radius: 4px;"
        " padding: 4px 10px; font-size: 14px; }"
    )

    def __init__(self, provider: AiProvider | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._provider: AiProvider = provider or StubAiProvider()
        self._voice_worker: VoiceInputWorker | None = None
        self._is_recording = False
        self._setup_ui()

    # -- UI setup ----------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- response area ------------------------------------------------
        self._response_area = QTextEdit()
        self._response_area.setReadOnly(True)
        self._response_area.setPlaceholderText("AI responses will appear here…")
        self._response_area.setStyleSheet(
            "QTextEdit { background-color: #1E1E1E; color: #DDDDDD;"
            " border: 1px solid #333333; border-radius: 4px; padding: 6px; }"
        )
        layout.addWidget(self._response_area, stretch=1)

        # --- input row ----------------------------------------------------
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText("Type a message or press 🎤 to speak…")
        self._prompt_input.setStyleSheet(
            "QLineEdit { background-color: #2A2A2A; color: #EEEEEE;"
            " border: 1px solid #444444; border-radius: 4px; padding: 6px; }"
        )
        self._prompt_input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._prompt_input, stretch=1)

        # Mic button (text fallback – no external icon file needed)
        self._mic_btn = QPushButton("\U0001F3A4")  # 🎤
        self._mic_btn.setToolTip("Toggle voice recording")
        self._mic_btn.setFixedWidth(40)
        self._mic_btn.setStyleSheet(self._IDLE_MIC_STYLE)
        self._mic_btn.clicked.connect(self._toggle_voice)
        input_row.addWidget(self._mic_btn)

        # Send button
        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: white;"
            " border: none; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1A8AE8; }"
            "QPushButton:pressed { background-color: #005EA6; }"
        )
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        layout.addLayout(input_row)

        # --- status label -------------------------------------------------
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("QLabel { color: #999999; font-size: 8pt; }")
        layout.addWidget(self._status_label)

    # -- Provider ----------------------------------------------------------

    def set_provider(self, provider: AiProvider):
        """Replace the current AI provider."""
        self._provider = provider

    # -- Send prompt -------------------------------------------------------

    def _on_send(self):
        text = self._prompt_input.text().strip()
        if not text:
            return
        self._prompt_input.clear()
        self._append_message("You", text)
        self.promptSent.emit(text)
        self.send_to_ai_provider(text)

    def send_to_ai_provider(self, text: str):
        """Send *text* to the configured AI provider and display the reply.

        Override or connect ``promptSent`` to customise routing.
        """
        self._status_label.setText("Thinking…")
        try:
            response = self._provider.complete(text)
        except Exception as exc:  # noqa: BLE001
            response = f"[error] {exc}"
        self._append_message("AI", response)
        self._status_label.setText("")

    # -- Voice input -------------------------------------------------------

    def _toggle_voice(self):
        if self._is_recording:
            self._stop_voice()
        else:
            self._start_voice()

    def _start_voice(self):
        if self._voice_worker is not None and self._voice_worker.isRunning():
            return
        self._voice_worker = VoiceInputWorker(self)
        self._voice_worker.transcriptionReady.connect(self._on_transcription)
        self._voice_worker.errorOccurred.connect(self._on_voice_error)
        self._voice_worker.recordingStarted.connect(self._on_recording_started)
        self._voice_worker.recordingStopped.connect(self._on_recording_stopped)
        self._voice_worker.finished.connect(self._on_voice_thread_finished)
        self._voice_worker.start()

    def _stop_voice(self):
        if self._voice_worker is not None:
            self._voice_worker.request_stop()

    def _on_transcription(self, text: str):
        # Insert transcribed text into the prompt input
        current = self._prompt_input.text()
        separator = " " if current and not current.endswith(" ") else ""
        self._prompt_input.setText(current + separator + text)
        self._prompt_input.setFocus()
        self._status_label.setText("Transcription complete.")

    def _on_voice_error(self, msg: str):
        self._status_label.setText(f"Voice error: {msg}")

    def _on_recording_started(self):
        self._is_recording = True
        self._mic_btn.setStyleSheet(self._RECORDING_MIC_STYLE)
        self._mic_btn.setText("\u23F9")  # ⏹
        self._status_label.setText("Recording… speak now.")

    def _on_recording_stopped(self):
        self._is_recording = False
        self._mic_btn.setStyleSheet(self._IDLE_MIC_STYLE)
        self._mic_btn.setText("\U0001F3A4")  # 🎤
        self._status_label.setText("Processing speech…")

    def _on_voice_thread_finished(self):
        self._is_recording = False
        self._mic_btn.setStyleSheet(self._IDLE_MIC_STYLE)
        self._mic_btn.setText("\U0001F3A4")

    # -- Helpers -----------------------------------------------------------

    def _append_message(self, role: str, text: str):
        colour = "#88CCFF" if role == "You" else "#88FF88"
        self._response_area.append(
            f'<span style="color:{colour};"><b>{role}:</b></span> '
            f'<span style="color:#DDDDDD;">{text}</span><br>'
        )
        # Scroll to bottom
        sb = self._response_area.verticalScrollBar()
        sb.setValue(sb.maximum())
