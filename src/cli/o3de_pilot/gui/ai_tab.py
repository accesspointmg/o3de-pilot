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


# ── Background workers ──────────────────────────────────────────────

class AIWorker(QObject):
    """Run an AI completion in a background thread."""
    finished = Signal(str)      # result text
    error = Signal(str)         # error message
    command = Signal(str)       # JSON command action from AI
    token = Signal(str)         # streaming token for progressive display

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
                    # Stream the chat response for progressive display
                    self._stream_response(data.get("response", response))
                else:
                    self.command.emit(response)
            except (json.JSONDecodeError, KeyError):
                # Not JSON — stream as free-form answer
                self._stream_response(response)
        except Exception as e:
            self.error.emit(str(e))

    def _stream_response(self, text: str) -> None:
        """Emit response as token chunks then signal finished.

        Simulates streaming for already-completed text by splitting
        into sentence-level chunks and emitting each via the token
        signal before sending the final finished signal.
        """
        import re
        # Split on sentence boundaries for chunked display
        sentences = re.split(r'(?<=[.!?\n])\s+', text)
        for sentence in sentences:
            if sentence:
                self.token.emit(sentence + " ")
        self.finished.emit(text)


class SpeechWorker(QObject):
    """Capture speech from microphone and transcribe via configured STT.

    Uses the voice module's :class:`AudioCapture` + :class:`STTProvider`
    for tiered STT (local Whisper, Google free, Deepgram, OpenAI Whisper API).
    Falls back to the legacy ``speech_recognition`` path when the voice
    module's audio capture is unavailable.
    """
    text_ready = Signal(str)
    error = Signal(str)
    level = Signal(float)   # 0‥1 mic amplitude
    listening = Signal()    # emitted when actually listening

    def __init__(self, timeout: int = 15, phrase_limit: int = 30):
        super().__init__()
        self._timeout = timeout
        self._phrase_limit = phrase_limit

    def run(self):
        try:
            from ..ai.voice import VoiceConfig, get_stt_provider, AudioCapture

            vcfg = VoiceConfig.from_config()
            stt = get_stt_provider(vcfg)
            capture = AudioCapture(
                on_level=lambda lv: self.level.emit(lv),
                max_seconds=self._timeout,
                silence_timeout=2.0,
            )
            self.listening.emit()
            audio_data = capture.capture()
            if not audio_data:
                self.error.emit("No audio captured.")
                return
            text = stt.transcribe(audio_data)
            if text.strip():
                self.text_ready.emit(text.strip())
            else:
                self.error.emit("Could not understand the audio.")
        except RuntimeError as exc:
            self.error.emit(str(exc))
        except Exception:
            # Fall back to legacy speech_recognition path
            self._legacy_recognize()

    def _legacy_recognize(self):
        """Legacy fallback using speech_recognition + Google free API."""
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
            text = recogniser.recognize_google(audio)
            self.text_ready.emit(text)
        except sr.UnknownValueError:
            self.error.emit("Could not understand the audio.")
        except sr.RequestError as e:
            self.error.emit(f"Speech service error: {e}")


class TTSWorker(QObject):
    """Synthesize text to speech and play it in a background thread."""
    finished = Signal()
    error = Signal(str)

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def run(self):
        try:
            from ..ai.voice import VoiceConfig, get_tts_provider, play_wav

            vcfg = VoiceConfig.from_config()
            tts = get_tts_provider(vcfg)
            if not tts.is_available():
                self.finished.emit()
                return
            wav = tts.synthesize(self._text[:500])
            play_wav(wav)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


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
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text().strip()
            if text:
                self.submitted.emit(text)
            return
        super().keyPressEvent(event)


# ── Chat history display ───────────────────────────────────────────

class ChatBubble(QLabel):
    """Single chat message bubble."""

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bg = "#3A3A3A" if is_user else "#0078D4"
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: #EEEEEE;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 10pt;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)


class CommandBubble(QWidget):
    """Shows a recognised command with a Run button."""
    run_requested = Signal(str)  # JSON action

    def __init__(self, action_json: str, parent=None):
        super().__init__(parent)
        self._action_json = action_json
        try:
            data = json.loads(action_json)
        except Exception:
            data = {"command": "?", "description": action_json}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Description
        desc = data.get("description", data.get("command", ""))
        cmd = data.get("command", "")
        args = data.get("args", {})
        args_str = " ".join(f"{k}={v}" for k, v in args.items()) if args else ""

        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background-color: #1A3A2A;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(4)

        cmd_label = QLabel(f"⚡ {cmd} {args_str}".strip())
        cmd_label.setStyleSheet("color: #80E0A0; font-size: 10pt; font-weight: bold; background: transparent;")
        card_layout.addWidget(cmd_label)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #AADDBB; font-size: 9pt; background: transparent;")
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        run_btn = QPushButton("Run")
        run_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
        """)
        run_btn.clicked.connect(lambda: self.run_requested.emit(self._action_json))
        btn_row.addWidget(run_btn)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        self.setMaximumWidth(560)


# ── AI Tab ──────────────────────────────────────────────────────────

class AITab(QWidget):
    """Main AI assistant tab."""

    # Emitted when a command should be executed
    execute_command = Signal(str, dict)  # command, args

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_thread: Optional[QThread] = None
        self._ai_worker: Optional[AIWorker] = None
        self._speech_thread: Optional[QThread] = None
        self._tts_thread: Optional[QThread] = None
        self._tts_worker: Optional[TTSWorker] = None
        self._streaming_bubble = None
        self._is_thinking = False
        self._setup_ui()
        self._refresh_ai_state()

    def _refresh_ai_state(self):
        """Set animation state based on provider config and connection status."""
        try:
            from ..core.config import get_config
            config = get_config()
            provider = config.get("ai.provider", "")
            connected = config.get("ai.connected", False)
            model = config.get("ai.model", "")
            provider_display = self._get_provider_display_name(provider)
            if provider and connected:
                self._animation.set_state(AIState.IDLE)
                self._status_label.setText("")
                self._online_badge.setText("● Online")
                self._online_badge.setStyleSheet(
                    "color: #4EC94E; font-size: 9pt; font-weight: bold; "
                    "padding: 4px 0; background: transparent;"
                )
                self._provider_model_label.setText(
                    f"{provider_display}  ·  {model}" if model else provider_display
                )
                self._settings_btn.hide()
            elif provider:
                self._animation.set_state(AIState.DISCONNECTED)
                self._status_label.setText("AI not verified")
                self._online_badge.setText("● Offline")
                self._online_badge.setStyleSheet(
                    "color: #CC3333; font-size: 9pt; font-weight: bold; "
                    "padding: 4px 0; background: transparent;"
                )
                self._provider_model_label.setText(
                    f"{provider_display}  ·  {model}" if model else provider_display
                )
                self._settings_btn.show()
            else:
                self._animation.set_state(AIState.DORMANT)
                self._status_label.setText("No AI configured")
                self._online_badge.setText("")
                self._provider_model_label.setText("")
                self._settings_btn.show()
        except Exception:
            self._animation.set_state(AIState.DORMANT)
            self._status_label.setText("No AI configured")
            self._online_badge.setText("")
            self._provider_model_label.setText("")
            self._settings_btn.show()

    @staticmethod
    def _get_provider_display_name(provider_id: str) -> str:
        """Map provider ID to a friendly display name."""
        names = {
            "ollama": "Ollama",
            "gemini": "Gemini",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "groq": "Groq",
            "mistral": "Mistral",
            "deepseek": "DeepSeek",
            "xai": "xAI",
            "openrouter": "OpenRouter",
            "together": "Together AI",
            "perplexity": "Perplexity",
        }
        return names.get(provider_id, provider_id.title() if provider_id else "")

    def _open_ai_settings(self):
        """Open the AI Settings dialog and refresh state afterwards."""
        from .ai_settings_dialog import AISettingsDialog
        dialog = AISettingsDialog(self.window())
        dialog.exec()
        self._refresh_ai_state()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Container with dark background
        container = QWidget()
        container.setStyleSheet("background-color: #222222;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(0)

        # ── Animation ───────────────────────────────────────────────
        anim_row = QHBoxLayout()
        anim_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._animation = AIAnimationWidget()
        self._animation.setFixedSize(120, 120)
        anim_row.addWidget(self._animation)
        layout.addLayout(anim_row)

        # ── Status area (under animation) ───────────────────────────
        status_row = QHBoxLayout()
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.setSpacing(10)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            "color: #888888; font-size: 9pt; padding: 4px 0; background: transparent;"
        )
        status_row.addWidget(self._status_label)

        self._settings_btn = QPushButton("AI Settings")
        self._settings_btn.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: white; border: none; "
            "border-radius: 4px; padding: 6px 16px; font-size: 9pt; font-weight: bold; } "
            "QPushButton:hover { background-color: #1A8AE8; }"
        )
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self._open_ai_settings)
        self._settings_btn.hide()
        status_row.addWidget(self._settings_btn)

        layout.addLayout(status_row)

        # ── Prompt display (shown while processing) ─────────────────
        self._prompt_display = QLabel("")
        self._prompt_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prompt_display.setWordWrap(True)
        self._prompt_display.setStyleSheet(
            "color: #BBBBBB; font-size: 10.5pt; font-style: italic; "
            "padding: 4px 0 8px 0; background: transparent;"
        )
        self._prompt_display.hide()
        layout.addWidget(self._prompt_display)

        # ── Chat history (scrollable, fixed minimum height) ─────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #333333;
                border-radius: 6px;
                background-color: #1A1A1A;
            }
            QWidget#chatContainer { background: transparent; }
            QScrollBar:vertical {
                background: #1A1A1A;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #777777; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_container.setObjectName("chatContainer")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()

        scroll.setWidget(self._chat_container)
        self._scroll = scroll
        layout.addWidget(scroll, 1)  # takes all remaining space

        # ── Input row ───────────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._prompt = PromptInput()
        self._prompt.submitted.connect(self._on_submit)
        input_row.addWidget(self._prompt, 1)

        # Microphone button
        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setToolTip("Hold to speak (requires SpeechRecognition + PyAudio)")
        self._mic_btn.setFixedSize(42, 42)
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 21px;
                font-size: 13.5pt;
            }
            QPushButton:hover { background-color: #3D3D3D; border-color: #0078D4; }
            QPushButton:pressed { background-color: #0078D4; }
        """)
        self._mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self._mic_btn)

        # Send / Stop button (play ▶ / stop ■)
        self._send_btn = QPushButton("▶")
        self._send_btn.setFixedSize(42, 42)
        self._send_btn.setToolTip("Send prompt")
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 21px;
                font-size: 13.5pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1A8AE8; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self._send_btn.clicked.connect(self._on_send_stop_clicked)
        input_row.addWidget(self._send_btn)

        layout.addLayout(input_row)

        # ── Bottom status bar (provider · model + connection badge) ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)
        bottom_bar.setSpacing(8)

        self._online_badge = QLabel("")
        self._online_badge.setStyleSheet(
            "color: #4EC94E; font-size: 8pt; font-weight: bold; "
            "background: transparent;"
        )
        bottom_bar.addWidget(self._online_badge)

        self._provider_model_label = QLabel("")
        self._provider_model_label.setStyleSheet(
            "color: #888888; font-size: 8pt; background: transparent;"
        )
        bottom_bar.addWidget(self._provider_model_label)

        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)

        root.addWidget(container)

    # ── Send / Stop toggle ──────────────────────────────────────────

    def _on_send_stop_clicked(self):
        if self._is_thinking:
            self._cancel_ai()
        else:
            self._on_submit(self._prompt.text().strip())

    def _set_thinking_ui(self, thinking: bool):
        self._is_thinking = thinking
        if thinking:
            self._send_btn.setText("■")
            self._send_btn.setToolTip("Stop")
            self._send_btn.setStyleSheet("""
                QPushButton {
                    background-color: #CC3333;
                    color: white;
                    border: none;
                    border-radius: 21px;
                    font-size: 13.5pt;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #EE4444; }
            """)
        else:
            self._send_btn.setText("▶")
            self._send_btn.setToolTip("Send prompt")
            self._send_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0078D4;
                    color: white;
                    border: none;
                    border-radius: 21px;
                    font-size: 13.5pt;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1A8AE8; }
                QPushButton:disabled { background-color: #444444; color: #888888; }
            """)

    # ── Submit prompt ───────────────────────────────────────────────

    def _on_submit(self, text: str):
        if not text:
            return
        self._prompt.clear()

        # Show the prompt under the animation
        self._prompt_display.setText(f'"{text}"')
        self._prompt_display.show()

        # Add user bubble
        self._add_bubble(text, is_user=True)

        # Try local pattern match first
        from ..ai.command_router import match_command
        action = match_command(text)
        if action:
            self._animation.set_state(AIState.IDLE)
            self._status_label.setText("")
            self._prompt_display.hide()
            self._show_command(json.dumps({
                "command": action.command,
                "args": action.args,
                "description": action.description,
            }))
            return

        # Fall through to AI
        self._send_to_ai(text)

    def _send_to_ai(self, text: str):
        """Send prompt to AI provider in a background thread."""
        self._animation.set_state(AIState.THINKING)
        self._status_label.setText("Thinking…")
        self._set_thinking_ui(True)
        QApplication.processEvents()

        try:
            from ..ai.provider import get_ai_provider
            from ..ai.command_router import get_ai_classification_prompt
            provider = get_ai_provider()
        except Exception as e:
            self._on_ai_error(str(e))
            return

        classification_prompt = get_ai_classification_prompt(text)

        self._ai_thread = QThread()
        self._ai_worker = AIWorker(provider, text, classification_prompt)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_response)
        self._ai_worker.token.connect(self._on_ai_token)
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

    def _cancel_ai(self):
        """Cancel the in-progress AI request."""
        if self._ai_thread and self._ai_thread.isRunning():
            self._ai_thread.quit()
            self._ai_thread.wait(2000)
            if self._ai_thread and self._ai_thread.isRunning():
                self._ai_thread.terminate()
        self._cleanup_ai_worker()
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._prompt_display.hide()
        self._set_thinking_ui(False)
        self._add_bubble("⚠ Cancelled", is_user=False)

    def _on_ai_response(self, text: str):
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._prompt_display.hide()
        self._set_thinking_ui(False)
        # If we already streamed tokens, the bubble was built progressively;
        # finalize it rather than adding a duplicate.
        if not self._streaming_bubble:
            self._add_bubble(text, is_user=False)
        self._streaming_bubble = None
        # Speak the response if voice is enabled
        self._speak(text)

    def _on_ai_token(self, token: str):
        """Handle a streaming token — append to an in-progress bubble."""
        if self._streaming_bubble is None:
            self._streaming_bubble = self._add_bubble("", is_user=False)
        current = self._streaming_bubble.text()
        self._streaming_bubble.setText(current + token)
        # Scroll to show latest text
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _on_ai_command(self, action_json: str):
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._prompt_display.hide()
        self._set_thinking_ui(False)
        self._show_command(action_json)

    def _on_ai_error(self, msg: str):
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        self._prompt_display.hide()
        self._set_thinking_ui(False)
        self._add_bubble(f"⚠ {msg}", is_user=False)

    # ── Microphone ──────────────────────────────────────────────────

    def _on_mic_clicked(self):
        if self._speech_thread and self._speech_thread.isRunning():
            return  # Already listening

        self._animation.set_state(AIState.LISTENING)
        self._status_label.setText("Listening…")
        self._mic_btn.setStyleSheet(self._mic_btn.styleSheet().replace(
            "border-color: #444444", "border-color: #00CC66"
        ))

        self._speech_thread = QThread()
        worker = SpeechWorker()
        worker.moveToThread(self._speech_thread)
        self._speech_thread.started.connect(worker.run)
        worker.text_ready.connect(self._on_speech_text)
        worker.error.connect(self._on_speech_error)
        worker.level.connect(self._animation.set_mic_level)
        # Cleanup
        worker.text_ready.connect(self._speech_thread.quit)
        worker.error.connect(self._speech_thread.quit)
        worker.text_ready.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._speech_thread.finished.connect(self._speech_thread.deleteLater)
        self._speech_thread.finished.connect(self._on_speech_done)
        self._speech_thread.start()

    def _on_speech_text(self, text: str):
        self._prompt.setText(text)
        self._on_submit(text)

    def _on_speech_error(self, msg: str):
        self._add_bubble(f"🎤 {msg}", is_user=False)

    def _on_speech_done(self):
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        # Reset mic button style
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 21px;
                font-size: 13.5pt;
            }
            QPushButton:hover { background-color: #3D3D3D; border-color: #0078D4; }
            QPushButton:pressed { background-color: #0078D4; }
        """)

    # ── Chat helpers ────────────────────────────────────────────────

    def _add_bubble(self, text: str, is_user: bool):
        row = QHBoxLayout()
        bubble = ChatBubble(text, is_user)
        if is_user:
            row.addStretch(1)          # 20% gutter
            row.addWidget(bubble, 4)   # 80% bubble
        else:
            row.addWidget(bubble, 4)   # 80% bubble
            row.addStretch(1)          # 20% gutter
        # Insert before the stretch at the end
        self._chat_layout.insertLayout(self._chat_layout.count() - 1, row)
        # Auto-scroll to bottom
        QTimer.singleShot(50, self._scroll_to_bottom)
        return bubble

    def _show_command(self, action_json: str):
        row = QHBoxLayout()
        bubble = CommandBubble(action_json)
        bubble.run_requested.connect(self._on_run_command)
        row.addWidget(bubble)
        row.addStretch()
        self._chat_layout.insertLayout(self._chat_layout.count() - 1, row)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _on_run_command(self, action_json: str):
        try:
            data = json.loads(action_json)
            command = data.get("command", "")
            args = data.get("args", {})
            self._add_bubble(f"▶ Running: {command} {' '.join(f'{k}={v}' for k, v in args.items())}".strip(), is_user=False)
            self.execute_command.emit(command, args)
        except Exception as e:
            self._add_bubble(f"⚠ Failed to run: {e}", is_user=False)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── TTS (speak AI responses) ────────────────────────────────────

    def _speak(self, text: str) -> None:
        """Speak *text* via TTS in a background thread if voice is enabled."""
        try:
            from ..ai.voice import VoiceConfig

            vcfg = VoiceConfig.from_config()
            if not vcfg.enabled:
                return
        except Exception:
            return

        self._animation.set_state(AIState.THINKING)
        self._status_label.setText("Speaking…")

        tts_thread = QThread()
        tts_worker = TTSWorker(text)
        tts_worker.moveToThread(tts_thread)
        tts_thread.started.connect(tts_worker.run)
        tts_worker.finished.connect(tts_thread.quit)
        tts_worker.error.connect(tts_thread.quit)
        tts_worker.finished.connect(self._on_tts_done)
        tts_worker.error.connect(lambda msg: self._on_tts_done())
        tts_worker.finished.connect(tts_worker.deleteLater)
        tts_worker.error.connect(tts_worker.deleteLater)
        tts_thread.finished.connect(tts_thread.deleteLater)
        tts_thread.start()
        # Store refs so they don't get GC'd
        self._tts_thread = tts_thread
        self._tts_worker = tts_worker

    def _on_tts_done(self) -> None:
        """Restore UI after TTS finishes."""
        self._animation.set_state(AIState.IDLE)
        self._status_label.setText("")
        # Auto-listen for next voice command if configured
        try:
            from ..ai.voice import VoiceConfig

            vcfg = VoiceConfig.from_config()
            if vcfg.auto_listen:
                QTimer.singleShot(300, self._on_mic_clicked)
        except Exception:
            pass
