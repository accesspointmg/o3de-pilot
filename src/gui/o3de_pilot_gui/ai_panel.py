# O3DE Pilot GUI — AI Panel (Dockable)
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Dockable AI panel that replaces the old AI tab.

The panel is always visible (collapsible, floatable, dockable) and contains:
- A session list sidebar on the left
- The active session's chat view on the right
- Session management controls (new session, reset, etc.)

The coordinator session is always present and is the default view.
Specialist sessions appear in the sidebar and can be viewed individually.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QStackedWidget, QSizePolicy, QMenu, QApplication,
)

from o3de_cli.ai.session import (
    AISession, SessionManager, SessionRole, ContextItem,
)
from o3de_cli.ai.coordinator import Coordinator, DispatchResult

from .session_chat_widget import SessionChatWidget
from .ai_animation import AIAnimationWidget, AIState


# ── AI Worker (provider call in background) ────────────────────────────────

class SessionAIWorker(QObject):
    """Run an AI provider call in a background thread."""
    finished = Signal(str, str)     # (session_id, response_text)
    token = Signal(str, str)        # (session_id, token_chunk)
    command = Signal(str, str)      # (session_id, action_json)
    error = Signal(str, str)        # (session_id, error_message)

    def __init__(self, session_id: str, provider, prompt: str,
                 classification_prompt: str):
        super().__init__()
        self._session_id = session_id
        self._provider = provider
        self._prompt = prompt
        self._classification_prompt = classification_prompt

    def run(self) -> None:
        try:
            response = self._provider.complete(self._classification_prompt)

            # Strip markdown code fences
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if len(lines) >= 2:
                    text = "\n".join(lines[1:-1] if lines[-1].strip() == "```"
                                    else lines[1:])

            # Try to parse as JSON command
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "command" in parsed:
                    cmd = parsed["command"]
                    if cmd == "chat":
                        resp_text = parsed.get("response", text)
                        self._stream_response(resp_text)
                        return
                    else:
                        self.command.emit(self._session_id, text)
                        return
            except (json.JSONDecodeError, KeyError):
                pass

            # Free-form text response
            self._stream_response(text)

        except Exception as e:
            self.error.emit(self._session_id, str(e))

    def _stream_response(self, text: str) -> None:
        """Simulate streaming by emitting sentence chunks."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for i, sentence in enumerate(sentences):
            if i > 0:
                self.token.emit(self._session_id, " ")
            self.token.emit(self._session_id, sentence)
        self.finished.emit(self._session_id, text)


# ── Session List Widget ───────────────────────────────────────────────────

class SessionListWidget(QWidget):
    """Sidebar showing all sessions with management controls."""

    session_selected = Signal(str)      # session_id
    new_session_requested = Signal()
    reset_requested = Signal(str)       # "coordinator", "all", or session_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(160)
        self.setAutoFillBackground(True)
        self.setStyleSheet("SessionListWidget { background-color: #1E1E1E; }")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("Sessions")
        header.setStyleSheet(
            "color: #AAAAAA; font-size: 9pt; font-weight: bold; "
            "padding: 4px 0px;"
        )
        layout.addWidget(header)

        # New Session button
        new_btn = QPushButton("+ New Session")
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-size: 9pt;
            }
            QPushButton:hover { background-color: #1A8AD4; }
        """)
        new_btn.clicked.connect(self.new_session_requested.emit)
        layout.addWidget(new_btn)

        # Session list
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                font-size: 9pt;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #2A2A2A;
            }
        """)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list, 1)

        # Reset menu button
        reset_btn = QPushButton("\u21BB Reset...")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #333333;
                color: #CCCCCC;
            }
        """)
        reset_menu = QMenu(self)
        reset_menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #444444;
            }
            QMenu::item:selected { background-color: #0078D4; }
        """)
        reset_menu.addAction("Reset Coordinator", lambda: self.reset_requested.emit("coordinator"))
        reset_menu.addSeparator()
        reset_menu.addAction("Reset All Sessions", lambda: self.reset_requested.emit("all"))
        reset_btn.setMenu(reset_menu)
        layout.addWidget(reset_btn)

    def update_sessions(self, sessions: list[AISession], active_id: str) -> None:
        """Refresh the session list."""
        self._list.blockSignals(True)
        self._list.clear()

        for session in sessions:
            icon = {
                SessionRole.COORDINATOR: "\U0001F9E0",  # brain
                SessionRole.CLI: "\u2328",       # keyboard
                SessionRole.BUILD: "\U0001F528",  # hammer
                SessionRole.EDITOR: "\U0001F3A8",  # palette
                SessionRole.GENERAL: "\U0001F4AC",  # speech bubble
            }.get(session.role, "\U0001F4AC")

            item = QListWidgetItem(f"{icon} {session.name}")
            item.setData(Qt.UserRole, session.id)
            self._list.addItem(item)
            if session.id == active_id:
                self._list.setCurrentItem(item)

        self._list.blockSignals(False)

    def _on_item_changed(self, current: QListWidgetItem, _prev) -> None:
        if current:
            session_id = current.data(Qt.UserRole)
            self.session_selected.emit(session_id)

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        session_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #444444;
            }
            QMenu::item:selected { background-color: #0078D4; }
        """)
        menu.addAction("Reset this session",
                        lambda: self.reset_requested.emit(session_id))
        menu.exec(self._list.mapToGlobal(pos))


# ── AI Panel (QDockWidget) ─────────────────────────────────────────────────

class AIPanel(QDockWidget):
    """Dockable AI panel with multi-session support.

    Signals
    -------
    execute_command(str, dict)
        Emitted when the user or AI triggers a CLI command.
    """

    execute_command = Signal(str, dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("AI", parent)
        self.setObjectName("AIPanel")

        # Dock widget properties
        self.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
            }
            QDockWidget::title {
                background-color: #2D2D2D;
                padding: 6px;
                text-align: left;
            }
        """)

        # Session model
        self._persist_dir = self._get_persist_dir()
        self._session_manager = SessionManager(persist_dir=self._persist_dir)
        self._session_manager.load_all()
        self._session_manager.setup_default_specialists()
        self._coordinator = Coordinator(self._session_manager)

        # Active session tracking
        self._active_session_id = self._coordinator.session.id
        self._chat_widgets: dict[str, SessionChatWidget] = {}

        # AI worker state
        self._ai_thread: QThread | None = None
        self._ai_worker: SessionAIWorker | None = None

        self._setup_ui()
        self._refresh_session_list()

    def _get_persist_dir(self) -> Path:
        from o3de_cli.core.paths import get_dot_o3de_path
        return get_dot_o3de_path() / "pilot" / "ai_sessions"

    # ── UI Setup ───────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        main = QWidget()
        main.setAutoFillBackground(True)
        main.setStyleSheet("background-color: #1E1E1E;")
        self.setWidget(main)

        outer = QVBoxLayout(main)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Animation widget (compact)
        self._animation = AIAnimationWidget()
        self._animation.setFixedHeight(60)
        self._animation.setAutoFillBackground(True)
        self._animation.setStyleSheet("background-color: #1E1E1E;")
        self._animation.set_state(AIState.IDLE)
        outer.addWidget(self._animation)

        # Splitter: session list | chat area
        splitter = QSplitter(Qt.Horizontal)
        splitter.setAutoFillBackground(True)
        splitter.setStyleSheet("""
            QSplitter {
                background-color: #1E1E1E;
            }
            QSplitter::handle {
                background-color: #333333;
                width: 2px;
            }
        """)

        # Left: session list
        self._session_list = SessionListWidget()
        self._session_list.session_selected.connect(self._on_session_selected)
        self._session_list.new_session_requested.connect(self._on_new_session)
        self._session_list.reset_requested.connect(self._on_reset)
        splitter.addWidget(self._session_list)

        # Right: stacked chat views
        self._chat_stack = QStackedWidget()
        self._chat_stack.setAutoFillBackground(True)
        self._chat_stack.setStyleSheet("background-color: #1E1E1E;")
        splitter.addWidget(self._chat_stack)

        splitter.setStretchFactor(0, 0)  # session list doesn't stretch
        splitter.setStretchFactor(1, 1)  # chat area stretches

        outer.addWidget(splitter, 1)

        # Status bar
        self._status = QLabel()
        self._status.setStyleSheet(
            "color: #888888; font-size: 8pt; padding: 4px 8px; "
            "background-color: #1A1A1A;"
        )
        self._update_status()
        outer.addWidget(self._status)

        # Create chat widgets for existing sessions
        for session in self._session_manager.list_sessions():
            self._get_or_create_chat_widget(session)

        self._switch_to_session(self._active_session_id)

    # ── Session management ─────────────────────────────────────────

    def _refresh_session_list(self) -> None:
        sessions = self._session_manager.list_sessions()
        # Sort: coordinator first, then by role, then by name
        sessions.sort(key=lambda s: (
            0 if s.role == SessionRole.COORDINATOR else 1,
            s.role.value,
            s.name,
        ))
        self._session_list.update_sessions(sessions, self._active_session_id)

    def _get_or_create_chat_widget(self, session: AISession) -> SessionChatWidget:
        if session.id not in self._chat_widgets:
            widget = SessionChatWidget(session)
            widget.prompt_submitted.connect(
                lambda text, sid=session.id: self._on_prompt_submitted(sid, text)
            )
            self._chat_widgets[session.id] = widget
            self._chat_stack.addWidget(widget)
        return self._chat_widgets[session.id]

    def _switch_to_session(self, session_id: str) -> None:
        session = self._session_manager.get_session(session_id)
        if not session:
            return
        widget = self._get_or_create_chat_widget(session)
        self._chat_stack.setCurrentWidget(widget)
        self._active_session_id = session_id
        self._update_status()

    def _on_session_selected(self, session_id: str) -> None:
        self._switch_to_session(session_id)

    def _on_new_session(self) -> None:
        """Reset coordinator (specialists keep context)."""
        coordinator = self._session_manager.reset_coordinator()
        # Remove old coordinator chat widget
        old_ids = [sid for sid, w in self._chat_widgets.items()
                   if w.session.role == SessionRole.COORDINATOR
                   and sid != coordinator.id]
        for sid in old_ids:
            w = self._chat_widgets.pop(sid)
            self._chat_stack.removeWidget(w)
            w.deleteLater()

        self._get_or_create_chat_widget(coordinator)
        self._active_session_id = coordinator.id
        self._refresh_session_list()
        self._switch_to_session(coordinator.id)

    def _on_reset(self, target: str) -> None:
        if target == "coordinator":
            self._on_new_session()
        elif target == "all":
            # Remove all chat widgets
            for w in self._chat_widgets.values():
                self._chat_stack.removeWidget(w)
                w.deleteLater()
            self._chat_widgets.clear()

            coordinator = self._session_manager.reset_all()
            self._session_manager.setup_default_specialists()

            for session in self._session_manager.list_sessions():
                self._get_or_create_chat_widget(session)
            self._active_session_id = coordinator.id
            self._refresh_session_list()
            self._switch_to_session(coordinator.id)
        else:
            # Reset specific session
            self._session_manager.reset_session(target)
            if target in self._chat_widgets:
                session = self._session_manager.get_session(target)
                if session:
                    self._chat_widgets[target].set_session(session)

    # ── User prompt handling ───────────────────────────────────────

    def _on_prompt_submitted(self, session_id: str, text: str) -> None:
        """Handle user input in any session."""
        session = self._session_manager.get_session(session_id)
        if not session:
            return

        chat = self._chat_widgets.get(session_id)
        if not chat:
            return

        # Add user message to model and view
        session.add_user_message(text)
        chat.add_user_message(text)

        # If this is the coordinator, try routing first
        if session.role == SessionRole.COORDINATOR:
            # Check for local command match first
            from o3de_cli.ai.command_router import match_command
            action = match_command(text)
            if action:
                action_json = json.dumps({
                    "command": action.command,
                    "args": action.args,
                    "description": action.description,
                })
                self._show_command(session_id, action_json)
                return

            # Route through coordinator
            dispatch = self._coordinator.route(text)
            if not dispatch.direct:
                # Specialist handles it — show routing info
                chat.add_assistant_message(
                    f"Routing to {dispatch.session.name}...",
                    source="Coordinator",
                )
                self._send_to_ai(dispatch.session.id, dispatch.prompt)
                return

        # Direct AI call for this session
        self._send_to_ai(session_id, text)

    def _send_to_ai(self, session_id: str, text: str) -> None:
        """Send a prompt to the AI provider for a specific session."""
        self._animation.set_state(AIState.THINKING)
        self._status.setText("Thinking...")

        try:
            from o3de_cli.ai.provider import get_ai_provider
            from o3de_cli.ai.command_router import get_ai_classification_prompt

            provider = get_ai_provider()
            classification_prompt = get_ai_classification_prompt(text)

            thread = QThread()
            worker = SessionAIWorker(session_id, provider, text,
                                     classification_prompt)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            # Connect signals to main-thread methods
            worker.finished.connect(self._on_ai_finished)
            worker.token.connect(self._on_ai_token)
            worker.command.connect(self._on_ai_command)
            worker.error.connect(self._on_ai_error)

            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(worker.deleteLater)

            # Wire cleanup
            for sig in (worker.finished, worker.command, worker.error):
                sig.connect(lambda *_: thread.quit())

            self._ai_thread = thread
            self._ai_worker = worker
            thread.start()

        except Exception as e:
            self._on_ai_error(session_id, str(e))

    # ── AI response handlers ──────────────────────────────────────

    def _on_ai_token(self, session_id: str, token: str) -> None:
        chat = self._chat_widgets.get(session_id)
        if chat:
            chat.add_streaming_token(token)

    def _on_ai_finished(self, session_id: str, text: str) -> None:
        session = self._session_manager.get_session(session_id)
        chat = self._chat_widgets.get(session_id)

        if session and chat:
            session.add_assistant_message(text)
            chat.finish_streaming()

            # If this was a specialist, report result to coordinator
            if session.role != SessionRole.COORDINATOR:
                self._coordinator.report_specialist_result(
                    session, text, auto_include=False,
                )
                coord_chat = self._chat_widgets.get(self._coordinator.session.id)
                if coord_chat:
                    # Show as context item in coordinator
                    items = self._coordinator.session.get_visible_context_items()
                    if items:
                        coord_chat.add_context_item(items[-1])

        self._animation.set_state(AIState.IDLE)
        self._update_status()
        self._session_manager.save_all()

    def _on_ai_command(self, session_id: str, action_json: str) -> None:
        self._animation.set_state(AIState.IDLE)
        self._show_command(session_id, action_json)

    def _on_ai_error(self, session_id: str, msg: str) -> None:
        chat = self._chat_widgets.get(session_id)
        if chat:
            chat.add_assistant_message(f"\u26A0 {msg}", source="Error")
        self._animation.set_state(AIState.IDLE)
        self._update_status()

    def _show_command(self, session_id: str, action_json: str) -> None:
        """Show a command action in the chat and offer to run it."""
        chat = self._chat_widgets.get(session_id)
        if not chat:
            return

        try:
            data = json.loads(action_json)
            cmd = data.get("command", "")
            args = data.get("args", {})
            desc = data.get("description", cmd)

            # Show as assistant message with run info
            args_str = " ".join(f"{v}" for v in args.values() if v)
            chat.add_assistant_message(
                f"\U0001F4CB {desc}\n\n`o3de-pilot {cmd} {args_str}`",
                source="Command",
            )

            # Emit for MainWindow to execute
            self.execute_command.emit(cmd, args)

        except Exception as e:
            chat.add_assistant_message(f"\u26A0 Bad command: {e}", source="Error")

    # ── Command output handling ────────────────────────────────────

    # ── Status ─────────────────────────────────────────────────────

    def _update_status(self) -> None:
        session = self._session_manager.get_session(self._active_session_id)
        if session:
            count = len(self._session_manager.list_sessions())
            msgs = len(session.messages)
            self._status.setText(
                f"{session.name} \u2022 {msgs} messages \u2022 {count} sessions"
            )

    # ── Public API for MainWindow ──────────────────────────────────

    def refresh_ai_state(self) -> None:
        """Called when AI settings change."""
        try:
            from o3de_cli.ai.provider import get_ai_provider
            provider = get_ai_provider()
            self._animation.set_state(AIState.IDLE)
        except Exception:
            self._animation.set_state(AIState.DISCONNECTED)

    def save_sessions(self) -> None:
        """Persist all sessions to disk and stop any running AI thread."""
        # Stop running AI thread before closing
        try:
            if self._ai_thread and self._ai_thread.isRunning():
                self._ai_thread.quit()
                self._ai_thread.wait(3000)
        except RuntimeError:
            pass  # C++ object already deleted
        self._session_manager.save_all()
