# O3DE Pilot GUI — AI Session Chat Widget
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Chat widget for a single AI session.

Displays conversation messages in a scrollable area.  User messages
appear as right-aligned bubbles; AI responses and command output appear
as left-aligned plain text blocks (no bubble styling).  Context items
show with include/exclude/delete controls.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QFrame,
)

from .ai_session import AISession, ContextItem, ContextItemState


# ── Prompt Input ───────────────────────────────────────────────────────────

class SessionPromptInput(QLineEdit):
    """Single-line prompt input with Enter-to-submit."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText("Message the coordinator...")
        self.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border-color: #0078D4;
            }
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            text = self.text().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


# ── Message Widgets ────────────────────────────────────────────────────────

class UserMessageWidget(QFrame):
    """Right-aligned user message bubble."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #0078D4;
                border-radius: 10px;
                padding: 8px 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #FFFFFF; font-size: 10pt; background: transparent;")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)


class AssistantMessageWidget(QFrame):
    """Left-aligned AI response — plain text, no bubble."""

    def __init__(self, text: str, source: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                padding: 4px 0px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        if source:
            src_label = QLabel(source)
            src_label.setStyleSheet(
                "color: #888888; font-size: 8pt; font-weight: bold; "
                "background: transparent;"
            )
            layout.addWidget(src_label)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setStyleSheet("color: #CCCCCC; font-size: 10pt; background: transparent;")
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._label)

    def append_text(self, text: str) -> None:
        self._label.setText(self._label.text() + text)


# ── Context Item Widget ───────────────────────────────────────────────────

class ContextItemWidget(QFrame):
    """Displays a context item with include/exclude/delete controls."""

    state_changed = Signal(str, str)  # (item_id, new_state)

    def __init__(self, item: ContextItem, parent: QWidget | None = None):
        super().__init__(parent)
        self._item = item
        self._setup_ui()
        self._update_style()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Source label (only if non-empty)
        if self._item.source:
            src = QLabel(f"[{self._item.source}]")
            src.setStyleSheet("color: #888888; font-size: 8pt; font-weight: bold;")
            layout.addWidget(src)

        # Content (summary or truncated)
        self._full_text = self._item.summary or self._item.content
        self._truncated = len(self._full_text) > 120
        self._expanded = False

        self._content_label = QLabel(self._display_text())
        self._content_label.setWordWrap(True)
        self._content_label.setStyleSheet("font-size: 9pt;")
        self._content_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self._content_label.setContextMenuPolicy(Qt.DefaultContextMenu)
        layout.addWidget(self._content_label, 1)

        # Expand/collapse button (only for truncated content)
        if self._truncated:
            self._expand_btn = QPushButton("\u25B6")  # right triangle
            self._expand_btn.setFixedSize(24, 24)
            self._expand_btn.setToolTip("Expand / Collapse")
            self._expand_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none;
                    font-size: 10pt; color: #888888;
                }
                QPushButton:hover { color: #CCCCCC; }
            """)
            self._expand_btn.clicked.connect(self._toggle_expand)
            layout.addWidget(self._expand_btn)

        # Include/Exclude toggle
        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setToolTip("Include in context / Exclude from context")
        self._toggle_btn.clicked.connect(self._toggle_state)
        layout.addWidget(self._toggle_btn)

        # Delete button
        delete_btn = QPushButton("\U0001F5D1")  # wastebasket
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("Remove from view")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                font-size: 12pt; color: #888888;
            }
            QPushButton:hover { color: #FF4444; }
        """)
        delete_btn.clicked.connect(self._delete)
        layout.addWidget(delete_btn)

    def _display_text(self) -> str:
        if self._expanded or not self._truncated:
            return self._full_text
        return self._full_text[:117] + "..."

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self._content_label.setText(self._display_text())
        self._expand_btn.setText("\u25BC" if self._expanded else "\u25B6")

    def _toggle_state(self) -> None:
        if self._item.state == ContextItemState.INCLUDED:
            self._item.exclude()
        else:
            self._item.include()
        self._update_style()
        self.state_changed.emit(self._item.id, self._item.state.value)

    def _delete(self) -> None:
        self._item.delete()
        self.state_changed.emit(self._item.id, self._item.state.value)
        self.setVisible(False)

    def _update_style(self) -> None:
        if self._item.state == ContextItemState.INCLUDED:
            self.setStyleSheet("""
                QFrame {
                    background-color: #1E3A1E;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
            self._content_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
            self._toggle_btn.setText("\u2713")  # checkmark
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #44AA44; border: none; border-radius: 4px;
                    color: white; font-weight: bold; font-size: 10pt;
                }
                QPushButton:hover { background: #55BB55; }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2A2A2A;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
            self._content_label.setStyleSheet("color: #777777; font-size: 9pt;")
            self._toggle_btn.setText("\u2715")  # X mark
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #555555; border: none; border-radius: 4px;
                    color: #AAAAAA; font-size: 10pt;
                }
                QPushButton:hover { background: #666666; }
            """)


# ── Session Chat Widget ───────────────────────────────────────────────────

class SessionChatWidget(QWidget):
    """Chat view for a single AI session.

    Displays messages and context items with a prompt input at the bottom.
    User messages are right-aligned bubbles.  AI responses are plain
    left-aligned text blocks.  Context items appear with include/exclude
    controls.
    """

    prompt_submitted = Signal(str)  # user typed a message

    def __init__(self, session: AISession, parent: QWidget | None = None):
        super().__init__(parent)
        self._session = session
        self._streaming_widget: AssistantMessageWidget | None = None
        self._setup_ui()
        self._populate_from_session()

    @property
    def session(self) -> AISession:
        return self._session

    def set_session(self, session: AISession) -> None:
        """Switch to a different session, repopulating the view."""
        self._session = session
        self._streaming_widget = None
        self._populate_from_session()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1E1E1E;
                border: none;
            }
            QScrollBar:vertical {
                background: #1E1E1E;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #444444;
                border-radius: 4px;
                min-height: 20px;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background-color: #1E1E1E;")
        self._chat_layout = QVBoxLayout(self._container)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch(1)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

        # Input area
        input_row = QHBoxLayout()
        input_row.setContentsMargins(8, 4, 8, 8)
        input_row.setSpacing(4)

        self._prompt = SessionPromptInput()
        self._prompt.submitted.connect(self.prompt_submitted.emit)
        input_row.addWidget(self._prompt, 1)

        send_btn = QPushButton("\u27A4")  # arrow
        send_btn.setFixedSize(36, 36)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14pt;
            }
            QPushButton:hover { background-color: #1A8AD4; }
        """)
        send_btn.clicked.connect(self._on_send)
        input_row.addWidget(send_btn)

        layout.addLayout(input_row)

    def _on_send(self) -> None:
        text = self._prompt.text().strip()
        if text:
            self._prompt.clear()
            self.prompt_submitted.emit(text)

    # ── Population ─────────────────────────────────────────────────

    def _populate_from_session(self) -> None:
        """Rebuild the chat view from the session's current state."""
        # Clear existing widgets (except the stretch)
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add messages
        for msg in self._session.messages:
            if msg.role == "user":
                self._add_user_message(msg.content)
            elif msg.role == "assistant":
                self._add_assistant_message(msg.content)

        # Add visible context items
        for ci in self._session.get_visible_context_items():
            self._add_context_item_widget(ci)

        self._scroll_to_bottom()

    # ── Adding messages ────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        """Add a user message to the view."""
        self._add_user_message(text)
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str, source: str = "") -> None:
        """Add an AI response to the view."""
        self._streaming_widget = None
        self._add_assistant_message(text, source)
        self._scroll_to_bottom()

    def add_streaming_token(self, token: str) -> None:
        """Append a token to the current streaming response."""
        if self._streaming_widget is None:
            self._streaming_widget = AssistantMessageWidget("")
            idx = self._chat_layout.count() - 1  # before stretch
            self._chat_layout.insertWidget(idx, self._streaming_widget)
        self._streaming_widget.append_text(token)
        self._scroll_to_bottom()

    def finish_streaming(self) -> None:
        """Mark the current streaming response as complete."""
        self._streaming_widget = None

    def add_context_item(self, item: ContextItem) -> None:
        """Add a context item widget to the view."""
        self._add_context_item_widget(item)
        self._scroll_to_bottom()

    # ── Internal widget insertion ──────────────────────────────────

    def _add_user_message(self, text: str) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        bubble = UserMessageWidget(text)
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        bubble.setMaximumWidth(500)
        row.addWidget(bubble)

        wrapper = QWidget()
        wrapper.setLayout(row)
        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, wrapper)

    def _add_assistant_message(self, text: str, source: str = "") -> None:
        widget = AssistantMessageWidget(text, source)
        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, widget)

    def _add_context_item_widget(self, item: ContextItem) -> None:
        widget = ContextItemWidget(item)
        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, widget)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
